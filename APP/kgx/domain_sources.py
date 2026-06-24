from __future__ import annotations

from typing import Any

from kgx.genomics_source import (
    load_detail_layouts as load_genomics_detail_layouts,
    load_semantic_registry as load_genomics_semantic_registry,
    load_semantic_schema as load_genomics_semantic_schema,
)
from kgx.people_source import (
    load_detail_layouts as load_people_detail_layouts,
    load_semantic_registry as load_people_semantic_registry,
    load_semantic_schema as load_people_semantic_schema,
)


def load_domain_detail_layouts(domain_name: str | None, ui_config: dict[str, Any] | None) -> dict[str, object]:
    name = str(domain_name or "").strip().lower()
    if name == "genomics":
        return load_genomics_detail_layouts(ui_config)
    if name == "people":
        return load_people_detail_layouts(ui_config)
    return {}


def load_domain_semantic_schema(domain_name: str | None, ui_config: dict[str, Any] | None) -> dict[str, object]:
    name = str(domain_name or "").strip().lower()
    if name == "genomics":
        return load_genomics_semantic_schema(ui_config)
    if name == "people":
        return load_people_semantic_schema(ui_config)
    return {}


def load_domain_semantic_registry(domain_name: str | None, ui_config: dict[str, Any] | None) -> dict[str, object]:
    name = str(domain_name or "").strip().lower()
    if name == "genomics":
        return load_genomics_semantic_registry(ui_config)
    if name == "people":
        return load_people_semantic_registry(ui_config)
    return {}
