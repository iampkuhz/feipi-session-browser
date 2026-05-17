#!/usr/bin/env python3
"""Layout quality scoring for the session detail HIFI layout.

Usage:
    python scripts/qa/session_ui/check_layout_quality.py [--url URL] [--html PATH]

Checks:
    1. Hero: HIFI data selectors, anomaly banner placeholder
    2. Workbench: container exists above the fold, view switch buttons
    3. Token chart: NOT a dominant block between hero and workbench
    4. Legacy tabs: old top-level tabs are not primary layout
    5. Inspector: contextual inspector exists
    6. Overflow: no obvious horizontal overflow markers
    7. Button roles: buttons are not duplicated across zones

Exits non-zero on any FAIL.
"""

from __future__ import annotations

import argparse
import os
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

# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

def fetch_html(url: str, timeout: float = 3.0) -> str | None:
    """Try to fetch HTML from a running local server."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "layout-quality-check/1.0"})
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

def check_hero(soup: BeautifulSoup, html: str) -> tuple[str, list[str]]:
    """Hero: HIFI data selectors exist, anomaly banner placeholder."""
    notes: list[str] = []
    pass_count = 0

    # Check for HIFI hero data attribute
    hero = soup.select_one("[data-session-overview-hero]")
    if hero:
        notes.append("[data-session-overview-hero] found")
        pass_count += 1
    else:
        notes.append("[data-session-overview-hero] MISSING")

    # Fallback: check for hero class-based element or session header bar
    hero_class = soup.select_one(".hero, .hero-main, .session-info-bar, .session-header")
    if hero_class:
        notes.append(f"hero/hero-equivalent element found (.{hero_class.get('class', ['?'])[0]})")
        pass_count += 1
    else:
        notes.append("hero/hero-equivalent element MISSING")

    # Anomaly banner placeholder
    anomaly = soup.select_one(".anomaly-banner, .anomaly-banner__icon, [data-anomaly]")
    if anomaly:
        notes.append("anomaly banner placeholder found")
        pass_count += 1
    else:
        notes.append("anomaly banner placeholder MISSING")

    # Hero alerts section
    alerts = soup.select_one(".hero-alerts")
    if alerts:
        notes.append("hero-alerts section found")
        pass_count += 1
    else:
        notes.append("hero-alerts section MISSING")

    status = "PASS" if pass_count >= 3 else ("WARN" if pass_count >= 2 else "FAIL")
    return status, notes


def check_workbench(soup: BeautifulSoup, html: str) -> tuple[str, list[str]]:
    """Workbench: container exists above the fold, view switch buttons."""
    notes: list[str] = []
    pass_count = 0

    # HIFI data attribute
    wb = soup.select_one("[data-workbench]")
    if wb:
        notes.append("[data-workbench] found")
        pass_count += 1
    else:
        notes.append("[data-workbench] MISSING")

    # Fallback: class-based workbench
    wb_class = soup.select_one(".card.wb, .wb-head, [class*='workbench']")
    if wb_class:
        notes.append("workbench container found (.card.wb / .wb-head)")
        pass_count += 1
    else:
        notes.append("workbench container MISSING")

    # View switch buttons
    view_switch = soup.select_one(".view-switch")
    switch_btns = soup.select("[data-switch]")
    if view_switch or len(switch_btns) >= 2:
        notes.append(f"view switch found (data-switch count={len(switch_btns)})")
        pass_count += 1
    else:
        notes.append("view switch buttons MISSING")

    # wb-viewbar
    viewbar = soup.select_one(".wb-viewbar")
    if viewbar:
        notes.append("wb-viewbar found")
        pass_count += 1
    else:
        notes.append("wb-viewbar MISSING")

    status = "PASS" if pass_count >= 3 else ("WARN" if pass_count >= 2 else "FAIL")
    return status, notes


def check_token_chart(soup: BeautifulSoup, html: str) -> tuple[str, list[str]]:
    """Token chart: token-charts-card__body is NOT a dominant block between hero and workbench."""
    notes: list[str] = []

    # Count token chart body occurrences
    chart_bodies = soup.select("div.token-charts-card__body")
    chart_cards = soup.select(".token-charts-card")

    total_body_lines = 0
    for body in chart_bodies:
        body_html = str(body)
        total_body_lines += body_html.count("\n")

    # Total document lines
    total_lines = html.count("\n")

    # The token chart card should not dominate the space between hero and workbench
    if chart_cards:
        # Check if token-charts-card exists (it does in current baseline)
        notes.append(f"token-charts-card found (count={len(chart_cards)})")
        notes.append(f"token-charts-card__body found (count={len(chart_bodies)})")

        if total_lines > 0:
            pct = (total_body_lines / total_lines) * 100
            notes.append(f"token-charts-card__body lines: {total_body_lines}/{total_lines} ({pct:.1f}%)")

            # If the token chart body takes > 5% of total HTML, it's dominant
            if pct > 5.0:
                notes.append("WARN: token chart block is dominant between hero and workbench")
                return "FAIL", notes
            else:
                notes.append("OK: token chart block is not dominant")
                return "PASS", notes
        else:
            return "WARN", notes
    else:
        notes.append("token-charts-card NOT found (ideal: HIFI removes this block)")
        return "PASS", notes


def check_legacy_tabs(soup: BeautifulSoup, html: str) -> tuple[str, list[str]]:
    """Legacy tabs: old top-level tabs (Profile/Timeline/Hotspots) are not primary layout."""
    notes: list[str] = []

    # Check for old-style top-level tab navigation
    legacy_tabs = soup.select(".tab-nav, .tab-bar, nav[aria-label*='tab']")
    legacy_labels = []

    for tab in legacy_tabs:
        text = tab.get_text(strip=True)
        if any(kw in text.lower() for kw in ["profile", "timeline", "hotspots"]):
            legacy_labels.append(text)

    # Also check for standalone Profile/Timeline/Hotspots tab buttons
    tab_buttons = soup.select("button[data-tab], .tab-item, .nav-tab")
    legacy_tab_buttons = []
    for btn in tab_buttons:
        text = btn.get_text(strip=True).lower()
        if text in ("profile", "timeline", "hotspots"):
            legacy_tab_buttons.append(text)

    if legacy_labels or legacy_tab_buttons:
        notes.append(f"Legacy tab navigation FOUND: {legacy_labels + legacy_tab_buttons}")
        return "FAIL", notes
    else:
        notes.append("No legacy top-level tab navigation found (good)")
        return "PASS", notes


def check_inspector(soup: BeautifulSoup, html: str) -> tuple[str, list[str]]:
    """Inspector: contextual inspector exists."""
    notes: list[str] = []
    pass_count = 0

    # HIFI data attribute
    inspector = soup.select_one("[data-context-inspector]")
    if inspector:
        notes.append("[data-context-inspector] found")
        pass_count += 1
    else:
        notes.append("[data-context-inspector] MISSING")

    # Fallback: class-based inspector
    inspector_class = soup.select_one("aside.inspector, .inspector, .inspector-inner")
    if inspector_class:
        notes.append("inspector element found (class-based)")
        pass_count += 1
    else:
        notes.append("inspector element MISSING")

    # Inspector header/title
    insp_title = soup.select_one(".insp-title, .inspector-inner .insp-title")
    if insp_title:
        notes.append(f"inspector title found: '{insp_title.get_text(strip=True)}'")
        pass_count += 1
    else:
        notes.append("inspector title MISSING")

    status = "PASS" if pass_count >= 2 else ("WARN" if pass_count >= 1 else "FAIL")
    return status, notes


def check_overflow(soup: BeautifulSoup, html: str) -> tuple[str, list[str]]:
    """Overflow: no obvious horizontal overflow markers in DOM/CSS."""
    notes: list[str] = []
    issues = 0

    # Check for very wide inline styles (width > 2000px)
    wide_elements = soup.select('[style*="width"]')
    for el in wide_elements:
        style = el.get("style", "")
        match = re.search(r'width\s*:\s*(\d+)\s*px', style)
        if match and int(match.group(1)) > 2000:
            issues += 1
            notes.append(f"OVERFLOW: element with width={match.group(1)}px exceeds 2000px")

    # Check for min-width that forces wide layouts
    min_width_elements = soup.select('[style*="min-width"]')
    for el in min_width_elements:
        style = el.get("style", "")
        match = re.search(r'min-width\s*:\s*(\d+)\s*px', style)
        if match and int(match.group(1)) > 1800:
            issues += 1
            notes.append(f"OVERFLOW: element with min-width={match.group(1)}px may cause horizontal scroll")

    # Check body min-width in style tags
    style_tags = soup.find_all("style")
    for tag in style_tags:
        text = tag.string or ""
        # Look for body/html min-width > viewport typical
        body_mw = re.findall(r'(?:body|html)\s*\{[^}]*min-width\s*:\s*(\d+)px', text)
        for mw in body_mw:
            if int(mw) > 1400:
                issues += 1
                notes.append(f"OVERFLOW: body min-width={mw}px may cause horizontal scroll on narrow screens")

    # Check for scrollable containers with very large widths
    scrollable = soup.select('[style*="overflow-x"]')
    for el in scrollable:
        style = el.get("style", "")
        if "hidden" not in style and ("scroll" in style or "auto" in style):
            width_match = re.search(r'width\s*:\s*(\d+)\s*px', style)
            if width_match and int(width_match.group(1)) > 2000:
                issues += 1
                notes.append(f"OVERFLOW: scrollable container width={width_match.group(1)}px")

    if issues > 0:
        notes.append(f"Total overflow markers found: {issues}")
        return "FAIL", notes
    else:
        notes.append("No obvious horizontal overflow markers detected")
        return "PASS", notes


def check_button_roles(soup: BeautifulSoup, html: str) -> tuple[str, list[str]]:
    """Button roles: buttons are not duplicated across topbar/hero/workbench."""
    notes: list[str] = []
    duplicates = 0

    # Collect button text/labels from each zone
    def get_button_labels(container):
        if not container:
            return set()
        labels = set()
        for btn in container.find_all("button"):
            text = btn.get_text(strip=True)
            aria = btn.get("aria-label", "").strip()
            title = btn.get("title", "").strip()
            label = text or aria or title
            if label:
                labels.add(label.lower())
        return labels

    topbar = soup.select_one(".topbar")
    hero = soup.select_one(".hero, .hero-main")
    workbench = soup.select_one(".card.wb, .wb-head, [data-workbench]")

    topbar_btns = get_button_labels(topbar)
    hero_btns = get_button_labels(hero)
    wb_btns = get_button_labels(workbench)

    notes.append(f"topbar buttons: {sorted(topbar_btns)}")
    notes.append(f"hero buttons: {sorted(hero_btns)}")
    notes.append(f"workbench buttons: {sorted(wb_btns)}")

    # Check for cross-zone duplicates
    topbar_hero_overlap = topbar_btns & hero_btns
    if topbar_hero_overlap:
        duplicates += len(topbar_hero_overlap)
        notes.append(f"DUPLICATE topbar <-> hero: {sorted(topbar_hero_overlap)}")

    topbar_wb_overlap = topbar_btns & wb_btns
    if topbar_wb_overlap:
        duplicates += len(topbar_wb_overlap)
        notes.append(f"DUPLICATE topbar <-> workbench: {sorted(topbar_wb_overlap)}")

    hero_wb_overlap = hero_btns & wb_btns
    if hero_wb_overlap:
        # Some overlap is expected (e.g., "Jump" / "Inspect" actions)
        functional_overlap = {l for l in hero_wb_overlap if l in ("jump", "inspect", "open selected")}
        non_functional = hero_wb_overlap - functional_overlap
        if non_functional:
            duplicates += len(non_functional)
            notes.append(f"DUPLICATE hero <-> workbench: {sorted(non_functional)}")
        else:
            notes.append(f"hero <-> workbench overlap is functional (expected): {sorted(functional_overlap)}")

    if duplicates > 0:
        notes.append(f"Total button duplicates: {duplicates}")
        return "FAIL", notes
    else:
        notes.append("No button duplication across zones")
        return "PASS", notes


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

CHECKS = [
    ("Hero", check_hero),
    ("Workbench", check_workbench),
    ("Token chart", check_token_chart),
    ("Legacy tabs", check_legacy_tabs),
    ("Inspector", check_inspector),
    ("Overflow", check_overflow),
    ("Button roles", check_button_roles),
]


def run_checks(html: str, source: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    results = {}
    for name, fn in CHECKS:
        status, notes = fn(soup, html)
        results[name] = {"status": status, "notes": notes}
    return results


def print_report(results: dict, source: str) -> bool:
    """Print compact report. Returns True if all PASS/WARN (no FAIL)."""
    print(f"\n{'='*60}")
    print(f"  Layout Quality Report")
    print(f"  Source: {source}")
    print(f"{'='*60}\n")

    any_fail = False
    for name, data in results.items():
        status = data["status"]
        if status == "FAIL":
            any_fail = True
        icon = {"PASS": "[PASS]", "WARN": "[WARN]", "FAIL": "[FAIL]"}.get(status, "[??]")
        print(f"  {icon}  {name}")
        for note in data["notes"]:
            print(f"        {note}")
        print()

    # Summary
    counts = {"PASS": 0, "WARN": 0, "FAIL": 0}
    for data in results.values():
        counts[data["status"]] = counts.get(data["status"], 0) + 1

    total = len(results)
    score = counts["PASS"] * 100 + counts["WARN"] * 50
    max_score = total * 100
    pct = (score / max_score * 100) if max_score > 0 else 0

    print(f"{'='*60}")
    print(f"  Score: {counts['PASS']}/{total} PASS, {counts['WARN']} WARN, {counts['FAIL']} FAIL")
    print(f"  Quality: {pct:.0f}%")
    print(f"  Verdict: {'PASS' if not any_fail else 'FAIL'}")
    print(f"{'='*60}\n")

    return not any_fail


def main():
    parser = argparse.ArgumentParser(description="Layout quality scoring for session detail HIFI layout")
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
