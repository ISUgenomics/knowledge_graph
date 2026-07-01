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
- explicit gene/transcript/protein subset filtering for expression scalar summaries

Contract note:
- current genomics analyses are now normalized to a versioned in-code contract (`genomics-chat-analysis-v1`) before synthesis.
- the normalizer currently enforces core required fields and fills default `subject.selection_mode`, `execution.preferred_engine`, `execution.requires_live_schema`, and `presentation` flags.
- this is still a module-local contract layer, not yet a shared cross-domain base abstraction.

Effector-filter note:
- `effector_tag_filters` now carries explicit family classification in analysis/trace, such as `known` or `putative`, instead of leaving that distinction fully implicit in query synthesis.
- generic effector family collapse is now partly registry-driven: the grouping of broad matches into families such as `known`, `putative`, `dna`, or `protein` is derived from dynamic-family collapse config rather than only from handwritten module branching.
- effector evidence-column enrichment is now also registry-driven: alias/metadata-field projections for SCN/BCN effector prompts come from dynamic-family display rules rather than a module-local tag-id substring map.
- scoped-vs-generic effector alias selection is now registry-driven too: the match-group order and whether selection stops at the first non-empty group are configured in the dynamic-family definition rather than fixed in code.

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
