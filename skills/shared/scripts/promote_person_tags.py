#!/usr/bin/env python3
"""Promote source-entity tags onto people using config-driven support thresholds."""

from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from builder_config import get_tagging_policy
from vault_db import VaultDB


def _ancestor_tags(db: VaultDB, tag_id: str, hierarchy_relation_type: str) -> list[str]:
    rows = db.conn.execute(
        """
        WITH RECURSIVE ancestors(tag_id) AS (
            SELECT target_id
            FROM relationships
            WHERE source_id = ? AND rel_type = ?
          UNION
            SELECT r.target_id
            FROM relationships r
            JOIN ancestors a ON r.source_id = a.tag_id
            WHERE r.rel_type = ?
        )
        SELECT DISTINCT tag_id FROM ancestors
        """,
        (tag_id, hierarchy_relation_type, hierarchy_relation_type),
    ).fetchall()
    return [row["tag_id"] for row in rows]


def promote_person_tags(db: VaultDB, config_path: str | Path | None = None) -> dict:
    policy = get_tagging_policy(config_path).get("person_tag_promotion", {}) or {}
    if not policy.get("enabled", False):
        return {"enabled": False, "promoted": 0, "people": 0}

    source_entity_type = policy.get("source_entity_type", "publication")
    source_relation_type = policy.get("source_relation_type", "AUTHORED")
    annotation_relation_type = policy.get("annotation_relation_type", "TAGGED")
    hierarchy_relation_type = policy.get("hierarchy_relation_type", "BROADER")
    min_support_count = max(int(policy.get("min_support_count", 2) or 2), 1)
    include_ancestor_tags = bool(policy.get("include_ancestor_tags", False))
    max_tags_per_person = max(int(policy.get("max_tags_per_person", 0) or 0), 0)

    relation_rows = db.conn.execute(
        """
        SELECT
            r.source_id,
            r.target_id,
            source.type AS source_type,
            target.type AS target_type,
            json_extract(source.metadata, '$.profiled') AS source_profiled,
            json_extract(target.metadata, '$.profiled') AS target_profiled
        FROM relationships r
        JOIN entities source ON source.id = r.source_id
        JOIN entities target ON target.id = r.target_id
        WHERE r.rel_type = ?
          AND (
            (source.type = 'person' AND target.type = ?)
            OR
            (source.type = ? AND target.type = 'person')
          )
        """,
        (source_relation_type, source_entity_type, source_entity_type),
    ).fetchall()

    source_ids_by_person: dict[str, set[str]] = defaultdict(set)
    for row in relation_rows:
        source_id = row["source_id"]
        target_id = row["target_id"]
        if row["source_type"] == "person":
            if not row["source_profiled"]:
                continue
            person_id, related_id = source_id, target_id
        else:
            if not row["target_profiled"]:
                continue
            person_id, related_id = target_id, source_id
        source_ids_by_person[person_id].add(related_id)

    promoted = 0
    people = 0
    for person_id, related_ids in source_ids_by_person.items():
        counts: Counter[str] = Counter()
        for related_id in related_ids:
            rows = db.conn.execute(
                """
                SELECT target_id
                FROM relationships
                WHERE source_id = ? AND rel_type = ?
                """,
                (related_id, annotation_relation_type),
            ).fetchall()
            for row in rows:
                counts[row["target_id"]] += 1

        selected = [tag_id for tag_id, count in counts.items() if count >= min_support_count]
        selected.sort(key=lambda tag_id: (-counts[tag_id], tag_id))
        if max_tags_per_person:
            selected = selected[:max_tags_per_person]

        final_tags: list[str] = []
        seen = set()
        for tag_id in selected:
            if tag_id not in seen:
                final_tags.append(tag_id)
                seen.add(tag_id)
            if include_ancestor_tags:
                for ancestor_id in _ancestor_tags(db, tag_id, hierarchy_relation_type):
                    if ancestor_id not in seen:
                        final_tags.append(ancestor_id)
                        seen.add(ancestor_id)

        if not final_tags:
            continue

        people += 1
        for tag_id in final_tags:
            db.add_relationship(person_id, annotation_relation_type, tag_id)
            promoted += 1

    return {
        "enabled": True,
        "promoted": promoted,
        "people": people,
        "source_entity_type": source_entity_type,
        "source_relation_type": source_relation_type,
        "annotation_relation_type": annotation_relation_type,
        "min_support_count": min_support_count,
        "include_ancestor_tags": include_ancestor_tags,
        "max_tags_per_person": max_tags_per_person,
    }


def main():
    parser = argparse.ArgumentParser(description="Promote source-entity tags onto people using config policy")
    parser.add_argument("--db", required=True, help="Path to vault.db")
    parser.add_argument("--config", default=None, help="Optional KGX config file with db_build tagging policy")
    args = parser.parse_args()

    with VaultDB(args.db) as db:
        stats = promote_person_tags(db, config_path=args.config)
    print(stats)


if __name__ == "__main__":
    main()
