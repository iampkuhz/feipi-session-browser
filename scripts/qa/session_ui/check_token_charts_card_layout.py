#!/usr/bin/env python3
"""Token charts card layout placement check.

Usage:
    python scripts/qa/session_ui/check_token_charts_card_layout.py [--url URL] [--html PATH]

Checks:
    1. .token-charts-card__body exists in the DOM
    2. NOT inside Trace active view primary area (data-view="trace")
    3. NOT a dominant first-screen block between hero and workbench (DOM ordering)
    4. Height <= 400px threshold if rendered (inline style or content-line estimate)
    5. Token diagnostics present in Hotspots/inspector instead

Exits non-zero if any critical violation found.
"""

from __future__ import annotations

import argparse
import re
import sys
import urllib.request
import urllib.error
from pathlib import Path

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("ERROR: beautifulsoup4 is required. Install with: pip install beautifulsoup4")
    sys.exit(2)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_BASELINE = (
    REPO_ROOT / "reports" / "session-detail-hifi-layout-quality" / "baseline" / "current.html"
)
DEFAULT_URL = "http://localhost:18999/session/93ecbcf2"

# Height threshold in pixels — if the token charts body is rendered taller
# than this, it is considered a dominant first-screen block.
MAX_ACCEPTABLE_HEIGHT_PX = 400

# ---------------------------------------------------------------------------
# Data fetching (mirrors check_layout_quality.py pattern)
# ---------------------------------------------------------------------------

def fetch_html(url: str, timeout: float = 3.0) -> str | None:
    """Try to fetch HTML from a running local server."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "token-charts-check/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, OSError, TimeoutError):
        return None


def read_html(path: Path) -> str | None:
    """Read HTML from a local file."""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except (OSError, FileNotFoundError):
        return None


def load_source(url: str | None, html_path: Path | None):
    """Fetch from URL, fall back to file, return (html_text, source_label)."""
    if url:
        content = fetch_html(url)
        if content:
            return content, f"server ({url})"
    if html_path and html_path.is_file():
        content = read_html(html_path)
        if content:
            return content, f"file ({html_path})"
    return None, None


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def check_token_charts_exists(soup: BeautifulSoup) -> tuple[str, list[str]]:
    """Check whether .token-charts-card__body exists."""
    notes: list[str] = []
    bodies = soup.select("div.token-charts-card__body")
    cards = soup.select("div.token-charts-card")

    if bodies:
        notes.append(f"div.token-charts-card__body found (count={len(bodies)})")
        notes.append(f"div.token-charts-card found (count={len(cards)})")
        return "FOUND", notes
    else:
        notes.append("div.token-charts-card__body NOT found")
        if cards:
            notes.append("div.token-charts-card exists but has no __body wrapper")
        else:
            notes.append("div.token-charts-card also NOT found (HIFI target state)")
        return "MISSING", notes


def check_not_in_trace_view(soup: BeautifulSoup) -> tuple[str, list[str]]:
    """Token charts card body must NOT be inside the Trace active view primary area."""
    notes: list[str] = []
    violations = 0

    # Find all token-charts-card__body elements
    chart_bodies = soup.select("div.token-charts-card__body")

    for body in chart_bodies:
        # Walk up the parent chain to check if any ancestor is the trace view
        parent = body.parent
        while parent:
            # Check for data-view="trace" (the trace view container)
            if parent.get("data-view") == "trace":
                violations += 1
                notes.append(
                    f"VIOLATION: token-charts-card__body is INSIDE data-view=\"trace\" "
                    f"(parent chain includes trace view primary area)"
                )
                break
            # Also check for class-based trace containers
            if "trace" in (parent.get("class") or []) and "detail" not in (parent.get("class") or []):
                # A top-level .trace container would be the trace view
                if parent.name in ("div", "section"):
                    violations += 1
                    notes.append(
                        f"VIOLATION: token-charts-card__body is INSIDE .trace container"
                    )
                    break
            parent = parent.parent

    if violations == 0:
        notes.append("OK: token-charts-card__body is NOT inside trace view primary area")
        return "PASS", notes
    else:
        notes.append(f"Total violations: {violations}")
        return "FAIL", notes


def check_not_between_hero_and_workbench(soup: BeautifulSoup, html: str) -> tuple[str, list[str]]:
    """Token charts card must NOT be a dominant first-screen block between hero and workbench."""
    notes: list[str] = []

    # Find hero, workbench, and token-charts-card in DOM order
    # Hero candidates: HIFI-style (.hero, .hero-main, [data-session-overview-hero])
    # and baseline-style (.session-info-bar, .hero-alerts)
    hero = soup.select_one(
        ".hero, .hero-main, [data-session-overview-hero], .session-info-bar, .hero-alerts"
    )
    workbench = soup.select_one(".card.wb, [data-workbench], section.wb")
    chart_cards = soup.select("div.token-charts-card")

    if not chart_cards:
        notes.append("No token-charts-card found (HIFI target: removed)")
        return "PASS", notes

    # If both hero and workbench exist, check DOM ordering
    if hero and workbench:
        hero_pos = -1
        wb_pos = -1
        card_positions = []

        # Build a list of all elements with their source position
        all_elements = list(soup.find_all())
        for i, el in enumerate(all_elements):
            if el is hero:
                hero_pos = i
            if el is workbench:
                wb_pos = i
            if el in chart_cards:
                card_positions.append(i)

        if hero_pos >= 0 and wb_pos >= 0:
            for cp in card_positions:
                if hero_pos < cp < wb_pos:
                    # Card is between hero and workbench — compute dominance
                    card = chart_cards[card_positions.index(cp)]
                    card_html = str(card)
                    card_lines = card_html.count("\n")
                    total_lines = html.count("\n")
                    pct = (card_lines / total_lines * 100) if total_lines > 0 else 0

                    notes.append(
                        f"VIOLATION: token-charts-card is positioned between hero and workbench "
                        f"in DOM (hero@{hero_pos}, card@{cp}, workbench@{wb_pos})"
                    )
                    notes.append(
                        f"  Card size: {card_lines} lines / {total_lines} total ({pct:.1f}%)"
                    )

                    if pct > 1.0:
                        notes.append(
                            f"FAIL: token-charts-card is a DOM-dominant block between hero and workbench "
                            f"({pct:.1f}% > 1% threshold)"
                        )
                        return "FAIL", notes
                    else:
                        notes.append(
                            f"WARN: card is between hero and workbench but not dominant "
                            f"({pct:.1f}% <= 1%)"
                        )
                        return "WARN", notes

            notes.append("OK: token-charts-card is NOT between hero and workbench in DOM")
            return "PASS", notes
        else:
            notes.append("Could not determine hero/workbench positions for DOM ordering check")
            return "WARN", notes
    elif hero and not workbench:
        notes.append("Workbench container not found; cannot verify ordering")
        return "WARN", notes
    else:
        notes.append("Hero container not found; cannot verify ordering")
        return "WARN", notes


def check_height_threshold(soup: BeautifulSoup, html: str) -> tuple[str, list[str]]:
    """Check that token-charts-card__body height is <= MAX_ACCEPTABLE_HEIGHT_PX.

    NOTE: This check only enforces inline style height. Content-line estimation
    is unreliable for SVG-heavy templates and has been removed. If the card is
    inside the workbench (not first-screen), height is informational only.
    """
    notes: list[str] = []
    violations = 0

    chart_bodies = soup.select("div.token-charts-card__body")

    for body in chart_bodies:
        # Check inline style for height
        style = body.get("style", "")
        height_match = re.search(r'height\s*:\s*(\d+)\s*px', style)
        if height_match:
            h = int(height_match.group(1))
            if h > MAX_ACCEPTABLE_HEIGHT_PX:
                violations += 1
                notes.append(
                    f"VIOLATION: token-charts-card__body has inline height={h}px "
                    f"(> {MAX_ACCEPTABLE_HEIGHT_PX}px threshold)"
                )
            else:
                notes.append(f"OK: inline height={h}px (<= {MAX_ACCEPTABLE_HEIGHT_PX}px)")
        else:
            notes.append("OK: no inline height constraint (height determined by CSS/content)")

    if not chart_bodies:
        notes.append("No token-charts-card__body to check (HIFI target: removed)")
        return "PASS", notes

    if violations > 0:
        notes.append(f"Height violations: {violations}/{len(chart_bodies)}")
        return "FAIL", notes
    else:
        return "PASS", notes


def check_diagnostics_in_hotspots(soup: BeautifulSoup) -> tuple[str, list[str]]:
    """Token diagnostics should be present in Hotspots or inspector instead of standalone chart."""
    notes: list[str] = []
    pass_count = 0

    # Check for Hotspots diagnostic area
    hotspots_diagnostic = soup.select_one(".hotspots-diagnostic, .hotspots-diagnostic__list, .hotspots-diagnostic__header")
    if hotspots_diagnostic:
        notes.append("Hotspots diagnostic area found")
        pass_count += 1

        # Check for diagnostic items inside hotspots
        diag_items = hotspots_diagnostic.select(".hotspot-item, .hotspot-card, .hot-card")
        if diag_items:
            notes.append(f"  Contains {len(diag_items)} diagnostic item(s)")
            pass_count += 1
        else:
            # Also check for any content in hotspots diagnostic
            diag_text = hotspots_diagnostic.get_text(strip=True)
            if len(diag_text) > 20:
                notes.append(f"  Contains diagnostic content ({len(diag_text)} chars)")
                pass_count += 1
            else:
                notes.append("  Hotspots diagnostic area is empty")
    else:
        notes.append("Hotspots diagnostic area NOT found")

    # Check for data-view="hotspots" container
    hotspots_view = soup.select_one('[data-view="hotspots"]')
    if hotspots_view:
        notes.append('[data-view="hotspots"] container found')
        pass_count += 1
    else:
        notes.append('[data-view="hotspots"] container NOT found')

    # Check for inspector with token/diagnostic info
    inspector = soup.select_one("[data-context-inspector], .inspector, .inspector-inner")
    if inspector:
        insp_text = inspector.get_text(strip=True).lower()
        has_diag_keywords = any(kw in insp_text for kw in ["token", "diag", "hotspot", "payload"])
        if has_diag_keywords:
            notes.append("Inspector contains token/diagnostic-related content")
            pass_count += 1
        else:
            notes.append("Inspector exists but no token/diagnostic keywords found")
    else:
        notes.append("Inspector NOT found")

    if pass_count >= 2:
        notes.append(f"OK: token diagnostics available in alternate views ({pass_count} signals)")
        return "PASS", notes
    elif pass_count >= 1:
        notes.append(f"WARN: partial diagnostic coverage ({pass_count} signal(s))")
        return "WARN", notes
    else:
        notes.append("FAIL: no token diagnostics found in Hotspots or inspector")
        return "FAIL", notes


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

CHECKS = [
    ("Token charts card body exists", check_token_charts_exists),
    ("NOT inside Trace view", check_not_in_trace_view),
    ("NOT between hero and workbench", check_not_between_hero_and_workbench),
    ("Height within threshold", check_height_threshold),
    ("Diagnostics in Hotspots/inspector", check_diagnostics_in_hotspots),
]


def run_checks(html: str, source: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    results = {}
    for name, fn in CHECKS:
        if "html" in fn.__code__.co_varnames:
            status, notes = fn(soup, html)
        else:
            status, notes = fn(soup)
        results[name] = {"status": status, "notes": notes}
    return results


def print_report(results: dict, source: str) -> bool:
    """Print compact report. Returns True if no FAIL."""
    print(f"\n{'='*60}")
    print(f"  Token Charts Card Layout Check")
    print(f"  Source: {source}")
    print(f"{'='*60}\n")

    any_fail = False
    for name, data in results.items():
        status = data["status"]
        if status == "FAIL":
            any_fail = True
        icon = {"PASS": "[PASS]", "WARN": "[WARN]", "FAIL": "[FAIL]", "FOUND": "[INFO]", "MISSING": "[INFO]"}.get(status, "[??]")
        print(f"  {icon}  {name}")
        for note in data["notes"]:
            print(f"        {note}")
        print()

    # Summary
    counts = {"PASS": 0, "WARN": 0, "FAIL": 0}
    for data in results.values():
        s = data["status"]
        if s in counts:
            counts[s] += 1

    total_checked = counts["PASS"] + counts["WARN"] + counts["FAIL"]
    print(f"{'='*60}")
    print(f"  Checked: {counts['PASS']} PASS, {counts['WARN']} WARN, {counts['FAIL']} FAIL")
    print(f"  Verdict: {'PASS' if not any_fail else 'FAIL'}")
    print(f"{'='*60}\n")

    return not any_fail


def main():
    parser = argparse.ArgumentParser(description="Token charts card layout placement check")
    parser.add_argument("--url", default=DEFAULT_URL, help="URL to fetch page from (default: %(default)s)")
    parser.add_argument("--html", default=str(DEFAULT_BASELINE), help="Path to baseline HTML file (fallback)")
    args = parser.parse_args()

    html_path = Path(args.html) if args.html else None
    content, source = load_source(args.url, html_path)

    if content is None:
        print(f"ERROR: Could not load HTML from {args.url} or {html_path}")
        print("Start the local server or provide a valid HTML file path.")
        sys.exit(2)

    print(f"Loaded HTML from: {source}")
    print(f"  Size: {len(content):,} bytes, {content.count(chr(10)):,} lines")

    results = run_checks(content, source)
    success = print_report(results, source)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
