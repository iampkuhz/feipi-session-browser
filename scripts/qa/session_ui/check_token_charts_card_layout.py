#!/usr/bin/env python3
"""Token metrics placement check for Phase 1 session detail.

After Phase 1, the token-charts-card is deleted. Token data now appears in:
  - Hero KPIs (total tokens, cache hit, duration, failed tools)
  - Issue summary (highest token round card)
  - Trace rows (per-round mixbar + .mixval, data-round-tokens)

Usage:
    python scripts/qa/session_ui/check_token_charts_card_layout.py [--url URL] [--html PATH]

Checks:
    1. Token total appears in hero KPIs
    2. Highest token round appears in issue summary (if any)
    3. Per-round token data in trace rows (.mixval or data-round-tokens)
    4. token-charts-card is removed (negative check)

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

# ---------------------------------------------------------------------------
# Data fetching (mirrors check_layout_quality.py pattern)
# ---------------------------------------------------------------------------

def fetch_html(url: str, timeout: float = 3.0) -> str | None:
    """Try to fetch HTML from a running local server."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "token-metrics-check/2.0"})
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

def check_token_total_in_kpis(soup: BeautifulSoup) -> tuple[str, list[str]]:
    """Check that token total appears in hero KPIs."""
    notes: list[str] = []
    pass_count = 0

    # Check for KPIs section
    kpis = soup.select_one(".kpis")
    if kpis:
        notes.append("hero KPIs section found")
        pass_count += 1

        # Look for a KPI label containing "token"
        kpi_labels = kpis.select(".kpi .l")
        token_kpi = None
        for label in kpi_labels:
            text = label.get_text(strip=True).lower()
            if "token" in text:
                token_kpi = label
                break

        if token_kpi:
            # Check the corresponding value
            value_el = token_kpi.find_previous_sibling(class_="v")
            if value_el:
                val_text = value_el.get_text(strip=True)
                notes.append(f"token KPI value: '{val_text}' (label: '{token_kpi.get_text(strip=True)}')")
                pass_count += 1
            else:
                notes.append(f"token KPI label found but no value sibling")
        else:
            notes.append("No KPI label contains 'token'")

        # Also check secondary metrics strip for total tokens
        secondary = soup.select_one(".hero-secondary-metrics")
        if secondary:
            sec_text = secondary.get_text()
            if "总 Token" in sec_text or "total token" in sec_text.lower():
                notes.append("total tokens present in secondary metrics strip")
                pass_count += 1
    else:
        notes.append("hero KPIs section NOT found")

    if pass_count >= 2:
        return "PASS", notes
    elif pass_count >= 1:
        return "WARN", notes
    else:
        notes.append("FAIL: no token total found in hero KPIs")
        return "FAIL", notes


def check_highest_token_round_in_issues(soup: BeautifulSoup) -> tuple[str, list[str]]:
    """Check that highest token round appears in issue summary (if data warrants it)."""
    notes: list[str] = []
    pass_count = 0

    # Check for issue summary section
    issue_section = soup.select_one("[data-issue-summary], .issue-summary")
    if issue_section:
        notes.append("issue summary section found")
        pass_count += 1
    else:
        notes.append("issue summary section NOT found")
        return "WARN", notes  # Not a hard failure

    # Look for highest token round card (issue-card--cost)
    cost_card = issue_section.select_one(".issue-card--cost")
    if cost_card:
        title = cost_card.select_one(".issue-card__title")
        sub = cost_card.select_one(".issue-card__sub")
        if title:
            title_text = title.get_text(strip=True)
            notes.append(f"highest token round card title: '{title_text}'")
            pass_count += 1

            # Check if it mentions "tokens"
            if "token" in title_text.lower():
                notes.append("card title contains 'tokens' keyword")
                pass_count += 1

        if sub:
            notes.append(f"card subtitle: '{sub.get_text(strip=True)}'")
    else:
        notes.append("No highest-token-round cost card found (may be OK if no data or round < 2)")

    # Also check for data-action="jump-round" buttons that reference rounds
    jump_buttons = issue_section.select('[data-action="jump-round"][data-round]')
    if jump_buttons:
        notes.append(f"jump-round buttons in issue summary: {len(jump_buttons)}")

    if pass_count >= 2:
        return "PASS", notes
    elif pass_count >= 1:
        return "WARN", notes
    else:
        return "WARN", notes


def check_per_round_token_data(soup: BeautifulSoup) -> tuple[str, list[str]]:
    """Check that per-round token data appears in trace rows."""
    notes: list[str] = []
    pass_count = 0

    trace_rows = soup.select(".trace-row")
    if not trace_rows:
        notes.append("No trace rows found")
        return "FAIL", notes

    notes.append(f"trace rows found (count={len(trace_rows)})")
    pass_count += 1

    # Check for .mixval in trace rows
    rows_with_mixval = soup.select(".trace-row .mixval")
    if rows_with_mixval:
        notes.append(f".mixval elements found in trace rows (count={len(rows_with_mixval)})")
        pass_count += 1

        # Verify values are non-empty
        sample_values = [el.get_text(strip=True) for el in rows_with_mixval[:3]]
        notes.append(f"sample mixval values: {sample_values}")
    else:
        notes.append("No .mixval elements found in trace rows")

    # Check for data-round-tokens attribute on trace rows
    rows_with_token_data = [r for r in trace_rows if r.get("data-round-tokens")]
    if rows_with_token_data:
        notes.append(f"trace rows with data-round-tokens: {len(rows_with_token_data)}")
        pass_count += 1

        # Sample values
        sample = [r["data-round-tokens"] for r in rows_with_token_data[:3]]
        notes.append(f"sample data-round-tokens values: {sample}")
    else:
        notes.append("No data-round-tokens attributes on trace rows")

    # Check for mixbar (token composition bar)
    mixbars = soup.select(".trace-row .mixbar")
    if mixbars:
        notes.append(f"mixbar elements found (count={len(mixbars)})")
        pass_count += 1
    else:
        notes.append("No mixbar elements found")

    if pass_count >= 3:
        return "PASS", notes
    elif pass_count >= 2:
        return "WARN", notes
    else:
        return "FAIL", notes


def check_token_charts_card_removed(soup: BeautifulSoup) -> tuple[str, list[str]]:
    """Negative check: token-charts-card should NOT be present in Phase 1."""
    notes: list[str] = []

    chart_cards = soup.select(".token-charts-card")
    chart_bodies = soup.select("div.token-charts-card__body")

    if chart_cards:
        notes.append(f"VIOLATION: .token-charts-card still present (count={len(chart_cards)})")
        return "FAIL", notes
    elif chart_bodies:
        notes.append(f"VIOLATION: .token-charts-card__body still present (count={len(chart_bodies)})")
        return "FAIL", notes
    else:
        notes.append("OK: token-charts-card fully removed (Phase 1 target state)")
        return "PASS", notes


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

CHECKS = [
    ("Token total in hero KPIs", check_token_total_in_kpis),
    ("Highest token round in issues", check_highest_token_round_in_issues),
    ("Per-round token data in traces", check_per_round_token_data),
    ("token-charts-card removed", check_token_charts_card_removed),
]


def run_checks(html: str, source: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    results = {}
    for name, fn in CHECKS:
        status, notes = fn(soup)
        results[name] = {"status": status, "notes": notes}
    return results


def print_report(results: dict, source: str) -> bool:
    """Print compact report. Returns True if no FAIL."""
    print(f"\n{'='*60}")
    print(f"  Token Metrics Placement Check (Phase 1)")
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
    parser = argparse.ArgumentParser(description="Token metrics placement check for Phase 1")
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
