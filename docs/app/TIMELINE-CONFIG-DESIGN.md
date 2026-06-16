# Timeline Config Design

## Purpose

This document now describes the Timeline model that is implemented today, plus
the narrow config surface it currently uses.

It is no longer a pure pre-implementation design note.

## Implemented Timeline Model

Timeline is an anchor-based arrangement.

The current pipeline is:

1. read the default Timeline profile from `ui.layouts.timeline`
2. fetch detected timeline candidates from the backend
3. resolve active `anchor_type` and `order_field`
4. place anchor nodes deterministically on the timeline spine
5. assign visible non-anchor nodes to one primary anchor
6. place secondary nodes in semantic bands above anchors
7. place tag nodes in hierarchy-aware tag bands
8. pin the solved coordinates in the Timeline force

## Current Backend / UI Contract

Frontend Timeline options are loaded from:

- `GET /api/layout/timeline/options`

Returned payload:

- `profile`
- `candidates`
- `detected_type_min_count`

This allows the UI to use:

- module defaults from config
- detected runtime candidates from the current DB

## Current Config Placement

Timeline defaults live under:

```yaml
ui:
  layouts:
    timeline:
      ...
```

This is module-level config, not DB-stored state.

## Current Supported Config Fields

### `anchor_type`

Example:

```yaml
anchor_type: award
```

Meaning:

- node type that forms the deterministic timeline spine

### `order.field_candidates`

Example:

```yaml
order:
  field_candidates: [award_year]
```

Meaning:

- preferred logical order fields for the chosen anchor type
- frontend resolves aliases against detected backend fields

Current alias support in UI includes:

- `award_year -> year`
- `publication_year -> year`
- `event_year -> year`
- `award_date -> date`

### `order.direction`

Example:

```yaml
order:
  direction: asc
```

Meaning:

- controls ordering of anchor groups on `x`

### `anchors.z`

Example:

```yaml
anchors:
  z: 0
```

Meaning:

- base `z` layer for anchor nodes

### `anchors.x_step`

Example:

```yaml
anchors:
  x_step: 190
```

Meaning:

- spacing between adjacent anchor order values

### `anchors.same_value_y_step`

Example:

```yaml
anchors:
  same_value_y_step: 110
```

Meaning:

- vertical tie spread for anchors with the same order value

### `assignment.primary_anchor_rule`

Example:

```yaml
assignment:
  primary_anchor_rule: strongest_then_earliest
```

Meaning:

- how non-anchor nodes choose one primary placement anchor

Current implemented rule family:

- strongest visible anchor neighborhood first
- then earliest/latest tie-break depending on rule text

### `layers`

Example:

```yaml
layers:
  person:
    z: 120
  organization:
    z: 240
```

Meaning:

- optional per-type explicit `z` overrides

If absent, the UI falls back to generic type/category heuristics.

### `unanchored.mode`

Example:

```yaml
unanchored:
  mode: hide_or_dim
```

Current implemented behavior:

- `hide_or_dim`
  - unanchored nodes/tags receive Timeline-only hidden flags
- otherwise
  - unanchored nodes are placed into fallback buckets

Note:
- current implementation hides rather than visually dims

### `detection.detected_type_min_count`

Example:

```yaml
detection:
  detected_type_min_count: 1
```

Meaning:

- minimum entity-type count for backend timeline candidate detection

### `featured_top_ids`

Example:

```yaml
featured_top_ids: [nobel-prize]
```

Meaning:

- config-selected ids that should use the `top` tag band
- this is module-specific config, not a hardcoded UI special case

## Current Generic Layer Model

Timeline currently assumes a generic semantic band model.

Entity-like bands:

- anchor band
- person-like band
- organization-like band
- fallback secondary band

Tag bands:

- `top`
- `domain`
- `field`
- `topic`

This is intentionally generic across modules, though the exact `z` constants
are still frontend-defined today.

## Current Dense Bucket Model

For secondary nodes within one anchor/layer bucket, the current solver uses:

- visible-neighbor-derived local core selection
- direct vs indirect bucket role
- compact inner-shell placement
- outer-shell placement around connected inner nodes
- sibling repulsion
- nearest-core / nearest-inner constraints
- strict containment inside the current anchor `x` band

This is generalized from graph structure, not from dataset-specific labels.

## What Is Config-Driven vs Hardcoded

### Config-driven today

- default Timeline profile
- anchor type default
- order field candidate defaults
- anchor spacing inputs
- primary assignment rule
- explicit per-type layer overrides
- unanchored handling mode
- top-tag ids

### Still code-defined today

- the generic semantic model for person/organization/tag-like types
- the four generic tag bands
- the exact bucket-solving heuristics
- current `z` spacing constants and micro-jitter constants
- field alias convenience logic

## Current Non-Goals

Not implemented yet:

- a full generic settings panel for Timeline tuning
- user-editable Timeline spacing/jitter controls
- per-layout preset architecture
- backend persistence of visualization settings

Those belong to the upcoming settings refactor, not the current Timeline
arrangement implementation.

## Recommended Next Config Refactor

When the settings system is generalized, Timeline should expose user-adjustable
controls through layout-specific UI state while keeping module config as the
default base.

Recommended future split:

- config defaults
- runtime session overrides
- local saved last-used settings
- optional named presets

Timeline-specific user-tunable controls can then include:

- anchor spacing
- band spacing
- micro-jitter
- unanchored policy
- possibly bucket density controls
