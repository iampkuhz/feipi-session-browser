#!/usr/bin/env python3
"""API-first static smoke checks for the Java Sessions list page."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from _api_first_checklib import CSS, JS, TEMPLATES, exists, has_all, has_none, read, run


# 运行页面静态契约检查。
def main() -> int:
    """返回：
        进程退出码。
    """
    html_path = TEMPLATES / 'sessions.html'
    js_path = JS / 'sessions-list.js'
    css_path = CSS / 'sessions-list.css'
    html = read(html_path)
    js = read(js_path)
    checks = [
        ('sessions.html exists', lambda: exists(html_path)),
        ('sessions-list.js exists', lambda: exists(js_path)),
        ('sessions-list.css exists', lambda: exists(css_path)),
        (
            'template declares split Sessions APIs',
            lambda: has_all(
                html,
                [
                    'data-api-summary="/api/sessions/summary"',
                    'data-api-options="/api/sessions/options"',
                    'data-api-rows="/api/sessions/rows"',
                    'Filters loaded from /api/sessions/active-filters',
                ],
            ),
        ),
        (
            'template keeps loading shell and controls',
            lambda: has_all(
                html,
                ['Loading sessions', 'Loading matching sessions', 'data-action="sort"', 'data-action="clear"', 'data-action="prev-page"', 'data-action="next-page"', 'data-action="page-size"'],
            ),
        ),
        (
            'template has no SSR session rows/tokenbars',
            lambda: has_none(html, ['{% for session', '{% for row', 'tokenbar-seg fresh', 'sessions_' + 'aggregate', 'data-action="row"']),
        ),
        (
            'JS fetches split Sessions APIs',
            lambda: has_all(js, ['/api/sessions/summary', '/api/sessions/options', '/api/sessions/rows', '/api/sessions/active-filters']),
        ),
        (
            'JS owns dynamic row/tokenbar/pagination rendering',
            lambda: has_all(js, ['renderRows', 'renderPagination', 'data-action', "setAttribute('data-action', 'row')", 'tokenbar-seg fresh', 'tokenbar-seg out']),
        ),
        ('JS no legacy /sessions HTML fetch headers', lambda: has_none(js, ['X-Requested-With'])),
    ]
    return run('sessions list API-first QA checks', checks)


if __name__ == '__main__':
    raise SystemExit(main())
