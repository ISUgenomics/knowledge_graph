from __future__ import annotations

from typing import Any

from kgx.semantic_templates import (
    load_common_semantic_templates,
    load_domain_semantic_templates,
    load_domain_template_bindings,
)


_GENERATED_TEMPLATE_RUNTIME_SUPPORT: dict[str, dict[str, str]] = {
    "people": {
        "contact_field": "generated_runtime",
        "relationship_authorship": "generated_runtime",
    },
    "genomics": {
        "expression_measurement": "generated_runtime",
        "dge_contrast": "generated_runtime",
        "genomic_location": "generated_runtime",
        "sequence_feature": "generated_runtime",
    },
}


def _walk_strings(value: Any) -> list[str]:
    strings: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            strings.append(str(key))
            strings.extend(_walk_strings(item))
    elif isinstance(value, list):
        for item in value:
            strings.extend(_walk_strings(item))
    elif isinstance(value, tuple):
        for item in value:
            strings.extend(_walk_strings(item))
    elif value is not None:
        strings.append(str(value))
    return strings


def _normalized_strings(value: Any) -> set[str]:
    return {" ".join(str(item).strip().lower().split()) for item in _walk_strings(value) if str(item).strip()}


def _db_table_names(db) -> set[str]:
    rows = db.execute_read("SELECT name FROM sqlite_master WHERE type = 'table'")
    return {str(row.get("name", "") or "").strip().lower() for row in rows if str(row.get("name", "") or "").strip()}


def _db_entity_types(db) -> set[str]:
    return {str(row.get("type", "") or "").strip().lower() for row in db.entity_types() if str(row.get("type", "") or "").strip()}


def _db_relationship_types(db) -> set[str]:
    return {str(row.get("rel_type", "") or "").strip().upper() for row in db.relationship_types() if str(row.get("rel_type", "") or "").strip()}


def _db_metadata_keys(db, entity_types: set[str]) -> set[str]:
    keys: set[str] = set()
    for entity_type in entity_types:
        keys.update(str(key).strip().lower() for key in db.metadata_keys(entity_type) if str(key).strip())
    return keys


def _db_tag_ids(db) -> set[str]:
    rows = db.execute_read("SELECT id FROM entities WHERE type = 'tag'")
    return {str(row.get("id", "") or "").strip().lower() for row in rows if str(row.get("id", "") or "").strip()}


def _db_contact_fields(db, table_names: set[str]) -> set[str]:
    if "contact_info" not in table_names:
        return set()
    rows = db.execute_read("SELECT DISTINCT field FROM contact_info ORDER BY field")
    return {str(row.get("field", "") or "").strip().lower() for row in rows if str(row.get("field", "") or "").strip()}


def collect_dataset_semantic_signals(
    db,
    *,
    ui_config: dict[str, Any] | None = None,
    explore_config: dict[str, Any] | None = None,
    db_build_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    entity_types = _db_entity_types(db)
    relationship_types = _db_relationship_types(db)
    metadata_keys = _db_metadata_keys(db, entity_types)
    tag_ids = _db_tag_ids(db)
    table_names = _db_table_names(db)
    contact_fields = _db_contact_fields(db, table_names)
    config_strings = _normalized_strings({
        "ui": ui_config or {},
        "explore": explore_config or {},
        "db_build": db_build_config or {},
    })
    return {
        "entity_types": entity_types,
        "relationship_types": relationship_types,
        "metadata_keys": metadata_keys,
        "tag_ids": tag_ids,
        "table_names": table_names,
        "contact_fields": contact_fields,
        "config_strings": config_strings,
    }


def _matches_any_prefix(values: set[str], patterns: list[str]) -> list[str]:
    matched: list[str] = []
    for pattern in patterns:
        low = str(pattern).strip().lower()
        if not low:
            continue
        normalized = low.replace(".*", "")
        if any(value.startswith(normalized) or normalized in value for value in values):
            matched.append(pattern)
    return matched


def _matches_any_contains(values: set[str], patterns: list[str], *, upper: bool = False) -> list[str]:
    haystack = {value.upper() if upper else value.lower() for value in values}
    matched: list[str] = []
    for pattern in patterns:
        probe = str(pattern).strip().upper() if upper else str(pattern).strip().lower()
        if probe and probe in haystack:
            matched.append(pattern)
    return matched


def _matches_prompt_aliases(config_strings: set[str], aliases: list[str]) -> list[str]:
    matched: list[str] = []
    for alias in aliases:
        probe = " ".join(str(alias).strip().lower().split())
        if not probe:
            continue
        if any(probe in item for item in config_strings):
            matched.append(alias)
    return matched


def score_template_detection(template: dict[str, Any], signals: dict[str, Any]) -> dict[str, Any]:
    hints = template.get("detection_hints", {}) if isinstance(template, dict) else {}
    if not isinstance(hints, dict):
        return {"score": 0, "matched": {}, "confidence": "none"}

    matched: dict[str, list[str]] = {}
    score = 0

    entity_matches = _matches_any_contains(
        set(signals.get("entity_types", set()) or set()),
        list(hints.get("entity_types", []) or []),
    )
    if entity_matches:
        matched["entity_types"] = entity_matches
        score += 2

    target_type_matches = _matches_any_contains(
        set(signals.get("entity_types", set()) or set()),
        list(hints.get("target_types_any", []) or []),
    )
    if target_type_matches:
        matched["target_types_any"] = target_type_matches
        score += 2

    rel_matches = _matches_any_contains(
        set(signals.get("relationship_types", set()) or set()),
        list(hints.get("relationship_types_any", []) or []),
        upper=True,
    )
    if rel_matches:
        matched["relationship_types_any"] = rel_matches
        score += 3

    metadata_matches = _matches_any_contains(
        set(signals.get("metadata_keys", set()) or set()),
        list(hints.get("metadata_fields_any", []) or []),
    )
    if metadata_matches:
        matched["metadata_fields_any"] = metadata_matches
        score += 3

    tag_matches = _matches_any_prefix(
        set(signals.get("tag_ids", set()) or set()),
        list(hints.get("tag_prefixes_any", []) or []),
    )
    if tag_matches:
        matched["tag_prefixes_any"] = tag_matches
        score += 2

    table_matches = _matches_any_contains(
        set(signals.get("table_names", set()) or set()),
        list(hints.get("table_names", []) or []),
    )
    if table_matches:
        matched["table_names"] = table_matches
        score += 2

    field_value_matches = _matches_any_contains(
        set(signals.get("contact_fields", set()) or set()),
        list(hints.get("field_values_any", []) or []),
    )
    if field_value_matches:
        matched["field_values_any"] = field_value_matches
        score += 3

    alias_matches = _matches_prompt_aliases(
        set(signals.get("config_strings", set()) or set()),
        list(hints.get("prompt_aliases", []) or []),
    )
    if alias_matches:
        matched["prompt_aliases"] = alias_matches
        score += 1

    confidence = "none"
    if score >= 6:
        confidence = "high"
    elif score >= 3:
        confidence = "medium"
    elif score > 0:
        confidence = "low"
    return {"score": score, "matched": matched, "confidence": confidence}


def propose_domain_template_candidates(
    domain_name: str | None,
    db,
    *,
    ui_config: dict[str, Any] | None = None,
    explore_config: dict[str, Any] | None = None,
    db_build_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    name = str(domain_name or "").strip().lower()
    common_templates = load_common_semantic_templates()
    domain_templates = load_domain_semantic_templates(name)
    bindings = load_domain_template_bindings(name)
    signals = collect_dataset_semantic_signals(
        db,
        ui_config=ui_config,
        explore_config=explore_config,
        db_build_config=db_build_config,
    )

    bound_template_ids = {
        str(item.get("template_id", "") or "")
        for items in (bindings.get("categories", {}) or {}).values()
        for item in list(items or [])
        if isinstance(item, dict)
    }

    candidates: list[dict[str, Any]] = []
    for template_id, template in domain_templates.items():
        detection = score_template_detection(template, signals)
        common_template_id = str(template.get("extends", "") or "")
        candidates.append({
            "template_id": template_id,
            "label": str(template.get("label", template_id) or template_id),
            "extends": common_template_id,
            "shared_pattern": dict(common_templates.get(common_template_id, {}) or {}) if common_template_id else {},
            "already_bound": template_id in bound_template_ids,
            "optional": bool(template.get("optional", False)),
            "concept_kind": str(template.get("concept_kind", "") or ""),
            "confidence": detection["confidence"],
            "score": detection["score"],
            "matched_signals": detection["matched"],
        })

    candidates.sort(key=lambda item: (item["already_bound"], item["score"], item["template_id"]), reverse=True)
    return {
        "domain": name,
        "signals": {
            "entity_types": sorted(signals["entity_types"]),
            "relationship_types": sorted(signals["relationship_types"]),
            "metadata_keys": sorted(signals["metadata_keys"]),
            "tag_ids": sorted(signals["tag_ids"]),
            "table_names": sorted(signals["table_names"]),
            "contact_fields": sorted(signals["contact_fields"]),
        },
        "candidates": candidates,
    }


def _default_category_for_template(domain_name: str, template_id: str) -> str:
    name = str(domain_name or "").strip().lower()
    if name == "genomics":
        if template_id == "expression_measurement":
            return "expression"
        if template_id == "dge_contrast":
            return "differential_expression"
        if template_id == "genomic_location":
            return "location"
        if template_id == "sequence_feature":
            return "sequence"
        if template_id == "taxonomy_scope":
            return "organism_scope"
    if name == "people":
        if template_id == "contact_field":
            return "contact"
        if template_id == "relationship_authorship":
            return "publications"
    return template_id


def _draft_binding_for_candidate(domain_name: str, candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "category": _default_category_for_template(domain_name, str(candidate.get("template_id", "") or "")),
        "template_id": str(candidate.get("template_id", "") or ""),
        "optional": bool(candidate.get("optional", False)),
        "activation_reason": f"{candidate.get('confidence', 'low')}-confidence detection from dataset signals",
        "matched_signals": dict(candidate.get("matched_signals", {}) or {}),
    }


def describe_domain_template_coverage(domain_name: str | None) -> dict[str, Any]:
    name = str(domain_name or "").strip().lower()
    templates = load_domain_semantic_templates(name)
    bindings = load_domain_template_bindings(name)
    bound_by_template: dict[str, list[str]] = {}
    for category, items in dict(bindings.get("categories", {}) or {}).items():
        for item in list(items or []):
            if not isinstance(item, dict):
                continue
            template_id = str(item.get("template_id", "") or "")
            if template_id:
                bound_by_template.setdefault(template_id, []).append(str(category))
    generated_support = dict(_GENERATED_TEMPLATE_RUNTIME_SUPPORT.get(name, {}) or {})
    coverage: list[dict[str, Any]] = []
    for template_id, template in templates.items():
        bound_categories = list(bound_by_template.get(template_id, []))
        support = str(generated_support.get(template_id, "") or "")
        if bound_categories:
            coverage_kind = "bound_registry"
            runtime_support = "bound_runtime"
        elif support:
            coverage_kind = "generated_fragment"
            runtime_support = support
        else:
            coverage_kind = "uncovered"
            runtime_support = "none"
        coverage.append({
            "template_id": template_id,
            "label": str(template.get("label", template_id) or template_id),
            "optional": bool(template.get("optional", False)),
            "extends": str(template.get("extends", "") or ""),
            "bound_categories": bound_categories,
            "coverage_kind": coverage_kind,
            "runtime_support": runtime_support,
        })
    coverage.sort(key=lambda item: item["template_id"])
    return {
        "domain": name,
        "templates": coverage,
        "summary": {
            "total": len(coverage),
            "bound_registry": sum(1 for item in coverage if item["coverage_kind"] == "bound_registry"),
            "generated_fragment": sum(1 for item in coverage if item["coverage_kind"] == "generated_fragment"),
            "uncovered": sum(1 for item in coverage if item["coverage_kind"] == "uncovered"),
        },
    }


def _pick_first(values: list[str], default: str) -> str:
    return str(values[0]) if values else default


def _expression_registry_fragment(candidate: dict[str, Any]) -> dict[str, Any]:
    matched = dict(candidate.get("matched_signals", {}) or {})
    entity_types = [str(item) for item in list(matched.get("entity_types", []) or []) if str(item).strip()]
    rel_types = [str(item) for item in list(matched.get("relationship_types_any", []) or []) if str(item).strip()]
    metadata_fields = [str(item) for item in list(matched.get("metadata_fields_any", []) or []) if str(item).strip()]
    target_type = _pick_first(entity_types, "expression_measure")
    rel_type = _pick_first(rel_types, "HAS_EXPRESSION_SUMMARY")
    return {
        "categories": {
            "expression": {
                "entity_types": [target_type],
                "metadata_fields": metadata_fields,
            },
        },
        "relation_families": {
            "expression_measurement": [
                {
                    "id": "expression_measurement",
                    "category": "expression",
                    "aliases": ["expression", "abundance", "tpm", "fpkm"],
                    "parser_kind": "alias_match",
                    "rel_type": rel_type,
                    "owner_type": "transcript",
                    "target_types": [target_type],
                },
            ],
        },
        "operators": {
            "condition_handlers": {
                "expression_measurement": "expression_measurement",
            },
        },
    }


def _contact_registry_fragment(candidate: dict[str, Any]) -> dict[str, Any]:
    matched = dict(candidate.get("matched_signals", {}) or {})
    fields = [str(item) for item in list(matched.get("field_values_any", []) or []) if str(item).strip()]
    if not fields:
        fields = ["email", "orcid"]
    return {
        "categories": {
            "contact": {
                "fields": fields,
            },
        },
        "operators": {
            "condition_handlers": {
                "contact_filter": "contact_filter",
            },
            "specs": {
                "contact_filters": {
                    field: {
                        "field": field,
                        "aliases": [field],
                        "parser_kind": "field_value",
                        "display": {"alias": field},
                    }
                    for field in fields
                },
            },
        },
    }


def _authorship_registry_fragment(candidate: dict[str, Any]) -> dict[str, Any]:
    matched = dict(candidate.get("matched_signals", {}) or {})
    rel_types = [str(item) for item in list(matched.get("relationship_types_any", []) or []) if str(item).strip()]
    rel_type = _pick_first(rel_types, "AUTHORED")
    return {
        "categories": {
            "publications": {
                "relationship_types": [rel_type],
                "target_types": ["publication"],
            },
        },
        "operators": {
            "condition_handlers": {
                "relationship_filter": "relationship_filter",
            },
            "specs": {
                "relationship_filters": {
                    "authored_publication": {
                        "rel_type": rel_type,
                        "target_type": "publication",
                        "aliases": ["publication", "publications", "paper", "papers", "authored"],
                        "parser_kind": "presence",
                        "display": {"alias": "publication_name"},
                    },
                },
            },
        },
    }


def _dge_registry_fragment(candidate: dict[str, Any]) -> dict[str, Any]:
    matched = dict(candidate.get("matched_signals", {}) or {})
    entity_types = [str(item) for item in list(matched.get("entity_types", []) or []) if str(item).strip()]
    rel_types = [str(item) for item in list(matched.get("relationship_types_any", []) or []) if str(item).strip()]
    metadata_fields = [str(item) for item in list(matched.get("metadata_fields_any", []) or []) if str(item).strip()]
    target_type = _pick_first(entity_types, "contrast_definition")
    rel_type = _pick_first(rel_types, "HAS_EXPRESSION_CONTRAST")
    return {
        "categories": {
            "differential_expression": {
                "entity_types": [target_type],
                "metadata_fields": metadata_fields,
            },
        },
        "relation_families": {
            "dge_contrast": [
                {
                    "id": "dge_contrast",
                    "category": "differential_expression",
                    "aliases": ["differential expression", "dge", "contrast", "upregulated", "downregulated"],
                    "parser_kind": "alias_match",
                    "rel_type": rel_type,
                    "owner_type": "transcript",
                    "target_types": [target_type],
                },
            ],
        },
        "operators": {
            "condition_handlers": {
                "dge_contrast": "dge_contrast",
            },
        },
    }


def _genomic_location_registry_fragment(candidate: dict[str, Any]) -> dict[str, Any]:
    matched = dict(candidate.get("matched_signals", {}) or {})
    entity_types = [str(item) for item in list(matched.get("entity_types", []) or []) if str(item).strip()]
    metadata_fields = [str(item) for item in list(matched.get("metadata_fields_any", []) or []) if str(item).strip()]
    return {
        "categories": {
            "location": {
                "entity_types": entity_types or ["chromosome", "scaffold", "contig"],
                "metadata_fields": metadata_fields or ["start", "end", "strand", "chromosome"],
            },
        },
        "metadata_hints": {
            "location": {
                "preferred_fields": metadata_fields or ["start", "end", "strand", "chromosome"],
                "target_entity_types": entity_types or ["chromosome", "scaffold", "contig"],
                "query_style": "json_extract",
            },
        },
        "operators": {
            "renderers": {
                "metadata": {
                    "where_templates": [
                        "  AND json_extract(owner.metadata, '$.{field}') = '{value}'",
                    ],
                    "validation_signatures": [
                        "$.{field}",
                        "{value}",
                    ],
                },
            },
            "parsers": {
                "field_value": {
                    "mode": "field_value",
                    "split_pattern": r"\s+\b(?:and|or)\b|[?!,]",
                },
            },
            "specs": {
                "metadata_filters": {
                    field: {
                        "field": field,
                        "aliases": [field],
                        "parser_kind": "field_value",
                        "owner_type": (entity_types or ["chromosome", "scaffold", "contig"])[0],
                        "category": "location",
                        "display": {"alias": field},
                    }
                    for field in (metadata_fields or ["start", "end", "strand", "chromosome"])
                },
            },
        },
    }


def _sequence_feature_registry_fragment(candidate: dict[str, Any]) -> dict[str, Any]:
    matched = dict(candidate.get("matched_signals", {}) or {})
    entity_types = [str(item) for item in list(matched.get("entity_types", []) or []) if str(item).strip()]
    metadata_fields = [str(item) for item in list(matched.get("metadata_fields_any", []) or []) if str(item).strip()]
    rel_types = [str(item) for item in list(matched.get("relationship_types_any", []) or []) if str(item).strip()]
    return {
        "categories": {
            "sequence": {
                "entity_types": entity_types or ["protein", "domain", "motif"],
                "metadata_fields": metadata_fields or ["protein_sequence", "mrna_sequence", "length"],
                "relationship_types": rel_types,
            },
        },
        "metadata_hints": {
            "sequence": {
                "preferred_fields": metadata_fields or ["protein_sequence", "mrna_sequence", "length"],
                "target_entity_types": entity_types or ["protein", "domain", "motif"],
                "query_style": "json_extract",
            },
        },
        "operators": {
            "renderers": {
                "metadata": {
                    "where_templates": [
                        "  AND json_extract(owner.metadata, '$.{field}') = '{value}'",
                    ],
                    "validation_signatures": [
                        "$.{field}",
                        "{value}",
                    ],
                },
            },
            "parsers": {
                "field_value": {
                    "mode": "field_value",
                    "split_pattern": r"\s+\b(?:and|or)\b|[?!,]",
                },
            },
            "specs": {
                "metadata_filters": {
                    field: {
                        "field": field,
                        "aliases": [field],
                        "parser_kind": "field_value",
                        "owner_type": (["protein"] if "protein" in (entity_types or []) else (entity_types or ["protein", "domain", "motif"]))[0],
                        "category": "sequence",
                        "display": {"alias": field},
                    }
                    for field in (metadata_fields or ["protein_sequence", "mrna_sequence", "length"])
                },
            },
        },
    }


def generate_draft_registry_fragment(domain_name: str | None, candidate: dict[str, Any]) -> dict[str, Any]:
    name = str(domain_name or "").strip().lower()
    template_id = str(candidate.get("template_id", "") or "")
    if name == "people" and template_id == "contact_field":
        return _contact_registry_fragment(candidate)
    if name == "people" and template_id == "relationship_authorship":
        return _authorship_registry_fragment(candidate)
    if name == "genomics" and template_id == "expression_measurement":
        return _expression_registry_fragment(candidate)
    if name == "genomics" and template_id == "dge_contrast":
        return _dge_registry_fragment(candidate)
    if name == "genomics" and template_id == "genomic_location":
        return _genomic_location_registry_fragment(candidate)
    if name == "genomics" and template_id == "sequence_feature":
        return _sequence_feature_registry_fragment(candidate)
    return {}


def generate_domain_onboarding_report(
    domain_name: str | None,
    db,
    *,
    ui_config: dict[str, Any] | None = None,
    explore_config: dict[str, Any] | None = None,
    db_build_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    proposal = propose_domain_template_candidates(
        domain_name,
        db,
        ui_config=ui_config,
        explore_config=explore_config,
        db_build_config=db_build_config,
    )
    name = str(proposal.get("domain", "") or "")

    active_now: list[dict[str, Any]] = []
    activate_candidates: list[dict[str, Any]] = []
    consider_later: list[dict[str, Any]] = []
    weak_signals: list[dict[str, Any]] = []

    for candidate in list(proposal.get("candidates", []) or []):
        item = {
            "template_id": str(candidate.get("template_id", "") or ""),
            "label": str(candidate.get("label", "") or ""),
            "confidence": str(candidate.get("confidence", "none") or "none"),
            "score": int(candidate.get("score", 0) or 0),
            "optional": bool(candidate.get("optional", False)),
            "matched_signals": dict(candidate.get("matched_signals", {}) or {}),
        }
        if candidate.get("already_bound"):
            active_now.append(item)
            continue
        if item["confidence"] == "high":
            activate_candidates.append({
                **item,
                "draft_binding": _draft_binding_for_candidate(name, candidate),
                "draft_registry_fragment": generate_draft_registry_fragment(name, candidate),
            })
            continue
        if item["confidence"] == "medium":
            consider_later.append({
                **item,
                "draft_binding": _draft_binding_for_candidate(name, candidate),
                "draft_registry_fragment": generate_draft_registry_fragment(name, candidate),
            })
            continue
        if item["confidence"] == "low":
            weak_signals.append(item)

    return {
        "domain": name,
        "signals": dict(proposal.get("signals", {}) or {}),
        "summary": {
            "active_count": len(active_now),
            "activate_count": len(activate_candidates),
            "consider_count": len(consider_later),
            "weak_count": len(weak_signals),
        },
        "active_now": active_now,
        "activate_candidates": activate_candidates,
        "consider_later": consider_later,
        "weak_signals": weak_signals,
    }


def _merge_fragment_values(base: Any, overlay: Any) -> Any:
    if isinstance(base, dict) and isinstance(overlay, dict):
        merged = dict(base)
        for key, value in overlay.items():
            merged[key] = _merge_fragment_values(merged.get(key), value) if key in merged else value
        return merged
    return overlay


def _merge_registry_fragments(fragments: list[dict[str, Any]]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for fragment in fragments:
        if not isinstance(fragment, dict):
            continue
        merged = _merge_fragment_values(merged, fragment)
    return merged


def generate_domain_onboarding_artifact(
    domain_name: str | None,
    db,
    *,
    ui_config: dict[str, Any] | None = None,
    explore_config: dict[str, Any] | None = None,
    db_build_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    report = generate_domain_onboarding_report(
        domain_name,
        db,
        ui_config=ui_config,
        explore_config=explore_config,
        db_build_config=db_build_config,
    )
    activate_candidates = list(report.get("activate_candidates", []) or [])
    proposed_fragments = [
        dict(item.get("draft_registry_fragment", {}) or {})
        for item in activate_candidates
        if dict(item.get("draft_registry_fragment", {}) or {})
    ]
    return {
        "artifact_version": "semantics-onboarding.v1",
        "domain": str(report.get("domain", "") or ""),
        "review_status": "draft",
        "signals": dict(report.get("signals", {}) or {}),
        "summary": dict(report.get("summary", {}) or {}),
        "decisions": {
            "active_now": list(report.get("active_now", []) or []),
            "activate_candidates": activate_candidates,
            "consider_later": list(report.get("consider_later", []) or []),
            "weak_signals": list(report.get("weak_signals", []) or []),
        },
        "proposed_registry_fragments": proposed_fragments,
        "proposed_registry_patch": _merge_registry_fragments(proposed_fragments),
    }


def extract_registry_patch_artifact(onboarding_artifact: dict[str, Any]) -> dict[str, Any]:
    return {
        "artifact_version": "semantic-registry-patch.v1",
        "domain": str(onboarding_artifact.get("domain", "") or ""),
        "source_artifact_version": str(onboarding_artifact.get("artifact_version", "") or ""),
        "review_status": str(onboarding_artifact.get("review_status", "draft") or "draft"),
        "summary": {
            "activate_count": int(((onboarding_artifact.get("summary", {}) or {}).get("activate_count", 0)) or 0),
            "fragment_count": len(list(onboarding_artifact.get("proposed_registry_fragments", []) or [])),
        },
        "registry_patch": dict(onboarding_artifact.get("proposed_registry_patch", {}) or {}),
    }
