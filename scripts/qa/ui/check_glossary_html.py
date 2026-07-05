#!/usr/bin/env python3
"""Static/API-section smoke checks for the Java Token Glossary page."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from _api_first_checklib import CSS, JS, TEMPLATES, LEGACY_PY_ROOT, exists, has_all, has_none, read, run


def main() -> int:
    html_path = TEMPLATES / 'glossary.html'
    js_path = JS / 'glossary.js'
    css_path = CSS / 'glossary.css'
    api_handler = read(Path(__file__).resolve().parents[3] / 'java/web/src/main/java/com/feipi/session/browser/web/api/GlossaryApiHandler.java')
    routes = read(Path(__file__).resolve().parents[3] / 'java/web/src/main/java/com/feipi/session/browser/web/WebCompositionRoot.java')
    html = read(html_path)
    js = read(js_path)
    checks = [
        ('glossary.html exists', lambda: exists(html_path)),
        ('glossary.js exists', lambda: exists(js_path)),
        ('glossary.css exists', lambda: exists(css_path)),
        (
            'template covers glossary sections statically',
            lambda: has_all(html, ['Token Types', 'Derived Metrics', 'Provider Field Mapping', 'Round Signals', 'Badge Reference']),
        ),
        (
            'template keeps search/sort smoke controls',
            lambda: has_all(html, ['id="glossary-search"', 'data-search="glossary-term"', 'data-action="sort"', 'glossary-empty', 'aria-live="polite"']),
        ),
        (
            'template has required glossary terms/badges',
            lambda: has_all(html, ['Fresh', 'Cache Read', 'Cache Write', 'Output', 'Total Tokens', 'Not reported', 'Estimated']),
        ),
        (
            'Java exposes optional section APIs for contract tests',
            lambda: has_all(routes + api_handler, ['/api/glossary/summary', '/api/glossary/token-types', '/api/glossary/derived-metrics', '/api/glossary/provider-mapping', '/api/glossary/round-signals']),
        ),
        ('glossary search JS and shared table sort are present', lambda: has_all(js + read(JS / 'data-table.js'), ['glossary-search', 'filterGlossary', 'data-table-enhanced', 'DataTable.sort'])),
        ('no legacy dynamic data helpers', lambda: has_none(html + js, ['format_compact_token', LEGACY_PY_ROOT, 'onclick='])),
    ]
    return run('glossary API/static contract QA checks', checks)


if __name__ == '__main__':
    raise SystemExit(main())
