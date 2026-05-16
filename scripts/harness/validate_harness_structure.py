#!/usr/bin/env python3
from pathlib import Path
import sys
required = [
    'CLAUDE.md','AGENTS.md','.claude/settings.json','.claude/commands','.claude/agents',
    'openspec/specs','openspec/changes','harness/workflow','harness/context','harness/prompts',
    'harness/quality','harness/templates','harness/migration','scripts/harness'
]
missing = [p for p in required if not (Path.cwd()/p).exists()]
if missing:
    print('Missing harness paths:')
    for p in missing: print(' - '+p)
    sys.exit(1)
print('harness structure ok')
