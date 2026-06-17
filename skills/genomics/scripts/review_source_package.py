#!/usr/bin/env python3
"""Optional local-LLM review for inferred genomics source mappings."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from infer_source_package import (
    _default_dataset_name,
    _infer_annotation_bins,
    _infer_boolean_tags,
    _infer_groups,
    _infer_primary_record,
    _infer_tag_bins,
    _infer_value_presence_tags,
    _pick_context,
    _read_rows,
    _slug,
)


def _load_llm_settings(config_path: Path | None) -> dict[str, Any]:
    if config_path is None:
        return {
            "base_url": "http://localhost:11434",
            "model": "qwen3-coder:30b",
            "temperature": 0.0,
        }
    from kgx.config import load_config

    cfg = load_config(config_path)
    return {
        "base_url": cfg.llm.base_url,
        "model": cfg.llm.model,
        "temperature": cfg.llm.temperature,
    }


def _extract_json_block(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        return json.loads(stripped)
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fenced:
        return json.loads(fenced.group(1))
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(text[start:end + 1])
    raise ValueError("No JSON object found in LLM response")


def _sample_rows(rows: list[dict[str, Any]], limit: int = 3) -> list[dict[str, Any]]:
    sample: list[dict[str, Any]] = []
    for row in rows[:limit]:
        trimmed = {}
        for key, value in row.items():
            if value in (None, ""):
                continue
            text = str(value)
            trimmed[key] = text[:180] + ("…" if len(text) > 180 else "")
        sample.append(trimmed)
    return sample


def _build_review_prompt(*, source_file: Path, dataset_name: str, organism: str, sidecar: dict[str, str], header: list[str], rows: list[dict[str, Any]], deterministic: dict[str, Any]) -> str:
    prompt = {
        "task": "Review a deterministic genomics source inference and suggest semantic improvements without editing files.",
        "requirements": [
            "Respect biological entity boundaries such as gene, transcript, and protein.",
            "Protein biophysics, composition, localization, and domain annotations belong to protein unless there is strong contrary evidence.",
            "Prefer field-general genomics conventions over dataset-specific naming when possible.",
            "Do not invent columns or tools that are not present.",
            "Return JSON only.",
        ],
        "expected_json_schema": {
            "summary": "short review summary",
            "confidence": "high|medium|low",
            "primary_record_entity": "gene|transcript|protein",
            "top_issues": [
                {"severity": "high|medium|low", "issue": "text", "reason": "text"}
            ],
            "column_suggestions": [
                {
                    "column": "column_name",
                    "suggested_entity": "gene|transcript|protein|annotation|tag|ignore",
                    "suggested_group": "short_group_name",
                    "reason": "text",
                }
            ],
            "group_suggestions": [
                {
                    "title": "group title",
                    "columns": ["col1", "col2"],
                    "reason": "text",
                }
            ],
            "ambiguities": [
                {
                    "column": "column_name",
                    "question": "text",
                    "reason": "text",
                }
            ],
        },
        "dataset_context": {
            "source_file": source_file.name,
            "dataset_name": dataset_name,
            "organism": organism,
            "sidecar": sidecar,
            "column_count": len(header),
            "columns": header,
            "sample_rows": _sample_rows(rows),
        },
        "deterministic_inference": deterministic,
    }
    return json.dumps(prompt, indent=2)


def review_source_package(
    *,
    source_file: Path,
    source_dir: Path | None = None,
    dataset_id: str | None = None,
    dataset_name: str | None = None,
    organism: str | None = None,
    note_paths: list[Path] | None = None,
    config_path: Path | None = None,
    model: str | None = None,
    base_url: str | None = None,
    llm_client: Any | None = None,
) -> tuple[Path, Path]:
    source_file = source_file.resolve()
    output_dir = (source_dir.resolve() if source_dir else source_file.parent.resolve())
    output_dir.mkdir(parents=True, exist_ok=True)
    notes = [path.resolve() for path in (note_paths or [])]

    header, rows = _read_rows(source_file)
    if not header:
        raise ValueError(f"No header detected in {source_file}")

    sidecar = _pick_context(notes, source_file)
    inferred_dataset_id = dataset_id or _slug(source_file.stem)
    inferred_dataset_name = dataset_name or _default_dataset_name(source_file, sidecar)
    inferred_organism = organism or sidecar.get("organism") or "Unknown organism"
    primary_entity, id_column, gene_column = _infer_primary_record(header, rows)
    groups = _infer_groups(header, rows, id_column, gene_column)

    deterministic = {
        "dataset_id": inferred_dataset_id,
        "dataset_name": inferred_dataset_name,
        "organism": inferred_organism,
        "primary_record_entity": primary_entity,
        "id_column": id_column,
        "gene_column": gene_column or "",
        "group_counts": {key: len(value) for key, value in groups.items()},
        "group_columns": groups,
        "annotation_bins": [item["column"] for item in _infer_annotation_bins(header)],
        "tag_bins": [item["column"] for item in _infer_tag_bins(header)],
        "boolean_tags": [item["column"] for item in _infer_boolean_tags(header)],
        "value_presence_tags": [item["column"] for item in _infer_value_presence_tags(header)],
    }

    owned_client = None
    if llm_client is None:
        settings = _load_llm_settings(config_path)
        from kgx.llm import OllamaClient

        owned_client = OllamaClient(
            base_url=base_url or settings["base_url"],
            model=model or settings["model"],
            temperature=float(settings.get("temperature", 0.0) or 0.0),
        )
        llm_client = owned_client

    if not llm_client.is_available():
        raise RuntimeError("Local Ollama endpoint is not reachable for genomics review")

    prompt = _build_review_prompt(
        source_file=source_file,
        dataset_name=inferred_dataset_name,
        organism=inferred_organism,
        sidecar=sidecar,
        header=header,
        rows=rows,
        deterministic=deterministic,
    )
    raw_response = llm_client.chat(
        [
            {
                "role": "system",
                "content": (
                    "You review genomics dataset inference for a local knowledge graph builder. "
                    "Return JSON only. Be conservative, biologically precise, and avoid inventing missing context."
                ),
            },
            {"role": "user", "content": prompt},
        ]
    )
    parsed = _extract_json_block(raw_response)
    report = {
        "source_file": str(source_file),
        "notes": [str(path) for path in notes],
        "deterministic_inference": deterministic,
        "llm_review": parsed,
    }

    review_path = output_dir / "llm-review.yaml"
    raw_path = output_dir / "llm-review.raw.txt"
    review_path.write_text(yaml.safe_dump(report, sort_keys=False, allow_unicode=False))
    raw_path.write_text(raw_response)

    if owned_client is not None:
        owned_client.close()

    return review_path, raw_path


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Review inferred genomics mappings with a local Ollama model.")
    parser.add_argument("--source-file", required=True)
    parser.add_argument("--source-dir", default="")
    parser.add_argument("--dataset-id", default="")
    parser.add_argument("--dataset-name", default="")
    parser.add_argument("--organism", default="")
    parser.add_argument("--notes", action="append", default=[])
    parser.add_argument("--config", default="")
    parser.add_argument("--model", default="")
    parser.add_argument("--base-url", default="")
    args = parser.parse_args()
    review_source_package(
        source_file=Path(args.source_file),
        source_dir=Path(args.source_dir) if args.source_dir else None,
        dataset_id=args.dataset_id or None,
        dataset_name=args.dataset_name or None,
        organism=args.organism or None,
        note_paths=[Path(p) for p in args.notes],
        config_path=Path(args.config) if args.config else None,
        model=args.model or None,
        base_url=args.base_url or None,
    )
