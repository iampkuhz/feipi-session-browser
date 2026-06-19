"""Codex normalized adapter snapshot tests."""

from __future__ import annotations

import json
from pathlib import Path

from session_browser.normalized import validate_normalized_session
from session_browser.normalized.agents.codex import parse_codex_events, parse_codex_rollout_file
from session_browser.sources.codex import parse_normalized_session_file


FIXTURE_DIR = Path("tests/fixtures/normalized/codex")
TOOL_LOOP_INPUT = FIXTURE_DIR / "tool_loop.input" / "rollout.jsonl"
TOOL_LOOP_EXPECTED = FIXTURE_DIR / "tool_loop.expected.json"
SUBAGENT_INPUT = FIXTURE_DIR / "subagent.input" / "rollout-2026-06-18T14-11-04-parent-thread.jsonl"


def _thread_info() -> dict:
    return {
        "id": "codex-fixture-tool-loop",
        "title": "Codex fixture tool loop",
        "cwd": "/repo",
        "source": "fixture",
        "model": "gpt-5.5",
        "git_branch": "main",
        "rollout_path": str(TOOL_LOOP_INPUT),
        "first_user_message": "Run tests",
    }


def _load_expected() -> dict:
    return json.loads(TOOL_LOOP_EXPECTED.read_text(encoding="utf-8"))


def test_codex_tool_loop_snapshot_matches_expected_json():
    actual = parse_codex_rollout_file(TOOL_LOOP_INPUT, thread_info=_thread_info())
    expected = _load_expected()

    assert actual == expected


def test_codex_tool_loop_normalized_semantics():
    actual = parse_codex_rollout_file(TOOL_LOOP_INPUT, thread_info=_thread_info())

    validate_normalized_session(actual)

    assert len(actual["calls"]) == 2
    assert [c["call_id"] for c in actual["calls"]] == [
        "codex-call-0001",
        "codex-call-0002",
    ]

    c1, c2 = actual["calls"]
    assert actual["schema_version"] == "session-detail.normalized.v2"
    assert c1["request"] == {"tool_result_ids": []}
    assert c1["response"]["tool_call_ids"] == ["call_run_tests"]
    assert c2["request"]["tool_result_ids"] == ["call_run_tests"]
    assert actual["tool_executions"][0]["tool_call_id"] == "call_run_tests"
    assert actual["tool_executions"][0]["declared_by_call_id"] == "codex-call-0001"
    assert actual["tool_executions"][0]["result_consumed_by_call_id"] == "codex-call-0002"
    assert "result_ref" not in actual["tool_executions"][0]
    assert "parameters" not in actual["tool_executions"][0]
    assert "type" not in actual["tool_executions"][0]
    assert "status" not in actual["tool_executions"][0]
    assert "content_refs" not in c1["request"]
    assert "token_sources" not in c1["request"]
    assert "payload_index" not in actual


def test_codex_source_file_entrypoint_matches_adapter_snapshot():
    actual = parse_normalized_session_file(TOOL_LOOP_INPUT, thread_info=_thread_info())
    expected = _load_expected()

    assert actual == expected


def test_codex_normalized_skips_duplicate_cumulative_token_count():
    events = [
        {
            "timestamp": "2026-06-10T00:00:00.000Z",
            "type": "session_meta",
            "payload": {"id": "codex-duplicate-token", "cwd": "/repo"},
        },
        {
            "timestamp": "2026-06-10T00:00:01.000Z",
            "type": "event_msg",
            "payload": {"type": "user_message", "message": "start"},
        },
        {
            "timestamp": "2026-06-10T00:00:02.000Z",
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "call_id": "call_1",
                "name": "exec_command",
                "arguments": "{}",
            },
        },
        {
            "timestamp": "2026-06-10T00:00:03.000Z",
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "info": {
                    "last_token_usage": {
                        "input_tokens": 32405,
                        "cached_input_tokens": 2432,
                        "output_tokens": 574,
                        "total_tokens": 32979,
                    },
                    "total_token_usage": {
                        "input_tokens": 32405,
                        "cached_input_tokens": 2432,
                        "output_tokens": 574,
                        "total_tokens": 32979,
                    },
                },
            },
        },
        {
            "timestamp": "2026-06-10T00:00:04.000Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "visible"}],
            },
        },
        {
            "timestamp": "2026-06-10T00:00:05.000Z",
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "info": {
                    "last_token_usage": {
                        "input_tokens": 34122,
                        "cached_input_tokens": 32128,
                        "output_tokens": 701,
                        "total_tokens": 34823,
                    },
                    "total_token_usage": {
                        "input_tokens": 66527,
                        "cached_input_tokens": 34560,
                        "output_tokens": 1275,
                        "total_tokens": 67802,
                    },
                },
            },
        },
        {
            "timestamp": "2026-06-10T00:00:06.000Z",
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "info": {
                    "last_token_usage": {
                        "input_tokens": 34122,
                        "cached_input_tokens": 32128,
                        "output_tokens": 701,
                        "total_tokens": 34823,
                    },
                    "total_token_usage": {
                        "input_tokens": 66527,
                        "cached_input_tokens": 34560,
                        "output_tokens": 1275,
                        "total_tokens": 67802,
                    },
                },
            },
        },
    ]

    actual = parse_codex_events(events, thread_info={"id": "codex-duplicate-token", "cwd": "/repo"})

    validate_normalized_session(actual)
    assert [call["usage"]["total"] for call in actual["calls"]] == [32979, 34823]
    assert len(actual["calls"]) == 2
    [fragment] = actual["diagnostics"]
    assert fragment["record_index"] == 7
    assert fragment["status"] == "duplicate_token_count"
    assert fragment["contribution"] == 0
    assert fragment["cumulative_total_tokens"] == 67802


def test_codex_subagent_rollout_links_parent_tool_and_child_calls():
    actual = parse_codex_rollout_file(
        SUBAGENT_INPUT,
        thread_info={
            "id": "parent-thread",
            "title": "Codex subagent fixture",
            "cwd": "/repo",
            "source": "fixture",
            "model": "gpt-5.5",
            "git_branch": "main",
        },
    )

    validate_normalized_session(actual)

    calls = actual["calls"]
    assert [call["scope"] for call in calls] == ["main", "subagent", "subagent", "main", "main"]
    sub_calls = [call for call in calls if call["scope"] == "subagent"]
    assert {call["subagent_id"] for call in sub_calls} == {"child-thread"}
    assert {call["parent_tool_call_id"] for call in sub_calls} == {"call_spawn"}
    assert {call["parent_tool_name"] for call in sub_calls} == {"spawn_agent"}
    assert [call["usage"]["total"] for call in sub_calls] == [78, 92]

    parent_spawn = next(tool for tool in actual["tool_executions"] if tool["tool_call_id"] == "call_spawn")
    assert parent_spawn["name"] == "spawn_agent"
    assert parent_spawn["scope"] == "main"
    assert parent_spawn["subagent_id"] == "child-thread"
    assert parent_spawn["result_consumed_by_call_id"] == "codex-call-0002"

    child_tool = next(tool for tool in actual["tool_executions"] if tool["tool_call_id"] == "call_child_exec")
    assert child_tool["scope"] == "subagent"
    assert child_tool["declared_by_call_id"].startswith("codex-subagent-child-thread-call-")
    assert child_tool["result_consumed_by_call_id"].startswith("codex-subagent-child-thread-call-")
