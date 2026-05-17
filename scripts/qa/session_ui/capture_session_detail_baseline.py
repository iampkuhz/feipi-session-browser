#!/usr/bin/env python3
"""Capture current session detail page DOM and selector inventory baseline.

Fetches the live session detail page, saves HTML, and inventories key selectors.
Uses the already-running server on port 18999 (or SESSION_BROWSER_LOCAL_PORT).
"""

import json
import os
import sys
import urllib.request
import urllib.error
from html.parser import HTMLParser

# --- Configuration ---
PROJECT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
REPORT_DIR = os.path.join(PROJECT_DIR, "reports", "session-detail-hifi-layout-quality", "baseline")
LOCAL_HOST = os.environ.get("SESSION_BROWSER_LOCAL_HOST", "127.0.0.1")
LOCAL_PORT = int(os.environ.get("SESSION_BROWSER_LOCAL_PORT", "18999"))
BASE_URL = f"http://{LOCAL_HOST}:{LOCAL_PORT}"

# Selectors to inventory
TARGET_SELECTORS = [
    ".token-charts-card__body",
    ".token-charts-card__body-grid",
    ".round-summary-table",
    ".tabs",
    "#profile",
    "#timeline",
    "content-modal",
    "template",
]


class SelectorInventoryParser(HTMLParser):
    """Walk the HTML and record which target selectors are present."""

    def __init__(self):
        super().__init__()
        self.found = {s: False for s in TARGET_SELECTORS}
        # Track all class names seen
        self._classes_seen = set()
        # Track all IDs seen
        self._ids_seen = set()
        # Track all tag names seen
        self._tags_seen = set()

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        self._tags_seen.add(tag.lower())

        # Check tag name selectors
        if tag.lower() == "template":
            self.found["template"] = True

        # Check class selectors
        classes = set()
        for cls in (attrs_dict.get("class") or "").split():
            self._classes_seen.add(cls)
            classes.add(cls)

        if "token-charts-card__body" in classes:
            self.found[".token-charts-card__body"] = True
        if "token-charts-card__body-grid" in classes:
            self.found[".token-charts-card__body-grid"] = True
        if "round-summary-table" in classes:
            self.found[".round-summary-table"] = True
        if "tabs" in classes:
            self.found[".tabs"] = True

        # Check ID selectors
        tag_id = attrs_dict.get("id", "")
        if tag_id:
            self._ids_seen.add(tag_id)
            if tag_id == "profile":
                self.found["#profile"] = True
            if tag_id == "timeline":
                self.found["#timeline"] = True

        # Check custom element: <content-modal>
        if tag.lower() == "content-modal":
            self.found["content-modal"] = True


def find_session_url():
    """Find the first session detail URL from the dashboard."""
    try:
        req = urllib.request.Request(f"{BASE_URL}/dashboard")
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"ERROR: Cannot reach dashboard at {BASE_URL}/dashboard: {e}")
        return None

    # Extract first session link
    import re
    match = re.search(r'href="(/sessions/[^"]+)"', html)
    if match:
        return f"{BASE_URL}{match.group(1)}"
    return None


def fetch_session_html(session_url):
    """Fetch the session detail page HTML."""
    try:
        req = urllib.request.Request(session_url)
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"ERROR: Cannot fetch {session_url}: {e}")
        return None


def inventory_selectors(html):
    """Parse HTML and return selector presence dict."""
    parser = SelectorInventoryParser()
    parser.feed(html)
    return parser.found


def main():
    os.makedirs(REPORT_DIR, exist_ok=True)

    # Step 1: Find a session to capture
    print(f"Connecting to session browser at {BASE_URL} ...")
    session_url = find_session_url()
    if not session_url:
        print("ERROR: No session found on dashboard. Cannot proceed.")
        sys.exit(1)
    print(f"Found session: {session_url}")

    # Step 2: Fetch session detail HTML
    print("Fetching session detail page HTML ...")
    html = fetch_session_html(session_url)
    if not html:
        print("ERROR: Failed to fetch session HTML.")
        sys.exit(1)
    print(f"  Fetched {len(html):,} bytes")

    # Step 3: Save baseline HTML
    html_path = os.path.join(REPORT_DIR, "current.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  Saved: {html_path}")

    # Step 4: Generate selector inventory
    print("Inventorying selectors ...")
    inventory = inventory_selectors(html)

    # Add metadata
    report = {
        "source_url": session_url,
        "html_size_bytes": len(html),
        "selectors": inventory,
        "summary": {
            "present": [k for k, v in inventory.items() if v],
            "missing": [k for k, v in inventory.items() if not v],
        },
    }

    inventory_path = os.path.join(REPORT_DIR, "selector-inventory.json")
    with open(inventory_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"  Saved: {inventory_path}")

    # Step 5: Print summary
    print("\n=== Selector Inventory ===")
    for sel, present in inventory.items():
        status = "FOUND" if present else "MISSING"
        print(f"  [{status}] {sel}")
    print(f"\n  Present: {len(report['summary']['present'])}/{len(inventory)}")
    print(f"  Missing: {len(report['summary']['missing'])}/{len(inventory)}")

    if report["summary"]["missing"]:
        print("\n  Missing selectors:")
        for s in report["summary"]["missing"]:
            print(f"    - {s}")

    print("\nBaseline capture complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
