#!/usr/bin/env python3
"""Capture a live session-detail DOM and selector inventory baseline.

This QA utility is run manually against the local fixture server on port 18999,
or the host/port supplied through SESSION_BROWSER_LOCAL_HOST and
SESSION_BROWSER_LOCAL_PORT. It reads the dashboard, fetches the first session
link, writes HTML plus selector inventory under reports/, and exits non-zero
when the server or session page cannot be reached.
"""

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
    """Record target selector presence while parsing session-detail HTML.

    The baseline capture command creates one parser per fetched page. It tracks
    selector presence plus observed classes, ids, and tag names in memory only;
    generated JSON is written later by main. Its initializer prepares selector
    inventory state for one captured page.
    """

    def __init__(self) -> None:
        """Initialize selector inventory state for one captured page."""  # noqa: RUF100  # noqa: DOC301
        super().__init__()
        self.found = dict.fromkeys(TARGET_SELECTORS, False)
        self._classes_seen: set[str] = set()
        self._ids_seen: set[str] = set()
        self._tags_seen: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Update selector inventory from a start tag emitted by HTMLParser.

        Args:
            tag: Raw tag name from the fetched session-detail HTML.
            attrs: Attribute pairs for the tag; missing values are treated as empty.
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


def find_session_url() -> str | None:
    """Find the first session-detail URL from the live dashboard.

    Returns:
        Absolute session URL when the dashboard contains a session link; None when
        the server is unreachable or no session link is present.
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


def fetch_session_html(session_url: str) -> str | None:
    """Fetch session-detail HTML for baseline capture.

    Args:
        session_url: Absolute session URL discovered from the local dashboard.

    Returns:
        Decoded HTML when the request succeeds; None when the page cannot be fetched.
    """
    try:
        req = urllib.request.Request(session_url)
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode('utf-8', errors='replace')
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f'ERROR: Cannot fetch {session_url}: {exc}')
        return None


def inventory_selectors(html: str) -> dict[str, bool]:
    """Parse session-detail HTML and report target selector presence.

    Args:
        html: HTML fetched from the live session-detail page.

    Returns:
        Mapping from each target selector to a boolean presence flag.
    """
    parser = SelectorInventoryParser()
    parser.feed(html)
    return parser.found


def main() -> int:
    """Run the baseline capture CLI and write report artifacts.

    The QA maintainer runs this script after starting a local server. It writes
    current.html and selector-inventory.json under reports/, prints a summary,
    and returns 1 for missing server/session inputs.

    Returns:
        Process exit code 0 after successful artifact generation, otherwise 1.
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
