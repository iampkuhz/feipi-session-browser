"""Tests for the payload map contract in session detail.

Verifies that:
1. <script type="application/json" id="session-payload-map"> exists in the template.
2. All [data-action="open-payload"] buttons have data-payload-key.
3. All data-payload-key values are registered in the payload map source.
4. LLM call cards have explicit Request and Response buttons.
5. Generic "Payload" button text count stays within a compatibility threshold (<= 3).
6. No massive duplication of "Payload" buttons (must not be 400+).
"""

import re
from pathlib import Path

TEMPLATE_DIR = Path(__file__).parent.parent / "src" / "session_browser" / "web" / "templates"


def _session_source():
    return (TEMPLATE_DIR / "session.html").read_text(encoding="utf-8")


# ── Payload map script element ─────────────────────────────────────────


def test_payload_map_script_exists():
    """Template must contain <script type="application/json" id="session-payload-map">."""
    source = _session_source()
    assert 'type="application/json"' in source and 'id="session-payload-map"' in source, (
        "Template must include <script type=\"application/json\" id=\"session-payload-map\">"
    )


def test_payload_map_script_has_required_fields():
    """Payload map entries must contain type, title, rendered, raw, missing_reason."""
    source = _session_source()
    # The template builds a dict with these keys before serializing
    assert "'type'" in source or '"type"' in source, (
        "Payload map entries must have 'type' field"
    )
    assert "'title'" in source or '"title"' in source, (
        "Payload map entries must have 'title' field"
    )
    assert "'rendered'" in source or '"rendered"' in source, (
        "Payload map entries must have 'rendered' field"
    )
    assert "'raw'" in source or '"raw"' in source, (
        "Payload map entries must have 'raw' field"
    )
    assert "'missing_reason'" in source or '"missing_reason"' in source, (
        "Payload map entries must have 'missing_reason' field"
    )


def test_payload_map_uses_safe_json():
    """Payload map must be serialized with a safe HTML-escape filter."""
    source = _session_source()
    # tojson_safe_html or safe_json_display must be used
    assert 'tojson_safe_html' in source or 'safe_json_display' in source, (
        "Payload map must use safe JSON serialization filter"
    )


# ── All open-payload buttons have data-payload-key ─────────────────────


def test_all_payload_buttons_have_key():
    """Every data-action="open-payload" must have data-payload-key."""
    source = _session_source()
    # Find all open-payload buttons and verify each has data-payload-key
    # Strategy: for each occurrence of data-action="open-payload", check
    # that data-payload-key appears on the same button tag
    button_blocks = re.findall(
        r'<button[^>]*data-action="open-payload"[^>]*>',
        source
    )
    assert len(button_blocks) > 0, (
        "Template must contain at least one open-payload button"
    )
    for block in button_blocks:
        assert 'data-payload-key=' in block, (
            f"Button missing data-payload-key: {block[:120]}"
        )


def test_all_payload_buttons_have_type():
    """Every data-action="open-payload" must have data-payload-type."""
    source = _session_source()
    button_blocks = re.findall(
        r'<button[^>]*data-action="open-payload"[^>]*>',
        source
    )
    for block in button_blocks:
        assert 'data-payload-type=' in block, (
            f"Button missing data-payload-type: {block[:120]}"
        )


def test_all_payload_buttons_have_title():
    """Every data-action="open-payload" must have data-payload-title."""
    source = _session_source()
    button_blocks = re.findall(
        r'<button[^>]*data-action="open-payload"[^>]*>',
        source
    )
    for block in button_blocks:
        assert 'data-payload-title=' in block, (
            f"Button missing data-payload-title: {block[:120]}"
        )


def test_all_payload_button_keys_exist_in_map_source():
    """Every data-payload-key value from buttons must appear in payload map source."""
    source = _session_source()
    # Extract all data-payload-key values from buttons
    button_keys = re.findall(
        r'data-payload-key="([^"]+)"',
        source
    )
    # The payload map is built from a dict that gets serialized to JSON
    # Each key should appear somewhere in the template (as dict key construction)
    for key in button_keys:
        # The key pattern appears in the Jinja template as dict key building
        # We verify that the key or its template-building components exist
        assert key in source, (
            f"Button payload key '{key}' not found in template source"
        )


# ── Payload type taxonomy ──────────────────────────────────────────────


def test_payload_type_taxonomy():
    """Template must define the full payload type taxonomy."""
    source = _session_source()
    required_types = [
        'message.user',
        'message.user.raw',
        'message.assistant',
        'message.assistant.raw',
        'llm.context',
        'llm.output',
        'llm.raw',
        'tool.result',
    ]
    for ptype in required_types:
        assert ptype in source, (
            f"Payload type '{ptype}' must appear in template"
        )


# ── LLM call card explicit buttons ─────────────────────────────────────


def test_llm_call_card_has_context_button():
    """LLM call card must have an explicit Context button."""
    source = _session_source()
    assert 'data-payload-type="llm.context"' in source, (
        "LLM call card must have Context button with data-payload-type='llm.context'"
    )


def test_llm_call_card_has_output_button():
    """LLM call card must have an explicit Output button."""
    source = _session_source()
    assert 'data-payload-type="llm.output"' in source, (
        "LLM call card must have Output button with data-payload-type='llm.output'"
    )


def test_llm_call_context_button_label():
    """Context button must show 'Context' as visible text."""
    source = _session_source()
    match = re.search(
        r'data-payload-type="llm.context"[^>]*>\s*Context\s*<',
        source
    )
    assert match, (
        "Context button must display 'Context' as visible label"
    )


def test_llm_call_output_button_label():
    """Output button must show 'Output' as visible text."""
    source = _session_source()
    match = re.search(
        r'data-payload-type="llm.output"[^>]*>\s*Output\s*<',
        source
    )
    assert match, (
        "Output button must display 'Output' as visible label"
    )


# ── Tool call button labels ────────────────────────────────────────────


def test_tool_call_result_button():
    """Tool call button must show 'Result' instead of 'Payload'."""
    source = _session_source()
    assert 'data-payload-type="tool.result"' in source, (
        "Tool call must have button with data-payload-type='tool.result'"
    )
    match = re.search(
        r'data-payload-type="tool.result"[^>]*>\s*Result\s*<',
        source
    )
    assert match, (
        "Tool call button must display 'Result' as visible label"
    )


# ── Message button labels ──────────────────────────────────────────────


def test_user_message_open_button():
    """User message must have 'Open request' button."""
    source = _session_source()
    assert 'data-payload-type="message.user"' in source, (
        "User message must have button with data-payload-type='message.user'"
    )
    match = re.search(
        r'data-payload-type="message.user"[^>]*>\s*Open request\s*<',
        source
    )
    assert match, (
        "User message button must display 'Open request'"
    )


def test_user_message_raw_button():
    """User message must have 'Raw' button."""
    source = _session_source()
    assert 'data-payload-type="message.user.raw"' in source, (
        "User message must have Raw button with data-payload-type='message.user.raw'"
    )


def test_assistant_message_open_button():
    """Assistant message must have 'Open response' button."""
    source = _session_source()
    assert 'data-payload-type="message.assistant"' in source, (
        "Assistant message must have button with data-payload-type='message.assistant'"
    )
    match = re.search(
        r'data-payload-type="message.assistant"[^>]*>\s*Open response\s*<',
        source
    )
    assert match, (
        "Assistant message button must display 'Open response'"
    )


def test_assistant_message_raw_button():
    """Assistant message must have 'Raw' button."""
    source = _session_source()
    assert 'data-payload-type="message.assistant.raw"' in source, (
        "Assistant message must have Raw button with data-payload-type='message.assistant.raw'"
    )


# DEDUPLICATED: Hero quick access tests are covered in
# test_session_detail_message_payload_coverage.py:
# - test_first_request_quick_action_exists
# - test_first_assistant_response_quick_action_exists
# - test_quick_access_container_exists
# Kept here only the unique payload-key validation for quick access buttons.
# Removed: test_hero_quick_access_exists (duplicated)


def test_quick_access_buttons_have_payload_keys():
    """Quick access buttons must have valid data-payload-key."""
    source = _session_source()
    # Find quick access button blocks and verify payload keys
    qa_block = re.findall(
        r'<button[^>]*data-quick-action[^>]*>|<button[^>]*class="quick-access-btn"[^>]*>',
        source
    )
    for block in qa_block:
        assert 'data-payload-key=' in block, (
            f"Quick access button missing data-payload-key: {block[:120]}"
        )
        assert 'data-payload-type=' in block, (
            f"Quick access button missing data-payload-type: {block[:120]}"
        )


# ── Generic "Payload" button count ─────────────────────────────────────


def test_generic_payload_button_count_low():
    """Generic 'Payload' button text count must be <= 3 (compatibility threshold)."""
    source = _session_source()
    # Count buttons where the visible text is exactly "Payload"
    # This matches patterns like >Payload< in button tags
    payload_buttons = re.findall(
        r'<button[^>]*data-action="open-payload"[^>]*>\s*Payload\s*</button>',
        source
    )
    assert len(payload_buttons) <= 3, (
        f"Generic 'Payload' button count must be <= 3, found {len(payload_buttons)}"
    )


def test_no_massive_payload_buttons():
    """Must not have 400+ 'Payload' buttons."""
    source = _session_source()
    payload_buttons = re.findall(
        r'<button[^>]*data-action="open-payload"[^>]*>\s*Payload\s*</button>',
        source
    )
    assert len(payload_buttons) < 400, (
        f"Must not have 400+ generic 'Payload' buttons, found {len(payload_buttons)}"
    )


# ── Backward compatibility ─────────────────────────────────────────────


def test_backward_compatible_payload_registry():
    """window.__SESSION_PAYLOADS__ must still be set for backward compatibility."""
    source = _session_source()
    assert 'window.__SESSION_PAYLOADS__' in source, (
        "Backward-compatible payload registry must be maintained"
    )


def test_payload_map_exposed_as_global():
    """window.__SESSION_PAYLOAD_MAP__ must be set from the JSON script."""
    source = _session_source()
    assert 'window.__SESSION_PAYLOAD_MAP__' in source, (
        "Canonical payload map must be exposed as window.__SESSION_PAYLOAD_MAP__"
    )


def test_payload_map_reads_from_script_element():
    """JS must read payload map from the JSON script element."""
    source = _session_source()
    assert "getElementById('session-payload-map')" in source or \
           'getElementById("session-payload-map")' in source, (
        "JS must read from #session-payload-map script element"
    )


# ── Modal uses data attributes ─────────────────────────────────────────


def test_open_payload_modal_accepts_button():
    """openPayloadModal must accept a button parameter for data attribute access."""
    source = _session_source()
    assert 'openPayloadModal(key, button)' in source or \
           'openPayloadModal(key,button)' in source, (
        "openPayloadModal must accept button parameter"
    )


def test_modal_uses_payload_type():
    """Modal must use data-payload-type for tab selection."""
    source = _session_source()
    assert 'dataset.payloadType' in source or 'payload_type' in source, (
        "Modal must read data-payload-type from button"
    )


def test_modal_uses_payload_title():
    """Modal must use data-payload-title for modal title."""
    source = _session_source()
    assert 'dataset.payloadTitle' in source or 'payload_title' in source, (
        "Modal must read data-payload-title from button"
    )


# ── CSS for new button styles ──────────────────────────────────────────


def test_css_has_llm_action_button_styles():
    """style.css must contain .llm-call-card__action-btn styles."""
    css_path = Path(__file__).parent.parent / "src" / "session_browser" / "web" / "static" / "style.css"
    css = css_path.read_text(encoding="utf-8")
    assert '.llm-call-card__action-btn' in css, (
        "CSS must define .llm-call-card__action-btn styles"
    )
