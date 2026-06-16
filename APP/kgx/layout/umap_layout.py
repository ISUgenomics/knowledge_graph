"""
Compute a 3D UMAP layout from stored embeddings.

Positions are stored in layout_positions (entity_id, layout, x, y, z).
The table is created on first use — no migration required.
"""

from __future__ import annotations

import struct

from kgx.db import KnowledgeGraphDB

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS layout_positions (
    entity_id  TEXT NOT NULL,
    layout     TEXT NOT NULL,
    x          REAL NOT NULL,
    y          REAL NOT NULL,
    z          REAL NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (entity_id, layout)
)
"""


def _ensure_table(db: KnowledgeGraphDB):
    db.conn.execute(_CREATE_TABLE)
    db.conn.commit()


def compute_umap(
    db: KnowledgeGraphDB,
    n_neighbors: int = 15,
    min_dist: float = 0.1,
    spread: float = 500.0,
) -> int:
    """
    Run UMAP on stored embeddings and persist 3D positions.
    Returns number of positions written.
    Raises ImportError if umap-learn / numpy are missing.
    """
    try:
        import numpy as np
        import umap as umap_module
    except ImportError:
        raise ImportError(
            "umap-learn and numpy are required: pip install umap-learn numpy"
        )

    rows = db.conn.execute(
        "SELECT entity_id, vector FROM embeddings"
    ).fetchall()

    if len(rows) < 4:
        raise ValueError(
            f"Need at least 4 embeddings for UMAP, got {len(rows)}. "
            "Run the embedding step first."
        )

    ids, vectors = [], []
    for entity_id, blob in rows:
        n = len(blob) // 4
        vec = list(struct.unpack(f"{n}f", blob))
        ids.append(entity_id)
        vectors.append(vec)

    X = np.array(vectors, dtype=np.float32)

    reducer = umap_module.UMAP(
        n_components=3,
        n_neighbors=min(n_neighbors, len(ids) - 1),
        min_dist=min_dist,
        random_state=42,
        metric="cosine",
    )
    coords = reducer.fit_transform(X)

    # Normalise to zero-mean, then scale to graph coordinate space
    coords -= coords.mean(axis=0)
    std = coords.std(axis=0)
    std[std < 1e-8] = 1.0
    coords = (coords / std) * spread

    _ensure_table(db)

    for entity_id, pos in zip(ids, coords):
        db.conn.execute(
            """INSERT INTO layout_positions (entity_id, layout, x, y, z)
               VALUES (?, 'umap', ?, ?, ?)
               ON CONFLICT(entity_id, layout) DO UPDATE SET
                 x = excluded.x, y = excluded.y, z = excluded.z,
                 updated_at = datetime('now')""",
            (entity_id, float(pos[0]), float(pos[1]), float(pos[2])),
        )
    db.conn.commit()

    return len(ids)


def get_positions(db: KnowledgeGraphDB, layout: str = "umap") -> dict[str, dict]:
    """Return {entity_id: {x, y, z}} for the given layout."""
    _ensure_table(db)
    rows = db.conn.execute(
        "SELECT entity_id, x, y, z FROM layout_positions WHERE layout = ?",
        (layout,),
    ).fetchall()
    return {r[0]: {"x": r[1], "y": r[2], "z": r[3]} for r in rows}


def umap_status(db: KnowledgeGraphDB) -> dict:
    """Summary of embedding and position counts."""
    _ensure_table(db)
    emb_count = db.conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
    pos_count = db.conn.execute(
        "SELECT COUNT(*) FROM layout_positions WHERE layout = 'umap'"
    ).fetchone()[0]
    total = db.conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
    return {
        "embedding_count": emb_count,
        "position_count": pos_count,
        "total_entities": total,
        "ready": pos_count > 0,
    }
