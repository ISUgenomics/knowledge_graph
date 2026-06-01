"""
KnowledgeGraphDB — the single interface for all SQLite access in the explorer.

Design rules:
- No other module touches sqlite3 directly.
- All methods return plain dicts, never sqlite3.Row objects.
- metadata is always deserialized from JSON before returning.
- execute_read() raises if SQL is not SELECT.
- execute_write() raises if SQL is SELECT (use execute_read instead).
- Domain-agnostic: no hardcoded entity or relationship types.
"""

import json
import re
import sqlite3
import threading
from pathlib import Path

from .schema import init_schema


def _rows(cursor) -> list[dict]:
    """Convert sqlite3 cursor results to list of plain dicts."""
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


def _deserialize(entity: dict) -> dict:
    """Deserialize JSON metadata field in-place."""
    if "metadata" in entity and isinstance(entity["metadata"], str):
        try:
            entity["metadata"] = json.loads(entity["metadata"])
        except (json.JSONDecodeError, TypeError):
            entity["metadata"] = {}
    return entity


def _normalize_id(raw: str) -> str:
    """Normalize a raw string to a canonical slug."""
    raw = raw.strip().lower()
    raw = re.sub(r"\s+", "-", raw)
    raw = re.sub(r"[^a-z0-9:._/-]", "", raw)
    return raw


class KnowledgeGraphDB:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.schema_version = init_schema(self.conn)

    def _exec(self, sql, params=None):
        """Thread-safe execute — all DB access goes through this."""
        with self._lock:
            return self.conn.execute(sql, params or [])

    def _exec_commit(self, sql, params=None):
        """Thread-safe execute + commit."""
        with self._lock:
            cur = self.conn.execute(sql, params or [])
            self.conn.commit()
            return cur

    def _exec_many(self, statements):
        """Thread-safe batch: list of (sql, params) tuples, single commit."""
        with self._lock:
            results = []
            for sql, params in statements:
                results.append(self.conn.execute(sql, params or []))
            self.conn.commit()
            return results

    def close(self):
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    # ------------------------------------------------------------------
    # Schema discovery
    # ------------------------------------------------------------------

    def entity_types(self) -> list[dict]:
        """Return all entity types with counts. Schema-driven, never hardcoded."""
        cur = self.conn.execute(
            "SELECT type, COUNT(*) as count FROM entities GROUP BY type ORDER BY type"
        )
        return _rows(cur)

    def relationship_types(self) -> list[dict]:
        """Return all relationship types with counts."""
        cur = self.conn.execute(
            "SELECT rel_type, COUNT(*) as count FROM relationships GROUP BY rel_type ORDER BY rel_type"
        )
        return _rows(cur)

    def metadata_keys(self, entity_type: str = "") -> list[str]:
        """
        Return all metadata keys observed across entities (optionally filtered by type).
        Useful for building query builders and filter UIs.
        """
        if entity_type:
            rows = self.conn.execute(
                "SELECT metadata FROM entities WHERE type = ?", (entity_type,)
            ).fetchall()
        else:
            rows = self.conn.execute("SELECT metadata FROM entities").fetchall()

        keys: set[str] = set()
        for row in rows:
            try:
                meta = json.loads(row[0])
                keys.update(meta.keys())
            except (json.JSONDecodeError, TypeError):
                pass
        return sorted(keys)

    # ------------------------------------------------------------------
    # Bulk graph data (for visualization — minimal fields only)
    # ------------------------------------------------------------------

    def graph_nodes(self) -> list[dict]:
        """Return all nodes with just id/type/name — for graph rendering."""
        cur = self.conn.execute("SELECT id, type, name FROM entities ORDER BY type, name")
        return _rows(cur)

    def graph_edges(self) -> list[dict]:
        """Return all edges with source/target/rel_type — for graph rendering."""
        cur = self.conn.execute(
            "SELECT source_id as source, target_id as target, rel_type FROM relationships"
        )
        return _rows(cur)

    # ------------------------------------------------------------------
    # Entity CRUD
    # ------------------------------------------------------------------

    def get_entity(self, entity_id: str) -> dict | None:
        """Get a single entity by ID including aliases."""
        entity_id = _normalize_id(entity_id)
        row = self.conn.execute(
            "SELECT * FROM entities WHERE id = ?", (entity_id,)
        ).fetchone()
        if not row:
            return None
        result = _deserialize(dict(row))
        result["aliases"] = [
            r[0] for r in self.conn.execute(
                "SELECT alias FROM aliases WHERE entity_id = ?", (entity_id,)
            ).fetchall()
        ]
        return result

    def get_entities(self, entity_type: str = "", search: str = "") -> list[dict]:
        """Return entities, optionally filtered by type and/or name search."""
        params: list = []
        where: list[str] = []

        if entity_type:
            where.append("type = ?")
            params.append(entity_type)
        if search:
            where.append("name LIKE ?")
            params.append(f"%{search}%")

        sql = "SELECT id, type, name, updated_at FROM entities"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY name"

        return _rows(self._exec(sql, params))

    def upsert_entity(
        self,
        entity_type: str,
        entity_id: str,
        *,
        name: str = "",
        metadata: dict | None = None,
        aliases: list[str] | None = None,
    ) -> str:
        """Insert or update an entity. Returns the canonical entity_id."""
        entity_id = _normalize_id(entity_id)
        name = name or entity_id
        meta_json = json.dumps(metadata or {})

        with self._lock:
            self.conn.execute(
                """INSERT INTO entities (id, type, name, metadata) VALUES (?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET name = ?, metadata = ?, updated_at = datetime('now')""",
                (entity_id, entity_type, name, meta_json, name, meta_json),
            )

            if aliases:
                for alias in aliases:
                    norm = _normalize_id(alias)
                    self.conn.execute(
                        "INSERT OR IGNORE INTO aliases (alias, entity_id) VALUES (?, ?)",
                        (norm, entity_id),
                    )

            self.conn.commit()
        return entity_id

    def delete_entity(self, entity_id: str) -> bool:
        """Delete entity and all its relationships and aliases. Returns True if found."""
        entity_id = _normalize_id(entity_id)
        with self._lock:
            cur = self.conn.execute("DELETE FROM entities WHERE id = ?", (entity_id,))
            self.conn.commit()
        return cur.rowcount > 0

    def resolve(self, raw_id: str) -> str | None:
        """Resolve a raw ID or alias to the canonical entity_id."""
        norm = _normalize_id(raw_id)
        row = self.conn.execute("SELECT id FROM entities WHERE id = ?", (norm,)).fetchone()
        if row:
            return row[0]
        row = self.conn.execute(
            "SELECT entity_id FROM aliases WHERE alias = ?", (norm,)
        ).fetchone()
        return row[0] if row else None

    def ensure_entity(
        self,
        entity_type: str,
        raw_id: str,
        *,
        name: str = "",
        metadata: dict | None = None,
        aliases: list[str] | None = None,
    ) -> str:
        """Resolve or create. Returns canonical ID."""
        canonical = self.resolve(raw_id)
        if canonical:
            return canonical
        return self.upsert_entity(
            entity_type, raw_id, name=name, metadata=metadata, aliases=aliases
        )

    # ------------------------------------------------------------------
    # Relationship CRUD
    # ------------------------------------------------------------------

    def get_relationships(
        self,
        entity_id: str,
        rel_type: str = "",
        direction: str = "both",
    ) -> list[dict]:
        """Get relationships for an entity. direction: 'outgoing', 'incoming', or 'both'."""
        results = []

        def _query(col_match: str, col_other: str) -> list[dict]:
            sql = f"SELECT source_id, rel_type, target_id, metadata FROM relationships WHERE {col_match} = ?"
            params: list = [entity_id]
            if rel_type:
                sql += " AND rel_type = ?"
                params.append(rel_type)
            rows = _rows(self.conn.execute(sql, params))
            for r in rows:
                try:
                    r["metadata"] = json.loads(r["metadata"])
                except (json.JSONDecodeError, TypeError):
                    r["metadata"] = {}
            return rows

        if direction in ("outgoing", "both"):
            results.extend(_query("source_id", "target_id"))
        if direction in ("incoming", "both"):
            results.extend(_query("target_id", "source_id"))
        return results

    def add_relationship(
        self,
        source_id: str,
        rel_type: str,
        target_id: str,
        metadata: dict | None = None,
    ):
        """Add a relationship between two entities (idempotent)."""
        source_id = _normalize_id(source_id)
        target_id = _normalize_id(target_id)
        with self._lock:
            self.conn.execute(
                "INSERT OR IGNORE INTO relationships (source_id, rel_type, target_id, metadata) VALUES (?, ?, ?, ?)",
                (source_id, rel_type, target_id, json.dumps(metadata or {})),
            )
            self.conn.commit()

    def delete_relationship(self, source_id: str, rel_type: str, target_id: str) -> bool:
        """Delete a specific relationship. Returns True if it existed."""
        source_id = _normalize_id(source_id)
        target_id = _normalize_id(target_id)
        with self._lock:
            cur = self.conn.execute(
                "DELETE FROM relationships WHERE source_id = ? AND rel_type = ? AND target_id = ?",
                (source_id, rel_type, target_id),
            )
            self.conn.commit()
        return cur.rowcount > 0

    # ------------------------------------------------------------------
    # Graph queries
    # ------------------------------------------------------------------

    def neighbors(self, entity_id: str, rel_type: str = "") -> list[dict]:
        """Return all directly connected entities."""
        params: list
        if rel_type:
            sql = """
                SELECT DISTINCT e.id, e.type, e.name FROM entities e
                WHERE e.id IN (
                    SELECT target_id FROM relationships WHERE source_id = ? AND rel_type = ?
                    UNION
                    SELECT source_id FROM relationships WHERE target_id = ? AND rel_type = ?
                )
            """
            params = [entity_id, rel_type, entity_id, rel_type]
        else:
            sql = """
                SELECT DISTINCT e.id, e.type, e.name FROM entities e
                WHERE e.id IN (
                    SELECT target_id FROM relationships WHERE source_id = ?
                    UNION
                    SELECT source_id FROM relationships WHERE target_id = ?
                )
            """
            params = [entity_id, entity_id]
        return _rows(self._exec(sql, params))

    def shared_connections(self, id1: str, id2: str) -> list[dict]:
        """Find entities connected to both id1 and id2."""
        return _rows(self._exec("""
            SELECT e.id, e.type, e.name FROM entities e
            WHERE e.id IN (
                SELECT target_id FROM relationships WHERE source_id = ?
                UNION SELECT source_id FROM relationships WHERE target_id = ?
            )
            AND e.id IN (
                SELECT target_id FROM relationships WHERE source_id = ?
                UNION SELECT source_id FROM relationships WHERE target_id = ?
            )
        """, (id1, id1, id2, id2)))

    def hub_nodes(
        self,
        min_degree: int = 5,
        entity_type: str = "",
        exclude_stubs: bool = False,
    ) -> list[dict]:
        """Find entities with the most connections."""
        where = "WHERE e.type = ?" if entity_type else ""
        params: list = [entity_type] if entity_type else []

        if exclude_stubs:
            stub_filter = """
                AND o.id NOT IN (
                    SELECT id FROM entities
                    WHERE type = 'person'
                    AND (json_extract(metadata, '$.profiled') IS NULL
                         OR json_extract(metadata, '$.profiled') = 0)
                )
            """
        else:
            stub_filter = ""

        sql = f"""
            SELECT e.id, e.type, e.name, COUNT(*) AS degree
            FROM entities e
            JOIN (
                SELECT source_id AS eid, target_id AS other FROM relationships
                UNION ALL
                SELECT target_id AS eid, source_id AS other FROM relationships
            ) r ON r.eid = e.id
            JOIN entities o ON o.id = r.other
            {where}
            {stub_filter}
            GROUP BY e.id
            HAVING degree >= ?
            ORDER BY degree DESC
        """
        params.append(min_degree)
        return _rows(self._exec(sql, params))

    def degree(self, entity_id: str) -> int:
        """Count total relationships (in + out) for an entity."""
        row = self.conn.execute("""
            SELECT COUNT(*) FROM (
                SELECT source_id FROM relationships WHERE source_id = ?
                UNION ALL
                SELECT target_id FROM relationships WHERE target_id = ?
            )
        """, (entity_id, entity_id)).fetchone()
        return row[0]

    def stats(self) -> dict:
        """Summary counts for entities, relationships, aliases."""
        entity_counts = {
            r[0]: r[1]
            for r in self.conn.execute(
                "SELECT type, COUNT(*) FROM entities GROUP BY type"
            ).fetchall()
        }
        rel_counts = {
            r[0]: r[1]
            for r in self.conn.execute(
                "SELECT rel_type, COUNT(*) FROM relationships GROUP BY rel_type"
            ).fetchall()
        }
        alias_count = self.conn.execute("SELECT COUNT(*) FROM aliases").fetchone()[0]
        return {
            "entities": entity_counts,
            "relationships": rel_counts,
            "aliases": alias_count,
            "total_entities": sum(entity_counts.values()),
            "total_relationships": sum(rel_counts.values()),
        }

    # ------------------------------------------------------------------
    # Raw SQL (for chat-to-SQL)
    # ------------------------------------------------------------------

    def execute_read(self, sql: str, params: list | None = None) -> list[dict]:
        """Execute a SELECT query (including WITH CTEs). Raises ValueError on DML."""
        stripped = sql.strip().upper()
        if not (stripped.startswith("SELECT") or stripped.startswith("WITH")):
            raise ValueError(f"execute_read only accepts SELECT/WITH queries. Got: {sql[:80]}")
        cur = self.conn.execute(sql, params or [])
        return _rows(cur)

    def execute_write(self, sql: str, params: list | None = None) -> int:
        """Execute an INSERT/UPDATE/DELETE. Raises ValueError if it's a SELECT."""
        if sql.strip().upper().startswith("SELECT"):
            raise ValueError("execute_write does not accept SELECT queries. Use execute_read.")
        with self._lock:
            cur = self.conn.execute(sql, params or [])
            self.conn.commit()
        return cur.rowcount

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export_graph_json(self) -> dict:
        """Export full graph as JSON (nodes + edges + metadata)."""
        nodes = []
        for row in self.conn.execute("SELECT * FROM entities ORDER BY type, name").fetchall():
            e = _deserialize(dict(row))
            e["aliases"] = [
                r[0] for r in self.conn.execute(
                    "SELECT alias FROM aliases WHERE entity_id = ?", (e["id"],)
                ).fetchall()
            ]
            nodes.append(e)

        edges = _rows(self.conn.execute(
            "SELECT source_id, rel_type, target_id, metadata FROM relationships"
        ))
        for e in edges:
            try:
                e["metadata"] = json.loads(e["metadata"])
            except (json.JSONDecodeError, TypeError):
                e["metadata"] = {}

        return {
            "schema_version": self.schema_version,
            "stats": self.stats(),
            "nodes": nodes,
            "edges": edges,
        }

    def export_markdown(self, entity_id: str) -> str:
        """Render a single entity as markdown. Generic — works for any entity type."""
        entity = self.get_entity(entity_id)
        if not entity:
            return f"# Not found: {entity_id}\n"

        rels = self.get_relationships(entity_id)
        meta = entity.get("metadata", {})

        lines = [
            "---",
            f'id: "{entity["id"]}"',
            f'type: "{entity["type"]}"',
            f'name: "{entity["name"]}"',
        ]
        for k, v in meta.items():
            if isinstance(v, (str, int, float, bool)):
                lines.append(f'{k}: "{v}"')
        lines.extend(["---", "", f'# {entity["name"]}', ""])

        if meta:
            lines.append("## Properties")
            lines.append("")
            lines.append("| Field | Value |")
            lines.append("|---|---|")
            for k, v in meta.items():
                lines.append(f"| {k} | {v} |")
            lines.append("")

        if rels:
            lines.append("## Relationships")
            lines.append("")
            # Group by rel_type
            by_type: dict[str, list] = {}
            for r in rels:
                by_type.setdefault(r["rel_type"], []).append(r)
            for rel_type, rel_list in sorted(by_type.items()):
                lines.append(f"### {rel_type}")
                lines.append("")
                for r in rel_list:
                    other = r["target_id"] if r["source_id"] == entity_id else r["source_id"]
                    lines.append(f"- [[{other}]]")
                lines.append("")

        return "\n".join(lines)

    def export_neo4j_csv(self, output_dir: Path) -> dict[str, Path]:
        """
        Export graph to Neo4j-importable CSV files.
        Returns dict of {name: path} for all files written.
        """
        import csv
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        files: dict[str, Path] = {}

        # Node files per entity type
        for type_row in self.entity_types():
            etype = type_row["type"]
            entities = self.conn.execute(
                "SELECT id, name, metadata FROM entities WHERE type = ?", (etype,)
            ).fetchall()

            # Collect all metadata keys for this type to use as columns
            meta_keys: list[str] = []
            metas = []
            for e in entities:
                try:
                    m = json.loads(e[2])
                except (json.JSONDecodeError, TypeError):
                    m = {}
                metas.append(m)
                for k in m:
                    if k not in meta_keys:
                        meta_keys.append(k)

            path = output_dir / f"nodes_{etype}.csv"
            with open(path, "w", newline="") as f:
                fieldnames = [f"{etype}Id:ID({etype})", "name"] + meta_keys
                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
                writer.writeheader()
                for e, m in zip(entities, metas):
                    row = {f"{etype}Id:ID({etype})": e[0], "name": e[1]}
                    for k in meta_keys:
                        v = m.get(k, "")
                        row[k] = v if not isinstance(v, (dict, list)) else json.dumps(v)
                    writer.writerow(row)
            files[f"nodes_{etype}"] = path

        # Relationship files per rel_type
        for rel_row in self.relationship_types():
            rtype = rel_row["rel_type"]
            rels = self.conn.execute(
                "SELECT source_id, target_id FROM relationships WHERE rel_type = ?", (rtype,)
            ).fetchall()
            path = output_dir / f"rels_{rtype.lower()}.csv"
            with open(path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=[":START_ID", ":END_ID", ":TYPE"])
                writer.writeheader()
                for r in rels:
                    writer.writerow({":START_ID": r[0], ":END_ID": r[1], ":TYPE": rtype})
            files[f"rels_{rtype.lower()}"] = path

        return files
