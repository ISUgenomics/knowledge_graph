"""
Generate text embeddings for entities using Ollama's embedding API.
Stores results in the embeddings table (entity_id, vector BLOB, model TEXT).

Text extraction is config-driven via embedding_config:
  type_fields:      {type: [field1, field2, ...]} — per-type metadata fields
  default_fields:   [field1, field2, ...]         — fallback for unlisted types
  max_field_length: int                           — truncate long field values
  skip_stub_type:   str                           — entity type to skip stubs for
  skip_stub_flag:   str                           — metadata key marking non-stubs
"""

from __future__ import annotations

import json
import struct

import httpx

from kgx.db import KnowledgeGraphDB


def _entity_text(entity: dict, embedding_config: dict | None = None) -> str:
    """Build a plain-text description for embedding.

    Uses embedding_config to determine which metadata fields to extract
    per entity type. Falls back to name + default_fields."""
    cfg = embedding_config or {}
    meta = entity.get("metadata", {}) or {}
    name = entity["name"]
    etype = entity["type"]

    type_fields = cfg.get("type_fields", {})
    default_fields = cfg.get("default_fields", ["title", "summary", "description"])
    max_len = cfg.get("max_field_length", 600)

    # Determine which fields to extract
    fields = type_fields.get(etype, default_fields)

    parts = [name]
    for field in fields:
        val = meta.get(field)
        if val:
            parts.append(str(val)[:max_len])

    return " | ".join(parts)


class Embedder:
    def __init__(self, base_url: str, model: str = "nomic-embed-text"):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._client = httpx.Client(timeout=60.0)

    def embed(self, text: str) -> list[float]:
        resp = self._client.post(
            f"{self.base_url}/api/embeddings",
            json={"model": self.model, "prompt": text},
        )
        resp.raise_for_status()
        return resp.json()["embedding"]

    def is_available(self) -> bool:
        try:
            r = self._client.get(f"{self.base_url}/api/tags", timeout=3.0)
            return r.status_code == 200
        except Exception:
            return False

    def close(self):
        self._client.close()


def generate_embeddings(
    db: KnowledgeGraphDB,
    embedder: Embedder,
    entity_types: list[str] | None = None,
    skip_stubs: bool = True,
    progress_cb=None,
    embedding_config: dict | None = None,
) -> dict:
    """
    Generate and store embeddings for all qualifying entities.

    Skips entities that already have an embedding from the same model.
    Returns {done, skipped, errors}.
    """
    cfg = embedding_config or {}
    skip_stub_type = cfg.get("skip_stub_type", "")
    skip_stub_flag = cfg.get("skip_stub_flag", "profiled")

    rows = db.conn.execute(
        "SELECT id, type, name, metadata FROM entities ORDER BY type, name"
    ).fetchall()

    done = skipped = errors = 0
    total = len(rows)

    for i, row in enumerate(rows):
        entity_id, etype, name, meta_raw = row
        meta = {}
        try:
            meta = json.loads(meta_raw or "{}")
        except Exception:
            pass

        entity = {"id": entity_id, "type": etype, "name": name, "metadata": meta}

        # Type filter
        if entity_types and etype not in entity_types:
            skipped += 1
            continue

        # Skip stubs — configurable entity type and metadata flag
        if skip_stubs and skip_stub_type and etype == skip_stub_type and not meta.get(skip_stub_flag):
            skipped += 1
            continue

        # Skip if already embedded by this model
        existing = db.conn.execute(
            "SELECT model FROM embeddings WHERE entity_id = ?", (entity_id,)
        ).fetchone()
        if existing and existing[0] == embedder.model:
            skipped += 1
            if progress_cb:
                progress_cb(i + 1, total, name, "skip")
            continue

        text = _entity_text(entity, cfg)
        try:
            vector = embedder.embed(text)
            blob = struct.pack(f"{len(vector)}f", *vector)
            db.conn.execute(
                """INSERT INTO embeddings (entity_id, vector, model)
                   VALUES (?, ?, ?)
                   ON CONFLICT(entity_id) DO UPDATE SET
                     vector = excluded.vector,
                     model  = excluded.model,
                     updated_at = datetime('now')""",
                (entity_id, blob, embedder.model),
            )
            db.conn.commit()
            done += 1
            if progress_cb:
                progress_cb(i + 1, total, name, "done")
        except Exception as e:
            errors += 1
            if progress_cb:
                progress_cb(i + 1, total, name, f"error:{e}")

    return {"done": done, "skipped": skipped, "errors": errors, "total": total}
