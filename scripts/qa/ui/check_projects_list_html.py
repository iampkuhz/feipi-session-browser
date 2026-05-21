#!/usr/bin/env python3
"""T109 — Static QA for projects-list page HTML structure.

Validates projects.html against the page behavior contract:

1. File existence: projects.html exists
2. Template structure: extends base.html, active_page set, ui_primitives imported
3. No inline: no onclick, no inline <script> (except application/json), no inline <style>
4. CSS/JS imports: projects.css and projects.js imported
5. Page head: .page-head with h1, subtitle text
6. Metric grid: 4 metric cards, each with metric-icon, metric-label, metric-value
7. Info buttons: data-action="metric-info" with data-metric attributes
8. Filter card: filter-card class, search input with data-search, Apply/Clear buttons
9. Active filters: active-filters region with filter-chip
10. Table: data-table class, 6 column headers
11. Sortable headers: data-action="sort" with data-sort for sessions, tokens, tools, last_active
12. Table toolbar: table-toolbar, table-title, table-note
13. Row structure: data-action="open-project", open-project-link, copy-project-path, clipboard-text
14. Agent badges: badge cc/cx/qd classes with dot claude/codex/qoder
15. Token bar: tokenbar class with 4 segment classes, tooltip present
16. Pagination: nav with role="navigation", data-action="page-input", data-action="next-page"
17. Empty states: empty_state macro, error_state macro, state-strip class
18. data-action coverage: verify all expected data-action values exist

Run from repo root:
  python scripts/qa/ui/check_projects_list_html.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PROJECTS_HTML = ROOT / "src/session_browser/web/templates/projects.html"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def main() -> int:
    html = read(PROJECTS_HTML)

    checks: list[tuple[str, callable]] = [
        # ── 1. File existence ──────────────────────────────────────
        ("T109-H01 projects.html exists",
         lambda: (PROJECTS_HTML.exists(),
                  "exists" if PROJECTS_HTML.exists() else "MISSING")),

        # ── 2. Template structure ──────────────────────────────────
        ("T109-H02 extends base.html",
         lambda: ('{% extends "base.html" %}' in html,
                  "extends base.html found" if '{% extends "base.html" %}' in html else "MISSING")),
        ("T109-H03 active_page set to projects",
         lambda: ("{% set active_page = 'projects' %}" in html,
                  "active_page='projects' found" if "{% set active_page = 'projects' %}" in html else "MISSING")),
        ("T109-H04 ui_primitives imported",
         lambda: ('{% import "components/ui_primitives.html" as ui %}' in html,
                  "ui_primitives imported" if '{% import "components/ui_primitives.html" as ui %}' in html else "MISSING")),

        # ── 3. No inline style/script/onclick ──────────────────────
        ("T109-H05 No inline <style> blocks",
         lambda: (not bool(re.search(r'<style>', html)),
                  "clean" if not re.search(r'<style>', html) else "INLINE STYLE FOUND")),
        ("T109-H06 No inline <script> (non-JSON)",
         lambda: (
             not bool(re.findall(r'<script(?![^>]*type="application/json")[^>]*>[^<]', html)),
             "clean" if not re.findall(r'<script(?![^>]*type="application/json")[^>]*>[^<]', html) else "INLINE SCRIPT FOUND"
         )),
        ("T109-H07 No inline onclick",
         lambda: ("onclick=" not in html,
                  "clean" if "onclick=" not in html else "INLINE ONCLICK FOUND")),

        # ── 4. CSS/JS imports ──────────────────────────────────────
        ("T109-H08 projects.css imported",
         lambda: ('href="/static/css/projects.css"' in html,
                  "projects.css found" if 'href="/static/css/projects.css"' in html else "MISSING")),
        ("T109-H09 projects.js imported",
         lambda: ('src="/static/js/projects.js"' in html,
                  "projects.js found" if 'src="/static/js/projects.js"' in html else "MISSING")),

        # ── 5. Page head ───────────────────────────────────────────
        ("T109-H10 .page-head present",
         lambda: ('class="page-head"' in html,
                  "page-head found" if 'class="page-head"' in html else "MISSING")),
        ("T109-H11 h1 in page-head",
         lambda: ("<h1>Projects</h1>" in html,
                  "h1 found" if "<h1>Projects</h1>" in html else "MISSING")),
        ("T109-H12 Subtitle text present",
         lambda: ("<p>Indexed local workspaces</p>" in html,
                  "subtitle found" if "<p>Indexed local workspaces</p>" in html else "MISSING")),

        # ── 6. Metric grid ─────────────────────────────────────────
        ("T109-H13 metric-grid present",
         lambda: ('class="metric-grid"' in html,
                  "metric-grid found" if 'class="metric-grid"' in html else "MISSING")),
        ("T109-H14 4 metric cards",
         lambda: (html.count('class="metric-card"') >= 4,
                  f'{html.count("class=\"metric-card\"")} metric-card(s) found' if html.count('class="metric-card"') >= 4 else f"ONLY {html.count('class=\"metric-card\"')} metric-card(s)")),
        ("T109-H15 metric-icon present in cards",
         lambda: ('class="metric-icon' in html,
                  "metric-icon found" if 'class="metric-icon' in html else "MISSING")),
        ("T109-H16 metric-label present in cards",
         lambda: ('class="metric-label"' in html,
                  "metric-label found" if 'class="metric-label"' in html else "MISSING")),
        ("T109-H17 metric-value present in cards",
         lambda: ('class="metric-value' in html,
                  "metric-value found" if 'class="metric-value' in html else "MISSING")),

        # ── 7. Info buttons ────────────────────────────────────────
        ("T109-H18 metric-info buttons present",
         lambda: (html.count('data-action="metric-info"') >= 4,
                  f'{html.count("data-action=\"metric-info\"")} metric-info button(s) found')),
        ("T109-H19 data-metric: projects-count",
         lambda: ('data-metric="projects-count"' in html,
                  "data-metric=projects-count found" if 'data-metric="projects-count"' in html else "MISSING")),
        ("T109-H20 data-metric: total-sessions",
         lambda: ('data-metric="total-sessions"' in html,
                  "data-metric=total-sessions found" if 'data-metric="total-sessions"' in html else "MISSING")),
        ("T109-H21 data-metric: total-tokens",
         lambda: ('data-metric="total-tokens"' in html,
                  "data-metric=total-tokens found" if 'data-metric="total-tokens"' in html else "MISSING")),
        ("T109-H22 data-metric: failed-tools",
         lambda: ('data-metric="failed-tools"' in html,
                  "data-metric=failed-tools found" if 'data-metric="failed-tools"' in html else "MISSING")),

        # ── 8. Filter card ─────────────────────────────────────────
        ("T109-H23 filter-card present",
         lambda: ('class="card filter-card"' in html,
                  "filter-card found" if 'class="card filter-card"' in html else "MISSING")),
        ("T109-H24 Search input with data-search",
         lambda: ('data-search="project-name"' in html,
                  "data-search found" if 'data-search="project-name"' in html else "MISSING")),
        ("T109-H25 Apply button",
         lambda: ('data-action="apply-search"' in html,
                  "apply-search button found" if 'data-action="apply-search"' in html else "MISSING")),
        ("T109-H26 Clear button",
         lambda: ('data-action="clear-search"' in html,
                  "clear-search button found" if 'data-action="clear-search"' in html else "MISSING")),

        # ── 9. Active filters ──────────────────────────────────────
        ("T109-H27 active-filters region",
         lambda: ('class="active-filters"' in html,
                  "active-filters found" if 'class="active-filters"' in html else "MISSING")),
        ("T109-H28 filter-chip present",
         lambda: ('class="filter-chip"' in html,
                  "filter-chip found" if 'class="filter-chip"' in html else "MISSING")),

        # ── 10. Table ──────────────────────────────────────────────
        ("T109-H29 data-table present",
         lambda: ('class="data-table"' in html,
                  "data-table found" if 'class="data-table"' in html else "MISSING")),
        ("T109-H30 6 column headers",
         lambda: (
             all(x in html for x in [
                 "<th>Project</th>",
                 "<th>Agents</th>",
                 "Sessions",
                 "Tokens",
                 "Tools",
                 "Last Active",
             ]),
             "all 6 columns found" if all(x in html for x in [
                 "<th>Project</th>", "<th>Agents</th>",
                 "Sessions", "Tokens", "Tools", "Last Active",
             ]) else "MISSING column headers"
         )),

        # ── 11. Sortable headers ───────────────────────────────────
        ("T109-H31 Sortable headers (data-action=sort)",
         lambda: (html.count('data-action="sort"') >= 4,
                  f'{html.count("data-action=\"sort\"")} sortable header(s) found')),
        ("T109-H32 data-sort=sessions",
         lambda: ('data-sort="sessions"' in html,
                  "data-sort=sessions found" if 'data-sort="sessions"' in html else "MISSING")),
        ("T109-H33 data-sort=tokens",
         lambda: ('data-sort="tokens"' in html,
                  "data-sort=tokens found" if 'data-sort="tokens"' in html else "MISSING")),
        ("T109-H34 data-sort=tools",
         lambda: ('data-sort="tools"' in html,
                  "data-sort=tools found" if 'data-sort="tools"' in html else "MISSING")),
        ("T109-H35 data-sort=last_active",
         lambda: ('data-sort="last_active"' in html,
                  "data-sort=last_active found" if 'data-sort="last_active"' in html else "MISSING")),

        # ── 12. Table toolbar ──────────────────────────────────────
        ("T109-H36 table-toolbar present",
         lambda: ('class="table-toolbar"' in html,
                  "table-toolbar found" if 'class="table-toolbar"' in html else "MISSING")),
        ("T109-H37 table-title present",
         lambda: ('class="table-title"' in html,
                  "table-title found" if 'class="table-title"' in html else "MISSING")),
        ("T109-H38 table-note present",
         lambda: ('class="table-note"' in html,
                  "table-note found" if 'class="table-note"' in html else "MISSING")),

        # ── 13. Row structure ──────────────────────────────────────
        ("T109-H39 data-action=open-project",
         lambda: ('data-action="open-project"' in html,
                  "open-project found" if 'data-action="open-project"' in html else "MISSING")),
        ("T109-H40 data-action=open-project-link",
         lambda: ('data-action="open-project-link"' in html,
                  "open-project-link found" if 'data-action="open-project-link"' in html else "MISSING")),
        ("T109-H41 data-action=copy-project-path",
         lambda: ('data-action="copy-project-path"' in html,
                  "copy-project-path found" if 'data-action="copy-project-path"' in html else "MISSING")),
        ("T109-H42 data-clipboard-text present",
         lambda: ('data-clipboard-text="' in html,
                  "data-clipboard-text found" if 'data-clipboard-text="' in html else "MISSING")),

        # ── 14. Agent badges ───────────────────────────────────────
        ("T109-H43 badge cc (Claude Code)",
         lambda: ('class="badge cc"' in html,
                  "badge cc found" if 'class="badge cc"' in html else "MISSING")),
        ("T109-H44 badge cx (Codex)",
         lambda: ('class="badge cx"' in html,
                  "badge cx found" if 'class="badge cx"' in html else "MISSING")),
        ("T109-H45 badge qd (Qoder)",
         lambda: ('class="badge qd"' in html,
                  "badge qd found" if 'class="badge qd"' in html else "MISSING")),
        ("T109-H46 dot claude",
         lambda: ('class="dot claude"' in html,
                  "dot claude found" if 'class="dot claude"' in html else "MISSING")),
        ("T109-H47 dot codex",
         lambda: ('class="dot codex"' in html,
                  "dot codex found" if 'class="dot codex"' in html else "MISSING")),
        ("T109-H48 dot qoder",
         lambda: ('class="dot qoder"' in html,
                  "dot qoder found" if 'class="dot qoder"' in html else "MISSING")),

        # ── 15. Token bar ──────────────────────────────────────────
        ("T109-H49 tokenbar present",
         lambda: ('class="tokenbar"' in html,
                  "tokenbar found" if 'class="tokenbar"' in html else "MISSING")),
        ("T109-H50 tokenbar-seg fresh",
         lambda: ('class="tokenbar-seg fresh"' in html,
                  "fresh segment found" if 'class="tokenbar-seg fresh"' in html else "MISSING")),
        ("T109-H51 tokenbar-seg read",
         lambda: ('class="tokenbar-seg read"' in html,
                  "read segment found" if 'class="tokenbar-seg read"' in html else "MISSING")),
        ("T109-H52 tokenbar-seg write",
         lambda: ('class="tokenbar-seg write"' in html,
                  "write segment found" if 'class="tokenbar-seg write"' in html else "MISSING")),
        ("T109-H53 tokenbar-seg out",
         lambda: ('class="tokenbar-seg out"' in html,
                  "out segment found" if 'class="tokenbar-seg out"' in html else "MISSING")),
        ("T109-H54 Token tooltip present",
         lambda: ('class="tooltip"' in html and 'class="tip-title"' in html,
                  "tooltip found" if 'class="tooltip"' in html and 'class="tip-title"' in html else "MISSING")),

        # ── 16. Pagination ─────────────────────────────────────────
        ("T109-H55 nav with role=navigation",
         lambda: ('role="navigation"' in html,
                  "role=navigation found" if 'role="navigation"' in html else "MISSING")),
        ("T109-H56 page-input present",
         lambda: ('data-action="page-input"' in html,
                  "page-input found" if 'data-action="page-input"' in html else "MISSING")),
        ("T109-H57 next-page button",
         lambda: ('data-action="next-page"' in html,
                  "next-page found" if 'data-action="next-page"' in html else "MISSING")),
        ("T109-H58 page-status present",
         lambda: ('class="page-status"' in html,
                  "page-status found" if 'class="page-status"' in html else "MISSING")),

        # ── 17. Empty/error states ─────────────────────────────────
        ("T109-H59 empty_state macro",
         lambda: ("ui.empty_state(" in html,
                  "empty_state found" if "ui.empty_state(" in html else "MISSING")),
        ("T109-H60 error_state macro",
         lambda: ("ui.error_state(" in html,
                  "error_state found" if "ui.error_state(" in html else "MISSING")),
        ("T109-H61 state-strip present",
         lambda: ('class="state-strip' in html,
                  "state-strip found" if 'class="state-strip' in html else "MISSING")),

        # ── 18. data-action coverage ───────────────────────────────
        ("T109-H62 data-action coverage (sort, open-project, copy, pagination)",
         lambda: (
             all(x in html for x in [
                 'data-action="sort"',
                 'data-action="open-project"',
                 'data-action="open-project-link"',
                 'data-action="copy-project-path"',
                 'data-action="apply-search"',
                 'data-action="clear-search"',
                 'data-action="page-input"',
                 'data-action="next-page"',
                 'data-action="metric-info"',
             ]),
             "all covered" if all(x in html for x in [
                 'data-action="sort"',
                 'data-action="open-project"',
                 'data-action="open-project-link"',
                 'data-action="copy-project-path"',
                 'data-action="apply-search"',
                 'data-action="clear-search"',
                 'data-action="page-input"',
                 'data-action="next-page"',
                 'data-action="metric-info"',
             ]) else "MISSING some data-action values"
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
        print("PASS: projects-list HTML QA checks")
        return 0
    else:
        print("FAIL: projects-list HTML QA checks -- see details above")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
