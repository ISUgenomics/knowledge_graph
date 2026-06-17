# Genomics Graph Model

This document is the canonical design spec for the genomics module.

It defines:
- which node families exist
- which relationships are canonical in the stored graph
- which relationships are derived only in projections
- what `Display` and `Explore` are supposed to mean
- how the markdown vault should mirror the same model

The intent is to keep the genomics module on one straight semantic path and avoid fallback to older ad hoc projection rules.

## Principles

1. The stored graph must preserve real semantics with minimal redundancy.
2. `Display` should show a broad view of the real model, not a provenance star.
3. `Explore` variants must answer analytical questions, not just hide arbitrary types.
4. Derived shortcut edges may exist in projections, but not as canonical stored edges.
5. `dataset` is provenance/container structure, not biological backbone.
6. `organism` is the biological root.

## Node Categories

The genomics module uses four semantic categories.

### 1. Backbone

Intrinsic biological entities:
- `organism`
- `chromosome` or `scaffold` (planned)
- `gene`
- `transcript`
- `protein`

### 2. Comparative

Cross-entity or cross-organism grouping:
- `orthogroup`
- homology entities later (`ortholog_group`, `paralog_group`, etc.)

These are not backbone and are not generic tags.

### 3. Measurements

Observed or computed biological state tied to backbone nodes:
- `expression_measure`
- `contrast_definition`
- `localization_call`
- `prediction_call`

### 4. Ontology

Controlled semantic classification and hierarchy:
- `annotation_term`
- `tag`

Examples:
- GO terms
- InterPro/Pfam/SMART/PANTHER/FunFam terms when treated as ontology-like concepts
- curated effectors / functional grouping tags

## Canonical Stored Backbone

The backbone is:

- `dataset -> ABOUT_ORGANISM -> organism`
- `gene -> FROM_ORGANISM -> organism`
- `gene -> IN_DATASET -> dataset`
- `gene -> HAS_TRANSCRIPT -> transcript`
- `transcript -> TRANSLATED_TO -> protein`

Planned extension:

- `organism -> HAS_CHROMOSOME -> chromosome`
- `chromosome -> HAS_GENE -> gene`

## Canonical Stored Edge Rules

### Provenance

- Keep `dataset` as a real stored node.
- Keep `gene -> IN_DATASET -> dataset`.
- Do not attach transcripts, proteins, orthogroups, measurements, or ontology nodes directly to `dataset` by default.

Reason:
- direct dataset links on every node turn `Display` into a noisy hub
- provenance remains queryable without distorting the graph

### Backbone

- Store `gene -> transcript`
- Store `transcript -> protein`
- Do not store `gene -> protein` canonically

Reason:
- `gene -> protein` is derivable
- storing it collapses transcript/isoform logic
- the transcript layer must remain meaningful

### Comparative

- Store `gene -> orthogroup`
- future homology entities should connect at the correct biological level, usually from `gene`

Do not flatten comparative entities into tags.

### Measurements

Attach measurements at the level where they are defined.

Current module rules:
- `transcript -> HAS_EXPRESSION_SUMMARY -> expression_measure`
- `transcript -> HAS_EXPRESSION_CONTRAST -> contrast_definition`
- `contrast_definition -> CONTRAST_SOURCE -> expression_measure`
- `contrast_definition -> CONTRAST_TARGET -> expression_measure`
- `protein -> HAS_LOCALIZATION -> localization_call`
- `protein -> HAS_PREDICTION -> prediction_call`

### Ontology

Attach ontology terms to the nearest valid biological layer:
- `protein -> HAS_ANNOTATION -> annotation_term`
- `gene|transcript|protein -> TAGGED -> tag` only when the tag truly classifies that node

Hierarchy stays within ontology:
- `tag -> BROADER -> tag`

Do not use ontology hierarchy as a substitute for comparative structure or measurement structure.

## Stored Edge Matrix

Allowed canonical edges now or by direct planned extension:

- `dataset -> organism`
- `organism -> chromosome` planned
- `chromosome -> gene` planned
- `gene -> dataset`
- `gene -> organism`
- `gene -> transcript`
- `gene -> orthogroup`
- `transcript -> protein`
- `transcript -> expression_measure`
- `transcript -> contrast_definition`
- `protein -> annotation_term`
- `protein -> localization_call`
- `protein -> prediction_call`
- `contrast_definition -> expression_measure`
- `tag -> tag`
- typed nodes -> `tag` where classification is real

Disallowed as canonical stored shortcuts:

- `gene -> protein`
- `dataset -> transcript`
- `dataset -> protein`
- `dataset -> orthogroup`
- `dataset -> expression_measure`
- `dataset -> contrast_definition`
- `dataset -> annotation_term`
- `dataset -> localization_call`
- `dataset -> prediction_call`
- generic all-to-all similarity without a defined semantic basis

## Display Projection

`Display` should be the broad all-in-one view of the real model, but with meaningful defaults.

Expected emphasis:
- show biological backbone
- show comparative branch
- show measurement branch
- show ontology branch

Default visibility guidance:
- `organism`: visible
- `dataset`: hidden by default unless provenance mode is active
- `gene`, `transcript`, `protein`: visible
- measurement and ontology nodes: visible when present
- tags with only broad grouping value may be reduced if needed, but not by inventing fake hierarchy

`Display` is not supposed to be a dataset-centered hub.

## Explore Variants

`Explore` variants must be defined by analytical question.

They are not just raw graph minus a few types.

### Backbone

Goal:
- inspect structural biological organization

Visible:
- `organism`
- `chromosome` when available
- `gene`
- `transcript`
- `protein`

Hidden or reduced:
- most ontology
- most measurements
- most comparative nodes

Connection layers:
- stored edges: `FROM_ORGANISM`, `HAS_TRANSCRIPT`, `TRANSLATED_TO`
- no derived shortcuts by default

### Gene-Centric

Goal:
- understand gene neighborhoods and downstream biological consequences

Visible:
- `organism`
- `gene`
- `protein`
- `orthogroup`

Connection layers:
- stored edges: `FROM_ORGANISM`, `BELONGS_TO_ORTHOGROUP`
- derived projection edges: `GENE_PRODUCT` via `gene -> transcript -> protein`
- optional mediated similarity: `SHARES_ORTHOGROUP`

Rationale:
- keep gene as the analytical anchor
- preserve family structure through orthogroups
- collapse transcript mediation only where it helps readability

### Transcript-Centric

Goal:
- study isoform-level and expression-linked behavior

Visible:
- `organism`
- `gene`
- `transcript`
- `protein`
- `expression_measure`
- `contrast_definition`

Connection layers:
- stored edges: `FROM_ORGANISM`, `HAS_TRANSCRIPT`, `TRANSLATED_TO`
- stored measurement edges: `HAS_EXPRESSION_SUMMARY`, `HAS_EXPRESSION_CONTRAST`
- stored contrast endpoints: `CONTRAST_SOURCE`, `CONTRAST_TARGET`

Rationale:
- transcript remains explicit because expression is defined there
- this is the canonical view for isoform-aware expression interpretation

### Protein-Centric

Goal:
- inspect function, localization, domains, and effector evidence

Visible:
- `organism`
- `gene`
- `protein`
- `annotation_term`
- `localization_call`
- `prediction_call`
- selected ontology tags

Connection layers:
- stored edges: `FROM_ORGANISM`, `HAS_ANNOTATION`, `HAS_LOCALIZATION`, `HAS_PREDICTION`
- stored ontology edges: `TAGGED`, `BROADER`
- derived projection edges: `GENE_PRODUCT` via `gene -> transcript -> protein`
- optional mediated similarity: `SHARES_PROTEIN_FUNCTION`

Rationale:
- function and evidence attach at the protein layer
- transcript mediation may be collapsed here because isoform structure is not the primary question

### Comparative

Goal:
- explore homology and family structure

Visible:
- `organism`
- `chromosome`
- `gene`
- `protein`
- `orthogroup`
- `bcn_gene`
- `comparative_hit`
- `tag` from the homology-scope ontology subtree

Connection layers:
- stored scaffold edges: `HAS_CHROMOSOME`, `HAS_GENE`, `BELONGS_TO_ORTHOGROUP`, `HAS_BCN_MEMBER`
- stored external root edge: `FROM_ORGANISM` for `bcn_gene -> organism`
- protein evidence edges: `HAS_BCN_HIT`, `HAS_NEMATODE_HIT`, `HAS_BROAD_HOMOLOGY_HIT`
- ontology edges: `TAGGED`, `BROADER` for the homology-scope subtree
- optional mediated similarity: `SHARES_ORTHOGROUP`

Rationale:
- comparative structure is its own branch, not ontology and not backbone
- orthogroup remains the family container
- explicit BCN family members and protein-hit evidence are not the same thing
- `bcn_gene` carries external comparative gene members from orthogroup-side source columns
- `comparative_hit` carries BLASTP-style protein-hit evidence from BCN, nematode, and broad best-hit columns
- broader comparative breadth is represented by homology-scope tags so the comparative projection can show specific hits together with cyst nematode / nematode / broad strata
- only true ortholog collection members get organism roots; generic hit evidence stays unrooted apart from comparative scope

### Expression-Centric

Goal:
- inspect stage progression, contrasts, and transcript sharing patterns

Visible:
- `organism`
- `gene`
- `expression_measure`
- `contrast_definition`

Connection layers:
- stored edges: `FROM_ORGANISM`, `CONTRAST_SOURCE`, `CONTRAST_TARGET`
- derived projection edges:
  - `GENE_EXPRESSION_MEASURE` via `gene -> transcript -> expression_measure`
  - `GENE_EXPRESSION_CONTRAST` via `gene -> transcript -> contrast_definition`

Rationale:
- keep the stage and contrast layer explicit
- collapse transcript mediation only for the gene-facing projection, not in the stored graph
- preserve exact contrast direction through source/target endpoints

### Provenance

Goal:
- inspect sample membership and biological source without scientific overlays

Visible:
- `dataset`
- `organism`
- `gene`

Connection layers:
- stored edges: `IN_DATASET`, `ABOUT_ORGANISM`, `FROM_ORGANISM`

Rationale:
- this is where dataset belongs when surfaced
- provenance remains available without dominating scientific views

## Projection Configuration Principle

`Explore` presets should be declared positively.

That means each preset should define:
- which node families are visible
- which stored relationship families are intentionally included
- which projection-only derived edges are added

Do not define a genomics preset mainly by a long skip list.
If a relationship is part of the view's meaning, include it explicitly.

Visible:
- `transcript`
- `expression_measure`
- `contrast_definition`
- `gene` optionally
- expression-relevant ontology only

Important:
- direct contrast-to-summary links must stay visible
- contrast endpoints must follow canonical direction

### Provenance

Optional only.

Goal:
- inspect export/sample/build lineage

Visible:
- `dataset`
- `organism`
- optionally `gene`

This is the right place for dataset visibility when provenance matters.

## Derived Projection Edges

Projection-time derived edges are allowed only when they improve readability without changing meaning.

Examples of acceptable derived edges:
- optional `gene -> protein` in a projection that explicitly collapses transcript detail
- orthogroup-mediated peer links in comparative exploration
- annotation-context or expression-context links only when clearly labeled as derived

Rules:
- do not store derived shortcuts as canonical edges
- derived edges must be projection-specific and explainable
- if a derived edge hides important biology, do not use it

## Layout Intent

### Timeline

Use for ordered biological progression:
- developmental stages
- condition sequences
- contrast interpretation through stage anchors

Do not use chromosome order as timeline order.

### Locus-Aware Layout

Future chromosome/scaffold layouts should use genomic coordinates and chromosome grouping, not the timeline model.

## Vault Structure

The rendered markdown vault under `sample_data/2_vault/genomics/` should mirror the same categories.

Current folders:
- `organisms/`
- `datasets/`
- `genes/`
- `transcripts/`
- `proteins/`
- `orthogroups/`
- `expression/`
- `contrasts/`
- `annotations/`
- `localizations/`
- `predictions/`
- `tags/`

The vault is a generated view of the graph, not a separate model.

## Migration Rules

When adding a new genomics node type, answer these before implementation:

1. Which category does it belong to: backbone, comparative, measurements, or ontology?
2. What is its canonical attachment point?
3. Is it stored or only derived in projections?
4. Should it be visible in `Display` by default?
5. Which Explore variant actually benefits from it?
6. Does it need hierarchy, and if so, what kind of hierarchy?

If those answers are not clear, do not add the type yet.

## Current Direction

This module intentionally moves away from the first genomics sketch where:
- `dataset` over-connected the graph
- Explore presets were mostly type-pruning
- category boundaries between comparative, measurement, and ontology concepts were blurred

The maintained direction is:
- organism-rooted backbone
- semantics-first stored graph
- analytical Explore variants
- no return to ad hoc all-to-all or dataset-hub modeling
