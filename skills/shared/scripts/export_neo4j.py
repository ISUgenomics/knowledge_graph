#!/usr/bin/env python3
"""
export_neo4j.py — Export Obsidian vault to Neo4j-importable CSV files.

Generates node and relationship CSVs that can be loaded with:
    LOAD CSV WITH HEADERS FROM 'file:///nodes_person.csv' AS row ...

Or with neo4j-admin import:
    neo4j-admin database import full --nodes=nodes_person.csv ...

Usage:
    python export_neo4j.py                          # default vault path
    python export_neo4j.py --vault /path/to/vault
    python export_neo4j.py --vault /path/to/vault --output /path/to/csvs
    python export_neo4j.py --cypher                 # also generate a Cypher load script
"""
import argparse
import csv
import re
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# YAML frontmatter parser (minimal, no PyYAML dependency)
# ---------------------------------------------------------------------------
def parse_frontmatter(text: str) -> dict:
    """Parse YAML frontmatter from markdown text. Returns dict of fields."""
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return {}
    fm = {}
    current_key = None
    list_values = []

    for line in m.group(1).splitlines():
        # List item under a key
        list_match = re.match(r"^\s+-\s+(.+)", line)
        if list_match and current_key:
            val = list_match.group(1).strip().strip('"').strip("'")
            list_values.append(val)
            fm[current_key] = list_values
            continue

        # Key: value
        kv_match = re.match(r"^(\w[\w_-]*)\s*:\s*(.*)", line)
        if kv_match:
            current_key = kv_match.group(1)
            val = kv_match.group(2).strip().strip('"').strip("'")
            # Inline list: [a, b, c]
            if val.startswith("[") and val.endswith("]"):
                fm[current_key] = [v.strip().strip('"').strip("'")
                                   for v in val[1:-1].split(",") if v.strip()]
                list_values = fm[current_key]
            elif val:
                fm[current_key] = val
                list_values = []
            else:
                # Value may follow as list items
                list_values = []
                fm[current_key] = list_values
            continue

        # Nested key (sources, etc.) — skip
        if re.match(r"^\s+\w", line) and ":" in line and not list_match:
            continue

    return fm


def extract_wiki_links(text: str) -> list[str]:
    """Extract all [[slug]] wiki-links from text."""
    return re.findall(r"\[\[([a-z0-9][a-z0-9-]*)\]\]", text)


# ---------------------------------------------------------------------------
# Vault readers
# ---------------------------------------------------------------------------
def read_people(vault: Path) -> list[dict]:
    people_dir = vault / "people"
    if not people_dir.exists():
        return []
    nodes = []
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

        # Extract department/title from Contact table
        dept_match = re.search(r"\|\s*Department\s*\|\s*(.+?)\s*\|", text)
        title_match = re.search(r"\|\s*Title\s*\|\s*(.+?)\s*\|", text)

        slug = md.stem
        nodes.append({
            "id": slug,
            "name": fm.get("aliases", [slug])[0] if isinstance(fm.get("aliases"), list) else slug,
            "role": fm.get("role", ""),
            "department": dept_match.group(1).strip() if dept_match else "",
            "title": title_match.group(1).strip() if title_match else "",
            "institution": fm.get("institution", "Iowa State University"),
            "tags": fm.get("tags", []),
            "coauthors": extract_wiki_links(
                # Only from Coauthors section
                re.search(r"## Coauthors\s*\n((?:- \[\[.+\]\]\n?)+)", text, re.DOTALL).group(1)
                if re.search(r"## Coauthors", text) else ""
            ),
        })
    return nodes


def read_abstracts(vault: Path) -> list[dict]:
    abstracts_dir = vault / "abstracts"
    if not abstracts_dir.exists():
        return []
    nodes = []
    for f in sorted(abstracts_dir.glob("*.md")):
        text = f.read_text()
        fm = parse_frontmatter(text)
        # Authors are wiki-links in frontmatter
        raw_authors = fm.get("authors", [])
        authors = []
        for a in raw_authors:
            m = re.search(r"\[\[([a-z0-9-]+)\]\]", a)
            if m:
                authors.append(m.group(1))
        nodes.append({
            "id": f.stem,
            "title": fm.get("title", f.stem),
            "year": fm.get("year", ""),
            "journal": fm.get("journal", ""),
            "doi": fm.get("doi", ""),
            "pmid": fm.get("pmid", ""),
            "tags": fm.get("tags", []),
            "authors": authors,
        })
    return nodes


def read_signals(vault: Path) -> list[dict]:
    signals_dir = vault / "signals"
    if not signals_dir.exists():
        return []
    nodes = []
    for f in sorted(signals_dir.glob("*.md")):
        if f.name.startswith("."):
            continue
        text = f.read_text()
        fm = parse_frontmatter(text)
        # People mentioned — extract from wiki-links in People section
        people_section = re.search(r"## People Mentioned\s*\n(.*?)(?=\n##|\Z)", text, re.DOTALL)
        people_links = extract_wiki_links(people_section.group(1)) if people_section else []
        nodes.append({
            "id": f.stem,
            "title": fm.get("title", f.stem) if fm.get("title") else f.stem,
            "source": fm.get("source", ""),
            "url": fm.get("url", ""),
            "published": fm.get("published", ""),
            "tags": fm.get("tags", []),
            "people": people_links,
        })
    return nodes


def read_events(vault: Path) -> list[dict]:
    events_dir = vault / "events"
    if not events_dir.exists():
        return []
    nodes = []
    for d in sorted(events_dir.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        md = d / f"{d.name}.md"
        if not md.exists():
            continue
        text = md.read_text()
        fm = parse_frontmatter(text)
        attendees = extract_wiki_links(text)
        nodes.append({
            "id": d.name,
            "title": fm.get("title", d.name),
            "date": fm.get("date", ""),
            "event_type": fm.get("event_type", ""),
            "location": fm.get("location", ""),
            "tags": fm.get("tags", []),
            "attendees": attendees,
        })
    return nodes


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------
def write_csv(path: Path, rows: list[dict], fieldnames: list[str]):
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"  {path.name}: {len(rows)} rows")


def export(vault: Path, output: Path, generate_cypher: bool = False):
    output.mkdir(parents=True, exist_ok=True)

    # --- Read vault ---
    people = read_people(vault)
    abstracts = read_abstracts(vault)
    signals = read_signals(vault)
    events = read_events(vault)

    # Collect all tags as nodes
    all_tags = set()
    for collection in [people, abstracts, signals, events]:
        for item in collection:
            for t in item.get("tags", []):
                all_tags.add(t)

    print(f"Vault: {len(people)} people, {len(abstracts)} abstracts, "
          f"{len(signals)} signals, {len(events)} events, {len(all_tags)} tags\n")

    # --- Node CSVs ---
    print("Nodes:")
    write_csv(output / "nodes_person.csv",
              [{"personId": p["id"], "name": p["name"], "role": p["role"],
                "department": p["department"], "title": p["title"],
                "institution": p["institution"]} for p in people],
              ["personId", "name", "role", "department", "title", "institution"])

    write_csv(output / "nodes_abstract.csv",
              [{"abstractId": a["id"], "title": a["title"], "year": a["year"],
                "journal": a["journal"], "doi": a["doi"], "pmid": a["pmid"]}
               for a in abstracts],
              ["abstractId", "title", "year", "journal", "doi", "pmid"])

    write_csv(output / "nodes_signal.csv",
              [{"signalId": s["id"], "title": s["title"], "source": s["source"],
                "url": s["url"], "published": s["published"]}
               for s in signals],
              ["signalId", "title", "source", "url", "published"])

    write_csv(output / "nodes_event.csv",
              [{"eventId": e["id"], "title": e["title"], "date": e["date"],
                "eventType": e["event_type"], "location": e["location"]}
               for e in events],
              ["eventId", "title", "date", "eventType", "location"])

    write_csv(output / "nodes_tag.csv",
              [{"tagId": t} for t in sorted(all_tags)],
              ["tagId"])

    # --- Relationship CSVs ---
    print("\nRelationships:")

    # AUTHORED: Person → Abstract
    authored = []
    for a in abstracts:
        for author_slug in a["authors"]:
            authored.append({"personId": author_slug, "abstractId": a["id"]})
    write_csv(output / "rels_authored.csv", authored, ["personId", "abstractId"])

    # MENTIONED_IN: Person → Signal
    mentioned = []
    for s in signals:
        for person_slug in s["people"]:
            mentioned.append({"personId": person_slug, "signalId": s["id"]})
    write_csv(output / "rels_mentioned_in.csv", mentioned, ["personId", "signalId"])

    # ATTENDED: Person → Event
    attended = []
    for e in events:
        for person_slug in e["attendees"]:
            attended.append({"personId": person_slug, "eventId": e["id"]})
    write_csv(output / "rels_attended.csv", attended, ["personId", "eventId"])

    # TAGGED: any node → Tag
    tagged = []
    for p in people:
        for t in p.get("tags", []):
            tagged.append({"sourceId": p["id"], "sourceType": "Person", "tagId": t})
    for a in abstracts:
        for t in a.get("tags", []):
            tagged.append({"sourceId": a["id"], "sourceType": "Abstract", "tagId": t})
    for s in signals:
        for t in s.get("tags", []):
            tagged.append({"sourceId": s["id"], "sourceType": "Signal", "tagId": t})
    for e in events:
        for t in e.get("tags", []):
            tagged.append({"sourceId": e["id"], "sourceType": "Event", "tagId": t})
    write_csv(output / "rels_tagged.csv", tagged, ["sourceId", "sourceType", "tagId"])

    # COAUTHOR: Person ↔ Person (from coauthors section)
    coauthor_pairs = set()
    for p in people:
        for co in p.get("coauthors", []):
            pair = tuple(sorted([p["id"], co]))
            coauthor_pairs.add(pair)
    write_csv(output / "rels_coauthor.csv",
              [{"personId1": a, "personId2": b} for a, b in sorted(coauthor_pairs)],
              ["personId1", "personId2"])

    # --- Cypher load script ---
    if generate_cypher:
        cypher_path = output / "load.cypher"
        cypher_path.write_text(_build_cypher_script())
        print(f"\n  {cypher_path.name}: Cypher load script generated")

    print(f"\nDone. Import with:\n  neo4j-admin database import full \\\n"
          f"    --nodes=Person={output}/nodes_person.csv \\\n"
          f"    --nodes=Abstract={output}/nodes_abstract.csv \\\n"
          f"    --nodes=Signal={output}/nodes_signal.csv \\\n"
          f"    --nodes=Event={output}/nodes_event.csv \\\n"
          f"    --nodes=Tag={output}/nodes_tag.csv \\\n"
          f"    --relationships=AUTHORED={output}/rels_authored.csv \\\n"
          f"    --relationships=MENTIONED_IN={output}/rels_mentioned_in.csv \\\n"
          f"    --relationships=ATTENDED={output}/rels_attended.csv \\\n"
          f"    --relationships=TAGGED={output}/rels_tagged.csv \\\n"
          f"    --relationships=COAUTHOR={output}/rels_coauthor.csv\n")
    print(f"Or use LOAD CSV in Neo4j Browser — see {output}/load.cypher")


def _build_cypher_script() -> str:
    return """\
// ============================================================
// Neo4j Cypher load script for ISU Knowledge Vault
// Run in Neo4j Browser or via cypher-shell
// Place CSV files in the Neo4j import/ directory first
// ============================================================

// --- Constraints & indexes ---
CREATE CONSTRAINT person_id IF NOT EXISTS FOR (p:Person) REQUIRE p.id IS UNIQUE;
CREATE CONSTRAINT abstract_id IF NOT EXISTS FOR (a:Abstract) REQUIRE a.id IS UNIQUE;
CREATE CONSTRAINT signal_id IF NOT EXISTS FOR (s:Signal) REQUIRE s.id IS UNIQUE;
CREATE CONSTRAINT event_id IF NOT EXISTS FOR (e:Event) REQUIRE e.id IS UNIQUE;
CREATE CONSTRAINT tag_id IF NOT EXISTS FOR (t:Tag) REQUIRE t.id IS UNIQUE;

// --- Nodes ---
LOAD CSV WITH HEADERS FROM 'file:///nodes_person.csv' AS row
MERGE (p:Person {id: row.personId})
SET p.name = row.name, p.role = row.role, p.department = row.department,
    p.title = row.title, p.institution = row.institution;

LOAD CSV WITH HEADERS FROM 'file:///nodes_abstract.csv' AS row
MERGE (a:Abstract {id: row.abstractId})
SET a.title = row.title, a.year = toInteger(row.year), a.journal = row.journal,
    a.doi = row.doi, a.pmid = row.pmid;

LOAD CSV WITH HEADERS FROM 'file:///nodes_signal.csv' AS row
MERGE (s:Signal {id: row.signalId})
SET s.title = row.title, s.source = row.source, s.url = row.url,
    s.published = row.published;

LOAD CSV WITH HEADERS FROM 'file:///nodes_event.csv' AS row
MERGE (e:Event {id: row.eventId})
SET e.title = row.title, e.date = row.date, e.eventType = row.eventType,
    e.location = row.location;

LOAD CSV WITH HEADERS FROM 'file:///nodes_tag.csv' AS row
MERGE (t:Tag {id: row.tagId});

// --- Relationships ---
LOAD CSV WITH HEADERS FROM 'file:///rels_authored.csv' AS row
MATCH (p:Person {id: row.personId})
MATCH (a:Abstract {id: row.abstractId})
MERGE (p)-[:AUTHORED]->(a);

LOAD CSV WITH HEADERS FROM 'file:///rels_mentioned_in.csv' AS row
MATCH (p:Person {id: row.personId})
MATCH (s:Signal {id: row.signalId})
MERGE (p)-[:MENTIONED_IN]->(s);

LOAD CSV WITH HEADERS FROM 'file:///rels_attended.csv' AS row
MATCH (p:Person {id: row.personId})
MATCH (e:Event {id: row.eventId})
MERGE (p)-[:ATTENDED]->(e);

LOAD CSV WITH HEADERS FROM 'file:///rels_tagged.csv' AS row
CALL {
  WITH row
  MATCH (t:Tag {id: row.tagId})
  WITH row, t
  CALL {
    WITH row, t
    WITH row, t WHERE row.sourceType = 'Person'
    MATCH (n:Person {id: row.sourceId})
    MERGE (n)-[:TAGGED]->(t)
  }
  CALL {
    WITH row, t
    WITH row, t WHERE row.sourceType = 'Abstract'
    MATCH (n:Abstract {id: row.sourceId})
    MERGE (n)-[:TAGGED]->(t)
  }
  CALL {
    WITH row, t
    WITH row, t WHERE row.sourceType = 'Signal'
    MATCH (n:Signal {id: row.sourceId})
    MERGE (n)-[:TAGGED]->(t)
  }
  CALL {
    WITH row, t
    WITH row, t WHERE row.sourceType = 'Event'
    MATCH (n:Event {id: row.sourceId})
    MERGE (n)-[:TAGGED]->(t)
  }
} IN TRANSACTIONS OF 500 ROWS;

LOAD CSV WITH HEADERS FROM 'file:///rels_coauthor.csv' AS row
MATCH (p1:Person {id: row.personId1})
MATCH (p2:Person {id: row.personId2})
MERGE (p1)-[:COAUTHOR]-(p2);

// --- Summary ---
MATCH (n) RETURN labels(n)[0] AS label, count(n) AS count ORDER BY count DESC;
"""


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Export Obsidian vault to Neo4j CSV files")
    parser.add_argument("--vault", default=None, help="Path to vault root")
    parser.add_argument("--output", default=None, help="Output directory for CSV files")
    parser.add_argument("--cypher", action="store_true", help="Also generate Cypher load script")
    args = parser.parse_args()

    vault = Path(args.vault) if args.vault else Path(__file__).resolve().parents[2] / "vault"
    output = Path(args.output) if args.output else vault / "neo4j-export"

    if not vault.exists():
        print(f"ERROR: Vault not found at {vault}")
        sys.exit(1)

    print(f"Vault:  {vault}")
    print(f"Output: {output}\n")
    export(vault, output, generate_cypher=args.cypher)


if __name__ == "__main__":
    main()
