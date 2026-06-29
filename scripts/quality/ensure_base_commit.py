#!/usr/bin/env python3
"""Record the current git HEAD as the agent session base commit if absent."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.quality.changed_files import write_base_commit_if_missing  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    """Write the base commit marker used by fail-closed changed-file routing."""
    argv = sys.argv[1:] if argv is None else argv
    write_base_commit_if_missing(REPO_ROOT, overwrite='--force' in argv)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
