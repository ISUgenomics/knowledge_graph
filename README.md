# LangGraph-Orchestrated Skill System

A progressive build of a LangGraph skill plugin system, using local models via Ollama.
Each milestone introduces new LangGraph concepts before adding complexity.

---

## Setup

```bash
pip install -r requirements.txt

ollama pull qwen3-coder:30b
ollama serve
```

The code defaults to `qwen3-coder:30b` — a MoE model (30B total, 3B active per
token) with the most reliable tool calling of any local model. Runs well on 32GB+
Macs. Pass `--model <name>` to the runners to use a different model.

---

## Milestones

### M1 — Minimal ReAct Loop

**What you learn:** `StateGraph`, `add_messages` reducer, `conditional_edges`, `MemorySaver`

```bash
python learning/01_react_basics/react_agent.py
```

The agent calls two tools (`get_current_time`, `add_numbers`) in a loop until it has
an answer. The graph topology is printed as ASCII before the run.

Key concepts in `learning/01_react_basics/react_agent.py`:
- `AgentState` TypedDict with `add_messages` — new messages append, not overwrite
- `should_continue()` routing function — returns `"tools"` or `END`
- `graph.compile(checkpointer=MemorySaver())` — state persists across calls
- `app.get_state(config)` — inspect the full state after a run

---

### M2 — SkillState + Plugin Contract

**What you learn:** Extended state, reducers, the plugin interface

No runnable demo — this is the shared data layer used by M3+.

Files:
- `harness/skill_state.py` — `SkillState` TypedDict + `validate_plugin()`

`SkillState` fields:
```
task            — original user request (never changes)
phase           — current phase: gather | execute | verify | deliver
plan            — upfront plan (planreact strategy only)
messages        — full LLM conversation (add_messages reducer)
tool_results    — dict keyed by tool name
verify_failures — parsed FAIL lines from verify script
attempts        — retry counter
output_path     — path to the artifact produced
answer          — final answer returned to user
```

Plugin contract — what every `plugin.py` must export:
```python
PROMPTS  = {"gather": "...", "execute": "...", "deliver": "..."}
TOOLS    = [list_of_langchain_tool_functions]
VERIFY   = {"script": "run_all.sh", "max_attempts": 3, "parse_failures": callable}
STRATEGY = "react"   # optional: "react" | "act" | "planreact"
```

---

### M3 — Shared Skill Harness

**What you learn:** Multi-node conditional routing, failure injection, checkpointing

```bash
python learning/02_skill_harness/demo.py
```

Graph topology (shared by all skills):
```
[plan] → gather → execute ⇄ tools
                          ↓
                       verify
                      /      \
                (PASS)        (FAIL, retries left)
                   ↓                  ↓
                deliver          inject_failures → execute
                   ↓
                  END
```

`[plan]` node is only present when `STRATEGY = "planreact"`.

Key function: `build_skill_graph(plugin, model, strategy)` in `harness/skill_harness.py`.
Takes any plugin dict and returns a compiled LangGraph app.

Inspect the graph at any time:
```python
app = build_skill_graph(plugin)
app.get_graph().print_ascii()
```

---

### M4 — person-research Plugin

**What you learn:** Real `@tool` wrappers over shell scripts, end-to-end run

```bash
cd skills/person_research
python run.py "Andrew Severin"
python run.py "Andrew Severin" --institution "Iowa State University"
python run.py "Jane Doe" --model qwen3-coder:30b --thread my-run-1
```

The plugin wraps the existing shell scripts from `person-research/` as `@tool` functions:

| Tool | Script |
|------|--------|
| `classify_person` | `scripts/fetch_classify.sh` |
| `fetch_openalex` | `scripts/fetch_openalex.sh` |
| `fetch_pubmed` | `scripts/fetch_pubmed.sh` |
| `fetch_orcid` | `scripts/fetch_orcid.sh` |
| `fetch_webpage` | `scripts/fetch_webpage.sh` |
| `fetch_contact` | `scripts/fetch_contact.sh` |
| `scaffold_person` | `stubs/scaffold_person.sh` |
| `check_deliver` | `scripts/check_deliver.sh` |

Verify runs `run_all.sh <output_file>` and parses lines containing `FAIL`.
Failed checks are injected into the message context so the LLM knows what to fix.

Inspect state mid-run or after completion:
```python
snapshot = app.get_state({"configurable": {"thread_id": "my-run-1"}})
print(snapshot.values)
```

Resume an interrupted run by re-running with the same `--thread` value:
```bash
python run.py "Andrew Severin" --thread person-research-andrew-severin
```

---

### M5 — Pluggable Reasoning Strategy

**What you learn:** How strategy changes prompt behavior and graph topology

Three strategies are supported:

| Strategy | Behavior | Best for |
|----------|----------|----------|
| `react` (default) | LLM reasons step-by-step before each tool call | General purpose |
| `act` | LLM calls tools directly, no narrated reasoning | Simple tasks, token savings |
| `planreact` | Upfront plan node, then reason+act per step | Complex multi-step tasks |

Set in plugin:
```python
STRATEGY = "react"   # in plugin.py
```

Or override at runtime:
```python
app = build_skill_graph(plugin, strategy="act")
```

Compare strategies on the same task:
```bash
# react (default)
python skills/person_research/run.py "Andrew Severin"

# act — fewer tokens, faster, less robust
python skills/person_research/run.py "Andrew Severin" --strategy act

# planreact — adds plan node before gather
python skills/person_research/run.py "Andrew Severin" --strategy planreact
```

---

## Adding a New Skill

1. Create `skills/<skill_name>/plugin.py` exporting `PROMPTS`, `TOOLS`, `VERIFY`, `STRATEGY`
2. Wrap each shell script as a `@tool` function using `subprocess.run`
3. Point `VERIFY["script"]` at the skill's `run_all.sh`
4. Run it: `build_skill_graph(plugin).invoke({"task": "..."})`

The shell scripts are the stable tested layer. The plugin is just the bridge.

---

## File Structure

```
AgentPlugin/
  requirements.txt
  README.md
  design-notes/             ← conceptual design docs (01–09)
  harness/
    skill_state.py          ← M2: SkillState TypedDict + plugin contract
    skill_harness.py        ← M3+5: build_skill_graph() factory (shared by all skills)
  learning/
    01_react_basics/
      react_agent.py        ← M1: standalone ReAct loop with comments
    02_skill_harness/
      demo_plugin.py        ← M3: toy plugin (word count, no external deps)
      demo.py               ← M3: harness demo runner
  skills/
    person_research/        ← M4: person-research plugin
      plugin.py
      run.py
      scripts/
      stubs/
      unit_tests/
      people/               ← output (gitignored or kept locally)
    # future skills go here
```
