#!/usr/bin/env python3
"""
tag_resolver.py — Tag registry loader and resolver.

Ensures tag consistency across the vault by matching candidate tags
against existing tags. No hard cap on new tags — early vault population
needs volume. Fuzzy matching prevents accidental synonyms.

Supports two backends:
  - SQLite (vault_db) — preferred, tags are entities in vault.db
  - Markdown fallback — reads tags/tag-registry.md and tags/tag-aliases.md
"""

import re
from pathlib import Path


# ------------------------------------------------------------------
# Loading: DB-first, markdown fallback
# ------------------------------------------------------------------

def load_tag_registry(vault_root: str = ".", db=None) -> dict[str, dict]:
    """
    Load the tag registry. Tries DB first, falls back to markdown.

    Returns {tag_name: {"category": str, "description": str}}
    """
    if db is not None:
        return db.get_tag_registry()

    # Try DB auto-discovery
    db_path = Path(vault_root) / "vault.db"
    if db_path.exists():
        from vault_db import VaultDB
        with VaultDB(db_path) as auto_db:
            registry = auto_db.get_tag_registry()
            if registry:
                return registry

    # Markdown fallback
    return _load_registry_md(vault_root)


def load_tag_aliases(vault_root: str = ".", db=None) -> dict[str, str]:
    """
    Load alias → canonical tag mappings. Tries DB first, falls back to markdown.

    Returns {alias: canonical_tag}
    """
    if db is not None:
        return db.get_tag_aliases()

    db_path = Path(vault_root) / "vault.db"
    if db_path.exists():
        from vault_db import VaultDB
        with VaultDB(db_path) as auto_db:
            aliases = auto_db.get_tag_aliases()
            if aliases:
                return aliases

    return _load_aliases_md(vault_root)


def _load_registry_md(vault_root: str) -> dict[str, dict]:
    """Load tag registry from tags/tag-registry.md."""
    registry_path = Path(vault_root) / "tags" / "tag-registry.md"
    if not registry_path.exists():
        return {}

    registry = {}
    for line in registry_path.read_text().splitlines():
        line = line.strip()
        if line == "---":
            continue
        if line.startswith("|") and "Tag" not in line and "---" not in line:
            parts = [p.strip() for p in line.split("|")[1:-1]]
            if len(parts) >= 3:
                tag = parts[0].strip()
                category = parts[1].strip()
                description = parts[2].strip()
                if tag:
                    registry[tag] = {"category": category, "description": description}
    return registry


def _load_aliases_md(vault_root: str) -> dict[str, str]:
    """Load alias → canonical tag mappings from tags/tag-aliases.md."""
    alias_path = Path(vault_root) / "tags" / "tag-aliases.md"
    if not alias_path.exists():
        return {}

    aliases = {}
    for line in alias_path.read_text().splitlines():
        line = line.strip()
        if line == "---":
            continue
        if line.startswith("|") and "Alias" not in line and "---" not in line:
            parts = [p.strip() for p in line.split("|")[1:-1]]
            if len(parts) >= 2:
                alias = parts[0].strip()
                canonical = parts[1].strip()
                if alias and canonical:
                    aliases[alias] = canonical
    return aliases


# ------------------------------------------------------------------
# Resolution
# ------------------------------------------------------------------

def resolve_tags(
    candidate_tags: list[str],
    registry: dict[str, dict],
    aliases: dict[str, str] | None = None,
) -> tuple[list[str], list[str]]:
    """
    Match candidate tags against the registry. No cap on new tags.

    1. Alias lookup -> use canonical tag
    2. Exact match -> use existing tag
    3. Fuzzy match (edit distance <= 2, or common stem) -> use existing tag
    4. No match -> accept as new tag (kebab-cased)

    Returns:
        (resolved_tags, new_tags_to_add_to_registry)
    """
    if aliases is None:
        aliases = {}

    resolved = []
    new_tags = []
    seen = set()

    for candidate in candidate_tags:
        normalized = _kebab_case(candidate)
        if not normalized or normalized in seen:
            continue

        # Alias lookup (exact match on known synonyms)
        if normalized in aliases:
            canonical = aliases[normalized]
            if canonical not in seen:
                resolved.append(canonical)
                seen.add(canonical)
            continue

        # Exact match
        if normalized in registry:
            resolved.append(normalized)
            seen.add(normalized)
            continue

        # Fuzzy match against existing tags
        match = _fuzzy_find(normalized, registry)
        if match:
            resolved.append(match)
            seen.add(match)
            continue

        # New tag
        resolved.append(normalized)
        new_tags.append(normalized)
        seen.add(normalized)

    return resolved, new_tags


def suggest_tags_from_text(
    text: str,
    registry: dict[str, dict],
    max_suggestions: int = 10,
) -> list[str]:
    """
    Suggest tags from the registry that match the given text.
    Uses keyword overlap between text and tag names/descriptions.
    Returns ranked list of existing tags.
    """
    text_lower = text.lower()
    text_words = set(re.findall(r"[a-z]{3,}", text_lower))

    scored = []
    for tag, info in registry.items():
        tag_words = set(tag.replace("-", " ").split())
        desc_words = set(re.findall(r"[a-z]{3,}", info.get("description", "").lower()))
        all_tag_words = tag_words | desc_words

        overlap = text_words & all_tag_words
        if overlap:
            tag_in_text = tag.replace("-", " ") in text_lower or tag in text_lower
            score = len(overlap) + (3 if tag_in_text else 0)
            scored.append((tag, score))

    scored.sort(key=lambda x: -x[1])
    return [tag for tag, _ in scored[:max_suggestions]]


# ------------------------------------------------------------------
# Saving: DB-first, markdown fallback
# ------------------------------------------------------------------

def append_to_registry(
    new_tags: list[str],
    vault_root: str = ".",
    category: str = "topic",
    db=None,
) -> int:
    """
    Append new tags to the registry. Uses DB if available, else markdown.
    Returns count of tags added.
    """
    if db is not None:
        return _append_to_db(new_tags, db, category)

    db_path = Path(vault_root) / "vault.db"
    if db_path.exists():
        from vault_db import VaultDB
        with VaultDB(db_path) as auto_db:
            return _append_to_db(new_tags, auto_db, category)

    return _append_to_registry_md(new_tags, vault_root, category)


def _append_to_db(new_tags: list[str], db, category: str) -> int:
    """Insert new tags as tag entities in vault_db."""
    existing = db.get_tag_registry()
    added = 0
    for tag in new_tags:
        if tag not in existing:
            db.upsert_tag(tag, category=category)
            added += 1
    return added


def _append_to_registry_md(
    new_tags: list[str],
    vault_root: str = ".",
    category: str = "topic",
) -> int:
    """Append new tags to the markdown tag registry file."""
    registry_path = Path(vault_root) / "tags" / "tag-registry.md"
    if not registry_path.exists():
        return 0

    existing = _load_registry_md(vault_root)
    added = 0

    with open(registry_path, "a") as f:
        for tag in new_tags:
            if tag not in existing:
                f.write(f"| {tag} | {category} | |\n")
                added += 1

    return added


# ------------------------------------------------------------------
# Fuzzy matching helpers
# ------------------------------------------------------------------

def _kebab_case(s: str) -> str:
    """Convert a string to kebab-case tag format."""
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"-+", "-", s)
    return s.strip("-")


def _fuzzy_find(candidate: str, registry: dict[str, dict]) -> str | None:
    """
    Find a fuzzy match in the registry.

    Checks:
    1. One is a substring of the other (e.g., "genomic" matches "genomics")
    2. Edit distance <= 2
    3. Shared stems after splitting on hyphens
    """
    candidate_parts = set(candidate.split("-"))

    for existing in registry:
        # Substring match (only if both are > 3 chars to avoid false positives)
        if len(candidate) > 3 and len(existing) > 3:
            if candidate in existing or existing in candidate:
                return existing

        # Edit distance — scale threshold with tag length to avoid
        # short-tag false positives like "nlp" -> "nsf"
        min_len = min(len(candidate), len(existing))
        max_edit = 1 if min_len <= 5 else 2
        if _edit_distance(candidate, existing) <= max_edit:
            return existing

        # Shared stem: >60% of parts overlap
        existing_parts = set(existing.split("-"))
        overlap = candidate_parts & existing_parts
        total = candidate_parts | existing_parts
        if total and len(overlap) / len(total) > 0.6:
            return existing

    return None


def _edit_distance(a: str, b: str) -> int:
    """Compute Levenshtein edit distance."""
    if len(a) < len(b):
        return _edit_distance(b, a)
    if len(b) == 0:
        return len(a)

    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        curr = [i + 1]
        for j, cb in enumerate(b):
            cost = 0 if ca == cb else 1
            curr.append(min(curr[j] + 1, prev[j + 1] + 1, prev[j] + cost))
        prev = curr
    return prev[len(b)]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Resolve tags against registry")
    parser.add_argument("--vault", default=".", help="Vault root directory")
    parser.add_argument("--db", default="", help="Path to vault.db (overrides --vault auto-discovery)")
    parser.add_argument("tags", nargs="+", help="Candidate tags to resolve")
    args = parser.parse_args()

    db = None
    if args.db:
        from vault_db import VaultDB
        db = VaultDB(args.db)

    registry = load_tag_registry(args.vault, db=db)
    aliases = load_tag_aliases(args.vault, db=db)
    print(f"Registry: {len(registry)} tags loaded")
    print(f"Aliases: {len(aliases)} aliases loaded")

    resolved, new = resolve_tags(args.tags, registry, aliases)
    print(f"Resolved: {resolved}")
    print(f"New tags: {new}")

    if db:
        db.close()
