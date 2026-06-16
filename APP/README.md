# KGX — Knowledge Graph Explorer

A local-first web app for exploring, querying, and curating a knowledge graph stored in SQLite. Built with FastAPI, vanilla JS, and a 3D force-directed graph powered by [3d-force-graph](https://github.com/vasturiano/3d-force-graph).

No cloud services, no accounts, no telemetry. Everything runs on your machine.

New to KGX data setup? Give an LLM [prompts/kgx-data-setup.md](prompts/kgx-data-setup.md) as context to help design a schema, write an import script, tune tags, and produce a matching config.

```
┌─────────────────────────────────────────────────────────────────┐
│  Browser                                                         │
│  ┌──────────┐ ┌──────────────┐ ┌────────┐ ┌────────────────┐  │
│  │ Sidebar  │ │  3D Graph    │ │ Detail │ │ SQL Panel      │  │
│  │- Entities│ │  + Settings  │ │+ Rich  │ │ (last query    │  │
│  │- Filters │ │  + Layouts   │ │  content│ │  + copy)       │  │
│  └──────────┘ └──────────────┘ └────────┘ └────────────────┘  │
│               │  Chat Panel (NL → SQL + filter/highlight)  │    │
│               └────────────────────────────────────────────┘    │
│                        │  REST + SSE                             │
│  ┌─────────────────────┴─────────────────────────────────────┐  │
│  │  FastAPI  →  SQLite (vault.db v3)  ←  Ollama (optional)   │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
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
  - [SQL Panel](#sql-panel)
  - [Context Menu](#context-menu)
  - [Force Settings](#force-settings)
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
cd /path/to/KnowledgeGraph
conda activate agentplugin
cd APP
python -m kgx
```

This starts the server using the active config and opens your browser. With `config/default.yaml`, the default URL is `http://127.0.0.1:8005`. With `config/people.yaml`, the default URL is `http://127.0.0.1:8010`.

On first run:
- if `config/default.yaml` does not exist, KGX creates it with defaults
- if the configured database does not exist but a sibling `vault.seed.db` exists, KGX copies the seed DB into place automatically
- otherwise KGX exits with an error

If you want to use a different database, see [Using a different database](#using-a-different-database).

---

## Requirements

- **Python 3.10+**
- **SQLite database** — KGX needs a writable `.db` file with the KGX schema
- **Ollama** — required for chat-to-SQL and skill-assisted features
- **Ollama model for chat/skills** — default: `qwen3-coder:30b`
- **Ollama embedding model for UMAP** — default: `nomic-embed-text`

### System tools

You also need:
- network access to `http://localhost:11434` if Ollama runs locally on the default port

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

### Option A: Use the repo-level conda environment (recommended)

```bash
cd /path/to/KnowledgeGraph
conda activate agentplugin
cd APP

# Now you can run:
kgx                    # CLI command
python -m kgx          # module entry point
```

Create the environment once from the repo root:

```bash
cd /path/to/KnowledgeGraph
conda env create -f environment.yml
conda activate agentplugin
```

Sample alternate config:

```bash
python -m kgx --config config/proteins.yaml
python -m kgx --config config/people.yaml
```

## Configuration

KGX reads `config/default.yaml` by default. Domain presets live under `config/`.

`config/default.yaml` is the generic baseline. Use a domain preset such as `config/people.yaml` when you want a focused exploration model for a specific graph shape.

```yaml
# config/default.yaml

db:
  path: ../../runtime_data/vault/vault.db   # Repo-local DB path, resolved from APP/config/default.yaml

llm:
  provider: ollama             # Only Ollama supported currently
  base_url: http://localhost:11434
  model: qwen3-coder:30b       # Default chat/skill model
  fast_model: null             # Optional secondary model if you add one
  temperature: 0               # 0 = deterministic SQL output

skills:
  enabled: true
  directory: ../../skills      # Path to LangGraph skill directories
  python: python3              # Python interpreter for skill subprocess
  model: qwen3-coder:30b       # Default model used by skills

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

The `skills.python` setting controls which Python interpreter KGX uses when launching skill subprocesses.

### Arrangement-aware dataset contract

KGX now supports a canonical visualization contract under `db_build.visualization`. Use it when designing new datasets so importers, skills, and layouts share the same assumptions about:

- which entity types should support timeline anchoring
- which metadata fields should order those timeline anchors
- which relationship classes drive hierarchical leveling
- which dataset-specific types map into reusable semantic families

The UI layout profiles can still override behavior, but `db_build.visualization` is the preferred place to declare dataset semantics that future builders should preserve.

Two CLI helpers now validate and maintain that contract against an existing DB:

```bash
kgx --config config/people.yaml --db /path/to/db.sqlite --audit-visualization
kgx --config config/people.yaml --db /path/to/db.sqlite --repair-visualization
```

- `--audit-visualization` reports missing timeline metadata, uncategorized relationship types, and unmapped hierarchical families.
- `--repair-visualization` safely backfills canonical timeline order fields from configured metadata aliases before re-running the audit.

### CLI overrides

Any config value can be overridden from the command line:

```bash
kgx --db /path/to/other.db    # Different database
kgx --port 9000               # Different port
kgx --host 0.0.0.0            # Listen on all interfaces
kgx --config /path/to/cfg     # Different config file
kgx --no-browser              # Don't auto-open browser
```

## Fresh install: step-by-step

1. **Install Conda or Miniconda.**
2. **Create the KnowledgeGraph environment from the repo root:**
   ```bash
   cd /path/to/KnowledgeGraph
   conda env create -f environment.yml
   conda activate agentplugin
   ```
3. **Install Ollama** from https://ollama.com and start it:
   ```bash
   ollama serve
   ```
4. **Pull the default model used by this app:**
   ```bash
   ollama pull qwen3-coder:30b
   ```
5. **Pull the embedding model if you want UMAP layout:**
   ```bash
   ollama pull nomic-embed-text
   ```
6. **Create or point to a database**:
   - use the repo-local default `../runtime_data/vault/vault.db`, or
   - set `db.path` in `config/default.yaml`, or
   - pass `--db /path/to/your.db` on the command line
7. **Run the app:**
   ```bash
   cd APP
   python -m kgx
   ```

If your Ollama model is different, update `llm.model` in `config/default.yaml` to match the model you pulled.

## Using a different database

KGX can run against any SQLite file that matches the KGX schema.

### Option 1: one-off override

```bash
python -m kgx --db /path/to/your/vault.db
```

### Option 2: make it the default in `config/default.yaml`

```yaml
db:
  path: ../../runtime_data/vault/vault.db
```

### Option 3: start from an empty file

```bash
touch /path/to/your/vault.db
python -m kgx --db /path/to/your/vault.db
```

KGX will create the schema on startup if the file is empty. For the repo-local default path, KGX can also bootstrap `../runtime_data/vault/vault.db` from `../sample_data/3_db/vault.seed.db` on first launch.

If you move the database later, update either `config/default.yaml` or the `--db` flag so KGX points at the new file.

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
  DB:     /path/to/your/vault.db
  URL:    http://127.0.0.1:8000
  Press Ctrl+C to stop
```

---

## Using the Interface

The UI is a five-panel layout: sidebar (left), graph (center), detail (upper-right), chat (bottom-center), and SQL panel (bottom-right).

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
| Deselect / clear highlight | Click empty space |

Mouse damping/inertia is disabled — releasing the mouse stops all motion immediately.

**Display vs Explore:**

KGX has two graph projection modes over the same database.

- **Display** — broader, more literal graph view. It keeps more of the stored structure, including mediator nodes, provenance/detail edges, and configured leaf-context nodes.
- **Explore** — curated navigation view. It removes low-signal structural noise, hides configured stub/detail layers, rewrites some transitive structure, and can synthesize simpler derived links.

These are **server-side projections**, not just UI filters. Switching modes reloads a different graph from the same DB. Edge checkboxes, SQL hide filters, highlighting, layouts, and cluster coloring only affect the already loaded projection.

**Explore mode:**

The graph loads in **explore mode** — a server-side projection that transforms the raw database into a more focused navigation view. Depending on config, that projection can:

- **Hide stub or placeholder nodes** — entities marked as incomplete can be removed from the navigation graph
- **Hide mediator/detail nodes** — intermediate nodes such as publications, records, or low-level artifacts can be excluded
- **Flatten hierarchies** — leaf-level annotations can be rolled up through configured hierarchy edges such as `BROADER`
- **Collapse transitive paths** — multi-step paths through mediator nodes can become simpler direct links
- **Derive higher-level edges** — shared mediator links can be summarized as a new relationship type, such as `COLLABORATOR`
- **Prune orphans** — nodes with no remaining edges after projection can be removed

Shared skill builders follow the same path automatically: resolved tags are now written through the shared tag registry helper, which creates known ontology parents and `BROADER` links for recognized tags instead of leaving every new tag flat.

How much this reduces the graph depends on the active preset. People-style graphs often shrink dramatically; other domains may keep more of the original structure.

**Database-agnostic design:**

Explore mode is config-driven. The backend reads the graph from the DB, then applies the configured projection rules at runtime. Typical conventions include:

| Convention | How it's used |
|---|---|
| Stub marker metadata | Distinguishes complete entities from placeholder/stub entities that can be hidden in Explore mode. |
| Hierarchy edges such as `BROADER` | Define roll-up relationships used to flatten annotation or taxonomy structure. |
| Mediator + annotation edges such as `AUTHORED` and `TAGGED` | Used to collapse multi-step paths and derive simpler higher-level links. |

The shipped people config uses these rules for person/publication/tag exploration, but the projection model is not limited to people-centric datasets. A different domain can point Explore mode at different stub types, mediator types, hierarchy edges, and derived-edge rules.

The shipped presets use this model differently:

- `config/default.yaml` — generic baseline, no domain-specific projection assumptions
- `config/people.yaml` — people/publication/tag preset with stub handling, mediator collapse, hierarchy rollup, and derived collaborator links
- `config/proteins.yaml` — protein-feature preset that derives similarity structure through configured mediator nodes

**Visual encoding:**

- **Node color** — each entity type gets a distinct color (auto-assigned), or cluster-based coloring (toggle with Clusters button)
- **Node size** — proportional to filtered degree (recomputes dynamically when edge types are toggled)
- **Link thickness** — proportional to edge weight (for example, derived edges such as `COLLABORATOR` can appear thicker when they summarize more shared mediator links)
- **Edge particles** — animated directional particles show relationship direction
- **Edge styling** — width, opacity, color, and particle count are adjustable via Settings

**Layouts** (switchable via header dropdown):

| Layout | Description |
|---|---|
| Force | Default — d3-force with adjustable parameters |
| Cluster by Type | Nodes pulled toward type-based centroids arranged in a circle |
| Timeline | Anchor-based linear layout using module defaults |
| UMAP | Semantic layout from embeddings (requires `ollama pull nomic-embed-text`) |
| Hierarchical ↓ | Top-down DAG layout |

### Sidebar

The left panel shows all entity types discovered in the database, with counts.

- **Expand a type** — click the type header to list all entities of that type
- **Select an entity** — click an entity name to focus the camera on it and load its detail panel
- **Search entities** — type in the search box at the top to filter across all types
- **Edge type filters** — checkboxes toggle relationship types on/off in the graph. All types are visible by default. Types and counts are derived from the currently loaded projection (`Display` or `Explore`), not the raw database.
- **SQL filters** — write custom SQL (`SELECT id FROM entities WHERE ...`) to hide matching nodes. Filters are saved to localStorage and can be toggled on/off. Filters can also be saved here directly from chat results.

### Detail Panel

The right panel shows full details for a selected node with type-specific rendering.

**Person entities show:**
- Type badge, name, degree
- Topics (as colored chips)
- Contact info (email, title, department, etc.)
- Research interests
- Snippets about this person (from signals that mention them, with signal name)
- Sources (provenance URLs)
- Relationships (grouped by type, with clickable entity names)

**Signal/publication entities show:**
- Topics, abstract
- Snippets (blockquote excerpts)
- Sources, relationships

**Arrow key navigation:** Press `↑`/`↓` to cycle through entities of the same type without going back to the graph.

### Chat Panel

The bottom panel provides natural language querying of the database.

**How it works:**
1. Type a question like "show all persons with > 10 edges"
2. The LLM (Ollama) translates it to SQL
3. SELECT queries execute immediately and results appear as a table
4. Mutations (INSERT/UPDATE/DELETE) show a confirmation dialog first

**Instant answers (no LLM, no waiting):**

Some questions are answered directly from the database without calling the LLM:

| Question pattern | What you get |
|---|---|
| "what types are there?" | Entity and relationship types with counts |
| "what can I order by?" | Sortable fields and metadata keys per type |
| "what topics exist?" | All topics with entity counts |
| "help" | Usage guide with examples |

**Local timeline commands (no LLM, immediate):**

| Command | Effect |
|---|---|
| `timeline` | Switch to Timeline layout using module defaults |
| `timeline reset` | Reset Timeline back to module defaults |

**Filter/highlight actions on results:**

When query results contain an `id` column, three action buttons appear:

| Button | Effect |
|---|---|
| **Highlight N** | Turns matched nodes white, dims everything else. Click background to clear. Button resets and can be clicked again. |
| **Hide N** | Applies an immediate SQL filter to hide those nodes from the graph |
| **Save filter** | Prompts for a name and saves the query as a toggleable SQL filter in the sidebar |

**Clickable result rows:** Click any row with an ID to select that entity in the detail panel and set it as the orbit center for graph rotation.

**Input history:** Press `↑`/`↓` in the chat input to browse previous queries (like a terminal).

**Example queries:**

```
show all persons with more than 20 edges
publications from 2024 ordered by degree
find signals about genomics
who has the most connections?
give me IDs of nodes with fewer than 5 edges  (→ filter buttons appear)
filter out persons not tagged with any topic   (→ filter buttons appear)
```

**Example timeline commands:**

```text
timeline
timeline reset
```

**Requirements:** Ollama must be running (`ollama serve`). The status indicator shows the model name when connected.

### SQL Panel

The bottom-right panel displays the last SQL query that was executed (whether generated by the LLM or from a filter). Click **Copy** to copy it to the clipboard.

### Context Menu

Right-click any node in the graph for these actions:

| Action | Description |
|---|---|
| Show Detail | Load the detail panel for this node |
| Focus | Pan the camera to center on this node |
| Orbit | Set this node as the orbit rotation pivot (doesn't change zoom) |
| Highlight Neighbors | Highlight all directly connected nodes in the current graph view |
| Expand Neighbors | Show all directly connected nodes from the current graph edges |
| Hide Node | Remove this node from the current view |
| Research Person | (person nodes only) Run the person_research skill |
| Copy ID | Copy the entity ID to clipboard |

**Highlight Neighbors** dims all other nodes and highlights the selected node's direct connections in the graph. Click empty space to clear the highlight.

**Expand Neighbors** finds neighbors from the current graph edges (explore-mode aware) and force-shows them even if hidden by edge type filters.

### Force Settings

Click the **Settings** button in the header to open a draggable floating panel with live-adjustable graph parameters:

**Force parameters:**

| Slider | Controls |
|---|---|
| Link Distance | How far apart connected nodes prefer to be |
| Charge Strength | Global repulsion (negative = repel) |
| Center Strength | How strongly nodes are pulled toward the center |
| Link Strength | How rigid the link constraints are |
| Collision Radius | Minimum distance between nodes (0 = off) |
| Alpha Decay | How quickly the simulation cools down |

**Per-type node charge:** Override the global charge for specific entity types (e.g., make publications repel more strongly than persons).

**Edge styling:**

| Slider | Controls |
|---|---|
| Edge Width | Line thickness |
| Edge Opacity | Transparency |
| Edge Color | Color picker |
| Particles | Number of directional particles per edge |

**Presets:** Save named presets (stored in localStorage). Click a preset name to load it. Delete with the × button. Works like saved SQL filters.

**Reset Defaults** restores all parameters. **Reheat** restarts the simulation.

### Header Controls

The header bar contains global controls:

| Control | Description |
|---|---|
| **Search** | Global search box — finds entities by name across all types |
| **Layout** | Dropdown: Force, Cluster, Timeline, UMAP, Hierarchical ↓ |
| **Labels** | Pin labels for the selected detail node or the active highlighted set |
| **Clusters** | Toggle cluster-detection coloring on/off (label propagation algorithm) |
| **Reset** | Clear hidden nodes, edge filters, SQL filters, and force-shown nodes from the current graph view |
| **Export** | Dropdown containing PNG Snapshot, JSON, and Neo4j CSV export actions |
| **Settings** | Open/close the force graph settings panel |

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
4. Configure in `config/default.yaml`:
   ```yaml
   llm:
     base_url: http://localhost:11434
     model: qwen3-coder:30b
   ```

### How it works

The LLM receives a system prompt containing:
- The full database schema (all 11 tables with columns)
- A live snapshot of entity types, relationship types, metadata keys, topics, and contact fields
- Common query patterns (degree counting, topic filtering, filter queries)
- Rules for output format and the `/no_think` suffix to suppress reasoning tokens

The chat module includes:
- **Fast-path answers** — schema questions ("what types?", "what topics?") are answered instantly from the DB without calling the LLM
- **Robust SQL parsing** — handles `\`\`\`sql`, plain `\`\`\``, bare SQL, single backticks, and missing fences
- **`<think>` block stripping** — removes qwen3's reasoning tokens from output
- **Context trimming** — only last 4 history messages sent to avoid filling the context window

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
    plugin.py          # Required: skill definition
    run.py             # Actual runner used by KGX
    manifest.yaml      # Optional: metadata
  event_research/
    plugin.py
    run_event.py
  center_research/
    plugin.py
    run_center.py
  signal_capture/
    plugin.py
    run_signal.py
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

1. Click `Skills` in the header to launch any available skill, or right-click a person node → `Research person...`
2. KGX shows the skill's configured help prompts and effective source-policy settings before launch
3. The skill runs through its real runner script (`run.py`, `run_signal.py`, etc.), not `plugin.py`
4. Output streams live to the chat panel via SSE
5. When the skill writes to `vault.db`, the graph auto-refreshes

### Running skills from the API

```bash
# List available skills
curl http://localhost:8000/api/skill/list

# Show skill help + effective config
curl http://localhost:8000/api/skill/help/person_research

# Run a skill
curl -X POST http://localhost:8000/api/skill/run \
  -H "Content-Type: application/json" \
  -d '{"skill_id": "person_research", "args": ["Jane Doe"]}'

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
| GET | `/api/graph` | All nodes and edges. Query param: `mode=explore` for projected view |
| GET | `/api/types` | Entity and relationship types with counts |
| GET | `/api/stats` | Summary statistics |

### Entities

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/entities/{type}` | List entities of a type. Query params: `search`, `limit` |
| GET | `/api/entity/{id}` | Full entity detail + relationships + neighbors + degree + rich content |
| GET | `/api/entity/{id}/neighbors` | Direct neighbors. Query param: `rel_type` |
| GET | `/api/entity/{id}/markdown` | Entity rendered as Obsidian markdown |

The `/api/entity/{id}` response includes a `rich` object with: `topics`, `snippets`, `snippets_about` (for persons), `interests`, `contact`, `sources`.

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

### Layout

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/layout/umap/status` | Embedding and position counts |
| POST | `/api/layout/umap/compute` | Generate embeddings + compute UMAP (SSE progress) |
| GET | `/api/layout/umap/positions` | Get 3D positions for all entities |

### Skills

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/skill/list` | Available skills. Query param: `entity_type` |
| GET | `/api/skill/help/{skill_id}` | Skill help prompts + effective `db_build` config |
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

### PNG export

Click **Export PNG** in the header to download a snapshot of the current graph view. The export uses the live camera position and includes visible highlight state, the selected-node marker, and pinned labels when they are enabled.

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

KGX uses a single SQLite file (`vault.db`) as its data store. Schema version 3.

### Schema

**Core tables:**

```
entities         — id, type, name, metadata (JSON), created_at, updated_at
relationships    — source_id, rel_type, target_id, metadata (JSON)
aliases          — alias → entity_id mapping
```

**Rich content tables (v3):**

```
entity_topics       — entity_id, topic (multiple per entity)
snippets            — entity_id, ref_id, ref_type, text, ordinal
research_interests  — entity_id, interest, ordinal
sources             — entity_id, source_name, url, retrieved_at
contact_info        — entity_id, field, value (email, phone, orcid, etc.)
```

**Support tables:**

```
embeddings       — entity_id → vector blob (for UMAP layout)
saved_views      — named view configurations
chat_history     — session-based chat log
```

### Creating a database from scratch

If you don't have a vault.db yet, you can create one with the API:

```bash
# Start with an empty DB (KGX creates the schema automatically)
mkdir -p ../runtime_data/vault
touch ../runtime_data/vault/vault.db
kgx --db ../runtime_data/vault/vault.db

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
cp ../runtime_data/vault/vault.db ../runtime_data/vault/vault.db.backup
```

SQLite WAL mode is enabled, so you can safely copy while the server is running — but for maximum safety, stop the server first.

---

## Running Tests

```bash
cd APP
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
Error: Database not found at /path/to/runtime_data/vault/vault.db
```

KGX needs an existing vault.db. Either:
- Point to one: `kgx --db /path/to/vault.db`
- Create one: `mkdir -p ../runtime_data/vault && touch ../runtime_data/vault/vault.db && kgx`
- Run your skills first — they create or update `runtime_data/vault/vault.db`

### Graph is empty

- Check that vault.db has data: `sqlite3 ../runtime_data/vault/vault.db "SELECT COUNT(*) FROM entities"`
- Check the API: `curl http://localhost:8000/api/stats`
- Check the browser console for errors (F12)

### Chat says "Ollama not reachable"

- Start Ollama: `ollama serve`
- Check the URL in `config/default.yaml` matches where Ollama is running
- Test directly: `curl http://localhost:11434/api/tags`
- Pull a model if none installed: `ollama pull qwen3-coder:30b`

### Chat stops responding after a few queries

The LLM context window may fill up. KGX sends only the last 4 history messages to mitigate this. If it still hangs:
- Click the clear button (↻) to reset chat history
- Refresh the page for a full reset
- Schema questions ("what types?", "help") use the fast-path and never call the LLM

### Chat shows SQL but no results

The LLM may have output SQL with broken backtick fences. KGX handles most variations (single backtick, missing opening fence, bare SQL), but if parsing fails:
- The SQL still appears in the SQL panel (bottom-right) — copy and run it manually via the sidebar SQL filter
- Try rephrasing the query

### Edge filter doesn't seem to work

- Unchecking an edge type hides those edges and any nodes connected *only* by that type
- Nodes with other visible connections remain shown
- Click **Show All** to reset all filters
- **Expand Neighbors** (right-click) overrides all filters for that node's connections

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

- The default explore mode already reduces ~10,000 raw nodes to ~300-400 meaningful nodes
- Toggle labels off (Labels button) — text sprites are the main performance cost
- Use edge filters to hide less important relationship types
- Reduce particles to 0 in Settings
- Beyond ~5,000 visible nodes, consider filtering to a subgraph via SQL filters

---

## Architecture

See [../docs/app/ARCHITECTURE.md](../docs/app/ARCHITECTURE.md) for full diagrams including:
- System overview diagram
- Event bus protocol (30+ events)
- API routes map (21 endpoints)
- Database schema (11 tables, v3)
- File tree

### Key design decisions

- **vault.db is the sole source of truth** — markdown is a generated export, not a data store
- **No CDN dependencies** — 3d-force-graph is vendored in `kgx/ui/lib/`
- **Event bus architecture** — UI components communicate only via pub/sub, never import each other
- **Schema-agnostic** — no hardcoded entity or relationship types; explore mode is driven by configured projection rules over the runtime graph
- **Local LLM only** — chat uses Ollama (localhost), no data leaves your machine
- **Mutation safety** — all DML requires explicit user confirmation via a token-based flow
- **Rich content in DB** — topics, snippets, contacts, interests, sources stored in dedicated tables (not just metadata JSON)
- **Profiled vs stubs** — person entities distinguished by `metadata.profiled` flag, rendered as separate groups with distinct colors/forces
- **Explore mode projection** — server-side, config-driven graph transformation: can hide stubs or detail nodes, roll up hierarchy structure, derive higher-level edges through mediator nodes, and prune disconnected leftovers
- **Community detection** — client-side label propagation that recomputes when edge filters change, with toggleable coloring
- **Dynamic sizing** — node sizes recompute based on filtered degree (visible edges only)
- **Filter override** — Expand Neighbors force-shows nodes regardless of active filters
- **Fast-path chat** — schema questions answered instantly from DB without LLM round-trip
