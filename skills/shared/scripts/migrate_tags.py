#!/usr/bin/env python3
"""
migrate_tags.py — Load tag-registry.md and tag-aliases.md into vault.db.

One-shot migration: creates tag entities and wires up aliases.
Safe to re-run (upserts).

Usage:
    python migrate_tags.py /path/to/vault
"""
set_euo = True  # reminder: this is Python, not bash

import sys
from pathlib import Path

# Add shared/scripts to path for imports
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from tag_resolver import _load_registry_md, _load_aliases_md
from vault_db import VaultDB


def migrate_tags(vault_root: str) -> dict:
    vault_path = Path(vault_root)
    db_path = vault_path / "vault.db"

    registry = _load_registry_md(vault_root)
    aliases = _load_aliases_md(vault_root)

    if not registry:
        print(f"No tags found in {vault_path / 'tags' / 'tag-registry.md'}")
        return {"tags": 0, "aliases": 0}

    db = VaultDB(db_path)

    tag_count = 0
    for tag_name, info in registry.items():
        db.upsert_tag(
            tag_name,
            category=info.get("category", "topic"),
            description=info.get("description", ""),
        )
        tag_count += 1

    # Wire up aliases: each alias points to its canonical tag entity
    alias_count = 0
    for alias, canonical in aliases.items():
        # Ensure canonical tag exists
        if canonical not in registry:
            db.upsert_tag(canonical, category="topic")
            tag_count += 1

        # Add alias to the canonical tag entity
        canonical_id = db._normalize_id(canonical)
        alias_id = db._normalize_id(alias)
        try:
            db.conn.execute(
                "INSERT OR IGNORE INTO aliases (alias, entity_id) VALUES (?, ?)",
                (alias_id, canonical_id),
            )
        except Exception as e:
            print(f"  Warning: alias '{alias}' -> '{canonical}': {e}")
        alias_count += 1

    db.conn.commit()

    result = {"tags": tag_count, "aliases": alias_count}
    print(f"Migrated {tag_count} tags, {alias_count} aliases to {db_path}")

    # Verify
    db_registry = db.get_tag_registry()
    db_aliases = db.get_tag_aliases()
    print(f"Verify: {len(db_registry)} tags, {len(db_aliases)} aliases in DB")

    db.close()
    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Migrate tags from markdown to vault.db")
    parser.add_argument("vault", help="Path to vault root directory")
    args = parser.parse_args()

    migrate_tags(args.vault)
