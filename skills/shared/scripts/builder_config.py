#!/usr/bin/env python3
"""Helpers for loading generalized DB-build policy from a KGX config file."""

from __future__ import annotations

from pathlib import Path


def load_builder_config(config_path: str | Path | None) -> tuple[dict, Path | None]:
    """Load a KGX YAML config and return its db_build section plus config path."""
    if not config_path:
        return {}, None
    import yaml

    path = Path(config_path).resolve()
    data = yaml.safe_load(path.read_text()) or {}
    return data.get("db_build", {}) or {}, path


def resolve_config_path(raw_path: str, *, config_path: Path | None) -> Path | None:
    """Resolve a possibly-relative path against the config file location."""
    text = str(raw_path or "").strip()
    if not text:
        return None
    path = Path(text)
    if path.is_absolute():
        return path
    if config_path is None:
        return path.resolve()
    return (config_path.parent / path).resolve()


def get_tagging_policy(config_path: str | Path | None) -> dict:
    """Return normalized tagging policy dict from db_build config."""
    db_build, resolved_config_path = load_builder_config(config_path)
    tagging = db_build.get("tagging", {}) or {}
    ontology = tagging.get("ontology", {}) or {}
    return {
        "config_path": resolved_config_path,
        "ontology": {
            "registry_path": resolve_config_path(ontology.get("registry_path", ""), config_path=resolved_config_path),
            "aliases_path": resolve_config_path(ontology.get("aliases_path", ""), config_path=resolved_config_path),
            "hierarchy_path": resolve_config_path(ontology.get("hierarchy_path", ""), config_path=resolved_config_path),
            "apply_on_build": bool(ontology.get("apply_on_build", False)),
        },
        "entity_policies": tagging.get("entity_policies", {}) or {},
        "person_tag_promotion": tagging.get("person_tag_promotion", {}) or {},
    }


def get_visualization_policy(config_path: str | Path | None) -> dict:
    """Return normalized visualization policy dict from db_build config."""
    db_build, _resolved_config_path = load_builder_config(config_path)
    visualization = db_build.get("visualization", {}) or {}
    timeline = visualization.get("timeline", {}) or {}
    hierarchical = visualization.get("hierarchical", {}) or {}
    return {
        "timeline": {
            "preferred_anchor_types": list(timeline.get("preferred_anchor_types", []) or []),
            "anchor_order_fields": dict(timeline.get("anchor_order_fields", {}) or {}),
            "field_aliases": dict(timeline.get("field_aliases", {}) or {}),
            "weak_order_fields": list(timeline.get("weak_order_fields", []) or []),
            "required_metadata_by_type": dict(timeline.get("required_metadata_by_type", {}) or {}),
        },
        "hierarchical": {
            "relation_classes": dict(hierarchical.get("relation_classes", {}) or {}),
            "type_families": dict(hierarchical.get("type_families", {}) or {}),
            "bands": dict(hierarchical.get("bands", {}) or {}),
            "annotation_driver_default": bool(hierarchical.get("annotation_driver_default", True)),
            "mediator_one_side_default": bool(hierarchical.get("mediator_one_side_default", False)),
            "strict_bands_default": bool(hierarchical.get("strict_bands_default", False)),
        },
    }
