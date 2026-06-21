#!/usr/bin/env python3
"""Validate required repository schema paths for OpenSpec and harness gates.

This root-level script is called by required quality gates to make sure the
agent, OpenSpec, harness, and quality entry points still exist. It reads only
the repository layout, prints missing paths, and exits 1 for schema drift or 0
when the expected structure is present.
"""

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
    'scripts/agent_hooks',
    'scripts/quality',
    'scripts/session-browser.sh',
]
missing = [p for p in required if not (Path.cwd() / p).exists()]
if missing:
    print('Missing required paths:')
    for p in missing:
        print(' - ' + p)
    sys.exit(1)
print('openspec layout ok')
