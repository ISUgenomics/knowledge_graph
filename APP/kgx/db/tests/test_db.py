"""
Tests for kgx.db.KnowledgeGraphDB.

Uses an in-memory SQLite database — no fixtures, no files on disk.
"""

import pytest
from kgx.db import KnowledgeGraphDB


@pytest.fixture
def db():
    """Fresh in-memory DB for each test."""
    d = KnowledgeGraphDB(":memory:")
    yield d
    d.close()


@pytest.fixture
def populated_db(db):
    """DB with a small sample graph: 3 people, 2 publications, 1 event, tags."""
    # People
    db.upsert_entity("person", "alice-smith", name="Alice Smith",
                     metadata={"role": "faculty", "department": "CS", "profiled": True})
    db.upsert_entity("person", "bob-jones", name="Bob Jones",
                     metadata={"role": "staff", "department": "Biology", "profiled": True})
    db.upsert_entity("person", "carol-lee", name="Carol Lee",
                     metadata={"role": "student"})  # unprofiled stub

    # Publications
    db.upsert_entity("publication", "doi:10.1234/test1", name="Paper on AI",
                     metadata={"year": 2024, "journal": "Nature", "doi": "10.1234/test1"})
    db.upsert_entity("publication", "doi:10.1234/test2", name="Graph Methods",
                     metadata={"year": 2023, "journal": "Science", "doi": "10.1234/test2"})

    # Event
    db.upsert_entity("event", "ai-workshop-2024", name="AI Workshop 2024",
                     metadata={"date": "2024-03-15", "location": "Ames, IA"})

    # Tags
    db.upsert_entity("tag", "ai", name="ai")
    db.upsert_entity("tag", "genomics", name="genomics")

    # Relationships
    db.add_relationship("alice-smith", "AUTHORED", "doi:10.1234/test1")
    db.add_relationship("alice-smith", "AUTHORED", "doi:10.1234/test2")
    db.add_relationship("bob-jones", "AUTHORED", "doi:10.1234/test1")
    db.add_relationship("alice-smith", "COAUTHOR", "bob-jones")
    db.add_relationship("alice-smith", "ATTENDED", "ai-workshop-2024")
    db.add_relationship("bob-jones", "ATTENDED", "ai-workshop-2024")
    db.add_relationship("alice-smith", "TAGGED", "ai")
    db.add_relationship("bob-jones", "TAGGED", "genomics")
    db.add_relationship("doi:10.1234/test1", "TAGGED", "ai")

    return db


# --- Schema discovery ---

class TestSchemaDiscovery:
    def test_entity_types_empty(self, db):
        assert db.entity_types() == []

    def test_entity_types_populated(self, populated_db):
        types = {t["type"]: t["count"] for t in populated_db.entity_types()}
        assert types["person"] == 3
        assert types["publication"] == 2
        assert types["event"] == 1
        assert types["tag"] == 2

    def test_relationship_types(self, populated_db):
        rels = {r["rel_type"]: r["count"] for r in populated_db.relationship_types()}
        assert rels["AUTHORED"] == 3
        assert rels["COAUTHOR"] == 1
        assert rels["ATTENDED"] == 2
        assert rels["TAGGED"] == 3

    def test_metadata_keys(self, populated_db):
        keys = populated_db.metadata_keys("person")
        assert "role" in keys
        assert "department" in keys

    def test_metadata_keys_no_type(self, populated_db):
        keys = populated_db.metadata_keys()
        assert "role" in keys
        assert "year" in keys  # from publications


# --- Bulk graph data ---

class TestGraphData:
    def test_graph_nodes_minimal_fields(self, populated_db):
        nodes = populated_db.graph_nodes()
        assert len(nodes) == 8  # 3 people + 2 pubs + 1 event + 2 tags
        for n in nodes:
            assert set(n.keys()) == {"id", "type", "name"}

    def test_graph_edges(self, populated_db):
        edges = populated_db.graph_edges()
        assert len(edges) == 9
        for e in edges:
            assert "source" in e
            assert "target" in e
            assert "rel_type" in e


# --- Entity CRUD ---

class TestEntityCRUD:
    def test_upsert_creates(self, db):
        eid = db.upsert_entity("person", "Jane Doe", name="Jane Doe")
        assert eid == "jane-doe"  # normalized
        entity = db.get_entity("jane-doe")
        assert entity is not None
        assert entity["name"] == "Jane Doe"
        assert entity["type"] == "person"

    def test_upsert_updates(self, db):
        db.upsert_entity("person", "jane-doe", name="Jane Doe")
        db.upsert_entity("person", "jane-doe", name="Jane A. Doe", metadata={"title": "Professor"})
        entity = db.get_entity("jane-doe")
        assert entity["name"] == "Jane A. Doe"
        assert entity["metadata"]["title"] == "Professor"

    def test_upsert_with_aliases(self, db):
        db.upsert_entity("person", "alice-smith", name="Alice Smith",
                         aliases=["A. Smith", "Alice B. Smith"])
        assert db.resolve("a.-smith") == "alice-smith"
        assert db.resolve("alice-b.-smith") == "alice-smith"

    def test_metadata_deserialized(self, populated_db):
        entity = populated_db.get_entity("alice-smith")
        assert isinstance(entity["metadata"], dict)
        assert entity["metadata"]["role"] == "faculty"

    def test_get_entity_not_found(self, db):
        assert db.get_entity("nonexistent") is None

    def test_delete_entity(self, populated_db):
        assert populated_db.delete_entity("carol-lee") is True
        assert populated_db.get_entity("carol-lee") is None

    def test_delete_entity_cascades_relationships(self, populated_db):
        populated_db.delete_entity("alice-smith")
        rels = populated_db.get_relationships("alice-smith")
        assert rels == []

    def test_get_entities_by_type(self, populated_db):
        people = populated_db.get_entities("person")
        assert len(people) == 3

    def test_get_entities_search(self, populated_db):
        results = populated_db.get_entities(search="Alice")
        assert len(results) == 1
        assert results[0]["name"] == "Alice Smith"

    def test_ensure_entity_existing(self, populated_db):
        eid = populated_db.ensure_entity("person", "alice-smith", name="Different Name")
        assert eid == "alice-smith"
        # Name should NOT be overwritten by ensure_entity
        entity = populated_db.get_entity("alice-smith")
        assert entity["name"] == "Alice Smith"

    def test_ensure_entity_new(self, db):
        eid = db.ensure_entity("person", "new-person", name="New Person")
        assert eid == "new-person"
        assert db.get_entity("new-person") is not None

    def test_resolve_by_id(self, populated_db):
        assert populated_db.resolve("alice-smith") == "alice-smith"

    def test_resolve_not_found(self, db):
        assert db.resolve("nobody") is None


# --- Relationship CRUD ---

class TestRelationships:
    def test_add_and_get(self, db):
        db.upsert_entity("person", "alice", name="Alice")
        db.upsert_entity("publication", "pub1", name="Paper 1")
        db.add_relationship("alice", "AUTHORED", "pub1")
        rels = db.get_relationships("alice", "AUTHORED", "outgoing")
        assert len(rels) == 1
        assert rels[0]["target_id"] == "pub1"

    def test_idempotent(self, populated_db):
        # Adding same relationship twice should not duplicate
        populated_db.add_relationship("alice-smith", "AUTHORED", "doi:10.1234/test1")
        rels = populated_db.get_relationships("alice-smith", "AUTHORED", "outgoing")
        assert len(rels) == 2  # still just the original 2

    def test_incoming_direction(self, populated_db):
        rels = populated_db.get_relationships("doi:10.1234/test1", direction="incoming")
        authors = [r["source_id"] for r in rels if r["rel_type"] == "AUTHORED"]
        assert "alice-smith" in authors
        assert "bob-jones" in authors

    def test_delete_relationship(self, populated_db):
        assert populated_db.delete_relationship("alice-smith", "AUTHORED", "doi:10.1234/test1")
        rels = populated_db.get_relationships("alice-smith", "AUTHORED", "outgoing")
        assert len(rels) == 1  # only test2 remains

    def test_delete_nonexistent(self, populated_db):
        assert not populated_db.delete_relationship("alice-smith", "AUTHORED", "nonexistent")


# --- Graph queries ---

class TestGraphQueries:
    def test_neighbors(self, populated_db):
        neighbors = populated_db.neighbors("alice-smith")
        ids = {n["id"] for n in neighbors}
        assert "doi:10.1234/test1" in ids
        assert "doi:10.1234/test2" in ids
        assert "bob-jones" in ids  # via COAUTHOR
        assert "ai-workshop-2024" in ids
        assert "ai" in ids

    def test_neighbors_filtered_by_rel_type(self, populated_db):
        neighbors = populated_db.neighbors("alice-smith", "AUTHORED")
        ids = {n["id"] for n in neighbors}
        assert "doi:10.1234/test1" in ids
        assert "bob-jones" not in ids

    def test_shared_connections(self, populated_db):
        shared = populated_db.shared_connections("alice-smith", "bob-jones")
        ids = {n["id"] for n in shared}
        # Both attended the event and co-authored test1
        assert "ai-workshop-2024" in ids
        assert "doi:10.1234/test1" in ids

    def test_hub_nodes(self, populated_db):
        hubs = populated_db.hub_nodes(min_degree=3)
        ids = {h["id"] for h in hubs}
        assert "alice-smith" in ids  # has many connections

    def test_degree(self, populated_db):
        d = populated_db.degree("alice-smith")
        assert d >= 5  # authored 2, coauthor 1, attended 1, tagged 1

    def test_stats(self, populated_db):
        s = populated_db.stats()
        assert s["total_entities"] == 8
        assert s["total_relationships"] == 9
        assert s["entities"]["person"] == 3


# --- Raw SQL ---

class TestRawSQL:
    def test_execute_read_select(self, populated_db):
        results = populated_db.execute_read("SELECT id, name FROM entities WHERE type = 'person'")
        assert len(results) == 3

    def test_execute_read_rejects_non_select(self, populated_db):
        with pytest.raises(ValueError, match="execute_read only accepts SELECT"):
            populated_db.execute_read("DELETE FROM entities")

    def test_execute_write_insert(self, db):
        db.upsert_entity("person", "alice", name="Alice")
        rows = db.execute_write(
            "UPDATE entities SET name = ? WHERE id = ?", ["Alice Updated", "alice"]
        )
        assert rows == 1
        assert db.get_entity("alice")["name"] == "Alice Updated"

    def test_execute_write_rejects_select(self, populated_db):
        with pytest.raises(ValueError, match="does not accept SELECT"):
            populated_db.execute_write("SELECT * FROM entities")

    def test_execute_read_with_params(self, populated_db):
        results = populated_db.execute_read(
            "SELECT id FROM entities WHERE type = ?", ["person"]
        )
        assert len(results) == 3


# --- Export ---

class TestExport:
    def test_export_graph_json_structure(self, populated_db):
        data = populated_db.export_graph_json()
        assert "nodes" in data
        assert "edges" in data
        assert "stats" in data
        assert len(data["nodes"]) == 8
        assert len(data["edges"]) == 9

    def test_export_markdown_entity(self, populated_db):
        md = populated_db.export_markdown("alice-smith")
        assert "Alice Smith" in md
        assert "AUTHORED" in md or "Properties" in md

    def test_export_markdown_not_found(self, db):
        md = db.export_markdown("nobody")
        assert "Not found" in md

    def test_export_neo4j_csv(self, populated_db, tmp_path):
        files = populated_db.export_neo4j_csv(tmp_path)
        assert "nodes_person" in files
        assert "nodes_publication" in files
        assert files["nodes_person"].exists()
        # Check content
        content = files["nodes_person"].read_text()
        assert "Alice Smith" in content
