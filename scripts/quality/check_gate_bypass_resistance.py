#!/usr/bin/env python3
"""Check required gate bypass resistance via synthetic escape-rate scenarios."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.quality.measure_gate_escape_rate import main as measure_main  # noqa: E402


if __name__ == '__main__':
    raise SystemExit(measure_main())
