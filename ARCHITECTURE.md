# LangGraph Skill System — Architecture

## What Was Built

A LangGraph-orchestrated skill plugin system where:
- The **graph is the orchestrator** — phases, retries, and routing are explicit edges
- The **LLM is just a node** — it calls tools and generates text, nothing more
- Each **skill is a plugin** (PROMPTS + TOOLS + VERIFY) dropped into a shared harness
- Local models run via **Ollama** (`qwen3-coder:30b`)

---

## File Structure

```
src/
├── requirements.txt
├── README.md
├── ARCHITECTURE.md             ← this file
│
├── 01_react_basics/
│   └── react_agent.py          ← M1: teach LangGraph fundamentals
│
├── 02_skill_harness/
│   ├── skill_state.py          ← M2: SkillState + plugin contract spec
│   ├── skill_harness.py        ← M3+5: build_skill_graph() factory
│   ├── demo_plugin.py          ← M3: toy plugin (word count, no external deps)
│   └── demo.py                 ← M3: harness demo runner
│
└── 03_person_research/
    ├── plugin.py               ← M4: person-research plugin
    └── run.py                  ← M4: CLI runner
```

---

## M1 — Minimal ReAct Graph

The simplest possible LangGraph: one agent, two tools, one loop.

```
                  +----------------------------------+
                  |         AgentState               |
                  |  messages: Annotated[list,       |
                  |            add_messages] <-------+-- accumulates, never replaces
                  +----------------------------------+

  +-------------+
  |  START      |
  +------+------+
         |
         v
  +-------------+   tool_calls?   +-------------+
  |    agent    | --------------> |    tools    |
  |  (calls LLM)|                 | (ToolNode)  |
  +-------------+ <-------------- +-------------+
         |          always loop
         | no tool_calls
         v
  +-------------+
  |     END     |
  +-------------+

  Key concepts learned:
  - StateGraph, TypedDict, add_messages reducer
  - conditional_edges (should_continue)
  - MemorySaver checkpointing + thread_id
  - app.get_state(config) inspection
```

---

## M2 — SkillState

```
  SkillState (TypedDict)
  +----------------------------------------------------------+
  |  task          : str      <- never changes after start   |
  |  phase         : str      <- gather | execute | verify   |
  |                               | deliver                  |
  |  plan          : str      <- planreact only              |
  |                                                          |
  |  messages      : list     <- add_messages reducer        |
  |                               (appends, never replaces)  |
  |                                                          |
  |  tool_results  : dict     <- keyed by tool name          |
  |  output_path   : str      <- set when scaffold runs      |
  |                                                          |
  |  verify_failures: list    <- parsed FAIL lines           |
  |  attempts      : int      <- retry counter               |
  |                                                          |
  |  answer        : str      <- final user-facing response  |
  +----------------------------------------------------------+

  Reducer rule:
  - messages   -> append  (add_messages)
  - all others -> replace (last-write-wins)
```

---

## M3+5 — Full Skill Harness Graph

```
  +--------------------------------------------------------------+
  |                    build_skill_graph(plugin)                  |
  |                                                              |
  |  [plan] ---> gather <------------------------------+         |
  |  (planreact    |                                   |         |
  |   only)        | tool_calls?              loop back|         |
  |                v                          (phase=  |         |
  |           route_gather                    "gather")|         |
  |           /          \                            |         |
  |     tool_calls      no tool_calls                 |         |
  |         |                |                        |         |
  |         v                v                        |         |
  |      +------+        execute <--------------------+----+    |
  |      |tools |            |                        |    |    |
  |      |      +-- phase? --+  tool_calls?           |    |    |
  |      |      |               v                     |    |    |
  |      +------+          route_execute              |    |    |
  |                         /          \              |    |    |
  |                   tool_calls    no tool_calls      |    |    |
  |                       |              |             |    |    |
  |                       +---> tools <--+             |    |    |
  |                       (phase="execute",            |    |    |
  |                        loops back here)            |    |    |
  |                                                    |    |    |
  |                           v                        |    |    |
  |                         verify                     |    |    |
  |                        /       \                   |    |    |
  |                 no FAIL     FAIL + retries left     |    |    |
  |                   |               |                |    |    |
  |                   v               v                |    |    |
  |                deliver    inject_failures ---------+    |    |
  |                   |       (adds FAIL lines to messages) |    |
  |                   v                                     |    |
  |                 END      FAIL + max_attempts exceeded --+    |
  |                          (deliver with unresolved issues)    |
  +--------------------------------------------------------------+

  Key fix: gather originally had no tools edge — the LLM's tool calls
  were silently dropped. Now gather <-> tools loops until data is
  fully collected, then advances to execute.
```

---

## M4 — person-research Plugin (current)

```
  plugin.py exports:
  +--------------------------------------------------------------+
  |  PROMPTS = {                                                 |
  |    "gather":  "call research_person (1 composite tool)"      |
  |    "execute": "call build_and_save with role/summary/tags"   |
  |    "deliver": "summarize folder path, counts, tags"          |
  |  }                                                           |
  |                                                              |
  |  TOOLS = [                                                   |
  |    research_person  -> research_person_all() (parallel APIs) |
  |                        fetch_openalex (+ abstracts, topics)  |
  |                        fetch_pubmed   (+ abstracts, MeSH)    |
  |                        fetch_orcid                           |
  |                        discover_isu_profile_and_cv           |
  |    build_and_save   -> build_profile.py (deterministic)      |
  |                        writes folder: <slug>/<slug>.md       |
  |                        writes abstracts/<YYYY_slug>.md × N   |
  |    fetch_webpage    -> fetch_webpage.sh (curl + HTML clean)  |
  |  ]                                                           |
  |                                                              |
  |  VERIFY = {                                                  |
  |    "script":          run_all.sh <folder_or_file>            |
  |    "max_attempts":    2                                      |
  |    "parse_failures":  lines containing "FAIL"                |
  |  }                                                           |
  |                                                              |
  |  STRATEGY       = "act"                                      |
  |  PATH_TOOL      = "build_and_save"  <- sets output_path      |
  |  PATH_EXTRACTOR = parses "Created: <path>" from output       |
  +--------------------------------------------------------------+

  See 03_person_research/ARCHITECTURE.md for detailed diagrams
  of LLM vs Script boundaries, data flow, and vault structure.
```

---

## M4 — Typical Run Flow (current)

```
  python run.py "Amy Toth"

  [gather]  LLM calls 1 tool
    -> research_person("Amy Toth")
    <- (internally runs 4 API fetches in parallel):
       • fetch_openalex  → works + abstracts + topics + all_authors
       • fetch_pubmed    → papers + abstracts (efetch XML) + MeSH terms
       • fetch_orcid     → ORCID ID
       • discover_isu_profile_and_cv → profile pages + CV text
    <- returns compact brief (~500 tokens) to LLM
       full data cached in _research_cache (Python, not LLM context)
    (no more tool calls -> route to execute)

  [execute]  LLM calls 1 tool
    -> build_and_save("Amy Toth", role="faculty", summary="...",
                      tags="...", interests="...", department="...",
                      title="...", email="...", output_dir="people")
    <- (internally runs deterministic Python):
       • merge_and_dedup_papers() with unicode normalization
       • build_markdown()          → people/amy-toth/amy-toth.md
       • build_abstract_markdown() → people/amy-toth/abstracts/*.md × N
    <- "Created: people/amy-toth/amy-toth.md"
       ^ PATH_EXTRACTOR fires, output_path set

  [tools → route_after_tools]
    output_path is set → SHORT-CIRCUIT to verify (BP #17)
    (does NOT loop back to execute)

  [verify]  attempts=1
    runs: run_all.sh people/amy-toth/
    <- check_security:  PASS
    <- check_sections:  PASS
    <- check_links:     PASS
    <- check_abstracts: PASS  (new: validates abstract frontmatter)

  [deliver]  LLM summarizes
    Folder: people/amy-toth/, 9 papers, 9 abstracts, tags: ...
```

---

## M5 — Strategy Comparison

```
  STRATEGY = "react"     (default)
  ---------------------------------------------------------------
  gather -> [think before each tool call] -> execute -> ...
  Prompt suffix: "Think step by step before each tool call."
  Best for: general purpose, complex multi-tool decisions

  STRATEGY = "act"
  ---------------------------------------------------------------
  gather -> [call tools directly, no narration] -> execute -> ...
  Prompt suffix: "Act directly. Minimize prose."
  Best for: simple tasks, fewer tokens, faster runs

  STRATEGY = "planreact"
  ---------------------------------------------------------------
  plan -> gather -> execute -> ...
  plan_node added at entry, uses llm_base (no tools bound)
  Produces numbered steps stored in state["plan"]
  Injected into gather and execute prompts as context
  Best for: complex multi-step tasks where upfront structure helps

  Graph topology differs only for planreact (extra plan node).
  react vs act is purely a system prompt change.
```

---

## LLM Split: llm vs llm_base

```
  llm_base = get_llm(model)            # no tools
  llm      = llm_base.bind_tools(...)  # with tool schemas attached

  Used where:
  +---------------+------------------------------------------+
  | llm           | gather, execute  (need tool calling)     |
  | llm_base      | plan, deliver    (must NOT emit tool     |
  |               |  calls -- no tool edge from these nodes) |
  +---------------+------------------------------------------+
```

---

## Data Layer — vault.db

```
  ┌──────────────────────────────────────────────────────────────┐
  │  vault.db (SQLite)  — single source of truth                │
  │                                                              │
  │  Entity types:                                               │
  │    person, publication, signal, event, center, tag           │
  │                                                              │
  │  Relationship types:                                         │
  │    AUTHORED   person → publication                           │
  │    ATTENDED   person → event                                 │
  │    MENTIONED  person → signal                                │
  │    TAGGED     any    → tag                                   │
  │    COAUTHOR   person ↔ person                                │
  │    MEMBER_OF  person → center                                │
  │    BROADER    tag    → parent tag  (ontology hierarchy)      │
  │                                                              │
  │  Tables: entities, aliases, relationships,                   │
  │          entity_topics, snippets, research_interests,        │
  │          contact_info, sources                               │
  └──────────────────────────────────────────────────────────────┘

  Tag Ontology (BROADER hierarchy):
  ┌─────────────────────────────────────────────────────────┐
  │  domain (5)  →  field (36)  →  leaf (~700)              │
  │                                                         │
  │  biology ─── plant-science ─── soybean-genetics         │
  │         ├── genomics ──────── barley-genetics            │
  │         └── agriculture ───── crop-yield                 │
  │                                                         │
  │  computing ── ai ──────────── adversarial-robustness    │
  │          ├── machine-learning ── reinforcement-learning  │
  │          └── nlp ──────────── text-analysis              │
  └─────────────────────────────────────────────────────────┘

  Key queries:
    db.get_ancestors("soybean-genetics")  → [plant-science, biology]
    db.get_subtree_entities("plant-science", "person")
      → all persons tagged plant-science or any child tag
```

---

## Key Bugs Fixed

| Bug | Symptom | Fix |
|-----|---------|-----|
| No tools edge from gather | LLM hallucinated entire answer, 0 tool calls | Added `gather <-> tools` loop with `route_gather` |
| `tools` always routed to execute | gather tool calls fired but results went to wrong phase | `route_after_tools` checks `state["phase"]` |
| No `write_file` tool | verify always found unfilled FILL markers, 3 retries | Added `write_file` tool (later replaced by `build_and_save`) |
| `output_path` hardcoded | verify ran against wrong file | `PATH_TOOL`/`PATH_EXTRACTOR` extracts path from scaffold result |
| `verify` with empty `output_path` | silently passed (no "FAIL" in usage error output) | Explicit FAIL returned when `output_path` is empty |
| `deliver` used tool-bound LLM | could emit tool calls with no execution edge | `deliver_node` uses `llm_base` |
| `plan_node` used tool-bound LLM | wasted tokens on tool calls during planning | `plan_node` uses `llm_base` |
| Dead `route_verify` function | misleading comments, confused the codebase | Removed |
| execute→tools→execute cycle (BP #17) | LLM re-called `build_and_save` in infinite loop | `route_after_tools` short-circuits to verify when `output_path` set |
| Unicode dash dedup failure (BP #18) | Duplicate papers (OpenAlex `‐` vs PubMed `-`) | `_norm()` normalizes unicode dashes to ASCII in dedup key |
