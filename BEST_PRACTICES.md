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
