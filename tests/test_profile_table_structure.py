"""Tests for Profile (Calls) table DOM structure.

After profile refactoring, inline LLM call details were moved to the Inspector.
The Calls view (data-view="calls") uses a div-based data-table structure.

Ensures that:
- Profile/Calls view does NOT have inline llm-call-detail expansion rows.
- Profile does NOT contain .llm-call-detail__pre-block elements.
- Profile does NOT contain "Request Context:" inline label.
- Each profile row has a clickable entry calling openLLMInspector.
- Hidden Inspector templates exist for content retrieval.
- Preview column has truncation class.
"""

import re
from pathlib import Path

TEMPLATE_DIR = Path(__file__).parent.parent / "src" / "session_browser" / "web" / "templates"


def _session_source():
    return (TEMPLATE_DIR / "session.html").read_text(encoding="utf-8")


# ── Profile must NOT have inline detail expansion ────────────────────

def test_no_inline_llm_call_detail_rows():
    """Profile should NOT expand inline detail rows — details belong in Inspector."""
    source = _session_source()
    assert 'llm-call-detail' not in source, (
        "Calls view must not contain llm-call-detail rows — "
        "inline detail expansion should be removed; use Inspector instead"
    )


def test_no_pre_block_class():
    """Profile should NOT contain .llm-call-detail__pre-block — no large inline <pre>."""
    source = _session_source()
    assert 'llm-call-detail__pre-block' not in source, (
        "Calls view must not contain .llm-call-detail__pre-block — "
        "large inline <pre> blocks cause unstable row height"
    )


def test_no_request_context_label():
    """Profile should NOT contain 'Request Context:' inline label."""
    source = _session_source()
    assert 'Request Context:' not in source, (
        "Calls view must not contain 'Request Context:' label — "
        "this confuses rendered context with request payload"
    )


# ── Profile must have Inspector entry points ─────────────────────────

def test_rows_call_openLLMInspector():
    """Each profile row must be clickable via openLLMInspector."""
    source = _session_source()
    assert 'openLLMInspector' in source, (
        "Calls view must reference openLLMInspector function"
    )


def test_has_inspector_templates():
    """Profile must have hidden <template> elements for Inspector retrieval."""
    source = _session_source()
    assert "inspect-request" in source, (
        "Calls view must have inspect-request template id pattern"
    )
    assert "inspect-response" in source, (
        "Calls view must have inspect-response template id pattern"
    )


# ── Marker / data attributes ─────────────────────────────────────────

def test_rows_have_data_attributes():
    """Each row must have data attributes for Inspector."""
    source = _session_source()
    assert "data-call-idx=" in source, (
        "Calls rows must have data-call-idx"
    )
    assert "data-model=" in source, (
        "Calls rows must have data-model"
    )
    assert "data-llm-call-id=" in source or "data-call-idx=" in source, (
        "Calls rows must have an identifier data attribute"
    )


# ── Preview truncation ───────────────────────────────────────────────

def test_preview_has_truncation():
    """Preview column must have truncation applied."""
    source = _session_source()
    # Check that preview text uses truncation (either via truncate filter or CSS)
    assert "truncate" in source, (
        "Calls view must have truncation for preview text"
    )
