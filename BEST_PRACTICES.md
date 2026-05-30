# Skill Harness Best Practices

Lessons learned building the person-research plugin on the LangGraph skill harness. These should inform the skill builder for future skills.

## 1. Consolidate gather tools into one parallel call

**Problem**: Multiple small tools (fetch_openalex, fetch_pubmed, fetch_orcid, etc.) require the LLM to decide which to call, in what order, and how to handle failures at each step. Each decision is an LLM round-trip that can go wrong.

**Fix**: One composite tool (`research_person`) that runs all data sources in parallel via Python threads and returns combined structured text. Gather phase drops from 10+ LLM iterations to 1-2.

**Rule**: If your gather phase has 3+ independent data sources, combine them into a single tool with internal parallelism.

## 2. Never let the LLM construct URLs

**Problem**: Local LLMs (qwen3-coder, etc.) will fabricate URLs — especially Google search URLs — that return nothing useful. The model then loops, appending more keywords to the failing URL.

**Fix**: Tools construct URLs internally from structured parameters (name, institution). The LLM passes `name="Andrew Severin"`, not `url="https://google.com/search?q=..."`.

**Rule**: If a tool takes a URL parameter, it should be optional or only accept URLs returned by other tools. Never rely on the LLM to construct a valid URL from scratch.

## 3. Block known-bad inputs at the tool level

**Problem**: Prompt instructions like "do NOT use Google URLs" are routinely ignored by local models. The model will retry the same bad pattern indefinitely.

**Fix**: Validate inputs inside the tool function. Return an immediate refusal with a concrete alternative. Don't rely on the LLM reading error messages — after the first refusal, make subsequent refusals terse to avoid the model treating each error as "new information" to act on.

**Rule**: If you can enumerate bad inputs (blocked domains, malformed args), reject them in the tool code, not in the prompt.

## 4. Guard every loop with a hard iteration cap

**Problem**: The gather→tools→gather cycle has no natural termination if the LLM keeps calling tools. Local models are especially prone to infinite loops.

**Fix**: Track `gather_iterations` in state. At the soft limit, inject "stop calling tools" into the prompt. At the hard limit, the router forces advancement to execute regardless.

**Rule**: Every cycle in the graph needs a counter and a cap. Default: 5 for gather, 3 for verify retries. Make it configurable via the plugin dict (`MAX_GATHER_ITERATIONS`).

## 5. Deduplicate tool calls within a batch

**Problem**: Local models sometimes emit the same tool call 2-4x in a single response. Without dedup, each runs independently — multiplying latency and API calls.

**Fix**: In `tool_node`, hash each call by `name + sorted(args)`. Execute the first, return "(duplicate — skipped)" for repeats. Each still gets a unique `ToolMessage` with the correct `tool_call_id` so LangGraph's 1:1 correspondence is satisfied.

**Rule**: Always deduplicate tool calls in the harness. This is a model-agnostic defense.

## 6. Use authoritative API data, not LLM inference

**Problem**: The LLM inferred "Plant Pathology department" from paper topics (soybean cyst nematode). The actual department is different. LLMs hallucinate institutional details.

**Fix**: OpenAlex returns `last_known_institutions` with the real institution name and type. The prompt says "Use the institution from OpenAlex — do NOT guess the department from paper topics."

**Rule**: For factual fields (institution, department, ORCID, paper counts), always source from structured APIs. Put explicit instructions in the execute prompt about which source to use for which field.

## 7. Separate orchestration scripts from data scripts

**Problem**: The original skill had orchestration scripts (`plan_context_load.sh`, `profile_steps.sh`) mixed with data-fetching scripts. When LangGraph took over orchestration, these became dead code.

**Fix**: Only copy data-fetching scripts into the plugin. Orchestration is the harness's job.

**Rule**: Scripts in the plugin should be pure functions — take inputs, return data. No workflow logic, no step sequencing, no LLM calls inside scripts.

## 8. Don't call a second LLM from inside a tool

**Problem**: `fetch_classify.sh` called Ollama (qwen2.5-coder:32b, a coding model) to classify a person. `fetch_webpage.sh` called Ollama to extract fields. These are redundant — the orchestrating LLM already does this work.

**Fix**: Tools fetch raw data. The orchestrating LLM handles all reasoning, classification, and extraction. Eliminated 2 LLM calls per run + removed wrong-model-for-task issue.

**Rule**: Tools should be deterministic data fetchers. If you need LLM reasoning on tool output, let the orchestrating LLM do it — that's what it's there for.

## 9. Fail gracefully with structured output

**Problem**: When APIs return nothing, scripts would output freeform text like "status: not found" that the LLM might misinterpret.

**Fix**: Every tool returns structured sections with clear headers. Empty results get explicit labels: `(author not found)`, `(no results for: query)`. The LLM can parse these reliably.

**Rule**: Tool output should be parseable without LLM reasoning. Use consistent formatting: `key: value`, section headers, and explicit absence markers.

## 10. Webpage fetching is supplementary, not primary

**Problem**: Webpage fetching is unreliable — CAPTCHAs, anti-bot walls, JavaScript-rendered content, inconsistent HTML structure. Making it a primary data source causes cascading failures.

**Fix**: APIs (OpenAlex, PubMed, ORCID) are the primary data sources. Webpage fetch only runs if the APIs returned a known-good URL, and only to supplement missing contact details.

**Rule**: Design the skill to produce a complete output from structured APIs alone. Webpage data is a bonus, not a requirement.

## 11. Pre-fill structural fields in templates — don't trust the LLM to preserve them

**Problem**: The scaffold template had `tags: <!-- FILL -->`, `categories: <!-- FILL -->`, and `type: person` in the YAML frontmatter. The LLM consistently dropped or mangled these fields when writing the full file, causing every verify attempt to fail on the same frontmatter checks.

**Fix**: Pre-fill structural fields that have known values: `tags: []`, `categories: [person, academic]`, `type: person`, `subtype: academic`. The LLM only needs to *add* tag keywords to an existing list, not reconstruct the YAML structure from a FILL marker. The execute prompt now has explicit frontmatter rules.

**Rule**: Any template field that has a deterministic or default value should be pre-filled, not left as a FILL marker. Reserve FILL markers for fields that genuinely require gathered data.

## 12. Test external API response shapes — they change between versions

**Problem**: The ROR API v2 changed `links` from a list of strings to a list of dicts (`{"type": "website", "value": "https://..."}`). The code did `links[0]` expecting a string, got a dict, and the entire profile/CV discovery pipeline silently failed — no profile pages found, no CV extracted.

**Fix**: Handle both v1 (string) and v2 (dict) response shapes. More importantly: test each API integration standalone with real data before wiring it into the pipeline.

**Rule**: When integrating external APIs, always validate the actual response shape at runtime. Type-check fields (`isinstance(link, dict)` vs `str`) rather than assuming a structure. Add a standalone test mode for each API function.

## 13. Use the best available local tool for data extraction

**Problem**: PDF text extraction fell back to a crude byte parser (regex over raw PDF bytes) when `pdftotext` wasn't installed. The output was garbage — binary fragments instead of readable text. The CV was successfully downloaded but completely unusable.

**Fix**: Check for PyMuPDF (`fitz`) first — it was already installed in the conda env and produces clean text from any PDF. Fall through to `pdftotext` CLI, then give up (no crude fallback that produces garbage).

**Rule**: Before writing a custom parser/extractor, check what's already installed (`pip list | grep pdf`). A bad fallback that produces garbage is worse than no fallback — the LLM will try to use the garbage output. If extraction fails cleanly, the LLM knows to skip it.

## 14. Move deterministic data transformation to Python — use the LLM only for reasoning

**Problem**: The LLM was generating the entire markdown file including all publications. It consistently truncated the publication list (5 out of 18+ papers), reformatted citations inconsistently, and dropped frontmatter fields. Stronger prompts and embedded templates didn't fix it — the LLM simply can't reliably reproduce 25 structured citations it was shown in context.

**Fix**: Split the work by what each component is good at:
- **LLM provides only reasoning fields** (~200 tokens): role, summary, tags, interests
- **Python handles all deterministic work**: merging papers from multiple APIs, deduplicating by normalized title, formatting as MLA citations, assembling the complete markdown with frontmatter

A module-level cache (`_research_cache`) passes structured data between the `research_person` tool (gather) and `build_and_save` tool (execute) without sending it through the LLM. Result: ~90% token reduction, 100% of papers included, perfectly consistent output format every time.

**Rule**: If a task involves transforming structured data into a structured output (formatting citations, building tables, assembling templates), do it in Python. The LLM should only touch fields that require judgment or synthesis. Never send large structured datasets through the LLM just to get them back in a different format.

## 15. Use a module-level cache to share data between tools without passing through the LLM

**Problem**: The gather tool collected 25+ papers from APIs. To get them into the output file, the data had to travel through the LLM context — which truncated, reformatted, and hallucinated over it.

**Fix**: Store the full structured data in a Python dict (`_research_cache`) at module scope. The gather tool writes to it; the build tool reads from it. The LLM never sees the raw paper data — only a compact brief (~500 tokens) with enough context to determine role, write a summary, and pick tags.

**Rule**: When Tool A gathers data that Tool B needs to process, pass it through Python state, not through the LLM. The LLM should receive only what it needs for reasoning — a brief, not a dataset.

## 16. Count what you verify — match the regex to the actual output format

**Problem**: The verify script counted publications by matching `### ` headings (old format). After switching to MLA citations, the regex matched 0 papers despite 19 being present. The verify step failed every run, wasting retry attempts.

**Fix**: The regex must match the actual output of the formatter. MLA format produces `"Title." *Journal*, Year.` — the regex was looking for `"` then `.` but the actual order is `.` then `"`. A one-character swap fixed it. Both old (`**Year:**`) and new (MLA) patterns are matched for backward compatibility.

**Rule**: When you change the output format, update the verify script regex in the same commit. Test the regex against actual output before considering the format change done. A verify script that can't parse the output it's checking is worse than no verify — it creates false failures that waste LLM retries.

## 17. Short-circuit the execute→tools→execute loop when output is produced

**Problem**: After `execute_node` calls `build_and_save` and `tool_node` runs it successfully, `route_after_tools` returns `"execute"` (the current phase). This sends the conversation back to `execute_node`, which re-invokes the LLM. Local LLMs see the tool result and call `build_and_save` again with identical args — creating an infinite loop. The dedup logic only catches duplicates *within a single LLM response*, not across separate execute→tools→execute cycles.

**Fix**: In `route_after_tools`, check if the execute phase produced an `output_path`. If so, skip back to `verify` directly instead of returning to `execute_node`. The LLM already got what it needed — there's no reason to ask it again.

```python
if phase == "execute" and state.get("output_path"):
    return "verify"
```

**Rule**: When a tool in the execute phase produces the final artifact (output_path is set), route directly to verify. Never send the LLM back to execute after a successful build — it will try to build again. This is model-agnostic: even capable models occasionally re-call tools when shown a success result.

## 18. Normalize unicode in dedup keys — APIs return inconsistent encodings

**Problem**: OpenAlex and PubMed return the same paper title with different unicode characters. OpenAlex uses unicode en-dashes (`\u2010`–`\u2015`) while PubMed uses ASCII hyphens (`-`). The title dedup normalized to lowercase but didn't normalize dashes, so "Development of High‐Throughput..." and "Development of High-Throughput..." were treated as different papers. This produced duplicate entries in the vault.

**Fix**: Add unicode dash normalization to the `_norm()` function used for dedup keys:

```python
t = re.sub(r"[\u2010-\u2015\u2212\uFE58\uFE63\uFF0D]", "-", t)
```

**Rule**: When deduplicating data from multiple APIs, normalize all unicode variants (dashes, quotes, whitespace, accents) to ASCII equivalents in the dedup key. Different APIs have different encoding conventions for the same content.

## 19. Detect soft 404s — validate page content, not just HTTP status

**Problem**: Many ISU department sites return HTTP 200 for nonexistent `/people/<slug>` URLs. The page renders a generic template with no actual person data. Treating any 200 response as a valid profile page polluted the brief with irrelevant content and led the LLM to fabricate department/title from template boilerplate.

**Fix**: After fetching a candidate profile URL, validate that the HTML actually contains the person's last name. A 200 response with `len(html) > 200` but no mention of the person is a soft 404 — discard it.

```python
if html and len(html) > 200 and last_name in html.lower():
    # Valid profile page
```

**Rule**: When scraping sites that don't return proper 404 status codes, validate the response body contains expected content (person's name, a key identifier) before treating it as a hit. This is common on CMS-driven university sites.

## 20. Rank data sources by authority — use the most reliable source for each field

**Problem**: The skill initially treated all data sources equally. OpenAlex might say "Ecology, Evolution & Organismal Biology" (the department associated with publications), while the person actually works in a different unit. Profile page text might contain multiple department names from collaborators listed on the page.

**Fix**: Establish a strict priority order per field type:
- **Title/Department/Email**: LDAP (Active Directory) > Department profile page > Staff listing > OpenAlex
- **Publications**: OpenAlex > PubMed (merge and dedup)
- **ORCID**: OpenAlex `orcid` field > ORCID API search

The brief presents LDAP data first with explicit labels (`ISU Directory Title:`, `ISU Directory Department:`) so the LLM knows which source is authoritative.

**Rule**: When multiple sources can provide the same field, document the priority order in both the code and the prompt. Label data by source in the brief so the LLM can resolve conflicts correctly.

## 21. Disambiguate fallback searches — validate identity, not just name match

**Problem**: When OpenAlex couldn't find an author with the institution filter, the fallback searched without it. This returned authors at other institutions with the same name. The LLM used the wrong person's publication record without noticing.

**Fix**: The fallback search validates that at least one of the candidate's `last_known_institutions` matches the target institution before accepting the result:

```python
matched = [r for r in results if any(
    inst_lower in (i.get("display_name", "").lower())
    for i in (r.get("last_known_institutions") or [])
)]
```

**Rule**: When relaxing a search filter for better recall, add a validation step that checks the critical constraint (institution, affiliation) against the results. A wrong-person match is worse than no match.

## 22. Provide fallback discovery paths for different organizational structures

**Problem**: Not all ISU units have individual `/people/<slug>` profile pages. Facilities like the Protein Facility or Biotech center list staff on a shared page (`/staff/`). People at these units were invisible to profile discovery.

**Fix**: Maintain a list of known staff listing page URLs (`ISU_STAFF_LISTINGS`). When individual profile discovery fails, search these pages for the person's name and extract title/position from HTML patterns (Elementor widgets, generic name-near-title patterns).

**Rule**: Institutional websites have heterogeneous structures. Design discovery with multiple fallback strategies: individual profile pages → shared staff listings → directory searches. Each layer catches people the previous layer missed.

## 23. Generate per-record files for Obsidian graph connectivity

**Problem**: A single monolithic profile file with inline citations doesn't leverage Obsidian's graph view. Coauthors are just text strings — no connections form between people in the vault.

**Fix**: Generate individual abstract files (`abstracts/YYYY_title-slug.md`) for each paper, each containing:
- YAML frontmatter with all authors as wiki-links (`[[first-last]]`)
- Topic/MeSH tags for cross-linking
- DOI and PMID links

The main profile wiki-links to each abstract. When two people share a paper, both profiles link to the same abstract file (by convention), and the abstract links back to both — creating graph edges automatically.

**Rule**: When building for a knowledge graph tool (Obsidian, Roam, Logseq), decompose output into atomic linked files rather than monolithic documents. Each entity (person, paper, project) should be its own node with explicit links to related nodes.

## 24. Encode role classification rules explicitly — don't rely on LLM world knowledge

**Problem**: The LLM classified a Facility Manager as "faculty" because they had publications and worked at a university. "Faculty" has a specific meaning in academia (professorial rank, runs a lab, teaches courses) that general-purpose LLMs don't reliably distinguish from "works at a university."

**Fix**: The execute prompt includes explicit classification rules with examples:
- `faculty` — only professorial titles (Professor, Associate/Assistant/Distinguished/Emeritus Professor)
- `staff` — any other employee, with strong indicators listed (Manager, Coordinator, Specialist, works in a Facility/Core/Center)
- `student` — Graduate Student, PhD Candidate, Postdoc
- Default to `staff` when uncertain (not `faculty`)

LDAP `employeeType` and `title` fields provide the primary signal, with the prompt directing the LLM to use these over its own inference.

**Rule**: When the LLM must classify into domain-specific categories, provide exhaustive rules with examples in the prompt — not just category names. Include the default/fallback category explicitly. Domain terms that overlap with common English ("faculty" = "people at a university" vs. "faculty" = "professorial rank") are especially prone to misclassification.

---

## Architectural Principle: Minimize LLM Surface Area

The single most impactful design decision for a LangGraph skill is **how much work you give the LLM vs. how much you handle in code**. This section captures the meta-pattern behind rules 1-24.

### Prompt-driven vs. tool-driven skills

A skill generator (or a first-draft skill) naturally produces a **prompt-driven** design: a long SKILL.md that tells the LLM how to research, fetch, classify, merge, format, and output — step by step. The LLM orchestrates everything. This has predictable failure modes:

| Failure | Why it happens |
|---|---|
| Truncated output | LLM drops items from long lists (papers, coauthors) to fit its generation budget |
| Inconsistent formatting | Each run produces slightly different markdown structure |
| Hallucinated facts | LLM fills gaps with plausible-sounding but wrong data (departments from paper topics, fabricated DOIs) |
| High token cost | LLM reads raw web pages (2,000-15,000 tokens each) just to extract 5 fields |
| Fragile orchestration | Each step depends on the LLM correctly deciding what to do next |

A **tool-driven** design inverts this. Python does the data work; the LLM provides only judgment:

```
┌─────────────────────────────────────────────────┐
│  Prompt-driven (original)                       │
│                                                 │
│  LLM → fetch → read page → extract → format →  │
│        merge → deduplicate → build markdown →   │
│        fill template → verify → fix → deliver   │
│                                                 │
│  LLM touches: everything                       │
│  Token cost: ~5,000-15,000 per run              │
│  Papers: 3-5 (template-limited)                 │
│  Consistency: variable                          │
└─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────┐
│  Tool-driven (current)                          │
│                                                 │
│  Python → parallel API calls → structured data  │
│  LLM   → reads 500-token brief → outputs 6-8   │
│           reasoning fields (role, summary, tags) │
│  Python → merge, dedup, format, build markdown  │
│                                                 │
│  LLM touches: role, summary, tags, interests    │
│  Token cost: ~800-1,500 per run                 │
│  Papers: 13-25 (API-limited, not LLM-limited)   │
│  Consistency: deterministic                     │
└─────────────────────────────────────────────────┘
```

### The design question for every new skill

When designing a skill, classify each piece of work:

1. **Data fetching** → Python (parallel threads, structured APIs, retries, timeout handling)
2. **Data transformation** → Python (merging, deduplication, formatting, template assembly)
3. **Judgment calls** → LLM (classification, summarization, tagging, disambiguation)
4. **Orchestration** → LangGraph harness (state machine, phase transitions, retry loops)

If a piece of work doesn't require *judgment*, it shouldn't go through the LLM. The test: "Could a Python function do this deterministically given the right inputs?" If yes, write the function.

### How LangGraph contributes vs. the code architecture

LangGraph provides valuable scaffolding (~20-30% of the improvement):
- **State machine**: gather → execute → verify → deliver with automatic phase transitions
- **Verify-retry loop**: run validation scripts and retry on failure (configurable attempts)
- **Checkpointing**: resume interrupted runs via `thread_id`
- **Strategy selection**: act/react/planreact reasoning modes per skill

But the dominant improvement (~70-80%) comes from the code architecture:
- **Structured data pipeline**: Python hits APIs and returns dicts, not raw web pages for the LLM to parse
- **Deterministic builder**: Python assembles the final artifact from structured data + LLM reasoning fields
- **Module-level cache**: large datasets pass between tools through Python state, never through LLM context
- **Domain-specific hardcoded knowledge**: institutional URL patterns, LDAP integration, soft-404 detection — things that can't be reliably encoded in a prompt

### Applying this to new skills

When building a new skill for the harness:

1. **Start by listing every output field.** For each, decide: is the value deterministic given the right API data, or does it require LLM reasoning?
2. **Build the data pipeline first** (`scripts/` directory). Fetch from APIs, return structured dicts. Test standalone.
3. **Build the deterministic builder** — takes structured data + a few LLM-provided fields, produces the final artifact. Test standalone.
4. **Write the plugin last** — define tools that wrap the pipeline and builder. The gather prompt should say "call this one tool." The execute prompt should list only the reasoning fields the LLM must provide.
5. **The LLM's brief should be ~500 tokens** — enough context to reason, not a data dump. If the brief is >1,000 tokens, you're probably sending data the LLM doesn't need.

---

## When the LLM Earns Its Keep (and When a Bash Pipeline Is Enough)

If a well-designed skill has the LLM making straight-line tool calls with no branching, why not just chain the Python scripts in bash?

```bash
python research_person.py "Dennis Lavrov" > /tmp/data.json
python build_profile.py --data /tmp/data.json --output people/
bash run_all.sh people/dennis-lavrov/dennis-lavrov.md
```

For person-research as it exists today, this would handle ~85% of runs. The LLM's contribution is 6 reasoning fields (role, summary, tags, interests, department, title). If you hardcoded role classification rules and used OpenAlex topics as tags, you could eliminate the LLM entirely.

**That's not a problem — it's the goal.** A skill where the LLM is almost optional means you've successfully pushed work into deterministic code. The question is: what does the LLM add that a pipeline can't?

### Where the LLM earns its keep

1. **Ambiguous inputs.** The user says "look up Lavrov at ISU" — partial name, unclear institution. The LLM disambiguates, asks clarifying questions, handles "did you mean..." A bash pipeline just fails or picks wrong.

2. **Judgment that resists rules.** Role classification is rule-based for 90% of cases. The 10% edge cases (adjunct who's also a facility director, emeritus with an active lab, postdoc with a courtesy title) need reasoning. Summaries and tags genuinely benefit from reading a brief and synthesizing — a rule-based tagger is noticeably worse.

3. **Error recovery with context.** When verify fails, the LLM reads the failure message, understands what's wrong, and fixes it. A bash pipeline needs hand-coded fix logic for every failure mode.

4. **Conversation.** The user says "actually make them faculty, not staff" or "add a note about their NSF grant." The LLM adjusts. A pipeline produces output — take it or rerun.

5. **Composition.** Inside a larger agent session, the LLM can decide to research a person as part of another task. A bash pipeline is standalone and can't be invoked mid-conversation.

### The spectrum

Skills fall on a spectrum of how much LLM reasoning they need:

```
Mostly deterministic          Mostly reasoning
◄─────────────────────────────────────────────►
person-research    code-review    debugging    creative writing
(6 LLM fields)    (judgment on    (exploratory  (nearly all
                   every hunk)    search)       LLM output)
```

Skills on the left benefit most from the "minimize LLM surface area" principle — push everything into code, use the LLM for the thin reasoning layer. Skills on the right inherently need more LLM involvement; the harness still helps with structure (phases, retry, verify) but the LLM is doing the real work.

### The design framework

**Start with a bash pipeline. Add the LLM only where deterministic logic can't handle the variance.** Specifically:

1. Build the data pipeline as standalone Python scripts. Test them without any LLM.
2. Build the output assembler as a standalone Python function. Test it with hardcoded inputs.
3. Identify which fields genuinely need reasoning — these become the LLM's job.
4. If the list of reasoning fields is empty, you don't need a LangGraph skill — ship the bash pipeline.
5. If the list is small (3-8 fields), use `act` strategy with one gather tool and one build tool.
6. If the list is large or the reasoning is exploratory, use `react` or `planreact`.

If you find the LLM doing straight-line tool calls with no judgment, that's a sign you've succeeded at the architecture — not that you chose the wrong tool. The LLM is there for the edge cases, the ambiguity, and the conversation — the parts that make a skill usable by a human instead of just runnable by a cron job.

---

## Choosing a Reasoning Strategy: Act vs ReAct vs PlanReAct

The harness supports three strategies. Picking the right one affects token cost, latency, and reliability.

### Act (default for most skills)

The LLM calls tools without explicit reasoning steps. Use when:
- The tool sequence is fixed: gather → one call → execute → one call → done
- Tool selection is obvious (1-2 tools per phase, no branching)
- The LLM brief contains everything needed — no conditional logic

**Example**: person-research. Every run follows the same path: `research_person` → read brief → `build_and_save`. There's nothing to reason about.

**Cost**: Lowest. No reasoning tokens between tool calls.

### ReAct (Reasoning + Acting)

The LLM produces an explicit reasoning step before each action. Use when:
- **Tool selection depends on prior results.** The gather phase returns data that determines *which* tools to call next (e.g., "person has a GitHub profile → call `fetch_repos`; person has patents → call `fetch_patents`"). The LLM must reason about what it learned before acting.
- **The search space is exploratory.** A debugging skill, literature review, or root-cause analysis where the next step genuinely depends on what you found. The tool sequence can't be prescribed in advance.
- **Error recovery requires diagnosis.** A tool fails and there are multiple alternative paths (different API, relaxed filters, ask the user). The LLM needs to reason about *why* it failed before picking the next action.
- **Multiple tools with overlapping capabilities.** The skill exposes 5+ tools and the LLM must choose the right one based on context. Explicit reasoning reduces wrong-tool calls — especially with local models.

**Cost**: ~30-50% more tokens per iteration (the reasoning text adds up). Worth it when wrong tool choices waste even more tokens via retries.

### PlanReAct

The LLM writes a full plan before executing any tools, then follows it with ReAct-style reasoning. Use when:
- The task has many interdependent steps that benefit from upfront planning
- The skill is complex enough that the LLM loses track of what it's doing mid-execution
- You need the plan as an auditable artifact (e.g., the user reviews the plan before execution)

**Cost**: Highest. Plan generation + per-step reasoning. Only justified for complex multi-phase skills.

### The heuristic

If you can draw the tool-call sequence as a **straight line** (or a simple fork), use `act`. If it's a **tree** where the LLM must navigate based on results, use `react`. If it's a **graph** with interdependencies that need upfront coordination, use `planreact`.

Most well-designed skills should land on `act` — because if you've followed the principle of minimizing LLM surface area, you've already moved the branching logic into Python tools. The tool returns structured data; the LLM just calls the next tool. ReAct is a signal that your tools might not be consolidated enough, or that the problem genuinely requires exploration.

---

## 25. When scraping fails, hard stop — no retries, no header rotation

**Problem**: When a URL returns a bot challenge (reCAPTCHA, Cloudflare), the natural instinct is to retry with different headers, add delays, or rotate user-agents. This wastes time, risks IP blocks, and never works against real bot detection.

**Fix**: `fetch_with_fallback.py` checks for bot markers in the response body (recaptcha, cloudflare, "checking your browser", etc.). On detection, it returns a hard stop with instructions for the user to download the page manually:

```python
BOT_MARKERS = ["recaptcha", "cloudflare", "challenge-platform", ...]

for marker in BOT_MARKERS:
    if marker in body_lower:
        return _blocked(url, f"Bot challenge detected ({marker})")
```

The blocked response includes download instructions (`--folder /path/to/folder`) so the user can provide the content locally.

**Rule**: When a fetch is blocked by bot detection, stop immediately. Return a clear message with the URL and instructions for manual download. Never retry, rotate headers, or attempt to bypass — it wastes tokens and risks the IP.

## 26. Handle HTTP content encoding — urllib doesn't auto-decompress

**Problem**: `urllib.request.urlopen()` returns raw bytes including gzip-compressed content. Calling `.read().decode("utf-8")` on gzip data produces garbled binary strings. The LLM then tries to parse garbage, wasting tokens and producing nonsense output.

**Fix**: Check the `Content-Encoding` response header and decompress before decoding:

```python
raw = resp.read()
encoding = resp.headers.get("Content-Encoding", "")
if encoding == "gzip":
    import gzip
    raw = gzip.decompress(raw)
elif encoding == "deflate":
    import zlib
    raw = zlib.decompress(raw, -zlib.MAX_WBITS)
body = raw.decode("utf-8", errors="replace")
```

Also send `Accept-Encoding: gzip, deflate` in the request headers so the server knows compression is supported.

**Rule**: Any URL-fetching code using `urllib` must handle gzip/deflate decompression. This is easy to miss because `requests` does it automatically but `urllib` does not. Test fetch code against real URLs before integrating.

## 27. Rebuild the LangGraph app periodically in batch mode

**Problem**: LangGraph's in-memory checkpointer accumulates message histories across all thread runs within the same `app` object. After ~5 articles in batch mode with a 30B local model, hundreds of messages in RAM cause Ollama inference to slow and eventually stall. The model appears frozen but is actually processing an enormous context.

**Fix**: Rebuild the graph every N items to flush accumulated state:

```python
for i, url in enumerate(urls):
    if i % 5 == 0:
        app = build_skill_graph(plugin, model=args.model, strategy=args.strategy)
    run_one_signal(url, app, plugin_module, args)
```

Also clear the module-level cache between runs (`_signal_cache.clear()`) and use a unique `thread_id` per item to avoid cross-contamination.

**Rule**: In batch mode, rebuild the LangGraph app every 5-10 items. Use unique thread IDs per item. Clear module-level caches between runs. This prevents state accumulation from degrading performance with local models.

## 28. Generate cross-skill .tsv files for pipeline composition

**Problem**: Each skill discovers people (signal articles mention researchers, events have attendees, centers have members). Without a standard handoff format, the user must manually extract names and feed them to person-research.

**Fix**: Each non-person skill generates a .tsv file alongside its main output:
- `signals/<slug>-people.tsv` — people mentioned in a news article
- `centers/<slug>-members.tsv` — center members and leadership
- `events/<slug>/attendees.tsv` — event attendees with roles

Format: `name\tdepartment\trole` (tab-separated, one per line). These feed directly into `person-research --input`.

**Rule**: When a skill discovers entities that another skill can process, emit a standard .tsv file that the downstream skill accepts as `--input`. This enables pipeline composition: `signal-capture → person-research`, `event-research → person-research`.

## 29. Use real-world dates, not creation dates — follow the date convention

**Problem**: Obsidian notes had inconsistent date fields. Some used `created:` (ambiguous — when was the note created vs. when did the event happen?), others used `date:` without clarity on whether it meant the real-world event or the indexing time.

**Fix**: Strict convention across all skills:
- `date:` / `published:` / `founded:` — real-world dates (when it happened, for timeline visualization)
- `updated:` — last time the profile was refreshed
- `_indexed:` — when the skill created or updated the note (internal, underscore prefix)
- **Never use `created:`** — it's ambiguous

**Rule**: Every note type must use the date convention. Real-world dates go in unprefixed fields for Obsidian timeline plugins. Internal metadata gets an underscore prefix. Document which date field each skill type uses.

## 30. Use consistent tag resolution across all skills

**Problem**: Without centralized tag management, each skill invents its own tags. "machine-learning", "ML", "machine learning", and "artificial-intelligence/machine-learning" all refer to the same concept but create disconnected graph nodes in Obsidian.

**Fix**: All skills use `tag_resolver.py` which fuzzy-matches candidate tags against `vault/tags/tag-registry.md` (>80% similarity threshold). If a match exists, the existing tag is returned. If not, the new tag is added. This prevents synonym proliferation while allowing organic growth.

**Rule**: Never hardcode tags in a skill. Always resolve through `tag_resolver.py` against the vault's tag registry. Person profiles get 5-10 tags, events 5-8, centers and signals 3-5.

## 31. Sanitize tags at build time — don't rely solely on the resolver

**Problem**: The tag resolver fuzzy-matches against the registry, but LLM-provided tags sometimes contain spaces, special characters, or mixed case that survive matching. Tags like `"machine learning"` or `"AI & Robotics"` create broken Obsidian tags.

**Fix**: Every builder script (`build_profile.py`, `build_signal.py`, `build_center.py`, `build_event.py`) applies `_sanitize_tag()` before writing tags to frontmatter:

```python
def _sanitize_tag(tag: str) -> str:
    t = tag.lower().strip()
    t = re.sub(r"[^a-z0-9\s-]", "", t)
    t = re.sub(r"\s+", "-", t)
    t = re.sub(r"-+", "-", t)
    return t.strip("-")
```

**Rule**: Tag resolution (fuzzy matching) and tag sanitization (formatting) are separate concerns. Both must run. The resolver picks the right tag; the sanitizer ensures valid kebab-case output.

## 32. Preserve raw source content alongside processed notes

**Problem**: After processing a URL into a signal note, the original article text is lost. If extraction logic improves later, every URL must be re-fetched — but URLs may have moved, gone behind paywalls, or been blocked by bot detection.

**Fix**: Save the raw extracted text to `raw/<slug>.txt` during the gather phase. Include a `raw_file:` field in the signal note's frontmatter linking to the raw file. This enables retroactive re-processing without network access.

**Rule**: When a skill fetches content from an external source, save the raw text alongside the processed output. Raw files are cheap to store and expensive to re-fetch.

## 33. Extract quotes with attribution-aware snippet windows

**Problem**: Simple keyword-in-context snippets (±N characters around a name mention) produce truncated, low-value snippets. A quote like `"But that's not how the body is," Krishnamurthy said. "The body has both – hard bo..."` is cut off mid-sentence because the window is fixed-size.

**Fix**: `extract_person_snippets()` uses a priority-based approach:
1. **Direct quotes**: Find attribution points (speech verb + name), then expand outward following quote marks to capture full multi-sentence quotes
2. **Keyword-rich mentions**: Score proximity to high-value words (goal, mission, lead, discover, award, grant, etc.)
3. **Basic name proximity**: Fallback to simple ±N character windows

The quote expansion follows quotation marks bidirectionally from the attribution point, capturing continuation quotes (`"..." said Name. "..."`) as a single snippet.

**Rule**: When extracting snippets around person mentions, prioritize direct quotes with full sentence boundaries. A truncated quote is worse than no quote — expand windows to follow quotation marks rather than using fixed character limits.

## 34. Use backfill scripts for retroactive updates — don't re-run the LLM

**Problem**: After adding new features (tag sanitization, snippet extraction, raw data links), 60 existing signal notes needed updating. Re-running the full LLM pipeline for each would be slow, expensive, and might produce different summaries.

**Fix**: A standalone `backfill_signals.py` script parses existing markdown, applies targeted fixes (tag sanitization, snippet insertion, raw file linking) without invoking the LLM. It preserves all LLM-generated content (summary, tags, people) while adding the new deterministic sections.

**Rule**: When adding a feature that affects existing notes, write a backfill script that operates on the markdown directly. Reserve LLM re-processing for cases where the LLM's judgment is actually needed (e.g., re-classifying roles). Deterministic updates (tag formatting, section insertion, link addition) should never require an LLM call.

## 35. Script vault setup — don't configure Obsidian by hand

**Problem**: Obsidian graph color groups, CSS snippets, folder structure, and tag registries must be configured for each vault. Manual setup is error-prone, undocumented, and hard to reproduce.

**Fix**: `setup_vault.py` configures all vault settings from a single command:
- Graph color groups in `graph.json` (using `path:"folder/"` query format)
- CSS snippets for folder color coding in the file explorer
- Enable snippets in `appearance.json`
- Create folder structure and tag registry scaffold

**Rule**: Vault configuration is code, not manual settings. When adding a new entity type (e.g., abstracts), update `setup_vault.py` — don't document a manual process.

### Obsidian graph.json gotchas

- Query format must be `path:"folder/"` with quotes and trailing slash
- Obsidian overwrites `graph.json` on exit — quit Obsidian before writing
- `workspace.json` state overrides `graph.json` for open graph views — but Obsidian resets workspace state on startup, so `graph.json` is the reliable target
- Colors use RGB decimal: `(R * 65536) + (G * 256) + B`

---

## Summary: Skill Design Checklist

- [ ] Gather phase uses 1-2 composite tools, not 5+ individual ones
- [ ] Tools never accept LLM-constructed URLs
- [ ] Bad inputs are blocked in tool code, not just prompts
- [ ] Every graph loop has a hard iteration cap
- [ ] Tool calls are deduplicated in the harness
- [ ] Factual fields sourced from APIs, not LLM inference
- [ ] Plugin contains only data scripts, no orchestration scripts
- [ ] No LLM calls inside tools — orchestrating LLM handles reasoning
- [ ] Tool output is structured and parseable
- [ ] Webpage fetching is optional/supplementary
- [ ] Template fields with known defaults are pre-filled, not FILL markers
- [ ] External API response shapes are validated and version-tolerant
- [ ] Data extraction uses the best installed tool, not a crude fallback
- [ ] Deterministic data transformation (formatting, merging, dedup) is in Python, not the LLM
- [ ] Large datasets pass between tools via Python state, not through LLM context
- [ ] Verify script regexes are tested against the actual output format
- [ ] Execute→tools loop short-circuits to verify when output is produced
- [ ] Dedup keys normalize unicode (dashes, quotes, whitespace) to ASCII
- [ ] Soft 404s detected by validating page content, not just HTTP status
- [ ] Data sources ranked by authority per field type (title from LDAP > profile > API)
- [ ] Fallback searches validate identity (institution match) before accepting
- [ ] Multiple discovery paths for heterogeneous organizational structures
- [ ] Output decomposed into atomic linked files for knowledge graph tools
- [ ] Domain-specific classification rules are explicit in the prompt with examples and defaults
- [ ] Bot-blocked fetches hard stop immediately — no retries or header rotation
- [ ] URL fetch code handles gzip/deflate Content-Encoding decompression
- [ ] Batch mode rebuilds LangGraph app every 5-10 items to flush state
- [ ] Skills emit .tsv files for cross-skill pipeline composition
- [ ] Date fields follow convention: published/date (real-world), _indexed (internal), never created
- [ ] Tags resolved through tag_resolver.py against vault registry, never hardcoded
- [ ] Tags sanitized to kebab-case at build time via `_sanitize_tag()` in every builder
- [ ] Raw source content saved to `raw/` folder alongside processed notes
- [ ] Person snippets prioritize direct quotes, then keyword-rich mentions, then proximity
- [ ] Retroactive updates use backfill scripts, not LLM re-processing
- [ ] Vault setup scripted via `setup_vault.py`, not configured manually
