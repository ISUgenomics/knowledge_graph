from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


_CORPUS_PATH = Path(__file__).with_suffix("").parent / "tests" / "prompt_corpus.yaml"


@lru_cache(maxsize=1)
def load_prompt_corpus() -> dict[str, Any]:
    raw = yaml.safe_load(_CORPUS_PATH.read_text()) or {}
    if not isinstance(raw, dict):
        return {}
    return raw


def flattened_prompt_corpus() -> list[dict[str, Any]]:
    raw = load_prompt_corpus()
    entries: list[dict[str, Any]] = []

    for entry in list(raw.get("general", []) or []):
        entries.append({**entry, "section": "general", "module": str(entry.get("module", "default"))})

    for module_name, module_entries in (raw.get("modules", {}) or {}).items():
        for entry in list(module_entries or []):
            entries.append({**entry, "section": f"modules.{module_name}", "module": str(module_name)})

    return entries


def prompt_corpus_few_shots(
    module_name: str | None = None,
    *,
    general_limit: int = 2,
    module_limit: int = 4,
) -> list[dict[str, str]]:
    selected: list[dict[str, str]] = []
    general_count = 0
    module_count = 0
    target_module = str(module_name or "").strip().lower()

    for entry in flattened_prompt_corpus():
        sql = str(entry.get("few_shot_sql", "") or "").strip()
        prompt = str(entry.get("prompt", "") or "").strip()
        section = str(entry.get("section", "") or "")
        if not prompt or not sql:
            continue
        if section == "general":
            if general_count >= general_limit:
                continue
            general_count += 1
        elif target_module and section == f"modules.{target_module}":
            if module_count >= module_limit:
                continue
            module_count += 1
        else:
            continue
        selected.append({
            "id": str(entry.get("id", "")),
            "section": section,
            "prompt": prompt,
            "sql": sql,
        })

    return selected
