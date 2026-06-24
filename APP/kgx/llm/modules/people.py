from __future__ import annotations

from typing import Any

from kgx.people_source import load_semantic_registry, load_semantic_schema

from .registry_filters import RegistryFilterModule


class PeopleChatModule(RegistryFilterModule):
    _FILTER_SPEC_TYPES = {
        "metadata_filters": "metadata",
        "contact_filters": "contact",
        "relationship_filters": "relationship",
    }

    def __init__(
        self,
        semantic_schema: dict[str, Any] | None = None,
        semantic_registry: dict[str, Any] | None = None,
    ):
        super().__init__(
            semantic_registry_loader=load_semantic_registry,
            semantic_schema=semantic_schema,
            semantic_registry=semantic_registry,
        )

    def corpus_section(self) -> str | None:
        return "people"

    def preferred_result_types(self, chat, message: str, available_types: list[str]) -> list[str]:
        low = f" {str(message or '').lower()} "
        if "person" in available_types and (" people " in low or " person " in low or " persons " in low):
            return ["person"]
        return []

    def schema_context_lines(self, chat) -> list[str]:
        hints = self.semantic_registry.get("metadata_hints", {}) if isinstance(self.semantic_registry, dict) else {}
        person_hints = hints.get("person", {}) if isinstance(hints, dict) else {}
        preferred_fields = [str(item) for item in list(person_hints.get("preferred_fields", []) or []) if str(item).strip()]
        if not preferred_fields:
            return []
        return [
            "People semantic hints: person queries usually filter person rows with "
            f"`json_extract(e.metadata, '$.<field>')` over preferred fields: {', '.join(preferred_fields)}."
        ]

    def registry_filter_result_type(self) -> str | None:
        return "person"

    def registry_filter_unexpected_error(self, filter_kind: str, spec: dict[str, Any]) -> str:
        if filter_kind == "metadata":
            return (
                f"Unexpected people metadata filter: the SQL constrains '{spec.get('field', '')}', but the user did not request that people filter."
            )
        if filter_kind == "contact":
            return (
                f"Unexpected people contact filter: the SQL constrains '{spec.get('field', '')}', but the user did not request that contact field."
            )
        if filter_kind == "relationship":
            return (
                f"Unexpected people relationship filter: the SQL constrains '{spec.get('rel_type', '')}', but the user did not request that relationship-based people filter."
            )
        return ""

    def registry_filter_missing_error(self, filter_kind: str, item: dict[str, str]) -> str:
        if filter_kind == "metadata":
            return (
                f"Missing people metadata filter: the user requested {item['field']} '{item['value']}', but the SQL does not constrain that person metadata field."
            )
        if filter_kind == "contact":
            return (
                f"Missing people contact filter: the user requested {item['field']} '{item['value']}', but the SQL does not constrain that contact field."
            )
        if filter_kind == "relationship":
            return (
                f"Missing people relationship filter: the user requested '{item['id']}', but the SQL does not include relationship '{item['rel_type']}'."
            )
        return ""
