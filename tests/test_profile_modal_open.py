"""Tests for Profile tab LLM Call modal Open button reliability.

After profile refactoring (P-01/P-02):
- Profile no longer has inline Open buttons for request/response.
- Details are viewed via Inspector (openLLMInspector).
- Hidden <template> elements exist for Inspector content retrieval.
- Each row is clickable via onclick="openLLMInspector(this)".
"""

import re
from pathlib import Path

TEMPLATE_DIR = Path(__file__).parent.parent / "src" / "session_browser" / "web" / "templates"


def _session_source():
    return (TEMPLATE_DIR / "session.html").read_text(encoding="utf-8")


def _base_source():
    return (TEMPLATE_DIR / "base.html").read_text(encoding="utf-8")


# ── Profile uses Inspector, not inline Open buttons ──────────────────


def test_profile_no_inline_detail_rows():
    """Profile must NOT have inline llm-call-detail expansion rows."""
    source = _session_source()
    assert 'llm-call-detail' not in source, (
        "Profile must not contain llm-call-detail rows — "
        "details belong in Inspector"
    )


def test_profile_has_inspector_templates():
    """Profile must have hidden <template> elements for Inspector retrieval."""
    source = _session_source()
    assert "inspect-request" in source, (
        "Profile must have inspect-request template id pattern"
    )
    assert "inspect-response" in source, (
        "Profile must have inspect-response template id pattern"
    )


def test_profile_row_has_data_attrs():
    """Each profile row must have data attributes for Inspector."""
    source = _session_source()
    assert "data-llm-call-id=" in source or "data-call-idx=" in source, (
        "Profile rows must have identifier data attributes"
    )
    assert "data-call-idx=" in source, (
        "Profile rows must have data-call-idx"
    )


def test_profile_row_is_clickable():
    """Profile rows must be clickable via openLLMInspector (no separate inspect-btn)."""
    source = _session_source()
    assert "openLLMInspector" in source, (
        "Profile must reference openLLMInspector function"
    )
    # The row itself is clickable via onclick
    assert "onclick=\"openLLMInspector(this)\"" in source, (
        "Profile rows must have onclick handler for openLLMInspector"
    )


# ── openContentModal compatibility ────────────────────────────────────


def test_open_content_modal_supports_template_id():
    """openContentModal must read data-raw-template-id / data-md-template-id."""
    source = _session_source()

    assert "_getTemplateTextById" in source, (
        "openContentModal must use _getTemplateTextById helper"
    )
    assert "data-raw-template-id" in source or "_getTemplateTextById" in source, (
        "openContentModal must support template ID retrieval"
    )
    assert "data-md-template-id" in source or "_getTemplateTextById" in source, (
        "openContentModal must support MD template ID retrieval"
    )


def test_open_content_modal_fallback_nested_template():
    """openContentModal must fallback to btn.querySelectorAll('template') for old buttons."""
    source = _session_source()

    assert "querySelectorAll('template')" in source or 'querySelectorAll("template")' in source, (
        "openContentModal must fallback to nested template querying"
    )


def test_open_content_modal_warns_on_missing_content():
    """openContentModal must log console.warn when no template content is found."""
    source = _session_source()

    assert "console.warn" in source, (
        "openContentModal must call console.warn on failure, not silently return"
    )


def test_open_content_modal_sets_visible():
    """openContentModal must add 'visible' class to modal."""
    source = _session_source()

    assert "modal.classList.add('visible')" in source, (
        "openContentModal must add 'visible' class to modal"
    )


# ── Event handling ────────────────────────────────────────────────────


def test_capture_phase_click_listener():
    """base.html must have a capture-phase click listener for [data-content-modal]."""
    source = _base_source()

    assert "addEventListener('click'" in source, (
        "base.html must add click event listeners"
    )
    # The capture-phase listener uses `true` as the third argument
    assert ", true)" in source, (
        "base.html must register a capture-phase click listener (third arg = true)"
    )


def test_closest_polyfill():
    """base.html must define a closest helper for older WebView compatibility."""
    source = _base_source()

    assert "_arpClosest" in source, (
        "base.html must define _arpClosest helper function"
    )
    assert "webkitMatchesSelector" in source, (
        "base.html's _arpClosest must support webkitMatchesSelector for old browsers"
    )


def test_capture_handler_sets_handled_flag():
    """The capture-phase handler must set e.__contentModalHandled to skip bubbling handler."""
    source = _base_source()

    assert "__contentModalHandled" in source, (
        "Capture handler must set e.__contentModalHandled flag"
    )


def test_bubble_handler_skips_handled():
    """The bubble-phase .show-more handler must check __contentModalHandled."""
    source = _base_source()

    # The bubble handler should skip if the flag is set
    assert "__contentModalHandled" in source, (
        "Bubble handler must check e.__contentModalHandled to avoid double handling"
    )


# ── Timeline backward compatibility ───────────────────────────────────


def test_timeline_uses_macro():
    """Timeline tab should import and use timeline_node macro."""
    source = _session_source()

    assert 'from "components/timeline.html" import' in source, \
        "Timeline tab should import timeline component macros"
    assert "build_timeline_nodes" in source, \
        "Timeline tab should define build_timeline_nodes helper"


def test_timeline_has_trace_structure():
    """Timeline should use the trace-based structure for detail rows."""
    source = _session_source()

    assert "trace-row" in source, \
        "Timeline should contain trace-row elements for expandable rounds"
