#!/usr/bin/env python3
"""
migrate_vault.py — Import existing Obsidian vault markdown into SQLite.

Reads all vault markdown (people, abstracts, signals, events, tags),
parses frontmatter and wiki-links, and populates vault.db.

Usage:
    python migrate_vault.py                          # default vault path
    python migrate_vault.py --vault /path/to/vault
    python migrate_vault.py --vault /path/to/vault --db vault.db
"""

import argparse
import json
import re
import sys
from pathlib import Path

# Add shared scripts to path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from vault_db import VaultDB


# ---------------------------------------------------------------------------
# Frontmatter parser
# ---------------------------------------------------------------------------
def parse_frontmatter(text: str) -> dict:
    """Parse YAML frontmatter from markdown text."""
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return {}
    fm = {}
    current_key = None
    list_values = []

    for line in m.group(1).splitlines():
        list_match = re.match(r"^\s+-\s+(.+)", line)
        if list_match and current_key:
            val = list_match.group(1).strip().strip('"').strip("'")
            list_values.append(val)
            fm[current_key] = list_values
            continue

        kv_match = re.match(r"^(\w[\w_-]*)\s*:\s*(.*)", line)
        if kv_match:
            current_key = kv_match.group(1)
            val = kv_match.group(2).strip().strip('"').strip("'")
            if val.startswith("[") and val.endswith("]"):
                fm[current_key] = [v.strip().strip('"').strip("'")
                                   for v in val[1:-1].split(",") if v.strip()]
                list_values = fm[current_key]
            elif val:
                fm[current_key] = val
                list_values = []
            else:
                list_values = []
                fm[current_key] = list_values
            continue

    return fm


def extract_wiki_links(text: str) -> list[str]:
    """Extract [[slug]] wiki-links from text."""
    return re.findall(r"\[\[([a-z0-9][a-z0-9-]*)\]\]", text)


def strip_wiki_link(val) -> str:
    """Extract slug from '[[slug]]' or return raw value."""
    if not isinstance(val, str):
        val = str(val) if val else ""
    if not val:
        return ""
    m = re.search(r"\[\[([a-z0-9-]+)\]\]", val)
    return m.group(1) if m else val.strip().lower().replace(" ", "-")


# ---------------------------------------------------------------------------
# Importers
# ---------------------------------------------------------------------------
def import_tags(db: VaultDB, vault: Path):
    """Import tags from tag-registry.md."""
    registry = vault / "tags" / "tag-registry.md"
    if not registry.exists():
        return 0
    text = registry.read_text()
    count = 0
    for m in re.finditer(r"^\|\s*([a-z0-9-]+)\s*\|\s*(\w+)\s*\|\s*(.*?)\s*\|",
                         text, re.MULTILINE):
        tag_id, category, description = m.group(1), m.group(2), m.group(3)
        db.upsert_entity("tag", tag_id, name=tag_id,
                         metadata={"category": category, "description": description})
        count += 1
    return count


def import_people(db: VaultDB, vault: Path):
    """Import person profiles."""
    people_dir = vault / "people"
    if not people_dir.exists():
        return 0
    count = 0
    for d in sorted(people_dir.iterdir()):
        if d.name.startswith("."):
            continue
        if d.is_dir():
            md = d / f"{d.name}.md"
        elif d.suffix == ".md":
            md = d
        else:
            continue
        if not md.exists():
            continue

        text = md.read_text()
        fm = parse_frontmatter(text)
        slug = md.stem

        # Extract display name from aliases or H1
        aliases_raw = fm.get("aliases", [])
        if isinstance(aliases_raw, str):
            aliases_raw = [aliases_raw]
        name = aliases_raw[0] if aliases_raw else slug

        # Extract structured fields from Contact table
        dept_match = re.search(r"\|\s*Department\s*\|\s*(.+?)\s*\|", text)
        title_match = re.search(r"\|\s*Title\s*\|\s*(.+?)\s*\|", text)
        email_match = re.search(r"\|\s*Email\s*\|\s*(.+?)\s*\|", text)

        # Extract summary (first paragraph after H1)
        summary_match = re.search(r"^# .+\n\n(.+?)(?:\n\n|\n##)", text, re.DOTALL)

        meta = {
            "role": fm.get("role", ""),
            "department": dept_match.group(1).strip() if dept_match else "",
            "title": title_match.group(1).strip() if title_match else "",
            "email": email_match.group(1).strip() if email_match else "",
            "institution": fm.get("institution", "Iowa State University"),
            "summary": summary_match.group(1).strip()[:500] if summary_match else "",
            "sources": {},
        }

        # Parse sources block
        for src_match in re.finditer(r"^\s+(openalex|orcid|profile):\s*(.+)",
                                     text, re.MULTILINE):
            val = src_match.group(2).strip().strip('"').strip("'")
            if val and val != "N/A":
                meta["sources"][src_match.group(1)] = val

        # Tags → TAGGED relationships
        tags = fm.get("tags", [])

        # Aliases for name resolution
        alias_slugs = []
        for a in aliases_raw:
            alias_slug = re.sub(r"[^a-z0-9-]", "", a.strip().lower().replace(" ", "-"))
            if alias_slug and alias_slug != slug:
                alias_slugs.append(alias_slug)

        meta["profiled"] = True
        db.upsert_entity("person", slug, name=name, aliases=alias_slugs, metadata=meta)

        for tag in tags:
            tag_id = db.ensure_entity("tag", tag, name=tag)
            db.add_relationship(slug, "TAGGED", tag_id)

        # Coauthors
        coauthor_section = re.search(r"## Coauthors\s*\n((?:- \[\[.+\]\]\n?)+)",
                                     text, re.DOTALL)
        if coauthor_section:
            for co_slug in extract_wiki_links(coauthor_section.group(1)):
                co_id = db.ensure_entity("person", co_slug, name=co_slug)
                # Store both directions for undirected relationship
                pair = tuple(sorted([slug, co_id]))
                db.add_relationship(pair[0], "COAUTHOR", pair[1])

        count += 1
    return count


def import_abstracts(db: VaultDB, vault: Path):
    """Import publication abstracts."""
    abstracts_dir = vault / "abstracts"
    if not abstracts_dir.exists():
        return 0
    count = 0
    for f in sorted(abstracts_dir.glob("*.md")):
        text = f.read_text()
        fm = parse_frontmatter(text)

        # Use DOI as canonical ID if available, otherwise filename
        doi = fm.get("doi", "")
        if doi and doi != "N/A":
            pub_id = re.sub(r"[^a-z0-9:._/-]", "", doi.lower())
            # Normalize DOI to a safe slug
            pub_id = pub_id.replace("https://doi.org/", "doi:").replace("http://doi.org/", "doi:")
        else:
            pub_id = f.stem

        # Extract abstract text
        abstract_match = re.search(r"## Abstract\s*\n\n(.+?)(?:\n\n##|\Z)", text, re.DOTALL)

        meta = {
            "title": fm.get("title", f.stem),
            "year": fm.get("year", ""),
            "journal": fm.get("journal", ""),
            "doi": doi,
            "pmid": fm.get("pmid", ""),
            "abstract": abstract_match.group(1).strip()[:2000] if abstract_match else "",
            "filename": f.name,
        }

        db.upsert_entity("publication", pub_id, name=meta["title"], metadata=meta)

        # AUTHORED relationships from frontmatter authors
        raw_authors = fm.get("authors", [])
        for a in raw_authors:
            author_slug = strip_wiki_link(a)
            if author_slug:
                author_id = db.ensure_entity("person", author_slug, name=author_slug)
                db.add_relationship(author_id, "AUTHORED", pub_id)

        # TAGGED relationships
        for tag in fm.get("tags", []):
            tag_id = db.ensure_entity("tag", tag, name=tag)
            db.add_relationship(pub_id, "TAGGED", tag_id)

        count += 1
    return count


def import_signals(db: VaultDB, vault: Path):
    """Import signal/news articles."""
    signals_dir = vault / "signals"
    if not signals_dir.exists():
        return 0
    count = 0
    for f in sorted(signals_dir.glob("*.md")):
        if f.name.startswith("."):
            continue
        text = f.read_text()
        fm = parse_frontmatter(text)
        slug = f.stem

        # Extract summary (first paragraph after H1)
        summary_match = re.search(r"^# .+\n\n(.+?)(?:\n\n|\n##)", text, re.DOTALL)

        meta = {
            "title": fm.get("title", slug),
            "source": fm.get("source", ""),
            "url": fm.get("url", ""),
            "published": fm.get("published", ""),
            "topic": fm.get("topic", ""),
            "summary": summary_match.group(1).strip()[:500] if summary_match else "",
        }

        # Use slug if no title in frontmatter
        name = meta["title"] if meta["title"] != slug else slug

        db.upsert_entity("signal", slug, name=name, metadata=meta)

        # People mentioned — from frontmatter and wiki-links in People section
        people_fm = fm.get("people", [])
        people_section = re.search(r"## People Mentioned\s*\n(.*?)(?=\n##|\Z)",
                                   text, re.DOTALL)
        all_people_slugs = set()
        for p in people_fm:
            ps = strip_wiki_link(p)
            if ps:
                all_people_slugs.add(ps)
        if people_section:
            for ps in extract_wiki_links(people_section.group(1)):
                all_people_slugs.add(ps)

        for person_slug in all_people_slugs:
            person_id = db.ensure_entity("person", person_slug, name=person_slug)
            db.add_relationship(person_id, "MENTIONED_IN", slug)

        # TAGGED
        for tag in fm.get("tags", []):
            tag_id = db.ensure_entity("tag", tag, name=tag)
            db.add_relationship(slug, "TAGGED", tag_id)

        count += 1
    return count


def import_events(db: VaultDB, vault: Path):
    """Import event notes."""
    events_dir = vault / "events"
    if not events_dir.exists():
        return 0
    count = 0
    for d in sorted(events_dir.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        md = d / f"{d.name}.md"
        if not md.exists():
            continue

        text = md.read_text()
        fm = parse_frontmatter(text)
        slug = d.name

        meta = {
            "title": fm.get("title", slug),
            "date": fm.get("date", ""),
            "event_type": fm.get("event_type", ""),
            "location": fm.get("location", ""),
            "organizer": fm.get("organizer", ""),
            "hosted_by": strip_wiki_link(fm.get("hosted_by", "")) if fm.get("hosted_by") else "",
        }

        db.upsert_entity("event", slug, name=meta["title"], metadata=meta)

        # Attendees — extract wiki-links from Attendees section
        attendee_section = re.search(r"## Attendees\s*\n(.*?)(?=\n##|\Z)", text, re.DOTALL)
        if attendee_section:
            for person_slug in extract_wiki_links(attendee_section.group(1)):
                person_id = db.ensure_entity("person", person_slug, name=person_slug)
                db.add_relationship(person_id, "ATTENDED", slug)

        # TAGGED
        for tag in fm.get("tags", []):
            tag_id = db.ensure_entity("tag", tag, name=tag)
            db.add_relationship(slug, "TAGGED", tag_id)

        # hosted_by → center relationship
        if meta["hosted_by"]:
            center_id = db.ensure_entity("center", meta["hosted_by"],
                                         name=meta["hosted_by"])
            db.add_relationship(slug, "MEMBER_OF", center_id)

        count += 1
    return count


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def migrate(vault: Path, db_path: Path):
    """Run the full migration."""
    if db_path.exists():
        print(f"WARNING: {db_path} already exists. Overwriting.")
        db_path.unlink()

    db = VaultDB(db_path)

    print(f"Vault:  {vault}")
    print(f"DB:     {db_path}\n")

    print("Importing...")
    tag_count = import_tags(db, vault)
    print(f"  Tags (registry): {tag_count}")

    person_count = import_people(db, vault)
    print(f"  People: {person_count}")

    abstract_count = import_abstracts(db, vault)
    print(f"  Abstracts: {abstract_count}")

    signal_count = import_signals(db, vault)
    print(f"  Signals: {signal_count}")

    event_count = import_events(db, vault)
    print(f"  Events: {event_count}")

    # Print stats
    stats = db.stats()
    print(f"\n--- Database Summary ---")
    print(f"Entities:")
    for t, c in sorted(stats["entities"].items()):
        print(f"  {t}: {c}")
    print(f"  total: {stats['total_entities']} ({stats['aliases']} aliases)")
    print(f"\nRelationships:")
    for t, c in sorted(stats["relationships"].items()):
        print(f"  {t}: {c}")
    print(f"  total: {stats['total_relationships']}")

    # Show top hub nodes
    hubs = db.hub_nodes(min_degree=10, entity_type="person")
    if hubs:
        print(f"\nTop person hubs:")
        for h in hubs[:10]:
            print(f"  {h['name']:40s} degree={h['degree']}")

    db.close()
    print(f"\nDone. Database at: {db_path}")


def main():
    parser = argparse.ArgumentParser(description="Migrate Obsidian vault to SQLite")
    parser.add_argument("--vault", default=None, help="Path to vault root")
    parser.add_argument("--db", default=None, help="Output database path")
    args = parser.parse_args()

    vault = Path(args.vault) if args.vault else Path(__file__).resolve().parents[2] / "vault"
    db_path = Path(args.db) if args.db else vault / "vault.db"

    if not vault.exists():
        print(f"ERROR: Vault not found at {vault}")
        sys.exit(1)

    migrate(vault, db_path)


if __name__ == "__main__":
    main()
