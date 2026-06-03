"""Tests for the attribution session context builder (Task 02c).

Verifies:
1. build_attribution_session_context returns non-null context.
2. First interaction has empty preceding_tool_results.
3. Second interaction includes first interaction's tool results.
4. interaction_index is correctly set.
"""

import json
from pathlib import Path

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


def test_claude_code_available_tools_uses_agent_definition():
    """Claude Code should use tools from .claude/agents/*.md frontmatter.

    The JSONL event format does NOT persist the tools array. When a project
    has agent definition files with explicit ``tools:`` in YAML frontmatter,
    those tools should be used instead of the full SDK registry.

    When no project_dir is provided (or no agent files found), falls back
    to observed tools, then to the full SDK registry.
    """
    from session_browser.attribution.agents.claude_code_tool_schemas import (
        ALL_CLAUDE_CODE_TOOLS,
    )
    from session_browser.attribution.context import _build_available_tools

    # Without project_dir: falls back to observed tools
    invoked_tools = ["Read", "Bash", "Edit", "Grep"]
    all_tool_calls = [
        ToolCall(name=name, parameters={}, result="ok")
        for name in invoked_tools
    ]

    fake_lc = _make_lc(tool_calls_raw=json.dumps([
        {"type": "tool_use", "name": name, "id": f"id-{name}"}
        for name in invoked_tools
    ]))

    # Without project_dir, observed tools are used
    result = _build_available_tools(
        all_tool_calls=all_tool_calls,
        agent_name="claude_code",
        llm_calls=[fake_lc],
    )
    assert result == sorted(invoked_tools)

    # Without observed tools but with project_dir, agent files are used
    result = _build_available_tools(
        all_tool_calls=[],
        agent_name="claude_code",
        llm_calls=[],
        project_dir=".",
    )
    # Union of all .claude/agents/*.md tools: 11 tools
    assert len(result) == 11
    assert "Agent" in result
    assert "Bash" in result
    assert "Read" in result
    assert "Write" in result

    # Without project_dir and without observed tools, full registry
    result = _build_available_tools(
        all_tool_calls=[],
        agent_name="claude_code",
        llm_calls=[],
    )
    assert result == sorted(ALL_CLAUDE_CODE_TOOLS)
    assert len(result) == len(ALL_CLAUDE_CODE_TOOLS)


def test_qoder_available_tools_uses_observed():
    """Qoder should use observed tool calls when available."""
    from session_browser.attribution.context import _build_available_tools

    all_tool_calls = [
        ToolCall(name="ReadFile", parameters={}, result="ok"),
        ToolCall(name="WriteFile", parameters={}, result="ok"),
    ]

    result = _build_available_tools(
        all_tool_calls=all_tool_calls,
        agent_name="qoder",
    )
    assert result == ["ReadFile", "WriteFile"]


def test_codex_available_tools_empty():
    """Codex should return empty when no tools are available."""
    from session_browser.attribution.context import _build_available_tools

    result = _build_available_tools(
        all_tool_calls=None,
        agent_name="codex",
    )
    assert result == []


def test_parse_agent_tools_from_frontmatter():
    """Parse tools field from YAML frontmatter."""
    from session_browser.attribution.context import _parse_agent_tools_from_frontmatter

    text = (
        "---\n"
        "name: test-agent\n"
        "tools: Agent(implementer, qa-verifier), Read, Glob, Grep, Bash, Edit, Write\n"
        "---\n\n"
        "# Agent body\n"
    )
    tools = _parse_agent_tools_from_frontmatter(text)
    assert tools == ["Agent", "Bash", "Edit", "Glob", "Grep", "Read", "Write"]


def test_read_agent_tool_list_union():
    """_read_agent_tool_list should return the union of all agent tools."""
    from session_browser.attribution.context import _read_agent_tool_list

    tools = _read_agent_tool_list(Path("."))
    assert tools is not None
    assert len(tools) >= 10
    assert "Agent" in tools
    assert "Bash" in tools
    assert "Read" in tools
