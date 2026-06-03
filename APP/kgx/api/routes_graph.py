"""
Graph routes — /api/graph, /api/types

These two endpoints serve the entire graph for visualization.
Kept minimal: only id/type/name for nodes, no metadata.
"""

from fastapi import APIRouter
from kgx.db import KnowledgeGraphDB


def make_graph_router(db: KnowledgeGraphDB, explore_config: dict | None = None) -> APIRouter:
    router = APIRouter(tags=["graph"])
    _explore_cfg = explore_config or {}

    @router.get("/graph")
    def get_graph(mode: str = "display", collapse_rel_types: str = "", top_k: int = 20, min_weight: int = 2, collapse_stubs: bool = True):
        """
        Return nodes and edges for the graph view.
        mode=display returns a reduced projection; mode=full returns the canonical graph.
        collapse_rel_types is a comma-separated list of rel_types eligible for aggregation.
        """
        if mode == "full":
            return {
                "nodes": db.graph_nodes(),
                "edges": db.graph_edges(),
                "projection": {"mode": "full"},
            }
        if mode == "explore":
            return db.graph_explore(_explore_cfg)
        rels = [r.strip() for r in collapse_rel_types.split(",") if r.strip()]
        stub_type = _explore_cfg.get("stub_type", "")
        stub_flag = _explore_cfg.get("stub_flag", "profiled")
        return db.graph_display(
            collapse_rel_types=rels, top_k=top_k, min_weight=min_weight,
            collapse_stubs=collapse_stubs, stub_type=stub_type, stub_flag=stub_flag,
        )

    @router.get("/types")
    def get_types():
        """
        Return distinct entity types and relationship types with counts.
        Used to auto-populate the sidebar and edge filter toggles.
        No hardcoded types — fully dynamic from schema.
        """
        return {
            "entity_types": db.entity_types(),
            "relationship_types": db.relationship_types(),
        }

    @router.get("/stats")
    def get_stats():
        """Return summary statistics for the knowledge graph."""
        return db.stats()

    return router
