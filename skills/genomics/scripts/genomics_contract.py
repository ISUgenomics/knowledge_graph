#!/usr/bin/env python3
"""Shared functional genomics contract helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


CONTRACTS_DIR = Path(__file__).resolve().parents[1] / "contracts"


def load_contract(name: str = "functional_genomics") -> dict[str, Any]:
    path = CONTRACTS_DIR / f"{name}.yaml"
    payload = yaml.safe_load(path.read_text()) or {}
    contract = payload.get("contract") or {}
    contract["path"] = str(path)
    return contract


def items_for_header(items: list[dict[str, Any]], header: list[str]) -> list[dict[str, Any]]:
    header_set = set(header)
    return [item for item in items if item.get("column") in header_set]


def promoted_entities_for_header(items: dict[str, dict[str, Any]], header: list[str]) -> dict[str, dict[str, Any]]:
    header_set = set(header)
    return {
        name: spec
        for name, spec in (items or {}).items()
        if spec.get("source_column") in header_set
    }


def split_shared_and_specific(
    items: list[dict[str, Any]] | dict[str, dict[str, Any]],
    *,
    contract_items: list[dict[str, Any]] | dict[str, dict[str, Any]],
) -> dict[str, Any]:
    if isinstance(items, dict):
        shared_keys = set((contract_items or {}).keys())
        return {
            "shared": {key: value for key, value in items.items() if key in shared_keys},
            "dataset_specific": {key: value for key, value in items.items() if key not in shared_keys},
        }

    shared_columns = {item.get("column") for item in (contract_items or [])}
    shared = [item for item in items if item.get("column") in shared_columns]
    specific = [item for item in items if item.get("column") not in shared_columns]
    return {"shared": shared, "dataset_specific": specific}


def combine_section(section: Any) -> Any:
    if isinstance(section, dict) and "shared" in section and "dataset_specific" in section:
        shared = section.get("shared")
        specific = section.get("dataset_specific")
        if isinstance(shared, dict):
            merged: dict[str, Any] = {}
            merged.update(shared or {})
            merged.update(specific or {})
            return merged
        return list(shared or []) + list(specific or [])
    return section or ([] if isinstance(section, list) else {})
