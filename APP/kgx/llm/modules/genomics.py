from __future__ import annotations

import re

from .base import ChatModule


class GenomicsChatModule(ChatModule):
    _PROTEIN_EVIDENCE_BRIDGES = [
        {
            "aliases": ["hgt donor", "horizontal gene transfer", " hgt "],
            "rel_type": "HAS_HGT_DONOR",
            "target_type": "hgt_donor",
        },
    ]

    @staticmethod
    def _message_matches_aliases(message: str, aliases: list[str]) -> bool:
        low = f" {str(message or '').lower()} "
        return any(alias in low for alias in aliases)

    def preferred_result_types(self, chat, message: str, available_types: list[str]) -> list[str]:
        low = f" {str(message or '').lower()} "
        preferred: list[str] = []
        explicit_gene_like = any(token in low for token in [" genes ", " transcript ", " transcripts ", " protein ", " proteins "])
        if " gene " in low and " gene transfer " not in low:
            explicit_gene_like = True
        if "hgt_donor" in available_types and (
            " hgt donor " in low
            or " hgt donors " in low
            or " horizontal gene transfer donor " in low
            or " horizontal gene transfer donors " in low
        ) and not explicit_gene_like:
            preferred.append("hgt_donor")
        return preferred

    def _protein_evidence_bridge(self, chat, message: str, requested_types: list[str]) -> str | None:
        requested_type = requested_types[0] if requested_types else ""
        if requested_type not in {"gene", "transcript", "protein"}:
            return None
        patterns = chat._typed_rel_patterns()
        for spec in self._PROTEIN_EVIDENCE_BRIDGES:
            if not self._message_matches_aliases(message, spec["aliases"]):
                continue
            rel_type = spec["rel_type"]
            target_type = spec["target_type"]
            if ("protein", rel_type, target_type) not in patterns:
                continue
            path = chat._shortest_type_path(requested_type, "protein")
            if requested_type != "protein" and not path:
                continue
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
            joins.append(
                f"JOIN relationships ev ON ev.source_id = {current_node_ref} AND ev.rel_type = '{rel_type}'"
            )
            return "\n".join([
                "SELECT DISTINCT e.id, e.name, e.type",
                "FROM entities e",
                *joins,
                f"WHERE e.type = '{requested_type}'",
            ])
        return None

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
            "Comparative and HGT evidence can live on protein rows and still be queried at the gene or "
            "transcript level by bridging through the typed path to protein first.",
        ]

    def validation_error(self, chat, sql: str, requested_types: list[str], message: str) -> str | None:
        if not sql or not requested_types:
            return None
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
        protein_evidence_sql = self._protein_evidence_bridge(chat, message, requested_types)
        if protein_evidence_sql:
            return protein_evidence_sql
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
