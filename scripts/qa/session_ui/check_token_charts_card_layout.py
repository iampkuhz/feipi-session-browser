#!/usr/bin/env python3
"""API-first token metrics placement check for Session Detail.

The current page no longer exposes per-round business token data in static HTML.
This checker verifies the shell points to typed APIs and that dynamic tokenbar
rendering lives in JavaScript instead of requiring legacy inline round token attributes.
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

from _api_first_checklib import JS, TEMPLATES, LEGACY_ROUND_TOKEN_ATTR, has_all, has_none, read, run  # noqa: E402


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
            req = urllib.request.Request(url, headers={'User-Agent': 'token-metrics-check/3.0'})
            with urllib.request.urlopen(req, timeout=10) as response:
                return response.read().decode('utf-8', errors='replace'), f'url:{url}'
        except (OSError, TimeoutError, urllib.error.URLError) as exc:
            return '', f'url-load-failed:{exc}'
    if html_path:
        path = Path(html_path)
        return read(path), f'file:{path}'
    path = TEMPLATES / 'session.html'
    return read(path), f'default:{path.relative_to(REPO_ROOT)}'


# 运行 token 指标卡片布局检查。
def main() -> int:
    """返回：
        进程退出码。
    """
    parser = argparse.ArgumentParser(description='Session Detail token API-first shell check')
    parser.add_argument('--url')
    parser.add_argument('--html')
    args = parser.parse_args()

    html, source = load_html(args.html, args.url)
    init_js = read(JS / 'session-detail/init.js')
    lazy_js = read(JS / 'session-detail/lazy_rounds.js')
    checks = [
        ('input HTML loaded', lambda: (bool(html), source if html else f'no content from {source}')),
        ('legacy token charts card removed', lambda: has_none(html, ['token-charts-card', 'token-charts-card__body'])),
        (
            'hero token metrics are API shell values',
            lambda: has_all(html, ['data-session-metrics-shell', 'Total Tokens', 'Fresh', 'Cache Read', 'Cache Write', 'Output', 'Loaded from /api/sessions/{agent}/{sessionId}/metrics']),
        ),
        (
            'trace table declares rounds API instead of legacy inline round-token data',
            lambda: has_all(html, ['data-trace-list', 'Trace rows are loaded from /api/sessions/{agent}/{sessionId}/rounds.']),
        ),
        ('static shell does not require old inline round-token data', lambda: has_none(html, [LEGACY_ROUND_TOKEN_ATTR, '.mixbar', '.mixval'])),
        (
            'JS hydrates metrics/round tokenbars from APIs',
            lambda: has_all(init_js + lazy_js, ['/metrics', '/rounds', 'tokenbar-seg fresh', 'tokenbar-seg read', 'tokenbar-seg write', 'tokenbar-seg out']),
        ),
    ]
    return run('session detail token API-first layout checks', checks)


if __name__ == '__main__':
    raise SystemExit(main())
