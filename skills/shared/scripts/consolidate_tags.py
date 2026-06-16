#!/usr/bin/env python3
"""
consolidate_tags.py — Find and merge duplicate tags in vault.db.

Uses a two-stage pipeline:
  1. Fuzzy scan finds candidate clusters (fast, deterministic)
  2. LLM validates/corrects clusters (accurate, catches semantic issues)

Modes:
    --scan              Fuzzy scan only, write proposed merges to JSON.
    --scan --llm        Fuzzy scan + LLM validation of candidates.
    --llm-scan          LLM groups ALL tags from scratch (full semantic pass).
    --apply FILE        Apply merges from a reviewed JSON file.
    --auto              Scan + LLM validate + apply in one step.

The scan picks a "winner" per cluster using these criteria (in order):
  1. Tag exists in the curated registry (has a description)
  2. Tag already has aliases registered
  3. Shortest tag name (prefer concise canonical forms)
  4. Most incoming TAGGED relationships (most used)

Merge operation (via VaultDB.merge_tags):
  - Re-points all TAGGED relationships from loser → winner
  - Transfers loser's aliases to winner
  - Adds loser ID as alias of winner
  - Deletes loser entity

Usage:
    # Fuzzy scan only (fast, may have false positives)
    python consolidate_tags.py /path/to/vault --scan -o merges.json

    # Fuzzy scan + LLM validation (recommended)
    python consolidate_tags.py /path/to/vault --scan --llm -o merges.json

    # Full LLM semantic grouping (slow, best recall)
    python consolidate_tags.py /path/to/vault --llm-scan -o merges.json

    # Review merges.json, then apply
    python consolidate_tags.py /path/to/vault --apply merges.json

    # One-shot: scan + validate + apply
    python consolidate_tags.py /path/to/vault --auto
"""

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from vault_db import VaultDB
from tag_resolver import _edit_distance

OLLAMA_BASE = "http://localhost:11434"
DEFAULT_MODEL = "qwen3-coder:30b"


# ------------------------------------------------------------------
# Ollama helper
# ------------------------------------------------------------------

def _llm_chat(messages: list[dict], model: str = DEFAULT_MODEL) -> str:
    """Send messages to Ollama, return assistant reply text."""
    import httpx
    resp = httpx.post(
        f"{OLLAMA_BASE}/v1/chat/completions",
        json={
            "model": model,
            "messages": messages,
            "temperature": 0.0,
            "stream": False,
        },
        timeout=600.0,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def _llm_available(model: str = DEFAULT_MODEL) -> bool:
    """Check if Ollama is reachable."""
    import httpx
    try:
        r = httpx.get(f"{OLLAMA_BASE}/api/tags", timeout=3.0)
        return r.status_code == 200
    except Exception:
        return False


# ------------------------------------------------------------------
# DB helpers
# ------------------------------------------------------------------

def _tag_degree(db: VaultDB, tag_id: str) -> int:
    """Count incoming TAGGED relationships for a tag."""
    row = db.conn.execute(
        "SELECT COUNT(*) AS cnt FROM relationships WHERE target_id = ? AND rel_type = 'TAGGED'",
        (tag_id,),
    ).fetchone()
    return row["cnt"]


def _alias_count(db: VaultDB, tag_id: str) -> int:
    """Count aliases for a tag."""
    row = db.conn.execute(
        "SELECT COUNT(*) AS cnt FROM aliases WHERE entity_id = ?",
        (tag_id,),
    ).fetchone()
    return row["cnt"]


def _pick_winner(db: VaultDB, cluster: list[str], registry: dict) -> str:
    """Pick the best canonical tag from a cluster."""
    def score(tag_id):
        has_desc = 1 if registry.get(tag_id, {}).get("description") else 0
        has_aliases = 1 if _alias_count(db, tag_id) > 0 else 0
        shortness = -len(tag_id)
        degree = _tag_degree(db, tag_id)
        return (has_desc, has_aliases, shortness, degree)

    return max(cluster, key=score)


# ------------------------------------------------------------------
# Stage 1: Fuzzy scan (deterministic)
# ------------------------------------------------------------------

def _match_reason(t1: str, t2: str) -> str | None:
    """Return why t1 and t2 match, or None if they don't."""
    parts1 = t1.split("-")
    parts2 = t2.split("-")
    set1 = set(parts1)
    set2 = set(parts2)

    # Whole-word subset: one tag's words are a strict subset of the other's
    if len(set1) >= 2 and len(set2) >= 2:
        if set1 < set2 or set2 < set1:
            return "word_subset"

    # Pluralization: differ only by trailing 's'
    if (t1 + "s" == t2) or (t2 + "s" == t1):
        return "plural"

    # Edit distance 1, but only if they share a hyphenated word
    if min(len(t1), len(t2)) > 5:
        dist = _edit_distance(t1, t2)
        if dist == 1 and (set1 & set2):
            return "edit_dist=1"

    # Stem overlap: > 75% of hyphenated parts overlap
    overlap = set1 & set2
    total = set1 | set2
    if len(total) >= 3 and len(overlap) / len(total) > 0.75:
        return f"stem_overlap={len(overlap)}/{len(total)}"

    return None


def scan_duplicates(db: VaultDB) -> list[dict]:
    """Find fuzzy duplicate clusters among all tag entities."""
    registry = db.get_tag_registry()
    tag_ids = sorted(registry.keys())
    seen = set()
    clusters = []

    for i, t1 in enumerate(tag_ids):
        if t1 in seen:
            continue
        group = [t1]
        reasons = {}

        for t2 in tag_ids[i + 1:]:
            if t2 in seen:
                continue
            reason = _match_reason(t1, t2)
            if reason:
                group.append(t2)
                reasons[t2] = reason
                seen.add(t2)

        if len(group) > 1:
            seen.add(t1)
            winner = _pick_winner(db, group, registry)

            # Validate: each loser must match the winner directly
            losers = []
            for t in group:
                if t == winner:
                    continue
                reason = _match_reason(winner, t) or reasons.get(t)
                if reason:
                    losers.append(t)
                    reasons[t] = reason

            if not losers:
                continue

            reason_parts = [f"{l} ({reasons.get(l, 'cluster')})" for l in losers]
            clusters.append({
                "winner": winner,
                "losers": losers,
                "reason": "; ".join(reason_parts),
            })

    return clusters


# ------------------------------------------------------------------
# Stage 2: LLM validation of fuzzy candidates
# ------------------------------------------------------------------

def llm_validate_merges(merges: list[dict], model: str = DEFAULT_MODEL) -> list[dict]:
    """
    Send fuzzy-matched clusters to the LLM to filter false positives
    and correct winner choices.
    """
    if not merges:
        return []

    # Build a compact representation for the prompt
    cluster_lines = []
    for i, m in enumerate(merges):
        all_tags = [m["winner"]] + m["losers"]
        cluster_lines.append(f"{i}: {', '.join(all_tags)}")

    prompt = f"""You are a tag taxonomy expert. I have {len(merges)} proposed tag merges.
Each cluster groups tags that a fuzzy matcher thinks are duplicates.

For each cluster, decide:
1. Are these truly the same concept? (reject if they are meaningfully different)
2. Which tag should be the canonical winner? (prefer short, clear, general terms)

Clusters:
{chr(10).join(cluster_lines)}

Return ONLY a JSON array. Each element:
{{"id": <cluster index>, "action": "merge" or "reject", "winner": "<chosen winner tag>", "losers": ["<tags to merge into winner>"], "reason": "<brief reason>"}}

For rejected clusters, still include the entry with action "reject" and empty losers.
Do not include any text outside the JSON array. /no_think"""

    print(f"  Sending {len(merges)} clusters to {model} for validation...")
    raw = _llm_chat([{"role": "user", "content": prompt}], model=model)

    # Parse JSON from response (handle markdown code blocks)
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()

    try:
        results = json.loads(raw)
    except json.JSONDecodeError:
        # Try to find JSON array in response
        start = raw.find("[")
        end = raw.rfind("]") + 1
        if start >= 0 and end > start:
            results = json.loads(raw[start:end])
        else:
            print(f"  WARNING: Could not parse LLM response, keeping fuzzy results")
            return merges

    # Rebuild merges from LLM output
    validated = []
    rejected = 0
    corrected = 0
    for r in results:
        if r.get("action") == "reject":
            rejected += 1
            continue

        idx = r.get("id", -1)
        winner = r.get("winner", "")
        losers = r.get("losers", [])

        if not winner or not losers:
            continue

        # Check if LLM changed the winner from our pick
        if 0 <= idx < len(merges) and winner != merges[idx]["winner"]:
            corrected += 1

        validated.append({
            "winner": winner,
            "losers": losers,
            "reason": r.get("reason", "llm-validated"),
        })

    print(f"  LLM result: {len(validated)} approved, {rejected} rejected, {corrected} winner-corrected")
    return validated


# ------------------------------------------------------------------
# Full LLM semantic scan (no fuzzy pre-filter)
# ------------------------------------------------------------------

def llm_scan_all_tags(db: VaultDB, model: str = DEFAULT_MODEL) -> list[dict]:
    """
    Send ALL tags to the LLM for semantic duplicate detection.

    Strategy: send the full tag list (compact, one line) and ask the LLM
    to output ONLY the merge groups. Most tags have no duplicates, so the
    output is much smaller than the input — this keeps generation fast.

    Falls back to batching if the tag list exceeds ~500 tags.
    """
    registry = db.get_tag_registry()
    tag_ids = sorted(registry.keys())

    # Split into batches of 500 (fits in context, output stays small)
    batch_size = 500
    all_clusters = []

    total_batches = (len(tag_ids) + batch_size - 1) // batch_size
    print(f"  Sending {len(tag_ids)} tags to {model} in {total_batches} batch(es)...")

    for batch_start in range(0, len(tag_ids), batch_size):
        batch = tag_ids[batch_start:batch_start + batch_size]
        batch_num = batch_start // batch_size + 1
        if total_batches > 1:
            print(f"  Batch {batch_num}/{total_batches} ({len(batch)} tags)...")

        tag_block = "\n".join(batch)

        prompt = f"""You are a tag taxonomy expert. Below are {len(batch)} tags from a research knowledge base.
Find tags that are REDUNDANT — same concept, different wording — and should be merged.

IMPORTANT:
- Only merge true synonyms (e.g. "covid-19" and "sars-cov-2", "nematode" and "nematoda")
- Do NOT merge related-but-distinct tags (e.g. "plant-genetics" ≠ "plant-breeding")
- Pick the shortest, clearest tag as the canonical winner
- Most tags will have NO duplicates — only output the ones that do

Tags:
{tag_block}

Return ONLY a JSON array of merge groups. Keep it short — most tags need no merging.
{{"winner": "<canonical>", "losers": ["<redundant>"], "reason": "<2-3 words>"}}

If nothing to merge, return []. No other text. /no_think"""

        raw = None
        for attempt in range(3):
            try:
                raw = _llm_chat([{"role": "user", "content": prompt}], model=model)
                break
            except Exception as e:
                if attempt < 2:
                    wait = 5 * (attempt + 1)
                    print(f"    Attempt {attempt + 1} failed, retrying in {wait}s...")
                    import time
                    time.sleep(wait)
                else:
                    print(f"    WARNING: Batch {batch_num} failed after 3 attempts: {e}")

        if raw is None:
            continue

        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()

        try:
            batch_results = json.loads(raw)
        except json.JSONDecodeError:
            start = raw.find("[")
            end = raw.rfind("]") + 1
            if start >= 0 and end > start:
                try:
                    batch_results = json.loads(raw[start:end])
                except json.JSONDecodeError:
                    print(f"    WARNING: Could not parse batch {batch_num}, skipping")
                    continue
            else:
                print(f"    WARNING: Could not parse batch {batch_num}, skipping")
                continue

        # Validate that winner and losers are real tags in the DB
        for r in batch_results:
            winner = r.get("winner", "")
            losers = [l for l in r.get("losers", []) if l in registry]
            if winner in registry and losers:
                all_clusters.append({
                    "winner": winner,
                    "losers": losers,
                    "reason": r.get("reason", "llm-semantic"),
                })

    # Deduplicate: a tag should only appear as loser once
    seen_losers = set()
    deduped = []
    for c in all_clusters:
        new_losers = [l for l in c["losers"] if l not in seen_losers]
        if new_losers:
            c["losers"] = new_losers
            deduped.append(c)
            seen_losers.update(new_losers)

    print(f"  LLM found {len(deduped)} clusters, "
          f"{sum(len(c['losers']) for c in deduped)} tags to merge")
    return deduped


# ------------------------------------------------------------------
# Apply merges
# ------------------------------------------------------------------

def apply_merges(db: VaultDB, merges: list[dict], verbose: bool = True) -> dict:
    """Apply a list of merge operations. Returns summary stats."""
    total_merged = 0
    total_rels_moved = 0
    total_aliases_moved = 0
    skipped = 0

    for m in merges:
        winner = m["winner"]
        if not db.get_entity(winner):
            if verbose:
                print(f"  SKIP: winner '{winner}' not found")
            skipped += 1
            continue

        for loser in m["losers"]:
            if not db.get_entity(loser):
                if verbose:
                    print(f"  SKIP: loser '{loser}' not found (already merged?)")
                skipped += 1
                continue

            result = db.merge_tags(winner, loser)
            total_merged += 1
            total_rels_moved += result["relationships_moved"]
            total_aliases_moved += result["aliases_moved"]
            if verbose:
                print(f"  {loser} -> {winner}  "
                      f"(rels={result['relationships_moved']}, "
                      f"aliases={result['aliases_moved']})")

    return {
        "merged": total_merged,
        "relationships_moved": total_rels_moved,
        "aliases_moved": total_aliases_moved,
        "skipped": skipped,
    }


# ------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Consolidate duplicate tags in vault.db",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  # Fuzzy scan + LLM validation (recommended):
  python consolidate_tags.py vault/ --scan --llm -o merges.json

  # Full LLM semantic scan (best recall, slower):
  python consolidate_tags.py vault/ --llm-scan -o merges.json

  # Review then apply:
  python consolidate_tags.py vault/ --apply merges.json

  # One-shot with LLM:
  python consolidate_tags.py vault/ --auto
""")
    parser.add_argument("vault", help="Path to vault root directory")
    parser.add_argument("--scan", action="store_true",
                        help="Fuzzy scan for duplicates")
    parser.add_argument("--llm", action="store_true",
                        help="Use LLM to validate fuzzy candidates (with --scan) or full scan (--llm-scan)")
    parser.add_argument("--llm-scan", action="store_true",
                        help="Full LLM semantic grouping of all tags")
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help=f"Ollama model (default: {DEFAULT_MODEL})")
    parser.add_argument("--apply", metavar="FILE",
                        help="Apply merges from a JSON file")
    parser.add_argument("--auto", action="store_true",
                        help="Scan + LLM validate + apply in one step")
    parser.add_argument("-o", "--output", default="tag_merges.json",
                        help="Output file for --scan (default: tag_merges.json)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would happen without changing DB")
    args = parser.parse_args()

    vault_path = Path(args.vault)
    db_path = vault_path / "vault.db"
    if not db_path.exists():
        print(f"ERROR: {db_path} not found")
        sys.exit(1)

    db = VaultDB(db_path)
    before = db.get_tag_registry()
    print(f"Tags before: {len(before)}")

    merges = None

    if args.llm_scan:
        # Full LLM semantic scan
        if not _llm_available(args.model):
            print("ERROR: Ollama not reachable. Start it with: ollama serve")
            sys.exit(1)
        merges = llm_scan_all_tags(db, model=args.model)

    elif args.scan or args.auto:
        print("Scanning for duplicate clusters (fuzzy)...")
        merges = scan_duplicates(db)
        total_losers = sum(len(m["losers"]) for m in merges)
        print(f"Fuzzy scan: {len(merges)} clusters, {total_losers} candidates")

        # LLM validation pass
        if args.llm or args.auto:
            if not _llm_available(args.model):
                print("WARNING: Ollama not reachable, skipping LLM validation")
            else:
                merges = llm_validate_merges(merges, model=args.model)

    elif args.apply:
        merge_path = Path(args.apply)
        if not merge_path.exists():
            print(f"ERROR: {merge_path} not found")
            sys.exit(1)
        merges = json.loads(merge_path.read_text())
        total_losers = sum(len(m["losers"]) for m in merges)
        print(f"Loaded {len(merges)} clusters, {total_losers} tags to merge")

    else:
        parser.print_help()
        db.close()
        return

    if merges is None:
        db.close()
        return

    total_losers = sum(len(m["losers"]) for m in merges)

    # If scanning (not applying), write to file
    if (args.scan or args.llm_scan) and not args.auto:
        out_path = Path(args.output)
        out_path.write_text(json.dumps(merges, indent=2))
        print(f"\nProposed merges: {len(merges)} clusters, {total_losers} tags")
        print(f"Written to {out_path}")
        print(f"Review, then: python consolidate_tags.py {args.vault} --apply {out_path}")
        db.close()
        return

    # Apply (--auto or --apply)
    if args.dry_run:
        print(f"\n[DRY RUN] Would merge {total_losers} tags:")
        for m in merges:
            for loser in m["losers"]:
                reason = m.get("reason", "")
                print(f"  {loser} -> {m['winner']}  ({reason})")
    else:
        print(f"\nApplying {total_losers} merges...")
        result = apply_merges(db, merges)
        after = db.get_tag_registry()
        print(f"\nDone: merged {result['merged']} tags, "
              f"moved {result['relationships_moved']} relationships, "
              f"moved {result['aliases_moved']} aliases, "
              f"skipped {result['skipped']}")
        print(f"Tags after: {len(after)} (reduced by {len(before) - len(after)})")

    db.close()


if __name__ == "__main__":
    main()
