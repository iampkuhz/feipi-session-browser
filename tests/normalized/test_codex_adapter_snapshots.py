"""Codex normalized adapter snapshot tests."""

from __future__ import annotations

import json
from pathlib import Path

from session_browser.normalized import validate_normalized_session
from session_browser.normalized.agents.codex_normalization import parse_codex_events, parse_codex_rollout_file
from session_browser.sources.codex_session_source import parse_normalized_session_file


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
    assert c1["attribution_candidates"]["response"]["tool_calls"][0]["payload"]["call_id"] == "call_run_tests"
    assert "tool_results" not in c1["attribution_candidates"]["request"]
    assert c2["attribution_candidates"]["request"]["tool_results"][0]["payload"]["call_id"] == "call_run_tests"
    assert "reasoning_output" in c1["attribution_candidates"]["response"]
    required_source_unit_fields = {
        "source_id",
        "dedupe_key",
        "origin_path",
        "canonical_source_locator",
        "unit_type",
        "candidate",
        "direction",
        "event_order",
        "part_index",
        "byte_range",
    }
    assert all(required_source_unit_fields <= set(unit) for unit in c1["source_units"])
    assert not any(
        unit["candidate"] == "tool_results"
        for unit in c1["source_units"]
        if unit["direction"] == "request"
    )
    assert any(
        unit["candidate"] == "tool_results"
        for unit in c2["source_units"]
        if unit["direction"] == "request"
    )


def test_codex_normalized_candidates_follow_call_flow():
    actual = parse_codex_rollout_file(TOOL_LOOP_INPUT, thread_info=_thread_info())
    c1, c2 = actual["calls"]

    c1_request = c1["attribution_candidates"]["request"]
    c1_response = c1["attribution_candidates"]["response"]
    c2_request = c2["attribution_candidates"]["request"]

    assert c1_request["user_input"][0]["text"] == "Run tests"
    assert c1_response["tool_calls"][0]["payload"]["name"] == "exec_command"
    assert c2_request["tool_results"][0]["text"].startswith("Process exited with code 0")
    history_sources = {item["source_candidate"] for item in c2_request["conversation_history"]}
    assert {"user_input", "assistant_output", "reasoning_output", "tool_calls"}.issubset(history_sources)


def test_codex_project_instruction_wrapper_maps_to_system_instruction_source_unit():
    project_wrapper = (
        "# AGENTS.md instructions for /repo\n\n"
        "<INSTRUCTIONS>\n"
        "Use concise Chinese responses.\n"
        "</INSTRUCTIONS>"
    )
    events = [
        {
            "timestamp": "2026-06-10T00:00:00.000Z",
            "type": "session_meta",
            "payload": {"id": "codex-project-wrapper", "cwd": "/repo"},
        },
        {
            "timestamp": "2026-06-10T00:00:01.000Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "developer",
                "content": [{"type": "input_text", "text": project_wrapper}],
            },
        },
        {
            "timestamp": "2026-06-10T00:00:02.000Z",
            "type": "event_msg",
            "payload": {"type": "user_message", "message": "start"},
        },
        {
            "timestamp": "2026-06-10T00:00:03.000Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "ok"}],
            },
        },
        {
            "timestamp": "2026-06-10T00:00:04.000Z",
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "info": {
                    "last_token_usage": {
                        "input_tokens": 100,
                        "output_tokens": 10,
                        "total_tokens": 110,
                    },
                    "total_token_usage": {
                        "input_tokens": 100,
                        "output_tokens": 10,
                        "total_tokens": 110,
                    },
                },
            },
        },
    ]

    actual = parse_codex_events(events, thread_info={"id": "codex-project-wrapper", "cwd": "/repo"})
    validate_normalized_session(actual)
    units = actual["calls"][0]["source_units"]
    project_unit = next(unit for unit in units if unit["unit_type"] == "project_instruction_bundle")

    assert project_unit["candidate"] == "system_instructions"
    assert project_unit["canonical_source_locator"] == "/repo/AGENTS.md"
    assert not any(unit["candidate"] == "repo_context" for unit in units)


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
