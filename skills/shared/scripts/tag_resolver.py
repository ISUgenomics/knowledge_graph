#!/usr/bin/env python3
"""
tag_resolver.py — Tag registry loader and resolver.

Ensures tag consistency across the vault by matching candidate tags
against existing tags. No hard cap on new tags — early vault population
needs volume. Fuzzy matching prevents accidental synonyms.
"""

import re
from pathlib import Path


def load_tag_registry(vault_root: str = ".") -> dict[str, dict]:
    """
    Load the tag registry from tags/tag-registry.md.

    Returns {tag_name: {"category": str, "description": str}}
    """
    registry_path = Path(vault_root) / "tags" / "tag-registry.md"
    if not registry_path.exists():
        return {}

    registry = {}
    in_table = False
    for line in registry_path.read_text().splitlines():
        line = line.strip()
        # Skip frontmatter
        if line == "---":
            continue
        # Detect table rows (skip header and separator)
        if line.startswith("|") and "Tag" not in line and "---" not in line:
            parts = [p.strip() for p in line.split("|")[1:-1]]
            if len(parts) >= 3:
                tag = parts[0].strip()
                category = parts[1].strip()
                description = parts[2].strip()
                if tag:
                    registry[tag] = {"category": category, "description": description}

    return registry


def resolve_tags(
    candidate_tags: list[str],
    registry: dict[str, dict],
) -> tuple[list[str], list[str]]:
    """
    Match candidate tags against the registry. No cap on new tags.

    1. Exact match -> use existing tag
    2. Fuzzy match (edit distance <= 2, or common stem) -> use existing tag
    3. No match -> accept as new tag (kebab-cased)

    Returns:
        (resolved_tags, new_tags_to_add_to_registry)
    """
    resolved = []
    new_tags = []
    seen = set()

    for candidate in candidate_tags:
        normalized = _kebab_case(candidate)
        if not normalized or normalized in seen:
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

        # Score: how many tag-related words appear in the text
        overlap = text_words & all_tag_words
        if overlap:
            # Bonus for tag name itself appearing in text
            tag_in_text = tag.replace("-", " ") in text_lower or tag in text_lower
            score = len(overlap) + (3 if tag_in_text else 0)
            scored.append((tag, score))

    scored.sort(key=lambda x: -x[1])
    return [tag for tag, _ in scored[:max_suggestions]]


def append_to_registry(
    new_tags: list[str],
    vault_root: str = ".",
    category: str = "topic",
) -> int:
    """
    Append new tags to the tag registry file.
    Returns count of tags added.
    """
    registry_path = Path(vault_root) / "tags" / "tag-registry.md"
    if not registry_path.exists():
        return 0

    existing = load_tag_registry(vault_root)
    added = 0

    with open(registry_path, "a") as f:
        for tag in new_tags:
            if tag not in existing:
                f.write(f"| {tag} | {category} | |\n")
                added += 1

    return added


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
        # Substring match
        if candidate in existing or existing in candidate:
            return existing

        # Edit distance
        if _edit_distance(candidate, existing) <= 2:
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
    parser.add_argument("tags", nargs="+", help="Candidate tags to resolve")
    args = parser.parse_args()

    registry = load_tag_registry(args.vault)
    print(f"Registry: {len(registry)} tags loaded")

    resolved, new = resolve_tags(args.tags, registry)
    print(f"Resolved: {resolved}")
    print(f"New tags: {new}")
