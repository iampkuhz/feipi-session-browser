"""source_units 细粒度来源关联测试。"""

from __future__ import annotations

from session_browser.attribution.agents.claude_code_attribution_builder import (
    ClaudeCodeAttributionBuilder,
)
from session_browser.attribution.agents.claude_code_parts.utils import (
    extract_tool_name,
    mask_sensitive_keys,
    tool_description,
    truncate_preview,
)
from session_browser.attribution.agents.claude_code_tool_schemas import get_tool_schema_tokens
from session_browser.attribution.context import (
    _mask_sensitive_keys as context_mask_sensitive_keys,
    _truncate_preview as context_truncate_preview,
)
from session_browser.domain.models import ChatMessage, ConversationRound, LLMCall


def _make_lc(**kwargs):
    defaults = dict(
        id="llm-test", model="claude-sonnet-4-20250514", scope="main",
        subagent_id="", round_index=0, parent_id="", parent_tool_name="",
        timestamp="2025-01-01T00:00:00Z", status="ok",
        input_tokens=10000, output_tokens=3000,
        cache_read_tokens=5000, cache_write_tokens=1000,
        finish_reason="end_turn", content_blocks=[],
        response_full="", request_full="", tool_calls_raw="",
    )
    defaults.update(kwargs)
    return LLMCall(**defaults)


def _make_ro(user_content: str = "hello") -> ConversationRound:
    return ConversationRound(
        round_index=0,
        user_msg=ChatMessage(role="user", content=user_content, timestamp="2025-01-01T00:00:00Z"),
        assistant_msg=ChatMessage(role="assistant", content="hi", timestamp="2025-01-01T00:00:00Z"),
    )


def _unit(candidate: str, direction: str, text: str, index: int = 1) -> dict:
    return {
        "source_id": f"test:{direction}:{candidate}:{index}",
        "dedupe_key": f"dedupe:{direction}:{candidate}:{index}",
        "origin_path": f"fixture.{candidate}",
        "canonical_source_locator": f"fixture:{candidate}:{index}",
        "unit_type": f"{candidate}_unit",
        "candidate": candidate,
        "direction": direction,
        "event_order": 1,
        "part_index": index,
        "byte_range": [0, len(text.encode("utf-8"))],
        "text": text,
        "label": candidate,
        "preview": text[:120],
    }


def _builder(*units: dict, input_tokens: int = 10000, output_tokens: int = 3000):
    return ClaudeCodeAttributionBuilder(
        llm_call=_make_lc(input_tokens=input_tokens, output_tokens=output_tokens),
        round_obj=_make_ro("Tell me about cats"),
        session_context={"normalized_call": {"call_id": "llm-test", "source_units": list(units)}},
    )


class TestToolDescriptions:
    def test_known_tool_read(self):
        assert "file" in tool_description("Read")

    def test_known_tool_write(self):
        assert "file" in tool_description("Write")

    def test_known_tool_edit(self):
        assert "replacements" in tool_description("Edit")

    def test_known_tool_bash(self):
        assert "command" in tool_description("Bash")

    def test_known_tool_grep(self):
        assert "regular" in tool_description("Grep")

    def test_known_tool_glob(self):
        assert "pattern" in tool_description("Glob")

    def test_known_tool_ls(self):
        assert "目录" in tool_description("LS")

    def test_known_tool_agent(self):
        assert "agent" in tool_description("Agent").lower()

    def test_known_tool_todo_write(self):
        assert "task" in tool_description("TodoWrite").lower()

    def test_known_tool_web_fetch(self):
        assert "URL" in tool_description("WebFetch")

    def test_unknown_tool_fallback(self):
        assert "未知" in tool_description("SomeUnknownTool")


class TestToolSchemaTokens:
    def test_large_tool_has_more_tokens(self):
        assert get_tool_schema_tokens("Bash") >= 240

    def test_small_tool_has_tokens(self):
        assert get_tool_schema_tokens("Agent") >= 200


class TestExtractToolName:
    def test_empty_returns_unknown(self):
        assert extract_tool_name("") == "unknown"

    def test_none_returns_unknown(self):
        assert extract_tool_name(None) == "unknown"

    def test_fallback_first_word(self):
        assert extract_tool_name("Read output: hello world") == "Read"

    def test_caps_long_name(self):
        name = extract_tool_name("abcdefghijklmnopqrstuvwxyz1234567890 result")
        assert len(name) <= 30


class TestMaskSensitiveKeys:
    def test_api_key_masked(self):
        text = 'api_key: "sk-1234567890"'
        result = mask_sensitive_keys(text)
        assert "sk-1234567890" not in result
        assert "MASKED" in result

    def test_token_masked(self):
        text = "token = abc123secret"
        result = mask_sensitive_keys(text)
        assert "abc123secret" not in result
        assert "MASKED" in result

    def test_password_masked(self):
        text = '"password": "supersecret"'
        result = mask_sensitive_keys(text)
        assert "supersecret" not in result
        assert "MASKED" in result

    def test_authorization_masked(self):
        text = "authorization: Bearer eyJhbGciOi"
        result = mask_sensitive_keys(text)
        assert "eyJhbGciOi" not in result
        assert "MASKED" in result

    def test_normal_text_unchanged(self):
        assert "Hello world" in mask_sensitive_keys("Hello world, this is normal content.")

    def test_empty_string(self):
        assert mask_sensitive_keys("") == ""

    def test_context_masking_api_key(self):
        result = context_mask_sensitive_keys('{"api_key": "secret-value-123"}')
        assert "secret-value-123" not in result
        assert "MASKED" in result


class TestTruncatePreview:
    def test_short_text_unchanged(self):
        assert truncate_preview("Hello", 200) == "Hello"

    def test_long_text_truncated(self):
        result = truncate_preview("A" * 300, 100)
        assert len(result) == 101
        assert result.endswith("…")

    def test_context_truncate_short(self):
        assert context_truncate_preview("Hi", 50) == "Hi"

    def test_context_truncate_long(self):
        result = context_truncate_preview("X" * 500, 50)
        assert len(result) == 51
        assert result.endswith("…")

    def test_empty_string(self):
        assert truncate_preview("", 100) == ""


class TestSourceUnitBucketDetails:
    def test_tool_definitions_use_source_unit_details(self):
        result = _builder(_unit("tool_definitions", "request", "Read Write Bash schemas")).build_request()
        bucket = next(b for b in result.buckets if b.key == "tool_definitions")

        assert bucket.details["kind"] == "source_units"
        item = bucket.details["items"][0]
        assert item["source_id"] == "test:request:tool_definitions:1"
        assert item["origin_path"] == "fixture.tool_definitions"
        assert item["unit_type"] == "tool_definitions_unit"
        assert item["preview"]

    def test_instruction_source_unit_maps_to_instruction_context(self):
        result = _builder(_unit("system_instructions", "request", "项目行为规则")).build_request()
        bucket = next(b for b in result.buckets if b.key == "instruction_context")

        assert bucket.details["candidate"] == "system_instructions"
        assert bucket.details["items"][0]["label"] == "system_instructions"

    def test_prior_messages_use_conversation_history_candidate(self):
        result = _builder(_unit("conversation_history", "request", "prior user", 1)).build_request()
        bucket = next(b for b in result.buckets if b.key == "conversation_messages")

        assert bucket.details["kind"] == "source_units"
        assert bucket.details["items"][0]["unit_type"] == "conversation_history_unit"

    def test_current_user_input_has_preview(self):
        result = _builder(_unit("user_input", "request", "Tell me about cats")).build_request()
        bucket = next(b for b in result.buckets if b.key == "current_user_input")

        assert bucket.details["candidate"] == "user_input"
        assert "cats" in bucket.details["items"][0]["preview"]

    def test_unlocated_residual_is_not_fake_source_text(self):
        result = _builder(_unit("user_input", "request", "small"), input_tokens=1000).build_request()
        bucket = next(b for b in result.buckets if b.key == "unlocated_residual")

        assert bucket.details == {}
        assert bucket.tokens >= 0

    def test_response_tool_call_details_are_actual_output_source_units(self):
        result = _builder(_unit("tool_calls", "response", "Bash({command: pytest -q})")).build_response()
        bucket = next(b for b in result.buckets if b.key == "tool_call")

        assert bucket.details["kind"] == "source_units"
        assert bucket.details["candidate"] == "tool_calls"
        assert "pytest" in bucket.details["items"][0]["preview"]
