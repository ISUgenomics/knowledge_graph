#!/usr/bin/env python3
"""
extract_snippets.py — Extract context snippets around keywords from text.

Used by signal-capture (and other skills) to show topic and people context
in Obsidian notes.
"""

import re


def extract_snippets(
    text: str,
    keyword: str,
    context_chars: int = 200,
    max_snippets: int = 5,
) -> list[str]:
    """
    Extract text snippets surrounding occurrences of a keyword.

    Args:
        text: Full source text to search
        keyword: Keyword or phrase to find (case-insensitive)
        context_chars: Number of characters of context on each side
        max_snippets: Maximum number of snippets to return

    Returns:
        List of snippet strings with the keyword highlighted in **bold**.
    """
    if not text or not keyword:
        return []

    pattern = re.compile(re.escape(keyword), re.IGNORECASE)
    matches = list(pattern.finditer(text))

    if not matches:
        return []

    snippets = []
    used_ranges = []

    for match in matches:
        if len(snippets) >= max_snippets:
            break

        start = max(0, match.start() - context_chars)
        end = min(len(text), match.end() + context_chars)

        # Skip if this range overlaps significantly with a previous one
        overlaps = False
        for prev_start, prev_end in used_ranges:
            overlap = min(end, prev_end) - max(start, prev_start)
            if overlap > context_chars:
                overlaps = True
                break
        if overlaps:
            continue

        used_ranges.append((start, end))
        snippets.append(_format_snippet(text, start, end, pattern))

    return snippets


def _format_snippet(text: str, start: int, end: int, bold_pattern=None) -> str:
    """Extract a snippet from text[start:end], clean it, optionally bold a pattern."""
    snippet = text[start:end]
    if start > 0:
        snippet = "..." + snippet.lstrip()
    if end < len(text):
        snippet = snippet.rstrip() + "..."
    snippet = re.sub(r"\s+", " ", snippet)
    if bold_pattern:
        snippet = bold_pattern.sub(lambda m: f"**{m.group()}**", snippet)
    return snippet


# ---------------------------------------------------------------------------
# Quote / keyword extraction for people
# ---------------------------------------------------------------------------

# Verbs that introduce direct or indirect speech
_SPEECH_VERBS = (
    r"said|says|stated|explained|noted|added|described|recalled|"
    r"emphasized|stressed|observed|commented|mentioned|argued|"
    r"suggested|told|reported|announced|warned|acknowledged|"
    r"believes|predicts|envisions|hopes|proposed|according to"
)

# High-value context keywords (near a person's name = more interesting snippet)
_CONTEXT_KEYWORDS = re.compile(
    r"goal|mission|purpose|vision|aim|focus|lead|direct|found|"
    r"develop|discover|create|launch|award|grant|fund|partner|"
    r"collaborate|pioneer|innovate|research|project|initiative",
    re.IGNORECASE,
)


def _find_quotes(text: str, name: str, context_chars: int = 250) -> list[str]:
    """
    Find direct quotes attributed to a person.

    Strategy: find attribution points (Name said / said Name), then expand
    outward to capture the full quoted passage — including continuation
    quotes like:  "First part," Name said. "Second part."
    """
    name_esc = re.escape(name)
    name_pat = re.compile(re.escape(name), re.IGNORECASE)

    # Find attribution points: "Name said" or "said Name" (with speech verbs)
    attr_patterns = [
        # "..." said/says Name
        re.compile(
            rf'(?:{_SPEECH_VERBS})\s+{name_esc}',
            re.IGNORECASE,
        ),
        # Name said/says "..."
        re.compile(
            rf'{name_esc}\s+(?:{_SPEECH_VERBS})',
            re.IGNORECASE,
        ),
        # according to Name
        re.compile(
            rf'according\s+to\s+{name_esc}',
            re.IGNORECASE,
        ),
    ]

    # Collect all attribution positions
    attr_positions = []
    for pat in attr_patterns:
        for m in pat.finditer(text):
            attr_positions.append(m.start())

    if not attr_positions:
        return []

    # Deduplicate nearby positions (within 50 chars = same attribution)
    attr_positions.sort()
    deduped = [attr_positions[0]]
    for pos in attr_positions[1:]:
        if pos - deduped[-1] > 50:
            deduped.append(pos)
    attr_positions = deduped

    snippets = []
    quote_chars = re.compile(r'["\u201c\u201d]')

    for attr_pos in attr_positions:
        # Expand backward to find the opening quote
        search_start = max(0, attr_pos - 600)
        before = text[search_start:attr_pos]
        # Find the last opening quote before the attribution
        quote_positions = [m.start() for m in quote_chars.finditer(before)]
        if quote_positions:
            # Walk back to find the outermost opening quote of this passage
            # (skip quote marks that are part of nested/earlier quotes)
            start = search_start + quote_positions[-1]
            # Check one more back — if there's a quote close then open nearby,
            # it might be a multi-sentence quote
            for qp in reversed(quote_positions[:-1]):
                abs_qp = search_start + qp
                gap = start - abs_qp
                # If there's another quote mark within 80 chars, it's likely
                # the real start of a multi-sentence quote
                if gap < 80:
                    start = abs_qp
                else:
                    break
        else:
            start = max(0, attr_pos - context_chars)

        # Expand forward to find the closing quote(s)
        search_end = min(len(text), attr_pos + 600)
        after = text[attr_pos:search_end]
        quote_positions_after = [m.start() for m in quote_chars.finditer(after)]

        if quote_positions_after:
            # Find the last closing quote in a reasonable range
            # Look for pattern: attribution ... "continuation quote."
            end = attr_pos
            for qp in quote_positions_after:
                candidate_end = attr_pos + qp + 1
                # Stop if we've gone too far past the attribution
                if qp > 500:
                    break
                end = candidate_end

                # Check if this looks like a closing quote (followed by
                # whitespace, punctuation, or end)
                next_pos = attr_pos + qp + 1
                if next_pos < len(text):
                    next_char = text[next_pos]
                    # If followed by a newline or period+space, this is likely
                    # the final closing quote
                    if next_char in '\n' or (next_pos + 1 < len(text) and
                                             text[next_pos:next_pos+2] in ('. ', '.\n')):
                        break
        else:
            end = min(len(text), attr_pos + context_chars)

        # Add small padding for context
        start = max(0, start - 20)
        end = min(len(text), end + 20)

        snippet = _format_snippet(text, start, end, name_pat)
        snippets.append(snippet)

    return _dedup_snippets(snippets)


def _find_keyword_mentions(
    text: str, name: str, context_chars: int = 200, max_snippets: int = 3,
) -> list[str]:
    """
    Find mentions of a person near high-value context keywords
    (goal, mission, lead, discover, etc.).
    """
    name_pat = re.compile(re.escape(name), re.IGNORECASE)
    matches = list(name_pat.finditer(text))

    if not matches:
        return []

    scored = []
    for m in matches:
        start = max(0, m.start() - context_chars)
        end = min(len(text), m.end() + context_chars)
        window = text[start:end]

        # Score by how many context keywords appear nearby
        keyword_hits = _CONTEXT_KEYWORDS.findall(window)
        if keyword_hits:
            scored.append((len(keyword_hits), start, end))

    # Sort by keyword density descending
    scored.sort(key=lambda x: -x[0])

    snippets = []
    used_ranges = []
    for _, start, end in scored:
        if len(snippets) >= max_snippets:
            break
        # Skip overlapping ranges
        overlaps = False
        for ps, pe in used_ranges:
            if min(end, pe) - max(start, ps) > context_chars:
                overlaps = True
                break
        if overlaps:
            continue
        used_ranges.append((start, end))
        snippets.append(_format_snippet(text, start, end, name_pat))

    return snippets


def _dedup_snippets(snippets: list[str], threshold: int = 80) -> list[str]:
    """Remove near-duplicate snippets by checking first N chars."""
    seen = []
    result = []
    for s in snippets:
        norm = re.sub(r"\*\*", "", s)[:threshold].lower()
        if not any(norm[:40] in prev for prev in seen):
            seen.append(norm)
            result.append(s)
    return result


def extract_person_snippets(
    text: str,
    people: list[dict],
    context_chars: int = 150,
    max_per_person: int = 2,
) -> dict[str, list[str]]:
    """
    Extract context snippets for each person mentioned in the text.

    Priority order:
      1. Direct quotes attributed to the person
      2. Mentions near high-value keywords (goal, mission, lead, discover, etc.)
      3. Basic name-proximity context (fallback)

    Args:
        text: Full source text
        people: List of person dicts with at least a "name" key
        context_chars: Characters of context on each side
        max_per_person: Max snippets per person

    Returns:
        Dict mapping person name -> list of snippets
    """
    if not text or not people:
        return {}

    result = {}
    for person in people:
        name = person.get("name", "")
        if not name:
            continue

        collected = []

        # 1. Direct quotes (highest priority)
        quotes = _find_quotes(text, name, context_chars=context_chars)
        collected.extend(quotes)

        # 2. Keyword-rich mentions
        if len(collected) < max_per_person:
            keyword_snippets = _find_keyword_mentions(
                text, name, context_chars=context_chars,
                max_snippets=max_per_person - len(collected),
            )
            collected.extend(keyword_snippets)

        # 3. Fallback: basic name proximity
        if len(collected) < max_per_person:
            basic = extract_snippets(
                text, name,
                context_chars=context_chars,
                max_snippets=max_per_person - len(collected),
            )
            collected.extend(basic)

        # Deduplicate and trim
        collected = _dedup_snippets(collected)[:max_per_person]

        if collected:
            result[name] = collected

    return result
