from pathlib import Path

from kgx.db import KnowledgeGraphDB
from kgx.llm import ChatToSQL
from kgx.llm.modules.genomics import GenomicsChatModule


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
    assert "CAST(gc.value AS INTEGER) >= 3" in sql
    assert rows
    assert rows[0]["id"] == "gene-1"


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
    assert "CAST(gc.value AS INTEGER) >= 3" in sql
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


def test_synthesizes_protein_query_for_scn_known_effectors(tmp_path: Path):
    db_path = tmp_path / "chat-scn-effectors.db"
    db = KnowledgeGraphDB(str(db_path))
    db.upsert_entity("organism", "organism:heterodera-glycines", name="Heterodera glycines")
    db.upsert_entity("chromosome", "chromosome:heterodera-glycines:chr1", name="chr1")
    db.upsert_entity("protein", "prot-1", name="10A06")
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
    sql = chat.module.synthesize_query(
        chat,
        "select all proteins identified as known effectors in H. glycines",
        "SELECT 1",
        ["protein"],
    )
    assert sql is not None
    rows = db.execute_read(sql)
    db.close()

    assert "JOIN relationships etg" in sql
    assert "TAGGED" in sql
    assert "tag:scn-dna-effector-hit" in sql
    assert "tag:scn-protein-effector-hit" in sql
    assert rows
    assert rows[0]["id"] == "prot-1"


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
