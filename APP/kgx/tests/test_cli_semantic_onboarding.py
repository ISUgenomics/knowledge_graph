import json
from pathlib import Path

from kgx.cli import _build_semantic_onboarding_artifact, _build_semantic_onboarding_patch
from kgx.config import load_config
from kgx.db import KnowledgeGraphDB


def test_build_semantic_onboarding_artifact_from_genomics_config(tmp_path: Path):
    db_path = tmp_path / "cli-genomics-onboarding.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("gene", "gene-1", name="Gene 1", metadata={"log2fc": "2.1"})
    db.upsert_entity("expression_measure", "expr-1", name="Stage 1", metadata={"tpm": "14.2", "stage_order": 1})
    db.upsert_entity("contrast_definition", "contrast-1", name="infected_vs_control", metadata={"contrast": "infected_vs_control", "padj": "0.003"})
    db.add_relationship("gene-1", "HAS_EXPRESSION_SUMMARY", "expr-1")
    db.add_relationship("gene-1", "HAS_EXPRESSION_CONTRAST", "contrast-1")
    db.close()

    cfg = load_config(Path("/workspace/KnowledgeGraph/APP/config/genomics.yaml"))
    cfg.db.path = str(db_path)

    artifact = _build_semantic_onboarding_artifact(cfg, db_path)

    assert artifact["artifact_version"] == "semantics-onboarding.v1"
    assert artifact["domain"] == "genomics"
    assert artifact["summary"]["activate_count"] >= 2
    assert artifact["proposed_registry_patch"]["relation_families"]["expression_measurement"][0]["rel_type"] == "HAS_EXPRESSION_SUMMARY"
    assert artifact["proposed_registry_patch"]["relation_families"]["dge_contrast"][0]["rel_type"] == "HAS_EXPRESSION_CONTRAST"


def test_semantic_onboarding_artifact_is_json_serializable(tmp_path: Path):
    db_path = tmp_path / "cli-people-onboarding.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("person", "person-1", name="Alice Example", metadata={"title": "PI", "department": "Biology"})
    db.close()

    cfg = load_config(Path("/workspace/KnowledgeGraph/APP/config/people.yaml"))
    cfg.db.path = str(db_path)

    artifact = _build_semantic_onboarding_artifact(cfg, db_path)
    rendered = json.dumps(artifact, indent=2, sort_keys=True)

    assert '"artifact_version": "semantics-onboarding.v1"' in rendered
    assert '"domain": "people"' in rendered


def test_build_semantic_onboarding_patch_from_genomics_config(tmp_path: Path):
    db_path = tmp_path / "cli-genomics-patch.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("gene", "gene-1", name="Gene 1", metadata={"log2fc": "2.1"})
    db.upsert_entity("expression_measure", "expr-1", name="Stage 1", metadata={"tpm": "14.2", "stage_order": 1})
    db.upsert_entity("contrast_definition", "contrast-1", name="infected_vs_control", metadata={"contrast": "infected_vs_control", "padj": "0.003"})
    db.add_relationship("gene-1", "HAS_EXPRESSION_SUMMARY", "expr-1")
    db.add_relationship("gene-1", "HAS_EXPRESSION_CONTRAST", "contrast-1")
    db.close()

    cfg = load_config(Path("/workspace/KnowledgeGraph/APP/config/genomics.yaml"))
    cfg.db.path = str(db_path)

    patch = _build_semantic_onboarding_patch(cfg, db_path)

    assert patch["artifact_version"] == "semantic-registry-patch.v1"
    assert patch["domain"] == "genomics"
    assert patch["summary"]["activate_count"] >= 2
    assert patch["registry_patch"]["relation_families"]["expression_measurement"][0]["rel_type"] == "HAS_EXPRESSION_SUMMARY"
    assert patch["registry_patch"]["relation_families"]["dge_contrast"][0]["rel_type"] == "HAS_EXPRESSION_CONTRAST"
