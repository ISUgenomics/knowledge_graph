import json
from pathlib import Path

from kgx.cli import _build_semantic_onboarding_patch
from kgx.config import load_config
from kgx.db import KnowledgeGraphDB
from kgx.genomics_source import load_semantic_registry


def test_genomics_registry_can_load_generated_overlay_patch(tmp_path: Path):
    db_path = tmp_path / "overlay-genomics.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("gene", "gene-1", name="Gene 1", metadata={"log2fc": "2.1"})
    db.upsert_entity("expression_measure", "expr-1", name="Stage 1", metadata={"tpm": "14.2", "stage_order": 1})
    db.upsert_entity("contrast_definition", "contrast-1", name="infected_vs_control", metadata={"contrast": "infected_vs_control", "padj": "0.003"})
    db.add_relationship("gene-1", "HAS_EXPRESSION_SUMMARY", "expr-1")
    db.add_relationship("gene-1", "HAS_EXPRESSION_CONTRAST", "contrast-1")
    db.close()

    cfg = load_config(Path("/workspace/KnowledgeGraph/APP/config/genomics.yaml"))
    cfg.db.path = str(db_path)

    patch_artifact = _build_semantic_onboarding_patch(cfg, db_path)
    overlay_path = tmp_path / "semantic-overlay.json"
    overlay_path.write_text(json.dumps(patch_artifact, indent=2), encoding="utf-8")

    registry = load_semantic_registry({"semantic_registry_overlay": str(overlay_path)})

    assert "expression" in registry["categories"]
    assert "differential_expression" in registry["categories"]
    assert registry["relation_families"]["expression_measurement"][0]["rel_type"] == "HAS_EXPRESSION_SUMMARY"
    assert registry["relation_families"]["dge_contrast"][0]["rel_type"] == "HAS_EXPRESSION_CONTRAST"
    assert registry["operators"]["condition_handlers"]["expression_measurement"] == "expression_measurement"
    assert registry["operators"]["condition_handlers"]["dge_contrast"] == "dge_contrast"
