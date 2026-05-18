"""Tests for LLM call card contract in session detail trace.

After Task 03, trace-detail must render LLM calls as first-class cards
with clear separation of:
- LLM call cards (.llm-call-card)
- User message cards (.message-card--user)
- Assistant message cards (.message-card--assistant)
- Tool calls nested under LLM calls (.llm-call-card__tools)
"""

import re
from pathlib import Path

TEMPLATE_DIR = Path(__file__).parent.parent / "src" / "session_browser" / "web" / "templates"


def _session_source():
    return (TEMPLATE_DIR / "session.html").read_text(encoding="utf-8")


# ── LLM call card structure ──────────────────────────────────────────


def test_has_llm_call_card():
    """Template must contain .llm-call-card elements."""
    source = _session_source()
    assert 'class="llm-call-card"' in source, (
        "Trace detail must use .llm-call-card for LLM calls"
    )


def test_llm_call_card_has_header():
    """Each .llm-call-card must have a header with title, model, scope, status."""
    source = _session_source()
    assert 'class="llm-call-card__header"' in source, (
        ".llm-call-card must have .llm-call-card__header"
    )
    assert 'class="llm-call-card__title"' in source, (
        "Header must include .llm-call-card__title"
    )
    assert 'class="llm-call-card__model"' in source, (
        "Header must include .llm-call-card__model"
    )
    assert 'llm-call-card__scope' in source, (
        "Header must include .llm-call-card__scope"
    )
    assert 'llm-call-card__status' in source, (
        "Header must include .llm-call-card__status"
    )


def test_llm_call_card_has_metrics():
    """Each .llm-call-card must have a metrics section."""
    source = _session_source()
    assert 'class="llm-call-card__metrics"' in source, (
        ".llm-call-card must have .llm-call-card__metrics"
    )


def test_llm_call_card_has_request_response_actions():
    """Each .llm-call-card must have Request and Response action buttons."""
    source = _session_source()
    assert 'data-payload-key="llm-R{{ round_idx }}-IX{{ ix_index }}-request"' in source, (
        "LLM call card must have Request button with llm-...-request payload key"
    )
    assert 'data-payload-key="llm-R{{ round_idx }}-IX{{ ix_index }}-response"' in source, (
        "LLM call card must have Response button with llm-...-response payload key"
    )


def test_llm_call_card_has_raw_action():
    """Each .llm-call-card must have a Raw action button."""
    source = _session_source()
    assert 'data-payload-key="llm-R{{ round_idx }}-IX{{ ix_index }}-raw"' in source, (
        "LLM call card must have Raw button with llm-...-raw payload key"
    )


def test_llm_call_card_has_tools_section():
    """Each .llm-call-card must have a tools section."""
    source = _session_source()
    assert 'class="llm-call-card__tools"' in source, (
        ".llm-call-card must have .llm-call-card__tools section"
    )
    assert 'class="llm-call-card__no-tools"' in source, (
        "Tools section must show 'No tool calls' when empty"
    )


# ── Tool calls nested under LLM call ─────────────────────────────────


def test_tool_calls_nested_under_llm_call():
    """Tool calls must appear inside .llm-call-card__tools, not at round level."""
    source = _session_source()
    # Find the llm-call-card__tools section and verify tool-call-row appears within it
    tools_section_match = re.search(
        r'llm-call-card__tools.*?tool-call-row',
        source,
        re.DOTALL
    )
    assert tools_section_match, (
        "Tool call rows must appear inside .llm-call-card__tools"
    )


def test_tool_call_row_has_data_attrs():
    """Each tool call row must have data attributes for Inspector."""
    source = _session_source()
    # tool-call-row elements inside llm-call-card__tools should have data attrs
    assert 'class="tool-call-row' in source, (
        "Tool calls must use .tool-call-row class"
    )
    assert 'data-tool-name=' in source, (
        "Tool call rows must have data-tool-name"
    )
    assert 'data-tool-status=' in source, (
        "Tool call rows must have data-tool-status"
    )
    assert 'data-tool-idx=' in source, (
        "Tool call rows must have data-tool-idx"
    )


# ── Message cards ────────────────────────────────────────────────────


def test_has_user_message_card():
    """Template must contain .message-card--user for user messages."""
    source = _session_source()
    assert 'class="message-card message-card--user"' in source, (
        "Trace detail must use .message-card--user for user messages"
    )
    assert 'class="message-card__header"' in source, (
        "Message card must have a header"
    )


def test_has_assistant_message_card():
    """Template must contain .message-card--assistant for assistant responses."""
    source = _session_source()
    assert 'class="message-card message-card--assistant"' in source, (
        "Trace detail must use .message-card--assistant for assistant responses"
    )


def test_message_card_has_actions():
    """User message card must have Open message and Raw buttons."""
    source = _session_source()
    assert 'data-payload-key="msg-R{{ loop.index }}-user"' in source, (
        "User message must have 'Open message' payload key"
    )
    assert 'data-payload-key="msg-R{{ loop.index }}-user-raw"' in source, (
        "User message must have 'Raw' payload key"
    )


# ── No LLM calls fallback ───────────────────────────────────────────


def test_no_llm_calls_fallback():
    """When a round has no interactions, show fallback message."""
    source = _session_source()
    assert 'No LLM calls captured for this round' in source, (
        "Must show fallback message when round has no LLM calls"
    )


# ── Payload registry ────────────────────────────────────────────────


def test_payload_registry_has_llm_request_key():
    """Payload registry must register llm-R{N}-IX{N}-request key."""
    source = _session_source()
    assert "llm-R{{ round_idx }}-IX{{ ix_index }}-request" in source, (
        "Payload registry must include llm-...-request key"
    )


def test_payload_registry_has_llm_response_key():
    """Payload registry must register llm-R{N}-IX{N}-response key."""
    source = _session_source()
    assert "llm-R{{ round_idx }}-IX{{ ix_index }}-response" in source, (
        "Payload registry must include llm-...-response key"
    )


def test_payload_registry_has_llm_raw_key():
    """Payload registry must register llm-R{N}-IX{N}-raw key."""
    source = _session_source()
    assert "llm-R{{ round_idx }}-IX{{ ix_index }}-raw" in source, (
        "Payload registry must include llm-...-raw key"
    )


def test_payload_registry_has_user_message_key():
    """Payload registry must register user message keys."""
    source = _session_source()
    assert "msg-R" in source and "-user" in source, (
        "Payload registry must include user message keys"
    )


# ── Negative: no flat span LLM rendering in detail ───────────────────


def test_no_flat_llm_span_in_detail():
    """Round detail must not render flat 'LLM #n ... Payload' span rows
    for LLM calls. The old pattern `class="span llm"` with `data-span-id="R...-IX`
    for interactions should be replaced by llm-call-card."""
    source = _session_source()
    # The old pattern had span llm with data-span-id containing -IX
    # Check that this specific pattern is no longer used for interactions
    old_llm_span = re.search(
        r'class="span llm"[^>]*data-span-id="R[^"]*-IX',
        source
    )
    assert old_llm_span is None, (
        "Round detail must not use flat span llm with IX data-span-id; "
        "use .llm-call-card instead"
    )


# ── CSS classes exist ────────────────────────────────────────────────


def test_css_has_llm_call_card_styles():
    """style.css must contain .llm-call-card styles."""
    css_path = Path(__file__).parent.parent / "src" / "session_browser" / "web" / "static" / "style.css"
    css = css_path.read_text(encoding="utf-8")
    assert ".llm-call-card" in css, (
        "CSS must define .llm-call-card styles"
    )
    assert ".llm-call-card__header" in css, (
        "CSS must define .llm-call-card__header styles"
    )
    assert ".llm-call-card__metrics" in css, (
        "CSS must define .llm-call-card__metrics styles"
    )
    assert ".llm-call-card__tools" in css, (
        "CSS must define .llm-call-card__tools styles"
    )


def test_css_has_message_card_styles():
    """style.css must contain .message-card styles."""
    css_path = Path(__file__).parent.parent / "src" / "session_browser" / "web" / "static" / "style.css"
    css = css_path.read_text(encoding="utf-8")
    assert ".message-card" in css, (
        "CSS must define .message-card styles"
    )
    assert ".message-card--user" in css, (
        "CSS must define .message-card--user styles"
    )
    assert ".message-card--assistant" in css, (
        "CSS must define .message-card--assistant styles"
    )
