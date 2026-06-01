#!/usr/bin/env python3
"""
vault_db.py — SQLite-backed entity store for the ISU knowledge vault.

Single source of truth for all entities and relationships.
Markdown is a generated view — this is the data layer.

Entity types: person, publication, signal, event, center, tag
Relationship types: AUTHORED, ATTENDED, MENTIONED_IN, TAGGED, COAUTHOR, MEMBER_OF

Usage:
    from vault_db import VaultDB
    db = VaultDB("vault.db")
    db.upsert_entity("person", "amy-toth", name="Amy Toth", aliases=["Amy L Toth"])
    db.add_relationship("amy-toth", "AUTHORED", "doi:10.1016/j.cois.2024.101167")
    hubs = db.hub_nodes(min_degree=5)
"""

import json
import re
import sqlite3
from pathlib import Path

SCHEMA_VERSION = 1

ENTITY_TYPES = {"person", "publication", "signal", "event", "center", "tag"}

RELATIONSHIP_TYPES = {
    "AUTHORED",      # person → publication
    "ATTENDED",      # person → event
    "MENTIONED_IN",  # person → signal
    "TAGGED",        # any → tag
    "COAUTHOR",      # person ↔ person (undirected)
    "MEMBER_OF",     # person → center
}


class VaultDB:
    def __init__(self, db_path: str | Path):
        self.path = Path(db_path)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()

    def _init_schema(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY
            );

            CREATE TABLE IF NOT EXISTS entities (
                id          TEXT PRIMARY KEY,
                type        TEXT NOT NULL,
                name        TEXT NOT NULL,
                metadata    TEXT DEFAULT '{}',
                created_at  TEXT DEFAULT (datetime('now')),
                updated_at  TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(type);
            CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(name);

            CREATE TABLE IF NOT EXISTS aliases (
                alias       TEXT PRIMARY KEY,
                entity_id   TEXT NOT NULL,
                FOREIGN KEY (entity_id) REFERENCES entities(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_aliases_entity ON aliases(entity_id);

            CREATE TABLE IF NOT EXISTS relationships (
                source_id   TEXT NOT NULL,
                rel_type    TEXT NOT NULL,
                target_id   TEXT NOT NULL,
                metadata    TEXT DEFAULT '{}',
                PRIMARY KEY (source_id, rel_type, target_id),
                FOREIGN KEY (source_id) REFERENCES entities(id) ON DELETE CASCADE,
                FOREIGN KEY (target_id) REFERENCES entities(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_rels_source ON relationships(source_id);
            CREATE INDEX IF NOT EXISTS idx_rels_target ON relationships(target_id);
            CREATE INDEX IF NOT EXISTS idx_rels_type ON relationships(rel_type);
        """)
        # Set schema version if not present
        cur = self.conn.execute("SELECT version FROM schema_version LIMIT 1")
        if cur.fetchone() is None:
            self.conn.execute("INSERT INTO schema_version VALUES (?)", (SCHEMA_VERSION,))
        self.conn.commit()

    # ------------------------------------------------------------------
    # Entity operations
    # ------------------------------------------------------------------
    def upsert_entity(self, entity_type: str, entity_id: str, *,
                      name: str = "", aliases: list[str] | None = None,
                      metadata: dict | None = None) -> str:
        """
        Insert or update an entity. Returns the canonical entity_id.

        If entity_id already exists, updates name/metadata.
        Aliases are added (not replaced) on update.
        """
        if entity_type not in ENTITY_TYPES:
            raise ValueError(f"Unknown entity type: {entity_type}")

        entity_id = self._normalize_id(entity_id)
        name = name or entity_id

        existing = self.conn.execute(
            "SELECT id FROM entities WHERE id = ?", (entity_id,)
        ).fetchone()

        meta_json = json.dumps(metadata or {})

        if existing:
            self.conn.execute("""
                UPDATE entities SET name = ?, metadata = ?, updated_at = datetime('now')
                WHERE id = ?
            """, (name, meta_json, entity_id))
        else:
            self.conn.execute("""
                INSERT INTO entities (id, type, name, metadata) VALUES (?, ?, ?, ?)
            """, (entity_id, entity_type, name, meta_json))

        # Add aliases
        if aliases:
            for alias in aliases:
                norm_alias = self._normalize_id(alias)
                try:
                    self.conn.execute(
                        "INSERT OR IGNORE INTO aliases (alias, entity_id) VALUES (?, ?)",
                        (norm_alias, entity_id)
                    )
                except sqlite3.IntegrityError:
                    pass  # Alias already points to another entity

        self.conn.commit()
        return entity_id

    def resolve(self, raw_id: str) -> str | None:
        """
        Resolve a raw ID or alias to the canonical entity_id.
        Returns None if no match found.
        """
        norm = self._normalize_id(raw_id)

        # Direct match
        row = self.conn.execute("SELECT id FROM entities WHERE id = ?", (norm,)).fetchone()
        if row:
            return row["id"]

        # Alias match
        row = self.conn.execute("SELECT entity_id FROM aliases WHERE alias = ?", (norm,)).fetchone()
        if row:
            return row["entity_id"]

        return None

    def ensure_entity(self, entity_type: str, raw_id: str, *,
                      name: str = "", aliases: list[str] | None = None,
                      metadata: dict | None = None) -> str:
        """
        Resolve or create an entity. If raw_id matches an existing entity
        or alias, returns the canonical ID. Otherwise creates a new entity.
        """
        canonical = self.resolve(raw_id)
        if canonical:
            return canonical
        return self.upsert_entity(entity_type, raw_id, name=name,
                                  aliases=aliases, metadata=metadata)

    def get_entity(self, entity_id: str) -> dict | None:
        """Get a single entity by ID."""
        row = self.conn.execute(
            "SELECT * FROM entities WHERE id = ?", (entity_id,)
        ).fetchone()
        if not row:
            return None
        result = dict(row)
        result["metadata"] = json.loads(result["metadata"])
        result["aliases"] = [r["alias"] for r in self.conn.execute(
            "SELECT alias FROM aliases WHERE entity_id = ?", (entity_id,)
        )]
        return result

    def get_entities(self, entity_type: str = "") -> list[dict]:
        """Get all entities, optionally filtered by type."""
        if entity_type:
            rows = self.conn.execute(
                "SELECT * FROM entities WHERE type = ? ORDER BY name", (entity_type,)
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM entities ORDER BY type, name"
            ).fetchall()
        results = []
        for row in rows:
            r = dict(row)
            r["metadata"] = json.loads(r["metadata"])
            results.append(r)
        return results

    def delete_entity(self, entity_id: str):
        """Delete an entity and all its relationships and aliases."""
        self.conn.execute("DELETE FROM entities WHERE id = ?", (entity_id,))
        self.conn.commit()

    # ------------------------------------------------------------------
    # Relationship operations
    # ------------------------------------------------------------------
    def add_relationship(self, source_id: str, rel_type: str, target_id: str,
                         metadata: dict | None = None):
        """Add a relationship between two entities."""
        if rel_type not in RELATIONSHIP_TYPES:
            raise ValueError(f"Unknown relationship type: {rel_type}")

        source_id = self._normalize_id(source_id)
        target_id = self._normalize_id(target_id)
        meta_json = json.dumps(metadata or {})

        self.conn.execute("""
            INSERT OR IGNORE INTO relationships (source_id, rel_type, target_id, metadata)
            VALUES (?, ?, ?, ?)
        """, (source_id, rel_type, target_id, meta_json))
        self.conn.commit()

    def get_relationships(self, entity_id: str, rel_type: str = "",
                          direction: str = "both") -> list[dict]:
        """
        Get relationships for an entity.
        direction: "outgoing", "incoming", or "both"
        """
        results = []
        if direction in ("outgoing", "both"):
            q = "SELECT * FROM relationships WHERE source_id = ?"
            params = [entity_id]
            if rel_type:
                q += " AND rel_type = ?"
                params.append(rel_type)
            results.extend(dict(r) for r in self.conn.execute(q, params))

        if direction in ("incoming", "both"):
            q = "SELECT * FROM relationships WHERE target_id = ?"
            params = [entity_id]
            if rel_type:
                q += " AND rel_type = ?"
                params.append(rel_type)
            results.extend(dict(r) for r in self.conn.execute(q, params))

        return results

    # ------------------------------------------------------------------
    # Graph queries
    # ------------------------------------------------------------------
    def degree(self, entity_id: str) -> int:
        """Count total relationships (in + out) for an entity."""
        row = self.conn.execute("""
            SELECT COUNT(*) AS deg FROM (
                SELECT source_id FROM relationships WHERE source_id = ?
                UNION ALL
                SELECT target_id FROM relationships WHERE target_id = ?
            )
        """, (entity_id, entity_id)).fetchone()
        return row["deg"]

    def hub_nodes(self, min_degree: int = 5, entity_type: str = "",
                  exclude_unprofiled: bool = False) -> list[dict]:
        """Find entities with the most connections.

        If exclude_unprofiled=True, relationships to unprofiled person stubs
        are not counted toward degree.
        """
        if exclude_unprofiled:
            # Only count edges where the OTHER end is not an unprofiled person stub
            unprofiled_filter = """
                SELECT source_id AS eid, target_id AS other FROM relationships
                UNION ALL
                SELECT target_id AS eid, source_id AS other FROM relationships
            """
            q = f"""
                SELECT e.id, e.type, e.name,
                       COUNT(*) AS degree
                FROM entities e
                JOIN ({unprofiled_filter}) r ON r.eid = e.id
                JOIN entities o ON o.id = r.other
                WHERE NOT (o.type = 'person' AND COALESCE(json_extract(o.metadata, '$.profiled'), 0) != 1)
            """
            params = []
            if entity_type:
                q += " AND e.type = ?"
                params.append(entity_type)
        else:
            q = """
                SELECT e.id, e.type, e.name,
                       COUNT(*) AS degree
                FROM entities e
                JOIN (
                    SELECT source_id AS eid FROM relationships
                    UNION ALL
                    SELECT target_id AS eid FROM relationships
                ) r ON r.eid = e.id
            """
            params = []
            if entity_type:
                q += " WHERE e.type = ?"
                params.append(entity_type)
        q += " GROUP BY e.id HAVING degree >= ? ORDER BY degree DESC"
        params.append(min_degree)
        return [dict(r) for r in self.conn.execute(q, params)]

    def neighbors(self, entity_id: str, rel_type: str = "") -> list[dict]:
        """Get all directly connected entities."""
        q = """
            SELECT DISTINCT e.id, e.type, e.name FROM entities e
            WHERE e.id IN (
                SELECT target_id FROM relationships WHERE source_id = ?
                UNION
                SELECT source_id FROM relationships WHERE target_id = ?
            )
        """
        params = [entity_id, entity_id]
        if rel_type:
            q = """
                SELECT DISTINCT e.id, e.type, e.name FROM entities e
                WHERE e.id IN (
                    SELECT target_id FROM relationships WHERE source_id = ? AND rel_type = ?
                    UNION
                    SELECT source_id FROM relationships WHERE target_id = ? AND rel_type = ?
                )
            """
            params = [entity_id, rel_type, entity_id, rel_type]
        return [dict(r) for r in self.conn.execute(q, params)]

    def shared_connections(self, id1: str, id2: str) -> list[dict]:
        """Find entities connected to both id1 and id2."""
        return [dict(r) for r in self.conn.execute("""
            SELECT e.id, e.type, e.name FROM entities e
            WHERE e.id IN (
                SELECT target_id FROM relationships WHERE source_id = ?
                UNION SELECT source_id FROM relationships WHERE target_id = ?
            )
            AND e.id IN (
                SELECT target_id FROM relationships WHERE source_id = ?
                UNION SELECT source_id FROM relationships WHERE target_id = ?
            )
        """, (id1, id1, id2, id2))]

    def stats(self) -> dict:
        """Get summary statistics."""
        entity_counts = {}
        for row in self.conn.execute(
            "SELECT type, COUNT(*) AS cnt FROM entities GROUP BY type"
        ):
            entity_counts[row["type"]] = row["cnt"]

        rel_counts = {}
        for row in self.conn.execute(
            "SELECT rel_type, COUNT(*) AS cnt FROM relationships GROUP BY rel_type"
        ):
            rel_counts[row["rel_type"]] = row["cnt"]

        alias_count = self.conn.execute("SELECT COUNT(*) FROM aliases").fetchone()[0]

        return {
            "entities": entity_counts,
            "relationships": rel_counts,
            "aliases": alias_count,
            "total_entities": sum(entity_counts.values()),
            "total_relationships": sum(rel_counts.values()),
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _normalize_id(raw: str) -> str:
        """Normalize a raw string to a canonical slug."""
        raw = raw.strip().lower()
        raw = re.sub(r"\s+", "-", raw)
        raw = re.sub(r"[^a-z0-9:._-]", "", raw)
        return raw

    def close(self):
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Vault DB CLI")
    parser.add_argument("db", help="Path to vault.db")
    parser.add_argument("--stats", action="store_true", help="Print stats")
    parser.add_argument("--hubs", type=int, default=0, help="Show hub nodes with >= N connections")
    parser.add_argument("--neighbors", type=str, default="", help="Show neighbors of entity")
    parser.add_argument("--type", type=str, default="", help="Filter by entity type")
    parser.add_argument("--profiled", action="store_true", help="Only show profiled persons (have real vault profiles)")
    args = parser.parse_args()

    db = VaultDB(args.db)

    if args.stats:
        s = db.stats()
        print("Entities:")
        for t, c in sorted(s["entities"].items()):
            print(f"  {t}: {c}")
        print(f"  total: {s['total_entities']}")
        print(f"  aliases: {s['aliases']}")
        print("\nRelationships:")
        for t, c in sorted(s["relationships"].items()):
            print(f"  {t}: {c}")
        print(f"  total: {s['total_relationships']}")

    if args.hubs:
        hubs = db.hub_nodes(min_degree=args.hubs, entity_type=args.type,
                            exclude_unprofiled=args.profiled)
        label = f"Hub nodes (degree >= {args.hubs})"
        if args.profiled:
            label += ", excluding unprofiled stubs"
        print(f"\n{label}:")
        for h in hubs:
            print(f"  [{h['type']}] {h['name']:40s} degree={h['degree']}")

    if args.neighbors:
        ns = db.neighbors(args.neighbors)
        print(f"\nNeighbors of {args.neighbors}:")
        for n in ns:
            print(f"  [{n['type']}] {n['name']}")

    db.close()
