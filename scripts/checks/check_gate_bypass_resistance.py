#!/usr/bin/env python3
"""本模块负责用合成场景检查 required Gate 的防绕过能力。

不负责修复被检查对象；由 Gate executor 或维护者命令行调用。"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.checks._trigger import parse_changed_files, skip_if_not_triggered  # noqa: E402
from scripts.checks.measure_gate_escape_rate import main as measure_main  # noqa: E402

TRIGGER_PATTERNS = [
    'AGENTS.md',
    'CLAUDE.md',
    '.agents/**',
    '.claude/**',
    '.codex/**',
    '.qoder/**',
    'skills/**',
    'harness/**',
    'scripts/agent_runtime/**/*.py',
    'scripts/hooks/**/*.py',
    'scripts/harness/**/*.py',
    'scripts/harness/**/*.sh',
    'scripts/checks/**/*.py',
]

# 自感知跳过：当变更文件不匹配触发模式时直接 SKIP。
_changed_files = None
if '--changed-files' in sys.argv:
    _idx = sys.argv.index('--changed-files')
    if _idx + 1 < len(sys.argv):
        _changed_files = parse_changed_files(sys.argv[_idx + 1])
    skip_if_not_triggered(_changed_files, TRIGGER_PATTERNS)
else:
    skip_if_not_triggered(None, TRIGGER_PATTERNS)


if __name__ == '__main__':
    raise SystemExit(measure_main())
