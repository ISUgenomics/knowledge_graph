from __future__ import annotations

import json
import re
from typing import Any

from kgx.genomics_source import load_semantic_registry

from .base import RegistryConditionModule


class GenomicsChatModule(RegistryConditionModule):
    """Genomics semantic module.

    Most evidence/operator discovery now flows from the shared semantic registry.
    The remaining handwritten logic is intentionally limited to heuristics that
    still depend on live graph content or dynamic organism/tag naming, notably:
    - effector tag family expansion and organism scoping
    - live organism alias collection from the graph
    - tag-branch traversal for scope/effector discovery

    Those paths are the current fallback boundary rather than hidden semantic
    duplication. They are kept local until they can be represented declaratively
    without making the runtime more brittle.
    """
    _HOMOLOGY_SCOPE_ROOT = "homology-scope"
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
        return "genomics"

    def reconciliation_semantic_kinds(self) -> set[str]:
        return {
            "functional_derived_connections",
            "functional_annotation_ranking",
            "common_functional_annotation_terms",
            "common_promoted_entity_terms",
            "genomics_metadata_filters",
            "expression_ranking",
            "genomics_semantic_conditions",
            "broad_homology_organism_tags",
            "hgt_donor_result",
            "ortholog_count_map",
            "ortholog_member_edges",
        }

    @staticmethod
    def _message_matches_aliases(message: str, aliases: list[str]) -> bool:
        low = f" {str(message or '').lower()} "
        return any(alias in low for alias in aliases)

    @staticmethod
    def _requested_orthogroup_label(message: str) -> str:
        match = re.search(r"\b(?:orthogroup\s+)?(og\d{4,})\b", str(message or ""), re.IGNORECASE)
        return match.group(1).upper() if match else ""

    def _organism_name_aliases(self, name: str) -> set[str]:
        text = str(name or "").strip()
        if not text:
            return set()
        low = text.lower()
        aliases = {low}
        parts = low.split()
        if len(parts) >= 2:
            aliases.add(f"{parts[0][0]}. {parts[-1]}")
            aliases.add(parts[-1])
        overrides = (
            self.semantic_registry.get("organisms", {}).get("alias_overrides", {})
            if isinstance(self.semantic_registry, dict)
            else {}
        )
        aliases.update(str(item).strip().lower() for item in list(overrides.get(low, []) or []) if str(item).strip())
        return {alias.strip() for alias in aliases if alias.strip()}

    def _protein_evidence_specs(self) -> list[dict[str, Any]]:
        families = self._registry_relation_families()
        specs = families.get("protein_evidence", []) if isinstance(families, dict) else []
        return [dict(item) for item in list(specs or []) if isinstance(item, dict)]

    @staticmethod
    def _is_evidence_relation_spec(spec: dict[str, Any]) -> bool:
        if not isinstance(spec, dict):
            return False
        rel_type = str(spec.get("rel_type", "") or "").strip()
        aliases = [str(alias).strip() for alias in list(spec.get("aliases", []) or []) if str(alias).strip()]
        target_types = [str(item).strip() for item in list(spec.get("target_types", []) or []) if str(item).strip()]
        return bool(rel_type and aliases and target_types)

    def _evidence_relation_specs(self, family_id: str | None = None) -> list[dict[str, Any]]:
        families = self._registry_relation_families()
        if not isinstance(families, dict):
            return []
        selected = {str(family_id)} if family_id else set(families.keys())
        specs: list[dict[str, Any]] = []
        for current_family_id in selected:
            family_value = families.get(current_family_id, [])
            if not isinstance(family_value, list):
                continue
            for item in family_value:
                if not isinstance(item, dict) or not self._is_evidence_relation_spec(item):
                    continue
                spec = dict(item)
                spec.setdefault("parser_kind", "alias_match")
                spec["family_id"] = current_family_id
                specs.append(spec)
        return specs

    def _evidence_spec_by_id(self, evidence_id: str) -> dict[str, Any] | None:
        return next((spec for spec in self._evidence_relation_specs() if spec.get("id") == evidence_id), None)

    def _ortholog_member_spec(self) -> dict[str, Any]:
        ortholog_member = self._registry_relation_family("ortholog_member")
        return dict(ortholog_member) if isinstance(ortholog_member, dict) else {}

    def _ortholog_member_aliases(self) -> list[str]:
        aliases = list(self._ortholog_member_spec().get("aliases", []) or [])
        return [str(alias) for alias in aliases if str(alias).strip()]

    def _relation_family(self, family_id: str) -> dict[str, Any]:
        return self._registry_relation_family(family_id)

    def _condition_parser(self, parser_kind: str) -> dict[str, Any]:
        operators = self._registry_operators()
        parsers = operators.get("parsers", {}) if isinstance(operators, dict) else {}
        parser = parsers.get(str(parser_kind), {}) if isinstance(parsers, dict) else {}
        return dict(parser) if isinstance(parser, dict) else {}

    def _scope_tag_operator(self, tag_id: str) -> dict[str, Any]:
        operators = self._registry_operators()
        scope_tags = operators.get("scope_tags", {}) if isinstance(operators, dict) else {}
        operator = scope_tags.get(str(tag_id), {}) if isinstance(scope_tags, dict) else {}
        return dict(operator) if isinstance(operator, dict) else {}

    def _validation_config(self) -> dict[str, Any]:
        validation = self.semantic_registry.get("validation", {}) if isinstance(self.semantic_registry, dict) else {}
        return dict(validation) if isinstance(validation, dict) else {}

    def _metadata_filter_specs(self) -> list[dict[str, Any]]:
        operators = self._registry_operators()
        specs = operators.get("specs", {}) if isinstance(operators, dict) else {}
        metadata_filters = specs.get("metadata_filters", {}) if isinstance(specs, dict) else {}
        if not isinstance(metadata_filters, dict):
            return []
        items: list[dict[str, Any]] = []
        for filter_id, spec in metadata_filters.items():
            if not isinstance(spec, dict):
                continue
            item = {
                "id": str(filter_id),
                "field": str(spec.get("field", filter_id) or filter_id),
                "aliases": [str(alias) for alias in list(spec.get("aliases", []) or []) if str(alias).strip()],
                "parser_kind": str(spec.get("parser_kind", "") or ""),
                "owner_type": str(spec.get("owner_type", "") or ""),
                "category": str(spec.get("category", "") or ""),
            }
            if isinstance(spec.get("display"), dict):
                item["display"] = dict(spec.get("display", {}) or {})
            item["aliases"] = self._expanded_metadata_filter_aliases(item)
            items.append(item)
        return items

    @staticmethod
    def _expanded_metadata_filter_aliases(spec: dict[str, Any]) -> list[str]:
        aliases = [str(alias) for alias in list(spec.get("aliases", []) or []) if str(alias).strip()]
        field = str(spec.get("field", "") or "")
        category = str(spec.get("category", "") or "")
        if category == "sequence":
            if field == "protein_sequence":
                aliases.extend(["protein sequence", "sequence", "amino acid sequence"])
            elif field == "mrna_sequence":
                aliases.extend(["mrna sequence", "mrna seq", "rna sequence", "nucleotide sequence"])
        seen: set[str] = set()
        ordered: list[str] = []
        for alias in aliases:
            norm = alias.strip().lower()
            if not norm or norm in seen:
                continue
            seen.add(norm)
            ordered.append(norm)
        return ordered

    def _metadata_filter_renderer(self) -> dict[str, Any]:
        operators = self._registry_operators()
        renderers = operators.get("renderers", {}) if isinstance(operators, dict) else {}
        renderer = renderers.get("metadata", {}) if isinstance(renderers, dict) else {}
        return dict(renderer) if isinstance(renderer, dict) else {}

    @staticmethod
    def _sql_literal(value: str) -> str:
        return str(value).replace("'", "''")

    @staticmethod
    def _format_registry_template(template: str, context: dict[str, str]) -> str:
        try:
            return str(template).format(**context)
        except KeyError:
            return ""

    def _condition_display_specs(self, condition: dict[str, Any]) -> list[dict[str, str]]:
        direct_display = condition.get("display", [])
        if isinstance(direct_display, list):
            items = [dict(item) for item in list(direct_display or []) if isinstance(item, dict)]
            if items:
                return items
        kind = str(condition.get("kind", "") or "")
        if kind == "orthogroup_filter":
            spec = self._registry_operator_spec("orthogroup_filter")
            display = spec.get("display", []) if isinstance(spec, dict) else []
            return [dict(item) for item in list(display or []) if isinstance(item, dict)]
        if kind == "scope_tag":
            operator = self._scope_tag_operator(str(condition.get("tag_id", "") or ""))
            display = operator.get("display", []) if isinstance(operator, dict) else []
            return [dict(item) for item in list(display or []) if isinstance(item, dict)]
        return []

    def _condition_display_value(
        self,
        chat,
        condition: dict[str, Any],
        display_spec: dict[str, str],
    ) -> str:
        value_ref = str(display_spec.get("value_ref", "") or "").strip()
        if value_ref:
            return str(condition.get(value_ref, "") or "")
        value_source = str(display_spec.get("value_source", "") or "").strip()
        if value_source == "tag_name":
            tag_id = str(condition.get("tag_id", "") or "")
            entity = chat.db.get_entity(tag_id) if tag_id else None
            return str((entity or {}).get("name", "") or "")
        return str(display_spec.get("value", "") or "")

    def _semantic_condition_evidence_columns(
        self,
        chat,
        conditions: list[dict[str, Any]],
    ) -> list[tuple[str, str]]:
        evidence_columns: list[tuple[str, str]] = []
        seen_aliases: set[str] = set()
        for cond in conditions:
            for display_spec in self._condition_display_specs(cond):
                alias = str(display_spec.get("alias", "") or "").strip()
                if not alias or alias in seen_aliases:
                    continue
                value = self._sql_literal(self._condition_display_value(chat, cond, display_spec))
                if not value:
                    continue
                evidence_columns.append((f"'{value}'", alias))
                seen_aliases.add(alias)
        return evidence_columns

    def _accepted_sql_condition_evidence_columns(
        self,
        requested_type: str,
        conditions: list[dict[str, Any]],
    ) -> list[tuple[str, str]]:
        evidence_columns: list[tuple[str, str]] = []
        seen_aliases: set[str] = set()
        for cond in conditions:
            owner_types = [str(item) for item in list(cond.get("owner_types", []) or [cond.get("owner_type", "")]) if str(item).strip()]
            if requested_type not in owner_types:
                continue
            if cond.get("kind") == "protein_evidence":
                context = {
                    **self._protein_evidence_context(cond),
                    "owner_ref": "e.id",
                }
            elif cond.get("kind") == "tag_evidence":
                context = {
                    **self._tag_evidence_context(cond),
                    "owner_ref": "e.id",
                }
            else:
                continue
            for expr, alias in self._condition_display_columns_from_context(cond, context):
                alias_text = str(alias).strip()
                expr_text = str(expr).strip()
                if not alias_text or not expr_text or alias_text in seen_aliases:
                    continue
                evidence_columns.append((expr_text, alias_text))
                seen_aliases.add(alias_text)
        return evidence_columns

    def _requested_metadata_filters(self, message: str) -> list[dict[str, Any]]:
        text = str(message or "").strip()
        requested: list[dict[str, Any]] = []
        seen: set[str] = set()
        for spec in self._metadata_filter_specs():
            if spec["field"] in seen:
                continue
            parser = self._condition_parser(str(spec.get("parser_kind", "") or ""))
            if str(parser.get("mode", "") or "") != "field_value":
                continue
            split_pattern = str(parser.get("split_pattern", r"\s+\b(?:and|or)\b|[?!,]") or r"\s+\b(?:and|or)\b|[?!,]")
            for alias in list(spec.get("aliases", []) or []):
                match = re.search(rf"\b{re.escape(alias.lower())}\b", text.lower())
                if not match:
                    continue
                value_text = text[match.end():].strip()
                value = re.split(split_pattern, value_text, maxsplit=1)[0].strip().strip("'\"")
                if not value:
                    continue
                item = {
                    "id": str(spec["id"]),
                    "field": str(spec["field"]),
                    "value": value,
                    "owner_type": str(spec.get("owner_type", "") or ""),
                    "category": str(spec.get("category", "") or ""),
                }
                if isinstance(spec.get("display"), dict):
                    item["display"] = dict(spec.get("display", {}) or {})
                requested.append(item)
                seen.add(str(spec["field"]))
                break
        return requested

    def _metadata_filter_context(self, item: dict[str, Any]) -> dict[str, str]:
        return {key: self._sql_literal(str(value)) for key, value in item.items() if key != "display"}

    @staticmethod
    def _requested_limit(message: str) -> int | None:
        low = str(message or "").lower()
        for pattern in [
            r"\btop\s+(\d+)\b",
            r"\bselect\s+(\d+)\s+(?:genes?|proteins?|transcripts?|chromosomes?)\b",
            r"\bfirst\s+(\d+)\b",
        ]:
            match = re.search(pattern, low)
            if match:
                return int(match.group(1))
        return None

    @staticmethod
    def _requests_functional_derived_connections(message: str, requested_types: list[str]) -> bool:
        low = f" {str(message or '').lower()} "
        if "protein" not in requested_types:
            return False
        if " connection " not in low and " connections " not in low:
            return False
        derived_cue = (
            " derived " in low
            or " cross connection " in low
            or " cross connections " in low
            or " other proteins " in low
        )
        if not derived_cue:
            return False
        return (
            " protein " in low
            or " proteins " in low
        )

    def _functional_derived_connection_query(
        self,
        chat,
        message: str,
        requested_types: list[str],
    ) -> str | dict[str, Any] | None:
        if not self._requests_functional_derived_connections(message, requested_types):
            return None
        patterns = set(chat._typed_rel_patterns())
        if ("protein", "HAS_ANNOTATION", "annotation_term") not in patterns:
            return None
        limit = self._requested_limit(message)
        low = f" {str(message or '').lower()} "
        if limit is None and (" most " in low or " highest " in low):
            limit = 1
        evidence_columns = [
            ("COUNT(DISTINCT other.id)", "derived_connection_count"),
            ("COUNT(DISTINCT ann.id)", "shared_annotation_count"),
        ]
        lines = [
            self._select_clause_with_evidence(evidence_columns),
            "FROM entities e",
            "JOIN relationships ha1 ON ha1.source_id = e.id AND ha1.rel_type = 'HAS_ANNOTATION'",
            "JOIN entities ann ON ann.id = ha1.target_id AND ann.type = 'annotation_term'",
            "JOIN relationships ha2 ON ha2.target_id = ann.id AND ha2.rel_type = 'HAS_ANNOTATION'",
            "JOIN entities other ON other.id = ha2.source_id AND other.type = 'protein'",
            "WHERE e.type = 'protein'",
            "  AND other.id != e.id",
            "GROUP BY e.id, e.name, e.type",
            "ORDER BY derived_connection_count DESC, shared_annotation_count DESC, e.name ASC",
        ]
        if limit:
            lines.append(f"LIMIT {int(limit)}")
        return self._synthesis_result(
            "\n".join(lines),
            evidence_columns=evidence_columns,
            semantic_trace={"kind": "functional_derived_connections"},
        )

    @staticmethod
    def _requests_functional_annotation_ranking(message: str, requested_types: list[str]) -> bool:
        low = f" {str(message or '').lower()} "
        if not any(item in {"gene", "transcript", "protein"} for item in requested_types):
            return False
        annotation_cue = (
            " functional annotation " in low
            or " functional annotations " in low
            or " annotation " in low
            or " annotations " in low
        )
        ranking_cue = (
            " most " in low
            or " highest " in low
            or " top " in low
        )
        return annotation_cue and ranking_cue

    def _functional_annotation_owner_type(
        self,
        chat,
        requested_type: str,
    ) -> tuple[str, list[tuple[str, str, str]]]:
        patterns = set(chat._typed_rel_patterns())
        if (requested_type, "HAS_ANNOTATION", "annotation_term") in patterns:
            return requested_type, []
        candidates: list[tuple[int, str, list[tuple[str, str, str]]]] = []
        for owner_type in ("protein", "transcript", "gene"):
            if (owner_type, "HAS_ANNOTATION", "annotation_term") not in patterns:
                continue
            path = chat._shortest_type_path(requested_type, owner_type)
            if requested_type == owner_type or path:
                candidates.append((len(path), owner_type, path))
        if not candidates:
            return "", []
        _distance, owner_type, path = sorted(candidates, key=lambda item: (item[0], item[1]))[0]
        return owner_type, path

    def _functional_annotation_ranking_query(
        self,
        chat,
        message: str,
        requested_types: list[str],
    ) -> str | dict[str, Any] | None:
        if not self._requests_functional_annotation_ranking(message, requested_types):
            return None
        requested_type = self._requested_core_type(requested_types)
        if requested_type not in {"gene", "transcript", "protein"}:
            return None
        owner_type, path = self._functional_annotation_owner_type(chat, requested_type)
        if not owner_type:
            return None
        limit = self._requested_limit(message)
        low = f" {str(message or '').lower()} "
        if limit is None and (" most " in low or " highest " in low):
            limit = 1
        joins: list[str] = []
        owner_ref = "e.id"
        alias_index = 0
        current_type = requested_type
        for src, rel, dst in path:
            if src != current_type:
                return None
            alias_index += 1
            rel_alias = f"p{alias_index}"
            joins.append(
                f"JOIN relationships {rel_alias} ON {rel_alias}.source_id = {owner_ref} AND {rel_alias}.rel_type = '{rel}'"
            )
            owner_ref = f"{rel_alias}.target_id"
            current_type = dst
        evidence_columns = [
            ("COUNT(DISTINCT ann.id)", "functional_annotation_count"),
        ]
        lines = [
            self._select_clause_with_evidence(evidence_columns),
            "FROM entities e",
            *joins,
            f"JOIN relationships ha ON ha.source_id = {owner_ref} AND ha.rel_type = 'HAS_ANNOTATION'",
            "JOIN entities ann ON ann.id = ha.target_id AND ann.type = 'annotation_term'",
            f"WHERE e.type = '{requested_type}'",
            "GROUP BY e.id, e.name, e.type",
            "ORDER BY functional_annotation_count DESC, e.name ASC",
        ]
        if limit:
            lines.append(f"LIMIT {int(limit)}")
        return self._synthesis_result(
            "\n".join(lines),
            evidence_columns=evidence_columns,
            semantic_trace={
                "kind": "functional_annotation_ranking",
                "requested_type": requested_type,
                "owner_type": owner_type,
            },
        )

    @staticmethod
    def _functional_annotation_namespace_specs() -> list[dict[str, Any]]:
        return [
            {"namespace": "go", "category": "functional_annotation", "aliases": [" go term ", " go terms ", " gene ontology ", " gene ontology term ", " gene ontology terms "]},
            {"namespace": "interpro", "category": "domain_annotation", "aliases": [" interpro ", " interpro domain ", " interpro domains "]},
            {"namespace": "pfam", "category": "domain_annotation", "aliases": [" pfam ", " pfam family ", " pfam families "]},
            {"namespace": "smart", "category": "domain_annotation", "aliases": [" smart domain ", " smart domains ", " smart "]},
            {"namespace": "funfam", "category": "domain_annotation", "aliases": [" funfam ", " funfam family ", " funfam families "]},
            {"namespace": "panther", "category": "domain_annotation", "aliases": [" panther ", " panther family ", " panther families "]},
        ]

    @staticmethod
    def _common_promoted_entity_specs() -> list[dict[str, Any]]:
        return [
            {
                "result_type": "annotation_term",
                "rel_type": "HAS_ANNOTATION",
                "category": "functional_annotation",
                "aliases": [" functional annotation ", " functional annotations ", " annotation term ", " annotation terms "],
                "count_alias": "annotated_entity_count",
            },
            {
                "result_type": "localization_call",
                "rel_type": "HAS_LOCALIZATION",
                "category": "localization",
                "aliases": [" localization assigned ", " localization ", " localizations ", " subcellular localization ", " subcellular localizations "],
                "count_alias": "assigned_entity_count",
            },
            {
                "result_type": "prediction_call",
                "rel_type": "HAS_PREDICTION",
                "category": "prediction_feature",
                "aliases": [" prediction assigned ", " prediction feature ", " prediction features ", " signal assigned ", " signal feature ", " signal features "],
                "count_alias": "assigned_entity_count",
            },
        ]

    def _requested_functional_annotation_namespace(self, message: str) -> dict[str, Any] | None:
        low = f" {str(message or '').lower()} "
        for spec in self._functional_annotation_namespace_specs():
            if any(alias in low for alias in spec["aliases"]):
                return dict(spec)
        return None

    def _requested_common_promoted_entity_spec(self, chat, message: str, available_types: list[str]) -> dict[str, Any] | None:
        low = f" {str(message or '').lower()} "
        for spec in self._common_promoted_entity_specs_for_chat(chat):
            if str(spec.get("result_type", "") or "") not in available_types:
                continue
            if any(alias in low for alias in list(spec.get("aliases", []) or [])):
                return dict(spec)
        return None

    def _live_promoted_entity_specs(self, chat) -> list[dict[str, Any]]:
        rows = chat.db.execute_read(
            """
            SELECT source.type AS owner_type,
                   target.type AS result_type,
                   r.rel_type AS rel_type,
                   json_extract(target.metadata, '$.category') AS category,
                   json_extract(target.metadata, '$.source_column') AS source_column
            FROM relationships r
            JOIN entities source ON source.id = r.source_id
            JOIN entities target ON target.id = r.target_id
            WHERE json_extract(target.metadata, '$.category') IS NOT NULL
              AND target.type != 'tag'
            GROUP BY source.type, target.type, r.rel_type, category, source_column
            ORDER BY source.type, target.type, r.rel_type, category, source_column
            """
        )
        specs: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str, str]] = set()
        for row in rows:
            owner_type = str(row.get("owner_type", "") or "").strip()
            result_type = str(row.get("result_type", "") or "").strip()
            rel_type = str(row.get("rel_type", "") or "").strip()
            category = str(row.get("category", "") or "").strip()
            source_column = str(row.get("source_column", "") or "").strip()
            if not owner_type or not result_type or not rel_type or not category:
                continue
            key = (owner_type, result_type, rel_type, category)
            if key in seen:
                continue
            seen.add(key)
            specs.append({
                "owner_type": owner_type,
                "result_type": result_type,
                "rel_type": rel_type,
                "category": category,
                "source_column": source_column,
            })
        return specs

    def _common_promoted_entity_specs_for_chat(self, chat) -> list[dict[str, Any]]:
        specs = [dict(item) for item in self._common_promoted_entity_specs()]
        known = {
            (
                str(item.get("owner_type", "protein") or "protein"),
                str(item.get("result_type", "") or ""),
                str(item.get("rel_type", "") or ""),
                str(item.get("category", "") or ""),
            )
            for item in specs
        }
        for item in self._live_promoted_entity_specs(chat):
            key = (
                str(item.get("owner_type", "") or ""),
                str(item.get("result_type", "") or ""),
                str(item.get("rel_type", "") or ""),
                str(item.get("category", "") or ""),
            )
            if key in known:
                continue
            auto = dict(item)
            category = str(auto.get("category", "") or "")
            source_column = str(auto.get("source_column", "") or "")
            auto["aliases"] = [
                f" {category.replace('_', ' ')} ",
                f" {source_column.replace('_', ' ')} " if source_column else "",
            ]
            auto["count_alias"] = "assigned_entity_count"
            specs.append(auto)
        return specs

    @staticmethod
    def _normalized_prompt_text(text: str) -> str:
        low = str(text or "").lower().replace("_", " ").replace("-", " ")
        low = re.sub(r"[^a-z0-9\s]+", " ", low)
        low = re.sub(r"\s+", " ", low).strip()
        return f" {low} " if low else " "

    @staticmethod
    def _promoted_call_name_aliases(name: str) -> set[str]:
        base = re.sub(r"\s+", " ", str(name or "").lower().replace("_", " ").replace("-", " ")).strip()
        if not base:
            return set()
        aliases = {base}
        parts = base.split()
        if parts and parts[-1].endswith("s"):
            aliases.add(" ".join(parts[:-1] + [parts[-1][:-1]]))
        if base.endswith(" domain"):
            aliases.add(base + "s")
        if base.endswith(" signal"):
            aliases.add(base + "s")
        return {alias.strip() for alias in aliases if alias.strip()}

    def _matched_promoted_call_conditions(self, chat, message: str) -> list[dict[str, Any]]:
        low = self._normalized_prompt_text(message)
        request_promoted = any(
            token in low
            for token in [
                " predicted ", " prediction ", " predictions ", " signal ",
                " localization ", " localized ", " assigned ", " measured ",
                " measurement ", " measurements ", " with ", " having ",
            ]
        )
        if not request_promoted:
            return []
        conditions: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for spec in self._common_promoted_entity_specs_for_chat(chat):
            result_type = str(spec.get("result_type", "") or "")
            rel_type = str(spec.get("rel_type", "") or "")
            category = str(spec.get("category", "") or "")
            owner_type = str(spec.get("owner_type", "protein") or "protein")
            source_column_hint = str(spec.get("source_column", "") or "").strip()
            rows = chat.db.execute_read(
                "SELECT id, name, metadata FROM entities WHERE type = ? ORDER BY id",
                (result_type,),
            )
            for row in rows:
                entity_id = str(row.get("id", "") or "").strip()
                entity_name = str(row.get("name", "") or "").strip()
                if not entity_id or not entity_name:
                    continue
                if entity_id in seen_ids:
                    continue
                aliases = self._promoted_call_name_aliases(entity_name)
                if source_column_hint:
                    aliases.add(source_column_hint.replace("_", " ").strip().lower())
                if not any(f" {alias} " in low for alias in aliases):
                    continue
                conditions.append({
                    "kind": "promoted_call",
                    "result_type": result_type,
                    "rel_type": rel_type,
                    "entity_id": entity_id,
                    "entity_name": entity_name,
                    "category": category,
                    "owner_type": owner_type,
                })
                seen_ids.add(entity_id)
        return conditions

    def _matched_generic_tag_conditions(self, chat, message: str) -> list[dict[str, Any]]:
        low = self._normalized_prompt_text(message)
        if not any(token in low for token in [" tagged ", " tag ", " with tag ", " has tag ", " tagged as ", " tagged with "]):
            return []
        rows = chat.db.execute_read(
            """
            SELECT DISTINCT source.type AS owner_type, t.id, t.name
            FROM relationships r
            JOIN entities source ON source.id = r.source_id
            JOIN entities t ON t.id = r.target_id
            WHERE r.rel_type = 'TAGGED' AND t.type = 'tag'
            ORDER BY source.type, t.id
            """
        )
        conditions: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for row in rows:
            owner_type = str(row.get("owner_type", "") or "").strip()
            tag_id = str(row.get("id", "") or "").strip()
            tag_name = str(row.get("name", "") or "").strip()
            if not owner_type or not tag_id or not tag_name:
                continue
            aliases = self._promoted_call_name_aliases(tag_name)
            if not any(f" {alias} " in low for alias in aliases):
                continue
            key = (owner_type, tag_id)
            if key in seen:
                continue
            seen.add(key)
            conditions.append({
                "kind": "generic_tag",
                "owner_type": owner_type,
                "tag_id": tag_id,
                "tag_name": tag_name,
            })
        return conditions

    def _requests_functional_annotation_term_result(self, message: str, available_types: list[str]) -> bool:
        if "annotation_term" not in available_types:
            return False
        low = f" {str(message or '').lower()} "
        if self._requested_functional_annotation_namespace(message):
            return True
        return (
            (" annotation term " in low or " annotation terms " in low)
            or (
                (" functional annotation " in low or " functional annotations " in low)
                and not re.search(r"\b(genes?|proteins?|transcripts?)\b", low)
            )
        )

    def _requests_common_functional_annotation_terms(self, message: str, requested_types: list[str]) -> bool:
        low = f" {str(message or '').lower()} "
        if "annotation_term" not in requested_types:
            return False
        return (
            " most common " in low
            or " commonest " in low
            or " top " in low
            or " frequent " in low
            or " frequently " in low
        )

    @staticmethod
    def _requests_functional_annotation_category(message: str) -> bool:
        low = f" {str(message or '').lower()} "
        return " functional annotation " in low or " functional annotations " in low

    def _common_functional_annotation_terms_query(
        self,
        chat,
        message: str,
        requested_types: list[str],
    ) -> str | dict[str, Any] | None:
        if not self._requests_common_functional_annotation_terms(message, requested_types):
            return None
        patterns = set(chat._typed_rel_patterns())
        if ("protein", "HAS_ANNOTATION", "annotation_term") not in patterns:
            return None
        namespace_spec = self._requested_functional_annotation_namespace(message)
        low = f" {str(message or '').lower()} "
        limit = self._requested_limit(message)
        if limit is None and (" most common " in low or " commonest " in low):
            limit = 1
        where_lines = ["WHERE e.type = 'annotation_term'"]
        if namespace_spec:
            namespace = str(namespace_spec.get("namespace", "") or "").strip()
            category = str(namespace_spec.get("category", "") or "").strip()
            if namespace:
                where_lines.append(f"  AND json_extract(e.metadata, '$.namespace') = '{self._sql_literal(namespace)}'")
            if category:
                where_lines.append(f"  AND json_extract(e.metadata, '$.category') = '{self._sql_literal(category)}'")
        elif self._requests_functional_annotation_category(message):
            where_lines.append("  AND json_extract(e.metadata, '$.category') = 'functional_annotation'")
        evidence_columns = [
            ("COUNT(DISTINCT owner.id)", "annotated_entity_count"),
            ("json_extract(e.metadata, '$.namespace')", "annotation_namespace"),
            ("json_extract(e.metadata, '$.category')", "annotation_category"),
        ]
        lines = [
            self._select_clause_with_evidence(evidence_columns),
            "FROM entities e",
            "JOIN relationships ha ON ha.target_id = e.id AND ha.rel_type = 'HAS_ANNOTATION'",
            "JOIN entities owner ON owner.id = ha.source_id",
            *where_lines,
            "GROUP BY e.id, e.name, e.type",
            "ORDER BY annotated_entity_count DESC, e.name ASC",
        ]
        if limit:
            lines.append(f"LIMIT {int(limit)}")
        return self._synthesis_result(
            "\n".join(lines),
            evidence_columns=evidence_columns,
            semantic_trace={
                "kind": "common_functional_annotation_terms",
                "namespace": str((namespace_spec or {}).get("namespace", "") or ""),
            },
        )

    def _requests_common_promoted_entity_terms(self, message: str, requested_types: list[str]) -> dict[str, Any] | None:
        low = f" {str(message or '').lower()} "
        if not (
            " most common " in low
            or " commonest " in low
            or " top " in low
            or " frequent " in low
            or " frequently " in low
        ):
            return None
        requested = set(requested_types)
        for spec in self._common_promoted_entity_specs():
            if spec["result_type"] == "annotation_term":
                continue
            if spec["result_type"] in requested:
                return dict(spec)
        return None

    def _common_promoted_entity_terms_query(
        self,
        chat,
        message: str,
        requested_types: list[str],
    ) -> str | dict[str, Any] | None:
        spec = self._requests_common_promoted_entity_terms(message, requested_types)
        if not spec:
            return None
        rel_type = str(spec.get("rel_type", "") or "")
        result_type = str(spec.get("result_type", "") or "")
        count_alias = str(spec.get("count_alias", "assigned_entity_count") or "assigned_entity_count")
        patterns = set(chat._typed_rel_patterns())
        if ("protein", rel_type, result_type) not in patterns:
            return None
        low = f" {str(message or '').lower()} "
        limit = self._requested_limit(message)
        if limit is None and (" most common " in low or " commonest " in low):
            limit = 1
        where_lines = [f"WHERE e.type = '{self._sql_literal(result_type)}'"]
        category = str(spec.get("category", "") or "").strip()
        if category:
            where_lines.append(f"  AND json_extract(e.metadata, '$.category') = '{self._sql_literal(category)}'")
        evidence_columns = [
            ("COUNT(DISTINCT owner.id)", count_alias),
            ("json_extract(e.metadata, '$.category')", "call_category"),
            ("json_extract(e.metadata, '$.source_column')", "source_column"),
        ]
        lines = [
            self._select_clause_with_evidence(evidence_columns),
            "FROM entities e",
            f"JOIN relationships pr ON pr.target_id = e.id AND pr.rel_type = '{self._sql_literal(rel_type)}'",
            "JOIN entities owner ON owner.id = pr.source_id",
            *where_lines,
            "GROUP BY e.id, e.name, e.type",
            f"ORDER BY {count_alias} DESC, e.name ASC",
        ]
        if limit:
            lines.append(f"LIMIT {int(limit)}")
        return self._synthesis_result(
            "\n".join(lines),
            evidence_columns=evidence_columns,
            semantic_trace={
                "kind": "common_promoted_entity_terms",
                "result_type": result_type,
                "rel_type": rel_type,
            },
        )

    def _expression_ranking_request(self, chat, message: str, requested_types: list[str]) -> dict[str, str | int] | None:
        low = f" {str(message or '').lower()} "
        if " expression " not in low:
            return None
        if " highest " not in low and " lowest " not in low and " top " not in low:
            return None
        requested_type = requested_types[0] if requested_types else ""
        if not requested_type:
            return None
        limit = self._requested_limit(message)
        if limit is None:
            return None
        direction = "DESC" if (" highest " in low or " top " in low) else "ASC"
        rows = chat.db.execute_read("SELECT id, name, metadata FROM entities WHERE type = 'expression_measure' ORDER BY id")
        for row in rows:
            expr_id = str(row.get("id", "") or "")
            expr_name = str(row.get("name", "") or "")
            metadata = row.get("metadata", {}) or {}
            if isinstance(metadata, str):
                try:
                    metadata = json.loads(metadata)
                except Exception:
                    metadata = {}
            if not isinstance(metadata, dict):
                metadata = {}
            label = str(metadata.get("label", expr_name) or expr_name)
            source_column = str(metadata.get("source_column", "") or "").strip()
            aliases = {
                expr_name.lower(),
                label.lower(),
                expr_id.split(":", 1)[-1].lower(),
                f"in {label.lower()}",
                f"under {label.lower()}",
                f"{label.lower()} condition",
                f"in {label.lower()} condition",
                f"under {label.lower()} condition",
                f"{label.lower()} stage",
            }
            if not any(alias and alias in low for alias in aliases):
                continue
            if not source_column:
                continue
            return {
                "requested_type": requested_type,
                "owner_type": "transcript",
                "expr_id": expr_id,
                "expr_label": label,
                "source_column": source_column,
                "direction": direction,
                "limit": limit,
            }
        return None

    def _primary_organism_aliases(self, chat) -> set[str]:
        try:
            rows = chat.db.execute_read(
                """
                SELECT o.name
                FROM entities o
                JOIN relationships r ON r.source_id = o.id
                WHERE o.type = 'organism' AND r.rel_type = 'HAS_CHROMOSOME'
                GROUP BY o.id, o.name
                ORDER BY COUNT(*) DESC, o.name
                LIMIT 1
                """
            )
        except Exception:
            rows = []
        if not rows:
            return set()
        return self._organism_name_aliases(str(rows[0].get("name", "") or ""))

    def _secondary_organism_aliases(self, chat) -> set[str]:
        primary = self._primary_organism_aliases(chat)
        try:
            rows = chat.db.execute_read("SELECT name FROM entities WHERE type = 'organism' ORDER BY name")
        except Exception:
            rows = []
        aliases: set[str] = set()
        for row in rows:
            name = str(row.get("name", "") or "")
            these = self._organism_name_aliases(name)
            if these & primary:
                continue
            aliases.update(these)
        return aliases

    def _requested_homology_organism_matches(self, chat, message: str) -> list[dict[str, str]]:
        seen: set[tuple[str, str]] = set()
        matches: list[dict[str, str]] = []
        for phrase in chat._message_candidate_phrases(message):
            for entity_id, entity_type, entity_name in chat._entity_name_matches(phrase):
                if entity_type != "tag" or not str(entity_id).startswith("homology-organism:"):
                    continue
                key = (str(entity_id), str(entity_name))
                if key in seen:
                    continue
                seen.add(key)
                matches.append({
                    "tag_id": str(entity_id),
                    "name": str(entity_name),
                })
        return matches

    def _requested_organism_name_matches(self, chat, message: str) -> list[str]:
        seen: set[str] = set()
        names: list[str] = []
        for phrase in chat._message_candidate_phrases(message):
            for _entity_id, entity_type, entity_name in chat._entity_name_matches(phrase):
                if entity_type != "organism":
                    continue
                normalized = str(entity_name or "").strip()
                if not normalized or normalized in seen:
                    continue
                seen.add(normalized)
                names.append(normalized)
        return names

    def _schema_group_aliases(self, group_id: str) -> list[str]:
        groups = self._semantic_schema_groups()
        group = groups.get(group_id, {}) if isinstance(groups, dict) else {}
        aliases = list(group.get("aliases", []) or [])
        return [f" {alias.strip()} " for alias in aliases if str(alias).strip()]

    def _message_has_group_cue(self, message: str, group_id: str) -> bool:
        aliases = self._schema_group_aliases(group_id)
        return bool(aliases) and self._message_matches_aliases(message, aliases)

    def _dynamic_family_scoped_aliases(self, chat, family: dict[str, Any]) -> dict[str, set[str]]:
        # Genomics still owns only the live organism-alias lookup. The dynamic
        # family executor in the shared base handles how these scoped values are
        # interpreted by registry templates.
        return {
            "primary": self._primary_organism_aliases(chat),
            "secondary": self._secondary_organism_aliases(chat),
        }

    def _effector_tag_specs(self, chat) -> list[dict[str, Any]]:
        # Runtime adapter now only supplies the organism alias sets; branch/tag
        # expansion, classification, and alias rendering live in the shared
        # dynamic-family infrastructure plus registry config.
        specs = self._dynamic_family_specs(chat, "effector_evidence")
        for spec in specs:
            spec["display"] = self._effector_display_specs(spec)
        return specs

    @staticmethod
    def _tag_id_to_name_signature(tag_id: str) -> str:
        text = str(tag_id or "").strip()
        if not text:
            return ""
        if text.startswith("tag:"):
            text = text[len("tag:"):]
        text = text.replace("-", " ")
        return " ".join(word.capitalize() for word in text.split())

    @staticmethod
    def _effector_display_specs(spec: dict[str, Any]) -> list[dict[str, str]]:
        spec_id = str(spec.get("id", "") or "")
        display: list[dict[str, str]] = []
        if "scn-dna-effector" in spec_id:
            display.append({
                "alias": "scn_known_n",
                "expr_template": "(SELECT json_extract(o.metadata, '$.glycines_effectors_dna') FROM entities o WHERE o.id = {owner_ref})",
            })
        if "scn-protein-effector" in spec_id:
            display.append({
                "alias": "scn_known_p",
                "expr_template": "(SELECT json_extract(o.metadata, '$.glycines_effectors_prot') FROM entities o WHERE o.id = {owner_ref})",
            })
        if "bcn-known-effector" in spec_id:
            display.append({
                "alias": "bcn_known",
                "expr_template": "(SELECT json_extract(o.metadata, '$.schachtii_effectors_known') FROM entities o WHERE o.id = {owner_ref})",
            })
        if "bcn-putative-effector" in spec_id:
            display.append({
                "alias": "bcn_putative",
                "expr_template": "(SELECT json_extract(o.metadata, '$.schachtii_effectors_putative') FROM entities o WHERE o.id = {owner_ref})",
            })
        if spec.get("is_putative"):
            display.append({
                "alias": "scn_putative",
                "expr_template": "(SELECT json_extract(o.metadata, '$.effector') FROM entities o WHERE o.id = {owner_ref})",
            })
        return display

    @staticmethod
    def _scope_aliases_for_tag(tag_id: str, tag_name: str) -> list[str]:
        aliases = {
            str(tag_name or "").strip().lower(),
            str(tag_id or "").strip().lower().replace("homology-scope-", "").replace("-", " "),
        }
        return [f" {alias.strip()} " for alias in aliases if alias.strip()]

    def _homology_scope_branch(self, chat) -> list[tuple[str, str]]:
        branch_ids = chat.db._ordered_branch_ids(self._HOMOLOGY_SCOPE_ROOT, hierarchy_edge="BROADER")
        if branch_ids == [self._HOMOLOGY_SCOPE_ROOT] and not chat.db.get_entity(self._HOMOLOGY_SCOPE_ROOT):
            rows = chat.db.execute_read(
                "SELECT id, name FROM entities WHERE type = 'tag' AND id LIKE 'homology-scope-%' ORDER BY id"
            )
            return [(row["id"], row.get("name", row["id"])) for row in rows]
        branch: list[tuple[str, str]] = []
        for tag_id in branch_ids:
            entity = chat.db.get_entity(tag_id)
            if not entity or entity.get("type") != "tag" or entity.get("id") == self._HOMOLOGY_SCOPE_ROOT:
                continue
            branch.append((entity["id"], entity.get("name", entity["id"])))
        return branch

    def _requested_scope_tag_ids(self, chat, message: str) -> list[str]:
        low = f" {str(message or '').lower()} "
        has_effector_cue = any(
            self._message_matches_aliases(message, list(spec.get("aliases", []) or []))
            for spec in self._effector_tag_specs(chat)
        ) or self._message_has_group_cue(message, "effectors")
        scope_tags = self._registry_operators().get("scope_tags", {}) if isinstance(self._registry_operators(), dict) else {}
        parser_kind = ""
        for operator in scope_tags.values() if isinstance(scope_tags, dict) else []:
            if isinstance(operator, dict) and operator.get("parser_kind"):
                parser_kind = str(operator.get("parser_kind", "") or "")
                break
        parser = self._condition_parser(parser_kind)
        required_message_cues = [str(cue) for cue in list(parser.get("required_message_cues", []) or []) if str(cue).strip()]
        required_group_cues = [str(group_id) for group_id in list(parser.get("required_group_cues", []) or []) if str(group_id).strip()]
        blocked_group_cues = [str(group_id) for group_id in list(parser.get("blocked_group_cues", []) or []) if str(group_id).strip()]
        required_relation_families = [str(family_id) for family_id in list(parser.get("required_relation_families", []) or []) if str(family_id).strip()]
        has_required_message_cue = any(cue in low for cue in required_message_cues)
        has_required_group_cue = any(self._message_has_group_cue(message, group_id) for group_id in required_group_cues)
        has_required_relation_family = any(
            any(
                self._message_matches_aliases(message, list(spec.get("aliases", []) or []))
                for spec in self._evidence_relation_specs(family_id)
            )
            for family_id in required_relation_families
        )
        has_required_cue = has_required_message_cue or has_required_group_cue or has_required_relation_family
        requires_cue = bool(required_message_cues or required_group_cues or required_relation_families)
        blocked = any(self._message_has_group_cue(message, group_id) for group_id in blocked_group_cues)
        if requires_cue and not has_required_cue:
            return []
        if blocked and not has_required_cue:
            return []

        found: list[str] = []
        for tag_id, tag_name in self._homology_scope_branch(chat):
            aliases = self._scope_aliases_for_tag(tag_id, tag_name)
            if self._message_matches_aliases(message, aliases):
                found.append(tag_id)

        pruned: list[str] = []
        found_set = set(found)
        for tag_id in found:
            descendants = chat.db._descendant_ids(tag_id, hierarchy_edge="BROADER")
            if any(descendant in found_set for descendant in descendants):
                continue
            pruned.append(tag_id)
        return pruned

    def _matched_protein_evidence_conditions(self, message: str) -> list[dict[str, Any]]:
        conditions: list[dict[str, Any]] = []
        for spec in self._evidence_relation_specs():
            parser = self._condition_parser(str(spec.get("parser_kind", "") or ""))
            parser_mode = str(parser.get("mode", "") or "alias_match")
            if parser_mode != "alias_match":
                continue
            if not self._message_matches_aliases(message, list(spec.get("aliases", []) or [])):
                continue
            owner_type = str(spec.get("owner_type", "protein") or "protein")
            conditions.append({"kind": "protein_evidence", **spec, "owner_types": [owner_type]})
        return conditions

    def _metadata_filter_query(self, chat, requested_type: str, filters: list[dict[str, Any]]) -> str | dict[str, Any] | None:
        if not filters:
            return None
        owner_types = {str(item.get("owner_type", "") or "") for item in filters if str(item.get("owner_type", "") or "")}
        if len(owner_types) != 1:
            return None
        owner_type = next(iter(owner_types), "")
        if not owner_type:
            return None
        joins: list[str] = []
        where_lines = [f"WHERE e.type = '{requested_type}'"]
        alias_index = 0
        path_joins, owner_ref, alias_index = self._append_path_joins(
            chat,
            from_type=requested_type,
            to_type=owner_type,
            current_node_ref="e.id",
            alias_index=alias_index,
        )
        if requested_type != owner_type and not path_joins:
            return None
        joins.extend(path_joins)
        if requested_type == owner_type:
            joins.append(f"JOIN entities owner ON owner.id = e.id AND owner.type = '{owner_type}'")
        else:
            joins.append(f"JOIN entities owner ON owner.id = {owner_ref} AND owner.type = '{owner_type}'")
        evidence_columns: list[tuple[str, str]] = []
        for item in filters:
            context = self._metadata_filter_context(item)
            for template in list(self._metadata_filter_renderer().get("where_templates", []) or []):
                where_lines.append(self._format_registry_template(str(template), context))
            field = str(item.get("field", "") or "")
            alias = ""
            if isinstance(item.get("display"), dict):
                alias = str(item["display"].get("alias", "") or "").strip()
            if field:
                evidence_columns.append((f"json_extract(owner.metadata, '$.{field}')", alias or field))
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
                "kind": "genomics_metadata_filters",
                "requested_type": requested_type,
                "filter_fields": [str(item.get("field", "") or "") for item in filters],
                "owner_type": owner_type,
            },
        )

    def _expression_ranking_query(self, chat, request: dict[str, str | int]) -> str | dict[str, Any] | None:
        requested_type = str(request.get("requested_type", "") or "")
        owner_type = str(request.get("owner_type", "") or "")
        expr_id = self._sql_literal(str(request.get("expr_id", "") or ""))
        source_column = self._sql_literal(str(request.get("source_column", "") or ""))
        direction = "DESC" if str(request.get("direction", "DESC") or "DESC").upper() == "DESC" else "ASC"
        limit = int(request.get("limit", 0) or 0)
        if not requested_type or not owner_type or not expr_id or not source_column or limit <= 0:
            return None
        joins: list[str] = []
        alias_index = 0
        path_joins, owner_ref, alias_index = self._append_path_joins(
            chat,
            from_type=requested_type,
            to_type=owner_type,
            current_node_ref="e.id",
            alias_index=alias_index,
        )
        if requested_type != owner_type and not path_joins:
            return None
        joins.extend(path_joins)
        if requested_type == owner_type:
            joins.append(f"JOIN entities owner ON owner.id = e.id AND owner.type = '{owner_type}'")
        else:
            joins.append(f"JOIN entities owner ON owner.id = {owner_ref} AND owner.type = '{owner_type}'")
        joins.append("JOIN relationships ex ON ex.source_id = owner.id AND ex.rel_type = 'HAS_EXPRESSION_SUMMARY'")
        joins.append(f"JOIN entities expr ON expr.id = ex.target_id AND expr.type = 'expression_measure' AND expr.id = '{expr_id}'")
        value_expr = f"CAST(json_extract(owner.metadata, '$.{source_column}') AS REAL)"
        evidence_columns = [
            ("expr.name", "expression_condition"),
            (value_expr, "expression_value"),
        ]
        rendered_sql = "\n".join([
            self._select_clause_with_evidence(evidence_columns),
            "FROM entities e",
            *joins,
            f"WHERE e.type = '{requested_type}'",
            f"  AND json_extract(owner.metadata, '$.{source_column}') IS NOT NULL",
            f"ORDER BY {value_expr} {direction}",
            f"LIMIT {limit}",
        ])
        return self._synthesis_result(
            rendered_sql,
            evidence_columns=evidence_columns,
            semantic_trace={
                "kind": "expression_ranking",
                "requested_type": requested_type,
                "expression_measure_id": str(request.get("expr_id", "") or ""),
                "source_column": source_column,
                "direction": direction,
                "limit": limit,
            },
        )

    def _matched_ortholog_member_conditions(self, message: str) -> list[dict[str, Any]]:
        spec = self._ortholog_member_spec()
        parser = self._condition_parser(str(spec.get("parser_kind", "") or ""))
        low = str(message or "").lower()
        ortholog_aliases = [str(alias) for alias in list(spec.get("aliases", []) or []) if str(alias).strip()]
        exclude_patterns = [str(pattern) for pattern in list(spec.get("exclude_patterns", []) or []) if str(pattern).strip()]
        parser_mode = str(parser.get("mode", "") or "alias_match")
        if (
            ortholog_aliases
            and self._message_matches_aliases(message, ortholog_aliases)
            and (
                parser_mode == "alias_match"
                or (parser_mode == "alias_match_excluding_terms" and not any(re.search(pattern, low) for pattern in exclude_patterns))
            )
        ):
            return [{"kind": "ortholog_member"}]
        return []

    def _semantic_conditions(self, chat, message: str) -> list[dict[str, Any]]:
        # Registry-driven discovery handles protein evidence, ortholog member,
        # and scope-tag cues. Effector conditions remain the main handwritten
        # fallback because they are derived from live branch/tag expansion.
        conditions: list[dict[str, Any]] = self._matched_protein_evidence_conditions(message)
        specific_effector_conditions: list[dict[str, Any]] = []
        generic_effector_conditions: list[dict[str, Any]] = []
        for spec in self._effector_tag_specs(chat):
            if self._message_matches_aliases(message, list(spec.get("primary_scoped_aliases", []) or [])):
                specific_effector_conditions.append({"kind": "tag_evidence", **spec})
                continue
            if self._message_matches_aliases(message, list(spec.get("secondary_scoped_aliases", []) or [])):
                specific_effector_conditions.append({"kind": "tag_evidence", **spec})
                continue
            if self._message_matches_aliases(message, list(spec.get("generic_aliases", []) or [])):
                generic_effector_conditions.append({"kind": "tag_evidence", **spec})
        conditions.extend(
            specific_effector_conditions
            or self._collapse_generic_effector_conditions(message, generic_effector_conditions)
        )
        evidence_ids = {cond["id"] for cond in conditions if cond["kind"] == "protein_evidence"}
        if "bcn_homology" in evidence_ids and "nematode_homology" in evidence_ids:
            conditions = [
                cond for cond in conditions
                if not (cond["kind"] == "protein_evidence" and cond["id"] == "nematode_homology")
            ]
        orthogroup_label = self._requested_orthogroup_label(message)
        if orthogroup_label:
            conditions.append({"kind": "orthogroup_filter", "label": orthogroup_label})
        conditions.extend(self._matched_ortholog_member_conditions(message))
        conditions.extend(self._matched_promoted_call_conditions(chat, message))
        conditions.extend(self._matched_generic_tag_conditions(chat, message))
        for tag_id in self._requested_scope_tag_ids(chat, message):
            conditions.append({"kind": "scope_tag", "tag_id": tag_id})
        return conditions

    @staticmethod
    def _collapse_generic_effector_conditions(message: str, conditions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if len(conditions) <= 1:
            return conditions
        low = f" {str(message or '').lower()} "
        requested_known = " known effector " in low or " known effectors " in low
        requested_putative = " putative effector " in low or " putative effectors " in low
        grouped: dict[tuple[str, tuple[str, ...]], dict[str, Any]] = {}
        for cond in conditions:
            if requested_known and (cond.get("is_known") or cond.get("is_dna") or cond.get("is_protein")):
                family = "known"
            elif requested_putative and cond.get("is_putative"):
                family = "putative"
            elif cond.get("is_known"):
                family = "known"
            elif cond.get("is_putative"):
                family = "putative"
            elif cond.get("is_dna"):
                family = "dna"
            elif cond.get("is_protein"):
                family = "protein"
            else:
                family = cond["id"]
            owner_types = tuple(list(cond.get("owner_types", []) or ["protein"]))
            key = (family, owner_types)
            if key not in grouped:
                grouped[key] = {
                    **cond,
                    "id": family,
                    "tag_ids": [],
                }
            for tag_id in list(cond.get("tag_ids", []) or []):
                if tag_id not in grouped[key]["tag_ids"]:
                    grouped[key]["tag_ids"].append(tag_id)
        return list(grouped.values())

    def preferred_result_types(self, chat, message: str, available_types: list[str]) -> list[str]:
        low = f" {str(message or '').lower()} "
        preferred: list[str] = []
        if self._requests_broad_homology_organism_tags(message, available_types):
            preferred.append("tag")
        requested_hgt_donor = self._requests_hgt_donor_result(message, available_types)
        if requested_hgt_donor:
            preferred.append("hgt_donor")
        if "protein" in available_types and re.search(r"\bproteins?\b", low):
            preferred.append("protein")
        if "transcript" in available_types and re.search(r"\btranscripts?\b", low):
            preferred.append("transcript")
        if "gene" in available_types and re.search(r"\bgenes?\b", low) and " gene transfer " not in low and not requested_hgt_donor:
            preferred.append("gene")
        explicit_core = bool(preferred)
        if self._requests_functional_annotation_term_result(message, available_types) and not explicit_core:
            preferred.append("annotation_term")
        promoted_spec = self._requested_common_promoted_entity_spec(chat, message, available_types)
        if promoted_spec and promoted_spec["result_type"] != "annotation_term" and not explicit_core:
            preferred.append(str(promoted_spec["result_type"]))
        if "bcn_gene" in available_types and self._message_matches_aliases(message, self._ortholog_member_aliases()) and not explicit_core:
            preferred.append("bcn_gene")
        if "comparative_hit" in available_types and self._message_matches_aliases(message, ["homology hit", "homology hits"]) and not explicit_core:
            preferred.append("comparative_hit")
        return preferred

    def suppressed_result_types(self, chat, message: str, available_types: list[str]) -> list[str]:
        if self._requests_broad_homology_organism_tags(message, available_types):
            return ["organism"]
        if self._requests_hgt_donor_result(message, available_types):
            return ["gene"]
        return []

    @staticmethod
    def _requests_hgt_donor_result(message: str, available_types: list[str]) -> bool:
        low = f" {str(message or '').lower()} "
        if "hgt_donor" not in available_types:
            return False
        explicit_type_check = low.replace(" horizontal gene transfer ", " ").replace(" hgt ", " ")
        if re.search(r"\b(genes?|proteins?|transcripts?)\b", explicit_type_check):
            return False
        return (
            " hgt donor " in low
            or " hgt donors " in low
            or " horizontal gene transfer donor " in low
            or " horizontal gene transfer donors " in low
        )

    @staticmethod
    def _requests_broad_homology_organism_tags(message: str, available_types: list[str]) -> bool:
        low = f" {str(message or '').lower()} "
        if "tag" not in available_types:
            return False
        broad_cue = (
            " broad homology " in low
            or " broad homologies " in low
            or " broad parasitism " in low
            or " broad parasistism " in low
        )
        organism_cue = (
            " organism " in low
            or " organisms " in low
            or " organism tag " in low
            or " organism tags " in low
        )
        return broad_cue and organism_cue

    def _requested_core_type(self, requested_types: list[str]) -> str:
        return next((item for item in requested_types if item in {"gene", "transcript", "protein"}), "")

    @staticmethod
    def _requests_hgt_donor_semantics(message: str) -> bool:
        low = f" {str(message or '').lower()} "
        return (
            " hgt donor " in low
            or " hgt donors " in low
            or " horizontal gene transfer donor " in low
            or " horizontal gene transfer donors " in low
        )

    def _ortholog_count_owner_type(
        self,
        chat,
        *,
        requested_type: str,
        selected_type: str,
        rel_type: str,
    ) -> tuple[str, list[tuple[str, str, str]]]:
        patterns = chat._typed_rel_patterns()
        if rel_type:
            target_types = sorted({dst for src, rel, dst in patterns if src == requested_type and rel == rel_type})
            owner_type = next((etype for etype in target_types if "gene_counts" in set(chat.db.metadata_keys(etype))), "")
            if owner_type:
                return owner_type, chat._shortest_type_path(requested_type, owner_type)
        if "gene_counts" in set(chat.db.metadata_keys(selected_type)):
            return selected_type, chat._shortest_type_path(requested_type, selected_type)

        candidate_types = sorted({
            row["type"]
            for row in chat.db.execute_read("SELECT type FROM entities GROUP BY type ORDER BY type")
            if "type" in row
        })
        for candidate_type in candidate_types:
            if "gene_counts" not in set(chat.db.metadata_keys(candidate_type)):
                continue
            path = chat._shortest_type_path(requested_type, candidate_type)
            if requested_type == candidate_type or path:
                return candidate_type, path
        return "", []

    def _owner_has_non_primary_gene_counts(self, chat, owner_type: str) -> bool:
        if not owner_type:
            return False
        try:
            rows = chat.db.execute_read(
                """
                SELECT 1
                FROM entities owner
                JOIN json_each(owner.metadata, '$.gene_counts') gc
                WHERE owner.type = ?
                  AND gc.key != json_extract(owner.metadata, '$.organism')
                LIMIT 1
                """,
                (owner_type,),
            )
        except Exception:
            return False
        return bool(rows)

    def _ortholog_member_edge_spec(self, chat, owner_type: str) -> tuple[list[str], list[str]]:
        rel_types: list[str] = []
        target_types: list[str] = []
        registry_rel_type = str(self._ortholog_member_spec().get("rel_type", "") or "").strip().upper()
        patterns = chat._typed_rel_patterns()
        for src, rel, dst in patterns:
            rel_up = str(rel or "").upper()
            if src != owner_type:
                continue
            if rel_up == registry_rel_type or rel_up == "HAS_BCN_MEMBER" or "ORTHOLOG_MEMBER" in rel_up:
                if rel_up not in rel_types:
                    rel_types.append(rel_up)
                if dst not in target_types:
                    target_types.append(dst)
        return rel_types, target_types

    def _protein_evidence_context(self, cond: dict[str, Any]) -> dict[str, Any]:
        owner_type = next(iter(list(cond.get("owner_types", []) or [cond.get("owner_type", "protein")])), "protein")
        return {
            "owner_type": str(owner_type or "protein"),
            "evidence_rel_type": str(cond.get("rel_type", "") or ""),
            "target_types": [str(item) for item in list(cond.get("target_types", []) or []) if str(item).strip()],
        }

    def _condition_display_columns_from_context(
        self,
        cond: dict[str, Any],
        context: dict[str, Any],
    ) -> list[tuple[str, str]]:
        columns: list[tuple[str, str]] = []
        display_specs = [dict(item) for item in list(cond.get("display", []) or []) if isinstance(item, dict)]
        target_types = [str(item) for item in list(context.get("target_types", []) or cond.get("target_types", []) or []) if str(item).strip()]
        display_context = {
            "owner_ref": str(context.get("owner_ref", "e.id") or "e.id"),
            "evidence_rel_type": str(context.get("evidence_rel_type", cond.get("rel_type", "")) or cond.get("rel_type", "")),
            "target_type": target_types[0] if target_types else "",
            "evidence_target": str(context.get("evidence_target", "") or ""),
        }
        for spec in display_specs:
            alias = str(spec.get("alias", "") or "").strip()
            if not alias:
                continue
            expr_template = str(spec.get("expr_template", "") or "").strip()
            if expr_template:
                expr = self._format_registry_template(expr_template, display_context).strip()
                if expr:
                    columns.append((expr, alias))
                    continue
            value_source = str(spec.get("value_source", "") or "").strip()
            if value_source == "target_name" and display_context["evidence_target"]:
                columns.append((f"{display_context['evidence_target']}.name", alias))
        return columns

    def _protein_evidence_rel_types(self) -> list[str]:
        rel_types: list[str] = []
        for spec in self._evidence_relation_specs():
            rel_type = str(spec.get("rel_type", "") or "").strip()
            if rel_type and rel_type not in rel_types:
                rel_types.append(rel_type)
        return rel_types

    def _scope_tag_context(self, tag_id: str, operator: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
        return {
            "tag_id": str(tag_id),
            "owner_type": str(operator.get("owner_type", evidence.get("owner_type", "protein")) or "protein"),
            "evidence_rel_type": str(evidence.get("rel_type", "") or ""),
            "target_types": [str(operator.get("target_type", "comparative_hit") or "comparative_hit")],
            "tag_rel_type": str(operator.get("tag_rel_type", "TAGGED") or "TAGGED"),
        }

    def _tag_evidence_context(self, cond: dict[str, Any]) -> dict[str, Any]:
        owner_type = next(iter(list(cond.get("owner_types", []) or ["protein"])), "protein")
        tag_ids = [str(tag_id) for tag_id in list(cond.get("tag_ids", []) or []) if str(tag_id).strip()]
        return {
            "owner_type": str(owner_type or "protein"),
            "tag_ids": tag_ids,
        }

    def _append_scope_tag_filter_from_context(
        self,
        *,
        tag_id: str,
        operator: dict[str, Any],
        joins: list[str],
        where_lines: list[str],
        alias_index: int,
        used_scope_tags: set[str],
        context: dict[str, Any],
    ) -> tuple[bool, int]:
        ok, alias_index, _context = self._append_registry_operator_joins(
            None,
            operator_id="scope_tag",
            requested_type=str(context.get("owner_type", "protein") or "protein"),
            joins=joins,
            where_lines=where_lines,
            alias_index=alias_index,
            template_context={
                "tag_id": tag_id,
                "owner_type": str(context.get("owner_type", "protein") or "protein"),
                "evidence_rel_type": str(context.get("evidence_rel_type", "") or ""),
                "target_types": list(context.get("target_types", []) or []),
                "tag_rel_type": str(operator.get("tag_rel_type", "TAGGED") or "TAGGED"),
            },
            initial_context={
                "owner_ref": context.get("owner_ref", "e.id"),
                "evidence_rel": context.get("evidence_rel", ""),
                "evidence_target": context.get("evidence_target", ""),
            },
        )
        if not ok:
            return False, alias_index
        used_scope_tags.add(tag_id)
        return True, alias_index

    def _append_protein_evidence_joins(
        self,
        chat,
        *,
        requested_type: str,
        cond: dict[str, Any],
        joins: list[str],
        where_lines: list[str],
        alias_index: int,
        scope_tag_ids: set[str],
        used_scope_tags: set[str],
        state: dict[str, Any],
        evidence_columns: list[tuple[str, str]] | None = None,
    ) -> tuple[bool, int]:
        ok, alias_index, context = self._append_registry_operator_joins(
            chat,
            operator_id="protein_evidence",
            requested_type=requested_type,
            joins=joins,
            where_lines=where_lines,
            alias_index=alias_index,
            template_context=self._protein_evidence_context(cond),
        )
        if not ok:
            return False, alias_index
        if evidence_columns is not None:
            evidence_columns.extend(self._condition_display_columns_from_context(cond, context))
        target_types = list(cond.get("target_types", []) or [])
        target_alias = str(context.get("evidence_target", "") or "")
        requested_homology_organisms = list(state.get("homology_organisms", []) or [])
        if cond.get("id") == "broad_homology" and target_alias and requested_homology_organisms:
            for organism in requested_homology_organisms:
                alias_index += 1
                tag_rel_alias = f"ho{alias_index}"
                alias_index += 1
                tag_alias = f"hot{alias_index}"
                tag_id = str(organism.get("tag_id", "") or "").strip()
                joins.append(
                    f"JOIN relationships {tag_rel_alias} ON {tag_rel_alias}.source_id = {target_alias}.id AND {tag_rel_alias}.rel_type = 'TAGGED'"
                )
                joins.append(
                    f"JOIN entities {tag_alias} ON {tag_alias}.id = {tag_rel_alias}.target_id AND {tag_alias}.type = 'tag'"
                )
                if tag_id:
                    where_lines.append(f"  AND {tag_alias}.id = '{tag_id}'")
                else:
                    literal = str(organism.get("name", "") or "").replace("'", "''")
                    where_lines.append(f"  AND {tag_alias}.name = '{literal}'")
                if evidence_columns is not None:
                    evidence_columns.append((f"{tag_alias}.name", "homolog_organism"))
        for scope_tag_id in scope_tag_ids:
            operator = self._scope_tag_operator(scope_tag_id)
            if operator.get("evidence_id") != cond["id"]:
                continue
            if target_types and operator.get("target_type") and operator.get("target_type") not in target_types:
                continue
            ok, alias_index = self._append_scope_tag_filter_from_context(
                tag_id=scope_tag_id,
                operator=operator,
                joins=joins,
                where_lines=where_lines,
                alias_index=alias_index,
                used_scope_tags=used_scope_tags,
                context={
                    **self._protein_evidence_context(cond),
                    "owner_ref": context.get("owner_ref", "e.id"),
                    "evidence_rel": context.get("evidence_rel", ""),
                    "evidence_target": target_alias,
                },
            )
            if not ok:
                return False, alias_index
        return True, alias_index

    def _append_scope_tag_joins(
        self,
        chat,
        *,
        requested_type: str,
        tag_id: str,
        joins: list[str],
        where_lines: list[str],
        alias_index: int,
        used_scope_tags: set[str],
    ) -> tuple[bool, int]:
        operator = self._scope_tag_operator(tag_id)
        if not operator:
            return True, alias_index
        evidence = self._evidence_spec_by_id(str(operator.get("evidence_id", "") or ""))
        if not evidence:
            return False, alias_index
        ok, alias_index, _context = self._append_registry_operator_joins(
            chat,
            operator_id="scope_tag",
            requested_type=requested_type,
            joins=joins,
            where_lines=where_lines,
            alias_index=alias_index,
            template_context=self._scope_tag_context(tag_id, operator, evidence),
        )
        if not ok:
            return False, alias_index
        used_scope_tags.add(tag_id)
        return True, alias_index

    def _append_tag_evidence_joins(
        self,
        chat,
        *,
        requested_type: str,
        cond: dict[str, Any],
        joins: list[str],
        alias_index: int,
        evidence_columns: list[tuple[str, str]] | None = None,
    ) -> tuple[bool, int]:
        ok, alias_index, context = self._append_registry_operator_joins(
            chat,
            operator_id="tag_evidence",
            requested_type=requested_type,
            joins=joins,
            where_lines=[],
            alias_index=alias_index,
            template_context=self._tag_evidence_context(cond),
        )
        if ok and evidence_columns is not None:
            evidence_columns.extend(self._condition_display_columns_from_context(cond, context))
        return ok, alias_index

    def _handle_condition_protein_evidence(
        self,
        chat,
        *,
        requested_type: str,
        condition: dict[str, Any],
        joins: list[str],
        where_lines: list[str],
        alias_index: int,
        state: dict[str, Any],
    ) -> tuple[bool, int]:
        return self._append_protein_evidence_joins(
            chat,
            requested_type=requested_type,
            cond=condition,
            joins=joins,
            where_lines=where_lines,
            alias_index=alias_index,
            scope_tag_ids=state.setdefault("scope_tag_ids", set()),
            used_scope_tags=state.setdefault("used_scope_tags", set()),
            state=state,
            evidence_columns=state.setdefault("evidence_columns", []),
        )

    def _handle_condition_orthogroup_filter(
        self,
        chat,
        *,
        requested_type: str,
        condition: dict[str, Any],
        joins: list[str],
        where_lines: list[str],
        alias_index: int,
        state: dict[str, Any],
    ) -> tuple[bool, int]:
        ok, alias_index, _context = self._append_registry_operator_joins(
            chat,
            operator_id="orthogroup_filter",
            requested_type=requested_type,
            joins=joins,
            where_lines=where_lines,
            alias_index=alias_index,
            template_context={"label": str(condition.get("label", "") or "")},
        )
        return ok, alias_index

    def _handle_condition_ortholog_member(
        self,
        chat,
        *,
        requested_type: str,
        condition: dict[str, Any],
        joins: list[str],
        where_lines: list[str],
        alias_index: int,
        state: dict[str, Any],
    ) -> tuple[bool, int]:
        ok, alias_index, _context = self._append_registry_operator_joins(
            chat,
            operator_id="ortholog_member",
            requested_type=requested_type,
            joins=joins,
            where_lines=where_lines,
            alias_index=alias_index,
        )
        return ok, alias_index

    def _handle_condition_scope_tag(
        self,
        chat,
        *,
        requested_type: str,
        condition: dict[str, Any],
        joins: list[str],
        where_lines: list[str],
        alias_index: int,
        state: dict[str, Any],
    ) -> tuple[bool, int]:
        tag_id = str(condition.get("tag_id", "") or "")
        used_scope_tags = state.setdefault("used_scope_tags", set())
        if tag_id in used_scope_tags or not state.get("has_protein_evidence", False):
            return True, alias_index
        return self._append_scope_tag_joins(
            chat,
            requested_type=requested_type,
            tag_id=tag_id,
            joins=joins,
            where_lines=where_lines,
            alias_index=alias_index,
            used_scope_tags=used_scope_tags,
        )

    def _handle_condition_tag_evidence(
        self,
        chat,
        *,
        requested_type: str,
        condition: dict[str, Any],
        joins: list[str],
        where_lines: list[str],
        alias_index: int,
        state: dict[str, Any],
    ) -> tuple[bool, int]:
        return self._append_tag_evidence_joins(
            chat,
            requested_type=requested_type,
            cond=condition,
            joins=joins,
            alias_index=alias_index,
            evidence_columns=state.setdefault("evidence_columns", []),
        )

    def _handle_condition_promoted_call(
        self,
        chat,
        *,
        requested_type: str,
        condition: dict[str, Any],
        joins: list[str],
        where_lines: list[str],
        alias_index: int,
        state: dict[str, Any],
    ) -> tuple[bool, int]:
        owner_type = str(condition.get("owner_type", "protein") or "protein")
        owner_ref = "e.id"
        current_type = requested_type
        if requested_type != owner_type:
            path = chat._shortest_type_path(requested_type, owner_type)
            if not path:
                return False, alias_index
            for src, rel, dst in path:
                if src != current_type:
                    return False, alias_index
                alias_index += 1
                rel_alias = f"pc{alias_index}"
                joins.append(
                    f"JOIN relationships {rel_alias} ON {rel_alias}.source_id = {owner_ref} AND {rel_alias}.rel_type = '{rel}'"
                )
                owner_ref = f"{rel_alias}.target_id"
                current_type = dst
        alias_index += 1
        rel_alias = f"pc{alias_index}"
        joins.append(
            f"JOIN relationships {rel_alias} ON {rel_alias}.source_id = {owner_ref} AND {rel_alias}.rel_type = '{str(condition.get('rel_type', '') or '')}'"
        )
        alias_index += 1
        target_alias = f"pcall{alias_index}"
        joins.append(
            f"JOIN entities {target_alias} ON {target_alias}.id = {rel_alias}.target_id AND {target_alias}.type = '{str(condition.get('result_type', '') or '')}'"
        )
        entity_id = str(condition.get("entity_id", "") or "").strip()
        category = str(condition.get("category", "") or "").strip()
        if entity_id:
            where_lines.append(f"  AND {target_alias}.id = '{self._sql_literal(entity_id)}'")
        if category:
            where_lines.append(f"  AND json_extract({target_alias}.metadata, '$.category') = '{self._sql_literal(category)}'")
        state.setdefault("evidence_columns", []).extend([
            (f"{target_alias}.name", "matched_call"),
            (f"json_extract({target_alias}.metadata, '$.category')", "matched_call_category"),
        ])
        return True, alias_index

    def _handle_condition_generic_tag(
        self,
        chat,
        *,
        requested_type: str,
        condition: dict[str, Any],
        joins: list[str],
        where_lines: list[str],
        alias_index: int,
        state: dict[str, Any],
    ) -> tuple[bool, int]:
        owner_type = str(condition.get("owner_type", "") or "").strip()
        owner_ref = "e.id"
        current_type = requested_type
        if requested_type != owner_type:
            path = chat._shortest_type_path(requested_type, owner_type)
            if not path:
                return False, alias_index
            for src, rel, dst in path:
                if src != current_type:
                    return False, alias_index
                alias_index += 1
                rel_alias = f"tg{alias_index}"
                joins.append(
                    f"JOIN relationships {rel_alias} ON {rel_alias}.source_id = {owner_ref} AND {rel_alias}.rel_type = '{rel}'"
                )
                owner_ref = f"{rel_alias}.target_id"
                current_type = dst
        alias_index += 1
        rel_alias = f"tg{alias_index}"
        joins.append(
            f"JOIN relationships {rel_alias} ON {rel_alias}.source_id = {owner_ref} AND {rel_alias}.rel_type = 'TAGGED'"
        )
        alias_index += 1
        tag_alias = f"tag{alias_index}"
        joins.append(
            f"JOIN entities {tag_alias} ON {tag_alias}.id = {rel_alias}.target_id AND {tag_alias}.type = 'tag'"
        )
        tag_id = str(condition.get("tag_id", "") or "").strip()
        if tag_id:
            where_lines.append(f"  AND {tag_alias}.id = '{self._sql_literal(tag_id)}'")
        state.setdefault("evidence_columns", []).append((f"{tag_alias}.name", "matched_tag"))
        return True, alias_index

    def _semantic_condition_handlers_map(self) -> dict[str, Any]:
        return {
            "protein_evidence": self._handle_condition_protein_evidence,
            "orthogroup_filter": self._handle_condition_orthogroup_filter,
            "ortholog_member": self._handle_condition_ortholog_member,
            "scope_tag": self._handle_condition_scope_tag,
            "tag_evidence": self._handle_condition_tag_evidence,
            "promoted_call": self._handle_condition_promoted_call,
            "generic_tag": self._handle_condition_generic_tag,
        }

    def _semantic_query(self, chat, message: str, requested_types: list[str]) -> str | dict[str, Any] | None:
        requested_type = self._requested_core_type(requested_types)
        if requested_type not in {"gene", "transcript", "protein"}:
            return None
        conditions = self._semantic_conditions(chat, message)
        if not conditions:
            return None
        state = {
            "scope_tag_ids": {cond["tag_id"] for cond in conditions if cond["kind"] == "scope_tag"},
            "used_scope_tags": set(),
            "has_protein_evidence": any(cond["kind"] == "protein_evidence" for cond in conditions),
            "evidence_columns": [],
            "homology_organisms": self._requested_homology_organism_matches(chat, message),
        }
        rendered_sql = self._build_semantic_entity_query(
            chat,
            requested_type=requested_type,
            conditions=conditions,
            distinct=True,
            state=state,
        )
        if not rendered_sql:
            return None
        evidence_columns = list(state.get("evidence_columns", []) or []) + self._semantic_condition_evidence_columns(chat, conditions)
        if evidence_columns:
            rendered_sql = rendered_sql.replace(
                "SELECT DISTINCT e.id, e.name, e.type",
                self._select_clause_with_evidence(evidence_columns),
                1,
            )
        return self._synthesis_result(
            rendered_sql,
            evidence_columns=evidence_columns,
            semantic_trace={
                "kind": "genomics_semantic_conditions",
                "requested_type": requested_type,
                "condition_kinds": [str(cond.get("kind", "") or "") for cond in conditions],
            },
        )

    def schema_context_lines(self, chat) -> list[str]:
        lines: list[str] = []
        metadata_hints = self.semantic_registry.get("metadata_hints", {}) if isinstance(self.semantic_registry, dict) else {}
        if isinstance(metadata_hints, dict):
            for hint_name, hint in metadata_hints.items():
                if not isinstance(hint, dict):
                    continue
                preferred_fields = [str(item) for item in list(hint.get("preferred_fields", []) or []) if str(item).strip()]
                target_types = [str(item) for item in list(hint.get("target_entity_types", []) or []) if str(item).strip()]
                query_style = str(hint.get("query_style", "json_extract") or "json_extract")
                if not preferred_fields:
                    continue
                target_text = f" on {', '.join(target_types)}" if target_types else ""
                lines.append(
                    f"{str(hint_name).replace('_', ' ').title()} semantic hints: use {query_style}{target_text} over preferred fields: {', '.join(preferred_fields)}."
                )
        try:
            count_map_examples = chat.db.conn.execute(
                """
                SELECT type
                FROM entities
                WHERE json_extract(metadata, '$.organism') IS NOT NULL
                  AND json_extract(metadata, '$.gene_counts') IS NOT NULL
                GROUP BY type
                ORDER BY type
                LIMIT 10
                """
            ).fetchall()
        except Exception:
            count_map_examples = []
        if count_map_examples:
            type_list = ", ".join(row["type"] for row in count_map_examples)
            lines.extend([
                "Count-map semantics: some entity types store primary-organism counts as "
                "`metadata.organism` + `metadata.gene_counts`. For those types, the primary count is the "
                "entry in `gene_counts` keyed by `organism`, and ortholog/other-organism counts are the other "
                f"entries in the same map. Types using this pattern: {type_list}",
                "Comparative and HGT evidence can live on protein rows and still be queried at the gene, "
                "transcript, or protein level by bridging through typed paths in either direction.",
            ])
        return lines

    def validation_error(self, chat, sql: str, requested_types: list[str], message: str) -> str | None:
        if not sql or not requested_types:
            return None
        sql_up = sql.upper()
        if self._requests_functional_derived_connections(message, requested_types):
            if (
                "HAS_ANNOTATION" not in sql_up
                or "COUNT(DISTINCT OTHER.ID)" not in sql_up
                or "OTHER.TYPE = 'PROTEIN'" not in sql_up
                or "OTHER.ID != E.ID" not in sql_up
            ):
                return (
                    "Missing functional derived-connection query: the user requested proteins with the most "
                    "derived cross connections to other proteins, so the SQL must count distinct other protein "
                    "neighbors connected through shared annotation mediators rather than generic relationship degree."
                )
        if self._requests_functional_annotation_ranking(message, requested_types):
            if (
                "HAS_ANNOTATION" not in sql_up
                or "COUNT(DISTINCT ANN.ID)" not in sql_up
                or "ANNOTATION_TERM" not in sql_up
            ):
                return (
                    "Missing functional-annotation ranking query: the user requested the entity with the most "
                    "functional annotations, so the SQL must count distinct annotation_term rows reached through "
                    "HAS_ANNOTATION on the correct typed path."
                )
        if self._requests_common_functional_annotation_terms(message, requested_types):
            namespace_spec = self._requested_functional_annotation_namespace(message)
            if (
                "HAS_ANNOTATION" not in sql_up
                or "COUNT(DISTINCT OWNER.ID)" not in sql_up
                or "E.TYPE = 'ANNOTATION_TERM'" not in sql_up
            ):
                return (
                    "Missing common annotation-term query: the user requested the most common functional annotation term, "
                    "so the SQL must return annotation_term rows and count distinct annotated owner entities through "
                    "HAS_ANNOTATION."
                )
            if namespace_spec:
                namespace = str(namespace_spec.get("namespace", "") or "").upper()
                category = str(namespace_spec.get("category", "") or "").upper()
                if namespace and f"$.NAMESPACE') = '{namespace}'" not in sql_up:
                    return (
                        "Wrong annotation namespace filter: the user requested a specific annotation family, "
                        f"so the SQL must constrain annotation_term.metadata.namespace = '{str(namespace_spec.get('namespace', '') or '')}'."
                    )
                if category and f"$.CATEGORY') = '{category}'" not in sql_up:
                    return (
                        "Wrong annotation category filter: the user requested a specific annotation family, "
                        f"so the SQL must constrain annotation_term.metadata.category = '{str(namespace_spec.get('category', '') or '')}'."
                    )
            elif self._requests_functional_annotation_category(message):
                if "$.CATEGORY') = 'FUNCTIONAL_ANNOTATION'" not in sql_up:
                    return (
                        "Wrong annotation category filter: the user requested functional annotations, "
                        "so the SQL must constrain annotation_term.metadata.category = 'functional_annotation'."
                    )
        promoted_spec = self._requests_common_promoted_entity_terms(message, requested_types)
        if promoted_spec:
            rel_type = str(promoted_spec.get("rel_type", "") or "").upper()
            result_type = str(promoted_spec.get("result_type", "") or "").upper()
            category = str(promoted_spec.get("category", "") or "").upper()
            if (
                rel_type not in sql_up
                or "COUNT(DISTINCT OWNER.ID)" not in sql_up
                or f"E.TYPE = '{result_type}'" not in sql_up
            ):
                return (
                    "Missing common promoted-call query: the user requested the most common assigned call, "
                    f"so the SQL must return {str(promoted_spec.get('result_type', '') or '')} rows and count distinct owner entities through "
                    f"{str(promoted_spec.get('rel_type', '') or '')}."
                )
            if category and f"$.CATEGORY') = '{category}'" not in sql_up:
                return (
                    "Wrong promoted-call category filter: the SQL must constrain "
                    f"{str(promoted_spec.get('result_type', '') or '')}.metadata.category = '{str(promoted_spec.get('category', '') or '')}'."
                )
        promoted_call_conditions = [cond for cond in self._semantic_conditions(chat, message) if cond.get("kind") == "promoted_call"]
        for cond in promoted_call_conditions:
            rel_type = str(cond.get("rel_type", "") or "").upper()
            entity_id = str(cond.get("entity_id", "") or "").upper()
            category = str(cond.get("category", "") or "").upper()
            if rel_type not in sql_up or entity_id not in sql_up:
                return (
                    "Missing promoted-call filter: the user requested a specific predicted/localization call, "
                    f"so the SQL must bridge through {str(cond.get('rel_type', '') or '')} and constrain "
                    f"the matched call entity '{str(cond.get('entity_name', '') or '')}'."
                )
            if category and f"$.CATEGORY') = '{category}'" not in sql_up:
                return (
                    "Wrong promoted-call category filter: the SQL must constrain "
                    f"{str(cond.get('result_type', '') or '')}.metadata.category = '{str(cond.get('category', '') or '')}'."
                )
        expression_ranking = self._expression_ranking_request(chat, message, requested_types)
        if expression_ranking:
            expr_id = str(expression_ranking["expr_id"]).upper()
            source_column = str(expression_ranking["source_column"])
            limit = int(expression_ranking["limit"])
            direction = str(expression_ranking["direction"]).upper()
            if (
                expr_id not in sql_up
                or f"$.{source_column}".upper() not in sql_up
                or f"LIMIT {limit}" not in sql_up
                or "ORDER BY" not in sql_up
                or direction not in sql_up
            ):
                return (
                    f"Missing stage-ranked expression semantics: the user requested top expression for '{expression_ranking['expr_label']}', "
                    f"but the SQL does not constrain expression measure '{expression_ranking['expr_id']}', order by transcript metadata "
                    f"field '{expression_ranking['source_column']}', and apply LIMIT {limit}."
                )
        requested_metadata_filters = self._requested_metadata_filters(message)
        metadata_renderer = self._metadata_filter_renderer()
        sql_low = str(sql or "").lower()
        requested_metadata_fields = {str(item.get("field", "") or "") for item in requested_metadata_filters}
        for spec in self._metadata_filter_specs():
            signatures = [
                rendered.lower()
                for template in list(metadata_renderer.get("validation_signatures", []) or [])
                if (rendered := self._format_registry_template(str(template), self._metadata_filter_context({
                    "id": str(spec["id"]),
                    "field": str(spec["field"]),
                    "value": "",
                    "owner_type": str(spec.get("owner_type", "") or ""),
                    "category": str(spec.get("category", "") or ""),
                }))) and rendered.strip()
            ]
            if signatures and any(signature in sql_low for signature in signatures) and spec["field"] not in requested_metadata_fields:
                return (
                    f"Unexpected genomics metadata filter: the SQL constrains '{spec['field']}', but the user did not request that metadata-based genomics filter."
                )
        for item in requested_metadata_filters:
            signatures = [
                rendered.lower()
                for template in list(metadata_renderer.get("validation_signatures", []) or [])
                if (rendered := self._format_registry_template(str(template), self._metadata_filter_context(item))) and rendered.strip()
            ]
            if signatures and not all(signature in sql_low for signature in signatures):
                return (
                    f"Missing genomics metadata filter: the user requested {item['field']} '{item['value']}', but the SQL does not constrain that metadata field."
                )
        requested_condition_kinds = self._semantic_conditions(chat, message)
        requested_protein_rel_types = {
            cond["rel_type"]
            for cond in requested_condition_kinds
            if cond["kind"] == "protein_evidence"
        }
        requested_scope_tags = {
            cond["tag_id"].upper()
            for cond in requested_condition_kinds
            if cond["kind"] == "scope_tag"
        }
        requested_tag_evidence_ids = {
            cond["id"]
            for cond in requested_condition_kinds
            if cond["kind"] == "tag_evidence"
        }
        ortholog_member_rel_types = self._operator_rel_types("ortholog_member")
        ortholog_member_rel_type = next((rel_type for rel_type in ortholog_member_rel_types if rel_type != "BELONGS_TO_ORTHOGROUP"), "")
        orthogroup_filter_rel_types = self._operator_rel_types("orthogroup_filter")
        orthogroup_filter_rel_type = next(iter(orthogroup_filter_rel_types), "")
        requested_has_bcn_member = any(cond["kind"] == "ortholog_member" for cond in requested_condition_kinds)
        unexpected_checks: list[tuple[list[str], bool, str]] = []
        for rel_type in self._protein_evidence_rel_types():
            unexpected_checks.append((
                [rel_type],
                rel_type in requested_protein_rel_types,
                (
                    f"Unexpected evidence condition: the SQL includes relationship '{rel_type}', but the user did not request that evidence. "
                    "Keep the requested result type and only apply evidence conditions that are explicitly implied by the prompt."
                ),
            ))
        for tag_id, _tag_name in self._homology_scope_branch(chat):
            unexpected_checks.append((
                [tag_id],
                tag_id.upper() in requested_scope_tags,
                (
                    f"Unexpected scope filter: the SQL constrains '{tag_id.lower()}', but the user did not request that homology scope. "
                    "Keep the requested result type and only apply scope filters that are explicitly implied by the prompt."
                ),
            ))
        if ortholog_member_rel_type:
            unexpected_checks.append((
                [ortholog_member_rel_type],
                requested_has_bcn_member,
                "Unexpected ortholog-member filter: the SQL requires ortholog members, but the user did not request an ortholog-member condition.",
            ))
        for spec in self._effector_tag_specs(chat):
            tag_name_signatures = [
                self._tag_id_to_name_signature(tag_id)
                for tag_id in list(spec.get("tag_ids", []) or [])
                if str(tag_id).strip()
            ]
            unexpected_checks.append((
                [
                    *[str(tag_id) for tag_id in list(spec.get("tag_ids", []) or []) if str(tag_id).strip()],
                    *[name for name in tag_name_signatures if name],
                ],
                spec["id"] in requested_tag_evidence_ids,
                (
                    f"Unexpected tag-evidence filter: the SQL constrains '{spec['id']}', but the user did not request that effector/tag evidence."
                ),
            ))
        error = self._find_unexpected_signature_error(sql, unexpected_checks)
        if error:
            return error

        missing_checks: list[tuple[list[str], bool, str]] = []
        for cond in requested_condition_kinds:
            if cond["kind"] == "protein_evidence":
                missing_checks.append((
                    [str(cond.get("rel_type", "") or "")],
                    True,
                    (
                        f"Missing evidence condition: the user requested '{cond['id']}' semantics, but the SQL does not include "
                        f"relationship '{cond['rel_type']}'. Keep the requested result type and add that evidence bridge."
                    ),
                ))
            if cond["kind"] == "tag_evidence":
                signatures = [
                    *[str(tag_id) for tag_id in list(cond.get("tag_ids", []) or []) if str(tag_id).strip()],
                    *[
                        name
                        for tag_id in list(cond.get("tag_ids", []) or [])
                        if str(tag_id).strip()
                        if (name := self._tag_id_to_name_signature(tag_id))
                    ],
                ]
                if signatures and not any(signature.upper() in sql_up for signature in signatures):
                    return (
                        f"Missing tag-evidence condition: the user requested '{cond['id']}', "
                        "but the SQL does not include the matching normalized effector/tag ids or tag names."
                    )
            if cond["kind"] == "scope_tag":
                missing_checks.append((
                    [str(cond.get("tag_id", "") or "")],
                    True,
                    (
                        f"Missing scope filter: the user requested scope '{cond['tag_id']}', but the SQL does not constrain that tag. "
                        "Keep the requested result type and add the matching tag filter."
                    ),
                ))
            if cond["kind"] == "ortholog_member" and ortholog_member_rel_type:
                missing_checks.append((
                    [ortholog_member_rel_type],
                    True,
                    "Missing ortholog-member filter: the user requested ortholog genes, but the SQL does not include the orthogroup-to-ortholog-member path.",
                ))
        error = self._find_missing_signature_error(sql, missing_checks)
        if error:
            return error
        orthogroup_label = self._requested_orthogroup_label(message)
        if orthogroup_label and self._message_matches_aliases(message, ["hgt donor", "horizontal gene transfer", " hgt "]):
            if orthogroup_filter_rel_type and orthogroup_filter_rel_type not in sql_up and "ORTHOGROUP" not in sql_up:
                return (
                    f"Missing orthogroup filter: the user requested orthogroup '{orthogroup_label}' together with HGT evidence. "
                    "Keep the requested result type, but also bridge through the gene-to-orthogroup path and filter on the requested orthogroup."
                )
        type_match = re.search(r"e\.type\s*=\s*'([^']+)'", sql, re.IGNORECASE)
        rel_match = re.search(r"r\.rel_type\s*=\s*'([^']+)'", sql, re.IGNORECASE)
        sql_low = str(sql or "").lower()
        requested_homology_organisms = self._requested_homology_organism_matches(chat, message)
        if requested_homology_organisms and self._message_matches_aliases(message, [" broad homology ", " broad parasitism ", " broad parasistism "]):
            requested_names = [str(item.get("name", "") or "") for item in requested_homology_organisms]
            has_filter = any(
                name.lower() in sql_low or str(item.get("tag_id", "") or "").lower() in sql_low
                for item, name in zip(requested_homology_organisms, requested_names)
            )
            if not has_filter:
                return (
                    "Missing broad-homology organism filter: the user requested broad homology hits for "
                    + ", ".join(repr(name) for name in requested_names)
                    + ", but the SQL does not constrain the matching homology-organism tag or matched organism."
                )
            if " as homolog_organism" not in sql_low and " as tag_name" not in sql_low and "matched_organism" not in sql_low:
                return (
                    "Missing broad-homology organism projection: the SQL filters by a specific homolog organism, "
                    "but the final result does not project that organism evidence column."
                )
        if not (type_match and rel_match):
            threshold = chat._extract_numeric_threshold(message, sql)
            if "ortholog" in str(message or "").lower() and threshold:
                owner_type = next(
                    (
                        candidate
                        for candidate in ("orthogroup", "comparative_hit")
                        if candidate in {row["type"] for row in chat.db.entity_types()}
                    ),
                    "",
                )
                edge_rel_types, _edge_target_types = self._ortholog_member_edge_spec(chat, owner_type)
                if self._owner_has_non_primary_gene_counts(chat, owner_type):
                    if "gene_counts" not in sql_low or "json_each" not in sql_low:
                        return (
                            "Wrong counting strategy: ortholog copy counts come from the owner entity's "
                            "`metadata.gene_counts` map, expanded with `json_each(...)`, not by counting raw edges."
                        )
                elif edge_rel_types:
                    if not any(rel_type.lower() in sql_low for rel_type in edge_rel_types):
                        return (
                            "Wrong counting strategy: ortholog copy counts in this dataset come from live ortholog-member "
                            "relationships on the orthogroup, not from a degenerate `gene_counts` map or unrelated edge counts."
                        )
                else:
                    if "gene_counts" not in sql_low or "json_each" not in sql_low:
                        return (
                            "Wrong counting strategy: ortholog copy counts come from the owner entity's "
                            "`metadata.gene_counts` map, expanded with `json_each(...)`, not by counting raw edges."
                        )
                if "ortholog_copy_count" not in sql_low and "count(" not in sql_low and "gc.value" not in sql_low:
                    return (
                        "Missing ortholog copy-count projection: the SQL applies an ortholog copy-count filter, "
                        "but the final result does not project the matched copy count."
                    )
            return None
        selected_type = type_match.group(1)
        rel_type = rel_match.group(1)
        if "ortholog" not in str(message or "").lower():
            return None
        threshold = chat._extract_numeric_threshold(message, sql)
        if threshold:
            owner_type_guess, _owner_path = self._ortholog_count_owner_type(
                chat,
                requested_type=selected_type,
                selected_type=selected_type,
                rel_type=rel_type,
            )
            edge_rel_types, _edge_target_types = self._ortholog_member_edge_spec(chat, owner_type_guess or "orthogroup")
            if self._owner_has_non_primary_gene_counts(chat, owner_type_guess):
                if "gene_counts" not in sql_low or "json_each" not in sql_low:
                    return (
                        "Wrong counting strategy: ortholog copy counts come from the owner entity's "
                        "`metadata.gene_counts` map, expanded with `json_each(...)`, not by counting raw edges."
                    )
            elif edge_rel_types:
                if not any(rel_type_name.lower() in sql_low for rel_type_name in edge_rel_types):
                    return (
                        "Wrong counting strategy: ortholog copy counts in this dataset come from live ortholog-member "
                        "relationships on the orthogroup, not from a degenerate `gene_counts` map or unrelated edge counts."
                    )
            else:
                if "gene_counts" not in sql_low or "json_each" not in sql_low:
                    return (
                        "Wrong counting strategy: ortholog copy counts come from the owner entity's "
                        "`metadata.gene_counts` map, expanded with `json_each(...)`, not by counting raw edges."
                    )
            if "ortholog_copy_count" not in sql_low and "gc.value" not in sql_low and "count(" not in sql_low:
                return (
                    "Missing ortholog copy-count projection: the SQL applies an ortholog copy-count filter, "
                    "but the final result does not project the matched copy count."
                )
        count_rel_pattern = re.search(
            r"select\s+count\(\*\)\s+from\s+relationships\s+r\s+where\s+r\.source_id\s*=\s*e\.id\s+and\s+r\.rel_type\s*=\s*'([^']+)'",
            sql,
            re.IGNORECASE | re.DOTALL,
        )
        if not count_rel_pattern:
            return None
        counted_rel = count_rel_pattern.group(1)
        if counted_rel != rel_type:
            return None
        patterns = chat._typed_rel_patterns()
        valid_targets = sorted({dst for src, rel, dst in patterns if src == selected_type and rel == counted_rel})
        owner_bits = []
        for valid_target in valid_targets[:3]:
            owner_keys = set(chat.db.metadata_keys(valid_target))
            if "gene_counts" in owner_keys:
                path = chat._shortest_type_path(selected_type, valid_target)
                rendered = " ; ".join(f"{src} -{rel}-> {dst}" for src, rel, dst in path) if path else f"{selected_type} -{counted_rel}-> {valid_target}"
                owner_bits.append(
                    f"'{counted_rel}' is a bridge to '{valid_target}', and ortholog copy counts are stored on '{valid_target}.metadata.gene_counts', not as repeated '{counted_rel}' edges. Path: {rendered}"
                )
        if owner_bits:
            return "Wrong counting strategy: " + " ".join(owner_bits)
        return None

    def synthesize_query(self, chat, message: str, sql: str, requested_types: list[str]) -> str | dict[str, Any] | None:
        expression_ranking = self._expression_ranking_request(chat, message, requested_types)
        if expression_ranking:
            expression_sql = self._expression_ranking_query(chat, expression_ranking)
            if expression_sql:
                return expression_sql
        common_promoted_sql = self._common_promoted_entity_terms_query(chat, message, requested_types)
        if common_promoted_sql:
            return common_promoted_sql
        common_annotation_term_sql = self._common_functional_annotation_terms_query(chat, message, requested_types)
        if common_annotation_term_sql:
            return common_annotation_term_sql
        functional_annotation_sql = self._functional_annotation_ranking_query(chat, message, requested_types)
        if functional_annotation_sql:
            return functional_annotation_sql
        derived_connection_sql = self._functional_derived_connection_query(chat, message, requested_types)
        if derived_connection_sql:
            return derived_connection_sql
        semantic_sql = self._semantic_query(chat, message, requested_types)
        if semantic_sql:
            return semantic_sql
        metadata_filters = self._requested_metadata_filters(message)
        metadata_requested_type = requested_types[0] if requested_types else ""
        if metadata_requested_type and metadata_filters:
            metadata_sql = self._metadata_filter_query(chat, metadata_requested_type, metadata_filters)
            if metadata_sql:
                return metadata_sql
        if not sql or not requested_types:
            return None
        available_types = [row["type"] for row in chat.db.entity_types()]
        if "tag" in requested_types and self._requests_broad_homology_organism_tags(message, available_types):
            evidence_columns = [
                ("parent.name", "tag_group"),
                ("scope_tag.name", "homology_scope"),
            ]
            return self._synthesis_result("\n".join([
                self._select_clause_with_evidence(evidence_columns),
                "FROM entities e",
                "JOIN relationships broader ON broader.source_id = e.id AND broader.rel_type = 'BROADER'",
                "JOIN entities parent ON parent.id = broader.target_id AND parent.type = 'tag'",
                "JOIN relationships tag_hit ON tag_hit.target_id = e.id AND tag_hit.rel_type = 'TAGGED'",
                "JOIN entities hit ON hit.id = tag_hit.source_id AND hit.type = 'comparative_hit'",
                "JOIN relationships ev ON ev.target_id = hit.id AND ev.rel_type = 'HAS_BROAD_HOMOLOGY_HIT'",
                "JOIN relationships scope_rel ON scope_rel.source_id = hit.id AND scope_rel.rel_type = 'TAGGED'",
                "JOIN entities scope_tag ON scope_tag.id = scope_rel.target_id AND scope_tag.type = 'tag'",
                "WHERE e.type = 'tag'",
                "  AND e.id LIKE 'homology-organism:%'",
                "  AND parent.id = 'homology-organism'",
                "  AND scope_tag.id = 'homology-scope-broad-parasitism'",
            ]), evidence_columns=evidence_columns, semantic_trace={"kind": "broad_homology_organism_tags"})
        if "hgt_donor" in requested_types and self._requests_hgt_donor_semantics(message):
            return self._synthesis_result("\n".join([
                "SELECT DISTINCT e.id, e.name, e.type",
                "FROM entities e",
                "JOIN relationships r ON r.target_id = e.id AND r.rel_type = 'HAS_HGT_DONOR'",
                "WHERE e.type = 'hgt_donor'",
            ]), semantic_trace={"kind": "hgt_donor_result"})
        msg = str(message or "").lower()
        if "ortholog" not in msg:
            return None
        rel_match = re.search(r"r\.rel_type\s*=\s*'([^']+)'", sql, re.IGNORECASE)
        type_match = re.search(r"e\.type\s*=\s*'([^']+)'", sql, re.IGNORECASE)
        threshold = chat._extract_numeric_threshold(message, sql)
        if not (type_match and threshold):
            return None
        selected_type = type_match.group(1)
        requested_type = requested_types[0]
        if requested_types and selected_type not in requested_types and selected_type != "orthogroup":
            return None
        rel_type = rel_match.group(1) if rel_match else ""
        owner_type, path = self._ortholog_count_owner_type(
            chat,
            requested_type=requested_type,
            selected_type=selected_type,
            rel_type=rel_type,
        )
        if not owner_type or (requested_type != owner_type and not path):
            return None
        op, value = threshold
        joins: list[str] = []
        current_node_ref = "e.id"
        current_type = requested_type
        alias_index = 0
        for src, edge_rel, dst in path:
            if src != current_type:
                return None
            alias_index += 1
            rel_alias = f"p{alias_index}"
            joins.append(
                f"JOIN relationships {rel_alias} ON {rel_alias}.source_id = {current_node_ref} AND {rel_alias}.rel_type = '{edge_rel}'"
            )
            current_node_ref = f"{rel_alias}.target_id"
            current_type = dst
        owner_join = (
            f"JOIN entities owner ON owner.id = {current_node_ref} AND owner.type = '{owner_type}'"
            if requested_type != owner_type
            else f"JOIN entities owner ON owner.id = e.id AND owner.type = '{owner_type}'"
        )
        if self._owner_has_non_primary_gene_counts(chat, owner_type):
            evidence_columns = [
                ("json_extract(owner.metadata, '$.organism')", "owner_organism"),
                ("json_extract(owner.metadata, '$.gene_counts')", "gene_counts"),
                ("group_concat(DISTINCT gc.key)", "ortholog_organisms"),
                ("MAX(CAST(gc.value AS INTEGER))", "ortholog_copy_count"),
            ]
            return self._synthesis_result("\n".join([
                self._select_clause_with_evidence(evidence_columns),
                "FROM entities e",
                *joins,
                owner_join,
                "JOIN json_each(owner.metadata, '$.gene_counts') gc",
                f"WHERE e.type = '{requested_type}'",
                "  AND gc.key != json_extract(owner.metadata, '$.organism')",
                "GROUP BY e.id, e.name, e.type, json_extract(owner.metadata, '$.organism'), json_extract(owner.metadata, '$.gene_counts')",
                f"HAVING MAX(CAST(gc.value AS INTEGER)) {op} {value}",
            ]), evidence_columns=evidence_columns, semantic_trace={"kind": "ortholog_count_map", "requested_type": requested_type, "owner_type": owner_type})

        edge_rel_types, edge_target_types = self._ortholog_member_edge_spec(chat, owner_type)
        if edge_rel_types and edge_target_types:
            rel_list = ", ".join(f"'{item}'" for item in edge_rel_types)
            type_list = ", ".join(f"'{item}'" for item in edge_target_types)
            requested_organisms = self._requested_organism_name_matches(chat, message)
            organism_where: list[str] = []
            organism_group_expr = "group_concat(DISTINCT json_extract(member.metadata, '$.organism'))"
            if requested_organisms:
                escaped = ", ".join("'" + name.replace("'", "''") + "'" for name in requested_organisms)
                organism_where.append(f"  AND json_extract(member.metadata, '$.organism') IN ({escaped})")
                if len(requested_organisms) == 1:
                    organism_group_expr = "'" + requested_organisms[0].replace("'", "''") + "'"
            evidence_columns = [
                ("owner.name", "orthogroup_label"),
                (organism_group_expr, "ortholog_organisms"),
                ("COUNT(DISTINCT member.id)", "ortholog_copy_count"),
            ]
            return self._synthesis_result("\n".join([
                self._select_clause_with_evidence(evidence_columns),
                "FROM entities e",
                *joins,
                owner_join,
                f"JOIN relationships om ON om.source_id = owner.id AND om.rel_type IN ({rel_list})",
                f"JOIN entities member ON member.id = om.target_id AND member.type IN ({type_list})",
                f"WHERE e.type = '{requested_type}'",
                *organism_where,
                "GROUP BY e.id, e.name, e.type, owner.name",
                f"HAVING COUNT(DISTINCT member.id) {op} {value}",
            ]), evidence_columns=evidence_columns, semantic_trace={"kind": "ortholog_member_edges", "requested_type": requested_type, "owner_type": owner_type, "rel_types": edge_rel_types})
        return None

    def evidence_columns_for_sql(self, chat, message: str, sql: str, requested_types: list[str]) -> list[tuple[str, str]] | None:
        evidence_columns: list[tuple[str, str]] = []
        requested_core_type = self._requested_core_type(requested_types)
        if requested_core_type in {"gene", "transcript", "protein"}:
            conditions = self._semantic_conditions(chat, message)
            evidence_columns.extend(self._semantic_condition_evidence_columns(chat, conditions))
            evidence_columns.extend(self._accepted_sql_condition_evidence_columns(requested_core_type, conditions))
            for cond in conditions:
                kind = str(cond.get("kind", "") or "")
                if kind == "promoted_call":
                    entity_name = str(cond.get("entity_name", "") or "").strip()
                    category = str(cond.get("category", "") or "").strip()
                    if entity_name:
                        evidence_columns.append((f"'{self._sql_literal(entity_name)}'", "matched_call"))
                    if category:
                        evidence_columns.append((f"'{self._sql_literal(category)}'", "matched_call_category"))
                elif kind == "generic_tag":
                    tag_name = str(cond.get("tag_name", "") or "").strip()
                    if tag_name:
                        evidence_columns.append((f"'{self._sql_literal(tag_name)}'", "matched_tag"))
        selected_type = requested_types[0] if requested_types else ""
        if selected_type:
            metadata_filters = self._requested_metadata_filters(message)
            if metadata_filters and all(str(item.get("owner_type", "") or "") == selected_type for item in metadata_filters):
                for item in metadata_filters:
                    field = str(item.get("field", "") or "")
                    alias = ""
                    if isinstance(item.get("display"), dict):
                        alias = str(item["display"].get("alias", "") or "").strip()
                    if field:
                        evidence_columns.append((f"json_extract(e.metadata, '$.{field}')", alias or field))
        if not evidence_columns:
            return None
        requested_homology_organisms = self._requested_homology_organism_matches(chat, message)
        if requested_homology_organisms and "HAS_BROAD_HOMOLOGY_HIT" in str(sql or "") and " AS homolog_organism" not in str(sql or ""):
            tag_name_match = re.search(r"\b([A-Za-z_][A-Za-z0-9_]*)\.name\s*=\s*'([^']+)'", str(sql or ""), re.IGNORECASE)
            if tag_name_match:
                evidence_columns.append((f"{tag_name_match.group(1)}.name", "homolog_organism"))
        deduped: list[tuple[str, str]] = []
        seen_aliases: set[str] = set()
        for expr, alias in evidence_columns:
            alias_text = str(alias).strip()
            expr_text = str(expr).strip()
            if not alias_text or not expr_text or alias_text in seen_aliases:
                continue
            seen_aliases.add(alias_text)
            deduped.append((expr_text, alias_text))
        return deduped or None
