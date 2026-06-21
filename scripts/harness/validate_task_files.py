#!/usr/bin/env python3
"""Validate that task markdown files contain the required section headings."""

import sys
from pathlib import Path

required = [
    '## Goal',
    '## Scope',
    '## Files to inspect',
    '## Required changes',
    '## Validation',
    '## Acceptance criteria',
]
errors = []
for p in (Path.cwd() / 'tasks').rglob('*.md') if (Path.cwd() / 'tasks').exists() else []:
    text = p.read_text(encoding='utf-8')
    if 'templates' in p.parts:
        continue
    missing = [h for h in required if h not in text]
    if missing:
        errors.append(f'{p}: missing {missing}')
if errors:
    print('\n'.join(errors))
    sys.exit(1)
print('task files ok')
