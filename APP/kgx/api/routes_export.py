"""
Export routes — /api/export/json, /api/export/neo4j, /api/export/markdown/:id
"""

import io
import json
import zipfile
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse

from kgx.db import KnowledgeGraphDB


def make_export_router(db: KnowledgeGraphDB) -> APIRouter:
    router = APIRouter(tags=["export"])

    @router.get("/export/json")
    def export_json():
        """Export full graph as JSON (nodes + edges + metadata)."""
        data = db.export_graph_json()
        return JSONResponse(content=data)

    @router.get("/export/neo4j")
    def export_neo4j():
        """Export graph as Neo4j-importable CSV files, returned as a zip archive."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            files = db.export_neo4j_csv(Path(tmp))
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for name, path in files.items():
                    zf.write(path, arcname=path.name)
            buf.seek(0)
            return StreamingResponse(
                buf,
                media_type="application/zip",
                headers={"Content-Disposition": "attachment; filename=neo4j-export.zip"},
            )

    @router.get("/export/markdown/{entity_id:path}")
    def export_markdown(entity_id: str):
        """Return a single entity as markdown."""
        entity = db.get_entity(entity_id)
        if not entity:
            raise HTTPException(status_code=404, detail=f"Entity not found: {entity_id}")
        md = db.export_markdown(entity_id)
        return PlainTextResponse(content=md, media_type="text/markdown")

    return router
