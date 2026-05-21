#!/usr/bin/env python3
"""T165 — Static QA for glossary page HTML structure.

Validates glossary.html against the page behavior contract:

1. Template structure: extends base.html, active_page set, ui_primitives imported
2. Header: .page-head, h1, .subtitle
3. No inline: no onclick, no inline <script>, no inline <style>
4. CSS/JS imports: glossary.css and glossary.js imported
5. Metric grid: 4 metric cards with icon, label, value, note
6. Filter card: .filter-card, .input.search, data-search attribute
7. Empty state: .state-strip with ARIA attributes
8. Sections: 7 .card.section with .section-head
9. Tables: 5 data-tables with data-table-enhanced, sortable headers
10. data-action coverage: sort, search
11. Accessibility: aria-hidden, aria-label, aria-live, role
12. Stale patterns: no page-header, hero, legacy-, onclick

Run from repo root:
  python scripts/qa/ui/check_glossary_html.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
GLOSSARY_HTML = ROOT / "src/session_browser/web/templates/glossary.html"
GLOSSARY_CSS = ROOT / "src/session_browser/web/static/css/glossary.css"
GLOSSARY_JS = ROOT / "src/session_browser/web/static/js/glossary.js"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def main() -> int:
    html = read(GLOSSARY_HTML)
    css = read(GLOSSARY_CSS)
    js = read(GLOSSARY_JS)

    checks: list[tuple[str, callable]] = [
        # ── Template structure ─────────────────────────────────────
        ("T165-H01 glossary.html exists",
         lambda: (GLOSSARY_HTML.exists(),
                  "exists" if GLOSSARY_HTML.exists() else "MISSING")),

        ("T165-H02 extends base.html",
         lambda: ('{% extends "base.html" %}' in html,
                  "extends base.html found" if '{% extends "base.html" %}' in html else "MISSING")),

        ("T165-H03 active_page set to 'glossary'",
         lambda: ("{% set active_page = 'glossary' %}" in html,
                  "active_page='glossary' found" if "{% set active_page = 'glossary' %}" in html else "MISSING")),

        ("T165-H04 ui_primitives imported",
         lambda: ('{% import "components/ui_primitives.html" as ui %}' in html
                  or '{%- import "components/ui_primitives.html" as ui %}' in html,
                  "ui_primitives imported" if ('{% import "components/ui_primitives.html" as ui %}' in html
                                               or '{%- import "components/ui_primitives.html" as ui %}' in html) else "MISSING")),

        # ── Header ─────────────────────────────────────────────────
        ("T165-H05 .page-head present",
         lambda: ('class="page-head"' in html,
                  "page-head found" if 'class="page-head"' in html else "MISSING")),

        ("T165-H06 h1 title present",
         lambda: ('<h1>' in html,
                  "h1 found" if '<h1>' in html else "MISSING")),

        ("T165-H07 .subtitle present",
         lambda: ('class="subtitle"' in html,
                  "subtitle found" if 'class="subtitle"' in html else "MISSING")),

        # ── No inline ──────────────────────────────────────────────
        ("T165-H08 No inline <style> blocks",
         lambda: (not bool(re.search(r'<style>', html)),
                  "clean" if not re.search(r'<style>', html) else "INLINE STYLE FOUND")),

        ("T165-H09 No inline <script> (non-JSON)",
         lambda: (
             not bool(re.findall(r'<script(?![^>]*type="application/json")[^>]*>[^<]', html)),
             "clean" if not re.findall(r'<script(?![^>]*type="application/json")[^>]*>[^<]', html) else "INLINE SCRIPT FOUND"
         )),

        ("T165-H10 No inline onclick",
         lambda: ("onclick=" not in html,
                  "clean" if "onclick=" not in html else "INLINE ONCLICK FOUND")),

        # ── CSS/JS ─────────────────────────────────────────────────
        ("T165-H11 glossary.css exists",
         lambda: (GLOSSARY_CSS.exists(),
                  "exists" if GLOSSARY_CSS.exists() else "MISSING")),

        ("T165-H12 glossary.js exists and syntax valid",
         lambda: _check_js_syntax(js)),

        ("T165-H13 glossary.css linked in head_extra",
         lambda: ('/static/css/glossary.css' in html,
                  "glossary.css linked" if '/static/css/glossary.css' in html else "MISSING")),

        ("T165-H14 glossary.js imported in script_extra",
         lambda: ('/static/js/glossary.js' in html,
                  "glossary.js imported" if '/static/js/glossary.js' in html else "MISSING")),

        # ── Metric grid ────────────────────────────────────────────
        ("T165-H15 .metric-grid present",
         lambda: ('class="metric-grid"' in html,
                  "metric-grid found" if 'class="metric-grid"' in html else "MISSING")),

        ("T165-H16 4 .card.metric-card elements",
         lambda: (html.count('class="card metric-card"') >= 4,
                  f'{html.count("class=\"card metric-card\"")} card.metric-card(s) found'
                  if html.count('class="card metric-card"') >= 4
                  else f"ONLY {html.count('class=\"card metric-card\"')} card.metric-card(s)")),

        ("T165-H17 .metric-icon in each card",
         lambda: ('class="metric-icon' in html,
                  "metric-icon found" if 'class="metric-icon' in html else "MISSING")),

        ("T165-H18 .metric-label in each card",
         lambda: ('class="metric-label"' in html,
                  "metric-label found" if 'class="metric-label"' in html else "MISSING")),

        ("T165-H19 .metric-value in each card",
         lambda: ('class="metric-value' in html,
                  "metric-value found" if 'class="metric-value' in html else "MISSING")),

        ("T165-H20 All 4 labels present",
         lambda: (
             all(x in html for x in [
                 "Token Types", "Derived Metrics", "Provider Fields", "Round Signals",
             ]),
             "all 4 labels found" if all(x in html for x in [
                 "Token Types", "Derived Metrics", "Provider Fields", "Round Signals",
             ]) else "MISSING metric labels")),

        # ── Filter card ────────────────────────────────────────────
        ("T165-H21 .filter-card present",
         lambda: ('filter-card' in html,
                  "filter-card found" if 'filter-card' in html else "MISSING")),

        ("T165-H22 .input.search present",
         lambda: ('class="input search"' in html,
                  "input search found" if 'class="input search"' in html else "MISSING")),

        ("T165-H23 data-search attribute on search input",
         lambda: ('data-search=' in html,
                  "data-search found" if 'data-search=' in html else "MISSING")),

        # ── Empty state ────────────────────────────────────────────
        ("T165-H24 .state-strip present",
         lambda: ('class="state-strip' in html,
                  "state-strip found" if 'class="state-strip' in html else "MISSING")),

        ("T165-H25 role=\"status\" on empty state",
         lambda: ('role="status"' in html,
                  "role=status found" if 'role="status"' in html else "MISSING")),

        ("T165-H26 aria-live=\"polite\" on empty state",
         lambda: ('aria-live="polite"' in html,
                  "aria-live=polite found" if 'aria-live="polite"' in html else "MISSING")),

        # ── Sections ───────────────────────────────────────────────
        ("T165-H27 7 .card.section elements",
         lambda: (html.count('class="card section"') >= 7,
                  f'{html.count("class=\"card section\"")} card.section(s) found'
                  if html.count('class="card section"') >= 7
                  else f"ONLY {html.count('class=\"card section\"')} card.section(s)")),

        ("T165-H28 .section-head in each section",
         lambda: ('class="section-head"' in html,
                  "section-head found" if 'class="section-head"' in html else "MISSING")),

        ("T165-H29 .section-title in each section",
         lambda: ('class="section-title"' in html,
                  "section-title found" if 'class="section-title"' in html else "MISSING")),

        ("T165-H30 .section-sub present",
         lambda: ('class="section-sub"' in html,
                  "section-sub found" if 'class="section-sub"' in html else "MISSING")),

        # ── Tables ─────────────────────────────────────────────────
        ("T165-H31 5 .data-table elements",
         lambda: (html.count('class="data-table"') >= 5,
                  f'{html.count("class=\"data-table\"")} data-table(s) found'
                  if html.count('class="data-table"') >= 5
                  else f"ONLY {html.count('class=\"data-table\"')} data-table(s)")),

        ("T165-H32 data-table-enhanced on all tables",
         lambda: (html.count('data-table-enhanced') >= 5,
                  f'{html.count("data-table-enhanced")} data-table-enhanced found'
                  if html.count('data-table-enhanced') >= 5
                  else f"ONLY {html.count('data-table-enhanced')} data-table-enhanced")),

        ("T165-H33 .table-wrap on all tables",
         lambda: ('class="table-wrap"' in html,
                  "table-wrap found" if 'class="table-wrap"' in html else "MISSING")),

        # ── Sortable headers ───────────────────────────────────────
        ("T165-H34 data-action=\"sort\" on sortable headers",
         lambda: (html.count('data-action="sort"') >= 6,
                  f'{html.count("data-action=\"sort\"")} sortable header(s) found'
                  if html.count('data-action="sort"') >= 6
                  else f"ONLY {html.count('data-action=\"sort\"')} sortable header(s)")),

        ("T165-H35 data-sort-key on sortable headers",
         lambda: ('data-sort-key=' in html,
                  "data-sort-key found" if 'data-sort-key=' in html else "MISSING")),

        # ── Section content checks ─────────────────────────────────
        ("T165-H36 Badge reference section with status badges",
         lambda: (
             'class="section-title">Badge Reference' in html
             and 'status_success(' in html
             and 'status_warning(' in html
             and 'status_error(' in html,
             "Badge Reference section with status macros found"
             if ('class="section-title">Badge Reference' in html
                 and 'status_success(' in html
                 and 'status_warning(' in html
                 and 'status_error(' in html)
             else "MISSING Badge Reference section")),

        ("T165-H37 Token 组成 section with token badges",
         lambda: (
             'token-badge--input' in html
             and 'token-badge--cache-read' in html
             and 'token-badge--cache-write' in html
             and 'token-badge--output' in html,
             "Token badges found"
             if ('token-badge--input' in html
                 and 'token-badge--cache-read' in html
                 and 'token-badge--cache-write' in html
                 and 'token-badge--output' in html)
             else "MISSING token badges")),

        ("T165-H38 Provider mapping section present",
         lambda: (
             'id="provider-mapping"' in html
             and 'class="section-title">Provider 映射' in html,
             "Provider mapping section found"
             if ('id="provider-mapping"' in html
                 and 'class="section-title">Provider 映射' in html)
             else "MISSING Provider mapping section")),

        ("T165-H39 Known limitations section present",
         lambda: ('class="section-title">已知限制' in html,
                  "Known limitations section found" if 'class="section-title">已知限制' in html else "MISSING")),

        ("T165-H40 Session Anomalies section present",
         lambda: ('class="section-title">Session Anomalies' in html,
                  "Session Anomalies section found" if 'class="section-title">Session Anomalies' in html else "MISSING")),

        ("T165-H41 Round Signals section present",
         lambda: ('class="section-title">Round Signals' in html,
                  "Round Signals section found" if 'class="section-title">Round Signals' in html else "MISSING")),

        # ── data-action coverage ───────────────────────────────────
        ("T165-H42 data-action: sort",
         lambda: ('data-action="sort"' in html,
                  "sort found" if 'data-action="sort"' in html else "MISSING")),

        ("T165-H43 data-action: search",
         lambda: ('data-search="glossary-term"' in html,
                  "glossary-term search found" if 'data-search="glossary-term"' in html else "MISSING")),

        # ── Accessibility ──────────────────────────────────────────
        ("T165-H44 aria-hidden=\"true\" on emoji spans",
         lambda: ('aria-hidden="true"' in html,
                  "aria-hidden found" if 'aria-hidden="true"' in html else "MISSING")),

        ("T165-H45 aria-label on search input",
         lambda: ('aria-label="Search glossary terms"' in html,
                  "aria-label=Search glossary terms found" if 'aria-label="Search glossary terms"' in html else "MISSING")),

        ("T165-H46 aria-label on metric grid",
         lambda: ('aria-label="术语页摘要指标"' in html,
                  "aria-label on metric grid found" if 'aria-label="术语页摘要指标"' in html else "MISSING")),

        # ── Breadcrumb ─────────────────────────────────────────────
        ("T165-H47 Breadcrumb present with dashboard link",
         lambda: ('href="/dashboard"' in html,
                  "breadcrumb with dashboard link found" if 'href="/dashboard"' in html else "MISSING")),

        # ── Token formatting ───────────────────────────────────────
        ("T165-H48 No raw compact token format (glossary is static)",
         lambda: ('format_compact_token' not in html,
                  "clean — no format_compact_token in static glossary" if 'format_compact_token' not in html else "UNEXPECTED format_compact_token in static page")),

        # ── Stale patterns ─────────────────────────────────────────
        ("T165-H49 No stale patterns: no page-header, no hero, no legacy-, no onclick",
         lambda: (
             'class="page-header"' not in html
             and 'class="hero"' not in html
             and 'legacy-' not in html
             and 'onclick=' not in html,
             "clean" if (
                 'class="page-header"' not in html
                 and 'class="hero"' not in html
                 and 'legacy-' not in html
                 and 'onclick=' not in html
             ) else "STALE PATTERN FOUND"
         )),

        ("T165-H50 No TODO/FIXME/HACK comments",
         lambda: (
             'TODO' not in html
             and 'FIXME' not in html
             and 'HACK' not in html,
             "clean" if ('TODO' not in html and 'FIXME' not in html and 'HACK' not in html) else "TODO/FIXME/HACK FOUND"
         )),
    ]

    all_pass = True
    for label, run in checks:
        ok, detail = run()
        status = "PASS" if ok else "FAIL"
        if not ok:
            all_pass = False
        print(f"  [{status}] {label}: {detail}")

    print()
    if all_pass:
        print("PASS: glossary HTML QA checks")
        return 0
    else:
        print("FAIL: glossary HTML QA checks -- see details above")
        return 1


def _check_js_syntax(js: str) -> tuple[bool, str]:
    """Basic JS syntax check via balanced braces/parens/brackets."""
    if not js:
        return (False, "glossary.js is empty or missing")

    stack: list[str] = []
    pairs = {"{": "}", "(": ")", "[": "]"}
    openers = set(pairs.keys())
    closers = set(pairs.values())
    in_string: str | None = None
    escaped = False

    for ch in js:
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if in_string:
            if ch == in_string:
                in_string = None
            continue
        if ch in ('"', "'", "`"):
            in_string = ch
            continue
        if ch in openers:
            stack.append(ch)
        elif ch in closers:
            if not stack:
                return (False, f"unmatched closer '{ch}'")
            opener = stack.pop()
            if pairs[opener] != ch:
                return (False, f"mismatched braces: '{opener}' vs '{ch}'")

    if stack:
        return (False, f"unclosed: {stack[-1]}")

    essential_markers = [
        "use strict",
        "document.getElementById",
        "addEventListener",
        "function ",
        "data-table-enhanced",
    ]
    missing_markers = [m for m in essential_markers if m not in js]
    if missing_markers:
        return (False, f"balanced but missing markers: {', '.join(missing_markers)}")

    return (True, f"balanced braces/parens/brackets, {len(js)} bytes, all structural markers present")


if __name__ == "__main__":
    raise SystemExit(main())
