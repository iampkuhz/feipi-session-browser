#!/usr/bin/env python3
"""Validate active OpenSpec task files contain checkboxes and validation notes."""

import sys
from pathlib import Path

required_checkbox = ['- [ ]', '- [x]']  # at least one checkbox pattern
required = [required_checkbox, 'Validation:']
errors = []
for p in (
    (Path.cwd() / 'openspec' / 'changes').rglob('tasks.md')
    if (Path.cwd() / 'openspec' / 'changes').exists()
    else []
):
    if 'archive' in p.parts:
        continue
    text = p.read_text(encoding='utf-8')
    has_checkbox = any(c in text for c in required_checkbox)
    if not has_checkbox:
        errors.append(f'{p}: missing checkbox pattern')
    if 'Validation:' not in text:
        errors.append(f'{p}: missing Validation: lines')
if errors:
    print('\n'.join(errors))
    sys.exit(1)
print('task files ok')
