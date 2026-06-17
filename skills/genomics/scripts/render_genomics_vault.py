#!/usr/bin/env python3
"""Render a genomics SQLite graph as a markdown vault."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[3] / "APP"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from kgx.db import KnowledgeGraphDB


TYPE_FOLDERS = {
    "organism": "organisms",
    "dataset": "datasets",
    "chromosome": "chromosomes",
    "gene": "genes",
    "transcript": "transcripts",
    "protein": "proteins",
    "orthogroup": "orthogroups",
    "bcn_gene": "bcn_genes",
    "comparative_hit": "comparative_hits",
    "annotation_term": "annotations",
    "localization_call": "localizations",
    "prediction_call": "predictions",
    "expression_measure": "expression",
    "contrast_definition": "contrasts",
    "tag": "tags",
}


def _slug_note_name(entity_id: str) -> str:
    return entity_id.replace(":", "-").replace("/", "-")


def _folder_for_type(entity_type: str) -> str:
    return TYPE_FOLDERS.get(entity_type, "other")


def _link_for_entity(entity: dict) -> str:
    folder = _folder_for_type(str(entity.get("type", "")))
    return f"{folder}/{_slug_note_name(str(entity.get('id', '')))}"


def _render_entity_markdown(db: KnowledgeGraphDB, entity: dict, entity_map: dict[str, dict]) -> str:
    metadata = entity.get("metadata", {}) or {}
    rels = db.get_relationships(entity["id"])

    lines = [
        "---",
        f'id: "{entity["id"]}"',
        f'type: "{entity["type"]}"',
        f'name: "{entity["name"]}"',
        "---",
        "",
        f"# {entity['name']}",
        "",
    ]

    if metadata:
        lines.extend(["## Properties", "", "| Field | Value |", "|---|---|"])
        for key in sorted(metadata):
            value = metadata[key]
            if isinstance(value, (str, int, float, bool)):
                lines.append(f"| {key} | {value} |")
        lines.append("")

    if rels:
        grouped: dict[str, list[dict]] = {}
        for rel in rels:
            grouped.setdefault(rel["rel_type"], []).append(rel)
        lines.extend(["## Relationships", ""])
        for rel_type in sorted(grouped):
            lines.extend([f"### {rel_type}", ""])
            for rel in grouped[rel_type]:
                other_id = rel["target_id"] if rel["source_id"] == entity["id"] else rel["source_id"]
                other = entity_map.get(other_id, {"id": other_id, "name": other_id, "type": ""})
                meta = rel.get("metadata") or {}
                suffix = ""
                if meta:
                    bits = [f"{k}={v}" for k, v in sorted(meta.items()) if isinstance(v, (str, int, float, bool))]
                    if bits:
                        suffix = f" ({', '.join(bits)})"
                lines.append(f"- [[{_link_for_entity(other)}|{other['name']}]]{suffix}")
            lines.append("")

    return "\n".join(lines)


def render_genomics_vault(*, db_path: Path, output_dir: Path) -> Path:
    output_dir = output_dir.resolve()
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with KnowledgeGraphDB(db_path) as db:
        by_type: dict[str, list[dict]] = {}
        for type_row in db.entity_types():
            entity_type = str(type_row.get("type", ""))
            for item in db.get_entities(entity_type):
                entity = db.get_entity(item["id"])
                if entity is None:
                    continue
                by_type.setdefault(entity_type, []).append(entity)
        entity_map = {
            entity["id"]: entity
            for items in by_type.values()
            for entity in items
        }

        for entity_type, items in by_type.items():
            folder = output_dir / _folder_for_type(entity_type)
            folder.mkdir(parents=True, exist_ok=True)
            for entity in sorted(items, key=lambda item: (str(item.get("name", "")), str(item.get("id", "")))):
                note_path = folder / f"{_slug_note_name(entity['id'])}.md"
                note_path.write_text(_render_entity_markdown(db, entity, entity_map))

        index_lines = [
            "# Genomics Vault",
            "",
            f"Source DB: `{db_path}`",
            "",
            "## Entity Types",
            "",
            "| Type | Count | Folder |",
            "|---|---:|---|",
        ]
        for entity_type in sorted(by_type):
            index_lines.append(f"| {entity_type} | {len(by_type[entity_type])} | `{_folder_for_type(entity_type)}/` |")
        index_lines.append("")
        (output_dir / "index.md").write_text("\n".join(index_lines))

    return output_dir


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Render a genomics DB as a markdown vault.")
    parser.add_argument("--db", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    render_genomics_vault(db_path=Path(args.db), output_dir=Path(args.output))
