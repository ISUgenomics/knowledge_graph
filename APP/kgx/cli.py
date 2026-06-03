"""
kgx CLI entry point.

Usage:
    python -m kgx                          # uses config.yaml in cwd
    python -m kgx --db vault.db            # override db path
    python -m kgx --config /path/to/cfg    # use specific config file
    python -m kgx --port 8080              # override port
    python -m kgx --no-browser             # don't auto-open browser
"""

import argparse
import sys
import time
import webbrowser
from pathlib import Path
from threading import Timer

import uvicorn

from kgx.config import load_config
from kgx.api import create_app


def main():
    parser = argparse.ArgumentParser(
        description="Knowledge Graph Explorer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--db", help="Path to vault.db (overrides config)")
    parser.add_argument("--config", help="Path to config.yaml")
    parser.add_argument("--port", type=int, help="Server port (overrides config)")
    parser.add_argument("--host", help="Server host (overrides config)")
    parser.add_argument("--no-browser", action="store_true", help="Don't open browser")
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
    if not db_path.exists():
        print(f"Error: Database not found at {db_path}", file=sys.stderr)
        print("Create a vault.db first by running your skills, or specify a different path with --db", file=sys.stderr)
        sys.exit(1)

    # Build app
    app_config = {
        "db_path": str(db_path),
        "server": config.server.model_dump(),
        "ui": config.ui.model_dump(),
        "llm": config.llm.model_dump(),
        "skills": config.skills.model_dump(),
        "explore": config.explore.model_dump(),
        "embedding": config.embedding.model_dump(),
    }
    app = create_app(app_config)

    host = config.server.host
    port = config.server.port
    url = f"http://{host}:{port}"

    print(f"\nKnowledge Graph Explorer")
    print(f"  DB:     {db_path.resolve()}")
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
