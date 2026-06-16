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
from build_tag_ontology import apply_ontology
from builder_config import get_tagging_policy, get_visualization_policy
from promote_person_tags import promote_person_tags
from tag_resolver import ensure_tag_ontology, load_registry_file
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
    return [target.split("|", 1)[0] for target in re.findall(r"\[\[([a-z0-9][a-z0-9._/-]*(?:\|[^\]]+)?)\]\]", text)]


def strip_wiki_link(val) -> str:
    """Extract slug from '[[slug]]' or return raw value."""
    if not isinstance(val, str):
        val = str(val) if val else ""
    if not val:
        return ""
    m = re.search(r"\[\[([a-z0-9][a-z0-9._/-]*)", val)
    return m.group(1) if m else val.strip().lower().replace(" ", "-")


def _json_list(values) -> list[dict]:
    """Parse list[str] of JSON blobs from frontmatter into dicts."""
    results: list[dict] = []
    for value in values or []:
        if not value:
            continue
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            results.append(parsed)
    return results


def _entity_id_from_note(target: str, prefix: str) -> str:
    """Convert vault links like `awards/foo` into canonical entity IDs."""
    cleaned = target.strip()
    if cleaned.startswith(f"{prefix}/"):
        cleaned = cleaned.split("/", 1)[1]
    if cleaned.endswith(".md"):
        cleaned = cleaned[:-3]
    return f"{prefix[:-1]}:{cleaned}"


# ---------------------------------------------------------------------------
# Importers
# ---------------------------------------------------------------------------
def import_tags(db: VaultDB, vault: Path, tagging_policy: dict | None = None):
    """Import tags from the configured registry source."""
    registry = None
    if tagging_policy:
        registry = tagging_policy.get("ontology", {}).get("registry_path")
    if not registry:
        registry = vault / "tags" / "tag-registry.md"
    registry = Path(registry)
    if not registry.exists():
        return 0
    count = 0
    for tag_id, info in load_registry_file(registry).items():
        category = info.get("category", "topic")
        description = info.get("description", "")
        ensured = ensure_tag_ontology([tag_id], db=db, default_category=category)
        if ensured:
            db.upsert_entity("tag", ensured[0], name=tag_id,
                             metadata={"category": category, "description": description})
        count += 1
    return count


def _entity_tag_policy(tagging_policy: dict, entity_type: str) -> dict:
    return (tagging_policy.get("entity_policies", {}) or {}).get(entity_type, {}) or {}


def _attach_tags(
    db: VaultDB,
    entity_id: str,
    entity_type: str,
    tags: list[str],
    tagging_policy: dict | None = None,
):
    policy = _entity_tag_policy(tagging_policy or {}, entity_type)
    if policy and not policy.get("enabled", True):
        return 0
    default_category = policy.get("default_category", "topic")
    relationship_type = policy.get("relationship_type", "TAGGED")
    ensured_tags = ensure_tag_ontology(list(tags or []), db=db, default_category=default_category)
    for tag_id in ensured_tags:
        db.add_relationship(entity_id, relationship_type, tag_id)
    return len(ensured_tags)


def import_people(db: VaultDB, vault: Path, tagging_policy: dict | None = None):
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
            "extensions": fm.get("extensions", []),
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

        _attach_tags(db, slug, "person", tags, tagging_policy)

        # Coauthors
        coauthor_section = re.search(r"## Coauthors\s*\n((?:- \[\[.+\]\]\n?)+)",
                                     text, re.DOTALL)
        if coauthor_section:
            for co_slug in extract_wiki_links(coauthor_section.group(1)):
                co_id = db.ensure_entity("person", co_slug, name=co_slug)
                db.add_coauthor_relationship(slug, co_id)

        for record in _json_list(fm.get("award_records", [])):
            award_id = record.get("id", "")
            if not award_id:
                continue
            db.upsert_entity("award", award_id, name=record.get("title", award_id), metadata=record)
            db.add_relationship(slug, "WON", award_id, metadata={
                "award_year": record.get("year", ""),
                "category": record.get("category", ""),
            })

        for record in _json_list(fm.get("organization_records", [])):
            org_id = record.get("id", "")
            if not org_id:
                continue
            db.upsert_entity("organization", org_id, name=record.get("title", org_id), metadata=record)
            db.add_relationship(slug, "AFFILIATED_WITH", org_id)

        awards_section = re.search(r"## Awards\s*\n(.*?)(?=\n##|\Z)", text, re.DOTALL)
        if awards_section:
            for award_target in extract_wiki_links(awards_section.group(1)):
                if not award_target.startswith("awards/"):
                    continue
                award_id = _entity_id_from_note(award_target, "awards")
                db.ensure_entity("award", award_id, name=award_id)
                db.add_relationship(slug, "WON", award_id)

        affiliations_section = re.search(r"## Affiliations\s*\n(.*?)(?=\n##|\Z)", text, re.DOTALL)
        if affiliations_section:
            for org_target in extract_wiki_links(affiliations_section.group(1)):
                if not org_target.startswith("organizations/"):
                    continue
                org_id = _entity_id_from_note(org_target, "organizations")
                db.ensure_entity("organization", org_id, name=org_id)
                db.add_relationship(slug, "AFFILIATED_WITH", org_id)

        count += 1
    return count


def import_awards(db: VaultDB, vault: Path):
    """Import award notes."""
    awards_dir = vault / "awards"
    if not awards_dir.exists():
        return 0
    count = 0
    for f in sorted(awards_dir.glob("*.md")):
        text = f.read_text()
        fm = parse_frontmatter(text)
        award_id = fm.get("id", f"award:{f.stem}")
        meta = {
            "title": fm.get("title", f.stem),
            "year": fm.get("year", ""),
            "category": fm.get("category", ""),
            "category_full_name": fm.get("category_full_name", ""),
            "date_awarded": fm.get("date_awarded", ""),
            "source_url": fm.get("source_url", ""),
        }
        motivation_match = re.search(r"## Motivation\s*\n\n(.+?)(?:\n\n##|\Z)", text, re.DOTALL)
        if motivation_match:
            meta["motivation"] = motivation_match.group(1).strip()
        db.upsert_entity("award", award_id, name=meta["title"], metadata=meta)
        count += 1
    return count


def import_organizations(db: VaultDB, vault: Path):
    """Import organization notes."""
    org_dir = vault / "organizations"
    if not org_dir.exists():
        return 0
    count = 0
    for f in sorted(org_dir.glob("*.md")):
        text = f.read_text()
        fm = parse_frontmatter(text)
        org_id = fm.get("id", f"organization:{f.stem}")
        meta = {
            "title": fm.get("title", f.stem),
            "city": fm.get("city", ""),
            "country": fm.get("country", ""),
            "location": fm.get("location", ""),
        }
        db.upsert_entity("organization", org_id, name=meta["title"], metadata=meta)
        count += 1
    return count


def import_abstracts(db: VaultDB, vault: Path, tagging_policy: dict | None = None):
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
        _attach_tags(db, pub_id, "publication", fm.get("tags", []), tagging_policy)

        count += 1
    return count


def import_signals(db: VaultDB, vault: Path, tagging_policy: dict | None = None):
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
        _attach_tags(db, slug, "signal", fm.get("tags", []), tagging_policy)

        count += 1
    return count


def import_events(db: VaultDB, vault: Path, tagging_policy: dict | None = None):
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
        _attach_tags(db, slug, "event", fm.get("tags", []), tagging_policy)

        # hosted_by → center relationship
        if meta["hosted_by"]:
            center_id = db.ensure_entity("center", meta["hosted_by"],
                                         name=meta["hosted_by"])
            db.add_relationship(slug, "MEMBER_OF", center_id)

        count += 1
    return count


def audit_visualization_contract(db: VaultDB, visualization_policy: dict | None = None) -> list[str]:
    """Return human-readable warnings for missing arrangement-critical metadata."""
    policy = visualization_policy or {}
    timeline = policy.get("timeline", {}) or {}
    hierarchical = policy.get("hierarchical", {}) or {}
    required_by_type = timeline.get("required_metadata_by_type", {}) or {}
    warnings: list[str] = []
    default_family_types = {"person", "publication", "organization", "tag"}

    for entity_type, fields in sorted(required_by_type.items()):
        if not fields:
            continue
        rows = db.conn.execute(
            "SELECT id, metadata FROM entities WHERE type = ?",
            (entity_type,),
        ).fetchall()
        if not rows:
            warnings.append(
                f"visualization: type '{entity_type}' is declared as timeline-capable but no entities were imported"
            )
            continue
        missing = 0
        for entity_id, metadata_json in rows:
            try:
                metadata = json.loads(metadata_json or "{}")
            except json.JSONDecodeError:
                metadata = {}
            if any(metadata.get(field) in ("", None, []) for field in fields):
                missing += 1
        if missing:
            warnings.append(
                f"visualization: {missing}/{len(rows)} '{entity_type}' entities are missing required timeline metadata fields {fields}"
            )

    preferred_anchor_types = timeline.get("preferred_anchor_types", []) or []
    anchor_order_fields = timeline.get("anchor_order_fields", {}) or {}
    for entity_type in preferred_anchor_types:
        if not anchor_order_fields.get(entity_type):
            warnings.append(
                f"visualization: preferred timeline anchor type '{entity_type}' has no configured order fields"
            )

    relation_classes = hierarchical.get("relation_classes", {}) or {}
    declared_rel_types: set[str] = set()
    for rels in relation_classes.values():
        declared_rel_types.update(rels or [])
    rel_rows = db.conn.execute(
        "SELECT rel_type, COUNT(*) FROM relationships GROUP BY rel_type"
    ).fetchall()
    uncategorized = sorted(rel_type for rel_type, _count in rel_rows if rel_type not in declared_rel_types)
    if uncategorized:
        warnings.append(
            f"visualization: uncategorized relationship types present in DB: {', '.join(uncategorized)}"
        )

    family_overrides = hierarchical.get("type_families", {}) or {}
    type_rows = db.conn.execute("SELECT DISTINCT type FROM entities ORDER BY type").fetchall()
    unclassified_types = [
        entity_type
        for (entity_type,) in type_rows
        if entity_type not in default_family_types and entity_type not in family_overrides
    ]
    if unclassified_types:
        warnings.append(
            f"visualization: entity types missing hierarchical family mapping: {', '.join(unclassified_types)}"
        )

    return warnings


def repair_visualization_contract(db: VaultDB, visualization_policy: dict | None = None) -> list[str]:
    """Backfill canonical timeline order fields from configured metadata aliases."""
    policy = visualization_policy or {}
    timeline = policy.get("timeline", {}) or {}
    anchor_order_fields = timeline.get("anchor_order_fields", {}) or {}
    field_aliases = timeline.get("field_aliases", {}) or {}
    changed: list[str] = []

    for entity_type, canonical_fields in sorted(anchor_order_fields.items()):
        rows = db.conn.execute(
            "SELECT id, metadata FROM entities WHERE type = ?",
            (entity_type,),
        ).fetchall()
        for entity_id, metadata_json in rows:
            try:
                metadata = json.loads(metadata_json or "{}")
            except json.JSONDecodeError:
                metadata = {}
            updated = False
            for canonical in canonical_fields:
                if metadata.get(canonical) not in ("", None, []):
                    continue
                for alias in field_aliases.get(canonical, []) or []:
                    alias_value = metadata.get(alias)
                    if alias_value not in ("", None, []):
                        metadata[canonical] = alias_value
                        updated = True
                        break
            if updated:
                db.conn.execute(
                    "UPDATE entities SET metadata = ?, updated_at = datetime('now') WHERE id = ?",
                    (json.dumps(metadata, ensure_ascii=False, separators=(",", ":")), entity_id),
                )
                changed.append(entity_id)

    if changed:
        db.conn.commit()
    return changed


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def migrate(vault: Path, db_path: Path, *, config_path: str | Path | None = None):
    """Run the full migration."""
    if db_path.exists():
        print(f"WARNING: {db_path} already exists. Overwriting.")
        db_path.unlink()

    db = VaultDB(db_path)
    tagging_policy = get_tagging_policy(config_path)
    visualization_policy = get_visualization_policy(config_path)

    print(f"Vault:  {vault}")
    print(f"DB:     {db_path}\n")

    print("Importing...")
    tag_count = import_tags(db, vault, tagging_policy)
    print(f"  Tags (registry): {tag_count}")

    person_count = import_people(db, vault, tagging_policy)
    print(f"  People: {person_count}")

    abstract_count = import_abstracts(db, vault, tagging_policy)
    print(f"  Abstracts: {abstract_count}")

    award_count = import_awards(db, vault)
    print(f"  Awards: {award_count}")

    organization_count = import_organizations(db, vault)
    print(f"  Organizations: {organization_count}")

    signal_count = import_signals(db, vault, tagging_policy)
    print(f"  Signals: {signal_count}")

    event_count = import_events(db, vault, tagging_policy)
    print(f"  Events: {event_count}")

    hierarchy_path = tagging_policy.get("ontology", {}).get("hierarchy_path")
    if tagging_policy.get("ontology", {}).get("apply_on_build") and hierarchy_path and Path(hierarchy_path).exists():
        ontology = json.loads(Path(hierarchy_path).read_text())
        stats = apply_ontology(db, ontology)
        print(f"  Ontology applied: {stats}")

    promotion_stats = promote_person_tags(db, config_path=config_path)
    if promotion_stats.get("enabled"):
        print(f"  Person tag promotion: {promotion_stats}")

    repaired_ids = repair_visualization_contract(db, visualization_policy)
    if repaired_ids:
        print(f"  Visualization repair: backfilled canonical timeline fields for {len(repaired_ids)} entities")

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

    viz_warnings = audit_visualization_contract(db, visualization_policy)
    if viz_warnings:
        print(f"\nVisualization contract warnings:")
        for warning in viz_warnings:
            print(f"  - {warning}")

    db.close()
    print(f"\nDone. Database at: {db_path}")


def main():
    parser = argparse.ArgumentParser(description="Migrate Obsidian vault to SQLite")
    parser.add_argument("--vault", default=None, help="Path to vault root")
    parser.add_argument("--db", default=None, help="Output database path")
    parser.add_argument("--config", default=None, help="Optional KGX config file with db_build tagging policy")
    args = parser.parse_args()

    vault = Path(args.vault) if args.vault else Path(__file__).resolve().parents[2] / "vault"
    db_path = Path(args.db) if args.db else vault / "vault.db"

    if not vault.exists():
        print(f"ERROR: Vault not found at {vault}")
        sys.exit(1)

    migrate(vault, db_path, config_path=args.config)


if __name__ == "__main__":
    main()
