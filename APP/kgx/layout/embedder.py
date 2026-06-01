"""
Generate text embeddings for entities using Ollama's embedding API.
Stores results in the embeddings table (entity_id, vector BLOB, model TEXT).

Only embeds entities with meaningful content:
  - persons with profiled=true
  - publications, signals, events, centers (all have text metadata)
  - tags (just the name — lightweight but useful for semantic clustering)
"""

from __future__ import annotations

import json
import struct

import httpx

from kgx.db import KnowledgeGraphDB


def _entity_text(entity: dict) -> str:
    """Build a plain-text description for embedding."""
    meta = entity.get("metadata", {}) or {}
    name = entity["name"]
    etype = entity["type"]

    if etype == "person":
        parts = [name]
        if meta.get("title"):
            parts.append(meta["title"])
        if meta.get("institution"):
            parts.append(f"at {meta['institution']}")
        if meta.get("department"):
            parts.append(meta["department"])
        if meta.get("summary"):
            parts.append(str(meta["summary"])[:400])
        return " | ".join(parts)

    if etype == "publication":
        title = meta.get("title") or name
        parts = [title]
        if meta.get("year"):
            parts.append(str(meta["year"]))
        if meta.get("journal"):
            parts.append(meta["journal"])
        if meta.get("abstract"):
            parts.append(str(meta["abstract"])[:600])
        return " | ".join(parts)

    if etype == "signal":
        parts = [meta.get("title") or name]
        if meta.get("topic"):
            parts.append(f"Topic: {meta['topic']}")
        if meta.get("summary"):
            parts.append(str(meta["summary"])[:400])
        return " | ".join(parts)

    # event, center, tag — use name + summary if available
    parts = [name]
    if meta.get("summary"):
        parts.append(str(meta["summary"])[:300])
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
) -> dict:
    """
    Generate and store embeddings for all qualifying entities.

    Skips entities that already have an embedding from the same model.
    Returns {done, skipped, errors}.
    """
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

        # Skip unprofiled person stubs — they have no useful text
        if skip_stubs and etype == "person" and not meta.get("profiled"):
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

        text = _entity_text(entity)
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
