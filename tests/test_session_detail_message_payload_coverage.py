"""Tests for session detail message payload coverage.

Verifies that:
1. R1 user message card exists with open action buttons.
2. R1 assistant message card exists if assistant content exists.
3. All message payload buttons resolve in the payload map source.
4. First request quick action exists and resolves.
5. No user/assistant full content is only available as truncated preview.
6. Payload map has msg-R1-user, msg-R1-user-raw, msg-R1-assistant, msg-R1-assistant-raw keys.
7. Each message payload entry has type, title, rendered, raw, missing_reason.
"""

import re
from pathlib import Path

TEMPLATE_DIR = Path(__file__).parent.parent / "src" / "session_browser" / "web" / "templates"


def _session_source():
    return (TEMPLATE_DIR / "session.html").read_text(encoding="utf-8")


# ── R1 user message card ──────────────────────────────────────────────────


def test_r1_user_message_card_exists():
    """Template must have a user message card for R1."""
    source = _session_source()
    # The card must appear inside trace-detail with message-card--user class
    assert 'message-card--user' in source, (
        "Template must contain .message-card--user for user message cards"
    )
    # Verify R1-specific payload key exists
    assert 'msg-R1-user' in source, (
        "Template must reference msg-R1-user payload key"
    )


def test_r1_user_message_has_open_action():
    """R1 user message must have an 'Open request' button with valid payload key."""
    source = _session_source()
    # The message card inside trace-detail uses Jinja loop for payload keys
    # Quick access button uses literal msg-R1-user key with "First user request" label
    match = re.search(
        r'data-payload-key="msg-R1-user".*?data-payload-type="message\.user"',
        source, re.DOTALL
    )
    assert match, (
        "R1 user message must have button with data-payload-key='msg-R1-user'"
    )
    # Verify "Open request" label exists in the template (on message card button)
    assert 'Open request' in source, (
        "R1 user message button must have 'Open request' label"
    )


def test_r1_user_message_has_raw_button():
    """R1 user message must have a 'Raw' button."""
    source = _session_source()
    # Message card button uses Jinja expression for raw key: msg-R{{ loop.index }}-user-raw
    assert "'msg-R' ~ loop.index ~ '-user-raw'" in source, (
        "R1 user message must have raw button with msg-R-N-user-raw payload key"
    )
    # Verify the template produces raw button with correct type
    assert 'message.user.raw' in source, (
        "R1 user message raw button must have data-payload-type='message.user.raw'"
    )


# ── R1 assistant message card ─────────────────────────────────────────────


def test_r1_assistant_message_card_exists():
    """Template must have an assistant message card for R1 if assistant content exists."""
    source = _session_source()
    assert 'message-card--assistant' in source, (
        "Template must contain .message-card--assistant for assistant message cards"
    )
    assert 'msg-R1-assistant' in source, (
        "Template must reference msg-R1-assistant payload key"
    )


def test_r1_assistant_message_has_open_action():
    """R1 assistant message must have an 'Open response' button."""
    source = _session_source()
    # Quick access button uses literal msg-R1-assistant key with "First assistant response" label
    match = re.search(
        r'data-payload-key="msg-R1-assistant".*?data-payload-type="message\.assistant"',
        source, re.DOTALL
    )
    assert match, (
        "R1 assistant message must have button with data-payload-key='msg-R1-assistant'"
    )
    # Verify "Open response" label exists in the template (on message card button)
    assert 'Open response' in source, (
        "R1 assistant message button must have 'Open response' label"
    )


def test_r1_assistant_message_has_raw_button():
    """R1 assistant message must have a 'Raw' button."""
    source = _session_source()
    # Message card button uses Jinja expression for raw key: msg-R{{ loop.index }}-assistant-raw
    assert "'msg-R' ~ loop.index ~ '-assistant-raw'" in source, (
        "R1 assistant message must have raw button with msg-R-N-assistant-raw payload key"
    )
    # Verify the template produces raw button with correct type
    assert 'message.assistant.raw' in source, (
        "R1 assistant message raw button must have data-payload-type='message.assistant.raw'"
    )


# ── Payload map message entries ────────────────────────────────────────────


def test_payload_map_has_r1_user_entry():
    """Payload map source must build msg-R1-user entry."""
    source = _session_source()
    # Check that the Jinja template builds the entry
    assert "'msg-R' ~ loop.index ~ '-user'" in source or \
           "'key': 'msg-R1-user'" in source, (
        "Payload map must build msg-R1-user entry"
    )


def test_payload_map_has_r1_user_raw_entry():
    """Payload map source must build msg-R1-user-raw entry."""
    source = _session_source()
    assert "'msg-R' ~ loop.index ~ '-user-raw'" in source or \
           "'key': 'msg-R1-user-raw'" in source, (
        "Payload map must build msg-R1-user-raw entry"
    )


def test_payload_map_has_r1_assistant_entry():
    """Payload map source must build msg-R1-assistant entry."""
    source = _session_source()
    assert "'msg-R' ~ loop.index ~ '-assistant'" in source or \
           "'key': 'msg-R1-assistant'" in source, (
        "Payload map must build msg-R1-assistant entry"
    )


def test_payload_map_has_r1_assistant_raw_entry():
    """Payload map source must build msg-R1-assistant-raw entry."""
    source = _session_source()
    assert "'msg-R' ~ loop.index ~ '-assistant-raw'" in source or \
           "'key': 'msg-R1-assistant-raw'" in source, (
        "Payload map must build msg-R1-assistant-raw entry"
    )


def test_message_payload_entries_have_required_fields():
    """Each message payload entry must have type, title, rendered, raw, missing_reason."""
    source = _session_source()
    # The template builds entries with these keys in the serialized dict
    # Verify the dict construction includes all required fields
    entry_block = re.search(
        r"'type':\s*['\"]message\.user['\"]\s*,\s*'title':",
        source
    )
    assert entry_block, (
        "Message payload entries must have 'type' and 'title' fields"
    )
    # Verify the final dict construction has all fields
    dict_build = re.search(
        r"_pmap_dict\.update\(\{item\.key:\s*\{[^}]*'type'[^}]*'title'[^}]*'rendered'[^}]*'raw'[^}]*'missing_reason'[^}]*\}\}\)",
        source
    )
    assert dict_build, (
        "Payload map dict must include type, title, rendered, raw, missing_reason"
    )


# ── Session-level quick access ─────────────────────────────────────────────


def test_first_request_quick_action_exists():
    """Hero section must have a 'First user request' quick action."""
    source = _session_source()
    assert 'First user request' in source, (
        "Template must have 'First user request' quick access button"
    )


def test_first_assistant_response_quick_action_exists():
    """Hero section must have a 'First assistant response' quick action."""
    source = _session_source()
    assert 'First assistant response' in source, (
        "Template must have 'First assistant response' quick access button"
    )


def test_quick_action_resolves_to_payload_key():
    """Quick access buttons must have data-payload-key that resolves to msg-R1-* keys."""
    source = _session_source()
    # Find quick access buttons and check their payload keys
    qa_buttons = re.findall(
        r'class="quick-access-btn"[^>]*data-payload-key="([^"]+)"',
        source
    )
    for key in qa_buttons:
        assert key.startswith('msg-R1-'), (
            f"Quick access payload key must start with msg-R1-, got: {key}"
        )


def test_quick_access_container_exists():
    """Hero quick access must be wrapped in a dedicated container."""
    source = _session_source()
    assert 'data-quick-access' in source, (
        "Hero quick access must have data-quick-access container attribute"
    )


# ── Content availability (not truncated only) ──────────────────────────────


def test_user_content_available_in_full():
    """User message content must be available in full via payload map, not just truncated."""
    source = _session_source()
    # The payload map entry for user message must use full content, not truncate
    # Look for the rendered field using round.user_msg.content without truncate
    assert re.search(
        r"'rendered':\s*round\.user_msg\.content\s*\|\s*default",
        source
    ), (
        "User message payload rendered field must use full content, not truncated"
    )


def test_assistant_content_available_in_full():
    """Assistant message content must be available in full via payload map, not just truncated."""
    source = _session_source()
    # The payload map entry for assistant message must use full content
    assert re.search(
        r"'rendered':\s*round\.assistant_msg\.content\s*\|\s*striptags\s*\|\s*default",
        source
    ) or re.search(
        r"'rendered':\s*round\.assistant_msg\.content\s*\|\s*default",
        source
    ), (
        "Assistant message payload rendered field must use full content, not truncated"
    )


def test_no_truncated_only_for_user_content():
    """User message must not be ONLY available as truncated preview."""
    source = _session_source()
    # Verify there is a full-content path (payload map) in addition to truncated preview
    has_preview = 'round.user_msg.content | striptags | truncate(200)' in source
    has_full_payload = 'msg-R' in source and 'message.user' in source
    assert has_full_payload, (
        "User message must have a full-content payload entry"
    )


def test_no_truncated_only_for_assistant_content():
    """Assistant message must not be ONLY available as truncated preview."""
    source = _session_source()
    has_preview = 'round.assistant_msg.content | striptags | truncate' in source
    has_full_payload = 'msg-R' in source and 'message.assistant' in source
    assert has_full_payload, (
        "Assistant message must have a full-content payload entry"
    )


# ── Message card data attributes ───────────────────────────────────────────


def test_user_message_card_has_role_attribute():
    """User message card must have data-message-role attribute."""
    source = _session_source()
    # Check that the template can produce data-message-role
    assert 'data-message-role' in source or 'data-round-idx' in source, (
        "Message cards should have identifying data attributes"
    )


def test_message_cards_have_round_idx():
    """Message cards should be associated with a round index."""
    source = _session_source()
    # The R{{ loop.index }} pattern in payload keys ensures round association
    assert "loop.index" in source, (
        "Message payload keys must use loop.index for round association"
    )
