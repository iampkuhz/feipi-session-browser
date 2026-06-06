#!/usr/bin/env python3
"""T081 — Static QA for sessions-list page HTML structure.

Validates sessions.html and sessions_list_components.html against
the page behavior contract (tests/acceptance/ui/behavior-sessions.md):

1. Filter form: search input, agent/model/project selects, Apply button
2. Active filters region with chip structure
3. Table: column headers, sortable columns, token bar, pagination
4. Row click: data-action="row" on tbody rows
5. Pagination: prev/next buttons, page input, page-status spans
6. No inline style/script/onclick in sessions.html
7. Token bar segment classes present

Run from repo root:
  python scripts/qa/ui/check_sessions_list_html.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SESSIONS_HTML = ROOT / "src/session_browser/web/templates/sessions.html"
COMPONENTS = ROOT / "src/session_browser/web/templates/components/sessions_list_components.html"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def main() -> int:
    sessions = read(SESSIONS_HTML)
    components = read(COMPONENTS)
    combined = sessions + "\n" + components

    checks: list[tuple[str, callable]] = [
        ("T081-H01 sessions.html exists", lambda: (SESSIONS_HTML.exists(), "exists" if SESSIONS_HTML.exists() else "MISSING")),
        ("T081-H02 sessions_list_components.html exists", lambda: (COMPONENTS.exists(), "exists" if COMPONENTS.exists() else "MISSING")),

        # Filter form
        ("T081-H03 Filter form present", lambda: ('id="session-filter-form"' in sessions, "form#session-filter-form found" if 'id="session-filter-form"' in sessions else "form#session-filter-form NOT FOUND")),
        ("T081-H04 Search input present", lambda: ('id="session-search"' in sessions, "search input found" if 'id="session-search"' in sessions else "search input NOT FOUND")),
        ("T081-H05 Agent select present", lambda: ('id="filter-agent"' in sessions, "agent select found" if 'id="filter-agent"' in sessions else "agent select NOT FOUND")),
        ("T081-H06 Model select present", lambda: ('id="filter-model"' in sessions, "model select found" if 'id="filter-model"' in sessions else "model select NOT FOUND")),
        ("T081-H07 Project select present", lambda: ('id="filter-project"' in sessions, "project select found" if 'id="filter-project"' in sessions else "project select NOT FOUND")),
        ("T081-H08 Apply button present", lambda: ("data_action='apply'" in sessions or 'data_action="apply"' in sessions, "apply button found" if ("data_action='apply'" in sessions or 'data_action="apply"' in sessions) else "apply button NOT FOUND")),

        # Active filters
        ("T081-H09 Active filters macro present", lambda: ("active_filters" in components or "active-filters" in sessions, "active filters found" if ("active_filters" in components or "active-filters" in sessions) else "active filters NOT FOUND")),

        # Table
        ("T081-H10 Data table present", lambda: ('class="data-table"' in sessions, "data-table found" if 'class="data-table"' in sessions else "data-table NOT FOUND")),
        ("T081-H11 Sortable columns present", lambda: (sessions.count('data-action="sort"') >= 4, f'{sessions.count("data-action=\"sort\"")} sortable columns found')),
        ("T081-H12 Token bar segments present", lambda: ("tokenbar-seg fresh" in sessions and "tokenbar-seg out" in sessions, "tokenbar segments found")),

        # Row click
        ("T081-H13 Row click action present", lambda: ('data-action="row"' in sessions, "data-action=row found" if 'data-action="row"' in sessions else "data-action=row NOT FOUND")),

        # Pagination
        ("T081-H14 Pagination prev button", lambda: ('data-action="prev-page"' in sessions or 'data-action="prev"' in sessions, "prev button found")),
        ("T081-H15 Pagination next button", lambda: ('data-action="next-page"' in sessions or 'data-action="next"' in sessions, "next button found")),
        ("T081-H16 Pagination page input", lambda: ('data-action="page-input"' in sessions, "page input found")),
        ("T081-H17 Pagination page-status", lambda: ("page-status" in sessions, "page-status spans found")),

        # No inline style/script
        ("T081-H18 No inline <style> blocks", lambda: (not bool(re.search(r'<style>(?!.*mhtml)', sessions, re.DOTALL)), "clean" if not re.search(r'<style>(?!.*mhtml)', sessions, re.DOTALL) else "INLINE STYLE FOUND")),
        ("T081-H19 No inline <script> (non-JSON)", lambda: (
            not bool(re.findall(r'<script(?![^>]*type="application/json")[^>]*>[^<]', sessions)),
            "clean" if not re.findall(r'<script(?![^>]*type="application/json")[^>]*>[^<]', sessions) else "INLINE SCRIPT FOUND"
        )),
        ("T081-H20 No inline onclick", lambda: ("onclick=" not in sessions, "clean" if "onclick=" not in sessions else "INLINE ONCLICK FOUND")),

        # data-action coverage
        ("T081-H21 data-action coverage (clear, row, sort)", lambda: (
            ("data_action='clear'" in sessions or 'data_action="clear"' in sessions) and
            'data-action="row"' in sessions and
            'data-action="sort"' in sessions,
            "all present" if all(x in sessions for x in ["data_action='clear'", 'data-action="row"', 'data-action="sort"']) else "MISSING some"
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
        print("PASS: sessions-list HTML QA checks")
        return 0
    else:
        print("FAIL: sessions-list HTML QA checks — see details above")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
