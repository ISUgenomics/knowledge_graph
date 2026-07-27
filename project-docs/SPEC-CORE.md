# Knowledge Graph Explorer -- Core Specification (Platform-Agnostic)

Version: 0.1 | Date: 2026-05-31

## 1. Vision

A local-first, LLM-curated knowledge graph explorer where:
- Raw inputs (websites, files, folders) are extracted into structured entities by local LLMs
- A SQLite database is the single source of truth
- All views (graph, detail panels, markdown) are rendered on demand from the DB
- The LLM handles both ingestion (skill execution) and interactive querying (chat-to-SQL)
- No cloud dependency -- Ollama + qwen3-coder:30b runs everything locally

## 2. Existing System (What's Already Built)

### 2.1 Skill Suite (Python + LangGraph + Ollama)

Four LangGraph plugins sharing a common harness:

| Skill | Entry point | Entity types produced |
|---|---|---|
| person-research | `skills/person_research/run.py` | person, publication, tag |
| signal-capture | `skills/signal_capture/run_signal.py` | signal, person (stub), tag |
| event-research | `skills/event_research/run_event.py` | event, person (stub), tag |
| center-research | `skills/center_research/run_center.py` | center, person (stub), tag |

Architecture per skill:
```
gather tool (API/file/URL) --> LLM reasoning --> build_and_save tool --> verify --> deliver
```

- Harness: `harness/skill_harness.py` -- builds LangGraph state machines
- LLM: Ollama `qwen3-coder:30b` via `ChatOpenAI(base_url="http://localhost:11434/v1")`
- Strategies: react, act, planreact (configurable per skill)
- All skills sync to vault.db in their `build_and_save_*` tools (best-effort)

### 2.2 SQLite Database (`vault_db.py`)

Location: `skills/vault/vault.db`

Schema:
```sql
entities (id TEXT PK, type TEXT, name TEXT, metadata JSON, created_at, updated_at)
aliases  (alias TEXT PK, entity_id TEXT FK)
relationships (source_id TEXT, rel_type TEXT, target_id TEXT, metadata JSON, PK(source,rel,target))
```

Entity types: `person`, `publication`, `signal`, `event`, `center`, `tag`
Relationship types: `AUTHORED`, `ATTENDED`, `MENTIONED_IN`, `TAGGED`, `COAUTHOR`, `MEMBER_OF`

Existing query methods:
- `upsert_entity()`, `resolve()`, `ensure_entity()`, `get_entity()`, `get_entities()`
- `add_relationship()`, `get_relationships()`
- `hub_nodes()`, `neighbors()`, `shared_connections()`, `degree()`, `stats()`

### 2.3 Markdown Rendering (`render_vault.py`)

Generates read-only markdown from vault.db. Renderers for: person, publication, signal, event, tag-registry. Skips unprofiled person stubs.

### 2.4 Neo4j Export (`export_neo4j.py`)

Generates CSV files + Cypher load script from the vault markdown. Currently reads markdown (not vault.db directly) -- should be updated to read from DB.

### 2.5 Shared Infrastructure

- `tag_resolver.py` -- fuzzy-matches tags against registry, prevents synonyms
- `extract_text.py`, `inventory_folder.py`, `extract_names.py` -- input processing
- `fetch_with_fallback.py` -- HTTP with bot-wall detection

## 3. Explorer Application Requirements

### 3.1 Graph Visualization

**Must have:**
- 3D force-directed graph rendering of all entities and relationships from vault.db
- Nodes colored by entity type (auto-detected from `SELECT DISTINCT type FROM entities`)
- Edges drawn by relationship type
- Click node to select, show detail panel
- Right-click context menu on nodes:
  - "Research this person" --> spawn `run.py` subprocess
  - "Hide this node" --> remove from current view (not from DB)
  - "Expand neighbors" --> load and show connected nodes
  - "Show detail" --> open detail panel
- Right-click context menu on edges:
  - "Hide this relationship type" --> filter toggle
- Camera controls: zoom, pan, rotate (3D)

**Should have:**
- Layout presets:
  - Force-directed (default)
  - Hierarchical by entity type (signals top, people middle, events bottom -- configurable)
  - Cluster by tag co-occurrence
  - Cluster by text embedding (UMAP/t-SNE)
- Hide/show highly-connected nodes temporarily
- Node size proportional to degree
- Highlight nodes matching a chat query result
- Animated edge appearance when DB changes

**Nice to have:**
- Multiple saved views/layouts
- Time-based animation (show graph evolution by date fields)
- VR/AR mode via WebXR or RealityKit

### 3.2 Dynamic Sidebar

**Must have:**
- Auto-populated from DB schema, not hardcoded entity types:
  ```
  On DB load:
    SELECT DISTINCT type FROM entities --> sidebar sections
    SELECT DISTINCT rel_type FROM relationships --> edge filter toggles
  ```
- Each section shows: entity type name + count
- Click section to expand list of entity names
- Click name to select node in graph + show detail
- Search/filter within each section

**Should have:**
- Drag entity from sidebar onto graph to pin it
- Badge showing profiled vs stub counts for persons
- Sort options: alphabetical, degree, date

### 3.3 Detail Panel (Lazy Rendering)

**Must have:**
- Rendered on demand from vault.db when a node is clicked
- Never writes to filesystem -- purely ephemeral
- Shows: name, type, all metadata fields, related entities as clickable links
- Clicking a linked entity in the detail panel navigates the graph

**Should have:**
- Markdown-formatted rendering (rendered from DB fields, not from stored .md files)
- Inline editing of metadata fields --> writes back to vault.db
- "Export as markdown" button for individual entity

**Nice to have:**
- Side-by-side comparison of two entities

### 3.4 Chat Panel (LLM-Powered)

**Must have:**
- Text input for natural language queries
- LLM translates to SQL, executes against vault.db
- Three intent categories:
  1. **Read (SELECT)** --> results displayed as table in chat panel, mentioned nodes highlighted in graph
  2. **Write (INSERT/UPDATE/DELETE)** --> LLM proposes SQL, confirmation dialog before execution, graph updates after commit
  3. **Skill dispatch** --> LLM recognizes intent ("research Jane Doe"), spawns appropriate skill subprocess, monitors completion, refreshes graph
- Safety: SELECTs run immediately, mutations always require confirmation

**Should have:**
- Chat history within session
- SQL preview toggle (show/hide the generated SQL)
- Streaming responses from Ollama
- Progress indicator for skill dispatch (subprocess output streaming)

**Nice to have:**
- Multi-turn conversation with context
- "Undo last mutation" button
- Save useful queries as named shortcuts

### 3.5 Data Layer

**Must have:**
- vault.db (SQLite) is the sole source of truth
- Graph view loads with two queries:
  ```sql
  SELECT id, type, name FROM entities
  SELECT source_id, target_id, rel_type FROM relationships
  ```
- Detail panel loads with:
  ```sql
  SELECT * FROM entities WHERE id = ?
  SELECT * FROM relationships WHERE source_id = ? OR target_id = ?
  ```
- File picker to select/create vault.db on first launch
- App knows nothing about "person" or "event" -- all entity types are dynamic from schema

**Should have:**
- Watch vault.db for changes (filesystem notification) and auto-refresh graph
- Export vault.db to Neo4j CSV + Cypher (update `export_neo4j.py` to read DB directly)
- Import from other SQLite knowledge graphs (same schema)

### 3.6 Skill Execution

**Must have:**
- Spawn Python skill scripts as subprocesses from the app
- Configurable paths:
  - Python interpreter path
  - Skills directory path
  - Ollama endpoint (default `http://localhost:11434`)
  - Model name (default `qwen3-coder:30b`)
- First-launch setup checks:
  - Ollama installed and running?
  - Model pulled?
  - Python available?
  - Skills directory valid?

**Should have:**
- Subprocess stdout/stderr streaming to a log panel
- Cancel running skill
- Queue multiple skill executions

### 3.7 LLM Integration

**Must have:**
- Chat-to-SQL via Ollama API (`http://localhost:11434/api/chat`)
- System prompt includes: DB schema, entity type list, relationship type list, example queries
- Intent classification: read query vs write mutation vs skill dispatch

**Should have:**
- Apple Intelligence (Foundation Models framework) for lightweight tasks:
  - Intent classification (is this a query, mutation, or skill dispatch?)
  - Simple SQL generation
  - Detail panel summarization
  - Route complex tasks to Ollama
- Fallback: if Apple Intelligence unavailable, Ollama handles everything

**Nice to have:**
- Configurable model selection per task type
- Token usage display

## 4. Database Schema Additions Needed

The current `vault_db.py` schema supports the explorer as-is for the core graph view. Additions for the full vision:

```sql
-- Embeddings for clustering (optional, populated on demand)
CREATE TABLE IF NOT EXISTS embeddings (
    entity_id TEXT PRIMARY KEY,
    vector    BLOB,  -- float32 array, serialized
    model     TEXT,  -- e.g. "nomic-embed-text"
    updated_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (entity_id) REFERENCES entities(id) ON DELETE CASCADE
);

-- Saved views / graph layouts (optional)
CREATE TABLE IF NOT EXISTS saved_views (
    name        TEXT PRIMARY KEY,
    config      TEXT,  -- JSON: filters, layout, camera position
    created_at  TEXT DEFAULT (datetime('now'))
);

-- Chat history (optional, per-session)
CREATE TABLE IF NOT EXISTS chat_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT,
    role        TEXT,  -- "user" or "assistant"
    content     TEXT,
    sql_query   TEXT,  -- generated SQL if applicable
    created_at  TEXT DEFAULT (datetime('now'))
);
```

## 5. Graph Data Flow

```
                         vault.db
                            |
              +-------------+-------------+
              |             |             |
         Graph View    Detail Panel    Chat Panel
              |             |             |
         2 queries      on-click       LLM->SQL
         (all nodes,    (1 entity +    (any query)
          all edges)     its edges)
              |             |             |
              +------+------+------+------+
                     |             |
              Node actions    Skill dispatch
              (hide, filter,  (subprocess)
               expand)            |
                            vault.db updates
                                  |
                            graph refresh
```

## 6. Non-Functional Requirements

- **Startup time:** Graph with 10k nodes should render in < 3 seconds
- **Click-to-detail:** < 200ms from click to detail panel populated
- **DB size:** Must handle vault.db up to 100MB (millions of rows)
- **Memory:** Graph view should not load all metadata -- just id/type/name for nodes
- **Offline:** Fully functional without internet (Ollama runs locally)
- **Data safety:** Never auto-delete from vault.db. All mutations require confirmation.
