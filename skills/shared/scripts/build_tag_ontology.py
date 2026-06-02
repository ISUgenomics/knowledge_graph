#!/usr/bin/env python3
"""
build_tag_ontology.py — Build a BROADER hierarchy for tags in vault.db.

Three-level hierarchy:
  Domain  (biology, engineering, computing, social-science, funding, other)
  Field   (curated tags with descriptions — ai, genomics, plant-science, ...)
  Leaf    (all remaining tags — assigned to a field by LLM)

Uses the local Ollama model to assign each leaf tag to its best-fit field.

Usage:
    # Scan: propose hierarchy, write to JSON for review
    python build_tag_ontology.py /path/to/vault --scan -o ontology.json

    # Apply: write BROADER relationships to vault.db
    python build_tag_ontology.py /path/to/vault --apply ontology.json

    # One-shot
    python build_tag_ontology.py /path/to/vault --auto
"""

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from vault_db import VaultDB

OLLAMA_BASE = "http://localhost:11434"
DEFAULT_MODEL = "qwen3-coder:30b"

# ------------------------------------------------------------------
# Domain definitions (top level)
# ------------------------------------------------------------------
DOMAINS = {
    "biology": {
        "description": "Life sciences, organisms, ecosystems",
        "fields": [
            "agriculture", "animal-science", "bioinformatics", "biomedical",
            "ecology", "entomology", "evolution", "genomics", "microbiome",
            "molecular-biology", "plant-science", "soil-health",
        ],
    },
    "engineering": {
        "description": "Physical engineering, materials, energy",
        "fields": [
            "3d-printing", "digital-twins", "materials-science",
            "nanotechnology", "precision-agriculture", "renewable-energy",
            "robotics",
        ],
    },
    "computing": {
        "description": "Computer science, AI, data",
        "fields": [
            "ai", "computer-vision", "cybersecurity", "data-science",
            "deep-learning", "machine-learning", "nlp", "quantum-computing",
            "research-computing",
        ],
    },
    "social-science": {
        "description": "Education, policy, outreach, business",
        "fields": [
            "education", "entrepreneurship", "extension", "sustainability",
        ],
    },
    "funding": {
        "description": "Funding agencies and programs",
        "fields": ["doe", "nih", "nsf", "usda"],
    },
}

# Flatten field → domain lookup
FIELD_TO_DOMAIN = {}
ALL_FIELDS = []
for domain, info in DOMAINS.items():
    for field in info["fields"]:
        FIELD_TO_DOMAIN[field] = domain
        ALL_FIELDS.append(field)


# ------------------------------------------------------------------
# Ollama helper
# ------------------------------------------------------------------

def _llm_chat(messages: list[dict], model: str = DEFAULT_MODEL) -> str:
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


def _llm_available() -> bool:
    import httpx
    try:
        return httpx.get(f"{OLLAMA_BASE}/api/tags", timeout=3.0).status_code == 200
    except Exception:
        return False


# ------------------------------------------------------------------
# Build hierarchy
# ------------------------------------------------------------------

def build_ontology(db: VaultDB, model: str = DEFAULT_MODEL) -> dict:
    """
    Returns {
        "domains": {domain: [field, ...]},
        "field_parents": {field: domain},
        "leaf_parents": {leaf_tag: field},
        "unassigned": [tags that couldn't be assigned],
    }
    """
    registry = db.get_tag_registry()
    all_tags = sorted(registry.keys())

    # Separate fields from leaves
    field_set = set(ALL_FIELDS)
    leaves = [t for t in all_tags if t not in field_set and t not in DOMAINS]

    print(f"  Tags: {len(all_tags)} total, {len(field_set)} fields, {len(leaves)} to classify")

    # Build field reference for the prompt
    field_descriptions = []
    for field in ALL_FIELDS:
        desc = registry.get(field, {}).get("description", "")
        domain = FIELD_TO_DOMAIN[field]
        field_descriptions.append(f"  {field} ({domain}): {desc}")
    field_block = "\n".join(field_descriptions)

    # Send leaves to LLM in batches
    batch_size = 300
    leaf_parents = {}
    unassigned = []

    for batch_start in range(0, len(leaves), batch_size):
        batch = leaves[batch_start:batch_start + batch_size]
        batch_num = batch_start // batch_size + 1
        total_batches = (len(leaves) + batch_size - 1) // batch_size
        print(f"  Batch {batch_num}/{total_batches} ({len(batch)} tags)...")

        tag_block = "\n".join(batch)

        prompt = f"""You are a taxonomy expert. Assign each tag below to its best-fit parent field.

FIELDS (pick one per tag):
{field_block}

TAGS TO CLASSIFY:
{tag_block}

Rules:
- Each tag gets exactly ONE parent field from the list above
- Pick the most specific field that fits (e.g. "soybean-genetics" → plant-science, not biology)
- If a tag truly doesn't fit any field, assign it to "other"
- Be precise: "crop-yield" → agriculture, "neural-networks" → deep-learning

Return ONLY a JSON object mapping tag → parent field. No other text.
Example: {{"soybean-genetics": "plant-science", "crop-yield": "agriculture"}}
/no_think"""

        raw = None
        for attempt in range(3):
            try:
                raw = _llm_chat([{"role": "user", "content": prompt}], model=model)
                break
            except Exception as e:
                if attempt < 2:
                    print(f"    Retry {attempt + 1}...")
                    import time
                    time.sleep(5)
                else:
                    print(f"    WARNING: Batch {batch_num} failed: {e}")

        if raw is None:
            unassigned.extend(batch)
            continue

        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()

        try:
            assignments = json.loads(raw)
        except json.JSONDecodeError:
            # Try to find JSON object
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    assignments = json.loads(raw[start:end])
                except json.JSONDecodeError:
                    print(f"    WARNING: Could not parse batch {batch_num}")
                    unassigned.extend(batch)
                    continue
            else:
                print(f"    WARNING: Could not parse batch {batch_num}")
                unassigned.extend(batch)
                continue

        # Validate assignments
        for tag, parent in assignments.items():
            if tag not in registry:
                continue
            if parent in field_set:
                leaf_parents[tag] = parent
            elif parent == "other":
                unassigned.append(tag)
            else:
                # LLM returned an unknown field — try to match
                unassigned.append(tag)

    # Tags not in LLM response
    assigned_set = set(leaf_parents.keys()) | set(unassigned)
    for leaf in leaves:
        if leaf not in assigned_set:
            unassigned.append(leaf)

    print(f"  Assigned: {len(leaf_parents)}, Unassigned: {len(unassigned)}")

    return {
        "domains": {d: info["fields"] for d, info in DOMAINS.items()},
        "field_parents": FIELD_TO_DOMAIN.copy(),
        "leaf_parents": leaf_parents,
        "unassigned": sorted(set(unassigned)),
    }


def apply_ontology(db: VaultDB, ontology: dict) -> dict:
    """Write BROADER relationships to vault.db from ontology dict."""
    stats = {"domain_links": 0, "field_links": 0, "leaf_links": 0}

    # Ensure domain entities exist
    for domain, fields in ontology["domains"].items():
        db.upsert_tag(domain, category="domain",
                       description=DOMAINS.get(domain, {}).get("description", ""))

    # Field → domain
    for field, domain in ontology["field_parents"].items():
        if db.get_entity(field) and db.get_entity(domain):
            db.add_broader(field, domain)
            stats["domain_links"] += 1

    # Leaf → field
    for leaf, field in ontology["leaf_parents"].items():
        if db.get_entity(leaf) and db.get_entity(field):
            db.add_broader(leaf, field)
            stats["leaf_links"] += 1

    print(f"  Applied: {stats['domain_links']} field→domain, "
          f"{stats['leaf_links']} leaf→field links")
    return stats


# ------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Build tag ontology hierarchy in vault.db")
    parser.add_argument("vault", help="Path to vault root directory")
    parser.add_argument("--scan", action="store_true",
                        help="Build ontology and write to JSON for review")
    parser.add_argument("--apply", metavar="FILE",
                        help="Apply ontology from a JSON file")
    parser.add_argument("--auto", action="store_true",
                        help="Build and apply in one step")
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help=f"Ollama model (default: {DEFAULT_MODEL})")
    parser.add_argument("-o", "--output", default="tag_ontology.json",
                        help="Output file for --scan")
    args = parser.parse_args()

    vault_path = Path(args.vault)
    db_path = vault_path / "vault.db"
    if not db_path.exists():
        print(f"ERROR: {db_path} not found")
        sys.exit(1)

    db = VaultDB(db_path)

    if args.scan or args.auto:
        if not _llm_available():
            print("ERROR: Ollama not reachable. Start with: ollama serve")
            sys.exit(1)

        ontology = build_ontology(db, model=args.model)

        if args.scan and not args.auto:
            out_path = Path(args.output)
            out_path.write_text(json.dumps(ontology, indent=2))
            print(f"\nOntology written to {out_path}")
            print(f"  {len(ontology['field_parents'])} fields across "
                  f"{len(ontology['domains'])} domains")
            print(f"  {len(ontology['leaf_parents'])} leaves assigned")
            print(f"  {len(ontology['unassigned'])} unassigned")
            print(f"\nReview, then: python build_tag_ontology.py {args.vault} --apply {out_path}")
            db.close()
            return

        # --auto
        stats = apply_ontology(db, ontology)
        forest = db.get_tag_forest_stats()
        print(f"\nOntology stats: {forest}")

    elif args.apply:
        apply_path = Path(args.apply)
        if not apply_path.exists():
            print(f"ERROR: {apply_path} not found")
            sys.exit(1)
        ontology = json.loads(apply_path.read_text())
        stats = apply_ontology(db, ontology)
        forest = db.get_tag_forest_stats()
        print(f"\nOntology stats: {forest}")

    else:
        parser.print_help()

    db.close()


if __name__ == "__main__":
    main()
