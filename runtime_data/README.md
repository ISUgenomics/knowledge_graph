# Runtime Data

`runtime_data/` contains mutable local state created while using KnowledgeGraph.

- `vault/` is the live working vault and database location.
- `rendered/` is for generated markdown exports from the current DB.
- `logs/` is for local logs.
- `tmp/` is for temporary files.

This directory should stay local and should not be committed, except for lightweight documentation files like this one.
