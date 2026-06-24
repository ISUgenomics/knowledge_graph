from __future__ import annotations

from typing import Any


def load_detail_layouts(ui_config: dict[str, Any] | None) -> dict[str, object]:
    return {}


def load_semantic_schema(ui_config: dict[str, Any] | None) -> dict[str, object]:
    return {
        "group_order": ["identity", "affiliation"],
        "groups": {
            "identity": {
                "id": "identity",
                "label": "Identity",
                "aliases": ["people", "person", "people records", "person records"],
                "fields": [
                    {"key": "title", "label": "Title", "aliases": ["title"]},
                    {"key": "summary", "label": "Summary", "aliases": ["summary", "bio", "biography"]},
                ],
            },
            "affiliation": {
                "id": "affiliation",
                "label": "Affiliation",
                "aliases": ["affiliation", "department", "institution", "organization"],
                "fields": [
                    {"key": "department", "label": "Department", "aliases": ["department"]},
                    {"key": "institution", "label": "Institution", "aliases": ["institution", "organization"]},
                ],
            },
        },
    }


def load_semantic_registry(ui_config: dict[str, Any] | None) -> dict[str, object]:
    semantic_schema = load_semantic_schema(ui_config)
    return {
        "domain": "people",
        "schema": semantic_schema,
        "categories": {
            "people": {
                "entity_types": ["person"],
            },
            "affiliation": {
                "metadata_fields": ["department", "institution"],
            },
        },
        "metadata_hints": {
            "person": {
                "preferred_fields": ["title", "department", "institution", "summary"],
                "query_style": "json_extract",
            },
        },
        "operators": {
            "condition_handlers": {
                "metadata_filter": "metadata_filter",
                "contact_filter": "contact_filter",
                "relationship_filter": "relationship_filter",
            },
            "renderers": {
                "metadata": {
                    "where_templates": [
                        "  AND json_extract(e.metadata, '$.{field}') = '{value}'",
                    ],
                    "validation_signatures": [
                        "$.{field}",
                        "{value}",
                    ],
                },
                "contact": {
                    "join_templates": [
                        "JOIN contact_info {join_alias} ON {join_alias}.entity_id = e.id",
                    ],
                    "where_templates": [
                        "  AND {join_alias}.field = '{field}'",
                        "  AND {join_alias}.value = '{value}'",
                    ],
                    "validation_signatures": [
                        "c.field = '{field}'",
                        "{value}",
                    ],
                },
                "relationship": {
                    "join_templates": [
                        "JOIN relationships {join_alias} ON {join_alias}.source_id = e.id AND {join_alias}.rel_type = '{rel_type}'",
                        "JOIN entities {target_alias} ON {target_alias}.id = {join_alias}.target_id AND {target_alias}.type = '{target_type}'",
                    ],
                    "validation_signatures": [
                        "{rel_type}",
                    ],
                },
            },
            "parsers": {
                "field_value": {
                    "mode": "field_value",
                    "split_pattern": r"\s+\b(?:and|or)\b|[?!,]",
                },
                "presence": {
                    "mode": "presence",
                },
            },
            "specs": {
                "metadata_filters": {
                    "title": {
                        "field": "title",
                        "aliases": ["title"],
                        "parser_kind": "field_value",
                    },
                    "department": {
                        "field": "department",
                        "aliases": ["department"],
                        "parser_kind": "field_value",
                    },
                    "institution": {
                        "field": "institution",
                        "aliases": ["institution"],
                        "parser_kind": "field_value",
                    },
                },
                "contact_filters": {
                    "email": {
                        "field": "email",
                        "aliases": ["email"],
                        "parser_kind": "field_value",
                    },
                    "orcid": {
                        "field": "orcid",
                        "aliases": ["orcid"],
                        "parser_kind": "field_value",
                    },
                },
                "relationship_filters": {
                    "authored_publication": {
                        "rel_type": "AUTHORED",
                        "target_type": "publication",
                        "aliases": ["publication", "publications", "paper", "papers", "authored"],
                        "parser_kind": "presence",
                    },
                },
            },
        },
        "validation": {},
        "paths": {
            "person->person": [],
        },
    }
