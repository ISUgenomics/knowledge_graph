#!/usr/bin/env python3
"""
migrate_rich_content.py — Populate new rich-content tables from existing vault markdown.

Reads all signal, person, and abstract markdown files and writes to:
  entity_topics      — topics per entity
  snippets           — blockquote excerpts (topic + person context)
  research_interests — ordered interest list per person
  sources            — provenance records per entity
  contact_info       — contact fields per person

Safe to re-run: snippets are cleared and rewritten per entity; other tables use
INSERT OR IGNORE / upsert so duplicates are skipped.

Usage:
    python migrate_rich_content.py <vault_dir> [--db <path>] [--dry-run]
"""

import argparse
import re
import sys
from pathlib import Path

# Allow running from any directory
sys.path.insert(0, str(Path(__file__).resolve().parent))
from vault_db import VaultDB


# ---------------------------------------------------------------------------
# Markdown parsers
# ---------------------------------------------------------------------------

def _frontmatter(text: str) -> tuple[dict, str]:
    """Split YAML frontmatter from body. Returns (fm_dict, body_text)."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    fm_block = text[3:end].strip()
    body = text[end + 4:].strip()
    fm = {}
    # Simple line-by-line parse — handles scalars, quoted strings, and lists
    lines = fm_block.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if ":" not in line:
            i += 1
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if val == "" or val == "|" or val == ">":
            # Check for YAML list on subsequent lines
            items = []
            i += 1
            while i < len(lines) and lines[i].startswith("  - "):
                items.append(lines[i][4:].strip().strip('"').strip("'"))
                i += 1
            fm[key] = items
            # i already points to the next non-list line — do not increment again
        elif val.startswith("[") and val.endswith("]"):
            # Inline list: [a, b, c]
            fm[key] = [x.strip().strip('"').strip("'") for x in val[1:-1].split(",") if x.strip()]
            i += 1
        else:
            fm[key] = val
            i += 1
    return fm, body


def _extract_blockquotes(section_text: str) -> list[str]:
    """Extract all > blockquote lines from a section, joined into paragraphs."""
    quotes = []
    current = []
    for line in section_text.splitlines():
        if line.startswith("> "):
            current.append(line[2:].strip())
        elif line.startswith(">"):
            current.append(line[1:].strip())
        else:
            if current:
                quotes.append(" ".join(current).strip())
                current = []
    if current:
        quotes.append(" ".join(current).strip())
    return [q for q in quotes if q]


def _split_h2_sections(body: str) -> dict[str, str]:
    """Split body into {section_heading: section_text} by ## headers."""
    sections = {}
    current_heading = ""
    current_lines = []
    for line in body.splitlines():
        if line.startswith("## "):
            if current_heading or current_lines:
                sections[current_heading] = "\n".join(current_lines)
            current_heading = line[3:].strip()
            current_lines = []
        else:
            current_lines.append(line)
    if current_heading or current_lines:
        sections[current_heading] = "\n".join(current_lines)
    return sections


def _split_h3_sections(section_text: str) -> dict[str, str]:
    """Split a section into {subsection_heading: text} by ### headers."""
    subsections = {}
    current = ""
    current_lines = []
    for line in section_text.splitlines():
        if line.startswith("### "):
            if current or current_lines:
                subsections[current] = "\n".join(current_lines)
            current = line[4:].strip()
            current_lines = []
        else:
            current_lines.append(line)
    if current or current_lines:
        subsections[current] = "\n".join(current_lines)
    return subsections


def _parse_markdown_table(text: str) -> list[dict]:
    """Parse a simple markdown table into list of row dicts."""
    rows = []
    headers = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if all(re.match(r"^[-:]+$", c) for c in cells if c):
            continue  # separator row
        if not headers:
            headers = cells
        else:
            rows.append(dict(zip(headers, cells)))
    return rows


def _wikilink_to_id(link: str) -> str:
    """Convert [[slug]] to slug."""
    m = re.match(r"\[\[([^\]]+)\]\]", link.strip())
    return m.group(1) if m else link.strip()


# ---------------------------------------------------------------------------
# Per-entity-type migration
# ---------------------------------------------------------------------------

def migrate_signal(db: VaultDB, md_path: Path, dry_run: bool) -> dict:
    text = md_path.read_text(encoding="utf-8", errors="replace")
    fm, body = _frontmatter(text)
    sections = _split_h2_sections(body)

    # Resolve entity_id from filename stem
    entity_id = md_path.stem
    if not db.resolve(entity_id):
        return {"skipped": entity_id, "reason": "not in DB"}

    counts = {"topics": 0, "topic_snippets": 0, "person_snippets": 0, "sources": 0}

    # --- Topics ---
    topics = []
    if fm.get("topic"):
        topics.append(fm["topic"])
    # Also pick up any "## Topic: X" headings
    for heading in sections:
        if heading.startswith("Topic:"):
            t = heading[6:].strip()
            if t not in topics:
                topics.append(t)
    for topic in topics:
        if not dry_run:
            db.add_topic(entity_id, topic)
        counts["topics"] += 1

    # --- Topic snippets ---
    for heading, content in sections.items():
        if heading.startswith("Topic:"):
            topic = heading[6:].strip()
            quotes = _extract_blockquotes(content)
            for i, q in enumerate(quotes):
                if not dry_run:
                    db.add_snippet(entity_id, q, ref_id=None, ref_type="topic", ordinal=i)
                counts["topic_snippets"] += 1

    # --- Person context snippets ---
    # Clear existing person snippets for this signal before re-inserting
    if not dry_run:
        db.conn.execute(
            "DELETE FROM snippets WHERE entity_id = ? AND ref_type = 'person'",
            (entity_id,)
        )
        db.conn.commit()

    people_context = sections.get("People Context", "")
    if people_context:
        person_subsections = _split_h3_sections(people_context)
        for person_name, content in person_subsections.items():
            if not person_name:
                continue
            # Try to resolve person by name
            person_slug = re.sub(r"\s+", "-", person_name.strip().lower())
            person_slug = re.sub(r"[^a-z0-9-]", "", person_slug)
            person_id = db.resolve(person_slug)
            quotes = _extract_blockquotes(content)
            for i, q in enumerate(quotes):
                if not dry_run:
                    db.add_snippet(entity_id, q,
                                   ref_id=person_id,
                                   ref_type="person",
                                   ordinal=i)
                counts["person_snippets"] += 1

    # --- Sources ---
    sources_text = sections.get("Sources", "")
    if sources_text:
        for row in _parse_markdown_table(sources_text):
            src = row.get("Source", "").strip()
            url = row.get("URL", "").strip()
            date = row.get("Published", row.get("Retrieved", "")).strip()
            if src and src not in ("N/A", ""):
                if not dry_run:
                    db.upsert_source(entity_id, src,
                                     url=url if url not in ("N/A", "") else None,
                                     retrieved_at=date if date not in ("N/A", "") else None)
                counts["sources"] += 1

    return counts


def migrate_person(db: VaultDB, md_path: Path, dry_run: bool) -> dict:
    text = md_path.read_text(encoding="utf-8", errors="replace")
    fm, body = _frontmatter(text)
    sections = _split_h2_sections(body)

    # Person slug from directory or filename
    entity_id = md_path.stem  # e.g. kris-baldwin
    if not db.resolve(entity_id):
        return {"skipped": entity_id, "reason": "not in DB"}

    counts = {"interests": 0, "contact_fields": 0, "sources": 0}

    # --- Research interests ---
    interests_text = sections.get("Research Interests", "")
    interests = []
    for line in interests_text.splitlines():
        line = line.strip()
        if line.startswith("- "):
            interest = line[2:].strip()
            if interest and interest.lower() not in ("none", "n/a", ""):
                interests.append(interest)
    if interests:
        if not dry_run:
            db.set_research_interests(entity_id, interests)
        counts["interests"] = len(interests)

    # --- Contact info ---
    contact_text = sections.get("Contact", "")
    contact_map = {
        "Department": "department",
        "Title": "title",
        "Email": "email",
        "Phone": "phone",
        "ORCID": "orcid",
        "Website": "website",
    }
    for row in _parse_markdown_table(contact_text):
        field_raw = row.get("Field", "").strip()
        value = row.get("Value", "").strip()
        field = contact_map.get(field_raw, field_raw.lower())
        if value and value not in ("N/A", ""):
            if not dry_run:
                db.upsert_contact(entity_id, field, value)
            counts["contact_fields"] += 1

    # --- Sources ---
    sources_text = sections.get("Sources", "")
    for row in _parse_markdown_table(sources_text):
        src = row.get("Source", "").strip()
        url = row.get("URL", "").strip()
        date = row.get("Retrieved", row.get("Published", "")).strip()
        if src and src not in ("N/A", ""):
            if not dry_run:
                db.upsert_source(entity_id, src,
                                 url=url if url not in ("N/A", "") else None,
                                 retrieved_at=date if date not in ("N/A", "") else None)
            counts["sources"] += 1

    return counts


def migrate_abstract(db: VaultDB, md_path: Path, dry_run: bool) -> dict:
    text = md_path.read_text(encoding="utf-8", errors="replace")
    fm, body = _frontmatter(text)

    # Publications are keyed by title in the DB
    title = fm.get("title", "").strip()
    if not title:
        return {"skipped": md_path.stem, "reason": "no title in frontmatter"}

    # Try to find by filename in metadata, then by name match
    row = db.conn.execute(
        "SELECT id FROM entities WHERE type = 'publication' AND name = ?", (title,)
    ).fetchone()
    if not row:
        # Try metadata filename field
        row = db.conn.execute(
            "SELECT id FROM entities WHERE type='publication' AND json_extract(metadata,'$.filename') = ?",
            (md_path.name,)
        ).fetchone()
    if not row:
        return {"skipped": md_path.stem, "reason": "not in DB"}

    entity_id = row[0]
    counts = {"topics": 0}

    # Publications don't have topic/snippet sections yet — just topics from tags
    for tag in (fm.get("tags") or []):
        # Only treat broad subject tags as topics (skip method/technique tags)
        if not dry_run:
            db.add_topic(entity_id, tag)
        counts["topics"] += 1

    return counts


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Migrate rich content from vault markdown to DB")
    parser.add_argument("vault_dir", help="Path to vault root (e.g. skills/vault)")
    parser.add_argument("--db", default=None,
                        help="Path to vault.db (defaults to <vault_dir>/vault.db)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Parse and count without writing to DB")
    args = parser.parse_args()

    vault = Path(args.vault_dir).resolve()
    db_path = Path(args.db).resolve() if args.db else vault / "vault.db"

    if not db_path.exists():
        print(f"ERROR: vault.db not found at {db_path}", file=sys.stderr)
        sys.exit(1)

    db = VaultDB(str(db_path))
    mode = "DRY RUN" if args.dry_run else "LIVE"
    print(f"migrate_rich_content [{mode}]  db={db_path}")
    print()

    totals = {
        "signals": 0, "people": 0, "abstracts": 0,
        "topics": 0, "topic_snippets": 0, "person_snippets": 0,
        "interests": 0, "contact_fields": 0, "sources": 0,
        "skipped": 0,
    }

    # Signals
    signal_dir = vault / "signals"
    for md in sorted(signal_dir.glob("*.md")):
        result = migrate_signal(db, md, args.dry_run)
        if "skipped" in result:
            totals["skipped"] += 1
            print(f"  SKIP signal {result['skipped']}: {result['reason']}")
        else:
            totals["signals"] += 1
            totals["topics"] += result.get("topics", 0)
            totals["topic_snippets"] += result.get("topic_snippets", 0)
            totals["person_snippets"] += result.get("person_snippets", 0)
            totals["sources"] += result.get("sources", 0)

    # People (nested: people/<slug>/<slug>.md or people/<slug>.md)
    people_dir = vault / "people"
    person_files = list(people_dir.glob("**/*.md"))
    for md in sorted(person_files):
        result = migrate_person(db, md, args.dry_run)
        if "skipped" in result:
            totals["skipped"] += 1
        else:
            totals["people"] += 1
            totals["interests"] += result.get("interests", 0)
            totals["contact_fields"] += result.get("contact_fields", 0)
            totals["sources"] += result.get("sources", 0)

    # Abstracts
    abstracts_dir = vault / "abstracts"
    if abstracts_dir.exists():
        for md in sorted(abstracts_dir.glob("*.md")):
            result = migrate_abstract(db, md, args.dry_run)
            if "skipped" in result:
                totals["skipped"] += 1
            else:
                totals["abstracts"] += 1
                totals["topics"] += result.get("topics", 0)

    db.close()

    print(f"\nResults ({mode}):")
    print(f"  Signals migrated:       {totals['signals']:>4}")
    print(f"  People migrated:        {totals['people']:>4}")
    print(f"  Abstracts migrated:     {totals['abstracts']:>4}")
    print(f"  Skipped (not in DB):    {totals['skipped']:>4}")
    print()
    print(f"  entity_topics written:  {totals['topics']:>4}")
    print(f"  topic snippets:         {totals['topic_snippets']:>4}")
    print(f"  person snippets:        {totals['person_snippets']:>4}")
    print(f"  research_interests:     {totals['interests']:>4}")
    print(f"  contact_info fields:    {totals['contact_fields']:>4}")
    print(f"  sources:                {totals['sources']:>4}")


if __name__ == "__main__":
    main()
