#!/usr/bin/env python3
"""本模块负责执行 `validate_harness_structure` 对应的确定性仓库检查。

不负责产品业务处理；由 harness 命令行或受控收口流程调用。"""

import sys
from pathlib import Path

required = [
    'CLAUDE.md',
    'AGENTS.md',
    '.claude/settings.json',
    '.claude/commands',
    '.claude/agents',
    '.codex/hooks.json',
    '.qoder/settings.json',
    '.qoder/settings.local.example.json',
    'skills/authoring/feipi-openspec-orchestrate-change/SKILL.md',
    '.agents/skills/feipi-openspec-orchestrate-change',
    '.codex/skills/feipi-openspec-orchestrate-change',
    '.claude/skills/feipi-openspec-orchestrate-change',
    'openspec/specs',
    'openspec/changes',
    'harness/README.md',
    'harness/manifest.yaml',
    'harness/agent-runtime.manifest.yaml',
    'docs/agent-runtime.md',
    'scripts/harness',
    'scripts/harness/change.py',
    'scripts/agent_runtime/hook_entry.py',
    'scripts/agent_runtime/change/controller.py',
    'scripts/agent_runtime/change/model.py',
    'scripts/agent_runtime/change/store.py',
    'scripts/agent_runtime/change/runtime.py',
    'scripts/agent_runtime/change/candidate.py',
    'scripts/agent_runtime/change/fixture.py',
    'scripts/agent_runtime/change/protocol.py',
    'scripts/agent_runtime/stop/evidence.py',
    'scripts/harness/hook_dispatch.py',
    'scripts/harness/sessionctl.py',
]
missing = [p for p in required if not (Path.cwd() / p).exists()]
if missing:
    print('Missing harness paths:')
    for p in missing:
        print(' - ' + p)
    sys.exit(1)
print('harness structure ok')
