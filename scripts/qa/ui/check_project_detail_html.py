#!/usr/bin/env python3
"""API-first static smoke checks for the Java Project Detail page."""

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
    html_path = TEMPLATES / 'project.html'
    js_path = JS / 'projects.js'
    css_path = CSS / 'projects.css'
    html = read(html_path)
    js = read(js_path)
    checks = [
        ('project.html exists', lambda: exists(html_path)),
        ('projects.js exists', lambda: exists(js_path)),
        ('projects.css exists', lambda: exists(css_path)),
        (
            'template declares project resource APIs',
            lambda: has_all(
                html,
                [
                    'data-api-summary="/api/projects/{{ project.projectKey | urlencode }}/summary"',
                    'data-api-token-trend="/api/projects/{{ project.projectKey | urlencode }}/token-trend"',
                    'data-api-agent-mix="/api/projects/{{ project.projectKey | urlencode }}/agent-mix"',
                    'data-api-tool-hotspots="/api/projects/{{ project.projectKey | urlencode }}/tool-hotspots"',
                    'data-api-sessions-summary="/api/projects/{{ project.projectKey | urlencode }}/sessions/summary"',
                    'data-api-sessions="/api/projects/{{ project.projectKey | urlencode }}/sessions/rows"',
                ],
            ),
        ),
        (
            'template keeps API loading shells',
            lambda: has_all(
                html,
                ['Loading token trend from API', 'Loading agent mix from API', 'Project session rows are loaded from /api/projects/{projectKey}/sessions/rows.', 'Tool hotspot data unavailable'],
            ),
        ),
        (
            'template keeps interaction controls only',
            lambda: has_all(html, ['role="search"', 'data-action="apply-search"', 'data-action="sort"', 'data-action="prev-page"', 'data-action="next-page"', 'data-action="page-size"']),
        ),
        (
            'template has no SSR detail business rows/tokenbars',
            lambda: has_none(
                html,
                ['project_' + 'detail.', '{% for session', '{% for row', 'class="tokenbar"', 'class="tokenbar-seg fresh"'],
            ),
        ),
        (
            'JS fetches split Project Detail APIs',
            lambda: has_all(
                js,
                ['/summary', '/token-trend', '/agent-mix', '/tool-hotspots', '/sessions/summary', '/sessions/rows'],
            ),
        ),
        (
            'JS owns dynamic project-session row rendering',
            lambda: has_all(js, ['renderProjectSessions', 'data-action', 'open-session', 'view-all', 'renderProjectTokenTrend', 'renderProjectAgentMix']),
        ),
    ]
    return run('project detail API-first QA checks', checks)


if __name__ == '__main__':
    raise SystemExit(main())
