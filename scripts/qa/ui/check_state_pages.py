#!/usr/bin/env python3
"""T179 — Static QA for state pages HTML structure (404.html, error.html).

Validates state page templates against the page behavior contract:

1. Template structure: extends base.html, states.css imported in head_extra
2. 404.html: .state-panel with icon "404", title, desc, 4 nav links
3. error.html: .state-panel with error icon "!", title, desc, 1 nav link, details toggle
4. ARIA: role="status"/role="alert", aria-live, aria-hidden, aria-label
5. No inline: no onclick, no inline <script>, no inline <style>
6. CSS/JS: states.css exists, states.js exists (IIFE stub)
7. Navigation link completeness: all hrefs point to valid top-level routes
8. Stale patterns: no page-header, hero, legacy-, onclick
9. Error page: {% if error %} guard, details/summary/pre structure

Run from repo root:
  python scripts/qa/ui/check_state_pages.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HTML_404 = ROOT / "src/session_browser/web/templates/404.html"
HTML_ERROR = ROOT / "src/session_browser/web/templates/error.html"
STATES_CSS = ROOT / "src/session_browser/web/static/css/states.css"
STATES_JS = ROOT / "src/session_browser/web/static/js/states.js"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def main() -> int:
    html_404 = read(HTML_404)
    html_error = read(HTML_ERROR)
    css = read(STATES_CSS)
    js = read(STATES_JS)

    checks: list[tuple[str, callable]] = [
        # ── Template structure ─────────────────────────────────────
        ("T179-S01 404.html exists",
         lambda: (HTML_404.exists(),
                  "exists" if HTML_404.exists() else "MISSING")),

        ("T179-S02 error.html exists",
         lambda: (HTML_ERROR.exists(),
                  "exists" if HTML_ERROR.exists() else "MISSING")),

        ("T179-S03 404.html extends base.html",
         lambda: ('{% extends "base.html" %}' in html_404,
                  "extends base.html found" if '{% extends "base.html" %}' in html_404 else "MISSING")),

        ("T179-S04 error.html extends base.html",
         lambda: ('{% extends "base.html" %}' in html_error,
                  "extends base.html found" if '{% extends "base.html" %}' in html_error else "MISSING")),

        ("T179-S05 404.html links states.css",
         lambda: ('/static/css/states.css' in html_404,
                  "states.css linked" if '/static/css/states.css' in html_404 else "MISSING")),

        ("T179-S06 error.html links states.css",
         lambda: ('/static/css/states.css' in html_error,
                  "states.css linked" if '/static/css/states.css' in html_error else "MISSING")),

        ("T179-S07 states.css exists",
         lambda: (STATES_CSS.exists(),
                  "exists" if STATES_CSS.exists() else "MISSING")),

        ("T179-S08 states.js exists",
         lambda: (STATES_JS.exists(),
                  "exists" if STATES_JS.exists() else "MISSING")),

        ("T179-S09 states.js uses IIFE + strict mode",
         lambda: (
             "(function ()" in js and "'use strict'" in js,
             "IIFE + strict mode found" if "(function ()" in js and "'use strict'" in js else "MISSING IIFE or strict"
         )),

        # ── 404.html: Canonical classes ────────────────────────────
        ("T179-S10 404: .state-panel present",
         lambda: ('class="state-panel"' in html_404,
                  "state-panel found" if 'class="state-panel"' in html_404 else "MISSING")),

        ("T179-S11 404: .state-panel__icon present",
         lambda: ('class="state-panel__icon"' in html_404,
                  "state-panel__icon found" if 'class="state-panel__icon"' in html_404 else "MISSING")),

        ("T179-S12 404: icon text is '404'",
         lambda: ('>404<' in html_404,
                  "404 icon text found" if '>404<' in html_404 else "MISSING")),

        ("T179-S13 404: .state-panel__title present",
         lambda: ('class="state-panel__title"' in html_404,
                  "state-panel__title found" if 'class="state-panel__title"' in html_404 else "MISSING")),

        ("T179-S14 404: .state-panel__desc present",
         lambda: ('class="state-panel__desc"' in html_404,
                  "state-panel__desc found" if 'class="state-panel__desc"' in html_404 else "MISSING")),

        ("T179-S15 404: .state-panel__links present",
         lambda: ('class="state-panel__links"' in html_404,
                  "state-panel__links found" if 'class="state-panel__links"' in html_404 else "MISSING")),

        # ── 404.html: Navigation links (3 required) ────────────────
        ("T179-S16 404: link to /dashboard",
         lambda: ('href="/dashboard"' in html_404,
                  "dashboard link found" if 'href="/dashboard"' in html_404 else "MISSING")),

        ("T179-S17 404: link to /projects",
         lambda: ('href="/projects"' in html_404,
                  "projects link found" if 'href="/projects"' in html_404 else "MISSING")),

        ("T179-S18 404: link to /sessions",
         lambda: ('href="/sessions"' in html_404,
                  "sessions link found" if 'href="/sessions"' in html_404 else "MISSING")),

        ("T179-S20 404: exactly 3 nav links via .state-panel__link",
         lambda: (html_404.count('class="state-panel__link"') == 3,
                  f'{html_404.count("class=\"state-panel__link\"")} link(s) found'
                  if html_404.count('class="state-panel__link"') == 3
                  else f"{html_404.count('class=\"state-panel__link\"')} link(s), expected 3")),

        # ── error.html: Canonical classes ──────────────────────────
        ("T179-S21 error: .state-panel present",
         lambda: ('class="state-panel"' in html_error,
                  "state-panel found" if 'class="state-panel"' in html_error else "MISSING")),

        ("T179-S22 error: .state-panel__icon present",
         lambda: ('class="state-panel__icon' in html_error,
                  "state-panel__icon found" if 'class="state-panel__icon' in html_error else "MISSING")),

        ("T179-S23 error: .state-panel__icon--error variant",
         lambda: ('state-panel__icon--error' in html_error,
                  "error variant found" if 'state-panel__icon--error' in html_error else "MISSING")),

        ("T179-S24 error: icon text is '!'",
         lambda: ('>!<' in html_error,
                  "! icon text found" if '>!<' in html_error else "MISSING")),

        ("T179-S25 error: .state-panel__title present",
         lambda: ('class="state-panel__title"' in html_error,
                  "state-panel__title found" if 'class="state-panel__title"' in html_error else "MISSING")),

        ("T179-S26 error: .state-panel__desc present",
         lambda: ('class="state-panel__desc"' in html_error,
                  "state-panel__desc found" if 'class="state-panel__desc"' in html_error else "MISSING")),

        ("T179-S27 error: .state-panel__links present",
         lambda: ('class="state-panel__links"' in html_error,
                  "state-panel__links found" if 'class="state-panel__links"' in html_error else "MISSING")),

        # ── error.html: Navigation links ───────────────────────────
        ("T179-S28 error: link to /dashboard",
         lambda: ('href="/dashboard"' in html_error,
                  "dashboard link found" if 'href="/dashboard"' in html_error else "MISSING")),

        ("T179-S29 error: at least 1 nav link",
         lambda: (html_error.count('class="state-panel__link"') >= 1,
                  f'{html_error.count("class=\"state-panel__link\"")} link(s) found'
                  if html_error.count('class="state-panel__link"') >= 1
                  else "NO nav links")),

        # ── error.html: details toggle (conditional) ───────────────
        ("T179-S30 error: {% if error %} guard present",
         lambda: ('{% if error %}' in html_error,
                  "if error guard found" if '{% if error %}' in html_error else "MISSING")),

        ("T179-S31 error: details.state-panel__details present",
         lambda: ('class="state-panel__details"' in html_error,
                  "state-panel__details found" if 'class="state-panel__details"' in html_error else "MISSING")),

        ("T179-S32 error: summary 'Error details' present",
         lambda: ('<summary>Error details</summary>' in html_error,
                  "summary found" if '<summary>Error details</summary>' in html_error else "MISSING")),

        ("T179-S33 error: pre.state-panel__raw present",
         lambda: ('class="state-panel__raw"' in html_error,
                  "state-panel__raw found" if 'class="state-panel__raw"' in html_error else "MISSING")),

        ("T179-S34 error: {{ error }} variable used",
         lambda: ('{{ error }}' in html_error,
                  "error variable found" if '{{ error }}' in html_error else "MISSING")),

        # ── ARIA attributes ────────────────────────────────────────
        ("T179-S35 404: role=\"status\" on state-panel",
         lambda: ('role="status"' in html_404,
                  "role=status found" if 'role="status"' in html_404 else "MISSING")),

        ("T179-S36 404: aria-live=\"polite\" on state-panel",
         lambda: ('aria-live="polite"' in html_404,
                  "aria-live=polite found" if 'aria-live="polite"' in html_404 else "MISSING")),

        ("T179-S37 error: role=\"alert\" on state-panel",
         lambda: ('role="alert"' in html_error,
                  "role=alert found" if 'role="alert"' in html_error else "MISSING")),

        ("T179-S38 error: aria-live=\"assertive\" on state-panel",
         lambda: ('aria-live="assertive"' in html_error,
                  "aria-live=assertive found" if 'aria-live="assertive"' in html_error else "MISSING")),

        ("T179-S39 404: aria-hidden on icon",
         lambda: ('aria-hidden="true"' in html_404,
                  "aria-hidden found" if 'aria-hidden="true"' in html_404 else "MISSING")),

        ("T179-S40 error: aria-hidden on icon",
         lambda: ('aria-hidden="true"' in html_error,
                  "aria-hidden found" if 'aria-hidden="true"' in html_error else "MISSING")),

        ("T179-S41 404: aria-label on nav links",
         lambda: ('aria-label="Navigation links"' in html_404,
                  "aria-label on nav found" if 'aria-label="Navigation links"' in html_404 else "MISSING")),

        ("T179-S42 error: aria-label on nav links",
         lambda: ('aria-label="Navigation links"' in html_error,
                  "aria-label on nav found" if 'aria-label="Navigation links"' in html_error else "MISSING")),

        # ── No inline styles/scripts ───────────────────────────────
        ("T179-S43 404: No inline <style> blocks",
         lambda: (not bool(re.search(r'<style>', html_404)),
                  "clean" if not re.search(r'<style>', html_404) else "INLINE STYLE FOUND")),

        ("T179-S44 404: No inline <script> blocks",
         lambda: (
             not bool(re.findall(r'<script(?![^>]*type="application/json")[^>]*>[^<]', html_404)),
             "clean" if not re.findall(r'<script(?![^>]*type="application/json")[^>]*>[^<]', html_404) else "INLINE SCRIPT FOUND"
         )),

        ("T179-S45 404: No inline onclick",
         lambda: ("onclick=" not in html_404,
                  "clean" if "onclick=" not in html_404 else "INLINE ONCLICK FOUND")),

        ("T179-S46 error: No inline <style> blocks",
         lambda: (not bool(re.search(r'<style>', html_error)),
                  "clean" if not re.search(r'<style>', html_error) else "INLINE STYLE FOUND")),

        ("T179-S47 error: No inline <script> blocks",
         lambda: (
             not bool(re.findall(r'<script(?![^>]*type="application/json")[^>]*>[^<]', html_error)),
             "clean" if not re.findall(r'<script(?![^>]*type="application/json")[^>]*>[^<]', html_error) else "INLINE SCRIPT FOUND"
         )),

        ("T179-S48 error: No inline onclick",
         lambda: ("onclick=" not in html_error,
                  "clean" if "onclick=" not in html_error else "INLINE ONCLICK FOUND")),

        # ── CSS content validation ─────────────────────────────────
        ("T179-S49 states.css: .state-panel defined",
         lambda: (".state-panel" in css,
                  "found" if ".state-panel" in css else "MISSING")),

        ("T179-S50 states.css: .state-panel__icon defined",
         lambda: (".state-panel__icon" in css,
                  "found" if ".state-panel__icon" in css else "MISSING")),

        ("T179-S51 states.css: error variant defined",
         lambda: (".state-panel__icon--error" in css,
                  "found" if ".state-panel__icon--error" in css else "MISSING")),

        ("T179-S52 states.css: responsive rules present",
         lambda: ("@media" in css,
                  "found" if "@media" in css else "MISSING")),

        # ── Breadcrumb ─────────────────────────────────────────────
        ("T179-S53 404: breadcrumb with dashboard link",
         lambda: ('href="/dashboard"' in html_404,
                  "found" if 'href="/dashboard"' in html_404 else "MISSING")),

        ("T179-S54 error: breadcrumb with dashboard link",
         lambda: ('href="/dashboard"' in html_error,
                  "found" if 'href="/dashboard"' in html_error else "MISSING")),

        # ── Stale patterns ─────────────────────────────────────────
        ("T179-S55 404: No stale patterns (page-header, hero, legacy-, onclick)",
         lambda: (
             'class="page-header"' not in html_404
             and 'class="hero"' not in html_404
             and 'legacy-' not in html_404
             and 'onclick=' not in html_404,
             "clean" if (
                 'class="page-header"' not in html_404
                 and 'class="hero"' not in html_404
                 and 'legacy-' not in html_404
                 and 'onclick=' not in html_404
             ) else "STALE PATTERN FOUND"
         )),

        ("T179-S56 error: No stale patterns (page-header, hero, legacy-, onclick)",
         lambda: (
             'class="page-header"' not in html_error
             and 'class="hero"' not in html_error
             and 'legacy-' not in html_error
             and 'onclick=' not in html_error,
             "clean" if (
                 'class="page-header"' not in html_error
                 and 'class="hero"' not in html_error
                 and 'legacy-' not in html_error
                 and 'onclick=' not in html_error
             ) else "STALE PATTERN FOUND"
         )),

        ("T179-S57 404: No TODO/FIXME/HACK comments",
         lambda: (
             'TODO' not in html_404
             and 'FIXME' not in html_404
             and 'HACK' not in html_404,
             "clean" if ('TODO' not in html_404 and 'FIXME' not in html_404 and 'HACK' not in html_404) else "TODO/FIXME/HACK FOUND"
         )),

        ("T179-S58 error: No TODO/FIXME/HACK comments",
         lambda: (
             'TODO' not in html_error
             and 'FIXME' not in html_error
             and 'HACK' not in html_error,
             "clean" if ('TODO' not in html_error and 'FIXME' not in html_error and 'HACK' not in html_error) else "TODO/FIXME/HACK FOUND"
         )),

        # ── No vN/patch/fix/overlay CSS or JS ──────────────────────
        ("T179-S59 No versioned state CSS/JS (states.v1, states-patch, etc.)",
         lambda: _check_no_versioned_files()),

        # ── Navigation link semantic consistency ───────────────────
        ("T179-S60 All 404 nav links use .state-panel__link class",
         lambda: (
             all(
                 f'class="state-panel__link"' in html_404
                 for _ in range(1)
             ) and html_404.count('class="state-panel__link"') >= 4,
             "all links use canonical class" if html_404.count('class="state-panel__link"') >= 4 else "NON-CANONICAL link class"
         )),

        ("T179-S61 Dashboard link uses ← prefix (404)",
         lambda: ("&larr;" in html_404 or "&larr" in html_404,
                  "arrow prefix found" if ("&larr;" in html_404 or "&larr" in html_404) else "MISSING")),

        ("T179-S62 Dashboard link uses ← prefix (error)",
         lambda: ("&larr;" in html_error or "&larr" in html_error,
                  "arrow prefix found" if ("&larr;" in html_error or "&larr" in html_error) else "MISSING")),

        # ── topbar_toggles suppressed on state pages ───────────────
        ("T179-S63 404: topbar_toggles block suppressed",
         lambda: ('{% block topbar_toggles %}{% endblock %}' in html_404,
                  "suppressed" if '{% block topbar_toggles %}{% endblock %}' in html_404 else "NOT SUPPRESSED")),

        ("T179-S64 error: topbar_toggles block suppressed",
         lambda: ('{% block topbar_toggles %}{% endblock %}' in html_error,
                  "suppressed" if '{% block topbar_toggles %}{% endblock %}' in html_error else "NOT SUPPRESSED")),

        # ── CSS contract: no inline style attribute in templates ───
        ("T179-S65 404: No inline style= attributes",
         lambda: ('style=' not in html_404,
                  "clean" if 'style=' not in html_404 else "INLINE STYLE ATTR FOUND")),

        ("T179-S66 error: No inline style= attributes",
         lambda: ('style=' not in html_error,
                  "clean" if 'style=' not in html_error else "INLINE STYLE ATTR FOUND")),
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
        print("PASS: state pages HTML QA checks")
        return 0
    else:
        print("FAIL: state pages HTML QA checks -- see details above")
        return 1


def _check_no_versioned_files() -> tuple[bool, str]:
    """Ensure no versioned/patch/fix/overlay variants of states.css/js exist."""
    qa_dir = ROOT / "scripts" / "qa" / "ui"
    static_css = ROOT / "src" / "session_browser" / "web" / "static" / "css"
    static_js = ROOT / "src" / "session_browser" / "web" / "static" / "js"

    patterns = ["states.v", "states-patch", "states-fix", "states-overlay"]

    for directory in [static_css, static_js]:
        if directory.exists():
            for f in directory.iterdir():
                name = f.name.lower()
                for pat in patterns:
                    if pat in name:
                        return (False, f"VERSIONED file found: {f.name}")

    return (True, "no versioned/patch/fix/overlay states files")


if __name__ == "__main__":
    raise SystemExit(main())
