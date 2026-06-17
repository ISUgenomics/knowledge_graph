# Genomics

The `genomics` skill supports local-first database creation for structured scientific datasets. It is designed for cases where the source data already exists as local files and should be standardized, reviewed, and compiled into a KGX-compatible SQLite database without relying on online harvesting.

Canonical semantics for the module live in [GRAPH_MODEL.md](./GRAPH_MODEL.md). Treat that file as the source of truth for node categories, canonical edge rules, projection intent, and vault structure.

## Current Scope

The current base flow supports:
- raw source tables in `.tsv`, `.csv`, or `.xlsx`
- standardized source metadata in `dataset.yaml` and `schema.yaml`
- deterministic graph builds for `organism`, `dataset`, `gene`, `transcript`, `protein`, and optional linked entities such as `orthogroup`
- optional local-LLM review of inferred mappings before build
- optional rendered markdown vault output from the built genomics graph

## Commands

Run from the repo root:

```bash
/workspace/.codex/agentplugin-venv/bin/python skills/genomics/run_genomics.py <command> ...
```

Available commands:
- `normalize`: convert a known raw source package into standardized YAML metadata
- `infer`: infer `dataset.yaml` and `schema.yaml` from an arbitrary local table and optional sidecar notes
- `review`: ask a local Ollama model to review the deterministic inference and write sidecar review files
- `propose`: convert `llm-review.yaml` into a deterministic `schema.patch.yaml` and `schema.proposed.yaml`
- `apply-proposal`: apply `schema.patch.yaml` to a schema file and write a backup first
- `build`: compile the standardized source package into a SQLite graph database

## End-to-End Example

The included `genomics_scn` sample shows the expected workflow:

```bash
cd /workspace/KnowledgeGraph

/workspace/.codex/agentplugin-venv/bin/python skills/genomics/run_genomics.py infer \
  --source-file sample_data/1_source/genomics_scn/DATA.tsv \
  --source-dir sample_data/1_source/genomics_scn \
  --apply

/workspace/.codex/agentplugin-venv/bin/python skills/genomics/run_genomics.py build \
  --source-dir sample_data/1_source/genomics_scn \
  --db sample_data/3_db/genomics_scn.db \
  --vault-output sample_data/2_vault/genomics \
  --fresh
```

If the dataset needs semantic review before build:

```bash
/workspace/.codex/agentplugin-venv/bin/python skills/genomics/run_genomics.py review \
  --source-file sample_data/1_source/genomics_scn/DATA.tsv \
  --source-dir sample_data/1_source/genomics_scn \
  --config APP/config/genomics.yaml

/workspace/.codex/agentplugin-venv/bin/python skills/genomics/run_genomics.py propose \
  --review sample_data/1_source/genomics_scn/llm-review.yaml \
  --schema sample_data/1_source/genomics_scn/schema.yaml \
  --output-dir sample_data/1_source/genomics_scn

/workspace/.codex/agentplugin-venv/bin/python skills/genomics/run_genomics.py apply-proposal \
  --patch sample_data/1_source/genomics_scn/schema.patch.yaml \
  --schema sample_data/1_source/genomics_scn/schema.yaml
```

Then rebuild:

```bash
/workspace/.codex/agentplugin-venv/bin/python skills/genomics/run_genomics.py build \
  --source-dir sample_data/1_source/genomics_scn \
  --db sample_data/3_db/genomics_scn.db \
  --vault-output sample_data/2_vault/genomics \
  --fresh
```

## Output Files

The standard genomics source package can include:
- `DATA.tsv` or another local raw table
- `dataset.yaml`
- `schema.yaml`
- `inference-report.yaml`
- `llm-review.yaml`
- `schema.patch.yaml`
- `schema.proposed.yaml`

The build output is a SQLite database such as:
- `sample_data/3_db/genomics_scn.db`

The build can also render a canonical markdown vault such as:
- `sample_data/2_vault/genomics/`
