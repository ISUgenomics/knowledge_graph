#!/usr/bin/env python3
"""
tag_resolver.py — Tag registry loader and resolver.

Ensures tag consistency across the vault by matching candidate tags
against existing tags. No hard cap on new tags — early vault population
needs volume. Fuzzy matching prevents accidental synonyms.
"""

import json
import re
from pathlib import Path

try:
    from build_tag_ontology import DOMAINS, FIELD_TO_DOMAIN
except Exception:
    DOMAINS = {}
    FIELD_TO_DOMAIN = {}

AUTO_TAG_PARENTS = {
    "nobel-prize": "awards",
    "laureate": "awards",
    "physics": "science",
    "chemistry": "science",
    "medicine": "science",
    "physiology": "medicine",
    "physiology-or-medicine": "science",
    "economic-sciences": "science",
    "economics": "science",
    "literature": "humanities",
    "peace": "society",
    "spectroscopy": "physics",
    "quantum-mechanics": "physics",
    "particle-physics": "physics",
    "astrophysics": "physics",
    "organic": "chemistry",
    "organic-chemistry": "chemistry",
    "inorganic": "chemistry",
    "inorganic-chemistry": "chemistry",
    "biochemistry": "chemistry",
}

AUTO_FIELD_TAGS = {
    "physics",
    "chemistry",
    "medicine",
    "physiology-or-medicine",
    "economic-sciences",
    "economics",
    "literature",
    "peace",
    "biology",
    "computing",
    "engineering",
    "education",
    "materials-science",
    "data-science",
    "molecular-biology",
    "biomedical",
    "plant-science",
    "bioinformatics",
    "research-computing",
    "robotics",
}

AUTO_UMBRELLA_TOPIC_TAGS = {
    "nobel-prize",
    "laureate",
}

AUTO_TAG_KEYWORDS = [
    (r"(quantum|relativity|spectroscopy|x-ray|gamma-ray|laser|atomic|black-holes|astronomy|planetary|stellar|topological|photoreceptor|magnetic)", "physics"),
    (r"(chemical|chemistry|synthesis|crystallization|inorganic|organic|polymer)", "chemistry"),
    (r"(graphene|nanoparticle|thin-films|materials|conducting-polymers)", "materials-science"),
    (r"(economic|auction-theory|game-theory|merger|microfinance|income-poverty|poverty-education)", "economic-sciences"),
    (r"(literature|linguistic|history|legal)", "humanities"),
    (r"(peace|military|organ-donation)", "society"),
    (r"(education|pedagogy|outreach)", "education"),
    (r"(robotics)", "robotics"),
    (r"(data-visualization|informatics|data-science)", "data-science"),
    (r"(genetic|genomics|genome|dna|rna|protein-kinase|protein|molecular|cellular|ubiquitin|autophagy|bacteriophage|bacterial|yersinia|trypanosoma|microbial|microbiota|plant-virus|plant-pathogens|nematode|leishmaniasis)", "molecular-biology"),
    (r"(neuro|neural|glaucoma|ophthalmology|cardiomyopathy|liver|renal|metabolism|physiology|medicine|medical-imaging|radiation-therapy|organ-transplantation)", "biomedical"),
    (r"(plant|soybean|legume|agriculture|crop|soil)", "plant-science"),
    (r"(bioinformatics)", "bioinformatics"),
    (r"(facility|laboratory|microscopy|cytometry|metabolomics)", "research-computing"),
]

AUTO_ROOT_TAGS = {
    "biology": {"category": "domain", "description": "Life sciences, organisms, and biological systems"},
    "computing": {"category": "domain", "description": "Computer science, AI, data, and computational methods"},
    "engineering": {"category": "domain", "description": "Engineering, materials, and physical systems"},
    "social-science": {"category": "domain", "description": "Education, outreach, policy, and related social domains"},
    "funding": {"category": "domain", "description": "Funding agencies and program umbrellas"},
    "science": {"category": "domain", "description": "Scientific disciplines and broad research areas"},
    "humanities": {"category": "domain", "description": "Literature and related humanistic disciplines"},
    "society": {"category": "domain", "description": "Peace, civic impact, and public society topics"},
    "awards": {"category": "domain", "description": "Awards, laureates, and prize-related umbrella tags"},
}


# ------------------------------------------------------------------
# Loading: DB-backed registry
# ------------------------------------------------------------------

def load_tag_registry(vault_root: str = ".", db=None) -> dict[str, dict]:
    """
    Load the tag registry from vault.db.

    Returns {tag_name: {"category": str, "description": str}}
    """
    if db is not None:
        return db.get_tag_registry()

    db_path = Path(vault_root) / "vault.db"
    if db_path.exists():
        from vault_db import VaultDB
        with VaultDB(db_path) as auto_db:
            return auto_db.get_tag_registry()

    return {}


def load_tag_aliases(vault_root: str = ".", db=None) -> dict[str, str]:
    """
    Load alias → canonical tag mappings from vault.db.

    Returns {alias: canonical_tag}
    """
    if db is not None:
        return db.get_tag_aliases()

    db_path = Path(vault_root) / "vault.db"
    if db_path.exists():
        from vault_db import VaultDB
        with VaultDB(db_path) as auto_db:
            return auto_db.get_tag_aliases()

    return {}


def _load_registry_md_path(registry_path: str | Path) -> dict[str, dict]:
    """Load tag registry from an explicit markdown file path."""
    registry_path = Path(registry_path)
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


def _load_registry_json_path(registry_path: str | Path) -> dict[str, dict]:
    """Load tag registry from an explicit JSON file path."""
    registry_path = Path(registry_path)
    if not registry_path.exists():
        return {}
    payload = json.loads(registry_path.read_text())
    tags = payload.get("tags", payload if isinstance(payload, dict) else [])
    registry: dict[str, dict] = {}
    if isinstance(tags, dict):
        for tag, info in tags.items():
            registry[tag] = {
                "category": (info or {}).get("category", "topic"),
                "description": (info or {}).get("description", ""),
            }
        return registry
    for item in tags if isinstance(tags, list) else []:
        tag = str((item or {}).get("tag", "")).strip()
        if not tag:
            continue
        registry[tag] = {
            "category": str((item or {}).get("category", "topic")).strip() or "topic",
            "description": str((item or {}).get("description", "")).strip(),
        }
    return registry


def _load_registry_md(vault_root: str) -> dict[str, dict]:
    """Load tag registry from tags/tag-registry.md under a vault root."""
    return _load_registry_md_path(Path(vault_root) / "tags" / "tag-registry.md")


def load_registry_file(registry_path: str | Path) -> dict[str, dict]:
    """Load tag registry from a supported source file path."""
    path = Path(registry_path)
    if path.suffix.lower() == ".json":
        return _load_registry_json_path(path)
    return _load_registry_md_path(path)


def _load_aliases_md_path(alias_path: str | Path) -> dict[str, str]:
    """Load alias → canonical tag mappings from an explicit markdown file path."""
    alias_path = Path(alias_path)
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


def _load_aliases_json_path(alias_path: str | Path) -> dict[str, str]:
    """Load alias mappings from an explicit JSON file path."""
    alias_path = Path(alias_path)
    if not alias_path.exists():
        return {}
    payload = json.loads(alias_path.read_text())
    aliases = payload.get("aliases", payload if isinstance(payload, dict) else [])
    if isinstance(aliases, dict):
        return {str(k).strip(): str(v).strip() for k, v in aliases.items() if str(k).strip() and str(v).strip()}
    resolved: dict[str, str] = {}
    for item in aliases if isinstance(aliases, list) else []:
        alias = str((item or {}).get("alias", "")).strip()
        canonical = str((item or {}).get("canonical", "")).strip()
        if alias and canonical:
            resolved[alias] = canonical
    return resolved


def _load_aliases_md(vault_root: str) -> dict[str, str]:
    """Load alias → canonical tag mappings from tags/tag-aliases.md under a vault root."""
    return _load_aliases_md_path(Path(vault_root) / "tags" / "tag-aliases.md")


def load_aliases_file(alias_path: str | Path) -> dict[str, str]:
    """Load alias mappings from a supported source file path."""
    path = Path(alias_path)
    if path.suffix.lower() == ".json":
        return _load_aliases_json_path(path)
    return _load_aliases_md_path(path)


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
# Saving: DB-backed registry
# ------------------------------------------------------------------

def append_to_registry(
    new_tags: list[str],
    vault_root: str = ".",
    category: str = "topic",
    db=None,
) -> int:
    """
    Append new tags to the DB-backed registry.
    Returns count of tags added.
    """
    if db is not None:
        return _append_to_db(new_tags, db, category)

    db_path = Path(vault_root) / "vault.db"
    if db_path.exists():
        from vault_db import VaultDB
        with VaultDB(db_path) as auto_db:
            return _append_to_db(new_tags, auto_db, category)

    return 0


def _append_to_db(new_tags: list[str], db, category: str) -> int:
    """Insert new tags as tag entities in vault_db."""
    existing = db.get_tag_registry()
    added = 0
    for tag in new_tags:
        if tag not in existing:
            ensure_tag_ontology([tag], db=db, default_category=category)
            added += 1
    return added


def ensure_tag_ontology(
    tags: list[str],
    *,
    db,
    default_category: str = "topic",
) -> list[str]:
    """
    Ensure tags exist in the DB and attach any known ontology parents.

    Returns normalized tag IDs actually ensured.
    """
    ensured = []
    seen = set()
    for raw_tag in tags:
        tag = _kebab_case(raw_tag)
        if not tag or tag in seen:
            continue
        seen.add(tag)
        _ensure_single_tag_ontology(tag, db=db, default_category=default_category)
        ensured.append(tag)
    return ensured


def _ensure_single_tag_ontology(tag: str, *, db, default_category: str = "topic") -> str:
    if tag in AUTO_ROOT_TAGS:
        info = AUTO_ROOT_TAGS[tag]
        db.upsert_tag(tag, category=info["category"], description=info["description"])
        return tag

    if tag in FIELD_TO_DOMAIN:
        parent = FIELD_TO_DOMAIN[tag]
        _ensure_single_tag_ontology(parent, db=db, default_category="domain")
        db.upsert_tag(tag, category="field")
        db.add_broader(tag, parent)
        return tag

    parent = AUTO_TAG_PARENTS.get(tag)
    if parent:
        parent_id = _ensure_single_tag_ontology(parent, db=db, default_category="field")
        category = default_category
        if tag in AUTO_UMBRELLA_TOPIC_TAGS:
            category = "topic"
        elif tag in AUTO_FIELD_TAGS or parent in AUTO_ROOT_TAGS:
            category = "field"
        db.upsert_tag(tag, category=category)
        db.add_broader(tag, parent_id)
        return tag

    for pattern, inferred_parent in AUTO_TAG_KEYWORDS:
        if re.search(pattern, tag):
            parent_id = _ensure_single_tag_ontology(inferred_parent, db=db, default_category="field")
            category = "field" if tag in AUTO_FIELD_TAGS else default_category
            db.upsert_tag(tag, category=category)
            db.add_broader(tag, parent_id)
            return tag

    db.upsert_tag(tag, category=default_category)
    return tag


# ------------------------------------------------------------------
# Markdown import helpers used by migrate_tags.py
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
