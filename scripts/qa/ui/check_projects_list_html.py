#!/usr/bin/env python3
"""API-first static smoke checks for the Java Projects list page."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from _api_first_checklib import CSS, JS, TEMPLATES, exists, has_all, has_none, read, run


def main() -> int:
    html_path = TEMPLATES / 'projects.html'
    js_path = JS / 'projects.js'
    css_path = CSS / 'projects.css'
    html = read(html_path)
    js = read(js_path)
    checks = [
        ('projects.html exists', lambda: exists(html_path)),
        ('projects.js exists', lambda: exists(js_path)),
        ('projects.css exists', lambda: exists(css_path)),
        (
            'template declares resource APIs',
            lambda: has_all(
                html,
                [
                    'data-api-summary="/api/projects/summary"',
                    'data-api-rows="/api/projects/rows"',
                    'Project rows are loaded from /api/projects/rows.',
                ],
            ),
        ),
        (
            'template keeps loading/state shell',
            lambda: has_all(
                html,
                ['Loading projects', 'Loading matching projects', 'projects-empty', 'role="status"', 'aria-live="polite"'],
            ),
        ),
        (
            'template keeps API-first controls',
            lambda: has_all(
                html,
                ['data-action="sort"', 'data-action="clear-search"', 'data-action="prev-page"', 'data-action="next-page"', 'data-action="page-size"'],
            ),
        ),
        (
            'template has no SSR business rows/tokenbars',
            lambda: has_none(
                html,
                ['{% for project', '{% for p in projects', 'class="tokenbar"', 'class="tokenbar-seg fresh"', 'project_' + 'summary.'],
            ),
        ),
        (
            'JS fetches split Projects APIs',
            lambda: has_all(js, ['/api/projects/summary', '/api/projects/rows', '/api/projects/active-filters']),
        ),
        (
            'JS owns dynamic row/tokenbar rendering',
            lambda: has_all(js, ['renderProjectRows', 'data-action', 'open-project', 'copy', 'tokenbar-seg fresh', 'tokenbar-seg out']),
        ),
        ('JS no legacy HTML fragment fetch', lambda: has_none(js, ['X-Requested-With', "fetch('/projects'", 'fetch("/projects"'])),
    ]
    return run('projects list API-first QA checks', checks)


if __name__ == '__main__':
    raise SystemExit(main())
