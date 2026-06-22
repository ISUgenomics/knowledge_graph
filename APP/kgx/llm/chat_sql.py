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
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from kgx.db import KnowledgeGraphDB
from .client import OllamaClient
from .modules.base import ChatModule

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

The `metadata` column is a JSON string. Use json_extract() to query it.
Example: json_extract(metadata, '$.orcid')

## Live schema snapshot

{schema_context}

Use the typed relationship patterns in the live schema snapshot to choose the correct join path. Do not assume a relationship starts from the entity type named in the user's question.

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
WHERE t.topic LIKE '%example-topic%'
```

Find an entity's contact info:
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
12. If a user asks for entities connected through several semantic layers, follow the typed relationship patterns step by step. Example shape: `gene -> transcript -> protein -> hit -> tag`.
13. Preserve the user's requested result entity type. If the user asks for genes, proteins, tags, publications, or another specific entity type, the final SELECT rows must be that type even if the evidence is attached on a downstream or upstream node.
"""


@dataclass
class ChatResult:
    intent: str          # "query" | "mutation" | "answer"
    content: str         # raw LLM reply
    sql: str | None = None
    results: list[dict] = field(default_factory=list)
    error: str | None = None
    debug: list[dict[str, Any]] = field(default_factory=list)


class ChatToSQL:
    def __init__(self, db: KnowledgeGraphDB, llm: OllamaClient, module: ChatModule | None = None):
        self.db = db
        self.llm = llm
        self.module = module

    def _schema_context(self) -> str:
        """Build a compact schema snapshot from the live DB."""
        lines = []
        types: list[dict[str, Any]] = []
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
            # Metadata keys per type (trimmed per type to limit context)
            for etype in [t["type"] for t in (types or [])]:
                keys = self.db.metadata_keys(etype)
                if keys:
                    lines.append(f"Metadata keys for '{etype}': {', '.join(keys[:12])}")
        except Exception:
            pass
        if self.module:
            try:
                lines.extend(self.module.schema_context_lines(self))
            except Exception:
                pass
        try:
            typed_patterns = self.db.conn.execute(
                """
                SELECT source.type AS source_type,
                       r.rel_type AS rel_type,
                       target.type AS target_type,
                       COUNT(*) AS cnt
                FROM relationships r
                JOIN entities source ON source.id = r.source_id
                JOIN entities target ON target.id = r.target_id
                GROUP BY source.type, r.rel_type, target.type
                ORDER BY cnt DESC, source.type, r.rel_type, target.type
                LIMIT 40
                """
            ).fetchall()
            if typed_patterns:
                lines.append("Typed relationship patterns (source_type -rel_type-> target_type → count):")
                for row in typed_patterns:
                    lines.append(
                        f"  {row['source_type']} -{row['rel_type']}-> {row['target_type']} → {row['cnt']}"
                    )
        except Exception:
            pass
        try:
            tag_roots = self.db.conn.execute(
                """
                SELECT child.id, child.name, COUNT(grandchild.id) AS child_count
                FROM entities child
                LEFT JOIN relationships broader
                  ON broader.source_id = child.id
                 AND broader.rel_type = 'BROADER'
                LEFT JOIN entities parent
                  ON parent.id = broader.target_id
                LEFT JOIN relationships broader2
                  ON broader2.target_id = child.id
                 AND broader2.rel_type = 'BROADER'
                LEFT JOIN entities grandchild
                  ON grandchild.id = broader2.source_id
                WHERE child.type = 'tag'
                  AND parent.id IS NULL
                GROUP BY child.id, child.name
                ORDER BY child.name
                LIMIT 20
                """
            ).fetchall()
            if tag_roots:
                lines.append("Top-level tag roots (tag → immediate child count):")
                for row in tag_roots:
                    lines.append(f"  {row['name']} ({row['id']}) → {row['child_count']}")
        except Exception:
            pass
        try:
            tag_examples = self.db.conn.execute(
                """
                SELECT parent.id AS parent_id,
                       parent.name AS parent_name,
                       child.name AS child_name
                FROM relationships r
                JOIN entities child ON child.id = r.source_id AND child.type = 'tag'
                JOIN entities parent ON parent.id = r.target_id AND parent.type = 'tag'
                WHERE r.rel_type = 'BROADER'
                ORDER BY parent.name, child.name
                LIMIT 30
                """
            ).fetchall()
            if tag_examples:
                lines.append("Tag hierarchy examples (child -> parent):")
                for row in tag_examples:
                    lines.append(f"  {row['child_name']} -> {row['parent_name']} ({row['parent_id']})")
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

    @staticmethod
    def _type_name_variants(entity_type: str) -> set[str]:
        text = str(entity_type or "").strip().lower()
        if not text:
            return set()
        variants = {text, text.replace("_", " ")}
        if text.endswith("y"):
            variants.add(f"{text[:-1]}ies")
            variants.add(f"{text[:-1]}y".replace("_", " "))
            variants.add(f"{text[:-1]}ies".replace("_", " "))
        elif text.endswith("s"):
            variants.add(f"{text}es")
            variants.add(f"{text}es".replace("_", " "))
        else:
            variants.add(f"{text}s")
            variants.add(f"{text}s".replace("_", " "))
        return {item for item in variants if item}

    def _requested_result_types(self, message: str) -> list[str]:
        low = f" {message.lower()} "
        requested: list[str] = []
        try:
            types = [row["type"] for row in self.db.entity_types()]
        except Exception:
            types = []
        for entity_type in types:
            for variant in self._type_name_variants(entity_type):
                if f" {variant} " in low:
                    requested.append(entity_type)
                    break
        # Preserve DB type order and deduplicate.
        seen: set[str] = set()
        ordered: list[str] = []
        for entity_type in requested:
            if entity_type in seen:
                continue
            seen.add(entity_type)
            ordered.append(entity_type)
        return ordered

    def _typed_rel_patterns(self) -> set[tuple[str, str, str]]:
        rows = self.db.conn.execute(
            """
            SELECT DISTINCT source.type AS source_type,
                            r.rel_type AS rel_type,
                            target.type AS target_type
            FROM relationships r
            JOIN entities source ON source.id = r.source_id
            JOIN entities target ON target.id = r.target_id
            """
        ).fetchall()
        return {(row["source_type"], row["rel_type"], row["target_type"]) for row in rows}

    def _shortest_type_path(self, start_type: str, end_type: str) -> list[tuple[str, str, str]]:
        if not start_type or not end_type:
            return []
        if start_type == end_type:
            return []
        patterns = self._typed_rel_patterns()
        neighbors: dict[str, list[tuple[str, str, str]]] = {}
        for src, rel, dst in patterns:
            neighbors.setdefault(src, []).append((src, rel, dst))
        queue: deque[tuple[str, list[tuple[str, str, str]]]] = deque([(start_type, [])])
        seen = {start_type}
        while queue:
            current, path = queue.popleft()
            for edge in neighbors.get(current, []):
                _, _, dst = edge
                if dst in seen:
                    continue
                new_path = path + [edge]
                if dst == end_type:
                    return new_path
                seen.add(dst)
                queue.append((dst, new_path))
        return []

    def _entity_name_matches(self, name: str) -> list[tuple[str, str, str]]:
        rows = self.db.conn.execute(
            """
            SELECT id, type, name
            FROM entities
            WHERE lower(name) = lower(?)
            ORDER BY type, id
            LIMIT 20
            """,
            (name,),
        ).fetchall()
        return [(row["id"], row["type"], row["name"]) for row in rows]

    @staticmethod
    def _message_candidate_phrases(message: str) -> list[str]:
        cleaned = re.sub(r"\s+", " ", str(message or "")).strip()
        if not cleaned:
            return []
        quoted = re.findall(r'"([^"]+)"|\'([^\']+)\'', cleaned)
        candidates: list[str] = []
        for a, b in quoted:
            text = (a or b).strip()
            if text:
                candidates.append(text)
        words = re.findall(r"[A-Za-z0-9_.-]+", cleaned)
        stop = {
            "select", "show", "list", "find", "all", "that", "have", "has", "with", "for",
            "the", "a", "an", "and", "or", "from", "to", "of", "in", "on", "by", "broad",
            "homology", "hits", "hit", "genes", "gene", "proteins", "protein", "tags", "tag",
            "comparative", "scope",
        }
        lowered = [w.lower() for w in words]
        n = len(words)
        for i in range(n):
            for size in range(5, 0, -1):
                if i + size > n:
                    continue
                span = words[i:i + size]
                span_low = lowered[i:i + size]
                if all(token in stop for token in span_low):
                    continue
                # Prefer proper-looking phrases or suffix phrases after "for".
                if any(token[:1].isupper() for token in span):
                    candidates.append(" ".join(span))
        seen: set[str] = set()
        ordered: list[str] = []
        for item in candidates:
            key = item.lower()
            if key in seen:
                continue
            seen.add(key)
            ordered.append(item)
        return ordered

    def _message_entity_match_hints(self, message: str) -> list[str]:
        hints: list[str] = []
        seen: set[tuple[str, str]] = set()
        for phrase in self._message_candidate_phrases(message):
            matches = self._entity_name_matches(phrase)
            if not matches:
                continue
            types = sorted({match_type for _, match_type, _ in matches})
            key = (phrase.lower(), ",".join(types))
            if key in seen:
                continue
            seen.add(key)
            hints.append(
                f"Exact entity-name match in user request: '{phrase}' exists as type(s): {', '.join(types)}."
            )
        return hints

    def _validate_sql_against_schema(self, sql: str, requested_types: list[str], message: str = "") -> str | None:
        """
        Catch a common NL→SQL failure mode:
        the model selects one entity type but applies a relationship as if it
        started directly from that type when the live DB says otherwise.
        """
        if not sql or not requested_types:
            return None
        message_low = str(message or "").lower()
        if not re.search(r"\bfrom\s+entities\s+e\b", sql, re.IGNORECASE):
            return None

        type_match = re.search(r"e\.type\s*=\s*'([^']+)'", sql, re.IGNORECASE)
        rel_match = re.search(r"r\.rel_type\s*=\s*'([^']+)'", sql, re.IGNORECASE)
        join_match = re.search(
            r"join\s+relationships\s+r\s+on\s+e\.id\s*=\s*r\.(source_id|target_id)",
            sql,
            re.IGNORECASE,
        )
        if not type_match:
            return None

        selected_type = type_match.group(1)
        if requested_types and selected_type not in requested_types:
            bridge_bits = []
            for requested_type in requested_types[:3]:
                path = self._shortest_type_path(requested_type, selected_type)
                if path:
                    rendered = " ; ".join(f"{src} -{rel}-> {dst}" for src, rel, dst in path)
                    bridge_bits.append(f"To reach '{selected_type}' from '{requested_type}': {rendered}")
            bridge_text = f" {' '.join(bridge_bits)}" if bridge_bits else ""
            return (
                f"Wrong result type: the SQL returns '{selected_type}' rows, but the user requested "
                f"'{', '.join(requested_types)}'. Keep the user's requested result type in the final SELECT rows."
                f"{bridge_text}"
            )

        metadata_owners: dict[str, set[str]] = {}
        try:
            for row in self.db.entity_types():
                etype = row["type"]
                metadata_owners[etype] = set(self.db.metadata_keys(etype))
        except Exception:
            metadata_owners = {}

        for field_name in re.findall(r"json_extract\(\s*e\.metadata\s*,\s*'\$\.([A-Za-z0-9_]+)", sql, re.IGNORECASE):
            owner_keys = metadata_owners.get(selected_type, set())
            if field_name in owner_keys:
                continue
            other_types = sorted(
                etype for etype, keys in metadata_owners.items()
                if field_name in keys and etype != selected_type
            )
            if other_types:
                bridge_bits = []
                for owner_type in other_types[:3]:
                    path = self._shortest_type_path(selected_type, owner_type)
                    if path:
                        rendered = " ; ".join(f"{src} -{rel}-> {dst}" for src, rel, dst in path)
                        bridge_bits.append(f"Path to '{owner_type}': {rendered}")
                bridge_text = f" {' '.join(bridge_bits)}" if bridge_bits else ""
                return (
                    f"Wrong metadata owner: field '{field_name}' is not stored on '{selected_type}' rows. "
                    f"In the live DB it exists on: {', '.join(other_types)}. "
                    f"Keep the requested result type in the final SELECT rows, but join to the related entity type "
                    f"that owns '{field_name}' before filtering on that metadata.{bridge_text}"
                )

        if not (rel_match and join_match):
            rel_match = re.search(r"r\.rel_type\s*=\s*'([^']+)'", sql, re.IGNORECASE)
            if not rel_match:
                return None

        rel_type = rel_match.group(1)
        rel_side = join_match.group(1).lower() if join_match else "source_id"
        patterns = self._typed_rel_patterns()

        if rel_side == "source_id":
            valid = any(src == selected_type and rel == rel_type for src, rel, _ in patterns)
            if not valid:
                valid_sources = sorted({src for src, rel, _ in patterns if rel == rel_type})
                if valid_sources:
                    bridge_bits = []
                    for valid_source in valid_sources[:3]:
                        path = self._shortest_type_path(selected_type, valid_source)
                        if path:
                            rendered = " ; ".join(f"{src} -{rel}-> {dst}" for src, rel, dst in path)
                            bridge_bits.append(f"To reach '{valid_source}' from '{selected_type}': {rendered}")
                    bridge_text = f" {' '.join(bridge_bits)}" if bridge_bits else ""
                    return (
                        f"Invalid direct join: selected type '{selected_type}' does not originate relationship "
                        f"'{rel_type}'. In the live DB, '{rel_type}' starts from: {', '.join(valid_sources)}. "
                        f"Keep the requested result type, but bridge through the typed path instead of joining "
                        f"that relationship directly from '{selected_type}'.{bridge_text}"
                    )
        else:
            valid = any(dst == selected_type and rel == rel_type for _, rel, dst in patterns)
            if not valid:
                valid_targets = sorted({dst for _, rel, dst in patterns if rel == rel_type})
                if valid_targets:
                    bridge_bits = []
                    for valid_target in valid_targets[:3]:
                        path = self._shortest_type_path(valid_target, selected_type)
                        if path:
                            rendered = " ; ".join(f"{src} -{rel}-> {dst}" for src, rel, dst in path)
                            bridge_bits.append(f"To return '{selected_type}' from '{valid_target}': {rendered}")
                    bridge_text = f" {' '.join(bridge_bits)}" if bridge_bits else ""
                    return (
                        f"Invalid direct join: selected type '{selected_type}' is not a valid target for "
                        f"relationship '{rel_type}'. In the live DB, '{rel_type}' targets: {', '.join(valid_targets)}. "
                        f"Keep the requested result type, but bridge through the typed path instead of joining "
                        f"that relationship directly to '{selected_type}'.{bridge_text}"
                    )
        if self.module:
            try:
                module_error = self.module.validation_error(self, sql, requested_types, message)
            except Exception:
                module_error = None
            if module_error:
                return module_error
        return None

    @staticmethod
    def _extract_numeric_threshold(message: str, sql: str) -> tuple[str, int] | None:
        msg = str(message or "").lower()
        if match := re.search(r"\b(\d+)\s+or\s+more\b", msg):
            return (">=", int(match.group(1)))
        if match := re.search(r"\bat\s+least\s+(\d+)\b", msg):
            return (">=", int(match.group(1)))
        if match := re.search(r"\bmore\s+than\s+(\d+)\b", msg):
            return (">", int(match.group(1)))
        if match := re.search(r"\b(\d+)\s+or\s+less\b", msg):
            return ("<=", int(match.group(1)))
        if match := re.search(r"\bless\s+than\s+(\d+)\b", msg):
            return ("<", int(match.group(1)))
        if match := re.search(r"(>=|<=|>|<)\s*(\d+)", sql or ""):
            return (match.group(1), int(match.group(2)))
        return None

    @staticmethod
    def _quoted_literals(sql: str) -> list[str]:
        literals = re.findall(r"'([^']+)'", sql or "")
        seen: set[str] = set()
        ordered: list[str] = []
        for item in literals:
            if item in seen:
                continue
            seen.add(item)
            ordered.append(item)
        return ordered

    def _zero_result_retry_hint(self, sql: str, requested_types: list[str]) -> str | None:
        if not sql:
            return None
        literals = self._quoted_literals(sql)
        if not literals:
            return None

        hints: list[str] = ["Previous SQL executed successfully but returned 0 rows."]
        useful = False

        for literal in literals[:6]:
            matches = self._entity_name_matches(literal)
            if not matches:
                continue
            useful = True
            match_types = ", ".join(sorted({match[1] for match in matches}))
            hints.append(f"Exact entity-name matches for '{literal}' exist as type(s): {match_types}.")

        if requested_types:
            patterns = self._typed_rel_patterns()
            for requested in requested_types[:3]:
                related = sorted(
                    {
                        f"{src} -{rel}-> {dst}"
                        for src, rel, dst in patterns
                        if src == requested or dst == requested
                    }
                )
                if related:
                    useful = True
                    hints.append(
                        f"Typed patterns touching requested type '{requested}': "
                        + "; ".join(related[:10])
                    )

        if not useful:
            return None
        hints.append(
            "Rewrite the SQL using those live entity types and typed paths. "
            "Keep the requested result type in the final SELECT rows."
        )
        return " ".join(hints)

    def _synthesize_typed_path_query(self, sql: str, requested_types: list[str]) -> str | None:
        if not sql or not requested_types:
            return None
        rel_match = re.search(r"r\.rel_type\s*=\s*'([^']+)'", sql, re.IGNORECASE)
        if not rel_match:
            return None
        rel_type = rel_match.group(1)
        literals = self._quoted_literals(sql)
        if not literals:
            return None

        patterns = self._typed_rel_patterns()
        valid_sources = sorted({src for src, rel, _ in patterns if rel == rel_type})
        valid_targets = sorted({dst for _, rel, dst in patterns if rel == rel_type})
        if not valid_sources or not valid_targets:
            return None

        tag_literals: list[str] = []
        for literal in literals:
            matches = self._entity_name_matches(literal)
            if any(match_type == "tag" for _, match_type, _ in matches):
                tag_literals.append(literal)
        if not tag_literals:
            return None

        for requested_type in requested_types:
            for valid_source in valid_sources:
                path = self._shortest_type_path(requested_type, valid_source)
                if requested_type != valid_source and not path:
                    continue
                if not any(src == valid_targets[0] and rel == "TAGGED" and dst == "tag" for src, rel, dst in patterns):
                    continue

                joins: list[str] = []
                current_node_ref = "e.id"
                alias_index = 0
                current_type = requested_type
                for src, edge_rel, dst in path:
                    if src != current_type:
                        break
                    alias_index += 1
                    rel_alias = f"p{alias_index}"
                    joins.append(
                        f"JOIN relationships {rel_alias} ON {rel_alias}.source_id = {current_node_ref} AND {rel_alias}.rel_type = '{edge_rel}'"
                    )
                    current_node_ref = f"{rel_alias}.target_id"
                    current_type = dst
                else:
                    joins.append(
                        f"JOIN relationships ev ON ev.source_id = {current_node_ref} AND ev.rel_type = '{rel_type}'"
                    )
                    joins.append("JOIN relationships tg ON tg.source_id = ev.target_id AND tg.rel_type = 'TAGGED'")
                    joins.append("JOIN entities t ON t.id = tg.target_id")
                    literal = tag_literals[0].replace("'", "''")
                    return "\n".join(
                        [
                            "SELECT DISTINCT e.id, e.name, e.type",
                            "FROM entities e",
                            *joins,
                            f"WHERE e.type = '{requested_type}'",
                            "  AND t.type = 'tag'",
                            f"  AND t.name = '{literal}'",
                        ]
                    )
        return None

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
            try:
                type_names = [t["type"] for t in self.db.entity_types()]
            except Exception:
                type_names = []
            ex1 = type_names[0] if type_names else "nodes"
            ex2 = type_names[1] if len(type_names) > 1 else "nodes"
            parts.append(
                f"**I can help you query the knowledge graph.** Try:\n"
                f"  - \"show all {ex1}\" or \"list {ex2}\"\n"
                f"  - \"nodes with > 10 edges\"\n"
                f"  - \"what types are there?\"\n"
                f"  - \"find {ex1} named Smith\"\n\n"
                f"**Filters** (returns IDs → apply to graph):\n"
                f"  - \"filter out nodes with fewer than 5 edges\"\n"
                f"  - \"hide {ex1} not tagged with any topic\"\n"
                f"  When results have an `id` column, you can **Hide** those nodes or **Save as sidebar filter**."
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

        debug_steps: list[dict[str, Any]] = []
        system = _SYSTEM_TEMPLATE.format(schema_context=self._schema_context())
        messages: list[dict] = [{"role": "system", "content": system}]
        requested_types = self._requested_result_types(message)
        debug_steps.append({"step": "requested_result_types", "value": requested_types})
        if requested_types:
            messages.append({
                "role": "system",
                "content": (
                    "Requested result entity types: "
                    + ", ".join(requested_types)
                    + ". Return rows of those type(s); do not stop at intermediary evidence nodes."
                ),
            })
        entity_match_hints = self._message_entity_match_hints(message)
        debug_steps.append({"step": "message_entity_match_hints", "value": entity_match_hints})
        if entity_match_hints:
            messages.append({
                "role": "system",
                "content": " ".join(entity_match_hints) + " Use those exact matched types in the SQL path.",
            })
        if history:
            # Only keep last 4 turns (2 exchanges) to avoid filling context window
            messages.extend(history[-4:])
        # Append /no_think to suppress qwen3's <think> reasoning (faster responses)
        messages.append({"role": "user", "content": message + " /no_think"})

        try:
            reply = self.llm.chat(messages)
        except Exception as e:
            return ChatResult(intent="answer", content="", error=f"LLM error: {e}", debug=debug_steps)

        result = self._parse(reply)
        debug_steps.append({"step": "initial_sql", "sql": result.sql, "count": len(result.results)})
        validation_error = self._validate_sql_against_schema(result.sql or "", requested_types, message)
        if validation_error:
            debug_steps.append({"step": "validation_error", "value": validation_error})
        if validation_error:
            count_map_sql = self.module.synthesize_query(self, message, result.sql or "", requested_types) if self.module else None
            debug_steps.append({"step": "validation_count_map_sql", "sql": count_map_sql})
            if count_map_sql:
                try:
                    count_map_results = self.db.execute_read(count_map_sql)
                except Exception:
                    count_map_results = []
                debug_steps.append({"step": "validation_count_map_sql_results", "count": len(count_map_results)})
                return ChatResult(
                    intent="query",
                    content=result.content,
                    sql=count_map_sql,
                    results=count_map_results,
                    debug=debug_steps,
                )
            retry_messages = list(messages)
            retry_messages.append({
                "role": "system",
                "content": (
                    validation_error
                    + " Rewrite the SQL so the final result rows remain the requested type."
                ),
            })
            try:
                retry_reply = self.llm.chat(retry_messages)
            except Exception:
                result.debug = debug_steps
                return result
            retry_result = self._parse(retry_reply)
            debug_steps.append({"step": "validation_retry_sql", "sql": retry_result.sql, "count": len(retry_result.results)})
            retry_validation_error = self._validate_sql_against_schema(retry_result.sql or "", requested_types, message)
            if retry_result.sql and not retry_validation_error:
                retry_result.debug = debug_steps
                return retry_result
        if result.intent == "query" and result.sql and not result.results:
            count_map_sql = self.module.synthesize_query(self, message, result.sql, requested_types) if self.module else None
            debug_steps.append({"step": "count_map_sql", "sql": count_map_sql})
            if count_map_sql:
                try:
                    count_map_results = self.db.execute_read(count_map_sql)
                except Exception:
                    count_map_results = []
                debug_steps.append({"step": "count_map_sql_results", "count": len(count_map_results)})
                return ChatResult(
                    intent="query",
                    content=result.content,
                    sql=count_map_sql,
                    results=count_map_results,
                    debug=debug_steps,
                )
            synthesized_sql = self._synthesize_typed_path_query(result.sql, requested_types)
            debug_steps.append({"step": "synthesized_sql", "sql": synthesized_sql})
            if synthesized_sql:
                try:
                    synthesized_results = self.db.execute_read(synthesized_sql)
                except Exception:
                    synthesized_results = []
                debug_steps.append({"step": "synthesized_sql_results", "count": len(synthesized_results)})
                return ChatResult(
                    intent="query",
                    content=result.content,
                    sql=synthesized_sql,
                    results=synthesized_results,
                    debug=debug_steps,
                )
            zero_hint = self._zero_result_retry_hint(result.sql, requested_types)
            debug_steps.append({"step": "zero_result_retry_hint", "value": zero_hint})
            if zero_hint:
                retry_messages = list(messages)
                retry_messages.append({"role": "system", "content": zero_hint})
                try:
                    retry_reply = self.llm.chat(retry_messages)
                except Exception:
                    result.debug = debug_steps
                    return result
                retry_result = self._parse(retry_reply)
                debug_steps.append({"step": "zero_retry_sql", "sql": retry_result.sql, "count": len(retry_result.results)})
                retry_validation_error = self._validate_sql_against_schema(retry_result.sql or "", requested_types, message)
                if retry_result.sql and not retry_validation_error and retry_result.results:
                    retry_result.debug = debug_steps
                    return retry_result
        result.debug = debug_steps
        return result

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
