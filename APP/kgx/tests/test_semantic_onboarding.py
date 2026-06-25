from pathlib import Path

from kgx.config import load_config
from kgx.db import KnowledgeGraphDB
from kgx.semantic_onboarding import (
    generate_domain_onboarding_artifact,
    generate_domain_onboarding_report,
    propose_domain_template_candidates,
)


def test_genomics_onboarding_detects_expression_and_dge_from_config_and_graph(tmp_path: Path):
    db_path = tmp_path / "genomics-onboarding.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("gene", "gene-1", name="Gene 1", metadata={"log2fc": "2.1"})
    db.upsert_entity("expression_measure", "expr-1", name="Stage 1", metadata={"tpm": "14.2", "stage_order": 1})
    db.upsert_entity("contrast_definition", "contrast-1", name="infected_vs_control", metadata={"contrast": "infected_vs_control", "padj": "0.003"})
    db.add_relationship("gene-1", "HAS_EXPRESSION_SUMMARY", "expr-1")
    db.add_relationship("gene-1", "HAS_EXPRESSION_CONTRAST", "contrast-1")
    db.close()

    cfg = load_config(Path("/workspace/KnowledgeGraph/APP/config/genomics.yaml"))
    db = KnowledgeGraphDB(str(db_path))
    proposal = propose_domain_template_candidates(
        "genomics",
        db,
        ui_config=cfg.ui.model_dump(),
        explore_config=cfg.explore.model_dump(),
        db_build_config=cfg.db_build.model_dump(),
    )
    db.close()

    candidates = {item["template_id"]: item for item in proposal["candidates"]}

    assert candidates["expression_measurement"]["confidence"] == "high"
    assert "tpm" in candidates["expression_measurement"]["matched_signals"]["metadata_fields_any"]
    assert "expression_measure" in proposal["signals"]["entity_types"]

    assert candidates["dge_contrast"]["confidence"] == "high"
    assert "contrast_definition" in proposal["signals"]["entity_types"]
    assert "HAS_EXPRESSION_CONTRAST" in proposal["signals"]["relationship_types"]
    assert "padj" in candidates["dge_contrast"]["matched_signals"]["metadata_fields_any"]


def test_people_onboarding_detects_identity_and_affiliation_templates(tmp_path: Path):
    db_path = tmp_path / "people-onboarding.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity(
        "person",
        "person-1",
        name="Alice Example",
        metadata={"title": "PI", "department": "Biology", "institution": "ISU"},
    )
    db.close()

    cfg = load_config(Path("/workspace/KnowledgeGraph/APP/config/people.yaml"))
    db = KnowledgeGraphDB(str(db_path))
    proposal = propose_domain_template_candidates(
        "people",
        db,
        ui_config=cfg.ui.model_dump(),
        explore_config=cfg.explore.model_dump(),
        db_build_config=cfg.db_build.model_dump(),
    )
    db.close()

    candidates = {item["template_id"]: item for item in proposal["candidates"]}

    assert candidates["identity_record"]["confidence"] in {"medium", "high"}
    assert "title" in candidates["identity_record"]["matched_signals"]["metadata_fields_any"]
    assert candidates["affiliation_metadata"]["confidence"] in {"medium", "high"}
    assert "department" in candidates["affiliation_metadata"]["matched_signals"]["metadata_fields_any"]


def test_people_onboarding_detects_contact_and_authorship_templates(tmp_path: Path):
    db_path = tmp_path / "people-contact-authorship.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("person", "person-1", name="Alice Example", metadata={"title": "PI"})
    db.upsert_entity("publication", "pub-1", name="Paper 1")
    db.execute_write("INSERT INTO contact_info(entity_id, field, value) VALUES (?, ?, ?)", ("person-1", "email", "alice@example.org"))
    db.execute_write("INSERT INTO contact_info(entity_id, field, value) VALUES (?, ?, ?)", ("person-1", "orcid", "0000-0000-0000-0001"))
    db.add_relationship("person-1", "AUTHORED", "pub-1")
    db.close()

    cfg = load_config(Path("/workspace/KnowledgeGraph/APP/config/people.yaml"))
    db = KnowledgeGraphDB(str(db_path))
    proposal = propose_domain_template_candidates(
        "people",
        db,
        ui_config={**cfg.ui.model_dump(), "semantic_examples": ["email", "publication", "authored"]},
        explore_config=cfg.explore.model_dump(),
        db_build_config=cfg.db_build.model_dump(),
    )
    db.close()

    candidates = {item["template_id"]: item for item in proposal["candidates"]}

    assert candidates["contact_field"]["confidence"] == "high"
    assert "email" in candidates["contact_field"]["matched_signals"]["field_values_any"]
    assert candidates["relationship_authorship"]["confidence"] == "high"
    assert "AUTHORED" in candidates["relationship_authorship"]["matched_signals"]["relationship_types_any"]


def test_genomics_onboarding_report_groups_detected_expression_candidates(tmp_path: Path):
    db_path = tmp_path / "genomics-onboarding-report.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("gene", "gene-1", name="Gene 1", metadata={"log2fc": "2.1"})
    db.upsert_entity("expression_measure", "expr-1", name="Stage 1", metadata={"tpm": "14.2", "stage_order": 1})
    db.upsert_entity("contrast_definition", "contrast-1", name="infected_vs_control", metadata={"contrast": "infected_vs_control", "padj": "0.003"})
    db.add_relationship("gene-1", "HAS_EXPRESSION_SUMMARY", "expr-1")
    db.add_relationship("gene-1", "HAS_EXPRESSION_CONTRAST", "contrast-1")
    db.close()

    cfg = load_config(Path("/workspace/KnowledgeGraph/APP/config/genomics.yaml"))
    db = KnowledgeGraphDB(str(db_path))
    report = generate_domain_onboarding_report(
        "genomics",
        db,
        ui_config=cfg.ui.model_dump(),
        explore_config=cfg.explore.model_dump(),
        db_build_config=cfg.db_build.model_dump(),
    )
    db.close()

    assert report["domain"] == "genomics"
    assert report["summary"]["activate_count"] >= 2

    activate = {item["template_id"]: item for item in report["activate_candidates"]}
    assert activate["expression_measurement"]["draft_binding"]["category"] == "expression"
    assert activate["dge_contrast"]["draft_binding"]["category"] == "differential_expression"
    assert "tpm" in activate["expression_measurement"]["draft_binding"]["matched_signals"]["metadata_fields_any"]
    assert "padj" in activate["dge_contrast"]["draft_binding"]["matched_signals"]["metadata_fields_any"]
    assert activate["expression_measurement"]["draft_registry_fragment"]["relation_families"]["expression_measurement"][0]["rel_type"] == "HAS_EXPRESSION_SUMMARY"
    assert activate["expression_measurement"]["draft_registry_fragment"]["relation_families"]["expression_measurement"][0]["target_types"] == ["expression_measure"]
    assert activate["dge_contrast"]["draft_registry_fragment"]["relation_families"]["dge_contrast"][0]["rel_type"] == "HAS_EXPRESSION_CONTRAST"
    assert activate["dge_contrast"]["draft_registry_fragment"]["categories"]["differential_expression"]["entity_types"] == ["contrast_definition"]


def test_genomics_onboarding_artifact_merges_registry_patch(tmp_path: Path):
    db_path = tmp_path / "genomics-onboarding-artifact.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("gene", "gene-1", name="Gene 1", metadata={"log2fc": "2.1"})
    db.upsert_entity("expression_measure", "expr-1", name="Stage 1", metadata={"tpm": "14.2", "stage_order": 1})
    db.upsert_entity("contrast_definition", "contrast-1", name="infected_vs_control", metadata={"contrast": "infected_vs_control", "padj": "0.003"})
    db.add_relationship("gene-1", "HAS_EXPRESSION_SUMMARY", "expr-1")
    db.add_relationship("gene-1", "HAS_EXPRESSION_CONTRAST", "contrast-1")
    db.close()

    cfg = load_config(Path("/workspace/KnowledgeGraph/APP/config/genomics.yaml"))
    db = KnowledgeGraphDB(str(db_path))
    artifact = generate_domain_onboarding_artifact(
        "genomics",
        db,
        ui_config=cfg.ui.model_dump(),
        explore_config=cfg.explore.model_dump(),
        db_build_config=cfg.db_build.model_dump(),
    )
    db.close()

    assert artifact["artifact_version"] == "semantics-onboarding.v1"
    assert artifact["review_status"] == "draft"
    assert artifact["summary"]["activate_count"] >= 2
    assert len(artifact["proposed_registry_fragments"]) >= 2

    patch = artifact["proposed_registry_patch"]
    assert "expression" in patch["categories"]
    assert "differential_expression" in patch["categories"]
    assert patch["relation_families"]["expression_measurement"][0]["rel_type"] == "HAS_EXPRESSION_SUMMARY"
    assert patch["relation_families"]["dge_contrast"][0]["rel_type"] == "HAS_EXPRESSION_CONTRAST"
    assert patch["operators"]["condition_handlers"]["expression_measurement"] == "expression_measurement"
    assert patch["operators"]["condition_handlers"]["dge_contrast"] == "dge_contrast"


def test_people_onboarding_artifact_emits_contact_and_authorship_fragments(tmp_path: Path):
    db_path = tmp_path / "people-onboarding-artifact.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("person", "person-1", name="Alice Example", metadata={"title": "PI"})
    db.upsert_entity("publication", "pub-1", name="Paper 1")
    db.execute_write("INSERT INTO contact_info(entity_id, field, value) VALUES (?, ?, ?)", ("person-1", "email", "alice@example.org"))
    db.execute_write("INSERT INTO contact_info(entity_id, field, value) VALUES (?, ?, ?)", ("person-1", "orcid", "0000-0000-0000-0001"))
    db.add_relationship("person-1", "AUTHORED", "pub-1")
    db.close()

    cfg = load_config(Path("/workspace/KnowledgeGraph/APP/config/people.yaml"))
    db = KnowledgeGraphDB(str(db_path))
    artifact = generate_domain_onboarding_artifact(
        "people",
        db,
        ui_config={**cfg.ui.model_dump(), "semantic_examples": ["email", "publication", "authored"]},
        explore_config=cfg.explore.model_dump(),
        db_build_config=cfg.db_build.model_dump(),
    )
    db.close()

    activate = {item["template_id"]: item for item in artifact["decisions"]["activate_candidates"]}
    assert "contact_field" in activate
    assert "relationship_authorship" in activate

    patch = artifact["proposed_registry_patch"]
    assert patch["operators"]["specs"]["contact_filters"]["email"]["field"] == "email"
    assert patch["operators"]["specs"]["contact_filters"]["email"]["display"]["alias"] == "email"
    assert patch["operators"]["specs"]["relationship_filters"]["authored_publication"]["rel_type"] == "AUTHORED"
    assert patch["operators"]["specs"]["relationship_filters"]["authored_publication"]["display"]["alias"] == "publication_name"
    assert patch["categories"]["contact"]["fields"] == ["email", "orcid"]


def test_genomics_onboarding_artifact_emits_location_and_sequence_fragments(tmp_path: Path):
    db_path = tmp_path / "genomics-location-sequence-artifact.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("organism", "organism-1", name="Org 1")
    db.upsert_entity("chromosome", "chr-1", name="Chr 1", metadata={"chromosome": "1", "start": 10, "end": 20, "strand": "+"})
    db.upsert_entity("protein", "prot-1", name="Protein 1", metadata={"protein_sequence": "MSTN", "length": 4})
    db.upsert_entity("domain", "dom-1", name="PF00001")
    db.add_relationship("organism-1", "HAS_CHROMOSOME", "chr-1")
    db.add_relationship("prot-1", "HAS_DOMAIN", "dom-1")
    db.close()

    cfg = load_config(Path("/workspace/KnowledgeGraph/APP/config/genomics.yaml"))
    db = KnowledgeGraphDB(str(db_path))
    artifact = generate_domain_onboarding_artifact(
        "genomics",
        db,
        ui_config={**cfg.ui.model_dump(), "semantic_examples": ["chromosome coordinates", "pfam domain sequence"]},
        explore_config=cfg.explore.model_dump(),
        db_build_config=cfg.db_build.model_dump(),
    )
    db.close()

    activate = {item["template_id"]: item for item in artifact["decisions"]["activate_candidates"]}
    assert "genomic_location" in activate
    assert "sequence_feature" in activate

    patch = artifact["proposed_registry_patch"]
    assert patch["categories"]["location"]["entity_types"] == ["chromosome"]
    assert "start" in patch["metadata_hints"]["location"]["preferred_fields"]
    assert "protein_sequence" in patch["metadata_hints"]["sequence"]["preferred_fields"]
    assert "HAS_DOMAIN" in patch["categories"]["sequence"]["relationship_types"]
    assert patch["operators"]["specs"]["metadata_filters"]["chromosome"]["display"]["alias"] == "chromosome"
    assert patch["operators"]["specs"]["metadata_filters"]["protein_sequence"]["display"]["alias"] == "protein_sequence"
