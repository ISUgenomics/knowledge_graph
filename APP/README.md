# KGX — Knowledge Graph Explorer

A local-first web app for exploring, querying, and curating a knowledge graph stored in SQLite. Built with FastAPI, vanilla JS, and a 3D force-directed graph powered by [3d-force-graph](https://github.com/vasturiano/3d-force-graph).

No cloud services, no accounts, no telemetry. Everything runs on your machine.

```
┌─────────────────────────────────────────────────────────────┐
│  Browser                                                     │
│  ┌──────────┐ ┌──────────────┐ ┌────────┐ ┌──────────────┐ │
│  │ Sidebar  │ │  3D Graph    │ │ Detail │ │  Chat Panel  │ │
│  │          │ │              │ │        │ │  (NL → SQL)  │ │
│  └──────────┘ └──────────────┘ └────────┘ └──────────────┘ │
│                        │  REST + SSE                         │
│  ┌─────────────────────┴─────────────────────────────────┐  │
│  │  FastAPI  →  SQLite (vault.db)  ←  Ollama (optional)  │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## Table of Contents

- [Quick Start](#quick-start)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Running the Server](#running-the-server)
- [Using the Interface](#using-the-interface)
  - [3D Graph](#3d-graph)
  - [Sidebar](#sidebar)
  - [Detail Panel](#detail-panel)
  - [Chat Panel](#chat-panel)
  - [Context Menu](#context-menu)
  - [Header Controls](#header-controls)
- [Chat-to-SQL (Ollama)](#chat-to-sql-ollama)
- [Skill Integration](#skill-integration)
- [API Reference](#api-reference)
- [Exporting Data](#exporting-data)
- [Database](#database)
- [Running Tests](#running-tests)
- [Troubleshooting](#troubleshooting)
- [Architecture](#architecture)

---

## Quick Start

```bash
cd APP
pip install -e .
python -m kgx
```

This starts the server at `http://127.0.0.1:8000` and opens your browser. If no `config.yaml` exists, one is created with defaults. If no `vault.db` exists, you'll get an error — see [Database](#database) to create one.

---

## Requirements

- **Python 3.10+**
- **vault.db** — a SQLite database with the KGX schema (created by the skill suite or manually)
- **Ollama** (optional) — only needed for the chat-to-SQL feature

### Python Dependencies

| Package | Purpose |
|---|---|
| `fastapi` | HTTP API server |
| `uvicorn` | ASGI server |
| `httpx` | HTTP client for Ollama API |
| `pydantic` | Config validation |
| `pyyaml` | Config file parsing |

---

## Installation

### Option A: Editable install (recommended for development)

```bash
cd APP
pip install -e .

# Now you can run:
kgx                    # CLI command
python -m kgx          # module entry point
```

### Option B: Direct dependencies

```bash
cd APP
pip install -r requirements.txt
python -m kgx
```

---

## Configuration

KGX reads `config.yaml` from the current working directory. A default is created on first run.

```yaml
# config.yaml

db:
  path: ./vault.db             # Path to SQLite database

llm:
  provider: ollama             # Only Ollama supported currently
  base_url: http://localhost:11434
  model: qwen3-coder:30b      # Any Ollama model that handles SQL
  temperature: 0               # 0 = deterministic SQL output

skills:
  enabled: true
  directory: ../skills         # Path to LangGraph skill directories
  python: python3              # Python interpreter for skill subprocess

server:
  host: 127.0.0.1              # Use 0.0.0.0 for LAN access (see warning)
  port: 8000
  cors_origins: []             # Empty = no CORS middleware

ui:
  theme: dark
  default_layout: force        # "force" or "hierarchical"
  node_size_by_degree: true    # Larger nodes = more connections
  show_labels: true            # Text labels on high-degree nodes
  max_visible_nodes: 5000
```

### CLI overrides

Any config value can be overridden from the command line:

```bash
kgx --db /path/to/other.db    # Different database
kgx --port 9000               # Different port
kgx --host 0.0.0.0            # Listen on all interfaces
kgx --config /path/to/cfg     # Different config file
kgx --no-browser              # Don't auto-open browser
```

### Security note

KGX has no authentication. When using `--host 0.0.0.0`, anyone on your network can read and write your database. Only use this on trusted networks.

---

## Running the Server

```bash
# Default: starts at http://127.0.0.1:8000, opens browser
kgx

# Headless (e.g., on a remote machine accessed via SSH tunnel)
kgx --no-browser

# Specify everything
kgx --db ~/research/vault.db --port 9000 --no-browser
```

Output:

```
Knowledge Graph Explorer
  DB:     /Users/you/research/vault.db
  URL:    http://127.0.0.1:8000
  Press Ctrl+C to stop
```

---

## Using the Interface

The UI is a four-panel layout: sidebar (left), graph (center), detail (right), and chat (bottom).

### 3D Graph

The main panel renders all entities and relationships as a 3D force-directed graph using WebGL.

**Navigation:**

| Action | Control |
|---|---|
| Rotate | Left-click + drag |
| Pan (translate) | Right-click + drag |
| Zoom | Scroll wheel |
| Select node | Left-click a node |
| Right-click menu | Right-click a node |
| Deselect | Click empty space |

**Visual encoding:**

- **Node color** — each entity type gets a distinct color (auto-assigned)
- **Node size** — proportional to degree (number of connections)
- **Text labels** — shown on high-degree nodes (degree >= 3 on large graphs)
- **Edge particles** — animated directional particles show relationship direction

### Sidebar

The left panel shows all entity types discovered in the database, with counts.

- **Expand a type** — click the type header to list all entities of that type
- **Select an entity** — click an entity name to focus the camera on it and load its detail panel
- **Search entities** — type in the search box at the top to filter across all types
- **Edge type filters** — checkboxes at the bottom toggle relationship types on/off in the graph. Unchecking a type hides those edges and any nodes connected only by that type.

### Detail Panel

The right panel shows full details for a selected node.

- **Properties** — all metadata fields displayed in a table
- **Relationships** — grouped by type, with clickable links to connected entities
- **Export markdown** — button to download the entity as an Obsidian-compatible markdown file

Click any linked entity in the detail panel to navigate to it.

### Chat Panel

The bottom panel provides natural language querying of the database.

**How it works:**
1. Type a question like "who has the most publications?"
2. The LLM (Ollama) translates it to SQL
3. SELECT queries execute immediately and results appear as a table
4. Mutations (INSERT/UPDATE/DELETE) show a confirmation dialog first
5. Multi-turn context is preserved within the session

**Example queries:**

```
How many people are in the graph?
Show me all events from 2024
Who are the coauthors of john-doe?
What metadata keys do person entities have?
List the top 10 most connected nodes
Find people tagged with "machine-learning"
```

**Requirements:** Ollama must be running (`ollama serve`). The status indicator in the chat panel shows green when connected.

### Context Menu

Right-click any node in the graph for these actions:

| Action | Description |
|---|---|
| Show Detail | Load the detail panel for this node |
| Focus | Pan the camera to center on this node |
| Expand Neighbors | Un-hide all directly connected nodes |
| Hide Node | Remove this node from the current view |
| Research Person | (person nodes only) Run the person_research skill |
| Copy ID | Copy the entity ID to clipboard |

### Header Controls

The header bar contains global controls:

| Control | Description |
|---|---|
| **Search** | Global search box — finds entities by name across all types |
| **Layout** | Dropdown to switch between Force (default) and Hierarchical |
| **Labels** | Toggle text labels on/off |
| **Show All** | Reset all hidden nodes and edge filters |
| **Export JSON** | Download the full graph as JSON |
| **Export Neo4j** | Download Neo4j-importable CSV files as a zip |

---

## Chat-to-SQL (Ollama)

The chat panel uses a local Ollama instance to translate natural language to SQL.

### Setup

1. Install Ollama: https://ollama.ai
2. Pull a model:
   ```bash
   ollama pull qwen3-coder:30b    # recommended
   # or any model good at SQL:
   ollama pull codellama:34b
   ollama pull deepseek-coder:33b
   ```
3. Start the Ollama server:
   ```bash
   ollama serve
   ```
4. Configure in `config.yaml`:
   ```yaml
   llm:
     base_url: http://localhost:11434
     model: qwen3-coder:30b
   ```

### How it works

The LLM receives a system prompt containing:
- The full database schema (tables, columns, types)
- A live snapshot of entity types, relationship types, and metadata keys from the actual database
- Rules for output format (SQL in fences, MUTATION prefix for DML)

This means the LLM knows your actual data shape — it can query metadata JSON fields with `json_extract()`, filter by real entity types, and use real relationship names.

### Mutation safety

When the LLM generates a mutation (INSERT/UPDATE/DELETE):
1. The SQL is shown in a confirmation dialog
2. An estimated row count is displayed
3. You must click "Execute" to apply it
4. Tokens expire after 5 minutes if unused

No mutation ever runs without your explicit confirmation.

---

## Skill Integration

KGX can discover and run LangGraph skills (Python plugins) that write to the same vault.db.

### Skill directory structure

```
skills/
  person_research/
    plugin.py          # Required: entry point
    manifest.yaml      # Optional: metadata
  event_research/
    plugin.py
  center_research/
    plugin.py
  signal_capture/
    plugin.py
```

### manifest.yaml format

```yaml
name: Person Research
description: Research a person and build their profile
entity_types:
  - person
args:
  - name: input
    flag: --input
    description: Entity ID to research
    required: true
```

If no manifest exists, the skill ID is derived from the directory name.

### Running skills from the UI

1. Right-click a person node → "Research person..."
2. The skill runs as a subprocess
3. Output streams live to the chat panel via SSE
4. When the skill writes to vault.db, the graph auto-refreshes

### Running skills from the API

```bash
# List available skills
curl http://localhost:8000/api/skill/list

# Run a skill
curl -X POST http://localhost:8000/api/skill/run \
  -H "Content-Type: application/json" \
  -d '{"skill_id": "person_research", "args": ["--input", "john-doe"]}'

# Stream job output (SSE)
curl http://localhost:8000/api/skill/stream/<job_id>
```

### Auto-refresh

KGX watches vault.db for filesystem changes (mtime polling every 2 seconds). When a skill writes new data, the graph and sidebar reload automatically — no manual refresh needed.

---

## API Reference

All endpoints are prefixed with `/api/`. The server also serves the UI at `/`.

### Graph

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/graph` | All nodes (id, type, name) and edges (source, target, rel_type) |
| GET | `/api/types` | Entity and relationship types with counts |
| GET | `/api/stats` | Summary statistics |

### Entities

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/entities/{type}` | List entities of a type. Query params: `search`, `limit` |
| GET | `/api/entity/{id}` | Full entity detail + relationships + neighbors + degree |
| GET | `/api/entity/{id}/neighbors` | Direct neighbors. Query param: `rel_type` |
| GET | `/api/entity/{id}/markdown` | Entity rendered as Obsidian markdown |

### Query

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/query` | Execute a read-only SELECT. Body: `{sql, params}` |
| POST | `/api/mutate/preview` | Preview a mutation, get a confirmation token |
| POST | `/api/mutate/execute` | Execute a mutation with token. Body: `{token}` |

### Chat

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/chat/status` | Ollama health check + model info |
| POST | `/api/chat` | Natural language → SQL. Body: `{message, history}` |

### Skills

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/skill/list` | Available skills. Query param: `entity_type` |
| POST | `/api/skill/run` | Start a skill job. Body: `{skill_id, args}` |
| GET | `/api/skill/job/{id}` | Job status + buffered output |
| GET | `/api/skill/stream/{id}` | SSE stream of live job output |
| GET | `/api/skill/jobs` | List all jobs |

### Export

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/export/json` | Full graph as JSON |
| GET | `/api/export/neo4j` | Neo4j CSV files as zip |
| GET | `/api/export/markdown/{id}` | Single entity as markdown |

### Watch

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/watch` | SSE stream — emits `changed` event when vault.db is modified |

---

## Exporting Data

### JSON export

Click **Export JSON** in the header or visit `/api/export/json`. Returns the full graph including all entity metadata, aliases, relationships, and statistics.

### Neo4j export

Click **Export Neo4j** in the header or visit `/api/export/neo4j`. Downloads a zip containing:
- `nodes_{type}.csv` — one file per entity type, with ID, name, and all metadata columns
- `rels_{type}.csv` — one file per relationship type, with START_ID, END_ID, TYPE

Import into Neo4j with:
```bash
neo4j-admin import \
  --nodes=Person=nodes_person.csv \
  --nodes=Publication=nodes_publication.csv \
  --relationships=AUTHORED=rels_authored.csv \
  --relationships=COAUTHOR=rels_coauthor.csv
```

### Markdown export

Click **Export .md** in the detail panel or visit `/api/export/markdown/{entity_id}`. Returns an Obsidian-compatible markdown file with YAML frontmatter, properties table, and `[[wikilink]]` relationships.

---

## Database

KGX uses a single SQLite file (`vault.db`) as its data store.

### Schema

```
entities         — id, type, name, metadata (JSON), created_at, updated_at
relationships    — source_id, rel_type, target_id, metadata (JSON)
aliases          — alias → entity_id mapping
embeddings       — entity_id → vector blob (for future clustering)
saved_views      — named view configurations (for future saved layouts)
chat_history     — session-based chat log
```

### Creating a database from scratch

If you don't have a vault.db yet, you can create one with the API:

```bash
# Start with an empty DB (KGX creates the schema automatically)
touch vault.db
kgx --db vault.db

# Then add entities via the chat panel or API:
curl -X POST http://localhost:8000/api/mutate/preview \
  -H "Content-Type: application/json" \
  -d '{"sql": "INSERT INTO entities (id, type, name) VALUES (\"alice\", \"person\", \"Alice Smith\")"}'
```

Or populate it from the skill suite — the person_research, event_research, center_research, and signal_capture skills all write to vault.db automatically.

### Metadata

The `metadata` column stores arbitrary JSON. Query it with SQLite's `json_extract()`:

```sql
-- Find people with an ORCID
SELECT name FROM entities
WHERE type = 'person'
AND json_extract(metadata, '$.orcid') IS NOT NULL;

-- Find profiled people (not stubs)
SELECT name FROM entities
WHERE type = 'person'
AND json_extract(metadata, '$.profiled') = 1;
```

### Backup

vault.db is a regular SQLite file. Copy it to back up:

```bash
cp vault.db vault.db.backup
```

SQLite WAL mode is enabled, so you can safely copy while the server is running — but for maximum safety, stop the server first.

---

## Running Tests

```bash
cd APP
pip install -e ".[dev]"
pytest
```

The test suite covers the database layer (40 tests): CRUD operations, graph queries, export, thread safety, and edge cases.

```bash
# Run with verbose output
pytest -v

# Run a specific test
pytest kgx/db/tests/test_db.py::test_upsert_entity
```

---

## Troubleshooting

### "Database not found" on startup

```
Error: Database not found at ./vault.db
```

KGX needs an existing vault.db. Either:
- Point to one: `kgx --db /path/to/vault.db`
- Create one: `touch vault.db && kgx` (empty DB, schema auto-created)
- Run your skills first — they create vault.db in the vault directory

### Graph is empty

- Check that vault.db has data: `sqlite3 vault.db "SELECT COUNT(*) FROM entities"`
- Check the API: `curl http://localhost:8000/api/stats`
- Check the browser console for errors (F12)

### Chat says "Ollama not reachable"

- Start Ollama: `ollama serve`
- Check the URL in config.yaml matches where Ollama is running
- Test directly: `curl http://localhost:11434/api/tags`
- Pull a model if none installed: `ollama pull qwen3-coder:30b`

### Edge filter doesn't seem to work

- Unchecking an edge type hides those edges and any nodes connected *only* by that type
- Nodes with other visible connections remain shown
- Click **Show All** to reset all filters

### Nodes "explode" or scatter

This should not happen in the current version. If it does, check the browser console for errors and reload the page. The graph uses visibility toggling (not data reload) for filtering, so positions should stay stable.

### Port already in use

```
ERROR: [Errno 48] Address already in use
```

Another process is using port 8000. Either:
- Kill it: `lsof -i :8000` then `kill <pid>`
- Use a different port: `kgx --port 9000`

### Large graph is slow

- Toggle labels off (Labels button) — text sprites are the main performance cost
- Use edge filters to hide less important relationship types
- The graph handles ~5,000 nodes + ~11,000 edges at interactive frame rates
- Beyond ~10,000 nodes, consider filtering to a subgraph

---

## Architecture

See [project-docs/ARCHITECTURE.md](project-docs/ARCHITECTURE.md) for full diagrams including:
- System overview diagram
- Event bus protocol
- API routes map
- Database schema
- File tree

### Key design decisions

- **vault.db is the sole source of truth** — markdown is a generated export, not a data store
- **No CDN dependencies** — 3d-force-graph is vendored in `kgx/ui/lib/`
- **Event bus architecture** — UI components communicate only via pub/sub, never import each other
- **Schema-agnostic** — no hardcoded entity or relationship types; everything is discovered from the database at runtime
- **Local LLM only** — chat uses Ollama (localhost), no data leaves your machine
- **Mutation safety** — all DML requires explicit user confirmation via a token-based flow
