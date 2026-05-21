#!/usr/bin/env python3
"""T095 — Static QA for session-detail page HTML structure.

Validates session.html and session_detail_*.html component templates
against the session-detail page behavior contract:

1. Hero area structure (agent pill, KPIs, summary strip, issue strip)
2. Tab navigation (3 tabs with data-action)
3. Trace table structure (colgroup, thead, round-row pattern)
4. Filter buttons (status-all, status-failed, collapse-all)
5. Token bar 4-segment structure
6. Payload modal data attributes
7. No inline style/script/onclick in session.html and component templates
8. Canonical CSS import check

Run from repo root:
  python scripts/qa/ui/check_session_detail.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SESSIONS_HTML = ROOT / "src/session_browser/web/templates/session.html"
TIMELINE_CMP = ROOT / "src/session_browser/web/templates/components/session_detail_timeline.html"
PRIMITIVES_CMP = ROOT / "src/session_browser/web/templates/components/session_detail_primitives.html"
CSS_MAIN = ROOT / "src/session_browser/web/static/css/session-detail.css"
CSS_TIMELINE = ROOT / "src/session_browser/web/static/css/session-detail-timeline.css"
JS_MAIN = ROOT / "src/session_browser/web/static/js/session-detail.js"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def main() -> int:
    session = read(SESSIONS_HTML)
    timeline = read(TIMELINE_CMP)
    primitives = read(PRIMITIVES_CMP)
    css = read(CSS_MAIN)
    combined = session + "\n" + timeline + "\n" + primitives

    checks: list[tuple[str, callable]] = [
        # ── File existence ──────────────────────────────────────────
        ("T095-01 session.html exists", lambda: (
            SESSIONS_HTML.exists(),
            "exists" if SESSIONS_HTML.exists() else "MISSING"
        )),
        ("T095-02 session_detail_timeline.html exists", lambda: (
            TIMELINE_CMP.exists(),
            "exists" if TIMELINE_CMP.exists() else "MISSING"
        )),
        ("T095-03 session_detail_primitives.html exists", lambda: (
            PRIMITIVES_CMP.exists(),
            "exists" if PRIMITIVES_CMP.exists() else "MISSING"
        )),
        ("T095-04 session-detail.css exists", lambda: (
            CSS_MAIN.exists(),
            "exists" if CSS_MAIN.exists() else "MISSING"
        )),
        ("T095-05 session-detail.js exists", lambda: (
            JS_MAIN.exists(),
            "exists" if JS_MAIN.exists() else "MISSING"
        )),

        # ── Canonical CSS import ────────────────────────────────────
        ("T095-06 Canonical CSS imported", lambda: (
            "session-detail.css" in session and "session-detail-timeline.css" not in session,
            "session-detail.css imported" if "session-detail.css" in session else "NOT FOUND"
        )),

        # ── No inline style/script/onclick ──────────────────────────
        ("T095-07 No inline <style> blocks", lambda: (
            not bool(re.search(r'<style[^>]*>', session, re.DOTALL)),
            "clean" if not re.search(r'<style[^>]*>', session) else "INLINE STYLE FOUND"
        )),
        ("T095-08 No inline <script> (non-JSON) in session.html", lambda: (
            not bool(re.findall(r'<script(?![^>]*type="application/json")[^>]*>[^<]', session)),
            "clean" if not re.findall(r'<script(?![^>]*type="application/json")[^>]*>[^<]', session) else "INLINE SCRIPT FOUND"
        )),
        ("T095-09 No inline onclick", lambda: (
            "onclick=" not in combined,
            "clean" if "onclick=" not in combined else "INLINE ONCLICK FOUND"
        )),
        ("T095-10 No inline onclick in components", lambda: (
            "onclick=" not in timeline and "onclick=" not in primitives,
            "clean" if "onclick=" not in timeline and "onclick=" not in primitives else "INLINE ONCLICK FOUND"
        )),

        # ── Hero area structure ─────────────────────────────────────
        ("T095-11 Hero container present", lambda: (
            "sd-hero" in timeline and "data-session-overview-hero" in timeline,
            "sd-hero with data-session-overview-hero found" if ("sd-hero" in timeline and "data-session-overview-hero" in timeline) else "MISSING"
        )),
        ("T095-12 Agent pill present", lambda: (
            "sd-agent-pill" in timeline,
            "sd-agent-pill found" if "sd-agent-pill" in timeline else "MISSING"
        )),
        ("T095-13 KPI section present (4 KPIs)", lambda: (
            "sd-kpis" in timeline and timeline.count("sd-kpi") >= 4,
            f"sd-kpis with {timeline.count('sd-kpi')} KPI entries found" if ("sd-kpis" in timeline and timeline.count("sd-kpi") >= 4) else "MISSING"
        )),
        ("T095-14 Summary strip present", lambda: (
            "sd-summary-strip" in timeline and "data-summary-strip" in timeline,
            "sd-summary-strip with data-summary-strip found" if ("sd-summary-strip" in timeline and "data-summary-strip" in timeline) else "MISSING"
        )),
        ("T095-15 Issue strip present", lambda: (
            "sd-issue-strip" in timeline and "data-issue-strip" in timeline,
            "sd-issue-strip with data-issue-strip found" if ("sd-issue-strip" in timeline and "data-issue-strip" in timeline) else "MISSING"
        )),

        # ── Tab navigation ──────────────────────────────────────────
        ("T095-16 Tab navigation present", lambda: (
            "sd-tabs" in session and "data-session-tabs" in session,
            "sd-tabs with data-session-tabs found" if ("sd-tabs" in session and "data-session-tabs" in session) else "MISSING"
        )),
        ("T095-17 Tab count = 3 (trace, metrics, payloads)", lambda: (
            session.count("sd-tab") >= 3,
            f"{session.count('sd-tab')} tabs found" if session.count("sd-tab") >= 3 else "EXPECTED 3"
        )),
        ("T095-18 Trace tab data-action", lambda: (
            'data-action="tab-trace"' in session,
            "tab-trace data-action found" if 'data-action="tab-trace"' in session else "MISSING"
        )),
        ("T095-19 Metrics tab data-action", lambda: (
            'data-action="tab-metrics"' in session,
            "tab-metrics data-action found" if 'data-action="tab-metrics"' in session else "MISSING"
        )),
        ("T095-20 Payloads tab data-action", lambda: (
            'data-action="tab-payloads"' in session,
            "tab-payloads data-action found" if 'data-action="tab-payloads"' in session else "MISSING"
        )),

        # ── Trace table structure ───────────────────────────────────
        ("T095-21 Trace table present", lambda: (
            "trace-table" in session,
            "trace-table found" if "trace-table" in session else "MISSING"
        )),
        ("T095-22 Trace table colgroup present", lambda: (
            "<colgroup>" in session,
            "colgroup found" if "<colgroup>" in session else "MISSING"
        )),
        ("T095-23 Trace table thead present", lambda: (
            "<thead>" in session,
            "thead found" if "<thead>" in session else "MISSING"
        )),
        ("T095-24 Round row pattern (data-trace-round-row)", lambda: (
            "data-trace-round-row" in timeline,
            "data-trace-round-row found" if "data-trace-round-row" in timeline else "MISSING"
        )),
        ("T095-25 Trace list data attribute", lambda: (
            "data-trace-list" in session,
            "data-trace-list found" if "data-trace-list" in session else "MISSING"
        )),
        ("T095-26 Trace panel container", lambda: (
            "sd-trace-panel" in session and "data-trace-panel" in session,
            "sd-trace-panel with data-trace-panel found" if ("sd-trace-panel" in session and "data-trace-panel" in session) else "MISSING"
        )),

        # ── Filter buttons ──────────────────────────────────────────
        ("T095-27 Status-all filter button", lambda: (
            'data-action="status-all"' in timeline or ('data-action="filter-status"' in timeline and 'data-status="all"' in timeline),
            "status-all filter found" if ('data-action="status-all"' in timeline or ('data-action="filter-status"' in timeline and 'data-status="all"' in timeline)) else "MISSING"
        )),
        ("T095-28 Status-failed filter button", lambda: (
            'data-action="status-failed"' in timeline or ('data-action="filter-status"' in timeline and 'data-status="failed"' in timeline),
            "status-failed filter found" if ('data-action="status-failed"' in timeline or ('data-action="filter-status"' in timeline and 'data-status="failed"' in timeline)) else "MISSING"
        )),
        ("T095-29 Collapse-all button", lambda: (
            'data-action="collapse-all"' in timeline,
            "collapse-all data-action found" if 'data-action="collapse-all"' in timeline else "MISSING"
        )),

        # ── Token bar 4-segment structure ───────────────────────────
        ("T095-30 Token bar 4 segments (fresh, read, write, out) in timeline", lambda: (
            "class=\"fresh\"" in timeline and "class=\"read\"" in timeline and "class=\"write\"" in timeline and "class=\"out\"" in timeline,
            "4-segment tokenbar found" if ("class=\"fresh\"" in timeline and "class=\"read\"" in timeline and "class=\"write\"" in timeline and "class=\"out\"" in timeline) else "MISSING segments"
        )),
        ("T095-31 Token bar CSS classes present", lambda: (
            "tokenbar .fresh" in css and "tokenbar .read" in css and "tokenbar .write" in css and "tokenbar .out" in css,
            "4 tokenbar CSS classes found" if ("tokenbar .fresh" in css and "tokenbar .read" in css and "tokenbar .write" in css and "tokenbar .out" in css) else "MISSING CSS classes"
        )),

        # ── Payload modal data attributes ───────────────────────────
        ("T095-32 Payload modal dialog element", lambda: (
            "sd-payload-modal" in timeline and 'id="payload-modal"' in timeline,
            "payload modal dialog found" if ("sd-payload-modal" in timeline and 'id="payload-modal"' in timeline) else "MISSING"
        )),
        ("T095-33 Payload modal aria-labelledby", lambda: (
            'aria-labelledby="payload-title"' in timeline,
            "aria-labelledby found" if 'aria-labelledby="payload-title"' in timeline else "MISSING"
        )),
        ("T095-34 Payload title element (data-payload-title)", lambda: (
            "data-payload-title" in timeline,
            "data-payload-title found" if "data-payload-title" in timeline else "MISSING"
        )),
        ("T095-35 Payload subtitle element (data-payload-subtitle)", lambda: (
            "data-payload-subtitle" in timeline,
            "data-payload-subtitle found" if "data-payload-subtitle" in timeline else "MISSING"
        )),
        ("T095-36 Payload body container (data-payload-body)", lambda: (
            "data-payload-body" in timeline,
            "data-payload-body found" if "data-payload-body" in timeline else "MISSING"
        )),
        ("T095-37 Payload empty state (data-payload-empty)", lambda: (
            "data-payload-empty" in timeline,
            "data-payload-empty found" if "data-payload-empty" in timeline else "MISSING"
        )),
        ("T095-38 Payload modal metadata fields (data-meta-*)", lambda: (
            "data-meta-id" in timeline and "data-meta-kind" in timeline and "data-meta-status" in timeline and "data-meta-size" in timeline,
            "data-meta-{id,kind,status,size} found" if ("data-meta-id" in timeline and "data-meta-kind" in timeline and "data-meta-status" in timeline and "data-meta-size" in timeline) else "MISSING"
        )),
        ("T095-39 Close payload button (data-action=close-payload)", lambda: (
            'data-action="close-payload"' in timeline,
            "close-payload data-action found" if 'data-action="close-payload"' in timeline else "MISSING"
        )),
        ("T095-40 Payload source templates (data-payload-source)", lambda: (
            "data-payload-source" in timeline,
            "data-payload-source found" if "data-payload-source" in timeline else "MISSING"
        )),
        ("T095-41 Open payload buttons (open-payload action via macro)", lambda: (
            "'open-payload'" in timeline or '"open-payload"' in timeline,
            "open-payload action found in macro calls" if ("'open-payload'" in timeline or '"open-payload"' in timeline) else "MISSING"
        )),

        # ── Round toggle & expand behavior ──────────────────────────
        ("T095-42 Toggle round data-action", lambda: (
            'data-action="toggle-round"' in timeline,
            "toggle-round data-action found" if 'data-action="toggle-round"' in timeline else "MISSING"
        )),
        ("T095-43 Expanded row (data-trace-detail)", lambda: (
            "data-trace-detail" in timeline,
            "data-trace-detail found" if "data-trace-detail" in timeline else "MISSING"
        )),
        ("T095-44 Copy session URL action", lambda: (
            'data-action="copy-session-url"' in timeline,
            "copy-session-url data-action found" if 'data-action="copy-session-url"' in timeline else "MISSING"
        )),

        # ── CSS: no legacy file references ──────────────────────────
        ("T095-45 No legacy session-detail-timeline.css in session.html", lambda: (
            "session-detail-timeline.css" not in session,
            "no legacy CSS reference" if "session-detail-timeline.css" not in session else "LEGACY CSS STILL REFERENCED"
        )),

        # ── CSS: required session-detail selectors ──────────────────
        ("T095-46 CSS: .sd-hero selector", lambda: (
            ".sd-hero" in css,
            ".sd-hero found" if ".sd-hero" in css else "MISSING"
        )),
        ("T095-47 CSS: .sd-tabs selector", lambda: (
            ".sd-tabs" in css,
            ".sd-tabs found" if ".sd-tabs" in css else "MISSING"
        )),
        ("T095-48 CSS: .trace-table selector", lambda: (
            ".trace-table" in css,
            ".trace-table found" if ".trace-table" in css else "MISSING"
        )),
        ("T095-49 CSS: .sd-payload-modal selector", lambda: (
            ".sd-payload-modal" in css,
            ".sd-payload-modal found" if ".sd-payload-modal" in css else "MISSING"
        )),
        ("T095-50 CSS: .round-row selector", lambda: (
            ".round-row" in css,
            ".round-row found" if ".round-row" in css else "MISSING"
        )),

        # ── CSS variables defined ───────────────────────────────────
        ("T095-51 CSS: --sd-brand variable", lambda: (
            "--sd-brand" in css,
            "--sd-brand found" if "--sd-brand" in css else "MISSING"
        )),
        ("T095-52 CSS: --sd-err variable", lambda: (
            "--sd-err" in css,
            "--sd-err found" if "--sd-err" in css else "MISSING"
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
        print("PASS: session-detail HTML QA checks")
        return 0
    else:
        print("FAIL: session-detail HTML QA checks — see details above")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
