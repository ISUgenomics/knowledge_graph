"""
Skill registry — auto-discovers available skills from the filesystem.

A skill is a directory containing a plugin.py with a run() or main() entry
point. The registry reads skill metadata from a manifest.yaml (optional) or
infers it from the directory name.

Expected directory layout (relative to skills_dir):
  skills_dir/
    person_research/
      plugin.py       ← required; must define run(args) or main()
      manifest.yaml   ← optional; keys: name, description, entity_types, args
    event_research/
      plugin.py
    ...
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml
    _YAML_OK = True
except ImportError:
    _YAML_OK = False


@dataclass
class SkillMeta:
    id: str                         # directory name slug, e.g. "person_research"
    name: str                       # human-readable label
    description: str
    entity_types: list[str]         # entity types this skill can act on (empty = any)
    args: list[dict]                # [{name, flag, description, required}]
    path: Path                      # absolute path to skill directory
    plugin_path: Path               # absolute path to plugin.py
    entry_path: Path                # executable entrypoint used by the runner

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "entity_types": self.entity_types,
            "args": self.args,
            "entry_path": str(self.entry_path.name),
        }


class SkillRegistry:
    def __init__(self, skills_dir: str | Path):
        self.skills_dir = Path(skills_dir)
        self._skills: dict[str, SkillMeta] = {}
        self._scan()

    def _scan(self):
        self._skills.clear()
        if not self.skills_dir.exists():
            return
        for entry in sorted(self.skills_dir.iterdir()):
            if not entry.is_dir():
                continue
            plugin = entry / "plugin.py"
            if not plugin.exists():
                continue
            meta = self._load_meta(entry)
            self._skills[meta.id] = meta

    def _load_meta(self, skill_dir: Path) -> SkillMeta:
        skill_id = skill_dir.name
        manifest_path = skill_dir / "manifest.yaml"

        defaults: dict[str, Any] = {
            "name": skill_id.replace("_", " ").title(),
            "description": f"Run the {skill_id} skill.",
            "entity_types": [],
            "args": [],
        }

        if manifest_path.exists() and _YAML_OK:
            try:
                data = yaml.safe_load(manifest_path.read_text()) or {}
                defaults.update(data)
            except Exception:
                pass

        entry_path = self._resolve_entry_path(skill_dir, defaults.get("entry"))

        return SkillMeta(
            id=skill_id,
            name=defaults["name"],
            description=defaults["description"],
            entity_types=defaults.get("entity_types") or [],
            args=defaults.get("args") or [],
            path=skill_dir,
            plugin_path=skill_dir / "plugin.py",
            entry_path=entry_path,
        )

    def _resolve_entry_path(self, skill_dir: Path, configured: str | None) -> Path:
        if configured:
            entry = skill_dir / configured
            if entry.exists():
                return entry

        direct = skill_dir / "run.py"
        if direct.exists():
            return direct

        prefix = skill_dir.name.split("_", 1)[0]
        prefixed = skill_dir / f"run_{prefix}.py"
        if prefixed.exists():
            return prefixed

        candidates = sorted(
            p for p in skill_dir.glob("run*.py")
            if p.is_file() and p.name != "run_all.py"
        )
        if candidates:
            return candidates[0]

        return skill_dir / "plugin.py"

    def list(self, entity_type: str = "") -> list[SkillMeta]:
        skills = list(self._skills.values())
        if entity_type:
            skills = [s for s in skills if not s.entity_types or entity_type in s.entity_types]
        return skills

    def get(self, skill_id: str) -> SkillMeta | None:
        return self._skills.get(skill_id)

    def refresh(self):
        """Re-scan the filesystem (call after adding/removing skills)."""
        self._scan()
