# Backlog

Deferred work and known issues. Newest at the top.

## UMAP layout is non-functional — hidden from the layout menu

- **Status:** Deferred. The `UMAP` option is commented out in the layout
  dropdown (`APP/kgx/ui/index.html`). All UMAP code is retained
  (`showUmapOverlay`, `runUmapCompute`, `applyUmapPositions`, the
  `layout === 'umap'` branch in `graph.js`, and the `/api/layout/umap/*`
  endpoints).
- **Why:** The layout does not currently work end-to-end.
- **To re-enable:** Uncomment the `<option value="umap">UMAP</option>` line and
  fix the underlying compute/positions flow.

## Remove remaining laptop-specific config

- `APP/config.yaml` (ISU academic profile) was removed — it pointed at a
  `vault.db` and skills directory that only exist on a local laptop. The app
  defaults to `APP/config/default.yaml` (relative paths), so nothing else
  depends on it.
- `APP/config-proteins.yaml` was also removed (moved to a local temp folder for
  possible later exploration) — it hardcoded a laptop-only path. If protein
  data is revisited, restore it as a relative/sample config.
