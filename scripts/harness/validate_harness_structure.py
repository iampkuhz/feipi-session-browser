#!/usr/bin/env python3
"""本模块负责执行 `validate_harness_structure` 对应的确定性仓库检查。

不负责产品业务处理；由 harness 命令行或受控收口流程调用。"""

import sys
from pathlib import Path

required = [
    'CLAUDE.md',
    'AGENTS.md',
    'harness/agent-policy.manifest.yaml',
    'harness/skill-registry.yaml',
    'skills/authoring/feipi-openspec-orchestrate-change/SKILL.md',
    '.agents/skills/feipi-openspec-orchestrate-change',
    '.codex/skills/feipi-openspec-orchestrate-change',
    '.claude/skills/feipi-openspec-orchestrate-change',
    'openspec/specs',
    'openspec/changes',
    'harness/README.md',
    'scripts/openspec/validate_layout.py',
]
missing = [p for p in required if not (Path.cwd() / p).exists()]
if missing:
    print('Missing harness paths:')
    for p in missing:
        print(' - ' + p)
    sys.exit(1)
print('harness structure ok')
