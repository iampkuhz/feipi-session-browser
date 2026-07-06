#!/usr/bin/env python3
"""Repository-level UI static contract smoke for the Java web resources."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from _api_first_checklib import CSS, JS, TEMPLATES, LEGACY_PY_ROOT, LEGACY_TEMPLATE_ROOT, exists, has_all, has_none, read, run


# 运行页面静态契约检查。
def main() -> int:
    """返回：
        进程退出码。
    """
    templates = ''.join(read(path) for path in sorted(TEMPLATES.glob('*.html')))
    css = ''.join(read(path) for path in sorted(CSS.glob('*.css')))
    js = ''.join(read(path) for path in sorted(JS.glob('*.js')))
    checks = [
        ('Java templates directory exists', lambda: exists(TEMPLATES)),
        ('Java static css directory exists', lambda: exists(CSS)),
        ('Java static js directory exists', lambda: exists(JS)),
        (
            'core pages declare API-first resource links',
            lambda: has_all(
                templates,
                ['/api/dashboard/summary', '/api/sessions/rows', '/api/projects/rows', '/api/projects/{projectKey}/sessions/rows', '/api/sessions/{agent}/{sessionId}/rounds'],
            ),
        ),
        (
            'shared UI primitive assets are present',
            lambda: has_all(css + js, ['.tokenbar-seg', '.empty-state', '.data-table', 'data-action']),
        ),
        (
            'templates avoid legacy Python paths and inline event handlers',
            lambda: has_none(templates + css + js, [LEGACY_PY_ROOT, LEGACY_TEMPLATE_ROOT, 'onclick=']),
        ),
        (
            'API-first JS avoids legacy XHR HTML fragment header',
            lambda: has_none(js, ['X-Requested-With']),
        ),
        (
            'responsive shell constraints exist',
            lambda: has_all(read(CSS / 'shell.css') + read(CSS / 'base.css'), ['--max', '.main', '@media']),
        ),
    ]
    return run('Java UI contract QA checks', checks)


if __name__ == '__main__':
    raise SystemExit(main())
