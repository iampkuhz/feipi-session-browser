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
    assert [s["canonical_category"] for s in c1["request"]["token_sources"]] == [
        "system_base_prompt",
        "runtime_policy_context",
        "tool_definitions",
        "skills_and_agents",
        "project_context",
        "current_user_input",
        "tool_results",
        "conversation_history",
        "unknown_retained_context",
    ]
    assert c1["request"]["token_sources"][1]["agent_bucket"] == "Developer instructions"
    assert c1["request"]["token_sources"][4]["agent_bucket"] == "Project/environment context"
    assert c1["request"]["token_sources"][5]["agent_bucket"] == "Current user prompt"
    assert {b["canonical_category"] for b in c1["response"]["token_sources"]} == {
        "visible_text",
        "tool_use",
        "reasoning",
    }
    assert c1["response"]["tool_use_ids"] == ["call_run_tests"]
    assert c2["request"]["tool_result_ids"] == ["call_run_tests"]
    assert c2["request"]["token_sources"][6]["agent_bucket"] == "Tool results"
    assert actual["tool_executions"][0]["tool_call_id"] == "call_run_tests"
    assert actual["tool_executions"][0]["declared_by_call_id"] == "codex-call-0001"
    assert actual["tool_executions"][0]["result_consumed_by_call_id"] == "codex-call-0002"
    assert actual["tool_executions"][0]["result_ref"]["payload_path"] == "result"


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
    [fragment] = actual["diagnostics"]["token_fragments"]
    assert fragment["record_index"] == 7
    assert fragment["status"] == "duplicate_token_count"
    assert fragment["contribution"] == 0
    assert fragment["cumulative_total_tokens"] == 67802
