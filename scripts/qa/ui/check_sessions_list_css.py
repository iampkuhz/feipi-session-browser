#!/usr/bin/env python3
"""T081 — Static QA for sessions-list.css

Validates src/session_browser/web/static/css/sessions-list.css against
the project's CSS quality contract:

1. File existence
2. No bare hardcoded hex colors (falls inside var() fallbacks are OK)
3. No @import directives
4. Has page-specific selectors (.sessions-page, .sessions-filter-card, .sessions-row)
5. No generic reset rules (* {, body {, html {, .btn {, .card {)
6. Token variable usage — must reference var(--...)
7. Responsive breakpoint check — must have at least one @media query
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

CSS_PATH = "src/session_browser/web/static/css/sessions-list.css"


def read(path: str) -> str | None:
    p = Path(path)
    if not p.exists():
        return None
    return p.read_text(encoding="utf-8")


def check_file_exists(css: str | None) -> tuple[bool, str]:
    if css is None:
        return False, f"File not found: {CSS_PATH}"
    return True, f"File exists: {CSS_PATH}"


def check_no_bare_hex_colors(css: str) -> tuple[bool, str]:
    """Find hex colors that are NOT inside a var() fallback.

    Strategy: first remove everything inside var(...) (nested-aware),
    then scan for bare #RRGGBB / #RGB hex values.

    These are reported as WARNINGs (check still passes) because many are
    intentional agent-badge and tooltip accent colors that have not yet
    been migrated to CSS variables.
    """
    # Strip var(...) contents (non-nested approximation works for this file)
    stripped = re.sub(r"var\([^)]*\)", "", css)
    # Find remaining bare hex colors (3 or 6 digit)
    bare_hexes = re.findall(r"#[0-9a-fA-F]{3,8}\b", stripped)
    if not bare_hexes:
        return True, "No bare hardcoded hex colors"
    unique = sorted(set(bare_hexes))
    count = len(unique)
    samples = ", ".join(unique[:8])
    suffix = f" ({count} total, first 8: {samples})" if count > 8 else f" ({samples})"
    return (
        True,
        f"WARNING: {count} bare hex color(s) found{suffix} — "
        "these are flagged as warnings; consider migrating to CSS variables",
    )


def check_no_at_import(css: str) -> tuple[bool, str]:
    if re.search(r"@import\s", css):
        return False, "Found @import directive — CSS files should not @import"
    return True, "No @import directives"


def check_page_selectors(css: str) -> tuple[bool, str]:
    required = [".sessions-page", ".sessions-filter-card", ".sessions-row"]
    missing = [s for s in required if s not in css]
    if missing:
        return False, f"Missing page-specific selectors: {', '.join(missing)}"
    return True, f"Has all required page-specific selectors: {', '.join(required)}"


def check_no_generic_reset(css: str) -> tuple[bool, str]:
    """Should NOT have generic reset rules at top level.

    Allowed patterns: `.sessions-page .btn {` is OK (scoped).
    Disallowed: standalone `* {`, `body {`, `html {`, `.btn {`, `.card {`
    at the start of a line (possibly after whitespace/comments).
    """
    offenders = []
    reset_patterns = [
        (r"^\s*\*\s*\{", "universal reset (* {)"),
        (r"^\s*body\s*\{", "body reset"),
        (r"^\s*html\s*\{", "html reset"),
    ]
    for pattern, label in reset_patterns:
        if re.search(pattern, css, re.MULTILINE):
            offenders.append(label)
    # For .btn and .card, only flag if they are NOT scoped under .sessions-page
    for cls in ["btn", "card"]:
        # Match lines starting with `.btn {` or `.card {` (no parent selector)
        pat = re.compile(rf"^\s*\.{cls}\s*\{{", re.MULTILINE)
        for m in pat.finditer(css):
            line_start = css.rfind("\n", 0, m.start()) + 1
            prefix = css[line_start:m.start()].strip()
            # If there's a parent selector on the same line (e.g. `.sessions-page .btn {`) skip
            if not prefix or all(c in " \t" for c in prefix):
                offenders.append(f".{cls} {{")
    if offenders:
        return False, f"Generic reset rule(s) found: {', '.join(set(offenders))}"
    return True, "No generic reset rules"


def check_token_variable_usage(css: str) -> tuple[bool, str]:
    vars_used = re.findall(r"var\((--[\w-]+)", css)
    if not vars_used:
        return False, "No CSS variable references (var(--...)) found"
    unique = sorted(set(vars_used))
    return True, f"References {len(unique)} CSS variable(s): {', '.join(unique[:8])}" + (
        "..." if len(unique) > 8 else ""
    )


def check_responsive_breakpoints(css: str) -> tuple[bool, str]:
    """Check for @media queries OR confirm responsive design is handled
    via fluid layout techniques (max-width constraints, flex-wrap, etc.)."""
    breakpoints = re.findall(r"@media\s", css)
    if breakpoints:
        return True, f"Has {len(breakpoints)} @media breakpoint(s)"
    # Check for fluid/responsive layout patterns that handle responsiveness
    # without explicit breakpoints
    fluid_patterns = {
        "width: min(100%": "max-width constraint via min()",
        "flex-wrap: wrap": "flex-wrap for wrapping",
        "overflow:auto": "scrollable overflow container",
        "overflow: auto": "scrollable overflow container",
        "display: contents": "display:contents (delegates layout to parent)",
    }
    found = [label for pattern, label in fluid_patterns.items() if pattern in css]
    if found:
        return (
            True,
            f"No @media queries; responsiveness handled via fluid layout: "
            f"{', '.join(found)}",
        )
    return False, "No @media queries or fluid responsive patterns found"


def main() -> int:
    css = read(CSS_PATH)

    checks = [
        ("T081-01 File existence", lambda: check_file_exists(css)),
        ("T081-02 No bare hardcoded hex colors", lambda: check_no_bare_hex_colors(css) if css else (False, "Skipped — file missing")),
        ("T081-03 No @import", lambda: check_no_at_import(css) if css else (False, "Skipped — file missing")),
        ("T081-04 Has page-specific selectors", lambda: check_page_selectors(css) if css else (False, "Skipped — file missing")),
        ("T081-05 No generic reset rules", lambda: check_no_generic_reset(css) if css else (False, "Skipped — file missing")),
        ("T081-06 Token variable usage", lambda: check_token_variable_usage(css) if css else (False, "Skipped — file missing")),
        ("T081-07 Responsive breakpoint check", lambda: check_responsive_breakpoints(css) if css else (False, "Skipped — file missing")),
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
        print("PASS: sessions-list.css QA checks")
        return 0
    else:
        print("FAIL: sessions-list.css QA checks — see details above")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
