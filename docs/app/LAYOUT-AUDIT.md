# Layout Audit

## Scope

Audit of the current graph layout pipeline after the Timeline refactor.

Files inspected:

- `APP/kgx/ui/components/graph/graph.js`
- `APP/kgx/ui/index.html`
- `APP/kgx/api/routes_layout.py`
- `APP/kgx/db/queries.py`
- `APP/kgx/config/loader.py`
- `APP/config/default.yaml`

## Current Layout Entry Points

The active arrangement is chosen from the top-bar layout dropdown in
`APP/kgx/ui/index.html`.

The dropdown emits:

- `layout:change { layout }`

The graph component handles that event in:

- `APP/kgx/ui/components/graph/graph.js`

Before switching arrangements, the graph clears custom layout forces and any
Timeline-only hidden state via `clearCustomForces()`.

## Current Layout Types

### Force

- standard force-directed graph
- driven by the force settings panel and `force:update`

### Cluster

- custom app layout
- groups nodes by `_group` / type
- positions type centroids around a circle
- uses a custom D3 force toward those centroids

### Timeline

Timeline is now a deterministic, config-backed arrangement rather than a soft
`x` hint.

Current behavior:

- fetches Timeline profile and detected candidates from:
  - `GET /api/layout/timeline/options`
- resolves:
  - active `anchor_type`
  - active `order_field`
  - optional profile overrides from config / session
- fetches anchor values from the DB for the resolved anchor type + order field
- computes deterministic anchor targets:
  - order value on `x`
  - same-value ties spread on `y`
  - anchor base on `z`
- assigns every visible non-tag node to one primary anchor using visible graph
  structure
- places secondary nodes in semantic bands above anchors
- places tag-like nodes in hierarchy-aware tag bands
- pins solved `x`, `y`, and `z` targets in the Timeline force

This is not a generic D3 force layout with one timeline bias anymore. It is a
solved arrangement that uses force only to settle around explicit targets.

### UMAP

- custom app + backend route
- uses precomputed positions from `/api/layout/umap/*`
- applies them via fixed `fx/fy/fz`

### Hierarchical / DAG

- any layout not handled by explicit custom branches falls back to:
  - `graphInstance.dagMode(layout)`
- still library-driven
- not part of the Timeline refactor

## Current Timeline Config Surface

Timeline defaults now come from `ui.layouts.timeline`.

Current profile fields in use:

- `anchor_type`
- `order.field_candidates`
- `order.direction`
- `anchors.z`
- `anchors.x_step`
- `anchors.same_value_y_step`
- `assignment.primary_anchor_rule`
- `layers`
- `unanchored.mode`
- `detection.detected_type_min_count`
- `featured_top_ids`

The frontend receives that profile through:

- `/api/layout/timeline/options`

## Current Timeline Data Model

Timeline operates on the currently loaded graph, not a separate raw timeline
dataset.

Important implications:

- Timeline respects the active projection (`explore` / `display`)
- secondary-node assignment is driven by visible graph connectivity
- tag hierarchy placement depends on hierarchy edges plus tag metadata
- Explore semantics still depend on backend projection rules in
  `APP/kgx/db/queries.py`

## Current Timeline Placement Model

### 1. Anchor spine

- anchors are nodes of the resolved `anchor_type`
- anchor order values come from the selected field
- anchors are placed deterministically on:
  - `x`: ordered scalar/date value
  - `y`: tie spreading within equal order value
  - `z`: anchor base layer

### 2. Primary-anchor assignment

- non-anchor visible nodes choose one primary anchor
- assignment uses visible-neighbor anchor counts
- rule currently defaults to `strongest_then_earliest` unless overridden by
  profile

### 3. Secondary bands

- secondary nodes are bucketed by:
  - assigned anchor
  - layer `z`
  - direct vs indirect relation to the anchor
- first-band direct buckets are aligned to the anchor row
- bucket contents are solved iteratively with explicit `x/y/z` targets

### 4. Tag hierarchy bands

Tag-like nodes use a generic four-layer semantic model:

- `top`
- `domain`
- `field`
- `topic`

Selection of the `top` band is config-driven through `featured_top_ids`.

Tags are placed from:

- hierarchy category metadata when available
- fallback generic tag-category inference otherwise

### 5. Dense bucket solving

Dense secondary buckets are arranged by local graph structure, not by
dataset-specific ids.

Current generalized rules include:

- preferred local core selection from visible neighbors
- first-band anchor-core alignment for direct buckets
- compact inner-shell placement
- outer-shell placement around connected inner nodes
- sibling repulsion and nearest-core / nearest-inner constraints
- tight `x` containment inside the current timeline anchor bin

## Current Visibility Behavior In Timeline

Timeline has layout-specific visibility handling.

Current behavior:

- nodes/edges can receive `__timelineHidden`
- this is used primarily for unanchored nodes when
  `unanchored.mode = hide_or_dim`
- `refreshVisibility()` and projection snapshots use:
  - base hidden flags
  - Timeline-only hidden flags

This means Timeline can hide de-anchored nodes without changing the underlying
global filters permanently.

## Current Filter / Recompute Behavior

Timeline now recomputes through one post-filter path.

When sidebar or visibility actions occur:

- hidden flags are recomputed
- if current layout is Timeline:
  - `applyTimelineLayout()` runs directly
- otherwise:
  - generic visibility refresh + projection snapshot run

This avoids the earlier intermediate render state where non-Timeline visibility
would flash before Timeline recomputed.

## Generalization Status

What is generalized:

- no dataset-specific ids or names in the Timeline layout solver
- no Nobel-specific placement logic in `graph.js`
- module-specific top-tag behavior comes from config, not code
- anchor detection and field selection are generic
- bucket solving uses visible graph structure, not hardcoded entity ids

What remains intentionally semantic:

- generic timelineable type heuristics like:
  - `person`
  - `organization`
  - tag-like types
- generic tag hierarchy bands:
  - `top`, `domain`, `field`, `topic`
- generic field aliases like:
  - `award_year -> year`

These are model assumptions, not dataset-specific hacks.

## Remaining Gaps / Future Refactor Targets

Timeline arrangement is implemented and working, but settings architecture is
not yet generalized.

Main follow-up work:

1. split shared graph settings from per-layout settings
2. replace the Force-only settings popup with:
   - shared `Graph` section
   - active-layout section
3. persist last-used layout settings separately from named presets
4. document/reset settings scopes cleanly:
   - shared graph
   - per-layout
   - preset snapshots
