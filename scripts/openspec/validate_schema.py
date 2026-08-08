#!/usr/bin/env python3
"""本模块负责执行 `validate_schema` 对应的确定性仓库检查。

不负责修改业务代码；由 OpenSpec 命令行或 required Gate 调用。"""

import sys
from pathlib import Path

required = [
    'CLAUDE.md',
    'AGENTS.md',
    '.claude/settings.json',
    '.claude/commands',
    '.claude/agents',
    'openspec/specs',
    'openspec/changes',
    'openspec/schemas',
    'openspec/templates',
    'harness/README.md',
    'harness/manifest.yaml',
    'scripts/openspec',
    'scripts/gates/checks',
    'scripts/session-browser.sh',
]
missing = [p for p in required if not (Path.cwd() / p).exists()]
if missing:
    print('Missing required paths:')
    for p in missing:
        print(' - ' + p)
    sys.exit(1)
print('openspec layout ok')
