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
- [ ] Rebuild sample DBs from corrected source/schema where needed
- [ ] Mark which current repairs are temporary bridges vs acceptable steady-state behavior

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
  - effector prompts now use a dedicated `effector_tag_filters` analysis path, and most family/selection/display semantics are registry-driven, but the live branch/tag expansion itself is still module-owned
  - evidence + scope prompts now use `scope_tag_filters`, including mixed cases like HGT donor plus broad parasitism
  - comparative scope + ortholog prompts now use `comparative_scope_filters`
  - protein-evidence + named orthogroup prompts now use `evidence_orthogroup_filters`
  - protein-evidence + ortholog-member prompts now use `evidence_ortholog_member_filters`
  - protein-evidence + requested homology-organism prompts now use `evidence_homology_organism_filters`
  - `multi_condition_filters` remains an explicit primary analysis kind for genuinely mixed cross-family combinations rather than an implied fallback bucket
  - scalar/stat outputs are now started, but only for expression average / percentile summaries
  - generic scalar/stat result rendering is not yet generalized across domains or metric families

### Phase 3. Move semantics from code to data/registry

- [ ] Represent more aliases declaratively
- [ ] Represent promoted families declaratively from live schema where possible
- [ ] Represent result-type preferences declaratively
- [ ] Represent supported aggregations declaratively
- [ ] Reduce special-case prompt branching in `genomics.py`
- [ ] Make dataset-specific semantics explicit in source schema/config, not hidden in runtime fallbacks

Current Phase 3 progress:
- result-type preference/suppression now starts from registry rules for donor/tag/comparative/ortholog cases
- analysis routing/synthesis dispatch now uses declarative handler tables instead of one manual branch chain

### Phase 4. Deterministic execution layer

- [ ] Compile structured analyses to SQL for row-based and aggregation outputs
- [ ] Add Python-side deterministic stats where SQL is awkward
- [ ] Support percentiles, averages, distributions, comparisons, and ranked summaries
- [ ] Ensure execution artifacts can be reused by both table and summary outputs

### Phase 5. Multi-output chat responses

- [ ] Support scalar/stat responses in addition to tables
- [ ] Support ranked summaries grounded in computed outputs
- [ ] Support narrative summaries over deterministic result artifacts
- [ ] Decide how UI exposes table vs summary vs both
- [ ] Keep the raw SQL/result artifact inspectable

### Phase 6. Cleanup and simplification

- [ ] Retire redundant prompt-family repairs once covered by the structured model
- [ ] Remove genomics-only special cases that become declarative
- [ ] Shrink shared/core logic back to generic orchestration primitives
- [ ] Audit performance and token usage before/after refactor
- [ ] Remove temporary bridges once demos are stable on the primary path

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
- 2026-06-30: Semantic-spec cleanup: annotation-namespace alias specs and common-promoted entity specs now come from the semantic registry instead of static module lists, so those selection vocabularies are overrideable and no longer duplicated in code.
- 2026-06-30: Validation cleanup: validation for migrated ranking/metadata/expression families now begins from `analyze_request()` plus analysis-kind-specific checks instead of fully re-deriving those semantics from prompt-only branching, reducing the remaining parallel interpretation path.
- 2026-06-30: Validation cleanup: generic-tag, orthogroup-label, broad-homology-organism, direct `hgt_donor` result, broad-homology tag result, and ortholog copy-count checks now consume structured analysis data directly (condition signatures, homology organisms, owner/strategy/threshold) instead of rediscovering those semantics from prompt text inside `validation_error()`.
