#!/usr/bin/env python3
"""
repair_tag_ontology.py — backfill deterministic tag ontology links in an existing vault DB.

This uses the shared tag resolver's ontology rules to ensure known parent/field/domain
tags exist and to add BROADER links for existing flat tags.
"""

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from tag_resolver import ensure_tag_ontology
from vault_db import VaultDB


def repair_db(db_path: Path) -> dict:
    db = VaultDB(db_path)
    before = db.get_tag_forest_stats()
    tag_ids = sorted(db.get_tag_registry().keys())
    ensured = ensure_tag_ontology(tag_ids, db=db, default_category="topic")
    after = db.get_tag_forest_stats()
    db.close()
    return {
        "db": str(db_path),
        "tags_seen": len(tag_ids),
        "tags_processed": len(ensured),
        "before": before,
        "after": after,
        "new_broader_links": after["with_parent"] - before["with_parent"],
    }


def main():
    parser = argparse.ArgumentParser(description="Backfill deterministic BROADER links for existing tags")
    parser.add_argument("db", nargs="+", help="Path(s) to vault-style SQLite DBs")
    args = parser.parse_args()

    for raw in args.db:
        db_path = Path(raw).resolve()
        if not db_path.exists():
            print(f"SKIP: missing {db_path}")
            continue
        result = repair_db(db_path)
        print(f"== {result['db']}")
        print(
            f"tags={result['tags_seen']} processed={result['tags_processed']} "
            f"new_broader={result['new_broader_links']}"
        )
        print(f"before={result['before']}")
        print(f"after={result['after']}")
        print()


if __name__ == "__main__":
    main()
