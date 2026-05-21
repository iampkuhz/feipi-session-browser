#!/usr/bin/env python3
"""T123 -- Static QA for project detail page HTML structure.

Validates project.html against the page behavior contract:

1. File existence: project.html exists
2. Template structure: extends base.html, active_page set, ui_primitives imported
3. No inline: no onclick, no inline <script> (except application/json), no inline <style>
4. CSS/JS imports: projects.css and projects.js imported
5. Page head: .page-head section, back-btn with href="/projects", h1, .path-row, .path-chip, .subtitle
6. Metric cards: 4 cards with .card.metric, each has .metric-icon (emoji aria-hidden), .metric-label, .metric-value, info button with data-action="info"
7. Info buttons: 5 info buttons with data-action="info" and aria-label
8. Table toolbar: .table-toolbar, .card-title, .card-sub, search input with data-action="search"
9. Table structure: id="project-sessions-table", 9 column headers, sortable headers with data-action="sort" and data-sort for tokens/rounds/tools/failed/duration/updated
10. Row structure: data-action="open-session", data-href, .title-main, .title-sub, copy-session with data-action, agent badges (.badge.cc/.cx/.qd + .dot), .token-cell with .token-total and .tokenbar (fresh/read/write/out segments)
11. Pagination: nav with role="navigation", data-action="page-input", data-action="next-page", page-status, aria-label
12. Empty state: ui.empty_state macro present, "No sessions" text, data-action="view-all"
13. Error state: ui.error_state macro present, data-action="go-projects", href="/projects"
14. data-action coverage: verify all expected data-action values exist

Run from repo root:
  python scripts/qa/ui/check_project_detail_html.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PROJECT_HTML = ROOT / "src/session_browser/web/templates/project.html"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def main() -> int:
    html = read(PROJECT_HTML)

    checks: list[tuple[str, callable]] = [
        # ── 1. File existence ──────────────────────────────────────
        ("T123-H01 project.html exists",
         lambda: (PROJECT_HTML.exists(),
                  "exists" if PROJECT_HTML.exists() else "MISSING")),

        # ── 2. Template structure ──────────────────────────────────
        ("T123-H02 extends base.html",
         lambda: ('{% extends "base.html" %}' in html,
                  "extends base.html found" if '{% extends "base.html" %}' in html else "MISSING")),
        ("T123-H03 active_page set to projects",
         lambda: ("{% set active_page = 'projects' %}" in html,
                  "active_page='projects' found" if "{% set active_page = 'projects' %}" in html else "MISSING")),
        ("T123-H04 ui_primitives imported",
         lambda: ('{% import "components/ui_primitives.html" as ui %}' in html,
                  "ui_primitives imported" if '{% import "components/ui_primitives.html" as ui %}' in html else "MISSING")),

        # ── 3. No inline style/script/onclick ──────────────────────
        ("T123-H05 No inline <style> blocks",
         lambda: (not bool(re.search(r'<style>', html)),
                  "clean" if not re.search(r'<style>', html) else "INLINE STYLE FOUND")),
        ("T123-H06 No inline <script> (non-JSON)",
         lambda: (
             not bool(re.findall(r'<script(?![^>]*type="application/json")[^>]*>[^<]', html)),
             "clean" if not re.findall(r'<script(?![^>]*type="application/json")[^>]*>[^<]', html) else "INLINE SCRIPT FOUND"
         )),
        ("T123-H07 No inline onclick",
         lambda: ("onclick=" not in html,
                  "clean" if "onclick=" not in html else "INLINE ONCLICK FOUND")),

        # ── 4. CSS/JS imports ──────────────────────────────────────
        ("T123-H08 projects.css imported",
         lambda: ('href="/static/css/projects.css"' in html,
                  "projects.css found" if 'href="/static/css/projects.css"' in html else "MISSING")),
        ("T123-H09 projects.js imported",
         lambda: ('src="/static/js/projects.js"' in html,
                  "projects.js found" if 'src="/static/js/projects.js"' in html else "MISSING")),

        # ── 5. Page head ───────────────────────────────────────────
        ("T123-H10 .page-head section present",
         lambda: ('class="page-head"' in html,
                  "page-head found" if 'class="page-head"' in html else "MISSING")),
        ("T123-H11 back-btn with href=/projects",
         lambda: ('href="/projects" class="back-btn"' in html or 'class="back-btn" href="/projects"' in html,
                  "back-btn found" if ('href="/projects" class="back-btn"' in html or 'class="back-btn" href="/projects"' in html) else "MISSING")),
        ("T123-H12 h1 in page-head",
         lambda: ("<h1>" in html,
                  "h1 found" if "<h1>" in html else "MISSING")),
        ("T123-H13 .path-row present",
         lambda: ('class="path-row"' in html,
                  "path-row found" if 'class="path-row"' in html else "MISSING")),
        ("T123-H14 .path-chip present",
         lambda: ('class="path-chip' in html,
                  "path-chip found" if 'class="path-chip' in html else "MISSING")),
        ("T123-H15 .subtitle present",
         lambda: ('class="subtitle"' in html,
                  "subtitle found" if 'class="subtitle"' in html else "MISSING")),

        # ── 6. Metric cards ────────────────────────────────────────
        ("T123-H16 4 metric cards (card metric)",
         lambda: (html.count('class="card metric"') >= 4,
                  f'{html.count("class=\"card metric\"")} card metric(s) found' if html.count('class="card metric"') >= 4 else f"ONLY {html.count('class=\"card metric\"')} card metric(s)")),
        ("T123-H17 metric-icon with emoji aria-hidden",
         lambda: ('class="metric-icon' in html and 'aria-hidden="true"' in html,
                  "metric-icon with aria-hidden found" if 'class="metric-icon' in html and 'aria-hidden="true"' in html else "MISSING")),
        ("T123-H18 metric-label present",
         lambda: ('class="metric-label"' in html,
                  "metric-label found" if 'class="metric-label"' in html else "MISSING")),
        ("T123-H19 metric-value present",
         lambda: ('class="metric-value' in html,
                  "metric-value found" if 'class="metric-value' in html else "MISSING")),

        # ── 7. Info buttons ────────────────────────────────────────
        ("T123-H20 data-action=info buttons count >= 5",
         lambda: (html.count('data-action="info"') >= 5,
                  f'{html.count("data-action=\"info\"")} info button(s) found' if html.count('data-action="info"') >= 5 else f"ONLY {html.count('data-action=\"info\"')} info button(s)")),
        ("T123-H21 info buttons have aria-label",
         lambda: (html.count('data-action="info"') <= html.count('aria-label="'),
                  "info buttons with aria-label found" if html.count('data-action="info"') <= html.count('aria-label="') else "MISSING aria-label on info buttons")),

        # ── 8. Table toolbar ───────────────────────────────────────
        ("T123-H22 .table-toolbar present",
         lambda: ('class="table-toolbar"' in html,
                  "table-toolbar found" if 'class="table-toolbar"' in html else "MISSING")),
        ("T123-H23 .card-title present",
         lambda: ('class="card-title"' in html,
                  "card-title found" if 'class="card-title"' in html else "MISSING")),
        ("T123-H24 .card-sub present",
         lambda: ('class="card-sub"' in html,
                  "card-sub found" if 'class="card-sub"' in html else "MISSING")),
        ("T123-H25 search input with data-action=search",
         lambda: ('data-action="search"' in html,
                  "search action found" if 'data-action="search"' in html else "MISSING")),

        # ── 9. Table structure ─────────────────────────────────────
        ("T123-H26 id=project-sessions-table",
         lambda: ('id="project-sessions-table"' in html,
                  "project-sessions-table id found" if 'id="project-sessions-table"' in html else "MISSING")),
        ("T123-H27 9 column headers",
         lambda: (
             all(x in html for x in [
                 "<th>Title</th>",
                 "<th>Agent</th>",
                 "<th>Model</th>",
                 "Tokens",
                 "Rounds",
                 "Tools",
                 "Failed",
                 "Duration",
                 "Updated",
             ]),
             "all 9 columns found" if all(x in html for x in [
                 "<th>Title</th>", "<th>Agent</th>", "<th>Model</th>",
                 "Tokens", "Rounds", "Tools", "Failed", "Duration", "Updated",
             ]) else "MISSING column headers"
         )),
        ("T123-H28 sortable headers (data-action=sort)",
         lambda: (html.count('data-action="sort"') >= 6,
                  f'{html.count("data-action=\"sort\"")} sortable header(s) found' if html.count('data-action="sort"') >= 6 else f"ONLY {html.count('data-action=\"sort\"')} sortable header(s)")),
        ("T123-H29 data-sort=tokens",
         lambda: ('data-sort="tokens"' in html,
                  "data-sort=tokens found" if 'data-sort="tokens"' in html else "MISSING")),
        ("T123-H30 data-sort=rounds",
         lambda: ('data-sort="rounds"' in html,
                  "data-sort=rounds found" if 'data-sort="rounds"' in html else "MISSING")),
        ("T123-H31 data-sort=tools",
         lambda: ('data-sort="tools"' in html,
                  "data-sort=tools found" if 'data-sort="tools"' in html else "MISSING")),
        ("T123-H32 data-sort=failed",
         lambda: ('data-sort="failed"' in html,
                  "data-sort=failed found" if 'data-sort="failed"' in html else "MISSING")),
        ("T123-H33 data-sort=duration",
         lambda: ('data-sort="duration"' in html,
                  "data-sort=duration found" if 'data-sort="duration"' in html else "MISSING")),
        ("T123-H34 data-sort=updated",
         lambda: ('data-sort="updated"' in html,
                  "data-sort=updated found" if 'data-sort="updated"' in html else "MISSING")),

        # ── 10. Row structure ──────────────────────────────────────
        ("T123-H35 data-action=open-session",
         lambda: ('data-action="open-session"' in html,
                  "open-session found" if 'data-action="open-session"' in html else "MISSING")),
        ("T123-H36 data-href on rows",
         lambda: ('data-href="/sessions/' in html,
                  "data-href found" if 'data-href="/sessions/' in html else "MISSING")),
        ("T123-H37 .title-main present",
         lambda: ('class="title-main"' in html,
                  "title-main found" if 'class="title-main"' in html else "MISSING")),
        ("T123-H38 .title-sub present",
         lambda: ('class="title-sub' in html,
                  "title-sub found" if 'class="title-sub' in html else "MISSING")),
        ("T123-H39 copy-session with data-action",
         lambda: ('data-action="copy-session"' in html,
                  "copy-session found" if 'data-action="copy-session"' in html else "MISSING")),
        ("T123-H40 badge cc",
         lambda: ('class="badge cc"' in html,
                  "badge cc found" if 'class="badge cc"' in html else "MISSING")),
        ("T123-H41 badge dynamic agent class (dot class varies cc/cx/qd)",
         lambda: ('class="dot ' in html and "'claude'" in html and "'qoder'" in html and "'codex'" in html,
                  "dynamic dot class found with claude/qoder/codex variants" if ('class="dot ' in html and "'claude'" in html and "'qoder'" in html and "'codex'" in html) else "MISSING")),
        ("T123-H42 CC/CX/QD labels in row",
         lambda: ("'CC'" in html and "'CX'" in html and "'QD'" in html,
                  "CC/CX/QD labels found" if ("'CC'" in html and "'CX'" in html and "'QD'" in html) else "MISSING")),
        ("T123-H43 dot class for agent indicator",
         lambda: ('class="dot ' in html,
                  "dot class found" if 'class="dot ' in html else "MISSING")),
        ("T123-H44 .token-cell present",
         lambda: ('class="token-cell"' in html,
                  "token-cell found" if 'class="token-cell"' in html else "MISSING")),
        ("T123-H45 .token-total present",
         lambda: ('class="token-total"' in html,
                  "token-total found" if 'class="token-total"' in html else "MISSING")),
        ("T123-H46 .tokenbar present",
         lambda: ('class="tokenbar"' in html,
                  "tokenbar found" if 'class="tokenbar"' in html else "MISSING")),
        ("T123-H47 tokenbar-seg fresh",
         lambda: ('class="tokenbar-seg fresh"' in html,
                  "fresh segment found" if 'class="tokenbar-seg fresh"' in html else "MISSING")),
        ("T123-H48 tokenbar-seg read",
         lambda: ('class="tokenbar-seg read"' in html,
                  "read segment found" if 'class="tokenbar-seg read"' in html else "MISSING")),
        ("T123-H49 tokenbar-seg write",
         lambda: ('class="tokenbar-seg write"' in html,
                  "write segment found" if 'class="tokenbar-seg write"' in html else "MISSING")),
        ("T123-H50 tokenbar-seg out",
         lambda: ('class="tokenbar-seg out"' in html,
                  "out segment found" if 'class="tokenbar-seg out"' in html else "MISSING")),

        # ── 11. Pagination ─────────────────────────────────────────
        ("T123-H51 nav with role=navigation",
         lambda: ('role="navigation"' in html,
                  "role=navigation found" if 'role="navigation"' in html else "MISSING")),
        ("T123-H52 data-action=page-input",
         lambda: ('data-action="page-input"' in html,
                  "page-input found" if 'data-action="page-input"' in html else "MISSING")),
        ("T123-H53 data-action=next-page",
         lambda: ('data-action="next-page"' in html,
                  "next-page found" if 'data-action="next-page"' in html else "MISSING")),
        ("T123-H54 page-status present",
         lambda: ('class="page-status"' in html,
                  "page-status found" if 'class="page-status"' in html else "MISSING")),
        ("T123-H55 aria-label on pagination",
         lambda: ('aria-label="Page number"' in html,
                  "aria-label found" if 'aria-label="Page number"' in html else "MISSING")),

        # ── 12. Empty state ────────────────────────────────────────
        ("T123-H56 ui.empty_state macro present",
         lambda: ("ui.empty_state(" in html,
                  "empty_state found" if "ui.empty_state(" in html else "MISSING")),
        ("T123-H57 No sessions text present",
         lambda: ("No sessions" in html,
                  "No sessions text found" if "No sessions" in html else "MISSING")),
        ("T123-H58 data-action=view-all (Jinja2 data_action)",
         lambda: ("data_action='view-all'" in html or 'data_action="view-all"' in html,
                  "view-all found" if ("data_action='view-all'" in html or 'data_action="view-all"' in html) else "MISSING")),

        # ── 13. Error state ────────────────────────────────────────
        ("T123-H59 ui.error_state macro present",
         lambda: ("ui.error_state(" in html,
                  "error_state found" if "ui.error_state(" in html else "MISSING")),
        ("T123-H60 data-action=go-projects",
         lambda: ('data_action=\'go-projects\'' in html or 'data-action="go-projects"' in html,
                  "go-projects found" if ('data_action=\'go-projects\'' in html or 'data-action="go-projects"' in html) else "MISSING")),
        ("T123-H61 href=/projects in error state",
         lambda: ("href='/projects'" in html,
                  "href=/projects found" if "href='/projects'" in html else "MISSING")),

        # ── 14. data-action coverage ───────────────────────────────
        ("T123-H62 data-action coverage (sort, open-session, copy, pagination, info, search)",
         lambda: (
             all(x in html for x in [
                 'data-action="sort"',
                 'data-action="open-session"',
                 'data-action="copy-session"',
                 'data-action="page-input"',
                 'data-action="next-page"',
                 'data-action="info"',
                 'data-action="search"',
             ])
             and ("data_action='view-all'" in html or 'data_action="view-all"' in html)
             and ('data-action="copy-path"' in html),
             "all covered" if (
                 all(x in html for x in [
                     'data-action="sort"',
                     'data-action="open-session"',
                     'data-action="copy-session"',
                     'data-action="page-input"',
                     'data-action="next-page"',
                     'data-action="info"',
                     'data-action="search"',
                 ])
                 and ("data_action='view-all'" in html or 'data_action="view-all"' in html)
                 and ('data-action="copy-path"' in html)
             ) else "MISSING some data-action values"
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
        print("PASS: project-detail HTML QA checks")
        return 0
    else:
        print("FAIL: project-detail HTML QA checks -- see details above")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
