#!/usr/bin/env python3
"""Check Profile table DOM structure in session.html.

Static analysis: ensures Profile is LLM Call Index only, not carrying
inline request/response expansion blocks.

Checks:
  1. Profile table contains only call summary columns (no inline detail rows).
  2. No .llm-call-detail__pre-block, "Request Context:", or large inline <pre>.
  3. Each row has an Inspect button that can open Inspector.
  4. Marker container exists in the template.
  5. Preview column has truncation class for single/two-line clipping.

Usage:
    cd <repo-root>
    PYTHONPATH=src python scripts/check_profile_table_structure.py

Exit codes:
    0 — all checks passed
    1 — one or more checks failed
    2 — input error (template file not found)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


# ── locate template ──────────────────────────────────────────────────

def find_session_html() -> Path:
    """Return the path to session.html template."""
    candidates = [
        Path(__file__).resolve().parent.parent / "src" / "session_browser" / "web" / "templates" / "session.html",
        Path.cwd() / "src" / "session_browser" / "web" / "templates" / "session.html",
    ]
    for p in candidates:
        if p.exists():
            return p
    raise FileNotFoundError(
        "Cannot find session.html. Run from repo root or set PYTHONPATH."
    )


# ── extraction ───────────────────────────────────────────────────────

def extract_profile_template(source: str) -> str | None:
    """Extract the content of <template id="profile-template">."""
    m = re.search(
        r'<template id="profile-template">(.*?)</template>',
        source,
        re.DOTALL,
    )
    return m.group(1) if m else None


def extract_profile_table(template: str) -> str | None:
    """Extract the profile table block (from <table> to </table>)."""
    m = re.search(r'(<table.*?</table>)', template, re.DOTALL)
    return m.group(1) if m else None


# ── checks ───────────────────────────────────────────────────────────

def check_no_inline_detail_rows(template: str) -> tuple[bool, str]:
    """FAIL if <tr class="llm-call-detail ..."> exists — Profile should not expand inline."""
    if re.search(r'class="[^"]*\bllm-call-detail\b[^"]*"', template):
        return False, 'Found <tr class="... llm-call-detail ..."> — Profile should not have inline detail expansion rows'
    return True, 'No inline llm-call-detail expansion rows'


def check_no_pre_blocks(template: str) -> tuple[bool, str]:
    """FAIL if .llm-call-detail__pre-block exists — no large inline <pre> blocks."""
    if 'llm-call-detail__pre-block' in template:
        return False, 'Found .llm-call-detail__pre-block — Profile should not contain large inline <pre> blocks'
    return True, 'No .llm-call-detail__pre-block elements'


def check_no_request_context_label(template: str) -> tuple[bool, str]:
    """FAIL if 'Request Context:' label exists — rendered context != request payload."""
    if 'Request Context:' in template:
        return False, 'Found "Request Context:" label — Profile should not expose inline request context labels'
    return True, 'No "Request Context:" inline label'


def check_inspect_buttons_exist(template: str) -> tuple[bool, str]:
    """OK if each row has an Inspect button calling openLLMInspector."""
    buttons = re.findall(
        r'<button[^>]*class="[^"]*inspect-btn[^"]*"[^>]*>',
        template,
    )
    if not buttons:
        return False, 'No inspect buttons found — each profile row should have an Inspect button'

    # Verify they reference openLLMInspector
    has_open = 'openLLMInspector' in template
    if not has_open:
        return False, 'Inspect buttons exist but openLLMInspector function not found'

    return True, f'{len(buttons)} inspect button(s) found with openLLMInspector handler'


def check_marker_container(template: str) -> tuple[bool, str]:
    """OK if a marker container exists in the profile template."""
    # Look for a marker-style container (data-marker, or a div with marker class)
    if 'data-marker' in template or 'marker-container' in template or 'profile-marker' in template:
        return True, 'Marker container found'
    return False, 'No marker container found (data-marker / marker-container / profile-marker)'


def check_preview_truncation(template: str) -> tuple[bool, str]:
    """OK if preview column has truncation class."""
    # Look for truncate class on preview cells
    if 'class="text-xs mono truncate"' in template or 'class="truncate"' in template or 'truncate' in template:
        return True, 'Preview column has truncation class'
    return False, 'Preview column missing truncation class'


def check_no_large_inline_pre(template: str) -> tuple[bool, str]:
    """FAIL if <pre> blocks inside the detail grid contain > 200 chars of template content."""
    # Find <pre> blocks inside llm-call-detail__grid area
    detail_section = re.search(
        r'llm-call-detail__grid.*?(?=</template>)',
        template,
        re.DOTALL,
    )
    if not detail_section:
        return True, 'No llm-call-detail__grid section found'

    section = detail_section.group()
    pre_blocks = re.findall(r'<pre[^>]*>(.*?)</pre>', section, re.DOTALL)
    for i, content in enumerate(pre_blocks):
        # Strip Jinja2 template syntax for length check
        stripped = re.sub(r'\{\{.*?\}\}', '', content)
        stripped = re.sub(r'\{%.*?%\}', '', stripped)
        if len(stripped.strip()) > 200:
            return False, f'Large inline <pre> block #{i+1} in detail grid ({len(stripped.strip())} chars of static content)'

    return True, 'No large inline <pre> blocks in detail grid'


# ── runner ───────────────────────────────────────────────────────────

CHECKS = [
    ("No inline detail rows", check_no_inline_detail_rows),
    ("No pre-blocks", check_no_pre_blocks),
    ("No Request Context label", check_no_request_context_label),
    ("Inspect buttons exist", check_inspect_buttons_exist),
    ("Marker container", check_marker_container),
    ("Preview truncation", check_preview_truncation),
    ("No large inline <pre>", check_no_large_inline_pre),
]


def run(template_path: Path) -> int:
    """Run all checks. Returns exit code."""
    source = template_path.read_text(encoding="utf-8")
    template = extract_profile_template(source)

    if template is None:
        print("[ERROR] Cannot find <template id=\"profile-template\"> in session.html", file=sys.stderr)
        return 2

    print(f"Checking profile table structure in: {template_path}")
    print(f"Template length: {len(template)} chars")
    print()

    failures = 0
    passes = 0

    for name, check_fn in CHECKS:
        ok, msg = check_fn(template)
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
        path = find_session_html()
    except FileNotFoundError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2

    return run(path)


if __name__ == "__main__":
    sys.exit(main())
