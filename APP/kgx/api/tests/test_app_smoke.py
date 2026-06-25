from pathlib import Path

import httpx
import pytest

from kgx.api import create_app
from kgx.config import load_config
from kgx.db import KnowledgeGraphDB


@pytest.fixture
def app_config(tmp_path):
    db_path = tmp_path / "smoke.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("person", "alice", name="Alice", metadata={"profiled": True, "title": "PI"})
    db.upsert_entity("person", "bob", name="Bob", metadata={})
    db.upsert_entity(
        "publication",
        "paper-1",
        name="Paper 1",
        metadata={"title": "Paper 1", "abstract": "A" * 300},
    )
    db.upsert_entity("award", "award-2022", name="Award 2022", metadata={"award_year": 2022})
    db.upsert_entity("award", "award-2023", name="Award 2023", metadata={"award_year": 2023})
    db.upsert_entity("award", "award-2024", name="Award 2024", metadata={"award_year": 2024})
    db.upsert_entity("tag", "ai", name="AI")
    db.add_relationship("alice", "AUTHORED", "paper-1")
    db.add_relationship("bob", "AUTHORED", "paper-1")
    db.add_relationship("paper-1", "TAGGED", "ai")
    db.conn.execute(
        "INSERT INTO snippets (entity_id, ref_id, ref_type, text, ordinal) VALUES (?, ?, ?, ?, 0)",
        ("paper-1", "alice", "person", "Alice mention"),
    )
    db.conn.commit()
    db.close()

    cfg = load_config(Path("/workspace/KnowledgeGraph/APP/config/people.yaml"))
    db_build = cfg.db_build.model_dump()
    db_build["person_research"]["extensions"] = ["isu_profile"]

    return {
        "db_path": str(db_path),
        "server": cfg.server.model_dump(),
        "ui": cfg.ui.model_dump(),
        "llm": cfg.llm.model_dump(),
        "skills": cfg.skills.model_dump(),
        "explore": cfg.explore.model_dump(),
        "embedding": cfg.embedding.model_dump(),
        "domain": cfg.domain.model_dump(),
        "db_build": db_build,
    }


@pytest.mark.asyncio
async def test_app_smoke(app_config):
    app = create_app(app_config)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/api/config")
        assert resp.status_code == 200
        config = resp.json()
        assert config["explore"]["stub_type"] == "person"
        assert config["embedding"]["skip_stub_type"] == "person"
        assert config["ui"]["layouts"] is not None
        assert config["ui"]["layouts"]["timeline"]["enabled"] is True
        assert config["ui"]["layouts"]["hierarchical"]["enabled"] is True
        assert config["ui"]["semantic_schema"]["group_order"] == ["identity", "affiliation"]
        assert config["ui"]["semantic_registry"]["domain"] == "people"
        assert config["ui"]["semantic_registry"]["metadata_hints"]["person"]["preferred_fields"][0] == "title"
        assert config["ui"]["semantic_registry"]["operators"]["parsers"]["field_value"]["mode"] == "field_value"
        assert config["ui"]["semantic_registry"]["operators"]["renderers"]["relationship"]["validation_signatures"][0] == "{rel_type}"
        assert config["ui"]["semantic_registry"]["operators"]["specs"]["relationship_filters"]["authored_publication"]["rel_type"] == "AUTHORED"

        resp = await client.get("/api/semantic/onboarding")
        assert resp.status_code == 200
        onboarding = resp.json()
        assert onboarding["artifact_version"] == "semantics-onboarding.v1"
        assert onboarding["domain"] == "people"
        assert onboarding["summary"]["active_count"] >= 2

        resp = await client.get("/api/semantic/patch")
        assert resp.status_code == 200
        patch = resp.json()
        assert patch["artifact_version"] == "semantic-registry-patch.v1"
        assert patch["domain"] == "people"
        assert "registry_patch" in patch

        cfg = load_config(Path("/workspace/KnowledgeGraph/APP/config/people.yaml"))
        assert cfg.domain.name == "people"
        assert cfg.db_build.source_policy.official_only is False
        assert cfg.db_build.model_dump()["person_research"]["enabled"] is True

        resp = await client.get("/api/layout/timeline/options")
        assert resp.status_code == 200
        timeline = resp.json()
        assert timeline["profile"] is not None
        assert timeline["profile"]["profile_name"] == "people"
        assert timeline["detected_type_min_count"] == 3
        award_candidate = next(item for item in timeline["candidates"] if item["type"] == "award")
        assert award_candidate["order_fields"][0]["field"] == "award_year"
        assert award_candidate["order_fields"][0]["non_null_count"] == 3

        resp = await client.get("/api/skill/help/person_research")
        assert resp.status_code == 200
        skill_help = resp.json()
        assert skill_help["skill"]["id"] == "person_research"
        assert skill_help["skill"]["name"] == "Person Research"
        assert skill_help["skill"]["entry_path"] == "run_person.py"
        assert skill_help["skill"]["entity_types"] == ["person"]
        assert any(arg["name"] == "config" for arg in skill_help["skill"]["args"])
        assert skill_help["settings"]["institution"] == "Iowa State University"
        assert skill_help["source_policy"]["official_only"] is False

        resp = await client.get("/api/graph", params={"mode": "display"})
        assert resp.status_code == 200
        display = resp.json()
        assert any(n["id"] == "bob" and not n["hidden"] for n in display["nodes"])
        assert any(e["rel_type"] == "AUTHORED" and not e["hidden"] for e in display["edges"])

        resp = await client.get("/api/graph", params={"mode": "explore"})
        assert resp.status_code == 200
        explore = resp.json()
        node_ids = {n["id"] for n in explore["nodes"]}
        rel_types = {e["rel_type"] for e in explore["edges"]}
        assert "bob" not in node_ids
        assert "paper-1" not in node_ids
        assert "alice" in node_ids
        assert "ai" in node_ids
        assert "COLLABORATOR" not in rel_types
        assert "TAGGED" in rel_types

        resp = await client.get("/api/entity/alice")
        assert resp.status_code == 200
        entity = resp.json()
        assert entity["entity"]["id"] == "alice"
        assert entity["degree"] >= 1

        nobel_cfg = load_config(Path("/workspace/KnowledgeGraph/APP/config/people.yaml"))
        nobel_db_build = nobel_cfg.db_build.model_dump()
        nobel_db_build["person_research"]["extensions"] = ["nobel_profile"]
        nobel_app_config = {
            "db_path": app_config["db_path"],
            "server": nobel_cfg.server.model_dump(),
            "ui": nobel_cfg.ui.model_dump(),
            "llm": nobel_cfg.llm.model_dump(),
            "skills": nobel_cfg.skills.model_dump(),
            "explore": nobel_cfg.explore.model_dump(),
            "embedding": nobel_cfg.embedding.model_dump(),
            "domain": nobel_cfg.domain.model_dump(),
            "db_build": nobel_db_build,
        }

        nobel_app = create_app(nobel_app_config)
        nobel_transport = httpx.ASGITransport(app=nobel_app)
        async with httpx.AsyncClient(transport=nobel_transport, base_url="http://testserver") as nobel_client:
            resp = await nobel_client.get("/api/skill/help/person_research")
            assert resp.status_code == 200
            nobel_help = resp.json()
            assert nobel_help["settings"]["extensions"] == ["nobel_profile"]
            assert nobel_help["settings"]["role_profile"]["default_role"] == "laureate"
            assert nobel_help["source_policy"]["official_only"] is True
            assert "api.nobelprize.org" in nobel_help["source_policy"]["allowed_domains"]
            assert any("Nobel laureate" in prompt for prompt in nobel_help["help_prompts"])

            resp = await nobel_client.get("/api/skill/help/signal_capture")
            assert resp.status_code == 200
            signal_help = resp.json()
            assert signal_help["source_policy"]["official_only"] is True
            assert any("official Nobel announcement" in prompt for prompt in signal_help["help_prompts"])


@pytest.mark.asyncio
async def test_graph_explore_presets_filter_types_and_tag_roots(tmp_path):
    db_path = tmp_path / "genomics.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("organism", "organism:heterodera-glycines", name="Heterodera glycines")
    db.upsert_entity("organism", "organism:heterodera-schachtii", name="Heterodera schachtii")
    db.upsert_entity("chromosome", "chromosome:heterodera-glycines:chr1", name="chr1")
    db.upsert_entity("gene", "gene-1", name="Gene 1")
    db.upsert_entity("transcript", "tx-1", name="Transcript 1", metadata={"expression_bin_13": "bin_a"})
    db.upsert_entity("protein", "prot-1", name="Protein 1", metadata={"pfam": "PF00001"})
    db.upsert_entity("orthogroup", "orthogroup:og1", name="OG1")
    db.upsert_entity("bcn_gene", "bcn_gene:heterodera-schachtii:hsc_gene_1.t1", name="Hsc_gene_1.t1", metadata={"organism": "Heterodera schachtii"})
    db.upsert_entity("comparative_hit", "comparative_hit:cyst_nematode:hsc-gene-1-t1", name="Hsc_gene_1.t1", metadata={"organism": "Heterodera schachtii"})
    db.upsert_entity("tag", "homology", name="Homology", metadata={"category": "field"})
    db.upsert_entity("tag", "homology-scope", name="Homology Scope", metadata={"category": "topic"})
    db.upsert_entity("tag", "homology-scope-cyst-nematode", name="Cyst Nematode", metadata={"category": "topic"})
    db.upsert_entity("tag", "functional-annotations", name="Functional Annotations", metadata={"category": "field"})
    db.upsert_entity("tag", "pfam-family", name="Pfam Family", metadata={"category": "topic"})
    db.upsert_entity("tag", "pfam:pf00001", name="PF00001", metadata={"category": "topic"})
    db.upsert_entity("tag", "expression", name="Expression", metadata={"category": "field"})
    db.upsert_entity("tag", "expression-bin", name="Expression Bin", metadata={"category": "topic"})
    db.upsert_entity("tag", "tag:bin_a", name="bin_a", metadata={"category": "topic"})
    db.add_relationship("gene-1", "HAS_TRANSCRIPT", "tx-1")
    db.add_relationship("tx-1", "TRANSLATED_TO", "prot-1")
    db.add_relationship("organism:heterodera-glycines", "HAS_CHROMOSOME", "chromosome:heterodera-glycines:chr1")
    db.add_relationship("chromosome:heterodera-glycines:chr1", "HAS_GENE", "gene-1")
    db.add_relationship("gene-1", "FROM_ORGANISM", "organism:heterodera-glycines")
    db.add_relationship("gene-1", "BELONGS_TO_ORTHOGROUP", "orthogroup:og1")
    db.add_relationship("orthogroup:og1", "HAS_BCN_MEMBER", "bcn_gene:heterodera-schachtii:hsc_gene_1.t1")
    db.add_relationship("prot-1", "HAS_BCN_HIT", "bcn_gene:heterodera-schachtii:hsc_gene_1.t1")
    db.add_relationship("prot-1", "HAS_BROAD_HOMOLOGY_HIT", "comparative_hit:cyst_nematode:hsc-gene-1-t1")
    db.add_relationship("bcn_gene:heterodera-schachtii:hsc_gene_1.t1", "FROM_ORGANISM", "organism:heterodera-schachtii")
    db.add_relationship("homology-scope", "BROADER", "homology")
    db.add_relationship("homology-scope-cyst-nematode", "BROADER", "homology-scope")
    db.add_relationship("bcn_gene:heterodera-schachtii:hsc_gene_1.t1", "TAGGED", "homology-scope-cyst-nematode")
    db.add_relationship("comparative_hit:cyst_nematode:hsc-gene-1-t1", "TAGGED", "homology-scope-cyst-nematode")
    db.add_relationship("pfam-family", "BROADER", "functional-annotations")
    db.add_relationship("pfam:pf00001", "BROADER", "pfam-family")
    db.add_relationship("expression-bin", "BROADER", "expression")
    db.add_relationship("tag:bin_a", "BROADER", "expression-bin")
    db.add_relationship("prot-1", "TAGGED", "pfam:pf00001")
    db.add_relationship("tx-1", "TAGGED", "tag:bin_a")
    db.close()

    cfg = load_config(Path("/workspace/KnowledgeGraph/APP/config/genomics.yaml"))
    app_config = {
        "db_path": str(db_path),
        "server": cfg.server.model_dump(),
        "ui": cfg.ui.model_dump(),
        "llm": cfg.llm.model_dump(),
        "skills": cfg.skills.model_dump(),
        "explore": cfg.explore.model_dump(),
        "embedding": cfg.embedding.model_dump(),
        "domain": cfg.domain.model_dump(),
        "db_build": cfg.db_build.model_dump(),
    }
    app = create_app(app_config)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/api/config")
        assert resp.status_code == 200
        cfg_data = resp.json()
        detail_layouts = cfg_data["ui"].get("detail_layouts", {})
        assert "genomics_source_groups" in detail_layouts
        genomics_layout = detail_layouts["genomics_source_groups"]
        assert "protein" in genomics_layout["entity_types"]
        assert genomics_layout["groups"][0]["id"] == "core"
        assert genomics_layout["groups"][0]["label"] == "Core"
        assert genomics_layout["groups"][1]["id"] == "genomics"
        assert any(field["key"] == "glycines_effectors_dna" and field["label"] == "SCN known (N)" for field in next(group for group in genomics_layout["groups"] if group["id"] == "effectors")["fields"])
        semantic_schema = cfg_data["ui"].get("semantic_schema", {})
        assert semantic_schema["group_order"][0] == "core"
        assert "effectors" in semantic_schema["groups"]
        assert "homology" in semantic_schema["groups"]
        assert "effectors" in semantic_schema["groups"]["effectors"]["aliases"]
        assert any(field["key"] == "schachtii_effectors_known" for field in semantic_schema["groups"]["effectors"]["fields"])
        semantic_registry = cfg_data["ui"].get("semantic_registry", {})
        assert semantic_registry["domain"] == "genomics"
        assert semantic_registry["schema"]["group_order"][0] == "core"
        assert semantic_registry["relation_families"]["protein_evidence"][0]["rel_type"] == "HAS_HGT_DONOR"
        assert semantic_registry["operators"]["condition_handlers"]["protein_evidence"] == "protein_evidence"
        assert semantic_registry["operators"]["specs"]["orthogroup_filter"]["steps"][0]["rel_type"] == "BELONGS_TO_ORTHOGROUP"
        assert semantic_registry["operators"]["specs"]["ortholog_member"]["steps"][1]["rel_type"] == "HAS_BCN_MEMBER"
        assert "bcn" in semantic_registry["organisms"]["alias_overrides"]["heterodera schachtii"]

        resp = await client.get("/api/semantic/onboarding")
        assert resp.status_code == 200
        onboarding = resp.json()
        assert onboarding["artifact_version"] == "semantics-onboarding.v1"
        assert onboarding["domain"] == "genomics"
        assert onboarding["summary"]["active_count"] >= 4

        resp = await client.get("/api/semantic/patch")
        assert resp.status_code == 200
        patch = resp.json()
        assert patch["artifact_version"] == "semantic-registry-patch.v1"
        assert patch["domain"] == "genomics"
        assert "registry_patch" in patch

        resp = await client.get("/api/graph", params={"mode": "explore", "preset": "protein_centric"})
        assert resp.status_code == 200
        data = resp.json()
        node_ids = {n["id"] for n in data["nodes"]}
        rel_types = {e["rel_type"] for e in data["edges"]}
        preset_ids = {p["id"] for p in data["projection"]["available_presets"]}
        assert data["projection"]["active_preset"] == "protein_centric"
        assert "expression_centric" not in preset_ids
        assert "prot-1" in node_ids
        assert "gene-1" in node_ids
        assert "tx-1" not in node_ids
        assert "pfam:pf00001" in node_ids
        assert "tag:bin_a" not in node_ids
        assert "GENE_PRODUCT" in rel_types

        resp = await client.get("/api/graph", params={"mode": "display", "preset": "comparative"})
        assert resp.status_code == 200
        data = resp.json()
        display_tag_group_ids = {group["id"] for group in data["projection"].get("visible_tag_groups", [])}
        assert "homology-scope" in display_tag_group_ids

        resp = await client.get("/api/graph", params={"mode": "explore", "preset": "comparative"})
        assert resp.status_code == 200
        data = resp.json()
        node_ids = {n["id"] for n in data["nodes"]}
        rel_types = {e["rel_type"] for e in data["edges"]}
        tag_group_ids = {group["id"] for group in data["projection"].get("visible_tag_groups", [])}
        assert data["projection"]["active_preset"] == "comparative"
        assert "homology-scope" in tag_group_ids
        assert "orthogroup:og1" in node_ids
        assert "bcn_gene:heterodera-schachtii:hsc_gene_1.t1" in node_ids
        assert "comparative_hit:cyst_nematode:hsc-gene-1-t1" in node_ids
        assert "homology-scope-cyst-nematode" in node_ids
        assert "gene-1" in node_ids
        assert "prot-1" in node_ids
        assert "organism:heterodera-glycines" in node_ids
        assert "organism:heterodera-schachtii" in node_ids
        assert "chromosome:heterodera-glycines:chr1" in node_ids
        assert "tx-1" not in node_ids
        assert "HAS_CHROMOSOME" in rel_types
        assert "HAS_GENE" in rel_types
        assert "BELONGS_TO_ORTHOGROUP" in rel_types
        assert "HAS_BCN_MEMBER" in rel_types
        assert "HAS_BCN_HIT" in rel_types
        assert "HAS_BROAD_HOMOLOGY_HIT" in rel_types
        assert "PROTEIN_ORTHOGROUP" in rel_types
        assert "TAGGED" in rel_types
        assert "BROADER" in rel_types
        assert "FROM_ORGANISM" in rel_types


@pytest.mark.asyncio
async def test_graph_explore_presets_hide_optional_genomics_modes_when_layers_absent(tmp_path):
    db_path = tmp_path / "genomics-minimal.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("organism", "organism:heterodera-glycines", name="Heterodera glycines")
    db.upsert_entity("chromosome", "chromosome:heterodera-glycines:chr1", name="chr1")
    db.upsert_entity("gene", "gene-1", name="Gene 1")
    db.add_relationship("organism:heterodera-glycines", "HAS_CHROMOSOME", "chromosome:heterodera-glycines:chr1")
    db.add_relationship("chromosome:heterodera-glycines:chr1", "HAS_GENE", "gene-1")
    db.close()

    cfg = load_config(Path("/workspace/KnowledgeGraph/APP/config/genomics.yaml"))
    app_config = {
        "db_path": str(db_path),
        "server": cfg.server.model_dump(),
        "ui": cfg.ui.model_dump(),
        "llm": cfg.llm.model_dump(),
        "skills": cfg.skills.model_dump(),
        "explore": cfg.explore.model_dump(),
        "embedding": cfg.embedding.model_dump(),
        "domain": cfg.domain.model_dump(),
        "db_build": cfg.db_build.model_dump(),
    }
    app = create_app(app_config)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/api/graph", params={"mode": "explore"})
        assert resp.status_code == 200
        data = resp.json()
        preset_ids = {item["id"] for item in data["projection"]["available_presets"]}
        assert data["projection"]["active_preset"] == "structure"
        assert "structure" in preset_ids
        assert "gene_centric" in preset_ids
        assert "transcript_centric" not in preset_ids
        assert "protein_centric" not in preset_ids
        assert "comparative" not in preset_ids
        assert "expression_centric" not in preset_ids
