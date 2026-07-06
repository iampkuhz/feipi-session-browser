#!/usr/bin/env python3
"""API-first layout quality smoke for Session Detail static shell."""

from __future__ import annotations

import argparse
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
HELPER_DIR = REPO_ROOT / 'scripts/qa/ui'
if str(HELPER_DIR) not in sys.path:
    sys.path.insert(0, str(HELPER_DIR))

from _api_first_checklib import CSS, JS, TEMPLATES, has_all, has_none, read, run  # noqa: E402


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
            req = urllib.request.Request(url, headers={'User-Agent': 'layout-quality-check/3.0'})
            with urllib.request.urlopen(req, timeout=10) as response:
                return response.read().decode('utf-8', errors='replace'), f'url:{url}'
        except (OSError, TimeoutError, urllib.error.URLError) as exc:
            return '', f'url-load-failed:{exc}'
    if html_path:
        path = Path(html_path)
        return read(path), f'file:{path}'
    path = TEMPLATES / 'session.html'
    return read(path), f'default:{path.relative_to(REPO_ROOT)}'


# 检查 HTML 内联宽度是否存在明显异常。
def no_wide_inline_styles(html: str) -> tuple[bool, str]:
    """参数：
        html: 待检查的 HTML 内容。

    返回：
        检查是否通过和说明文本。
    """
    widths = [int(value) for value in re.findall(r'(?:min-)?width\s*:\s*(\d+)px', html)]
    bad = [value for value in widths if value > 2000]
    return not bad, 'clean' if not bad else f'wide inline widths: {bad[:5]}'


# 运行 Session Detail 布局质量检查。
def main() -> int:
    """返回：
        进程退出码。
    """
    parser = argparse.ArgumentParser(description='Session Detail API-first layout quality smoke')
    parser.add_argument('--url')
    parser.add_argument('--html')
    args = parser.parse_args()

    html, source = load_html(args.html, args.url)
    css_parts = ''.join(read(path) for path in sorted((CSS / 'session-detail').glob('*.css')))
    js = read(JS / 'session-detail/init.js') + read(JS / 'session-detail/lazy_rounds.js')
    checks = [
        ('input HTML loaded', lambda: (bool(html), source if html else f'no content from {source}')),
        (
            'hero shell is present',
            lambda: has_all(html, ['class="sd-hero"', 'data-session-overview-hero', 'data-session-hero', 'data-session-metrics-shell']),
        ),
        (
            'trace panel shell is present',
            lambda: has_all(html, ['data-trace-panel', 'data-action="status-all"', 'data-action="status-failed"', 'data-action="status-low-cache"', 'data-action="toggle-all"', 'data-trace-list']),
        ),
        (
            'legacy workbench/tabs/token chart artifacts absent',
            lambda: has_none(html, ['data-workbench', 'data-switch="calls"', 'data-switch="hotspots"', 'token-charts-card', 'tab-nav', 'wb-viewbar']),
        ),
        ('no obvious wide inline overflow', lambda: no_wide_inline_styles(html)),
        (
            'CSS defines current layout selectors',
            lambda: has_all(css_parts, ['.sd-hero', '.sd-tabs', '.trace-table', '.round-row', '.sd-payload-modal']),
        ),
        ('JS hydrates shell from APIs', lambda: has_all(js, ['/meta', '/metrics', '/diagnostics', '/rounds', '/payloads'])),
    ]
    return run('session detail API-first layout quality checks', checks)


if __name__ == '__main__':
    raise SystemExit(main())
