"""Tests for payload modal and trace structure after Phase 1 simplification.

After Phase 1 simplification:
- Calls/Hotspots views removed; trace is the primary view
- Tool spans use openToolInspector for inspection
- Hidden <template> elements exist for tool result retrieval
- Payload modal (payload-modal) is the only modal — content-modal removed
"""

import re
from pathlib import Path

TEMPLATE_DIR = Path(__file__).parent.parent / "src" / "session_browser" / "web" / "templates"


def _session_source():
    return (TEMPLATE_DIR / "session.html").read_text(encoding="utf-8")


def _base_source():
    return (TEMPLATE_DIR / "base.html").read_text(encoding="utf-8")


# ── Tool result templates and inspector entry ──────────────────


def test_has_tool_result_templates():
    """Trace must have hidden <template> elements for tool result retrieval."""
    source = _session_source()
    assert "tool-result-" in source, (
        "Trace must have tool-result template id pattern"
    )


def test_tool_spans_have_data_attrs():
    """Each tool span must have data attributes for Inspector."""
    source = _session_source()
    assert "data-tool-name=" in source, (
        "Tool spans must have data-tool-name"
    )
    assert "data-tool-status=" in source, (
        "Tool spans must have data-tool-status"
    )
    assert "data-tool-idx=" in source, (
        "Tool spans must have data-tool-idx"
    )


def test_tool_spans_clickable():
    """Tool spans must be clickable via openToolInspector."""
    source = _session_source()
    assert "openToolInspector" in source, (
        "Trace must reference openToolInspector function"
    )


# ── Content modal removed in Phase 1.1 — negative assertions ────────


def test_open_content_modal_removed():
    """openContentModal must be removed (Phase 1.1)."""
    source = _session_source()
    assert "openContentModal" not in source, (
        "openContentModal must be removed (Phase 1.1)"
    )
    assert "switchContentView" not in source, (
        "switchContentView must be removed (Phase 1.1)"
    )
    assert "closeContentModal" not in source, (
        "closeContentModal must be removed (Phase 1.1)"
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
