#!/usr/bin/env python3
from pathlib import Path
import sys
required = [
    'CLAUDE.md', 'AGENTS.md',
    '.claude/settings.json', '.claude/commands', '.claude/agents',
    'openspec/specs', 'openspec/changes',
    'openspec/schemas', 'openspec/templates',
    'harness/README.md', 'harness/manifest.yaml',
    'scripts/openspec', 'scripts/agent_hooks', 'scripts/quality',
    'scripts/session-browser.sh',
]
missing = [p for p in required if not (Path.cwd() / p).exists()]
if missing:
    print('Missing required paths:')
    for p in missing:
        print(' - ' + p)
    sys.exit(1)
print('openspec layout ok')
