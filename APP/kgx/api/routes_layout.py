"""
Layout routes — /api/layout/umap/*

GET  /api/layout/umap/status    — embedding + position counts, ready flag
GET  /api/layout/umap/positions — {entity_id: {x,y,z}} for all computed nodes
POST /api/layout/umap/compute   — SSE stream: generate embeddings then run UMAP
"""

from __future__ import annotations

import asyncio
import queue
import threading

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from kgx.db import KnowledgeGraphDB


class ComputeRequest(BaseModel):
    embedding_model: str = "nomic-embed-text"
    entity_types: list[str] | None = None  # None = all qualifying types
    skip_stubs: bool = True                 # skip stub entities
    n_neighbors: int = 15
    min_dist: float = 0.1
    spread: float = 500.0


def make_layout_router(db: KnowledgeGraphDB, llm_config: dict, embedding_config: dict | None = None) -> APIRouter:
    router = APIRouter(tags=["layout"])
    base_url = llm_config.get("base_url", "http://localhost:11434")
    _emb_cfg = embedding_config or {}

    @router.get("/layout/umap/status")
    def get_umap_status():
        from kgx.layout.umap_layout import umap_status
        return umap_status(db)

    @router.get("/layout/umap/positions")
    def get_umap_positions():
        from kgx.layout.umap_layout import get_positions
        positions = get_positions(db)
        if not positions:
            raise HTTPException(
                status_code=404,
                detail="No UMAP positions found. Run /api/layout/umap/compute first."
            )
        return {"positions": positions, "count": len(positions)}

    @router.post("/layout/umap/compute")
    async def compute_umap(req: ComputeRequest):
        """
        SSE stream that generates embeddings then computes UMAP.
        Yields 'data: <message>' lines; ends with 'event: done'.
        """
        q: queue.Queue = queue.Queue()

        def worker():
            from kgx.layout.embedder import Embedder, generate_embeddings
            from kgx.layout.umap_layout import compute_umap as run_umap

            def put(msg: str):
                q.put(f"data: {msg}\n\n")

            try:
                embedder = Embedder(base_url, req.embedding_model)
                if not embedder.is_available():
                    put(f"ERROR: Ollama not reachable at {base_url}")
                    q.put("event: error\ndata: {}\n\n")
                    return

                put(f"Generating embeddings with {req.embedding_model}…")

                stats = generate_embeddings(
                    db,
                    embedder,
                    entity_types=req.entity_types,
                    skip_stubs=req.skip_stubs,
                    embedding_config=_emb_cfg,
                )
                embedder.close()

                put(
                    f"Embeddings: {stats['done']} new, "
                    f"{stats['skipped']} skipped, "
                    f"{stats['errors']} errors"
                )

                emb_total = db.conn.execute(
                    "SELECT COUNT(*) FROM embeddings"
                ).fetchone()[0]
                put(f"Total embeddings stored: {emb_total}")
                put("Running UMAP (may take 30–120s for large datasets)…")

                n = run_umap(
                    db,
                    n_neighbors=req.n_neighbors,
                    min_dist=req.min_dist,
                    spread=req.spread,
                )
                put(f"Done — {n} positions computed")
                q.put("event: done\ndata: {}\n\n")

            except ImportError as e:
                put(f"ERROR: {e}")
                q.put("event: error\ndata: {}\n\n")
            except Exception as e:
                put(f"ERROR: {e}")
                q.put("event: error\ndata: {}\n\n")
            finally:
                q.put(None)  # sentinel

        threading.Thread(target=worker, daemon=True).start()

        async def event_stream():
            loop = asyncio.get_event_loop()
            while True:
                msg = await loop.run_in_executor(None, q.get)
                if msg is None:
                    break
                yield msg

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return router
