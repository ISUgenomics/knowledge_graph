# Knowledge Graph Explorer -- Cross-Platform Web Implementation Spec

Version: 0.1 | Date: 2026-05-31 | Depends on: SPEC-CORE.md

## 1. Architecture Overview

```
+-----------------------------------------------------------+
|  Browser (any OS: macOS, Windows, Linux)                  |
|                                                           |
|  +-- Sidebar ----------+  +-- Canvas ------------------+ |
|  |  HTML/CSS            |  |  3d-force-graph (WebGL)    | |
|  |  Auto from /api      |  |  Same library as Swift ver | |
|  |  Search/filter       |  |  Right-click context menus | |
|  +----------------------+  +---------------------------+ |
|                                                           |
|  +-- Detail Panel (HTML) -------------------------------+ |
|  |  Rendered markdown via marked.js                      | |
|  |  On-demand from /api/entity/:id                       | |
|  +------------------------------------------------------+ |
|                                                           |
|  +-- Chat Panel (HTML) ---------------------------------+ |
|  |  WebSocket for streaming Ollama responses             | |
|  |  /api/chat endpoint                                   | |
|  +------------------------------------------------------+ |
+-----------------------------------------------------------+
           |                    |
           | HTTP/WS            | HTTP/WS
           |                    |
+-----------------------------------------------------------+
|  Python Backend (FastAPI)                                 |
|                                                           |
|  +-- API Layer -----------------------------------------+ |
|  |  /api/graph          -- all nodes + edges (2 queries) | |
|  |  /api/types          -- distinct entity types         | |
|  |  /api/entity/:id     -- single entity + relationships | |
|  |  /api/query          -- arbitrary SELECT (read-only)  | |
|  |  /api/mutate         -- INSERT/UPDATE with confirm    | |
|  |  /api/chat           -- LLM chat endpoint (streaming) | |
|  |  /api/skill/run      -- trigger skill subprocess      | |
|  |  /api/skill/status   -- poll subprocess status        | |
|  +------------------------------------------------------+ |
|                                                           |
|  +-- Data Layer ----------------------------------------+ |
|  |  vault_db.py (already exists, used directly)          | |
|  +------------------------------------------------------+ |
|                                                           |
|  +-- LLM Layer -----------------------------------------+ |
|  |  Ollama client (httpx, streaming)                     | |
|  |  Chat-to-SQL with schema injection                    | |
|  +------------------------------------------------------+ |
|                                                           |
|  +-- Skill Runner --------------------------------------+ |
|  |  asyncio.subprocess for Python skill scripts          | |
|  |  WebSocket streaming of stdout/stderr                 | |
|  +------------------------------------------------------+ |
+-----------------------------------------------------------+
```

## 2. Technology Choices

| Component | Technology | Rationale |
|---|---|---|
| Backend framework | FastAPI | Async Python, auto OpenAPI docs, WebSocket support, you already write Python |
| Database | vault_db.py (existing) | Zero rewrite -- import and use directly |
| Graph rendering | 3d-force-graph | Same library as Swift spec -- identical graph code |
| Frontend framework | Vanilla JS + HTML/CSS | No build step, no npm, minimal complexity. Add a framework later if needed. |
| Markdown rendering | marked.js | Lightweight, client-side markdown to HTML |
| LLM client | httpx (async) | Streaming Ollama responses, SSE to browser |
| Subprocess | asyncio.create_subprocess_exec | Non-blocking skill execution |
| Distribution | `python app.py` | No packaging needed. Optional: PyInstaller for single binary |

## 3. Project Structure

```
explorer/
  app.py                      -- FastAPI entry point, uvicorn runner
  api/
    routes.py                  -- all API endpoints
    chat.py                    -- Ollama integration, chat-to-SQL
    skill_runner.py            -- subprocess management
  static/
    index.html                 -- single-page app
    css/
      style.css                -- layout: sidebar, graph, detail, chat
    js/
      app.js                   -- main app controller
      graph.js                 -- 3d-force-graph init + events (same as Swift version)
      sidebar.js               -- dynamic sidebar from /api/types
      detail.js                -- entity detail panel
      chat.js                  -- chat panel + WebSocket
      context-menu.js          -- right-click menus
    lib/
      3d-force-graph.min.js    -- bundled (no CDN dependency)
      three.min.js             -- bundled
      marked.min.js            -- bundled
  pyproject.toml               -- app package metadata and dependencies
```

## 4. Key Implementation Details

### 4.1 Backend API (routes.py)

```python
from fastapi import FastAPI, WebSocket
from vault_db import VaultDB

app = FastAPI()
db: VaultDB = None  # initialized on startup

@app.on_event("startup")
def startup():
    global db
    db = VaultDB(os.environ.get("VAULT_DB", "vault.db"))

@app.get("/api/graph")
def get_graph():
    """Return all nodes and edges for the graph view."""
    nodes = [{"id": e["id"], "type": e["type"], "name": e["name"]}
             for e in db.get_entities()]
    edges = [dict(r) for r in db.conn.execute(
        "SELECT source_id, target_id, rel_type FROM relationships"
    )]
    return {"nodes": nodes, "edges": edges}

@app.get("/api/types")
def get_types():
    """Return distinct entity types and relationship types with counts."""
    entity_types = [dict(r) for r in db.conn.execute(
        "SELECT type, COUNT(*) as count FROM entities GROUP BY type ORDER BY type"
    )]
    rel_types = [dict(r) for r in db.conn.execute(
        "SELECT rel_type, COUNT(*) as count FROM relationships GROUP BY rel_type"
    )]
    return {"entity_types": entity_types, "relationship_types": rel_types}

@app.get("/api/entity/{entity_id}")
def get_entity(entity_id: str):
    """Return full entity detail + relationships."""
    entity = db.get_entity(entity_id)
    if not entity:
        raise HTTPException(404)
    rels = db.get_relationships(entity_id)
    neighbors = db.neighbors(entity_id)
    return {"entity": entity, "relationships": rels, "neighbors": neighbors}

@app.get("/api/entities/{entity_type}")
def get_entities_by_type(entity_type: str):
    """Return list of entities for sidebar."""
    return [{"id": e["id"], "name": e["name"]}
            for e in db.get_entities(entity_type)]

@app.post("/api/query")
def run_query(body: dict):
    """Execute a read-only SQL query. Rejects non-SELECT statements."""
    sql = body["sql"].strip()
    if not sql.upper().startswith("SELECT"):
        raise HTTPException(400, "Only SELECT queries allowed via this endpoint")
    results = [dict(r) for r in db.conn.execute(sql)]
    return {"results": results, "count": len(results)}

@app.post("/api/mutate")
def run_mutation(body: dict):
    """Execute a write query. Requires confirmation token."""
    # Frontend must first POST to /api/mutate/preview to get a token
    # Then POST to /api/mutate with the token to execute
    ...

@app.post("/api/skill/run")
async def run_skill(body: dict):
    """Trigger a skill subprocess. Returns a job_id for status polling."""
    ...

@app.get("/api/skill/status/{job_id}")
async def skill_status(job_id: str):
    """Return current status + output of a running skill."""
    ...
```

### 4.2 Chat-to-SQL (chat.py)

```python
import httpx

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")

SYSTEM_PROMPT = """You are a SQL assistant for a knowledge graph database.

Schema:
  entities (id TEXT PK, type TEXT, name TEXT, metadata JSON, created_at, updated_at)
  aliases  (alias TEXT PK, entity_id TEXT FK)
  relationships (source_id TEXT, rel_type TEXT, target_id TEXT, metadata JSON)

Entity types: {entity_types}
Relationship types: {rel_types}

Rules:
- Return ONLY the SQL query, no explanation
- For metadata fields, use json_extract(metadata, '$.field_name')
- Use entity type and relationship type values exactly as listed above
- For mutations, prefix with -- MUTATION so the app can detect it
"""

async def chat_to_sql(question: str, db: VaultDB) -> dict:
    """Translate natural language to SQL via Ollama."""
    stats = db.stats()
    entity_types = list(stats["entities"].keys())
    rel_types = list(stats["relationships"].keys())

    system = SYSTEM_PROMPT.format(
        entity_types=entity_types, rel_types=rel_types
    )

    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{OLLAMA_URL}/api/chat", json={
            "model": os.environ.get("OLLAMA_MODEL", "qwen3-coder:30b"),
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": question},
            ],
            "stream": False,
        })
        sql = resp.json()["message"]["content"].strip()

    is_mutation = sql.startswith("-- MUTATION") or not sql.upper().startswith("SELECT")
    return {"sql": sql, "is_mutation": is_mutation}
```

### 4.3 WebSocket for Streaming (routes.py)

```python
@app.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket):
    """Streaming chat endpoint. Sends tokens as they arrive from Ollama."""
    await websocket.accept()
    while True:
        question = await websocket.receive_text()
        async with httpx.AsyncClient() as client:
            async with client.stream("POST", f"{OLLAMA_URL}/api/chat", json={
                "model": "qwen3-coder:30b",
                "messages": [{"role": "user", "content": question}],
                "stream": True,
            }) as resp:
                async for line in resp.aiter_lines():
                    chunk = json.loads(line)
                    await websocket.send_text(chunk["message"]["content"])

@app.websocket("/ws/skill/{job_id}")
async def ws_skill_output(websocket: WebSocket, job_id: str):
    """Stream subprocess stdout/stderr to browser."""
    await websocket.accept()
    # Stream from the running asyncio.subprocess
    ...
```

### 4.4 Frontend Graph (graph.js)

Identical to the Swift version's graph.js -- same library, same event patterns.
The only difference: events POST to `/api/` endpoints instead of `window.webkit.messageHandlers`.

```javascript
// Fetch graph data from API
async function loadGraph() {
    const resp = await fetch('/api/graph');
    const data = await resp.json();

    Graph.graphData({
        nodes: data.nodes,
        links: data.edges.map(e => ({
            source: e.source_id, target: e.target_id, rel_type: e.rel_type
        }))
    });
}

// Node click -> fetch detail from API
Graph.onNodeClick(async (node) => {
    const resp = await fetch(`/api/entity/${node.id}`);
    const detail = await resp.json();
    renderDetailPanel(detail);
});

// Right-click -> context menu
Graph.onNodeRightClick((node, event) => {
    showContextMenu(node, event.clientX, event.clientY);
});
```

### 4.5 Dynamic Sidebar (sidebar.js)

```javascript
async function loadSidebar() {
    const resp = await fetch('/api/types');
    const data = await resp.json();

    const sidebar = document.getElementById('sidebar');
    sidebar.innerHTML = '';

    for (const t of data.entity_types) {
        const section = createSection(t.type, t.count);
        section.addEventListener('click', () => expandSection(t.type));
        sidebar.appendChild(section);
    }

    // Edge filter toggles
    const filters = document.getElementById('edge-filters');
    for (const r of data.relationship_types) {
        filters.appendChild(createToggle(r.rel_type, r.count));
    }
}

async function expandSection(type) {
    const resp = await fetch(`/api/entities/${type}`);
    const entities = await resp.json();
    // Render as clickable list items
}
```

## 5. Distribution

### Development (any OS)
```bash
pip install fastapi uvicorn httpx
VAULT_DB=/path/to/vault.db python explorer/app.py
# Open http://localhost:8000
```

### Production-ish (single command)
```bash
# One-liner start script
VAULT_DB=~/vault/vault.db OLLAMA_MODEL=qwen3-coder:30b python -m uvicorn explorer.app:app --host 0.0.0.0 --port 8000
```

### Packaged binary (optional)
```bash
# PyInstaller for single-file distribution
pip install pyinstaller
pyinstaller --onefile --add-data "static:static" app.py
# Produces: dist/app (single binary, ~50MB with Python bundled)
```

### Docker (optional, for team sharing)
```dockerfile
FROM python:3.12-slim
COPY explorer/ /app/
WORKDIR /app
RUN pip install fastapi uvicorn httpx
EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
# Note: Ollama must be accessible from the container (host network or separate service)
```

## 6. Build Order

| Phase | Deliverable | Depends on |
|---|---|---|
| 1 | FastAPI app + `/api/graph`, `/api/types`, `/api/entity/:id` | vault_db.py (exists) |
| 2 | Static HTML + graph.js: render nodes/edges from API | Phase 1 |
| 3 | Sidebar: auto from `/api/types` | Phase 1 |
| 4 | Click handler: detail panel from `/api/entity/:id` | Phase 2 |
| 5 | Right-click: context menu + hide/expand | Phase 2 |
| 6 | Chat-to-SQL via Ollama (`/api/chat`) | Phase 1 |
| 7 | Chat panel UI wired via WebSocket | Phase 6 |
| 8 | Skill runner: `/api/skill/run` + WebSocket output | Phase 1 |
| 9 | Right-click "Research this person" --> skill runner | Phase 5, 8 |
| 10 | Layout presets, clustering, embedding viz | Phase 2 |
| 11 | Docker / PyInstaller packaging (optional) | All |

Phases 1-5 produce a working graph explorer (any browser, any OS). Same milestone as Swift Phase 1-5.

## 7. Apple Intelligence Alternative

No Apple Intelligence available in the web version. All LLM tasks go through Ollama.
For intent classification, use a small local model (e.g., `phi-4:14b`) for fast routing,
with `qwen3-coder:30b` for complex SQL generation and extraction.

Two-model approach:
```python
FAST_MODEL = "phi-4:14b"       # intent classification, simple queries
HEAVY_MODEL = "qwen3-coder:30b"  # complex SQL, skill dispatch reasoning
```
