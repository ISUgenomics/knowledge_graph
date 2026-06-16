#!/usr/bin/env python3
"""
curate_nobel_person_tags.py — remove clearly spurious tags from Nobel-profile people.

Rule:
- Keep `nobel-prize`
- Keep tags that live under the same ontology domain(s) as the person's Nobel category
- Drop tags from unrelated ontology branches and orphan root topics
"""

import argparse
import json
import sqlite3
from pathlib import Path


def normalize_category(value: str) -> str:
    return value.strip().lower().replace(" ", "-")


def descendants(cur: sqlite3.Cursor, root_names: set[str]) -> set[str]:
    if not root_names:
        return set()
    name_to_id = {
        row[0]: row[1]
        for row in cur.execute("SELECT name, id FROM entities WHERE type = 'tag'")
    }
    root_ids = {name_to_id[name] for name in root_names if name in name_to_id}
    if not root_ids:
        return set(root_names)
    seen = set(root_ids)
    frontier = set(root_ids)
    while frontier:
        placeholders = ",".join("?" for _ in frontier)
        rows = cur.execute(
            f"SELECT source_id FROM relationships WHERE rel_type = 'BROADER' AND target_id IN ({placeholders})",
            list(frontier),
        ).fetchall()
        frontier = {row[0] for row in rows if row[0] not in seen}
        seen |= frontier
    id_to_name = {
        row[0]: row[1]
        for row in cur.execute("SELECT id, name FROM entities WHERE type = 'tag'")
    }
    return {id_to_name[tag_id] for tag_id in seen if tag_id in id_to_name}


def ancestor_names(cur: sqlite3.Cursor, tag_names: set[str]) -> set[str]:
    if not tag_names:
        return set()
    name_to_id = {
        row[0]: row[1]
        for row in cur.execute("SELECT name, id FROM entities WHERE type = 'tag'")
    }
    id_to_name = {
        row[0]: row[1]
        for row in cur.execute("SELECT id, name FROM entities WHERE type = 'tag'")
    }
    frontier = {name_to_id[name] for name in tag_names if name in name_to_id}
    seen = set(frontier)
    while frontier:
        placeholders = ",".join("?" for _ in frontier)
        rows = cur.execute(
            f"SELECT target_id FROM relationships WHERE rel_type = 'BROADER' AND source_id IN ({placeholders})",
            list(frontier),
        ).fetchall()
        frontier = {row[0] for row in rows if row[0] not in seen}
        seen |= frontier
    return {id_to_name[tag_id] for tag_id in seen if tag_id in id_to_name}


def curate_db(db_path: Path, source_db_path: Path | None = None) -> dict:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    source_conn = None
    source_cur = cur
    if source_db_path:
        source_conn = sqlite3.connect(source_db_path)
        source_conn.row_factory = sqlite3.Row
        source_cur = source_conn.cursor()

    people = cur.execute(
        """
        SELECT id, name, metadata
        FROM entities
        WHERE type = 'person'
          AND json_extract(metadata, '$.extensions[0]') = 'noble_profile'
        """
    ).fetchall()

    removed = []
    restored = []
    for person in people:
        md = json.loads(person["metadata"] or "{}")
        prizes = ((md.get("nobel") or {}).get("prizes") or [])
        category_roots = {
            normalize_category(prize.get("category", ""))
            for prize in prizes
            if prize.get("category")
        }
        category_roots.discard("")
        allowed_domains = {
            name for name in ancestor_names(cur, category_roots)
            if name in {"science", "humanities", "society", "awards"}
        }
        source_person = source_cur.execute(
            "SELECT id FROM entities WHERE type = 'person' AND name = ?",
            (person["name"],),
        ).fetchone()
        candidate_tag_rows = source_cur.execute(
            """
            SELECT t.id, t.name
            FROM relationships r
            JOIN entities t ON t.id = r.target_id
            WHERE r.source_id = ? AND r.rel_type = 'TAGGED' AND t.type = 'tag'
            """,
            ((source_person["id"] if source_person else person["id"]),),
        ).fetchall()
        allowed = set()
        for tag in candidate_tag_rows:
            name = tag["name"]
            if name == "nobel-prize":
                allowed.add(name)
                continue
            lineage = ancestor_names(cur, {name}) | {name}
            if category_roots & lineage:
                allowed.add(name)
                continue
            if allowed_domains & lineage:
                allowed.add(name)
                continue

        current_tag_rows = cur.execute(
            """
            SELECT t.id, t.name
            FROM relationships r
            JOIN entities t ON t.id = r.target_id
            WHERE r.source_id = ? AND r.rel_type = 'TAGGED' AND t.type = 'tag'
            """,
            (person["id"],),
        ).fetchall()
        current = {tag["name"]: tag["id"] for tag in current_tag_rows}
        for tag in current_tag_rows:
            if tag["name"] not in allowed:
                cur.execute(
                    "DELETE FROM relationships WHERE source_id = ? AND rel_type = 'TAGGED' AND target_id = ?",
                    (person["id"], tag["id"]),
                )
                removed.append((person["name"], tag["name"]))
        name_to_id = {
            row[0]: row[1]
            for row in cur.execute("SELECT name, id FROM entities WHERE type = 'tag'")
        }
        for tag_name in sorted(allowed):
            tag_id = name_to_id.get(tag_name)
            if tag_id and tag_name not in current:
                cur.execute(
                    "INSERT OR IGNORE INTO relationships (source_id, rel_type, target_id, metadata) VALUES (?, 'TAGGED', ?, '{}')",
                    (person["id"], tag_id),
                )
                restored.append((person["name"], tag_name))

    conn.commit()
    conn.close()
    if source_conn:
        source_conn.close()
    return {"db": str(db_path), "removed": removed, "restored": restored}


def main():
    parser = argparse.ArgumentParser(description="Curate Nobel-profile person tags in a vault DB")
    parser.add_argument("db", nargs="+", help="Path(s) to Nobel-style SQLite DBs")
    parser.add_argument("--source-db", default="", help="Optional uncurated source DB to restore valid tags from")
    args = parser.parse_args()

    for raw in args.db:
        path = Path(raw).resolve()
        if not path.exists():
            print(f"SKIP: missing {path}")
            continue
        source_path = Path(args.source_db).resolve() if args.source_db else None
        result = curate_db(path, source_db_path=source_path)
        print(f"== {result['db']}")
        print(f"removed={len(result['removed'])} restored={len(result['restored'])}")
        for person, tag in result["removed"][:40]:
            print(f"  {person}: {tag}")
        if len(result["removed"]) > 40:
            print(f"  ... and {len(result['removed']) - 40} more")
        for person, tag in result["restored"][:20]:
            print(f"  + {person}: {tag}")
        if len(result["restored"]) > 20:
            print(f"  ... and {len(result['restored']) - 20} more restored")
        print()


if __name__ == "__main__":
    main()
