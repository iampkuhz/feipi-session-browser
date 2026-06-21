"""Codex normalized adapter snapshot tests."""

from __future__ import annotations

import json
from pathlib import Path

from session_browser.normalized import validate_normalized_session
from session_browser.normalized.agents.codex_normalization import parse_codex_events, parse_codex_rollout_file
from session_browser.attribution.context import _hydrate_normalized_call
from session_browser.sources.codex_session_source import parse_normalized_session_file


FIXTURE_DIR = Path("tests/fixtures/normalized/codex")
TOOL_LOOP_INPUT = FIXTURE_DIR / "tool_loop.input" / "rollout.jsonl"
TOOL_LOOP_EXPECTED = FIXTURE_DIR / "tool_loop.expected.json"
SUBAGENT_INPUT = FIXTURE_DIR / "subagent.input" / "rollout-2026-06-18T14-11-04-parent-thread.jsonl"
THREE_AGENT_SAMPLE = Path(
    "docs/session-samples/codex/019ede24-67de-7b11-b46f-7922530907a9/"
    "019ede24-67de-7b11-b46f-7922530907a9.jsonl"
)


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
    h1 = _hydrate_normalized_call(actual, c1)
    h2 = _hydrate_normalized_call(actual, c2)
    assert actual["schema_version"] == "session-detail.normalized.v3"
    assert actual["source_unit_catalog"]
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
    assert "source_units" not in c1
    assert "attribution_candidates" not in c1
    assert h1["attribution_candidates"]["response"]["tool_calls"][0]["payload"]["call_id"] == "call_run_tests"
    assert "tool_results" not in h1["attribution_candidates"]["request"]
    assert h2["attribution_candidates"]["request"]["tool_results"][0]["payload"]["call_id"] == "call_run_tests"
    assert "reasoning_output" in h1["attribution_candidates"]["response"]
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
    assert all(required_source_unit_fields <= set(unit) for unit in h1["source_units"])
    assert not any(
        unit["candidate"] == "tool_results"
        for unit in h1["source_units"]
        if unit["direction"] == "request"
    )
    assert any(
        unit["candidate"] == "tool_results"
        for unit in h2["source_units"]
        if unit["direction"] == "request"
    )


def test_codex_normalized_candidates_follow_call_flow():
    actual = parse_codex_rollout_file(TOOL_LOOP_INPUT, thread_info=_thread_info())
    c1, c2 = actual["calls"]
    h1 = _hydrate_normalized_call(actual, c1)
    h2 = _hydrate_normalized_call(actual, c2)

    c1_request = h1["attribution_candidates"]["request"]
    c1_response = h1["attribution_candidates"]["response"]
    c2_request = h2["attribution_candidates"]["request"]

    assert c1_request["user_input"][0]["text"] == "Run tests"
    assert c1_response["tool_calls"][0]["payload"]["name"] == "exec_command"
    assert c2_request["tool_results"][0]["text"].startswith("Process exited with code 0")
    history_sources = {item["source_candidate"] for item in c2_request["conversation_history"]}
    assert {"user_input", "assistant_output", "tool_calls"}.issubset(history_sources)
    reasoning_sources = {item["source_candidate"] for item in c2_request["reasoning_state"]}
    assert "reasoning_output" in reasoning_sources


def test_codex_compact_source_units_stay_linear_and_hydrate_last_call(monkeypatch):
    from session_browser.normalized.agents import codex_normalization as codex_norm

    rounds = 24
    events = _linear_codex_events(rounds)
    original = codex_norm.draft_to_catalog_unit
    finalize_count = 0

    def counted_draft_to_catalog_unit(draft):
        nonlocal finalize_count
        finalize_count += 1
        return original(draft)

    monkeypatch.setattr(codex_norm, "draft_to_catalog_unit", counted_draft_to_catalog_unit)

    actual = parse_codex_events(events, thread_info={"id": "codex-linear", "cwd": "/repo"})

    validate_normalized_session(actual)
    assert len(actual["calls"]) == rounds
    assert all("source_units" not in call for call in actual["calls"])
    assert all("attribution_candidates" not in call for call in actual["calls"])
    assert len(actual["source_unit_catalog"]) <= rounds * 6 + 8
    assert finalize_count <= rounds * 6 + 8

    hydrated = _hydrate_normalized_call(actual, actual["calls"][-1])
    request_candidates = hydrated["attribution_candidates"]["request"]
    history_text = "\n".join(
        str(item.get("text") or item.get("preview") or "")
        for item in request_candidates["conversation_history"]
    )
    assert "request 1" in history_text
    assert f"answer {rounds - 1}" in history_text


def _linear_codex_events(rounds: int) -> list[dict]:
    events: list[dict] = [
        {
            "timestamp": "2026-06-10T00:00:00.000Z",
            "type": "session_meta",
            "payload": {
                "id": "codex-linear",
                "cwd": "/repo",
                "base_instructions": {"text": "Be concise."},
            },
        }
    ]
    cumulative_input = 0
    cumulative_output = 0
    for idx in range(1, rounds + 1):
        cumulative_input += 100 + idx
        cumulative_output += 10 + idx
        events.extend([
            {
                "timestamp": f"2026-06-10T00:{idx:02d}:00.000Z",
                "type": "turn_context",
                "payload": {
                    "turn_id": f"turn-{idx}",
                    "cwd": "/repo",
                    "model": "gpt-test",
                },
            },
            {
                "timestamp": f"2026-06-10T00:{idx:02d}:01.000Z",
                "type": "event_msg",
                "payload": {"type": "user_message", "message": f"request {idx}"},
            },
            {
                "timestamp": f"2026-06-10T00:{idx:02d}:02.000Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": f"answer {idx}"}],
                },
            },
            {
                "timestamp": f"2026-06-10T00:{idx:02d}:03.000Z",
                "type": "event_msg",
                "payload": {
                    "type": "token_count",
                    "info": {
                        "last_token_usage": {
                            "input_tokens": 100 + idx,
                            "output_tokens": 10 + idx,
                            "total_tokens": 110 + idx * 2,
                        },
                        "total_token_usage": {
                            "input_tokens": cumulative_input,
                            "output_tokens": cumulative_output,
                            "total_tokens": cumulative_input + cumulative_output,
                        },
                    },
                },
            },
        ])
    return events


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
    units = _hydrate_normalized_call(actual, actual["calls"][0])["source_units"]
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


def test_codex_three_agent_sample_matches_recovered_call_graph():
    """目标样例应恢复 Main 5 + 两个 subagent 各 2 个业务 call。"""
    actual = parse_codex_rollout_file(
        THREE_AGENT_SAMPLE,
        thread_info={
            "id": "019ede24-67de-7b11-b46f-7922530907a9",
            "title": "你是 `feipi-session-browser` 仓库的主 agent。请并行 spawn 2 个 scoped subagent，并等待两者结束后只汇总状态。",
            "cwd": "/Users/zhehan/Documents/tools/llm/feipi-session-browser",
            "source": "vscode",
            "model": "gpt-5.5",
            "git_branch": "main",
        },
    )

    validate_normalized_session(actual)

    calls = actual["calls"]
    assert len(calls) == 9
    assert [call["scope"] for call in calls] == [
        "main",
        "main",
        "subagent",
        "subagent",
        "subagent",
        "subagent",
        "main",
        "main",
        "main",
    ]
    assert {call["model"] for call in calls} == {"gpt-5.5"}

    c1, c2 = calls[0], calls[1]
    assert c1["response"]["tool_call_ids"] == ["call_XsbhHJb7vGOu1oAP5oFqgBr7"]
    assert c2["request"]["tool_result_ids"] == ["call_XsbhHJb7vGOu1oAP5oFqgBr7"]
    assert c2["usage"] == {
        "fresh": 13443,
        "cache_read": 16384,
        "cache_write": 0,
        "output": 1112,
        "total": 30939,
    }

    tool_search = actual["tool_executions"][0]
    assert tool_search["tool_call_id"] == "call_XsbhHJb7vGOu1oAP5oFqgBr7"
    assert tool_search["result_consumed_by_call_id"] == "codex-call-0002"
    assert "status" not in tool_search

    hydrated_c2 = _hydrate_normalized_call(actual, c2)
    request_candidates = hydrated_c2["attribution_candidates"]["request"]
    assert "tool_definitions" in request_candidates
    assert request_candidates["tool_definitions"][0]["payload"]["call_id"] == "call_XsbhHJb7vGOu1oAP5oFqgBr7"
    assert "reasoning_state" in request_candidates
