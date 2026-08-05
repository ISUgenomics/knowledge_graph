# Scalability & review-response fixes — 2026-08-05

Prompted by an external review of the knowledge-graph app (scalability past ~10k
nodes, "why 3D", differentiator). Each fix below is **independent** — consider or
implement them one at a time. Ordered by impact/effort.

## Grounding facts (verified against the code)

These correct the review's assumptions and justify the fixes:

- **Physics is not naive O(n²).** Renderer is `3d-force-graph` v1.80.0
  (`APP/kgx/ui/lib/3d-force-graph.min.js`, instantiated `graph.js:3704`), bundling
  **d3-force-3d**. Charge force = **Barnes-Hut octree, ~O(n log n), default theta
  0.9**. `forceCollide` (the costly per-tick force) is effectively **not attached**
  (guarded on a global `d3` that isn't exposed — `graph.js:4634-4640`).
- **Rendering is instanced WebGL** (three.js `InstancedMesh`), not per-node meshes.
- **Aggregation/clustering/filtering already exist:** server-side projection
  `graph_explore` (`queries.py:478-815`) hides stubs, excludes types, synthesizes
  collapsed edges (COLLABORATOR / derived-path), rolls up tags, prunes orphans;
  frontend has label-propagation community detection with a resolution knob
  (`graph.js:418-509`) and type/rel/SQL/group filters + search.
- **Real gaps:** (1) `max_visible_nodes: 5000` is defined
  (`loader.py:239`, served via `/api/config`) but **read by nothing** — no SQL
  `LIMIT` on `graph_nodes`/`graph_edges` (`queries.py:307,329`), no client clamp;
  (2) **3D-only** (`numDimensions` never set); (3) **no LOD** on the DOM label
  layer, which is updated every frame.
- **Differentiator is the local LLM→SQL→highlight/filter loop** (`llm/chat_sql.py`,
  qwen3-coder:30b via Ollama; results drive `node:highlight`/`node:sql-filter`),
  not the 3D view.

---

## Fix 1 (P0) — Enforce a node budget + truncation warning
**Problem:** Nothing caps node count before it reaches the renderer, so large
graphs degrade (layout convergence + per-frame label DOM + hairball). The
`max_visible_nodes` cap is dead config.

**Fix:**
- Thread `max_visible_nodes` (`loader.py:239`) into the projection path
  (`routes_graph.py` → `queries.py:478-815`). When post-projection node count
  exceeds the cap, keep the **top-K by degree** and re-run the existing orphan
  prune (`queries.py:751-766`). Reuse the degree ranking already in `hub_nodes()`
  (`queries.py:1123`).
- Extend the `projection` response block (`queries.py:796-814`) with
  `truncated`, `kept`, `total`.
- Show a UI banner via the existing `graph:projection` event (`graph.js:3458`):
  "Showing top 5,000 of N by connectivity — refine with a filter or chat query."

**Effort:** M. **Risk:** changes which nodes a user sees — must be visible + offer
"load full via filter/chat", never silent.

---

## Fix 2 (P1) — 2D mode toggle
**Problem:** 3D-only; the review's "why 3D / hairball" point lands, and 2D is
more readable for dense data.

**Fix:** Add a toggle that calls `graphInstance.numDimensions(2)` (d3-force-3d
supports it — flattens z), pins the camera top-down, and disables z-using layouts
(timeline/spherical) while active. Wire next to the layout `<select>`
(`index.html:453`); track alongside `currentLayout` (`graph.js:169`). Same
renderer/forces, just constrains a dimension.

**Effort:** S. **Risk:** low.

---

## Fix 3 (P2) — Level-of-detail for labels (+ dense links)
**Problem:** Labels are DOM elements updated every frame
(`labelLayer` / `updatePinnedLabelPositions`) — the biggest per-frame cost at
scale.

**Fix:**
- Virtualize labels: render only for nodes above a size/degree threshold or within
  a camera-distance cutoff, and cap the total shown.
- Optionally lower `LIVE_NODE_RESOLUTION` (`graph.js:109`, currently 8) at high
  node counts, and generalize the existing dense-edge auto-hide
  (`graph.js:3646-3658`, `>3000` count) beyond display mode.

**Effort:** M. **Risk:** low; purely visual.

---

## Fix 4 (P3) — Benchmark harness
**Problem:** "Falls over above 10k" is an untested claim.

**Fix:** Script that loads synthetic graphs at 5k/10k/50k/100k and records
layout-convergence time and steady-state FPS/tick time. Publish the node count
where FPS crosses ~30, before and after Fixes 1-3. Turns an admission into a
measured limit with a documented mitigation.

**Effort:** M. **Risk:** none (additive).

---

## Fix 5 (P4) — Reposition around the LLM→SQL layer
**Problem:** The differentiator (local natural-language → schema-grounded SQL →
highlight/filter, with self-correction in `chat_sql.py:651,771,930,973`) is
undersold; the 3D view is the weakest, most conventional part.

**Fix:** Update `APP/README.md` / launch blurb to lead with the query loop
(local, private, no cloud), 3D as one of several projections. Cite the SQL
self-correction as the technical depth.

**Effort:** S. **Risk:** none.

---

## Verification (per fix)
- **Fix 1:** lower `max_visible_nodes` in `APP/config/default.yaml`, call
  `GET /api/graph?mode=explore`, confirm node count is clamped,
  `projection.truncated` set, banner shows, kept nodes are highest-degree.
- **Fix 2:** toggle 2D → nodes collapse to a plane, camera top-down; toggle back →
  z-layouts behave.
- **Fix 3:** at ~10k nodes, compare browser-profiler scripting/layout time with
  labels-all vs. LOD labels.
- **Fix 4:** run the script; record the FPS-crossover node count.
- Run path: `python -m kgx` from `APP/` (defaults to `config/default.yaml`).

## Related
- UMAP semantic layout is built but shelved — see `docs/BACKLOG.md`. If the
  differentiator pitch leans on "semantic", note UMAP is deferred, not shipped.
