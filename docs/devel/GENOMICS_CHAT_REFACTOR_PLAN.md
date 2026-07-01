# Genomics Chat Refactor Plan

Status: active development outline
Scope: Explore chat for genomics, with emphasis on Explore Focus: Functional

## Goal

Move the genomics chat system from a mixed model
- LLM SQL generation
- handwritten prompt-family fixes
- post-hoc repair logic

to a more structured model where
- the live graph/schema/registry provides the semantic action space
- the LLM is used mainly for intent mapping
- deterministic execution computes the result
- the UI can render either tables or higher-level summaries from the same intermediate analysis model

Primary direction:
- avoid long-term fallback layers
- straighten the main path until it is the normal path
- adjust datasets/schema/build rules where needed so demos work cleanly through that primary path

## Current Model

Today the flow is roughly:
1. user asks a natural-language question
2. LLM proposes SQL
3. built-in module logic validates, rewrites, enriches, or replaces it
4. UI shows a result table, sometimes with evidence columns

This works, but a lot of correctness currently depends on curated genomics-specific rules.

## Target Model

Target flow:
1. user asks a natural-language question
2. LLM maps the request to a structured intent
3. deterministic layer resolves live entity families, paths, filters, aggregations, and evidence projections
4. execution layer computes the result in SQL and/or Python
5. UI renders one of:
   - entity table
   - scalar/stat summary
   - comparison
   - ranked list
   - narrative summary grounded in computed results

## Main Refactor Themes

### 1. Structured live semantics

Replace handwritten prompt-family branching with a richer live semantic layer that can describe:
- entity families
- aliases
- owner/result type preferences
- valid typed paths
- evidence projections
- supported aggregation types
- supported comparison/stat operations
- dataset-specific overrides

### 2. Shared structured analysis model

Introduce one shared intermediate representation for chat analyses, so the same intent can produce:
- SQL table output
- computed summary output
- evidence-rich narrative output

### 3. Keep LLM flexible, reduce LLM responsibility

The LLM should still understand flexible phrasing and novel combinations, but it should not be responsible for:
- numeric correctness
- path correctness
- evidence-column selection
- result-shape correctness

### 4. Primary-path first, not fallback-first

Refactoring should prefer one clean primary execution model over a growing stack of rescue layers.

That means:
- if a dataset shape is inconsistent with intended semantics, fix the dataset/schema/build mapping
- if a concept is real and supported, model it in the structured semantic layer
- if a demo prompt matters, make it work through the primary path rather than via a hidden special-case repair
- use temporary bridges only when necessary, and mark them for removal

## Proposed Intermediate Analysis Model

Example shape only:

```yaml
analysis:
  domain: genomics
  intent: rank | filter | aggregate | compare | summarize | correlate
  requested_result_kind: entity_rows | scalar | distribution | narrative
  subject:
    entity_type: protein
    subset: ...
  operations:
    - type: filter_by_tag
    - type: filter_by_promoted_call
    - type: aggregate_count
    - type: percentile
  dimensions:
    group_by: ...
  evidence:
    include:
      - matched_call
      - orthogroup_label
      - hgt_donor
  presentation:
    prefer_table: true
    prefer_summary: false
```

This should be rich enough to support both:
- `select proteins predicted as transmembrane domains`
- `what is the 90th percentile of Egg-stage expression for transcripts x, y, z`

## Phases

### Phase 0. Stabilize current behavior

- [x] Add lossless post-LLM reconciliation for genomics chat paths
- [x] Preserve and enrich evidence columns on accepted/repaired SQL
- [x] Add regression coverage for current repaired prompt families
- [x] Rebuild sample DBs from corrected source/schema where needed
- [x] Mark which current repairs are temporary bridges vs acceptable steady-state behavior

### Phase 1. Inventory current semantics

- [x] List all current handwritten genomics prompt-family handlers
- [x] List all current deterministic rewrite types
- [x] List all evidence-column projection rules
- [x] Separate generally reusable semantics from SCN-specific semantics
- [x] Document which semantics are live-derived today vs hardcoded
- [x] Identify demo-critical prompts that must migrate onto the clean primary path

### Phase 1 Inventory Snapshot

Current genomics chat behavior in `APP/kgx/llm/modules/genomics.py` falls into four buckets.

1. Registry-driven semantics
- protein evidence families and relation specs
- ortholog-member semantics
- metadata-filter specs and renderers
- scope-tag operators
- validation config and prompt guidance

2. Live-derived semantics
- promoted entity families discovered from graph shape
- promoted call/tag names discovered from live entities
- homology scope branch traversal from live tags
- organism aliases expanded from live registry and dataset content
- available requested/result types inferred from live graph

3. Handwritten deterministic prompt-family logic
- functional derived-connection ranking
- functional annotation owner ranking
- common functional annotation term ranking
- common promoted entity term ranking
- stage-ranked expression requests
- HGT donor result requests
- broad homology organism tag result requests

4. Handwritten semantic condition matching and repair
- effector-family expansion and collapse
- promoted-call condition matching
- generic tag condition matching
- orthogroup label extraction
- accepted-SQL evidence enrichment and semantic reconciliation
- validation rules for missing/wrong-shape SQL

### Current Deterministic Rewrite Types

- entity filter synthesis from semantic conditions
- ranking synthesis for derived annotation neighbors
- owner ranking by functional annotation count
- promoted entity ranking by owner count
- annotation-term ranking by annotated owner count
- expression ranking by condition/stage label
- metadata-filter query synthesis
- ortholog-member bridging for comparative prompts
- HGT donor/tag-oriented typed result queries

### Current Evidence Projection Rules

- semantic condition display columns from registry specs
- accepted SQL evidence columns for protein evidence and tag evidence
- `matched_call` and `matched_call_category` for promoted-call filters
- `matched_tag` for generic tag filters
- annotation namespace/category projection for common-term rankings
- `shared_annotation_count`, `functional_annotation_count`, expression condition labels, orthogroup labels, homolog organism labels

### Reusable vs Dataset-Specific

Generally reusable genomics semantics:
- protein evidence relation families
- orthogroup/ortholog-member bridging
- promoted-call families
- functional annotation families and namespace/category filters
- expression ranking semantics

Still dataset- or branch-specific:
- SCN effector tag families and aliases
- sample-data fixes such as `effector_islands` source interpretation
- organism-specific homology/effector naming quirks

### Demo-Critical Prompt Families

These prompt families should migrate onto the clean primary path first because they are central to the current genomics demos:
- functional annotation rankings
- GO/common functional term rankings
- localization/prediction assignment rankings
- promoted-call protein filters such as transmembrane-domain prompts
- generic tag filters such as effector-island prompts
- HGT donor + orthogroup evidence prompts
- comparative ortholog-member prompts
- expression stage ranking prompts

### Phase 2. Define the structured intent model

- [x] Define a stable `analysis` schema for chat intent resolution
- [x] Define supported operation categories
- [x] Define supported output kinds
- [x] Define evidence projection semantics
- [x] Define dataset/module override points

Current implementation slice:
- a first in-code `analysis` contract now exists at the module layer for:
  - functional derived-connection rankings
  - common promoted-entity rankings
  - common functional annotation term rankings
  - functional annotation owner rankings
  - promoted-call entity filters
  - generic tag entity filters
  - effector tag entity filters
  - metadata-driven entity filters
  - protein-evidence plus scope-tag entity filters
  - comparative scope-tag entity filters
  - protein-evidence plus orthogroup entity filters
  - protein-evidence plus ortholog-member entity filters
  - protein-evidence plus homology-organism entity filters
  - direct HGT donor result queries
  - broad-homology organism tag result queries
  - ortholog copy-count result queries across both owner-map and live member-edge strategies
  - expression ranking entity queries
  - comparative/HGT semantic-condition entity filters
  - expression average / percentile scalar summaries
  - explicit gene/transcript/protein subset filtering for expression scalar summaries
- these current genomics prompt families now build an intermediate `analysis` dict and compile SQL from it, instead of going straight from prompt heuristics to SQL
- the structured `analysis` object is attached to `semantic_trace` for debugging and regression tests
- `analyze_request()` and `synthesize_analysis()` now route through declarative handler tables rather than one handwritten branch ladder per analysis kind
- remaining major handwritten areas are now narrower:
  - `multi_condition_filters` remains an explicit primary analysis kind for genuinely mixed cross-family combinations rather than an implied fallback bucket
  - scalar/stat outputs are now started, but only for expression average / percentile summaries
  - generic scalar/stat result rendering is not yet generalized across domains or metric families
  - some deterministic execution validation still remains module-owned because it checks runtime thresholds, resolved metadata values, live graph strategy selection, and required projected evidence columns

### Phase 3. Move semantics from code to data/registry

- [x] Represent more aliases declaratively
- [x] Represent promoted families declaratively from live schema where possible
- [x] Represent result-type preferences declaratively
- [x] Represent supported aggregations declaratively
- [x] Reduce special-case prompt branching in `genomics.py`
- [x] Make dataset-specific semantics explicit in source schema/config, not hidden in runtime fallbacks

Current Phase 3 progress:
- result-type preference/suppression now starts from registry rules for donor/tag/comparative/ortholog cases
- analysis routing/synthesis dispatch now uses declarative handler tables instead of one manual branch chain
- condition matching, condition pruning, live promoted-family discovery inputs, and scope-tag source discovery now also read registry-backed matcher/config state rather than parallel handwritten prompt loops
- accepted-sql evidence enrichment and prompt-side semantic validation now consume the same requested condition bundle instead of independently reconstructing prompt semantics
- remaining module-owned validation code is now considered intentional deterministic execution logic, not mixed prompt-routing fallback architecture

Phase boundary note:
- phases 2 and 3 are effectively complete for the current genomics prompt families in the sense intended by this refactor: prompt interpretation, routing, and semantic condition assembly now flow through the structured analysis path and registry-backed matcher/config layers rather than parallel prompt-to-sql branches
- what remains outside this boundary is primarily dynamic execution validation and broader scalar/stat generalization, which belong to later execution-layer work rather than more phase-2/3 semantic-routing cleanup

### Phase 4. Deterministic execution layer

- [x] Compile structured analyses to SQL for row-based and aggregation outputs
- [x] Add Python-side deterministic stats where SQL is awkward
- [x] Support percentiles, averages, distributions, comparisons, and ranked summaries
- [x] Ensure execution artifacts can be reused by both table and summary outputs

Phase-4 status note:
- For the current genomics prompt families, phase 4 is now effectively complete. The remaining work is no longer execution-path completion for those families; it is phase-5 presentation/narrative behavior plus later cleanup/generalization.

### Phase 5. Multi-output chat responses

- [ ] Support scalar/stat responses in addition to tables
- [ ] Support ranked summaries grounded in computed outputs
- [ ] Support narrative summaries over deterministic result artifacts
- [ ] Decide how UI exposes table vs summary vs both
- [ ] Keep the raw SQL/result artifact inspectable

Phase-5 progress note:
- The first slice is now in place for the current genomics summary analyses: explanatory narrative rendering can be produced from the normalized summary artifact, and `/api/chat` answer responses now keep `results` plus `artifact` attached for inspection.
- Ranked genomics analyses now also support artifact-driven explanatory summary responses for the current ranking families, using deterministic `ranked_summary` artifacts rather than remaining table-only for summary-style prompts.
- `/api/chat` now also exposes a normalized `presentation` block (`primary_view`, `available_views`, preference flags, summary style, artifact kind, requested result kind) so phase-5 consumers no longer have to infer summary-vs-table behavior from `intent`, prose, and artifact rows alone.
- the chat UI now consumes that `presentation` block directly for answer-style responses, rendering summary-first cards and only showing supporting tables when the contract explicitly exposes them.
- the chat UI now also exposes a built-in artifact inspector for summary-style answers, so the normalized deterministic payload is inspectable without leaving the chat surface.
- for the current genomics prompt families, phase 5 is now effectively complete in the sense intended by this refactor. Remaining work is no longer about whether multi-output deterministic responses exist for those families; it is about later cleanup/generalization and any broader non-genomics adoption.

### Phase 6. Cleanup and simplification

- [ ] Retire redundant prompt-family repairs once covered by the structured model
- [ ] Remove genomics-only special cases that become declarative
- [ ] Shrink shared/core logic back to generic orchestration primitives
- [x] Audit performance and token usage before/after refactor
- [ ] Remove temporary bridges once demos are stable on the primary path

### Next Task Queue

1. Deterministic-first execution for supported genomics prompt families
   Goal:
   - if `analyze_request()` + `synthesize_query()` can fully resolve the prompt, execute that path before calling the LLM
   Why this is the next safe optimization:
   - it reduces prompt size losslessly instead of trimming schema context blindly
   - it makes the primary path truly primary for already-migrated prompt families
   Validation:
   - preserve current user-visible results for ranking/filter/stat/comparison prompt families already covered by the structured analysis model
   - keep the current LLM path as fallback for unsupported or unresolved prompts
   Status:
   - completed on 2026-07-01 in `ChatToSQL.ask()`: the module now attempts deterministic synthesis before building the LLM prompt, and representative ranking/stat prompts have regression coverage asserting zero model calls

2. Conditional prompt compaction for fallback-only paths
   Goal:
   - once deterministic-first is in place, re-measure and only then decide whether the remaining schema snapshot or few-shot payload can be trimmed safely for prompts that still require the LLM
   Lossless guardrails:
   - do not remove live schema details that are still required for unsupported prompt families
   - prefer conditional omission over global prompt trimming
   - any compaction must be paired with side-by-side regression prompts covering typed joins, requested result types, and evidence-heavy routes

3. Residual bridge retirement
   Goal:
   - remove accepted-SQL rescue logic that becomes unreachable or redundant once deterministic-first execution covers the intended primary-path families

### Current Recorded Progress

Completed in the current cleanup / lossless pass:
- `ChatToSQL.ask()` now attempts module deterministic synthesis before building the LLM prompt, so supported genomics prompt families can skip prompt construction entirely
- supported ranking and scalar-summary prompts now have regression coverage asserting zero LLM calls on the deterministic-first path
- explicit dataset-semantic mismatches now return deterministic answers instead of falling through to speculative SQL for:
  - expression condition names
  - ortholog-count organism names
  - broad-homology organism names
- explicit condition-name matching was tightened so wrong cross-dataset phrases no longer collapse to shorter partial labels
- rebuilt SCN and Bison smoke checks now verify both:
  - valid dataset-native prompts still resolve deterministically
  - wrong dataset-native prompts return live alternative previews instead of broader fallback results

Next targets:
1. Audit fallback-only prompt dependencies
   - measure which live schema snapshot sections and few-shot examples are still actually needed once deterministic-first removes the supported prompt families from prompt assembly
2. Extend deterministic mismatch handling to other live semantic branches
   - especially named scope tags or dynamic-family targets that users can mention explicitly even when the active dataset does not contain them
3. Retire residual accepted-SQL rescue only where deterministic-first coverage is proven
   - keep rescue logic for unresolved prompt families until equivalent deterministic coverage exists

### Lossless Compaction Workstream

Use this list for the next cleanup/optimization sessions so safe prompt reduction stays ordered and auditable.

1. Primary-path coverage audit
   - enumerate the current genomics prompt families that already resolve deterministically before LLM invocation
   - add one representative no-LLM regression per family class where coverage is still thin
   - explicitly document unsupported prompt shapes that must still take the fallback prompt path
   - explicitly separate unresolved wording from explicit dataset-semantic mismatches; prompts that name a condition/entity family not present in the active dataset should return a deterministic mismatch answer rather than falling through to speculative LLM SQL

2. Fallback prompt dependency audit
   - identify which parts of the current system prompt are still exercised by prompts that genuinely require LLM SQL
   - separate required live schema facts from fixed explanatory ballast such as unconditional examples
   - record any fallback prompts that fail if typed-pattern or metadata-key context is reduced

3. Conditional compaction implementation
   - only build the full schema snapshot when deterministic synthesis does not resolve the prompt
   - then test whether few-shot examples can be reduced or selected by module/family instead of always included
   - keep `requested_result_types`, entity-match hints, and module-specific steering intact unless regression evidence shows they are unnecessary

4. Bridge retirement after evidence
   - remove accepted-SQL semantic rescue only for prompt families proven to stay on the deterministic-first path
   - keep fallback rescue for unresolved families until equivalent deterministic coverage or stronger validation exists
   - re-run demo-critical prompts on rebuilt sample DBs after each retirement slice

5. Final lossless verification
   - compare supported-prompt outputs before/after compaction on rebuilt SCN and BCN sample DBs
   - verify that supported prompts still make zero LLM calls and unsupported prompts still receive the required schema guidance
   - verify that obviously wrong dataset-native condition names produce a deterministic mismatch answer listing active alternatives instead of collapsing to a shorter partial match
   - update this plan with measured prompt-size deltas and any intentionally retained fallback complexity

## Non-Goals

- Do not remove LLM flexibility for user phrasing
- Do not replace deterministic correctness with freer LLM reasoning
- Do not add many parallel one-off summary paths before the shared analysis model exists

## Current Known Issues / Cleanup Items

- [ ] Current genomics chat still contains substantial handwritten live-derived matching and language heuristics, but the current prompt families no longer bypass the structured analysis path
- [ ] Some sample-data semantics are dataset-specific and should stay isolated from shared contracts
- [ ] Binary sample DB fixes should ideally come from source rebuilds, not only manual backfills
- [ ] Generic tag matching still depends on some explicit wording and could be more semantic
- [ ] Output model is still primarily table-first

Remaining intentional runtime boundary for the current genomics families:
- primary/secondary organism alias sets are still chosen from live organism rows in the active graph
- scope/effector tag discovery still walks the live tag hierarchy in the active graph, with registry config controlling how those discovered tags are interpreted
- dynamic-family family labels such as `known` and `putative` are still finalized from message phrasing over already live-derived family flags

These are different from accidental runtime semantics. The refactor has already moved most former prompt-routing, validation, artifact-shaping, and presentation choices into the structured analysis contract plus registry-driven config. The remaining question is not whether more code can be deleted blindly; it is whether these live-data decisions should stay runtime-owned or be pushed into source/build-time semantics without making the system more brittle.

### Current Boundary Classification

Acceptable steady-state behavior for now:
- live organism alias collection from current `organism` rows
- live branch/tag discovery when the active graph hierarchy is the source of truth
- final family selection over already live-derived dynamic-family flags when prompt phrasing legitimately changes the requested subset
- owner-type / count-strategy selection that depends on active graph content such as `gene_counts` presence versus live member edges
- deterministic rejection of explicit dataset-semantic mismatches when the active graph clearly lacks the named expression condition or analogous live semantic target

Temporary bridges to remove when the primary path is fully stable:
- any accepted-SQL semantic reconciliation that compensates for LLM SQL choosing the wrong typed bridge or evidence path when the structured analysis already knows the correct route
- prompt wording gates that exist only to protect a still-ambiguous matcher and do not correspond to a stable domain concept
- dataset-specific sample semantics that can be represented in source schema, semantic overlays, or deterministic build outputs instead of runtime rescue logic
- any DB-level backfill or checked-in binary fix that is not reproducible from `sample_data/1_source/*`

Bridges already retired in this refactor:
- duplicated prompt-family route wrappers for scope/comparative/effector analyses
- separate handwritten aggregation execution branches for current scalar/distribution/comparison summaries
- hardcoded primary-organism selection by `HAS_CHROMOSOME`
- duplicated live branch walkers for homology scope versus dynamic-family tag discovery

### Performance / Token Audit Baseline

Audit date: 2026-07-01
Environment:
- rebuilt `sample_data/3_db/genomics_scn.db`
- sample app config from `sample_data/1_source/genomics_scn/app-config.yaml`
- stub LLM returning an empty-result SQL shell so timings reflect prompt assembly, validation, deterministic synthesis, and DB execution rather than local-model inference

Representative prompt baseline:
- functional-annotation ranking:
  - prompt payload: ~3,131 approximate input tokens
  - system/schema portion: ~2,547 approximate tokens
  - average end-to-end latency: ~13.66 ms
- promoted-call filter:
  - prompt payload: ~3,131 approximate input tokens
  - average end-to-end latency: ~38.20 ms
- known-effector filter:
  - prompt payload: ~3,134 approximate input tokens
  - average end-to-end latency: ~12.66 ms
- expression percentile summary:
  - prompt payload: ~3,133 approximate input tokens
  - average end-to-end latency: ~24.97 ms
- expression comparison summary:
  - prompt payload: ~3,163 approximate input tokens
  - average end-to-end latency: ~34.36 ms

Observed hotspots from this baseline:
- the live schema snapshot dominates input size (~2.5k of ~3.1k approximate tokens for these prompts)
- few-shot examples are always present and contribute a fixed multi-message cost even when the deterministic synthesis path handles the request after a no-result SQL shell
- promoted-call and expression-comparison paths are currently the slower representative deterministic routes in this no-model baseline

Interpretation note:
- these measurements are useful for relative orchestration/regression tracking, not for predicting real user latency with Ollama or another local model
- real end-to-end latency will still be dominated by model inference time, but this baseline now makes prompt-size regressions and deterministic-path overhead measurable

Post-baseline update:
- as of 2026-07-01, supported structured-analysis prompts now attempt deterministic synthesis before prompt construction in `ChatToSQL.ask()`
- representative regressions now prove zero LLM calls for at least:
  - functional-annotation ranking
  - expression percentile scalar summaries
- rebuilt-SCN smoke audit also confirms zero LLM calls for:
  - `which proteins have the most functional annotations`
  - `what is 90th percentil of expression in ppJ2 stage?`
- cross-dataset smoke audit now also confirms deterministic mismatch handling for explicit wrong condition names:
  - SCN rejects `Adult Female Liver` as an expression condition and lists live SCN alternatives
  - Bison rejects `ppJ2` as an expression condition and lists live Bison alternatives
- ortholog-count prompts with explicit unknown organism names now also return deterministic mismatch answers with live organism alternatives sourced from active semantics (`organism` rows, `metadata.organism`, and `gene_counts` keys)
- broad-homology organism prompts with explicit unknown organism names now also return deterministic mismatch answers with live homology-organism alternatives sourced from active homology tags and comparative-hit metadata
- the next measurement to capture is fallback-only prompt payload size after excluding supported deterministic families from prompt assembly entirely

## Design Rules For Future Sessions

- Prefer extending structured semantics over adding another handwritten prompt-family patch
- Prefer fixing source/schema/build semantics over adding runtime dataset-specific rescue logic
- If a new behavior needs deterministic repair, note whether it is:
  - general genomics behavior
  - sample-specific behavior
  - temporary bridge behavior to remove later
- Any new non-table response type should be grounded in the same deterministic analysis model
- Avoid putting domain-specific hardcoding into shared `ChatToSQL` unless the module opts into it explicitly
- Demo-critical prompts should be tested against the intended primary path, not only against fallback behavior

## Reviewer Checklist

- [ ] Is the new behavior driven by live schema/registry where possible?
- [ ] Is any dataset-specific logic kept out of shared contracts unless truly global?
- [ ] If data semantics were wrong or inconsistent, were source/schema/build rules corrected instead of only patching runtime behavior?
- [ ] Does the same semantic intent support both table output and future summary output?
- [ ] Is the deterministic execution path clear and inspectable?
- [ ] Does this reduce or at least not increase long-term fallback complexity?
- [ ] Was a regression test added for the repaired behavior?

## Session Log Notes

Use this section to append short progress notes across sessions.

- 2026-06-30: Initial plan created. Current system stabilized with lossless genomics post-LLM reconciliation, evidence-column enrichment, expanded regression coverage, SCN effector-island source/schema fix, and `Functional` preset relabeling.
- 2026-06-30: Direction clarified: refactor should converge toward one clean primary path, with dataset/schema/build fixes where necessary, rather than preserving a large fallback stack as the long-term model.
- 2026-06-30: Phase 1 inventory captured in the plan doc. Current genomics behavior is now explicitly split into registry-driven, live-derived, handwritten deterministic, and handwritten repair layers to guide the refactor.
- 2026-06-30: First structured-analysis code slice landed. Common promoted rankings, common functional annotation rankings, functional annotation owner rankings, and promoted-call filters now pass through an explicit `analysis` representation before SQL compilation.
- 2026-06-30: Generic tag filters also migrated onto the structured `analysis` path. The biggest remaining handwritten query-construction cluster is now comparative/HGT evidence composition.
- 2026-06-30: Comparative/HGT semantic-condition prompts now also pass through the structured `analysis` wrapper before SQL compilation. The remaining gaps are mostly typed-result synthesis paths and expression/stat output unification.
- 2026-06-30: Expression ranking prompts now also use the shared `analysis` model. The biggest remaining gaps are typed-result synthesis paths and extending the model from ranked rows to scalar/stat outputs.
- 2026-06-30: First scalar/stat path landed. Expression average and percentile prompts now execute through the shared `analysis` model and return deterministic answer summaries with inspectable result artifacts.
- 2026-06-30: Expression scalar stats now support explicit transcript subsets matched from prompt entity names, so subset-based deterministic summaries are no longer table-only.
- 2026-06-30: Expression scalar stats now also cover explicit gene and protein subsets through the same structured analysis path, and the remaining legacy validator reference was removed so expression checks now rely on the shared analysis model end to end.
- 2026-06-30: Direct `hgt_donor` result queries and broad-homology organism-tag result queries now also go through the shared `analysis` path, narrowing the leftover separate typed-result logic to ortholog count/result synthesis.
- 2026-06-30: Ortholog copy-count result queries now also use the shared `analysis` model for both `gene_counts` owner maps and live ortholog-member edge datasets, removing the last major typed-result special-case branch from genomics chat synthesis.
- 2026-06-30: Added a repo-root `kgx` launcher shim so the standard conda/environment.yml workflow (`python -m kgx ...` from the repo root) resolves to the checked-out `APP/kgx` source tree instead of an older installed package.
- 2026-06-30: Metadata-driven genomics filters now also build and compile through the shared `analysis` model instead of bypassing it via a direct prompt-to-SQL helper.
- 2026-06-30: Pure effector prompts now synthesize through a dedicated `effector_tag_filters` analysis kind instead of the broader residual multi-condition bucket. Mixed comparative/scope combinations still remained on that residual path at that point.
- 2026-06-30: Effector filter analyses now also expose explicit family classification such as `known` and `putative`, reducing one more implicit piece of the old collapse logic and making future declarative cleanup easier.
- 2026-06-30: Pure protein-evidence plus scope-tag prompts now synthesize through a dedicated `scope_tag_filters` analysis kind. Mixed scope/comparative combinations still stayed on the residual multi-condition path at that point.
- 2026-06-30: Comparative prompts that combine scope tags with ortholog-style constraints now also synthesize through a dedicated `comparative_scope_filters` analysis kind, shrinking the residual multi-condition bucket again.
- 2026-06-30: Prompts that combine protein evidence with a named orthogroup filter now also synthesize through a dedicated `evidence_orthogroup_filters` analysis kind instead of the residual multi-condition path.
- 2026-06-30: Prompts that combine protein evidence with ortholog-member constraints now also synthesize through a dedicated `evidence_ortholog_member_filters` analysis kind, further shrinking the residual multi-condition path.
- 2026-06-30: Audit cleanup: promoted-call and generic-tag filters now emit analysis-specific trace kinds in debug output instead of the old generic `genomics_semantic_conditions` label, making the residual bucket easier to measure accurately.
- 2026-06-30: Audit follow-up: HGT donor plus broad-parasitism prompts are also covered by the primary `scope_tag_filters` path; the old generic trace expectation was a test/documentation mismatch rather than a real fallback route.
- 2026-06-30: Cleanup audit: `synthesize_query()` no longer carries redundant fallback branches for migrated families, and unused wrapper entrypoints for those old branches were removed so the structured analysis path is now the normal code path rather than a parallel route.
- 2026-06-30: Broad-homology prompts with explicit requested organisms now also synthesize through a dedicated `evidence_homology_organism_filters` analysis kind, so homolog-organism constraints are modeled explicitly in the primary path instead of being injected only via query-builder state.
- 2026-06-30: Audit follow-up: `broad homology + BCN orthologs` already fits the primary `evidence_ortholog_member_filters` model, so no extra analysis kind was added; the missing piece was explicit regression coverage, not routing logic.
- 2026-06-30: Final cleanup: the residual mixed path is now named consistently in code as `multi_condition_filters`, and it has explicit regression coverage for a true cross-family combination (`promoted_call + HGT evidence`) so it is treated as an intentional primary model, not a fallback.
- 2026-06-30: Internal cleanup: condition-derived validation state is now centralized in a shared helper instead of being recomputed in several ad hoc blocks, reducing leftover matcher/plumbing duplication around the primary analysis model.
- 2026-06-30: Higher-level cleanup: the recurring semantic-condition route families (`scope_tag_filters`, comparative/evidence combinations, and homology-organism variants) now share one declarative route-spec table for analysis construction and compilation, so those condition-family semantics are configured in one place instead of repeated across near-duplicate branch functions.
- 2026-06-30: Contract cleanup: genomics `analysis` dicts are now normalized through a versioned module-local contract layer before synthesis, which enforces core required fields and fills default `selection_mode`, `execution`, and `presentation` metadata for the existing structured-analysis paths.
- 2026-06-30: Effector cleanup: generic effector family collapse now reads registry config (`collapse.when_message_contains`, `fallback_precedence`, and optional `family_flag_matches`) instead of hardcoded `known`/`putative`/`dna`/`protein` branching, so family grouping is more declarative and testable.
- 2026-06-30: Effector cleanup: effector evidence-column enrichment now also reads registry display rules instead of hardcoded SCN/BCN tag-id substring checks, so metadata-field/alias projection for effector prompts can be overridden from semantic config and regression-tested directly.
- 2026-06-30: Effector cleanup: scoped-vs-generic effector alias precedence now also comes from dynamic-family selection config (`match_groups` plus `stop_at_first_nonempty_group`) instead of being hardcoded as primary-scoped, then secondary-scoped, then generic in the module.
- 2026-06-30: Result-type cleanup: alias-based result-type preference/suppression for broad-homology organism tags, HGT donors, ortholog-member targets, and comparative-hit prompts now starts from registry rules instead of only module branching, while the plain explicit `gene/protein/transcript` noun heuristic still remains local code.
- 2026-06-30: Matcher cleanup: promoted-call and generic-tag request cue vocabularies now come from semantic-registry matcher config instead of hardcoded token lists in the module, so wording-gate behavior for those families is now overrideable and regression-testable.
- 2026-06-30: Matcher cleanup: functional-annotation ranking cues, common-ranking cues, and functional-annotation category cues now also come from semantic-registry matcher config instead of module-local token lists, further shrinking the remaining handwritten language-detection surface.
- 2026-07-01: Safe prompt-reduction slice landed in shared orchestration: `ChatToSQL.ask()` now executes module-synthesized deterministic results before building the LLM prompt, and representative ranking/stat regressions assert zero LLM calls for supported genomics prompts.
- 2026-07-01: Rebuilt-SCN smoke audit confirmed the same zero-LLM behavior on representative live-data prompts for functional-annotation ranking and `ppJ2` percentile summaries, so the deterministic-first optimization is now verified beyond fixture-only tests.
- 2026-07-01: Expression-condition resolution was tightened to be dataset-aware and exact for explicit condition phrases. Cross-dataset wrong prompts such as SCN `Adult Female Liver` or Bison `ppJ2` now return deterministic mismatch answers with live condition previews instead of falling through to LLM SQL or collapsing to shorter partial labels.
- 2026-07-01: Ortholog-count organism mismatches now follow the same deterministic dataset-aware rule: explicit unknown organism names return a direct answer with live organism alternatives from the active dataset instead of a generic fallback or speculative SQL path.
- 2026-07-01: Broad-homology organism mismatches now follow the same rule: explicit unknown homology-organism names return a deterministic answer with live homology-organism alternatives instead of silently degrading to a broader homology query.
- 2026-06-30: Semantic-spec cleanup: annotation-namespace alias specs and common-promoted entity specs now come from the semantic registry instead of static module lists, so those selection vocabularies are overrideable and no longer duplicated in code.
- 2026-07-01: Matcher cleanup: homology-organism lookup, organism-name lookup, and entity-subset gating now share the same registry-backed matcher helper path instead of three separate prompt-entity loops, and subset cue detection is now configurable from semantic-registry matcher specs too.
- 2026-07-01: Live-promoted cleanup: runtime promoted-entity discovery now reads registry config for excluded relation/result types, alias-field synthesis, and default count aliases, and ortholog-member matching now shares the same relation-family matcher helper path as evidence-family matching instead of a bespoke alias/exclusion branch.
- 2026-07-01: Condition-bundle cleanup: semantic-condition assembly now follows an ordered registry `condition_matching` plan with declarative prune rules, and both `validation_error()` and `evidence_columns_for_sql()` now consume the same requested condition bundle instead of independently re-deriving prompt semantics.
- 2026-07-01: Live-tag cleanup: dynamic-family condition assembly now goes through one generic helper keyed by registry `output.condition_kind`, and homology-scope branch discovery now reads its root/hierarchy/fallback source from registry config instead of a fixed module-local root id.
- 2026-07-01: Validation cleanup: the simpler analysis-kind SQL requirements (`functional_derived_connections`, `functional_annotation_ranking`, `broad_homology_organism_tag_results`, `hgt_donor_results`) now come from semantic-registry validation config instead of only from the module’s handwritten validator block.
- 2026-07-01: Phase-4 start: expression scalar execution now uses a shared numeric aggregation helper for `average`, `percentile`, `min`, and `max` instead of embedding each statistic directly in the expression-specific executor, establishing the first reusable aggregation path under the `analysis` contract.
- 2026-07-01: Phase-4 follow-up: supported numeric scalar aggregations now also read registry-backed aggregation specs for metric labeling, so the first reusable execution slice depends on declarative aggregation metadata rather than only on hardcoded reducer branches.
- 2026-07-01: Phase-4 follow-up: grouped `count_distinct` aggregations used by current ranked genomics queries now also read registry-backed aggregation expression specs, so ranked count-style execution has started moving onto the same declarative aggregation layer as scalar reducers.
- 2026-07-01: Phase-4 follow-up: ranked grouped aggregations now also read registry-backed default ordering and extra evidence-column metadata, so shared row-shaping has started moving off analysis-kind-specific SQL builders too.
- 2026-07-01: Phase-4 follow-up: ortholog grouped threshold strategies now also read registry-backed grouped-metric evidence and `HAVING` specs, extending the shared execution layer beyond ranked counts into grouped filter metrics.
- 2026-07-01: Phase-4 follow-up: expression ranking now also reads registry-backed numeric value-expression, evidence-column, and ordering specs, so ranked numeric row outputs have joined the same declarative execution layer as ranked count outputs.
- 2026-07-01: Phase-4 follow-up: expression distributions now execute through a structured `distribution` analysis kind with registry-backed summary metrics, giving the execution layer its first deterministic non-scalar summary artifact.
- 2026-07-01: Phase-4 follow-up: expression comparisons now execute through a structured `comparison` analysis kind with registry-backed metric aliases, giving the execution layer its first deterministic comparison artifact on top of the shared expression-value path.
- 2026-07-01: Phase-4 follow-up: distribution/comparison artifact evidence fields now derive from the same registry-backed execution specs used to compute them, eliminating another hardcoded result-shape seam in the expression analysis builders.
- 2026-07-01: Phase-4 follow-up: comparison specs now support registry-driven metric bundles plus a declarative `difference_metric_alias`, so one comparison artifact can expose multiple computed metrics while still keeping a deterministic headline gap/winner field.
- 2026-07-01: Phase-4 completion for the current genomics families: deterministic summary outputs now emit a normalized `genomics-chat-result-v1` artifact payload, and non-tabular summary analyses now default to Python execution at analysis-normalization time instead of relying on per-analysis engine overrides.
- 2026-07-01: Phase-5 start for the current genomics families: explanatory summary/narrative prose can now be rendered from `genomics-chat-result-v1` artifacts for expression scalar/distribution/comparison outputs, and `/api/chat` now preserves `results`, `count`, and `artifact` for answer responses so summary artifacts stay inspectable end to end.
- 2026-07-01: Phase-5 follow-up: current ranked genomics analyses can now upgrade explanatory prompts into deterministic `ranked_summary` answer artifacts, including expression ranking and common-term/owner-count ranking families, so ranked outputs are no longer inherently table-only.
- 2026-07-01: Phase-5 interface follow-up: synthesized summary answers now preserve normalized presentation preferences end to end, and `/api/chat` exposes them as an explicit `presentation` contract instead of requiring clients to infer summary-vs-table availability from `intent` and artifact rows.
- 2026-07-01: Phase-5 consumer follow-up: the chat panel now renders answer responses through the normalized `presentation` contract, so summary-vs-table behavior is controlled by the same deterministic metadata on both the API and UI sides.
- 2026-07-01: Phase-5 inspectability follow-up: the chat panel now exposes raw `genomics-chat-result-v1` artifacts inline for answer-style responses, closing the current-family inspectability gap between API contract and user-visible surface.
- 2026-07-01: Phase-6 cleanup start: ortholog copy-count validation now uses one shared strategy/projection check instead of duplicating the same dataset-specific logic across multiple branches, and accepted-SQL metadata evidence enrichment now relies on structured `metadata_filters` analyses instead of reparsing prompt text at the enrichment step.
- 2026-07-01: Phase-6 cleanup follow-up: genomics result-type preference no longer duplicates core `gene`/`protein`/`transcript` regex inference inside the module, and HGT-donor result routing now reuses the registry-backed result-type rule instead of maintaining a second handwritten phrase matcher.
- 2026-07-01: Phase-6 cleanup follow-up: single-condition generic-tag and promoted-call analyses now consume the shared condition-builder dispatcher instead of invoking separate direct matcher paths, reducing another redundant message-to-condition interpretation seam inside the genomics module.
- 2026-07-01: Phase-6 cleanup follow-up: `effector_tag_filters` now uses the shared semantic-condition route analysis/compile helpers rather than its own bespoke route wrapper, with only the effector-family labeling pass still kept local because it depends on dynamic-family message interpretation.
- 2026-07-01: Phase-6 cleanup follow-up: scope/comparative/effector semantic-condition routes now also share one normalized synthesized-result contract (`sql` plus semantic trace/evidence metadata) instead of each route family relying on slightly different direct-call return shapes.
- 2026-07-01: Phase-6 cleanup follow-up: the remaining dynamic-family family-labeling logic is now factored into smaller reusable helpers (message-family selection plus flag-family matching) instead of one intertwined method, narrowing the last message-dependent handwritten boundary without changing the live discovery model.
- 2026-07-01: Aggregation cleanup: supported deterministic aggregation operations now execute through a registry-backed operation table, so scalar/distribution/comparison summaries no longer rely on a separate hardcoded `average`/`percentile`/`min`/`max` branch ladder in `genomics.py`, while legacy `numeric_scalar` label overrides remain compatible unless the newer operation spec overrides them explicitly.
- 2026-07-01: Phase-6 cleanup follow-up: the effector route now uses the same shared semantic-condition compile helper directly as the scope/comparative routes, and the dead effector-only wrapper/helper code was removed; the remaining effector-specific logic is now just family resolution over live dynamic-family matches.
- 2026-07-01: Phase-6 cleanup follow-up: effector family resolution now uses one registry-driven candidate-family precedence helper that merges message-triggered family cues with fallback precedence, instead of separate message-family and fallback helper stages. Coverage now also proves custom registry message phrases can steer collapse behavior when the matched live flags support it.
- 2026-07-01: Phase-6 cleanup follow-up: primary-organism selection for live scoped effector aliases is now registry-driven (`organisms.primary_selection.relationship_type`) instead of being hardcoded to `HAS_CHROMOSOME`, so the remaining runtime-owned organism logic is mostly the live alias collection itself rather than the selector rule.
- 2026-07-01: Phase-6 cleanup follow-up: homology-scope branch discovery now reuses the same shared `branch_tags` walker as dynamic-family tag discovery, removing another duplicated live-graph traversal path while keeping the active graph hierarchy as the runtime source of truth.
- 2026-07-01: Sample-data rebuild follow-up: rebuilt `sample_data/3_db/genomics_scn.db` and `sample_data/3_db/genomics_bison.db` from source packages. This also exposed and fixed an order-sensitive builder bug in tag-hierarchy seeding, so dataset-specific tag overrides that update a shared parent no longer depend on YAML merge insertion order.
- 2026-07-01: Phase-0 closeout: recorded which remaining genomics runtime behaviors are intentional steady-state ownership versus temporary bridges. The current line is that live graph facts stay runtime-owned, while wording-only guards, unreproducible binary fixes, and accepted-SQL rescue layers remain cleanup targets.
- 2026-07-01: Audit closeout: measured a representative no-model baseline on the rebuilt SCN sample DB. Current prompt payloads are roughly 3.1k approximate input tokens, with ~2.5k coming from the live schema/system block; deterministic orchestration latency is roughly 13-38 ms across the sampled prompt families before real model inference.
- 2026-06-30: Validation cleanup: validation for migrated ranking/metadata/expression families now begins from `analyze_request()` plus analysis-kind-specific checks instead of fully re-deriving those semantics from prompt-only branching, reducing the remaining parallel interpretation path.
- 2026-06-30: Validation cleanup: generic-tag, orthogroup-label, broad-homology-organism, direct `hgt_donor` result, broad-homology tag result, and ortholog copy-count checks now consume structured analysis data directly (condition signatures, homology organisms, owner/strategy/threshold) instead of rediscovering those semantics from prompt text inside `validation_error()`.
