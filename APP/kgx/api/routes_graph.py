"""
Graph routes — /api/graph, /api/types

These two endpoints serve the entire graph for visualization.
Kept minimal: only id/type/name for nodes, no metadata.
"""

from fastapi import APIRouter
from kgx.db import KnowledgeGraphDB


def make_graph_router(db: KnowledgeGraphDB) -> APIRouter:
    router = APIRouter(tags=["graph"])

    @router.get("/graph")
    def get_graph():
        """
        Return all nodes and edges for the graph view.
        Nodes: id, type, name only (no metadata — kept small for rendering).
        Edges: source, target, rel_type.
        """
        return {
            "nodes": db.graph_nodes(),
            "edges": db.graph_edges(),
        }

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
