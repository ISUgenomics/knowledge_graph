# Genomics Chat Analysis Model

Status: draft
Scope: shared intermediate representation for genomics Explore chat

Implemented first slice:
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
- comparative/HGT semantic-condition entity filters
- direct HGT donor result queries
- broad-homology organism tag result queries
- ortholog copy-count result queries across `gene_counts` maps and live member-edge datasets
- expression ranking entity queries
- expression average / percentile scalar summaries
- expression distribution summaries
- expression comparison summaries
- explicit gene/transcript/protein subset filtering for expression scalar summaries

Contract note:
- current genomics analyses are now normalized to a versioned in-code contract (`genomics-chat-analysis-v1`) before synthesis.
- the normalizer currently enforces core required fields and fills default `subject.selection_mode`, `execution.preferred_engine`, `execution.requires_live_schema`, and `presentation` flags.
- this is still a module-local contract layer, not yet a shared cross-domain base abstraction.
- for the current genomics prompt families, this contract plus the registry-backed matcher/config layers now define the intended phase-2/3 architecture boundary; the remaining handwritten residue is primarily deterministic execution validation, not a parallel prompt interpretation model.

Effector-filter note:
- `effector_tag_filters` now carries explicit family classification in analysis/trace, such as `known` or `putative`, instead of leaving that distinction fully implicit in query synthesis.
- generic effector family collapse is now partly registry-driven: the grouping of broad matches into families such as `known`, `putative`, `dna`, or `protein` is derived from dynamic-family collapse config rather than only from handwritten module branching.
- effector evidence-column enrichment is now also registry-driven: alias/metadata-field projections for SCN/BCN effector prompts come from dynamic-family display rules rather than a module-local tag-id substring map.
- scoped-vs-generic effector alias selection is now registry-driven too: the match-group order and whether selection stops at the first non-empty group are configured in the dynamic-family definition rather than fixed in code.
- residual entity-name lookup is narrower than before: homology-organism matches, organism-name matches, and subset member extraction now use one shared registry-backed matcher helper path rather than separate prompt-entity loops with duplicated dedupe/filter logic.
- live promoted-entity discovery is narrower too: exclusion rules, synthesized aliases, and default count aliases for runtime-discovered promoted families now come from semantic-registry config instead of hardcoded expression-specific branches and inline alias assembly.
- semantic-condition consumption is narrower too: validation and accepted-sql evidence enrichment now read the same requested condition bundle used for fallback semantic matching, rather than each reconstructing prompt semantics independently.
- live tag-family discovery is narrower too: effector condition assembly now uses a generic dynamic-family condition helper, and homology-scope branch traversal now reads source-root configuration from registry metadata instead of assuming one fixed in-module root.
- validation is narrower too: several analysis kinds now declare their required SQL signatures in registry-backed validation config, leaving the remaining handwritten validator logic focused on dynamic thresholds, metadata values, and dataset-specific live checks.
- phase-4 execution work has started: expression scalar summaries now run through a shared numeric aggregation helper, and the currently supported scalar aggregation types are `average`, `percentile`, `min`, and `max`.
- supported numeric scalar aggregations now also have registry-backed execution metadata for metric labeling, which is the first step toward declarative aggregation specs rather than analysis-kind-specific reducer code.
- grouped `count_distinct` aggregations now also have registry-backed execution expressions for the currently migrated ranked-query families, which begins aligning row-based ranked execution with the same aggregation-spec layer.
- ranked grouped aggregations now also have registry-backed default ordering and extra evidence-column metadata for the currently migrated ranked-query families, which begins aligning row shaping with the same aggregation-spec layer.
- ortholog grouped threshold strategies now also have registry-backed grouped-metric evidence and `having` metadata, which begins aligning grouped filter metrics with the same aggregation-spec layer instead of analysis-kind-specific SQL assembly.
- expression ranking now also has registry-backed numeric value-expression, evidence-column, and ordering metadata, which begins aligning ranked numeric row outputs with the same aggregation-spec layer instead of a separate handwritten path.
- expression distributions now also use a structured `distribution` analysis kind with registry-backed summary-metric definitions, which is the first deterministic non-scalar summary artifact on top of the shared execution layer.
- expression comparisons now also use a structured `comparison` analysis kind with registry-backed metric aliases, which is the first deterministic comparison artifact on top of the shared expression-value execution path.
- distribution/comparison evidence fields now derive from the same registry-backed summary/comparison specs used for execution, so artifact shape is no longer duplicated in expression-specific analysis builders.
- comparison execution now supports registry-backed metric bundles plus a declarative choice of which metric drives the headline difference/winner fields, which narrows the remaining analysis-kind-specific summary shaping.
- deterministic summary outputs now also emit a normalized result artifact payload (`genomics-chat-result-v1`) that records analysis kind, result kind, artifact kind, rows, and artifact metadata separately from the user-facing prose answer.
- non-tabular summary analyses now normalize to Python execution by default (`scalar`, `distribution`, `comparison`, `narrative`) instead of relying on per-analysis overrides to avoid accidental SQL-first fallback.

Scope-filter note:
- evidence-plus-scope prompts now use `scope_tag_filters`, which makes requested scope tags and evidence families explicit in the analysis/trace instead of leaving them inside the broader semantic-condition bucket. This includes mixed cases such as HGT donor plus broad parasitism, not only homology-only prompts.

Comparative-scope note:
- prompts that combine scope tags with ortholog-style comparative constraints now use `comparative_scope_filters`, separating that recurring demo shape from the remaining generic semantic-condition path.

Evidence-orthogroup note:
- prompts that combine protein evidence with a named orthogroup filter now use `evidence_orthogroup_filters`, making that recurring HGT/comparative pattern explicit in the analysis/trace.

Evidence-ortholog-member note:
- prompts that combine protein evidence with ortholog-member constraints now use `evidence_ortholog_member_filters`, including broad-homology + BCN-ortholog style prompts. This narrows the remaining residual multi-condition bucket further without introducing another near-duplicate analysis kind.

Evidence-homology-organism note:
- prompts that combine protein evidence with explicit requested homology organisms now use `evidence_homology_organism_filters`, making homolog-organism constraints part of the primary analysis model instead of hidden builder state.

Residual combinatorial note:
- the remaining mixed combinations now route through an explicit `multi_condition_filters` analysis kind. This is intended as the primary structured path for genuinely cross-family mixes, such as promoted-call plus HGT evidence, rather than as an implicit fallback bucket.

Validation boundary note:
- some validation logic intentionally remains code-owned even after the semantic refactor. the remaining handwritten checks mostly enforce runtime-dependent execution details such as threshold application, strategy selection, resolved metadata values, and required evidence projections.
- those checks are no longer treated as phase-2/3 routing residue unless they are re-parsing prompt semantics independently of `analysis` or the requested condition bundle.

Phase-4 boundary note:
- for the current genomics prompt families, phase 4 is now effectively complete in the sense intended by this refactor: structured analyses deterministically compile to row queries or Python-side summary execution, and summary outputs now expose normalized artifacts rather than only ad hoc prose/result rows.
- this does not mean the execution layer is now a shared cross-domain abstraction; it remains genomics-local, with phase 5 still responsible for broader presentation/narrative concerns.

Phase-5 start note:
- current genomics summary analyses can now render explanatory narrative prose from the normalized result artifact itself rather than only from analysis-kind-specific string assembly, which is the first concrete phase-5 presentation slice on top of `genomics-chat-result-v1`.
- `/api/chat` answer responses now also preserve `results`, `count`, and `artifact` for summary-style outputs, so the raw deterministic artifact remains inspectable alongside the rendered prose.
- current ranked genomics analyses can now also upgrade explanatory prompts into deterministic `ranked_summary` answer artifacts, so ranked rows are no longer inherently table-only when the prompt asks for a summary/explanation.
- synthesized summary answers now also preserve normalized presentation metadata (`primary_view`, `available_views`, preference flags, summary style, artifact kind, requested result kind), and `/api/chat` returns that `presentation` block directly so UI consumers can decide summary-vs-table behavior without re-deriving it from artifact shape.
- the chat UI now consumes that `presentation` block directly for answer responses, which keeps summary/table rendering policy aligned with the deterministic analysis/execution layer instead of introducing a second UI-local heuristic.
- the chat UI now also exposes the raw normalized result artifact inline for answer responses, so `genomics-chat-result-v1` remains inspectable at the same surface where the rendered summary is shown.

Phase-6 cleanup note:
- one of the remaining validation/evidence cleanup seams is now reduced: ortholog copy-count validation uses a shared strategy/projection check, and metadata evidence enrichment for accepted SQL now prefers the structured `metadata_filters` analysis payload rather than reparsing metadata intent from prompt text at the final enrichment step.
- result-type preference cleanup has also started: the module now relies on registry-backed result-type rules plus the shared generic entity-type detection in `ChatToSQL`, instead of separately regex-inferring core `gene`/`protein`/`transcript` result types inside genomics-local code.
- another condition-routing cleanup seam is now reduced: generic-tag and promoted-call single-condition analyses go through the shared condition-builder dispatcher, so those analyses no longer maintain a second direct message-matcher entry point separate from the broader semantic-condition bundle path.
- the effector-tag route is now also mostly on the shared semantic-condition route framework; the remaining local piece is just the post-route family labeling step that maps matched dynamic-family conditions back to higher-level effector families like `known` or `putative`.
- the semantic-condition route helper now also owns the normalized synthesized return shape for those route families (`sql`, `semantic_trace`, `evidence_columns`), which removes another small but real contract divergence between scope/comparative/effector direct synthesis paths.
- the remaining dynamic-family family-labeling boundary is now smaller as well: message-family selection and flag-family matching are separated into reusable helpers, leaving the live/data-derived decision itself intact but less entangled with surrounding route logic.

Current intentional runtime boundary:
- live organism alias selection remains runtime-owned because the active graph still determines which organism is “primary” versus “secondary”
- live scope/effector tag discovery remains runtime-owned because the active graph hierarchy is still the source of truth for those branch members
- final family labels over dynamic-family matches remain runtime-owned because they still depend on prompt phrasing applied to live-derived flag combinations

Everything else should now be presumed declarative-first unless there is a concrete reason it cannot be represented safely in registry/source/build-time semantics.

## Purpose

Define one structured analysis shape that sits between:
- user natural-language prompts
- deterministic SQL/Python execution
- UI result rendering

The same model should support:
- entity tables
- scalar/stat outputs
- ranked lists
- comparisons
- narrative summaries grounded in computed results

## Core Principles

- The LLM maps language to intent, not to final SQL details.
- Execution must be deterministic and inspectable.
- Evidence projection is part of the analysis contract, not a post-hoc patch.
- Dataset-specific semantics should enter through explicit schema/config overrides.
- One analysis should be renderable as both raw result artifacts and user-facing summaries.
- Result-type preference should increasingly come from semantic config, with module code retaining only the most generic language heuristics.

## Draft Shape

```yaml
analysis:
  domain: genomics
  intent: filter | rank | aggregate | compare | summarize | correlate
  requested_result_kind: entity_rows | ranked_rows | scalar | distribution | comparison | narrative
  subject:
    entity_type: gene | transcript | protein | orthogroup | annotation_term | prediction_call | localization_call | tag | hgt_donor
    selection_mode: explicit_ids | inferred_type | semantic_family
    ids: []
  filters:
    - type: relation_filter | tag_filter | promoted_call_filter | metadata_filter | path_filter | organism_filter
      owner_type: protein
      rel_type: HAS_PREDICTION
      target_type: prediction_call
      target_id: transmembrane_domain
  aggregations:
    - type: count | count_distinct | average | percentile | min | max
      field: null
      percentile: null
      over: target_entities | numeric_field
  dimensions:
    group_by: []
    order_by: []
    limit: null
  paths:
    - source_type: gene
      via_type: transcript
      target_type: protein
      rel_chain: [HAS_TRANSCRIPT, TRANSLATED_TO]
  evidence:
    include:
      - alias: matched_call
      - alias: matched_tag
      - alias: orthogroup_label
      - alias: hgt_donor
  execution:
    preferred_engine: sql | python | hybrid
    requires_live_schema: true
  presentation:
    prefer_table: true
    prefer_summary: false
    summary_style: concise | comparative | explanatory
```

## Minimal Required Fields

Every analysis should resolve at least:
- `domain`
- `intent`
- `requested_result_kind`
- `subject.entity_type`
- one of:
  - `filters`
  - `aggregations`
  - `paths`

## Operation Categories

### Filter operations
- filter by promoted call
- filter by tag
- filter by evidence relation
- filter by metadata field/value
- filter by organism
- filter by path membership

### Ranking operations
- rank entities by annotation count
- rank terms/calls by owner count
- rank entities by expression under a named condition

### Aggregate/stat operations
- count distinct owners
- average expression
- percentile of expression
- distribution summaries

### Comparison operations
- compare subsets
- compare conditions
- compare organisms or evidence groups

## Evidence Semantics

Evidence is part of the analysis plan, not a UI-only concern.

Examples:
- promoted-call filter should request `matched_call`
- generic tag filter should request `matched_tag`
- HGT + orthogroup query should request `hgt_donor` and `orthogroup_label`
- common annotation term ranking should request namespace/category when useful

## Mapping From Current Prompt Families

Examples:

- `select proteins predicted as transmembrane domains`
  - intent: `filter`
  - result kind: `entity_rows`
  - subject: `protein`
  - filter: `promoted_call_filter(HAS_PREDICTION -> prediction_call:transmembrane_domain)`
  - evidence: `matched_call`, `matched_call_category`

- `what is the most common GO term`
  - intent: `rank`
  - result kind: `ranked_rows`
  - subject: `annotation_term`
  - filter: `metadata_filter(namespace=go, category=functional_annotation)`
  - aggregation: `count_distinct(owner entities)`

- `what is the 90th percentile of expression in Egg stage`
  - intent: `aggregate`
  - result kind: `scalar`
  - subject: `transcript`
  - path: `transcript -> HAS_EXPRESSION_SUMMARY -> expression_measure`
  - filter: `condition label = Egg`
  - aggregation: `percentile(90)`

## Migration Notes

Initial implementation does not need to cover every current prompt family at once.

Suggested order:
1. promoted-call filters
2. common promoted/annotation rankings
3. annotation owner rankings
4. HGT/orthogroup comparative evidence
5. expression stats and summaries

## Open Questions

- Validation is now expected to consume the same normalized `analysis` object for condition signatures, requested homology organisms, and ortholog-count strategy/threshold semantics rather than re-parsing those prompt families separately.
- Should evidence aliases be standardized globally across modules?
- Where should path templates live: registry, module config, or live schema adapter?
- How should explicit entity lists from NL be represented?
- Should narrative summaries be generated from a normalized result artifact schema separate from `analysis` itself?
