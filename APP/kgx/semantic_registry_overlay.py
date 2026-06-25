from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _merge_values(base: Any, overlay: Any) -> Any:
    if isinstance(base, dict) and isinstance(overlay, dict):
        merged = dict(base)
        for key, value in overlay.items():
            merged[key] = _merge_values(merged.get(key), value) if key in merged else value
        return merged
    return overlay


def load_semantic_registry_overlay(ui_config: dict[str, Any] | None) -> dict[str, Any]:
    ui_config = ui_config or {}
    raw_path = str(ui_config.get("semantic_registry_overlay", "") or "").strip()
    if not raw_path:
        return {}
    path = Path(raw_path)
    if not path.is_absolute():
        path = path.resolve()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    if isinstance(data.get("registry_patch"), dict):
        return dict(data.get("registry_patch", {}) or {})
    return data


def merge_semantic_registry_overlay(base_registry: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(base_registry, dict):
        return dict(overlay or {}) if isinstance(overlay, dict) else {}
    if not isinstance(overlay, dict) or not overlay:
        return dict(base_registry)
    return _merge_values(base_registry, overlay)
