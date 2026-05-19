"""Tests for payload modal and trace structure (v9).

v9 architecture:
- Component-based Jinja2 macros (sdp, sdt) replace inline HTML.
- Tool calls rendered via sdt.tool_batch macro in session_detail_timeline.html.
- Payload modal in base.html handles all payload viewing.
- Click delegation via _arpClosest helper in base.html.
"""

from pathlib import Path

TEMPLATE_DIR = Path(__file__).parent.parent / "src" / "session_browser" / "web" / "templates"


def _session_source():
    return (TEMPLATE_DIR / "session.html").read_text(encoding="utf-8")


def _base_source():
    return (TEMPLATE_DIR / "base.html").read_text(encoding="utf-8")


def _timeline_component():
    return (TEMPLATE_DIR / "components" / "session_detail_timeline.html").read_text(encoding="utf-8")


# ── Tool rendering (v9 component macros) ──────────────────


def test_has_tool_batch_macro():
    """Timeline component must define tool_batch macro."""
    source = _timeline_component()
    assert "macro tool_batch" in source, "tool_batch macro must exist"


def test_tool_rows_have_data_attrs():
    """Tool rows must have data attributes for identification."""
    source = _timeline_component()
    assert "data-tool-call-id" in source, "Tool rows must have data-tool-call-id"


def test_tool_rows_show_status():
    """Tool rows must render status information."""
    source = _timeline_component()
    assert "tool.result_summary" in source or "tool.status_tone" in source, (
        "Tool rows must show status"
    )


# ── Payload modal (base.html) ────────────────────────────────────


def test_payload_modal_in_base():
    """Payload modal must be defined in base.html."""
    source = _base_source()
    assert "payload-modal" in source, "payload-modal must exist in base.html"


# ── Event handling (base.html) ────────────────────────────────────


def test_capture_phase_click_listener():
    """base.html must have a capture-phase click listener for [data-content-modal]."""
    source = _base_source()
    assert "addEventListener('click'" in source, (
        "base.html must add click event listeners"
    )
    assert ", true)" in source, (
        "base.html must register a capture-phase click listener"
    )


def test_closest_polyfill():
    """base.html must define a closest helper for older WebView compatibility."""
    source = _base_source()
    assert "_arpClosest" in source, (
        "base.html must define _arpClosest helper function"
    )
    assert "webkitMatchesSelector" in source, (
        "base.html's _arpClosest must support webkitMatchesSelector"
    )


def test_capture_handler_sets_handled_flag():
    """The capture-phase handler must set e.__contentModalHandled."""
    source = _base_source()
    assert "__contentModalHandled" in source, (
        "Capture handler must set e.__contentModalHandled flag"
    )


# ── v9 component usage ────────────────────────────────────────────


def test_session_uses_sdt_macros():
    """session.html must use sdt macros."""
    source = _session_source()
    assert "sdt.hero" in source, "Should use sdt.hero macro"
    assert "sdt.trace_header" in source, "Should use sdt.trace_header macro"
    assert "sdt.trace_round" in source, "Should use sdt.trace_round macro"


def test_session_uses_sdp_import():
    """session.html must import sdp primitives."""
    source = _session_source()
    assert "import" in source and "sdp" in source, "Should import sdp primitives"
