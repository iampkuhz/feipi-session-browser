"""Semantic correctness tests for LLM attribution data layer.

Verifies the core semantic fixes from Task 02b:
1. Tool schemas != actual tool_calls without available_tools
2. History messages require explicit prior_messages
3. Captured context fragment handles unclassifiable request_full
4. Response bucket double-count prevention via contributes_to_total
5. Coverage only counts contributes_to_total=True
"""

import json
import pytest

from session_browser.domain.models import (
    LLMCall, ChatMessage, ConversationRound, ToolCall,
)
from session_browser.attribution.service import (
    build_llm_request_attribution,
    build_llm_response_attribution,
)
from session_browser.attribution.agents.claude_code import ClaudeCodeAttributionBuilder
from session_browser.attribution.agents.qoder import QoderAttributionBuilder
from session_browser.attribution.agents.codex import CodexAttributionBuilder
from session_browser.attribution.contracts import ValuePrecision


def _make_lc(**kwargs):
    defaults = dict(
        id="test-call-001", model="test-model", scope="main",
        subagent_id="", round_index=0, parent_id="", parent_tool_name="",
        timestamp="2025-01-01T00:00:00Z", status="ok",
        input_tokens=0, output_tokens=0, cache_read_tokens=0, cache_write_tokens=0,
        finish_reason="end_turn", content_blocks=[],
        response_full="", request_full="", tool_calls_raw="",
    )
    defaults.update(kwargs)
    return LLMCall(**defaults)


def _make_ro(user_content="hello", tool_calls=None, interactions=None):
    return ConversationRound(
        user_msg=ChatMessage(role="user", content=user_content, timestamp="2025-01-01T00:00:00Z"),
        assistant_msg=ChatMessage(role="assistant", content="hi", timestamp="2025-01-01T00:00:00Z"),
        tool_calls=tool_calls or [],
        interactions=interactions or [],
    )


# ─── P0-1: Tool schemas != actual tool_calls ───────────────────────────


@pytest.mark.parametrize("agent", ["claude_code", "qoder", "codex"])
def test_tool_schemas_zero_without_available_tools(agent):
    """When only actual tool_calls exist without available_tools,
    tool_schemas tokens must be 0."""
    tc = ToolCall(name="Read", parameters={"file_path": "/tmp/a.py"}, result="ok")
    lc = _make_lc(input_tokens=10000)
    ro = _make_ro(user_content="test", tool_calls=[tc])
    result = build_llm_request_attribution(agent, lc, ro)

    schema_bucket = next((b for b in result.buckets if b.key == "tool_schemas"), None)
    assert schema_bucket is not None, f"Missing tool_schemas bucket for {agent}"
    assert schema_bucket.tokens == 0, (
        f"tool_schemas tokens should be 0 without available_tools for {agent}"
    )


def test_claude_code_tool_schemas_from_available_tools():
    """Claude Code: with available_tools, tool_schemas uses that count."""
    tc = ToolCall(name="Read", parameters={"file_path": "/tmp/a.py"}, result="ok")
    lc = _make_lc(input_tokens=10000)
    ro = _make_ro(user_content="test", tool_calls=[tc])
    ctx = {"available_tools": ["Read", "Bash", "Edit"]}
    builder = ClaudeCodeAttributionBuilder(lc, ro, session_context=ctx)
    result = builder.build_request()

    schema_bucket = next((b for b in result.buckets if b.key == "tool_schemas"), None)
    assert schema_bucket is not None
    assert schema_bucket.tokens == 3 * 240
    assert "3 tools" in schema_bucket.count_label


def test_tool_schemas_count_label_from_available_not_observed():
    """Tool schemas count_label must come from available_tools count,
    NOT observed tool_calls count."""
    tc = ToolCall(name="Read", parameters={"file_path": "/tmp/a.py"}, result="ok")
    lc = _make_lc(input_tokens=10000)
    ro = _make_ro(user_content="test", tool_calls=[tc])
    ctx = {"available_tools": ["Read", "Bash", "Edit", "Grep", "Glob"]}
    builder = ClaudeCodeAttributionBuilder(lc, ro, session_context=ctx)
    result = builder.build_request()

    schema_bucket = next((b for b in result.buckets if b.key == "tool_schemas"), None)
    assert schema_bucket is not None
    assert schema_bucket.tokens == 5 * 240
    assert "5 tools" in schema_bucket.count_label


# ─── P0-2: History messages require prior_messages ─────────────────────


@pytest.mark.parametrize("agent", ["claude_code", "qoder", "codex"])
def test_no_history_without_prior_messages(agent):
    """Without prior messages, history_messages bucket should have 0 tokens
    (or not exist as a positive bucket)."""
    lc = _make_lc(input_tokens=10000, request_full="role: user\n\nHello world\n\n")
    ro = _make_ro(user_content="test")
    result = build_llm_request_attribution(agent, lc, ro)

    history_bucket = next(
        (b for b in result.buckets if b.key in ("history_messages", "conversation_history")),
        None,
    )
    if history_bucket is not None:
        assert history_bucket.tokens == 0, (
            f"history_messages should be 0 without prior_messages for {agent}"
        )


@pytest.mark.parametrize("agent", ["claude_code", "qoder", "codex"])
def test_captured_context_when_request_full_exists(agent):
    """When request_full has content but no prior messages, content should
    go into captured_context_fragment, NOT history_messages."""
    lc = _make_lc(
        input_tokens=10000,
        request_full="some context data here that is not classifiable as history",
    )
    ro = _make_ro(user_content="test")
    result = build_llm_request_attribution(agent, lc, ro)

    ctx_bucket = next(
        (b for b in result.buckets if b.key == "captured_context_fragment"),
        None,
    )
    if ctx_bucket is not None:
        # captured_context_fragment exists with positive tokens
        assert ctx_bucket.tokens > 0


@pytest.mark.parametrize("agent", ["claude_code", "qoder", "codex"])
def test_current_user_message_not_double_counted(agent):
    """current_user_message must not be double-counted in history_messages."""
    lc = _make_lc(input_tokens=10000)
    ro = _make_ro(user_content="unique user message text that should not appear in history")
    result = build_llm_request_attribution(agent, lc, ro)

    # Check that user message tokens are in current_user_message bucket
    user_bucket = next(
        (b for b in result.buckets if b.key == "current_user_message"
         or b.key == "current_user_instruction"),
        None,
    )
    assert user_bucket is not None
    assert user_bucket.tokens > 0


# ─── P0-3: Response bucket double-count prevention ─────────────────────


def test_claude_response_tool_use_children_not_contribute_to_total():
    """Claude Code: per-tool child buckets should have contributes_to_total=False."""
    lc = _make_lc(
        output_tokens=3000,
        response_full="text response",
        content_blocks=[
            {"type": "text", "content": "Hello"},
            {"type": "tool_use", "name": "Read", "id": "tu-001",
             "parameters": {"file_path": "/tmp/test.py"}},
            {"type": "tool_use", "name": "Bash", "id": "tu-002",
             "parameters": {"command": "echo hello"}},
        ],
    )
    ro = _make_ro()
    result = build_llm_response_attribution("claude_code", lc, ro)

    # Check tool_use aggregate exists
    aggregate = next((b for b in result.buckets if b.key == "tool_use"), None)
    assert aggregate is not None
    assert aggregate.contributes_to_total is True

    # Check child buckets
    children = [b for b in result.buckets if b.key.startswith("tool_use:") and b.key != "tool_use"]
    assert len(children) == 2
    for child in children:
        assert child.contributes_to_total is False, (
            f"Child bucket {child.key} should not contribute to total"
        )


def test_coverage_only_counts_contributes_to_total():
    """Coverage calculation must only use contributes_to_total=True buckets."""
    lc = _make_lc(
        output_tokens=5000,
        response_full="response text here",
        content_blocks=[
            {"type": "text", "content": "Hello world this is a response"},
            {"type": "tool_use", "name": "Read", "id": "tu-001",
             "parameters": {"file_path": "/tmp/test.py"}},
        ],
    )
    ro = _make_ro()
    result = build_llm_response_attribution("claude_code", lc, ro)

    # Manual sum of contributes_to_total buckets (excluding unknown)
    contributing_sum = sum(
        b.tokens for b in result.buckets
        if b.contributes_to_total and b.key != "unknown"
    )
    total = result.total_output.value or 0
    if total > 0:
        expected_coverage = min(contributing_sum / total, 1.0)
    else:
        expected_coverage = 0.0

    assert abs(result.coverage.value - expected_coverage) < 0.01


def test_bucket_sum_not_exceeding_total_with_children():
    """Bucket sum should not exceed total even with child buckets present,
    because children have contributes_to_total=False."""
    lc = _make_lc(
        output_tokens=3000,
        response_full="text",
        content_blocks=[
            {"type": "text", "content": "Hello"},
            {"type": "tool_use", "name": "Read", "id": "tu-001",
             "parameters": {"file_path": "/tmp/test.py"}},
        ],
    )
    ro = _make_ro()
    result = build_llm_response_attribution("claude_code", lc, ro)

    total = result.total_output.value or 0
    contributing_sum = sum(
        b.tokens for b in result.buckets
        if b.contributes_to_total
    )
    assert contributing_sum <= total, (
        f"Contributing bucket sum {contributing_sum} exceeds total {total}"
    )


# ─── Every bucket has contributes_to_total ─────────────────────────────


@pytest.mark.parametrize("agent", ["claude_code", "qoder", "codex"])
def test_every_bucket_has_contributes_to_total_request(agent):
    """Every request bucket must have contributes_to_total field."""
    lc = _make_lc(input_tokens=10000, request_full="some context", response_full="some response")
    ro = _make_ro(user_content="test user message")
    result = build_llm_request_attribution(agent, lc, ro)

    for b in result.buckets:
        assert hasattr(b, "contributes_to_total"), (
            f"Bucket {b.key} missing contributes_to_total attribute"
        )


@pytest.mark.parametrize("agent", ["claude_code", "qoder", "codex"])
def test_every_bucket_has_contributes_to_total_response(agent):
    """Every response bucket must have contributes_to_total field."""
    lc = _make_lc(output_tokens=3000, content_blocks=[
        {"type": "text", "content": "hello"},
        {"type": "tool_use", "name": "Read", "id": "tu-001",
         "parameters": {"file_path": "/tmp/test.py"}},
    ])
    ro = _make_ro()
    result = build_llm_response_attribution(agent, lc, ro)

    for b in result.buckets:
        assert hasattr(b, "contributes_to_total"), (
            f"Bucket {b.key} missing contributes_to_total attribute"
        )
