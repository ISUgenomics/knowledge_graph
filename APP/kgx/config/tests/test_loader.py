from pathlib import Path
import tempfile

from kgx.config.loader import KGXConfig


def test_db_build_tagging_defaults_present():
    cfg = KGXConfig()

    assert cfg.db_build.visualization.timeline.weak_order_fields == ["created_at", "updated_at", "pmid"]
    assert "BROADER" in cfg.db_build.visualization.hierarchical.relation_classes.hierarchy
    assert cfg.db_build.tagging.ontology.registry_path == ""
    assert cfg.db_build.tagging.ontology.aliases_path == ""
    assert cfg.db_build.tagging.ontology.hierarchy_path == ""
    assert cfg.db_build.tagging.ontology.apply_on_build is False
    assert cfg.db_build.tagging.person_tag_promotion.enabled is False


def test_db_build_tagging_custom_values_parse():
    cfg = KGXConfig.model_validate({
        "db_build": {
            "tagging": {
                "ontology": {
                    "registry_path": "../../sample_data/1_source/tags/tag-registry.md",
                    "aliases_path": "../../sample_data/1_source/tags/tag-aliases.md",
                    "hierarchy_path": "../../sample_data/1_source/tags/tag-ontology.json",
                    "apply_on_build": True,
                },
                "entity_policies": {
                    "person": {
                        "enabled": True,
                        "relationship_type": "TAGGED",
                        "default_category": "topic",
                    },
                    "publication": {
                        "enabled": True,
                        "relationship_type": "TAGGED",
                        "default_category": "topic",
                    },
                },
                "person_tag_promotion": {
                    "enabled": True,
                    "source_entity_type": "publication",
                    "source_relation_type": "AUTHORED",
                    "annotation_relation_type": "TAGGED",
                    "hierarchy_relation_type": "BROADER",
                    "min_support_count": 3,
                    "include_ancestor_tags": True,
                    "max_tags_per_person": 12,
                },
            }
        }
    })

    assert cfg.db_build.tagging.ontology.apply_on_build is True
    assert cfg.db_build.tagging.entity_policies["person"].enabled is True
    assert cfg.db_build.tagging.entity_policies["publication"].relationship_type == "TAGGED"
    assert cfg.db_build.tagging.person_tag_promotion.min_support_count == 3
    assert cfg.db_build.tagging.person_tag_promotion.include_ancestor_tags is True


def test_person_acknowledgements_derived_target_fields_parse():
    cfg = KGXConfig.model_validate({
        "db_build": {
            "extensions": {
                "isu_profile": {
                    "institution": "Iowa State University",
                    "institution_short": "ISU",
                    "email_domain": "iastate.edu",
                    "require_kerberos": False,
                    "kerberos_principal_hint": "",
                    "ldap_server": "",
                    "ldap_base": "",
                    "directory_label": "LDAP",
                    "profile_label": "profile",
                    "employee_noun": "employee",
                    "employee_type_label": "Employee Type",
                    "directory_title_label": "Directory Title",
                    "directory_department_label": "Directory Department",
                    "directory_email_label": "Directory Email",
                    "api_base_url": "",
                    "laureates_dataset_url": "",
                    "source_snapshot_dir": "/tmp/people_isu_biotech",
                    "profile_url_templates": [],
                    "staff_listing_urls": [],
                    "filter_openalex_by_institution": False,
                    "filter_pubmed_by_institution": False,
                    "filter_orcid_by_institution": False,
                    "use_nobel_affiliation_for_scholarly_filters": False,
                    "acknowledgements": {
                        "enabled": True,
                        "derive_targets_from_office_structure": True,
                        "source_snapshot_dir": "/tmp/people_isu_biotech",
                        "targets": [
                            {
                                "entity_id": "high-resolution-microscopy-facility",
                                "aliases": ["Roy J. Carver High-Resolution Microscopy Facility"],
                            }
                        ],
                    },
                }
            }
        }
    })

    ack = cfg.db_build.extensions["isu_profile"].acknowledgements
    assert ack is not None
    assert ack.derive_targets_from_office_structure is True
    assert ack.source_snapshot_dir == "/tmp/people_isu_biotech"


def test_skill_contexts_parse():
    cfg = KGXConfig.model_validate({
        "db_build": {
            "skill_contexts": {
                "genomics": {
                    "help_prompts": [
                        "Build a local genomics graph from standardized TSV and YAML sources.",
                    ],
                    "settings": {
                        "module": "genomics",
                        "primary_record_entity": "transcript",
                    },
                    "source_policy": {
                        "official_only": False,
                    },
                }
            }
        }
    })

    genomics = cfg.db_build.skill_contexts["genomics"]
    assert genomics.settings["module"] == "genomics"
    assert genomics.help_prompts[0].startswith("Build a local genomics graph")
    assert genomics.source_policy is not None
    assert genomics.source_policy.official_only is False


def test_hierarchical_layout_defaults_present():
    cfg = KGXConfig()

    assert cfg.ui.layouts is not None
    assert cfg.ui.layouts.hierarchical is not None
    assert "BROADER" in cfg.ui.layouts.hierarchical.relation_classes.hierarchy
    assert cfg.ui.layouts.hierarchical.bands.person_y == 0.0
    assert cfg.ui.layouts.hierarchical.annotation_driver_default is True


def test_explore_presets_parse():
    cfg = KGXConfig.model_validate({
        "explore": {
            "mediator_type": "orthogroup",
            "mediator_edge": "BELONGS_TO_ORTHOGROUP",
            "derived_edge_type": "SHARES_ORTHOGROUP",
            "preserve_node_types": ["organism"],
            "include_rel_types": ["FROM_ORGANISM", "BELONGS_TO_ORTHOGROUP"],
            "include_rel_patterns": [
                {
                    "rel_type": "FROM_ORGANISM",
                    "source_type": "bcn_gene",
                    "target_type": "organism",
                }
            ],
            "default_hidden_rel_types": [],
            "derived_path_edges": [
                {
                    "source_type": "gene",
                    "via_type": "transcript",
                    "target_type": "protein",
                    "first_rel_type": "HAS_TRANSCRIPT",
                    "second_rel_type": "TRANSLATED_TO",
                    "edge_type": "GENE_PRODUCT",
                }
            ],
            "hierarchy_edge": "BROADER",
            "annotation_edge": "TAGGED",
            "skipped_rel_types": ["IN_DATASET"],
            "active_preset": "gene_centric",
            "presets": {
                "gene_centric": {
                    "label": "Gene-centric",
                    "include_node_types": ["gene", "transcript", "protein", "orthogroup", "tag"],
                    "include_rel_types": ["FROM_ORGANISM", "HAS_TRANSCRIPT"],
                    "default_hidden_rel_types": ["TRANSLATED_TO"],
                },
                "annotation_centric": {
                    "label": "Annotation-centric",
                    "include_node_types": ["gene", "protein", "tag"],
                    "include_rel_types": ["FROM_ORGANISM", "HAS_ANNOTATION", "TAGGED"],
                    "preserve_node_types": ["gene"],
                    "derived_path_edges": [
                        {
                            "source_type": "gene",
                            "via_type": "transcript",
                            "target_type": "protein",
                            "first_rel_type": "HAS_TRANSCRIPT",
                            "second_rel_type": "TRANSLATED_TO",
                            "edge_type": "GENE_PRODUCT",
                        }
                    ],
                    "included_tag_roots": ["functional-annotations"],
                    "mediator_type": "tag",
                    "mediator_edge": "TAGGED",
                    "skipped_rel_types": ["IN_DATASET", "BROADER"],
                },
            },
        }
    })

    assert cfg.explore.active_preset == "gene_centric"
    assert cfg.explore.preserve_node_types == ["organism"]
    assert cfg.explore.include_rel_types == ["FROM_ORGANISM", "BELONGS_TO_ORTHOGROUP"]
    assert cfg.explore.include_rel_patterns[0]["source_type"] == "bcn_gene"
    assert cfg.explore.default_hidden_rel_types == []
    assert cfg.explore.derived_path_edges[0]["edge_type"] == "GENE_PRODUCT"
    assert cfg.explore.presets["annotation_centric"].included_tag_roots == ["functional-annotations"]
    assert cfg.explore.presets["gene_centric"].include_rel_types == ["FROM_ORGANISM", "HAS_TRANSCRIPT"]
    assert cfg.explore.presets["gene_centric"].default_hidden_rel_types == ["TRANSLATED_TO"]
    assert cfg.explore.presets["annotation_centric"].preserve_node_types == ["gene"]
    assert cfg.explore.presets["annotation_centric"].mediator_type == "tag"


def test_hierarchical_layout_custom_values_parse():
    cfg = KGXConfig.model_validate({
        "ui": {
            "layouts": {
                "hierarchical": {
                    "profile_name": "people",
                    "relation_classes": {
                        "hierarchy": ["BROADER"],
                        "structural": ["AUTHORED", "WON"],
                        "affiliation": ["MEMBER_OF"],
                        "annotation": ["TAGGED"],
                        "associative": ["COAUTHOR"],
                    },
                    "type_families": {
                        "award": "artifact",
                    },
                    "type_aliases": {
                        "bcn_gene": "gene",
                    },
                    "type_levels": {
                        "organization": 1.0,
                        "person": 0.0,
                        "publication": -1.0,
                    },
                    "bands": {
                        "organization_y": 0.5,
                        "person_y": 0.0,
                        "publication_y": -0.75,
                        "tag_domain_y": -1.4,
                        "tag_field_y": -2.0,
                        "tag_topic_y": -2.7,
                    },
                    "annotation_driver_default": False,
                    "mediator_one_side_default": True,
                    "strict_bands_default": True,
                }
            }
        }
    })

    assert cfg.ui.layouts is not None
    assert cfg.ui.layouts.hierarchical is not None
    assert cfg.ui.layouts.hierarchical.relation_classes.structural == ["AUTHORED", "WON"]
    assert cfg.ui.layouts.hierarchical.type_families["award"] == "artifact"
    assert cfg.ui.layouts.hierarchical.type_aliases["bcn_gene"] == "gene"
    assert cfg.ui.layouts.hierarchical.type_levels["organization"] == 1.0
    assert cfg.ui.layouts.hierarchical.bands.publication_y == -0.75
    assert cfg.ui.layouts.hierarchical.mediator_one_side_default is True
    assert cfg.ui.layouts.hierarchical.strict_bands_default is True


def test_visualization_contract_custom_values_parse():
    cfg = KGXConfig.model_validate({
        "db_build": {
                "visualization": {
                    "timeline": {
                        "preferred_anchor_types": ["award", "publication"],
                        "anchor_order_fields": {
                            "award": ["award_year"],
                            "publication": ["year"],
                        },
                        "field_aliases": {
                            "award_year": ["year"],
                        },
                        "weak_order_fields": ["created_at"],
                        "required_metadata_by_type": {
                            "publication": ["year"],
                    },
                },
                "hierarchical": {
                    "relation_classes": {
                        "hierarchy": ["BROADER"],
                        "structural": ["AUTHORED"],
                        "affiliation": ["MEMBER_OF"],
                        "annotation": ["TAGGED"],
                        "associative": ["COAUTHOR"],
                    },
                    "type_families": {
                        "award": "artifact",
                    },
                    "type_aliases": {
                        "bcn_gene": "gene",
                    },
                    "type_levels": {
                        "award": -1.5,
                    },
                    "bands": {
                        "organization_y": 0.5,
                        "person_y": 0.0,
                        "publication_y": -0.75,
                        "tag_domain_y": -1.4,
                        "tag_field_y": -2.0,
                        "tag_topic_y": -2.7,
                    },
                    "annotation_driver_default": False,
                    "mediator_one_side_default": True,
                    "strict_bands_default": True,
                },
            }
        }
    })

    assert cfg.db_build.visualization.timeline.preferred_anchor_types == ["award", "publication"]
    assert cfg.db_build.visualization.timeline.anchor_order_fields["publication"] == ["year"]
    assert cfg.db_build.visualization.timeline.field_aliases["award_year"] == ["year"]
    assert cfg.db_build.visualization.hierarchical.type_families["award"] == "artifact"
    assert cfg.db_build.visualization.hierarchical.type_aliases["bcn_gene"] == "gene"
    assert cfg.db_build.visualization.hierarchical.type_levels["award"] == -1.5
    assert cfg.db_build.visualization.hierarchical.strict_bands_default is True


def test_load_config_applies_visualization_fallbacks(tmp_path: Path):
    cfg_path = tmp_path / "cfg.yaml"
    cfg_path.write_text(
        """
db:
  path: ./vault.db
ui:
  layouts:
    timeline:
      enabled: true
    hierarchical:
      enabled: true
db_build:
  visualization:
    timeline:
      preferred_anchor_types: [award]
      anchor_order_fields:
        award: [award_year]
    hierarchical:
      type_families:
        award: artifact
      type_aliases:
        bcn_gene: gene
      type_levels:
        award: -1.5
      relation_classes:
        hierarchy: [BROADER]
        structural: [AUTHORED]
        affiliation: [MEMBER_OF]
        annotation: [TAGGED]
        associative: [COAUTHOR]
      bands:
        organization_y: 0.5
        person_y: 0.0
        publication_y: -0.75
        tag_domain_y: -1.4
        tag_field_y: -2.0
        tag_topic_y: -2.7
      annotation_driver_default: false
      mediator_one_side_default: true
      strict_bands_default: true
"""
    )

    from kgx.config.loader import load_config

    cfg = load_config(cfg_path)
    assert cfg.ui.layouts is not None
    assert cfg.ui.layouts.timeline is not None
    assert cfg.ui.layouts.timeline.anchor_type == "award"
    assert cfg.ui.layouts.timeline.order.field_candidates == ["award_year"]
    assert cfg.ui.layouts.hierarchical is not None
    assert cfg.ui.layouts.hierarchical.type_families["award"] == "artifact"
    assert cfg.ui.layouts.hierarchical.type_aliases["bcn_gene"] == "gene"
    assert cfg.ui.layouts.hierarchical.type_levels["award"] == -1.5
    assert cfg.ui.layouts.hierarchical.relation_classes.structural == ["AUTHORED"]
    assert cfg.ui.layouts.hierarchical.strict_bands_default is True
