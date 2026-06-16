#!/usr/bin/env python3
"""
migrate_tags.py — Load tag-registry.md and tag-aliases.md into vault.db.

One-shot migration: creates tag entities and wires up aliases.
Safe to re-run (upserts).

Usage:
    python migrate_tags.py /path/to/vault
    python migrate_tags.py --vault /path/to/vault --config /path/to/config.yaml
"""
set_euo = True  # reminder: this is Python, not bash

import argparse
import sys
from pathlib import Path

# Add shared/scripts to path for imports
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from builder_config import get_tagging_policy
from tag_resolver import (
    _load_aliases_md,
    _load_registry_md,
    ensure_tag_ontology,
    load_aliases_file,
    load_registry_file,
)
from vault_db import VaultDB


def _load_tag_sources(vault_path: Path, tagging_policy: dict) -> tuple[dict[str, dict], dict[str, str], Path, Path]:
    ontology = tagging_policy.get("ontology", {}) or {}
    registry_path = ontology.get("registry_path") or (vault_path / "tags" / "tag-registry.md")
    aliases_path = ontology.get("aliases_path") or (vault_path / "tags" / "tag-aliases.md")

    registry = load_registry_file(registry_path) if registry_path else _load_registry_md(str(vault_path))
    aliases = load_aliases_file(aliases_path) if aliases_path and Path(aliases_path).exists() else _load_aliases_md(str(vault_path))
    return registry, aliases, Path(registry_path), Path(aliases_path)


def migrate_tags(vault_root: str, *, db_path: str | Path | None = None, config_path: str | Path | None = None) -> dict:
    vault_path = Path(vault_root)
    db_path = Path(db_path) if db_path else vault_path / "vault.db"
    tagging_policy = get_tagging_policy(config_path)

    registry, aliases, registry_path, aliases_path = _load_tag_sources(vault_path, tagging_policy)

    if not registry:
        print(f"No tags found in {registry_path}")
        return {"tags": 0, "aliases": 0}

    db = VaultDB(db_path)

    tag_count = 0
    for tag_name, info in registry.items():
        ensure_tag_ontology([tag_name], db=db, default_category=info.get("category", "topic"))
        if info.get("description"):
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
            ensure_tag_ontology([canonical], db=db, default_category="topic")
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
    print(f"  registry: {registry_path}")
    if aliases:
        print(f"  aliases:  {aliases_path}")

    # Verify
    db_registry = db.get_tag_registry()
    db_aliases = db.get_tag_aliases()
    print(f"Verify: {len(db_registry)} tags, {len(db_aliases)} aliases in DB")

    db.close()
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate tags from markdown to vault.db")
    parser.add_argument("vault", nargs="?", default=".", help="Path to vault root directory")
    parser.add_argument("--db", default=None, help="Path to vault.db (defaults to <vault>/vault.db)")
    parser.add_argument("--config", default=None, help="Optional KGX config file with db_build tagging policy")
    args = parser.parse_args()

    migrate_tags(args.vault, db_path=args.db, config_path=args.config)
