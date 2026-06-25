from __future__ import annotations

import re
from typing import Any

from .base import RegistryChatModule


class RegistryFilterModule(RegistryChatModule):
    _FILTER_SPEC_TYPES: dict[str, str] = {}

    @staticmethod
    def _sql_literal(value: str) -> str:
        return str(value).replace("'", "''")

    @staticmethod
    def _format_template(template: str, context: dict[str, str]) -> str:
        try:
            return str(template).format(**context)
        except KeyError:
            return ""

    def _filter_specs(self, spec_key: str) -> list[dict[str, Any]]:
        operators = self._registry_operators()
        specs = operators.get("specs", {}) if isinstance(operators, dict) else {}
        spec_map = specs.get(spec_key, {}) if isinstance(specs, dict) else {}
        if not isinstance(spec_map, dict):
            return []
        filter_kind = self._FILTER_SPEC_TYPES.get(spec_key, "")
        items: list[dict[str, Any]] = []
        for filter_id, spec in spec_map.items():
            if not isinstance(spec, dict):
                continue
            item = {
                "id": str(filter_id),
                "aliases": [str(alias) for alias in list(spec.get("aliases", []) or []) if str(alias).strip()],
                "filter_kind": filter_kind,
                "parser_kind": str(spec.get("parser_kind", "") or ""),
            }
            if isinstance(spec.get("display"), dict):
                item["display"] = dict(spec.get("display", {}) or {})
            if filter_kind in {"metadata", "contact"}:
                item["field"] = str(spec.get("field", filter_id) or filter_id)
            if filter_kind == "relationship":
                item["rel_type"] = str(spec.get("rel_type", "") or "")
                item["target_type"] = str(spec.get("target_type", "") or "")
            items.append(item)
        return items

    def _filter_renderer(self, filter_kind: str) -> dict[str, Any]:
        operators = self._registry_operators()
        renderers = operators.get("renderers", {}) if isinstance(operators, dict) else {}
        renderer = renderers.get(str(filter_kind), {}) if isinstance(renderers, dict) else {}
        return dict(renderer) if isinstance(renderer, dict) else {}

    def _filter_parser(self, parser_kind: str) -> dict[str, Any]:
        operators = self._registry_operators()
        parsers = operators.get("parsers", {}) if isinstance(operators, dict) else {}
        parser = parsers.get(str(parser_kind), {}) if isinstance(parsers, dict) else {}
        return dict(parser) if isinstance(parser, dict) else {}

    def _all_filter_specs(self) -> list[dict[str, Any]]:
        return [
            item
            for spec_key in self._FILTER_SPEC_TYPES
            for item in self._filter_specs(spec_key)
        ]

    def _render_context(self, item: dict[str, str], *, join_alias: str = "", target_alias: str = "") -> dict[str, str]:
        context = {key: self._sql_literal(str(value)) for key, value in item.items()}
        if join_alias:
            context["join_alias"] = join_alias
        if target_alias:
            context["target_alias"] = target_alias
        return context

    def _default_evidence_columns(
        self,
        item: dict[str, str],
        *,
        join_alias: str,
        target_alias: str,
    ) -> list[tuple[str, str]]:
        kind = str(item.get("filter_kind", "") or "")
        field = str(item.get("field", "") or "")
        if kind == "metadata" and field:
            return [(f"json_extract(e.metadata, '$.{field}')", field)]
        if kind == "contact" and field:
            return [(f"{join_alias}.value", field)]
        if kind == "relationship":
            target_type = str(item.get("target_type", "") or "").strip()
            if target_type:
                return [(f"{target_alias}.name", f"{target_type}_name")]
        return []

    def _display_evidence_columns(
        self,
        item: dict[str, Any],
        *,
        join_alias: str,
        target_alias: str,
    ) -> list[tuple[str, str]]:
        display = item.get("display", {})
        if not isinstance(display, dict):
            return self._default_evidence_columns(item, join_alias=join_alias, target_alias=target_alias)
        if display.get("enabled", True) is False:
            return []

        alias = str(display.get("alias", "") or "").strip()
        expr_template = str(display.get("expr_template", "") or "").strip()
        if expr_template:
            expr = self._format_template(
                expr_template,
                self._render_context(
                    {key: str(value) for key, value in item.items() if key != "display"},
                    join_alias=join_alias,
                    target_alias=target_alias,
                ),
            ).strip()
            if expr:
                return [(expr, alias or str(item.get("field", "") or f"{item.get('id', 'value')}"))]

        default_columns = self._default_evidence_columns(item, join_alias=join_alias, target_alias=target_alias)
        if not default_columns:
            return []
        if not alias:
            return default_columns
        return [(default_columns[0][0], alias)]

    def _requested_filters(self, message: str) -> list[dict[str, Any]]:
        text = str(message or "").strip()
        low = f" {text.lower()} "
        requested: list[dict[str, str]] = []
        seen: set[str] = set()
        for spec in self._all_filter_specs():
            if spec["id"] in seen:
                continue
            aliases = [f" {alias.lower()} " for alias in list(spec.get("aliases", []) or [])]
            if not any(alias in low for alias in aliases):
                continue
            parser = self._filter_parser(str(spec.get("parser_kind", "") or ""))
            mode = str(parser.get("mode", "") or "")
            if mode == "presence":
                requested.append({
                    key: str(value)
                    for key, value in spec.items()
                    if key in {"id", "filter_kind", "rel_type", "target_type"}
                })
                if isinstance(spec.get("display"), dict):
                    requested[-1]["display"] = dict(spec.get("display", {}) or {})
                seen.add(spec["id"])
                continue
            if mode == "field_value":
                split_pattern = str(parser.get("split_pattern", r"\s+\b(?:and|or)\b|[?!,]") or r"\s+\b(?:and|or)\b|[?!,]")
                for alias in list(spec.get("aliases", []) or []):
                    match = re.search(rf"\b{re.escape(alias.lower())}\b", text.lower())
                    if not match:
                        continue
                    value_text = text[match.end():].strip()
                    value = re.split(split_pattern, value_text, maxsplit=1)[0].strip().strip("'\"")
                    if not value or spec.get("field") in seen:
                        continue
                    requested.append({
                        "id": str(spec["id"]),
                        "filter_kind": str(spec["filter_kind"]),
                        "field": str(spec["field"]),
                        "value": value,
                    })
                    if isinstance(spec.get("display"), dict):
                        requested[-1]["display"] = dict(spec.get("display", {}) or {})
                    seen.add(str(spec["field"]))
                    break
        return requested

    def registry_filter_result_type(self) -> str | None:
        return None

    def registry_filter_base_where(self, requested_type: str) -> list[str]:
        return [f"WHERE e.type = '{requested_type}'"]

    def registry_filter_unexpected_error(self, filter_kind: str, spec: dict[str, Any]) -> str:
        return ""

    def registry_filter_missing_error(self, filter_kind: str, item: dict[str, str]) -> str:
        return ""

    def validation_error(self, chat, sql: str, requested_types: list[str], message: str) -> str | None:
        requested_type = self.registry_filter_result_type()
        if not requested_type or requested_type not in requested_types:
            return None
        requested_filters = self._requested_filters(message)
        sql_low = str(sql or "").lower()
        requested_ids = {item["id"] for item in requested_filters}
        for spec in self._all_filter_specs():
            kind = str(spec.get("filter_kind", "") or "")
            renderer = self._filter_renderer(kind)
            signatures = [
                rendered.lower()
                for template in list(renderer.get("validation_signatures", []) or [])
                if (rendered := self._format_template(template, self._render_context({key: str(value) for key, value in spec.items()})))
            ]
            if signatures and any(signature in sql_low for signature in signatures) and spec["id"] not in requested_ids:
                return self.registry_filter_unexpected_error(kind, spec)
        for item in requested_filters:
            kind = str(item.get("filter_kind", "") or "")
            renderer = self._filter_renderer(kind)
            signatures = [
                rendered.lower()
                for template in list(renderer.get("validation_signatures", []) or [])
                if (rendered := self._format_template(template, self._render_context(item)))
            ]
            if signatures and not all(signature in sql_low for signature in signatures):
                return self.registry_filter_missing_error(kind, item)
        return None

    def synthesize_query(self, chat, message: str, sql: str, requested_types: list[str]) -> str | dict[str, Any] | None:
        requested_type = self.registry_filter_result_type()
        if not requested_type or requested_type not in requested_types:
            return None
        requested_filters = self._requested_filters(message)
        if not requested_filters:
            return None
        joins: list[str] = []
        where_lines = list(self.registry_filter_base_where(requested_type))
        join_indices: dict[str, int] = {}
        evidence_columns: list[tuple[str, str]] = []
        for item in requested_filters:
            kind = str(item.get("filter_kind", "") or "")
            renderer = self._filter_renderer(kind)
            join_indices[kind] = join_indices.get(kind, 0) + 1
            suffix = join_indices[kind]
            join_alias = f"{'r' if kind == 'relationship' else 'c' if kind == 'contact' else 'j'}{suffix}"
            target_alias = f"t{suffix}"
            context = self._render_context(item, join_alias=join_alias, target_alias=target_alias)
            for template in list(renderer.get("join_templates", []) or []):
                if "{target_type}" in template and not item.get("target_type"):
                    continue
                joins.append(self._format_template(template, context))
            for template in list(renderer.get("where_templates", []) or []):
                where_lines.append(self._format_template(template, context))
            evidence_columns.extend(self._display_evidence_columns(item, join_alias=join_alias, target_alias=target_alias))
        rendered_sql = "\n".join([
            self._select_clause_with_evidence(evidence_columns),
            "FROM entities e",
            *joins,
            *where_lines,
        ])
        return self._synthesis_result(
            rendered_sql,
            evidence_columns=evidence_columns,
            semantic_trace={
                "kind": "registry_filters",
                "requested_type": requested_type,
                "filter_ids": [str(item.get("id", "") or "") for item in requested_filters],
            },
        )

    def evidence_columns_for_sql(self, chat, message: str, sql: str, requested_types: list[str]) -> list[tuple[str, str]] | None:
        requested_type = self.registry_filter_result_type()
        if not requested_type or requested_type not in requested_types:
            return None
        requested_filters = self._requested_filters(message)
        if not requested_filters:
            return None
        evidence_columns: list[tuple[str, str]] = []
        for item in requested_filters:
            if str(item.get("filter_kind", "") or "") != "metadata":
                continue
            evidence_columns.extend(self._display_evidence_columns(item, join_alias="c1", target_alias="t1"))
        return evidence_columns or None
