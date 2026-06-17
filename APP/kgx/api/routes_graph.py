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

    def _resolved_explore_config(preset: str = "") -> tuple[dict, dict]:
        resolved = dict(_explore_cfg)
        presets = dict(resolved.get("presets", {}) or {})
        active_preset = preset or resolved.get("active_preset", "")
        preset_cfg = dict(presets.get(active_preset, {}) or {}) if active_preset else {}
        for key, value in preset_cfg.items():
            if key in {"label", "description"}:
                continue
            if value is not None:
                resolved[key] = value
        meta = {
            "active_preset": active_preset,
            "default_hidden_rel_types": list(resolved.get("default_hidden_rel_types", []) or []),
            "available_presets": [
                {
                    "id": preset_id,
                    "label": cfg.get("label") or preset_id,
                    "description": cfg.get("description", ""),
                }
                for preset_id, cfg in presets.items()
            ],
        }
        return resolved, meta

    @router.get("/graph")
    def get_graph(
        mode: str = "display",
        collapse_rel_types: str = "",
        top_k: int = 20,
        min_weight: int = 2,
        collapse_stubs: bool = True,
        preset: str = "",
    ):
        """
        Return nodes and edges for the graph view.
        mode=display returns a reduced projection; mode=full returns the canonical graph.
        collapse_rel_types is a comma-separated list of rel_types eligible for aggregation.
        """
        resolved_explore_cfg, preset_meta = _resolved_explore_config(preset)
        if mode == "full":
            return {
                "nodes": db.graph_nodes(),
                "edges": db.graph_edges(),
                "projection": {"mode": "full", **preset_meta},
            }
        if mode == "explore":
            result = db.graph_explore(resolved_explore_cfg)
            result["projection"] = {
                **(result.get("projection", {}) or {}),
                **preset_meta,
            }
            return result
        rels = [r.strip() for r in collapse_rel_types.split(",") if r.strip()]
        stub_type = resolved_explore_cfg.get("stub_type", "")
        stub_flag = resolved_explore_cfg.get("stub_flag", "profiled")
        result = db.graph_display(
            collapse_rel_types=rels,
            top_k=top_k,
            min_weight=min_weight,
            collapse_stubs=collapse_stubs,
            stub_type=stub_type,
            stub_flag=stub_flag,
            authored_edge=resolved_explore_cfg.get("mediator_edge", "AUTHORED"),
            collaboration_edge="COAUTHOR",
            mediator_type=resolved_explore_cfg.get("mediator_type", ""),
            included_tag_roots=resolved_explore_cfg.get("included_tag_roots", []),
            hierarchy_edge=resolved_explore_cfg.get("hierarchy_edge", "BROADER"),
        )
        result["projection"] = {
            **(result.get("projection", {}) or {}),
            **preset_meta,
        }
        return result

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
