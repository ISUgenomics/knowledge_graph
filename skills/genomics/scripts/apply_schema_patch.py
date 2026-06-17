#!/usr/bin/env python3
"""Apply a deterministic genomics schema patch proposal with backup."""

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
        cfg = entities.get(key) or {}
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


def _backup_path(schema_path: Path) -> Path:
    return schema_path.with_name(f"{schema_path.name}.bak")


def apply_schema_patch(
    *,
    patch_path: Path,
    schema_path: Path,
    force: bool = False,
) -> tuple[Path, Path]:
    patch_path = patch_path.resolve()
    schema_path = schema_path.resolve()
    patch = _load_yaml(patch_path)
    schema = _load_yaml(schema_path)

    declared_schema = str(patch.get("schema_path", "") or "").strip()
    if declared_schema and Path(declared_schema).resolve() != schema_path and not force:
        raise ValueError("Patch was generated for a different schema path. Pass force=True to override.")

    operations = list(patch.get("operations", []) or [])
    current_columns = _entity_columns(schema)
    proposed_columns = copy.deepcopy(current_columns)

    for operation in operations:
        column = str(operation.get("column", "") or "").strip()
        from_entity = str(operation.get("from_entity", "") or "").strip()
        to_entity = str(operation.get("to_entity", "") or "").strip()
        if not column or to_entity not in ENTITY_KEYS:
            continue
        if from_entity in ENTITY_KEYS:
            proposed_columns[from_entity] = [col for col in proposed_columns[from_entity] if col != column]
        else:
            for entity_key in ENTITY_KEYS:
                proposed_columns[entity_key] = [col for col in proposed_columns[entity_key] if col != column]
        if column not in proposed_columns[to_entity]:
            proposed_columns[to_entity].append(column)

    updated_schema = copy.deepcopy(schema)
    _set_entity_columns(updated_schema, proposed_columns)

    backup_path = _backup_path(schema_path)
    backup_path.write_text(schema_path.read_text())
    schema_path.write_text(yaml.safe_dump(updated_schema, sort_keys=False, allow_unicode=False))
    return schema_path, backup_path


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Apply a deterministic genomics schema patch with backup.")
    parser.add_argument("--patch", required=True, help="Path to schema.patch.yaml")
    parser.add_argument("--schema", required=True, help="Path to schema.yaml or schema.inferred.yaml")
    parser.add_argument("--force", action="store_true", help="Apply even if the patch references a different schema path.")
    args = parser.parse_args()
    apply_schema_patch(
        patch_path=Path(args.patch),
        schema_path=Path(args.schema),
        force=bool(args.force),
    )
