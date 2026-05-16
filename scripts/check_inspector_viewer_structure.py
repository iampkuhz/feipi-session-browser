#!/usr/bin/env python3
"""Check Inspector/Viewer tab structure in templates and JS.

Static analysis: verifies that the LLM Call Inspector has a clear tabs
shell with separated raw/rendered boundaries.

Checks:
  1. Seven required tabs exist: Overview, Rendered Context, Request Payload,
     Rendered Response, Response Payload, Tools, Raw.
  2. Tab buttons and tabpanels have active state and basic ARIA attributes.
  3. "Request Payload unavailable" empty-state text is renderable.
  4. Raw JSON/<pre> content is safely HTML-escaped.
  5. Old viewerHtml fallback does not break non-LLM Inspector.

Usage:
    cd <repo-root>
    PYTHONPATH=src python scripts/check_inspector_viewer_structure.py

Exit codes:
    0 — all checks passed
    1 — one or more checks failed
    2 — input error (template/JS file not found)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# ── locate files ─────────────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent.parent / "src" / "session_browser" / "web"


def find_file(rel: str) -> Path:
    """Return the path to a template/JS file."""
    p = BASE_DIR / rel
    if not p.exists():
        raise FileNotFoundError(f"Cannot find {rel} at {p}")
    return p


def read(rel: str) -> str:
    return find_file(rel).read_text(encoding="utf-8")


# ── extraction helpers ───────────────────────────────────────────────

_REQUIRED_TABS = [
    "Overview",
    "Rendered Context",
    "Request Payload",
    "Rendered Response",
    "Response Payload",
    "Tools",
    "Raw",
]

_INSPECTOR_FILES = [
    "templates/components/inspector.html",
    "templates/components/viewer.html",
    "templates/session.html",
    "static/js/inspector.js",
]


def _read_all() -> dict[str, str]:
    """Read all inspector-related source files."""
    result = {}
    for rel in _INSPECTOR_FILES:
        try:
            result[rel] = read(rel)
        except FileNotFoundError as exc:
            print(f"[ERROR] {exc}", file=sys.stderr)
            sys.exit(2)
    return result


def _combined_source(sources: dict[str, str]) -> str:
    return "\n".join(sources.values())


# ── checks ───────────────────────────────────────────────────────────

def check_required_tabs(sources: dict[str, str]) -> tuple[bool, str]:
    """FAIL if any of the 7 required tab labels are missing."""
    combined = _combined_source(sources)
    missing = []
    for tab in _REQUIRED_TABS:
        # Search for the tab label in button text, header, or data attribute
        if tab not in combined:
            missing.append(tab)
    if missing:
        return False, f"Missing tab labels: {', '.join(missing)}"
    return True, f"All {_REQUIRED_TABS.__len__()} required tabs found"


def check_tab_aria_and_active(sources: dict[str, str]) -> tuple[bool, str]:
    """FAIL if tab buttons lack role/tab or tabpanels lack role/tabpanel, or no active state."""
    combined = _combined_source(sources)

    # Check for tab button pattern: <button ... class="tab ..."> with role="tab" or data-tab
    has_tab_buttons = bool(re.search(
        r'<button[^>]*class="[^"]*\btab\b[^"]*"[^>]*>',
        combined,
    ))
    # Check for ARIA role on buttons
    has_aria_tab = 'role="tab"' in combined or "role='tab'" in combined
    # Check for tabpanel
    has_tabpanel = 'role="tabpanel"' in combined or "role='tabpanel'" in combined or 'class="tab-content"' in combined or 'class="tabpanel"' in combined
    # Check for active state class
    has_active = bool(re.search(r'class="[^"]*\bactive\b[^"]*"', combined))

    issues = []
    if not has_tab_buttons:
        issues.append("no tab button elements")
    if not has_aria_tab:
        issues.append("no role='tab' ARIA attribute")
    if not has_tabpanel:
        issues.append("no tabpanel element (role='tabpanel' or class='tab-content')")
    if not has_active:
        issues.append("no 'active' state class")

    if issues:
        return False, f"Tab structure issues: {'; '.join(issues)}"
    return True, "Tab buttons and tabpanels have active state and ARIA attributes"


def check_request_payload_unavailable(sources: dict[str, str]) -> tuple[bool, str]:
    """FAIL if 'Request Payload unavailable' empty-state text cannot be rendered."""
    combined = _combined_source(sources)
    # Look for an explicit "unavailable" empty-state marker for request payload
    patterns = [
        r'Request Payload.*unavailable',
        r'unavailable.*Request Payload',
        r'Request Payload.*not available',
        r'No request payload',
        r'request.*payload.*unavailable',
    ]
    for pat in patterns:
        if re.search(pat, combined, re.IGNORECASE):
            return True, "'Request Payload unavailable' empty-state text found"

    # Broader: just check for "unavailable" near "payload" or "request"
    if 'unavailable' in combined.lower() and ('payload' in combined.lower() or 'request' in combined.lower()):
        return True, "Generic unavailable text exists (but not specific 'Request Payload unavailable')"

    return False, "No 'Request Payload unavailable' empty-state text found"


def check_raw_content_escaping(sources: dict[str, str]) -> tuple[bool, str]:
    """FAIL if raw JSON/<pre> content is not safely HTML-escaped."""
    combined = _combined_source(sources)

    # Check for HTML escaping patterns: .replace(/&/g, '&amp;'), .replace(/</g, '&lt;')
    has_amp_escape = bool(re.search(r"replace\s*\(\s*/&/g\s*,\s*['\"]&amp;['\"]", combined))
    has_lt_escape = bool(re.search(r"replace\s*\(/</g\s*,\s*['\"]&lt;['\"]", combined))
    has_gt_escape = bool(re.search(r"/>/g\s*,\s*['\"]&gt;['\"]", combined))

    # Also check Jinja2 autoescape / |e filter usage
    has_jinja_escape = '|e' in combined or 'autoescape' in combined or '|safe' not in combined or 'safe_json_display' in combined

    issues = []
    if not has_amp_escape:
        issues.append("missing & -> &amp; escaping in JS")
    if not has_lt_escape:
        issues.append("missing < -> &lt; escaping in JS")
    if not has_gt_escape:
        issues.append("missing > -> &gt; escaping in JS")

    if issues:
        return False, f"Raw content escaping issues: {'; '.join(issues)}"
    return True, "Raw JSON/<pre> content is safely HTML-escaped"


def check_viewerhtml_fallback(sources: dict[str, str]) -> tuple[bool, str]:
    """OK if viewerHtml fallback in inspector.js does not break non-LLM Inspector."""
    js_source = sources.get("static/js/inspector.js", "")

    # Check that viewerHtml injection is guarded (conditional, not unconditional)
    # The pattern should be: if (payload.viewerHtml) { ... } — not direct assignment
    has_guarded_viewerhtml = bool(re.search(
        r'if\s*\(\s*payload\.viewerHtml\s*\)',
        js_source,
    ))

    if not has_guarded_viewerhtml:
        return False, "viewerHtml injection is not guarded by a conditional check"

    # Check that the inspector has default/empty state for when viewerHtml is absent
    inspector_html = sources.get("templates/components/inspector.html", "")
    has_fallback = bool(re.search(
        r'(No .*? available|Not available|—|viewer__fallback|inspector-viewer-slot)',
        inspector_html,
    ))

    if not has_fallback:
        return False, "No fallback content for absent viewerHtml in inspector template"

    return True, "viewerHtml fallback is guarded and has default content"


# ── inspector-specific tab structure check ───────────────────────────

def check_inspector_tab_shell(sources: dict[str, str]) -> tuple[bool, str]:
    """FAIL if inspector.html lacks a dedicated tab shell for LLM Call Inspector."""
    inspector = sources.get("templates/components/inspector.html", "")

    # Inspector should have its own tab container (not just the session-level tabs)
    has_inspector_tabs = bool(re.search(
        r'(inspector-tab|data-inspector-tab|class="inspector.*tab)',
        inspector,
        re.IGNORECASE,
    ))

    # Or tabs injected via JS in inspector.js
    js_source = sources.get("static/js/inspector.js", "")
    has_js_tabs = bool(re.search(
        r'(inspector-tab|tab.*panel|tabpanel|role.*tab)',
        js_source,
        re.IGNORECASE,
    ))

    if not has_inspector_tabs and not has_js_tabs:
        return False, "Inspector lacks a dedicated tab shell (no inspector-level tabs in HTML or JS)"
    return True, "Inspector has a dedicated tab shell"


def check_rendered_raw_separation(sources: dict[str, str]) -> tuple[bool, str]:
    """FAIL if rendered and raw content are confused (same class/element for both)."""
    combined = _combined_source(sources)

    # Check that there are distinct classes/containers for rendered vs raw
    has_rendered_container = bool(re.search(
        r'(rendered|markdown|viewer__markdown|viewer__part-markdown)',
        combined,
    ))
    has_raw_container = bool(re.search(
        r'(viewer__raw|raw-pre|raw-json|__raw)',
        combined,
    ))

    if not has_rendered_container or not has_raw_container:
        return False, "Rendered and raw containers are not clearly separated"

    return True, "Rendered and raw content have separate containers"


# ── runner ───────────────────────────────────────────────────────────

CHECKS = [
    ("7 required tabs", check_required_tabs),
    ("Tab ARIA and active state", check_tab_aria_and_active),
    ("Request Payload unavailable", check_request_payload_unavailable),
    ("Raw content escaping", check_raw_content_escaping),
    ("viewerHtml fallback", check_viewerhtml_fallback),
    ("Inspector tab shell", check_inspector_tab_shell),
    ("Rendered/raw separation", check_rendered_raw_separation),
]


def run(sources: dict[str, str]) -> int:
    """Run all checks. Returns exit code."""
    # Print file info
    for rel, content in sources.items():
        print(f"  {rel}: {len(content)} chars")
    print()

    failures = 0
    passes = 0

    for name, check_fn in CHECKS:
        ok, msg = check_fn(sources)
        if ok:
            print(f"[OK]   {name}: {msg}")
            passes += 1
        else:
            print(f"[FAIL] {name}: {msg}")
            failures += 1

    print()
    print(f"Result: {passes} passed, {failures} failed out of {len(CHECKS)} checks")

    return 1 if failures > 0 else 0


def main() -> int:
    try:
        sources = _read_all()
    except SystemExit:
        raise
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2

    print("Checking Inspector/Viewer structure...")
    print()
    return run(sources)


if __name__ == "__main__":
    sys.exit(main())
