"""Tests for Trace panel DOM structure after Phase 1 simplification.

After Phase 1 simplification:
- Calls/Hotspots views removed; trace is the only workbench view
- Inline detail expansion is removed — tool inspection uses openToolInspector
- Tool spans have data attributes for Inspector integration
- Trace uses trace-row + trace-detail structure for rounds
"""

import re
from pathlib import Path

TEMPLATE_DIR = Path(__file__).parent.parent / "src" / "session_browser" / "web" / "templates"


def _session_source():
    return (TEMPLATE_DIR / "session.html").read_text(encoding="utf-8")


# ── Trace must NOT have old inline detail expansion ────────────────────

def test_no_inline_llm_call_detail_rows():
    """Trace should NOT expand inline llm-call-detail rows."""
    source = _session_source()
    assert 'llm-call-detail' not in source, (
        "Trace must not contain llm-call-detail rows — "
        "inspection belongs in Inspector"
    )


def test_no_pre_block_class():
    """Trace should NOT contain .llm-call-detail__pre-block."""
    source = _session_source()
    assert 'llm-call-detail__pre-block' not in source, (
        "Trace must not contain .llm-call-detail__pre-block"
    )


def test_no_request_context_label():
    """Trace should NOT contain 'Request Context:' inline label."""
    source = _session_source()
    assert 'Request Context:' not in source, (
        "Trace must not contain 'Request Context:' label"
    )


# ── Trace has tool inspection entry points ─────────────────────────

def test_spans_call_openToolInspector():
    """Each tool span must be clickable via openToolInspector."""
    source = _session_source()
    assert 'openToolInspector' in source, (
        "Trace must reference openToolInspector function"
    )


def test_has_tool_result_templates():
    """Trace must have hidden <template> elements for tool result retrieval."""
    source = _session_source()
    assert "tool-result-" in source, (
        "Trace must have tool-result template id pattern"
    )


# ── Marker / data attributes ─────────────────────────────────────────

def test_spans_have_data_attributes():
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


# ── Preview truncation ───────────────────────────────────────────────

def test_preview_has_truncation():
    """Preview text must have truncation applied."""
    source = _session_source()
    # Check that preview text uses truncation (either via truncate filter or CSS)
    assert "truncate" in source, (
        "Trace must have truncation for preview text"
    )
