#!/usr/bin/env python3
"""DOM primitive contract smoke for Java static UI primitives."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from _api_first_checklib import CSS, JS, LEGACY_PY_ROOT, exists, has_all, has_none, read, run


def main() -> int:
    css_path = CSS / 'ui-primitives.css'
    js_path = JS / 'ui_primitives.js'
    css = read(css_path) + '\n'.join(read(path) for path in sorted((CSS / 'ui-primitives').glob('*.css')))
    js = read(js_path)
    checks = [
        ('ui-primitives.css exists', lambda: exists(css_path)),
        ('ui_primitives.js exists', lambda: exists(js_path)),
        ('primitive CSS covers buttons/forms/tables/states/tokenbar', lambda: has_all(css, ['.btn', '.input', '.data-table', '.empty-state', '.tokenbar-seg'])),
        ('primitive JS uses data-action delegation', lambda: has_all(js, ['data-action', 'closest', 'CustomEvent'])),
        ('tokenbar classes use semantic segments', lambda: has_all(css, ['.tokenbar-seg.fresh', '.tokenbar-seg.read', '.tokenbar-seg.write', '.tokenbar-seg.out'])),
        ('no legacy template primitive dependency', lambda: has_none(css + js, [LEGACY_PY_ROOT, 'ui_' + 'primitives.html'])),
    ]
    return run('DOM primitive API-first QA checks', checks)


if __name__ == '__main__':
    raise SystemExit(main())
