#!/usr/bin/env python3
"""Validate the minimal OpenSpec directory layout required by harness checks."""

import sys
from pathlib import Path

root = Path.cwd() / 'openspec'
errors = []
if not (root / 'specs').is_dir():
    errors.append('openspec/specs missing')
if not (root / 'changes').is_dir():
    errors.append('openspec/changes missing')
for change in (root / 'changes').glob('*') if (root / 'changes').exists() else []:
    if change.name == 'archive' or not change.is_dir():
        continue
    for f in ['proposal.md', 'tasks.md']:
        if not (change / f).exists():
            errors.append(f'{change}/{f} missing')
if errors:
    print('\n'.join(errors))
    sys.exit(1)
print('openspec layout ok')
