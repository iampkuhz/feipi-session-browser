"""Tests for Claude Code parser."""
import pytest
import json
from pathlib import Path
import tempfile

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.contract_case("DATA-SOURCE-001", "DATA-SOURCE-002", "DATA-SOURCE-003", "DATA-SOURCE-004")
@pytest.mark.contract_case("DATA-SOURCE-011", "DATA-SOURCE-014")
def test_parse_session_events():
    """Test that we can parse Claude session events."""
    from session_browser.sources.jsonl_reader import parse_jsonl_events

    fixture = FIXTURES / "claude_session_sample.jsonl"
    events, _ = parse_jsonl_events(fixture)
    assert len(events) > 0

    types = {ev.get("type") for ev in events}
    assert "user" in types
    assert "assistant" in types


@pytest.mark.contract_case("DATA-SOURCE-001", "DATA-SOURCE-002", "DATA-SOURCE-003", "DATA-SOURCE-004")
def test_build_summary_from_events():
    """Test summary building from events."""
    from session_browser.sources.jsonl_reader import parse_jsonl_events
    from session_browser.sources.claude import _build_summary_from_events

    fixture = FIXTURES / "claude_session_sample.jsonl"
    events, _ = parse_jsonl_events(fixture)
    summary = _build_summary_from_events(events, "test-session-id", "/test/project")

    assert summary.agent == "claude_code"
    assert summary.session_id == "test-session-id"
    assert summary.user_message_count >= 1
    assert summary.project_name == "project"


@pytest.mark.contract_case("DATA-SOURCE-001", "DATA-SOURCE-002", "DATA-SOURCE-003", "DATA-SOURCE-004")
def test_extract_messages():
    """Test message extraction."""
    from session_browser.sources.jsonl_reader import parse_jsonl_events
    from session_browser.sources.claude import _extract_messages

    fixture = FIXTURES / "claude_session_sample.jsonl"
    events, _ = parse_jsonl_events(fixture)
    messages = _extract_messages(events)

    user_msgs = [m for m in messages if m.role == "user"]
    assert len(user_msgs) >= 1
    assert user_msgs[0].content != ""


@pytest.mark.contract_case("DATA-SOURCE-001", "DATA-SOURCE-002", "DATA-SOURCE-003", "DATA-SOURCE-004")
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


@pytest.mark.contract_case("DATA-SOURCE-001", "DATA-SOURCE-002", "DATA-SOURCE-003", "DATA-SOURCE-004")
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


@pytest.mark.contract_case("DATA-SOURCE-001", "DATA-SOURCE-002", "DATA-SOURCE-003", "DATA-SOURCE-004")
def test_parse_session_events_skips_non_dict_json_values():
    """Non-dict JSON lines in session JSONL (strings, arrays, numbers, etc.)
    must be silently skipped, not crash downstream code.

    Regression for: AttributeError 'str' object has no attribute 'get'
    in _assistant_records when a real session JSONL contains a bare string
    or other non-object JSON value.
    """
    from session_browser.sources.jsonl_reader import parse_jsonl_events
    from session_browser.sources.claude import (
        _build_summary_from_events,
        _assistant_records,
    )

    valid_user = {
        "type": "user",
        "message": {"role": "user", "content": "hello"},
        "timestamp": "2026-05-02T00:00:00.000Z",
    }
    valid_assistant = {
        "type": "assistant",
        "message": {
            "id": "msg-1",
            "model": "claude-4-sonnet",
            "role": "assistant",
            "content": [{"type": "text", "text": "hi"}],
            "usage": {"input_tokens": 10, "output_tokens": 5},
            "stop_reason": "end_turn",
        },
        "timestamp": "2026-05-02T00:00:01.000Z",
    }

    # JSONL with mixed valid dicts and non-dict JSON values
    lines = [
        json.dumps(valid_user),
        json.dumps(valid_assistant),
        '"a bare string"',           # valid JSON string, not a dict
        "42",                         # valid JSON number
        "true",                       # valid JSON boolean
        "null",                       # valid JSON null
        "[1, 2, 3]",                 # valid JSON array
        "[]",                         # valid JSON empty array
        "{}",                         # valid JSON empty object (dict, should be kept)
        json.dumps(valid_assistant),  # second assistant (for merge test)
    ]

    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False, encoding="utf-8") as f:
        f.write("\n".join(lines))
        f.flush()
        tmp_path = Path(f.name)

    try:
        # parse_jsonl_events must only return dicts
        events, _ = parse_jsonl_events(tmp_path)
        assert all(isinstance(ev, dict) for ev in events), \
            f"parse_jsonl_events returned non-dict: {[type(e).__name__ for e in events if not isinstance(e, dict)]}"

        # Must have kept the valid events (2 valid_user/assistant + 1 empty dict)
        # The empty dict {} is also a dict, so it passes the isinstance check
        dict_count = sum(1 for line in lines if _is_valid_json_dict(line))
        assert len(events) == dict_count, f"Expected {dict_count} dict events, got {len(events)}"

        # _assistant_records must not crash
        records = _assistant_records(events)
        assert len(records) == 1, f"Expected 1 assistant record, got {len(records)}"

        # _build_summary_from_events must not crash
        summary = _build_summary_from_events(events, "test-sid", "/test/proj")
        assert summary.agent == "claude_code"
        assert summary.user_message_count >= 1
        assert summary.assistant_message_count >= 1
    finally:
        tmp_path.unlink(missing_ok=True)


def _is_valid_json_dict(line: str) -> bool:
    """Check if a JSON line parses to a dict."""
    try:
        return isinstance(json.loads(line.strip()), dict)
    except json.JSONDecodeError:
        return False


@pytest.mark.contract_case("DATA-SOURCE-001", "DATA-SOURCE-002", "DATA-SOURCE-003", "DATA-SOURCE-004")
def test_parse_pretty_printed_multiline_json():
    """Pretty-printed session files (multi-line JSON objects) must be fully
    parsed, not silently skipped.

    Some Claude Code sessions write pretty-printed JSON with indentation
    instead of single-line JSONL. Each top-level object spans multiple lines
    like:

        {
            "type": "user",
            "message": {"role": "user", "content": "hello"}
        }

    The parser must track brace depth (ignoring braces inside string values)
    and emit complete objects.
    """
    from session_browser.sources.jsonl_reader import parse_jsonl_events

    # A pretty-printed session file with two events
    content = '''{
    "type": "permission-mode",
    "permissionMode": "bypassPermissions",
    "sessionId": "test-session-id"
}
{
    "type": "user",
    "message": {"role": "user", "content": "hello world"},
    "uuid": "uuid-1",
    "timestamp": "2026-05-08T16:42:32.345Z",
    "cwd": "/test/project"
}
{
    "type": "assistant",
    "message": {
        "id": "msg-1",
        "model": "claude-4-sonnet",
        "role": "assistant",
        "content": [{"type": "text", "text": "hi!"}],
        "usage": {"input_tokens": 10, "output_tokens": 5},
        "stop_reason": "end_turn"
    },
    "uuid": "uuid-2",
    "timestamp": "2026-05-08T16:42:35.000Z"
}
'''
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False, encoding="utf-8") as f:
        f.write(content)
        f.flush()
        tmp_path = Path(f.name)

    try:
        events, _ = parse_jsonl_events(tmp_path)
        assert len(events) == 3, f"Expected 3 events, got {len(events)}"

        types = [ev.get("type") for ev in events]
        assert types == ["permission-mode", "user", "assistant"]

        user_ev = events[1]
        assert user_ev["message"]["content"] == "hello world"
        assert user_ev["cwd"] == "/test/project"

        assistant_ev = events[2]
        assert assistant_ev["message"]["id"] == "msg-1"
    finally:
        tmp_path.unlink(missing_ok=True)


@pytest.mark.contract_case("DATA-SOURCE-001", "DATA-SOURCE-002", "DATA-SOURCE-003", "DATA-SOURCE-004")
def test_parse_concatenated_json_transition_line():
    """Mixed-format files where pretty-printed transitions to JSONL with
    concatenated objects on a single line (``}{...}{...}``) must be parsed
    correctly.
    """
    from session_browser.sources.jsonl_reader import parse_jsonl_events

    # Simulate a transition line with two concatenated objects
    content = '''{
    "type": "user",
    "message": {"role": "user", "content": "first"},
    "uuid": "u1",
    "timestamp": "2026-05-08T16:42:32.345Z"
}
{"type":"assistant","message":{"id":"msg-1","model":"test","role":"assistant","content":[],"usage":{"input_tokens":10,"output_tokens":5},"stop_reason":"end_turn"},"uuid":"u2","timestamp":"2026-05-08T16:42:33.000Z"}
{"type":"user","message":{"role":"user","content":"second"},"uuid":"u3","timestamp":"2026-05-08T16:42:34.000Z"}
'''
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False, encoding="utf-8") as f:
        f.write(content)
        f.flush()
        tmp_path = Path(f.name)

    try:
        events, _ = parse_jsonl_events(tmp_path)
        assert len(events) == 3, f"Expected 3 events, got {len(events)}"

        types = [ev.get("type") for ev in events]
        assert types == ["user", "assistant", "user"]
    finally:
        tmp_path.unlink(missing_ok=True)


@pytest.mark.contract_case("DATA-SOURCE-001", "DATA-SOURCE-002", "DATA-SOURCE-003", "DATA-SOURCE-004")
def test_brace_inside_string_values_not_counted():
    """Braces/brackets inside JSON string values must not affect depth
    tracking.  E.g. ``{"key": "{value}"}`` should have depth 1 at the
    opening brace, not 2.
    """
    from session_browser.sources.jsonl_reader import _brace_chars_outside_strings

    # Braces inside strings should be ignored
    text = '{"key": "{nested}", "arr": [1, "{value}"]}'
    result = _brace_chars_outside_strings(text)
    # Only top-level {} and [] are kept; {nested} and {value} are inside strings
    assert result == "{[]}", f"Expected '{{[]}}', got '{result}'"

    # Real assistant message with string containing braces
    text2 = '{"content": "code: {x: 1}", "type": "text"}'
    result2 = _brace_chars_outside_strings(text2)
    assert result2 == "{}", f"Expected '{{}}', got '{result2}'"
