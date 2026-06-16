#!/usr/bin/env python3
"""Backfill abstract note tags from PMID/DOI metadata into vault markdown source."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "person_research" / "scripts"))

from builder_config import get_tagging_policy
from build_profile import generate_publication_tags, normalize_publication_tags
from migrate_vault import parse_frontmatter
from research_person import _fetch_pubmed_abstracts
from tag_resolver import _kebab_case, load_aliases_file, load_registry_file


def _load_registry_and_aliases(vault_path: Path, config_path: str | Path | None) -> tuple[dict[str, dict], dict[str, str]]:
    tagging_policy = get_tagging_policy(config_path)
    ontology = tagging_policy.get("ontology", {}) or {}
    registry_path = ontology.get("registry_path") or (vault_path / "tags" / "tag-registry.md")
    aliases_path = ontology.get("aliases_path") or (vault_path / "tags" / "tag-aliases.md")
    registry = load_registry_file(registry_path) if registry_path else {}
    aliases = load_aliases_file(aliases_path) if aliases_path and Path(aliases_path).exists() else {}
    return registry, aliases


def _extract_abstract(text: str) -> str:
    match = re.search(r"## Abstract\s*\n\n(.+?)(?:\n\n##|\Z)", text, re.DOTALL)
    return match.group(1).strip() if match else ""


def _fetch_openalex_topics(doi: str, registry: dict[str, dict] | None = None) -> list[str]:
    if not doi or doi == "N/A":
        return []
    import httpx

    normalized = doi.strip()
    if normalized.startswith("doi:"):
        normalized = normalized[4:]
    if not normalized.startswith("http://") and not normalized.startswith("https://"):
        normalized = f"https://doi.org/{normalized}"
    url = f"https://api.openalex.org/works/{normalized}"
    try:
        resp = httpx.get(url, timeout=20)
        resp.raise_for_status()
        payload = resp.json()
    except Exception:
        return []

    topics = [t.get("display_name", "").strip() for t in (payload.get("topics") or []) if t.get("display_name")]
    if topics:
        return topics[:10]

    fallback = []
    for concept in payload.get("concepts") or []:
        display_name = concept.get("display_name", "").strip()
        if not display_name:
            continue
        normalized = _kebab_case(display_name)
        if registry and registry.get(normalized, {}).get("category") != "field":
            continue
        fallback.append(display_name)
    return fallback[:10]


def _replace_tags_line(text: str, tags: list[str]) -> str:
    tag_str = ", ".join(tags)
    replacement = f"tags: [{tag_str}]"
    if re.search(r"^tags:\s*\[[^\]]*\]\s*$", text, re.MULTILINE):
        return re.sub(r"^tags:\s*\[[^\]]*\]\s*$", replacement, text, count=1, flags=re.MULTILINE)
    if re.search(r"^tags:\s*$", text, re.MULTILINE):
        return re.sub(r"^tags:\s*$", replacement, text, count=1, flags=re.MULTILINE)
    return text


def enrich_abstract_tags(
    vault_root: str | Path,
    *,
    config_path: str | Path | None = None,
    limit: int = 0,
    rewrite_existing: bool = False,
) -> dict:
    vault_path = Path(vault_root)
    abstracts_dir = vault_path / "abstracts"
    registry, aliases = _load_registry_and_aliases(vault_path, config_path)

    files = sorted(abstracts_dir.glob("*.md"))
    if limit > 0:
        files = files[:limit]

    note_data: list[dict] = []
    pmids: list[str] = []
    for path in files:
        text = path.read_text()
        fm = parse_frontmatter(text)
        existing_tags = list(fm.get("tags", []) or [])
        if existing_tags and not rewrite_existing:
            continue
        pmid = str(fm.get("pmid", "") or "").strip()
        doi = str(fm.get("doi", "") or "").strip()
        note_data.append({
            "path": path,
            "text": text,
            "existing_tags": existing_tags,
            "title": str(fm.get("title", path.stem) or path.stem),
            "journal": str(fm.get("journal", "") or ""),
            "pmid": pmid,
            "doi": doi,
            "abstract": _extract_abstract(text),
        })
        if pmid:
            pmids.append(pmid)

    mesh_map: dict[str, list[str]] = {}
    for start in range(0, len(pmids), 100):
        _, batch_mesh = _fetch_pubmed_abstracts(pmids[start:start + 100])
        mesh_map.update(batch_mesh)

    updated = 0
    used_pubmed = 0
    used_openalex = 0
    unchanged = 0

    for note in note_data:
        topics: list[str] = []
        mesh_terms = mesh_map.get(note["pmid"], [])
        if mesh_terms:
            used_pubmed += 1
        if note["doi"] and not mesh_terms:
            topics = _fetch_openalex_topics(note["doi"], registry=registry)
            if topics:
                used_openalex += 1
        elif note["doi"]:
            extra_topics = _fetch_openalex_topics(note["doi"], registry=registry)
            if extra_topics:
                topics = extra_topics
                used_openalex += 1

        paper = {
            "title": note["title"],
            "journal": note["journal"],
            "abstract": note["abstract"],
            "topics": topics,
            "mesh_terms": mesh_terms,
        }
        resolved_tags = generate_publication_tags(paper, registry=registry, aliases=aliases)
        if rewrite_existing:
            cleaned_existing = normalize_publication_tags(
                note["existing_tags"],
                registry=registry,
                aliases=aliases,
            )
            if cleaned_existing and len(cleaned_existing) > len(resolved_tags):
                resolved_tags = cleaned_existing
            elif not resolved_tags:
                resolved_tags = cleaned_existing
        resolved_tags = resolved_tags[:10]
        if not resolved_tags and not (rewrite_existing and note["existing_tags"]):
            unchanged += 1
            continue

        new_text = _replace_tags_line(note["text"], resolved_tags)
        if new_text == note["text"]:
            unchanged += 1
            continue
        note["path"].write_text(new_text)
        updated += 1

    return {
        "scanned": len(note_data),
        "updated": updated,
        "unchanged": unchanged,
        "used_pubmed": used_pubmed,
        "used_openalex": used_openalex,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill abstract note tags from PMID/DOI metadata")
    parser.add_argument("--vault", required=True, help="Path to vault root containing abstracts/")
    parser.add_argument("--config", default=None, help="Optional KGX config file with db_build tagging policy")
    parser.add_argument("--limit", type=int, default=0, help="Only process the first N abstract notes")
    parser.add_argument("--rewrite", action="store_true", help="Rewrite notes that already have tags")
    args = parser.parse_args()

    stats = enrich_abstract_tags(
        args.vault,
        config_path=args.config,
        limit=args.limit,
        rewrite_existing=args.rewrite,
    )
    print(stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
