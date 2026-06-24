from __future__ import annotations

from pathlib import Path

from kgx.db import KnowledgeGraphDB
from kgx.llm import ChatToSQL
from kgx.llm.modules.genomics import GenomicsChatModule
from kgx.llm.prompt_corpus import flattened_prompt_corpus, prompt_corpus_few_shots


GENOMICS_SAMPLE_DB = Path("/workspace/KnowledgeGraph/sample_data/3_db/genomics_scn.db")


class _SequenceLLM:
    def __init__(self, responses: list[str]):
        self._responses = [str(item) for item in responses]
        self.calls = 0

    def chat(self, messages):
        self.calls += 1
        if not self._responses:
            sql = "SELECT 1"
        elif self.calls <= len(self._responses):
            sql = self._responses[self.calls - 1]
        else:
            sql = self._responses[-1]
        return f"```sql\n{sql}\n```"


def _load_corpus() -> list[dict]:
    return flattened_prompt_corpus()


PROMPT_CORPUS = _load_corpus()


def test_prompt_corpus_few_shots_include_general_and_module_sections():
    genomics = prompt_corpus_few_shots("genomics", general_limit=4, module_limit=8)
    sections = {entry["section"] for entry in genomics}
    ids = {entry["id"] for entry in genomics}

    assert "general" in sections
    assert "modules.genomics" in sections
    assert "people_metadata_mix" in ids
    assert "genes_with_hgt_donor" in ids


def _build_dataset(dataset: str, tmp_path: Path) -> str:
    if dataset == "genomics_sample":
        return str(GENOMICS_SAMPLE_DB)

    db_path = tmp_path / f"{dataset}.db"
    db = KnowledgeGraphDB(str(db_path))

    if dataset == "ditylenchus_gene":
        db.upsert_entity("gene", "gene-1", name="Gene 1")
        db.upsert_entity("transcript", "tx-1", name="Transcript 1")
        db.upsert_entity("protein", "prot-1", name="Protein 1")
        db.upsert_entity("comparative_hit", "hit-1", name="KAI1713285.1")
        db.add_relationship("gene-1", "HAS_TRANSCRIPT", "tx-1")
        db.add_relationship("tx-1", "TRANSLATED_TO", "prot-1")
        db.add_relationship("prot-1", "HAS_BROAD_HOMOLOGY_HIT", "hit-1")
    elif dataset == "ditylenchus_protein":
        db.upsert_entity("protein", "prot-1", name="Protein 1")
        db.upsert_entity("comparative_hit", "hit-1", name="KAI1713285.1")
        db.upsert_entity("tag", "homology-hit-organism:ditylenchus-destructor", name="Ditylenchus destructor")
        db.add_relationship("prot-1", "HAS_BROAD_HOMOLOGY_HIT", "hit-1")
        db.add_relationship("hit-1", "TAGGED", "homology-hit-organism:ditylenchus-destructor")
    elif dataset == "ortholog_count":
        db.upsert_entity("gene", "gene-1", name="Gene 1")
        db.upsert_entity("orthogroup", "orthogroup:og1", name="OG1", metadata={
            "organism": "Heterodera glycines",
            "gene_counts": {
                "Heterodera glycines": 1,
                "Heterodera schachtii": 3,
            },
        })
        db.add_relationship("gene-1", "BELONGS_TO_ORTHOGROUP", "orthogroup:og1")
    elif dataset == "hgt_gene":
        db.upsert_entity("gene", "gene-1", name="Gene 1")
        db.upsert_entity("transcript", "tx-1", name="Transcript 1")
        db.upsert_entity("protein", "prot-1", name="Protein 1")
        db.upsert_entity("hgt_donor", "donor-1", name="WP_194067917")
        db.add_relationship("gene-1", "HAS_TRANSCRIPT", "tx-1")
        db.add_relationship("tx-1", "TRANSLATED_TO", "prot-1")
        db.add_relationship("prot-1", "HAS_HGT_DONOR", "donor-1", metadata={"hgt_alien_index": "0.56"})
    elif dataset == "hgt_orthogroup":
        db.upsert_entity("gene", "gene-1", name="Gene 1")
        db.upsert_entity("transcript", "tx-1", name="Transcript 1")
        db.upsert_entity("protein", "prot-1", name="Protein 1")
        db.upsert_entity("orthogroup", "orthogroup:og0005830", name="OG0005830")
        db.upsert_entity("hgt_donor", "donor-1", name="WP_194067917")
        db.add_relationship("gene-1", "HAS_TRANSCRIPT", "tx-1")
        db.add_relationship("tx-1", "TRANSLATED_TO", "prot-1")
        db.add_relationship("gene-1", "BELONGS_TO_ORTHOGROUP", "orthogroup:og0005830")
        db.add_relationship("prot-1", "HAS_HGT_DONOR", "donor-1", metadata={"hgt_alien_index": "0.56"})
    elif dataset == "bcn_combo":
        db.upsert_entity("gene", "gene-1", name="Gene 1")
        db.upsert_entity("transcript", "tx-1", name="Transcript 1")
        db.upsert_entity("protein", "prot-1", name="Protein 1")
        db.upsert_entity("orthogroup", "orthogroup:og1", name="OG1")
        db.upsert_entity("bcn_gene", "bcn-1", name="Hsc_gene_14957.t1")
        db.upsert_entity("comparative_hit", "hit-1", name="Hsc_gene_14957.t1")
        db.add_relationship("gene-1", "HAS_TRANSCRIPT", "tx-1")
        db.add_relationship("tx-1", "TRANSLATED_TO", "prot-1")
        db.add_relationship("gene-1", "BELONGS_TO_ORTHOGROUP", "orthogroup:og1")
        db.add_relationship("orthogroup:og1", "HAS_BCN_MEMBER", "bcn-1")
        db.add_relationship("prot-1", "HAS_BCN_HIT", "hit-1")
    elif dataset == "broad_bcn_orthologs":
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
    elif dataset == "hgt_broad":
        db.upsert_entity("protein", "prot-1", name="Protein 1")
        db.upsert_entity("hgt_donor", "donor-1", name="WP_194067917")
        db.upsert_entity("comparative_hit", "hit-1", name="Q04456.1")
        db.upsert_entity("tag", "homology-scope-broad-parasitism", name="Broad Parasitism")
        db.add_relationship("prot-1", "HAS_HGT_DONOR", "donor-1", metadata={"hgt_alien_index": "0.56"})
        db.add_relationship("prot-1", "HAS_BROAD_HOMOLOGY_HIT", "hit-1")
        db.add_relationship("hit-1", "TAGGED", "homology-scope-broad-parasitism")
    elif dataset == "people_metadata":
        db.upsert_entity("person", "alice", name="Alice", metadata={"title": "PI", "department": "Biology"})
        db.upsert_entity("person", "bob", name="Bob", metadata={"title": "Staff", "department": "Chemistry"})
    elif dataset == "gene_protein_metadata":
        db.upsert_entity("gene", "gene-1", name="Gene 1")
        db.upsert_entity("transcript", "tx-1", name="Transcript 1")
        db.upsert_entity("protein", "prot-1", name="Protein 1", metadata={"pfam": "PF00001", "secretion": "secreted"})
        db.add_relationship("gene-1", "HAS_TRANSCRIPT", "tx-1")
        db.add_relationship("tx-1", "TRANSLATED_TO", "prot-1")
    else:
        db.close()
        raise ValueError(f"Unknown prompt corpus dataset: {dataset}")

    db.close()
    return str(db_path)


def _module_for(name: str):
    if name == "genomics":
        return GenomicsChatModule()
    return None


def _corpus_ids(entry: dict) -> str:
    section = str(entry.get("section", "corpus"))
    return f"{section}:{entry.get('id', 'prompt')}"


def test_prompt_corpus_entries_unique():
    ids = [_corpus_ids(entry) for entry in PROMPT_CORPUS]
    assert ids
    assert len(ids) == len(set(ids))


def test_prompt_corpus(tmp_path: Path):
    for entry in PROMPT_CORPUS:
        db_path = _build_dataset(str(entry["dataset"]), tmp_path)
        db = KnowledgeGraphDB(db_path)
        llm = _SequenceLLM(list(entry.get("responses", []) or []))
        chat = ChatToSQL(db, llm, module=_module_for(str(entry.get("module", "default"))))
        result = chat.ask(str(entry["prompt"]))

        assert result.error is None, _corpus_ids(entry)
        assert result.sql is not None, _corpus_ids(entry)

        expected_ids = [str(item) for item in list(entry.get("expect_ids", []) or [])]
        if expected_ids:
            assert [row["id"] for row in result.results] == expected_ids, _corpus_ids(entry)

        expected_names = [str(item) for item in list(entry.get("expect_names", []) or [])]
        if expected_names:
            names = [str(row["name"]) for row in result.results]
            for expected in expected_names:
                assert expected in names, _corpus_ids(entry)

        for token in list(entry.get("expect_sql_contains", []) or []):
            assert str(token) in result.sql, _corpus_ids(entry)
        for token in list(entry.get("expect_sql_not_contains", []) or []):
            assert str(token) not in result.sql, _corpus_ids(entry)

        db.close()
