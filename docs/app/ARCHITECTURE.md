# KGX — Knowledge Graph Explorer Architecture

> Auto-generated from code scan on 2026-06-01

## System Overview

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                    Knowledge Graph Explorer (KGX)                            │
│                                                                              │
│   ┌──────────────────────────────────────────────────────────────────────┐   │
│   │                         Browser (localhost:8000)                      │   │
│   │                                                                      │   │
│   │   ┌─────────┐  ┌──────────┐  ┌─────────┐  ┌──────┐  ┌──────────┐  │   │
│   │   │ Sidebar  │  │  Graph   │  │ Detail  │  │ Chat │  │ SQL      │  │   │
│   │   │  .js     │  │  .js     │  │  .js    │  │ .js  │  │ Panel    │  │   │
│   │   │          │  │          │  │         │  │      │  │(last SQL)│  │   │
│   │   │- Entity  │  │- 3D Force│  │- Props  │  │- NL  │  │          │  │   │
│   │   │  browser │  │- UMAP    │  │- Rich   │  │  SQL │  │- Copy    │  │   │
│   │   │- Edge    │  │- Cluster │  │  content│  │- Fast│  │          │  │   │
│   │   │  filters │  │- Timeline│  │- Topics │  │  path│  │          │  │   │
│   │   │- SQL     │  │- Settings│  │- Nav    │  │- Hist│  │          │  │   │
│   │   │  filters │  │  panel   │  │  ↑↓     │  │  ↑↓  │  │          │  │   │
│   │   └────┬─────┘  └────┬────┘  └────┬────┘  └──┬───┘  └────┬─────┘  │   │
│   │        │             │            │           │            │        │   │
│   │        └─────────────┴──────┬─────┴───────────┴────────────┘        │   │
│   │                             │                                       │   │
│   │                      ┌──────┴──────┐                                │   │
│   │                      │  EventBus   │  (pub/sub — no direct imports) │   │
│   │                      └──────┬──────┘                                │   │
│   │                             │                                       │   │
│   │                      ┌──────┴──────┐                                │   │
│   │                      │  ApiClient  │  (fetch wrapper)               │   │
│   │                      └─────────────┘                                │   │
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
│   │   ┌────┴─────┐ ┌────┴─────┐ ┌────┴─────┐               ┌──┴───┐  │   │
│   │   │  Skills  │ │  Watch   │ │  Layout  │               │ LLM  │  │   │
│   │   │  Router  │ │  Router  │ │  Router  │               │Client│  │   │
│   │   └────┬─────┘ └────┬─────┘ └────┬─────┘               └──┬───┘  │   │
│   │        │             │            │                         │      │   │
│   │        │             │            │    ┌────────────┐       │      │   │
│   │        │             └────────────┴────┤            │       │      │   │
│   │        │                               │ KG DB      ├───────┘      │   │
│   │        │                ┌──────────────┤ (queries)  │              │   │
│   │        │                │              └──────┬─────┘              │   │
│   │        │                │                     │                    │   │
│   │   ┌────┴────┐   ┌──────┴───┐   ┌─────────────┴──┐                │   │
│   │   │Registry │   │ Runner   │   │  SQLite         │                │   │
│   │   │(skills) │   │(subprocess)  │  vault.db       │                │   │
│   │   └─────────┘   └──────────┘   │  (schema v3)    │                │   │
│   │                                 └────────────────┘                │   │
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
| **KnowledgeGraphDB** | All SQLite access — CRUD, graph queries, rich content, export | `kgx/db/queries.py`, `kgx/db/schema.py` |
| **LLM Module** | Ollama client + chat-to-SQL translation + fast-path schema answers | `kgx/llm/client.py`, `kgx/llm/chat_sql.py` |
| **Layout Module** | UMAP embedding + layout computation via Ollama nomic-embed-text | `kgx/layout/embedder.py`, `kgx/layout/umap_layout.py` |
| **Skill System** | Auto-discover + run LangGraph plugins as subprocesses | `kgx/skills/registry.py`, `kgx/skills/runner.py` |
| **Config** | YAML loader with Pydantic models | `kgx/config/loader.py` |
| **Graph UI** | 3D force-directed graph (3d-force-graph / Three.js) with explore mode, community detection, dynamic sizing | `kgx/ui/components/graph/graph.js` |
| **Sidebar UI** | Entity browser, edge type filters, SQL filters (localStorage) | `kgx/ui/components/sidebar/sidebar.js` |
| **Detail UI** | Entity detail — properties, rich content, relationships, arrow key nav | `kgx/ui/components/detail/detail.js` |
| **Chat UI** | NL query panel with result tables, filter/highlight actions, input history | `kgx/ui/components/chat/chat.js` |
| **SQL Panel** | Displays last executed SQL with copy button | `kgx/ui/index.html` (inline) |
| **Force Settings** | Draggable panel for force graph parameters, edge styling, presets | `kgx/ui/index.html` (inline) |
| **Context Menu** | Right-click node actions: detail, focus, orbit, highlight, expand, hide, research | `kgx/ui/components/graph/context-menu.js` |
| **EventBus** | Pub/sub — all UI components communicate via bus, never import each other | `kgx/ui/components/shared/event-bus.js` |

## Data Flow

```
  User types NL query         User clicks node           Skill writes to vault.db
       │                           │                            │
       ▼                           ▼                            ▼
  POST /api/chat              GET /api/entity/:id          mtime changes
       │                           │                            │
       ├─ fast-path?               ▼                            ▼
       │  (schema Q)          KG DB.get_entity()          /api/watch SSE
       │  → instant             + get_rich()               "changed" event
       │    answer                 │                            │
       │                           ▼                            ▼
       ├─ LLM path            Return JSON to detail       bus.emit(
       │  → Ollama             panel via EventBus           'db:changed')
       │  → SQL                    │                            │
       ▼                           ▼                            ▼
  KG DB.execute_read()        Detail panel renders        Graph + Sidebar
       │                      rich content:               auto-reload
       ▼                      topics, snippets,
  Results → Chat panel        contacts, interests,
       │                      sources, relationships
       ├─ Has id column?      with entity names
       │  → Highlight btn
       │  → Hide btn          User presses ↑↓
       │  → Save filter btn   → navigates to
       │                        next/prev entity
       └─ Clickable rows        of same type
          → orbit + select
```

## NL Query Backend

The natural-language query path is now split into a shared semantic execution layer and thinner domain modules.

### Runtime flow

1. `/api/chat` routes the request into `kgx/llm/chat_sql.py`.
2. `ChatToSQL` decides whether the prompt is:
   - a fast-path schema question answered directly from the DB, or
   - an LLM-backed SQL request.
3. The selected domain module contributes semantic context before and after the LLM step:
   - prompt/schema hints
   - preferred or suppressed result types
   - semantic validation
   - deterministic query synthesis or correction when the model misses required semantics
4. If validation fails, KGX now prefers registry-backed correction paths or a retry over returning invalid SQL silently.

### Shared semantic layer

Shared infrastructure in `kgx/llm/modules/base.py` now owns most reusable semantic behavior:

- semantic registry and schema loading
- registry-driven operator execution
- registry-driven condition dispatch
- registry-driven dynamic-family expansion
- shared validation helpers for missing or unexpected semantic signatures

This is the main move toward a single-source-of-truth backend: semantic rules increasingly live in registry/config and are executed by shared machinery instead of handwritten domain SQL logic.

### Domain module role

Domain modules should now mostly provide:

- domain registry loading
- prompt-corpus and schema-context hints
- minimal runtime adapters when live graph data is needed
- narrow fallback heuristics where the graph cannot yet be described declaratively

Current examples:

- `people` is mostly registry-driven for parsing, rendering, synthesis, and validation.
- `genomics` is substantially more registry-driven than before, but still keeps a smaller fallback layer for graph-derived organism/tag heuristics.

### Dynamic-family pattern

Dynamic semantic families, such as genomics effector evidence tags, follow this split:

- registry config defines source rules, normalization, flag classification, alias templates, owner typing, and output kind
- the shared executor expands those rules into runtime semantic specs
- domain code only supplies live scoped values when templates need them, such as primary and secondary organism aliases

If a new domain needs more than scoped live values, the intended direction is to extend the shared executor rather than reintroduce local semantic-family logic.

### Adding a new semantic domain

Use this checklist when bringing a new domain onto the NL backend:

1. Add domain registry and schema loaders.
   - Create `<domain>_source.py` with semantic schema and semantic registry definitions.
   - Register the domain through `kgx/domain_sources.py` if it needs app-level dispatch.

2. Add or extend the domain module.
   - Create or update `kgx/llm/modules/<domain>.py`.
   - Keep domain code focused on:
     - registry loading
     - prompt or schema-context hints
     - minimal live-data adapters
     - narrow fallback heuristics only when the graph cannot yet describe the behavior declaratively

3. Put semantics in registry/config first.
   - Prefer registry-defined:
     - aliases and parsing cues
     - operator specs
     - dynamic-family rules
     - validation signatures
     - prompt-corpus section names and schema hints
   - Only extend shared code when multiple domains would benefit from the same execution pattern.

4. Wire prompt corpus and app exposure.
   - Add few-shot examples in `kgx/llm/tests/prompt_corpus.yaml`.
   - Make sure the app exposes the domain semantic schema and registry through `kgx/api/app.py` and module loading paths.

5. Add contract tests across surfaces.
   - `kgx/llm/tests/test_chat_sql.py`
     - parsing
     - synthesis
     - validation
     - custom-registry behavior
   - `kgx/llm/tests/test_prompt_corpus.py`
     - corpus alignment with the domain module and registry
   - `kgx/api/tests/test_app_smoke.py`
     - app-exposed semantic schema and registry

6. Check the failure boundary explicitly.
   - If any semantic behavior remains handwritten, document why it is still a runtime fallback.
   - Prefer a small explicit fallback boundary over hidden semantic duplication in module logic.

## Event Bus Protocol

All UI components communicate via the shared EventBus. No component imports another.

| Event | Payload | Emitter → Listener |
|---|---|---|
| `graph:loaded` | `{nodeCount, edgeCount, typeColors, relTypeCounts}` | Graph → Sidebar, Header |
| `graph:refresh` | `{}` | any → Graph |
| `db:changed` | `{}` | Watch SSE → Graph, Sidebar |
| `node:selected` | `{id, type, name}` | Graph/Sidebar/Chat → Detail, Chat |
| `node:right-clicked` | `{id, type, name, x, y}` | Graph → ContextMenu |
| `node:hide` | `{id}` | ContextMenu → Graph |
| `node:show-all` | `{}` | Header → Graph (clears all filters + forceShown) |
| `node:highlight` | `{ids}` | Chat → Graph (white + dim others) |
| `node:highlight-neighbors` | `{id}` | ContextMenu → Graph (highlight direct neighbors) |
| `node:highlight-cleared` | `{}` | Graph → Chat (re-enable highlight btn) |
| `node:focus` | `{id}` | Sidebar/ContextMenu → Graph (camera fly-to) |
| `node:orbit` | `{id}` | ContextMenu/Chat → Graph (set orbit pivot) |
| `node:expand` | `{id}` | ContextMenu → Graph (force-show neighbors, overrides filters) |
| `node:sql-filter` | `{filter_id, ids, active}` | Sidebar/Chat → Graph |
| `edge:filter` | `{rel_type, visible}` | Sidebar → Graph |
| `edge:reset` | `{}` | Graph → Sidebar |
| `sidebar:select` | `{id, type, name}` | Sidebar → Graph |
| `labels:toggle` | `{visible}` | Header → Graph |
| `community:toggle` | `{}` | Header → Graph (toggle cluster coloring) |
| `layout:change` | `{layout}` | Header → Graph |
| `force:update` | `{linkDist, charge, ..., edgeWidth, edgeOpacity, edgeColor, particles, typeCharges}` | Settings → Graph |
| `force:get-types` | `{callback}` | Settings → Graph |
| `force:reheat` | `{}` | Settings → Graph |
| `skill:dispatch` | `{skill, entity_id, ...}` | ContextMenu → index.html |
| `skill:started` | `{job_id, skill, entity_name}` | index.html → Chat |
| `chat:mutation` | `{sql, token, preview}` | Chat → index.html (confirm dialog) |
| `chat:sql-executed` | `{sql}` | Chat → SQL Panel |
| `chat:save-filter` | `{name, sql}` | Chat → Sidebar (saves to localStorage) |

---

## API Routes

```
  /api/
  ├── graph/
  │   ├── GET    /graph?mode=explore               → routes_graph.py:get_graph
  │   ├── GET    /types                           → routes_graph.py:get_types
  │   └── GET    /stats                           → routes_graph.py:get_stats
  │
  ├── entity/
  │   ├── GET    /entities/{type}                 → routes_entity.py:get_entities
  │   ├── GET    /entity/{id}/neighbors           → routes_entity.py:get_neighbors
  │   ├── GET    /entity/{id}/markdown            → routes_entity.py:get_entity_markdown
  │   └── GET    /entity/{id}                     → routes_entity.py:get_entity
  │              (returns rich content: topics, snippets, contacts, interests, sources)
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
  │              (fast-path for schema Qs, LLM for SQL, strips <think> blocks)
  │
  ├── layout/
  │   ├── GET    /layout/umap/status              → routes_layout.py:umap_status
  │   ├── POST   /layout/umap/compute             → routes_layout.py:umap_compute (SSE)
  │   └── GET    /layout/umap/positions            → routes_layout.py:umap_positions
  │
  ├── skills/
  │   ├── GET    /skill/list                      → routes_skills.py:skill_list
  │   ├── GET    /skill/jobs                      → routes_skills.py:job_list
  │   ├── GET    /skill/job/{id}                  → routes_skills.py:job_status
  │   ├── POST   /skill/run                       → routes_skills.py:run_skill
  │   └── GET    /skill/stream/{id}               → routes_skills.py:stream_job (SSE)
  │
  └── watch/
      └── GET    /watch                           → routes_watch.py:watch_db (SSE)

  Total: 21 endpoints across 7 resources
```

---

## Database Schema (v3)

```
  Core Tables
  ═══════════

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

  Rich Content Tables (v3)
  ════════════════════════

  ┌──────────────────────────────┐      ┌──────────────────────────────┐
  │ entity_topics                │      │ snippets                     │
  ├──────────────────────────────┤      ├──────────────────────────────┤
  │ entity_id   TEXT    FK       │      │ id          INTEGER PK AUTO  │
  │ topic       TEXT             │      │ entity_id   TEXT    FK       │
  │ PK (entity_id, topic)       │      │ ref_id      TEXT    NULLABLE │
  └──────────────────────────────┘      │ ref_type    TEXT    NULLABLE │
                                        │ text        TEXT             │
  ┌──────────────────────────────┐      │ ordinal     INTEGER DEFAULT 0│
  │ research_interests           │      └──────────────────────────────┘
  ├──────────────────────────────┤
  │ entity_id   TEXT    FK       │      ┌──────────────────────────────┐
  │ interest    TEXT             │      │ sources                      │
  │ ordinal     INTEGER DEFAULT 0│      ├──────────────────────────────┤
  │ PK (entity_id, interest)    │      │ id           INTEGER PK AUTO │
  └──────────────────────────────┘      │ entity_id    TEXT    FK      │
                                        │ source_name  TEXT            │
  ┌──────────────────────────────┐      │ url          TEXT   NULLABLE │
  │ contact_info                 │      │ retrieved_at TEXT   NULLABLE │
  ├──────────────────────────────┤      └──────────────────────────────┘
  │ entity_id   TEXT    FK       │
  │ field       TEXT             │
  │ value       TEXT             │
  │ PK (entity_id, field)       │
  │ field values: email, phone,  │
  │   orcid, website, department,│
  │   title                      │
  └──────────────────────────────┘

  Support Tables
  ══════════════

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
    entities.type           — idx_entities_type
    entities.name           — idx_entities_name
    aliases.entity_id       — idx_aliases_entity
    relationships.source_id — idx_rels_source
    relationships.target_id — idx_rels_target
    relationships.rel_type  — idx_rels_type
    entity_topics.entity_id — idx_topics_entity
    entity_topics.topic     — idx_topics_topic
    snippets.entity_id      — idx_snippets_entity
    snippets.ref_id         — idx_snippets_ref
    research_interests      — idx_interests_entity
    sources.entity_id       — idx_sources_entity
    contact_info.entity_id  — idx_contact_entity
    chat_history.session_id — idx_chat_session

  Schema version:          3
  Journal mode:            WAL (concurrent reads)
  Foreign keys:            ON (CASCADE deletes)
```

---

## File Tree

```
APP/
├── config/default.yaml                 # Server, LLM, skills, UI config
├── pyproject.toml                      # Package metadata + dependencies
├── README.md                           # User-facing docs
├── kgx/
│   ├── __init__.py
│   ├── __main__.py                     # python -m kgx entry point
│   ├── cli.py                          # argparse CLI, uvicorn launcher
│   ├── config/
│   │   ├── __init__.py                 # re-exports load_config
│   │   └── loader.py                   # YAML → Pydantic models
│   ├── db/
│   │   ├── __init__.py                 # re-exports KnowledgeGraphDB
│   │   ├── schema.py                   # DDL v3, 11 tables, init_schema()
│   │   ├── queries.py                  # KnowledgeGraphDB class (all SQL)
│   │   │                               #   + graph_explore(), neighbors_explore(),
│   │   │                               #   degree_explore(), _descendant_ids()
│   │   └── tests/
│   │       └── test_db.py              # 40 tests for DB layer
│   ├── api/
│   │   ├── __init__.py                 # re-exports create_app
│   │   ├── app.py                      # FastAPI factory, router wiring
│   │   ├── routes_graph.py             # /api/graph, /api/types, /api/stats
│   │   ├── routes_entity.py            # /api/entity/* (+ rich content)
│   │   ├── routes_query.py             # /api/query, /api/mutate/*
│   │   ├── routes_export.py            # /api/export/json, neo4j, markdown
│   │   ├── routes_chat.py              # /api/chat, /api/chat/status
│   │   ├── routes_layout.py            # /api/layout/umap/* (SSE compute)
│   │   ├── routes_skills.py            # /api/skill/*
│   │   └── routes_watch.py             # /api/watch (SSE)
│   ├── llm/
│   │   ├── __init__.py                 # re-exports OllamaClient, ChatToSQL
│   │   ├── client.py                   # httpx wrapper for Ollama API
│   │   └── chat_sql.py                 # NL → SQL + fast-path schema answers
│   ├── layout/
│   │   ├── __init__.py
│   │   ├── embedder.py                 # Ollama nomic-embed-text embeddings
│   │   └── umap_layout.py             # UMAP 3D layout computation
│   ├── skills/
│   │   ├── __init__.py                 # re-exports SkillRegistry, SkillRunner
│   │   ├── registry.py                 # Auto-discover skills from filesystem
│   │   └── runner.py                   # Async subprocess execution
│   └── ui/
│       ├── index.html                  # App shell, header, SQL panel,
│       │                               #   force settings, presets, confirm
│       │                               #   dialog, search, global handlers
│       ├── lib/
│       │   └── 3d-force-graph.min.js   # Vendored (no CDN)
│       └── components/
│           ├── shared/
│           │   ├── theme.css           # CSS variables, dark theme
│           │   ├── event-bus.js        # Pub/sub event bus
│           │   └── api-client.js       # fetch() wrapper
│           ├── graph/
│           │   ├── graph.js            # 3D force graph + layouts + settings
│           │   │                       #   explore mode, community detection,
│           │   │                       #   filtered degree, weighted links
│           │   ├── graph.css
│           │   └── context-menu.js     # Right-click: detail, focus, orbit,
│           │                           #   highlight, expand, hide, research, copy
│           ├── sidebar/
│           │   ├── sidebar.js          # Entity browser + edge filters
│           │   │                       #   + SQL filters (localStorage)
│           │   │                       #   + chat:save-filter listener
│           │   └── sidebar.css
│           ├── detail/
│           │   ├── detail.js           # Entity detail: type-specific render
│           │   │                       #   topics, contacts, interests,
│           │   │                       #   snippets, snippets-about, sources,
│           │   │                       #   relationships with names, ↑↓ nav
│           │   └── detail.css
│           └── chat/
│               ├── chat.js             # NL chat panel: LLM queries,
│               │                       #   help guide, input history ↑↓,
│               │                       #   highlight/hide/save buttons,
│               │                       #   clickable result rows (orbit)
│               └── chat.css
```

---

## Changelog

| Date | Change |
|---|---|
| 2026-06-02 | Explore mode: server-side graph projection — removes stubs/publications, flattens tag hierarchy to field level, synthesizes COLLABORATOR edges from shared AUTHORED, rolls up person→tag via publications, prunes orphan nodes |
| 2026-06-02 | Community detection: client-side label propagation (max 20 iterations) that recomputes on edge filter changes, toggleable via header button |
| 2026-06-02 | Dynamic node sizing: filtered degree recomputes based on visible edges only |
| 2026-06-02 | Link thickness by weight: COLLABORATOR edges with more shared papers render thicker |
| 2026-06-02 | Edge type filters rebuilt from graph data (explore mode types: TAGGED, COLLABORATOR, ATTENDED, MENTIONED_IN, MEMBER_OF) instead of raw DB types |
| 2026-06-02 | All edge types visible by default (was: only AUTHORED) |
| 2026-06-02 | Highlight neighbors: right-click menu action + node:highlight-neighbors event |
| 2026-06-02 | Expand neighbors uses current graph edges (explore-aware) instead of raw DB API |
| 2026-06-02 | Simplified layouts: removed Hierarchical ↑→←, Radial Out/In (kept Force, Cluster, Timeline, UMAP, Hierarchical ↓) |
| 2026-06-02 | Detail panel: neighbors_explore() and degree_explore() for tag-hierarchy-aware counts (field tags include transitive BROADER descendants) |
| 2026-06-02 | Clusters toggle button in header |
| 2026-06-02 | nodeResolution(8) for GPU performance improvement |
| 2026-06-01 | v3 schema: entity_topics, snippets, research_interests, sources, contact_info |
| 2026-06-01 | Rich content in detail panel (type-specific rendering, snippets-about for persons) |
| 2026-06-01 | Arrow key navigation (↑↓) to cycle entities of same type in detail panel |
| 2026-06-01 | Force settings panel: draggable, per-type charges, edge styling, presets |
| 2026-06-01 | Profiled vs unprofiled person distinction (group field, separate force charges) |
| 2026-06-01 | Orbit pivot (right-click), expand neighbors overrides all filters |
| 2026-06-01 | Chat: fast-path schema answers, input history, filter/highlight/save actions |
| 2026-06-01 | Chat: clickable result rows orbit + select node in graph |
| 2026-06-01 | SQL panel (bottom-right) shows last query with copy button |
| 2026-06-01 | Chat → Sidebar filter bridge (save filter from chat results) |
| 2026-06-01 | Robust SQL parser: handles broken fences, bare SQL, single backtick |
| 2026-06-01 | TrackballControls: disabled damping/inertia (staticMoving) |
| 2026-06-01 | Layout router: UMAP status/compute/positions endpoints |
| 2026-05-31 | Initial architecture, API, and database diagrams generated from code scan |
