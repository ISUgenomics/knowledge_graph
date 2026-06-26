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
                    "parser_kind": "alias_match",
                    "rel_type": "HAS_HGT_DONOR",
                    "owner_type": "protein",
                    "target_types": ["hgt_donor"],
                },
                {
                    "id": "broad_homology",
                    "category": "homology",
                    "aliases": ["broad homology", "broad parasitism", "broad parasistism"],
                    "parser_kind": "alias_match",
                    "rel_type": "HAS_BROAD_HOMOLOGY_HIT",
                    "owner_type": "protein",
                    "target_types": ["comparative_hit"],
                },
                {
                    "id": "nematode_homology",
                    "category": "homology",
                    "aliases": ["nematode homology", "c. elegans", "caenorhabditis elegans"],
                    "parser_kind": "alias_match",
                    "rel_type": "HAS_NEMATODE_HIT",
                    "owner_type": "protein",
                    "target_types": ["comparative_hit"],
                },
                {
                    "id": "bcn_homology",
                    "category": "homology",
                    "aliases": ["cyst nematode homology", "bcn homology"],
                    "parser_kind": "alias_match",
                    "rel_type": "HAS_BCN_HIT",
                    "owner_type": "protein",
                    "target_types": ["comparative_hit"],
                },
            ],
            "orthogroup_filter": {
                "rel_type": "BELONGS_TO_ORTHOGROUP",
                "owner_type": "gene",
                "target_types": ["orthogroup"],
            },
            "ortholog_member": {
                "aliases": ["ortholog gene", "ortholog genes", "bcn ortholog", "bcn orthologs", "bcn gene", "bcn genes"],
                "parser_kind": "alias_match_excluding_terms",
                "exclude_patterns": [r"\bcop(y|ies)\b"],
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
            "parsers": {
                "alias_match": {
                    "mode": "alias_match",
                },
                "alias_match_excluding_terms": {
                    "mode": "alias_match_excluding_terms",
                },
                "scope_tag_alias_match": {
                    "mode": "scope_tag_alias_match",
                    "required_message_cues": [
                        " homology ",
                        " homologies ",
                        " ortholog ",
                        " orthologs ",
                        " ortholog gene ",
                        " ortholog genes ",
                    ],
                    "required_group_cues": ["homology"],
                    "required_relation_families": ["protein_evidence"],
                    "blocked_group_cues": ["effectors"],
                },
            },
            "dynamic_families": {
                "effector_evidence": {
                    "source": {
                        "mode": "branch_tags",
                        "root_tag_id": "effector-evidence",
                        "hierarchy_rel_type": "BROADER",
                        "fallback_tag_id_pattern": "tag:%effector%",
                    },
                    "normalize": {
                        "id_strip_prefix": "tag:",
                        "replace_dash_with_space": True,
                        "remove_suffixes": [" hit"],
                    },
                    "classify": {
                        "flags": {
                            "known": {"any_substrings": ["known"]},
                            "putative": {"any_substrings": ["putative"]},
                            "dna": {"any_substrings": ["dna"]},
                            "protein": {"any_substrings": ["protein"]},
                            "island": {"any_substrings": ["island"]},
                        },
                    },
                    "owner_types": {
                        "default": ["protein"],
                        "when_flags": {
                            "island": ["gene"],
                        },
                    },
                    "alias_templates": {
                        "generic": {
                            "known": ["known effector", "known effectors"],
                            "putative": ["putative effector", "putative effectors"],
                            "dna": ["dna effector", "dna effectors", "known effector", "known effectors"],
                            "protein": ["protein effector", "protein effectors", "known effector", "known effectors"],
                        },
                        "organism_scoped": {
                            "template_flag_matches": {
                                "known": ["known", "dna", "protein"],
                                "putative": ["putative"],
                            },
                            "organism_sets": {
                                "primary": {
                                    "include_when_any_flags": ["putative", "dna", "protein"],
                                    "exclude_when_flags": [],
                                },
                                "secondary": {
                                    "include_when_any_flags": ["known", "putative"],
                                    "exclude_when_flags": ["dna", "protein"],
                                },
                            },
                            "templates": {
                                "known": {
                                    "primary": [
                                        "known effector in {organism}",
                                        "known effectors in {organism}",
                                        "{organism} known effector",
                                        "{organism} known effectors",
                                        "identified as known effector in {organism}",
                                        "identified as known effectors in {organism}",
                                    ],
                                    "secondary": [
                                        "known effector in {organism}",
                                        "known effectors in {organism}",
                                        "{organism} known effector",
                                        "{organism} known effectors",
                                        "identified as known effector in {organism}",
                                        "identified as known effectors in {organism}",
                                    ],
                                },
                                "putative": {
                                    "primary": [
                                        "putative effector in {organism}",
                                        "putative effectors in {organism}",
                                    ],
                                    "secondary": [
                                        "putative effector in {organism}",
                                        "putative effectors in {organism}",
                                    ],
                                },
                            },
                        },
                    },
                    "collapse": {
                        "mode": "flag_family",
                        "when_message_contains": {
                            "known": [" known effector ", " known effectors "],
                            "putative": [" putative effector ", " putative effectors "],
                        },
                        "fallback_precedence": ["known", "putative", "dna", "protein"],
                        "merge_field": "tag_ids",
                    },
                    "output": {
                        "condition_kind": "tag_evidence",
                    },
                },
            },
            "condition_handlers": {
                "protein_evidence": "protein_evidence",
                "orthogroup_filter": "orthogroup_filter",
                "ortholog_member": "ortholog_member",
                "scope_tag": "scope_tag",
                "tag_evidence": "tag_evidence",
            },
            "specs": {
                "protein_evidence": {
                    "owner_type_ref": "owner_type",
                    "steps": [
                        {
                            "kind": "relationship",
                            "alias_prefix": "ev",
                            "source_ref": "{owner_ref}",
                            "direction": "forward",
                            "rel_type_ref": "evidence_rel_type",
                            "bind": "evidence_rel",
                        },
                        {
                            "kind": "entity",
                            "alias_prefix": "t",
                            "id_ref": "{evidence_rel}.target_id",
                            "entity_types_ref": "target_types",
                            "bind": "evidence_target",
                        },
                    ],
                },
                "orthogroup_filter": {
                    "owner_type": "gene",
                    "steps": [
                        {
                            "kind": "relationship",
                            "alias_prefix": "og",
                            "source_ref": "{owner_ref}",
                            "direction": "forward",
                            "rel_type": "BELONGS_TO_ORTHOGROUP",
                            "bind": "orthogroup_rel",
                        },
                        {
                            "kind": "entity",
                            "alias_prefix": "owner",
                            "id_ref": "{orthogroup_rel}.target_id",
                            "entity_type": "orthogroup",
                            "bind": "orthogroup_entity",
                        },
                    ],
                    "where_templates": [
                        "  AND (upper({orthogroup_entity}.name) = '{label}' OR upper({orthogroup_entity}.id) = 'ORTHOGROUP:{label}')",
                    ],
                },
                "ortholog_member": {
                    "owner_type": "gene",
                    "steps": [
                        {
                            "kind": "relationship",
                            "alias_prefix": "ogm",
                            "source_ref": "{owner_ref}",
                            "direction": "forward",
                            "rel_type": "BELONGS_TO_ORTHOGROUP",
                            "bind": "orthogroup_rel",
                        },
                        {
                            "kind": "relationship",
                            "alias_prefix": "mem",
                            "source_ref": "{orthogroup_rel}.target_id",
                            "direction": "forward",
                            "rel_type": "HAS_BCN_MEMBER",
                            "bind": "member_rel",
                        },
                    ],
                },
                "scope_tag": {
                    "owner_type_ref": "owner_type",
                    "steps": [
                        {
                            "kind": "relationship",
                            "alias_prefix": "sev",
                            "source_ref": "{owner_ref}",
                            "direction": "forward",
                            "rel_type_ref": "evidence_rel_type",
                            "bind": "evidence_rel",
                        },
                        {
                            "kind": "entity",
                            "alias_prefix": "shit",
                            "id_ref": "{evidence_rel}.target_id",
                            "entity_types_ref": "target_types",
                            "bind": "evidence_target",
                        },
                        {
                            "kind": "relationship",
                            "alias_prefix": "stg",
                            "source_ref": "{evidence_target}.id",
                            "direction": "forward",
                            "rel_type_ref": "tag_rel_type",
                            "bind": "tag_rel",
                        },
                        {
                            "kind": "entity",
                            "alias_prefix": "stag",
                            "id_ref": "{tag_rel}.target_id",
                            "entity_type": "tag",
                            "bind": "tag_entity",
                        },
                    ],
                    "where_templates": [
                        "  AND {tag_entity}.id = '{tag_id}'",
                    ],
                },
                "tag_evidence": {
                    "owner_type_ref": "owner_type",
                    "steps": [
                        {
                            "kind": "relationship",
                            "alias_prefix": "etg",
                            "source_ref": "{owner_ref}",
                            "direction": "forward",
                            "rel_type": "TAGGED",
                            "bind": "tag_rel",
                        },
                        {
                            "kind": "entity",
                            "alias_prefix": "etag",
                            "id_ref": "{tag_rel}.target_id",
                            "entity_type": "tag",
                            "id_in_ref": "tag_ids",
                            "bind": "tag_entity",
                        },
                    ],
                },
            },
            "scope_tags": {
                "homology-scope-broad-parasitism": {
                    "evidence_id": "broad_homology",
                    "parser_kind": "scope_tag_alias_match",
                    "owner_type": "protein",
                    "target_type": "comparative_hit",
                    "tag_rel_type": "TAGGED",
                },
                "homology-scope-nematode": {
                    "evidence_id": "nematode_homology",
                    "parser_kind": "scope_tag_alias_match",
                    "owner_type": "protein",
                    "target_type": "comparative_hit",
                    "tag_rel_type": "TAGGED",
                },
                "homology-scope-cyst-nematode": {
                    "evidence_id": "bcn_homology",
                    "parser_kind": "scope_tag_alias_match",
                    "owner_type": "protein",
                    "target_type": "comparative_hit",
                    "tag_rel_type": "TAGGED",
                },
            },
        },
        "validation": {},
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
