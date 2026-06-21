#!/usr/bin/env python3
"""Current static UI checks for feipi-session-browser."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path.cwd()
TEMPLATES = ROOT / 'src/session_browser/web/templates'
STATIC = ROOT / 'src/session_browser/web/static'

errors: list[str] = []
passes: list[str] = []


def read(path: Path) -> str:
    """Read a UI contract source file for the static QA script.

    Args:
        path: Template or asset path to inspect.

    Returns:
        File text, or an empty string when missing so the caller can fail the relevant check.
    """
    return path.read_text(encoding='utf-8', errors='ignore')


for base in [TEMPLATES, STATIC / 'css', STATIC / 'js']:
    if base.exists():
        passes.append(f'directory exists: {base.relative_to(ROOT)}')
    else:
        errors.append(f'missing directory: {base.relative_to(ROOT)}')

for base in [TEMPLATES, STATIC / 'css', STATIC / 'js']:
    if not base.exists():
        continue
    for path in base.rglob('*'):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT)
        if re.search(r'v\d+\.(css|js|html)$', path.name):
            errors.append(f'versioned filename: {rel}')
        if re.search(r'(patch|fix|overlay)\.(css|js)$', path.name):
            errors.append(f'patch/fix/overlay filename: {rel}')
        if path.suffix in {'.html', '.css', '.js'}:
            text = read(path)
            for pattern, label in [
                (r'session-browser-v\d+\.css', 'versioned global css reference'),
                (r'dashboard-v\d+\.css', 'versioned dashboard css reference'),
                (r'session_browser_ui_v\d+\.js', 'versioned ui js reference'),
            ]:
                if re.search(pattern, text):
                    errors.append(f'{label}: {rel}')

css_text = '\n'.join(read(path) for path in (STATIC / 'css').rglob('*.css'))
if re.search(r'@media\s*\([^)]*min-width:\s*1400px', css_text):
    passes.append('desktop viewport rule exists')
else:
    errors.append('missing desktop viewport rule: min-width 1400px')

for pattern in [
    r'max-width:\s*(767|768|820)px',
    r'@media[^{]*(mobile|tablet|ipad)',
]:
    if re.search(pattern, css_text, re.IGNORECASE):
        errors.append('forbidden mobile/tablet viewport rule in CSS')

dashboard = TEMPLATES / 'dashboard.html'
if dashboard.exists():
    text = read(dashboard)
    if 'css/dashboard.css' in text:
        passes.append('dashboard imports dashboard.css')
    else:
        errors.append('dashboard.html does not import dashboard.css')
    if 'js/dashboard.js' in text:
        passes.append('dashboard imports dashboard.js')
    else:
        errors.append('dashboard.html does not import dashboard.js')

if passes:
    print('UI contract checks:')
    for item in passes:
        print(f'  PASS: {item}')

if errors:
    print('\nUI contract check failed:')
    for item in errors:
        print(f'  FAIL: {item}')
    sys.exit(1)

print(f'\nAll UI contract checks passed ({len(passes)} checks)')
