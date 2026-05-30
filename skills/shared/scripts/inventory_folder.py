#!/usr/bin/env python3
"""
inventory_folder.py — Walk a folder and extract text from all supported files.

Returns a structured inventory with extracted text for each file.
Max depth 2 to avoid crawling into deep nested structures.
"""

import os
from pathlib import Path

from extract_text import extract_text, is_supported


def inventory_folder(folder_path: str, max_depth: int = 2,
                     max_chars_per_file: int = 15000) -> dict:
    """
    Inventory a folder and extract text from all supported files.

    Returns:
        {
            "folder": str,
            "files": [
                {
                    "path": str,
                    "name": str,
                    "format": str,
                    "chars": int,
                    "text": str,
                    "skipped": bool,
                    "error": str | None,
                },
                ...
            ],
            "total_files": int,
            "supported_files": int,
            "skipped_files": int,
            "total_chars": int,
        }
    """
    folder = Path(folder_path)
    if not folder.is_dir():
        return {
            "folder": str(folder),
            "files": [],
            "total_files": 0,
            "supported_files": 0,
            "skipped_files": 0,
            "total_chars": 0,
            "error": f"Not a directory: {folder_path}",
        }

    files = []
    base_depth = len(folder.parts)

    for root, dirs, filenames in os.walk(folder):
        current_depth = len(Path(root).parts) - base_depth
        if current_depth >= max_depth:
            dirs.clear()
            continue

        # Skip hidden directories and common junk
        dirs[:] = [d for d in dirs if not d.startswith(".")
                   and d not in ("__pycache__", "node_modules", ".git")]

        for fname in sorted(filenames):
            if fname.startswith("."):
                continue

            fpath = Path(root) / fname

            if not is_supported(str(fpath)):
                files.append({
                    "path": str(fpath),
                    "name": fname,
                    "format": fpath.suffix.lstrip(".") or "unknown",
                    "chars": 0,
                    "text": "",
                    "skipped": True,
                    "error": f"Unsupported format: {fpath.suffix}",
                })
                continue

            result = extract_text(str(fpath), max_chars=max_chars_per_file)
            files.append({
                "path": str(fpath),
                "name": fname,
                "format": result["format"],
                "chars": result["chars"],
                "text": result["text"],
                "skipped": False,
                "error": result.get("error"),
            })

    supported = [f for f in files if not f["skipped"]]
    skipped = [f for f in files if f["skipped"]]

    return {
        "folder": str(folder),
        "files": files,
        "total_files": len(files),
        "supported_files": len(supported),
        "skipped_files": len(skipped),
        "total_chars": sum(f["chars"] for f in supported),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Inventory a folder")
    parser.add_argument("folder", help="Path to folder")
    args = parser.parse_args()

    result = inventory_folder(args.folder)
    # Print summary without full text
    summary = {k: v for k, v in result.items() if k != "files"}
    summary["files"] = [
        {k: v for k, v in f.items() if k != "text"}
        for f in result["files"]
    ]
    print(json.dumps(summary, indent=2))
