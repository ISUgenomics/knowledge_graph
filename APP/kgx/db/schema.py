"""
Schema creation and migration for the Knowledge Graph DB.

Version history:
  1 — initial schema (entities, aliases, relationships)
  2 — add embeddings, saved_views, chat_history tables
"""

SCHEMA_VERSION = 2

CREATE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS schema_version (
        version INTEGER PRIMARY KEY
    );

    CREATE TABLE IF NOT EXISTS entities (
        id          TEXT PRIMARY KEY,
        type        TEXT NOT NULL,
        name        TEXT NOT NULL,
        metadata    TEXT NOT NULL DEFAULT '{}',
        created_at  TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
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
        metadata    TEXT NOT NULL DEFAULT '{}',
        PRIMARY KEY (source_id, rel_type, target_id),
        FOREIGN KEY (source_id) REFERENCES entities(id) ON DELETE CASCADE,
        FOREIGN KEY (target_id) REFERENCES entities(id) ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS idx_rels_source ON relationships(source_id);
    CREATE INDEX IF NOT EXISTS idx_rels_target ON relationships(target_id);
    CREATE INDEX IF NOT EXISTS idx_rels_type ON relationships(rel_type);

    CREATE TABLE IF NOT EXISTS embeddings (
        entity_id   TEXT PRIMARY KEY,
        vector      BLOB NOT NULL,
        model       TEXT NOT NULL,
        updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (entity_id) REFERENCES entities(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS saved_views (
        name        TEXT PRIMARY KEY,
        config      TEXT NOT NULL DEFAULT '{}',
        created_at  TEXT NOT NULL DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS chat_history (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id  TEXT NOT NULL,
        role        TEXT NOT NULL,
        content     TEXT NOT NULL,
        sql_query   TEXT,
        created_at  TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE INDEX IF NOT EXISTS idx_chat_session ON chat_history(session_id);
"""


def init_schema(conn) -> int:
    """
    Apply schema. Returns the current schema version.
    Safe to call on an existing DB — all statements use IF NOT EXISTS.
    """
    conn.executescript(CREATE_SCHEMA)
    cur = conn.execute("SELECT version FROM schema_version LIMIT 1")
    row = cur.fetchone()
    if row is None:
        conn.execute("INSERT INTO schema_version VALUES (?)", (SCHEMA_VERSION,))
        conn.commit()
        return SCHEMA_VERSION
    return row[0]
