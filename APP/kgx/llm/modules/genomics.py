from __future__ import annotations

import json
import math
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

    More concretely, the intentional runtime boundary is:
    - selecting primary/secondary organism alias sets from live organism rows
    - walking live tag branches when the scope/effector hierarchy present in the
      database is the source of truth
    - applying final message-dependent family labels over already live-derived
      dynamic-family flags

    These are distinct from accidental runtime semantics. Most former prompt
    routing, validation, artifact shaping, and presentation decisions have
    already been moved to the structured analysis contract plus registry-driven
    execution/presentation config.

    Those paths are the current fallback boundary rather than hidden semantic
    duplication. They are kept local until they can be represented declaratively
    without making the runtime more brittle.
    """
    _HOMOLOGY_SCOPE_ROOT = "homology-scope"
    _CORE_REQUESTED_TYPES = frozenset({"gene", "transcript", "protein"})
    _ANALYSIS_CONTRACT_VERSION = "genomics-chat-analysis-v1"
    _ANALYSIS_INTENTS = frozenset({"filter", "rank", "aggregate", "compare", "summarize", "correlate", "answer"})
    _ANALYSIS_RESULT_KINDS = frozenset({"entity_rows", "ranked_rows", "scalar", "distribution", "comparison", "narrative"})
    _ANALYSIS_HANDLER_SPECS = (
        ("_analysis_for_functional_derived_connections", "functional_derived_connections", "_compile_functional_derived_connection_analysis"),
        ("_analysis_for_common_promoted_entity_terms", "common_promoted_entity_terms", "_compile_common_promoted_entity_terms_analysis"),
        ("_analysis_for_common_functional_annotation_terms", "common_functional_annotation_terms", "_compile_common_functional_annotation_terms_analysis"),
        ("_analysis_for_functional_annotation_ranking", "functional_annotation_ranking", "_compile_functional_annotation_ranking_analysis"),
        ("_analysis_for_promoted_call_filters", "promoted_call_filters", "_compile_promoted_call_filter_analysis"),
        ("_analysis_for_generic_tag_filters", "generic_tag_filters", "_compile_generic_tag_filter_analysis"),
        ("_analysis_for_metadata_filters", "metadata_filters", "_compile_metadata_filter_analysis"),
        ("_analysis_for_effector_tag_filters", "effector_tag_filters", "_compile_effector_tag_filter_analysis"),
        ("_analysis_for_scope_tag_filters", "scope_tag_filters", "_compile_scope_tag_filter_analysis"),
        ("_analysis_for_comparative_scope_filters", "comparative_scope_filters", "_compile_comparative_scope_filter_analysis"),
        ("_analysis_for_evidence_homology_organism_filters", "evidence_homology_organism_filters", "_compile_evidence_homology_organism_filter_analysis"),
        ("_analysis_for_evidence_orthogroup_filters", "evidence_orthogroup_filters", "_compile_evidence_orthogroup_filter_analysis"),
        ("_analysis_for_evidence_ortholog_member_filters", "evidence_ortholog_member_filters", "_compile_evidence_ortholog_member_filter_analysis"),
        ("_analysis_for_broad_homology_organism_tag_results", "broad_homology_organism_tag_results", "_compile_broad_homology_organism_tag_result_analysis"),
        ("_analysis_for_hgt_donor_results", "hgt_donor_results", "_compile_hgt_donor_result_analysis"),
        ("_analysis_for_ortholog_count_results", "ortholog_count_results", "_compile_ortholog_count_result_analysis"),
        ("_analysis_for_expression_ranking", "expression_ranking", "_compile_expression_ranking_analysis"),
        ("_analysis_for_expression_distribution", "expression_distribution", "_compute_expression_distribution_analysis"),
        ("_analysis_for_expression_comparison", "expression_comparison", "_compute_expression_comparison_analysis"),
        ("_analysis_for_expression_stats", "expression_stats", "_compute_expression_stats_analysis"),
        ("_analysis_for_multi_condition_filters", "multi_condition_filters", "_compile_multi_condition_filter_analysis"),
    )
    _SEMANTIC_CONDITION_ROUTE_SPECS = (
        {
            "analysis_kind": "effector_tag_filters",
            "required_kinds": frozenset({"tag_evidence"}),
            "allowed_kinds": frozenset({"tag_evidence"}),
            "evidence_include": ["condition_display_columns"],
            "analysis_fields": ("families", "filter_ids", "tag_ids"),
            "trace_kind": "genomics_effector_tag_filters",
            "trace_fields": ("families", "filter_ids", "tag_ids"),
        },
        {
            "analysis_kind": "scope_tag_filters",
            "required_kinds": frozenset({"protein_evidence", "scope_tag"}),
            "allowed_kinds": frozenset({"protein_evidence", "scope_tag"}),
            "evidence_include": ["condition_display_columns", "homology_scope"],
            "analysis_fields": ("scope_tag_ids", "evidence_ids"),
            "trace_kind": "genomics_scope_tag_filters",
            "trace_fields": ("scope_tag_ids", "evidence_ids"),
        },
        {
            "analysis_kind": "comparative_scope_filters",
            "required_kinds": frozenset({"protein_evidence", "scope_tag"}),
            "required_any_kinds": frozenset({"ortholog_member", "orthogroup_filter"}),
            "allowed_kinds": frozenset({"protein_evidence", "scope_tag", "ortholog_member", "orthogroup_filter"}),
            "evidence_include": ["condition_display_columns", "homology_scope", "orthogroup_label"],
            "analysis_fields": ("scope_tag_ids", "evidence_ids", "condition_kinds"),
            "trace_kind": "genomics_comparative_scope_filters",
            "trace_fields": ("scope_tag_ids", "evidence_ids", "condition_kinds"),
        },
        {
            "analysis_kind": "evidence_homology_organism_filters",
            "required_kinds": frozenset({"protein_evidence"}),
            "allowed_kinds": frozenset({"protein_evidence", "ortholog_member", "orthogroup_filter"}),
            "requires_homology_organisms": True,
            "evidence_include": ["condition_display_columns", "homolog_organism", "orthogroup_label"],
            "analysis_fields": ("evidence_ids", "condition_kinds"),
            "trace_kind": "genomics_evidence_homology_organism_filters",
            "trace_fields": ("evidence_ids", "condition_kinds", "homology_organism_ids"),
        },
        {
            "analysis_kind": "evidence_orthogroup_filters",
            "required_kinds": frozenset({"protein_evidence", "orthogroup_filter"}),
            "allowed_kinds": frozenset({"protein_evidence", "orthogroup_filter"}),
            "evidence_include": ["condition_display_columns", "orthogroup_label", "hgt_donor"],
            "analysis_fields": ("evidence_ids", "orthogroup_labels", "condition_kinds"),
            "trace_kind": "genomics_evidence_orthogroup_filters",
            "trace_fields": ("evidence_ids", "orthogroup_labels", "condition_kinds"),
        },
        {
            "analysis_kind": "evidence_ortholog_member_filters",
            "required_kinds": frozenset({"protein_evidence", "ortholog_member"}),
            "allowed_kinds": frozenset({"protein_evidence", "ortholog_member"}),
            "evidence_include": ["condition_display_columns", "hgt_donor"],
            "analysis_fields": ("evidence_ids", "condition_kinds"),
            "trace_kind": "genomics_evidence_ortholog_member_filters",
            "trace_fields": ("evidence_ids", "condition_kinds"),
        },
    )

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
            "genomics_promoted_call_filters",
            "genomics_generic_tag_filters",
            "genomics_effector_tag_filters",
            "genomics_scope_tag_filters",
            "genomics_comparative_scope_filters",
            "genomics_evidence_homology_organism_filters",
            "genomics_evidence_orthogroup_filters",
            "genomics_evidence_ortholog_member_filters",
            "genomics_multi_condition_filters",
            "broad_homology_organism_tags",
            "hgt_donor_result",
            "ortholog_count_map",
            "ortholog_member_edges",
        }

    @classmethod
    def _normalize_analysis(cls, analysis: dict[str, Any] | None) -> dict[str, Any] | None:
        if not isinstance(analysis, dict):
            return None
        normalized = dict(analysis)
        analysis_kind = str(normalized.get("analysis_kind", "") or "").strip()
        intent = str(normalized.get("intent", "") or "").strip()
        requested_result_kind = str(normalized.get("requested_result_kind", "") or "").strip()
        subject = dict(normalized.get("subject", {}) or {})
        entity_type = str(subject.get("entity_type", "") or "").strip()
        if not analysis_kind or str(normalized.get("domain", "") or "").strip() != "genomics":
            return None
        if intent not in cls._ANALYSIS_INTENTS or requested_result_kind not in cls._ANALYSIS_RESULT_KINDS:
            return None
        if not entity_type:
            return None
        payload_keys = ("filters", "aggregations", "paths", "conditions")
        if not any(normalized.get(key) for key in payload_keys):
            return None
        subject.setdefault("selection_mode", "inferred_type")
        subject.setdefault("ids", [])
        normalized["subject"] = subject
        normalized.setdefault("contract_version", cls._ANALYSIS_CONTRACT_VERSION)
        normalized.setdefault("filters", [])
        normalized.setdefault("aggregations", [])
        normalized.setdefault("paths", [])
        if "conditions" in normalized:
            normalized["conditions"] = [dict(item) for item in list(normalized.get("conditions", []) or []) if isinstance(item, dict)]
        normalized["filters"] = [dict(item) for item in list(normalized.get("filters", []) or []) if isinstance(item, dict)]
        normalized["aggregations"] = [dict(item) for item in list(normalized.get("aggregations", []) or []) if isinstance(item, dict)]
        normalized["paths"] = [dict(item) for item in list(normalized.get("paths", []) or []) if isinstance(item, dict)]
        normalized["dimensions"] = dict(normalized.get("dimensions", {}) or {})
        normalized["evidence"] = dict(normalized.get("evidence", {}) or {})
        normalized["execution"] = cls._normalized_analysis_execution(normalized)
        normalized["presentation"] = cls._normalized_analysis_presentation(normalized)
        return normalized

    @classmethod
    def _normalized_analysis_execution(cls, analysis: dict[str, Any]) -> dict[str, Any]:
        execution = dict(analysis.get("execution", {}) or {})
        requested_result_kind = str(analysis.get("requested_result_kind", "") or "")
        preferred_engine = str(execution.get("preferred_engine", "") or "").strip()
        if not preferred_engine:
            preferred_engine = "python" if requested_result_kind in {"scalar", "distribution", "comparison", "narrative"} else "sql"
        execution["preferred_engine"] = preferred_engine
        execution.setdefault("requires_live_schema", True)
        return execution

    @classmethod
    def _normalized_analysis_presentation(cls, analysis: dict[str, Any]) -> dict[str, Any]:
        presentation = dict(analysis.get("presentation", {}) or {})
        requested_result_kind = str(analysis.get("requested_result_kind", "") or "")
        prefers_summary = requested_result_kind in {"scalar", "distribution", "comparison", "narrative"}
        presentation.setdefault("prefer_table", not prefers_summary)
        presentation.setdefault("prefer_summary", prefers_summary)
        presentation.setdefault("summary_style", "concise")
        return presentation

    @classmethod
    def _analysis_synthesis_result(
        cls,
        sql: str,
        *,
        analysis: dict[str, Any],
        evidence_columns: list[tuple[str, str]] | None = None,
        semantic_trace: dict[str, Any] | None = None,
    ):
        normalized = cls._normalize_analysis(analysis)
        if normalized is None:
            normalized = dict(analysis or {})
        return super()._analysis_synthesis_result(
            sql,
            analysis=normalized,
            evidence_columns=evidence_columns,
            semantic_trace=semantic_trace,
        )

    def analyze_request(self, chat, message: str, requested_types: list[str]) -> dict[str, Any] | None:
        for analyzer_name, _analysis_kind, _compiler_name in self._ANALYSIS_HANDLER_SPECS:
            analysis = getattr(self, analyzer_name)(chat, message, requested_types)
            if analysis:
                return self._normalize_analysis(analysis)
        return None

    def synthesize_analysis(self, chat, analysis: dict[str, Any]) -> str | dict[str, Any] | None:
        analysis = self._normalize_analysis(analysis)
        if not analysis:
            return None
        analysis_kind = str(analysis.get("analysis_kind", "") or "")
        compiler_name = next(
            (name for _analyzer_name, kind, name in self._ANALYSIS_HANDLER_SPECS if kind == analysis_kind),
            "",
        )
        if compiler_name:
            return getattr(self, compiler_name)(chat, analysis)
        return None

    @staticmethod
    def _message_matches_aliases(message: str, aliases: list[str]) -> bool:
        low = GenomicsChatModule._normalized_prompt_text(message)
        return any(GenomicsChatModule._normalized_prompt_text(alias) in low for alias in aliases)

    @staticmethod
    def _analysis_trace(kind: str, analysis: dict[str, Any], **extra: Any) -> dict[str, Any]:
        trace = {"kind": kind, "analysis": dict(analysis or {})}
        trace.update({key: value for key, value in extra.items() if value is not None})
        return trace

    @classmethod
    def _semantic_condition_route_spec(cls, analysis_kind: str) -> dict[str, Any] | None:
        return next(
            (dict(spec) for spec in cls._SEMANTIC_CONDITION_ROUTE_SPECS if spec.get("analysis_kind") == analysis_kind),
            None,
        )

    @staticmethod
    def _condition_kinds(conditions: list[dict[str, Any]]) -> set[str]:
        return {str(cond.get("kind", "") or "") for cond in conditions}

    @staticmethod
    def _sorted_condition_values(conditions: list[dict[str, Any]], *, kind: str, field: str) -> list[str]:
        return sorted({
            str(cond.get(field, "") or "")
            for cond in conditions
            if str(cond.get("kind", "") or "") == kind and str(cond.get(field, "") or "").strip()
        })

    def _semantic_condition_analysis_fields(
        self,
        conditions: list[dict[str, Any]],
        condition_kinds: set[str],
        field_names: tuple[str, ...] | list[str],
    ) -> dict[str, Any]:
        extras: dict[str, Any] = {}
        for field_name in field_names:
            if field_name == "scope_tag_ids":
                extras[field_name] = self._sorted_condition_values(conditions, kind="scope_tag", field="tag_id")
            elif field_name == "evidence_ids":
                extras[field_name] = self._sorted_condition_values(conditions, kind="protein_evidence", field="id")
            elif field_name == "orthogroup_labels":
                extras[field_name] = self._sorted_condition_values(conditions, kind="orthogroup_filter", field="label")
            elif field_name == "families":
                extras[field_name] = sorted({
                    str(cond.get("effector_family", "") or str(cond.get("id", "") or ""))
                    for cond in conditions
                    if str(cond.get("kind", "") or "") == "tag_evidence"
                    and str(cond.get("effector_family", "") or str(cond.get("id", "") or "")).strip()
                })
            elif field_name == "filter_ids":
                extras[field_name] = self._sorted_condition_values(conditions, kind="tag_evidence", field="id")
            elif field_name == "tag_ids":
                extras[field_name] = sorted({
                    str(tag_id)
                    for cond in conditions
                    if str(cond.get("kind", "") or "") == "tag_evidence"
                    for tag_id in list(cond.get("tag_ids", []) or [])
                    if str(tag_id).strip()
                })
            elif field_name == "condition_kinds":
                extras[field_name] = sorted(condition_kinds)
        return extras

    def _semantic_condition_route_analysis(
        self,
        chat,
        message: str,
        requested_types: list[str],
        analysis_kind: str,
    ) -> dict[str, Any] | None:
        spec = self._semantic_condition_route_spec(analysis_kind)
        if not spec:
            return None
        requested_type = self._requested_core_type(requested_types)
        if requested_type not in self._CORE_REQUESTED_TYPES:
            return None
        homology_organisms = [dict(item) for item in self._requested_homology_organism_matches(chat, message)]
        if spec.get("requires_homology_organisms") and not homology_organisms:
            return None
        all_conditions = self._semantic_conditions(chat, message)
        if not all_conditions:
            return None
        condition_kinds = self._condition_kinds(all_conditions)
        required_kinds = set(spec.get("required_kinds", set()) or set())
        if required_kinds and not required_kinds.issubset(condition_kinds):
            return None
        required_any_kinds = set(spec.get("required_any_kinds", set()) or set())
        if required_any_kinds and not condition_kinds.intersection(required_any_kinds):
            return None
        allowed_kinds = set(spec.get("allowed_kinds", set()) or set())
        if allowed_kinds and not condition_kinds.issubset(allowed_kinds):
            return None
        analysis = {
            "analysis_kind": analysis_kind,
            "domain": "genomics",
            "intent": "filter",
            "requested_result_kind": "entity_rows",
            "subject": {"entity_type": requested_type},
            "conditions": [dict(cond) for cond in all_conditions],
            "evidence": {"include": [str(item) for item in list(spec.get("evidence_include", []) or []) if str(item).strip()]},
        }
        if homology_organisms:
            analysis["homology_organisms"] = homology_organisms
        analysis.update(self._semantic_condition_analysis_fields(
            all_conditions,
            condition_kinds,
            tuple(spec.get("analysis_fields", ()) or ()),
        ))
        return analysis

    @staticmethod
    def _semantic_condition_query_state(
        conditions: list[dict[str, Any]],
        homology_organisms: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return {
            "scope_tag_ids": {
                str(cond.get("tag_id", "") or "")
                for cond in conditions
                if str(cond.get("kind", "") or "") == "scope_tag"
            },
            "used_scope_tags": set(),
            "has_protein_evidence": any(str(cond.get("kind", "") or "") == "protein_evidence" for cond in conditions),
            "evidence_columns": [],
            "homology_organisms": [dict(item) for item in list(homology_organisms or []) if isinstance(item, dict)],
        }

    def _semantic_condition_trace_extras(
        self,
        analysis: dict[str, Any],
        requested_type: str,
        field_names: tuple[str, ...] | list[str],
    ) -> dict[str, Any]:
        extras: dict[str, Any] = {"requested_type": requested_type}
        for field_name in field_names:
            if field_name == "homology_organism_ids":
                extras[field_name] = [
                    str(item.get("tag_id", "") or "")
                    for item in list(analysis.get("homology_organisms", []) or [])
                    if isinstance(item, dict) and str(item.get("tag_id", "") or "").strip()
                ]
            else:
                extras[field_name] = [str(item) for item in list(analysis.get(field_name, []) or []) if str(item).strip()]
        return extras

    def _compile_semantic_condition_route_analysis(
        self,
        chat,
        analysis: dict[str, Any],
        analysis_kind: str,
    ) -> str | dict[str, Any] | None:
        spec = self._semantic_condition_route_spec(analysis_kind)
        if not spec:
            return None
        requested_type = str(analysis.get("subject", {}).get("entity_type", "") or "")
        conditions = [dict(cond) for cond in list(analysis.get("conditions", []) or []) if isinstance(cond, dict)]
        if requested_type not in self._CORE_REQUESTED_TYPES or not conditions:
            return None
        condition_kinds = self._condition_kinds(conditions)
        allowed_kinds = set(spec.get("allowed_kinds", set()) or set())
        if allowed_kinds and not condition_kinds.issubset(allowed_kinds):
            return None
        state = self._semantic_condition_query_state(
            conditions,
            [dict(item) for item in list(analysis.get("homology_organisms", []) or []) if isinstance(item, dict)],
        )
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
        synthesized = self._analysis_synthesis_result(
            rendered_sql,
            analysis=analysis,
            evidence_columns=evidence_columns,
            semantic_trace=self._analysis_trace(
                str(spec.get("trace_kind", "") or f"genomics_{analysis_kind}"),
                analysis,
                **self._semantic_condition_trace_extras(
                    analysis,
                    requested_type,
                    tuple(spec.get("trace_fields", ()) or ()),
                ),
            ),
        )
        payload: dict[str, Any] = {"sql": str(synthesized)}
        if isinstance(evidence_columns, list):
            payload["evidence_columns"] = list(evidence_columns)
        semantic_trace = getattr(synthesized, "semantic_trace", None)
        if isinstance(semantic_trace, dict):
            payload["semantic_trace"] = dict(semantic_trace)
        return payload

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

    def _validation_analysis_requirement(self, analysis_kind: str) -> dict[str, Any]:
        config = self._validation_config()
        requirements = config.get("analysis_requirements", {}) if isinstance(config, dict) else {}
        requirement = requirements.get(str(analysis_kind), {}) if isinstance(requirements, dict) else {}
        return dict(requirement) if isinstance(requirement, dict) else {}

    def _aggregation_config(self) -> dict[str, Any]:
        config = self.semantic_registry.get("aggregations", {}) if isinstance(self.semantic_registry, dict) else {}
        return dict(config) if isinstance(config, dict) else {}

    def _numeric_scalar_aggregation_spec(self, aggregation_type: str) -> dict[str, Any]:
        config = self._aggregation_config()
        numeric_scalar = config.get("numeric_scalar", {}) if isinstance(config, dict) else {}
        spec = numeric_scalar.get(str(aggregation_type), {}) if isinstance(numeric_scalar, dict) else {}
        return dict(spec) if isinstance(spec, dict) else {}

    def _distribution_summary_spec(self, summary_id: str) -> dict[str, Any]:
        config = self._aggregation_config()
        summaries = config.get("distribution_summaries", {}) if isinstance(config, dict) else {}
        spec = summaries.get(str(summary_id), {}) if isinstance(summaries, dict) else {}
        return dict(spec) if isinstance(spec, dict) else {}

    def _comparison_spec(self, comparison_id: str) -> dict[str, Any]:
        config = self._aggregation_config()
        comparisons = config.get("comparisons", {}) if isinstance(config, dict) else {}
        spec = comparisons.get(str(comparison_id), {}) if isinstance(comparisons, dict) else {}
        return dict(spec) if isinstance(spec, dict) else {}

    def _distribution_rendering_spec(self, summary_id: str) -> dict[str, Any]:
        spec = self._distribution_summary_spec(summary_id)
        rendering = spec.get("rendering", {}) if isinstance(spec, dict) else {}
        return dict(rendering) if isinstance(rendering, dict) else {}

    def _comparison_rendering_spec(self, comparison_id: str) -> dict[str, Any]:
        spec = self._comparison_spec(comparison_id)
        rendering = spec.get("rendering", {}) if isinstance(spec, dict) else {}
        return dict(rendering) if isinstance(rendering, dict) else {}

    def _distribution_summary_evidence_fields(self, summary_id: str) -> list[str]:
        spec = self._distribution_summary_spec(summary_id)
        metrics = [dict(item) for item in list(spec.get("metrics", []) or []) if isinstance(item, dict)]
        fields: list[str] = []
        seen: set[str] = set()
        for metric in metrics:
            alias = str(metric.get("alias", "") or "").strip()
            if not alias or alias in seen:
                continue
            fields.append(alias)
            seen.add(alias)
        return fields

    def _comparison_metrics(self, comparison_id: str) -> list[dict[str, Any]]:
        spec = self._comparison_spec(comparison_id)
        metrics = [dict(item) for item in list(spec.get("metrics", []) or []) if isinstance(item, dict)]
        if metrics:
            return metrics
        metric = dict(spec.get("metric", {}) or {})
        return [metric] if metric else []

    def _comparison_evidence_fields(self, comparison_id: str) -> list[str]:
        spec = self._comparison_spec(comparison_id)
        metrics = self._comparison_metrics(comparison_id)
        fields: list[str] = ["left_condition", "right_condition"]
        seen: set[str] = set(fields)
        for metric in metrics:
            alias = str(metric.get("alias", "metric_value") or "metric_value").strip()
            if not alias:
                continue
            for side_alias in (f"{alias}_left", f"{alias}_right"):
                if side_alias in seen:
                    continue
                fields.append(side_alias)
                seen.add(side_alias)
        for alias in (
            str(spec.get("difference_alias", "difference") or "difference").strip(),
            str(spec.get("higher_condition_alias", "higher_condition") or "higher_condition").strip(),
        ):
            if alias and alias not in seen:
                fields.append(alias)
                seen.add(alias)
        return fields

    @staticmethod
    def _artifact_rows(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [dict(row) for row in list(results or []) if isinstance(row, dict)]

    def _summary_result_artifact(
        self,
        analysis: dict[str, Any],
        *,
        artifact_kind: str,
        results: list[dict[str, Any]],
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "artifact_version": "genomics-chat-result-v1",
            "domain": "genomics",
            "analysis_kind": str(analysis.get("analysis_kind", "") or ""),
            "requested_result_kind": str(analysis.get("requested_result_kind", "") or ""),
            "artifact_kind": artifact_kind,
            "presentation": dict(analysis.get("presentation", {}) or {}),
            "rows": self._artifact_rows(results),
            "metadata": dict(metadata or {}),
        }

    def _answer_result(
        self,
        *,
        analysis: dict[str, Any],
        semantic_kind: str,
        content: str | None = None,
        results: list[dict[str, Any]] | None = None,
        sql: str | None = None,
        artifact_kind: str,
        artifact_metadata: dict[str, Any] | None = None,
        trace_fields: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_results = self._artifact_rows(list(results or []))
        artifact = self._summary_result_artifact(
            analysis,
            artifact_kind=artifact_kind,
            results=normalized_results,
            metadata=artifact_metadata,
        )
        payload: dict[str, Any] = {
            "intent": "answer",
            "content": str(content or self._render_summary_content_from_artifact(analysis, artifact)),
            "results": normalized_results,
            "semantic_trace": self._analysis_trace(semantic_kind, analysis, **dict(trace_fields or {})),
            "artifact": artifact,
            "presentation": dict(analysis.get("presentation", {}) or {}),
        }
        if sql:
            payload["sql"] = str(sql)
        return payload

    @staticmethod
    def _summary_style_for_message(message: str, *, default: str = "concise") -> str:
        low = f" {str(message or '').lower()} "
        if any(token in low for token in (" explain ", " interpretation ", " interpret ", " why ", " summarize ", " summary ")):
            return "explanatory"
        if any(token in low for token in (" compare ", " comparison ", " versus ", " vs ", " difference ")):
            return "comparative"
        return default

    @staticmethod
    def _summary_result_kind_for_style(style: str, *, default: str) -> str:
        return "narrative" if style == "explanatory" else default

    @staticmethod
    def _metric_label_text(label: str) -> str:
        return str(label or "").replace("_", " ")

    def _render_template(self, template: str, context: dict[str, Any]) -> str:
        if not template:
            return ""
        safe_context = {key: str(value) for key, value in context.items()}
        return self._format_registry_template(template, safe_context).strip()

    def _render_summary_content_from_artifact(self, analysis: dict[str, Any], artifact: dict[str, Any]) -> str:
        rows = self._artifact_rows(list(artifact.get("rows", []) or []))
        metadata = dict(artifact.get("metadata", {}) or {})
        artifact_kind = str(artifact.get("artifact_kind", "") or "")
        style = str((analysis.get("presentation", {}) or {}).get("summary_style", "concise") or "concise")
        if not rows:
            measure_label = str(metadata.get("measure_label", "the requested measure") or "the requested measure")
            return f"No non-null values were found for {measure_label}."
        row = dict(rows[0] or {})
        if artifact_kind == "scalar_summary":
            metric = str(metadata.get("metric", row.get("metric", "value")) or "value")
            measure_label = str(metadata.get("measure_label", row.get("expression_condition", "the requested measure")) or "the requested measure")
            stat_value = row.get("stat_value")
            subject_count = row.get("subject_count")
            subset_count = row.get("subset_count")
            if style == "explanatory":
                if subset_count is not None:
                    return f"For {measure_label}, the {metric} expression is {stat_value} based on {subject_count} matched values from the requested subset of {subset_count} entities."
                return f"For {measure_label}, the {metric} expression is {stat_value} across {subject_count} matched {row.get('subject_type', 'subject')} rows."
            if subset_count is not None:
                return f"{metric.capitalize()} expression in {measure_label}: {stat_value} across {subject_count} matched values in the requested subset."
            return f"{metric.capitalize()} expression in {measure_label}: {stat_value} across {subject_count} {row.get('subject_type', 'subject')} rows."
        if artifact_kind == "distribution_summary":
            measure_label = str(metadata.get("measure_label", row.get("expression_condition", "the requested measure")) or "the requested measure")
            subject_count = row.get("subject_count")
            subset_count = row.get("subset_count")
            metric_text = self._distribution_summary_text(row)
            summary_id = str(metadata.get("summary_id", "") or "")
            rendering = self._distribution_rendering_spec(summary_id)
            subject_scope = f"{row.get('subject_type', 'subject')} rows"
            context = {
                "measure_label": measure_label,
                "metric_text": metric_text,
                "subject_count": subject_count,
                "subject_scope": subject_scope,
                "subset_count": subset_count if subset_count is not None else "",
            }
            if style == "explanatory":
                template = str(
                    rendering.get(
                        "explanatory_subset_template" if subset_count is not None else "explanatory_template",
                        "",
                    )
                    or ""
                )
                rendered = self._render_template(template, context)
                if rendered:
                    return rendered
                baseline = f"For {measure_label}, the observed expression values span {metric_text}."
                if subset_count is not None:
                    return f"{baseline} This uses {subject_count} matched values from the requested subset of {subset_count} entities."
                return f"{baseline} This uses {subject_count} matched {row.get('subject_type', 'subject')} rows."
            template = str(rendering.get("subset_template" if subset_count is not None else "concise_template", "") or "")
            rendered = self._render_template(context=context, template=template)
            if rendered:
                return rendered
            if subset_count is not None:
                return f"Expression distribution in {measure_label}: {metric_text} across {subject_count} matched values in the requested subset."
            return f"Expression distribution in {measure_label}: {metric_text} across {subject_count} {row.get('subject_type', 'subject')} rows."
        if artifact_kind == "comparison_summary":
            left_label = str(row.get("left_condition", metadata.get("left_measure_id", "left")) or "left")
            right_label = str(row.get("right_condition", metadata.get("right_measure_id", "right")) or "right")
            difference_alias = next(
                (key for key in row.keys() if key.endswith("_difference") or key.endswith("_gap") or key == "difference"),
                "difference",
            )
            metric_parts: list[str] = []
            for key, value in row.items():
                if not key.endswith("_left"):
                    continue
                base = key[:-5]
                right_key = f"{base}_right"
                if right_key not in row:
                    continue
                metric_parts.append(
                    f"{self._metric_label_text(base)} was {value} for {left_label} and {row[right_key]} for {right_label}"
                )
            metric_text = "; ".join(metric_parts)
            difference_value = row.get(difference_alias)
            higher_condition = row.get("higher_condition") or row.get("stronger_condition") or "equal"
            comparison_id = str(metadata.get("comparison_id", "") or "")
            rendering = self._comparison_rendering_spec(comparison_id)
            context = {
                "left_label": left_label,
                "right_label": right_label,
                "metric_text": metric_text,
                "difference_label": self._metric_label_text(difference_alias),
                "difference_value": difference_value,
                "higher_condition": higher_condition,
            }
            if style == "explanatory":
                rendered = self._render_template(str(rendering.get("explanatory_template", "") or ""), context)
                if rendered:
                    return rendered
                return (
                    f"Comparing {left_label} with {right_label}, {metric_text}. "
                    f"The {self._metric_label_text(difference_alias)} is {difference_value}, and the stronger condition is {higher_condition}."
                )
            rendered = self._render_template(str(rendering.get("comparative_template", "") or ""), context)
            if rendered:
                return rendered
            return (
                f"Compared expression in {left_label} versus {right_label}: "
                f"{metric_text}; {self._metric_label_text(difference_alias)} was {difference_value}."
            )
        if artifact_kind == "ranked_summary":
            analysis_kind = str(artifact.get("analysis_kind", "") or "")
            rendering = self._ranked_result_rendering_spec(analysis_kind)
            top_name = str(row.get("name", row.get("id", "the top result")) or "the top result")
            primary_alias_template = str(rendering.get("primary_alias", "") or "")
            secondary_alias_template = str(rendering.get("secondary_alias", "") or "")
            primary_alias = self._render_template(primary_alias_template, metadata) or primary_alias_template
            secondary_alias = self._render_template(secondary_alias_template, metadata) or secondary_alias_template
            context = {
                "top_name": top_name,
                "top_id": row.get("id", ""),
                "primary_value": row.get(primary_alias, "") if primary_alias else "",
                "secondary_value": row.get(secondary_alias, "") if secondary_alias else "",
                "subject_type": metadata.get("subject_type", "entity"),
                "measure_label": metadata.get("measure_label", ""),
                "row_count": len(rows),
            }
            if style == "explanatory":
                rendered = self._render_template(str(rendering.get("explanatory_template", "") or ""), context)
                if rendered:
                    return rendered
            rendered = self._render_template(str(rendering.get("concise_template", "") or ""), context)
            if rendered:
                return rendered
            return f"Top ranked result: {top_name}."
        return ""

    def _ranked_summary_answer(
        self,
        chat,
        analysis: dict[str, Any],
        *,
        sql: str,
        semantic_kind: str,
        trace_fields: dict[str, Any] | None = None,
        artifact_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            rows = chat.db.execute_read(str(sql))
        except Exception:
            rows = []
        if not rows:
            return self._answer_result(
                analysis=analysis,
                semantic_kind=semantic_kind,
                content="No ranked results matched the request.",
                results=[],
                sql=sql,
                artifact_kind="ranked_summary",
                artifact_metadata={**dict(artifact_metadata or {}), "empty": True},
                trace_fields=trace_fields,
            )
        return self._answer_result(
            analysis=analysis,
            semantic_kind=semantic_kind,
            results=rows,
            sql=sql,
            artifact_kind="ranked_summary",
            artifact_metadata=artifact_metadata,
            trace_fields=trace_fields,
        )

    def _count_distinct_aggregation_spec(self, over: str) -> dict[str, Any]:
        config = self._aggregation_config()
        grouped = config.get("count_distinct", {}) if isinstance(config, dict) else {}
        spec = grouped.get(str(over), {}) if isinstance(grouped, dict) else {}
        return dict(spec) if isinstance(spec, dict) else {}

    def _ranked_result_spec(self, analysis_kind: str) -> dict[str, Any]:
        config = self._aggregation_config()
        ranked = config.get("ranked_results", {}) if isinstance(config, dict) else {}
        spec = ranked.get(str(analysis_kind), {}) if isinstance(ranked, dict) else {}
        return dict(spec) if isinstance(spec, dict) else {}

    def _ranked_result_rendering_spec(self, analysis_kind: str) -> dict[str, Any]:
        spec = self._ranked_result_spec(analysis_kind)
        rendering = spec.get("rendering", {}) if isinstance(spec, dict) else {}
        return dict(rendering) if isinstance(rendering, dict) else {}

    def _ranked_result_value_expr(
        self,
        analysis: dict[str, Any],
        *,
        context: dict[str, Any] | None = None,
    ) -> str:
        analysis_kind = str(analysis.get("analysis_kind", "") or "")
        spec = self._ranked_result_spec(analysis_kind)
        template = str(spec.get("value_expr_template", "") or "").strip()
        if not template:
            return ""
        return self._format_registry_template(template, dict(context or {})).strip()

    def _grouped_metric_spec(self, metric_id: str) -> dict[str, Any]:
        config = self._aggregation_config()
        grouped = config.get("grouped_metrics", {}) if isinstance(config, dict) else {}
        spec = grouped.get(str(metric_id), {}) if isinstance(grouped, dict) else {}
        return dict(spec) if isinstance(spec, dict) else {}

    def _count_distinct_aggregation_columns(self, aggregations: list[dict[str, Any]]) -> list[tuple[str, str]]:
        columns: list[tuple[str, str]] = []
        for aggregation in aggregations:
            if not isinstance(aggregation, dict):
                continue
            if str(aggregation.get("type", "") or "") != "count_distinct":
                continue
            alias = str(aggregation.get("alias", "") or "").strip()
            over = str(aggregation.get("over", "") or "").strip()
            expr_template = str(self._count_distinct_aggregation_spec(over).get("expr_template", "") or "").strip()
            if not alias or not expr_template:
                continue
            columns.append((expr_template, alias))
        return columns

    def _ranked_result_order_by(
        self,
        analysis: dict[str, Any],
        *,
        fallback: list[str] | None = None,
        context: dict[str, Any] | None = None,
    ) -> list[str]:
        dimensions = analysis.get("dimensions", {}) if isinstance(analysis.get("dimensions"), dict) else {}
        explicit = [str(item).strip() for item in list(dimensions.get("order_by", []) or []) if str(item).strip()]
        if explicit:
            return explicit
        analysis_kind = str(analysis.get("analysis_kind", "") or "")
        spec = self._ranked_result_spec(analysis_kind)
        rendered: list[str] = []
        template_context = dict(context or {})
        template_context.setdefault("name_column", "e.name")
        for item in list(spec.get("default_order_by", []) or []):
            text = self._format_registry_template(str(item), template_context).strip()
            if not text:
                continue
            if text.lower().startswith("name "):
                rendered.append(f"e.{text}")
            else:
                rendered.append(text)
        if rendered:
            return rendered
        return [str(item).strip() for item in list(fallback or []) if str(item).strip()]

    def _ranked_result_extra_evidence_columns(
        self,
        analysis: dict[str, Any],
        *,
        context: dict[str, Any] | None = None,
    ) -> list[tuple[str, str]]:
        analysis_kind = str(analysis.get("analysis_kind", "") or "")
        spec = self._ranked_result_spec(analysis_kind)
        template_context = dict(context or {})
        columns: list[tuple[str, str]] = []
        for item in list(spec.get("extra_evidence", []) or []):
            if not isinstance(item, dict):
                continue
            expr_template = self._format_registry_template(str(item.get("expr_template", "") or ""), template_context).strip()
            alias = self._format_registry_template(str(item.get("alias", "") or ""), template_context).strip()
            if not expr_template or not alias:
                continue
            columns.append((expr_template, alias))
        return columns

    def _grouped_metric_evidence_columns(
        self,
        metric_id: str,
        *,
        context: dict[str, Any] | None = None,
    ) -> list[tuple[str, str]]:
        spec = self._grouped_metric_spec(metric_id)
        template_context = dict(context or {})
        columns: list[tuple[str, str]] = []
        for item in list(spec.get("evidence", []) or []):
            if not isinstance(item, dict):
                continue
            expr_template = self._format_registry_template(str(item.get("expr_template", "") or ""), template_context).strip()
            alias = self._format_registry_template(str(item.get("alias", "") or ""), template_context).strip()
            if not expr_template or not alias:
                continue
            columns.append((expr_template, alias))
        return columns

    def _grouped_metric_having_clause(
        self,
        metric_id: str,
        *,
        context: dict[str, Any] | None = None,
    ) -> str:
        spec = self._grouped_metric_spec(metric_id)
        return self._format_registry_template(
            str(spec.get("having_template", "") or ""),
            dict(context or {}),
        ).strip()

    def _validation_error_from_analysis_requirement(
        self,
        analysis_kind: str,
        *,
        sql_up: str,
        sql_low: str,
    ) -> str | None:
        requirement = self._validation_analysis_requirement(analysis_kind)
        if not requirement:
            return None
        required_up = [str(item) for item in list(requirement.get("required_sql_up_signatures", []) or []) if str(item).strip()]
        required_low = [str(item) for item in list(requirement.get("required_sql_low_signatures", []) or []) if str(item).strip()]
        if any(signature not in sql_up for signature in required_up):
            return str(requirement.get("failure_message", "") or "") or None
        if any(signature not in sql_low for signature in required_low):
            return str(requirement.get("failure_message", "") or "") or None
        return None

    def _matcher_config(self, matcher_id: str) -> dict[str, Any]:
        operators = self._registry_operators()
        matchers = operators.get("matchers", {}) if isinstance(operators, dict) else {}
        matcher = matchers.get(str(matcher_id), {}) if isinstance(matchers, dict) else {}
        return dict(matcher) if isinstance(matcher, dict) else {}

    def _live_promoted_entity_config(self) -> dict[str, Any]:
        operators = self._registry_operators()
        config = operators.get("live_promoted_entities", {}) if isinstance(operators, dict) else {}
        return dict(config) if isinstance(config, dict) else {}

    def _condition_matching_config(self) -> dict[str, Any]:
        operators = self._registry_operators()
        config = operators.get("condition_matching", {}) if isinstance(operators, dict) else {}
        return dict(config) if isinstance(config, dict) else {}

    def _scope_tag_source_config(self) -> dict[str, Any]:
        operators = self._registry_operators()
        config = operators.get("scope_tag_source", {}) if isinstance(operators, dict) else {}
        return dict(config) if isinstance(config, dict) else {}

    def _matcher_has_any_cue(self, message: str, matcher_id: str, field: str = "required_any_message_cues") -> bool:
        matcher = self._matcher_config(matcher_id)
        low = self._normalized_prompt_text(message)
        raw_low = str(message or "").lower()
        return any(
            str(token) in low or str(token) in raw_low
            for token in list(matcher.get(field, []) or [])
            if str(token).strip()
        )

    def _result_type_preference_config(self) -> dict[str, Any]:
        config = self.semantic_registry.get("result_type_preferences", {}) if isinstance(self.semantic_registry, dict) else {}
        return dict(config) if isinstance(config, dict) else {}

    def _annotation_namespace_specs(self) -> list[dict[str, Any]]:
        specs = self.semantic_registry.get("annotation_namespaces", []) if isinstance(self.semantic_registry, dict) else []
        return [dict(spec) for spec in list(specs or []) if isinstance(spec, dict)]

    def _common_promoted_entity_specs(self) -> list[dict[str, Any]]:
        specs = self.semantic_registry.get("common_promoted_entities", []) if isinstance(self.semantic_registry, dict) else []
        return [dict(spec) for spec in list(specs or []) if isinstance(spec, dict)]

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

    def _analysis_for_metadata_filters(
        self,
        chat,
        message: str,
        requested_types: list[str],
    ) -> dict[str, Any] | None:
        filters = self._requested_metadata_filters(message)
        requested_type = requested_types[0] if requested_types else ""
        if not requested_type or not filters:
            return None
        return {
            "analysis_kind": "metadata_filters",
            "domain": "genomics",
            "intent": "filter",
            "requested_result_kind": "entity_rows",
            "subject": {"entity_type": requested_type},
            "filters": [dict(item) for item in filters],
            "evidence": {
                "include": [
                    str((item.get("display") or {}).get("alias") or item.get("field") or "")
                    for item in filters
                    if str((item.get("display") or {}).get("alias") or item.get("field") or "").strip()
                ]
            },
        }

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

    def _analysis_for_functional_derived_connections(
        self,
        chat,
        message: str,
        requested_types: list[str],
    ) -> dict[str, Any] | None:
        if not self._requests_functional_derived_connections(message, requested_types):
            return None
        patterns = set(chat._typed_rel_patterns())
        if ("protein", "HAS_ANNOTATION", "annotation_term") not in patterns:
            return None
        limit = self._requested_limit(message)
        low = f" {str(message or '').lower()} "
        if limit is None and (" most " in low or " highest " in low):
            limit = 1
        summary_style = self._summary_style_for_message(message)
        return {
            "analysis_kind": "functional_derived_connections",
            "domain": "genomics",
            "intent": "rank",
            "requested_result_kind": self._summary_result_kind_for_style(summary_style, default="ranked_rows"),
            "subject": {"entity_type": "protein"},
            "paths": [{
                "source_type": "protein",
                "target_type": "protein",
                "via_type": "annotation_term",
                "rel_chain": ["HAS_ANNOTATION", "HAS_ANNOTATION"],
            }],
            "aggregations": [
                {"type": "count_distinct", "over": "other_proteins", "alias": "derived_connection_count"},
                {"type": "count_distinct", "over": "shared_annotation_terms", "alias": "shared_annotation_count"},
            ],
            "dimensions": {"limit": limit},
            "evidence": {"include": ["derived_connection_count", "shared_annotation_count"]},
            "presentation": {"prefer_summary": summary_style == "explanatory", "prefer_table": summary_style != "explanatory", "summary_style": summary_style},
        }

    def _compile_functional_derived_connection_analysis(
        self,
        chat,
        analysis: dict[str, Any],
    ) -> str | dict[str, Any] | None:
        if str(analysis.get("subject", {}).get("entity_type", "") or "") != "protein":
            return None
        patterns = set(chat._typed_rel_patterns())
        if ("protein", "HAS_ANNOTATION", "annotation_term") not in patterns:
            return None
        limit = analysis.get("dimensions", {}).get("limit")
        evidence_columns = self._count_distinct_aggregation_columns(
            [dict(item) for item in list(analysis.get("aggregations", []) or []) if isinstance(item, dict)]
        )
        if len(evidence_columns) != 2:
            return None
        order_by = self._ranked_result_order_by(
            analysis,
            fallback=["derived_connection_count DESC", "shared_annotation_count DESC", "e.name ASC"],
        )
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
            f"ORDER BY {', '.join(order_by)}",
        ]
        if limit:
            lines.append(f"LIMIT {int(limit)}")
        rendered_sql = "\n".join(lines)
        if str(analysis.get("requested_result_kind", "") or "") == "narrative":
            return self._ranked_summary_answer(
                chat,
                analysis,
                sql=rendered_sql,
                semantic_kind="functional_derived_connections",
                trace_fields={},
                artifact_metadata={"subject_type": "protein"},
            )
        return self._analysis_synthesis_result(
            rendered_sql,
            analysis=analysis,
            evidence_columns=evidence_columns,
            semantic_trace=self._analysis_trace("functional_derived_connections", analysis),
        )

    def _requests_functional_annotation_ranking(self, message: str, requested_types: list[str]) -> bool:
        if not any(item in {"gene", "transcript", "protein"} for item in requested_types):
            return False
        return self._matcher_has_any_cue(message, "functional_annotation_ranking") and self._matcher_has_any_cue(
            message,
            "functional_annotation_ranking",
            field="ranking_any_message_cues",
        )

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

    def _analysis_for_functional_annotation_ranking(
        self,
        chat,
        message: str,
        requested_types: list[str],
    ) -> dict[str, Any] | None:
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
        summary_style = self._summary_style_for_message(message)
        return {
            "analysis_kind": "functional_annotation_ranking",
            "domain": "genomics",
            "intent": "rank",
            "requested_result_kind": self._summary_result_kind_for_style(summary_style, default="ranked_rows"),
            "subject": {"entity_type": requested_type},
            "paths": [
                {
                    "source_type": requested_type,
                    "target_type": owner_type,
                    "rel_chain": [rel for _src, rel, _dst in path],
                    "path_nodes": [requested_type, *[dst for _src, _rel, dst in path]],
                }
            ],
            "filters": [],
            "aggregations": [{"type": "count_distinct", "over": "annotation_terms", "alias": "functional_annotation_count"}],
            "dimensions": {"limit": limit},
            "evidence": {"include": ["functional_annotation_count"]},
            "owner_type": owner_type,
            "presentation": {"prefer_summary": summary_style == "explanatory", "prefer_table": summary_style != "explanatory", "summary_style": summary_style},
        }

    def _compile_functional_annotation_ranking_analysis(
        self,
        _chat,
        analysis: dict[str, Any],
    ) -> str | dict[str, Any] | None:
        requested_type = str(analysis.get("subject", {}).get("entity_type", "") or "")
        owner_type = str(analysis.get("owner_type", "") or requested_type)
        limit = analysis.get("dimensions", {}).get("limit")
        path = list(analysis.get("paths", []) or [])
        joins: list[str] = []
        owner_ref = "e.id"
        if path:
            rel_chain = [str(item) for item in list(path[0].get("rel_chain", []) or []) if str(item).strip()]
            path_nodes = [str(item) for item in list(path[0].get("path_nodes", []) or []) if str(item).strip()]
            current_type = requested_type
            alias_index = 0
            for rel, dst in zip(rel_chain, path_nodes[1:]):
                if current_type == owner_type:
                    break
                alias_index += 1
                rel_alias = f"p{alias_index}"
                joins.append(
                    f"JOIN relationships {rel_alias} ON {rel_alias}.source_id = {owner_ref} AND {rel_alias}.rel_type = '{rel}'"
                )
                owner_ref = f"{rel_alias}.target_id"
                current_type = dst
        evidence_columns = self._count_distinct_aggregation_columns(
            [dict(item) for item in list(analysis.get("aggregations", []) or []) if isinstance(item, dict)]
        )
        if len(evidence_columns) != 1:
            return None
        order_by = self._ranked_result_order_by(
            analysis,
            fallback=["functional_annotation_count DESC", "e.name ASC"],
        )
        lines = [
            self._select_clause_with_evidence(evidence_columns),
            "FROM entities e",
            *joins,
            f"JOIN relationships ha ON ha.source_id = {owner_ref} AND ha.rel_type = 'HAS_ANNOTATION'",
            "JOIN entities ann ON ann.id = ha.target_id AND ann.type = 'annotation_term'",
            f"WHERE e.type = '{requested_type}'",
            "GROUP BY e.id, e.name, e.type",
            f"ORDER BY {', '.join(order_by)}",
        ]
        if limit:
            lines.append(f"LIMIT {int(limit)}")
        rendered_sql = "\n".join(lines)
        if str(analysis.get("requested_result_kind", "") or "") == "narrative":
            return self._ranked_summary_answer(
                _chat,
                analysis,
                sql=rendered_sql,
                semantic_kind="functional_annotation_ranking",
                trace_fields={"requested_type": requested_type, "owner_type": owner_type},
                artifact_metadata={"subject_type": requested_type},
            )
        return self._analysis_synthesis_result(
            rendered_sql,
            analysis=analysis,
            evidence_columns=evidence_columns,
            semantic_trace=self._analysis_trace("functional_annotation_ranking", analysis, requested_type=requested_type, owner_type=owner_type),
        )

    def _requested_functional_annotation_namespace(self, message: str) -> dict[str, Any] | None:
        low = self._normalized_prompt_text(message)
        for spec in self._annotation_namespace_specs():
            if any(self._normalized_prompt_text(alias) in low for alias in spec["aliases"]):
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

    def _matched_named_entities(
        self,
        chat,
        message: str,
        matcher_id: str,
        *,
        phrase_candidates: list[str] | None = None,
        allowed_types: list[str] | None = None,
        id_prefixes: list[str] | None = None,
    ) -> list[tuple[str, str, str]]:
        matcher = self._matcher_config(matcher_id)
        phrase_source = str(matcher.get("phrase_source", "message_candidates") or "message_candidates")
        if phrase_candidates is None:
            if phrase_source == "organism_phrase_candidates":
                phrase_candidates = self._requested_organism_phrase_candidates(message)
            else:
                phrase_candidates = chat._message_candidate_phrases(message)
        type_filter = {
            str(item).strip()
            for item in (allowed_types if allowed_types is not None else list(matcher.get("entity_types", []) or []))
            if str(item).strip()
        }
        prefix_filter = tuple(
            str(item).strip()
            for item in (id_prefixes if id_prefixes is not None else list(matcher.get("entity_id_prefixes", []) or []))
            if str(item).strip()
        )
        matches: list[tuple[str, str, str]] = []
        seen: set[tuple[str, str, str]] = set()
        for phrase in phrase_candidates:
            for entity_id, entity_type, entity_name in chat._entity_name_matches(phrase):
                normalized = (
                    str(entity_id or "").strip(),
                    str(entity_type or "").strip(),
                    str(entity_name or "").strip(),
                )
                entity_id_text, entity_type_text, entity_name_text = normalized
                if not entity_id_text or not entity_type_text or not entity_name_text:
                    continue
                if type_filter and entity_type_text not in type_filter:
                    continue
                if prefix_filter and not any(entity_id_text.startswith(prefix) for prefix in prefix_filter):
                    continue
                if normalized in seen:
                    continue
                seen.add(normalized)
                matches.append(normalized)
        return matches

    @classmethod
    def _matched_items_by_aliases(
        cls,
        message: str,
        items: list[Any],
        *,
        alias_getter,
        key_getter=None,
    ) -> list[Any]:
        matched: list[Any] = []
        seen: set[Any] = set()
        for item in items:
            aliases = [str(alias) for alias in list(alias_getter(item) or []) if str(alias).strip()]
            if not aliases or not cls._message_matches_aliases(message, aliases):
                continue
            key = key_getter(item) if key_getter is not None else id(item)
            if key in seen:
                continue
            seen.add(key)
            matched.append(item)
        return matched

    def _relation_family_specs_for_matching(self, family_id: str) -> list[dict[str, Any]]:
        if family_id == "ortholog_member":
            spec = self._ortholog_member_spec()
            return [spec] if isinstance(spec, dict) and spec else []
        return self._evidence_relation_specs(family_id)

    def _matched_relation_family_conditions(
        self,
        message: str,
        *,
        family_id: str,
        kind: str,
        build_condition,
    ) -> list[dict[str, Any]]:
        conditions: list[dict[str, Any]] = []
        for spec in self._matched_items_by_aliases(
            message,
            self._relation_family_specs_for_matching(family_id),
            alias_getter=lambda item: list(item.get("aliases", []) or []),
            key_getter=lambda item: str(item.get("id", "") or item.get("rel_type", "") or family_id),
        ):
            parser = self._condition_parser(str(spec.get("parser_kind", "") or ""))
            parser_mode = str(parser.get("mode", "") or "alias_match")
            low = str(message or "").lower()
            exclude_patterns = [str(pattern) for pattern in list(spec.get("exclude_patterns", []) or []) if str(pattern).strip()]
            if parser_mode == "alias_match":
                pass
            elif parser_mode == "alias_match_excluding_terms":
                if any(re.search(pattern, low) for pattern in exclude_patterns):
                    continue
            else:
                continue
            condition = build_condition(dict(spec))
            if isinstance(condition, dict):
                condition.setdefault("kind", kind)
                conditions.append(condition)
        return conditions

    @staticmethod
    def _condition_matches_rule(condition: dict[str, Any], rule: dict[str, Any]) -> bool:
        for key, expected in rule.items():
            if str(condition.get(str(key), "") or "") != str(expected):
                return False
        return True

    def _pruned_conditions(self, conditions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        config = self._condition_matching_config()
        prune_rules = [dict(item) for item in list(config.get("prune_rules", []) or []) if isinstance(item, dict)]
        pruned = [dict(item) for item in conditions if isinstance(item, dict)]
        for rule in prune_rules:
            present_rule = dict(rule.get("if_present", {}) or {})
            drop_rule = dict(rule.get("drop", {}) or {})
            if not present_rule or not drop_rule:
                continue
            if not any(self._condition_matches_rule(cond, present_rule) for cond in pruned):
                continue
            pruned = [cond for cond in pruned if not self._condition_matches_rule(cond, drop_rule)]
        return pruned

    def _ordered_condition_builders(self) -> list[str]:
        config = self._condition_matching_config()
        ordered = [str(item) for item in list(config.get("ordered_builders", []) or []) if str(item).strip()]
        return ordered or [
            "protein_evidence",
            "effector_tag",
            "orthogroup_filter",
            "ortholog_member",
            "promoted_call",
            "generic_tag",
            "scope_tag",
        ]

    def _match_condition_builder(self, chat, message: str, builder_id: str) -> list[dict[str, Any]]:
        if builder_id == "protein_evidence":
            return self._matched_protein_evidence_conditions(message)
        if builder_id == "effector_tag":
            return self._matched_dynamic_family_conditions(chat, message, "effector_evidence")
        if builder_id == "orthogroup_filter":
            orthogroup_label = self._requested_orthogroup_label(message)
            return [{"kind": "orthogroup_filter", "label": orthogroup_label}] if orthogroup_label else []
        if builder_id == "ortholog_member":
            return self._matched_ortholog_member_conditions(message)
        if builder_id == "promoted_call":
            return self._matched_promoted_call_conditions(chat, message)
        if builder_id == "generic_tag":
            return self._matched_generic_tag_conditions(chat, message)
        if builder_id == "scope_tag":
            return [{"kind": "scope_tag", "tag_id": tag_id} for tag_id in self._requested_scope_tag_ids(chat, message)]
        return []

    def _requested_condition_bundle(
        self,
        chat,
        message: str,
        requested_types: list[str],
    ) -> dict[str, Any]:
        analysis = self.analyze_request(chat, message, requested_types)
        conditions = self._analysis_conditions(analysis)
        if not conditions:
            matched: list[dict[str, Any]] = []
            for builder_id in self._ordered_condition_builders():
                matched.extend(self._match_condition_builder(chat, message, builder_id))
            conditions = self._pruned_conditions(matched)
        return {
            "analysis": analysis,
            "conditions": conditions,
            "condition_context": self._condition_validation_context(conditions),
        }

    @staticmethod
    def _live_promoted_entity_aliases(spec: dict[str, Any], config: dict[str, Any]) -> list[str]:
        alias_fields = [str(item) for item in list(config.get("alias_fields", []) or []) if str(item).strip()]
        aliases: list[str] = []
        for field_name in alias_fields:
            value = str(spec.get(field_name, "") or "").strip()
            if not value:
                continue
            aliases.append(f" {value.replace('_', ' ')} ")
        return aliases

    def _live_promoted_entity_specs(self, chat) -> list[dict[str, Any]]:
        config = self._live_promoted_entity_config()
        required_target_metadata_field = str(config.get("required_target_metadata_field", "category") or "category")
        excluded_result_types = {
            str(item).strip()
            for item in list(config.get("excluded_result_types", []) or [])
            if str(item).strip()
        }
        excluded_rel_types = {
            str(item).strip()
            for item in list(config.get("excluded_rel_types", []) or [])
            if str(item).strip()
        }
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
            if not owner_type or not result_type or not rel_type:
                continue
            if required_target_metadata_field == "category" and not category:
                continue
            if result_type in excluded_result_types or rel_type in excluded_rel_types:
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
        config = self._live_promoted_entity_config()
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
            auto["aliases"] = self._live_promoted_entity_aliases(auto, config)
            auto["count_alias"] = str(config.get("default_count_alias", "assigned_entity_count") or "assigned_entity_count")
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
        if not self._matcher_has_any_cue(message, "promoted_call"):
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
            matched_rows = self._matched_items_by_aliases(
                message,
                list(rows or []),
                alias_getter=lambda row: (
                    list(self._promoted_call_name_aliases(str(row.get("name", "") or "")))
                    + ([source_column_hint.replace("_", " ").strip().lower()] if source_column_hint else [])
                ),
                key_getter=lambda row: str(row.get("id", "") or "").strip(),
            )
            for row in matched_rows:
                entity_id = str(row.get("id", "") or "").strip()
                entity_name = str(row.get("name", "") or "").strip()
                if not entity_id or not entity_name:
                    continue
                if entity_id in seen_ids:
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
        if not self._matcher_has_any_cue(message, "generic_tag"):
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
        for row in self._matched_items_by_aliases(
            message,
            list(rows or []),
            alias_getter=lambda row: list(self._promoted_call_name_aliases(str(row.get("name", "") or ""))),
            key_getter=lambda row: (
                str(row.get("owner_type", "") or "").strip(),
                str(row.get("id", "") or "").strip(),
            ),
        ):
            owner_type = str(row.get("owner_type", "") or "").strip()
            tag_id = str(row.get("id", "") or "").strip()
            tag_name = str(row.get("name", "") or "").strip()
            if not owner_type or not tag_id or not tag_name:
                continue
            conditions.append({
                "kind": "generic_tag",
                "owner_type": owner_type,
                "tag_id": tag_id,
                "tag_name": tag_name,
            })
        return conditions

    def _analysis_for_promoted_call_filters(
        self,
        chat,
        message: str,
        requested_types: list[str],
    ) -> dict[str, Any] | None:
        conditions = self._match_condition_builder(chat, message, "promoted_call")
        if not conditions:
            return None
        requested_type = self._requested_core_type(requested_types)
        if requested_type not in {"gene", "transcript", "protein"}:
            requested_type = str(conditions[0].get("owner_type", "protein") or "protein")
        return {
            "analysis_kind": "promoted_call_filters",
            "domain": "genomics",
            "intent": "filter",
            "requested_result_kind": "entity_rows",
            "subject": {"entity_type": requested_type},
            "filters": [
                {
                    "type": "promoted_call_filter",
                    "owner_type": str(cond.get("owner_type", "protein") or "protein"),
                    "rel_type": str(cond.get("rel_type", "") or ""),
                    "target_type": str(cond.get("result_type", "") or ""),
                    "target_id": str(cond.get("entity_id", "") or ""),
                    "target_name": str(cond.get("entity_name", "") or ""),
                    "category": str(cond.get("category", "") or ""),
                }
                for cond in conditions
            ],
            "evidence": {"include": ["matched_call", "matched_call_category"]},
        }

    def _compile_promoted_call_filter_analysis(
        self,
        chat,
        analysis: dict[str, Any],
    ) -> str | dict[str, Any] | None:
        requested_type = str(analysis.get("subject", {}).get("entity_type", "") or "")
        filters = list(analysis.get("filters", []) or [])
        conditions = [
            {
                "kind": "promoted_call",
                "owner_type": str(item.get("owner_type", "protein") or "protein"),
                "rel_type": str(item.get("rel_type", "") or ""),
                "result_type": str(item.get("target_type", "") or ""),
                "entity_id": str(item.get("target_id", "") or ""),
                "entity_name": str(item.get("target_name", "") or ""),
                "category": str(item.get("category", "") or ""),
            }
            for item in filters
            if str(item.get("type", "") or "") == "promoted_call_filter"
        ]
        if not requested_type or not conditions:
            return None
        state = {"evidence_columns": []}
        rendered_sql = self._build_semantic_entity_query(
            chat,
            requested_type=requested_type,
            conditions=conditions,
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
        return self._analysis_synthesis_result(
            rendered_sql,
            analysis=analysis,
            evidence_columns=evidence_columns,
            semantic_trace=self._analysis_trace(
                "genomics_promoted_call_filters",
                analysis,
                condition_kinds=[str(cond.get("kind", "") or "") for cond in conditions],
            ),
        )

    def _analysis_for_generic_tag_filters(
        self,
        chat,
        message: str,
        requested_types: list[str],
    ) -> dict[str, Any] | None:
        conditions = self._match_condition_builder(chat, message, "generic_tag")
        if not conditions:
            return None
        requested_type = self._requested_core_type(requested_types)
        if requested_type not in {"gene", "transcript", "protein"}:
            requested_type = str(conditions[0].get("owner_type", "protein") or "protein")
        return {
            "analysis_kind": "generic_tag_filters",
            "domain": "genomics",
            "intent": "filter",
            "requested_result_kind": "entity_rows",
            "subject": {"entity_type": requested_type},
            "filters": [
                {
                    "type": "tag_filter",
                    "owner_type": str(cond.get("owner_type", "") or requested_type),
                    "tag_id": str(cond.get("tag_id", "") or ""),
                    "tag_name": str(cond.get("tag_name", "") or ""),
                }
                for cond in conditions
            ],
            "evidence": {"include": ["matched_tag"]},
        }

    def _compile_generic_tag_filter_analysis(
        self,
        chat,
        analysis: dict[str, Any],
    ) -> str | dict[str, Any] | None:
        requested_type = str(analysis.get("subject", {}).get("entity_type", "") or "")
        filters = list(analysis.get("filters", []) or [])
        conditions = [
            {
                "kind": "generic_tag",
                "owner_type": str(item.get("owner_type", "") or requested_type),
                "tag_id": str(item.get("tag_id", "") or ""),
                "tag_name": str(item.get("tag_name", "") or ""),
            }
            for item in filters
            if str(item.get("type", "") or "") == "tag_filter"
        ]
        if not requested_type or not conditions:
            return None
        state = {"evidence_columns": []}
        rendered_sql = self._build_semantic_entity_query(
            chat,
            requested_type=requested_type,
            conditions=conditions,
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
        return self._analysis_synthesis_result(
            rendered_sql,
            analysis=analysis,
            evidence_columns=evidence_columns,
            semantic_trace=self._analysis_trace(
                "genomics_generic_tag_filters",
                analysis,
                condition_kinds=[str(cond.get("kind", "") or "") for cond in conditions],
            ),
        )

    def _analysis_for_multi_condition_filters(
        self,
        chat,
        message: str,
        requested_types: list[str],
    ) -> dict[str, Any] | None:
        requested_type = self._requested_core_type(requested_types)
        if requested_type not in {"gene", "transcript", "protein"}:
            return None
        conditions = self._semantic_conditions(chat, message)
        if not conditions:
            return None
        condition_kinds = {str(cond.get("kind", "") or "") for cond in conditions}
        if condition_kinds.issubset({"promoted_call", "generic_tag"}):
            return None
        return {
            "analysis_kind": "multi_condition_filters",
            "domain": "genomics",
            "intent": "filter",
            "requested_result_kind": "entity_rows",
            "subject": {"entity_type": requested_type},
            "conditions": [dict(cond) for cond in conditions],
            "homology_organisms": [dict(item) for item in self._requested_homology_organism_matches(chat, message)],
            "evidence": {
                "include": [
                    "condition_display_columns",
                    "hgt_donor",
                    "orthogroup_label",
                    "homology_scope",
                    "homolog_organism",
                ]
            },
        }

    def _analysis_for_effector_tag_filters(
        self,
        chat,
        message: str,
        requested_types: list[str],
    ) -> dict[str, Any] | None:
        analysis = self._semantic_condition_route_analysis(chat, message, requested_types, "effector_tag_filters")
        if not analysis:
            return None
        family = self._registry_dynamic_family("effector_evidence")
        conditions = [dict(cond) for cond in list(analysis.get("conditions", []) or []) if isinstance(cond, dict)]
        analysis["families"] = sorted({
            self._dynamic_family_condition_family(message, cond, family)
            for cond in conditions
            if str(cond.get("kind", "") or "") == "tag_evidence"
            and self._dynamic_family_condition_family(message, cond, family).strip()
        })
        return analysis

    def _analysis_for_scope_tag_filters(
        self,
        chat,
        message: str,
        requested_types: list[str],
    ) -> dict[str, Any] | None:
        return self._semantic_condition_route_analysis(chat, message, requested_types, "scope_tag_filters")

    def _analysis_for_comparative_scope_filters(
        self,
        chat,
        message: str,
        requested_types: list[str],
    ) -> dict[str, Any] | None:
        return self._semantic_condition_route_analysis(chat, message, requested_types, "comparative_scope_filters")

    def _analysis_for_evidence_homology_organism_filters(
        self,
        chat,
        message: str,
        requested_types: list[str],
    ) -> dict[str, Any] | None:
        return self._semantic_condition_route_analysis(chat, message, requested_types, "evidence_homology_organism_filters")

    def _analysis_for_evidence_orthogroup_filters(
        self,
        chat,
        message: str,
        requested_types: list[str],
    ) -> dict[str, Any] | None:
        return self._semantic_condition_route_analysis(chat, message, requested_types, "evidence_orthogroup_filters")

    def _analysis_for_evidence_ortholog_member_filters(
        self,
        chat,
        message: str,
        requested_types: list[str],
    ) -> dict[str, Any] | None:
        return self._semantic_condition_route_analysis(chat, message, requested_types, "evidence_ortholog_member_filters")

    def _compile_multi_condition_filter_analysis(
        self,
        chat,
        analysis: dict[str, Any],
    ) -> str | dict[str, Any] | None:
        requested_type = str(analysis.get("subject", {}).get("entity_type", "") or "")
        conditions = [dict(cond) for cond in list(analysis.get("conditions", []) or []) if isinstance(cond, dict)]
        if requested_type not in {"gene", "transcript", "protein"} or not conditions:
            return None
        state = {
            "scope_tag_ids": {str(cond.get("tag_id", "") or "") for cond in conditions if str(cond.get("kind", "") or "") == "scope_tag"},
            "used_scope_tags": set(),
            "has_protein_evidence": any(str(cond.get("kind", "") or "") == "protein_evidence" for cond in conditions),
            "evidence_columns": [],
            "homology_organisms": [dict(item) for item in list(analysis.get("homology_organisms", []) or []) if isinstance(item, dict)],
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
        return self._analysis_synthesis_result(
            rendered_sql,
            analysis=analysis,
            evidence_columns=evidence_columns,
            semantic_trace=self._analysis_trace(
                "genomics_multi_condition_filters",
                analysis,
                requested_type=requested_type,
                condition_kinds=[str(cond.get("kind", "") or "") for cond in conditions],
            ),
        )

    @staticmethod
    def _condition_validation_context(conditions: list[dict[str, Any]]) -> dict[str, Any]:
        requested_protein_rel_types = {
            str(cond.get("rel_type", "") or "")
            for cond in conditions
            if str(cond.get("kind", "") or "") == "protein_evidence" and str(cond.get("rel_type", "") or "").strip()
        }
        requested_scope_tags = {
            str(cond.get("tag_id", "") or "").upper()
            for cond in conditions
            if str(cond.get("kind", "") or "") == "scope_tag" and str(cond.get("tag_id", "") or "").strip()
        }
        requested_tag_evidence_ids = {
            str(cond.get("id", "") or "")
            for cond in conditions
            if str(cond.get("kind", "") or "") == "tag_evidence" and str(cond.get("id", "") or "").strip()
        }
        requested_has_ortholog_member = any(
            str(cond.get("kind", "") or "") == "ortholog_member"
            for cond in conditions
        )
        requested_promoted_call_conditions = [
            dict(cond)
            for cond in conditions
            if str(cond.get("kind", "") or "") == "promoted_call"
        ]
        return {
            "requested_protein_rel_types": requested_protein_rel_types,
            "requested_scope_tags": requested_scope_tags,
            "requested_tag_evidence_ids": requested_tag_evidence_ids,
            "requested_has_ortholog_member": requested_has_ortholog_member,
            "requested_promoted_call_conditions": requested_promoted_call_conditions,
        }

    def _analysis_conditions(self, analysis: dict[str, Any] | None) -> list[dict[str, Any]]:
        if not isinstance(analysis, dict):
            return []
        analysis_kind = str(analysis.get("analysis_kind", "") or "")
        if list(analysis.get("conditions", []) or []):
            return [dict(item) for item in list(analysis.get("conditions", []) or []) if isinstance(item, dict)]
        if analysis_kind == "promoted_call_filters":
            return [
                {
                    "kind": "promoted_call",
                    "result_type": str(item.get("result_type", "") or ""),
                    "rel_type": str(item.get("rel_type", "") or ""),
                    "entity_id": str(item.get("entity_id", "") or ""),
                    "entity_name": str(item.get("entity_name", "") or ""),
                    "category": str(item.get("category", "") or ""),
                    "owner_type": str(item.get("owner_type", "") or ""),
                }
                for item in list(analysis.get("filters", []) or [])
                if isinstance(item, dict) and str(item.get("type", "") or "") == "promoted_call_filter"
            ]
        if analysis_kind == "generic_tag_filters":
            return [
                {
                    "kind": "generic_tag",
                    "owner_type": str(item.get("owner_type", "") or ""),
                    "tag_id": str(item.get("tag_id", "") or ""),
                    "tag_name": str(item.get("tag_name", "") or ""),
                }
                for item in list(analysis.get("filters", []) or [])
                if isinstance(item, dict) and str(item.get("type", "") or "") == "tag_filter"
            ]
        if analysis_kind == "effector_tag_filters":
            return [dict(item) for item in list(analysis.get("filters", []) or []) if isinstance(item, dict)]
        return []

    @staticmethod
    def _analysis_filter_values(
        analysis: dict[str, Any] | None,
        *,
        filter_type: str,
        field: str,
    ) -> list[str]:
        if not isinstance(analysis, dict):
            return []
        values: list[str] = []
        for item in list(analysis.get("filters", []) or []):
            if not isinstance(item, dict) or str(item.get("type", "") or "") != filter_type:
                continue
            raw = item.get(field)
            if isinstance(raw, list):
                values.extend(str(value) for value in raw if str(value).strip())
            elif str(raw or "").strip():
                values.append(str(raw))
        return values

    def _condition_sql_signatures(self, cond: dict[str, Any], *, ortholog_member_rel_type: str = "") -> list[str]:
        kind = str(cond.get("kind", "") or "")
        if kind == "protein_evidence":
            rel_type = str(cond.get("rel_type", "") or "").strip()
            return [rel_type] if rel_type else []
        if kind == "tag_evidence":
            return [
                *[str(tag_id) for tag_id in list(cond.get("tag_ids", []) or []) if str(tag_id).strip()],
                *[
                    name
                    for tag_id in list(cond.get("tag_ids", []) or [])
                    if str(tag_id).strip()
                    if (name := self._tag_id_to_name_signature(tag_id))
                ],
            ]
        if kind == "generic_tag":
            tag_id = str(cond.get("tag_id", "") or "").strip()
            tag_name = str(cond.get("tag_name", "") or "").strip()
            signatures = [tag_id] if tag_id else []
            if tag_name:
                signatures.append(tag_name)
            return signatures
        if kind == "scope_tag":
            tag_id = str(cond.get("tag_id", "") or "").strip()
            return [tag_id] if tag_id else []
        if kind == "ortholog_member":
            return [ortholog_member_rel_type] if ortholog_member_rel_type else []
        if kind == "orthogroup_filter":
            label = str(cond.get("label", "") or "").strip()
            signatures = [label] if label else []
            if label:
                signatures.append(f"orthogroup:{label}")
            return signatures
        if kind == "promoted_call":
            signatures = []
            rel_type = str(cond.get("rel_type", "") or "").strip()
            entity_id = str(cond.get("entity_id", "") or "").strip()
            if rel_type:
                signatures.append(rel_type)
            if entity_id:
                signatures.append(entity_id)
            return signatures
        return []

    def _compile_effector_tag_filter_analysis(
        self,
        chat,
        analysis: dict[str, Any],
    ) -> str | dict[str, Any] | None:
        synthesized = self._compile_semantic_condition_route_analysis(chat, analysis, "effector_tag_filters")
        if isinstance(synthesized, str):
            payload: dict[str, Any] = {"sql": str(synthesized)}
            evidence_columns = getattr(synthesized, "evidence_columns", None)
            semantic_trace = getattr(synthesized, "semantic_trace", None)
            if isinstance(evidence_columns, list):
                payload["evidence_columns"] = list(evidence_columns)
            if isinstance(semantic_trace, dict):
                payload["semantic_trace"] = dict(semantic_trace)
            return payload
        return synthesized

    def _compile_scope_tag_filter_analysis(
        self,
        chat,
        analysis: dict[str, Any],
    ) -> str | dict[str, Any] | None:
        return self._compile_semantic_condition_route_analysis(chat, analysis, "scope_tag_filters")

    def _compile_comparative_scope_filter_analysis(
        self,
        chat,
        analysis: dict[str, Any],
    ) -> str | dict[str, Any] | None:
        return self._compile_semantic_condition_route_analysis(chat, analysis, "comparative_scope_filters")

    def _compile_evidence_homology_organism_filter_analysis(
        self,
        chat,
        analysis: dict[str, Any],
    ) -> str | dict[str, Any] | None:
        return self._compile_semantic_condition_route_analysis(chat, analysis, "evidence_homology_organism_filters")

    def _compile_evidence_orthogroup_filter_analysis(
        self,
        chat,
        analysis: dict[str, Any],
    ) -> str | dict[str, Any] | None:
        return self._compile_semantic_condition_route_analysis(chat, analysis, "evidence_orthogroup_filters")

    def _compile_evidence_ortholog_member_filter_analysis(
        self,
        chat,
        analysis: dict[str, Any],
    ) -> str | dict[str, Any] | None:
        return self._compile_semantic_condition_route_analysis(chat, analysis, "evidence_ortholog_member_filters")

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
        if (
            "annotation_term" not in requested_types
            and not self._requested_functional_annotation_namespace(message)
            and not self._requests_functional_annotation_category(message)
        ):
            return False
        return self._matcher_has_any_cue(message, "common_ranking")

    def _requests_functional_annotation_category(self, message: str) -> bool:
        return self._matcher_has_any_cue(message, "functional_annotation_category")

    def _analysis_for_common_functional_annotation_terms(
        self,
        chat,
        message: str,
        requested_types: list[str],
    ) -> dict[str, Any] | None:
        if not self._requests_common_functional_annotation_terms(message, requested_types):
            return None
        patterns = set(chat._typed_rel_patterns())
        if ("protein", "HAS_ANNOTATION", "annotation_term") not in patterns:
            return None
        low = f" {str(message or '').lower()} "
        namespace_spec = self._requested_functional_annotation_namespace(message)
        limit = self._requested_limit(message)
        if limit is None and (" most common " in low or " commonest " in low):
            limit = 1
        summary_style = self._summary_style_for_message(message)
        filters: list[dict[str, str]] = []
        if namespace_spec:
            namespace = str(namespace_spec.get("namespace", "") or "").strip()
            category = str(namespace_spec.get("category", "") or "").strip()
            if namespace:
                filters.append({"type": "metadata_filter", "field": "namespace", "value": namespace})
            if category:
                filters.append({"type": "metadata_filter", "field": "category", "value": category})
        elif self._requests_functional_annotation_category(message):
            filters.append({"type": "metadata_filter", "field": "category", "value": "functional_annotation"})
        return {
            "analysis_kind": "common_functional_annotation_terms",
            "domain": "genomics",
            "intent": "rank",
            "requested_result_kind": "ranked_rows",
            "subject": {"entity_type": "annotation_term"},
            "paths": [{"source_type": "protein", "rel_type": "HAS_ANNOTATION", "target_type": "annotation_term"}],
            "filters": filters,
            "aggregations": [{"type": "count_distinct", "over": "owner_entities", "alias": "annotated_entity_count"}],
            "dimensions": {"limit": limit},
            "evidence": {"include": ["annotated_entity_count", "annotation_namespace", "annotation_category"]},
            "presentation": {"prefer_summary": summary_style == "explanatory", "prefer_table": summary_style != "explanatory", "summary_style": summary_style},
            "requested_result_kind": self._summary_result_kind_for_style(summary_style, default="ranked_rows"),
        }

    def _compile_common_functional_annotation_terms_analysis(
        self,
        _chat,
        analysis: dict[str, Any],
    ) -> str | dict[str, Any] | None:
        filters = list(analysis.get("filters", []) or [])
        limit = analysis.get("dimensions", {}).get("limit")
        where_lines = ["WHERE e.type = 'annotation_term'"]
        for item in filters:
            if str(item.get("type", "") or "") != "metadata_filter":
                continue
            field = str(item.get("field", "") or "").strip()
            value = str(item.get("value", "") or "").strip()
            if field and value:
                where_lines.append(f"  AND json_extract(e.metadata, '$.{field}') = '{self._sql_literal(value)}'")
        aggregation_columns = self._count_distinct_aggregation_columns(
            [dict(item) for item in list(analysis.get("aggregations", []) or []) if isinstance(item, dict)]
        )
        if len(aggregation_columns) != 1:
            return None
        evidence_columns = [
            *aggregation_columns,
            *self._ranked_result_extra_evidence_columns(analysis),
        ]
        order_by = self._ranked_result_order_by(
            analysis,
            fallback=["annotated_entity_count DESC", "e.name ASC"],
        )
        lines = [
            self._select_clause_with_evidence(evidence_columns),
            "FROM entities e",
            "JOIN relationships ha ON ha.target_id = e.id AND ha.rel_type = 'HAS_ANNOTATION'",
            "JOIN entities owner ON owner.id = ha.source_id",
            *where_lines,
            "GROUP BY e.id, e.name, e.type",
            f"ORDER BY {', '.join(order_by)}",
        ]
        if limit:
            lines.append(f"LIMIT {int(limit)}")
        rendered_sql = "\n".join(lines)
        if str(analysis.get("requested_result_kind", "") or "") == "narrative":
            return self._ranked_summary_answer(
                _chat,
                analysis,
                sql=rendered_sql,
                semantic_kind="common_functional_annotation_terms",
                trace_fields={},
                artifact_metadata={"subject_type": "annotation term"},
            )
        return self._analysis_synthesis_result(
            rendered_sql,
            analysis=analysis,
            evidence_columns=evidence_columns,
            semantic_trace=self._analysis_trace("common_functional_annotation_terms", analysis),
        )

    def _requests_common_promoted_entity_terms(self, message: str, requested_types: list[str]) -> dict[str, Any] | None:
        if not self._matcher_has_any_cue(message, "common_ranking"):
            return None
        requested = set(requested_types)
        for spec in self._common_promoted_entity_specs():
            if spec["result_type"] == "annotation_term":
                continue
            if spec["result_type"] in requested:
                return dict(spec)
        return None

    def _analysis_for_common_promoted_entity_terms(
        self,
        chat,
        message: str,
        requested_types: list[str],
    ) -> dict[str, Any] | None:
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
        summary_style = self._summary_style_for_message(message)
        filters: list[dict[str, str]] = []
        category = str(spec.get("category", "") or "").strip()
        if category:
            filters.append({"type": "metadata_filter", "field": "category", "value": category})
        return {
            "analysis_kind": "common_promoted_entity_terms",
            "domain": "genomics",
            "intent": "rank",
            "requested_result_kind": "ranked_rows",
            "subject": {"entity_type": result_type},
            "paths": [{"source_type": "protein", "rel_type": rel_type, "target_type": result_type}],
            "filters": filters,
            "aggregations": [{"type": "count_distinct", "over": "owner_entities", "alias": count_alias}],
            "dimensions": {"limit": limit},
            "evidence": {"include": [count_alias, "call_category", "source_column"]},
            "presentation": {"prefer_summary": summary_style == "explanatory", "prefer_table": summary_style != "explanatory", "summary_style": summary_style},
            "requested_result_kind": self._summary_result_kind_for_style(summary_style, default="ranked_rows"),
        }

    def _compile_common_promoted_entity_terms_analysis(
        self,
        _chat,
        analysis: dict[str, Any],
    ) -> str | dict[str, Any] | None:
        subject = analysis.get("subject", {}) if isinstance(analysis.get("subject"), dict) else {}
        paths = list(analysis.get("paths", []) or [])
        aggregations = list(analysis.get("aggregations", []) or [])
        dimensions = analysis.get("dimensions", {}) if isinstance(analysis.get("dimensions"), dict) else {}
        if not paths or not aggregations:
            return None
        path = dict(paths[0] or {})
        aggregation = dict(aggregations[0] or {})
        rel_type = str(path.get("rel_type", "") or "")
        result_type = str(subject.get("entity_type", "") or path.get("target_type", "") or "")
        count_alias = str(aggregation.get("alias", "assigned_entity_count") or "assigned_entity_count")
        limit = dimensions.get("limit")
        where_lines = [f"WHERE e.type = '{self._sql_literal(result_type)}'"]
        for item in list(analysis.get("filters", []) or []):
            if str(item.get("type", "") or "") != "metadata_filter":
                continue
            field = str(item.get("field", "") or "").strip()
            value = str(item.get("value", "") or "").strip()
            if field and value:
                where_lines.append(f"  AND json_extract(e.metadata, '$.{field}') = '{self._sql_literal(value)}'")
        aggregation_columns = self._count_distinct_aggregation_columns([aggregation])
        if len(aggregation_columns) != 1:
            return None
        evidence_columns = [
            *aggregation_columns,
            *self._ranked_result_extra_evidence_columns(analysis, context={"count_alias": count_alias}),
        ]
        order_by = self._ranked_result_order_by(
            analysis,
            fallback=[f"{count_alias} DESC", "e.name ASC"],
            context={"count_alias": count_alias},
        )
        lines = [
            self._select_clause_with_evidence(evidence_columns),
            "FROM entities e",
            f"JOIN relationships pr ON pr.target_id = e.id AND pr.rel_type = '{self._sql_literal(rel_type)}'",
            "JOIN entities owner ON owner.id = pr.source_id",
            *where_lines,
            "GROUP BY e.id, e.name, e.type",
            f"ORDER BY {', '.join(order_by)}",
        ]
        if limit:
            lines.append(f"LIMIT {int(limit)}")
        rendered_sql = "\n".join(lines)
        if str(analysis.get("requested_result_kind", "") or "") == "narrative":
            return self._ranked_summary_answer(
                chat,
                analysis,
                sql=rendered_sql,
                semantic_kind="common_promoted_entity_terms",
                trace_fields={"result_type": result_type, "rel_type": rel_type},
                artifact_metadata={"subject_type": result_type, "count_alias": count_alias},
            )
        return self._analysis_synthesis_result(
            rendered_sql,
            analysis=analysis,
            evidence_columns=evidence_columns,
            semantic_trace=self._analysis_trace("common_promoted_entity_terms", analysis, result_type=result_type, rel_type=rel_type),
        )

    def _analysis_for_expression_ranking(self, chat, message: str, requested_types: list[str]) -> dict[str, Any] | None:
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
        requested_measure = self._requested_expression_measure(chat, message)
        if not requested_measure:
            return None
        summary_style = self._summary_style_for_message(message)
        return {
            "analysis_kind": "expression_ranking",
            "domain": "genomics",
            "intent": "rank",
            "requested_result_kind": self._summary_result_kind_for_style(summary_style, default="ranked_rows"),
            "subject": {"entity_type": requested_type},
            "paths": [{"source_type": requested_type, "target_type": "transcript"}],
            "filters": [requested_measure],
            "aggregations": [{
                "type": "order_by_numeric_field",
                "field": str(requested_measure.get("source_column", "") or ""),
                "direction": direction,
            }],
            "dimensions": {"limit": limit},
            "evidence": {"include": ["expression_condition", "expression_value"]},
            "owner_type": "transcript",
            "presentation": {"prefer_summary": summary_style == "explanatory", "prefer_table": summary_style != "explanatory", "summary_style": summary_style},
        }

    def _analysis_for_expression_distribution(self, chat, message: str, requested_types: list[str]) -> dict[str, Any] | None:
        low = f" {str(message or '').lower()} "
        if " expression " not in low:
            return None
        if " distribution " not in low and " distributed " not in low:
            return None
        requested_measure = self._requested_expression_measure(chat, message)
        if not requested_measure:
            return None
        requested_type = self._requested_core_type(requested_types) or "transcript"
        subset_ids = self._requested_entity_subset_ids(chat, message, [requested_type, "transcript"])
        summary_style = self._summary_style_for_message(message)
        return {
            "analysis_kind": "expression_distribution",
            "domain": "genomics",
            "intent": "aggregate",
            "requested_result_kind": self._summary_result_kind_for_style(summary_style, default="distribution"),
            "subject": {"entity_type": requested_type},
            "paths": [{"source_type": requested_type, "target_type": "transcript"}],
            "filters": [requested_measure],
            "subset": {"entity_ids": subset_ids, "allowed_types": [requested_type, "transcript"]} if subset_ids else {},
            "aggregations": [{"type": "distribution_summary", "summary_id": "expression_numeric"}],
            "evidence": {"include": ["expression_condition", *self._distribution_summary_evidence_fields("expression_numeric")]},
            "owner_type": "transcript",
            "execution": {"preferred_engine": "python", "requires_live_schema": True},
            "presentation": {"prefer_summary": True, "prefer_table": False, "summary_style": summary_style},
        }

    def _analysis_for_expression_comparison(self, chat, message: str, requested_types: list[str]) -> dict[str, Any] | None:
        low = f" {str(message or '').lower()} "
        if " expression " not in low:
            return None
        if not any(token in low for token in (" compare ", " comparison ", " versus ", " vs ", " difference ")):
            return None
        requested_measures = self._requested_expression_measures(chat, message)
        unique_measures: list[dict[str, Any]] = []
        seen_measure_ids: set[str] = set()
        for measure in requested_measures:
            measure_id = str(measure.get("entity_id", "") or "")
            if not measure_id or measure_id in seen_measure_ids:
                continue
            seen_measure_ids.add(measure_id)
            unique_measures.append(dict(measure))
        if len(unique_measures) < 2:
            return None
        requested_type = self._requested_core_type(requested_types) or "transcript"
        subset_ids = self._requested_entity_subset_ids(chat, message, [requested_type, "transcript"])
        summary_style = self._summary_style_for_message(message, default="comparative")
        return {
            "analysis_kind": "expression_comparison",
            "domain": "genomics",
            "intent": "compare",
            "requested_result_kind": self._summary_result_kind_for_style(summary_style, default="comparison"),
            "subject": {"entity_type": requested_type},
            "paths": [{"source_type": requested_type, "target_type": "transcript"}],
            "filters": unique_measures[:2],
            "subset": {"entity_ids": subset_ids, "allowed_types": [requested_type, "transcript"]} if subset_ids else {},
            "aggregations": [{"type": "comparison_summary", "comparison_id": "expression_numeric"}],
            "evidence": {"include": self._comparison_evidence_fields("expression_numeric")},
            "owner_type": "transcript",
            "execution": {"preferred_engine": "python", "requires_live_schema": True},
            "presentation": {"prefer_summary": True, "prefer_table": False, "summary_style": summary_style},
        }

    def _analysis_for_expression_stats(self, chat, message: str, requested_types: list[str]) -> dict[str, Any] | None:
        low = f" {str(message or '').lower()} "
        if " expression " not in low:
            return None
        metric_type = ""
        percentile_value: int | None = None
        if " average " in low or " mean " in low:
            metric_type = "average"
        elif " minimum " in low or " min " in low or " lowest " in low:
            metric_type = "min"
        elif " maximum " in low or " max " in low:
            metric_type = "max"
        else:
            percentile_match = re.search(r"\b(\d{1,2}|100)(?:st|nd|rd|th)?\s+percentile\b", low)
            if percentile_match:
                percentile_value = int(percentile_match.group(1))
                metric_type = "percentile"
        if not metric_type:
            return None
        requested_type = self._requested_core_type(requested_types) or "transcript"
        requested_measure = self._requested_expression_measure(chat, message)
        if not requested_measure:
            return None
        subset_ids = self._requested_entity_subset_ids(chat, message, [requested_type, "transcript"])
        summary_style = self._summary_style_for_message(message)
        return {
            "analysis_kind": "expression_stats",
            "domain": "genomics",
            "intent": "aggregate",
            "requested_result_kind": self._summary_result_kind_for_style(summary_style, default="scalar"),
            "subject": {"entity_type": requested_type},
            "paths": [{"source_type": requested_type, "target_type": "transcript"}],
            "filters": [requested_measure],
            "subset": {"entity_ids": subset_ids, "allowed_types": [requested_type, "transcript"]} if subset_ids else {},
            "aggregations": [{
                "type": metric_type,
                "field": str(requested_measure.get("source_column", "") or ""),
                "percentile": percentile_value,
            }],
            "evidence": {"include": ["expression_condition", "stat_value", "subject_count"]},
            "owner_type": "transcript",
            "presentation": {"prefer_summary": True, "prefer_table": False, "summary_style": summary_style},
        }

    @staticmethod
    def _percentile_linear(values: list[float], percentile: int) -> float | None:
        if not values:
            return None
        ordered = sorted(values)
        if len(ordered) == 1:
            return float(ordered[0])
        rank = (len(ordered) - 1) * (percentile / 100.0)
        lower = int(math.floor(rank))
        upper = int(math.ceil(rank))
        if lower == upper:
            return float(ordered[lower])
        weight = rank - lower
        return float(ordered[lower] * (1 - weight) + ordered[upper] * weight)

    def _compute_numeric_aggregation(self, values: list[float], aggregation: dict[str, Any]) -> tuple[float | None, str]:
        metric_type = str(aggregation.get("type", "") or "")
        if not values or not metric_type:
            return None, metric_type
        spec = self._numeric_scalar_aggregation_spec(metric_type)
        if metric_type == "average":
            return float(sum(values) / len(values)), str(spec.get("metric_label", "average") or "average")
        if metric_type == "percentile":
            percentile_num = int(aggregation.get("percentile", 0) or 0)
            label_template = str(spec.get("metric_label_template", "{percentile}th percentile") or "{percentile}th percentile")
            metric_label = label_template.format(percentile=percentile_num)
            return self._percentile_linear(values, percentile_num), metric_label
        if metric_type == "min":
            return float(min(values)), str(spec.get("metric_label", "minimum") or "minimum")
        if metric_type == "max":
            return float(max(values)), str(spec.get("metric_label", "maximum") or "maximum")
        return None, metric_type

    def _requested_expression_measures(self, chat, message: str) -> list[dict[str, Any]]:
        low = f" {str(message or '').lower()} "
        rows = chat.db.execute_read("SELECT id, name, metadata FROM entities WHERE type = 'expression_measure' ORDER BY id")
        matched: list[dict[str, Any]] = []
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
            matched.append({
                "type": "expression_measure",
                "entity_id": expr_id,
                "label": label,
                "source_column": source_column,
            })
        return matched

    def _requested_expression_measure(self, chat, message: str) -> dict[str, Any] | None:
        matched = self._requested_expression_measures(chat, message)
        return dict(matched[0]) if matched else None

    def _expression_value_rows(
        self,
        chat,
        analysis: dict[str, Any],
    ) -> tuple[list[float], str, str, str, str, str] | None:
        requested_type = str(analysis.get("subject", {}).get("entity_type", "") or "")
        owner_type = str(analysis.get("owner_type", "") or "")
        filters = list(analysis.get("filters", []) or [])
        subset = analysis.get("subset", {}) if isinstance(analysis.get("subset"), dict) else {}
        expr_filter = next((dict(item) for item in filters if str(item.get("type", "") or "") == "expression_measure"), {})
        expr_id = str(expr_filter.get("entity_id", "") or "")
        expr_label = str(expr_filter.get("label", "") or expr_id)
        source_column = str(expr_filter.get("source_column", "") or "")
        if not requested_type or not owner_type or not expr_id or not source_column:
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
        joins.append(f"JOIN entities expr ON expr.id = ex.target_id AND expr.type = 'expression_measure' AND expr.id = '{self._sql_literal(expr_id)}'")
        sql = "\n".join([
            f"SELECT CAST(json_extract(owner.metadata, '$.{self._sql_literal(source_column)}') AS REAL) AS expression_value",
            "FROM entities e",
            *joins,
            f"WHERE e.type = '{requested_type}'",
            f"  AND json_extract(owner.metadata, '$.{self._sql_literal(source_column)}') IS NOT NULL",
        ])
        subset_ids = [str(item) for item in list(subset.get("entity_ids", []) or []) if str(item).strip()]
        if subset_ids:
            subset_list = ", ".join(f"'{self._sql_literal(item)}'" for item in subset_ids)
            sql += f"\n  AND (e.id IN ({subset_list}) OR owner.id IN ({subset_list}))"
        rows = chat.db.execute_read(sql)
        values = [float(row["expression_value"]) for row in rows if row.get("expression_value") is not None]
        return values, sql, expr_id, expr_label, source_column, requested_type

    def _compute_distribution_summary_row(self, values: list[float], summary_id: str) -> dict[str, Any] | None:
        spec = self._distribution_summary_spec(summary_id)
        metrics = [dict(item) for item in list(spec.get("metrics", []) or []) if isinstance(item, dict)]
        if not metrics:
            return None
        row: dict[str, Any] = {}
        for metric in metrics:
            alias = str(metric.get("alias", "") or "").strip()
            metric_type = str(metric.get("type", "") or "").strip()
            if not alias or not metric_type:
                continue
            if metric_type == "count":
                row[alias] = len(values)
                continue
            value, _metric_label = self._compute_numeric_aggregation(values, metric)
            if value is None:
                continue
            row[alias] = round(float(value), 6)
        return row if row else None

    def _compute_comparison_summary_row(
        self,
        left_values: list[float],
        right_values: list[float],
        comparison_id: str,
    ) -> dict[str, Any] | None:
        spec = self._comparison_spec(comparison_id)
        metrics = self._comparison_metrics(comparison_id)
        if not metrics:
            return None
        row: dict[str, Any] = {}
        metric_values: dict[str, tuple[float, float]] = {}
        for metric in metrics:
            metric_type = str(metric.get("type", "") or "").strip()
            metric_alias = str(metric.get("alias", "metric_value") or "metric_value").strip()
            if not metric_type or not metric_alias:
                continue
            left_value, _left_label = self._compute_numeric_aggregation(left_values, {"type": metric_type, **metric})
            right_value, _right_label = self._compute_numeric_aggregation(right_values, {"type": metric_type, **metric})
            if left_value is None or right_value is None:
                return None
            left_value = round(float(left_value), 6)
            right_value = round(float(right_value), 6)
            row[f"{metric_alias}_left"] = left_value
            row[f"{metric_alias}_right"] = right_value
            metric_values[metric_alias] = (left_value, right_value)
        if not metric_values:
            return None
        comparison_metric_alias = str(spec.get("difference_metric_alias", "") or "").strip() or next(iter(metric_values))
        left_metric, right_metric = metric_values.get(comparison_metric_alias, next(iter(metric_values.values())))
        difference_alias = str(spec.get("difference_alias", "difference") or "difference").strip()
        difference_direction = str(spec.get("difference_direction", "left_minus_right") or "left_minus_right").strip()
        difference_value = right_metric - left_metric if difference_direction == "right_minus_left" else left_metric - right_metric
        row[difference_alias] = round(float(difference_value), 6)
        row["_comparison_metric_alias"] = comparison_metric_alias
        return row

    @staticmethod
    def _distribution_summary_text(row: dict[str, Any]) -> str:
        labels = [
            ("minimum", "min"),
            ("first_quartile", "q1"),
            ("median", "median"),
            ("average", "average"),
            ("third_quartile", "q3"),
            ("maximum", "max"),
        ]
        parts = [f"{label} {row[key]}" for key, label in labels if key in row]
        used_keys = {key for key, _label in labels if key in row}
        base_keys = {"expression_condition", "subject_type", "subject_count", "subset_count"}
        for key, value in row.items():
            if key in used_keys or key in base_keys:
                continue
            parts.append(f"{key} {value}")
        return ", ".join(parts)

    def _measure_analysis_context(
        self,
        chat,
        analysis: dict[str, Any],
    ) -> dict[str, Any] | None:
        values_payload = self._expression_value_rows(chat, analysis)
        if not values_payload:
            return None
        values, sql, expr_id, expr_label, source_column, requested_type = values_payload
        subset = analysis.get("subset", {}) if isinstance(analysis.get("subset"), dict) else {}
        subset_ids = [str(item) for item in list(subset.get("entity_ids", []) or []) if str(item).strip()]
        return {
            "values": values,
            "sql": sql,
            "measure_id": expr_id,
            "measure_label": expr_label,
            "source_column": source_column,
            "requested_type": requested_type,
            "subset_ids": subset_ids,
        }

    def _compute_expression_stats_analysis(self, chat, analysis: dict[str, Any]) -> dict[str, Any] | None:
        aggregations = list(analysis.get("aggregations", []) or [])
        aggregation = dict(aggregations[0] or {}) if aggregations else {}
        metric_type = str(aggregation.get("type", "") or "")
        context = self._measure_analysis_context(chat, analysis)
        if not metric_type or not context:
            return None
        values = list(context.get("values", []) or [])
        sql = str(context.get("sql", "") or "")
        expr_id = str(context.get("measure_id", "") or "")
        expr_label = str(context.get("measure_label", "") or expr_id)
        source_column = str(context.get("source_column", "") or "")
        requested_type = str(context.get("requested_type", "") or "")
        subset_ids = [str(item) for item in list(context.get("subset_ids", []) or []) if str(item).strip()]
        if not values:
            return self._answer_result(
                analysis=analysis,
                semantic_kind="expression_stats",
                content=f"No non-null expression values found for {expr_label}.",
                results=[],
                artifact_kind="scalar_summary",
                artifact_metadata={"measure_id": expr_id, "measure_label": expr_label, "empty": True},
                trace_fields={"expression_measure_id": expr_id, "source_column": source_column},
            )
        stat_value, metric_label = self._compute_numeric_aggregation(values, aggregation)
        if stat_value is None:
            return None
        rounded_value = round(stat_value, 6)
        row = {
            "metric": metric_label,
            "expression_condition": expr_label,
            "stat_value": rounded_value,
            "subject_count": len(values),
            "subject_type": requested_type,
        }
        if subset_ids:
            row["subset_count"] = len(subset_ids)
        return self._answer_result(
            analysis=analysis,
            semantic_kind="expression_stats",
            results=[row],
            sql=sql,
            artifact_kind="scalar_summary",
            artifact_metadata={"measure_id": expr_id, "measure_label": expr_label, "metric": metric_label},
            trace_fields={"expression_measure_id": expr_id, "source_column": source_column, "metric": metric_label},
        )

    def _compute_expression_distribution_analysis(self, chat, analysis: dict[str, Any]) -> dict[str, Any] | None:
        aggregations = list(analysis.get("aggregations", []) or [])
        aggregation = dict(aggregations[0] or {}) if aggregations else {}
        summary_id = str(aggregation.get("summary_id", "") or "")
        context = self._measure_analysis_context(chat, analysis)
        if not summary_id or not context:
            return None
        values = list(context.get("values", []) or [])
        sql = str(context.get("sql", "") or "")
        expr_id = str(context.get("measure_id", "") or "")
        expr_label = str(context.get("measure_label", "") or expr_id)
        source_column = str(context.get("source_column", "") or "")
        requested_type = str(context.get("requested_type", "") or "")
        subset_ids = [str(item) for item in list(context.get("subset_ids", []) or []) if str(item).strip()]
        if not values:
            return self._answer_result(
                analysis=analysis,
                semantic_kind="expression_distribution",
                content=f"No non-null expression values found for {expr_label}.",
                results=[],
                artifact_kind="distribution_summary",
                artifact_metadata={"measure_id": expr_id, "measure_label": expr_label, "summary_id": summary_id, "empty": True},
                trace_fields={"expression_measure_id": expr_id, "source_column": source_column},
            )
        row = self._compute_distribution_summary_row(values, summary_id)
        if not row:
            return None
        row["expression_condition"] = expr_label
        row["subject_type"] = requested_type
        if subset_ids:
            row["subset_count"] = len(subset_ids)
        return self._answer_result(
            analysis=analysis,
            semantic_kind="expression_distribution",
            results=[row],
            sql=sql,
            artifact_kind="distribution_summary",
            artifact_metadata={"measure_id": expr_id, "measure_label": expr_label, "summary_id": summary_id},
            trace_fields={"expression_measure_id": expr_id, "source_column": source_column, "summary_id": summary_id},
        )

    def _compute_expression_comparison_analysis(self, chat, analysis: dict[str, Any]) -> dict[str, Any] | None:
        aggregations = list(analysis.get("aggregations", []) or [])
        aggregation = dict(aggregations[0] or {}) if aggregations else {}
        comparison_id = str(aggregation.get("comparison_id", "") or "")
        filters = [dict(item) for item in list(analysis.get("filters", []) or []) if isinstance(item, dict)]
        spec = self._comparison_spec(comparison_id)
        difference_alias = str(spec.get("difference_alias", "difference") or "difference")
        higher_condition_alias = str(spec.get("higher_condition_alias", "higher_condition") or "higher_condition")
        if len(filters) < 2 or not comparison_id or not self._comparison_metrics(comparison_id):
            return None
        left_analysis = dict(analysis)
        left_analysis["filters"] = [filters[0]]
        right_analysis = dict(analysis)
        right_analysis["filters"] = [filters[1]]
        left_context = self._measure_analysis_context(chat, left_analysis)
        right_context = self._measure_analysis_context(chat, right_analysis)
        if not left_context or not right_context:
            return None
        left_values = list(left_context.get("values", []) or [])
        right_values = list(right_context.get("values", []) or [])
        sql = str(left_context.get("sql", "") or "")
        left_expr_id = str(left_context.get("measure_id", "") or "")
        right_expr_id = str(right_context.get("measure_id", "") or "")
        left_label = str(left_context.get("measure_label", "") or left_expr_id)
        right_label = str(right_context.get("measure_label", "") or right_expr_id)
        left_source_column = str(left_context.get("source_column", "") or "")
        right_source_column = str(right_context.get("source_column", "") or "")
        requested_type = str(left_context.get("requested_type", "") or "")
        if not left_values or not right_values:
            return self._answer_result(
                analysis=analysis,
                semantic_kind="expression_comparison",
                content=f"Not enough non-null expression values were found to compare {left_label} and {right_label}.",
                results=[],
                artifact_kind="comparison_summary",
                artifact_metadata={
                    "left_measure_id": left_expr_id,
                    "right_measure_id": right_expr_id,
                    "comparison_id": comparison_id,
                    "empty": True,
                },
                trace_fields={"left_expression_measure_id": left_expr_id, "right_expression_measure_id": right_expr_id},
            )
        row = self._compute_comparison_summary_row(left_values, right_values, comparison_id)
        if not row:
            return None
        comparison_metric_alias = str(row.pop("_comparison_metric_alias", "") or "")
        left_metric_value = row.get(f"{comparison_metric_alias}_left")
        right_metric_value = row.get(f"{comparison_metric_alias}_right")
        if left_metric_value is None or right_metric_value is None:
            return None
        higher_condition = left_label if left_metric_value > right_metric_value else right_label if right_metric_value > left_metric_value else "equal"
        row = {
            "left_condition": left_label,
            "right_condition": right_label,
            higher_condition_alias: higher_condition,
            "subject_type": requested_type,
            "left_subject_count": len(left_values),
            "right_subject_count": len(right_values),
            **row,
        }
        return self._answer_result(
            analysis=analysis,
            semantic_kind="expression_comparison",
            results=[row],
            sql=sql,
            artifact_kind="comparison_summary",
            artifact_metadata={
                "left_measure_id": left_expr_id,
                "right_measure_id": right_expr_id,
                "comparison_id": comparison_id,
            },
            trace_fields={
                "left_expression_measure_id": left_expr_id,
                "right_expression_measure_id": right_expr_id,
                "left_source_column": left_source_column,
                "right_source_column": right_source_column,
                "comparison_id": comparison_id,
            },
        )

    def _analysis_for_broad_homology_organism_tag_results(
        self,
        chat,
        message: str,
        requested_types: list[str],
    ) -> dict[str, Any] | None:
        available_types = [row["type"] for row in chat.db.entity_types()]
        if "tag" not in requested_types or not self._requests_broad_homology_organism_tags(message, available_types):
            return None
        return {
            "analysis_kind": "broad_homology_organism_tag_results",
            "domain": "genomics",
            "intent": "filter",
            "requested_result_kind": "entity_rows",
            "subject": {"entity_type": "tag"},
            "filters": [
                {
                    "type": "tag_branch_filter",
                    "root_tag_id": "homology-organism",
                    "tag_id_like": "homology-organism:%",
                },
                {
                    "type": "comparative_hit_scope",
                    "scope_tag_id": "homology-scope-broad-parasitism",
                    "evidence_rel_type": "HAS_BROAD_HOMOLOGY_HIT",
                },
            ],
            "evidence": {"include": ["tag_group", "homology_scope"]},
        }

    def _compile_broad_homology_organism_tag_result_analysis(
        self,
        chat,
        analysis: dict[str, Any],
    ) -> str | dict[str, Any] | None:
        if str(analysis.get("subject", {}).get("entity_type", "") or "") != "tag":
            return None
        evidence_columns = [
            ("parent.name", "tag_group"),
            ("scope_tag.name", "homology_scope"),
        ]
        return self._analysis_synthesis_result(
            "\n".join([
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
            ]),
            analysis=analysis,
            evidence_columns=evidence_columns,
            semantic_trace=self._analysis_trace("broad_homology_organism_tags", analysis),
        )

    def _analysis_for_hgt_donor_results(self, chat, message: str, requested_types: list[str]) -> dict[str, Any] | None:
        available_types = [row["type"] for row in chat.db.entity_types()]
        if "hgt_donor" not in requested_types or not self._requests_hgt_donor_result(message, available_types):
            return None
        if self._requested_core_type(requested_types):
            return None
        if "hgt_donor" not in available_types:
            return None
        return {
            "analysis_kind": "hgt_donor_results",
            "domain": "genomics",
            "intent": "filter",
            "requested_result_kind": "entity_rows",
            "subject": {"entity_type": "hgt_donor"},
            "filters": [{"type": "relation_presence", "rel_type": "HAS_HGT_DONOR"}],
        }

    def _compile_hgt_donor_result_analysis(
        self,
        chat,
        analysis: dict[str, Any],
    ) -> str | dict[str, Any] | None:
        if str(analysis.get("subject", {}).get("entity_type", "") or "") != "hgt_donor":
            return None
        return self._analysis_synthesis_result(
            "\n".join([
                "SELECT DISTINCT e.id, e.name, e.type",
                "FROM entities e",
                "JOIN relationships r ON r.target_id = e.id AND r.rel_type = 'HAS_HGT_DONOR'",
                "WHERE e.type = 'hgt_donor'",
            ]),
            analysis=analysis,
            semantic_trace=self._analysis_trace("hgt_donor_result", analysis),
        )

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
        return [
            {"tag_id": entity_id, "name": entity_name}
            for entity_id, _entity_type, entity_name in self._matched_named_entities(chat, message, "homology_organism")
        ]

    def _requested_organism_name_matches(self, chat, message: str) -> list[str]:
        names: list[str] = []
        seen: set[str] = set()
        for _entity_id, _entity_type, entity_name in self._matched_named_entities(chat, message, "organism_name"):
            normalized = str(entity_name or "").strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            names.append(normalized)
        return names

    @staticmethod
    def _requested_organism_phrase_candidates(message: str) -> list[str]:
        text = str(message or "").strip()
        if not text:
            return []
        candidates: list[str] = []
        stop_words = {
            "and", "or", "with", "without", "that", "which", "where", "whose", "having",
            "has", "have", "for", "among", "between", "under", "over", "top", "highest",
            "lowest", "more", "less", "than", "copies", "copy", "ortholog", "orthologs",
            "gene", "genes", "protein", "proteins", "transcript", "transcripts",
        }
        patterns = [r"\bfrom\s+([^,.;:!?]+)", r"\bin\s+([^,.;:!?]+)"]
        for pattern in patterns:
            for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                raw = str(match.group(1) or "").strip(" ,.;:!?")
                if not raw:
                    continue
                tokens = re.findall(r"[A-Za-z0-9_.-]+", raw)
                phrase_tokens: list[str] = []
                for token in tokens:
                    if phrase_tokens and token.lower() in stop_words:
                        break
                    phrase_tokens.append(token)
                    if len(phrase_tokens) >= 5:
                        break
                phrase = " ".join(phrase_tokens).strip(" ,.;:!?")
                if phrase and len(phrase.split()) >= 2:
                    candidates.append(phrase)
        seen: set[str] = set()
        ordered: list[str] = []
        for item in candidates:
            key = item.lower()
            if key in seen:
                continue
            seen.add(key)
            ordered.append(item)
        return ordered

    def _requested_entity_subset_ids(
        self,
        chat,
        message: str,
        allowed_types: list[str],
    ) -> list[str]:
        allowed = {str(item) for item in allowed_types if str(item).strip()}
        if not allowed:
            return []
        if not self._matcher_has_any_cue(message, "entity_subset"):
            return []
        ids: list[str] = []
        seen: set[str] = set()
        for entity_id, _entity_type, _entity_name in self._matched_named_entities(
            chat,
            message,
            "entity_subset",
            allowed_types=sorted(allowed),
        ):
            if entity_id in seen:
                continue
            seen.add(entity_id)
            ids.append(entity_id)
        low = f" {str(message or '').lower()} "
        if len(ids) < 2 and " between " not in low and "," not in low and " and " not in low:
            return []
        return ids

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
            spec["display"] = self._effector_display_specs(spec, self._registry_dynamic_family("effector_evidence"))
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
    def _effector_display_specs(spec: dict[str, Any], family: dict[str, Any]) -> list[dict[str, str]]:
        display_config = family.get("display", {}) if isinstance(family, dict) else {}
        rules = list(display_config.get("rules", []) or []) if isinstance(display_config, dict) else []
        display: list[dict[str, str]] = []
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            required_all = [str(item) for item in list(rule.get("require_all_flags", []) or []) if str(item).strip()]
            required_any = [str(item) for item in list(rule.get("require_any_flags", []) or []) if str(item).strip()]
            blocked = [str(item) for item in list(rule.get("exclude_flags", []) or []) if str(item).strip()]
            if required_all and not all(spec.get(f"is_{flag_name}") for flag_name in required_all):
                continue
            if required_any and not any(spec.get(f"is_{flag_name}") for flag_name in required_any):
                continue
            if blocked and any(spec.get(f"is_{flag_name}") for flag_name in blocked):
                continue
            alias = str(rule.get("alias", "") or "").strip()
            metadata_field = str(rule.get("metadata_field", "") or "").strip()
            if not alias or not metadata_field:
                continue
            display.append({
                "alias": alias,
                "expr_template": f"(SELECT json_extract(o.metadata, '$.{metadata_field}') FROM entities o WHERE o.id = {{owner_ref}})",
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
        config = self._scope_tag_source_config()
        root_tag_id = str(config.get("root_tag_id", self._HOMOLOGY_SCOPE_ROOT) or self._HOMOLOGY_SCOPE_ROOT)
        hierarchy_rel_type = str(config.get("hierarchy_rel_type", "BROADER") or "BROADER")
        fallback_tag_id_pattern = str(config.get("fallback_tag_id_pattern", "homology-scope-%") or "homology-scope-%")
        branch_ids = chat.db._ordered_branch_ids(root_tag_id, hierarchy_edge=hierarchy_rel_type)
        if branch_ids == [root_tag_id] and not chat.db.get_entity(root_tag_id):
            rows = chat.db.execute_read(
                "SELECT id, name FROM entities WHERE type = 'tag' AND id LIKE ? ORDER BY id",
                (fallback_tag_id_pattern,),
            )
            return [(row["id"], row.get("name", row["id"])) for row in rows]
        branch: list[tuple[str, str]] = []
        for tag_id in branch_ids:
            entity = chat.db.get_entity(tag_id)
            if not entity or entity.get("type") != "tag" or entity.get("id") == root_tag_id:
                continue
            branch.append((entity["id"], entity.get("name", entity["id"])))
        return branch

    def _parser_message_eligibility(self, message: str, parser: dict[str, Any]) -> bool:
        low = f" {str(message or '').lower()} "
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
            return False
        if blocked and not has_required_cue:
            return False
        return True

    def _requested_scope_tag_ids(self, chat, message: str) -> list[str]:
        scope_tags = self._registry_operators().get("scope_tags", {}) if isinstance(self._registry_operators(), dict) else {}
        parser_kind = ""
        for operator in scope_tags.values() if isinstance(scope_tags, dict) else []:
            if isinstance(operator, dict) and operator.get("parser_kind"):
                parser_kind = str(operator.get("parser_kind", "") or "")
                break
        parser = self._condition_parser(parser_kind)
        if not self._parser_message_eligibility(message, parser):
            return []
        found = [
            str(tag_id)
            for tag_id, _tag_name in self._matched_items_by_aliases(
                message,
                list(self._homology_scope_branch(chat) or []),
                alias_getter=lambda item: self._scope_aliases_for_tag(str(item[0]), str(item[1])),
                key_getter=lambda item: str(item[0]),
            )
        ]

        pruned: list[str] = []
        found_set = set(found)
        for tag_id in found:
            descendants = chat.db._descendant_ids(tag_id, hierarchy_edge="BROADER")
            if any(descendant in found_set for descendant in descendants):
                continue
            pruned.append(tag_id)
        return pruned

    def _matched_protein_evidence_conditions(self, message: str) -> list[dict[str, Any]]:
        return self._matched_relation_family_conditions(
            message,
            family_id="protein_evidence",
            kind="protein_evidence",
            build_condition=lambda spec: {
                **spec,
                "owner_types": [str(spec.get("owner_type", "protein") or "protein")],
            },
        )

    def _matched_dynamic_family_conditions(self, chat, message: str, family_id: str) -> list[dict[str, Any]]:
        family = self._registry_dynamic_family(family_id)
        condition_kind = str((family.get("output", {}) or {}).get("condition_kind", "tag_evidence") or "tag_evidence")
        specs = self._dynamic_family_specs(chat, family_id)
        if family_id == "effector_evidence":
            for spec in specs:
                spec["display"] = self._effector_display_specs(spec, family)
        matched_groups = self._matched_dynamic_family_alias_groups(
            message,
            specs,
            family=family,
        )
        for group_name in self._dynamic_family_match_group_names(family):
            group_conditions = [
                {"kind": condition_kind, **spec}
                for spec in list(matched_groups.get(group_name, []) or [])
                if isinstance(spec, dict)
            ]
            if not group_conditions:
                continue
            if group_name == "generic_aliases":
                return self._collapse_generic_effector_conditions(
                    message,
                    group_conditions,
                    family=family,
                )
            return group_conditions
        return []

    def _matched_effector_tag_conditions(self, chat, message: str) -> list[dict[str, Any]]:
        return self._matched_dynamic_family_conditions(chat, message, "effector_evidence")

    @staticmethod
    def _dynamic_family_match_group_names(family: dict[str, Any]) -> list[str]:
        selection = family.get("selection", {}) if isinstance(family, dict) else {}
        groups = [str(item) for item in list(selection.get("match_groups", []) or []) if str(item).strip()]
        return groups or ["primary_scoped_aliases", "secondary_scoped_aliases", "generic_aliases"]

    @classmethod
    def _matched_dynamic_family_alias_groups(
        cls,
        message: str,
        specs: list[dict[str, Any]],
        *,
        family: dict[str, Any],
    ) -> dict[str, list[dict[str, Any]]]:
        selection = family.get("selection", {}) if isinstance(family, dict) else {}
        stop_at_first = bool(selection.get("stop_at_first_nonempty_group", True))
        matched: dict[str, list[dict[str, Any]]] = {}
        for group_name in cls._dynamic_family_match_group_names(family):
            group_matches = [
                dict(spec)
                for spec in specs
                if isinstance(spec, dict) and cls._message_matches_aliases(message, list(spec.get(group_name, []) or []))
            ]
            if group_matches:
                matched[group_name] = group_matches
                if stop_at_first:
                    break
        return matched

    @staticmethod
    def _dynamic_family_flag_match_map(family: dict[str, Any]) -> dict[str, list[str]]:
        collapse = family.get("collapse", {}) if isinstance(family, dict) else {}
        if isinstance(collapse.get("family_flag_matches"), dict):
            return {
                str(family_name): [str(item) for item in list(values or []) if str(item).strip()]
                for family_name, values in dict(collapse.get("family_flag_matches", {}) or {}).items()
            }
        scoped_templates = family.get("alias_templates", {}).get("organism_scoped", {}) if isinstance(family, dict) else {}
        template_flag_matches = scoped_templates.get("template_flag_matches", {}) if isinstance(scoped_templates, dict) else {}
        if isinstance(template_flag_matches, dict):
            return {
                str(family_name): [str(item) for item in list(values or []) if str(item).strip()]
                for family_name, values in template_flag_matches.items()
            }
        return {}

    @staticmethod
    def _dynamic_family_condition_matches_flags(cond: dict[str, Any], match_flags: list[str]) -> bool:
        return any(cond.get(f"is_{flag_name}") for flag_name in list(match_flags or []) if str(flag_name).strip())

    @classmethod
    def _dynamic_family_message_family(cls, message: str, family: dict[str, Any]) -> str:
        collapse = family.get("collapse", {}) if isinstance(family, dict) else {}
        low = f" {str(message or '').lower()} "
        when_message_contains = collapse.get("when_message_contains", {}) if isinstance(collapse, dict) else {}
        if not isinstance(when_message_contains, dict):
            return ""
        for family_name, phrases in when_message_contains.items():
            if any(str(phrase) in low for phrase in list(phrases or []) if str(phrase).strip()):
                return str(family_name)
        return ""

    @classmethod
    def _dynamic_family_condition_family(cls, message: str, cond: dict[str, Any], family: dict[str, Any]) -> str:
        collapse = family.get("collapse", {}) if isinstance(family, dict) else {}
        match_map = cls._dynamic_family_flag_match_map(family)
        message_family = cls._dynamic_family_message_family(message, family)
        if message_family:
            match_flags = match_map.get(message_family, [message_family])
            if cls._dynamic_family_condition_matches_flags(cond, match_flags):
                return message_family
        fallback_precedence = [str(item) for item in list(collapse.get("fallback_precedence", []) or []) if str(item).strip()]
        for family_name in fallback_precedence:
            match_flags = match_map.get(family_name, [family_name])
            if cls._dynamic_family_condition_matches_flags(cond, match_flags):
                return family_name
        return str(cond.get("id", "") or "")

    def _metadata_filter_query(
        self,
        chat,
        requested_type: str,
        filters: list[dict[str, Any]],
    ) -> tuple[str, list[tuple[str, str]]] | None:
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
        return rendered_sql, evidence_columns

    def _compile_metadata_filter_analysis(
        self,
        chat,
        analysis: dict[str, Any],
    ) -> str | dict[str, Any] | None:
        requested_type = str(analysis.get("subject", {}).get("entity_type", "") or "")
        filters = [dict(item) for item in list(analysis.get("filters", []) or []) if isinstance(item, dict)]
        if not requested_type or not filters:
            return None
        rendered = self._metadata_filter_query(chat, requested_type, filters)
        if not rendered:
            return None
        rendered_sql, evidence_columns = rendered
        return self._analysis_synthesis_result(
            rendered_sql,
            analysis=analysis,
            evidence_columns=evidence_columns,
            semantic_trace=self._analysis_trace(
                "genomics_metadata_filters",
                analysis,
                requested_type=requested_type,
                filter_fields=[str(item.get("field", "") or "") for item in filters],
            ),
        )

    def _compile_expression_ranking_analysis(self, chat, analysis: dict[str, Any]) -> str | dict[str, Any] | None:
        requested_type = str(analysis.get("subject", {}).get("entity_type", "") or "")
        owner_type = str(analysis.get("owner_type", "") or "")
        filters = list(analysis.get("filters", []) or [])
        dimensions = analysis.get("dimensions", {}) if isinstance(analysis.get("dimensions"), dict) else {}
        aggregations = list(analysis.get("aggregations", []) or [])
        expr_filter = next((dict(item) for item in filters if str(item.get("type", "") or "") == "expression_measure"), {})
        aggregation = dict(aggregations[0] or {}) if aggregations else {}
        expr_id = self._sql_literal(str(expr_filter.get("entity_id", "") or ""))
        source_column = self._sql_literal(str(expr_filter.get("source_column", "") or ""))
        direction = "DESC" if str(aggregation.get("direction", "DESC") or "DESC").upper() == "DESC" else "ASC"
        limit = int(dimensions.get("limit", 0) or 0)
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
        value_expr = self._ranked_result_value_expr(
            analysis,
            context={"source_column": source_column},
        ) or f"CAST(json_extract(owner.metadata, '$.{source_column}') AS REAL)"
        evidence_columns = self._ranked_result_extra_evidence_columns(
            analysis,
            context={"value_expr": value_expr, "direction": direction},
        )
        if len(evidence_columns) != 2:
            return None
        order_by = self._ranked_result_order_by(
            analysis,
            fallback=[f"{value_expr} {direction}"],
            context={"value_expr": value_expr, "direction": direction},
        )
        rendered_sql = "\n".join([
            self._select_clause_with_evidence(evidence_columns),
            "FROM entities e",
            *joins,
            f"WHERE e.type = '{requested_type}'",
            f"  AND json_extract(owner.metadata, '$.{source_column}') IS NOT NULL",
            f"ORDER BY {', '.join(order_by)}",
            f"LIMIT {limit}",
        ])
        if str(analysis.get("requested_result_kind", "") or "") == "narrative":
            return self._ranked_summary_answer(
                chat,
                analysis,
                sql=rendered_sql,
                semantic_kind="expression_ranking",
                trace_fields={
                    "requested_type": requested_type,
                    "expression_measure_id": str(expr_filter.get("entity_id", "") or ""),
                    "source_column": source_column,
                    "direction": direction,
                    "limit": limit,
                },
                artifact_metadata={"subject_type": requested_type, "measure_label": str(expr_filter.get("label", "") or "")},
            )
        return self._analysis_synthesis_result(
            rendered_sql,
            analysis=analysis,
            evidence_columns=evidence_columns,
            semantic_trace=self._analysis_trace(
                "expression_ranking",
                analysis,
                requested_type=requested_type,
                expression_measure_id=str(expr_filter.get("entity_id", "") or ""),
                source_column=source_column,
                direction=direction,
                limit=limit,
            ),
        )

    def _ortholog_count_strategy_error(
        self,
        chat,
        *,
        owner_type: str,
        sql_low: str,
    ) -> str | None:
        edge_rel_types, _edge_target_types = self._ortholog_member_edge_spec(chat, owner_type or "orthogroup")
        if self._owner_has_non_primary_gene_counts(chat, owner_type):
            if "gene_counts" not in sql_low or "json_each" not in sql_low:
                return (
                    "Wrong counting strategy: ortholog copy counts come from the owner entity's "
                    "`metadata.gene_counts` map, expanded with `json_each(...)`, not by counting raw edges."
                )
            return None
        if edge_rel_types:
            if not any(rel_type_name.lower() in sql_low for rel_type_name in edge_rel_types):
                return (
                    "Wrong counting strategy: ortholog copy counts in this dataset come from live ortholog-member "
                    "relationships on the orthogroup, not from a degenerate `gene_counts` map or unrelated edge counts."
                )
            return None
        if "gene_counts" not in sql_low or "json_each" not in sql_low:
            return (
                "Wrong counting strategy: ortholog copy counts come from the owner entity's "
                "`metadata.gene_counts` map, expanded with `json_each(...)`, not by counting raw edges."
            )
        return None

    @staticmethod
    def _ortholog_count_projection_error(sql_low: str) -> str | None:
        if "ortholog_copy_count" not in sql_low and "gc.value" not in sql_low and "count(" not in sql_low:
            return (
                "Missing ortholog copy-count projection: the SQL applies an ortholog copy-count filter, "
                "but the final result does not project the matched copy count."
            )
        return None

    def _matched_ortholog_member_conditions(self, message: str) -> list[dict[str, Any]]:
        return self._matched_relation_family_conditions(
            message,
            family_id="ortholog_member",
            kind="ortholog_member",
            build_condition=lambda _spec: {},
        )

    def _semantic_conditions(self, chat, message: str) -> list[dict[str, Any]]:
        return list(self._requested_condition_bundle(chat, message, []).get("conditions", []) or [])

    @classmethod
    def _collapse_generic_effector_conditions(
        cls,
        message: str,
        conditions: list[dict[str, Any]],
        *,
        family: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        family = dict(family or {})
        collapse = family.get("collapse", {}) if isinstance(family, dict) else {}
        merge_field = str(collapse.get("merge_field", "tag_ids") or "tag_ids")
        if len(conditions) <= 1:
            for cond in conditions:
                cond.setdefault("effector_family", cls._dynamic_family_condition_family(message, cond, family))
            return conditions
        grouped: dict[tuple[str, tuple[str, ...]], dict[str, Any]] = {}
        for cond in conditions:
            effector_family = cls._dynamic_family_condition_family(message, cond, family)
            owner_types = tuple(list(cond.get("owner_types", []) or ["protein"]))
            key = (effector_family, owner_types)
            if key not in grouped:
                grouped[key] = {
                    **cond,
                    "id": effector_family,
                    "effector_family": effector_family,
                    merge_field: [],
                }
            for value in list(cond.get(merge_field, []) or []):
                if value not in grouped[key][merge_field]:
                    grouped[key][merge_field].append(value)
        return list(grouped.values())

    def preferred_result_types(self, chat, message: str, available_types: list[str]) -> list[str]:
        preferred = self._preferred_result_types_from_registry(message, available_types, phase="pre_core")
        explicit_core = bool(preferred) or self._message_has_explicit_core_terms(
            message,
            [" horizontal gene transfer ", " hgt "],
        )
        if self._requests_functional_annotation_term_result(message, available_types) and not explicit_core:
            preferred.append("annotation_term")
        promoted_spec = self._requested_common_promoted_entity_spec(chat, message, available_types)
        if promoted_spec and promoted_spec["result_type"] != "annotation_term" and not explicit_core:
            preferred.append(str(promoted_spec["result_type"]))
        if not explicit_core:
            preferred.extend(self._preferred_result_types_from_registry(message, available_types, phase="post_core"))
        return preferred

    def suppressed_result_types(self, chat, message: str, available_types: list[str]) -> list[str]:
        return self._suppressed_result_types_from_registry(message, available_types)

    def _preferred_result_type_rules(self) -> list[dict[str, Any]]:
        config = self._result_type_preference_config()
        rules = config.get("prefer", []) if isinstance(config, dict) else []
        return [dict(rule) for rule in list(rules or []) if isinstance(rule, dict)]

    @staticmethod
    def _core_explicit_type_pattern() -> str:
        return r"\b(genes?|proteins?|transcripts?)\b"

    @classmethod
    def _message_has_explicit_core_terms(cls, message: str, ignored_terms: list[str] | None = None) -> bool:
        low = f" {str(message or '').lower()} "
        for term in list(ignored_terms or []) or []:
            if str(term).strip():
                low = low.replace(str(term), " ")
        return bool(re.search(cls._core_explicit_type_pattern(), low))

    def _result_type_rule_alias_groups(self, rule: dict[str, Any]) -> list[list[str]]:
        groups = [
            [str(alias) for alias in list(group or []) if str(alias).strip()]
            for group in list(rule.get("all_alias_groups", []) or [])
            if isinstance(group, list)
        ]
        if groups:
            return groups
        alias_source_operator = str(rule.get("alias_source_operator", "") or "").strip()
        if alias_source_operator:
            if alias_source_operator == "ortholog_member":
                return [self._ortholog_member_aliases()]
            operator = self._registry_operator_spec(alias_source_operator)
            aliases = [str(alias) for alias in list(operator.get("aliases", []) or []) if str(alias).strip()]
            if aliases:
                return [aliases]
        aliases = [str(alias) for alias in list(rule.get("aliases", []) or []) if str(alias).strip()]
        return [aliases] if aliases else []

    def _matches_result_type_rule(self, message: str, available_types: list[str], rule: dict[str, Any]) -> bool:
        available_type = str(rule.get("available_type", rule.get("result_type", "")) or "").strip()
        if available_type and available_type not in available_types:
            return False
        if rule.get("requires_no_explicit_core_terms") and self._message_has_explicit_core_terms(
            message,
            [str(item) for item in list(rule.get("ignore_terms_for_explicit_core_check", []) or []) if str(item).strip()],
        ):
            return False
        alias_groups = self._result_type_rule_alias_groups(rule)
        if alias_groups and not all(self._message_matches_aliases(message, group) for group in alias_groups if group):
            return False
        return bool(alias_groups)

    def _preferred_result_types_from_registry(self, message: str, available_types: list[str], *, phase: str) -> list[str]:
        preferred: list[str] = []
        for rule in self._preferred_result_type_rules():
            if str(rule.get("phase", "post_core") or "post_core") != phase:
                continue
            if not self._matches_result_type_rule(message, available_types, rule):
                continue
            result_type = str(rule.get("result_type", "") or "").strip()
            if result_type and result_type not in preferred:
                preferred.append(result_type)
        return preferred

    def _suppressed_result_types_from_registry(self, message: str, available_types: list[str]) -> list[str]:
        suppressed: list[str] = []
        for rule in self._preferred_result_type_rules():
            if not self._matches_result_type_rule(message, available_types, rule):
                continue
            for result_type in [str(item) for item in list(rule.get("suppress_result_types", []) or []) if str(item).strip()]:
                if result_type not in suppressed:
                    suppressed.append(result_type)
        return suppressed

    def _preferred_result_type_rule_by_id(self, rule_id: str) -> dict[str, Any]:
        return next(
            (item for item in self._preferred_result_type_rules() if str(item.get("id", "") or "") == str(rule_id)),
            {},
        )

    def _requests_hgt_donor_result(self, message: str, available_types: list[str]) -> bool:
        rule = self._preferred_result_type_rule_by_id("hgt_donor_results")
        return self._matches_result_type_rule(message, available_types, rule) if rule else False

    def _requests_broad_homology_organism_tags(self, message: str, available_types: list[str]) -> bool:
        rule = self._preferred_result_type_rule_by_id("broad_homology_organism_tags")
        return self._matches_result_type_rule(message, available_types, rule) if rule else False

    def _requested_core_type(self, requested_types: list[str]) -> str:
        return next((item for item in requested_types if item in {"gene", "transcript", "protein"}), "")

    def _analysis_for_ortholog_count_results(
        self,
        chat,
        message: str,
        requested_types: list[str],
    ) -> dict[str, Any] | None:
        if "ortholog" not in str(message or "").lower():
            return None
        threshold = chat._extract_numeric_threshold(message, "")
        if not threshold:
            return None
        requested_type = self._requested_core_type(requested_types) or (requested_types[0] if requested_types else "")
        if not requested_type:
            return None
        owner_type, path = self._ortholog_count_owner_type(
            chat,
            requested_type=requested_type,
            selected_type=requested_type,
            rel_type="",
        )
        if not owner_type or (requested_type != owner_type and not path):
            return None
        operator, value = threshold
        requested_organisms = self._requested_organism_name_matches(chat, message)
        unresolved_requested_organisms = []
        explicit_organism_phrases = self._requested_organism_phrase_candidates(message)
        if explicit_organism_phrases and not requested_organisms:
            unresolved_requested_organisms = list(explicit_organism_phrases)
        if self._owner_has_non_primary_gene_counts(chat, owner_type):
            strategy = "gene_counts_map"
            evidence = {"include": ["owner_organism", "gene_counts", "ortholog_organisms", "ortholog_copy_count"]}
        else:
            edge_rel_types, edge_target_types = self._ortholog_member_edge_spec(chat, owner_type)
            if not edge_rel_types or not edge_target_types:
                return None
            strategy = "member_edges"
            evidence = {"include": ["orthogroup_label", "ortholog_organisms", "ortholog_copy_count"]}
        return {
            "analysis_kind": "ortholog_count_results",
            "domain": "genomics",
            "intent": "filter",
            "requested_result_kind": "entity_rows",
            "subject": {"entity_type": requested_type},
            "owner": {"entity_type": owner_type},
            "paths": [{"source_type": requested_type, "target_type": owner_type, "rel_chain": [edge_rel for _src, edge_rel, _dst in path]}],
            "filters": [{"type": "organism_name", "names": requested_organisms}] if requested_organisms else [],
            "unresolved_requested_organisms": unresolved_requested_organisms,
            "aggregations": [{
                "type": "ortholog_copy_count",
                "strategy": strategy,
                "operator": operator,
                "value": value,
            }],
            "dimensions": {"order_by": ["ortholog_copy_count DESC", "e.name ASC"]},
            "evidence": evidence,
        }

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

    def _compile_ortholog_count_result_analysis(
        self,
        chat,
        analysis: dict[str, Any],
    ) -> str | dict[str, Any] | None:
        requested_type = str(analysis.get("subject", {}).get("entity_type", "") or "")
        owner_type = str(analysis.get("owner", {}).get("entity_type", "") or "")
        aggregations = list(analysis.get("aggregations", []) or [])
        filters = list(analysis.get("filters", []) or [])
        aggregation = dict(aggregations[0] or {}) if aggregations else {}
        strategy = str(aggregation.get("strategy", "") or "")
        operator = str(aggregation.get("operator", "") or "")
        value = aggregation.get("value")
        unresolved_requested_organisms = [
            str(item) for item in list(analysis.get("unresolved_requested_organisms", []) or []) if str(item).strip()
        ]
        if unresolved_requested_organisms:
            organism_text = ", ".join(unresolved_requested_organisms)
            return {
                "intent": "answer",
                "content": f"No organism named {organism_text} was found in this dataset.",
                "results": [],
                "semantic_trace": self._analysis_trace(
                    "ortholog_count_map",
                    analysis,
                    unresolved_requested_organisms=unresolved_requested_organisms,
                ),
            }
        if not requested_type or not owner_type or not strategy or not operator or value is None:
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
        requested_organisms = []
        for filter_item in filters:
            if str(filter_item.get("type", "") or "") == "organism_name":
                requested_organisms = [str(item) for item in list(filter_item.get("names", []) or []) if str(item).strip()]
                break
        if strategy == "gene_counts_map":
            evidence_columns = self._grouped_metric_evidence_columns("ortholog_count_map")
            having_clause = self._grouped_metric_having_clause(
                "ortholog_count_map",
                context={"operator": operator, "value": int(value)},
            )
            if len(evidence_columns) != 4 or not having_clause:
                return None
            rendered_sql = "\n".join([
                self._select_clause_with_evidence(evidence_columns),
                "FROM entities e",
                *joins,
                "JOIN json_each(owner.metadata, '$.gene_counts') gc",
                f"WHERE e.type = '{requested_type}'",
                "  AND gc.key != json_extract(owner.metadata, '$.organism')",
                "GROUP BY e.id, e.name, e.type, json_extract(owner.metadata, '$.organism'), json_extract(owner.metadata, '$.gene_counts')",
                f"HAVING {having_clause}",
            ])
            return self._analysis_synthesis_result(
                rendered_sql,
                analysis=analysis,
                evidence_columns=evidence_columns,
                semantic_trace=self._analysis_trace("ortholog_count_map", analysis, requested_type=requested_type, owner_type=owner_type),
            )
        if strategy != "member_edges":
            return None
        edge_rel_types, edge_target_types = self._ortholog_member_edge_spec(chat, owner_type)
        if not edge_rel_types or not edge_target_types:
            return None
        rel_list = ", ".join(f"'{item}'" for item in edge_rel_types)
        type_list = ", ".join(f"'{item}'" for item in edge_target_types)
        organism_where: list[str] = []
        organism_group_expr = "group_concat(DISTINCT json_extract(member.metadata, '$.organism'))"
        if requested_organisms:
            escaped = ", ".join("'" + name.replace("'", "''") + "'" for name in requested_organisms)
            organism_where.append(f"  AND json_extract(member.metadata, '$.organism') IN ({escaped})")
            if len(requested_organisms) == 1:
                organism_group_expr = "'" + requested_organisms[0].replace("'", "''") + "'"
        evidence_columns = self._grouped_metric_evidence_columns(
            "ortholog_member_count",
            context={"organism_group_expr": organism_group_expr},
        )
        having_clause = self._grouped_metric_having_clause(
            "ortholog_member_count",
            context={"operator": operator, "value": int(value)},
        )
        if len(evidence_columns) != 3 or not having_clause:
            return None
        rendered_sql = "\n".join([
            self._select_clause_with_evidence(evidence_columns),
            "FROM entities e",
            *joins,
            f"JOIN relationships om ON om.source_id = owner.id AND om.rel_type IN ({rel_list})",
            f"JOIN entities member ON member.id = om.target_id AND member.type IN ({type_list})",
            f"WHERE e.type = '{requested_type}'",
            *organism_where,
            "GROUP BY e.id, e.name, e.type, owner.name",
            f"HAVING {having_clause}",
        ])
        return self._analysis_synthesis_result(
            rendered_sql,
            analysis=analysis,
            evidence_columns=evidence_columns,
            semantic_trace=self._analysis_trace(
                "ortholog_member_edges",
                analysis,
                requested_type=requested_type,
                owner_type=owner_type,
                rel_types=edge_rel_types,
            ),
        )

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

    def _validation_error_for_analysis(self, chat, sql: str, analysis: dict[str, Any]) -> str | None:
        sql_up = str(sql or "").upper()
        sql_low = str(sql or "").lower()
        analysis_kind = str(analysis.get("analysis_kind", "") or "")
        if error := self._validation_error_from_analysis_requirement(
            analysis_kind,
            sql_up=sql_up,
            sql_low=sql_low,
        ):
            return error
        if analysis_kind == "common_functional_annotation_terms":
            filters = [dict(item) for item in list(analysis.get("filters", []) or []) if isinstance(item, dict)]
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
            namespace_filter = next((item for item in filters if item.get("type") == "metadata_filter" and item.get("field") == "namespace"), {})
            category_filter = next((item for item in filters if item.get("type") == "metadata_filter" and item.get("field") == "category"), {})
            namespace = str(namespace_filter.get("value", "") or "").upper()
            category = str(category_filter.get("value", "") or "").upper()
            if namespace and f"$.NAMESPACE') = '{namespace}'" not in sql_up:
                return (
                    "Wrong annotation namespace filter: the user requested a specific annotation family, "
                    f"so the SQL must constrain annotation_term.metadata.namespace = '{str(namespace_filter.get('value', '') or '')}'."
                )
            if category and f"$.CATEGORY') = '{category}'" not in sql_up:
                return (
                    "Wrong annotation category filter: the user requested a specific annotation family, "
                    f"so the SQL must constrain annotation_term.metadata.category = '{str(category_filter.get('value', '') or '')}'."
                )
        elif analysis_kind == "common_promoted_entity_terms":
            paths = [dict(item) for item in list(analysis.get("paths", []) or []) if isinstance(item, dict)]
            filters = [dict(item) for item in list(analysis.get("filters", []) or []) if isinstance(item, dict)]
            path = paths[0] if paths else {}
            rel_type = str(path.get("rel_type", "") or "").upper()
            result_type = str(analysis.get("subject", {}).get("entity_type", "") or path.get("target_type", "") or "").upper()
            category_filter = next((item for item in filters if item.get("type") == "metadata_filter" and item.get("field") == "category"), {})
            category = str(category_filter.get("value", "") or "").upper()
            if (
                rel_type not in sql_up
                or "COUNT(DISTINCT OWNER.ID)" not in sql_up
                or f"E.TYPE = '{result_type}'" not in sql_up
            ):
                return (
                    "Missing common promoted-call query: the user requested the most common assigned call, "
                    f"so the SQL must return {str(analysis.get('subject', {}).get('entity_type', '') or '').strip()} rows and count distinct owner entities through "
                    f"{str(path.get('rel_type', '') or '').strip()}."
                )
            if category and f"$.CATEGORY') = '{category}'" not in sql_up:
                return (
                    "Wrong promoted-call category filter: the SQL must constrain "
                    f"{str(analysis.get('subject', {}).get('entity_type', '') or '').strip()}.metadata.category = '{str(category_filter.get('value', '') or '')}'."
                )
        elif analysis_kind == "expression_ranking":
            expr_filter = next(
                (dict(item) for item in list(analysis.get("filters", []) or []) if str(item.get("type", "") or "") == "expression_measure"),
                {},
            )
            aggregation = dict((list(analysis.get("aggregations", []) or []) or [{}])[0] or {})
            expr_id = str(expr_filter.get("entity_id", "") or "").upper()
            source_column = str(expr_filter.get("source_column", "") or "")
            limit = int(analysis.get("dimensions", {}).get("limit", 0) or 0)
            direction = str(aggregation.get("direction", "DESC") or "DESC").upper()
            if (
                expr_id not in sql_up
                or f"$.{source_column}".upper() not in sql_up
                or f"LIMIT {limit}" not in sql_up
                or "ORDER BY" not in sql_up
                or direction not in sql_up
            ):
                return (
                    f"Missing stage-ranked expression semantics: the user requested top expression for '{expr_filter.get('label', expr_id)}', "
                    f"but the SQL does not constrain expression measure '{expr_filter.get('entity_id', '')}', order by transcript metadata "
                    f"field '{expr_filter.get('source_column', '')}', and apply LIMIT {limit}."
                )
        elif analysis_kind == "metadata_filters":
            requested_metadata_filters = [dict(item) for item in list(analysis.get("filters", []) or []) if isinstance(item, dict)]
            metadata_renderer = self._metadata_filter_renderer()
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
        elif analysis_kind == "ortholog_count_results":
            owner_type = str(analysis.get("owner", {}).get("entity_type", "") or "")
            aggregation = dict((list(analysis.get("aggregations", []) or []) or [{}])[0] or {})
            strategy = str(aggregation.get("strategy", "") or "")
            operator = str(aggregation.get("operator", "") or "")
            value = aggregation.get("value")
            requested_organisms = self._analysis_filter_values(
                analysis,
                filter_type="organism_name",
                field="names",
            )
            if owner_type and f"OWNER.TYPE = '{owner_type.upper()}'" not in sql_up:
                return (
                    "Wrong ortholog count owner: the SQL must bridge to the configured ortholog-count owner type "
                    f"'{owner_type}'."
                )
            if strategy == "gene_counts_map":
                if "GENE_COUNTS" not in sql_up or "JSON_EACH" not in sql_up:
                    return (
                        "Wrong counting strategy: ortholog copy counts come from the owner entity's "
                        "`metadata.gene_counts` map, expanded with `json_each(...)`, not by counting raw edges."
                    )
                if "ORTHOLOG_COPY_COUNT" not in sql_up and "GC.VALUE" not in sql_up and "MAX(CAST(GC.VALUE AS INTEGER))" not in sql_up:
                    return (
                        "Missing ortholog copy-count projection: the SQL applies an ortholog copy-count filter, "
                        "but the final result does not project the matched copy count."
                    )
                if operator and value is not None and f"HAVING MAX(CAST(GC.VALUE AS INTEGER)) {operator} {int(value)}" not in sql_up:
                    return (
                        "Wrong ortholog copy-count threshold: the SQL must apply the requested threshold using the "
                        "gene-count map aggregation."
                    )
            elif strategy == "member_edges":
                edge_rel_types, _edge_target_types = self._ortholog_member_edge_spec(chat, owner_type)
                if edge_rel_types and not any(rel_type.lower() in sql_low for rel_type in edge_rel_types):
                    return (
                        "Wrong counting strategy: ortholog copy counts in this dataset come from live ortholog-member "
                        "relationships on the orthogroup, not from a degenerate `gene_counts` map or unrelated edge counts."
                    )
                if "ORTHOLOG_COPY_COUNT" not in sql_up and "COUNT(DISTINCT MEMBER.ID)" not in sql_up:
                    return (
                        "Missing ortholog copy-count projection: the SQL applies an ortholog copy-count filter, "
                        "but the final result does not project the matched copy count."
                    )
                if operator and value is not None and f"HAVING COUNT(DISTINCT MEMBER.ID) {operator} {int(value)}" not in sql_up:
                    return (
                        "Wrong ortholog copy-count threshold: the SQL must apply the requested threshold using "
                        "ortholog-member counts."
                    )
            if requested_organisms and not all(name.lower() in sql_low for name in requested_organisms):
                return (
                    "Missing ortholog organism filter: the user requested ortholog copy counts for specific organisms, "
                    "but the SQL does not constrain those organism names."
                )
        requested_homology_organisms = [
            dict(item)
            for item in list(analysis.get("homology_organisms", []) or [])
            if isinstance(item, dict)
        ]
        has_broad_homology_condition = any(
            str(cond.get("kind", "") or "") == "protein_evidence" and str(cond.get("id", "") or "") == "broad_homology"
            for cond in self._analysis_conditions(analysis)
        )
        if requested_homology_organisms and has_broad_homology_condition:
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
        return None

    def validation_error(self, chat, sql: str, requested_types: list[str], message: str) -> str | None:
        if not sql or not requested_types:
            return None
        sql_up = sql.upper()
        sql_low = str(sql or "").lower()
        bundle = self._requested_condition_bundle(chat, message, requested_types)
        analysis = bundle.get("analysis")
        if analysis:
            if error := self._validation_error_for_analysis(chat, sql, analysis):
                return error
        requested_condition_kinds = [dict(item) for item in list(bundle.get("conditions", []) or []) if isinstance(item, dict)]
        condition_context = dict(bundle.get("condition_context", {}) or {})
        promoted_call_conditions = list(condition_context.get("requested_promoted_call_conditions", []) or [])
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
        requested_protein_rel_types = set(condition_context.get("requested_protein_rel_types", set()) or set())
        requested_scope_tags = set(condition_context.get("requested_scope_tags", set()) or set())
        requested_tag_evidence_ids = set(condition_context.get("requested_tag_evidence_ids", set()) or set())
        ortholog_member_rel_types = self._operator_rel_types("ortholog_member")
        ortholog_member_rel_type = next((rel_type for rel_type in ortholog_member_rel_types if rel_type != "BELONGS_TO_ORTHOGROUP"), "")
        requested_has_bcn_member = bool(condition_context.get("requested_has_ortholog_member"))
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
            kind = str(cond.get("kind", "") or "")
            if kind == "protein_evidence":
                missing_checks.append((
                    self._condition_sql_signatures(cond, ortholog_member_rel_type=ortholog_member_rel_type),
                    True,
                    (
                        f"Missing evidence condition: the user requested '{cond['id']}' semantics, but the SQL does not include "
                        f"relationship '{cond['rel_type']}'. Keep the requested result type and add that evidence bridge."
                    ),
                ))
            if kind == "tag_evidence":
                signatures = self._condition_sql_signatures(cond, ortholog_member_rel_type=ortholog_member_rel_type)
                if signatures and not any(signature.upper() in sql_up for signature in signatures):
                    return (
                        f"Missing tag-evidence condition: the user requested '{cond['id']}', "
                        "but the SQL does not include the matching normalized effector/tag ids or tag names."
                    )
            if kind == "scope_tag":
                missing_checks.append((
                    self._condition_sql_signatures(cond, ortholog_member_rel_type=ortholog_member_rel_type),
                    True,
                    (
                        f"Missing scope filter: the user requested scope '{cond['tag_id']}', but the SQL does not constrain that tag. "
                        "Keep the requested result type and add the matching tag filter."
                    ),
                ))
            if kind == "ortholog_member" and ortholog_member_rel_type:
                missing_checks.append((
                    self._condition_sql_signatures(cond, ortholog_member_rel_type=ortholog_member_rel_type),
                    True,
                    "Missing ortholog-member filter: the user requested ortholog genes, but the SQL does not include the orthogroup-to-ortholog-member path.",
                ))
            if kind == "orthogroup_filter":
                missing_checks.append((
                    self._condition_sql_signatures(cond, ortholog_member_rel_type=ortholog_member_rel_type),
                    True,
                    (
                        f"Missing orthogroup filter: the user requested orthogroup '{str(cond.get('label', '') or '')}', "
                        "but the SQL does not constrain the requested orthogroup."
                    ),
                ))
            if kind == "generic_tag":
                signatures = self._condition_sql_signatures(cond, ortholog_member_rel_type=ortholog_member_rel_type)
                if signatures and not any(signature.upper() in sql_up for signature in signatures):
                    return (
                        f"Missing generic-tag filter: the user requested tag '{str(cond.get('tag_name', '') or cond.get('tag_id', '') or '')}', "
                        "but the SQL does not constrain the matching tag id or name."
                    )
        error = self._find_missing_signature_error(sql, missing_checks)
        if error:
            return error
        type_match = re.search(r"e\.type\s*=\s*'([^']+)'", sql, re.IGNORECASE)
        rel_match = re.search(r"r\.rel_type\s*=\s*'([^']+)'", sql, re.IGNORECASE)
        ortholog_count_analysis = analysis if str((analysis or {}).get("analysis_kind", "") or "") == "ortholog_count_results" else None
        if not (type_match and rel_match):
            if ortholog_count_analysis:
                owner_type = next(
                    (
                        candidate
                        for candidate in ("orthogroup", "comparative_hit")
                        if candidate in {row["type"] for row in chat.db.entity_types()}
                    ),
                    "",
                )
                if error := self._ortholog_count_strategy_error(chat, owner_type=owner_type, sql_low=sql_low):
                    return error
                if error := self._ortholog_count_projection_error(sql_low):
                    return error
            return None
        selected_type = type_match.group(1)
        rel_type = rel_match.group(1)
        if not ortholog_count_analysis:
            return None
        if ortholog_count_analysis:
            owner_type_guess, _owner_path = self._ortholog_count_owner_type(
                chat,
                requested_type=selected_type,
                selected_type=selected_type,
                rel_type=rel_type,
            )
            if error := self._ortholog_count_strategy_error(chat, owner_type=owner_type_guess, sql_low=sql_low):
                return error
            if error := self._ortholog_count_projection_error(sql_low):
                return error
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
        analysis = self.analyze_request(chat, message, requested_types)
        if analysis:
            synthesized = self.synthesize_analysis(chat, analysis)
            if synthesized:
                return synthesized
        return None

    def evidence_columns_for_sql(self, chat, message: str, sql: str, requested_types: list[str]) -> list[tuple[str, str]] | None:
        evidence_columns: list[tuple[str, str]] = []
        bundle = self._requested_condition_bundle(chat, message, requested_types)
        analysis = bundle.get("analysis")
        requested_core_type = self._requested_core_type(requested_types)
        if requested_core_type in {"gene", "transcript", "protein"}:
            conditions = [dict(item) for item in list(bundle.get("conditions", []) or []) if isinstance(item, dict)]
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
            metadata_filters = (
                [dict(item) for item in list((analysis or {}).get("filters", []) or []) if isinstance(item, dict)]
                if str((analysis or {}).get("analysis_kind", "") or "") == "metadata_filters"
                else []
            )
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
