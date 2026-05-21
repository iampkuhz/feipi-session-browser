#!/usr/bin/env python3
"""T151 — Static QA for agent-detail page HTML structure.

Validates agent.html against the page behavior contract:

1. Template structure: extends base.html, active_page set, ui_primitives imported
2. Header: .header, .header-left, .back-btn, .agent-title, .agent-subtitle
3. No inline: no onclick, no inline <script>, no inline <style>
4. CSS/JS imports: agents.css and agents.js imported
5. Metric grid: 6 metric cards with icon, label, value, info buttons
6. Model breakdown: section, 7 table columns, tokenbar, sortable headers
7. Sessions: section, search input, 9 table columns, row structure
8. Pagination: unified-pagination, data-action coverage, aria labels
9. Empty/error states: ui.empty_state, ui.button, ui.error_state
10. data-action coverage: back, info, sort, open-session, page-input, prev-page, next-page, refresh
11. Accessibility: aria-hidden, aria-label, title attributes
12. Stale patterns: no page-header, hero, legacy-, onclick

Run from repo root:
  python scripts/qa/ui/check_agent_detail_html.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
AGENT_HTML = ROOT / "src/session_browser/web/templates/agent.html"
AGENTS_CSS = ROOT / "src/session_browser/web/static/css/agents.css"
AGENTS_JS = ROOT / "src/session_browser/web/static/js/agents.js"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def main() -> int:
    html = read(AGENT_HTML)
    css = read(AGENTS_CSS)
    js = read(AGENTS_JS)

    checks: list[tuple[str, callable]] = [
        # ── Template structure ─────────────────────────────────────
        ("T151-H01 agent.html exists",
         lambda: (AGENT_HTML.exists(),
                  "exists" if AGENT_HTML.exists() else "MISSING")),

        ("T151-H02 extends base.html",
         lambda: ('{% extends "base.html" %}' in html,
                  "extends base.html found" if '{% extends "base.html" %}' in html else "MISSING")),

        ("T151-H03 active_page set to 'agents'",
         lambda: ("{% set active_page = 'agents' %}" in html,
                  "active_page='agents' found" if "{% set active_page = 'agents' %}" in html else "MISSING")),

        ("T151-H04 ui_primitives imported",
         lambda: ('{% import "components/ui_primitives.html" as ui %}' in html,
                  "ui_primitives imported" if '{% import "components/ui_primitives.html" as ui %}' in html else "MISSING")),

        # ── Header ─────────────────────────────────────────────────
        ("T151-H05 .header class present",
         lambda: ('class="header"' in html,
                  "header found" if 'class="header"' in html else "MISSING")),

        ("T151-H06 .header-left present",
         lambda: ('class="header-left"' in html,
                  "header-left found" if 'class="header-left"' in html else "MISSING")),

        ("T151-H07 .back-btn with data-action=\"back\" and href=\"/agents\"",
         lambda: ('class="btn back-btn"' in html
                  and 'data-action="back"' in html
                  and 'href="/agents"' in html,
                  "back-btn with data-action=back and href=/agents found"
                  if ('class="btn back-btn"' in html
                      and 'data-action="back"' in html
                      and 'href="/agents"' in html)
                  else "MISSING")),

        ("T151-H08 .agent-title present",
         lambda: ('class="agent-title"' in html,
                  "agent-title found" if 'class="agent-title"' in html else "MISSING")),

        ("T151-H09 .agent-subtitle present",
         lambda: ('class="agent-subtitle"' in html,
                  "agent-subtitle found" if 'class="agent-subtitle"' in html else "MISSING")),

        # ── No inline ──────────────────────────────────────────────
        ("T151-H10 No inline <style> blocks",
         lambda: (not bool(re.search(r'<style>', html)),
                  "clean" if not re.search(r'<style>', html) else "INLINE STYLE FOUND")),

        ("T151-H11 No inline <script> (non-JSON)",
         lambda: (
             not bool(re.findall(r'<script(?![^>]*type="application/json")[^>]*>[^<]', html)),
             "clean" if not re.findall(r'<script(?![^>]*type="application/json")[^>]*>[^<]', html) else "INLINE SCRIPT FOUND"
         )),

        ("T151-H12 No inline onclick",
         lambda: ("onclick=" not in html,
                  "clean" if "onclick=" not in html else "INLINE ONCLICK FOUND")),

        # ── CSS/JS ─────────────────────────────────────────────────
        ("T151-H13 agents.css exists",
         lambda: (AGENTS_CSS.exists(),
                  "exists" if AGENTS_CSS.exists() else "MISSING")),

        ("T151-H14 agents.js exists and syntax valid",
         lambda: _check_js_syntax(js)),

        # ── Metric grid ────────────────────────────────────────────
        ("T151-H15 .metric-grid present",
         lambda: ('class="metric-grid"' in html,
                  "metric-grid found" if 'class="metric-grid"' in html else "MISSING")),

        ("T151-H16 6 .card.metric-card elements",
         lambda: (html.count('class="card metric-card"') >= 6,
                  f'{html.count("class=\"card metric-card\"")} card.metric-card(s) found'
                  if html.count('class="card metric-card"') >= 6
                  else f"ONLY {html.count('class=\"card metric-card\"')} card.metric-card(s)")),

        ("T151-H17 .metric-icon in each card",
         lambda: ('class="metric-icon' in html,
                  "metric-icon found" if 'class="metric-icon' in html else "MISSING")),

        ("T151-H18 .metric-label in each card",
         lambda: ('class="metric-label"' in html,
                  "metric-label found" if 'class="metric-label"' in html else "MISSING")),

        ("T151-H19 .metric-value in each card",
         lambda: ('class="metric-value' in html,
                  "metric-value found" if 'class="metric-value' in html else "MISSING")),

        ("T151-H20 All 6 labels present",
         lambda: (
             all(x in html for x in [
                 "Sessions", "Projects", "Input-side Tokens",
                 "Output Tokens", "Cache Reuse", "Failed Tools",
             ]),
             "all 6 labels found" if all(x in html for x in [
                 "Sessions", "Projects", "Input-side Tokens",
                 "Output Tokens", "Cache Reuse", "Failed Tools",
             ]) else "MISSING metric labels")),

        ("T151-H21 data-action=\"info\" on metric info icons",
         lambda: (html.count('data-action="info"') >= 6,
                  f'{html.count("data-action=\"info\"")} info icon(s) found'
                  if html.count('data-action="info"') >= 6
                  else f"ONLY {html.count('data-action=\"info\"')} info icon(s)")),

        # ── Model Breakdown ────────────────────────────────────────
        ("T151-H22 .section-head present for Model Breakdown",
         lambda: ('class="section-head"' in html,
                  "section-head found" if 'class="section-head"' in html else "MISSING")),

        ("T151-H23 .card.section wraps model breakdown",
         lambda: ('class="card section"' in html,
                  "card section found" if 'class="card section"' in html else "MISSING")),

        ("T151-H24 7 table columns (Model, Sessions, Tokens, Cache Reuse, Tools, Failed, Avg Duration)",
         lambda: (
             all(x in html for x in [
                 ">Model ", ">Sessions ", ">Tokens ", ">Cache Reuse ",
                 ">Tools ", ">Failed ", ">Avg Duration ",
             ]),
             "all 7 columns found" if all(x in html for x in [
                 ">Model ", ">Sessions ", ">Tokens ", ">Cache Reuse ",
                 ">Tools ", ">Failed ", ">Avg Duration ",
             ]) else "MISSING column headers")),

        ("T151-H25 tokenbar present in token cells",
         lambda: ('class="tokenbar"' in html,
                  "tokenbar found" if 'class="tokenbar"' in html else "MISSING")),

        ("T151-H26 .sort-mark for sort indicators",
         lambda: ('class="sort-mark"' in html,
                  "sort-mark found" if 'class="sort-mark"' in html else "MISSING")),

        ("T151-H27 Sortable headers with data-action=\"sort\" data-sort-key",
         lambda: (html.count('data-action="sort"') >= 7
                  and 'data-sort-key=' in html,
                  "sortable headers with data-sort-key found"
                  if (html.count('data-action="sort"') >= 7
                      and 'data-sort-key=' in html)
                  else "MISSING sortable headers")),

        # ── Sessions ───────────────────────────────────────────────
        ("T151-H28 .section-head present for Sessions",
         lambda: ('class="section-head"' in html,
                  "section-head found" if 'class="section-head"' in html else "MISSING")),

        ("T151-H29 .card.section wraps sessions",
         lambda: ('class="card section"' in html,
                  "card section found" if 'class="card section"' in html else "MISSING")),

        ("T151-H30 Search input with data-search attribute",
         lambda: ('data-search=' in html,
                  "data-search found" if 'data-search=' in html else "MISSING")),

        ("T151-H31 9 table columns (Title, Project, Model, Tokens, Rounds, Tools, Failed, Duration, Updated)",
         lambda: (
             all(x in html for x in [
                 "<th>Title</th>", "<th>Project</th>", ">Model ", ">Tokens ",
                 ">Rounds ", ">Tools ", ">Failed ", ">Duration ", ">Updated ",
             ]),
             "all 9 columns found" if all(x in html for x in [
                 "<th>Title</th>", "<th>Project</th>", ">Model ", ">Tokens ",
                 ">Rounds ", ">Tools ", ">Failed ", ">Duration ", ">Updated ",
             ]) else "MISSING column headers")),

        ("T151-H32 .title-main in title cells",
         lambda: ('class="title-main"' in html,
                  "title-main found" if 'class="title-main"' in html else "MISSING")),

        ("T151-H33 .title-sub.mono in title cells",
         lambda: ('class="title-sub mono"' in html,
                  "title-sub mono found" if 'class="title-sub mono"' in html else "MISSING")),

        ("T151-H34 .project-cell with path-tooltip",
         lambda: ('class="project-cell"' in html and 'class="path-tooltip"' in html,
                  "project-cell with path-tooltip found"
                  if ('class="project-cell"' in html and 'class="path-tooltip"' in html)
                  else "MISSING")),

        ("T151-H35 tokenbar in token cells",
         lambda: ('class="tokenbar"' in html,
                  "tokenbar found" if 'class="tokenbar"' in html else "MISSING")),

        ("T151-H36 .badge.err for non-zero failed",
         lambda: ('class="badge err"' in html,
                  "badge err found" if 'class="badge err"' in html else "MISSING")),

        ("T151-H37 data-action=\"open-session\" on rows",
         lambda: ('data-action="open-session"' in html,
                  "open-session found" if 'data-action="open-session"' in html else "MISSING")),

        # ── Pagination ─────────────────────────────────────────────
        ("T151-H38 .unified-pagination present",
         lambda: ('class="pagination unified-pagination"' in html
                  or 'unified-pagination' in html,
                  "unified-pagination found"
                  if ('class="pagination unified-pagination"' in html
                      or 'unified-pagination' in html)
                  else "MISSING")),

        ("T151-H39 data-action=\"page-input\"",
         lambda: ('data-action="page-input"' in html,
                  "page-input found" if 'data-action="page-input"' in html else "MISSING")),

        ("T151-H40 data-action=\"prev-page\"",
         lambda: ('data-action="prev-page"' in html,
                  "prev-page found" if 'data-action="prev-page"' in html else "MISSING")),

        ("T151-H41 data-action=\"next-page\"",
         lambda: ('data-action="next-page"' in html,
                  "next-page found" if 'data-action="next-page"' in html else "MISSING")),

        ("T151-H42 role=\"navigation\" on pagination nav",
         lambda: ('role="navigation"' in html,
                  "role=navigation found" if 'role="navigation"' in html else "MISSING")),

        ("T151-H43 aria-label on page input",
         lambda: ('aria-label="Page number"' in html,
                  "aria-label=Page number found" if 'aria-label="Page number"' in html else "MISSING")),

        # ── Empty/Error states ─────────────────────────────────────
        ("T151-H44 ui.empty_state( present",
         lambda: ("ui.empty_state(" in html,
                  "empty_state found" if "ui.empty_state(" in html else "MISSING")),

        ("T151-H45 ui.button( present in empty state",
         lambda: ("ui.button(" in html,
                  "button macro found" if "ui.button(" in html else "MISSING")),

        ("T151-H46 ui.error_state( present",
         lambda: ("ui.error_state(" in html,
                  "error_state found" if "ui.error_state(" in html else "MISSING")),

        # ── data-action coverage ───────────────────────────────────
        ("T151-H47 data-action: back",
         lambda: ('data-action="back"' in html,
                  "back found" if 'data-action="back"' in html else "MISSING")),

        ("T151-H48 data-action: info",
         lambda: ('data-action="info"' in html,
                  "info found" if 'data-action="info"' in html else "MISSING")),

        ("T151-H49 data-action: sort",
         lambda: ('data-action="sort"' in html,
                  "sort found" if 'data-action="sort"' in html else "MISSING")),

        ("T151-H50 data-action: open-session",
         lambda: ('data-action="open-session"' in html,
                  "open-session found" if 'data-action="open-session"' in html else "MISSING")),

        ("T151-H51 data-action: page-input",
         lambda: ('data-action="page-input"' in html,
                  "page-input found" if 'data-action="page-input"' in html else "MISSING")),

        ("T151-H52 data-action: prev-page",
         lambda: ('data-action="prev-page"' in html,
                  "prev-page found" if 'data-action="prev-page"' in html else "MISSING")),

        ("T151-H53 data-action: next-page",
         lambda: ('data-action="next-page"' in html,
                  "next-page found" if 'data-action="next-page"' in html else "MISSING")),

        ("T151-H54 data-action: refresh (in error state)",
         lambda: ('data_action=\'refresh\'' in html or 'data-action="refresh"' in html,
                  "refresh found" if ('data_action=\'refresh\'' in html or 'data-action="refresh"' in html) else "MISSING")),

        # ── Accessibility ──────────────────────────────────────────
        ("T151-H55 aria-hidden=\"true\" on emoji spans",
         lambda: ('aria-hidden="true"' in html,
                  "aria-hidden found" if 'aria-hidden="true"' in html else "MISSING")),

        ("T151-H56 aria-label on search input",
         lambda: ('aria-label="Search sessions"' in html,
                  "aria-label=Search sessions found" if 'aria-label="Search sessions"' in html else "MISSING")),

        ("T151-H57 aria-label on pagination",
         lambda: ('aria-label="Agent sessions pagination"' in html,
                  "aria-label=Agent sessions pagination found"
                  if 'aria-label="Agent sessions pagination"' in html else "MISSING")),

        ("T151-H58 title on info icons",
         lambda: ('title="Total sessions for this agent"' in html,
                  "title on info icon found"
                  if 'title="Total sessions for this agent"' in html else "MISSING")),

        ("T151-H59 aria-label on metric info buttons",
         lambda: (html.count('aria-label="') >= 3,
                  f'{html.count("aria-label=")} aria-label attribute(s) found'
                  if html.count('aria-label="') >= 3 else "INSUFFICIENT aria-labels")),

        # ── Stale patterns ─────────────────────────────────────────
        ("T151-H60 No stale patterns: no page-header, no hero, no legacy-, no onclick",
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
        print("PASS: agent-detail HTML QA checks")
        return 0
    else:
        print("FAIL: agent-detail HTML QA checks -- see details above")
        return 1


def _check_js_syntax(js: str) -> tuple[bool, str]:
    """Basic JS syntax check via balanced braces/parens/brackets."""
    if not js:
        return (False, "agents.js is empty or missing")

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
        "data-action",
    ]
    missing_markers = [m for m in essential_markers if m not in js]
    if missing_markers:
        return (False, f"balanced but missing markers: {', '.join(missing_markers)}")

    return (True, f"balanced braces/parens/brackets, {len(js)} bytes, all structural markers present")


if __name__ == "__main__":
    raise SystemExit(main())
