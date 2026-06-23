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

    assert requested[0] == "hgt_donor"
    assert "gene" in requested


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
