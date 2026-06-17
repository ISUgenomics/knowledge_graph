#!/usr/bin/env python3
"""CLI entrypoint for genomics source normalization and DB building."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from build_genomics_dataset import build_dataset
from infer_source_package import infer_source_package
from apply_schema_patch import apply_schema_patch
from normalize_source import normalize_source_package
from propose_schema_patch import propose_schema_patch
from review_source_package import review_source_package


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Normalize or build a local genomics dataset.")
    sub = parser.add_subparsers(dest="command", required=True)

    norm = sub.add_parser("normalize", help="Convert raw genomics source files into standardized YAML metadata.")
    norm.add_argument("--source-dir", required=True, help="Directory containing DATA.tsv and config.py")
    norm.add_argument("--dataset-id", default="genomics_scn", help="Stable dataset identifier.")
    norm.add_argument("--dataset-name", default="Heterodera glycines functional genomics sample", help="Human-readable dataset title.")
    norm.add_argument("--organism", default="Heterodera glycines", help="Organism label.")

    infer = sub.add_parser("infer", help="Infer standardized genomics metadata from an arbitrary local table and optional sidecar notes.")
    infer.add_argument("--source-file", required=True, help="Primary raw table file (.tsv, .csv, .xlsx).")
    infer.add_argument("--source-dir", default="", help="Directory to write inferred YAML files into. Defaults to the source file directory.")
    infer.add_argument("--dataset-id", default="", help="Stable dataset identifier override.")
    infer.add_argument("--dataset-name", default="", help="Human-readable dataset title override.")
    infer.add_argument("--organism", default="", help="Organism label override.")
    infer.add_argument("--notes", action="append", default=[], help="Optional sidecar note/config file to mine for dataset context. Repeatable.")
    infer.add_argument("--apply", action="store_true", help="Write canonical dataset.yaml and schema.yaml instead of *.inferred.yaml.")

    review = sub.add_parser("review", help="Ask a local LLM to review inferred genomics mappings and write a sidecar review report.")
    review.add_argument("--source-file", required=True, help="Primary raw table file (.tsv, .csv, .xlsx).")
    review.add_argument("--source-dir", default="", help="Directory to write review files into. Defaults to the source file directory.")
    review.add_argument("--dataset-id", default="", help="Stable dataset identifier override.")
    review.add_argument("--dataset-name", default="", help="Human-readable dataset title override.")
    review.add_argument("--organism", default="", help="Organism label override.")
    review.add_argument("--notes", action="append", default=[], help="Optional sidecar note/config file to mine for dataset context. Repeatable.")
    review.add_argument("--config", default="", help="Optional KGX config file to read local LLM settings from.")
    review.add_argument("--model", default="", help="Optional local LLM model override.")
    review.add_argument("--base-url", default="", help="Optional Ollama base URL override.")

    propose = sub.add_parser("propose", help="Convert an llm-review.yaml file into a deterministic schema patch proposal.")
    propose.add_argument("--review", required=True, help="Path to llm-review.yaml.")
    propose.add_argument("--schema", required=True, help="Path to schema.yaml or schema.inferred.yaml.")
    propose.add_argument("--output-dir", default="", help="Directory to write schema.patch.yaml and schema.proposed.yaml.")

    apply = sub.add_parser("apply-proposal", help="Apply schema.patch.yaml to a schema file and write a backup first.")
    apply.add_argument("--patch", required=True, help="Path to schema.patch.yaml.")
    apply.add_argument("--schema", required=True, help="Path to schema.yaml or schema.inferred.yaml.")
    apply.add_argument("--force", action="store_true", help="Apply even if the patch references a different schema path.")

    build = sub.add_parser("build", help="Build a genomics SQLite DB from standardized YAML metadata.")
    build.add_argument("--source-dir", required=True, help="Directory containing dataset.yaml, schema.yaml, and raw data.")
    build.add_argument("--db", required=True, help="Output SQLite database path.")
    build.add_argument("--fresh", action="store_true", help="Delete the target DB first if it already exists.")
    build.add_argument("--vault-output", default="", help="Optional output directory for rendered markdown vault notes.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "normalize":
        normalize_source_package(
            source_dir=Path(args.source_dir),
            dataset_id=args.dataset_id,
            dataset_name=args.dataset_name,
            organism=args.organism,
        )
        return 0
    if args.command == "build":
        build_dataset(
            source_dir=Path(args.source_dir),
            db_path=Path(args.db),
            fresh=bool(args.fresh),
            vault_output_dir=Path(args.vault_output) if args.vault_output else None,
        )
        return 0
    if args.command == "infer":
        infer_source_package(
            source_file=Path(args.source_file),
            source_dir=Path(args.source_dir) if args.source_dir else None,
            dataset_id=args.dataset_id or None,
            dataset_name=args.dataset_name or None,
            organism=args.organism or None,
            note_paths=[Path(p) for p in args.notes],
            apply=bool(args.apply),
        )
        return 0
    if args.command == "review":
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
        return 0
    if args.command == "propose":
        propose_schema_patch(
            review_path=Path(args.review),
            schema_path=Path(args.schema),
            output_dir=Path(args.output_dir) if args.output_dir else None,
        )
        return 0
    if args.command == "apply-proposal":
        apply_schema_patch(
            patch_path=Path(args.patch),
            schema_path=Path(args.schema),
            force=bool(args.force),
        )
        return 0
    raise ValueError(f"Unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
