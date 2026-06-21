#!/usr/bin/env python3
"""Validate that required harness contract files and entrypoints exist."""

import sys
from pathlib import Path

required = [
    'CLAUDE.md',
    'AGENTS.md',
    '.claude/settings.json',
    '.claude/commands',
    '.claude/agents',
    '.codex/hooks.json',
    '.codex/hooks/stop_check.sh',
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
    'harness/context/repo-map.md',
    'harness/context/ui-context.md',
    'harness/workflow/change-lifecycle.md',
    'harness/workflow/subagent-execution.md',
    'harness/quality/deterministic-quality-gate.md',
    'harness/quality/quality-gate-matrix.md',
    'scripts/harness',
    'scripts/harness/agent_stop_check.py',
]
missing = [p for p in required if not (Path.cwd() / p).exists()]
if missing:
    print('Missing harness paths:')
    for p in missing:
        print(' - ' + p)
    sys.exit(1)
print('harness structure ok')
