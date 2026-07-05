#!/usr/bin/env python3
"""API-first static smoke checks for the Java Session Detail page."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from _api_first_checklib import CSS, JS, TEMPLATES, LEGACY_ROUND_TOKEN_ATTR, exists, has_all, has_none, read, run


def main() -> int:
    html_path = TEMPLATES / 'session.html'
    css_path = CSS / 'session-detail.css'
    css_parts = ''.join(read(path) for path in sorted((CSS / 'session-detail').glob('*.css')))
    init_js = read(JS / 'session-detail/init.js')
    lazy_js = read(JS / 'session-detail/lazy_rounds.js')
    payload_js = read(JS / 'session-detail/payload.js')
    html = read(html_path)
    checks = [
        ('session.html exists', lambda: exists(html_path)),
        ('session-detail.css exists', lambda: exists(css_path)),
        ('session detail init.js exists', lambda: exists(JS / 'session-detail/init.js')),
        (
            'template declares API base metadata',
            lambda: has_all(html, ['name="payload-api-base"', 'name="session-page-api-base"', 'data-trace-page']),
        ),
        (
            'template keeps API-first shells',
            lambda: has_all(
                html,
                [
                    'Loading session',
                    'Loaded from /meta API',
                    'Loaded from /api/sessions/{agent}/{sessionId}/metrics',
                    'Anomaly rows are loaded from /api/sessions/{agent}/{sessionId}/diagnostics.',
                    'Trace rows are loaded from /api/sessions/{agent}/{sessionId}/rounds.',
                    'data-payload-sources-container',
                ],
            ),
        ),
        (
            'template exposes trace interaction controls',
            lambda: has_all(html, ['data-action="status-all"', 'data-action="status-failed"', 'data-action="status-low-cache"', 'data-action="toggle-all"', 'data-trace-list']),
        ),
        (
            'template no SSR trace/payload business data',
            lambda: has_none(html, ['{% for round', '{% for call', LEGACY_ROUND_TOKEN_ATTR, 'session_' + 'metrics.', 'payload_' + 'sources']),
        ),
        (
            'JS hydrates split Session Detail APIs',
            lambda: has_all(init_js, ['/meta', '/metrics', '/diagnostics', '/rounds', '/payloads']),
        ),
        (
            'JS keeps lazy round/payload interactions',
            lambda: has_all(lazy_js + payload_js, ['open-payload', 'data-payload-id', '/round/', 'payload-api-base']),
        ),
        (
            'CSS split parts define canonical selectors',
            lambda: has_all(css_parts, ['--sd-brand', '--sd-err', '.sd-hero', '.sd-tabs', '.trace-table', '.round-row', '.sd-payload-modal']),
        ),
    ]
    return run('session detail API-first QA checks', checks)


if __name__ == '__main__':
    raise SystemExit(main())
