# Knowledge Graph Explorer -- Modular Architecture & Implementation Plan

Version: 0.2 | Date: 2026-05-31 | Supersedes: SPEC-WEB.md

## 1. Design Principles

1. **Each module is a standalone package** -- runs independently, tests independently, has its own README
2. **Modules communicate through defined interfaces** -- never import internals from another module
3. **Zero knowledge of domain** -- the explorer knows "entities" and "relationships", never "person" or "event"
4. **Configuration over code** -- behavior changes come from config files, not source edits
5. **Any module is replaceable** -- swap the LLM backend, the graph renderer, or the DB layer without touching other modules

## 2. Module Map

```
kgx/                              <-- "Knowledge Graph Explorer" (top-level package)
|
+-- db/                            Module 1: Database abstraction
|   +-- __init__.py                exports: KnowledgeGraphDB
|   +-- schema.py                  schema creation + migration
|   +-- queries.py                 read queries (graph, detail, search)
|   +-- mutations.py               write operations (upsert, delete, relationships)
|   +-- export.py                  Neo4j CSV, JSON-LD, markdown export
|   +-- tests/
|
+-- llm/                           Module 2: LLM abstraction
|   +-- __init__.py                exports: LLMClient
|   +-- base.py                    abstract interface (protocol)
|   +-- ollama.py                  Ollama implementation
|   +-- openai_compat.py           any OpenAI-compatible API (LM Studio, vLLM, etc)
|   +-- chat_to_sql.py             natural language -> SQL translation
|   +-- intent.py                  intent classifier (query / mutation / skill)
|   +-- tests/
|
+-- skills/                        Module 3: Skill runner abstraction
|   +-- __init__.py                exports: SkillRegistry, SkillRunner
|   +-- registry.py                discovers skills from filesystem
|   +-- runner.py                  subprocess execution + output streaming
|   +-- tests/
|
+-- api/                           Module 4: REST/WebSocket API
|   +-- __init__.py                exports: create_app()
|   +-- app.py                     FastAPI app factory
|   +-- routes_graph.py            /api/graph, /api/types
|   +-- routes_entity.py           /api/entity/:id, /api/entities/:type
|   +-- routes_query.py            /api/query, /api/mutate
|   +-- routes_chat.py             /api/chat, /ws/chat
|   +-- routes_skill.py            /api/skill/*
|   +-- routes_export.py           /api/export/neo4j, /api/export/markdown
|   +-- middleware.py              CORS, error handling, request logging
|   +-- tests/
|
+-- ui/                            Module 5: Frontend (static files)
|   +-- index.html                 shell: layout containers only
|   +-- components/
|   |   +-- graph/
|   |   |   +-- graph.js           3d-force-graph wrapper (self-contained)
|   |   |   +-- graph.css
|   |   |   +-- layouts.js         force, hierarchical, clustered, embedding
|   |   |   +-- context-menu.js    right-click menu (generic, action-driven)
|   |   +-- sidebar/
|   |   |   +-- sidebar.js         dynamic sidebar (self-contained)
|   |   |   +-- sidebar.css
|   |   +-- detail/
|   |   |   +-- detail.js          entity detail panel (self-contained)
|   |   |   +-- detail.css
|   |   +-- chat/
|   |   |   +-- chat.js            chat panel + WebSocket (self-contained)
|   |   |   +-- chat.css
|   |   +-- shared/
|   |       +-- event-bus.js        pub/sub for inter-component communication
|   |       +-- api-client.js       fetch wrapper for all API calls
|   |       +-- theme.css           colors, fonts, spacing tokens
|   +-- lib/                        vendored dependencies (no CDN, no npm)
|   |   +-- three.min.js
|   |   +-- 3d-force-graph.min.js
|   |   +-- marked.min.js
|   +-- tests/
|
+-- config/                        Module 6: Configuration
|   +-- __init__.py                exports: load_config()
|   +-- schema.py                  config validation (pydantic)
|   +-- defaults.py                default values
|
+-- cli.py                         Entry point: `python -m kgx`
+-- config.yaml                    User config (created on first run)
+-- requirements.txt
+-- pyproject.toml
```

## 3. Module Specifications

---

### Module 1: `kgx.db` -- Database Abstraction

**Responsibility:** All SQLite access. No other module touches sqlite3 directly.

**Public interface:**

```python
class KnowledgeGraphDB:
    def __init__(self, path: str | Path): ...
    def close(self): ...

    # --- Schema discovery (no hardcoded types) ---
    def entity_types(self) -> list[dict]          # [{"type": "person", "count": 142}, ...]
    def relationship_types(self) -> list[dict]    # [{"rel_type": "AUTHORED", "count": 890}, ...]
    def metadata_keys(self, entity_type: str) -> list[str]  # ["department", "title", "email", ...]

    # --- Graph data (bulk, for visualization) ---
    def graph_nodes(self) -> list[dict]           # [{"id": ..., "type": ..., "name": ...}]
    def graph_edges(self) -> list[dict]           # [{"source": ..., "target": ..., "rel_type": ...}]

    # --- Entity CRUD ---
    def get_entity(self, id: str) -> dict | None
    def get_entities(self, type: str = "", search: str = "") -> list[dict]
    def upsert_entity(self, type: str, id: str, *, name: str, metadata: dict = None, aliases: list = None) -> str
    def delete_entity(self, id: str) -> bool
    def resolve(self, raw_id: str) -> str | None  # alias resolution

    # --- Relationship CRUD ---
    def get_relationships(self, entity_id: str, rel_type: str = "", direction: str = "both") -> list[dict]
    def add_relationship(self, source: str, rel_type: str, target: str, metadata: dict = None): ...
    def delete_relationship(self, source: str, rel_type: str, target: str): ...

    # --- Graph queries ---
    def neighbors(self, entity_id: str, rel_type: str = "") -> list[dict]
    def shared_connections(self, id1: str, id2: str) -> list[dict]
    def hub_nodes(self, min_degree: int = 5, entity_type: str = "") -> list[dict]
    def degree(self, entity_id: str) -> int
    def stats(self) -> dict

    # --- Raw SQL (for chat-to-SQL) ---
    def execute_read(self, sql: str, params: list = None) -> list[dict]   # SELECT only
    def execute_write(self, sql: str, params: list = None) -> int         # returns rows affected

    # --- Export ---
    def export_neo4j_csv(self, output_dir: Path) -> dict     # returns file paths
    def export_json(self) -> dict                              # full graph as JSON
    def export_markdown(self, entity_id: str) -> str           # single entity as markdown
```

**Key rules:**
- `execute_read()` raises if SQL is not a SELECT
- `execute_write()` raises if SQL is a SELECT (use `execute_read` instead)
- All methods return plain dicts, never sqlite3.Row objects
- `metadata` is always deserialized from JSON to dict before returning
- Schema migrations are versioned in `schema.py`

**Relationship to existing code:** This is a clean rewrite of `vault_db.py` with a broader interface. The existing `vault_db.py` continues to work for skills; `kgx.db` wraps the same schema for the explorer. Both read/write the same `vault.db` file.

---

### Module 2: `kgx.llm` -- LLM Abstraction

**Responsibility:** All LLM communication. Swappable backend.

**Public interface:**

```python
# Protocol (abstract interface)
class LLMClient(Protocol):
    async def chat(self, messages: list[dict], model: str = None) -> str: ...
    async def chat_stream(self, messages: list[dict], model: str = None) -> AsyncIterator[str]: ...
    async def is_available(self) -> bool: ...

# Intent classification result
@dataclass
class Intent:
    category: str                   # "query" | "mutation" | "skill" | "conversation"
    sql: str | None                 # generated SQL for query/mutation
    skill_name: str | None          # for skill dispatch
    skill_args: dict | None         # for skill dispatch
    confidence: float
    explanation: str                # human-readable explanation of what will happen

# Chat-to-SQL
class ChatToSQL:
    def __init__(self, llm: LLMClient, db: KnowledgeGraphDB): ...
    async def translate(self, question: str) -> Intent: ...
```

**Implementations:**

```python
class OllamaClient(LLMClient):
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "qwen3-coder:30b"): ...

class OpenAICompatClient(LLMClient):
    """Works with any OpenAI-compatible API: LM Studio, vLLM, text-generation-webui, etc."""
    def __init__(self, base_url: str, api_key: str = "EMPTY", model: str = ""): ...
```

**Key rules:**
- `ChatToSQL` auto-discovers schema from `db.entity_types()` and `db.relationship_types()` -- never hardcoded
- System prompt is a template, populated at runtime with live schema info
- Intent classification is a structured output parse, not regex
- `chat_stream` yields tokens for real-time display in the chat panel

---

### Module 3: `kgx.skills` -- Skill Runner Abstraction

**Responsibility:** Discover and execute external skill scripts. No knowledge of what skills do.

**Public interface:**

```python
@dataclass
class SkillDefinition:
    name: str                      # e.g. "person-research"
    script: str                    # path to run script
    description: str               # from skill's plugin.py docstring
    entity_types: list[str]        # what entity types this skill produces
    args: list[dict]               # expected arguments: [{"name": "name", "required": True}, ...]

class SkillRegistry:
    def __init__(self, skills_dir: str | Path): ...
    def discover(self) -> list[SkillDefinition]: ...
    def get(self, name: str) -> SkillDefinition | None: ...

@dataclass
class SkillJob:
    job_id: str
    skill_name: str
    status: str                    # "pending" | "running" | "completed" | "failed"
    output: list[str]              # stdout/stderr lines
    started_at: float
    finished_at: float | None
    exit_code: int | None

class SkillRunner:
    def __init__(self, registry: SkillRegistry, config: dict): ...
    async def run(self, skill_name: str, args: list[str]) -> str: ...   # returns job_id
    async def stream(self, job_id: str) -> AsyncIterator[str]: ...       # yield output lines
    def status(self, job_id: str) -> SkillJob: ...
    def cancel(self, job_id: str) -> bool: ...
    def list_jobs(self) -> list[SkillJob]: ...
```

**Skill discovery:** `SkillRegistry.discover()` walks the skills directory, looks for `run*.py` files, reads the plugin.py docstring and argument parser to build `SkillDefinition` objects. This means adding a new skill type requires zero code changes to the explorer.

**Key rules:**
- Skills are subprocesses, never imported
- Config provides: python path, skills dir, ollama model, ollama URL
- Output is streamed line-by-line via async iterator
- Job state is in-memory (dict of job_id -> SkillJob), not persisted

---

### Module 4: `kgx.api` -- REST/WebSocket API

**Responsibility:** HTTP interface. Thin layer connecting DB, LLM, and Skills modules.

**App factory pattern:**

```python
def create_app(config: dict) -> FastAPI:
    """Create a configured FastAPI app. Each route file registers its own router."""
    app = FastAPI(title="Knowledge Graph Explorer")
    db = KnowledgeGraphDB(config["db_path"])
    llm = create_llm_client(config["llm"])
    chat_sql = ChatToSQL(llm, db)
    registry = SkillRegistry(config["skills_dir"])
    runner = SkillRunner(registry, config)

    # Register route modules -- each gets only the dependencies it needs
    app.include_router(make_graph_router(db))        # /api/graph, /api/types
    app.include_router(make_entity_router(db))       # /api/entity/:id, /api/entities/:type
    app.include_router(make_query_router(db))        # /api/query, /api/mutate
    app.include_router(make_chat_router(chat_sql))   # /api/chat, /ws/chat
    app.include_router(make_skill_router(runner))    # /api/skill/*
    app.include_router(make_export_router(db))       # /api/export/*

    app.mount("/", StaticFiles(directory="ui", html=True))
    return app
```

**Route files are independent.** `routes_graph.py` only receives a `KnowledgeGraphDB` instance. `routes_chat.py` only receives a `ChatToSQL` instance. No route file imports another.

**API endpoints (complete list):**

```
GET    /api/graph                      -- all nodes + edges
GET    /api/types                      -- entity types + relationship types + counts
GET    /api/entity/{id}                -- single entity + relationships + neighbors
GET    /api/entities/{type}            -- list entities by type (sidebar)
GET    /api/entities/{type}/search?q=  -- search within type
POST   /api/query                      -- execute read-only SQL, body: {"sql": "..."}
POST   /api/mutate/preview             -- preview a mutation, returns {sql, affected_rows, token}
POST   /api/mutate/execute             -- execute with confirmation token
POST   /api/chat                       -- single-shot chat-to-SQL
WS     /ws/chat                        -- streaming chat
POST   /api/skill/run                  -- start a skill, body: {"skill": "...", "args": [...]}
GET    /api/skill/jobs                  -- list all jobs
GET    /api/skill/jobs/{id}             -- job status
WS     /ws/skill/{id}                  -- stream skill output
DELETE /api/skill/jobs/{id}             -- cancel a job
GET    /api/skills                      -- list available skills (from registry)
GET    /api/export/neo4j                -- download Neo4j CSV zip
GET    /api/export/json                 -- download full graph as JSON
GET    /api/export/markdown/{id}        -- single entity as markdown
POST   /api/db/watch                    -- toggle filesystem watch for vault.db changes
GET    /api/config                      -- current config (non-sensitive)
```

---

### Module 5: `kgx.ui` -- Frontend Components

**Responsibility:** Browser UI. Each component is a self-contained JS module that communicates via an event bus.

**Component isolation contract:**
- Each component lives in its own directory with its own .js and .css
- Components never import each other's functions
- All inter-component communication goes through `event-bus.js`
- All API calls go through `api-client.js`
- Components are initialized by `index.html` which wires them to the event bus

**Event Bus (`shared/event-bus.js`):**

```javascript
// Simple pub/sub -- the ONLY way components talk to each other
class EventBus {
    constructor() { this.listeners = {}; }
    on(event, callback) { ... }
    off(event, callback) { ... }
    emit(event, data) { ... }
}

// Event catalog (all events in one place):
// "graph:loaded"          -- graph finished loading, payload: {nodeCount, edgeCount}
// "node:selected"         -- user clicked a node, payload: {id, type, name}
// "node:right-clicked"    -- user right-clicked, payload: {id, type, name, x, y}
// "node:hide"             -- hide a node from view, payload: {id}
// "node:expand"           -- expand neighbors, payload: {id}
// "node:highlight"        -- highlight nodes (from chat), payload: {ids: [...]}
// "edge:filter"           -- toggle edge type visibility, payload: {rel_type, visible}
// "detail:loaded"         -- detail panel data ready, payload: {entity, relationships}
// "chat:result"           -- chat query returned results, payload: {results, sql}
// "chat:mutation"         -- chat proposed a mutation, payload: {sql, preview}
// "skill:started"         -- skill job started, payload: {job_id, skill_name}
// "skill:output"          -- skill output line, payload: {job_id, line}
// "skill:completed"       -- skill finished, payload: {job_id, exit_code}
// "db:changed"            -- database was modified, payload: {} (trigger refresh)
// "layout:change"         -- switch layout preset, payload: {layout: "force"|"hierarchical"|...}
// "sidebar:select"        -- sidebar item clicked, payload: {id, type}
```

**Component: Graph (`components/graph/graph.js`):**

```javascript
export function initGraph(container, eventBus, apiClient) {
    const Graph = ForceGraph3D()(container);

    // Load data
    async function refresh() {
        const data = await apiClient.get('/api/graph');
        Graph.graphData({
            nodes: data.nodes,
            links: data.edges.map(e => ({source: e.source, target: e.target, rel_type: e.rel_type}))
        });
        Graph.nodeColor(node => colorByType(node.type));
        eventBus.emit('graph:loaded', {nodeCount: data.nodes.length, edgeCount: data.edges.length});
    }

    // Outgoing events
    Graph.onNodeClick(node => eventBus.emit('node:selected', node));
    Graph.onNodeRightClick((node, ev) => eventBus.emit('node:right-clicked', {...node, x: ev.clientX, y: ev.clientY}));

    // Incoming events
    eventBus.on('node:hide', ({id}) => { /* filter from graphData */ });
    eventBus.on('node:highlight', ({ids}) => { /* pulse animation */ });
    eventBus.on('node:expand', async ({id}) => { /* fetch neighbors, add to graph */ });
    eventBus.on('edge:filter', ({rel_type, visible}) => { /* show/hide edges */ });
    eventBus.on('layout:change', ({layout}) => { /* switch layout engine */ });
    eventBus.on('db:changed', () => refresh());
    eventBus.on('sidebar:select', ({id}) => { /* focus camera on node */ });

    refresh();
    return { refresh, Graph };
}
```

**Component: Sidebar (`components/sidebar/sidebar.js`):**

```javascript
export function initSidebar(container, eventBus, apiClient) {
    async function refresh() {
        const types = await apiClient.get('/api/types');
        // Render sections from types.entity_types
        // Render edge filter toggles from types.relationship_types
    }

    // Click handlers emit events
    function onEntityClick(id, type) { eventBus.emit('sidebar:select', {id, type}); }
    function onFilterToggle(relType, visible) { eventBus.emit('edge:filter', {rel_type: relType, visible}); }

    // Listen for refresh
    eventBus.on('db:changed', () => refresh());

    refresh();
}
```

**Component: Detail (`components/detail/detail.js`):**

```javascript
export function initDetail(container, eventBus, apiClient) {
    eventBus.on('node:selected', async ({id}) => {
        const data = await apiClient.get(`/api/entity/${id}`);
        renderDetail(container, data);
        eventBus.emit('detail:loaded', data);
    });

    // Clicking a linked entity in detail navigates the graph
    container.addEventListener('click', (e) => {
        if (e.target.dataset.entityId) {
            eventBus.emit('node:selected', {id: e.target.dataset.entityId});
        }
    });
}
```

**Component: Chat (`components/chat/chat.js`):**

```javascript
export function initChat(container, eventBus, apiClient) {
    let ws = null;

    function connect() {
        ws = new WebSocket(`ws://${location.host}/ws/chat`);
        ws.onmessage = (e) => { /* append token to current response */ };
    }

    async function send(question) {
        // Option 1: single-shot (simpler, use first)
        const result = await apiClient.post('/api/chat', {question});
        if (result.intent === 'query') {
            renderTable(result.results);
            eventBus.emit('node:highlight', {ids: result.entity_ids});
        } else if (result.intent === 'mutation') {
            showConfirmDialog(result.sql, result.preview);
        } else if (result.intent === 'skill') {
            const job = await apiClient.post('/api/skill/run', {skill: result.skill, args: result.args});
            eventBus.emit('skill:started', job);
        }
    }

    eventBus.on('chat:mutation', async ({sql, token}) => {
        await apiClient.post('/api/mutate/execute', {sql, token});
        eventBus.emit('db:changed');
    });

    connect();
}
```

**`index.html` wiring (the only place components know about each other):**

```html
<script type="module">
    import { EventBus } from './components/shared/event-bus.js';
    import { ApiClient } from './components/shared/api-client.js';
    import { initGraph } from './components/graph/graph.js';
    import { initSidebar } from './components/sidebar/sidebar.js';
    import { initDetail } from './components/detail/detail.js';
    import { initChat } from './components/chat/chat.js';

    const bus = new EventBus();
    const api = new ApiClient();

    initGraph(document.getElementById('graph'), bus, api);
    initSidebar(document.getElementById('sidebar'), bus, api);
    initDetail(document.getElementById('detail'), bus, api);
    initChat(document.getElementById('chat'), bus, api);
</script>
```

---

### Module 6: `kgx.config` -- Configuration

**`config.yaml` (created on first run, user-editable):**

```yaml
# Knowledge Graph Explorer configuration

db:
  path: ./vault.db                  # path to SQLite database

llm:
  provider: ollama                  # ollama | openai_compat
  base_url: http://localhost:11434
  model: qwen3-coder:30b
  fast_model: null                  # optional: smaller model for intent classification
  temperature: 0

skills:
  enabled: true
  directory: ./skills               # path to skills directory
  python: python3                   # python interpreter
  model: qwen3-coder:30b            # model passed to skills via --model

server:
  host: 127.0.0.1                   # localhost only by default (security)
  port: 8000
  cors_origins: []                  # add origins if accessing from another host

ui:
  theme: dark                       # dark | light
  default_layout: force             # force | hierarchical | clustered
  node_size_by_degree: true
  show_labels: true
  max_visible_nodes: 5000           # performance cap
```

---

## 4. Implementation Plan

### Phase 1: Database Module (`kgx.db`)
**Goal:** Standalone DB package that passes tests without any other module.

Tasks:
- [ ] Create `kgx/db/` package structure
- [ ] Port `vault_db.py` methods into `KnowledgeGraphDB` class with expanded interface
- [ ] Add `entity_types()`, `relationship_types()`, `metadata_keys()` schema discovery
- [ ] Add `graph_nodes()`, `graph_edges()` bulk queries
- [ ] Add `execute_read()`, `execute_write()` with safety checks
- [ ] Add `export_neo4j_csv()` (port from `export_neo4j.py`, read from DB not markdown)
- [ ] Add `export_markdown()` (port per-entity renderers from `render_vault.py`)
- [ ] Write tests against a fixture vault.db
- [ ] Verify existing skills can still use their own `vault_db.py` import (no breakage)

**Deliverable:** `from kgx.db import KnowledgeGraphDB` works standalone.

---

### Phase 2: API Skeleton + Graph View (`kgx.api` + `kgx.ui.graph`)
**Goal:** Open browser, see 3D graph of your vault.db.

Tasks:
- [ ] Create `kgx/api/app.py` with app factory
- [ ] Implement `routes_graph.py`: `/api/graph`, `/api/types`
- [ ] Implement `routes_entity.py`: `/api/entity/:id`, `/api/entities/:type`
- [ ] Create `kgx/ui/index.html` with layout containers
- [ ] Create `kgx/ui/components/shared/event-bus.js`
- [ ] Create `kgx/ui/components/shared/api-client.js`
- [ ] Create `kgx/ui/components/graph/graph.js` -- load from `/api/graph`, render 3D
- [ ] Vendor 3d-force-graph + three.js into `ui/lib/`
- [ ] Create `kgx/cli.py` entry point: `python -m kgx --db vault.db`
- [ ] Create default `config.yaml` generation on first run

**Deliverable:** `python -m kgx --db vault.db` opens browser with 3D graph. Nodes colored by type. Click does nothing yet.

---

### Phase 3: Sidebar + Detail Panel (`kgx.ui.sidebar` + `kgx.ui.detail`)
**Goal:** Click a node, see its detail. Browse entities in sidebar.

Tasks:
- [ ] Create `kgx/ui/components/sidebar/sidebar.js` -- load from `/api/types`, expand sections
- [ ] Create `kgx/ui/components/detail/detail.js` -- load from `/api/entity/:id`
- [ ] Wire sidebar click -> `sidebar:select` event -> graph focuses node
- [ ] Wire graph node click -> `node:selected` event -> detail panel loads
- [ ] Detail panel: render metadata as key-value table, relationships as clickable links
- [ ] Detail panel: clicking a linked entity emits `node:selected` (navigation)
- [ ] Sidebar: search/filter within each entity type section
- [ ] CSS layout: resizable sidebar, collapsible detail panel

**Deliverable:** Full browse experience. Click through the graph, sidebar, and detail panel.

---

### Phase 4: Context Menu + Graph Interactions
**Goal:** Right-click nodes for actions. Filter edges. Hide nodes.

Tasks:
- [ ] Create `kgx/ui/components/graph/context-menu.js` -- generic, action-driven
- [ ] Right-click "Hide this node" -> `node:hide` event -> graph filters it out
- [ ] Right-click "Expand neighbors" -> `node:expand` event -> fetch + add to graph
- [ ] Right-click "Show detail" -> `node:selected` event
- [ ] Sidebar edge filter toggles -> `edge:filter` event -> graph shows/hides edge types
- [ ] Node size proportional to degree
- [ ] "Reset view" button to restore all hidden nodes/edges

**Deliverable:** Interactive graph exploration without chat or skills.

---

### Phase 5: LLM Module + Chat Panel (`kgx.llm` + `kgx.ui.chat`)
**Goal:** Type a question, get SQL results, see highlighted nodes.

Tasks:
- [ ] Create `kgx/llm/base.py` -- `LLMClient` protocol
- [ ] Create `kgx/llm/ollama.py` -- `OllamaClient` with chat + stream
- [ ] Create `kgx/llm/chat_to_sql.py` -- schema-aware prompt, intent classification
- [ ] Create `kgx/llm/intent.py` -- `Intent` dataclass
- [ ] Implement `routes_query.py`: `/api/query` (raw SQL), `/api/mutate/preview`, `/api/mutate/execute`
- [ ] Implement `routes_chat.py`: `/api/chat` (single-shot), `/ws/chat` (streaming)
- [ ] Create `kgx/ui/components/chat/chat.js` -- input, message list, SQL preview toggle
- [ ] Wire chat query results -> `node:highlight` event -> graph pulses matching nodes
- [ ] Wire chat mutation -> confirmation dialog -> `db:changed` event -> graph refresh
- [ ] Test: "who has the most publications" returns a table and highlights nodes

**Deliverable:** Natural language queries over the knowledge graph. Read queries run immediately, mutations require confirmation.

---

### Phase 6: Skill Runner + Dispatch (`kgx.skills`)
**Goal:** Right-click a node -> "Research this person" -> skill runs, graph updates.

Tasks:
- [ ] Create `kgx/skills/registry.py` -- scan skills dir, build SkillDefinition list
- [ ] Create `kgx/skills/runner.py` -- subprocess with async streaming
- [ ] Implement `routes_skill.py`: `/api/skills`, `/api/skill/run`, `/api/skill/jobs/:id`, `/ws/skill/:id`
- [ ] Context menu: "Research this person" -> POST `/api/skill/run` -> stream output
- [ ] Chat: "research Jane Doe" -> intent=skill -> dispatch skill -> stream output
- [ ] Add skill output panel (bottom drawer, shows streaming stdout)
- [ ] On skill completion -> `db:changed` event -> graph + sidebar refresh
- [ ] Test: right-click unprofiled coauthor node, research, see graph update

**Deliverable:** Full loop: explore -> identify gap -> dispatch skill -> see new data.

---

### Phase 7: Layout Presets + Export
**Goal:** Multiple graph layouts. Export to Neo4j/JSON/markdown.

Tasks:
- [ ] `layouts.js`: force-directed (default), hierarchical by type, clustered by tag
- [ ] Layout switcher in toolbar
- [ ] Implement `routes_export.py`: Neo4j CSV zip, full JSON, per-entity markdown
- [ ] Export buttons in toolbar
- [ ] DB file watcher: detect external changes to vault.db, emit `db:changed`

**Deliverable:** Multiple ways to view and export the graph.

---

### Phase 8: Embedding Clustering (stretch)
**Goal:** UMAP/t-SNE layout based on entity text similarity.

Tasks:
- [ ] Add embeddings table to schema (already in SPEC-CORE.md)
- [ ] Script to generate embeddings via Ollama (`/api/embeddings` endpoint)
- [ ] UMAP projection to 2D/3D coordinates
- [ ] "Cluster by embedding" layout preset
- [ ] Color by cluster assignment

**Deliverable:** Semantic clustering reveals thematic groups beyond tag assignments.

---

## 5. Module Dependency Graph

```
config ─────────────────────────────────┐
                                        v
db ◄──────────── api ──────────────► ui (static files)
                  │                     │
llm ◄─────────────┤                     │
                  │                 event-bus connects
skills ◄──────────┘                 all ui components

Key:
  ◄── "depends on" (api depends on db, llm, skills)
  db, llm, skills are independent of each other
  ui components are independent of each other (event-bus coupled)
  config is read by api at startup, passed to other modules
```

No circular dependencies. Each module can be tested by mocking its dependencies.

## 6. Testing Strategy

| Module | Test approach | Mock? |
|---|---|---|
| `kgx.db` | pytest, fixture vault.db with known data | No mocks -- real SQLite |
| `kgx.llm` | pytest, mock HTTP responses from Ollama | Mock httpx |
| `kgx.skills` | pytest, mock subprocess with fake skill script | Mock subprocess |
| `kgx.api` | pytest + httpx.AsyncClient (FastAPI test client) | Mock db, llm, skills |
| `kgx.ui` | Manual browser testing initially; Playwright later | Against running API |

## 7. What Changes in Existing Skills

**Nothing.** The existing skills continue to use their own `vault_db.py` import and write to `vault.db`. The explorer reads the same file. The only requirement: skills must write to the same `vault.db` that the explorer is configured to read. This is already the case.

If a skill runs while the explorer is open, the DB file watcher (Phase 7) detects the change and refreshes the graph automatically.
