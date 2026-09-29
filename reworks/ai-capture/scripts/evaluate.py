#!/usr/bin/env python3
"""Evaluate Capture datasets (run), or grade saved responses offline (score)."""

from pathlib import Path
import sys

_ROOT = Path(__file__).resolve().parents[1]
for _source in (_ROOT, _ROOT / "src", _ROOT / "src/capture/common"):
    sys.path.insert(0, str(_source))

from evals.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
