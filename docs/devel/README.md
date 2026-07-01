# Development Plans

This folder holds persistent development outlines that should survive across Codex sessions.

Use these docs to:
- capture big-picture refactor direction
- track phased progress with checkboxes
- note known issues and cleanup work
- keep later sessions aligned with earlier architectural decisions

## Active Plans

- [Genomics Chat Refactor Plan](./GENOMICS_CHAT_REFACTOR_PLAN.md)
- [Genomics Chat Analysis Model](./GENOMICS_CHAT_ANALYSIS_MODEL.md)

## Conventions

- Prefer one plan doc per major refactor/theme
- Keep plans practical: goals, phases, checkboxes, known issues
- Update checkboxes and session notes as work lands
- Prefer a clean primary architecture over accumulating fallback layers
- If demo behavior depends on bad or inconsistent sample semantics, fix the source/schema/build path when feasible
- Assume the user launches from the repo root with the conda environment created from `environment.yml`; preserve `python -m kgx ...` compatibility instead of relying on an ad hoc local venv import path
- Distinguish clearly between:
  - shared/core architecture work
  - domain/module work
  - sample- or dataset-specific fixes
