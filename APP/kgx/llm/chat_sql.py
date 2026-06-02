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

Core tables:
  entities(id TEXT PK, type TEXT, name TEXT, metadata TEXT [JSON], created_at TEXT, updated_at TEXT)
  relationships(source_id TEXT, rel_type TEXT, target_id TEXT, metadata TEXT [JSON], PRIMARY KEY(source_id, rel_type, target_id))
  aliases(alias TEXT PK, entity_id TEXT FK→entities)

Rich content tables:
  entity_topics(entity_id TEXT, topic TEXT, PK(entity_id, topic))
  snippets(id INTEGER PK, entity_id TEXT, ref_id TEXT, ref_type TEXT, text TEXT, ordinal INTEGER)
  research_interests(entity_id TEXT, interest TEXT, ordinal INTEGER, PK(entity_id, interest))
  sources(id INTEGER PK, entity_id TEXT, source_name TEXT, url TEXT, retrieved_at TEXT)
  contact_info(entity_id TEXT, field TEXT, value TEXT, PK(entity_id, field))
    — field values: 'email', 'phone', 'orcid', 'website', 'department', 'title'

The `metadata` column is a JSON string. Use json_extract() to query it.
Example: json_extract(metadata, '$.orcid')

## Live schema snapshot

{schema_context}

## Common query patterns

Count edges per node (degree):
```sql
SELECT e.name, e.type, COUNT(*) AS degree
FROM entities e
JOIN relationships r ON e.id = r.source_id OR e.id = r.target_id
GROUP BY e.id
HAVING degree > 10
ORDER BY degree DESC
```

Find nodes tagged with a topic:
```sql
SELECT e.name, e.type, t.topic
FROM entities e JOIN entity_topics t ON e.id = t.entity_id
WHERE t.topic LIKE '%genomics%'
```

Find a person's contact info:
```sql
SELECT e.name, c.field, c.value
FROM entities e JOIN contact_info c ON e.id = c.entity_id
WHERE e.name LIKE '%Smith%'
```

Filter query (hide nodes with fewer than 15 edges):
```sql
SELECT e.id FROM entities e
WHERE (SELECT COUNT(*) FROM relationships r WHERE r.source_id = e.id OR r.target_id = e.id) < 15
```

## Rules

1. If the user asks a read-only question, respond ONLY with a single ```sql SELECT ... ``` block. No explanation.
2. If the user asks to modify data, respond with MUTATION: followed by a ```sql ... ``` block.
3. If the user asks about the schema, available types, fields, or what they can query — answer in PLAIN TEXT using the live schema snapshot above. List the actual values. Be concise and helpful.
4. IMPORTANT: When responding with SQL, do NOT add any text before or after the SQL block. Just the fenced SQL.
5. Use only tables and columns from the schema above. Do not hallucinate tables.
6. Keep queries simple and correct for SQLite.
7. ALWAYS include `e.id` as the first column in every SELECT from entities. The UI uses it for filtering and navigation. Example: `SELECT e.id, e.name, e.type FROM entities e ...`
8. When the user says "edges", "connections", or "links", they mean rows in the `relationships` table. Count them with JOIN.
9. When the user says "tagged" they mean having rows in `entity_topics`.
10. "Order by" options for entities: name, type, created_at, updated_at, degree (via COUNT of relationships), topic count, metadata fields via json_extract.
11. When the user asks for a "filter" or says "hide nodes", return `SELECT e.id FROM entities e WHERE ...`. The UI will detect the `id` column and offer to apply it as a graph filter.
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
                lines.append("Entity types (type → count):")
                for t in types:
                    lines.append(f"  {t['type']} → {t['count']}")
        except Exception:
            pass
        try:
            rels = self.db.relationship_types()
            if rels:
                lines.append("Relationship types (rel_type → count):")
                for r in rels:
                    lines.append(f"  {r['rel_type']} → {r['count']}")
        except Exception:
            pass
        try:
            # Metadata keys (compact — top 3 types only to save context)
            for etype in [t['type'] for t in (types or [])[:3]]:
                keys = self.db.metadata_keys(etype)
                if keys:
                    lines.append(f"Metadata keys for '{etype}': {', '.join(keys[:10])}")
        except Exception:
            pass
        try:
            topics = self.db.conn.execute(
                "SELECT topic, COUNT(*) as cnt FROM entity_topics GROUP BY topic ORDER BY cnt DESC LIMIT 10"
            ).fetchall()
            if topics:
                lines.append("Topics in entity_topics (topic → entity count):")
                for r in topics:
                    lines.append(f"  {r[0]} → {r[1]}")
        except Exception:
            pass
        try:
            fields = self.db.conn.execute(
                "SELECT DISTINCT field FROM contact_info ORDER BY field"
            ).fetchall()
            if fields:
                lines.append(f"Contact info fields: {', '.join(r[0] for r in fields)}")
        except Exception:
            pass
        return "\n".join(lines) if lines else "No schema data available."

    # Keywords that indicate a schema/meta question (no SQL needed)
    _SCHEMA_KEYWORDS = [
        "what types", "which types", "what are the types",
        "what can i", "what else can i", "order by", "order it by",
        "sort by", "what fields", "what columns", "what tables",
        "what topics", "what relationships", "what metadata",
        "help", "what can you do", "how do i",
    ]

    def _try_fast_answer(self, message: str) -> ChatResult | None:
        """Answer schema questions instantly without calling the LLM."""
        low = message.lower().strip()

        for kw in self._SCHEMA_KEYWORDS:
            if kw in low:
                break
        else:
            return None

        ctx = self._schema_context()
        parts = []

        if any(w in low for w in ["type", "types"]):
            try:
                types = self.db.entity_types()
                parts.append("**Entity types:**\n" + "\n".join(
                    f"  {t['type']} ({t['count']})" for t in types))
            except Exception:
                pass
            try:
                rels = self.db.relationship_types()
                parts.append("**Relationship types:**\n" + "\n".join(
                    f"  {r['rel_type']} ({r['count']})" for r in rels))
            except Exception:
                pass

        if any(w in low for w in ["order", "sort", "field", "column"]):
            parts.append(
                "**You can order/sort entities by:**\n"
                "  name, type, created_at, updated_at\n"
                "  degree (COUNT of relationships via JOIN)\n"
                "  topic count (COUNT of entity_topics)\n"
                "  any metadata field via json_extract(metadata, '$.key')\n"
            )
            # Show available metadata keys
            try:
                types = self.db.entity_types()
                for t in (types or []):
                    keys = self.db.metadata_keys(t['type'])
                    if keys:
                        parts.append(f"  Metadata keys for '{t['type']}': {', '.join(keys[:15])}")
            except Exception:
                pass

        if any(w in low for w in ["topic", "topics"]):
            try:
                topics = self.db.conn.execute(
                    "SELECT topic, COUNT(*) as cnt FROM entity_topics GROUP BY topic ORDER BY cnt DESC LIMIT 30"
                ).fetchall()
                if topics:
                    parts.append("**Topics:**\n" + "\n".join(
                        f"  {r[0]} ({r[1]})" for r in topics))
            except Exception:
                pass

        if any(w in low for w in ["help", "what can"]):
            parts.append(
                "**I can help you query the knowledge graph.** Try:\n"
                "  - \"show all persons\" or \"list signals\"\n"
                "  - \"nodes with > 10 edges\"\n"
                "  - \"tagged nodes about genomics\"\n"
                "  - \"what types are there?\"\n"
                "  - \"find person named Smith\"\n"
                "  - \"publications by year\"\n\n"
                "**Filters** (returns IDs → apply to graph):\n"
                "  - \"filter out nodes with fewer than 5 edges\"\n"
                "  - \"hide persons not tagged with any topic\"\n"
                "  When results have an `id` column, you can **Hide** those nodes or **Save as sidebar filter**."
            )

        if parts:
            return ChatResult(intent="answer", content="\n\n".join(parts))
        return None

    def ask(self, message: str, history: list[dict] | None = None) -> ChatResult:
        """
        Translate message → SQL or answer.

        history: list of {role, content} prior turns for multi-turn context.
        """
        # Fast path: answer schema/meta questions directly from DB
        fast = self._try_fast_answer(message)
        if fast:
            return fast

        system = _SYSTEM_TEMPLATE.format(schema_context=self._schema_context())
        messages: list[dict] = [{"role": "system", "content": system}]
        if history:
            # Only keep last 4 turns (2 exchanges) to avoid filling context window
            messages.extend(history[-4:])
        # Append /no_think to suppress qwen3's <think> reasoning (faster responses)
        messages.append({"role": "user", "content": message + " /no_think"})

        try:
            reply = self.llm.chat(messages)
        except Exception as e:
            return ChatResult(intent="answer", content="", error=f"LLM error: {e}")

        return self._parse(reply)

    def _parse(self, reply: str) -> ChatResult:
        """Classify LLM reply and execute if it's a SELECT."""
        # Strip <think>...</think> blocks (qwen3 reasoning tokens)
        reply = re.sub(r"<think>.*?</think>", "", reply, flags=re.DOTALL).strip()

        # Strip all backtick fences (```, ```sql, stray `, etc.) to get clean text
        cleaned = re.sub(r"`{1,3}(?:sql)?\s*", "", reply, flags=re.IGNORECASE).strip()

        # Find SQL statement in the cleaned text
        sql_match = re.search(
            r"((?:SELECT|INSERT|UPDATE|DELETE|WITH|CREATE|ALTER|DROP)\b.*)",
            cleaned, re.DOTALL | re.IGNORECASE
        )

        if not sql_match:
            return ChatResult(intent="answer", content=reply)

        sql = sql_match.group(1).strip()
        # Remove any trailing non-SQL text after the statement
        # (e.g. LLM explanation after the query)
        sql = re.split(r"\n\s*\n(?=[A-Z][a-z])", sql, maxsplit=1)[0].strip()

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
