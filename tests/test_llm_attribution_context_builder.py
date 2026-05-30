"""Tests for the attribution session context builder (Task 02c).

Verifies:
1. build_attribution_session_context returns non-null context.
2. First interaction has empty preceding_tool_results.
3. Second interaction includes first interaction's tool results.
4. interaction_index is correctly set.
"""

import pytest

from session_browser.domain.models import (
    LLMCall, ChatMessage, ConversationRound, ToolCall,
)
from session_browser.attribution.context import build_attribution_session_context


def _make_lc(**kwargs):
    defaults = dict(
        id="test-call", model="test-model", scope="main",
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


def test_context_returns_non_null():
    """build_attribution_session_context should always return a dict."""
    lc = _make_lc()
    ro = _make_ro()
    ctx = build_attribution_session_context(
        session=None,
        round_obj=ro,
        interaction_index=0,
        interactions=[lc],
        round_tool_calls=[],
    )
    assert isinstance(ctx, dict)
    assert "interaction_index" in ctx
    assert "preceding_tool_results" in ctx
    assert "prior_messages" in ctx
    assert "available_tools" in ctx


def test_first_interaction_has_empty_preceding_tool_results():
    """First interaction (index=0) should have empty preceding_tool_results."""
    tc = ToolCall(name="Read", parameters={"file_path": "/tmp/a.py"}, result="result1")
    lc = _make_lc()
    ro = _make_ro(tool_calls=[tc])
    ctx = build_attribution_session_context(
        session=None,
        round_obj=ro,
        interaction_index=0,
        interactions=[lc],
        round_tool_calls=[tc],
    )
    assert ctx["interaction_index"] == 0
    assert ctx["preceding_tool_results"] == []


def test_second_interaction_includes_first_tool_results():
    """Second interaction (index=1) should include tool results from first interaction."""
    tc1 = ToolCall(name="Read", parameters={"file_path": "/tmp/a.py"}, result="result from first")
    tc2 = ToolCall(name="Bash", parameters={"command": "echo hi"}, result="result from second")

    lc1 = _make_lc(id="call-1")
    lc1.tool_calls = [tc1]
    lc2 = _make_lc(id="call-2")
    lc2.tool_calls = [tc2]

    ro = _make_ro(tool_calls=[tc1, tc2], interactions=[lc1, lc2])

    ctx = build_attribution_session_context(
        session=None,
        round_obj=ro,
        interaction_index=1,
        interactions=[lc1, lc2],
        round_tool_calls=[tc1, tc2],
    )
    assert ctx["interaction_index"] == 1
    assert "result from first" in ctx["preceding_tool_results"]
    assert "result from second" not in ctx["preceding_tool_results"]


def test_subagent_tool_results_excluded():
    """Tool results with subagent_id should be excluded."""
    tc = ToolCall(name="Read", parameters={"file_path": "/tmp/a.py"}, result="sub result")
    tc.subagent_id = "sub-001"

    lc = _make_lc()
    lc.tool_calls = [tc]
    ro = _make_ro(tool_calls=[tc], interactions=[lc])

    ctx = build_attribution_session_context(
        session=None,
        round_obj=ro,
        interaction_index=1,
        interactions=[lc],
        round_tool_calls=[tc],
    )
    # subagent tool results should be excluded
    assert "sub result" not in ctx["preceding_tool_results"]


def test_no_interactions_returns_empty():
    """When there are no prior interactions, preceding_tool_results is empty."""
    lc = _make_lc()
    ro = _make_ro()
    ctx = build_attribution_session_context(
        session=None,
        round_obj=ro,
        interaction_index=0,
        interactions=[],
        round_tool_calls=[],
    )
    assert ctx["preceding_tool_results"] == []
    assert ctx["interaction_index"] == 0
