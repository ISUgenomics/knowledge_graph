from pathlib import Path

from kgx.db import KnowledgeGraphDB
from kgx.llm import ChatToSQL


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
    chat = ChatToSQL(db, _FakeLLM())
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
