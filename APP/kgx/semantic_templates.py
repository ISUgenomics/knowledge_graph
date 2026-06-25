from __future__ import annotations

from typing import Any


def load_common_semantic_templates() -> dict[str, dict[str, Any]]:
    return {
        "metadata_filter_family": {
            "id": "metadata_filter_family",
            "label": "Metadata Filter Family",
            "description": "Entity-centric metadata filtering over structured fields.",
            "optional": False,
            "concept_kind": "shared_pattern",
            "detection_hints": {
                "metadata_fields_any": ["title", "summary", "description", "name", "department", "institution"],
                "prompt_aliases": ["metadata", "record", "profile", "field"],
            },
        },
        "contact_filter_family": {
            "id": "contact_filter_family",
            "label": "Contact Filter Family",
            "description": "Structured contact fields such as email, ORCID, or website.",
            "optional": True,
            "concept_kind": "shared_pattern",
            "detection_hints": {
                "table_names": ["contact_info"],
                "field_values_any": ["email", "orcid", "website"],
                "prompt_aliases": ["contact", "email", "orcid"],
            },
        },
        "relationship_filter_family": {
            "id": "relationship_filter_family",
            "label": "Relationship Filter Family",
            "description": "Presence or filtering over typed graph relationships.",
            "optional": False,
            "concept_kind": "shared_pattern",
            "detection_hints": {
                "relationship_types_any": ["AUTHORED", "BELONGS_TO_ORTHOGROUP", "HAS_HGT_DONOR"],
                "prompt_aliases": ["with", "has", "linked to", "related to"],
            },
        },
        "evidence_operator_family": {
            "id": "evidence_operator_family",
            "label": "Evidence Operator Family",
            "description": "Evidence-style semantic operators over biological support relationships.",
            "optional": True,
            "concept_kind": "shared_pattern",
            "detection_hints": {
                "relationship_types_any": ["HAS_BROAD_HOMOLOGY_HIT", "HAS_NEMATODE_HIT", "HAS_BCN_HIT", "HAS_HGT_DONOR"],
                "prompt_aliases": ["evidence", "hit", "homology", "donor"],
            },
        },
        "bridge_operator_family": {
            "id": "bridge_operator_family",
            "label": "Bridge Operator Family",
            "description": "Two-step or multi-hop graph semantics using bridge entities or relationships.",
            "optional": True,
            "concept_kind": "shared_pattern",
            "detection_hints": {
                "relationship_types_any": ["BELONGS_TO_ORTHOGROUP"],
                "prompt_aliases": ["member", "ortholog", "group"],
            },
        },
        "dynamic_tag_family": {
            "id": "dynamic_tag_family",
            "label": "Dynamic Tag Family",
            "description": "Tag-branch semantics expanded from graph hierarchies and template rules.",
            "optional": True,
            "concept_kind": "shared_pattern",
            "detection_hints": {
                "relationship_types_any": ["TAGGED", "BROADER"],
                "prompt_aliases": ["tag", "annotation", "family"],
            },
        },
        "measurement_filter_family": {
            "id": "measurement_filter_family",
            "label": "Measurement Filter Family",
            "description": "Quantitative measurement semantics over abundance or expression-like values.",
            "optional": True,
            "concept_kind": "shared_pattern",
            "detection_hints": {
                "metadata_fields_any": ["tpm", "fpkm", "cpm", "expression", "abundance"],
                "prompt_aliases": ["expression", "abundance", "tpm", "fpkm"],
            },
        },
        "contrast_filter_family": {
            "id": "contrast_filter_family",
            "label": "Contrast Filter Family",
            "description": "Differential or comparison-style semantics with directionality and thresholds.",
            "optional": True,
            "concept_kind": "shared_pattern",
            "detection_hints": {
                "metadata_fields_any": ["logfc", "log2fc", "padj", "fdr", "pvalue", "contrast"],
                "prompt_aliases": ["contrast", "dge", "differential expression", "upregulated", "downregulated"],
            },
        },
        "scope_family": {
            "id": "scope_family",
            "label": "Scope Family",
            "description": "Secondary scoping over organism, taxonomy, tissue, or other contextual dimensions.",
            "optional": True,
            "concept_kind": "shared_pattern",
            "detection_hints": {
                "entity_types": ["organism", "taxon", "sample", "condition"],
                "prompt_aliases": ["scope", "organism", "species", "condition"],
            },
        },
        "location_filter_family": {
            "id": "location_filter_family",
            "label": "Location Filter Family",
            "description": "Coordinate, chromosome, interval, and positional filtering semantics.",
            "optional": True,
            "concept_kind": "shared_pattern",
            "detection_hints": {
                "metadata_fields_any": ["start", "end", "strand", "chromosome"],
                "prompt_aliases": ["location", "chromosome", "interval", "coordinates"],
            },
        },
        "feature_filter_family": {
            "id": "feature_filter_family",
            "label": "Feature Filter Family",
            "description": "Sequence, motif, domain, or other feature-level filtering semantics.",
            "optional": True,
            "concept_kind": "shared_pattern",
            "detection_hints": {
                "metadata_fields_any": ["length", "protein_sequence", "mrna_sequence"],
                "prompt_aliases": ["feature", "domain", "motif", "sequence"],
            },
        },
    }


def load_people_semantic_templates() -> dict[str, dict[str, Any]]:
    return {
        "identity_record": {
            "id": "identity_record",
            "label": "Identity Record",
            "description": "Person-centric identity and profile metadata filters.",
            "optional": False,
            "concept_kind": "metadata_filter_family",
            "extends": "metadata_filter_family",
            "detection_hints": {
                "entity_types": ["person"],
                "metadata_fields_any": ["title", "summary", "description", "name"],
                "prompt_aliases": ["people", "person", "profile", "bio"],
            },
        },
        "affiliation_metadata": {
            "id": "affiliation_metadata",
            "label": "Affiliation Metadata",
            "description": "Organization, department, lab, or institution metadata filters for people.",
            "optional": False,
            "concept_kind": "metadata_filter_family",
            "extends": "metadata_filter_family",
            "detection_hints": {
                "entity_types": ["person"],
                "metadata_fields_any": ["department", "institution", "organization", "lab"],
                "prompt_aliases": ["department", "institution", "organization", "affiliation"],
            },
        },
        "contact_field": {
            "id": "contact_field",
            "label": "Contact Field",
            "description": "Structured people contact information such as email, ORCID, or website fields.",
            "optional": True,
            "concept_kind": "contact_filter_family",
            "extends": "contact_filter_family",
            "detection_hints": {
                "table_names": ["contact_info"],
                "field_values_any": ["email", "orcid", "website"],
                "prompt_aliases": ["email", "orcid", "contact"],
            },
        },
        "relationship_authorship": {
            "id": "relationship_authorship",
            "label": "Authorship Relationship",
            "description": "Person-to-publication authorship and similar artifact ownership relationships.",
            "optional": True,
            "concept_kind": "relationship_filter_family",
            "extends": "relationship_filter_family",
            "detection_hints": {
                "entity_types": ["person", "publication"],
                "relationship_types_any": ["AUTHORED", "WROTE", "CONTRIBUTED_TO"],
                "prompt_aliases": ["publication", "paper", "authored"],
            },
        },
    }


def load_genomics_semantic_templates() -> dict[str, dict[str, Any]]:
    return {
        "homology_evidence": {
            "id": "homology_evidence",
            "label": "Homology Evidence",
            "description": "Protein or gene evidence linking to comparative hits for homology-style queries.",
            "optional": False,
            "concept_kind": "evidence_operator_family",
            "extends": "evidence_operator_family",
            "detection_hints": {
                "relationship_types_any": ["HAS_BROAD_HOMOLOGY_HIT", "HAS_NEMATODE_HIT", "HAS_BCN_HIT"],
                "target_types_any": ["comparative_hit"],
                "prompt_aliases": ["homology", "comparative hit", "parasitism"],
            },
        },
        "orthology_membership": {
            "id": "orthology_membership",
            "label": "Orthology Membership",
            "description": "Orthogroup membership and downstream ortholog-member expansion.",
            "optional": False,
            "concept_kind": "bridge_operator_family",
            "extends": "bridge_operator_family",
            "detection_hints": {
                "relationship_types_any": ["BELONGS_TO_ORTHOGROUP", "HAS_BCN_MEMBER"],
                "entity_types": ["gene", "orthogroup"],
                "prompt_aliases": ["ortholog", "orthogroup"],
            },
        },
        "horizontal_gene_transfer": {
            "id": "horizontal_gene_transfer",
            "label": "Horizontal Gene Transfer",
            "description": "Evidence and result-type semantics for HGT donor style questions.",
            "optional": False,
            "concept_kind": "evidence_operator_family",
            "extends": "evidence_operator_family",
            "detection_hints": {
                "relationship_types_any": ["HAS_HGT_DONOR"],
                "target_types_any": ["hgt_donor"],
                "prompt_aliases": ["hgt", "horizontal gene transfer", "donor"],
            },
        },
        "effector_evidence": {
            "id": "effector_evidence",
            "label": "Effector Evidence",
            "description": "Tag-family semantics for effectors, including organism-scoped alias expansion.",
            "optional": True,
            "concept_kind": "dynamic_tag_family",
            "extends": "dynamic_tag_family",
            "detection_hints": {
                "tag_prefixes_any": ["effector", "tag:.*effector"],
                "relationship_types_any": ["TAGGED", "BROADER"],
                "prompt_aliases": ["effector", "effectors"],
            },
        },
        "expression_measurement": {
            "id": "expression_measurement",
            "label": "Expression Measurement",
            "description": "Quantitative expression values keyed by sample, condition, tissue, or stage.",
            "optional": True,
            "concept_kind": "measurement_filter_family",
            "extends": "measurement_filter_family",
            "detection_hints": {
                "relationship_types_any": ["HAS_EXPRESSION_SUMMARY"],
                "metadata_fields_any": ["tpm", "fpkm", "cpm", "expression", "abundance"],
                "entity_types": ["expression_measure", "sample", "condition", "tissue"],
                "prompt_aliases": ["expression", "abundance", "tpm", "fpkm"],
            },
        },
        "dge_contrast": {
            "id": "dge_contrast",
            "label": "DGE Contrast",
            "description": "Differential expression contrasts with directionality and significance thresholds.",
            "optional": True,
            "concept_kind": "contrast_filter_family",
            "extends": "contrast_filter_family",
            "detection_hints": {
                "relationship_types_any": ["HAS_EXPRESSION_CONTRAST", "CONTRAST_SOURCE", "CONTRAST_TARGET"],
                "metadata_fields_any": ["logfc", "log2fc", "padj", "fdr", "pvalue", "contrast"],
                "entity_types": ["contrast_definition", "contrast", "comparison", "dge_result"],
                "prompt_aliases": ["differential expression", "dge", "contrast", "upregulated", "downregulated"],
            },
        },
        "taxonomy_scope": {
            "id": "taxonomy_scope",
            "label": "Taxonomy Scope",
            "description": "Organism or lineage scoping layered onto other biological evidence or annotations.",
            "optional": True,
            "concept_kind": "scope_family",
            "extends": "scope_family",
            "detection_hints": {
                "entity_types": ["organism", "taxon"],
                "tag_prefixes_any": ["homology-organism", "taxon", "organism"],
                "prompt_aliases": ["organism", "species", "taxon", "lineage"],
            },
        },
        "genomic_location": {
            "id": "genomic_location",
            "label": "Genomic Location",
            "description": "Chromosome, contig, scaffold, interval, and coordinate-based semantics.",
            "optional": True,
            "concept_kind": "location_filter_family",
            "extends": "location_filter_family",
            "detection_hints": {
                "entity_types": ["chromosome", "scaffold", "contig"],
                "relationship_types_any": ["HAS_CHROMOSOME"],
                "metadata_fields_any": ["start", "end", "strand", "chromosome"],
                "prompt_aliases": ["chromosome", "location", "interval", "coordinates"],
            },
        },
        "sequence_feature": {
            "id": "sequence_feature",
            "label": "Sequence Feature",
            "description": "Protein domains, motifs, sequence length, and related feature-driven queries.",
            "optional": True,
            "concept_kind": "feature_filter_family",
            "extends": "feature_filter_family",
            "detection_hints": {
                "entity_types": ["protein", "domain", "motif"],
                "relationship_types_any": ["HAS_DOMAIN", "ANNOTATED_WITH"],
                "metadata_fields_any": ["protein_sequence", "mrna_sequence", "length"],
                "prompt_aliases": ["domain", "motif", "sequence", "pfam"],
            },
        },
    }


def load_semantic_template_catalog() -> dict[str, dict[str, dict[str, Any]]]:
    return {
        "common": load_common_semantic_templates(),
        "people": load_people_semantic_templates(),
        "genomics": load_genomics_semantic_templates(),
    }


def load_domain_semantic_templates(domain_name: str | None) -> dict[str, dict[str, Any]]:
    name = str(domain_name or "").strip().lower()
    if name == "people":
        return load_people_semantic_templates()
    if name == "genomics":
        return load_genomics_semantic_templates()
    return {}


def load_domain_template_bindings(domain_name: str | None) -> dict[str, Any]:
    name = str(domain_name or "").strip().lower()
    if name == "genomics":
        return {
            "categories": {
                "effectors": [{"template_id": "effector_evidence"}],
                "homology": [{"template_id": "homology_evidence"}, {"template_id": "taxonomy_scope", "optional": True}],
                "orthology": [{"template_id": "orthology_membership"}],
                "hgt": [{"template_id": "horizontal_gene_transfer"}],
            },
            "suggested": [
                {"template_id": "expression_measurement", "reason": "Enable expression-centric NL filtering when expression values or sample entities are detected."},
                {"template_id": "dge_contrast", "reason": "Enable upregulated/downregulated and contrast-aware NL queries when DGE result semantics are present."},
                {"template_id": "genomic_location", "reason": "Enable coordinate and chromosome-style NL filtering when interval metadata is present."},
                {"template_id": "sequence_feature", "reason": "Enable domain, motif, and sequence-feature semantics when protein annotations are present."},
            ],
        }
    if name == "people":
        return {
            "categories": {
                "people": [{"template_id": "identity_record"}],
                "affiliation": [{"template_id": "affiliation_metadata"}],
            },
            "suggested": [
                {"template_id": "contact_field", "reason": "Enable contact-field NL filters when structured contact info is present."},
                {"template_id": "relationship_authorship", "reason": "Enable publication and authorship semantics when person-to-publication relationships are present."},
            ],
        }
    return {"categories": {}, "suggested": []}
