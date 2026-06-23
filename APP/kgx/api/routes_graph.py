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

    def _available_schema_sets() -> tuple[set[str], set[str]]:
        entity_types = {str(item.get("type") or "") for item in db.entity_types()}
        relationship_types = {str(item.get("rel_type") or "") for item in db.relationship_types()}
        return entity_types, relationship_types

    def _preset_is_available(cfg: dict, available_entity_types: set[str], available_rel_types: set[str]) -> bool:
        required_node_types_all = [str(item) for item in (cfg.get("required_node_types_all") or []) if str(item)]
        required_node_types_any = [str(item) for item in (cfg.get("required_node_types_any") or []) if str(item)]
        required_rel_types_all = [str(item) for item in (cfg.get("required_rel_types_all") or []) if str(item)]
        required_rel_types_any = [str(item) for item in (cfg.get("required_rel_types_any") or []) if str(item)]

        if required_node_types_all and not all(item in available_entity_types for item in required_node_types_all):
            return False
        if required_node_types_any and not any(item in available_entity_types for item in required_node_types_any):
            return False
        if required_rel_types_all and not all(item in available_rel_types for item in required_rel_types_all):
            return False
        if required_rel_types_any and not any(item in available_rel_types for item in required_rel_types_any):
            return False
        return True

    def _resolved_explore_config(preset: str = "") -> tuple[dict, dict]:
        resolved = dict(_explore_cfg)
        presets = dict(resolved.get("presets", {}) or {})
        available_entity_types, available_rel_types = _available_schema_sets()
        available_presets = [
            (preset_id, cfg)
            for preset_id, cfg in presets.items()
            if _preset_is_available(dict(cfg or {}), available_entity_types, available_rel_types)
        ]
        available_preset_ids = {preset_id for preset_id, _ in available_presets}
        requested_preset = preset or resolved.get("active_preset", "")
        active_preset = requested_preset if requested_preset in available_preset_ids else (
            available_presets[0][0] if available_presets else ""
        )
        preset_cfg = dict(presets.get(active_preset, {}) or {}) if active_preset else {}
        for key, value in preset_cfg.items():
            if key in {"label", "description", "required_node_types_all", "required_node_types_any", "required_rel_types_all", "required_rel_types_any"}:
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
                for preset_id, cfg in available_presets
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
