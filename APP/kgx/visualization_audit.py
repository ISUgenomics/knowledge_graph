"""
Visualization contract audit and repair helpers.

These checks validate whether a built KGX database satisfies the arrangement-aware
contract declared in db_build.visualization.
"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from pathlib import Path


DEFAULT_FAMILY_TYPES = {
    "person": "person",
    "publication": "publication",
    "organization": "organization",
    "tag": "tag",
}


def _load_entities(conn: sqlite3.Connection, entity_type: str) -> list[tuple[str, dict]]:
    rows = conn.execute(
        "SELECT id, metadata FROM entities WHERE type = ?",
        (entity_type,),
    ).fetchall()
    results: list[tuple[str, dict]] = []
    for entity_id, metadata_json in rows:
        try:
            metadata = json.loads(metadata_json or "{}")
        except json.JSONDecodeError:
            metadata = {}
        results.append((entity_id, metadata))
    return results


def _all_relationship_types(conn: sqlite3.Connection) -> Counter:
    rows = conn.execute(
        "SELECT rel_type, COUNT(*) FROM relationships GROUP BY rel_type"
    ).fetchall()
    return Counter({rel_type: count for rel_type, count in rows})


def audit_visualization_contract(db_path: str | Path, policy: dict | None = None) -> list[str]:
    policy = policy or {}
    timeline = policy.get("timeline", {}) or {}
    hierarchical = policy.get("hierarchical", {}) or {}
    warnings: list[str] = []
    conn = sqlite3.connect(str(db_path))
    try:
        required_by_type = timeline.get("required_metadata_by_type", {}) or {}
        for entity_type, fields in sorted(required_by_type.items()):
            if not fields:
                continue
            rows = _load_entities(conn, entity_type)
            if not rows:
                warnings.append(
                    f"visualization: type '{entity_type}' is declared as timeline-capable but no entities were imported"
                )
                continue
            missing = 0
            for _entity_id, metadata in rows:
                if any(metadata.get(field) in ("", None, []) for field in fields):
                    missing += 1
            if missing:
                warnings.append(
                    f"visualization: {missing}/{len(rows)} '{entity_type}' entities are missing required timeline metadata fields {fields}"
                )

        preferred_anchor_types = timeline.get("preferred_anchor_types", []) or []
        anchor_order_fields = timeline.get("anchor_order_fields", {}) or {}
        for entity_type in preferred_anchor_types:
            if not anchor_order_fields.get(entity_type):
                warnings.append(
                    f"visualization: preferred timeline anchor type '{entity_type}' has no configured order fields"
                )

        rel_counts = _all_relationship_types(conn)
        declared_rel_types: set[str] = set()
        relation_classes = hierarchical.get("relation_classes", {}) or {}
        for rels in relation_classes.values():
            declared_rel_types.update(rels or [])
        uncategorized = sorted(rel for rel in rel_counts if rel not in declared_rel_types)
        if uncategorized:
            warnings.append(
                f"visualization: uncategorized relationship types present in DB: {', '.join(uncategorized)}"
            )

        family_overrides = hierarchical.get("type_families", {}) or {}
        entity_types = [row[0] for row in conn.execute("SELECT DISTINCT type FROM entities ORDER BY type").fetchall()]
        unclassified_types = [
            entity_type
            for entity_type in entity_types
            if entity_type not in DEFAULT_FAMILY_TYPES and entity_type not in family_overrides
        ]
        if unclassified_types:
            warnings.append(
                f"visualization: entity types missing hierarchical family mapping: {', '.join(unclassified_types)}"
            )
    finally:
        conn.close()
    return warnings


def repair_visualization_contract(db_path: str | Path, policy: dict | None = None) -> list[str]:
    """
    Safely backfill canonical timeline order fields from configured metadata aliases.
    """
    policy = policy or {}
    timeline = policy.get("timeline", {}) or {}
    anchor_order_fields = timeline.get("anchor_order_fields", {}) or {}
    field_aliases = timeline.get("field_aliases", {}) or {}
    changed: list[str] = []
    conn = sqlite3.connect(str(db_path))
    try:
        for entity_type, canonical_fields in sorted(anchor_order_fields.items()):
            rows = _load_entities(conn, entity_type)
            for entity_id, metadata in rows:
                updated = False
                for canonical in canonical_fields:
                    if metadata.get(canonical) not in ("", None, []):
                        continue
                    for alias in field_aliases.get(canonical, []) or []:
                        alias_value = metadata.get(alias)
                        if alias_value not in ("", None, []):
                            metadata[canonical] = alias_value
                            updated = True
                            break
                if updated:
                    conn.execute(
                        "UPDATE entities SET metadata = ?, updated_at = datetime('now') WHERE id = ?",
                        (json.dumps(metadata, ensure_ascii=False, separators=(",", ":")), entity_id),
                    )
                    changed.append(entity_id)
        if changed:
            conn.commit()
    finally:
        conn.close()
    return changed
