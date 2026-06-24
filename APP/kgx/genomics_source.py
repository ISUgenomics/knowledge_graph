from __future__ import annotations

from pathlib import Path
import runpy
from typing import Any


APP_DIR = Path(__file__).resolve().parents[1]


def _resolve_source_path(ui_config: dict[str, Any] | None) -> Path | None:
    ui_config = ui_config or {}
    source = str(ui_config.get("detail_layout_source", "") or "").strip()
    if not source:
        return None
    source_path = Path(source)
    if not source_path.is_absolute():
        source_path = (APP_DIR / source_path).resolve()
    if not source_path.exists():
        return None
    return source_path


def _load_raw_source_config(ui_config: dict[str, Any] | None) -> dict[str, Any]:
    source_path = _resolve_source_path(ui_config)
    if not source_path:
        return {}
    try:
        return runpy.run_path(str(source_path))
    except Exception:
        return {}


def _detail_layouts_from_raw(raw: dict[str, Any]) -> dict[str, object]:
    feature_groups = raw.get("FEATURE_GROUPS") or {}
    feature_columns = list(raw.get("FEATURE_COLUMNS") or [])
    if not feature_groups or not feature_columns:
        return {}

    ordered_groups: dict[str, dict[str, object]] = {}
    for group_id, label in feature_groups.items():
        ordered_groups[str(group_id)] = {
            "id": str(group_id),
            "label": str(label),
            "fields": [],
        }
    for item in feature_columns:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "").strip()
        group_id = str(item.get("group") or "").strip()
        if not key or not group_id or group_id not in ordered_groups:
            continue
        ordered_groups[group_id]["fields"].append({
            "key": key,
            "label": str(item.get("label") or key),
        })

    groups = [group for group in ordered_groups.values() if group["fields"]]
    if not groups:
        return {}
    return {
        "genomics_source_groups": {
            "groups": groups,
            "sequence_fields": [
                {"key": "protein_sequence", "label": "Protein Sequence"},
                {"key": "mrna_sequence", "label": "mRNA Sequence"},
            ],
            "entity_types": ["gene", "transcript", "protein"],
        }
    }


def _normalize_alias(text: str) -> str:
    cleaned = str(text or "").strip().lower()
    cleaned = cleaned.replace("_", " ").replace("-", " ")
    cleaned = " ".join(cleaned.replace("(", " ").replace(")", " ").split())
    return cleaned


def _semantic_schema_from_raw(raw: dict[str, Any]) -> dict[str, object]:
    feature_groups = raw.get("FEATURE_GROUPS") or {}
    feature_columns = list(raw.get("FEATURE_COLUMNS") or [])
    if not feature_groups or not feature_columns:
        return {}

    groups: dict[str, dict[str, object]] = {}
    for group_id, label in feature_groups.items():
        norm_label = _normalize_alias(str(label))
        aliases = {norm_label} if norm_label else set()
        groups[str(group_id)] = {
            "id": str(group_id),
            "label": str(label),
            "aliases": [],
            "fields": [],
        }
    for item in feature_columns:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "").strip()
        label = str(item.get("label") or key).strip()
        group_id = str(item.get("group") or "").strip()
        if not key or not group_id or group_id not in groups:
            continue
        field_aliases = {_normalize_alias(label), _normalize_alias(key)}
        field_aliases.discard("")
        groups[group_id]["fields"].append({
            "key": key,
            "label": label,
            "aliases": sorted(field_aliases),
        })

    for group in groups.values():
        alias_set = {_normalize_alias(str(group["label"]))}
        for field in group["fields"]:
            alias_set.update(list(field.get("aliases", []) or []))
        alias_set.discard("")
        group["aliases"] = sorted(alias_set)

    return {
        "group_order": [group_id for group_id in feature_groups.keys() if group_id in groups],
        "groups": groups,
    }


def load_detail_layouts(ui_config: dict[str, Any] | None) -> dict[str, object]:
    return _detail_layouts_from_raw(_load_raw_source_config(ui_config))


def load_semantic_schema(ui_config: dict[str, Any] | None) -> dict[str, object]:
    return _semantic_schema_from_raw(_load_raw_source_config(ui_config))


def load_semantic_registry(ui_config: dict[str, Any] | None) -> dict[str, object]:
    raw = _load_raw_source_config(ui_config)
    semantic_schema = _semantic_schema_from_raw(raw)
    return {
        "domain": "genomics",
        "schema": semantic_schema,
        "categories": {
            "effectors": {
                "group_ids": ["effectors"],
            },
            "homology": {
                "group_ids": ["homology"],
            },
            "orthology": {
                "relation_families": ["ortholog_member"],
            },
            "hgt": {
                "relation_families": ["hgt"],
            },
        },
        "relation_families": {
            "protein_evidence": [
                {
                    "id": "hgt",
                    "category": "hgt",
                    "aliases": ["hgt donor", "horizontal gene transfer", " hgt "],
                    "rel_type": "HAS_HGT_DONOR",
                    "owner_type": "protein",
                    "target_types": ["hgt_donor"],
                },
                {
                    "id": "broad_homology",
                    "category": "homology",
                    "aliases": ["broad homology", "broad parasitism", "broad parasistism"],
                    "rel_type": "HAS_BROAD_HOMOLOGY_HIT",
                    "owner_type": "protein",
                    "target_types": ["comparative_hit"],
                },
                {
                    "id": "nematode_homology",
                    "category": "homology",
                    "aliases": ["nematode homology", "c. elegans", "caenorhabditis elegans"],
                    "rel_type": "HAS_NEMATODE_HIT",
                    "owner_type": "protein",
                    "target_types": ["comparative_hit"],
                },
                {
                    "id": "bcn_homology",
                    "category": "homology",
                    "aliases": ["cyst nematode homology", "bcn homology"],
                    "rel_type": "HAS_BCN_HIT",
                    "owner_type": "protein",
                    "target_types": ["comparative_hit", "bcn_gene"],
                },
            ],
            "orthogroup_filter": {
                "rel_type": "BELONGS_TO_ORTHOGROUP",
                "owner_type": "gene",
                "target_types": ["orthogroup"],
            },
            "ortholog_member": {
                "aliases": ["ortholog gene", "ortholog genes", "bcn ortholog", "bcn orthologs", "bcn gene", "bcn genes"],
                "bridge_rel_type": "BELONGS_TO_ORTHOGROUP",
                "rel_type": "HAS_BCN_MEMBER",
                "owner_type": "orthogroup",
                "target_types": ["bcn_gene"],
            },
        },
        "organisms": {
            "alias_overrides": {
                "heterodera schachtii": ["bcn"],
            },
        },
        "operators": {
            "condition_handlers": {
                "protein_evidence": "protein_evidence",
                "orthogroup_filter": "orthogroup_filter",
                "ortholog_member": "ortholog_member",
                "scope_tag": "scope_tag",
                "tag_evidence": "tag_evidence",
            },
            "scope_tags": {
                "homology-scope-broad-parasitism": {
                    "evidence_id": "broad_homology",
                    "owner_type": "protein",
                    "target_type": "comparative_hit",
                    "tag_rel_type": "TAGGED",
                },
                "homology-scope-nematode": {
                    "evidence_id": "nematode_homology",
                    "owner_type": "protein",
                    "target_type": "comparative_hit",
                    "tag_rel_type": "TAGGED",
                },
                "homology-scope-cyst-nematode": {
                    "evidence_id": "bcn_homology",
                    "owner_type": "protein",
                    "target_type": "comparative_hit",
                    "tag_rel_type": "TAGGED",
                },
            },
        },
        "validation": {
            "protein_evidence_rel_types": [
                "HAS_HGT_DONOR",
                "HAS_BROAD_HOMOLOGY_HIT",
                "HAS_NEMATODE_HIT",
                "HAS_BCN_HIT",
            ],
            "ortholog_member_rel_type": "HAS_BCN_MEMBER",
            "orthogroup_filter_rel_type": "BELONGS_TO_ORTHOGROUP",
        },
        "paths": {
            "gene->gene": [],
            "gene->transcript": [
                {"src": "gene", "rel_type": "HAS_TRANSCRIPT", "dst": "transcript", "direction": "forward"},
            ],
            "gene->protein": [
                {"src": "gene", "rel_type": "HAS_TRANSCRIPT", "dst": "transcript", "direction": "forward"},
                {"src": "transcript", "rel_type": "TRANSLATED_TO", "dst": "protein", "direction": "forward"},
            ],
            "gene->orthogroup": [
                {"src": "gene", "rel_type": "BELONGS_TO_ORTHOGROUP", "dst": "orthogroup", "direction": "forward"},
            ],
            "transcript->gene": [
                {"src": "transcript", "rel_type": "HAS_TRANSCRIPT", "dst": "gene", "direction": "reverse"},
            ],
            "transcript->transcript": [],
            "transcript->protein": [
                {"src": "transcript", "rel_type": "TRANSLATED_TO", "dst": "protein", "direction": "forward"},
            ],
            "transcript->orthogroup": [
                {"src": "transcript", "rel_type": "HAS_TRANSCRIPT", "dst": "gene", "direction": "reverse"},
                {"src": "gene", "rel_type": "BELONGS_TO_ORTHOGROUP", "dst": "orthogroup", "direction": "forward"},
            ],
            "protein->gene": [
                {"src": "protein", "rel_type": "TRANSLATED_TO", "dst": "transcript", "direction": "reverse"},
                {"src": "transcript", "rel_type": "HAS_TRANSCRIPT", "dst": "gene", "direction": "reverse"},
            ],
            "protein->transcript": [
                {"src": "protein", "rel_type": "TRANSLATED_TO", "dst": "transcript", "direction": "reverse"},
            ],
            "protein->protein": [],
            "protein->orthogroup": [
                {"src": "protein", "rel_type": "TRANSLATED_TO", "dst": "transcript", "direction": "reverse"},
                {"src": "transcript", "rel_type": "HAS_TRANSCRIPT", "dst": "gene", "direction": "reverse"},
                {"src": "gene", "rel_type": "BELONGS_TO_ORTHOGROUP", "dst": "orthogroup", "direction": "forward"},
            ],
        },
    }
