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

SCHEMA_VERSION = 2

ENTITY_TYPES = {"person", "publication", "signal", "event", "center", "tag"}

RELATIONSHIP_TYPES = {
    "AUTHORED",      # person → publication
    "ATTENDED",      # person → event
    "MENTIONED_IN",  # person → signal
    "TAGGED",        # any → tag
    "COAUTHOR",      # person ↔ person (undirected)
    "MEMBER_OF",     # person → center
    "BROADER",       # tag → parent tag (ontology hierarchy)
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

            -- Topics: multiple topics per entity (signal, event, etc.)
            CREATE TABLE IF NOT EXISTS entity_topics (
                entity_id   TEXT NOT NULL,
                topic       TEXT NOT NULL,
                PRIMARY KEY (entity_id, topic),
                FOREIGN KEY (entity_id) REFERENCES entities(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_topics_entity ON entity_topics(entity_id);
            CREATE INDEX IF NOT EXISTS idx_topics_topic  ON entity_topics(topic);

            -- Snippets: blockquote excerpts from source text
            -- entity_id = signal; ref_id = person or NULL; ref_type = 'person'|'topic'|NULL
            CREATE TABLE IF NOT EXISTS snippets (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_id   TEXT NOT NULL,
                ref_id      TEXT,
                ref_type    TEXT,
                text        TEXT NOT NULL,
                ordinal     INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (entity_id) REFERENCES entities(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_snippets_entity ON snippets(entity_id);
            CREATE INDEX IF NOT EXISTS idx_snippets_ref    ON snippets(ref_id);

            -- Research interests: ordered list per person
            CREATE TABLE IF NOT EXISTS research_interests (
                entity_id   TEXT NOT NULL,
                interest    TEXT NOT NULL,
                ordinal     INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (entity_id, interest),
                FOREIGN KEY (entity_id) REFERENCES entities(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_interests_entity ON research_interests(entity_id);

            -- Sources: per-entity provenance records
            CREATE TABLE IF NOT EXISTS sources (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_id    TEXT NOT NULL,
                source_name  TEXT NOT NULL,
                url          TEXT,
                retrieved_at TEXT,
                FOREIGN KEY (entity_id) REFERENCES entities(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_sources_entity ON sources(entity_id);

            -- Contact info: queryable key/value contact fields for persons
            CREATE TABLE IF NOT EXISTS contact_info (
                entity_id   TEXT NOT NULL,
                field       TEXT NOT NULL,
                value       TEXT NOT NULL,
                PRIMARY KEY (entity_id, field),
                FOREIGN KEY (entity_id) REFERENCES entities(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_contact_entity ON contact_info(entity_id);
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
    # Rich content operations
    # ------------------------------------------------------------------
    def add_topic(self, entity_id: str, topic: str):
        """Associate a topic string with an entity. Idempotent."""
        entity_id = self._normalize_id(entity_id)
        self.conn.execute(
            "INSERT OR IGNORE INTO entity_topics (entity_id, topic) VALUES (?, ?)",
            (entity_id, topic.strip()),
        )
        self.conn.commit()

    def get_topics(self, entity_id: str) -> list[str]:
        """Return all topics for an entity."""
        rows = self.conn.execute(
            "SELECT topic FROM entity_topics WHERE entity_id = ? ORDER BY topic",
            (self._normalize_id(entity_id),),
        ).fetchall()
        return [r[0] for r in rows]

    def add_snippet(self, entity_id: str, text: str, *,
                    ref_id: str | None = None, ref_type: str | None = None,
                    ordinal: int = 0):
        """Add a blockquote snippet to a signal entity."""
        entity_id = self._normalize_id(entity_id)
        if ref_id:
            ref_id = self._normalize_id(ref_id)
        self.conn.execute(
            """INSERT INTO snippets (entity_id, ref_id, ref_type, text, ordinal)
               VALUES (?, ?, ?, ?, ?)""",
            (entity_id, ref_id, ref_type, text.strip(), ordinal),
        )
        self.conn.commit()

    def get_snippets(self, entity_id: str, ref_id: str | None = None) -> list[dict]:
        """Return snippets for a signal, optionally filtered by referenced person."""
        entity_id = self._normalize_id(entity_id)
        if ref_id:
            rows = self.conn.execute(
                """SELECT * FROM snippets WHERE entity_id = ? AND ref_id = ?
                   ORDER BY ordinal""",
                (entity_id, self._normalize_id(ref_id)),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM snippets WHERE entity_id = ? ORDER BY ref_type, ref_id, ordinal",
                (entity_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def set_research_interests(self, entity_id: str, interests: list[str]):
        """Replace research interests for a person (full overwrite)."""
        entity_id = self._normalize_id(entity_id)
        self.conn.execute(
            "DELETE FROM research_interests WHERE entity_id = ?", (entity_id,)
        )
        for i, interest in enumerate(interests):
            interest = interest.strip()
            if interest:
                self.conn.execute(
                    """INSERT OR IGNORE INTO research_interests (entity_id, interest, ordinal)
                       VALUES (?, ?, ?)""",
                    (entity_id, interest, i),
                )
        self.conn.commit()

    def get_research_interests(self, entity_id: str) -> list[str]:
        """Return ordered research interests for a person."""
        rows = self.conn.execute(
            "SELECT interest FROM research_interests WHERE entity_id = ? ORDER BY ordinal",
            (self._normalize_id(entity_id),),
        ).fetchall()
        return [r[0] for r in rows]

    def upsert_source(self, entity_id: str, source_name: str, *,
                      url: str | None = None, retrieved_at: str | None = None):
        """Add or update a provenance source record for an entity."""
        entity_id = self._normalize_id(entity_id)
        existing = self.conn.execute(
            "SELECT id FROM sources WHERE entity_id = ? AND source_name = ?",
            (entity_id, source_name),
        ).fetchone()
        if existing:
            self.conn.execute(
                "UPDATE sources SET url = ?, retrieved_at = ? WHERE id = ?",
                (url, retrieved_at, existing[0]),
            )
        else:
            self.conn.execute(
                """INSERT INTO sources (entity_id, source_name, url, retrieved_at)
                   VALUES (?, ?, ?, ?)""",
                (entity_id, source_name, url, retrieved_at),
            )
        self.conn.commit()

    def get_sources(self, entity_id: str) -> list[dict]:
        """Return provenance sources for an entity."""
        rows = self.conn.execute(
            "SELECT source_name, url, retrieved_at FROM sources WHERE entity_id = ? ORDER BY source_name",
            (self._normalize_id(entity_id),),
        ).fetchall()
        return [dict(r) for r in rows]

    def upsert_contact(self, entity_id: str, field: str, value: str):
        """Set a contact field for a person. Overwrites existing value."""
        entity_id = self._normalize_id(entity_id)
        self.conn.execute(
            """INSERT INTO contact_info (entity_id, field, value) VALUES (?, ?, ?)
               ON CONFLICT(entity_id, field) DO UPDATE SET value = excluded.value""",
            (entity_id, field.strip(), value.strip()),
        )
        self.conn.commit()

    def get_contact(self, entity_id: str) -> dict:
        """Return all contact fields for a person as a dict."""
        rows = self.conn.execute(
            "SELECT field, value FROM contact_info WHERE entity_id = ? ORDER BY field",
            (self._normalize_id(entity_id),),
        ).fetchall()
        return {r[0]: r[1] for r in rows}

    # ------------------------------------------------------------------
    # Tag registry operations
    # ------------------------------------------------------------------
    def upsert_tag(self, tag_name: str, *, category: str = "topic",
                   description: str = "", aliases: list[str] | None = None) -> str:
        """Create or update a tag entity with category/description metadata."""
        tag_id = self._normalize_id(tag_name)
        meta = {"category": category}
        if description:
            meta["description"] = description
        self.upsert_entity("tag", tag_id, name=tag_name, metadata=meta,
                           aliases=aliases)
        return tag_id

    def get_tag_registry(self) -> dict[str, dict]:
        """Return {tag_id: {"category": str, "description": str}} for all tag entities."""
        rows = self.conn.execute(
            "SELECT id, metadata FROM entities WHERE type = 'tag' ORDER BY id"
        ).fetchall()
        registry = {}
        for r in rows:
            meta = json.loads(r["metadata"])
            registry[r["id"]] = {
                "category": meta.get("category", "topic"),
                "description": meta.get("description", ""),
            }
        return registry

    def get_tag_aliases(self) -> dict[str, str]:
        """Return {alias: canonical_tag_id} for all tag entities."""
        rows = self.conn.execute("""
            SELECT a.alias, a.entity_id
            FROM aliases a
            JOIN entities e ON e.id = a.entity_id
            WHERE e.type = 'tag'
            ORDER BY a.alias
        """).fetchall()
        return {r["alias"]: r["entity_id"] for r in rows}

    def merge_tags(self, winner_id: str, loser_id: str) -> dict:
        """
        Merge loser tag into winner: re-point TAGGED relationships,
        transfer aliases, add loser as alias of winner, delete loser.

        Returns {"relationships_moved": int, "aliases_moved": int}.
        """
        winner_id = self._normalize_id(winner_id)
        loser_id = self._normalize_id(loser_id)

        if winner_id == loser_id:
            return {"relationships_moved": 0, "aliases_moved": 0}

        # Re-point TAGGED relationships from loser to winner
        # Skip duplicates (source already tagged with winner)
        existing = set(r[0] for r in self.conn.execute(
            "SELECT source_id FROM relationships WHERE target_id = ? AND rel_type = 'TAGGED'",
            (winner_id,),
        ).fetchall())

        loser_rels = self.conn.execute(
            "SELECT source_id, metadata FROM relationships WHERE target_id = ? AND rel_type = 'TAGGED'",
            (loser_id,),
        ).fetchall()

        moved = 0
        for row in loser_rels:
            src = row["source_id"]
            if src not in existing:
                self.conn.execute(
                    """INSERT OR IGNORE INTO relationships (source_id, rel_type, target_id, metadata)
                       VALUES (?, 'TAGGED', ?, ?)""",
                    (src, winner_id, row["metadata"]),
                )
                moved += 1

        # Delete old relationships
        self.conn.execute(
            "DELETE FROM relationships WHERE target_id = ? AND rel_type = 'TAGGED'",
            (loser_id,),
        )

        # Transfer aliases from loser to winner
        loser_aliases = self.conn.execute(
            "SELECT alias FROM aliases WHERE entity_id = ?", (loser_id,)
        ).fetchall()
        aliases_moved = 0
        for row in loser_aliases:
            try:
                self.conn.execute(
                    "UPDATE aliases SET entity_id = ? WHERE alias = ?",
                    (winner_id, row["alias"]),
                )
                aliases_moved += 1
            except sqlite3.IntegrityError:
                pass

        # Add loser ID itself as alias of winner
        try:
            self.conn.execute(
                "INSERT OR IGNORE INTO aliases (alias, entity_id) VALUES (?, ?)",
                (loser_id, winner_id),
            )
        except sqlite3.IntegrityError:
            pass

        # Delete loser entity
        self.conn.execute("DELETE FROM entities WHERE id = ?", (loser_id,))
        self.conn.commit()

        return {"relationships_moved": moved, "aliases_moved": aliases_moved}

    # ------------------------------------------------------------------
    # Tag ontology (BROADER hierarchy)
    # ------------------------------------------------------------------
    def add_broader(self, child_id: str, parent_id: str):
        """Set child tag's parent in the ontology. Replaces any existing parent."""
        child_id = self._normalize_id(child_id)
        parent_id = self._normalize_id(parent_id)
        # Remove existing parent link (a tag has at most one parent)
        self.conn.execute(
            "DELETE FROM relationships WHERE source_id = ? AND rel_type = 'BROADER'",
            (child_id,),
        )
        self.conn.execute(
            """INSERT OR IGNORE INTO relationships (source_id, rel_type, target_id, metadata)
               VALUES (?, 'BROADER', ?, '{}')""",
            (child_id, parent_id),
        )
        self.conn.commit()

    def get_parent(self, tag_id: str) -> str | None:
        """Return the direct parent tag, or None if root."""
        tag_id = self._normalize_id(tag_id)
        row = self.conn.execute(
            "SELECT target_id FROM relationships WHERE source_id = ? AND rel_type = 'BROADER'",
            (tag_id,),
        ).fetchone()
        return row["target_id"] if row else None

    def get_children(self, tag_id: str) -> list[str]:
        """Return direct child tags."""
        tag_id = self._normalize_id(tag_id)
        rows = self.conn.execute(
            "SELECT source_id FROM relationships WHERE target_id = ? AND rel_type = 'BROADER'",
            (tag_id,),
        ).fetchall()
        return [r["source_id"] for r in rows]

    def get_ancestors(self, tag_id: str) -> list[str]:
        """Walk up the BROADER chain. Returns [parent, grandparent, ...] (nearest first)."""
        ancestors = []
        current = self._normalize_id(tag_id)
        visited = set()
        while True:
            parent = self.get_parent(current)
            if parent is None or parent in visited:
                break
            ancestors.append(parent)
            visited.add(parent)
            current = parent
        return ancestors

    def get_descendants(self, tag_id: str) -> list[str]:
        """Return all tags below this one in the hierarchy (BFS)."""
        tag_id = self._normalize_id(tag_id)
        result = []
        queue = [tag_id]
        visited = {tag_id}
        while queue:
            current = queue.pop(0)
            children = self.get_children(current)
            for child in children:
                if child not in visited:
                    visited.add(child)
                    result.append(child)
                    queue.append(child)
        return result

    def get_subtree_entities(self, tag_id: str, entity_type: str = "") -> list[dict]:
        """
        Get all entities tagged with this tag OR any of its descendants.
        This is the key query: "show me everything under plant-science".
        """
        tag_id = self._normalize_id(tag_id)
        all_tags = [tag_id] + self.get_descendants(tag_id)
        placeholders = ",".join("?" * len(all_tags))

        q = f"""
            SELECT DISTINCT e.id, e.type, e.name
            FROM entities e
            JOIN relationships r ON r.source_id = e.id
            WHERE r.rel_type = 'TAGGED' AND r.target_id IN ({placeholders})
        """
        params = list(all_tags)
        if entity_type:
            q += " AND e.type = ?"
            params.append(entity_type)
        q += " ORDER BY e.name"
        return [dict(r) for r in self.conn.execute(q, params)]

    def get_tag_tree(self) -> dict:
        """
        Return the full tag hierarchy as a nested dict.
        {tag_id: {"children": {tag_id: {"children": {...}}}}
        Roots are tags with no parent.
        """
        # Get all BROADER edges
        rows = self.conn.execute(
            "SELECT source_id, target_id FROM relationships WHERE rel_type = 'BROADER'"
        ).fetchall()
        parent_map = {r["source_id"]: r["target_id"] for r in rows}
        children_map: dict[str, list[str]] = {}
        for child, parent in parent_map.items():
            children_map.setdefault(parent, []).append(child)

        # All tag entities
        all_tags = set(r["id"] for r in self.conn.execute(
            "SELECT id FROM entities WHERE type = 'tag'"
        ).fetchall())

        # Roots = tags with no parent
        roots = sorted(all_tags - set(parent_map.keys()))

        def build(tag_id):
            node = {}
            kids = sorted(children_map.get(tag_id, []))
            if kids:
                node["children"] = {k: build(k) for k in kids}
            return node

        return {r: build(r) for r in roots}

    def get_tag_forest_stats(self) -> dict:
        """Summary stats for the tag ontology."""
        total = self.conn.execute(
            "SELECT COUNT(*) FROM entities WHERE type = 'tag'"
        ).fetchone()[0]
        with_parent = self.conn.execute(
            "SELECT COUNT(DISTINCT source_id) FROM relationships WHERE rel_type = 'BROADER'"
        ).fetchone()[0]
        parents = self.conn.execute(
            "SELECT COUNT(DISTINCT target_id) FROM relationships WHERE rel_type = 'BROADER'"
        ).fetchone()[0]
        roots = total - with_parent
        # Max depth
        max_depth = 0
        root_ids = self.conn.execute("""
            SELECT id FROM entities WHERE type = 'tag'
            AND id NOT IN (SELECT source_id FROM relationships WHERE rel_type = 'BROADER')
        """).fetchall()
        for row in root_ids:
            depth = self._tree_depth(row["id"])
            if depth > max_depth:
                max_depth = depth
        return {
            "total_tags": total,
            "with_parent": with_parent,
            "roots": roots,
            "internal_nodes": parents,
            "max_depth": max_depth,
        }

    def _tree_depth(self, tag_id: str) -> int:
        """Max depth below a tag node."""
        children = self.get_children(tag_id)
        if not children:
            return 0
        return 1 + max(self._tree_depth(c) for c in children)

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
