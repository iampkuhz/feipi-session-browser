#!/usr/bin/env python3
"""验证 that 必需 harness contract files and entrypoints exist。"""

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
    'scripts/harness/stop_helpers.py',
    'scripts/harness/hook-common.sh',
    'scripts/harness/stop_entry_checks/__init__.py',
    'scripts/harness/sessionctl.py',
]
missing = [p for p in required if not (Path.cwd() / p).exists()]
if missing:
    print('Missing harness paths:')
    for p in missing:
        print(' - ' + p)
    sys.exit(1)
print('harness structure ok')
