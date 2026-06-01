"""
Chat-to-SQL translator.

Given a natural-language message and live schema context, asks Ollama to
produce either:
  - A SELECT SQL query (executed immediately)
  - A mutation SQL query (requires user confirmation)
  - A plain text answer (no SQL needed)

The LLM is prompted to wrap SQL in ```sql fences and prefix mutations
with the word MUTATION so we can detect them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from kgx.db import KnowledgeGraphDB
from .client import OllamaClient

_SYSTEM_TEMPLATE = """\
You are a SQL assistant for a local knowledge graph database backed by SQLite.

## Schema

Tables:
  entities(id TEXT PRIMARY KEY, type TEXT, name TEXT, metadata TEXT, created_at TEXT, updated_at TEXT)
  relationships(source_id TEXT, rel_type TEXT, target_id TEXT, metadata TEXT, created_at TEXT)
  aliases(alias TEXT PRIMARY KEY, entity_id TEXT)

The `metadata` column is a JSON string. Use json_extract() to query it.
Example: json_extract(metadata, '$.orcid')

## Live schema snapshot

{schema_context}

## Rules

1. If the user asks a read-only question, respond with a single ```sql SELECT ... ``` block.
2. If the user asks to modify data, respond with MUTATION: followed by a ```sql ... ``` block.
3. If the question does not need SQL (e.g. "what is X?", "help"), answer in plain text.
4. Never add explanation before or after a SQL block unless the user asks for it.
5. Use only tables and columns from the schema above. Do not hallucinate tables.
6. Keep queries simple and correct for SQLite.
"""


@dataclass
class ChatResult:
    intent: str          # "query" | "mutation" | "answer"
    content: str         # raw LLM reply
    sql: str | None = None
    results: list[dict] = field(default_factory=list)
    error: str | None = None


class ChatToSQL:
    def __init__(self, db: KnowledgeGraphDB, llm: OllamaClient):
        self.db = db
        self.llm = llm

    def _schema_context(self) -> str:
        """Build a compact schema snapshot from the live DB."""
        lines = []
        try:
            types = self.db.entity_types()
            if types:
                lines.append("Entity types (name, count):")
                for t in types:
                    lines.append(f"  {t['type']} ({t['count']})")
        except Exception:
            pass
        try:
            rels = self.db.relationship_types()
            if rels:
                lines.append("Relationship types (rel_type, count):")
                for r in rels:
                    lines.append(f"  {r['rel_type']} ({r['count']})")
        except Exception:
            pass
        try:
            keys = self.db.metadata_keys()
            if keys:
                lines.append(f"Common metadata keys: {', '.join(keys[:20])}")
        except Exception:
            pass
        return "\n".join(lines) if lines else "No schema data available."

    def ask(self, message: str, history: list[dict] | None = None) -> ChatResult:
        """
        Translate message → SQL or answer.

        history: list of {role, content} prior turns for multi-turn context.
        """
        system = _SYSTEM_TEMPLATE.format(schema_context=self._schema_context())
        messages: list[dict] = [{"role": "system", "content": system}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": message})

        try:
            reply = self.llm.chat(messages)
        except Exception as e:
            return ChatResult(intent="answer", content="", error=f"LLM error: {e}")

        return self._parse(reply)

    def _parse(self, reply: str) -> ChatResult:
        """Classify LLM reply and execute if it's a SELECT."""
        # Find SQL fences
        sql_match = re.search(r"```sql\s*(.*?)\s*```", reply, re.DOTALL | re.IGNORECASE)

        if not sql_match:
            # No SQL — plain answer
            return ChatResult(intent="answer", content=reply)

        sql = sql_match.group(1).strip()

        # Detect mutation intent: explicit "MUTATION:" prefix or DML keywords
        is_mutation = (
            "MUTATION:" in reply.upper()
            or re.match(r"^\s*(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER)\b", sql, re.IGNORECASE)
        )

        if is_mutation:
            return ChatResult(intent="mutation", content=reply, sql=sql)

        # SELECT — execute immediately
        try:
            results = self.db.execute_read(sql)
            return ChatResult(intent="query", content=reply, sql=sql, results=results)
        except Exception as e:
            return ChatResult(
                intent="query", content=reply, sql=sql,
                error=f"Query failed: {e}"
            )
