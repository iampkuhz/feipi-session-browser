"""Tests for Trace panel DOM structure (v9).

v9 uses component-based Jinja2 macros:
- Rounds rendered via sdt.trace_round macro
- Tool calls rendered via sdt.tool_batch macro
- No inline llm-call-detail expansion
- Tool inspection via open-payload action on buttons
"""

from pathlib import Path

TEMPLATE_DIR = Path(__file__).parent.parent / "src" / "session_browser" / "web" / "templates"
COMPONENTS = TEMPLATE_DIR / "components"


def _session_source():
    return (TEMPLATE_DIR / "session.html").read_text(encoding="utf-8")


def _timeline_component():
    return (COMPONENTS / "session_detail_timeline.html").read_text(encoding="utf-8")


def _primitives_component():
    return (COMPONENTS / "session_detail_primitives.html").read_text(encoding="utf-8")


# ── No old inline detail patterns ───────────────────────────────────

def test_no_inline_llm_call_detail_rows():
    """Trace should NOT have old inline llm-call-detail rows."""
    source = _session_source()
    assert 'llm-call-detail' not in source, (
        "Trace must not contain llm-call-detail rows"
    )


def test_no_pre_block_class():
    """Trace should NOT contain .llm-call-detail__pre-block."""
    source = _session_source()
    assert 'llm-call-detail__pre-block' not in source


def test_no_request_context_label():
    """Trace should NOT contain 'Request Context:' inline label."""
    source = _session_source()
    assert 'Request Context:' not in source


# ── Tool rendering in component macro ──────────────────────────────

def test_tool_batch_has_tool_buttons():
    """Tool batch macro should have payload buttons for tool results."""
    source = _timeline_component()
    assert "open-payload" in source, "Tool rows should have open-payload buttons"


def test_tool_rows_have_call_id():
    """Tool rows should have data-tool-call-id for identification."""
    source = _timeline_component()
    assert "data-tool-call-id" in source, "Tool rows must have data-tool-call-id"


def test_spans_have_data_attributes():
    """Tool rows should have status and result attributes."""
    source = _timeline_component()
    assert "tool.result_summary" in source, "Tool rows must render result summary"
    assert "tool.status_tone" in source, "Tool rows must render status tone"


# ── Preview truncation ─────────────────────────────────────────────

def test_preview_has_truncation_in_viewmodel():
    """Preview text truncation is done in routes.py view model."""
    routes = (Path(__file__).parent.parent / "src" / "session_browser" / "web" / "routes.py").read_text(encoding="utf-8")
    # preview_title is truncated
    assert "[:120]" in routes or "[:80]" in routes, (
        "View model should truncate preview text"
    )
