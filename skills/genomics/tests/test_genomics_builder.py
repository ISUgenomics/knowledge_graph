from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
APP_DIR = ROOT / "APP"
SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from build_genomics_dataset import build_dataset
from infer_source_package import infer_source_package
from apply_schema_patch import apply_schema_patch
from genomics_contract import combine_section
from normalize_source import normalize_source_package
from propose_schema_patch import propose_schema_patch
from review_source_package import review_source_package
from kgx.db import KnowledgeGraphDB


def test_normalize_source_package_emits_machine_readable_metadata(tmp_path: Path):
    source_dir = ROOT / "sample_data" / "1_source" / "genomics_scn"
    dataset_path, schema_path = normalize_source_package(
        source_dir=source_dir,
        dataset_id="genomics_scn",
        dataset_name="Heterodera glycines functional genomics sample",
        organism="Heterodera glycines",
    )

    assert dataset_path.exists()
    assert schema_path.exists()
    text = schema_path.read_text()
    assert "feature_groups:" in text
    assert "primary_record_entity: transcript" in text
    assert "contract:" in text
    assert "core_entities:" in text
    schema = yaml.safe_load(text)
    assert "chromosome" in schema["entity_model"]["entities"]
    orthogroup_spec = combine_section(schema["promoted_entities"])["orthogroup"]
    assert "glycines_gene_count" in orthogroup_spec["metadata_columns"]
    assert "schachtii_gene_count" in orthogroup_spec["metadata_columns"]
    comparative_entities = combine_section(schema["comparative_entities"])
    assert "homolog_family_member" in comparative_entities
    assert "bcn_hit" in comparative_entities
    assert "nematode_hit" in comparative_entities
    assert "sp_best_hit" in comparative_entities
    assert "nr_best_hit" in comparative_entities
    contrast_specs = schema["expression_entities"]["contrasts"]["dataset_specific"]
    egg_vs_ppj2 = next(spec for spec in contrast_specs if spec["column"] == "dge_egg_ppj2")
    assert egg_vs_ppj2["source_summary_column"] == "avg_egg"
    assert egg_vs_ppj2["target_summary_column"] == "avg_ppj2"


def test_build_dataset_creates_core_entities_and_relationships(tmp_path: Path):
    source_dir = ROOT / "sample_data" / "1_source" / "genomics_scn"
    normalize_source_package(
        source_dir=source_dir,
        dataset_id="genomics_scn",
        dataset_name="Heterodera glycines functional genomics sample",
        organism="Heterodera glycines",
    )
    db_path = tmp_path / "genomics_scn.db"
    vault_dir = tmp_path / "vault"
    build_dataset(source_dir=source_dir, db_path=db_path, fresh=True, vault_output_dir=vault_dir)

    with KnowledgeGraphDB(db_path) as db:
        stats = db.stats()
        assert stats["entities"]["organism"] == 2
        assert stats["entities"]["dataset"] == 1
        assert stats["entities"]["chromosome"] == 1
        assert stats["entities"]["gene"] == 8
        assert stats["entities"]["transcript"] == 9
        assert stats["entities"]["protein"] == 9
        assert stats["entities"]["bcn_gene"] > 0
        assert stats["entities"]["comparative_hit"] > 0
        assert stats["entities"]["annotation_term"] > 0
        assert stats["entities"]["localization_call"] > 0
        assert stats["entities"]["prediction_call"] > 0
        assert stats["entities"]["expression_measure"] > 0
        assert stats["entities"]["contrast_definition"] > 0
        assert stats["relationships"]["ABOUT_ORGANISM"] == 1
        assert stats["relationships"]["FROM_ORGANISM"] > 0
        assert stats["relationships"]["HAS_CHROMOSOME"] == 1
        assert stats["relationships"]["HAS_GENE"] == 8
        assert stats["relationships"]["HAS_BCN_MEMBER"] > 0
        assert stats["relationships"]["HAS_BCN_HIT"] > 0
        assert stats["relationships"].get("HAS_NEMATODE_HIT", 0) >= 0
        assert stats["relationships"]["HAS_BROAD_HOMOLOGY_HIT"] > 0
        assert stats["relationships"]["HAS_TRANSCRIPT"] == 9
        assert stats["relationships"]["TRANSLATED_TO"] == 9
        assert stats["relationships"]["IN_DATASET"] == 8
        assert stats["relationships"]["HAS_ANNOTATION"] > 0
        assert stats["relationships"]["HAS_LOCALIZATION"] > 0
        assert stats["relationships"]["HAS_PREDICTION"] > 0
        assert stats["relationships"]["HAS_EXPRESSION_SUMMARY"] > 0
        assert stats["relationships"]["HAS_EXPRESSION_CONTRAST"] > 0
        assert stats["relationships"]["CONTRAST_SOURCE"] > 0
        assert stats["relationships"]["CONTRAST_TARGET"] > 0
        assert "tag" in stats["entities"]

        broad_go_tag = db.get_entity("go-annotation")
        assert broad_go_tag is not None
        promoted_go_term = db.get_entity("annotation:go:0008150")
        assert promoted_go_term is not None
        ann_rels = db.get_relationships("hg_chrom1_tn10mrna_1:protein", "HAS_ANNOTATION", direction="outgoing")
        assert any(rel["target_id"] == "annotation:go:0008150" for rel in ann_rels)
        promoted_go_rels = db.get_relationships("annotation:go:0008150", "TAGGED", direction="outgoing")
        assert any(rel["target_id"] == "go-annotation" for rel in promoted_go_rels)
        loc_rels = db.get_relationships("hg_chrom1_tn10mrna_1:protein", "HAS_LOCALIZATION", direction="outgoing")
        assert any(rel["target_id"].startswith("localization:") for rel in loc_rels)
        pred_rels = db.get_relationships("hg_chrom1_tn10mrna_1:protein", "HAS_PREDICTION", direction="outgoing")
        assert any(rel["target_id"].startswith("prediction:") for rel in pred_rels)
        expr_rels = db.get_relationships("hg_chrom1_tn10mrna_1", "HAS_EXPRESSION_SUMMARY", direction="outgoing")
        assert any(rel["target_id"] == "expression_measure:j3" and rel["metadata"].get("expression_value") is not None for rel in expr_rels)
        contrast_rels = db.get_relationships("hg_chrom1_tn10mrna_1", "HAS_EXPRESSION_CONTRAST", direction="outgoing")
        assert any(rel["target_id"] == "contrast_definition:j3-vs-j4" and rel["metadata"].get("log2_fold_change") is not None for rel in contrast_rels)
        contrast_source_rels = db.get_relationships("contrast_definition:j3-vs-j4", "CONTRAST_SOURCE", direction="outgoing")
        assert any(rel["target_id"] == "expression_measure:j3" for rel in contrast_source_rels)
        contrast_target_rels = db.get_relationships("contrast_definition:j3-vs-j4", "CONTRAST_TARGET", direction="outgoing")
        assert any(rel["target_id"] == "expression_measure:j4" for rel in contrast_target_rels)
        gene_rels = db.get_relationships("hg_chrom1_tn10gene_960", "HAS_TRANSCRIPT", direction="outgoing")
        assert len(gene_rels) == 2
        chromosome_rels = db.get_relationships("organism:heterodera-glycines", "HAS_CHROMOSOME", direction="outgoing")
        assert any(rel["target_id"] == "chromosome:heterodera-glycines:chr1" for rel in chromosome_rels)
        gene_chromosome_rels = db.get_relationships("chromosome:heterodera-glycines:chr1", "HAS_GENE", direction="outgoing")
        assert len(gene_chromosome_rels) == 8
        dataset_incoming = db.get_relationships("dataset:genomics_scn", "IN_DATASET", direction="incoming")
        assert len(dataset_incoming) == 8
        assert all(":protein" not in rel["source_id"] and "mrna" not in rel["source_id"] for rel in dataset_incoming)
        orthogroup = db.get_entity("orthogroup:og0005552")
        assert orthogroup is not None
        assert orthogroup["metadata"]["glycines_gene_count"] == 1
        assert orthogroup["metadata"]["schachtii_gene_count"] == 1
        assert orthogroup["metadata"]["local_gene_count"] == 1
        assert orthogroup["metadata"]["local_gene_ids"] == ["hg_chrom1_tn10gene_10"]
        assert orthogroup["metadata"]["schachtii_genes"] == ["Hsc_gene_14957.t1"]
        bcn_gene = db.get_entity("bcn_gene:heterodera-schachtii:hsc_gene_14957.t1")
        assert bcn_gene is not None
        assert bcn_gene["metadata"]["organism"] == "Heterodera schachtii"
        assert bcn_gene["metadata"]["source_columns"] == ["schachtii_genes", "schachtii_hits"]
        assert bcn_gene["metadata"]["relationship_types"] == ["HAS_BCN_HIT", "HAS_BCN_MEMBER"]
        assert bcn_gene["metadata"]["scope_tag_ids"] == ["homology-scope-cyst-nematode"]
        schachtii = db.get_entity("organism:heterodera-schachtii")
        assert schachtii is not None
        bcn_org_rels = db.get_relationships("bcn_gene:heterodera-schachtii:hsc_gene_14957.t1", "FROM_ORGANISM", direction="outgoing")
        assert any(rel["target_id"] == "organism:heterodera-schachtii" for rel in bcn_org_rels)
        family_member_rels = db.get_relationships("orthogroup:og0005552", "HAS_BCN_MEMBER", direction="outgoing")
        assert any(rel["target_id"] == "bcn_gene:heterodera-schachtii:hsc_gene_14957.t1" for rel in family_member_rels)
        bcn_hit_rels = db.get_relationships("hg_chrom1_tn10mrna_10:protein", "HAS_BCN_HIT", direction="outgoing")
        assert any(rel["target_id"] == "bcn_gene:heterodera-schachtii:hsc_gene_14957.t1" for rel in bcn_hit_rels)
        singleton_bcn_hit = db.get_entity("comparative_hit:cyst_nematode:hsc-gene-4672-t1")
        assert singleton_bcn_hit is not None
        assert singleton_bcn_hit["metadata"]["source_columns"] == ["schachtii_hits"]
        assert singleton_bcn_hit["metadata"]["scope_tag_ids"] == ["homology-scope-cyst-nematode"]
        singleton_hit_rels = db.get_relationships("hg_chrom1_tn10mrna_1:protein", "HAS_BCN_HIT", direction="outgoing")
        assert any(rel["target_id"] == "comparative_hit:cyst_nematode:hsc-gene-4672-t1" for rel in singleton_hit_rels)
        broad_hits = db.get_relationships("hg_chrom1_tn10mrna_1:protein", "HAS_BROAD_HOMOLOGY_HIT", direction="outgoing")
        assert broad_hits
        scope_rels = db.get_relationships("comparative_hit:cyst_nematode:hsc-gene-4672-t1", "TAGGED", direction="outgoing")
        assert any(rel["target_id"] == "homology-scope-cyst-nematode" for rel in scope_rels)
        assert db.get_entity("homology-scope-cyst-nematode") is not None
        assert db.get_entity("homology-scope-broad-parasitism") is not None

    assert (vault_dir / "index.md").exists()
    assert (vault_dir / "organisms").exists()
    assert (vault_dir / "datasets").exists()
    assert (vault_dir / "chromosomes").exists()
    assert (vault_dir / "genes").exists()
    assert (vault_dir / "bcn_genes").exists()
    assert (vault_dir / "comparative_hits").exists()
    assert (vault_dir / "tags").exists()


def test_infer_source_package_from_arbitrary_local_table_and_notes(tmp_path: Path):
    source_dir = ROOT / "sample_data" / "1_source" / "genomics_scn"
    raw_copy = tmp_path / "raw_export.tsv"
    raw_copy.write_text((source_dir / "DATA.tsv").read_text())
    note_path = tmp_path / "notes.md"
    note_path.write_text(
        "# SCN Effector Export\n"
        "organism: Heterodera glycines\n"
        "description: Local export for inference testing.\n"
    )

    dataset_path, schema_path, report_path = infer_source_package(
        source_file=raw_copy,
        source_dir=tmp_path,
        note_paths=[note_path],
        apply=True,
    )

    assert dataset_path.name == "dataset.yaml"
    assert schema_path.name == "schema.yaml"
    assert report_path.exists()
    dataset_text = dataset_path.read_text()
    schema_text = schema_path.read_text()
    assert "organism: Heterodera glycines" in dataset_text
    assert "primary_record_entity: transcript" in schema_text
    assert "chromosome:" in schema_text
    assert "glycines_gene_count" in schema_text
    assert "bcn_gene" in schema_text
    assert "comparative_hit" in schema_text
    assert "homology-scope-cyst-nematode" in schema_text
    assert "data_path: raw_export.tsv" in schema_text
    assert "dataset_specific: []" in schema_text
    assert "expression_entities:" in schema_text
    assert "source_summary_column:" in schema_text

    db_path = tmp_path / "inferred.db"
    build_dataset(source_dir=tmp_path, db_path=db_path, fresh=True)
    with KnowledgeGraphDB(db_path) as db:
        stats = db.stats()
        assert stats["entities"]["organism"] == 2
        assert stats["entities"]["chromosome"] == 1
        assert stats["entities"]["transcript"] == 9
        assert stats["entities"]["protein"] == 9
        assert stats["relationships"]["CONTRAST_SOURCE"] > 0


def test_review_source_package_writes_llm_sidecar_without_changing_build_inputs(tmp_path: Path):
    source_dir = ROOT / "sample_data" / "1_source" / "genomics_scn"
    raw_copy = tmp_path / "raw_export.tsv"
    raw_copy.write_text((source_dir / "DATA.tsv").read_text())
    note_path = tmp_path / "notes.md"
    note_path.write_text("organism: Heterodera glycines\n")

    class FakeLLM:
        def is_available(self):
            return True

        def chat(self, messages):
            assert any("primary_record_entity" in msg["content"] for msg in messages if msg["role"] == "user")
            return """{
              "summary": "Transcript-centric inference looks reasonable.",
              "confidence": "high",
              "primary_record_entity": "transcript",
              "top_issues": [
                {"severity": "low", "issue": "orthogroup remains gene-attached", "reason": "acceptable default"}
              ],
              "column_suggestions": [
                {"column": "mol_weight", "suggested_entity": "protein", "suggested_group": "biophysics", "reason": "protein-derived property"}
              ],
              "group_suggestions": [],
              "ambiguities": []
            }"""

    review_path, raw_path = review_source_package(
        source_file=raw_copy,
        source_dir=tmp_path,
        note_paths=[note_path],
        llm_client=FakeLLM(),
    )

    assert review_path.exists()
    assert raw_path.exists()
    review_text = review_path.read_text()
    assert "primary_record_entity: transcript" in review_text
    assert "column: mol_weight" in review_text


def test_propose_schema_patch_translates_review_into_deterministic_sidecar(tmp_path: Path):
    schema_path = tmp_path / "schema.yaml"
    schema_path.write_text(
        """
entity_model:
  entities:
    gene:
      metadata_columns: [genome_location, mol_weight]
    transcript:
      metadata_columns: [avg_counts]
    protein:
      metadata_columns: [signalp5]
      sequence_column: protein_sequence
"""
    )
    review_path = tmp_path / "llm-review.yaml"
    review_path.write_text(
        """
llm_review:
  summary: move protein-derived fields
  confidence: high
  column_suggestions:
    - column: mol_weight
      suggested_entity: protein
      suggested_group: biophysics
      reason: protein-derived property
  ambiguities: []
  group_suggestions: []
"""
    )

    patch_path, proposed_path = propose_schema_patch(
        review_path=review_path,
        schema_path=schema_path,
        output_dir=tmp_path,
    )

    assert patch_path.exists()
    assert proposed_path.exists()
    patch_text = patch_path.read_text()
    proposed = yaml.safe_load(proposed_path.read_text())
    assert "to_entity: protein" in patch_text
    assert "from_entity: gene" in patch_text
    entities = proposed["entity_model"]["entities"]
    assert entities["gene"]["metadata_columns"] == ["genome_location"]
    assert entities["protein"]["metadata_columns"] == ["signalp5", "mol_weight"]


def test_apply_schema_patch_updates_schema_and_writes_backup(tmp_path: Path):
    schema_path = tmp_path / "schema.yaml"
    original_text = """
entity_model:
  entities:
    gene:
      metadata_columns: [genome_location, mol_weight]
    transcript:
      metadata_columns: [avg_counts]
    protein:
      metadata_columns: [signalp5]
      sequence_column: protein_sequence
"""
    schema_path.write_text(original_text)
    patch_path = tmp_path / "schema.patch.yaml"
    patch_path.write_text(
        f"""
schema_path: {schema_path}
operations:
  - column: mol_weight
    from_entity: gene
    to_entity: protein
    suggested_group: biophysics
    reason: protein-derived property
"""
    )

    updated_path, backup_path = apply_schema_patch(
        patch_path=patch_path,
        schema_path=schema_path,
    )

    assert updated_path == schema_path
    assert backup_path.exists()
    assert backup_path.read_text() == original_text
    updated = yaml.safe_load(schema_path.read_text())
    entities = updated["entity_model"]["entities"]
    assert entities["gene"]["metadata_columns"] == ["genome_location"]
    assert entities["protein"]["metadata_columns"] == ["signalp5", "mol_weight"]
