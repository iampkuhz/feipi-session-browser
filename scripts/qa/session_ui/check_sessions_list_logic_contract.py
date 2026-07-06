#!/usr/bin/env python3
"""API-first logic contract smoke for the Sessions list page.

The old checker expected server-rendered business rows.  The current contract is
that the HTML is only a shell and data correctness is proven by
/api/sessions/{summary,options,rows,active-filters} Java contract tests.
"""

from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
HELPER_DIR = REPO_ROOT / 'scripts/qa/ui'
if str(HELPER_DIR) not in sys.path:
    sys.path.insert(0, str(HELPER_DIR))

from _api_first_checklib import JS, TEMPLATES, has_all, has_none, read, run  # noqa: E402


# 加载待检查的 HTML 内容。
def load_html(html_path: str | None, url: str | None) -> tuple[str, str]:
    """参数：
        html_path: 本地 HTML 文件路径。
        url: 待请求的页面 URL。

    返回：
        HTML 内容和来源描述。
    """
    if url:
        try:
            with urllib.request.urlopen(url, timeout=10) as response:
                return response.read().decode('utf-8', errors='replace'), f'url:{url}'
        except (OSError, TimeoutError, urllib.error.URLError) as exc:
            return '', f'url-load-failed:{exc}'
    if html_path:
        path = Path(html_path)
        return read(path), f'file:{path}'
    path = TEMPLATES / 'sessions.html'
    return read(path), f'default:{path.relative_to(REPO_ROOT)}'


# 运行 Sessions 列表逻辑契约检查。
def main() -> int:
    """返回：
        进程退出码。
    """
    parser = argparse.ArgumentParser(description='Sessions list API-first logic contract smoke')
    parser.add_argument('--html')
    parser.add_argument('--url')
    args = parser.parse_args()

    html, source = load_html(args.html, args.url)
    js = read(JS / 'sessions-list.js')
    checks = [
        ('input HTML loaded', lambda: (bool(html), source if html else f'no content from {source}')),
        (
            'shell declares split resource APIs',
            lambda: has_all(html, ['/api/sessions/summary', '/api/sessions/options', '/api/sessions/rows', '/api/sessions/active-filters']),
        ),
        (
            'search/filter controls match API contract',
            lambda: has_all(html, ['name="q"', 'Search title, project, agent, model, session id', 'name="agent"', 'name="model"', 'name="project"', 'name="status"']),
        ),
        (
            'sort and pagination controls are shell-only interactions',
            lambda: has_all(html, ['data-action="sort"', 'data-action="prev-page"', 'data-action="next-page"', 'data-action="page-input"', 'data-action="page-size"']),
        ),
        (
            'footer/count is API hydration tolerant',
            lambda: has_all(html, ['Loading matching sessions', 'Filters loaded from /api/sessions/active-filters']),
        ),
        (
            'template does not carry SSR row truth',
            lambda: has_none(html, ['{% for session', 'sessions_' + 'aggregate', 'data-action="row"', 'tokenbar-seg fresh']),
        ),
        (
            'JS fetches JSON resources and renders rows',
            lambda: has_all(js, ['fetch(apiUrl(\'/api/sessions/summary\'', 'fetch(apiUrl(\'/api/sessions/options\'', 'fetch(apiUrl(\'/api/sessions/rows\'', 'renderRows', 'renderPagination']),
        ),
        ('JS does not send legacy HTML fragment header', lambda: has_none(js, ['X-Requested-With'])),
    ]
    return run('sessions list API-first logic contract', checks)


if __name__ == '__main__':
    raise SystemExit(main())
