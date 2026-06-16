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
