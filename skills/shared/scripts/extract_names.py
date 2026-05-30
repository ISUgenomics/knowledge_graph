#!/usr/bin/env python3
"""
extract_names.py — Regex-based name candidate extraction from text.

Conservative: extracts candidates with surrounding context.
The LLM or user disambiguates. Does NOT attempt identity resolution.
"""

import re


# Common academic title prefixes
_TITLES = r"(?:Dr\.?|Prof\.?|Professor|Mr\.?|Ms\.?|Mrs\.?)"

# Common academic suffixes
_SUFFIXES = r"(?:Ph\.?D\.?|M\.?D\.?|D\.?V\.?M\.?|M\.?S\.?|M\.?A\.?|Jr\.?|Sr\.?|III?|IV)"

# A capitalized name part: First, First-Middle, O'Brien, etc.
_NAME_PART = r"[A-Z][a-z]+(?:[-'][A-Z]?[a-z]+)*"

# Optional middle initial: "A." or "A"
_MIDDLE = r"(?:\s+[A-Z]\.?)?"


def extract_names_from_text(text: str, context_chars: int = 100) -> list[dict]:
    """
    Extract person name candidates from text using pattern matching.

    Returns list of:
        {
            "name": str,
            "context": str,
            "confidence": "high" | "medium" | "low",
            "pattern": str,
        }
    """
    candidates = []
    seen_names = set()

    # Pattern 1 (high confidence): Title + Name
    # "Dr. Jane Doe", "Professor Bob Smith", "Prof. Alice M. Jones"
    pattern1 = re.compile(
        rf"\b{_TITLES}\s+({_NAME_PART}{_MIDDLE}\s+{_NAME_PART})\b"
    )
    for m in pattern1.finditer(text):
        name = _normalize_name(m.group(1))
        if name and name not in seen_names:
            seen_names.add(name)
            candidates.append({
                "name": name,
                "context": _get_context(text, m.start(), context_chars),
                "confidence": "high",
                "pattern": "title_prefix",
            })

    # Pattern 2 (high confidence): Name + suffix
    # "Jane Doe, PhD", "Bob Smith, M.D."
    pattern2 = re.compile(
        rf"\b({_NAME_PART}{_MIDDLE}\s+{_NAME_PART}),?\s+{_SUFFIXES}\b"
    )
    for m in pattern2.finditer(text):
        name = _normalize_name(m.group(1))
        if name and name not in seen_names:
            seen_names.add(name)
            candidates.append({
                "name": name,
                "context": _get_context(text, m.start(), context_chars),
                "confidence": "high",
                "pattern": "name_suffix",
            })

    # Pattern 3 (medium confidence): "Last, First" format (common in rosters)
    pattern3 = re.compile(
        rf"\b({_NAME_PART}),\s+({_NAME_PART}(?:\s+[A-Z]\.?)?)\b"
    )
    for m in pattern3.finditer(text):
        last = m.group(1)
        first = m.group(2)
        # Skip common false positives
        if last.lower() in _SKIP_WORDS or first.lower() in _SKIP_WORDS:
            continue
        name = _normalize_name(f"{first} {last}")
        if name and name not in seen_names:
            seen_names.add(name)
            candidates.append({
                "name": name,
                "context": _get_context(text, m.start(), context_chars),
                "confidence": "medium",
                "pattern": "last_first",
            })

    # Pattern 4 (medium confidence): Two capitalized words in list context
    # Lines starting with bullet/number followed by a name
    pattern4 = re.compile(
        rf"^[\s]*[-*\u2022•]?\s*\d*\.?\s*({_NAME_PART}{_MIDDLE}\s+{_NAME_PART})\b",
        re.MULTILINE,
    )
    for m in pattern4.finditer(text):
        name = _normalize_name(m.group(1))
        if name and name not in seen_names and not _is_false_positive(name):
            seen_names.add(name)
            candidates.append({
                "name": name,
                "context": _get_context(text, m.start(), context_chars),
                "confidence": "medium",
                "pattern": "list_item",
            })

    return candidates


def _normalize_name(name: str) -> str:
    """Clean up a name: collapse whitespace, strip trailing periods."""
    name = re.sub(r"\s+", " ", name).strip().rstrip(".")
    parts = name.split()
    if len(parts) < 2:
        return ""
    # Filter out single-character parts that aren't initials
    return " ".join(parts)


def _get_context(text: str, pos: int, chars: int) -> str:
    """Get surrounding context around a position in text."""
    start = max(0, pos - chars // 2)
    end = min(len(text), pos + chars // 2)
    return text[start:end].replace("\n", " ").strip()


# Words that look like names but aren't (common false positives)
_SKIP_WORDS = {
    "the", "and", "for", "with", "from", "this", "that", "will",
    "have", "been", "were", "not", "but", "all", "can", "had",
    "her", "was", "one", "our", "out", "are", "has", "his",
    "how", "its", "let", "may", "new", "now", "old", "see",
    "way", "who", "did", "get", "got", "him", "hit", "own",
    "say", "she", "too", "use", "about", "after", "also",
    "abstract", "introduction", "methods", "results", "discussion",
    "conclusion", "references", "acknowledgments", "figure", "table",
    "university", "department", "college", "school", "institute",
    "center", "facility", "office", "program", "project",
    "january", "february", "march", "april", "june", "july",
    "august", "september", "october", "november", "december",
    "monday", "tuesday", "wednesday", "thursday", "friday",
    "saturday", "sunday",
}


def _is_false_positive(name: str) -> bool:
    """Check if a name candidate is likely a false positive."""
    parts = name.lower().split()
    # Both parts are common words
    if all(p in _SKIP_WORDS for p in parts):
        return True
    # First word is a month/day (e.g., "March Meeting")
    if parts[0] in _SKIP_WORDS:
        return True
    return False


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Extract name candidates from text")
    parser.add_argument("file", help="Path to text file")
    args = parser.parse_args()

    text = open(args.file).read()
    names = extract_names_from_text(text)
    print(json.dumps(names, indent=2))
    print(f"\n{len(names)} candidates found")
