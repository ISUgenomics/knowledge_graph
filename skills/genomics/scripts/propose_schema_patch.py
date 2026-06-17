#!/usr/bin/env python3
"""Generate a deterministic schema patch proposal from an LLM review sidecar."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml


ENTITY_KEYS = ("gene", "transcript", "protein")


def _load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text()) or {}


def _entity_columns(schema: dict[str, Any]) -> dict[str, list[str]]:
    entities = (((schema.get("entity_model") or {}).get("entities")) or {})
    result: dict[str, list[str]] = {}
    for key in ENTITY_KEYS:
        cfg = (entities.get(key) or {})
        cols = list(cfg.get("metadata_columns", []) or [])
        seq_col = str(cfg.get("sequence_column", "") or "").strip()
        if seq_col and seq_col not in cols:
            cols.append(seq_col)
        result[key] = cols
    return result


def _set_entity_columns(schema: dict[str, Any], entity_columns: dict[str, list[str]]) -> None:
    entities = (((schema.get("entity_model") or {}).get("entities")) or {})
    for key in ENTITY_KEYS:
        cfg = entities.get(key) or {}
        cols = list(entity_columns.get(key, []) or [])
        seq_col = str(cfg.get("sequence_column", "") or "").strip()
        if seq_col:
            cfg["metadata_columns"] = [col for col in cols if col != seq_col]
        else:
            cfg["metadata_columns"] = cols


def _normalize_target(entity_name: str) -> str | None:
    normalized = str(entity_name or "").strip().lower()
    return normalized if normalized in ENTITY_KEYS else None


def propose_schema_patch(
    *,
    review_path: Path,
    schema_path: Path,
    output_dir: Path | None = None,
) -> tuple[Path, Path]:
    review_path = review_path.resolve()
    schema_path = schema_path.resolve()
    out_dir = (output_dir.resolve() if output_dir else review_path.parent.resolve())
    out_dir.mkdir(parents=True, exist_ok=True)

    review = _load_yaml(review_path)
    schema = _load_yaml(schema_path)
    llm_review = review.get("llm_review", {}) or {}
    suggestions = list(llm_review.get("column_suggestions", []) or [])

    original_columns = _entity_columns(schema)
    proposed_columns = copy.deepcopy(original_columns)
    operations: list[dict[str, Any]] = []

    for suggestion in suggestions:
        column = str(suggestion.get("column", "") or "").strip()
        target = _normalize_target(suggestion.get("suggested_entity", ""))
        if not column or target is None:
            continue

        current_owner = next((entity for entity, cols in proposed_columns.items() if column in cols), None)
        if current_owner == target:
            continue

        changed = False
        if current_owner is not None:
            proposed_columns[current_owner] = [col for col in proposed_columns[current_owner] if col != column]
            changed = True
        if column not in proposed_columns[target]:
            proposed_columns[target].append(column)
            changed = True
        if not changed:
            continue

        operations.append({
            "column": column,
            "from_entity": current_owner or "",
            "to_entity": target,
            "suggested_group": str(suggestion.get("suggested_group", "") or ""),
            "reason": str(suggestion.get("reason", "") or ""),
        })

    proposed_schema = copy.deepcopy(schema)
    _set_entity_columns(proposed_schema, proposed_columns)

    patch = {
        "review_path": str(review_path),
        "schema_path": str(schema_path),
        "summary": {
            "operation_count": len(operations),
            "confidence": str(llm_review.get("confidence", "") or ""),
            "review_summary": str(llm_review.get("summary", "") or ""),
        },
        "operations": operations,
        "proposed_entity_columns": proposed_columns,
        "ambiguities": list(llm_review.get("ambiguities", []) or []),
        "group_suggestions": list(llm_review.get("group_suggestions", []) or []),
        "note": "Deterministic proposal only. No changes have been applied to schema.yaml.",
    }

    patch_path = out_dir / "schema.patch.yaml"
    proposed_path = out_dir / "schema.proposed.yaml"
    patch_path.write_text(yaml.safe_dump(patch, sort_keys=False, allow_unicode=False))
    proposed_path.write_text(yaml.safe_dump(proposed_schema, sort_keys=False, allow_unicode=False))
    return patch_path, proposed_path


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate a deterministic schema patch proposal from an LLM review file.")
    parser.add_argument("--review", required=True, help="Path to llm-review.yaml")
    parser.add_argument("--schema", required=True, help="Path to schema.yaml or schema.inferred.yaml")
    parser.add_argument("--output-dir", default="", help="Directory to write schema.patch.yaml and schema.proposed.yaml")
    args = parser.parse_args()
    propose_schema_patch(
        review_path=Path(args.review),
        schema_path=Path(args.schema),
        output_dir=Path(args.output_dir) if args.output_dir else None,
    )
