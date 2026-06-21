#!/usr/bin/env python3
"""Validate active OpenSpec change layout for required quality gates.

The script scans openspec/changes from the repository root, skips the archive,
and fails when active changes are missing proposal.md or tasks.md. It has no
write side effects; stdout lists structural errors and the exit code is 1 on
layout drift or 0 when the layout is valid.
"""

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
print('repo structure ok')
