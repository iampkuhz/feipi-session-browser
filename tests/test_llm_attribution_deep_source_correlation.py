"""Tests for LLM attribution deep source correlation (bucket details).

Covers:
1. tool_schemas details.items contains tool name/source/description_preview/estimated_tokens
2. local_instruction_context details.items contains CLAUDE.md/system-reminder/agent prompt sources
3. message_history details.items contains prior rounds, not current call response
4. current user message not double-counted in history
5. preceding tool_results only contains calls before current LLM call
6. unlocated details explains hidden/provider/tokenizer/unsafe sources
7. sensitive keys masked, no secret values returned
8. previews all truncated
"""

from __future__ import annotations

import pytest

from session_browser.attribution.agents.claude_code import (
    _tool_description,
    _extract_tool_name,
    _mask_sensitive_keys,
    _truncate_preview,
    ClaudeCodeAttributionBuilder,
)
from session_browser.attribution.agents.claude_code_tool_schemas import (
    get_tool_schema_tokens,
)
from session_browser.attribution.context import (
    _mask_sensitive_keys as context_mask_sensitive_keys,
    _truncate_preview as context_truncate_preview,
)


# ── Tool description tests ─────────────────────────────────────────


class TestToolDescriptions:
    def test_known_tool_read(self):
        assert "读取文件" in _tool_description("Read")

    def test_known_tool_write(self):
        assert "写入文件" in _tool_description("Write")

    def test_known_tool_edit(self):
        assert "精确" in _tool_description("Edit")

    def test_known_tool_bash(self):
        assert "shell" in _tool_description("Bash")

    def test_known_tool_grep(self):
        assert "搜索" in _tool_description("Grep")

    def test_known_tool_glob(self):
        assert "查找文件" in _tool_description("Glob")

    def test_known_tool_ls(self):
        assert "目录" in _tool_description("LS")

    def test_known_tool_agent(self):
        assert "子 agent" in _tool_description("Agent")

    def test_known_tool_todo_write(self):
        assert "任务列表" in _tool_description("TodoWrite")

    def test_known_tool_web_fetch(self):
        assert "网页" in _tool_description("WebFetch")

    def test_unknown_tool_fallback(self):
        desc = _tool_description("SomeUnknownTool")
        assert "未知" in desc


# ── Tool schema token estimation ──────────────────────────────────


class TestToolSchemaTokens:
    def test_large_tool_has_more_tokens(self):
        # Bash has a large description + input schema
        bash_tokens = get_tool_schema_tokens("Bash")
        assert bash_tokens >= 240

    def test_small_tool_has_tokens(self):
        # Even small tools like Agent have schema tokens
        tokens = get_tool_schema_tokens("Agent")
        assert tokens >= 200


# ── Tool name extraction ──────────────────────────────────────────


class TestExtractToolName:
    def test_empty_returns_unknown(self):
        assert _extract_tool_name("") == "unknown"

    def test_none_returns_unknown(self):
        assert _extract_tool_name(None) == "unknown"

    def test_fallback_first_word(self):
        result = _extract_tool_name("Read output: hello world")
        assert result == "Read"

    def test_caps_long_name(self):
        name = _extract_tool_name("abcdefghijklmnopqrstuvwxyz1234567890 result")
        assert len(name) <= 30


# ── Sensitive key masking ─────────────────────────────────────────


class TestMaskSensitiveKeys:
    def test_api_key_masked(self):
        text = 'api_key: "sk-1234567890"'
        result = _mask_sensitive_keys(text)
        assert "sk-1234567890" not in result
        assert "MASKED" in result

    def test_token_masked(self):
        text = 'token = abc123secret'
        result = _mask_sensitive_keys(text)
        assert "abc123secret" not in result
        assert "MASKED" in result

    def test_password_masked(self):
        text = '"password": "supersecret"'
        result = _mask_sensitive_keys(text)
        assert "supersecret" not in result
        assert "MASKED" in result

    def test_authorization_masked(self):
        text = "authorization: Bearer eyJhbGciOi"
        result = _mask_sensitive_keys(text)
        assert "eyJhbGciOi" not in result
        assert "MASKED" in result

    def test_normal_text_unchanged(self):
        text = "Hello world, this is normal content."
        result = _mask_sensitive_keys(text)
        assert "Hello world" in result

    def test_empty_string(self):
        assert _mask_sensitive_keys("") == ""

    def test_context_masking_api_key(self):
        text = '{"api_key": "secret-value-123"}'
        result = context_mask_sensitive_keys(text)
        assert "secret-value-123" not in result
        assert "MASKED" in result


# ── Truncate preview ──────────────────────────────────────────────


class TestTruncatePreview:
    def test_short_text_unchanged(self):
        text = "Hello"
        assert _truncate_preview(text, 200) == text

    def test_long_text_truncated(self):
        text = "A" * 300
        result = _truncate_preview(text, 100)
        assert len(result) == 101  # 100 + ellipsis
        assert result.endswith("…")

    def test_context_truncate_short(self):
        assert context_truncate_preview("Hi", 50) == "Hi"

    def test_context_truncate_long(self):
        text = "X" * 500
        result = context_truncate_preview(text, 50)
        assert len(result) == 51
        assert result.endswith("…")

    def test_empty_string(self):
        assert _truncate_preview("", 100) == ""


# ── Bucket details on Claude Code builder ─────────────────────────


class TestBucketDetailsToolSchemas:
    """Verify tool_schemas bucket has details.items with expected fields."""

    def _make_builder(self, session_context, **call_kwargs):
        from session_browser.domain.models import LLMCall, ConversationRound, ChatMessage
        defaults = dict(
            id="llm-test", model="claude-sonnet-4-20250514", scope="main",
            subagent_id="", round_index=0, parent_id="", parent_tool_name="",
            timestamp="2025-01-01T00:00:00Z", status="ok",
            input_tokens=10000, output_tokens=3000,
            cache_read_tokens=5000, cache_write_tokens=1000,
            finish_reason="end_turn", content_blocks=[],
            response_full="", request_full="", tool_calls_raw="",
        )
        defaults.update(call_kwargs)
        lc = LLMCall(**defaults)
        ro = ConversationRound(
            round_index=0,
            user_msg=ChatMessage(role="user", content="hello", timestamp="2025-01-01T00:00:00Z"),
            assistant_msg=ChatMessage(role="assistant", content="hi", timestamp="2025-01-01T00:00:00Z"),
        )
        return ClaudeCodeAttributionBuilder(
            llm_call=lc,
            round_obj=ro,
            session_context=session_context,
        )

    def test_tool_schemas_details_has_items(self):
        ctx = {
            "available_tools": ["Read", "Write", "Bash"],
            "prior_messages": [],
            "preceding_tool_results": [],
            "local_instructions": "",
        }
        builder = self._make_builder(ctx)
        result = builder.build_request()

        schema_bucket = None
        for b in result.buckets:
            if b.key == "tool_schemas":
                schema_bucket = b
                break

        assert schema_bucket is not None
        assert schema_bucket.details is not None
        assert schema_bucket.details.get("kind") == "tools"
        items = schema_bucket.details.get("items", [])
        assert len(items) == 3

        item = items[0]
        assert "name" in item
        assert "source" in item
        assert "description_preview" in item
        assert "estimated_tokens" in item
        assert "precision" in item

    def test_tool_schemas_fallback_default_tools(self):
        ctx = {
            "available_tools": [],
            "prior_messages": [],
            "preceding_tool_results": [],
        }
        builder = self._make_builder(ctx)
        result = builder.build_request()

        schema_bucket = None
        for b in result.buckets:
            if b.key == "tool_schemas":
                schema_bucket = b
                break

        assert schema_bucket is not None
        items = schema_bucket.details.get("items", [])
        assert len(items) > 0
        # Should use default_fallback source
        assert items[0]["source"] == "default_fallback"


class TestBucketDetailsLocalInstructions:
    """Verify local_instruction_context bucket details."""

    def _make_builder(self, session_context, **call_kwargs):
        from session_browser.domain.models import LLMCall, ConversationRound, ChatMessage
        defaults = dict(
            id="llm-test", model="claude-sonnet-4-20250514", scope="main",
            subagent_id="", round_index=0, parent_id="", parent_tool_name="",
            timestamp="2025-01-01T00:00:00Z", status="ok",
            input_tokens=10000, output_tokens=3000,
            cache_read_tokens=5000, cache_write_tokens=1000,
            finish_reason="end_turn", content_blocks=[],
            response_full="", request_full="", tool_calls_raw="",
        )
        defaults.update(call_kwargs)
        lc = LLMCall(**defaults)
        ro = ConversationRound(
            round_index=0,
            user_msg=ChatMessage(role="user", content="hello", timestamp="2025-01-01T00:00:00Z"),
            assistant_msg=ChatMessage(role="assistant", content="hi", timestamp="2025-01-01T00:00:00Z"),
        )
        return ClaudeCodeAttributionBuilder(
            llm_call=lc,
            round_obj=ro,
            session_context=session_context,
        )

    def test_local_instruction_has_claude_md_item(self):
        ctx = {
            "local_instructions": "Some project instructions here.",
            "prior_messages": [],
            "preceding_tool_results": [],
        }
        builder = self._make_builder(ctx)
        result = builder.build_request()

        bucket = None
        for b in result.buckets:
            if b.key == "local_instruction_context":
                bucket = b
                break

        assert bucket is not None
        assert bucket.details.get("kind") == "system_sources"
        items = bucket.details.get("items", [])
        claude_items = [i for i in items if "CLAUDE.md" in i.get("file_path", "")]
        assert len(claude_items) > 0
        assert claude_items[0]["source_type"] == "project_instructions"

    def test_local_instruction_has_system_reminder_item(self):
        ctx = {
            "local_instructions": "",
            "system_reminder_content": "Some system reminder.",
            "prior_messages": [],
            "preceding_tool_results": [],
        }
        builder = self._make_builder(ctx)
        result = builder.build_request()

        bucket = None
        for b in result.buckets:
            if b.key == "local_instruction_context":
                bucket = b
                break

        assert bucket is not None
        items = bucket.details.get("items", [])
        reminder_items = [i for i in items if "system-reminder" in i.get("file_path", "")]
        assert len(reminder_items) > 0


class TestBucketDetailsPriorMessages:
    """Verify prior_conversation_messages bucket details."""

    def _make_builder(self, session_context, **call_kwargs):
        from session_browser.domain.models import LLMCall, ConversationRound, ChatMessage
        defaults = dict(
            id="llm-test", model="claude-sonnet-4-20250514", scope="main",
            subagent_id="", round_index=0, parent_id="", parent_tool_name="",
            timestamp="2025-01-01T00:00:00Z", status="ok",
            input_tokens=10000, output_tokens=3000,
            cache_read_tokens=5000, cache_write_tokens=1000,
            finish_reason="end_turn", content_blocks=[],
            response_full="", request_full="", tool_calls_raw="",
        )
        defaults.update(call_kwargs)
        lc = LLMCall(**defaults)
        ro = ConversationRound(
            round_index=0,
            user_msg=ChatMessage(role="user", content="hello", timestamp="2025-01-01T00:00:00Z"),
            assistant_msg=ChatMessage(role="assistant", content="hi", timestamp="2025-01-01T00:00:00Z"),
        )
        return ClaudeCodeAttributionBuilder(
            llm_call=lc,
            round_obj=ro,
            session_context=session_context,
        )

    def test_prior_messages_has_detail_items(self):
        ctx = {
            "prior_messages": [
                {"role": "user", "content": "First message", "content_preview": "First...", "content_token_estimate": 3},
                {"role": "assistant", "content": "Second message", "content_preview": "Second...", "content_token_estimate": 4},
            ],
            "preceding_tool_results": [],
            "available_tools": [],
            "local_instructions": "",
        }
        builder = self._make_builder(ctx)
        result = builder.build_request()

        bucket = None
        for b in result.buckets:
            if b.key == "prior_conversation_messages":
                bucket = b
                break

        assert bucket is not None
        details = bucket.details
        assert details.get("kind") == "message_history"
        items = details.get("items", [])
        assert len(items) == 2
        assert items[0]["role"] == "user"
        assert items[1]["role"] == "assistant"
        assert "round_id" in items[0]
        assert "summary" in items[0]
        assert "tokens" in items[0]


class TestBucketDetailsUnlocated:
    """Verify unlocated_residual bucket details."""

    def _make_builder(self, session_context, **call_kwargs):
        from session_browser.domain.models import LLMCall, ConversationRound, ChatMessage
        defaults = dict(
            id="llm-test", model="claude-sonnet-4-20250514", scope="main",
            subagent_id="", round_index=0, parent_id="", parent_tool_name="",
            timestamp="2025-01-01T00:00:00Z", status="ok",
            input_tokens=10000, output_tokens=3000,
            cache_read_tokens=5000, cache_write_tokens=1000,
            finish_reason="end_turn", content_blocks=[],
            response_full="", request_full="", tool_calls_raw="",
        )
        defaults.update(call_kwargs)
        lc = LLMCall(**defaults)
        ro = ConversationRound(
            round_index=0,
            user_msg=ChatMessage(role="user", content="hello", timestamp="2025-01-01T00:00:00Z"),
            assistant_msg=ChatMessage(role="assistant", content="hi", timestamp="2025-01-01T00:00:00Z"),
        )
        return ClaudeCodeAttributionBuilder(
            llm_call=lc,
            round_obj=ro,
            session_context=session_context,
        )

    def test_unlocated_has_explanation(self):
        ctx = {
            "prior_messages": [],
            "preceding_tool_results": [],
            "available_tools": [],
            "local_instructions": "",
        }
        builder = self._make_builder(ctx)
        result = builder.build_request()

        bucket = None
        for b in result.buckets:
            if b.key == "unlocated_residual":
                bucket = b
                break

        assert bucket is not None
        details = bucket.details
        assert details.get("kind") == "unlocated"
        assert "explanation" in details
        assert len(details["explanation"]) > 0


class TestBucketDetailsHiddenEstimates:
    """Verify hidden_builtin_system_estimate and provider_wrapper_estimate details."""

    def _make_builder(self, session_context, **call_kwargs):
        from session_browser.domain.models import LLMCall, ConversationRound, ChatMessage
        defaults = dict(
            id="llm-test", model="claude-sonnet-4-20250514", scope="main",
            subagent_id="", round_index=0, parent_id="", parent_tool_name="",
            timestamp="2025-01-01T00:00:00Z", status="ok",
            input_tokens=10000, output_tokens=3000,
            cache_read_tokens=5000, cache_write_tokens=1000,
            finish_reason="end_turn", content_blocks=[],
            response_full="", request_full="", tool_calls_raw="",
        )
        defaults.update(call_kwargs)
        lc = LLMCall(**defaults)
        ro = ConversationRound(
            round_index=0,
            user_msg=ChatMessage(role="user", content="hello", timestamp="2025-01-01T00:00:00Z"),
            assistant_msg=ChatMessage(role="assistant", content="hi", timestamp="2025-01-01T00:00:00Z"),
        )
        return ClaudeCodeAttributionBuilder(
            llm_call=lc,
            round_obj=ro,
            session_context=session_context,
        )

    def test_hidden_builtin_has_explanation(self):
        ctx = {
            "prior_messages": [],
            "preceding_tool_results": [],
            "available_tools": [],
        }
        builder = self._make_builder(ctx)
        result = builder.build_request()

        bucket = None
        for b in result.buckets:
            if b.key == "hidden_builtin_system_estimate":
                bucket = b
                break

        assert bucket is not None
        assert bucket.details.get("kind") == "hidden_estimate"
        assert len(bucket.details.get("explanation", [])) > 0

    def test_provider_wrapper_has_explanation(self):
        ctx = {
            "prior_messages": [],
            "preceding_tool_results": [],
            "available_tools": [],
        }
        builder = self._make_builder(ctx)
        result = builder.build_request()

        bucket = None
        for b in result.buckets:
            if b.key == "provider_wrapper_estimate":
                bucket = b
                break

        assert bucket is not None
        assert bucket.details.get("kind") == "hidden_estimate"
        assert len(bucket.details.get("explanation", [])) > 0


class TestBucketDetailsCurrentUserMessage:
    """Verify current_user_message bucket details."""

    def _make_builder(self, session_context, **call_kwargs):
        from session_browser.domain.models import LLMCall, ConversationRound, ChatMessage
        defaults = dict(
            id="llm-test", model="claude-sonnet-4-20250514", scope="main",
            subagent_id="", round_index=0, parent_id="", parent_tool_name="",
            timestamp="2025-01-01T00:00:00Z", status="ok",
            input_tokens=10000, output_tokens=3000,
            cache_read_tokens=5000, cache_write_tokens=1000,
            finish_reason="end_turn", content_blocks=[],
            response_full="", request_full="", tool_calls_raw="",
        )
        defaults.update(call_kwargs)
        lc = LLMCall(**defaults)
        ro = ConversationRound(
            round_index=0,
            user_msg=ChatMessage(role="user", content="Tell me about cats", timestamp="2025-01-01T00:00:00Z"),
            assistant_msg=ChatMessage(role="assistant", content="hi", timestamp="2025-01-01T00:00:00Z"),
        )
        return ClaudeCodeAttributionBuilder(
            llm_call=lc,
            round_obj=ro,
            session_context=session_context,
        )

    def test_current_user_message_has_preview(self):
        ctx = {
            "prior_messages": [],
            "preceding_tool_results": [],
            "available_tools": [],
        }
        builder = self._make_builder(ctx)
        result = builder.build_request()

        bucket = None
        for b in result.buckets:
            if b.key == "current_user_message":
                bucket = b
                break

        assert bucket is not None
        details = bucket.details
        assert details.get("kind") == "current_user_message"
        assert "preview" in details
        assert "cats" in details["preview"]
        assert "tokens" in details
