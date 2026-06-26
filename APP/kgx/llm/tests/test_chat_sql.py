from pathlib import Path

from kgx.db import KnowledgeGraphDB
from kgx.genomics_source import load_semantic_registry
from kgx.llm import ChatToSQL
from kgx.llm.modules.genomics import GenomicsChatModule
from kgx.llm.modules.people import PeopleChatModule
from kgx.people_source import load_semantic_registry as load_people_semantic_registry
from kgx.semantic_onboarding import generate_draft_registry_fragment
from kgx.semantic_registry_overlay import merge_semantic_registry_overlay


class _FakeLLM:
    def chat(self, messages):
        return "```sql\nSELECT 1\n```"


class _RetryLLM:
    def __init__(self):
        self.calls = 0

    def chat(self, messages):
        self.calls += 1
        if self.calls == 1:
            return """```sql
SELECT e.id, e.name, e.type
FROM entities e
JOIN relationships r ON e.id = r.source_id
WHERE r.rel_type = 'HAS_BROAD_HOMOLOGY_HIT'
  AND e.type = 'gene'
```"""
        return """```sql
SELECT DISTINCT e.id, e.name, e.type
FROM entities e
JOIN relationships gt ON gt.source_id = e.id AND gt.rel_type = 'HAS_TRANSCRIPT'
JOIN relationships tp ON tp.source_id = gt.target_id AND tp.rel_type = 'TRANSLATED_TO'
JOIN relationships ph ON ph.source_id = tp.target_id AND ph.rel_type = 'HAS_BROAD_HOMOLOGY_HIT'
WHERE e.type = 'gene'
```"""


class _ZeroRetryLLM:
    def __init__(self):
        self.calls = 0

    def chat(self, messages):
        self.calls += 1
        if self.calls == 1:
            return """```sql
SELECT e.id, e.name, e.type
FROM entities e
JOIN relationships r ON e.id = r.source_id
WHERE r.rel_type = 'HAS_BROAD_HOMOLOGY_HIT'
AND EXISTS (
    SELECT 1
    FROM entities e2
    JOIN relationships r2 ON e2.id = r2.target_id
    WHERE r2.source_id = e.id
      AND e2.name = 'Ditylenchus destructor'
)
AND e.type = 'protein'
```"""
        return """```sql
SELECT DISTINCT e.id, e.name, e.type
FROM entities e
JOIN relationships ph ON ph.source_id = e.id AND ph.rel_type = 'HAS_BROAD_HOMOLOGY_HIT'
JOIN relationships ht ON ht.source_id = ph.target_id AND ht.rel_type = 'TAGGED'
JOIN entities t ON t.id = ht.target_id
WHERE e.type = 'protein'
  AND t.type = 'tag'
  AND t.name = 'Ditylenchus destructor'
```"""


class _HgtRetryLLM:
    def __init__(self):
        self.calls = 0

    def chat(self, messages):
        self.calls += 1
        return """```sql
SELECT e.id, e.name, e.type
FROM entities e
JOIN relationships r ON e.id = r.source_id
WHERE r.rel_type = 'HAS_HGT_DONOR'
AND e.type = 'gene'
```"""


class _HgtOrthogroupRetryLLM:
    def chat(self, messages):
        return """```sql
SELECT e.id, e.name, e.type
FROM entities e
JOIN relationships r ON e.id = r.source_id
WHERE r.rel_type = 'HAS_HGT_DONOR'
AND e.type = 'protein'
```"""


class _StaticSQLLLM:
    def __init__(self, sql: str):
        self.sql = sql

    def chat(self, messages):
        return f"```sql\n{self.sql}\n```"


class _CaptureLLM:
    def __init__(self, sql: str = "SELECT e.id, e.name, e.type FROM entities e WHERE 1 = 0"):
        self.sql = sql
        self.messages = None

    def chat(self, messages):
        self.messages = list(messages)
        return f"```sql\n{self.sql}\n```"


class _MetadataBridgeRetryLLM:
    def __init__(self):
        self.calls = 0

    def chat(self, messages):
        self.calls += 1
        if self.calls == 1:
            return """```sql
SELECT e.id, e.name, e.type
FROM entities e
WHERE e.type = 'gene'
  AND json_extract(e.metadata, '$.pfam') = 'PF00001'
  AND json_extract(e.metadata, '$.secretion') = 'secreted'
```"""
        return """```sql
SELECT DISTINCT e.id, e.name, e.type
FROM entities e
JOIN relationships gt ON gt.source_id = e.id AND gt.rel_type = 'HAS_TRANSCRIPT'
JOIN relationships tp ON tp.source_id = gt.target_id AND tp.rel_type = 'TRANSLATED_TO'
JOIN entities owner ON owner.id = tp.target_id AND owner.type = 'protein'
WHERE e.type = 'gene'
  AND json_extract(owner.metadata, '$.pfam') = 'PF00001'
  AND json_extract(owner.metadata, '$.secretion') = 'secreted'
```"""


def test_schema_context_includes_typed_patterns_and_tag_hierarchy(tmp_path: Path):
    db_path = tmp_path / "chat.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("gene", "gene-1", name="Gene 1")
    db.upsert_entity("transcript", "tx-1", name="Transcript 1")
    db.upsert_entity("protein", "prot-1", name="Protein 1")
    db.upsert_entity("comparative_hit", "hit-1", name="KAI1713285.1", metadata={"matched_organism": "Ditylenchus destructor"})
    db.upsert_entity("tag", "homology", name="Homology")
    db.upsert_entity("tag", "homology-hit-organism", name="Hit Organism")
    db.upsert_entity("tag", "homology-hit-organism:ditylenchus-destructor", name="Ditylenchus destructor")
    db.add_relationship("gene-1", "HAS_TRANSCRIPT", "tx-1")
    db.add_relationship("tx-1", "TRANSLATED_TO", "prot-1")
    db.add_relationship("prot-1", "HAS_BROAD_HOMOLOGY_HIT", "hit-1")
    db.add_relationship("homology-hit-organism", "BROADER", "homology")
    db.add_relationship("homology-hit-organism:ditylenchus-destructor", "BROADER", "homology-hit-organism")
    db.add_relationship("hit-1", "TAGGED", "homology-hit-organism:ditylenchus-destructor")
    db.close()

    db = KnowledgeGraphDB(str(db_path))
    chat = ChatToSQL(db, _FakeLLM(), module=GenomicsChatModule())
    context = chat._schema_context()
    db.close()

    assert "gene -HAS_TRANSCRIPT-> transcript" in context
    assert "transcript -TRANSLATED_TO-> protein" in context
    assert "protein -HAS_BROAD_HOMOLOGY_HIT-> comparative_hit" in context
    assert "comparative_hit -TAGGED-> tag" in context
    assert "Metadata keys for 'comparative_hit': matched_organism" in context
    assert "Hit Organism" in context
    assert "Ditylenchus destructor -> Hit Organism" in context


def test_requested_result_types_detects_plural_entity_names(tmp_path: Path):
    db_path = tmp_path / "chat-types.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("gene", "gene-1", name="Gene 1")
    db.upsert_entity("protein", "prot-1", name="Protein 1")
    db.upsert_entity("comparative_hit", "hit-1", name="Hit 1")
    db.close()

    db = KnowledgeGraphDB(str(db_path))
    chat = ChatToSQL(db, _FakeLLM())
    assert chat._requested_result_types("select all genes that have broad homology hits") == ["gene"]
    assert chat._requested_result_types("show proteins with broad homology hits") == ["protein"]
    assert set(chat._requested_result_types("list comparative hits for this protein")) == {"protein", "comparative_hit"}
    db.close()


def test_requested_result_types_prefers_hgt_donor_alias_over_gene_word(tmp_path: Path):
    db_path = tmp_path / "chat-hgt-type.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("gene", "gene-1", name="Gene 1")
    db.upsert_entity("hgt_donor", "donor-1", name="WP_194067917")
    db.close()

    db = KnowledgeGraphDB(str(db_path))
    chat = ChatToSQL(db, _FakeLLM(), module=GenomicsChatModule())
    requested = chat._requested_result_types("select horizontal gene transfer donors")
    db.close()

    assert requested == ["hgt_donor"]


def test_ask_includes_general_and_module_few_shot_examples(tmp_path: Path):
    db_path = tmp_path / "chat-few-shot.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("gene", "gene-1", name="Gene 1")
    db.upsert_entity("person", "person-1", name="Alice")
    db.upsert_entity("hgt_donor", "donor-1", name="WP_194067917")
    db.close()

    db = KnowledgeGraphDB(str(db_path))
    llm = _CaptureLLM()
    chat = ChatToSQL(db, llm, module=GenomicsChatModule())
    chat.ask("select horizontal gene transfer donors")
    db.close()

    assert llm.messages is not None
    contents = [str(item.get("content", "")) for item in llm.messages]
    assert any("select all genes that have broad homology hits for Ditylenchus destructor /no_think" in content for content in contents)
    assert any("select all genes that have HGT donor /no_think" in content for content in contents)


def test_genomics_module_reads_organism_alias_override_from_registry(tmp_path: Path):
    db_path = tmp_path / "chat-organism-alias.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("organism", "organism:heterodera-schachtii", name="Heterodera schachtii")
    db.close()

    module = GenomicsChatModule(
        semantic_registry={
            "organisms": {
                "alias_overrides": {
                    "heterodera schachtii": ["bcn"],
                },
            },
        },
    )
    db = KnowledgeGraphDB(str(db_path))
    chat = ChatToSQL(db, _FakeLLM(), module=module)
    aliases = module._secondary_organism_aliases(chat)
    db.close()

    assert "bcn" in aliases


def test_cross_db_people_prompt_can_mix_arbitrary_metadata_fields(tmp_path: Path):
    db_path = tmp_path / "chat-people-metadata.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("person", "alice", name="Alice", metadata={"title": "PI", "department": "Biology"})
    db.upsert_entity("person", "bob", name="Bob", metadata={"title": "Staff", "department": "Chemistry"})
    db.close()

    sql = """
SELECT e.id, e.name, e.type
FROM entities e
WHERE e.type = 'person'
  AND json_extract(e.metadata, '$.title') = 'PI'
  AND json_extract(e.metadata, '$.department') = 'Biology'
"""
    db = KnowledgeGraphDB(str(db_path))
    chat = ChatToSQL(db, _StaticSQLLLM(sql))
    result = chat.ask("select people with title PI and department Biology")
    db.close()

    assert result.error is None
    assert result.sql is not None
    assert result.results
    assert [row["id"] for row in result.results] == ["alice"]


def test_people_module_reads_metadata_hints_from_registry(tmp_path: Path):
    db_path = tmp_path / "chat-people-registry.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("person", "alice", name="Alice", metadata={"title": "PI", "department": "Biology"})
    db.close()

    module = PeopleChatModule(
        semantic_registry={
            "schema": {},
            "metadata_hints": {
                "person": {
                    "preferred_fields": ["title", "department", "institution"],
                },
            },
        },
    )
    db = KnowledgeGraphDB(str(db_path))
    chat = ChatToSQL(db, _FakeLLM(), module=module)
    context = chat._schema_context()
    db.close()

    assert "People semantic hints" in context
    assert "title, department, institution" in context


def test_people_module_synthesizes_registry_metadata_filters(tmp_path: Path):
    db_path = tmp_path / "chat-people-synthesize.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("person", "alice", name="Alice", metadata={"title": "PI", "department": "Biology"})
    db.upsert_entity("person", "bob", name="Bob", metadata={"title": "Staff", "department": "Chemistry"})
    db.close()

    sql = """
SELECT e.id, e.name, e.type
FROM entities e
WHERE e.type = 'person'
"""
    db = KnowledgeGraphDB(str(db_path))
    chat = ChatToSQL(db, _StaticSQLLLM(sql), module=PeopleChatModule())
    result = chat.ask("select people in department Chemistry")
    db.close()

    assert result.error is None
    assert result.sql is not None
    assert "json_extract(e.metadata, '$.department') = 'Chemistry'" in result.sql
    assert [row["id"] for row in result.results] == ["bob"]
    assert result.results[0]["department"] == "Chemistry"


def test_people_module_enriches_valid_llm_sql_with_metadata_evidence(tmp_path: Path):
    db_path = tmp_path / "chat-people-valid-metadata.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("person", "bob", name="Bob", metadata={"department": "Chemistry"})
    db.close()

    sql = """
SELECT e.id, e.name, e.type
FROM entities e
WHERE e.type = 'person'
  AND json_extract(e.metadata, '$.department') = 'Chemistry'
"""
    db = KnowledgeGraphDB(str(db_path))
    chat = ChatToSQL(db, _StaticSQLLLM(sql), module=PeopleChatModule())
    result = chat.ask("select people in department Chemistry")
    db.close()

    assert result.error is None
    assert [row["id"] for row in result.results] == ["bob"]
    assert result.results[0]["department"] == "Chemistry"


def test_people_registry_display_policy_controls_projected_alias(tmp_path: Path):
    db_path = tmp_path / "chat-people-display-policy.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("person", "bob", name="Bob", metadata={"department": "Chemistry"})
    db.close()

    registry = load_people_semantic_registry(None)
    registry["operators"]["specs"]["metadata_filters"]["department"]["display"] = {"alias": "department_value"}

    sql = """
SELECT e.id, e.name, e.type
FROM entities e
WHERE e.type = 'person'
"""
    db = KnowledgeGraphDB(str(db_path))
    chat = ChatToSQL(db, _StaticSQLLLM(sql), module=PeopleChatModule(semantic_registry=registry))
    result = chat.ask("select people in department Chemistry")
    db.close()

    assert result.error is None
    assert [row["id"] for row in result.results] == ["bob"]
    assert "department_value" in result.results[0]
    assert result.results[0]["department_value"] == "Chemistry"
    assert "department" not in result.results[0]


def test_people_validation_rejects_unrequested_registry_metadata_filter(tmp_path: Path):
    db_path = tmp_path / "chat-people-unrequested.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("person", "alice", name="Alice", metadata={"title": "PI", "department": "Biology"})
    db.close()

    db = KnowledgeGraphDB(str(db_path))
    chat = ChatToSQL(db, _FakeLLM(), module=PeopleChatModule())
    err = chat._validate_sql_against_schema(
        """
SELECT e.id, e.name, e.type
FROM entities e
WHERE e.type = 'person'
  AND json_extract(e.metadata, '$.department') = 'Biology'
""",
        ["person"],
        "select people",
    )
    db.close()

    assert err is not None
    assert "Unexpected people metadata filter" in err


def test_people_module_synthesizes_registry_contact_filters(tmp_path: Path):
    db_path = tmp_path / "chat-people-contact.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("person", "alice", name="Alice", metadata={"title": "PI"})
    db.upsert_entity("person", "bob", name="Bob", metadata={"title": "Staff"})
    db.conn.execute(
        "INSERT INTO contact_info (entity_id, field, value) VALUES (?, ?, ?)",
        ("alice", "email", "alice@example.org"),
    )
    db.conn.execute(
        "INSERT INTO contact_info (entity_id, field, value) VALUES (?, ?, ?)",
        ("bob", "email", "bob@example.org"),
    )
    db.conn.commit()
    db.close()

    sql = """
SELECT e.id, e.name, e.type
FROM entities e
WHERE e.type = 'person'
"""
    db = KnowledgeGraphDB(str(db_path))
    chat = ChatToSQL(db, _StaticSQLLLM(sql), module=PeopleChatModule())
    result = chat.ask("select people with email bob@example.org")
    db.close()

    assert result.error is None
    assert result.sql is not None
    assert "JOIN contact_info c1 ON c1.entity_id = e.id" in result.sql
    assert "c1.field = 'email'" in result.sql
    assert "c1.value = 'bob@example.org'" in result.sql
    assert [row["id"] for row in result.results] == ["bob"]
    assert result.results[0]["email"] == "bob@example.org"


def test_people_validation_rejects_unrequested_registry_contact_filter(tmp_path: Path):
    db_path = tmp_path / "chat-people-contact-unrequested.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("person", "alice", name="Alice", metadata={"title": "PI"})
    db.conn.execute(
        "INSERT INTO contact_info (entity_id, field, value) VALUES (?, ?, ?)",
        ("alice", "email", "alice@example.org"),
    )
    db.conn.commit()
    db.close()

    db = KnowledgeGraphDB(str(db_path))
    chat = ChatToSQL(db, _FakeLLM(), module=PeopleChatModule())
    err = chat._validate_sql_against_schema(
        """
SELECT e.id, e.name, e.type
FROM entities e
JOIN contact_info c ON c.entity_id = e.id
WHERE e.type = 'person'
  AND c.field = 'email'
  AND c.value = 'alice@example.org'
""",
        ["person"],
        "select people",
    )
    db.close()

    assert err is not None
    assert "Unexpected people contact filter" in err


def test_people_module_synthesizes_registry_relationship_filters(tmp_path: Path):
    db_path = tmp_path / "chat-people-publications.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("person", "alice", name="Alice", metadata={"title": "PI"})
    db.upsert_entity("person", "bob", name="Bob", metadata={"title": "Staff"})
    db.upsert_entity("publication", "paper-1", name="Paper 1", metadata={"title": "Paper 1"})
    db.add_relationship("alice", "AUTHORED", "paper-1")
    db.add_relationship("bob", "AUTHORED", "paper-1")
    db.close()

    sql = """
SELECT e.id, e.name, e.type
FROM entities e
WHERE e.type = 'person'
"""
    db = KnowledgeGraphDB(str(db_path))
    chat = ChatToSQL(db, _StaticSQLLLM(sql), module=PeopleChatModule())
    result = chat.ask("select people with publications")
    db.close()

    assert result.error is None
    assert result.sql is not None
    assert "AUTHORED" in result.sql
    assert "type = 'publication'" in result.sql
    assert [row["id"] for row in result.results] == ["alice", "bob"]
    assert [row["publication_name"] for row in result.results] == ["Paper 1", "Paper 1"]


def test_people_validation_rejects_unrequested_registry_relationship_filter(tmp_path: Path):
    db_path = tmp_path / "chat-people-publications-unrequested.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("person", "alice", name="Alice", metadata={"title": "PI"})
    db.upsert_entity("publication", "paper-1", name="Paper 1", metadata={"title": "Paper 1"})
    db.add_relationship("alice", "AUTHORED", "paper-1")
    db.close()

    db = KnowledgeGraphDB(str(db_path))
    chat = ChatToSQL(db, _FakeLLM(), module=PeopleChatModule())
    err = chat._validate_sql_against_schema(
        """
SELECT e.id, e.name, e.type
FROM entities e
JOIN relationships r ON r.source_id = e.id AND r.rel_type = 'AUTHORED'
JOIN entities t ON t.id = r.target_id AND t.type = 'publication'
WHERE e.type = 'person'
""",
        ["person"],
        "select people",
    )
    db.close()

    assert err is not None
    assert "Unexpected people relationship filter" in err


def test_people_registry_drives_parser_and_renderer_contract(tmp_path: Path):
    db_path = tmp_path / "chat-people-registry-contract.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("person", "alice", name="Alice", metadata={"department": "Biology"})
    db.upsert_entity("person", "bob", name="Bob", metadata={"department": "Chemistry"})
    db.close()

    module = PeopleChatModule(
        semantic_registry={
            "schema": {},
            "metadata_hints": {},
            "operators": {
                "condition_handlers": {
                    "metadata_filter": "metadata_filter",
                },
                "parsers": {
                    "field_value_semicolon": {
                        "mode": "field_value",
                        "split_pattern": r";",
                    },
                },
                "renderers": {
                    "metadata": {
                        "where_templates": [
                            "  AND lower(json_extract(e.metadata, '$.{field}')) = lower('{value}')",
                        ],
                        "validation_signatures": [
                            "$.{field}",
                            "lower('{value}')",
                        ],
                    },
                },
                "specs": {
                    "metadata_filters": {
                        "dept": {
                            "field": "department",
                            "aliases": ["dept"],
                            "parser_kind": "field_value_semicolon",
                        },
                    },
                    "contact_filters": {},
                    "relationship_filters": {},
                },
            },
            "validation": {},
            "paths": {
                "person->person": [],
            },
        },
    )

    sql = """
SELECT e.id, e.name, e.type
FROM entities e
WHERE e.type = 'person'
"""
    db = KnowledgeGraphDB(str(db_path))
    chat = ChatToSQL(db, _StaticSQLLLM(sql), module=module)
    result = chat.ask("select people with dept Chemistry; show matches")
    db.close()

    assert result.error is None
    assert result.sql is not None
    assert "lower(json_extract(e.metadata, '$.department')) = lower('Chemistry')" in result.sql
    assert [row["id"] for row in result.results] == ["bob"]

    db = KnowledgeGraphDB(str(db_path))
    chat = ChatToSQL(db, _FakeLLM(), module=module)
    err = chat._validate_sql_against_schema(
        """
SELECT e.id, e.name, e.type
FROM entities e
WHERE e.type = 'person'
  AND lower(json_extract(e.metadata, '$.department')) = lower('Chemistry')
""",
        ["person"],
        "select people",
    )
    db.close()

    assert err is not None
    assert "Unexpected people metadata filter" in err


def test_ask_includes_people_module_few_shot_examples(tmp_path: Path):
    db_path = tmp_path / "chat-people-few-shot.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("person", "alice", name="Alice", metadata={"title": "PI", "department": "Biology"})
    db.upsert_entity("person", "bob", name="Bob", metadata={"title": "Staff", "department": "Chemistry"})
    db.close()

    db = KnowledgeGraphDB(str(db_path))
    llm = _CaptureLLM()
    chat = ChatToSQL(db, llm, module=PeopleChatModule())
    chat.ask("select people in department Chemistry")
    db.close()

    assert llm.messages is not None
    contents = [str(item.get("content", "")) for item in llm.messages]
    assert any("select people with title PI and department Biology" in content for content in contents)
    assert any("select people in department Chemistry" in content for content in contents)


def test_cross_db_genomics_prompt_bridges_to_downstream_metadata_owner(tmp_path: Path):
    db_path = tmp_path / "chat-gene-protein-metadata.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("gene", "gene-1", name="Gene 1")
    db.upsert_entity("transcript", "tx-1", name="Transcript 1")
    db.upsert_entity("protein", "prot-1", name="Protein 1", metadata={"pfam": "PF00001", "secretion": "secreted"})
    db.add_relationship("gene-1", "HAS_TRANSCRIPT", "tx-1")
    db.add_relationship("tx-1", "TRANSLATED_TO", "prot-1")
    db.close()

    db = KnowledgeGraphDB(str(db_path))
    llm = _MetadataBridgeRetryLLM()
    chat = ChatToSQL(db, llm, module=GenomicsChatModule())
    result = chat.ask("select genes with pfam PF00001 and secretion secreted")
    db.close()

    assert llm.calls == 2
    assert result.error is None
    assert result.sql is not None
    assert "HAS_TRANSCRIPT" in result.sql
    assert "TRANSLATED_TO" in result.sql
    assert "json_extract(owner.metadata, '$.pfam')" in result.sql
    assert result.results
    assert [row["id"] for row in result.results] == ["gene-1"]


def test_ask_retries_when_direct_relationship_origin_conflicts_with_selected_type(tmp_path: Path):
    db_path = tmp_path / "chat-retry.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("gene", "gene-1", name="Gene 1")
    db.upsert_entity("transcript", "tx-1", name="Transcript 1")
    db.upsert_entity("protein", "prot-1", name="Protein 1")
    db.upsert_entity("comparative_hit", "hit-1", name="Hit 1")
    db.add_relationship("gene-1", "HAS_TRANSCRIPT", "tx-1")
    db.add_relationship("tx-1", "TRANSLATED_TO", "prot-1")
    db.add_relationship("prot-1", "HAS_BROAD_HOMOLOGY_HIT", "hit-1")
    db.close()

    db = KnowledgeGraphDB(str(db_path))
    llm = _RetryLLM()
    chat = ChatToSQL(db, llm)
    result = chat.ask("select genes with broad homology hits")
    db.close()

    assert llm.calls == 2
    assert result.sql is not None
    assert "HAS_TRANSCRIPT" in result.sql
    assert "HAS_BROAD_HOMOLOGY_HIT" in result.sql
    assert "e.type = 'gene'" in result.sql


def test_validation_error_includes_bridge_path(tmp_path: Path):
    db_path = tmp_path / "chat-bridge.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("gene", "gene-1", name="Gene 1")
    db.upsert_entity("transcript", "tx-1", name="Transcript 1")
    db.upsert_entity("protein", "prot-1", name="Protein 1")
    db.upsert_entity("comparative_hit", "hit-1", name="Hit 1")
    db.add_relationship("gene-1", "HAS_TRANSCRIPT", "tx-1")
    db.add_relationship("tx-1", "TRANSLATED_TO", "prot-1")
    db.add_relationship("prot-1", "HAS_BROAD_HOMOLOGY_HIT", "hit-1")
    db.close()

    db = KnowledgeGraphDB(str(db_path))
    chat = ChatToSQL(db, _FakeLLM())
    err = chat._validate_sql_against_schema(
        """
SELECT e.id, e.name, e.type
FROM entities e
JOIN relationships r ON e.id = r.source_id
WHERE e.type = 'gene' AND r.rel_type = 'HAS_BROAD_HOMOLOGY_HIT'
""",
        ["gene"],
    )
    db.close()

    assert err is not None
    assert "gene -HAS_TRANSCRIPT-> transcript" in err
    assert "transcript -TRANSLATED_TO-> protein" in err


def test_validation_error_rejects_wrong_result_type(tmp_path: Path):
    db_path = tmp_path / "chat-result-type.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("gene", "gene-1", name="Gene 1")
    db.upsert_entity("orthogroup", "orthogroup:og1", name="OG1")
    db.add_relationship("gene-1", "BELONGS_TO_ORTHOGROUP", "orthogroup:og1")
    db.close()

    db = KnowledgeGraphDB(str(db_path))
    chat = ChatToSQL(db, _FakeLLM())
    err = chat._validate_sql_against_schema(
        """
SELECT e.id, e.name, e.type
FROM entities e
WHERE e.type = 'orthogroup'
  AND 1 = 1
""",
        ["gene"],
    )
    db.close()

    assert err is not None
    assert "Wrong result type" in err
    assert "gene -BELONGS_TO_ORTHOGROUP-> orthogroup" in err


def test_message_entity_match_hints_detect_exact_name_types(tmp_path: Path):
    db_path = tmp_path / "chat-hints.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("tag", "homology-hit-organism:ditylenchus-destructor", name="Ditylenchus destructor")
    db.upsert_entity("comparative_hit", "hit-1", name="KAI1713285.1")
    db.close()

    db = KnowledgeGraphDB(str(db_path))
    chat = ChatToSQL(db, _FakeLLM())
    hints = chat._message_entity_match_hints("select all genes that have broad homology hits for Ditylenchus destructor")
    db.close()

    assert hints
    assert any("Ditylenchus destructor" in hint and "tag" in hint for hint in hints)


def test_ask_populates_debug_trace(tmp_path: Path):
    db_path = tmp_path / "chat-debug.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("gene", "gene-1", name="Gene 1")
    db.close()

    db = KnowledgeGraphDB(str(db_path))
    chat = ChatToSQL(db, _FakeLLM())
    result = chat.ask("select genes")
    db.close()

    assert result.debug
    steps = {item["step"] for item in result.debug}
    assert "requested_result_types" in steps
    assert "initial_sql" in steps


def test_ask_retries_after_zero_rows_using_live_name_matches(tmp_path: Path):
    db_path = tmp_path / "chat-zero-retry.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("protein", "prot-1", name="Protein 1")
    db.upsert_entity("comparative_hit", "hit-1", name="KAI1713285.1")
    db.upsert_entity("tag", "homology-hit-organism:ditylenchus-destructor", name="Ditylenchus destructor")
    db.add_relationship("prot-1", "HAS_BROAD_HOMOLOGY_HIT", "hit-1")
    db.add_relationship("hit-1", "TAGGED", "homology-hit-organism:ditylenchus-destructor")
    db.close()

    db = KnowledgeGraphDB(str(db_path))
    llm = _ZeroRetryLLM()
    chat = ChatToSQL(db, llm)
    result = chat.ask("select proteins that have broad homology hits for Ditylenchus destructor")
    db.close()

    assert llm.calls == 1
    assert result.results
    assert result.results[0]["id"] == "prot-1"
    assert "t.type = 'tag'" in (result.sql or "")


def test_accepted_broad_homology_sql_is_enriched_with_homolog_organism_column(tmp_path: Path):
    db_path = tmp_path / "chat-homology-organism-column.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("protein", "prot-1", name="Protein 1")
    db.upsert_entity("comparative_hit", "hit-1", name="KAI1713285.1")
    db.upsert_entity("tag", "homology-organism:ditylenchus-destructor", name="Ditylenchus destructor")
    db.add_relationship("prot-1", "HAS_BROAD_HOMOLOGY_HIT", "hit-1")
    db.add_relationship("hit-1", "TAGGED", "homology-organism:ditylenchus-destructor")
    db.close()

    llm = _StaticSQLLLM(
        """
SELECT DISTINCT e.id, e.name, e.type
FROM entities e
JOIN relationships ph ON ph.source_id = e.id AND ph.rel_type = 'HAS_BROAD_HOMOLOGY_HIT'
JOIN relationships ht ON ht.source_id = ph.target_id AND ht.rel_type = 'TAGGED'
JOIN entities t ON t.id = ht.target_id
WHERE e.type = 'protein'
  AND t.type = 'tag'
  AND t.name = 'Ditylenchus destructor'
"""
    )
    db = KnowledgeGraphDB(str(db_path))
    chat = ChatToSQL(db, llm, module=GenomicsChatModule())
    result = chat.ask("select proteins that have broad homology hits for Ditylenchus destructor")
    db.close()

    assert result.error is None
    assert result.sql is not None
    assert "AS homolog_organism" in result.sql
    assert result.results[0]["homolog_organism"] == "Ditylenchus destructor"


def test_ask_rewrites_broad_homology_query_to_include_requested_organism_filter(tmp_path: Path):
    db_path = tmp_path / "chat-homology-organism-filter.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("gene", "gene-1", name="Gene 1")
    db.upsert_entity("gene", "gene-2", name="Gene 2")
    db.upsert_entity("transcript", "tx-1", name="Transcript 1")
    db.upsert_entity("transcript", "tx-2", name="Transcript 2")
    db.upsert_entity("protein", "prot-1", name="Protein 1")
    db.upsert_entity("protein", "prot-2", name="Protein 2")
    db.upsert_entity("comparative_hit", "hit-1", name="Hit 1")
    db.upsert_entity("comparative_hit", "hit-2", name="Hit 2")
    db.upsert_entity("tag", "homology-organism:ditylenchus-destructor", name="Ditylenchus destructor")
    db.upsert_entity("tag", "homology-organism:mus-musculus", name="Mus musculus")
    db.add_relationship("gene-1", "HAS_TRANSCRIPT", "tx-1")
    db.add_relationship("gene-2", "HAS_TRANSCRIPT", "tx-2")
    db.add_relationship("tx-1", "TRANSLATED_TO", "prot-1")
    db.add_relationship("tx-2", "TRANSLATED_TO", "prot-2")
    db.add_relationship("prot-1", "HAS_BROAD_HOMOLOGY_HIT", "hit-1")
    db.add_relationship("prot-2", "HAS_BROAD_HOMOLOGY_HIT", "hit-2")
    db.add_relationship("hit-1", "TAGGED", "homology-organism:ditylenchus-destructor")
    db.add_relationship("hit-2", "TAGGED", "homology-organism:mus-musculus")
    db.close()

    llm = _StaticSQLLLM(
        """
SELECT DISTINCT e.id, e.name, e.type
FROM entities e
JOIN relationships gt ON gt.source_id = e.id AND gt.rel_type = 'HAS_TRANSCRIPT'
JOIN relationships tp ON tp.source_id = gt.target_id AND tp.rel_type = 'TRANSLATED_TO'
JOIN relationships ph ON ph.source_id = tp.target_id AND ph.rel_type = 'HAS_BROAD_HOMOLOGY_HIT'
JOIN entities hit ON hit.id = ph.target_id AND hit.type = 'comparative_hit'
WHERE e.type = 'gene'
"""
    )
    db = KnowledgeGraphDB(str(db_path))
    chat = ChatToSQL(db, llm, module=GenomicsChatModule())
    result = chat.ask("select genes that have broad homology hits for Ditylenchus destructor")
    db.close()

    assert result.error is None
    assert result.sql is not None
    assert "homology-organism:ditylenchus-destructor" in result.sql
    assert "AS homolog_organism" in result.sql
    assert [row["id"] for row in result.results] == ["gene-1"]
    assert result.results[0]["homolog_organism"] == "Ditylenchus destructor"


def test_synthesizes_gene_bridge_query_from_zero_row_direct_evidence_sql(tmp_path: Path):
    db_path = tmp_path / "chat-synth.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("gene", "gene-1", name="Gene 1")
    db.upsert_entity("transcript", "tx-1", name="Transcript 1")
    db.upsert_entity("protein", "prot-1", name="Protein 1")
    db.upsert_entity("comparative_hit", "hit-1", name="KAI1713285.1")
    db.upsert_entity("tag", "homology-hit-organism:ditylenchus-destructor", name="Ditylenchus destructor")
    db.add_relationship("gene-1", "HAS_TRANSCRIPT", "tx-1")
    db.add_relationship("tx-1", "TRANSLATED_TO", "prot-1")
    db.add_relationship("prot-1", "HAS_BROAD_HOMOLOGY_HIT", "hit-1")
    db.add_relationship("hit-1", "TAGGED", "homology-hit-organism:ditylenchus-destructor")
    db.close()

    db = KnowledgeGraphDB(str(db_path))
    chat = ChatToSQL(db, _FakeLLM())
    sql = chat._synthesize_typed_path_query(
        """
SELECT e.id, e.name, e.type
FROM entities e
JOIN relationships r ON e.id = r.source_id
WHERE r.rel_type = 'HAS_BROAD_HOMOLOGY_HIT'
AND EXISTS (
    SELECT 1
    FROM entities e2
    JOIN relationships r2 ON e2.id = r2.target_id
    WHERE r2.source_id = e.id
      AND e2.name = 'Ditylenchus destructor'
)
AND e.type = 'gene'
""",
        ["gene"],
    )
    assert sql is not None
    rows = db.execute_read(sql)
    db.close()

    assert "p1.rel_type = 'HAS_TRANSCRIPT'" in sql
    assert "p2.rel_type = 'TRANSLATED_TO'" in sql
    assert "ev.rel_type = 'HAS_BROAD_HOMOLOGY_HIT'" in sql
    assert "t.name = 'Ditylenchus destructor'" in sql
    assert rows
    assert rows[0]["id"] == "gene-1"


def test_synthesizes_ortholog_copy_query_from_count_map_misread(tmp_path: Path):
    db_path = tmp_path / "chat-ortholog-count.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("gene", "gene-1", name="Gene 1")
    db.upsert_entity("orthogroup", "orthogroup:og1", name="OG1", metadata={
        "organism": "Heterodera glycines",
        "gene_counts": {
            "Heterodera glycines": 1,
            "Heterodera schachtii": 3,
        },
    })
    db.add_relationship("gene-1", "BELONGS_TO_ORTHOGROUP", "orthogroup:og1")
    db.close()

    db = KnowledgeGraphDB(str(db_path))
    chat = ChatToSQL(db, _FakeLLM(), module=GenomicsChatModule())
    sql = chat.module.synthesize_query(
        chat,
        "select genes with 3 or more ortholog gene copies",
        """
SELECT e.id, e.name, e.type, json_extract(e.metadata, '$.gene_counts') as gene_counts
FROM entities e
JOIN relationships r ON e.id = r.source_id
WHERE r.rel_type = 'BELONGS_TO_ORTHOGROUP'
AND e.type = 'gene'
AND json_extract(e.metadata, '$.gene_counts') IS NOT NULL
AND (
    (json_extract(e.metadata, '$.gene_counts.\"Ditylenchus destructor\"') >= 3)
)
""",
        ["gene"],
    )
    assert sql is not None
    rows = db.execute_read(sql)
    db.close()

    assert "JOIN entities owner ON owner.id = p1.target_id AND owner.type = 'orthogroup'" in sql
    assert "gc.key != json_extract(owner.metadata, '$.organism')" in sql
    assert "HAVING MAX(CAST(gc.value AS INTEGER)) >= 3" in sql
    assert rows
    assert rows[0]["id"] == "gene-1"
    assert rows[0]["ortholog_copy_count"] == 3


def test_zero_result_count_map_fallback_still_returns_corrected_sql(tmp_path: Path):
    db_path = tmp_path / "chat-ortholog-zero.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("gene", "gene-1", name="Gene 1")
    db.upsert_entity("orthogroup", "orthogroup:og1", name="OG1", metadata={
        "organism": "Heterodera glycines",
        "gene_counts": {
            "Heterodera glycines": 1,
            "Heterodera schachtii": 1,
        },
    })
    db.add_relationship("gene-1", "BELONGS_TO_ORTHOGROUP", "orthogroup:og1")
    db.close()

    class _BadOrthologLLM:
        def chat(self, messages):
            return """```sql
SELECT e.id, e.name, e.type, json_extract(e.metadata, '$.orthogroup') as orthogroup_id
FROM entities e
WHERE e.type = 'gene'
AND (
    SELECT COUNT(*)
    FROM relationships r
    WHERE r.source_id = e.id
      AND r.rel_type = 'BELONGS_TO_ORTHOGROUP'
) >= 3
ORDER BY e.name
```"""

    db = KnowledgeGraphDB(str(db_path))
    chat = ChatToSQL(db, _BadOrthologLLM(), module=GenomicsChatModule())
    result = chat.ask("select genes with 3 or more ortholog gene copies")
    db.close()

    assert result.sql is not None
    assert "JOIN entities owner ON owner.id = p1.target_id AND owner.type = 'orthogroup'" in result.sql
    assert "JOIN json_each(owner.metadata, '$.gene_counts') gc" in result.sql
    assert result.results == []


def test_ask_rewrites_plain_ortholog_copy_count_query_to_gene_counts_owner(tmp_path: Path):
    db_path = tmp_path / "chat-ortholog-plain-count.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("gene", "gene-1", name="Gene 1")
    db.upsert_entity("gene", "gene-2", name="Gene 2")
    db.upsert_entity("orthogroup", "orthogroup:og1", name="OG1", metadata={
        "organism": "Heterodera glycines",
        "gene_counts": {
            "Heterodera glycines": 1,
            "Heterodera schachtii": 2,
        },
    })
    db.upsert_entity("orthogroup", "orthogroup:og2", name="OG2", metadata={
        "organism": "Heterodera glycines",
        "gene_counts": {
            "Heterodera glycines": 1,
            "Heterodera schachtii": 1,
        },
    })
    db.add_relationship("gene-1", "BELONGS_TO_ORTHOGROUP", "orthogroup:og1")
    db.add_relationship("gene-2", "BELONGS_TO_ORTHOGROUP", "orthogroup:og2")
    db.close()

    class _PlainBadOrthologCountLLM:
        def chat(self, messages):
            return """```sql
SELECT e.id, e.name, e.type
FROM entities e
WHERE e.type = 'gene'
AND (
    SELECT COUNT(*)
    FROM relationships r
    WHERE r.source_id = e.id
) >= 2
ORDER BY e.name
```"""

    db = KnowledgeGraphDB(str(db_path))
    chat = ChatToSQL(db, _PlainBadOrthologCountLLM(), module=GenomicsChatModule())
    result = chat.ask("select genes with 2 or more ortholog gene copies")
    db.close()

    assert result.error is None
    assert result.sql is not None
    assert "JOIN entities owner ON owner.id = p1.target_id AND owner.type = 'orthogroup'" in result.sql
    assert "JOIN json_each(owner.metadata, '$.gene_counts') gc" in result.sql
    assert "HAVING MAX(CAST(gc.value AS INTEGER)) >= 2" in result.sql
    assert [row["id"] for row in result.results] == ["gene-1"]
    assert result.results[0]["owner_organism"] == "Heterodera glycines"
    assert result.results[0]["ortholog_copy_count"] == 2
    assert result.results[0]["ortholog_organisms"] == "Heterodera schachtii"
    assert "Heterodera schachtii" in str(result.results[0]["gene_counts"])


def test_ask_rewrites_nonzero_ortholog_count_query_to_gene_counts_owner(tmp_path: Path):
    db_path = tmp_path / "chat-ortholog-nonzero-bad.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("gene", "gene-1", name="Gene 1")
    db.upsert_entity("transcript", "tx-1", name="Transcript 1")
    db.upsert_entity("orthogroup", "orthogroup:og1", name="OG1", metadata={
        "organism": "Heterodera glycines",
        "gene_counts": {
            "Heterodera glycines": 1,
            "Heterodera schachtii": 2,
        },
    })
    db.add_relationship("gene-1", "HAS_TRANSCRIPT", "tx-1")
    db.add_relationship("gene-1", "BELONGS_TO_ORTHOGROUP", "orthogroup:og1")
    db.close()

    class _BadNonzeroOrthologLLM:
        def chat(self, messages):
            return """```sql
SELECT e.id, e.name, e.type
FROM entities e
WHERE e.type = 'gene'
AND (
    SELECT COUNT(*)
    FROM relationships r
    WHERE r.source_id = e.id
) >= 2
ORDER BY e.name
```"""

    db = KnowledgeGraphDB(str(db_path))
    chat = ChatToSQL(db, _BadNonzeroOrthologLLM(), module=GenomicsChatModule())
    result = chat.ask("select genes with 2 or more ortholog gene copies")
    db.close()

    assert result.error is None
    assert result.sql is not None
    assert "JOIN json_each(owner.metadata, '$.gene_counts') gc" in result.sql
    assert "HAVING MAX(CAST(gc.value AS INTEGER)) >= 2" in result.sql
    assert [row["id"] for row in result.results] == ["gene-1"]
    assert result.results[0]["ortholog_copy_count"] == 2


def test_ask_rewrites_bison_style_ortholog_count_query_to_member_edge_count(tmp_path: Path):
    db_path = tmp_path / "chat-bison-ortholog-member-count.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("gene", "gene-1", name="Gene 1")
    db.upsert_entity("orthogroup", "orthogroup:og1", name="OG1", metadata={
        "organism": "Bison bison",
        "gene_counts": {
            "Bison bison": 1,
        },
    })
    db.upsert_entity("comparative_hit", "hit-1", name="Bos ortholog 1", metadata={"organism": "Bos taurus"})
    db.upsert_entity("comparative_hit", "hit-2", name="Bos ortholog 2", metadata={"organism": "Bos taurus"})
    db.upsert_entity("comparative_hit", "hit-3", name="Bos ortholog 3", metadata={"organism": "Bos taurus"})
    db.add_relationship("gene-1", "BELONGS_TO_ORTHOGROUP", "orthogroup:og1")
    db.add_relationship("orthogroup:og1", "HAS_ORTHOLOG_MEMBER", "hit-1")
    db.add_relationship("orthogroup:og1", "HAS_ORTHOLOG_MEMBER", "hit-2")
    db.add_relationship("orthogroup:og1", "HAS_ORTHOLOG_MEMBER", "hit-3")
    db.close()

    class _BadBisonOrthologCountLLM:
        def chat(self, messages):
            return """```sql
SELECT e.id, e.name, e.type
FROM entities e
WHERE e.type = 'gene'
AND (
    SELECT COUNT(*)
    FROM relationships r
    WHERE r.source_id = e.id
) >= 3
ORDER BY e.name
```"""

    db = KnowledgeGraphDB(str(db_path))
    chat = ChatToSQL(db, _BadBisonOrthologCountLLM(), module=GenomicsChatModule())
    result = chat.ask("select genes with 3 or more ortholog gene copies")
    db.close()

    assert result.error is None
    assert result.sql is not None
    assert "HAS_ORTHOLOG_MEMBER" in result.sql
    assert "COUNT(DISTINCT member.id) >= 3" in result.sql
    assert [row["id"] for row in result.results] == ["gene-1"]
    assert result.results[0]["ortholog_copy_count"] == 3
    assert "Bos taurus" in str(result.results[0]["ortholog_organisms"])


def test_ask_rewrites_bison_style_ortholog_count_query_with_organism_filter(tmp_path: Path):
    db_path = tmp_path / "chat-bison-ortholog-member-organism-count.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("gene", "gene-1", name="Gene 1")
    db.upsert_entity("gene", "gene-2", name="Gene 2")
    db.upsert_entity("organism", "organism:cervus-canadensis", name="Cervus canadensis")
    db.upsert_entity("orthogroup", "orthogroup:og1", name="OG1", metadata={
        "organism": "Bison bison",
        "gene_counts": {
            "Bison bison": 1,
        },
    })
    db.upsert_entity("orthogroup", "orthogroup:og2", name="OG2", metadata={
        "organism": "Bison bison",
        "gene_counts": {
            "Bison bison": 1,
        },
    })
    for idx in range(3):
        db.upsert_entity(f"comparative_hit", f"cervus-{idx}", name=f"Cervus ortholog {idx}", metadata={"organism": "Cervus canadensis"})
    db.upsert_entity("comparative_hit", "cervus-x", name="Cervus ortholog x", metadata={"organism": "Cervus canadensis"})
    db.upsert_entity("comparative_hit", "bos-1", name="Bos ortholog 1", metadata={"organism": "Bos taurus"})
    db.upsert_entity("comparative_hit", "bos-2", name="Bos ortholog 2", metadata={"organism": "Bos taurus"})
    db.add_relationship("gene-1", "BELONGS_TO_ORTHOGROUP", "orthogroup:og1")
    db.add_relationship("gene-2", "BELONGS_TO_ORTHOGROUP", "orthogroup:og2")
    db.add_relationship("orthogroup:og1", "HAS_ORTHOLOG_MEMBER", "cervus-0")
    db.add_relationship("orthogroup:og1", "HAS_ORTHOLOG_MEMBER", "cervus-1")
    db.add_relationship("orthogroup:og1", "HAS_ORTHOLOG_MEMBER", "bos-1")
    db.add_relationship("orthogroup:og2", "HAS_ORTHOLOG_MEMBER", "cervus-0")
    db.add_relationship("orthogroup:og2", "HAS_ORTHOLOG_MEMBER", "cervus-1")
    db.add_relationship("orthogroup:og2", "HAS_ORTHOLOG_MEMBER", "cervus-2")
    db.add_relationship("orthogroup:og2", "HAS_ORTHOLOG_MEMBER", "cervus-x")
    db.add_relationship("orthogroup:og2", "HAS_ORTHOLOG_MEMBER", "bos-2")
    db.close()

    class _BadBisonOrthologOrganismCountLLM:
        def chat(self, messages):
            return """```sql
SELECT e.id, e.name, e.type
FROM entities e
WHERE e.type = 'gene'
AND (
    SELECT COUNT(*)
    FROM relationships r
    WHERE r.source_id = e.id
) >= 2
ORDER BY e.name
```"""

    db = KnowledgeGraphDB(str(db_path))
    chat = ChatToSQL(db, _BadBisonOrthologOrganismCountLLM(), module=GenomicsChatModule())
    result = chat.ask("select genes with 2 or more ortholog gene copies from Cervus canadensis")
    db.close()

    assert result.error is None
    assert result.sql is not None
    assert "json_extract(member.metadata, '$.organism') IN ('Cervus canadensis')" in result.sql
    assert [row["id"] for row in result.results] == ["gene-1", "gene-2"]
    assert result.results[0]["ortholog_copy_count"] == 2
    assert result.results[0]["ortholog_organisms"] == "Cervus canadensis"
    assert result.results[1]["ortholog_copy_count"] == 4
    assert result.results[1]["ortholog_organisms"] == "Cervus canadensis"


def test_synthesizes_gene_query_from_owner_side_orthogroup_count_sql(tmp_path: Path):
    db_path = tmp_path / "chat-owner-side-count.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("gene", "gene-1", name="Gene 1")
    db.upsert_entity("orthogroup", "orthogroup:og1", name="OG1", metadata={
        "organism": "Heterodera glycines",
        "gene_counts": {
            "Heterodera glycines": 1,
            "Heterodera schachtii": 3,
        },
    })
    db.add_relationship("gene-1", "BELONGS_TO_ORTHOGROUP", "orthogroup:og1")
    db.close()

    db = KnowledgeGraphDB(str(db_path))
    chat = ChatToSQL(db, _FakeLLM(), module=GenomicsChatModule())
    sql = chat.module.synthesize_query(
        chat,
        "select genes with 3 or more ortholog gene copies",
        """
SELECT e.id, e.name, e.type, json_extract(e.metadata, '$.organism') AS organism, json_extract(e.metadata, '$.gene_counts') AS gene_counts
FROM entities e
WHERE e.type = 'orthogroup'
AND json_extract(e.metadata, '$.gene_counts') IS NOT NULL
AND (
    SELECT COUNT(*)
    FROM json_each(json_extract(e.metadata, '$.gene_counts'))
    WHERE value > 0
) >= 1
ORDER BY e.name
""",
        ["gene"],
    )
    assert sql is not None
    rows = db.execute_read(sql)
    db.close()

    assert "JOIN relationships p1 ON p1.source_id = e.id AND p1.rel_type = 'BELONGS_TO_ORTHOGROUP'" in sql
    assert "JOIN entities owner ON owner.id = p1.target_id AND owner.type = 'orthogroup'" in sql
    assert "HAVING MAX(CAST(gc.value AS INTEGER)) >= 3" in sql
    assert rows
    assert rows[0]["id"] == "gene-1"


def test_validation_error_rejects_counting_orthogroup_edges_for_ortholog_copies(tmp_path: Path):
    db_path = tmp_path / "chat-ortholog-edge-count.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("gene", "gene-1", name="Gene 1")
    db.upsert_entity("orthogroup", "orthogroup:og1", name="OG1", metadata={
        "organism": "Heterodera glycines",
        "gene_counts": {"Heterodera glycines": 1, "Heterodera schachtii": 3},
    })
    db.add_relationship("gene-1", "BELONGS_TO_ORTHOGROUP", "orthogroup:og1")
    db.close()

    db = KnowledgeGraphDB(str(db_path))
    chat = ChatToSQL(db, _FakeLLM(), module=GenomicsChatModule())
    err = chat._validate_sql_against_schema(
        """
SELECT e.id, e.name, e.type
FROM entities e
WHERE e.type = 'gene'
AND (
    SELECT COUNT(*)
    FROM relationships r
    WHERE r.source_id = e.id
      AND r.rel_type = 'BELONGS_TO_ORTHOGROUP'
) >= 3
""",
        ["gene"],
        "select genes with 3 or more ortholog gene copies",
    )
    db.close()

    assert err is not None
    assert "Wrong counting strategy" in err
    assert "metadata.gene_counts" in err


def test_validation_error_rejects_reading_gene_counts_from_gene_metadata(tmp_path: Path):
    db_path = tmp_path / "chat-gene-count-owner.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("gene", "gene-1", name="Gene 1")
    db.upsert_entity("orthogroup", "orthogroup:og1", name="OG1", metadata={
        "organism": "Heterodera glycines",
        "gene_counts": {"Heterodera glycines": 1, "Heterodera schachtii": 3},
    })
    db.add_relationship("gene-1", "BELONGS_TO_ORTHOGROUP", "orthogroup:og1")
    db.close()

    db = KnowledgeGraphDB(str(db_path))
    chat = ChatToSQL(db, _FakeLLM())
    err = chat._validate_sql_against_schema(
        """
SELECT e.id, e.name, e.type, json_extract(e.metadata, '$.gene_counts') as gene_counts
FROM entities e
WHERE e.type = 'gene'
AND json_extract(e.metadata, '$.gene_counts') IS NOT NULL
AND (
    SELECT COUNT(*)
    FROM json_each(json_extract(e.metadata, '$.gene_counts'))
    WHERE value >= 3
) > 0
""",
        ["gene"],
    )
    db.close()

    assert err is not None
    assert "Wrong metadata owner" in err
    assert "orthogroup" in err
    assert "gene -BELONGS_TO_ORTHOGROUP-> orthogroup" in err


def test_ask_synthesizes_gene_bridge_query_for_hgt_donor(tmp_path: Path):
    db_path = tmp_path / "chat-hgt.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("gene", "gene-1", name="Gene 1")
    db.upsert_entity("transcript", "tx-1", name="Transcript 1")
    db.upsert_entity("protein", "prot-1", name="Protein 1")
    db.upsert_entity("hgt_donor", "donor-1", name="WP_194067917")
    db.add_relationship("gene-1", "HAS_TRANSCRIPT", "tx-1")
    db.add_relationship("tx-1", "TRANSLATED_TO", "prot-1")
    db.add_relationship("prot-1", "HAS_HGT_DONOR", "donor-1", metadata={"hgt_alien_index": "0.56"})
    db.close()

    db = KnowledgeGraphDB(str(db_path))
    llm = _HgtRetryLLM()
    chat = ChatToSQL(db, llm, module=GenomicsChatModule())
    result = chat.ask("select all genes that have HGT donor")
    db.close()

    assert result.results
    assert result.results[0]["id"] == "gene-1"
    assert "HAS_TRANSCRIPT" in (result.sql or "")
    assert "TRANSLATED_TO" in (result.sql or "")
    assert "HAS_HGT_DONOR" in (result.sql or "")
    assert "e.type = 'gene'" in (result.sql or "")


def test_ask_synthesizes_gene_bridge_query_for_horizontal_gene_transfer(tmp_path: Path):
    db_path = tmp_path / "chat-hgt-alt.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("gene", "gene-1", name="Gene 1")
    db.upsert_entity("transcript", "tx-1", name="Transcript 1")
    db.upsert_entity("protein", "prot-1", name="Protein 1")
    db.upsert_entity("hgt_donor", "donor-1", name="WP_194067917")
    db.add_relationship("gene-1", "HAS_TRANSCRIPT", "tx-1")
    db.add_relationship("tx-1", "TRANSLATED_TO", "prot-1")
    db.add_relationship("prot-1", "HAS_HGT_DONOR", "donor-1", metadata={"hgt_alien_index": "0.56"})
    db.close()

    db = KnowledgeGraphDB(str(db_path))
    llm = _HgtRetryLLM()
    chat = ChatToSQL(db, llm, module=GenomicsChatModule())
    result = chat.ask("select all genes with horizontal gene transfer")
    db.close()

    assert result.results
    assert result.results[0]["id"] == "gene-1"
    assert "HAS_HGT_DONOR" in (result.sql or "")


def test_ask_returns_hgt_donor_nodes_for_hgt_donor_request(tmp_path: Path):
    db_path = tmp_path / "chat-hgt-donor-result-type.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("gene", "gene-1", name="Gene 1")
    db.upsert_entity("transcript", "tx-1", name="Transcript 1")
    db.upsert_entity("protein", "prot-1", name="Protein 1")
    db.upsert_entity("hgt_donor", "donor-1", name="WP_194067917")
    db.add_relationship("gene-1", "HAS_TRANSCRIPT", "tx-1")
    db.add_relationship("tx-1", "TRANSLATED_TO", "prot-1")
    db.add_relationship("prot-1", "HAS_HGT_DONOR", "donor-1", metadata={"hgt_alien_index": "0.56"})
    db.close()

    class _WrongGeneHgtLLM:
        def chat(self, messages):
            return """```sql
SELECT e.id, e.name, e.type
FROM entities e
JOIN relationships r ON e.id = r.source_id
WHERE r.rel_type = 'HAS_HGT_DONOR'
AND e.type = 'gene'
```"""

    db = KnowledgeGraphDB(str(db_path))
    chat = ChatToSQL(db, _WrongGeneHgtLLM(), module=GenomicsChatModule())
    result = chat.ask("select horizontal gene transfer donors")
    db.close()

    assert result.error is None
    assert result.sql is not None
    assert "r.target_id = e.id" in result.sql
    assert "e.type = 'hgt_donor'" in result.sql
    assert [row["id"] for row in result.results] == ["donor-1"]


def test_ask_returns_homology_organism_tags_for_broad_homology_organisms(tmp_path: Path):
    db_path = tmp_path / "chat-broad-homology-organisms.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("protein", "prot-1", name="Protein 1")
    db.upsert_entity("comparative_hit", "hit-1", name="Q04456.1")
    db.upsert_entity("tag", "homology-organism", name="Homology Organism")
    db.upsert_entity("tag", "homology-organism:ditylenchus-destructor", name="Ditylenchus destructor")
    db.upsert_entity("tag", "homology-scope-broad-parasitism", name="Broad Parasitism")
    db.add_relationship("prot-1", "HAS_BROAD_HOMOLOGY_HIT", "hit-1")
    db.add_relationship("hit-1", "TAGGED", "homology-organism:ditylenchus-destructor")
    db.add_relationship("hit-1", "TAGGED", "homology-scope-broad-parasitism")
    db.add_relationship("homology-organism:ditylenchus-destructor", "BROADER", "homology-organism")
    db.close()

    class _WrongBroadHomologyResultLLM:
        def chat(self, messages):
            return """```sql
SELECT e.id, e.name, e.type
FROM entities e
WHERE e.type = 'comparative_hit'
```"""

    db = KnowledgeGraphDB(str(db_path))
    chat = ChatToSQL(db, _WrongBroadHomologyResultLLM(), module=GenomicsChatModule())
    result = chat.ask("select all broad homology organisms")
    db.close()

    assert result.error is None
    assert result.sql is not None
    assert "e.id LIKE 'homology-organism:%'" in result.sql
    assert "scope_tag.id = 'homology-scope-broad-parasitism'" in result.sql
    assert [row["id"] for row in result.results] == ["homology-organism:ditylenchus-destructor"]
    assert result.results[0]["tag_group"] == "Homology Organism"
    assert result.results[0]["homology_scope"] == "Broad Parasitism"


def test_ask_returns_homology_organism_tags_for_broad_parasitism_driver_tags(tmp_path: Path):
    db_path = tmp_path / "chat-broad-parasitism-driver-tags.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("protein", "prot-1", name="Protein 1")
    db.upsert_entity("comparative_hit", "hit-1", name="Q04456.1")
    db.upsert_entity("tag", "homology-organism", name="Homology Organism")
    db.upsert_entity("tag", "homology-organism:caenorhabditis-briggsae", name="Caenorhabditis briggsae")
    db.upsert_entity("tag", "homology-scope-broad-parasitism", name="Broad Parasitism")
    db.add_relationship("prot-1", "HAS_BROAD_HOMOLOGY_HIT", "hit-1")
    db.add_relationship("hit-1", "TAGGED", "homology-organism:caenorhabditis-briggsae")
    db.add_relationship("hit-1", "TAGGED", "homology-scope-broad-parasitism")
    db.add_relationship("homology-organism:caenorhabditis-briggsae", "BROADER", "homology-organism")
    db.close()

    class _MissingEvidenceTagLLM:
        def chat(self, messages):
            return """```sql
SELECT e.id, e.name, e.type
FROM entities e
WHERE e.type = 'tag'
```"""

    db = KnowledgeGraphDB(str(db_path))
    chat = ChatToSQL(db, _MissingEvidenceTagLLM(), module=GenomicsChatModule())
    result = chat.ask("select all organism tags driving broad parasitism")
    db.close()

    assert result.error is None
    assert result.sql is not None
    assert "ev.target_id = hit.id AND ev.rel_type = 'HAS_BROAD_HOMOLOGY_HIT'" in result.sql
    assert [row["id"] for row in result.results] == ["homology-organism:caenorhabditis-briggsae"]


def test_ask_synthesizes_protein_hgt_query_with_orthogroup_filter(tmp_path: Path):
    db_path = tmp_path / "chat-hgt-og.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("gene", "gene-1", name="Gene 1")
    db.upsert_entity("transcript", "tx-1", name="Transcript 1")
    db.upsert_entity("protein", "prot-1", name="Protein 1")
    db.upsert_entity("orthogroup", "orthogroup:og0005830", name="OG0005830")
    db.upsert_entity("hgt_donor", "donor-1", name="WP_194067917")
    db.add_relationship("gene-1", "HAS_TRANSCRIPT", "tx-1")
    db.add_relationship("tx-1", "TRANSLATED_TO", "prot-1")
    db.add_relationship("gene-1", "BELONGS_TO_ORTHOGROUP", "orthogroup:og0005830")
    db.add_relationship("prot-1", "HAS_HGT_DONOR", "donor-1", metadata={"hgt_alien_index": "0.56"})
    db.close()

    db = KnowledgeGraphDB(str(db_path))
    chat = ChatToSQL(db, _HgtOrthogroupRetryLLM(), module=GenomicsChatModule())
    result = chat.ask("does any protein has HGT donor and belongs to orthogroup OG0005830?")
    db.close()

    assert result.results
    assert result.results[0]["id"] == "prot-1"
    assert "TRANSLATED_TO" in (result.sql or "")
    assert "BELONGS_TO_ORTHOGROUP" in (result.sql or "")
    assert "OG0005830" in (result.sql or "")
    assert result.results[0]["orthogroup_label"] == "OG0005830"


def test_genomics_module_enriches_valid_llm_sql_with_condition_evidence(tmp_path: Path):
    db_path = tmp_path / "chat-genomics-valid-condition.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("gene", "gene-1", name="Gene 1")
    db.upsert_entity("transcript", "tx-1", name="Transcript 1")
    db.upsert_entity("protein", "prot-1", name="Protein 1")
    db.upsert_entity("orthogroup", "orthogroup:og0005830", name="OG0005830")
    db.upsert_entity("hgt_donor", "donor-1", name="WP_194067917")
    db.add_relationship("gene-1", "HAS_TRANSCRIPT", "tx-1")
    db.add_relationship("tx-1", "TRANSLATED_TO", "prot-1")
    db.add_relationship("gene-1", "BELONGS_TO_ORTHOGROUP", "orthogroup:og0005830")
    db.add_relationship("prot-1", "HAS_HGT_DONOR", "donor-1")
    db.close()

    sql = """
SELECT DISTINCT e.id, e.name, e.type
FROM entities e
JOIN relationships p1 ON p1.target_id = e.id AND p1.rel_type = 'TRANSLATED_TO'
JOIN relationships p2 ON p2.target_id = p1.source_id AND p2.rel_type = 'HAS_TRANSCRIPT'
JOIN relationships ev3 ON ev3.source_id = e.id AND ev3.rel_type = 'HAS_HGT_DONOR'
JOIN entities t4 ON t4.id = ev3.target_id AND t4.type = 'hgt_donor'
JOIN relationships ogm4 ON ogm4.source_id = p2.source_id AND ogm4.rel_type = 'BELONGS_TO_ORTHOGROUP'
JOIN entities owner5 ON owner5.id = ogm4.target_id AND owner5.type = 'orthogroup'
WHERE e.type = 'protein'
  AND (upper(owner5.name) = 'OG0005830' OR upper(owner5.id) = 'ORTHOGROUP:OG0005830')
"""
    db = KnowledgeGraphDB(str(db_path))
    chat = ChatToSQL(db, _StaticSQLLLM(sql), module=GenomicsChatModule())
    result = chat.ask("does any protein has HGT donor and belongs to orthogroup OG0005830?")
    db.close()

    assert result.error is None
    assert [row["id"] for row in result.results] == ["prot-1"]
    assert result.results[0]["orthogroup_label"] == "OG0005830"


def test_genomics_registry_display_policy_controls_semantic_condition_alias(tmp_path: Path):
    db_path = tmp_path / "chat-genomics-condition-display.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("gene", "gene-1", name="Gene 1")
    db.upsert_entity("transcript", "tx-1", name="Transcript 1")
    db.upsert_entity("protein", "prot-1", name="Protein 1")
    db.upsert_entity("orthogroup", "orthogroup:og0005830", name="OG0005830")
    db.upsert_entity("hgt_donor", "donor-1", name="WP_194067917")
    db.add_relationship("gene-1", "HAS_TRANSCRIPT", "tx-1")
    db.add_relationship("tx-1", "TRANSLATED_TO", "prot-1")
    db.add_relationship("gene-1", "BELONGS_TO_ORTHOGROUP", "orthogroup:og0005830")
    db.add_relationship("prot-1", "HAS_HGT_DONOR", "donor-1")
    db.close()

    registry = load_semantic_registry(None)
    registry["operators"]["specs"]["orthogroup_filter"]["display"] = [
        {"alias": "selected_orthogroup", "value_ref": "label"},
    ]

    db = KnowledgeGraphDB(str(db_path))
    chat = ChatToSQL(db, _HgtOrthogroupRetryLLM(), module=GenomicsChatModule(semantic_registry=registry))
    result = chat.ask("does any protein has HGT donor and belongs to orthogroup OG0005830?")
    db.close()

    assert result.error is None
    assert result.results[0]["selected_orthogroup"] == "OG0005830"
    assert "orthogroup_label" not in result.results[0]


def test_ask_synthesizes_protein_query_for_hgt_and_broad_parasitism(tmp_path: Path):
    db_path = tmp_path / "chat-hgt-broad.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("gene", "gene-1", name="Gene 1")
    db.upsert_entity("transcript", "tx-1", name="Transcript 1")
    db.upsert_entity("protein", "prot-1", name="Protein 1")
    db.upsert_entity("hgt_donor", "donor-1", name="WP_194067917")
    db.upsert_entity("comparative_hit", "hit-1", name="Q04456.1")
    db.upsert_entity("tag", "homology-scope-broad-parasitism", name="Broad Parasitism")
    db.add_relationship("gene-1", "HAS_TRANSCRIPT", "tx-1")
    db.add_relationship("tx-1", "TRANSLATED_TO", "prot-1")
    db.add_relationship("prot-1", "HAS_HGT_DONOR", "donor-1", metadata={"hgt_alien_index": "0.56"})
    db.add_relationship("prot-1", "HAS_BROAD_HOMOLOGY_HIT", "hit-1")
    db.add_relationship("hit-1", "TAGGED", "homology-scope-broad-parasitism")
    db.close()

    class _HgtBroadLLM:
        def chat(self, messages):
            return """```sql
SELECT e.id, e.name, e.type
FROM entities e
JOIN relationships r ON e.id = r.source_id
WHERE r.rel_type = 'HAS_HGT_DONOR'
AND e.type = 'protein'
```"""

    db = KnowledgeGraphDB(str(db_path))
    chat = ChatToSQL(db, _HgtBroadLLM(), module=GenomicsChatModule())
    result = chat.ask("select proteins with HGT donor and broad parasitism")
    db.close()

    assert result.results
    assert result.results[0]["id"] == "prot-1"
    assert "HAS_HGT_DONOR" in (result.sql or "")
    assert "HAS_BROAD_HOMOLOGY_HIT" in (result.sql or "")
    assert result.results[0]["hgt_donor"] == "WP_194067917"
    assert result.results[0]["homology_scope"] == "Broad Parasitism"


def test_synthesizes_protein_query_for_scn_known_effectors(tmp_path: Path):
    db_path = tmp_path / "chat-scn-effectors.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("organism", "organism:heterodera-glycines", name="Heterodera glycines")
    db.upsert_entity("chromosome", "chromosome:heterodera-glycines:chr1", name="chr1")
    db.upsert_entity(
        "protein",
        "prot-1",
        name="10A06",
        metadata={
            "glycines_effectors_dna": "10A06|AF502391.1#tn8jg3150.t1",
            "glycines_effectors_prot": "10A06|AF5023911#tn8jg3150t1",
        },
    )
    db.upsert_entity("protein", "prot-2", name="Unknown_X")
    db.upsert_entity("tag", "effectors", name="Effectors")
    db.upsert_entity("tag", "effector-evidence", name="Effector Evidence")
    db.upsert_entity("tag", "tag:scn-dna-effector-hit", name="SCN DNA Effector Hit")
    db.upsert_entity("tag", "tag:scn-protein-effector-hit", name="SCN Protein Effector Hit")
    db.add_relationship("organism:heterodera-glycines", "HAS_CHROMOSOME", "chromosome:heterodera-glycines:chr1")
    db.add_relationship("effector-evidence", "BROADER", "effectors")
    db.add_relationship("tag:scn-dna-effector-hit", "BROADER", "effector-evidence")
    db.add_relationship("tag:scn-protein-effector-hit", "BROADER", "effector-evidence")
    db.add_relationship("prot-1", "TAGGED", "tag:scn-dna-effector-hit")
    db.add_relationship("prot-1", "TAGGED", "tag:scn-protein-effector-hit")
    db.close()

    db = KnowledgeGraphDB(str(db_path))
    chat = ChatToSQL(db, _FakeLLM(), module=GenomicsChatModule())
    synthesized = chat.module.synthesize_query(
        chat,
        "select all proteins identified as known effectors in H. glycines",
        "SELECT 1",
        ["protein"],
    )
    assert synthesized is not None
    sql = synthesized["sql"] if isinstance(synthesized, dict) else synthesized
    rows = db.execute_read(sql)
    db.close()

    assert "JOIN relationships etg" in sql
    assert "TAGGED" in sql
    assert "tag:scn-dna-effector-hit" in sql
    assert "tag:scn-protein-effector-hit" in sql
    assert rows
    assert rows[0]["id"] == "prot-1"
    assert rows[0]["scn_known_n"] == "10A06|AF502391.1#tn8jg3150.t1"
    assert rows[0]["scn_known_p"] == "10A06|AF5023911#tn8jg3150t1"


def test_synthesizes_protein_query_for_bcn_putative_effectors(tmp_path: Path):
    db_path = tmp_path / "chat-bcn-putative-effectors.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("organism", "organism:heterodera-schachtii", name="Heterodera schachtii")
    db.upsert_entity("chromosome", "chromosome:heterodera-schachtii:chr1", name="chr1")
    db.upsert_entity(
        "protein",
        "prot-1",
        name="BCN candidate",
        metadata={
            "schachtii_effectors_putative": "Hsc_gene_10002;Hsc_gene_10003",
        },
    )
    db.upsert_entity("protein", "prot-2", name="Unknown_X")
    db.upsert_entity("tag", "effectors", name="Effectors")
    db.upsert_entity("tag", "effector-evidence", name="Effector Evidence")
    db.upsert_entity("tag", "tag:bcn-putative-effector-hit", name="BCN Putative Effector Hit")
    db.add_relationship("organism:heterodera-schachtii", "HAS_CHROMOSOME", "chromosome:heterodera-schachtii:chr1")
    db.add_relationship("effector-evidence", "BROADER", "effectors")
    db.add_relationship("tag:bcn-putative-effector-hit", "BROADER", "effector-evidence")
    db.add_relationship("prot-1", "TAGGED", "tag:bcn-putative-effector-hit")
    db.close()

    db = KnowledgeGraphDB(str(db_path))
    chat = ChatToSQL(db, _FakeLLM(), module=GenomicsChatModule())
    synthesized = chat.module.synthesize_query(
        chat,
        "select all proteins identified as putative effectors in Heterodera schachtii",
        "SELECT 1",
        ["protein"],
    )
    assert synthesized is not None
    sql = synthesized["sql"] if isinstance(synthesized, dict) else synthesized
    rows = db.execute_read(sql)
    db.close()

    assert "JOIN relationships etg" in sql
    assert "TAGGED" in sql
    assert "tag:bcn-putative-effector-hit" in sql
    assert rows
    assert rows[0]["id"] == "prot-1"
    assert rows[0]["bcn_putative"] == "Hsc_gene_10002;Hsc_gene_10003"


def test_effector_queries_keep_generic_known_broad_but_organism_scoped_specific(tmp_path: Path):
    db_path = tmp_path / "chat-known-effectors-specificity.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("organism", "organism:heterodera-glycines", name="Heterodera glycines")
    db.upsert_entity("organism", "organism:heterodera-schachtii", name="Heterodera schachtii")
    db.upsert_entity("chromosome", "chromosome:heterodera-glycines:chr1", name="chr1")
    db.upsert_entity("protein", "prot-1", name="10A06")
    db.upsert_entity("protein", "prot-2", name="10C01")
    db.upsert_entity("protein", "prot-3", name="16B09")
    db.upsert_entity("protein", "prot-4", name="BCN_ONLY")
    db.upsert_entity("tag", "effectors", name="Effectors")
    db.upsert_entity("tag", "effector-evidence", name="Effector Evidence")
    db.upsert_entity("tag", "tag:bcn-known-effector-hit", name="BCN Known Effector Hit")
    db.upsert_entity("tag", "tag:scn-dna-effector-hit", name="SCN DNA Effector Hit")
    db.upsert_entity("tag", "tag:scn-protein-effector-hit", name="SCN Protein Effector Hit")
    db.add_relationship("organism:heterodera-glycines", "HAS_CHROMOSOME", "chromosome:heterodera-glycines:chr1")
    db.add_relationship("effector-evidence", "BROADER", "effectors")
    db.add_relationship("tag:bcn-known-effector-hit", "BROADER", "effector-evidence")
    db.add_relationship("tag:scn-dna-effector-hit", "BROADER", "effector-evidence")
    db.add_relationship("tag:scn-protein-effector-hit", "BROADER", "effector-evidence")
    db.add_relationship("prot-1", "TAGGED", "tag:scn-dna-effector-hit")
    db.add_relationship("prot-1", "TAGGED", "tag:scn-protein-effector-hit")
    db.add_relationship("prot-2", "TAGGED", "tag:bcn-known-effector-hit")
    db.add_relationship("prot-2", "TAGGED", "tag:scn-dna-effector-hit")
    db.add_relationship("prot-2", "TAGGED", "tag:scn-protein-effector-hit")
    db.add_relationship("prot-3", "TAGGED", "tag:bcn-known-effector-hit")
    db.add_relationship("prot-3", "TAGGED", "tag:scn-dna-effector-hit")
    db.add_relationship("prot-3", "TAGGED", "tag:scn-protein-effector-hit")
    db.add_relationship("prot-4", "TAGGED", "tag:bcn-known-effector-hit")
    db.close()

    db = KnowledgeGraphDB(str(db_path))
    chat = ChatToSQL(db, _FakeLLM(), module=GenomicsChatModule())

    generic_sql = chat.module.synthesize_query(chat, "select all known effectors", "SELECT 1", ["protein"])
    assert generic_sql is not None
    generic_rows = db.execute_read(generic_sql)
    assert "tag:bcn-known-effector-hit" in generic_sql
    assert "tag:scn-dna-effector-hit" in generic_sql
    assert "tag:scn-protein-effector-hit" in generic_sql
    assert len([line for line in generic_sql.splitlines() if "JOIN relationships etg" in line]) == 1
    assert sorted(row["name"] for row in generic_rows) == ["10A06", "10C01", "16B09", "BCN_ONLY"]

    scn_sql = chat.module.synthesize_query(
        chat,
        "select all proteins identified as known effectors in H. glycines",
        "SELECT 1",
        ["protein"],
    )
    assert scn_sql is not None
    scn_rows = db.execute_read(scn_sql)
    assert "tag:bcn-known-effector-hit" not in scn_sql
    assert "tag:scn-dna-effector-hit" in scn_sql
    assert "tag:scn-protein-effector-hit" in scn_sql
    assert sorted(row["name"] for row in scn_rows) == ["10A06", "10C01", "16B09"]

    full_scn_sql = chat.module.synthesize_query(
        chat,
        "select all proteins identified as known effectors in Heterodera glycines",
        "SELECT 1",
        ["protein"],
    )
    assert full_scn_sql is not None
    full_scn_rows = db.execute_read(full_scn_sql)
    assert "tag:bcn-known-effector-hit" not in full_scn_sql
    assert sorted(row["name"] for row in full_scn_rows) == ["10A06", "10C01", "16B09"]

    bcn_sql = chat.module.synthesize_query(
        chat,
        "select all proteins identified as known effectors in Heterodera schachtii",
        "SELECT 1",
        ["protein"],
    )
    assert bcn_sql is not None
    bcn_rows = db.execute_read(bcn_sql)
    assert "tag:bcn-known-effector-hit" in bcn_sql
    assert "tag:scn-dna-effector-hit" not in bcn_sql
    assert "tag:scn-protein-effector-hit" not in bcn_sql
    assert sorted(row["name"] for row in bcn_rows) == ["10C01", "16B09", "BCN_ONLY"]

    db.close()


def test_effector_prompts_do_not_mix_in_homology_scope_conditions(tmp_path: Path):
    db_path = tmp_path / "chat-effector-no-scope-mix.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("organism", "organism:heterodera-glycines", name="Heterodera glycines")
    db.upsert_entity("organism", "organism:heterodera-schachtii", name="Heterodera schachtii")
    db.upsert_entity("chromosome", "chromosome:heterodera-glycines:chr1", name="chr1")
    db.upsert_entity("tag", "effectors", name="Effectors")
    db.upsert_entity("tag", "effector-evidence", name="Effector Evidence")
    db.upsert_entity("tag", "tag:bcn-known-effector-hit", name="BCN Known Effector Hit")
    db.upsert_entity("tag", "tag:scn-dna-effector-hit", name="SCN DNA Effector Hit")
    db.upsert_entity("tag", "tag:scn-protein-effector-hit", name="SCN Protein Effector Hit")
    db.upsert_entity("tag", "homology", name="Homology")
    db.upsert_entity("tag", "homology-scope", name="Homology Scope")
    db.upsert_entity("tag", "homology-scope-cyst-nematode", name="Cyst Nematode")
    db.add_relationship("organism:heterodera-glycines", "HAS_CHROMOSOME", "chromosome:heterodera-glycines:chr1")
    db.add_relationship("effector-evidence", "BROADER", "effectors")
    db.add_relationship("tag:bcn-known-effector-hit", "BROADER", "effector-evidence")
    db.add_relationship("tag:scn-dna-effector-hit", "BROADER", "effector-evidence")
    db.add_relationship("tag:scn-protein-effector-hit", "BROADER", "effector-evidence")
    db.add_relationship("homology-scope", "BROADER", "homology")
    db.add_relationship("homology-scope-cyst-nematode", "BROADER", "homology-scope")
    db.close()

    db = KnowledgeGraphDB(str(db_path))
    chat = ChatToSQL(db, _FakeLLM(), module=GenomicsChatModule())

    effector_conditions = chat.module._semantic_conditions(
        chat,
        "select all proteins identified as known effectors in BCN",
    )
    assert not any(cond["kind"] == "scope_tag" for cond in effector_conditions)

    homology_conditions = chat.module._semantic_conditions(
        chat,
        "select proteins with cyst nematode homology",
    )
    assert any(cond["kind"] == "scope_tag" for cond in homology_conditions)

    db.close()


def test_registry_drives_protein_evidence_synthesis_and_validation(tmp_path: Path):
    db_path = tmp_path / "chat-registry-contract.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("protein", "prot-1", name="Protein 1")
    db.upsert_entity("hgt_donor", "donor-1", name="Donor 1")
    db.add_relationship("prot-1", "HAS_CUSTOM_DONOR", "donor-1")
    db.close()

    module = GenomicsChatModule(
        semantic_registry={
            "schema": {},
            "relation_families": {
                "protein_evidence": [
                    {
                        "id": "custom_hgt",
                        "aliases": [" custom donor "],
                        "rel_type": "HAS_CUSTOM_DONOR",
                        "owner_type": "protein",
                        "target_types": ["hgt_donor"],
                    },
                ],
                "ortholog_member": {
                    "aliases": [],
                },
            },
            "operators": {
                "condition_handlers": {
                    "protein_evidence": "protein_evidence",
                },
                "specs": {
                    "protein_evidence": {
                        "owner_type_ref": "owner_type",
                        "steps": [
                            {
                                "kind": "relationship",
                                "alias_prefix": "ev",
                                "source_ref": "{owner_ref}",
                                "direction": "forward",
                                "rel_type_ref": "evidence_rel_type",
                                "bind": "evidence_rel",
                            },
                            {
                                "kind": "entity",
                                "alias_prefix": "t",
                                "id_ref": "{evidence_rel}.target_id",
                                "entity_types_ref": "target_types",
                                "bind": "evidence_target",
                            },
                        ],
                    },
                },
                "scope_tags": {},
            },
            "organisms": {
                "alias_overrides": {},
            },
            "paths": {
                "protein->protein": [],
            },
            "validation": {},
        },
    )

    db = KnowledgeGraphDB(str(db_path))
    chat = ChatToSQL(db, _FakeLLM(), module=module)

    sql = chat.module.synthesize_query(chat, "select proteins with custom donor", "SELECT 1", ["protein"])
    assert sql is not None
    assert "HAS_CUSTOM_DONOR" in sql

    err = chat._validate_sql_against_schema(
        """
SELECT e.id, e.name, e.type
FROM entities e
JOIN relationships ev1 ON ev1.source_id = e.id AND ev1.rel_type = 'HAS_CUSTOM_DONOR'
JOIN entities t2 ON t2.id = ev1.target_id AND t2.type = 'hgt_donor'
WHERE e.type = 'protein'
""",
        ["protein"],
        "select proteins",
    )
    db.close()

    assert err is not None
    assert "Unexpected evidence condition" in err
    assert "HAS_CUSTOM_DONOR" in err


def test_validation_error_rejects_unrequested_extra_semantic_conditions(tmp_path: Path):
    db_path = tmp_path / "chat-extra-semantics.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("gene", "gene-1", name="Gene 1")
    db.upsert_entity("transcript", "tx-1", name="Transcript 1")
    db.upsert_entity("protein", "prot-1", name="Protein 1")
    db.upsert_entity("orthogroup", "orthogroup:og0005830", name="OG0005830")
    db.upsert_entity("hgt_donor", "donor-1", name="WP_194067917")
    db.upsert_entity("comparative_hit", "hit-1", name="Q04456.1")
    db.upsert_entity("tag", "homology-scope-nematode", name="Nematode")
    db.upsert_entity("tag", "homology-scope-cyst-nematode", name="Cyst Nematode")
    db.add_relationship("gene-1", "HAS_TRANSCRIPT", "tx-1")
    db.add_relationship("tx-1", "TRANSLATED_TO", "prot-1")
    db.add_relationship("gene-1", "BELONGS_TO_ORTHOGROUP", "orthogroup:og0005830")
    db.add_relationship("prot-1", "HAS_HGT_DONOR", "donor-1", metadata={"hgt_alien_index": "0.56"})
    db.add_relationship("prot-1", "HAS_BROAD_HOMOLOGY_HIT", "hit-1")
    db.add_relationship("hit-1", "TAGGED", "homology-scope-nematode")
    db.add_relationship("hit-1", "TAGGED", "homology-scope-cyst-nematode")
    db.close()

    db = KnowledgeGraphDB(str(db_path))
    chat = ChatToSQL(db, _FakeLLM(), module=GenomicsChatModule())
    err = chat._validate_sql_against_schema(
        """
SELECT DISTINCT e.id, e.name, e.type
FROM entities e
JOIN relationships ev1 ON ev1.source_id = e.id AND ev1.rel_type = 'HAS_HGT_DONOR'
JOIN entities t2 ON t2.id = ev1.target_id AND t2.type = 'hgt_donor'
JOIN relationships p3 ON p3.target_id = e.id AND p3.rel_type = 'TRANSLATED_TO'
JOIN relationships p4 ON p4.target_id = p3.source_id AND p4.rel_type = 'HAS_TRANSCRIPT'
JOIN relationships og5 ON og5.source_id = p4.source_id AND og5.rel_type = 'BELONGS_TO_ORTHOGROUP'
JOIN entities owner6 ON owner6.id = og5.target_id AND owner6.type = 'orthogroup'
JOIN relationships sev7 ON sev7.source_id = e.id AND sev7.rel_type = 'HAS_BROAD_HOMOLOGY_HIT'
JOIN entities shit8 ON shit8.id = sev7.target_id AND shit8.type = 'comparative_hit'
JOIN relationships stg9 ON stg9.source_id = shit8.id AND stg9.rel_type = 'TAGGED'
JOIN entities stag10 ON stag10.id = stg9.target_id AND stag10.type = 'tag'
WHERE e.type = 'protein'
  AND (upper(owner6.name) = 'OG0005830' OR upper(owner6.id) = 'ORTHOGROUP:OG0005830')
  AND stag10.id = 'homology-scope-nematode'
""",
        ["protein"],
        "select protein with HGT donor in orthogroup OG0005830",
    )
    db.close()

    assert err is not None
    assert "Unexpected evidence condition" in err or "Unexpected scope filter" in err


def test_ask_returns_error_when_validation_fails_and_no_fix_succeeds(tmp_path: Path):
    db_path = tmp_path / "chat-hard-validation-stop.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("gene", "gene-1", name="Gene 1")
    db.upsert_entity("hgt_donor", "donor-1", name="WP_194067917")
    db.close()

    class _AlwaysWrongTypeLLM:
        def chat(self, messages):
            return """```sql
SELECT e.id, e.name, e.type
FROM entities e
WHERE e.type = 'gene'
```"""

    db = KnowledgeGraphDB(str(db_path))
    chat = ChatToSQL(db, _AlwaysWrongTypeLLM())
    result = chat.ask("select hgt donors")
    db.close()

    assert result.error is not None
    assert "Wrong result type" in result.error
    assert result.results == []
    assert any(step["step"] == "validation_retry_error" for step in result.debug)


def test_genomics_registry_drives_custom_ortholog_alias_and_member_rel(tmp_path: Path):
    db_path = tmp_path / "chat-custom-ortholog-alias.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("gene", "gene-1", name="Gene 1")
    db.upsert_entity("orthogroup", "orthogroup:og1", name="OG1")
    db.upsert_entity("bcn_gene", "bcn-1", name="Hsc_gene_14957.t1")
    db.add_relationship("gene-1", "BELONGS_TO_ORTHOGROUP", "orthogroup:og1")
    db.add_relationship("orthogroup:og1", "HAS_CUSTOM_MEMBER", "bcn-1")
    db.close()

    module = GenomicsChatModule(
        semantic_registry={
            "schema": {},
            "categories": {},
            "relation_families": {
                "protein_evidence": [],
                "ortholog_member": {
                    "aliases": ["partner locus", "partner loci"],
                    "bridge_rel_type": "BELONGS_TO_ORTHOGROUP",
                    "rel_type": "HAS_CUSTOM_MEMBER",
                    "owner_type": "orthogroup",
                    "target_types": ["bcn_gene"],
                },
            },
            "operators": {
                "condition_handlers": {
                    "ortholog_member": "ortholog_member",
                },
                "specs": {
                    "ortholog_member": {
                        "owner_type": "gene",
                        "steps": [
                            {
                                "kind": "relationship",
                                "alias_prefix": "ogm",
                                "source_ref": "{owner_ref}",
                                "direction": "forward",
                                "rel_type": "BELONGS_TO_ORTHOGROUP",
                                "bind": "orthogroup_rel",
                            },
                            {
                                "kind": "relationship",
                                "alias_prefix": "mem",
                                "source_ref": "{orthogroup_rel}.target_id",
                                "direction": "forward",
                                "rel_type": "HAS_CUSTOM_MEMBER",
                                "bind": "member_rel",
                            },
                        ],
                    },
                },
                "scope_tags": {},
            },
            "organisms": {
                "alias_overrides": {},
            },
            "paths": {
                "gene->gene": [],
            },
            "validation": {},
        },
    )

    db = KnowledgeGraphDB(str(db_path))
    chat = ChatToSQL(db, _FakeLLM(), module=module)

    sql = chat.module.synthesize_query(chat, "select genes with partner loci", "SELECT 1", ["gene"])
    assert sql is not None
    assert "HAS_CUSTOM_MEMBER" in sql

    err = chat._validate_sql_against_schema(
        """
SELECT DISTINCT e.id, e.name, e.type
FROM entities e
JOIN relationships ogm1 ON ogm1.source_id = e.id AND ogm1.rel_type = 'BELONGS_TO_ORTHOGROUP'
JOIN relationships mem2 ON mem2.source_id = ogm1.target_id AND mem2.rel_type = 'HAS_CUSTOM_MEMBER'
WHERE e.type = 'gene'
""",
        ["gene"],
        "select genes with partner loci",
    )
    db.close()

    assert err is None


def test_genomics_registry_drives_custom_protein_evidence_condition_discovery(tmp_path: Path):
    db_path = tmp_path / "chat-custom-protein-evidence-discovery.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("protein", "prot-1", name="Protein 1")
    db.close()

    module = GenomicsChatModule(
        semantic_registry={
            "schema": {},
            "relation_families": {
                "protein_evidence": [
                    {
                        "id": "custom_hgt",
                        "aliases": [" custom donor "],
                        "parser_kind": "alias_match",
                        "rel_type": "HAS_CUSTOM_DONOR",
                        "owner_type": "protein",
                        "target_types": ["hgt_donor"],
                    },
                ],
                "ortholog_member": {"aliases": []},
            },
            "operators": {
                "parsers": {
                    "alias_match": {"mode": "alias_match"},
                },
                "condition_handlers": {
                    "protein_evidence": "protein_evidence",
                },
                "specs": {},
                "scope_tags": {},
            },
            "organisms": {"alias_overrides": {}},
            "paths": {},
            "validation": {},
        },
    )

    db = KnowledgeGraphDB(str(db_path))
    chat = ChatToSQL(db, _FakeLLM(), module=module)
    conditions = chat.module._semantic_conditions(chat, "select proteins with custom donor")
    db.close()

    assert any(cond["kind"] == "protein_evidence" and cond["id"] == "custom_hgt" for cond in conditions)


def test_genomics_registry_drives_ortholog_condition_exclusion_patterns(tmp_path: Path):
    db_path = tmp_path / "chat-custom-ortholog-exclusion.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("gene", "gene-1", name="Gene 1")
    db.close()

    module = GenomicsChatModule(
        semantic_registry={
            "schema": {},
            "relation_families": {
                "protein_evidence": [],
                "ortholog_member": {
                    "aliases": ["focal ortholog"],
                    "parser_kind": "alias_match_excluding_terms",
                    "exclude_patterns": [r"\bcopies\b"],
                    "rel_type": "HAS_BCN_MEMBER",
                    "owner_type": "orthogroup",
                    "target_types": ["bcn_gene"],
                },
            },
            "operators": {
                "parsers": {
                    "alias_match_excluding_terms": {"mode": "alias_match_excluding_terms"},
                },
                "condition_handlers": {
                    "ortholog_member": "ortholog_member",
                },
                "specs": {},
                "scope_tags": {},
            },
            "organisms": {"alias_overrides": {}},
            "paths": {},
            "validation": {},
        },
    )

    db = KnowledgeGraphDB(str(db_path))
    chat = ChatToSQL(db, _FakeLLM(), module=module)
    included = chat.module._semantic_conditions(chat, "select genes with focal ortholog")
    excluded = chat.module._semantic_conditions(chat, "select genes with focal ortholog copies")
    db.close()

    assert any(cond["kind"] == "ortholog_member" for cond in included)
    assert not any(cond["kind"] == "ortholog_member" for cond in excluded)


def test_genomics_registry_drives_scope_tag_eligibility_cues(tmp_path: Path):
    db_path = tmp_path / "chat-custom-scope-cues.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("tag", "homology", name="Homology")
    db.upsert_entity("tag", "homology-scope", name="Homology Scope")
    db.upsert_entity("tag", "homology-scope-cyst-nematode", name="Cyst Nematode")
    db.add_relationship("homology-scope", "BROADER", "homology")
    db.add_relationship("homology-scope-cyst-nematode", "BROADER", "homology-scope")
    db.close()

    module = GenomicsChatModule(
        semantic_registry={
            "schema": {
                "groups": {
                    "homology": {"aliases": []},
                    "effectors": {"aliases": []},
                },
            },
            "relation_families": {
                "protein_evidence": [],
                "ortholog_member": {"aliases": []},
            },
            "operators": {
                "parsers": {
                    "scope_tag_alias_match": {
                        "mode": "scope_tag_alias_match",
                        "required_message_cues": [" niche cue "],
                        "required_group_cues": [],
                        "required_relation_families": [],
                        "blocked_group_cues": [],
                    },
                },
                "condition_handlers": {
                    "scope_tag": "scope_tag",
                },
                "specs": {},
                "scope_tags": {
                    "homology-scope-cyst-nematode": {
                        "evidence_id": "bcn_homology",
                        "parser_kind": "scope_tag_alias_match",
                        "owner_type": "protein",
                        "target_type": "comparative_hit",
                        "tag_rel_type": "TAGGED",
                    },
                },
            },
            "organisms": {"alias_overrides": {}},
            "paths": {},
            "validation": {},
        },
    )

    db = KnowledgeGraphDB(str(db_path))
    chat = ChatToSQL(db, _FakeLLM(), module=module)
    without_cue = chat.module._semantic_conditions(chat, "select proteins with cyst nematode")
    with_cue = chat.module._semantic_conditions(chat, "select proteins with niche cue cyst nematode")
    db.close()

    assert not any(cond["kind"] == "scope_tag" for cond in without_cue)
    assert any(cond["kind"] == "scope_tag" and cond["tag_id"] == "homology-scope-cyst-nematode" for cond in with_cue)


def test_genomics_registry_drives_effector_template_flag_matches(tmp_path: Path):
    db_path = tmp_path / "chat-custom-effector-template-flags.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("organism", "organism:heterodera-glycines", name="Heterodera glycines")
    db.upsert_entity("organism", "organism:heterodera-schachtii", name="Heterodera schachtii")
    db.upsert_entity("chromosome", "chromosome:heterodera-glycines:chr1", name="chr1")
    db.upsert_entity("tag", "effectors", name="Effectors")
    db.upsert_entity("tag", "effector-evidence", name="Effector Evidence")
    db.upsert_entity("tag", "tag:scn-dna-effector-hit", name="SCN DNA Effector Hit")
    db.add_relationship("organism:heterodera-glycines", "HAS_CHROMOSOME", "chromosome:heterodera-glycines:chr1")
    db.add_relationship("effector-evidence", "BROADER", "effectors")
    db.add_relationship("tag:scn-dna-effector-hit", "BROADER", "effector-evidence")
    db.close()

    registry = load_semantic_registry(None)
    family = registry["operators"]["dynamic_families"]["effector_evidence"]
    family["alias_templates"]["organism_scoped"]["template_flag_matches"] = {
        "known": ["dna"],
        "putative": ["putative"],
    }
    family["alias_templates"]["organism_scoped"]["organism_sets"]["primary"]["include_when_any_flags"] = ["dna"]
    family["alias_templates"]["organism_scoped"]["organism_sets"]["secondary"]["include_when_any_flags"] = []
    family["alias_templates"]["organism_scoped"]["organism_sets"]["secondary"]["exclude_when_flags"] = []

    db = KnowledgeGraphDB(str(db_path))
    chat = ChatToSQL(db, _FakeLLM(), module=GenomicsChatModule(semantic_registry=registry))
    conditions = chat.module._semantic_conditions(chat, "select proteins identified as known effectors in h. glycines")
    db.close()

    assert any(
        cond["kind"] == "tag_evidence" and "tag:scn-dna-effector-hit" in list(cond.get("tag_ids", []) or [])
        for cond in conditions
    )


def test_genomics_overlay_expression_fragment_drives_runtime_semantics(tmp_path: Path):
    db_path = tmp_path / "chat-overlay-expression.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("gene", "gene-1", name="Gene 1")
    db.upsert_entity("transcript", "tx-1", name="Transcript 1")
    db.upsert_entity("expression_measure", "expr-1", name="TPM summary")
    db.add_relationship("gene-1", "HAS_TRANSCRIPT", "tx-1")
    db.add_relationship("tx-1", "HAS_EXPRESSION_SUMMARY", "expr-1")
    db.close()

    overlay_fragment = generate_draft_registry_fragment(
        "genomics",
        {
            "template_id": "expression_measurement",
            "matched_signals": {
                "entity_types": ["expression_measure"],
                "relationship_types_any": ["HAS_EXPRESSION_SUMMARY"],
                "metadata_fields_any": ["tpm"],
            },
        },
    )
    registry = merge_semantic_registry_overlay(load_semantic_registry(None), overlay_fragment)

    llm = _StaticSQLLLM(
        """
SELECT e.id, e.name, e.type
FROM entities e
WHERE e.type = 'gene'
        """.strip()
    )
    db = KnowledgeGraphDB(str(db_path))
    chat = ChatToSQL(db, llm, module=GenomicsChatModule(semantic_registry=registry))
    result = chat.ask("select genes with expression")
    db.close()

    assert result.error is None
    assert [row["id"] for row in result.results] == ["gene-1"]
    assert "HAS_EXPRESSION_SUMMARY" in str(result.sql or "")
    assert any(
        step.get("step") == "validation_count_map_sql" and "HAS_EXPRESSION_SUMMARY" in str(step.get("sql", ""))
        for step in result.debug
    )


def test_genomics_overlay_dge_fragment_drives_runtime_semantics(tmp_path: Path):
    db_path = tmp_path / "chat-overlay-dge.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("gene", "gene-1", name="Gene 1")
    db.upsert_entity("transcript", "tx-1", name="Transcript 1")
    db.upsert_entity("contrast_definition", "contrast-1", name="SCN vs control")
    db.add_relationship("gene-1", "HAS_TRANSCRIPT", "tx-1")
    db.add_relationship("tx-1", "HAS_EXPRESSION_CONTRAST", "contrast-1")
    db.close()

    overlay_fragment = generate_draft_registry_fragment(
        "genomics",
        {
            "template_id": "dge_contrast",
            "matched_signals": {
                "entity_types": ["contrast_definition"],
                "relationship_types_any": ["HAS_EXPRESSION_CONTRAST"],
                "metadata_fields_any": ["logfc", "padj"],
            },
        },
    )
    registry = merge_semantic_registry_overlay(load_semantic_registry(None), overlay_fragment)

    llm = _StaticSQLLLM(
        """
SELECT e.id, e.name, e.type
FROM entities e
WHERE e.type = 'gene'
        """.strip()
    )
    db = KnowledgeGraphDB(str(db_path))
    chat = ChatToSQL(db, llm, module=GenomicsChatModule(semantic_registry=registry))
    result = chat.ask("select genes with differential expression")
    db.close()

    assert result.error is None
    assert [row["id"] for row in result.results] == ["gene-1"]
    assert "HAS_EXPRESSION_CONTRAST" in str(result.sql or "")
    assert any(
        step.get("step") == "validation_count_map_sql" and "HAS_EXPRESSION_CONTRAST" in str(step.get("sql", ""))
        for step in result.debug
    )


def test_people_overlay_contact_fragment_drives_runtime_semantics(tmp_path: Path):
    db_path = tmp_path / "chat-people-overlay-contact.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("person", "person-1", name="Alice Example")
    db.execute_write("INSERT INTO contact_info(entity_id, field, value) VALUES (?, ?, ?)", ("person-1", "email", "alice@example.org"))
    db.close()

    overlay_fragment = generate_draft_registry_fragment(
        "people",
        {
            "template_id": "contact_field",
            "matched_signals": {
                "field_values_any": ["email"],
            },
        },
    )
    registry = merge_semantic_registry_overlay(load_people_semantic_registry(None), overlay_fragment)

    llm = _StaticSQLLLM(
        """
SELECT e.id, e.name, e.type
FROM entities e
WHERE e.type = 'person'
        """.strip()
    )
    db = KnowledgeGraphDB(str(db_path))
    chat = ChatToSQL(db, llm, module=PeopleChatModule(semantic_registry=registry))
    result = chat.ask("select people with email alice@example.org")
    db.close()

    assert result.error is None
    assert [row["id"] for row in result.results] == ["person-1"]
    assert "contact_info" in str(result.sql or "")
    assert "alice@example.org" in str(result.sql or "")


def test_people_overlay_authorship_fragment_drives_runtime_semantics(tmp_path: Path):
    db_path = tmp_path / "chat-people-overlay-authorship.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("person", "person-1", name="Alice Example")
    db.upsert_entity("publication", "pub-1", name="Paper 1")
    db.add_relationship("person-1", "WROTE", "pub-1")
    db.close()

    overlay_fragment = generate_draft_registry_fragment(
        "people",
        {
            "template_id": "relationship_authorship",
            "matched_signals": {
                "relationship_types_any": ["WROTE"],
            },
        },
    )
    registry = merge_semantic_registry_overlay(load_people_semantic_registry(None), overlay_fragment)

    llm = _StaticSQLLLM(
        """
SELECT e.id, e.name, e.type
FROM entities e
WHERE e.type = 'person'
        """.strip()
    )
    db = KnowledgeGraphDB(str(db_path))
    chat = ChatToSQL(db, llm, module=PeopleChatModule(semantic_registry=registry))
    result = chat.ask("select people with publications")
    db.close()

    assert result.error is None
    assert [row["id"] for row in result.results] == ["person-1"]
    assert "WROTE" in str(result.sql or "")


def test_genomics_overlay_metadata_hints_reach_prompt_context(tmp_path: Path):
    db_path = tmp_path / "chat-genomics-overlay-hints.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("chromosome", "chr-1", name="Chr 1", metadata={"chromosome": "1", "start": 10, "end": 20})
    db.upsert_entity("protein", "prot-1", name="Protein 1", metadata={"protein_sequence": "MSTN", "length": 4})
    db.close()

    location_fragment = generate_draft_registry_fragment(
        "genomics",
        {
            "template_id": "genomic_location",
            "matched_signals": {
                "entity_types": ["chromosome"],
                "metadata_fields_any": ["chromosome", "start", "end"],
            },
        },
    )
    sequence_fragment = generate_draft_registry_fragment(
        "genomics",
        {
            "template_id": "sequence_feature",
            "matched_signals": {
                "entity_types": ["protein"],
                "metadata_fields_any": ["protein_sequence", "length"],
                "relationship_types_any": ["HAS_DOMAIN"],
            },
        },
    )
    registry = merge_semantic_registry_overlay(
        merge_semantic_registry_overlay(load_semantic_registry(None), location_fragment),
        sequence_fragment,
    )

    db = KnowledgeGraphDB(str(db_path))
    chat = ChatToSQL(db, _FakeLLM(), module=GenomicsChatModule(semantic_registry=registry))
    schema_context = chat._schema_context()
    db.close()

    assert "Location semantic hints" in schema_context
    assert "preferred fields: chromosome, start, end" in schema_context
    assert "Sequence semantic hints" in schema_context
    assert "preferred fields: protein_sequence, length" in schema_context


def test_genomics_overlay_location_fragment_drives_runtime_semantics(tmp_path: Path):
    db_path = tmp_path / "chat-genomics-overlay-location.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("chromosome", "chr-1", name="Chr 1", metadata={"chromosome": "1", "start": 10, "end": 20})
    db.close()

    overlay_fragment = generate_draft_registry_fragment(
        "genomics",
        {
            "template_id": "genomic_location",
            "matched_signals": {
                "entity_types": ["chromosome"],
                "metadata_fields_any": ["chromosome", "start", "end"],
                "relationship_types_any": ["HAS_CHROMOSOME"],
            },
        },
    )
    registry = merge_semantic_registry_overlay(load_semantic_registry(None), overlay_fragment)

    llm = _StaticSQLLLM(
        """
SELECT e.id, e.name, e.type
FROM entities e
WHERE e.type = 'chromosome'
        """.strip()
    )
    db = KnowledgeGraphDB(str(db_path))
    chat = ChatToSQL(db, llm, module=GenomicsChatModule(semantic_registry=registry))
    result = chat.ask("select chromosomes with chromosome 1")
    db.close()

    assert result.error is None
    assert [row["id"] for row in result.results] == ["chr-1"]
    assert "json_extract(owner.metadata, '$.chromosome') = '1'" in str(result.sql or "")
    assert result.results[0]["chromosome"] == "1"


def test_genomics_overlay_sequence_fragment_drives_runtime_semantics(tmp_path: Path):
    db_path = tmp_path / "chat-genomics-overlay-sequence.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("protein", "prot-1", name="Protein 1", metadata={"protein_sequence": "MSTN", "length": "4"})
    db.close()

    overlay_fragment = generate_draft_registry_fragment(
        "genomics",
        {
            "template_id": "sequence_feature",
            "matched_signals": {
                "entity_types": ["protein"],
                "metadata_fields_any": ["protein_sequence", "length"],
                "relationship_types_any": ["HAS_DOMAIN"],
            },
        },
    )
    registry = merge_semantic_registry_overlay(load_semantic_registry(None), overlay_fragment)

    llm = _StaticSQLLLM(
        """
SELECT e.id, e.name, e.type
FROM entities e
WHERE e.type = 'protein'
        """.strip()
    )
    db = KnowledgeGraphDB(str(db_path))
    chat = ChatToSQL(db, llm, module=GenomicsChatModule(semantic_registry=registry))
    result = chat.ask("select proteins with protein_sequence MSTN")
    db.close()

    assert result.error is None
    assert [row["id"] for row in result.results] == ["prot-1"]
    assert "json_extract(owner.metadata, '$.protein_sequence') = 'MSTN'" in str(result.sql or "")
    assert result.results[0]["protein_sequence"] == "MSTN"


def test_genomics_expression_stage_ranking_rewrites_broad_query(tmp_path: Path):
    db_path = tmp_path / "chat-genomics-expression-ranking.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("expression_measure", "expression_measure:egg", name="Egg", metadata={
        "category": "summary",
        "source_column": "avg_egg",
        "label": "Egg",
        "order_index": 0,
        "stage_order": 0,
    })
    values = [
        ("prot-1", "tx-1", 10.0),
        ("prot-2", "tx-2", 50.0),
        ("prot-3", "tx-3", 30.0),
        ("prot-4", "tx-4", 20.0),
    ]
    for protein_id, transcript_id, egg_value in values:
        db.upsert_entity("protein", protein_id, name=protein_id.upper())
        db.upsert_entity("transcript", transcript_id, name=transcript_id.upper(), metadata={"avg_egg": egg_value})
        db.add_relationship(transcript_id, "TRANSLATED_TO", protein_id)
        db.add_relationship(transcript_id, "HAS_EXPRESSION_SUMMARY", "expression_measure:egg")
    db.close()

    llm = _StaticSQLLLM(
        """
SELECT e.id, e.name, e.type
FROM entities e
WHERE e.type = 'protein'
        """.strip()
    )
    db = KnowledgeGraphDB(str(db_path))
    chat = ChatToSQL(db, llm, module=GenomicsChatModule())
    result = chat.ask("select 3 proteins that have the highest expression in Egg stage")
    db.close()

    assert result.error is None
    assert [row["id"] for row in result.results] == ["prot-2", "prot-3", "prot-4"]
    assert "expression_measure:egg" in str(result.sql or "")
    assert "json_extract(owner.metadata, '$.avg_egg')" in str(result.sql or "")
    assert "ORDER BY" in str(result.sql or "")
    assert "DESC" in str(result.sql or "")
    assert "LIMIT 3" in str(result.sql or "")
    assert [row["expression_condition"] for row in result.results] == ["Egg", "Egg", "Egg"]
    assert [row["expression_value"] for row in result.results] == [50.0, 30.0, 20.0]
    assert any(
        step.get("step") == "validation_count_map_sql"
        and isinstance(step.get("semantic_trace"), dict)
        and step["semantic_trace"].get("kind") == "expression_ranking"
        for step in result.debug
    )


def test_genomics_expression_condition_ranking_is_not_stage_specific(tmp_path: Path):
    db_path = tmp_path / "chat-genomics-expression-condition.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("expression_measure", "expression_measure:heat-stress", name="Heat stress", metadata={
        "category": "summary",
        "source_column": "avg_heat_stress",
        "label": "Heat stress",
        "order_index": 0,
    })
    values = [
        ("gene-1", "tx-1", 5.0),
        ("gene-2", "tx-2", 15.0),
        ("gene-3", "tx-3", 9.0),
    ]
    for gene_id, transcript_id, cond_value in values:
        db.upsert_entity("gene", gene_id, name=gene_id.upper())
        db.upsert_entity("transcript", transcript_id, name=transcript_id.upper(), metadata={"avg_heat_stress": cond_value})
        db.add_relationship(gene_id, "HAS_TRANSCRIPT", transcript_id)
        db.add_relationship(transcript_id, "HAS_EXPRESSION_SUMMARY", "expression_measure:heat-stress")
    db.close()

    llm = _StaticSQLLLM(
        """
SELECT e.id, e.name, e.type
FROM entities e
WHERE e.type = 'gene'
        """.strip()
    )
    db = KnowledgeGraphDB(str(db_path))
    chat = ChatToSQL(db, llm, module=GenomicsChatModule())
    result = chat.ask("select top 2 genes with highest expression under Heat stress condition")
    db.close()

    assert result.error is None
    assert [row["id"] for row in result.results] == ["gene-2", "gene-3"]
    assert "expression_measure:heat-stress" in str(result.sql or "")
    assert "json_extract(owner.metadata, '$.avg_heat_stress')" in str(result.sql or "")
    assert "LIMIT 2" in str(result.sql or "")
    assert [row["expression_condition"] for row in result.results] == ["Heat stress", "Heat stress"]
    assert [row["expression_value"] for row in result.results] == [15.0, 9.0]


def test_ask_synthesizes_gene_query_for_hgt_and_ortholog_gene(tmp_path: Path):
    db_path = tmp_path / "chat-hgt-ortholog.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("gene", "gene-1", name="Gene 1")
    db.upsert_entity("transcript", "tx-1", name="Transcript 1")
    db.upsert_entity("protein", "prot-1", name="Protein 1")
    db.upsert_entity("orthogroup", "orthogroup:og1", name="OG1")
    db.upsert_entity("bcn_gene", "bcn-1", name="Hsc_gene_14957.t1")
    db.upsert_entity("hgt_donor", "donor-1", name="WP_194067917")
    db.add_relationship("gene-1", "HAS_TRANSCRIPT", "tx-1")
    db.add_relationship("tx-1", "TRANSLATED_TO", "prot-1")
    db.add_relationship("gene-1", "BELONGS_TO_ORTHOGROUP", "orthogroup:og1")
    db.add_relationship("orthogroup:og1", "HAS_BCN_MEMBER", "bcn-1")
    db.add_relationship("prot-1", "HAS_HGT_DONOR", "donor-1", metadata={"hgt_alien_index": "0.56"})
    db.close()

    class _HgtOrthologLLM:
        def chat(self, messages):
            return """```sql
SELECT e.id, e.name, e.type
FROM entities e
JOIN relationships r ON e.id = r.source_id
WHERE r.rel_type = 'HAS_HGT_DONOR'
AND e.type = 'gene'
```"""

    db = KnowledgeGraphDB(str(db_path))
    chat = ChatToSQL(db, _HgtOrthologLLM(), module=GenomicsChatModule())
    result = chat.ask("select genes with HGT donor and ortholog gene")
    db.close()

    assert result.results
    assert result.results[0]["id"] == "gene-1"
    assert "HAS_HGT_DONOR" in (result.sql or "")
    assert "HAS_BCN_MEMBER" in (result.sql or "")


def test_semantic_query_for_bcn_homology_and_bcn_orthologs(tmp_path: Path):
    db_path = tmp_path / "chat-bcn-combo.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("gene", "gene-1", name="Gene 1")
    db.upsert_entity("gene", "gene-2", name="Gene 2")
    db.upsert_entity("transcript", "tx-1", name="Transcript 1")
    db.upsert_entity("transcript", "tx-2", name="Transcript 2")
    db.upsert_entity("protein", "prot-1", name="Protein 1")
    db.upsert_entity("protein", "prot-2", name="Protein 2")
    db.upsert_entity("orthogroup", "orthogroup:og1", name="OG1")
    db.upsert_entity("orthogroup", "orthogroup:og2", name="OG2")
    db.upsert_entity("bcn_gene", "bcn-1", name="Hsc_gene_14957.t1")
    db.upsert_entity("comparative_hit", "hit-1", name="Hsc_gene_14957.t1")
    db.add_relationship("gene-1", "HAS_TRANSCRIPT", "tx-1")
    db.add_relationship("tx-1", "TRANSLATED_TO", "prot-1")
    db.add_relationship("gene-1", "BELONGS_TO_ORTHOGROUP", "orthogroup:og1")
    db.add_relationship("orthogroup:og1", "HAS_BCN_MEMBER", "bcn-1")
    db.add_relationship("prot-1", "HAS_BCN_HIT", "hit-1")
    db.add_relationship("gene-2", "HAS_TRANSCRIPT", "tx-2")
    db.add_relationship("tx-2", "TRANSLATED_TO", "prot-2")
    db.add_relationship("gene-2", "BELONGS_TO_ORTHOGROUP", "orthogroup:og2")
    db.close()

    db = KnowledgeGraphDB(str(db_path))
    chat = ChatToSQL(db, _FakeLLM(), module=GenomicsChatModule())
    sql = chat.module.synthesize_query(chat, "select genes with cyst nematode homology and BCN orthologs", "", ["gene"])
    rows = db.execute_read(sql)
    db.close()

    assert sql is not None
    assert "HAS_BCN_HIT" in sql
    assert "HAS_BCN_MEMBER" in sql
    assert "HAS_NEMATODE_HIT" not in sql
    assert "homology-scope-nematode" not in sql
    assert rows
    assert rows[0]["id"] == "gene-1"


def test_bcn_homology_and_bcn_orthologs_applies_cyst_scope_on_comparative_hits(tmp_path: Path):
    db_path = tmp_path / "chat-bcn-combo-comparative-scope.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("gene", "gene-1", name="Gene 1")
    db.upsert_entity("transcript", "tx-1", name="Transcript 1")
    db.upsert_entity("protein", "prot-1", name="Protein 1")
    db.upsert_entity("orthogroup", "orthogroup:og1", name="OG1")
    db.upsert_entity("bcn_gene", "bcn-1", name="Hsc_gene_14957.t1")
    db.upsert_entity("comparative_hit", "hit-1", name="Hsc_gene_14957.t1")
    db.upsert_entity("tag", "homology", name="Homology")
    db.upsert_entity("tag", "homology-scope", name="Homology Scope")
    db.upsert_entity("tag", "homology-scope-cyst-nematode", name="Cyst Nematode")
    db.add_relationship("gene-1", "HAS_TRANSCRIPT", "tx-1")
    db.add_relationship("tx-1", "TRANSLATED_TO", "prot-1")
    db.add_relationship("gene-1", "BELONGS_TO_ORTHOGROUP", "orthogroup:og1")
    db.add_relationship("orthogroup:og1", "HAS_BCN_MEMBER", "bcn-1")
    db.add_relationship("prot-1", "HAS_BCN_HIT", "hit-1")
    db.add_relationship("homology-scope", "BROADER", "homology")
    db.add_relationship("homology-scope-cyst-nematode", "BROADER", "homology-scope")
    db.add_relationship("hit-1", "TAGGED", "homology-scope-cyst-nematode")
    db.close()

    db = KnowledgeGraphDB(str(db_path))
    chat = ChatToSQL(db, _FakeLLM(), module=GenomicsChatModule())
    sql = chat.module.synthesize_query(chat, "select genes with cyst nematode homology and BCN orthologs", "", ["gene"])
    rows = db.execute_read(sql)
    db.close()

    assert sql is not None
    assert "HAS_BCN_HIT" in sql
    assert "HAS_BCN_MEMBER" in sql
    assert "shit6.type = 'comparative_hit'" in sql or "t4.type = 'comparative_hit'" in sql
    assert "homology-scope-cyst-nematode" in sql
    assert rows
    assert rows[0]["id"] == "gene-1"


def test_bcn_homology_and_bcn_orthologs_returns_zero_when_only_cyst_hit_has_no_orthogroup_member(tmp_path: Path):
    db_path = tmp_path / "chat-bcn-combo-singleton-hit.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("gene", "gene-1", name="Gene 1")
    db.upsert_entity("gene", "gene-2", name="Gene 2")
    db.upsert_entity("transcript", "tx-1", name="Transcript 1")
    db.upsert_entity("transcript", "tx-2", name="Transcript 2")
    db.upsert_entity("protein", "prot-1", name="Protein 1")
    db.upsert_entity("protein", "prot-2", name="Protein 2")
    db.upsert_entity("comparative_hit", "comparative_hit:cyst_nematode:hsc-gene-4672-t1", name="Hsc_gene_4672.t1")
    db.upsert_entity("orthogroup", "orthogroup:og2", name="OG2")
    db.upsert_entity("bcn_gene", "bcn-1", name="Hsc_gene_14957.t1")
    db.upsert_entity("tag", "homology", name="Homology")
    db.upsert_entity("tag", "homology-scope", name="Homology Scope")
    db.upsert_entity("tag", "homology-scope-cyst-nematode", name="Cyst Nematode")
    db.add_relationship("gene-1", "HAS_TRANSCRIPT", "tx-1")
    db.add_relationship("tx-1", "TRANSLATED_TO", "prot-1")
    db.add_relationship("prot-1", "HAS_BCN_HIT", "comparative_hit:cyst_nematode:hsc-gene-4672-t1")
    db.add_relationship("comparative_hit:cyst_nematode:hsc-gene-4672-t1", "TAGGED", "homology-scope-cyst-nematode")
    db.add_relationship("gene-2", "HAS_TRANSCRIPT", "tx-2")
    db.add_relationship("tx-2", "TRANSLATED_TO", "prot-2")
    db.add_relationship("gene-2", "BELONGS_TO_ORTHOGROUP", "orthogroup:og2")
    db.add_relationship("orthogroup:og2", "HAS_BCN_MEMBER", "bcn-1")
    db.add_relationship("homology-scope", "BROADER", "homology")
    db.add_relationship("homology-scope-cyst-nematode", "BROADER", "homology-scope")
    db.close()

    db = KnowledgeGraphDB(str(db_path))
    chat = ChatToSQL(db, _FakeLLM(), module=GenomicsChatModule())
    sql = chat.module.synthesize_query(chat, "select genes with cyst nematode homology and BCN orthologs", "", ["gene"])
    rows = db.execute_read(sql)
    db.close()

    assert sql is not None
    assert "HAS_BCN_HIT" in sql
    assert "HAS_BCN_MEMBER" in sql
    assert "homology-scope-cyst-nematode" in sql
    assert rows == []


def test_broad_homology_and_bcn_orthologs_does_not_add_cyst_scope_filter(tmp_path: Path):
    db_path = tmp_path / "chat-broad-bcn-orthologs.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("gene", "gene-1", name="Gene 1")
    db.upsert_entity("transcript", "tx-1", name="Transcript 1")
    db.upsert_entity("protein", "prot-1", name="Protein 1")
    db.upsert_entity("orthogroup", "orthogroup:og1", name="OG1")
    db.upsert_entity("bcn_gene", "bcn-1", name="Hsc_gene_14957.t1")
    db.upsert_entity("comparative_hit", "hit-1", name="Broad parasitism hit")
    db.upsert_entity("tag", "homology", name="Homology")
    db.upsert_entity("tag", "homology-scope", name="Homology Scope")
    db.upsert_entity("tag", "homology-scope-cyst-nematode", name="Cyst Nematode")
    db.add_relationship("gene-1", "HAS_TRANSCRIPT", "tx-1")
    db.add_relationship("tx-1", "TRANSLATED_TO", "prot-1")
    db.add_relationship("gene-1", "BELONGS_TO_ORTHOGROUP", "orthogroup:og1")
    db.add_relationship("orthogroup:og1", "HAS_BCN_MEMBER", "bcn-1")
    db.add_relationship("prot-1", "HAS_BROAD_HOMOLOGY_HIT", "hit-1")
    db.add_relationship("homology-scope", "BROADER", "homology")
    db.add_relationship("homology-scope-cyst-nematode", "BROADER", "homology-scope")
    db.close()

    db = KnowledgeGraphDB(str(db_path))
    chat = ChatToSQL(db, _FakeLLM(), module=GenomicsChatModule())
    sql = chat.module.synthesize_query(chat, "select genes with broad homology and BCN orthologs", "", ["gene"])
    rows = db.execute_read(sql)
    db.close()

    assert sql is not None
    assert "HAS_BROAD_HOMOLOGY_HIT" in sql
    assert "HAS_BCN_MEMBER" in sql
    assert "homology-scope-cyst-nematode" not in sql
    assert rows
    assert rows[0]["id"] == "gene-1"
