#!/usr/bin/env python3
"""
render_vault.py — Generate Obsidian markdown from vault.db.

Reads the SQLite database and generates/regenerates all vault markdown files.
The markdown is a read-only view of the database.

Usage:
    python render_vault.py                              # default paths
    python render_vault.py --db runtime_data/vault/vault.db --output runtime_data/rendered/
    python render_vault.py --db vault.db --type person   # render only people
"""

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vault_db import VaultDB

TODAY = date.today().isoformat()


def _note_name_for_entity(entity_id: str) -> str:
    if ":" in entity_id:
        entity_id = entity_id.split(":", 1)[1]
    return entity_id.replace(":", "-")


def _display_name(entity: dict | None, fallback_id: str = "") -> str:
    if not entity:
        return fallback_id
    name = str(entity.get("name", "") or "").strip()
    entity_id = str(entity.get("id", "") or "").strip()
    if name and name != entity_id:
        return name

    meta = entity.get("metadata", {}) or {}
    description = str(meta.get("description", "") or "").strip()
    if description:
        if " within " in description.lower():
            description = description[: description.lower().index(" within ")].strip()
        if "." in description:
            description = description.split(".", 1)[0].strip()
        if description:
            return description

    if entity_id:
        return entity_id.replace("-", " ")
    return fallback_id


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------
def render_person(db: VaultDB, entity: dict, output: Path):
    """Render a person profile markdown file."""
    eid = entity["id"]
    meta = entity["metadata"]
    name = entity["name"]

    # Get relationships
    authored = db.get_relationships(eid, "AUTHORED", "outgoing")
    attended = db.get_relationships(eid, "ATTENDED", "outgoing")
    mentioned = db.get_relationships(eid, "MENTIONED_IN", "outgoing")
    tags_rels = db.get_relationships(eid, "TAGGED", "outgoing")
    coauthor_rels = db.get_relationships(eid, "COAUTHOR")
    award_rels = db.get_relationships(eid, "WON", "outgoing")
    affiliation_rels = db.get_relationships(eid, "AFFILIATED_WITH", "outgoing")

    tags = [r["target_id"] for r in tags_rels]
    awards = []
    organizations = []
    coauthors = set()
    for r in coauthor_rels:
        other = r["target_id"] if r["source_id"] == eid else r["source_id"]
        coauthors.add(other)

    # Get publication details
    pubs = []
    for r in authored:
        pub = db.get_entity(r["target_id"])
        if pub:
            pubs.append(pub)
    pubs.sort(key=lambda p: str(p["metadata"].get("year", "0")), reverse=True)
    for r in award_rels:
        award = db.get_entity(r["target_id"])
        if award:
            awards.append(award)
    awards.sort(key=lambda a: str(a["metadata"].get("year", "0")), reverse=True)

    for r in affiliation_rels:
        org = db.get_entity(r["target_id"])
        if org:
            organizations.append(org)

    # Build markdown
    lines = [
        "---",
        f'aliases: ["{name}"]',
        f"tags: [{', '.join(tags)}]",
        f"categories: [person, {meta.get('role', 'staff')}]",
        "type: person",
        f"role: {meta.get('role', '')}",
        f"institution: {meta.get('institution', 'Iowa State University')}",
        f"updated: {TODAY}",
    ]
    extensions = meta.get("extensions", [])
    if extensions:
        lines.append(f"extensions: [{', '.join(extensions)}]")
    sources = meta.get("sources", {})
    if sources:
        lines.append("sources:")
        for k, v in sources.items():
            lines.append(f'  {k}: "{v}"')
    if awards:
        lines.append("award_records:")
        for award in awards:
            payload = {"id": award["id"], **award["metadata"]}
            lines.append(f"  - '{json.dumps(payload, ensure_ascii=True)}'")
    if organizations:
        lines.append("organization_records:")
        for org in organizations:
            payload = {"id": org["id"], **org["metadata"]}
            lines.append(f"  - '{json.dumps(payload, ensure_ascii=True)}'")
    lines.extend(["---", ""])

    lines.append(f"# {name}")
    lines.append("")
    if meta.get("summary"):
        lines.append(meta["summary"])
        lines.append("")

    # Contact table
    lines.append("## Contact")
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("|---|---|")
    if meta.get("department"):
        lines.append(f"| Department | {meta['department']} |")
    if meta.get("title"):
        lines.append(f"| Title | {meta['title']} |")
    if meta.get("email"):
        lines.append(f"| Email | {meta['email']} |")
    lines.append("")

    # Publications
    if pubs:
        lines.append(f"## Publications ({len(pubs)})")
        lines.append("")
        for pub in pubs[:25]:
            pm = pub["metadata"]
            year = pm.get("year", "")
            title = pm.get("title", pub["name"])
            journal = pm.get("journal", "")
            filename = pm.get("filename", f"{pub['id']}.md")
            lines.append(f"- [[abstracts/{filename}|{title}]] — *{journal}*, {year}")
        lines.append("")

    # Events attended
    if attended:
        lines.append("## Events")
        lines.append("")
        for r in attended:
            lines.append(f"- [[{r['target_id']}]]")
        lines.append("")

    # Signals mentioned in
    if mentioned:
        lines.append("## Mentioned In")
        lines.append("")
        for r in mentioned:
            lines.append(f"- [[{r['target_id']}]]")
        lines.append("")

    # Coauthors
    if coauthors:
        lines.append("## Coauthors")
        lines.append("")
        for co in sorted(coauthors):
            lines.append(f"- [[{co}]]")
        lines.append("")

    if awards:
        lines.append("## Awards")
        lines.append("")
        for award in awards:
            lines.append(f"- [[awards/{_note_name_for_entity(award['id'])}|{award['name']}]]")
        lines.append("")

    if organizations:
        lines.append("## Affiliations")
        lines.append("")
        for org in organizations:
            meta_org = org["metadata"]
            detail = ", ".join(part for part in [meta_org.get("city", ""), meta_org.get("country", "")] if part)
            suffix = f" — {detail}" if detail else ""
            lines.append(f"- [[organizations/{_note_name_for_entity(org['id'])}|{org['name']}]]{suffix}")
        lines.append("")

    # Write
    person_dir = output / "people" / eid
    person_dir.mkdir(parents=True, exist_ok=True)
    (person_dir / f"{eid}.md").write_text("\n".join(lines))


def render_award(db: VaultDB, entity: dict, output: Path):
    """Render an award markdown note."""
    meta = entity["metadata"]
    title = meta.get("title", entity["name"])
    lines = [
        "---",
        f'id: "{entity["id"]}"',
        "type: award",
        f'title: "{title}"',
        f'year: "{meta.get("year", "")}"',
        f'category: "{meta.get("category", "")}"',
        f'category_full_name: "{meta.get("category_full_name", "")}"',
        f'date_awarded: "{meta.get("date_awarded", "")}"',
        f'source_url: "{meta.get("source_url", "")}"',
        f"_indexed: {TODAY}",
        "---",
        "",
        f"# {title}",
        "",
    ]
    if meta.get("motivation"):
        lines.extend(["## Motivation", "", meta["motivation"], ""])
    out_dir = output / "awards"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{_note_name_for_entity(entity['id'])}.md").write_text("\n".join(lines))


def render_organization(db: VaultDB, entity: dict, output: Path):
    """Render an organization markdown note."""
    meta = entity["metadata"]
    title = meta.get("title", entity["name"])
    lines = [
        "---",
        f'id: "{entity["id"]}"',
        "type: organization",
        f'title: "{title}"',
        f'city: "{meta.get("city", "")}"',
        f'country: "{meta.get("country", "")}"',
        f'location: "{meta.get("location", "")}"',
        f"_indexed: {TODAY}",
        "---",
        "",
        f"# {title}",
        "",
    ]
    details = ", ".join(part for part in [meta.get("city", ""), meta.get("country", "")] if part)
    if details:
        lines.extend(["## Location", "", details, ""])
    out_dir = output / "organizations"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{_note_name_for_entity(entity['id'])}.md").write_text("\n".join(lines))


def render_publication(db: VaultDB, entity: dict, output: Path):
    """Render a publication/abstract markdown file."""
    eid = entity["id"]
    meta = entity["metadata"]

    # Get authors and tags
    author_rels = db.get_relationships(eid, "AUTHORED", "incoming")
    tag_rels = db.get_relationships(eid, "TAGGED", "outgoing")
    ack_rels = db.get_relationships(eid, "ACKNOWLEDGED", "outgoing")
    authors = [r["source_id"] for r in author_rels]
    tags = [r["target_id"] for r in tag_rels]
    ack_entities = []
    for rel in ack_rels:
        ack = db.get_entity(rel["target_id"])
        if ack:
            ack_entities.append(ack)

    filename = meta.get("filename", f"{eid}.md")

    lines = [
        "---",
        f'title: "{meta.get("title", "")}"',
        f'doi: "{meta.get("doi", "N/A")}"',
        f"year: {meta.get('year', '')}",
        f'journal: "{meta.get("journal", "")}"',
    ]
    if meta.get("pmid"):
        lines.append(f'pmid: "{meta["pmid"]}"')
    lines.append("authors:")
    for a in authors:
        lines.append(f'  - "[[{a}]]"')
    lines.append(f"tags: [{', '.join(tags)}]")
    lines.append(f"_indexed: {TODAY}")
    lines.extend(["---", ""])

    lines.append(f"# {meta.get('title', '')}")
    lines.append("")

    if meta.get("abstract"):
        lines.append("## Abstract")
        lines.append("")
        lines.append(meta["abstract"])
        lines.append("")

    if ack_entities:
        lines.append("## Acknowledgements")
        lines.append("")
        for ack in ack_entities:
            ack_id = ack["id"]
            ack_note = _note_name_for_entity(ack_id)
            target_rels = db.get_relationships(ack_id, "CREDITED", "outgoing")
            snippets = db.get_snippets(ack_id)
            targets = []
            for target_rel in target_rels:
                target = db.get_entity(target_rel["target_id"])
                target_id = target_rel["target_id"]
                targets.append((target_id, _display_name(target, target_id)))
            if snippets:
                for snippet in snippets:
                    text = snippet.get("text", "").strip()
                    if not text:
                        continue
                    lines.append(f"- {text}")
                    if targets:
                        if len(targets) == 1:
                            target_id, target_label = targets[0]
                            lines.append(f"  Credited: [[{target_id}|{target_label}]]")
                        else:
                            joined = ", ".join(f"[[{target_id}|{target_label}]]" for target_id, target_label in targets)
                            lines.append(f"  Credited: {joined}")
                    lines.append(f"  Evidence: [[acknowledgements/{ack_note}|acknowledgement note]]")
            elif targets:
                if len(targets) == 1:
                    target_id, target_label = targets[0]
                    lines.append(f"- Credited: [[{target_id}|{target_label}]]")
                else:
                    joined = ", ".join(f"[[{target_id}|{target_label}]]" for target_id, target_label in targets)
                    lines.append(f"- Credited: {joined}")
                lines.append(f"  Evidence: [[acknowledgements/{ack_note}|acknowledgement note]]")
        lines.append("")

    lines.append("## Authors")
    lines.append("")
    for a in authors:
        lines.append(f"- [[{a}]]")
    lines.append("")

    doi = meta.get("doi", "")
    pmid = meta.get("pmid", "")
    if doi or pmid:
        if doi and doi != "N/A":
            lines.append(f"**DOI:** {doi}")
        if pmid:
            lines.append(f"**PMID:** [{pmid}](https://pubmed.ncbi.nlm.nih.gov/{pmid}/)")
        lines.append(f"**Journal:** {meta.get('journal', '')}")
        lines.append(f"**Year:** {meta.get('year', '')}")
        lines.append("")

    # Write
    abstracts_dir = output / "abstracts"
    abstracts_dir.mkdir(parents=True, exist_ok=True)
    (abstracts_dir / filename).write_text("\n".join(lines))


def render_signal(db: VaultDB, entity: dict, output: Path):
    """Render a signal/news article markdown file."""
    eid = entity["id"]
    meta = entity["metadata"]

    people_rels = db.get_relationships(eid, "MENTIONED_IN", "incoming")
    tag_rels = db.get_relationships(eid, "TAGGED", "outgoing")
    people = [r["source_id"] for r in people_rels]
    tags = [r["target_id"] for r in tag_rels]

    lines = [
        "---",
        "type: signal",
        f'source: "{meta.get("source", "")}"',
        f'url: "{meta.get("url", "")}"',
        f"published: {meta.get('published', '')}",
        f"_indexed: {TODAY}",
        f"tags: [{', '.join(tags)}]",
        "categories: [signal, news]",
        "people:",
    ]
    for p in people:
        lines.append(f'  - "[[{p}]]"')
    if meta.get("topic"):
        lines.append(f'topic: "{meta["topic"]}"')
    lines.extend(["---", ""])

    title = meta.get("title", eid)
    lines.append(f"# {title}")
    lines.append("")
    if meta.get("summary"):
        lines.append(meta["summary"])
        lines.append("")

    if people:
        lines.append("## People Mentioned")
        lines.append("")
        for p in people:
            lines.append(f"- [[{p}]]")
        lines.append("")

    # Write
    signals_dir = output / "signals"
    signals_dir.mkdir(parents=True, exist_ok=True)
    (signals_dir / f"{eid}.md").write_text("\n".join(lines))


def render_acknowledgement(db: VaultDB, entity: dict, output: Path):
    """Render an acknowledgement evidence note."""
    eid = entity["id"]
    meta = entity["metadata"]
    target_rels = db.get_relationships(eid, "CREDITED", "outgoing")
    snippets = db.get_snippets(eid)
    publication = db.get_entity(meta.get("publication_id", "")) if meta.get("publication_id") else None

    targets = []
    for rel in target_rels:
        target = db.get_entity(rel["target_id"])
        targets.append((rel["target_id"], _display_name(target, rel["target_id"])))

    lines = [
        "---",
        f'id: "{eid}"',
        "type: acknowledgement",
        f'publication_id: "{meta.get("publication_id", "")}"',
        f'confidence: "{meta.get("confidence", "")}"',
        f'match_type: "{meta.get("match_type", "")}"',
        f'matched_phrase: "{meta.get("matched_phrase", "")}"',
        f'source_name: "{meta.get("source_name", "")}"',
        f'source_url: "{meta.get("source_url", "")}"',
        f"_indexed: {TODAY}",
        "---",
        "",
        f"# {entity['name']}",
        "",
    ]
    if publication:
        pub_title = publication["metadata"].get("title", publication["name"])
        pub_file = publication["metadata"].get("filename", f"{publication['id']}.md")
        lines.extend(["## Publication", "", f"[[abstracts/{pub_file}|{pub_title}]]", ""])
    if targets:
        lines.append("## Credited")
        lines.append("")
        for target_id, target_label in targets:
            lines.append(f"- [[{target_id}|{target_label}]]")
        lines.append("")
    if snippets:
        lines.append("## Evidence")
        lines.append("")
        for snippet in snippets:
            if snippet.get("text", "").strip():
                lines.append(f"> {snippet['text'].strip()}")
                lines.append("")
    out_dir = output / "acknowledgements"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{_note_name_for_entity(eid)}.md").write_text("\n".join(lines))


def render_event(db: VaultDB, entity: dict, output: Path):
    """Render an event markdown file."""
    eid = entity["id"]
    meta = entity["metadata"]

    attendee_rels = db.get_relationships(eid, "ATTENDED", "incoming")
    tag_rels = db.get_relationships(eid, "TAGGED", "outgoing")
    attendees = [r["source_id"] for r in attendee_rels]
    tags = [r["target_id"] for r in tag_rels]

    lines = [
        "---",
        "type: event",
        f"event_type: {meta.get('event_type', '')}",
        f'title: "{meta.get("title", "")}"',
        f"date: {meta.get('date', '')}",
        f'location: "{meta.get("location", "")}"',
    ]
    if meta.get("organizer"):
        lines.append(f'organizer: "{meta["organizer"]}"')
    if meta.get("hosted_by"):
        lines.append(f'hosted_by: "[[{meta["hosted_by"]}]]"')
    lines.append(f"tags: [{', '.join(tags)}]")
    lines.append(f"categories: [event, {meta.get('event_type', '')}]")
    lines.append(f"_indexed: {TODAY}")
    lines.append(f"attendee_count: {len(attendees)}")
    lines.extend(["---", ""])

    lines.append(f"# {meta.get('title', '')}")
    lines.append("")

    if attendees:
        lines.append("## Attendees")
        lines.append("")
        lines.append("| Name |")
        lines.append("|------|")
        for a in sorted(attendees):
            lines.append(f"| [[{a}]] |")
        lines.append("")

    # Write
    event_dir = output / "events" / eid
    event_dir.mkdir(parents=True, exist_ok=True)
    (event_dir / f"{eid}.md").write_text("\n".join(lines))


def render_tag_registry(db: VaultDB, output: Path):
    """Render the tag registry."""
    tags = db.get_entities("tag")
    lines = [
        "---",
        "type: registry",
        "description: Approved tags for the ISU knowledge vault",
        f"updated: {TODAY}",
        "---",
        "",
        "# Tag Registry",
        "",
        "| Tag | Category | Description |",
        "|-----|----------|-------------|",
    ]
    for t in sorted(tags, key=lambda x: x["name"]):
        meta = t["metadata"]
        cat = meta.get("category", "topic")
        desc = meta.get("description", "")
        lines.append(f"| {t['id']} | {cat} | {desc} |")
    lines.append("")

    tags_dir = output / "tags"
    tags_dir.mkdir(parents=True, exist_ok=True)
    (tags_dir / "tag-registry.md").write_text("\n".join(lines))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def render_all(db: VaultDB, output: Path, entity_type: str = ""):
    """Render all or a specific entity type."""
    output.mkdir(parents=True, exist_ok=True)

    types_to_render = [entity_type] if entity_type else ["person", "publication", "acknowledgement", "signal", "event", "award", "organization"]

    if not entity_type or entity_type == "acknowledgement":
        ack_dir = output / "acknowledgements"
        if ack_dir.exists():
            for stale in ack_dir.glob("*.md"):
                stale.unlink()

    for etype in types_to_render:
        entities = db.get_entities(etype)
        count = 0
        for entity in entities:
            if etype == "person":
                if not entity["metadata"].get("profiled"):
                    continue
                render_person(db, entity, output)
            elif etype == "publication":
                render_publication(db, entity, output)
            elif etype == "signal":
                render_signal(db, entity, output)
            elif etype == "acknowledgement":
                render_acknowledgement(db, entity, output)
            elif etype == "event":
                render_event(db, entity, output)
            elif etype == "award":
                render_award(db, entity, output)
            elif etype == "organization":
                render_organization(db, entity, output)
            count += 1
        print(f"  {etype}: {count} files")

    # Always render tag registry
    if not entity_type or entity_type == "tag":
        render_tag_registry(db, output)
        print(f"  tag-registry: 1 file")

    print(f"\nRendered to: {output}")


def main():
    parser = argparse.ArgumentParser(description="Render vault markdown from SQLite")
    parser.add_argument("--db", default=None, help="Path to vault.db")
    parser.add_argument("--output", default=None, help="Output directory")
    parser.add_argument("--type", default="", help="Only render this entity type")
    args = parser.parse_args()

    runtime_root = Path(__file__).resolve().parents[3] / "runtime_data"
    vault = runtime_root / "vault"
    db_path = Path(args.db) if args.db else vault / "vault.db"
    output = Path(args.output) if args.output else runtime_root / "rendered"

    if not db_path.exists():
        print(f"ERROR: Database not found at {db_path}")
        sys.exit(1)

    print(f"DB:     {db_path}")
    print(f"Output: {output}\n")

    db = VaultDB(db_path)
    render_all(db, output, entity_type=args.type)
    db.close()


if __name__ == "__main__":
    main()
