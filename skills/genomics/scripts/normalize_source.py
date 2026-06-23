#!/usr/bin/env python3
"""Convert raw local genomics source files into standardized YAML metadata."""

from __future__ import annotations

import csv
import re
import runpy
from collections import OrderedDict
from pathlib import Path
from typing import Any

import yaml

from genomics_contract import load_contract, split_shared_and_specific


GENE_COLUMNS = [
    "gene_name",
    "genome_location",
    "nested_genes",
    "nest_genes",
    "average_copy_number",
    "tn7_copy_number",
    "tn8_copy_number",
    "tn10_copy_number",
    "tn20_copy_number",
    "tn22_copy_number",
    "mm26_copy_number",
    "op50_copy_number",
    "pa3_copy_number",
    "x12_copy_number",
]

TRANSCRIPT_COLUMNS = [
    "uniquename",
    "cluster_name",
    "cluster_score",
    "expression_bin_13",
    "expression_bin_38",
    "avg_counts",
    "avg_egg",
    "avg_ppj2",
    "avg_pj2",
    "avg_j3",
    "avg_j4",
    "avg_female",
    "avg_male",
    "avg_j2g",
    "avg_j3g",
    "avg_glands",
    "dge_egg_ppj2",
    "dge_egg_pj2",
    "dge_ppj2_pj2",
    "dge_pj2_j3",
    "dge_j3_j4",
    "dge_j4_female",
    "dge_j4_male",
    "dge_female_male",
    "dge_j3g_j2g",
    "dge_j2g_pj2b",
    "dge_j3g_j3b",
    "dge_j2g_mm10_pa3",
    "dge_j3g_mm10_pa3",
    "mrna_sequence",
]

PROTEIN_COLUMNS = [
    "protein_sequence",
    "secretion",
    "dl_signals",
    "dl_localizations",
    "localizer",
    "l_nucleus_peptide",
    "l_mitochondria_peptide",
    "l_mitochondria_score",
    "l_chloroplast_peptide",
    "l_chloroplast_score",
    "signal_peptide",
    "signalp5",
    "signalp6",
    "tm_domain_sp5",
    "tm_domain_sp6",
    "dl_nucleus",
    "dl_mitochondrion",
    "dl_plastid",
    "dl_cytoplasm",
    "dl_endoplasmic_reticulum",
    "dl_lysosome_vacuole",
    "dl_golgi_apparatus",
    "dl_peroxisome",
    "dl_cell_membrane",
    "dl_extracellular",
    "glycines_effectors_dna",
    "glycines_effectors_prot",
    "schachtii_effectors_known",
    "schachtii_effectors_putative",
    "effector_islands",
    "orthogroup",
    "glycines_gene_count",
    "schachtii_gene_count",
    "schachtii_genes",
    "schachtii_hits",
    "celegans_hits",
    "sp_best_hit",
    "nr_best_hit",
    "hgt_donor_id",
    "hgt_alien_index",
    "t_factor",
    "go_consensus",
    "deepgoplus",
    "interpro",
    "smart",
    "pfam",
    "funfam",
    "panther",
    "disorder",
    "diso_regions",
    "num_globular",
    "domains",
    "pdb_hit",
    "hit_class",
    "inclusion_body",
    "mol_weight",
    "isoel_point",
    "charge",
    "charged",
    "aromatic",
    "polar",
    "non_polar",
    "basic",
    "acidic",
    "small",
    "alanine",
    "asparagine",
    "aspartate",
    "cysteine",
    "glutamate",
    "glutamine",
    "glycine",
    "histidine",
    "isoleucine",
    "leucine",
    "lysine",
    "methionine",
    "phenylalanine",
    "proline",
    "arginine",
    "serine",
    "threonine",
    "valine",
    "tryptophan",
    "tyrosine",
    "unknown",
]


ANNOTATION_BINS = [
    {"column": "go_consensus", "namespace": "go", "parser": "go_plain", "attach_to": "protein", "parent_tag": "go-annotation", "category": "functional_annotation", "promoted_entity_type": "annotation_term", "promoted_relation_type": "HAS_ANNOTATION", "promoted_id_template": "annotation:{namespace}:{id}"},
    {"column": "deepgoplus", "namespace": "go", "parser": "go_scored", "attach_to": "protein", "parent_tag": "go-annotation", "category": "functional_annotation", "promoted_entity_type": "annotation_term", "promoted_relation_type": "HAS_ANNOTATION", "promoted_id_template": "annotation:{namespace}:{id}"},
    {"column": "interpro", "namespace": "interpro", "parser": "interpro_ids", "attach_to": "protein", "parent_tag": "interpro-domain", "category": "domain_annotation", "promoted_entity_type": "annotation_term", "promoted_relation_type": "HAS_ANNOTATION", "promoted_id_template": "annotation:{namespace}:{id}"},
    {"column": "pfam", "namespace": "pfam", "parser": "pfam_ids", "attach_to": "protein", "parent_tag": "pfam-family", "category": "domain_annotation", "promoted_entity_type": "annotation_term", "promoted_relation_type": "HAS_ANNOTATION", "promoted_id_template": "annotation:{namespace}:{id}"},
    {"column": "smart", "namespace": "smart", "parser": "smart_ids", "attach_to": "protein", "parent_tag": "smart-domain", "category": "domain_annotation", "promoted_entity_type": "annotation_term", "promoted_relation_type": "HAS_ANNOTATION", "promoted_id_template": "annotation:{namespace}:{id}"},
    {"column": "funfam", "namespace": "funfam", "parser": "funfam_ids", "attach_to": "protein", "parent_tag": "funfam-family", "category": "domain_annotation", "promoted_entity_type": "annotation_term", "promoted_relation_type": "HAS_ANNOTATION", "promoted_id_template": "annotation:{namespace}:{id}"},
    {"column": "panther", "namespace": "panther", "parser": "panther_ids", "attach_to": "protein", "parent_tag": "panther-family", "category": "domain_annotation", "promoted_entity_type": "annotation_term", "promoted_relation_type": "HAS_ANNOTATION", "promoted_id_template": "annotation:{namespace}:{id}"},
]

TAG_BINS = [
    {"column": "dl_signals", "parser": "term_list", "attach_to": "protein", "parent_tag": "localization-signal", "category": "prediction_feature", "promoted_entity_type": "prediction_call", "promoted_relation_type": "HAS_PREDICTION", "promoted_id_template": "prediction:{category}:{id}"},
    {"column": "dl_localizations", "parser": "term_list", "attach_to": "protein", "parent_tag": "subcellular-localization", "category": "localization", "promoted_entity_type": "localization_call", "promoted_relation_type": "HAS_LOCALIZATION", "promoted_id_template": "localization:{id}"},
    {"column": "localizer", "parser": "term_list", "attach_to": "protein", "parent_tag": "subcellular-localization", "category": "localization", "promoted_entity_type": "localization_call", "promoted_relation_type": "HAS_LOCALIZATION", "promoted_id_template": "localization:{id}"},
    {"column": "expression_bin_13", "parser": "single_term", "attach_to": "transcript", "parent_tag": "expression-bin", "category": "expression_summary"},
    {"column": "expression_bin_38", "parser": "single_term", "attach_to": "transcript", "parent_tag": "expression-bin", "category": "expression_summary"},
    {"column": "t_factor", "parser": "single_term", "attach_to": "protein", "parent_tag": "functional-prediction", "category": "prediction_feature", "promoted_entity_type": "prediction_call", "promoted_relation_type": "HAS_PREDICTION", "promoted_id_template": "prediction:{category}:{id}"},
]

BOOLEAN_TAGS = [
    {"column": "effector_islands", "truthy": ["true", "yes", "1"], "tag_id": "effector-island", "label": "Effector Island", "attach_to": "gene", "parent_tag": "effector-evidence"},
]

VALUE_PRESENCE_TAGS = [
    {"column": "schachtii_effectors_known", "tag_id": "bcn-known-effector-hit", "label": "BCN Known Effector Hit", "attach_to": "protein", "parent_tag": "effector-evidence"},
    {"column": "schachtii_effectors_putative", "tag_id": "bcn-putative-effector-hit", "label": "BCN Putative Effector Hit", "attach_to": "protein", "parent_tag": "effector-evidence"},
    {"column": "glycines_effectors_dna", "tag_id": "scn-dna-effector-hit", "label": "SCN DNA Effector Hit", "attach_to": "protein", "parent_tag": "effector-evidence"},
    {"column": "glycines_effectors_prot", "tag_id": "scn-protein-effector-hit", "label": "SCN Protein Effector Hit", "attach_to": "protein", "parent_tag": "effector-evidence"},
]

CONTRACT = load_contract("functional_genomics")
TAG_HIERARCHY = dict(CONTRACT.get("tag_hierarchy", {}))

SUMMARY_TOKEN_ALIASES = {
    "f": "female",
    "m": "male",
    "j2": "pj2",
}


def _normalize_expression_token(value: str) -> str:
    return "".join(ch for ch in str(value).strip().lower() if ch.isalnum())


def _slug_text(value: str) -> str:
    lowered = str(value).strip().lower()
    lowered = re.sub(r"[^a-z0-9]+", "-", lowered)
    return lowered.strip("-") or "value"


def _summary_aliases(label: str, column: str) -> set[str]:
    aliases: set[str] = set()
    normalized_label = _normalize_expression_token(label)
    normalized_column = _normalize_expression_token(column.removeprefix("avg_"))
    if normalized_label:
        aliases.add(normalized_label)
    if normalized_column:
        aliases.add(normalized_column)
    if normalized_label == "female":
        aliases.add("f")
    if normalized_label == "male":
        aliases.add("m")
    if normalized_column.endswith("g"):
        aliases.add(f"g{normalized_column[:-1]}")
    if normalized_label.endswith("g"):
        aliases.add(f"g{normalized_label[:-1]}")
    return aliases


def _summary_lookup(expression_fields: dict[str, str]) -> dict[str, tuple[str, str]]:
    lookup: dict[str, tuple[str, str]] = {}
    for label, column in expression_fields.items():
        for alias in _summary_aliases(str(label), str(column)):
            lookup[alias] = (str(label), str(column))
    return lookup


def _resolve_summary_match(token: str, lookup: dict[str, tuple[str, str]]) -> tuple[str, str] | None:
    normalized = _normalize_expression_token(token)
    if not normalized:
        return None
    candidates = [normalized]
    alias = SUMMARY_TOKEN_ALIASES.get(normalized)
    if alias:
        candidates.append(alias)
    if normalized.endswith("b"):
        candidates.append(normalized[:-1])
    if normalized.startswith("g") and len(normalized) > 1:
        candidates.append(f"{normalized[1:]}g")
        candidates.append(normalized[1:])
    for candidate in candidates:
        match = lookup.get(candidate)
        if match:
            return match
        alias = SUMMARY_TOKEN_ALIASES.get(candidate)
        if alias and lookup.get(alias):
            return lookup[alias]
    return None


def derive_contrast_summary_links(
    expression_fields: dict[str, str],
    contrast_label: str,
    contrast_column: str,
) -> dict[str, str]:
    lookup = _summary_lookup(expression_fields)
    result: dict[str, str] = {}
    raw_column = str(contrast_column).removeprefix("dge_")
    column_parts = [part for part in raw_column.split("_") if part]

    matches: list[tuple[str, str]] = []
    if len(column_parts) >= 2:
        left = _resolve_summary_match(column_parts[0], lookup)
        right = _resolve_summary_match(column_parts[1], lookup)
        if left:
            matches.append(left)
        if right and right != left:
            matches.append(right)
    elif len(column_parts) == 1:
        left = _resolve_summary_match(column_parts[0], lookup)
        if left:
            matches.append(left)

    if not matches and " vs " in contrast_label.lower():
        left_text, right_text = re.split(r"\s+vs\s+", str(contrast_label), maxsplit=1, flags=re.IGNORECASE)
        left = _resolve_summary_match(left_text, lookup)
        right = _resolve_summary_match(right_text, lookup)
        if left:
            matches.append(left)
        if right and right != left:
            matches.append(right)

    if matches:
        result["source_summary_label"] = matches[0][0]
        result["source_summary_column"] = matches[0][1]
    if len(matches) > 1:
        result["target_summary_label"] = matches[1][0]
        result["target_summary_column"] = matches[1][1]
    return result


def _expression_items(
    mapping: dict[str, str],
    defaults: dict[str, Any],
    *,
    measure_type: str,
    expression_fields: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for index, (label, column) in enumerate(mapping.items()):
        item = {
            "label": str(label),
            "column": str(column),
            "attach_to": "transcript",
            "measure_type": measure_type,
            "order_index": index,
            "entity_type": defaults.get("entity_type", ""),
            "relation_type": defaults.get("relation_type", ""),
            "id_template": defaults.get("id_template", ""),
            "value_key": defaults.get("value_key", "value"),
            "parent_tag": defaults.get("parent_tag", ""),
        }
        if measure_type == "contrast" and expression_fields:
            item.update(derive_contrast_summary_links(expression_fields, str(label), str(column)))
        items.append(item)
    return items


def _ordered_dict(items: OrderedDict[str, str] | dict[str, str]) -> dict[str, str]:
    return {str(k): str(v) for k, v in dict(items).items()}


def _read_header(data_path: Path) -> list[str]:
    with data_path.open(newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")
        return next(reader)


def normalize_source_package(
    *,
    source_dir: Path,
    dataset_id: str,
    dataset_name: str,
    organism: str,
) -> tuple[Path, Path]:
    source_dir = source_dir.resolve()
    data_path = source_dir / "DATA.tsv"
    config_path = source_dir / "config.py"
    if not data_path.exists():
        raise FileNotFoundError(data_path)
    if not config_path.exists():
        raise FileNotFoundError(config_path)

    raw_cfg: dict[str, Any] = runpy.run_path(str(config_path))
    header = _read_header(data_path)
    header_set = set(header)

    feature_groups = raw_cfg.get("FEATURE_GROUPS", {}) or {}
    feature_columns = raw_cfg.get("FEATURE_COLUMNS", []) or []
    dropdown_initials = raw_cfg.get("DROPDOWN_INITIALS", {}) or {}
    expression_fields = raw_cfg.get("EXPRESSION_FIELDS", OrderedDict())
    log2fc_fields = raw_cfg.get("LOG2FC_FIELDS", OrderedDict())
    crosslink = raw_cfg.get("CROSSLINK", {}) or {}
    tooltips = raw_cfg.get("TOOLTIPS", {}) or {}

    shared_promoted_entities = {
        "orthogroup": {
            "source_column": "orthogroup",
            "entity_type": "orthogroup",
            "id_template": "orthogroup:{value}",
            "name_template": "{value}",
            "attach_from": "gene",
            "relationship_type": "BELONGS_TO_ORTHOGROUP",
            "metadata_columns": [
                column for column in [
                    "schachtii_genes",
                ]
                if column in header_set
            ],
        }
    }
    comparative_entities = {
        key: value
        for key, value in {
            "homolog_family_member": {
                "source_column": "schachtii_genes",
                "entity_type": "bcn_gene",
                "id_template": "bcn_gene:heterodera-schachtii:{value}",
                "name_template": "{value}",
                "attach_from": "orthogroup",
                "relationship_type": "HAS_BCN_MEMBER",
                "target_organism": "Heterodera schachtii",
                "scope_tag_id": "homology-scope-cyst-nematode",
                "parser": "term_list",
            },
            "bcn_hit": {
                "source_column": "schachtii_hits",
                "entity_type": "comparative_hit",
                "id_template": "comparative_hit:cyst_nematode:{value}",
                "name_template": "{value}",
                "attach_from": "protein",
                "relationship_type": "HAS_BCN_HIT",
                "target_organism": "Heterodera schachtii",
                "reuse_target_organism_identity": True,
                "scope_tag_id": "homology-scope-cyst-nematode",
                "value_parser": "comparative_hit_label",
                "parser": "term_list",
            },
            "nematode_hit": {
                "source_column": "celegans_hits",
                "entity_type": "comparative_hit",
                "id_template": "comparative_hit:nematode:{value}",
                "name_template": "{value}",
                "attach_from": "protein",
                "relationship_type": "HAS_NEMATODE_HIT",
                "scope_tag_id": "homology-scope-nematode",
                "value_parser": "comparative_hit_label",
                "parsed_field_promotions": [
                    {
                        "field": "matched_organism",
                        "kind": "tag",
                        "parent_tag": "homology-hit-organism",
                        "id_template": "homology-hit-organism:{value_slug}",
                        "name_template": "{value}",
                        "rel_type": "TAGGED",
                    }
                ],
                "parser": "term_list",
            },
            "sp_best_hit": {
                "source_column": "sp_best_hit",
                "entity_type": "comparative_hit",
                "id_template": "comparative_hit:broad_parasitism:{value}",
                "name_template": "{value}",
                "attach_from": "protein",
                "relationship_type": "HAS_BROAD_HOMOLOGY_HIT",
                "scope_tag_id": "homology-scope-broad-parasitism",
                "value_parser": "comparative_hit_label",
                "parsed_field_promotions": [
                    {
                        "field": "matched_organism",
                        "kind": "tag",
                        "parent_tag": "homology-hit-organism",
                        "id_template": "homology-hit-organism:{value_slug}",
                        "name_template": "{value}",
                        "rel_type": "TAGGED",
                    }
                ],
                "parser": "term_list",
            },
            "nr_best_hit": {
                "source_column": "nr_best_hit",
                "entity_type": "comparative_hit",
                "id_template": "comparative_hit:broad_parasitism:{value}",
                "name_template": "{value}",
                "attach_from": "protein",
                "relationship_type": "HAS_BROAD_HOMOLOGY_HIT",
                "scope_tag_id": "homology-scope-broad-parasitism",
                "value_parser": "comparative_hit_label",
                "parsed_field_promotions": [
                    {
                        "field": "matched_organism",
                        "kind": "tag",
                        "parent_tag": "homology-hit-organism",
                        "id_template": "homology-hit-organism:{value_slug}",
                        "name_template": "{value}",
                        "rel_type": "TAGGED",
                    }
                ],
                "parser": "term_list",
            },
            "hgt_donor": {
                "source_column": "hgt_donor_id",
                "entity_type": "hgt_donor",
                "id_template": "hgt_donor:{value}",
                "name_template": "{value}",
                "attach_from": "protein",
                "relationship_type": "HAS_HGT_DONOR",
                "excluded_values": ["No"],
                "parser": "term_list",
            },
        }.items()
        if value["source_column"] in header_set
    }

    schema = {
        "contract": {
            "name": CONTRACT.get("name", "functional_genomics"),
            "version": CONTRACT.get("version", 1),
            "path": CONTRACT.get("path", ""),
            "module": CONTRACT.get("module", "genomics"),
            "core_entities": list(CONTRACT.get("core_entities", [])),
            "optional_entities": list(CONTRACT.get("optional_entities", [])),
            "required_relationships": list(CONTRACT.get("required_relationships", [])),
        },
        "raw": {
            "data_path": data_path.name,
            "delimiter": "\\t",
            "config_source": config_path.name,
            "column_order": header,
        },
        "entity_model": {
            "primary_record_entity": "transcript",
            "entities": {
                "organism": {
                    "entity_type": "organism",
                    "entity_id": f"organism:{_slug_text(organism)}",
                    "name": organism,
                },
                "dataset": {
                    "entity_type": "dataset",
                    "entity_id": f"dataset:{dataset_id}",
                    "name": dataset_name,
                },
                **(
                    {
                        "chromosome": {
                            "entity_type": "chromosome",
                            "source_column": "genome_location",
                            "id_template": f"chromosome:{_slug_text(organism)}:{{chromosome}}",
                            "name_template": "{chromosome}",
                        }
                    }
                    if "genome_location" in header_set
                    else {}
                ),
                "gene": {
                    "entity_type": "gene",
                    "id_column": "gene_name",
                    "name_column": "gene_name",
                    "metadata_columns": [c for c in GENE_COLUMNS if c in header_set and c != "gene_name"],
                },
                "transcript": {
                    "entity_type": "transcript",
                    "id_column": "uniquename",
                    "name_column": "uniquename",
                    "metadata_columns": [c for c in TRANSCRIPT_COLUMNS if c in header_set and c != "uniquename"],
                },
                "protein": {
                    "entity_type": "protein",
                    "id_template": "{uniquename}:protein",
                    "name_template": "{gene_name} protein",
                    "metadata_columns": [c for c in PROTEIN_COLUMNS if c in header_set and c != "protein_sequence"],
                    "sequence_column": "protein_sequence" if "protein_sequence" in header_set else "",
                },
            },
            "relationships": list(CONTRACT.get("required_relationships", [])),
        },
        "promoted_entities": split_shared_and_specific(
            {key: value for key, value in shared_promoted_entities.items() if value["source_column"] in header_set},
            contract_items=CONTRACT.get("promoted_entities", {}),
        ),
        "comparative_entities": split_shared_and_specific(
            comparative_entities,
            contract_items=CONTRACT.get("comparative_entities", {}),
        ),
        "annotation_bins": split_shared_and_specific(
            [item for item in ANNOTATION_BINS if item["column"] in header_set],
            contract_items=CONTRACT.get("annotation_bins", []),
        ),
        "tag_bins": split_shared_and_specific(
            [item for item in TAG_BINS if item["column"] in header_set],
            contract_items=CONTRACT.get("tag_bins", []),
        ),
        "boolean_tags": split_shared_and_specific(
            [item for item in BOOLEAN_TAGS if item["column"] in header_set],
            contract_items=CONTRACT.get("boolean_tags", []),
        ),
        "value_presence_tags": split_shared_and_specific(
            [item for item in VALUE_PRESENCE_TAGS if item["column"] in header_set],
            contract_items=CONTRACT.get("value_presence_tags", []),
        ),
        "tag_hierarchy": split_shared_and_specific(
            TAG_HIERARCHY,
            contract_items=CONTRACT.get("tag_hierarchy", {}),
        ),
        "expression_entities": {
            "summaries": split_shared_and_specific(
                _expression_items(
                    _ordered_dict(expression_fields),
                    CONTRACT.get("expression_entities", {}).get("summaries_defaults", {}),
                    measure_type="summary",
                ),
                contract_items=[],
            ),
            "contrasts": split_shared_and_specific(
                _expression_items(
                    _ordered_dict(log2fc_fields),
                    CONTRACT.get("expression_entities", {}).get("contrasts_defaults", {}),
                    measure_type="contrast",
                    expression_fields=_ordered_dict(expression_fields),
                ),
                contract_items=[],
            ),
        },
        "ui": {
            "feature_groups": feature_groups,
            "feature_columns": feature_columns,
            "dropdown_initials": dropdown_initials,
            "expression_fields": _ordered_dict(expression_fields),
            "log2fc_fields": _ordered_dict(log2fc_fields),
            "crosslink": crosslink,
            "tooltips": tooltips,
        },
    }

    dataset = {
        "dataset": {
            "id": dataset_id,
            "name": dataset_name,
            "module": "genomics",
            "extension": "functional_genomics",
            "profile": "scn_effectors",
            "organism": organism,
            "description": (
                "Local functional genomics sample for transcript-centric records that separate "
                "gene, transcript, and protein entities while preserving raw feature-group metadata."
            ),
            "raw_sources": [
                {"path": data_path.name, "kind": "tsv", "role": "primary_matrix"},
                {"path": config_path.name, "kind": "python", "role": "ui_metadata"},
            ],
            "standardized_sources": {
                "schema": "schema.yaml",
            },
            "primary_record": {
                "entity_type": "transcript",
                "id_column": "uniquename",
                "gene_id_column": "gene_name",
                "protein_id_template": "{uniquename}:protein",
            },
            "llm_context": {
                "summary": (
                    "Transcript-centric Heterodera glycines functional genomics dataset with protein-derived "
                    "annotation, localization, structure, biophysics, composition, and expression features."
                ),
                "glossary": {
                    "scn": "Soybean cyst nematode, Heterodera glycines.",
                    "bcn": "Beet cyst nematode, Heterodera schachtii.",
                    "orthogroup": "Comparative gene family assignment across related organisms.",
                    "dge": "Differential gene expression represented as log2 fold-change contrasts.",
                },
            },
            "ui_hints": {
                "default_focus": "gene-centric",
                "recommended_focus_modes": [
                    "gene-centric",
                    "functional-annotation-centric",
                    "expression-centric",
                    "effector-candidate-centric",
                ],
            },
        }
    }

    dataset_path = source_dir / "dataset.yaml"
    schema_path = source_dir / "schema.yaml"
    dataset_path.write_text(yaml.safe_dump(dataset, sort_keys=False, allow_unicode=False))
    schema_path.write_text(yaml.safe_dump(schema, sort_keys=False, allow_unicode=False))
    return dataset_path, schema_path


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Convert raw genomics files into standardized YAML metadata.")
    parser.add_argument("--source-dir", required=True)
    parser.add_argument("--dataset-id", default="genomics_scn")
    parser.add_argument("--dataset-name", default="Heterodera glycines functional genomics sample")
    parser.add_argument("--organism", default="Heterodera glycines")
    cli_args = parser.parse_args()
    normalize_source_package(
        source_dir=Path(cli_args.source_dir),
        dataset_id=cli_args.dataset_id,
        dataset_name=cli_args.dataset_name,
        organism=cli_args.organism,
    )
