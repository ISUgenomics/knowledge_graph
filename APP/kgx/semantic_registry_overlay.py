from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml


def _merge_values(base: Any, overlay: Any) -> Any:
    if isinstance(base, dict) and isinstance(overlay, dict):
        merged = dict(base)
        for key, value in overlay.items():
            merged[key] = _merge_values(merged.get(key), value) if key in merged else value
        return merged
    return overlay


def _load_overlay_file(path_text: str) -> dict[str, Any]:
    path = Path(path_text)
    if not path.is_absolute():
        path = path.resolve()
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    if isinstance(data.get("registry_patch"), dict):
        return dict(data.get("registry_patch", {}) or {})
    return data


def load_semantic_registry_overlay(ui_config: dict[str, Any] | None) -> dict[str, Any]:
    ui_config = ui_config or {}
    overlay_paths: list[str] = []
    raw_path = str(ui_config.get("semantic_registry_overlay", "") or "").strip()
    if raw_path:
        overlay_paths.append(raw_path)
    for item in list(ui_config.get("semantic_registry_overlays", []) or []):
        path_text = str(item or "").strip()
        if path_text:
            overlay_paths.append(path_text)

    merged: dict[str, Any] = {}
    for path_text in overlay_paths:
        merged = merge_semantic_registry_overlay(merged, _load_overlay_file(path_text))
    return merged


def merge_semantic_registry_overlay(base_registry: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(base_registry, dict):
        return dict(overlay or {}) if isinstance(overlay, dict) else {}
    if not isinstance(overlay, dict) or not overlay:
        return dict(base_registry)
    return _merge_values(base_registry, overlay)
