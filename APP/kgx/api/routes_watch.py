"""
DB watch route — /api/watch

SSE endpoint that emits an event whenever vault.db is modified on disk.
The UI connects on load and triggers db:changed when it receives a ping.
"""

from __future__ import annotations

import asyncio
import json
import os

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse


def make_watch_router(db_path: str) -> APIRouter:
    router = APIRouter(tags=["watch"])

    @router.get("/watch")
    async def watch_db(request: Request):
        """SSE stream — sends 'changed' event when vault.db mtime changes."""
        async def event_stream():
            last_mtime = _get_mtime(db_path)
            while True:
                if await request.is_disconnected():
                    break
                await asyncio.sleep(2.0)
                current = _get_mtime(db_path)
                if current != last_mtime:
                    last_mtime = current
                    yield f"event: changed\ndata: {json.dumps({'mtime': current})}\n\n"

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return router


def _get_mtime(path: str) -> float:
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0.0
