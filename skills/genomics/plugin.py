#!/usr/bin/env python3
"""Thin entry wrapper for the genomics skill."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from run_genomics import main


if __name__ == "__main__":
    raise SystemExit(main())
