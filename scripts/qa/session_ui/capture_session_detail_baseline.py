#!/usr/bin/env python3
"""提供 capture session detail baseline 脚本能力。"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[3]
REPORT_DIR = PROJECT_DIR / 'reports' / 'session-detail-hifi-layout-quality' / 'baseline'
LOCAL_HOST = os.environ.get('SESSION_BROWSER_LOCAL_HOST', '127.0.0.1')
LOCAL_PORT = int(os.environ.get('SESSION_BROWSER_LOCAL_PORT', '18999'))
BASE_URL = f'http://{LOCAL_HOST}:{LOCAL_PORT}'

TARGET_SELECTORS = [
    '.token-charts-card__body',
    '.token-charts-card__body-grid',
    '.round-summary-table',
    '.tabs',
    '#profile',
    '#timeline',
    'content-modal',
    'template',
]


class SelectorInventoryParser(HTMLParser):
    """表示 SelectorInventoryParser。
    """

    # 维护init。
    def __init__(self) -> None:
        super().__init__()
        self.found = dict.fromkeys(TARGET_SELECTORS, False)
        self._classes_seen: set[str] = set()
        self._ids_seen: set[str] = set()
        self._tags_seen: set[str] = set()

    # 记录 HTML 开始标签。
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """参数：
            tag: tag 参数。
            attrs: attrs 参数。
        """
        attrs_dict = {key: value or '' for key, value in attrs}
        tag_name = tag.lower()
        self._tags_seen.add(tag_name)

        if tag_name == 'template':
            self.found['template'] = True

        classes = set()
        for cls in attrs_dict.get('class', '').split():
            self._classes_seen.add(cls)
            classes.add(cls)

        if 'token-charts-card__body' in classes:
            self.found['.token-charts-card__body'] = True
        if 'token-charts-card__body-grid' in classes:
            self.found['.token-charts-card__body-grid'] = True
        if 'round-summary-table' in classes:
            self.found['.round-summary-table'] = True
        if 'tabs' in classes:
            self.found['.tabs'] = True

        tag_id = attrs_dict.get('id', '')
        if tag_id:
            self._ids_seen.add(tag_id)
            if tag_id == 'profile':
                self.found['#profile'] = True
            if tag_id == 'timeline':
                self.found['#timeline'] = True

        if tag_name == 'content-modal':
            self.found['content-modal'] = True


# 查找session url。
def find_session_url() -> str | None:
    """返回：
        find session url 字符串。
    """
    try:
        req = urllib.request.Request(f'{BASE_URL}/dashboard')
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode('utf-8', errors='replace')
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f'ERROR: Cannot reach dashboard at {BASE_URL}/dashboard: {exc}')
        return None

    match = re.search(r'href="(/sessions/[^"]+)"', html)
    if match:
        return f'{BASE_URL}{match.group(1)}'
    return None


# 维护获取 session HTML。
def fetch_session_html(session_url: str) -> str | None:
    """参数：
        session_url: session url 参数。

    返回：
        fetch session HTML 字符串。
    """
    try:
        req = urllib.request.Request(session_url)
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode('utf-8', errors='replace')
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f'ERROR: Cannot fetch {session_url}: {exc}')
        return None


# 维护清单 selectors。
def inventory_selectors(html: str) -> dict[str, bool]:
    """参数：
        html: 待检查的 HTML 文本。

    返回：
        映射从each target selector到a 布尔值 presence flag。
    """
    parser = SelectorInventoryParser()
    parser.feed(html)
    return parser.found


# 解析命令行参数并运行脚本入口。
def main() -> int:
    """返回：
        进程退出码。

    说明：
        和 返回 1用于缺失 server/session inputs。
    """
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    print(f'Connecting to session browser at {BASE_URL} ...')
    session_url = find_session_url()
    if not session_url:
        print('ERROR: No session found on dashboard. Cannot proceed.')
        return 1
    print(f'Found session: {session_url}')

    print('Fetching session detail page HTML ...')
    html = fetch_session_html(session_url)
    if not html:
        print('ERROR: Failed to fetch session HTML.')
        return 1
    print(f'  Fetched {len(html):,} bytes')

    html_path = REPORT_DIR / 'current.html'
    html_path.write_text(html, encoding='utf-8')
    print(f'  Saved: {html_path}')

    print('Inventorying selectors ...')
    inventory = inventory_selectors(html)
    report = {
        'source_url': session_url,
        'html_size_bytes': len(html),
        'selectors': inventory,
        'summary': {
            'present': [key for key, present in inventory.items() if present],
            'missing': [key for key, present in inventory.items() if not present],
        },
    }

    inventory_path = REPORT_DIR / 'selector-inventory.json'
    inventory_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'  Saved: {inventory_path}')

    print('\n=== Selector Inventory ===')
    for selector, present in inventory.items():
        status = 'FOUND' if present else 'MISSING'
        print(f'  [{status}] {selector}')
    print(f'\n  Present: {len(report["summary"]["present"])}/{len(inventory)}')
    print(f'  Missing: {len(report["summary"]["missing"])}/{len(inventory)}')

    if report['summary']['missing']:
        print('\n  Missing selectors:')
        for selector in report['summary']['missing']:
            print(f'    - {selector}')

    print('\nBaseline capture complete.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
