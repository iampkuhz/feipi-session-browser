#!/usr/bin/env python3
"""Quality wrapper for the primary-session manifest validator."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.quality._trigger import parse_changed_files, skip_if_not_triggered
from scripts.harness.validate_primary_session_manifest import main  # noqa: E402

# 声明本脚本的触发模式：只有匹配的文件变更时才运行本检查。
TRIGGER_PATTERNS = [
    'data/**',
    'scripts/quality/check_primary_session_manifest.py',
]


if __name__ == "__main__":
    # 自感知跳过：当变更文件不匹配触发模式时直接 SKIP。
    changed_files = None
    for i, arg in enumerate(sys.argv):
        if arg == '--changed-files' and i + 1 < len(sys.argv):
            changed_files = parse_changed_files(sys.argv[i + 1])
            break
    skip_if_not_triggered(changed_files, TRIGGER_PATTERNS)

    raise SystemExit(main([]))
