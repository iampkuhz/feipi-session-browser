#!/usr/bin/env python3
"""Check that scroll shadow feature has been fully removed.

This script verifies:
1. No .table-wrap::before / ::after pseudo-element rules in CSS
2. No is-scroll-left / is-scroll-right class rules in CSS
3. No updateScrollShadow / initScrollShadows / initAllScrollShadows in JS
4. No resize/profile-loaded scroll-shadow listeners in JS

Usage:
    cd <repo-root>
    PYTHONPATH=src python scripts/check_scroll_shadow_behavior.py

Exit codes:
    0 — all checks pass (feature fully removed)
    1 — one or more FAILs detected (residuals found)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
SRC = REPO_ROOT / "src" / "session_browser" / "web"

CSS_FILE = SRC / "static" / "style.css"
JS_FILES = [
    SRC / "static" / "js" / "app.js",
    SRC / "static" / "js" / "data-table.js",
    SRC / "static" / "js" / "timeline.js",
    SRC / "static" / "js" / "keyboard.js",
]
INLINE_JS_FILES = [
    SRC / "templates" / "base.html",
    SRC / "templates" / "session.html",
]

_pass = 0
_fail = 0
_warn = 0
_findings: list[tuple[str, str]] = []


def _reset_counters() -> None:
    """Reset global counters for test isolation."""
    global _pass, _fail, _warn, _findings
    _pass = 0
    _fail = 0
    _warn = 0
    _findings = []


def report(level: str, check: str, detail: str = "") -> None:
    global _pass, _fail, _warn
    tag = {"OK": "OK", "FAIL": "FAIL", "WARN": "WARN"}.get(level, "??")
    line = f"  [{tag}] {check}"
    if detail:
        line += f" — {detail}"
    print(line)
    _findings.append((level, check))
    if level == "OK":
        _pass += 1
    elif level == "FAIL":
        _fail += 1
    else:
        _warn += 1


def read_file(p: Path) -> str:
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8")


def read_all_js() -> str:
    parts: list[str] = []
    for f in JS_FILES:
        content = read_file(f)
        if content:
            parts.append(content)
    return "\n".join(parts)


def read_all_inline_js() -> str:
    parts: list[str] = []
    for f in INLINE_JS_FILES:
        content = read_file(f)
        if not content:
            continue
        for m in re.finditer(r'<script[^>]*>(.*?)</script>', content, re.DOTALL):
            parts.append(m.group(1))
    return "\n".join(parts)


# ─── 1. CSS: verify ::before removed ───────────────────────────────

def check_right_shadow_absent(css: str) -> None:
    """Verify .table-wrap::after is removed."""
    has_after = bool(re.search(r'\.table-wrap\s*::after\s*\{', css))
    if not has_after:
        report("OK", "Right shadow (.table-wrap::after) removed")
    else:
        report("FAIL", "Right shadow (.table-wrap::after) still present")


# ─── 2. CSS: verify ::before removed ───────────────────────────────

def check_left_shadow_absent(css: str) -> None:
    """Verify .table-wrap::before is removed."""
    has_before = bool(re.search(r'\.table-wrap\s*::before\s*\{', css))
    if not has_before:
        report("OK", "Left shadow (.table-wrap::before) removed")
    else:
        report("FAIL", "Left shadow (.table-wrap::before) still present")


# ─── 3. CSS: verify state classes removed ──────────────────────────

def check_state_classes_absent(css: str) -> None:
    """Verify is-scroll-left/right class rules are removed."""
    has_left = '.is-scroll-left' in css
    has_right = '.is-scroll-right' in css
    if not has_left:
        report("OK", "is-scroll-left class rule removed")
    else:
        report("FAIL", "is-scroll-left class rule still present")
    if not has_right:
        report("OK", "is-scroll-right class rule removed")
    else:
        report("FAIL", "is-scroll-right class rule still present")


# ─── 4. JS: verify shadow functions removed ────────────────────────

def check_js_shadow_absent(js: str, inline_js: str) -> None:
    """Verify all scroll shadow JS code is removed."""
    all_js = js + "\n" + inline_js

    for name in ['updateScrollShadow', 'initScrollShadows', 'initAllScrollShadows']:
        if name not in all_js:
            report("OK", f"{name} removed from JS")
        else:
            report("FAIL", f"{name} still present in JS")

    # Check for resize listener tied to shadow init
    has_resize_shadow = bool(re.search(r"addEventListener.*['\"]resize['\"].*initAllScrollShadows", all_js))
    if not has_resize_shadow:
        report("OK", "resize+shadow init listener removed")
    else:
        report("FAIL", "resize+shadow init listener still present")

    # Check for profile-loaded shadow reinit
    has_profile_shadow = bool(re.search(r"addEventListener.*['\"]profile-loaded['\"].*initAllScrollShadows", all_js))
    if not has_profile_shadow:
        report("OK", "profile-loaded+shadow reinit listener removed")
    else:
        report("FAIL", "profile-loaded+shadow reinit listener still present")


# ─── 5. HTML: verify .table-wrap layout preserved ─────────────────

def check_table_wrap_layout(css: str) -> None:
    """Verify .table-wrap base layout CSS is still present."""
    has_base = bool(re.search(r'\.table-wrap\s*\{', css))
    has_overflow = 'overflow-x' in css and 'auto' in css
    if has_base:
        report("OK", ".table-wrap base rule preserved")
    else:
        report("FAIL", ".table-wrap base rule missing (layout broken)")
    if has_overflow:
        report("OK", "overflow-x:auto preserved (scrollable layout)")
    else:
        report("WARN", "overflow-x:auto not confirmed")


# ─── Main ───────────────────────────────────────────────────────────

def main() -> int:
    print("=" * 60)
    print("  Scroll Shadow Removal Verification")
    print("=" * 60)

    css = read_file(CSS_FILE)
    js = read_all_js()
    inline_js = read_all_inline_js()

    if not css:
        print(f"\n  ERROR: CSS file not found: {CSS_FILE}")
        return 2

    print("\n  [1] CSS: .table-wrap::after removed")
    print("  " + "-" * 40)
    check_right_shadow_absent(css)

    print("\n  [2] CSS: .table-wrap::before removed")
    print("  " + "-" * 40)
    check_left_shadow_absent(css)

    print("\n  [3] CSS: is-scroll-left/right classes removed")
    print("  " + "-" * 40)
    check_state_classes_absent(css)

    print("\n  [4] JS: scroll shadow functions removed")
    print("  " + "-" * 40)
    check_js_shadow_absent(js, inline_js)

    print("\n  [5] CSS: .table-wrap layout preserved")
    print("  " + "-" * 40)
    check_table_wrap_layout(css)

    # Summary
    print("\n" + "=" * 60)
    total = _pass + _fail + _warn
    print(f"  Results: {_pass} OK, {_warn} WARN, {_fail} FAIL (total: {total})")
    if _fail:
        print("  Status: FAIL — scroll shadow residuals found")
    elif _warn:
        print("  Status: PASS with warnings")
    else:
        print("  Status: PASS — scroll shadow feature fully removed")
    print("=" * 60)

    return 1 if _fail > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
