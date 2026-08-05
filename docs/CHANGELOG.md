# Changelog

Notable changes since **2026-06-16**, synthesized from commit history. Newest
first. Grouped by milestone; categories follow
[Keep a Changelog](https://keepachangelog.com) (Added / Changed / Fixed /
Removed).

---

## 2026-08-05 — Spherical layout & config cleanup

### Added
- **Spherical layout**: pins one node type equidistant on a sphere (Fibonacci
  distribution) and relaxes connected nodes around it; auto radius scaled from
  node/edge counts, optional grouping of anchors by shared-connection community.
- **"Relax/Unpin node"** right-click action to release a dragged (pinned) node
  back into the force layout.

### Changed
- Node context-menu action relabeled *Relax node* → *Unpin node*.

### Removed
- Laptop-only configs (`config.yaml`, `config-proteins.yaml`); the app defaults
  to `config/default.yaml`.
- **UMAP** layout hidden from the menu (code retained) until it is working — see
  `docs/BACKLOG.md`.

---

## 2026-08-04 — Reliable node interaction

### Added
- Forgiving, screen-space **click tolerance** and a **dead-zone drag** so a click
  never nudges a node.

### Fixed
- Reliable node selection via a movement threshold (click vs. drag).
- Custom node drag actually moves the grabbed node; other nodes **freeze during
  drag** and **relax on release** (no whole-graph jitter); built-in drag restored
  with click-select kept on top.

### Removed
- Stale root `ARCHITECTURE.md` and duplicate `BEST_PRACTICES.md`; references to
  deleted people-collection skills.

---

## 2026-08-03 — Packaging & first-run experience

### Added
- First run seeds the **Nobel laureates** sample dataset by default.

### Changed
- Conda environment renamed to `knowledgegraph`; docs aligned; `environment.yml`
  updated.

### Removed
- Data-collection harness (visualization app retained); stopped tracking
  `egg-info`.

---

## 2026-07-27 — Repository consolidation

### Changed
- Merged the original **AgentPlugin** history (from the `agent_skills` repo) into
  KnowledgeGraph; merged `alex-refactor` into `main`.

---

## 2026-06-22 → 2026-07-01 — Genomics module & semantic backend

The largest body of work in this period: a genomics domain plus a generalized,
registry-driven natural-language backend.

### Added
- **Genomics NL chat**: dataset-aware deterministic mismatch handling,
  deterministic-first orchestration for supported prompts, and unified
  deterministic answer artifacts alongside semantic route contracts.
- **Semantic registry backend**: shared registry module infrastructure,
  declarative genomics operators, registry-driven people-domain wiring,
  semantic onboarding + overlay workflow, and a registry-first NL semantic
  backend (documented).
- **Explore Focus presets** (dataset-aware): *Comparative*, *Functional*
  (renamed from protein-centric), and *Expression* (consolidated from the
  transcript view); derived-edge settings controls; HGT donor-edge data support.
- Chat UI: rendered summary/table presentation and exposed answer artifacts.
- Reproducible sample genomics builds; **bison** and **SCN** dataset packages;
  regenerated orthogroup/comparative artifacts.
- Extensive regression coverage for genomics semantic routing, repair, and
  effector evidence projection.

### Changed
- Modularized **LLM chat-to-SQL by domain**; refactored genomics semantics around
  shared declarative operators and the semantic registry.
- Comparative homology: organism-aware ortholog copy counting, hierarchy-aware
  comparative scope UI, HGT score moved onto donor edges, refined homology scope
  ontology.
- Refined genomics timeline placement (structural nodes relative to anchored
  comparative paths); refined semantic node color palette; UI tools filtered by
  active module.

### Fixed
- Chat SQL reconciliation for synthesized semantic answers; lossless genomics
  chat reconciliation and semantic query repair; NL interpretation prioritizes
  requested core result types.
- SCN putative-effector selection, alias/natural-sequence coverage, and effector
  island tagging; comparative hit-data parsing; config inheritance and semantic
  overlay loading for SCN.

---

## 2026-06-16 → 2026-06-17 — Genomics module scaffold & repo rename

### Added
- **Genomics module** scaffold with an example 9-record data source and generated
  sample-data artifacts; Explore projection variants and extended projection core
  for the genomics module.
- Documented genomics module basics; improved skill help and detail panel.

### Changed
- Renamed **AgentPlugin → knowledgegraph** and fixed path references throughout.
- Refined the genomics graph UI.

---

*Generated 2026-08-05 from `git log` since 2026-06-16 (97 commits). This is a
synthesized summary, not a per-commit list; see `git log` for full detail.*
