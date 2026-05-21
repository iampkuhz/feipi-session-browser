#!/usr/bin/env python3
"""DOM-oriented contract checks using rendered/static template text.
This is intentionally conservative and complements pytest/Playwright.

Checks:
  1. Primitive macro existence in ui_primitives.html
  2. Button data-action coverage
  3. Pagination prev/next/input structure
  4. Token bar segment color classes
  5. Payload modal data attributes
  6. Empty state and error state presence
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path.cwd()
errors: list[str] = []
passes: list[str] = []

# ---------------------------------------------------------------------------
# 1. Primitive macro existence
# ---------------------------------------------------------------------------
primitive_file = ROOT / "src/session_browser/web/templates/components/ui_primitives.html"
if primitive_file.exists():
    text = primitive_file.read_text(encoding="utf-8", errors="ignore")

    # Canonical macros (T032/T034)
    canonical_macros = [
        "button", "icon_button", "badge", "metric_card", "metric_grid",
        "pagination", "token_bar", "tooltip", "popover", "section_card",
        "data_table", "filter_bar", "payload_modal", "empty_state", "error_state",
    ]
    # Legacy macros still required for backward compatibility
    legacy_macros = ["btn", "select_control", "stat_pill", "th_static", "th_sort", "token_total"]

    all_macros = canonical_macros + legacy_macros  # 21 total; task target is 18+
    found: list[str] = []
    missing: list[str] = []
    for macro in all_macros:
        if re.search(rf"{{% macro {re.escape(macro)}\b", text):
            found.append(macro)
        else:
            missing.append(macro)

    if missing:
        errors.append(f"missing macros in ui_primitives.html: {', '.join(missing)}")
    else:
        passes.append(f"All {len(all_macros)} primitive macros present ({len(canonical_macros)} canonical + {len(legacy_macros)} legacy)")
else:
    errors.append(f"ui_primitives.html not found: {primitive_file}")

# ---------------------------------------------------------------------------
# 2. Button data-action coverage
# ---------------------------------------------------------------------------
if primitive_file.exists():
    text = primitive_file.read_text(encoding="utf-8", errors="ignore")
    button_re = re.compile(r"<button\b([^>]*)>", re.I)
    buttons_with_action = 0
    buttons_without_action = 0

    for m in button_re.finditer(text):
        attrs = m.group(1)
        if "data-action" in attrs or 'type="submit"' in attrs or "type='submit'" in attrs:
            buttons_with_action += 1
        else:
            buttons_without_action += 1

    if buttons_without_action > 0:
        errors.append(
            f"buttons without data-action/submit: {buttons_without_action} "
            f"(with: {buttons_with_action})"
        )
    else:
        passes.append(
            f"Button data-action coverage: {buttons_with_action} covered, 0 uncovered"
        )

# ---------------------------------------------------------------------------
# 3. Pagination prev/next/input structure
# ---------------------------------------------------------------------------
if primitive_file.exists():
    text = primitive_file.read_text(encoding="utf-8", errors="ignore")
    pagination_checks: list[str] = []

    # Check for pagination macro block
    pagination_block = re.search(
        r"{% macro pagination.*?{%-?\s*endmacro\s*%}", text, re.DOTALL
    )
    if not pagination_block:
        errors.append("pagination macro not found")
    else:
        block = pagination_block.group(0)
        checks = {
            "prev button": r"data-action=\"prev-page\"",
            "next button": r"data-action=\"next-page\"",
            "page input": r'data-action="page-input"',
            "page-status span": r'class="page-status"',
            "nav role": r'role="navigation"',
        }
        for label, pat in checks.items():
            if re.search(pat, block):
                pagination_checks.append(label)
            else:
                errors.append(f"pagination missing: {label}")

        if len(pagination_checks) == len(checks):
            passes.append(f"Pagination structure complete: {', '.join(pagination_checks)}")

# ---------------------------------------------------------------------------
# 4. Token bar segment color classes
# ---------------------------------------------------------------------------
if primitive_file.exists():
    text = primitive_file.read_text(encoding="utf-8", errors="ignore")
    token_block = re.search(
        r"{% macro token_bar.*?{%-?\s*endmacro\s*%}", text, re.DOTALL
    )
    if not token_block:
        errors.append("token_bar macro not found")
    else:
        block = token_block.group(0)
        segment_kinds = ["fresh", "read", "write", "out"]
        found_segments: list[str] = []
        for kind in segment_kinds:
            # Check that the segment class is referenced (as CSS class, not inline)
            if re.search(rf"['\"]{re.escape(kind)}['\"]", block):
                found_segments.append(kind)
            else:
                errors.append(f"token_bar missing segment class: {kind}")

        if len(found_segments) == len(segment_kinds):
            passes.append(f"Token bar segment classes: {', '.join(found_segments)}")

# ---------------------------------------------------------------------------
# 5. Payload modal data attributes
# ---------------------------------------------------------------------------
if primitive_file.exists():
    text = primitive_file.read_text(encoding="utf-8", errors="ignore")
    modal_block = re.search(
        r"{% macro payload_modal.*?{%-?\s*endmacro\s*%}", text, re.DOTALL
    )
    if not modal_block:
        errors.append("payload_modal macro not found")
    else:
        block = modal_block.group(0)
        modal_attrs: list[str] = []
        attr_checks = {
            "data-modal": r'data-modal\b',
            "data-modal-kind": r'data-modal-kind',
            "data-modal-title": r'data-modal-title',
            "data-modal-meta": r'data-modal-meta',
            "data-modal-content": r'data-modal-content',
            "role=dialog": r'role="dialog"',
            "aria-modal": r'aria-modal="true"',
            "close-modal action": r'data-action="close-modal"',
        }
        for label, pat in attr_checks.items():
            if re.search(pat, block):
                modal_attrs.append(label)
            else:
                errors.append(f"payload_modal missing: {label}")

        if len(modal_attrs) == len(attr_checks):
            passes.append(f"Payload modal data attributes: {', '.join(modal_attrs)}")

# ---------------------------------------------------------------------------
# 6. Empty state and error state presence
# ---------------------------------------------------------------------------
if primitive_file.exists():
    text = primitive_file.read_text(encoding="utf-8", errors="ignore")
    state_checks_passed: list[str] = []

    # Empty state
    empty_block = re.search(
        r"{% macro empty_state.*?{%-?\s*endmacro\s*%}", text, re.DOTALL
    )
    if not empty_block:
        errors.append("empty_state macro not found")
    else:
        block = empty_block.group(0)
        empty_attrs = {
            "role=status": r'role="status"',
            "aria-live=polite": r'aria-live="polite"',
            "state-strip class": r"['\"]state-strip['\"]",
            "state-title": r'class="state-title"',
            "state-icon": r'class="state-icon"',
        }
        for label, pat in empty_attrs.items():
            if re.search(pat, block):
                state_checks_passed.append(f"empty_state:{label}")
            else:
                errors.append(f"empty_state missing: {label}")

    # Error state
    error_block = re.search(
        r"{% macro error_state.*?{%-?\s*endmacro\s*%}", text, re.DOTALL
    )
    if not error_block:
        errors.append("error_state macro not found")
    else:
        block = error_block.group(0)
        error_attrs = {
            "role=alert": r'role="alert"',
            "aria-live=assertive": r'aria-live="assertive"',
            "state-strip class": r"['\"]state-strip['\"]",
            "state-title": r'class="state-title"',
            "state-icon": r'class="state-icon"',
        }
        for label, pat in error_attrs.items():
            if re.search(pat, block):
                state_checks_passed.append(f"error_state:{label}")
            else:
                errors.append(f"error_state missing: {label}")

    if not any(e.startswith("empty_state") or e.startswith("error_state") for e in errors):
        passes.append(f"Empty/Error states verified: {', '.join(state_checks_passed)}")

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
if passes:
    print("DOM contract checks:")
    for p in passes:
        print(f"  PASS: {p}")

if errors:
    print("\nDOM contract check failed:")
    for e in errors:
        print(f"  FAIL: {e}")
    sys.exit(1)

print("\nAll DOM contract checks passed")
