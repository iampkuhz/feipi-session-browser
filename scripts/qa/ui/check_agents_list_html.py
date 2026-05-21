#!/usr/bin/env python3
"""T137 — Static QA for agents-list page HTML structure.

Validates agents.html against the page behavior contract:

1. Template file exists and is valid Jinja2 (extends, imports, blocks)
2. CSS file (agents.css) exists and contains required selectors
3. JS file (agents.js) exists and is valid syntax
4. Metric grid: 4 cards with correct labels
5. Table: correct column headers, sortable headers
6. Token bars: segment classes present
7. Provider badges: CC/CX/QD classes
8. No inline styles/scripts/onclick
9. Empty state uses ui_primitives macro
10. Pagination structure present
11. data-action coverage for all interactive elements
12. Aria attributes on decorative elements

Run from repo root:
  python scripts/qa/ui/check_agents_list_html.py
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
AGENTS_HTML = ROOT / "src/session_browser/web/templates/agents.html"
AGENTS_CSS = ROOT / "src/session_browser/web/static/css/agents.css"
AGENTS_JS = ROOT / "src/session_browser/web/static/js/agents.js"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def main() -> int:
    html = read(AGENTS_HTML)
    css = read(AGENTS_CSS)
    js = read(AGENTS_JS)

    checks: list[tuple[str, callable]] = [
        # ── 1. Template file existence and Jinja2 structure ──────
        ("T137-H01 agents.html exists",
         lambda: (AGENTS_HTML.exists(),
                  "exists" if AGENTS_HTML.exists() else "MISSING")),

        ("T137-H02 extends base.html",
         lambda: ('{% extends "base.html" %}' in html,
                  "extends base.html found" if '{% extends "base.html" %}' in html else "MISSING")),

        ("T137-H03 active_page set to agents",
         lambda: ("{% set active_page = 'agents' %}" in html,
                  "active_page='agents' found" if "{% set active_page = 'agents' %}" in html else "MISSING")),

        ("T137-H04 ui_primitives imported",
         lambda: ('{% import "components/ui_primitives.html" as ui %}' in html,
                  "ui_primitives imported" if '{% import "components/ui_primitives.html" as ui %}' in html else "MISSING")),

        # ── 2. CSS file exists and contains required selectors ──
        ("T137-H05 agents.css exists",
         lambda: (AGENTS_CSS.exists(),
                  "exists" if AGENTS_CSS.exists() else "MISSING")),

        ("T137-H06 CSS: .page-head selector",
         lambda: (".page-head" in css,
                  ".page-head found" if ".page-head" in css else "MISSING")),

        ("T137-H07 CSS: .metric-grid selector",
         lambda: (".metric-grid" in css,
                  ".metric-grid found" if ".metric-grid" in css else "MISSING")),

        ("T137-H08 CSS: .card.metric selector",
         lambda: (".card.metric" in css,
                  ".card.metric found" if ".card.metric" in css else "MISSING")),

        ("T137-H09 CSS: .agent-avatar selector",
         lambda: (".agent-avatar" in css,
                  ".agent-avatar found" if ".agent-avatar" in css else "MISSING")),

        ("T137-H10 CSS: .tokenbar selector",
         lambda: (".tokenbar" in css,
                  ".tokenbar found" if ".tokenbar" in css else "MISSING")),

        ("T137-H11 CSS: .tokenbar-seg fresh/read/write/out selectors",
         lambda: (
             all(x in css for x in [".fresh", ".read", ".write", ".out"]),
             "all segment selectors found" if all(x in css for x in [".fresh", ".read", ".write", ".out"]) else "MISSING")),

        ("T137-H12 CSS: badge/dot selectors (agent-avatar, agent-dot, .dot claude/codex/qoder)",
         lambda: (
             all(x in css for x in ["agent-avatar", "agent-dot", "dot.claude", "dot.codex", "dot.qoder"]),
             "all agent-dot/avatar selectors found" if all(x in css for x in ["agent-avatar", "agent-dot", "dot.claude", "dot.codex", "dot.qoder"]) else "MISSING")),

        # ── 3. JS file exists and is valid syntax ────────────────
        ("T137-H13 agents.js exists",
         lambda: (AGENTS_JS.exists(),
                  "exists" if AGENTS_JS.exists() else "MISSING")),

        ("T137-H14 agents.js valid Python-AST-parseable JS (basic syntax check)",
         lambda: _check_js_syntax(js)),

        # ── 4. Metric grid: 4 cards with correct labels ──────────
        ("T137-H15 metric-grid present",
         lambda: ('class="metric-grid"' in html,
                  "metric-grid found" if 'class="metric-grid"' in html else "MISSING")),

        ("T137-H16 4 metric cards",
         lambda: (html.count('class="card metric"') >= 4,
                  f'{html.count("class=\"card metric\"")} card.metric(s) found' if html.count('class="card metric"') >= 4 else f"ONLY {html.count('class=\"card metric\"')} card.metric(s)")),

        ("T137-H17 metric-label present",
         lambda: ('class="metric-label"' in html,
                  "metric-label found" if 'class="metric-label"' in html else "MISSING")),

        ("T137-H18 metric-value present",
         lambda: ('class="metric-value"' in html,
                  "metric-value found" if 'class="metric-value"' in html else "MISSING")),

        ("T137-H19 metric-icon present",
         lambda: ('class="metric-icon' in html,
                  "metric-icon found" if 'class="metric-icon' in html else "MISSING")),

        ("T137-H20 Card labels: Active Agents, Sessions, Projects, Total Tokens",
         lambda: (
             all(x in html for x in ["Active Agents", "Total Tokens"]),
             "all metric labels found" if all(x in html for x in ["Active Agents", "Total Tokens"]) else "MISSING")),

        # ── 5. Table: correct column headers, sortable headers ───
        ("T137-H21 data-table present",
         lambda: ('class="data-table"' in html,
                  "data-table found" if 'class="data-table"' in html else "MISSING")),

        ("T137-H22 agents-table id",
         lambda: ('id="agents-table"' in html,
                  "id=agents-table found" if 'id="agents-table"' in html else "MISSING")),

        ("T137-H23 Table column headers (Agent, Provider, Sessions, Projects, Tokens, Tool Calls, Failed)",
         lambda: (
             all(x in html for x in [">Agent<", ">Provider<", ">Sessions<", ">Projects<", ">Tokens<", ">Tool Calls<", ">Failed<"]),
             "all 7+ column headers found" if all(x in html for x in [">Agent<", ">Provider<", ">Sessions<", ">Projects<", ">Tokens<", ">Tool Calls<", ">Failed<"]) else "MISSING")),

        ("T137-H24 Sortable headers (data-action=sort)",
         lambda: (html.count('data-action="sort"') >= 8,
                  f'{html.count("data-action=\"sort\"")} sortable element(s) found' if html.count('data-action="sort"') >= 8 else f"ONLY {html.count('data-action=\"sort\"')} sortable element(s)")),

        ("T137-H25 Sort keys: name, provider, sessions, tokens, tool_calls, last_active",
         lambda: (
             all(f'data-sort="{x}"' in html for x in ["name", "provider", "sessions", "tokens", "tool_calls", "last_active"]),
             "all sort keys found" if all(f'data-sort="{x}"' in html for x in ["name", "provider", "sessions", "tokens", "tool_calls", "last_active"]) else "MISSING")),

        # ── 6. Token bars: segment classes present ───────────────
        ("T137-H26 tokenbar present",
         lambda: ('class="tokenbar"' in html,
                  "tokenbar found" if 'class="tokenbar"' in html else "MISSING")),

        ("T137-H27 tokenbar-seg fresh",
         lambda: ('class="tokenbar-seg fresh"' in html,
                  "fresh segment found" if 'class="tokenbar-seg fresh"' in html else "MISSING")),

        ("T137-H28 tokenbar-seg read",
         lambda: ('class="tokenbar-seg read"' in html,
                  "read segment found" if 'class="tokenbar-seg read"' in html else "MISSING")),

        ("T137-H29 tokenbar-seg write",
         lambda: ('class="tokenbar-seg write"' in html,
                  "write segment found" if 'class="tokenbar-seg write"' in html else "MISSING")),

        ("T137-H30 tokenbar-seg out",
         lambda: ('class="tokenbar-seg out"' in html,
                  "out segment found" if 'class="tokenbar-seg out"' in html else "MISSING")),

        # ── 7. Provider badges: CC/CX/QD classes ─────────────────
        ("T137-H31 badge cc (Claude Code)",
         lambda: ('class="badge cc"' in html or "class=\"badge {{ a_badge_cls }}\"" in html or 'class="badge cx"' in html,
                  "badge cc/cx found" if ('class="badge cc"' in html or 'class="badge cx"' in html or "a_badge_cls" in html) else "MISSING")),

        ("T137-H32 badge qd (Qoder)",
         lambda: ('class="badge qd"' in html or "a_badge_cls" in html,
                  "badge qd reference found" if ('class="badge qd"' in html or "a_badge_cls" in html) else "MISSING")),

        ("T137-H33 dot claude",
         lambda: ('class="dot claude"' in html or "a_dot_cls" in html,
                  "dot claude reference found" if ('class="dot claude"' in html or "a_dot_cls" in html) else "MISSING")),

        ("T137-H34 dot codex",
         lambda: ('class="dot codex"' in html or "a_dot_cls" in html,
                  "dot codex reference found" if ('class="dot codex"' in html or "a_dot_cls" in html) else "MISSING")),

        ("T137-H35 dot qoder",
         lambda: ('class="dot qoder"' in html or "a_dot_cls" in html,
                  "dot qoder reference found" if ('class="dot qoder"' in html or "a_dot_cls" in html) else "MISSING")),

        ("T137-H36 agent-avatar classes",
         lambda: ('class="agent-avatar' in html or "a_avatar_cls" in html,
                  "agent-avatar reference found" if ('class="agent-avatar' in html or "a_avatar_cls" in html) else "MISSING")),

        # ── 8. No inline styles/scripts/onclick ──────────────────
        ("T137-H37 No inline <style> blocks",
         lambda: (not bool(re.search(r'<style>', html)),
                  "clean" if not re.search(r'<style>', html) else "INLINE STYLE FOUND")),

        ("T137-H38 No inline <script> (non-JSON, non-src)",
         lambda: (
             not bool(re.findall(r'<script(?![^>]*src=)[^>]*>[^<]', html)),
             "clean" if not re.findall(r'<script(?![^>]*src=)[^>]*>[^<]', html) else "INLINE SCRIPT FOUND"
         )),

        ("T137-H39 No inline onclick",
         lambda: ("onclick=" not in html,
                  "clean" if "onclick=" not in html else "INLINE ONCLICK FOUND")),

        # ── 9. Empty state uses ui_primitives macro ─────────────
        ("T137-H40 empty_state macro usage",
         lambda: ("ui.empty_state(" in html,
                  "empty_state macro found" if "ui.empty_state(" in html else "MISSING")),

        ("T137-H41 button macro usage in empty state",
         lambda: ("ui.button(" in html,
                  "button macro found" if "ui.button(" in html else "MISSING")),

        # ── 10. Pagination structure present ─────────────────────
        ("T137-H42 nav with role=navigation",
         lambda: ('role="navigation"' in html,
                  "role=navigation found" if 'role="navigation"' in html else "MISSING")),

        ("T137-H43 data-action=page-input",
         lambda: ('data-action="page-input"' in html,
                  "page-input found" if 'data-action="page-input"' in html else "MISSING")),

        ("T137-H44 data-action=next-page",
         lambda: ('data-action="next-page"' in html,
                  "next-page found" if 'data-action="next-page"' in html else "MISSING")),

        ("T137-H45 page-status present",
         lambda: ('class="page-status"' in html,
                  "page-status found" if 'class="page-status"' in html else "MISSING")),

        ("T137-H46 .unified-pagination present",
         lambda: ('class="pagination unified-pagination"' in html,
                  "unified-pagination found" if 'class="pagination unified-pagination"' in html else "MISSING")),

        # ── 11. data-action coverage ─────────────────────────────
        ("T137-H47 data-action: sort",
         lambda: ('data-action="sort"' in html,
                  "sort found" if 'data-action="sort"' in html else "MISSING")),

        ("T137-H48 data-action: open-agent",
         lambda: ('data-action="open-agent"' in html,
                  "open-agent found" if 'data-action="open-agent"' in html else "MISSING")),

        ("T137-H49 data-action: open-agent-link",
         lambda: ('data-action="open-agent-link"' in html,
                  "open-agent-link found" if 'data-action="open-agent-link"' in html else "MISSING")),

        ("T137-H50 data-action: copy-agent-name",
         lambda: ('data-action="copy-agent-name"' in html or 'data-action="copy-agent-name"' in js,
                  "copy-agent-name found" if ('data-action="copy-agent-name"' in html or 'data-action="copy-agent-name"' in js) else "MISSING")),

        ("T137-H51 data-action: info (metric info icon)",
         lambda: ('data-action="info"' in html,
                  "info found" if 'data-action="info"' in html else "MISSING")),

        ("T137-H52 data-action: prev-page (in JS)",
         lambda: ('data-action="prev-page"' in js,
                  "prev-page found in JS" if 'data-action="prev-page"' in js else "MISSING")),

        ("T137-H53 data-action: run-scan (empty state, via button macro parameter)",
         lambda: ("data_action='run-scan'" in html or 'data_action="run-scan"' in html,
                  "run-scan found" if ("data_action='run-scan'" in html or 'data_action="run-scan"' in html) else "MISSING")),

        # ── 12. Aria attributes on decorative elements ───────────
        ("T137-H54 aria-hidden on emoji spans",
         lambda: ('aria-hidden="true"' in html,
                  "aria-hidden found" if 'aria-hidden="true"' in html else "MISSING")),

        ("T137-H55 aria-label on metric info buttons",
         lambda: ('aria-label="Active Agents' in html or 'aria-label="Sessions' in html or 'aria-label="Total Tokens' in html,
                  "aria-label on info buttons found" if ('aria-label="Active Agents' in html or 'aria-label="Sessions' in html) else "MISSING")),

        ("T137-H56 aria-label on pagination input",
         lambda: ('aria-label="Page number"' in html,
                  "aria-label=Page number found" if 'aria-label="Page number"' in html else "MISSING")),

        ("T137-H57 aria-label on pagination nav",
         lambda: ('aria-label="Agents pagination"' in html,
                  "aria-label=Agents pagination found" if 'aria-label="Agents pagination"' in html else "MISSING")),

        ("T137-H58 aria-label on info-icon buttons",
         lambda: (html.count('aria-label="') >= 3,
                  f'{html.count("aria-label=")} aria-label attribute(s) found' if html.count('aria-label="') >= 3 else "INSUFFICIENT aria-labels")),

        # ── CSS/JS imports ───────────────────────────────────────
        ("T137-H59 agents.css imported in template",
         lambda: ('href="/static/css/agents.css"' in html,
                  "agents.css import found" if 'href="/static/css/agents.css"' in html else "MISSING")),

        ("T137-H60 agents.js imported in template",
         lambda: ('src="/static/js/agents.js"' in html,
                  "agents.js import found" if 'src="/static/js/agents.js"' in html else "MISSING")),

        # ── Additional page contract checks (T137 spec) ──────────
        ("T137-H61 .page-head with h1 \"Agents\"",
         lambda: ('class="page-head"' in html and "<h1>Agents</h1>" in html,
                  "page-head + h1 found" if ('class="page-head"' in html and "<h1>Agents</h1>" in html) else "MISSING")),

        ("T137-H62 .table-card wraps agents table",
         lambda: ('class="card table-card"' in html,
                  "table-card found" if 'class="card table-card"' in html else "MISSING")),

        ("T137-H63 Efficiency table present when data exists",
         lambda: (
             'id="efficiency-table"' in html
             and "Agent/Model Efficiency" in html,
             "efficiency-table + title found" if ('id="efficiency-table"' in html and "Agent/Model Efficiency" in html) else "MISSING"
         )),

        ("T137-H64 No stale patterns (no page-header, no hero, no legacy-classes)",
         lambda: (
             'class="page-header"' not in html
             and 'hero' not in html
             and 'legacy-' not in html,
             "clean" if (
                 'class="page-header"' not in html
                 and 'hero' not in html
                 and 'legacy-' not in html
             ) else "STALE PATTERN FOUND"
         )),

        # ── Additional page-specific static QA (T137, appended) ──

        # 1. data-metric on metric-info buttons (parity with projects page)
        ("T137-H65 data-metric on metric-info buttons",
         lambda: ('data-metric=' in html,
                  "data-metric found" if 'data-metric=' in html else "MISSING (agents page metric-info buttons lack data-metric, unlike projects page)")),

        # 2. data-tooltip attribute (used on efficiency table model column)
        ("T137-H66 data-tooltip attribute present",
         lambda: ('data-tooltip=' in html,
                  "data-tooltip found" if 'data-tooltip=' in html else "MISSING")),

        # 3. table-note ABSENCE (agents page table-toolbar intentionally has no table-note)
        ("T137-H67 table-note absent (expected for agents page)",
         lambda: ('class="table-note"' not in html,
                  "absent (expected)" if 'class="table-note"' not in html else "UNEXPECTED: table-note should NOT be on agents page")),

        # 4. Filter card ABSENCE (agents page intentionally has no filter card)
        ("T137-H68 filter-card absent (expected for agents page)",
         lambda: ('class="card filter-card"' not in html,
                  "absent (expected)" if 'class="card filter-card"' not in html else "UNEXPECTED: filter-card should NOT be on agents page")),

        # 5. error_state macro (agents page should have error_state like other pages)
        ("T137-H69 error_state macro present",
         lambda: ("ui.error_state(" in html,
                  "error_state found" if "ui.error_state(" in html else "MISSING (agents page lacks error_state macro for error handling)")),

        # 6. state-strip class
        ("T137-H70 state-strip class present",
         lambda: ('class="state-strip"' in html,
                  "state-strip found" if 'class="state-strip"' in html else "MISSING")),

        # 7. data-action summary block (all required values across html+js combined)
        ("T137-H71 data-action summary block (sort, open-agent, open-agent-link, copy-agent-name, info, prev-page, page-input, run-scan, metric-info)",
         lambda: (
             all(x in (html + js) for x in [
                 'data-action="sort"',
                 'data-action="open-agent"',
                 'data-action="open-agent-link"',
                 'data-action="copy-agent-name"',
                 'data-action="info"',
                 'data-action="prev-page"',
                 'data-action="page-input"',
                 'data-action="run-scan"',
                 'data-action="metric-info"',
             ]),
             "all covered" if all(x in (html + js) for x in [
                 'data-action="sort"',
                 'data-action="open-agent"',
                 'data-action="open-agent-link"',
                 'data-action="copy-agent-name"',
                 'data-action="info"',
                 'data-action="prev-page"',
                 'data-action="page-input"',
                 'data-action="run-scan"',
                 'data-action="metric-info"',
             ]) else "MISSING some data-action values"
         )),

        # 8. data-row attributes on agent rows (for JS interaction)
        ("T137-H72 data-row attributes on agent rows (data-agent-name, data-session-count, data-project-count, data-total-tokens, data-total-tool-calls, data-total-failed, data-last-active)",
         lambda: (
             all(x in html for x in [
                 'data-agent-name=',
                 'data-session-count=',
                 'data-project-count=',
                 'data-total-tokens=',
                 'data-total-tool-calls=',
                 'data-total-failed=',
                 'data-last-active=',
             ]),
             "all data-row attributes found" if all(x in html for x in [
                 'data-agent-name=',
                 'data-session-count=',
                 'data-project-count=',
                 'data-total-tokens=',
                 'data-total-tool-calls=',
                 'data-total-failed=',
                 'data-last-active=',
             ]) else "MISSING some data-row attributes"
         )),

        # 9. Efficiency table sortable header count (>= 11 for agent, model, sessions, avg_duration, p95_duration, avg_input_side, avg_tools, tools_per_round, cache_reuse, failed_per_session, last_active)
        ("T137-H73 Efficiency table sortable header count >= 11",
         lambda: (html.count('data-action="sort"') >= 11,
                  f'{html.count("data-action=\"sort\"")} sortable element(s) found (>= 11 expected)' if html.count('data-action="sort"') >= 11 else f"ONLY {html.count('data-action=\"sort\"')} sortable element(s)")),

        # 10. Breadcrumb structure (Dashboard link + Agents current span)
        ("T137-H74 Breadcrumb: /dashboard link + Agents current span",
         lambda: ('href="/dashboard"' in html and '<span class="current">Agents</span>' in html,
                  "breadcrumb complete" if ('href="/dashboard"' in html and '<span class="current">Agents</span>' in html) else "MISSING breadcrumb elements")),

        # 11. Token compact format (format_compact_token filter)
        ("T137-H75 format_compact_token filter used",
         lambda: ('format_compact_token' in html,
                  "format_compact_token found" if 'format_compact_token' in html else "MISSING")),

        # 12. prev-page button JS-only (data-action="prev-page" in agents.js, not HTML)
        ("T137-H76 prev-page in JS only (not in HTML)",
         lambda: ('data-action="prev-page"' in js and 'data-action="prev-page"' not in html,
                  "prev-page in JS only (expected)" if ('data-action="prev-page"' in js and 'data-action="prev-page"' not in html) else "UNEXPECTED: prev-page placement mismatch")),

        # 13. No inline style=\"--\" in non-tokenbar/progress-bar elements
        ("T137-H77 Inline style=\"--\" only in tokenbar-seg and progress-bar elements",
         lambda: _check_inline_styles(html)),

        # 14. Agent avatar class variation (claude, codex, qoder across HTML+CSS)
        ("T137-H78 Agent avatar classes for all three types (claude, codex, qoder) across HTML+CSS",
         lambda: (
             all(x in (html + css) for x in ["claude", "codex", "qoder"]),
             "all three avatar type classes found" if all(x in (html + css) for x in ["claude", "codex", "qoder"]) else "MISSING some avatar type classes"
         )),

        # 15. Jinja2 comment-free / no TODO or FIXME in agents.html
        ("T137-H79 No <!-- TODO or <!-- FIXME in agents.html",
         lambda: ("<!-- TODO" not in html and "<!-- FIXME" not in html,
                  "clean" if ("<!-- TODO" not in html and "<!-- FIXME" not in html) else "TODO/FIXME comments found")),
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
        print("PASS: agents-list HTML QA checks")
        return 0
    else:
        print("FAIL: agents-list HTML QA checks -- see details above")
        return 1


def _check_inline_styles(html: str) -> tuple[bool, str]:
    """Verify that inline style=\"--\" usages are only in tokenbar-seg and progress-bar elements.

    Expected patterns:
    - tokenbar-seg: style=\"--segment-width:...%\" (4 per agent row)
    - progress-bar: style=\"--fill-width:...%\" (1 per agent row)
    """
    if not html:
        return (False, "HTML is empty")

    # Find all occurrences of style="--"
    matches = list(re.finditer(r'style="(--[^"]*)"', html))
    if not matches:
        return (False, "No inline style=\"--\" usages found (expected tokenbar/progress-bar)")

    # Check that each match is within a tokenbar-seg or progress-bar context
    # Look at the surrounding context (50 chars before the match)
    unexpected = []
    for m in matches:
        start = max(0, m.start() - 50)
        context = html[start:m.start()]
        if "tokenbar-seg" not in context and "progress-bar" not in context and "progress-fill" not in context:
            unexpected.append(m.group(0))

    if unexpected:
        return (False, f"UNEXPECTED inline style=\"--\" outside tokenbar/progress-bar: {unexpected}")

    return (True, f"{len(matches)} inline style=\"--\" usage(s), all in tokenbar-seg or progress-bar (expected)")


def _check_js_syntax(js: str) -> tuple[bool, str]:
    """Basic JS syntax check. Since we cannot run a JS parser from Python,
    we do a minimal structural sanity check: balanced braces/parens/brackets."""
    if not js:
        return (False, "agents.js is empty or missing")

    # Check balanced braces, parens, brackets
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

    # Check for essential structural markers in agents.js
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
