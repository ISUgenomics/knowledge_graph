# Nobel Source Data

This directory stores official Nobel Prize source snapshots used by the `person_research` skill when the `noble_profile` extension is active.

Layout:

- `api/laureates.json` — cached official laureates dataset from `api.nobelprize.org`
- `matches/<person-slug>.json` — generated normalized per-person Nobel matches saved during research runs
- `tags/tag-registry.json` — canonical Nobel sample tag registry used as DB-build input
- `tags/tag-aliases.json` — optional alias mappings for canonical Nobel sample tags

Notes:

- `dataset_path` in match files is stored as a repo-relative snapshot reference for portability.
- Top-level `affiliations` in match files are deduplicated convenience summaries; the full per-prize affiliation records remain under each prize entry.
- `matches/` is a generated cache, not a canonical source input. The builder will recreate it during research/build runs, so the repo only keeps the directory structure and ignores the generated `.json` files.
- `tags/` is intended to be machine-readable, human-curated source input. The builder may render these tags into vault markdown, but the source files here should be treated as the durable input layer for sample DB refreshes.
- The builder/app config should point at these source files through the shared people-domain config, not through a separate sample-local config file.

These files are intended as reproducible source inputs for DB-building and sample-data testing.
