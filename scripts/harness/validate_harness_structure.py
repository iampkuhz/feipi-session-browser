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
    '.codex/hooks/session-start.sh',
    '.codex/hooks/pre_tool_guard.sh',
    '.codex/hooks/pre_write_guard.sh',
    '.codex/hooks/post_bash_guard.sh',
    '.codex/hooks/post_tool_guard.sh',
    '.codex/hooks/tool_failure.sh',
    '.codex/hooks/stop_check.sh',
    '.codex/hooks/stop_failure.sh',
    '.codex/hooks/session_end.sh',
    '.qoder/hooks/pre_tool_guard.sh',
    '.qoder/hooks/post_bash_guard.sh',
    '.qoder/hooks/post_tool_guard.sh',
    '.qoder/hooks/stop_check.sh',
    'skills/authoring/feipi-openspec-orchestrate-change/SKILL.md',
    '.agents/skills/feipi-openspec-orchestrate-change',
    '.codex/skills/feipi-openspec-orchestrate-change',
    '.claude/skills/feipi-openspec-orchestrate-change',
    'openspec/specs',
    'openspec/changes',
    'harness/README.md',
    'harness/agent-runtime.md',
    'harness/manifest.yaml',
    'harness/agent-runtime.manifest.yaml',
    'harness/context/repo-map.md',
    'harness/context/ui-context.md',
    'harness/workflow/change-lifecycle.md',
    'harness/workflow/subagent-execution.md',
    'harness/quality/deterministic-quality-gate.md',
    'harness/quality/quality-gate-matrix.md',
    'scripts/harness',
    'scripts/harness/stop_entry.py',
    'scripts/agent_runtime/stop/model.py',
    'scripts/agent_runtime/stop/pipeline.py',
    'scripts/agent_runtime/stop/evidence.py',
    'scripts/agent_runtime/stop/recovery.py',
    'scripts/agent_runtime/stop/report.py',
    'scripts/harness/hook-common.sh',
    'scripts/harness/sessionctl.py',
]
missing = [p for p in required if not (Path.cwd() / p).exists()]
if missing:
    print('Missing harness paths:')
    for p in missing:
        print(' - ' + p)
    sys.exit(1)
print('harness structure ok')
