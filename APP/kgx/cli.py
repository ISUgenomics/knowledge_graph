"""
kgx CLI entry point.

Usage:
    python -m kgx                          # uses config/default.yaml in cwd
    python -m kgx --db vault.db            # override db path
    python -m kgx --config /path/to/cfg    # use specific config file
    python -m kgx --port 8080              # override port
    python -m kgx --no-browser             # don't auto-open browser
"""

import argparse
import shutil
import sys
import time
import webbrowser
from pathlib import Path
from threading import Timer

import uvicorn

from kgx.config import load_config
from kgx.api import create_app
from kgx.visualization_audit import audit_visualization_contract, repair_visualization_contract


def _repo_root() -> Path:
    """Return the KnowledgeGraph repository root."""
    return Path(__file__).resolve().parents[2]


def _seed_db_path(db_path: Path) -> Path:
    """
    Return the preferred seed DB path for first-run bootstrapping.

    Order:
    1. Adjacent sibling seed file next to the target DB
    2. Repo sample seed at sample_data/3_db/vault.seed.db
    """
    sibling_seed = db_path.with_suffix(".seed.db")
    if sibling_seed.exists():
        return sibling_seed
    return _repo_root() / "sample_data" / "3_db" / "vault.seed.db"


def _bootstrap_db_from_seed(db_path: Path) -> bool:
    """
    Create db_path from a sibling seed DB if present.

    Returns True when a seed copy was performed, otherwise False.
    """
    seed_path = _seed_db_path(db_path)
    if db_path.exists() or not seed_path.exists():
        return False

    db_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(seed_path, db_path)
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Knowledge Graph Explorer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--db", help="Path to vault.db (overrides config)")
    parser.add_argument("--config", help="Path to a KGX config YAML file")
    parser.add_argument("--port", type=int, help="Server port (overrides config)")
    parser.add_argument("--host", help="Server host (overrides config)")
    parser.add_argument("--no-browser", action="store_true", help="Don't open browser")
    parser.add_argument("--audit-visualization", action="store_true", help="Audit the database against db_build.visualization and exit")
    parser.add_argument("--repair-visualization", action="store_true", help="Safely backfill configured visualization metadata aliases and exit")
    args = parser.parse_args()

    # Load config
    config = load_config(args.config)

    # Apply CLI overrides
    if args.db:
        config.db.path = args.db
    if args.port:
        config.server.port = args.port
    if args.host:
        config.server.host = args.host

    # Validate DB path
    db_path = Path(config.db.path)
    bootstrapped = _bootstrap_db_from_seed(db_path)
    if not db_path.exists():
        print(f"Error: Database not found at {db_path}", file=sys.stderr)
        print("Create a vault.db first by running your skills, or specify a different path with --db", file=sys.stderr)
        sys.exit(1)

    if args.repair_visualization:
        repaired = repair_visualization_contract(db_path, config.db_build.visualization.model_dump())
        if repaired:
            print(f"Visualization repair updated {len(repaired)} entities.")
        else:
            print("Visualization repair made no changes.")
        if not args.audit_visualization:
            return

    if args.audit_visualization:
        warnings = audit_visualization_contract(db_path, config.db_build.visualization.model_dump())
        if warnings:
            print("Visualization contract warnings:")
            for warning in warnings:
                print(f"  - {warning}")
            sys.exit(2)
        print("Visualization contract audit passed.")
        return

    # Build app
    app_config = {
        "db_path": str(db_path),
        "server": config.server.model_dump(),
        "ui": config.ui.model_dump(),
        "llm": config.llm.model_dump(),
        "skills": config.skills.model_dump(),
        "explore": config.explore.model_dump(),
        "embedding": config.embedding.model_dump(),
        "db_build": config.db_build.model_dump(),
    }
    app = create_app(app_config)

    host = config.server.host
    port = config.server.port
    url = f"http://{host}:{port}"

    print(f"\nKnowledge Graph Explorer")
    print(f"  DB:     {db_path.resolve()}")
    if bootstrapped:
        print(f"  Seed:   bootstrapped from {_seed_db_path(db_path).resolve()}")
    print(f"  URL:    {url}")
    if host == "0.0.0.0":
        print(f"  WARNING: Listening on all interfaces. API endpoints have no authentication.")
        print(f"           Only use 0.0.0.0 on trusted networks.")
    print(f"  Press Ctrl+C to stop\n")

    # Open browser after short delay (let server start first)
    if not args.no_browser:
        Timer(1.2, lambda: webbrowser.open(url)).start()

    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="warning",  # quiet — we print our own startup
    )


if __name__ == "__main__":
    main()
