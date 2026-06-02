"""
Entity routes — /api/entity/:id, /api/entities/:type

IMPORTANT: Routes with suffixes (/neighbors, /markdown) must be registered
BEFORE the catch-all {entity_id:path} route, because :path is greedy.
"""

from fastapi import APIRouter, HTTPException
from kgx.db import KnowledgeGraphDB


def make_entity_router(db: KnowledgeGraphDB) -> APIRouter:
    router = APIRouter(tags=["entities"])

    @router.get("/entities/{entity_type}")
    def get_entities(entity_type: str, search: str = "", limit: int = 500):
        """
        Return list of entities by type for sidebar population.
        Optionally filter by name search.
        """
        entities = db.get_entities(entity_type=entity_type, search=search)
        return {"entities": entities[:limit], "total": len(entities)}

    # --- Suffix routes MUST come before the catch-all ---

    @router.get("/entity/{entity_id:path}/neighbors")
    def get_neighbors(entity_id: str, rel_type: str = ""):
        """Return neighbors of an entity."""
        entity = db.get_entity(entity_id)
        if not entity:
            raise HTTPException(status_code=404, detail=f"Entity not found: {entity_id}")
        return {
            "entity_id": entity_id,
            "neighbors": db.neighbors(entity_id, rel_type=rel_type),
            "relationships": db.get_relationships(entity_id),
        }

    @router.get("/entity/{entity_id:path}/markdown")
    def get_entity_markdown(entity_id: str):
        """Return a single entity rendered as markdown."""
        entity = db.get_entity(entity_id)
        if not entity:
            raise HTTPException(status_code=404, detail=f"Entity not found: {entity_id}")
        return {"markdown": db.export_markdown(entity_id)}

    # --- Catch-all entity detail (must be last) ---

    @router.get("/entity/{entity_id:path}")
    def get_entity(entity_id: str):
        """
        Return full entity detail + relationships + neighbors + rich content.
        Uses explore-aware queries so field-level tags show transitive
        TAGGED neighbors (via BROADER hierarchy).
        """
        entity = db.get_entity(entity_id)
        if not entity:
            raise HTTPException(status_code=404, detail=f"Entity not found: {entity_id}")

        neighbors = db.neighbors_explore(entity_id)
        # Build name map so the UI can show names instead of raw IDs
        name_map = {n["id"]: n["name"] for n in neighbors}

        relationships = db.get_relationships(entity_id)
        # Annotate each relationship with the display name of the other entity
        for r in relationships:
            other_id = r["target_id"] if r["source_id"] == entity_id else r["source_id"]
            r["other_name"] = name_map.get(other_id, other_id)

        return {
            "entity": entity,
            "relationships": relationships,
            "neighbors": neighbors,
            "degree": db.degree_explore(entity_id),
            "rich": db.get_rich(entity_id, entity_type=entity["type"]),
        }

    return router
