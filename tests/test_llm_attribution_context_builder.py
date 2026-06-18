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
    LLMCall, ChatMessage, ConversationRound, SessionSummary, ToolCall,
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


def _make_session(
    project_dir: Path,
    session_file: Path,
    *,
    project_key: str | None = None,
    cwd: str | None = None,
) -> SessionSummary:
    return SessionSummary(
        agent="claude_code",
        session_id=session_file.stem,
        title="test session",
        project_key=project_key or str(project_dir),
        project_name=project_dir.name,
        cwd=cwd or str(project_dir),
        started_at="2025-01-01T00:00:00Z",
        ended_at="2025-01-01T00:00:01Z",
        file_path=str(session_file),
    )


def _write_agent(project_dir: Path, name: str, tools: str) -> None:
    agents_dir = project_dir / ".claude" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    (agents_dir / f"{name}.md").write_text(
        f"---\nname: {name}\ntools: {tools}\n---\n\n# {name}\n",
        encoding="utf-8",
    )


def _tool_schema_bucket_from_context(lc: LLMCall, ro: ConversationRound, ctx: dict):
    from session_browser.attribution.agents.claude_code import ClaudeCodeAttributionBuilder

    attr = ClaudeCodeAttributionBuilder(lc, ro, session_context=ctx).build_request()
    return next(bucket for bucket in attr.buckets if bucket.key == "tool_definitions")


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


def test_claude_code_default_config_uses_full_builtin_tools(tmp_path):
    """Default Claude Code sessions use the full builtin registry, not observed calls."""
    from session_browser.attribution.agents.claude_code_tool_schemas import (
        ALL_CLAUDE_CODE_TOOLS,
    )

    session_file = tmp_path / "default-session.jsonl"
    session_file.write_text(
        json.dumps({"type": "user", "message": {"content": "hello"}}) + "\n",
        encoding="utf-8",
    )
    observed = [
        ToolCall(name="Read", parameters={}, result="ok"),
        ToolCall(name="Bash", parameters={}, result="ok"),
    ]
    lc = _make_lc(
        input_tokens=20000,
        tool_calls_raw=json.dumps([
            {"type": "tool_use", "name": "Read", "id": "toolu-read"},
        ]),
    )
    ro = _make_ro(interactions=[lc], tool_calls=observed)

    ctx = build_attribution_session_context(
        session=_make_session(
            tmp_path,
            session_file,
            project_key="-Users-example-project",
            cwd=str(tmp_path),
        ),
        round_obj=ro,
        interaction_index=0,
        interactions=[lc],
        round_tool_calls=observed,
        all_tool_calls=observed,
        agent_name="claude_code",
        project_dir="-Users-example-project",
        all_llm_calls=[lc],
    )

    assert ctx["available_tools"] == list(ALL_CLAUDE_CODE_TOOLS)
    assert ctx["available_tools_source"] == "default_builtin"
    assert len(ctx["available_tools"]) == 34

    bucket = _tool_schema_bucket_from_context(lc, ro, ctx)
    assert bucket.count_label == "34 tools"
    assert [item["name"] for item in bucket.details["items"]] == sorted(ALL_CLAUDE_CODE_TOOLS)
    assert {item["source"] for item in bucket.details["items"]} == {"default_fallback"}


def test_claude_code_main_custom_agent_uses_that_agent_tools(tmp_path):
    """Main Claude Code calls use the selected agent-setting definition only."""
    session_file = tmp_path / "custom-main.jsonl"
    session_file.write_text(
        json.dumps({
            "type": "agent-setting",
            "agentSetting": "qwen-main-default",
            "timestamp": "2025-01-01T00:00:00Z",
        }) + "\n",
        encoding="utf-8",
    )
    _write_agent(
        tmp_path,
        "qwen-main-default",
        "Agent(implementer, repo-mapper), Read, Bash, Edit, Write, TaskCreate, TaskUpdate",
    )
    observed = [ToolCall(name="WebSearch", parameters={}, result="ok")]
    lc = _make_lc(input_tokens=20000)
    ro = _make_ro(interactions=[lc], tool_calls=observed)

    ctx = build_attribution_session_context(
        session=_make_session(tmp_path, session_file),
        round_obj=ro,
        interaction_index=0,
        interactions=[lc],
        round_tool_calls=observed,
        all_tool_calls=observed,
        agent_name="claude_code",
        project_dir=str(tmp_path),
        all_llm_calls=[lc],
    )

    expected = ["Agent", "Bash", "Edit", "Read", "TaskCreate", "TaskUpdate", "Write"]
    assert ctx["available_tools"] == expected
    assert ctx["available_tools_source"] == "agent_definition"
    assert ctx["available_tools_agent_name"] == "qwen-main-default"

    bucket = _tool_schema_bucket_from_context(lc, ro, ctx)
    assert bucket.count_label == "7 tools"
    assert [item["name"] for item in bucket.details["items"]] == expected
    assert {item["source"] for item in bucket.details["items"]} == {"agent_definition"}


def test_claude_code_subagent_uses_subagent_tools_not_main_or_observed(tmp_path):
    """Subagent Claude Code calls use their own agent definition independently."""
    session_file = tmp_path / "subagent-session.jsonl"
    session_file.write_text(
        json.dumps({
            "type": "agent-setting",
            "agentSetting": "qwen-main-default",
            "timestamp": "2025-01-01T00:00:00Z",
        }) + "\n",
        encoding="utf-8",
    )
    _write_agent(tmp_path, "qwen-main-default", "Agent(repo-mapper), Read, Bash, Edit, Write")
    _write_agent(tmp_path, "repo-mapper", "Read, Bash")

    observed = [
        ToolCall(name="Edit", parameters={}, result="ok"),
        ToolCall(name="Write", parameters={}, result="ok"),
    ]
    lc = _make_lc(input_tokens=20000, scope="subagent", subagent_id="agent-1")
    ro = _make_ro(interactions=[lc], tool_calls=observed)

    ctx = build_attribution_session_context(
        session=_make_session(tmp_path, session_file),
        round_obj=ro,
        interaction_index=0,
        interactions=[lc],
        round_tool_calls=observed,
        all_tool_calls=observed,
        agent_name="claude_code",
        project_dir=str(tmp_path),
        all_llm_calls=[lc],
        subagent_type="repo-mapper",
    )

    assert ctx["available_tools"] == ["Bash", "Read"]
    assert ctx["available_tools_source"] == "agent_definition"
    assert ctx["available_tools_agent_name"] == "repo-mapper"

    bucket = _tool_schema_bucket_from_context(lc, ro, ctx)
    assert bucket.count_label == "2 tools"
    assert [item["name"] for item in bucket.details["items"]] == ["Bash", "Read"]


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
    from session_browser.attribution.agents.claude_code_parts.claude_code_agent_tools import (
        parse_agent_tools_from_frontmatter,
    )

    text = (
        "---\n"
        "name: test-agent\n"
        "tools: Agent(implementer, qa-verifier), Read, Glob, Grep, Bash, Edit, Write\n"
        "---\n\n"
        "# Agent body\n"
    )
    tools = parse_agent_tools_from_frontmatter(text)
    assert tools == ["Agent", "Bash", "Edit", "Glob", "Grep", "Read", "Write"]


def test_read_agent_definition_tools_is_agent_specific(tmp_path):
    """Agent tool parsing should read one named agent, not the project union."""
    from session_browser.attribution.agents.claude_code_parts.claude_code_agent_tools import (
        read_agent_definition_tools,
    )

    _write_agent(tmp_path, "main-agent", "Read, Bash, Edit")
    _write_agent(tmp_path, "repo-mapper", "Read, Bash")

    tools, path = read_agent_definition_tools("repo-mapper", tmp_path)
    assert tools == ["Bash", "Read"]
    assert path.endswith(".claude/agents/repo-mapper.md")
