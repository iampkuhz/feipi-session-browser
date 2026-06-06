#!/usr/bin/env python3
from pathlib import Path
import sys
required = [
    'CLAUDE.md','AGENTS.md','.claude/settings.json','.claude/commands','.claude/agents',
    '.codex/hooks.json','.codex/hooks/stop_check.sh','.qoder/hooks/stop_check.sh',
    'openspec/specs','openspec/changes','harness/README.md','harness/agent-runtime.md','harness/manifest.yaml',
    'scripts/harness','scripts/harness/agent_stop_check.py'
]
missing = [p for p in required if not (Path.cwd()/p).exists()]
if missing:
    print('Missing harness paths:')
    for p in missing: print(' - '+p)
    sys.exit(1)
print('harness structure ok')
