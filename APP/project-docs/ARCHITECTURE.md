# KGX — Knowledge Graph Explorer Architecture

> Auto-generated from code scan on 2026-05-31

## System Overview

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                    Knowledge Graph Explorer (KGX)                            │
│                                                                              │
│   ┌──────────────────────────────────────────────────────────────────────┐   │
│   │                         Browser (localhost:8000)                      │   │
│   │                                                                      │   │
│   │   ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌────────┐  │   │
│   │   │ Sidebar  │  │  Graph  │  │ Detail  │  │  Chat   │  │Context │  │   │
│   │   │  .js     │  │  .js    │  │  .js    │  │  .js    │  │Menu .js│  │   │
│   │   └────┬─────┘  └────┬────┘  └────┬────┘  └────┬────┘  └────┬───┘  │   │
│   │        │             │            │             │             │      │   │
│   │        └─────────────┴──────┬─────┴─────────────┴─────────────┘      │   │
│   │                             │                                        │   │
│   │                      ┌──────┴──────┐                                 │   │
│   │                      │  EventBus   │  (pub/sub — no direct imports)  │   │
│   │                      └──────┬──────┘                                 │   │
│   │                             │                                        │   │
│   │                      ┌──────┴──────┐                                 │   │
│   │                      │  ApiClient  │  (fetch wrapper)                │   │
│   │                      └─────────────┘                                 │   │
│   └──────────────────────────────────────────────────────────────────────┘   │
│                                 │                                            │
│                            HTTP │ REST + SSE                                 │
│                                 ▼                                            │
│   ┌──────────────────────────────────────────────────────────────────────┐   │
│   │                    FastAPI Server (uvicorn)                           │   │
│   │                                                                      │   │
│   │   ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌─────────┐  │   │
│   │   │  Graph   │ │  Entity  │ │  Query   │ │  Export  │ │  Chat   │  │   │
│   │   │  Router  │ │  Router  │ │  Router  │ │  Router  │ │  Router │  │   │
│   │   └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬────┘  │   │
│   │        │             │            │             │             │      │   │
│   │   ┌────┴─────┐ ┌────┴─────┐                              ┌──┴───┐  │   │
│   │   │  Skills  │ │  Watch   │                              │ LLM  │  │   │
│   │   │  Router  │ │  Router  │                              │Client│  │   │
│   │   └────┬─────┘ └────┬─────┘                              └──┬───┘  │   │
│   │        │             │                                       │      │   │
│   │        │             │          ┌────────────┐               │      │   │
│   │        │             └──────────┤            │               │      │   │
│   │        │                        │ KG DB      ├───────────────┘      │   │
│   │        │                ┌───────┤ (queries)  │                      │   │
│   │        │                │       └──────┬─────┘                      │   │
│   │        │                │              │                            │   │
│   │   ┌────┴────┐   ┌──────┴───┐   ┌──────┴─────┐                     │   │
│   │   │Registry │   │ Runner   │   │  SQLite    │                     │   │
│   │   │(skills) │   │(subprocess)  │  vault.db  │                     │   │
│   │   └─────────┘   └──────────┘   └────────────┘                     │   │
│   └──────────────────────────────────────────────────────────────────────┘   │
│                                            │                                 │
│                                       file │ poll mtime                      │
│                                            │                                 │
│   ┌────────────────────────────────────────┴──────────────────────────────┐  │
│   │                    LangGraph Skills (external)                        │  │
│   │                                                                       │  │
│   │   ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌────────────┐  │  │
│   │   │person_research│ │center_research│ │event_research│ │signal_     │  │  │
│   │   │              │ │              │ │              │ │capture     │  │  │
│   │   └──────────────┘ └──────────────┘ └──────────────┘ └────────────┘  │  │
│   │              │                                                        │  │
│   │              └──────────── write ──────────────> vault.db             │  │
│   └───────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│   ┌───────────────────────────────────────────────────────────────────────┐  │
│   │                    Ollama (localhost:11434)                            │  │
│   │                    Model: qwen3-coder:30b                             │  │
│   └───────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────────┘
```

## Service Responsibilities

| Component | Role | Key Files |
|---|---|---|
| **FastAPI Server** | HTTP API, static file serving, app wiring | `kgx/api/app.py`, `kgx/cli.py` |
| **KnowledgeGraphDB** | All SQLite access — CRUD, graph queries, export | `kgx/db/queries.py`, `kgx/db/schema.py` |
| **LLM Module** | Ollama client + chat-to-SQL translation | `kgx/llm/client.py`, `kgx/llm/chat_sql.py` |
| **Skill System** | Auto-discover + run LangGraph plugins as subprocesses | `kgx/skills/registry.py`, `kgx/skills/runner.py` |
| **Config** | YAML loader with Pydantic models | `kgx/config/loader.py` |
| **Graph UI** | 3D force-directed graph (3d-force-graph / Three.js) | `kgx/ui/components/graph/graph.js` |
| **Sidebar UI** | Entity browser, edge type filters | `kgx/ui/components/sidebar/sidebar.js` |
| **Detail UI** | Entity detail panel (properties, relationships, markdown) | `kgx/ui/components/detail/detail.js` |
| **Chat UI** | Natural language query panel with result tables | `kgx/ui/components/chat/chat.js` |
| **EventBus** | Pub/sub — all UI components communicate via bus, never import each other | `kgx/ui/components/shared/event-bus.js` |

## Data Flow

```
  User types NL query         User clicks node           Skill writes to vault.db
       │                           │                            │
       ▼                           ▼                            ▼
  POST /api/chat              GET /api/entity/:id          mtime changes
       │                           │                            │
       ▼                           ▼                            ▼
  ChatToSQL.ask()             KG DB.get_entity()          /api/watch SSE
       │                           │                        "changed" event
       ▼                           ▼                            │
  Ollama generates SQL        Return JSON to detail         bus.emit(
       │                      panel via EventBus            'db:changed')
       ▼                                                        │
  KG DB.execute_read()                                          ▼
       │                                                   Graph + Sidebar
       ▼                                                   auto-reload
  Results → Chat panel
```

## Event Bus Protocol

All UI components communicate via the shared EventBus. No component imports another.

| Event | Payload | Emitter → Listener |
|---|---|---|
| `graph:loaded` | `{nodeCount, edgeCount, typeColors}` | Graph → Sidebar, Header |
| `graph:refresh` | `{}` | any → Graph |
| `db:changed` | `{}` | Watch SSE → Graph, Sidebar |
| `node:selected` | `{id, type, name}` | Graph/Sidebar → Detail, Sidebar |
| `node:right-clicked` | `{id, type, name, x, y}` | Graph → ContextMenu |
| `node:hide` | `{id}` | ContextMenu → Graph |
| `node:show-all` | `{}` | Header → Graph |
| `node:highlight` | `{ids}` | Chat → Graph |
| `node:focus` | `{id}` | Sidebar/ContextMenu → Graph |
| `node:expand` | `{id}` | ContextMenu → Graph |
| `edge:filter` | `{rel_type, visible}` | Sidebar → Graph |
| `edge:reset` | `{}` | Graph → Sidebar |
| `sidebar:select` | `{id, type, name}` | Sidebar → Graph |
| `labels:toggle` | `{visible}` | Header → Graph |
| `layout:change` | `{layout}` | Header → Graph |
| `skill:dispatch` | `{skill, entity_id, ...}` | ContextMenu → index.html |
| `skill:started` | `{job_id, skill, entity_name}` | index.html → Chat |
| `chat:mutation` | `{sql, token, preview}` | Chat → index.html (confirm dialog) |

---

## API Routes

```
  /api/
  ├── graph/
  │   ├── GET    /graph                           → routes_graph.py:get_graph
  │   ├── GET    /types                           → routes_graph.py:get_types
  │   └── GET    /stats                           → routes_graph.py:get_stats
  │
  ├── entity/
  │   ├── GET    /entities/{type}                 → routes_entity.py:get_entities
  │   ├── GET    /entity/{id}/neighbors           → routes_entity.py:get_neighbors
  │   ├── GET    /entity/{id}/markdown            → routes_entity.py:get_entity_markdown
  │   └── GET    /entity/{id}                     → routes_entity.py:get_entity  (catch-all, last)
  │
  ├── query/
  │   ├── POST   /query                           → routes_query.py:run_query
  │   ├── POST   /mutate/preview                  → routes_query.py:mutate_preview
  │   └── POST   /mutate/execute                  → routes_query.py:mutate_execute
  │
  ├── export/
  │   ├── GET    /export/json                     → routes_export.py:export_json
  │   ├── GET    /export/neo4j                    → routes_export.py:export_neo4j
  │   └── GET    /export/markdown/{id}            → routes_export.py:export_markdown
  │
  ├── chat/
  │   ├── GET    /chat/status                     → routes_chat.py:chat_status
  │   └── POST   /chat                            → routes_chat.py:chat
  │
  ├── skills/
  │   ├── GET    /skill/list                      → routes_skills.py:skill_list
  │   ├── GET    /skill/jobs                      → routes_skills.py:job_list
  │   ├── GET    /skill/job/{id}                  → routes_skills.py:job_status
  │   ├── POST   /skill/run                       → routes_skills.py:run_skill
  │   └── GET    /skill/stream/{id}               → routes_skills.py:stream_job  (SSE)
  │
  └── watch/
      └── GET    /watch                           → routes_watch.py:watch_db  (SSE)

  Total: 18 endpoints across 6 resources
```

---

## Database Schema

```
  ┌──────────────────────────────┐      ┌──────────────────────────────┐
  │ entities                     │      │ aliases                      │
  ├──────────────────────────────┤      ├──────────────────────────────┤
  │ id          TEXT    PK       │──┐   │ alias       TEXT    PK       │
  │ type        TEXT    NOT NULL │  │   │ entity_id   TEXT    FK ──────│──┐
  │ name        TEXT    NOT NULL │  │   └──────────────────────────────┘  │
  │ metadata    TEXT    JSON     │  │                                     │
  │ created_at  TEXT    DEFAULT  │  └─────────────────────────────────────┘
  │ updated_at  TEXT    DEFAULT  │
  └──────────────────────────────┘
           │
           │ FK (source_id, target_id)
           ▼
  ┌──────────────────────────────┐
  │ relationships                │
  ├──────────────────────────────┤
  │ source_id   TEXT    FK       │
  │ rel_type    TEXT    NOT NULL │
  │ target_id   TEXT    FK       │
  │ metadata    TEXT    JSON     │
  │ PK (source_id, rel_type,    │
  │     target_id)              │
  └──────────────────────────────┘

  ┌──────────────────────────────┐      ┌──────────────────────────────┐
  │ embeddings                   │      │ saved_views                  │
  ├──────────────────────────────┤      ├──────────────────────────────┤
  │ entity_id   TEXT    PK, FK   │      │ name        TEXT    PK       │
  │ vector      BLOB             │      │ config      TEXT    JSON     │
  │ model       TEXT             │      │ created_at  TEXT    DEFAULT  │
  │ updated_at  TEXT    DEFAULT  │      └──────────────────────────────┘
  └──────────────────────────────┘
                                        ┌──────────────────────────────┐
                                        │ chat_history                 │
                                        ├──────────────────────────────┤
                                        │ id          INTEGER PK AUTO  │
                                        │ session_id  TEXT             │
                                        │ role        TEXT             │
                                        │ content     TEXT             │
                                        │ sql_query   TEXT    NULLABLE │
                                        │ created_at  TEXT    DEFAULT  │
                                        └──────────────────────────────┘

  Indexes:
    entities.type          — idx_entities_type
    entities.name          — idx_entities_name
    aliases.entity_id      — idx_aliases_entity
    relationships.source_id — idx_rels_source
    relationships.target_id — idx_rels_target
    relationships.rel_type  — idx_rels_type
    chat_history.session_id — idx_chat_session

  Entity types (dynamic):  person, publication, signal, event, center, tag
  Relationship types:      AUTHORED, ATTENDED, MENTIONED_IN, TAGGED, COAUTHOR, MEMBER_OF
  Schema version:          2
  Journal mode:            WAL (concurrent reads)
  Foreign keys:            ON (CASCADE deletes)
```

---

## File Tree

```
APP/
├── config.yaml                         # Server, LLM, skills, UI config
├── pyproject.toml                      # Package metadata + dependencies
├── requirements.txt                    # Pinned dependencies
├── kgx/
│   ├── __init__.py
│   ├── __main__.py                     # python -m kgx entry point
│   ├── cli.py                          # argparse CLI, uvicorn launcher
│   ├── config/
│   │   ├── __init__.py                 # re-exports load_config
│   │   └── loader.py                   # YAML → Pydantic models
│   ├── db/
│   │   ├── __init__.py                 # re-exports KnowledgeGraphDB
│   │   ├── schema.py                   # DDL, migrations, init_schema()
│   │   ├── queries.py                  # KnowledgeGraphDB class (all SQL)
│   │   └── tests/
│   │       └── test_db.py              # 40 tests for DB layer
│   ├── api/
│   │   ├── __init__.py                 # re-exports create_app
│   │   ├── app.py                      # FastAPI factory, router wiring
│   │   ├── routes_graph.py             # /api/graph, /api/types, /api/stats
│   │   ├── routes_entity.py            # /api/entity/*, /api/entities/*
│   │   ├── routes_query.py             # /api/query, /api/mutate/*
│   │   ├── routes_export.py            # /api/export/json, neo4j, markdown
│   │   ├── routes_chat.py              # /api/chat, /api/chat/status
│   │   ├── routes_skills.py            # /api/skill/*
│   │   └── routes_watch.py             # /api/watch (SSE)
│   ├── llm/
│   │   ├── __init__.py                 # re-exports OllamaClient, ChatToSQL
│   │   ├── client.py                   # httpx wrapper for Ollama API
│   │   └── chat_sql.py                 # NL → SQL translator
│   ├── skills/
│   │   ├── __init__.py                 # re-exports SkillRegistry, SkillRunner
│   │   ├── registry.py                 # Auto-discover skills from filesystem
│   │   └── runner.py                   # Async subprocess execution
│   └── ui/
│       ├── index.html                  # App shell, bootstrap, global handlers
│       ├── lib/
│       │   └── 3d-force-graph.min.js   # Vendored (no CDN)
│       └── components/
│           ├── shared/
│           │   ├── theme.css           # CSS variables, dark theme
│           │   ├── event-bus.js        # Pub/sub event bus
│           │   └── api-client.js       # fetch() wrapper
│           ├── graph/
│           │   ├── graph.js            # 3D force graph (Three.js/WebGL)
│           │   ├── graph.css
│           │   └── context-menu.js     # Right-click menu
│           ├── sidebar/
│           │   ├── sidebar.js          # Entity browser + edge filters
│           │   └── sidebar.css
│           ├── detail/
│           │   ├── detail.js           # Entity detail panel
│           │   └── detail.css
│           └── chat/
│               ├── chat.js             # NL chat panel
│               └── chat.css
```

---

## Changelog

| Date | Change |
|---|---|
| 2026-05-31 | Initial architecture, API, and database diagrams generated from code scan |
