from __future__ import annotations

import re
from typing import Any

from kgx.genomics_source import load_semantic_registry

from .base import RegistryConditionModule


class GenomicsChatModule(RegistryConditionModule):
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

    def _ortholog_member_aliases(self) -> list[str]:
        ortholog_member = self._registry_relation_family("ortholog_member")
        aliases = list(ortholog_member.get("aliases", []) or [])
        return [str(alias) for alias in aliases if str(alias).strip()]

    def _relation_family(self, family_id: str) -> dict[str, Any]:
        return self._registry_relation_family(family_id)

    def _scope_tag_operator(self, tag_id: str) -> dict[str, Any]:
        operators = self._registry_operators()
        scope_tags = operators.get("scope_tags", {}) if isinstance(operators, dict) else {}
        operator = scope_tags.get(str(tag_id), {}) if isinstance(scope_tags, dict) else {}
        return dict(operator) if isinstance(operator, dict) else {}

    def _validation_config(self) -> dict[str, Any]:
        validation = self.semantic_registry.get("validation", {}) if isinstance(self.semantic_registry, dict) else {}
        return dict(validation) if isinstance(validation, dict) else {}

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

    def _schema_group_aliases(self, group_id: str) -> list[str]:
        groups = self._semantic_schema_groups()
        group = groups.get(group_id, {}) if isinstance(groups, dict) else {}
        aliases = list(group.get("aliases", []) or [])
        return [f" {alias.strip()} " for alias in aliases if str(alias).strip()]

    def _message_has_group_cue(self, message: str, group_id: str) -> bool:
        aliases = self._schema_group_aliases(group_id)
        return bool(aliases) and self._message_matches_aliases(message, aliases)

    def _effector_tag_specs(self, chat) -> list[dict[str, Any]]:
        branch_ids = chat.db._ordered_branch_ids("effector-evidence", hierarchy_edge="BROADER")
        if branch_ids == ["effector-evidence"] and not chat.db.get_entity("effector-evidence"):
            rows = chat.db.execute_read(
                "SELECT id, name FROM entities WHERE type = 'tag' AND id LIKE 'tag:%effector%' ORDER BY id"
            )
        else:
            rows = []
            for tag_id in branch_ids:
                entity = chat.db.get_entity(tag_id)
                if not entity or entity.get("type") != "tag" or entity.get("id") == "effector-evidence":
                    continue
                rows.append({"id": entity["id"], "name": entity.get("name", entity["id"])})

        primary_aliases = self._primary_organism_aliases(chat)
        secondary_aliases = self._secondary_organism_aliases(chat)
        specs: list[dict[str, Any]] = []
        for row in rows:
            tag_id = str(row.get("id", "") or "")
            tag_name = str(row.get("name", "") or "")
            norm_id = tag_id.lower()
            norm_name = tag_name.lower()
            if "effector" not in norm_id and "effector" not in norm_name:
                continue
            is_known = "known" in norm_id or "known" in norm_name
            is_putative = "putative" in norm_id or "putative" in norm_name
            is_dna = "dna" in norm_id or "dna" in norm_name
            is_protein = "protein" in norm_id or "protein" in norm_name
            aliases = {
                norm_name,
                norm_name.replace(" hit", ""),
                norm_id.replace("tag:", "").replace("-", " "),
                norm_id.replace("tag:", "").replace("-hit", "").replace("-", " "),
            }
            generic_aliases = set(aliases)
            primary_scoped_aliases: set[str] = set()
            secondary_scoped_aliases: set[str] = set()
            if is_known:
                generic_aliases.update({"known effector", "known effectors"})
            if is_dna or is_protein:
                generic_aliases.update({"known effector", "known effectors"})
            if is_putative:
                generic_aliases.update({"putative effector", "putative effectors"})
            if is_dna:
                generic_aliases.update({"dna effector", "dna effectors"})
            if is_protein:
                generic_aliases.update({"protein effector", "protein effectors"})
            if primary_aliases and (is_dna or is_protein):
                for org_alias in primary_aliases:
                    if is_known or is_dna or is_protein:
                        primary_scoped_aliases.update({
                            f"known effector in {org_alias}",
                            f"known effectors in {org_alias}",
                            f"{org_alias} known effector",
                            f"{org_alias} known effectors",
                            f"identified as known effector in {org_alias}",
                            f"identified as known effectors in {org_alias}",
                        })
                    if is_putative:
                        primary_scoped_aliases.update({
                            f"putative effector in {org_alias}",
                            f"putative effectors in {org_alias}",
                        })
            if secondary_aliases and not is_dna and not is_protein:
                for org_alias in secondary_aliases:
                    if is_known:
                        secondary_scoped_aliases.update({
                            f"known effector in {org_alias}",
                            f"known effectors in {org_alias}",
                            f"{org_alias} known effector",
                            f"{org_alias} known effectors",
                            f"identified as known effector in {org_alias}",
                            f"identified as known effectors in {org_alias}",
                        })
                    if is_putative:
                        secondary_scoped_aliases.update({
                            f"putative effector in {org_alias}",
                            f"putative effectors in {org_alias}",
                        })
            aliases.update(generic_aliases)
            aliases.update(primary_scoped_aliases)
            aliases.update(secondary_scoped_aliases)
            owner_types = ["gene"] if "island" in norm_id or "island" in norm_name else ["protein"]
            specs.append({
                "id": norm_id.replace("tag:", ""),
                "aliases": [f" {alias.strip()} " for alias in aliases if alias.strip()],
                "generic_aliases": [f" {alias.strip()} " for alias in generic_aliases if alias.strip()],
                "primary_scoped_aliases": [f" {alias.strip()} " for alias in primary_scoped_aliases if alias.strip()],
                "secondary_scoped_aliases": [f" {alias.strip()} " for alias in secondary_scoped_aliases if alias.strip()],
                "tag_ids": [tag_id],
                "owner_types": owner_types,
                "is_known": is_known,
                "is_putative": is_putative,
                "is_dna": is_dna,
                "is_protein": is_protein,
            })
        return specs

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
        has_homology_cue = (
            self._message_has_group_cue(message, "homology")
            or any(self._message_matches_aliases(message, spec["aliases"]) for spec in self._protein_evidence_specs())
            or " homology " in low
            or " homologies " in low
            or " ortholog " in low
            or " orthologs " in low
            or " ortholog gene " in low
            or " ortholog genes " in low
        )
        has_effector_cue = any(
            self._message_matches_aliases(message, list(spec.get("aliases", []) or []))
            for spec in self._effector_tag_specs(chat)
        ) or self._message_has_group_cue(message, "effectors")
        if has_effector_cue and not has_homology_cue:
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
        for spec in self._protein_evidence_specs():
            if not self._message_matches_aliases(message, list(spec.get("aliases", []) or [])):
                continue
            owner_type = str(spec.get("owner_type", "protein") or "protein")
            conditions.append({"kind": "protein_evidence", **spec, "owner_types": [owner_type]})
        return conditions

    def _matched_ortholog_member_conditions(self, message: str) -> list[dict[str, Any]]:
        low = str(message or "").lower()
        ortholog_aliases = self._ortholog_member_aliases()
        if (
            ortholog_aliases
            and self._message_matches_aliases(message, ortholog_aliases)
            and not re.search(r"\bcop(y|ies)\b", low)
        ):
            return [{"kind": "ortholog_member"}]
        return []

    def _semantic_conditions(self, chat, message: str) -> list[dict[str, Any]]:
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

    def _protein_evidence_context(self, cond: dict[str, Any]) -> dict[str, Any]:
        owner_type = next(iter(list(cond.get("owner_types", []) or [cond.get("owner_type", "protein")])), "protein")
        return {
            "owner_type": str(owner_type or "protein"),
            "evidence_rel_type": str(cond.get("rel_type", "") or ""),
            "target_types": [str(item) for item in list(cond.get("target_types", []) or []) if str(item).strip()],
        }

    def _protein_evidence_rel_types(self) -> list[str]:
        rel_types: list[str] = []
        for spec in self._protein_evidence_specs():
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
        target_types = list(cond.get("target_types", []) or [])
        target_alias = str(context.get("evidence_target", "") or "")
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
        evidence = next((spec for spec in self._protein_evidence_specs() if spec["id"] == operator.get("evidence_id")), None)
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
    ) -> tuple[bool, int]:
        ok, alias_index, _context = self._append_registry_operator_joins(
            chat,
            operator_id="tag_evidence",
            requested_type=requested_type,
            joins=joins,
            where_lines=[],
            alias_index=alias_index,
            template_context=self._tag_evidence_context(cond),
        )
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
        )

    def _semantic_condition_handlers_map(self) -> dict[str, Any]:
        return {
            "protein_evidence": self._handle_condition_protein_evidence,
            "orthogroup_filter": self._handle_condition_orthogroup_filter,
            "ortholog_member": self._handle_condition_ortholog_member,
            "scope_tag": self._handle_condition_scope_tag,
            "tag_evidence": self._handle_condition_tag_evidence,
        }

    def _semantic_query(self, chat, message: str, requested_types: list[str]) -> str | None:
        requested_type = self._requested_core_type(requested_types)
        if requested_type not in {"gene", "transcript", "protein"}:
            return None
        conditions = self._semantic_conditions(chat, message)
        if not conditions:
            return None

        return self._build_semantic_entity_query(
            chat,
            requested_type=requested_type,
            conditions=conditions,
            distinct=True,
            state={
                "scope_tag_ids": {cond["tag_id"] for cond in conditions if cond["kind"] == "scope_tag"},
                "used_scope_tags": set(),
                "has_protein_evidence": any(cond["kind"] == "protein_evidence" for cond in conditions),
            },
        )

    def schema_context_lines(self, chat) -> list[str]:
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
        if not count_map_examples:
            return []
        type_list = ", ".join(row["type"] for row in count_map_examples)
        return [
            "Count-map semantics: some entity types store primary-organism counts as "
            "`metadata.organism` + `metadata.gene_counts`. For those types, the primary count is the "
            "entry in `gene_counts` keyed by `organism`, and ortholog/other-organism counts are the other "
            f"entries in the same map. Types using this pattern: {type_list}",
            "Comparative and HGT evidence can live on protein rows and still be queried at the gene, "
            "transcript, or protein level by bridging through typed paths in either direction.",
        ]

    def validation_error(self, chat, sql: str, requested_types: list[str], message: str) -> str | None:
        if not sql or not requested_types:
            return None
        sql_up = sql.upper()
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
            unexpected_checks.append((
                [str(tag_id) for tag_id in list(spec.get("tag_ids", []) or []) if str(tag_id).strip()],
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
                missing_checks.append((
                    [str(tag_id) for tag_id in list(cond.get("tag_ids", []) or []) if str(tag_id).strip()],
                    True,
                    f"Missing tag-evidence condition: the user requested '{cond['id']}', but the SQL does not include the matching normalized effector/tag ids.",
                ))
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
        if not (type_match and rel_match):
            return None
        selected_type = type_match.group(1)
        rel_type = rel_match.group(1)
        if "ortholog" not in str(message or "").lower():
            return None
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

    def synthesize_query(self, chat, message: str, sql: str, requested_types: list[str]) -> str | None:
        semantic_sql = self._semantic_query(chat, message, requested_types)
        if semantic_sql:
            return semantic_sql
        if not sql or not requested_types:
            return None
        available_types = [row["type"] for row in chat.db.entity_types()]
        if "tag" in requested_types and self._requests_broad_homology_organism_tags(message, available_types):
            return "\n".join([
                "SELECT DISTINCT e.id, e.name, e.type",
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
            ])
        if "hgt_donor" in requested_types and self._requests_hgt_donor_semantics(message):
            return "\n".join([
                "SELECT DISTINCT e.id, e.name, e.type",
                "FROM entities e",
                "JOIN relationships r ON r.target_id = e.id AND r.rel_type = 'HAS_HGT_DONOR'",
                "WHERE e.type = 'hgt_donor'",
            ])
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
        return "\n".join([
            "SELECT DISTINCT e.id, e.name, e.type",
            "FROM entities e",
            *joins,
            owner_join,
            "JOIN json_each(owner.metadata, '$.gene_counts') gc",
            f"WHERE e.type = '{requested_type}'",
            "  AND gc.key != json_extract(owner.metadata, '$.organism')",
            f"  AND CAST(gc.value AS INTEGER) {op} {value}",
        ])
