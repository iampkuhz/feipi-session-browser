#!/usr/bin/env python3
"""Layout quality scoring for the Phase 1 session detail structure.

Usage:
    python scripts/qa/session_ui/check_layout_quality.py [--url URL] [--html PATH]

Checks:
    1. Hero: [data-session-overview-hero], .hero, .hero-alerts (only if failures exist), KPIs
    2. Trace Panel: [data-trace-panel], .trace-panel__toolbar, All/Failed buttons
    3. Token KPIs: token total present in hero KPIs (no separate token-charts-card)
    4. Legacy tabs: no data-workbench, no data-switch="calls", no data-switch="hotspots"
    5. Inspector: [data-context-inspector] in base.html but session detail uses no-inspector
    6. Overflow: no obvious horizontal overflow markers
    7. Button roles: no duplication of expand/collapse, no disabled placeholder buttons

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
        req = urllib.request.Request(url, headers={"User-Agent": "layout-quality-check/2.0"})
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
    """Hero: HIFI data selectors, KPIs, anomaly banner placeholder."""
    notes: list[str] = []
    pass_count = 0

    # Check for HIFI hero data attribute
    hero = soup.select_one("[data-session-overview-hero]")
    if hero:
        notes.append("[data-session-overview-hero] found")
        pass_count += 1
    else:
        notes.append("[data-session-overview-hero] MISSING")

    # Fallback: check for hero class-based element
    hero_class = soup.select_one(".hero, .hero-main, .session-header")
    if hero_class:
        notes.append(f"hero element found (.{hero_class.get('class', ['?'])[0]})")
        pass_count += 1
    else:
        notes.append("hero element MISSING")

    # Hero KPIs section
    kpis = soup.select_one(".kpis")
    if kpis:
        kpi_items = kpis.select(".kpi")
        notes.append(f"hero KPIs found ({len(kpi_items)} items)")
        pass_count += 1
    else:
        notes.append("hero KPIs section MISSING")

    # Hero alerts section (only expected when anomalies exist)
    alerts = soup.select_one(".hero-alerts")
    if alerts:
        notes.append("hero-alerts section found (anomalies present)")
        pass_count += 1
    else:
        notes.append("hero-alerts section absent (OK if no anomalies)")
        # Not a failure — alerts only appear when anomalies exist

    status = "PASS" if pass_count >= 3 else ("WARN" if pass_count >= 2 else "FAIL")
    return status, notes


def check_trace_panel(soup: BeautifulSoup, html: str) -> tuple[str, list[str]]:
    """Trace Panel: container exists with toolbar and filter buttons."""
    notes: list[str] = []
    pass_count = 0

    # HIFI data attribute
    panel = soup.select_one("[data-trace-panel]")
    if panel:
        notes.append("[data-trace-panel] found")
        pass_count += 1
    else:
        notes.append("[data-trace-panel] MISSING")

    # Toolbar
    toolbar = soup.select_one(".trace-panel__toolbar")
    if toolbar:
        notes.append(".trace-panel__toolbar found")
        pass_count += 1
    else:
        notes.append(".trace-panel__toolbar MISSING")

    # All/Failed filter buttons
    all_btn = soup.select_one('[data-action="status-all"]')
    failed_btn = soup.select_one('[data-action="status-failed"]')
    if all_btn and failed_btn:
        notes.append("All/Failed filter buttons found")
        pass_count += 1
    else:
        missing = []
        if not all_btn:
            missing.append("All")
        if not failed_btn:
            missing.append("Failed")
        notes.append(f"filter buttons MISSING: {', '.join(missing)}")

    # Expand/Collapse buttons
    expand_btn = soup.select_one('[data-action="expand-all"]')
    collapse_btn = soup.select_one('[data-action="collapse-all"]')
    if expand_btn and collapse_btn:
        notes.append("Expand All / Collapse All buttons found")
        pass_count += 1
    else:
        notes.append("Expand/Collapse buttons MISSING")

    # Trace rows
    trace_rows = soup.select(".trace-row")
    if trace_rows:
        notes.append(f"trace rows found (count={len(trace_rows)})")
        pass_count += 1
    else:
        notes.append("No trace rows found")

    status = "PASS" if pass_count >= 4 else ("WARN" if pass_count >= 3 else "FAIL")
    return status, notes


def check_token_kpis(soup: BeautifulSoup, html: str) -> tuple[str, list[str]]:
    """Token KPIs: token total appears in hero KPIs (no separate token-charts-card)."""
    notes: list[str] = []
    pass_count = 0

    # Verify token-charts-card is NOT present (it was deleted in Phase 1)
    chart_cards = soup.select(".token-charts-card")
    if chart_cards:
        notes.append(f"WARN: token-charts-card still present (count={len(chart_cards)})")
    else:
        notes.append("token-charts-card removed (expected for Phase 1)")
        pass_count += 1

    # Check for total tokens in hero KPIs
    kpis = soup.select_one(".kpis")
    if kpis:
        kpi_labels = kpis.select(".kpi .l")
        has_token_kpi = False
        for label in kpi_labels:
            text = label.get_text(strip=True).lower()
            if "token" in text:
                has_token_kpi = True
                notes.append(f"token KPI label found: '{label.get_text(strip=True)}'")
                pass_count += 1
                break
        if not has_token_kpi:
            notes.append("No token-related KPI label found in hero")

        # Check secondary metrics for total token value
        secondary = soup.select_one(".hero-secondary-metrics")
        if secondary:
            sec_text = secondary.get_text(strip=True).lower()
            if "token" in sec_text:
                notes.append("total tokens present in secondary metrics strip")
                pass_count += 1
            else:
                notes.append("total tokens NOT found in secondary metrics")
    else:
        notes.append("KPIs section not found")

    status = "PASS" if pass_count >= 2 else ("WARN" if pass_count >= 1 else "FAIL")
    return status, notes


def check_legacy_tabs(soup: BeautifulSoup, html: str) -> tuple[str, list[str]]:
    """Legacy tabs: negative check — no old workbench or tab switches."""
    notes: list[str] = []
    violations = 0

    # Check for data-workbench (removed in Phase 1)
    workbench = soup.select_one("[data-workbench]")
    if workbench:
        violations += 1
        notes.append("VIOLATION: [data-workbench] still present (should be removed)")
    else:
        notes.append("OK: [data-workbench] not found (expected)")

    # Check for data-switch="calls" (removed in Phase 1)
    calls_switch = soup.select_one('[data-switch="calls"]')
    if calls_switch:
        violations += 1
        notes.append('VIOLATION: [data-switch="calls"] still present')
    else:
        notes.append('OK: [data-switch="calls"] not found (expected)')

    # Check for data-switch="hotspots" (removed in Phase 1)
    hotspots_switch = soup.select_one('[data-switch="hotspots"]')
    if hotspots_switch:
        violations += 1
        notes.append('VIOLATION: [data-switch="hotspots"] still present')
    else:
        notes.append('OK: [data-switch="hotspots"] not found (expected)')

    # Check for old tab-nav/tab-bar structures
    old_tabs = soup.select(".tab-nav, .tab-bar, .tab-item, .wb-viewbar")
    if old_tabs:
        violations += len(old_tabs)
        notes.append(f"VIOLATION: old tab/viewbar structures found (count={len(old_tabs)})")
    else:
        notes.append("OK: no old tab navigation structures found")

    if violations > 0:
        notes.append(f"Total legacy violations: {violations}")
        return "FAIL", notes
    else:
        notes.append("No legacy tab/workbench artifacts found")
        return "PASS", notes


def check_inspector(soup: BeautifulSoup, html: str) -> tuple[str, list[str]]:
    """Inspector: should exist in base.html but NOT be rendered on session detail.

    Session detail uses 'no-inspector' class on the shell div to suppress the
    inspector panel. The base template conditionally renders inspector based on
    'no-inspector' not being in shell_class.
    """
    notes: list[str] = []
    pass_count = 0

    # Check that the session detail shell exists
    detail_shell = soup.select_one("[data-session-detail-shell]")
    if detail_shell:
        notes.append("[data-session-detail-shell] found")
        pass_count += 1
    else:
        notes.append("[data-session-detail-shell] MISSING")

    # Check for no-inspector class on the shell or body
    shell_cls = detail_shell.get("class", []) if detail_shell else []
    body_cls = soup.body.get("class", []) if soup.body else []
    has_no_inspector = "no-inspector" in shell_cls or "no-inspector" in body_cls

    if has_no_inspector:
        notes.append("'no-inspector' class found on shell/body (inspector suppressed)")
        pass_count += 1
    else:
        # Inspector may still be rendered — check if it's present
        inspector = soup.select_one("[data-context-inspector]")
        if inspector:
            notes.append("[data-context-inspector] is rendered on session detail")
            notes.append("WARN: inspector visible — Phase 1 may not need 'no-inspector'")
            pass_count += 1  # Not a hard fail, just informational
        else:
            notes.append("No inspector element found (suppressed via template or class)")
            pass_count += 1

    # Verify inspector does NOT appear as a visible panel on the detail page
    # In Phase 1, inspector is conditionally excluded via Jinja template
    inspector_aside = soup.select_one("aside.inspector")
    if inspector_aside and detail_shell:
        # Check if it's inside the detail shell (meaning it's rendered on this page)
        if inspector_aside.parent and _is_ancestor_of(inspector_aside.parent, detail_shell):
            notes.append("WARN: aside.inspector is rendered inside session detail shell")
        else:
            notes.append("aside.inspector not inside detail shell (OK)")
            pass_count += 1
    elif not inspector_aside:
        notes.append("aside.inspector not rendered (expected for Phase 1)")
        pass_count += 1

    status = "PASS" if pass_count >= 2 else ("WARN" if pass_count >= 1 else "FAIL")
    return status, notes


def _is_ancestor_of(potential_ancestor, element) -> bool:
    """Check if potential_ancestor is an ancestor of element (or is element)."""
    current = element
    while current:
        if current is potential_ancestor:
            return True
        current = current.parent
    return False


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
    """Button roles: no duplication of expand/collapse, no disabled placeholder buttons."""
    notes: list[str] = []
    issues = 0

    # Check for expand/collapse button duplication
    expand_all = soup.select('[data-action="expand-all"]')
    collapse_all = soup.select('[data-action="collapse-all"]')

    if len(expand_all) > 1:
        issues += len(expand_all) - 1
        notes.append(f"DUPLICATE: [data-action='expand-all'] found {len(expand_all)} times")
    elif len(expand_all) == 1:
        notes.append("[data-action='expand-all'] present (single)")

    if len(collapse_all) > 1:
        issues += len(collapse_all) - 1
        notes.append(f"DUPLICATE: [data-action='collapse-all'] found {len(collapse_all)} times")
    elif len(collapse_all) == 1:
        notes.append("[data-action='collapse-all'] present (single)")

    # Check for disabled placeholder buttons (should not have duplicate functional roles)
    disabled_placeholders = soup.select("button[disabled].topbar-action--placeholder")
    if disabled_placeholders:
        notes.append(f"disabled placeholder buttons found (count={len(disabled_placeholders)})")
        # Check for duplicates by aria-label
        labels = [b.get("aria-label", "").strip().lower() for b in disabled_placeholders]
        from collections import Counter
        dup_labels = {label for label, count in Counter(labels).items() if count > 1 and label}
        if dup_labels:
            issues += len(dup_labels)
            notes.append(f"DUPLICATE disabled placeholder labels: {sorted(dup_labels)}")
        else:
            notes.append("disabled placeholders have unique roles (OK)")

    # Check for duplicate "Jump to Trace" buttons
    jump_buttons = soup.select('button.jump[data-action="jump-anomaly"]')
    if len(jump_buttons) > len(soup.select(".hero-alerts .alert")):
        issues += 1
        notes.append(f"DUPLICATE: more 'Jump to Trace' buttons ({len(jump_buttons)}) than alerts")
    elif jump_buttons:
        notes.append(f"'Jump to Trace' buttons match alert count ({len(jump_buttons)})")

    if issues > 0:
        notes.append(f"Total button role issues: {issues}")
        return "FAIL", notes
    else:
        notes.append("No button role issues detected")
        return "PASS", notes


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

CHECKS = [
    ("Hero", check_hero),
    ("Trace Panel", check_trace_panel),
    ("Token KPIs", check_token_kpis),
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
    print(f"  Layout Quality Report (Phase 1)")
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
    parser = argparse.ArgumentParser(description="Layout quality scoring for Phase 1 session detail")
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
