from __future__ import annotations

import re
from typing import Any

from .base import ChatModule


class GenomicsChatModule(ChatModule):
    _HOMOLOGY_SCOPE_ROOT = "homology-scope"
    _PROTEIN_EVIDENCE_SPECS = [
        {
            "id": "hgt",
            "aliases": ["hgt donor", "horizontal gene transfer", " hgt "],
            "rel_type": "HAS_HGT_DONOR",
            "target_types": ["hgt_donor"],
        },
        {
            "id": "broad_homology",
            "aliases": ["broad homology", "broad parasitism"],
            "rel_type": "HAS_BROAD_HOMOLOGY_HIT",
            "target_types": ["comparative_hit"],
        },
        {
            "id": "nematode_homology",
            "aliases": ["nematode homology", "c. elegans", "caenorhabditis elegans"],
            "rel_type": "HAS_NEMATODE_HIT",
            "target_types": ["comparative_hit"],
        },
        {
            "id": "bcn_homology",
            "aliases": ["cyst nematode homology", "bcn homology", "h. schachtii", "heterodera schachtii"],
            "rel_type": "HAS_BCN_HIT",
            "target_types": ["comparative_hit", "bcn_gene"],
        },
    ]
    @staticmethod
    def _message_matches_aliases(message: str, aliases: list[str]) -> bool:
        low = f" {str(message or '').lower()} "
        return any(alias in low for alias in aliases)

    @staticmethod
    def _requested_orthogroup_label(message: str) -> str:
        match = re.search(r"\b(?:orthogroup\s+)?(og\d{4,})\b", str(message or ""), re.IGNORECASE)
        return match.group(1).upper() if match else ""

    @staticmethod
    def _scope_aliases_for_tag(tag_id: str, tag_name: str) -> list[str]:
        aliases = {
            str(tag_name or "").strip().lower(),
            str(tag_id or "").strip().lower().replace("homology-scope-", "").replace("-", " "),
        }
        normalized = str(tag_id or "").strip().lower()
        if normalized.endswith("cyst-nematode"):
            aliases.add("bcn")
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

    def _semantic_conditions(self, chat, message: str) -> list[dict[str, Any]]:
        conditions: list[dict[str, Any]] = []
        for spec in self._PROTEIN_EVIDENCE_SPECS:
            if self._message_matches_aliases(message, spec["aliases"]):
                conditions.append({"kind": "protein_evidence", **spec})
        evidence_ids = {cond["id"] for cond in conditions if cond["kind"] == "protein_evidence"}
        if "bcn_homology" in evidence_ids and "nematode_homology" in evidence_ids:
            conditions = [
                cond for cond in conditions
                if not (cond["kind"] == "protein_evidence" and cond["id"] == "nematode_homology")
            ]
        orthogroup_label = self._requested_orthogroup_label(message)
        if orthogroup_label:
            conditions.append({"kind": "orthogroup_filter", "label": orthogroup_label})
        low = str(message or "").lower()
        if re.search(r"\b(ortholog genes?|bcn orthologs?|bcn genes?)\b", low) and not re.search(r"\bcop(y|ies)\b", low):
            conditions.append({"kind": "ortholog_member"})
        for tag_id in self._requested_scope_tag_ids(chat, message):
            conditions.append({"kind": "scope_tag", "tag_id": tag_id})
        return conditions

    def preferred_result_types(self, chat, message: str, available_types: list[str]) -> list[str]:
        low = f" {str(message or '').lower()} "
        preferred: list[str] = []
        if "protein" in available_types and re.search(r"\bproteins?\b", low):
            preferred.append("protein")
        if "transcript" in available_types and re.search(r"\btranscripts?\b", low):
            preferred.append("transcript")
        if "gene" in available_types and re.search(r"\bgenes?\b", low) and " gene transfer " not in low:
            preferred.append("gene")
        explicit_core = bool(preferred)
        if "hgt_donor" in available_types and (
            " hgt donor " in low
            or " hgt donors " in low
            or " horizontal gene transfer donor " in low
            or " horizontal gene transfer donors " in low
        ) and not explicit_core:
            preferred.append("hgt_donor")
        if "bcn_gene" in available_types and self._message_matches_aliases(message, ["ortholog gene", "ortholog genes", "bcn ortholog", "bcn gene", "bcn genes"]) and not explicit_core:
            preferred.append("bcn_gene")
        if "comparative_hit" in available_types and self._message_matches_aliases(message, ["homology hit", "homology hits"]) and not explicit_core:
            preferred.append("comparative_hit")
        return preferred

    def _append_path_joins(
        self,
        chat,
        *,
        from_type: str,
        to_type: str,
        current_node_ref: str,
        alias_index: int,
    ) -> tuple[list[str], str, int]:
        joins: list[str] = []
        path = chat._shortest_type_path_any_direction(from_type, to_type)
        if from_type != to_type and not path:
            return [], "", alias_index
        ref = current_node_ref
        current_type = from_type
        for src, edge_rel, dst, direction in path:
            if src != current_type:
                return [], "", alias_index
            alias_index += 1
            rel_alias = f"p{alias_index}"
            if direction == "forward":
                joins.append(
                    f"JOIN relationships {rel_alias} ON {rel_alias}.source_id = {ref} AND {rel_alias}.rel_type = '{edge_rel}'"
                )
                ref = f"{rel_alias}.target_id"
            else:
                joins.append(
                    f"JOIN relationships {rel_alias} ON {rel_alias}.target_id = {ref} AND {rel_alias}.rel_type = '{edge_rel}'"
                )
                ref = f"{rel_alias}.source_id"
            current_type = dst
        return joins, ref, alias_index

    def _requested_core_type(self, requested_types: list[str]) -> str:
        return next((item for item in requested_types if item in {"gene", "transcript", "protein"}), "")

    def _semantic_query(self, chat, message: str, requested_types: list[str]) -> str | None:
        requested_type = self._requested_core_type(requested_types)
        if requested_type not in {"gene", "transcript", "protein"}:
            return None
        conditions = self._semantic_conditions(chat, message)
        if not conditions:
            return None

        joins: list[str] = []
        where_lines = [f"WHERE e.type = '{requested_type}'"]
        alias_index = 0
        scope_tag_ids = {cond["tag_id"] for cond in conditions if cond["kind"] == "scope_tag"}
        has_protein_evidence = any(cond["kind"] == "protein_evidence" for cond in conditions)
        used_scope_tags: set[str] = set()

        for cond in conditions:
            kind = cond["kind"]
            if kind == "protein_evidence":
                path_joins, owner_ref, alias_index = self._append_path_joins(
                    chat,
                    from_type=requested_type,
                    to_type="protein",
                    current_node_ref="e.id",
                    alias_index=alias_index,
                )
                if requested_type != "protein" and not path_joins:
                    return None
                joins.extend(path_joins)
                alias_index += 1
                ev_alias = f"ev{alias_index}"
                joins.append(
                    f"JOIN relationships {ev_alias} ON {ev_alias}.source_id = {owner_ref or 'e.id'} AND {ev_alias}.rel_type = '{cond['rel_type']}'"
                )
                alias_index += 1
                target_alias = f"t{alias_index}"
                target_types = list(cond.get("target_types", []) or [])
                if len(target_types) == 1:
                    target_type_clause = f"{target_alias}.type = '{target_types[0]}'"
                else:
                    target_type_clause = f"{target_alias}.type IN ({', '.join(repr(target_type) for target_type in target_types)})"
                joins.append(
                    f"JOIN entities {target_alias} ON {target_alias}.id = {ev_alias}.target_id AND {target_type_clause}"
                )
                if cond["id"] == "broad_homology" and "homology-scope-broad-parasitism" in scope_tag_ids:
                    alias_index += 1
                    tg_alias = f"tg{alias_index}"
                    joins.append(
                        f"JOIN relationships {tg_alias} ON {tg_alias}.source_id = {target_alias}.id AND {tg_alias}.rel_type = 'TAGGED'"
                    )
                    alias_index += 1
                    tag_alias = f"tag{alias_index}"
                    joins.append(
                        f"JOIN entities {tag_alias} ON {tag_alias}.id = {tg_alias}.target_id AND {tag_alias}.type = 'tag'"
                    )
                    where_lines.append(
                        f"  AND {tag_alias}.id = 'homology-scope-broad-parasitism'"
                    )
                    used_scope_tags.add("homology-scope-broad-parasitism")
                if cond["id"] == "nematode_homology" and "homology-scope-nematode" in scope_tag_ids:
                    used_scope_tags.add("homology-scope-nematode")
                if cond["id"] == "bcn_homology" and "homology-scope-cyst-nematode" in scope_tag_ids:
                    used_scope_tags.add("homology-scope-cyst-nematode")
            elif kind == "orthogroup_filter":
                path_joins, gene_ref, alias_index = self._append_path_joins(
                    chat,
                    from_type=requested_type,
                    to_type="gene",
                    current_node_ref="e.id",
                    alias_index=alias_index,
                )
                if requested_type != "gene" and not path_joins:
                    return None
                joins.extend(path_joins)
                alias_index += 1
                og_alias = f"og{alias_index}"
                joins.append(
                    f"JOIN relationships {og_alias} ON {og_alias}.source_id = {gene_ref or 'e.id'} AND {og_alias}.rel_type = 'BELONGS_TO_ORTHOGROUP'"
                )
                alias_index += 1
                owner_alias = f"owner{alias_index}"
                joins.append(
                    f"JOIN entities {owner_alias} ON {owner_alias}.id = {og_alias}.target_id AND {owner_alias}.type = 'orthogroup'"
                )
                where_lines.append(
                    f"  AND (upper({owner_alias}.name) = '{cond['label']}' OR upper({owner_alias}.id) = 'ORTHOGROUP:{cond['label']}')"
                )
            elif kind == "ortholog_member":
                path_joins, gene_ref, alias_index = self._append_path_joins(
                    chat,
                    from_type=requested_type,
                    to_type="gene",
                    current_node_ref="e.id",
                    alias_index=alias_index,
                )
                if requested_type != "gene" and not path_joins:
                    return None
                joins.extend(path_joins)
                alias_index += 1
                og_alias = f"ogm{alias_index}"
                joins.append(
                    f"JOIN relationships {og_alias} ON {og_alias}.source_id = {gene_ref or 'e.id'} AND {og_alias}.rel_type = 'BELONGS_TO_ORTHOGROUP'"
                )
                alias_index += 1
                mem_alias = f"mem{alias_index}"
                joins.append(
                    f"JOIN relationships {mem_alias} ON {mem_alias}.source_id = {og_alias}.target_id AND {mem_alias}.rel_type = 'HAS_BCN_MEMBER'"
                )
            elif kind == "scope_tag":
                if cond["tag_id"] in used_scope_tags or not has_protein_evidence:
                    continue
                path_joins, owner_ref, alias_index = self._append_path_joins(
                    chat,
                    from_type=requested_type,
                    to_type="protein",
                    current_node_ref="e.id",
                    alias_index=alias_index,
                )
                if requested_type != "protein" and not path_joins:
                    return None
                joins.extend(path_joins)
                broad_rel = next((spec for spec in self._PROTEIN_EVIDENCE_SPECS if spec["id"] == "broad_homology"), None)
                if not broad_rel:
                    return None
                alias_index += 1
                ev_alias = f"sev{alias_index}"
                joins.append(
                    f"JOIN relationships {ev_alias} ON {ev_alias}.source_id = {owner_ref or 'e.id'} AND {ev_alias}.rel_type = '{broad_rel['rel_type']}'"
                )
                alias_index += 1
                target_alias = f"shit{alias_index}"
                joins.append(
                    f"JOIN entities {target_alias} ON {target_alias}.id = {ev_alias}.target_id AND {target_alias}.type = 'comparative_hit'"
                )
                alias_index += 1
                tg_alias = f"stg{alias_index}"
                joins.append(
                    f"JOIN relationships {tg_alias} ON {tg_alias}.source_id = {target_alias}.id AND {tg_alias}.rel_type = 'TAGGED'"
                )
                alias_index += 1
                tag_alias = f"stag{alias_index}"
                joins.append(
                    f"JOIN entities {tag_alias} ON {tag_alias}.id = {tg_alias}.target_id AND {tag_alias}.type = 'tag'"
                )
                where_lines.append(f"  AND {tag_alias}.id = '{cond['tag_id']}'")
                used_scope_tags.add(cond["tag_id"])

        return "\n".join([
            "SELECT DISTINCT e.id, e.name, e.type",
            "FROM entities e",
            *joins,
            *where_lines,
        ])

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
        requested_has_bcn_member = any(cond["kind"] == "ortholog_member" for cond in requested_condition_kinds)

        for rel_type in ["HAS_HGT_DONOR", "HAS_BROAD_HOMOLOGY_HIT", "HAS_NEMATODE_HIT", "HAS_BCN_HIT"]:
            if rel_type in sql_up and rel_type not in requested_protein_rel_types:
                return (
                    f"Unexpected evidence condition: the SQL includes relationship '{rel_type}', but the user did not request that evidence. "
                    "Keep the requested result type and only apply evidence conditions that are explicitly implied by the prompt."
                )
        for tag_id, _tag_name in self._homology_scope_branch(chat):
            tag_id = tag_id.upper()
            if tag_id in sql_up and tag_id not in requested_scope_tags:
                return (
                    f"Unexpected scope filter: the SQL constrains '{tag_id.lower()}', but the user did not request that homology scope. "
                    "Keep the requested result type and only apply scope filters that are explicitly implied by the prompt."
                )
        if "HAS_BCN_MEMBER" in sql_up and not requested_has_bcn_member:
            return (
                "Unexpected ortholog-member filter: the SQL requires ortholog members, but the user did not request an ortholog-member condition."
            )

        for cond in requested_condition_kinds:
            if cond["kind"] == "protein_evidence" and cond["rel_type"] not in sql_up:
                return (
                    f"Missing evidence condition: the user requested '{cond['id']}' semantics, but the SQL does not include "
                    f"relationship '{cond['rel_type']}'. Keep the requested result type and add that evidence bridge."
                )
            if cond["kind"] == "scope_tag" and cond["tag_id"].upper() not in sql_up:
                return (
                    f"Missing scope filter: the user requested scope '{cond['tag_id']}', but the SQL does not constrain that tag. "
                    "Keep the requested result type and add the matching tag filter."
                )
            if cond["kind"] == "ortholog_member" and "HAS_BCN_MEMBER" not in sql_up:
                return (
                    "Missing ortholog-member filter: the user requested ortholog genes, but the SQL does not include "
                    "the orthogroup-to-ortholog-member path."
                )
        orthogroup_label = self._requested_orthogroup_label(message)
        if orthogroup_label and self._message_matches_aliases(message, ["hgt donor", "horizontal gene transfer", " hgt "]):
            if "BELONGS_TO_ORTHOGROUP" not in sql_up and "ORTHOGROUP" not in sql_up:
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
        msg = str(message or "").lower()
        if "ortholog" not in msg:
            return None
        if "gene_counts" not in sql.lower() and "belongs_to_orthogroup" not in sql.lower():
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
        patterns = chat._typed_rel_patterns()
        owner_type = ""
        path = []
        if rel_type:
            target_types = sorted({dst for src, rel, dst in patterns if src == requested_type and rel == rel_type})
            owner_type = next((etype for etype in target_types if "gene_counts" in set(chat.db.metadata_keys(etype))), "")
            if owner_type:
                path = chat._shortest_type_path(requested_type, owner_type)
        if not owner_type and "gene_counts" in set(chat.db.metadata_keys(selected_type)):
            owner_type = selected_type
            path = chat._shortest_type_path(requested_type, owner_type)
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
