#!/usr/bin/env python3
"""
verify_extraction.py — Extract-Verify-Cite pipeline for reliable
unstructured-to-structured data extraction.

Uses LLM for extraction with mandatory source citations,
then deterministically verifies citations against source text.
"""

import json
import re


def parse_llm_json(response: str) -> list[dict] | None:
    """
    Parse JSON from LLM response with fallback strategies.

    1. Strip markdown code fences
    2. json.loads()
    3. Regex extract JSON array
    4. Return None if unrecoverable
    """
    text = response.strip()

    # Strip markdown code fences
    text = re.sub(r"^```(?:json)?\s*\n?", "", text)
    text = re.sub(r"\n?```\s*$", "", text)
    text = text.strip()

    # Try direct parse
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            return [result]
    except json.JSONDecodeError:
        pass

    # Try to extract JSON array from response
    match = re.search(r"\[[\s\S]*\]", text)
    if match:
        try:
            result = json.loads(match.group())
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass

    return None


def verify_extraction(
    extracted: list[dict],
    source_text: str,
    threshold: float = 0.80,
) -> list[dict]:
    """
    Verify LLM extractions against source text.

    For each extracted entry, checks that _source fields are
    actual substrings of the source text (fuzzy match).

    Returns entries with a "verified" field: True/False/Partial
    """
    source_lower = source_text.lower()
    results = []

    for entry in extracted:
        checks = {}
        source_fields = [k for k in entry if k.endswith("_source") and entry[k]]

        for field in source_fields:
            citation = str(entry[field]).strip()
            if not citation:
                continue
            # Check if citation is a substring (fuzzy)
            checks[field] = _fuzzy_substring_match(citation, source_lower, threshold)

        if not source_fields:
            # No source fields — check if the name at least appears in text
            name = entry.get("name", "")
            if name:
                checks["name_in_text"] = name.lower() in source_lower
            entry["verified"] = all(checks.values()) if checks else False
        elif all(checks.values()):
            entry["verified"] = True
        elif any(checks.values()):
            entry["verified"] = "partial"
        else:
            entry["verified"] = False

        entry["_checks"] = checks
        results.append(entry)

    return results


def _fuzzy_substring_match(needle: str, haystack: str, threshold: float) -> bool:
    """
    Check if needle is approximately a substring of haystack.

    Uses a sliding window approach: for each window of len(needle) in haystack,
    compute character overlap ratio. If any window exceeds threshold, return True.
    """
    needle = needle.lower().strip()
    if not needle:
        return False

    # Exact substring
    if needle in haystack:
        return True

    # For short strings, require exact match
    if len(needle) < 10:
        # Check if all words appear
        words = needle.split()
        return all(w in haystack for w in words)

    # Sliding window fuzzy match
    n = len(needle)
    needle_chars = set(needle)

    for i in range(len(haystack) - n + 1):
        window = haystack[i:i + n]
        # Quick pre-check: character overlap
        common = sum(1 for c in needle if c in window)
        if common / n >= threshold:
            # Detailed check: position-wise match
            matches = sum(1 for a, b in zip(needle, window) if a == b)
            if matches / n >= threshold:
                return True

    return False


def estimate_entry_count(text: str) -> int:
    """
    Estimate how many people/entries are in the text.

    Uses heuristics: bullet points, numbered items, table rows, name patterns.
    Returns a rough count for sanity-checking LLM output.
    """
    count = 0

    # Count bullet points / numbered items
    bullets = len(re.findall(r"^[\s]*[-*\u2022•]\s+\S", text, re.MULTILINE))
    numbered = len(re.findall(r"^[\s]*\d+[.)]\s+\S", text, re.MULTILINE))

    # Count table rows (excluding headers/separators)
    table_rows = len(re.findall(r"^\s*\|[^-].*\|", text, re.MULTILINE))
    if table_rows > 2:
        table_rows -= 2  # subtract header + separator

    # Use the largest signal
    count = max(bullets, numbered, table_rows)

    # If no structural signals, estimate by name patterns
    if count == 0:
        # Count "First Last" patterns
        names = len(re.findall(
            r"\b[A-Z][a-z]+\s+[A-Z][a-z]+\b", text
        ))
        count = names // 2  # rough estimate (names appear multiple times)

    return max(count, 0)


def chunk_for_extraction(
    text: str,
    max_chars: int = 6000,
    overlap: int = 500,
) -> list[str]:
    """
    Split text into overlapping chunks for extraction.
    Each chunk is processed independently; results are merged and deduped.
    """
    if len(text) <= max_chars:
        return [text]

    chunks = []
    start = 0
    while start < len(text):
        end = start + max_chars
        chunk = text[start:end]
        chunks.append(chunk)
        start = end - overlap

    return chunks


def dedup_extracted(entries: list[dict], key_field: str = "name") -> list[dict]:
    """
    Deduplicate extracted entries by normalized key field.
    Keeps the first (highest confidence) occurrence.
    """
    seen = set()
    deduped = []
    for entry in entries:
        key = _normalize_key(entry.get(key_field, ""))
        if key and key not in seen:
            seen.add(key)
            deduped.append(entry)
    return deduped


def _normalize_key(s: str) -> str:
    """Normalize a string for dedup comparison."""
    s = s.lower().strip()
    s = re.sub(r"[^a-z\s]", "", s)
    s = re.sub(r"\s+", " ", s)
    return s


# ---------------------------------------------------------------------------
# Extraction prompt builder
# ---------------------------------------------------------------------------
def build_extraction_prompt(
    text: str,
    entity_type: str = "person",
    fields: list[str] | None = None,
) -> str:
    """
    Build an extraction prompt with citation requirements.

    Args:
        text: source text to extract from
        entity_type: what to extract ("person", "presentation", etc.)
        fields: list of fields to extract (default: name, title, department, institution)
    """
    if fields is None:
        fields = ["name", "title", "department", "institution"]

    field_lines = []
    for f in fields:
        field_lines.append(f"- {f}: the {entity_type}'s {f} if mentioned (or null)")
        field_lines.append(f"- {f}_source: the exact text span where you found it (or null)")

    field_str = "\n".join(field_lines)

    return f"""Extract all {entity_type}s mentioned in this text. For each {entity_type}, provide:
{field_str}

Rules:
- Only extract {entity_type}s explicitly named in the text
- Do NOT infer or guess any field — if it's not stated, set it to null
- The _source field must be a verbatim substring of the input text
- Return as a JSON array

Text:
{text}"""


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test extraction verification")
    parser.add_argument("--estimate", help="Estimate entry count in a file")
    args = parser.parse_args()

    if args.estimate:
        text = open(args.estimate).read()
        count = estimate_entry_count(text)
        print(f"Estimated entries: {count}")
