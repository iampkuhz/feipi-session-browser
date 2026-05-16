"""Tests for Claude Code parser."""

import json
from pathlib import Path
import tempfile

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_session_events():
    """Test that we can parse Claude session events."""
    from session_browser.sources.claude import _parse_session_events

    fixture = FIXTURES / "claude_session_sample.jsonl"
    events = _parse_session_events(fixture)
    assert len(events) > 0

    types = {ev.get("type") for ev in events}
    assert "user" in types
    assert "assistant" in types


def test_build_summary_from_events():
    """Test summary building from events."""
    from session_browser.sources.claude import (
        _parse_session_events,
        _build_summary_from_events,
    )

    fixture = FIXTURES / "claude_session_sample.jsonl"
    events = _parse_session_events(fixture)
    summary = _build_summary_from_events(events, "test-session-id", "/test/project")

    assert summary.agent == "claude_code"
    assert summary.session_id == "test-session-id"
    assert summary.user_message_count >= 1
    assert summary.project_name == "project"


def test_extract_messages():
    """Test message extraction."""
    from session_browser.sources.claude import (
        _parse_session_events,
        _extract_messages,
    )

    fixture = FIXTURES / "claude_session_sample.jsonl"
    events = _parse_session_events(fixture)
    messages = _extract_messages(events)

    user_msgs = [m for m in messages if m.role == "user"]
    assert len(user_msgs) >= 1
    assert user_msgs[0].content != ""


def test_parse_history_empty_when_missing():
    """Test that parse_history returns empty list when no data dir."""
    from session_browser.sources import claude
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        original = claude.CLAUDE_DATA_DIR
        claude.CLAUDE_DATA_DIR = Path(tmpdir)
        try:
            result = claude.parse_history()
            assert result == []
        finally:
            claude.CLAUDE_DATA_DIR = original


def test_parse_session_detail_includes_subagent_diagnostics():
    """Subagent sidechains should be visible in parent session diagnostics."""
    from session_browser.sources import claude

    session_id = "session-123"
    project_key = "-tmp-project"

    parent_events = [
        {
            "type": "user",
            "message": {"role": "user", "content": "collect sources"},
            "timestamp": "2026-05-02T00:00:00.000Z",
            "cwd": "/tmp/project",
            "entrypoint": "cli",
            "gitBranch": "main",
        },
        {
            "type": "assistant",
            "message": {
                "id": "msg-parent",
                "model": "qwen3.6-plus",
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_agent",
                        "name": "Agent",
                        "input": {
                            "description": "Collect",
                            "subagent_type": "source-evidence-agent",
                        },
                    }
                ],
                "usage": {"input_tokens": 100, "output_tokens": 10},
                "stop_reason": "tool_use",
            },
            "timestamp": "2026-05-02T00:00:01.000Z",
        },
        {
            "type": "user",
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_agent",
                        "content": "User rejected tool use",
                        "is_error": True,
                    }
                ],
            },
            "timestamp": "2026-05-02T00:00:03.000Z",
        },
    ]
    child_events = [
        {
            "type": "user",
            "isSidechain": True,
            "message": {"role": "user", "content": "child prompt"},
            "timestamp": "2026-05-02T00:00:01.100Z",
        },
        {
            "type": "assistant",
            "isSidechain": True,
            "message": {
                "id": "msg-child-1",
                "model": "qwen3.6-plus",
                "role": "assistant",
                "content": [{"type": "thinking", "thinking": "..."}],
                "usage": {"input_tokens": 200, "output_tokens": 0},
            },
            "timestamp": "2026-05-02T00:00:01.200Z",
        },
        {
            "type": "assistant",
            "isSidechain": True,
            "message": {
                "id": "msg-child-1",
                "model": "qwen3.6-plus",
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_read_1",
                        "name": "Read",
                        "input": {"file_path": "a.md"},
                    }
                ],
                "usage": {
                    "input_tokens": 5,
                    "cache_creation_input_tokens": 300,
                    "output_tokens": 20,
                },
                "stop_reason": "tool_use",
            },
            "timestamp": "2026-05-02T00:00:01.300Z",
        },
        {
            "type": "user",
            "isSidechain": True,
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_read_1",
                        "content": "ok",
                    }
                ],
            },
            "timestamp": "2026-05-02T00:00:01.400Z",
        },
        {
            "type": "assistant",
            "isSidechain": True,
            "message": {
                "id": "msg-child-2",
                "model": "qwen3.6-plus",
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_read_2",
                        "name": "Read",
                        "input": {"file_path": "b.md"},
                    }
                ],
                "usage": {
                    "input_tokens": 6,
                    "cache_read_input_tokens": 300,
                    "output_tokens": 21,
                },
                "stop_reason": "tool_use",
            },
            "timestamp": "2026-05-02T00:00:02.000Z",
        },
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        original = claude.CLAUDE_DATA_DIR
        claude.CLAUDE_DATA_DIR = Path(tmpdir)
        try:
            project_dir = Path(tmpdir) / "projects" / project_key
            subagent_dir = project_dir / session_id / "subagents"
            subagent_dir.mkdir(parents=True)
            parent_file = project_dir / f"{session_id}.jsonl"
            child_file = subagent_dir / "agent-child.jsonl"
            meta_file = subagent_dir / "agent-child.meta.json"

            parent_file.write_text(
                "\n".join(json.dumps(e) for e in parent_events),
                encoding="utf-8",
            )
            child_file.write_text(
                "\n".join(json.dumps(e) for e in child_events),
                encoding="utf-8",
            )
            meta_file.write_text(
                json.dumps({
                    "agentType": "source-evidence-agent",
                    "description": "Collect",
                }),
                encoding="utf-8",
            )

            summary, messages, tool_calls, subagent_runs = claude.parse_session_detail(
                project_key,
                session_id,
            )
        finally:
            claude.CLAUDE_DATA_DIR = original

    assert summary.user_message_count == 1
    assert summary.assistant_message_count == 1
    assert summary.tool_call_count == 3
    assert summary.failed_tool_count == 1
    assert summary.input_tokens == 306  # parent 100 + child max(200,5) + child 6
    assert summary.cached_input_tokens == 300
    assert summary.cached_output_tokens == 300

    assert len(subagent_runs) == 1
    assert subagent_runs[0]["summary"]["agent_id"] == "child"

    assert [m.llm_call_id for m in messages if m.role == "assistant"] == ["msg-parent"]
    assert [tc.name for tc in tool_calls] == ["Agent", "Read", "Read"]
    agent_call = tool_calls[0]
    assert agent_call.tool_use_id == "toolu_agent"
    assert agent_call.is_failed
    assert agent_call.llm_call_count == 2
    assert agent_call.subagent_tool_call_count == 2
    assert agent_call.subagent_summary["tool_counts"] == {"Read": 2}
    assert all(tc.scope == "subagent" for tc in tool_calls[1:])
