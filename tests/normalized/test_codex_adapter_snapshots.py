"""Codex normalized adapter snapshot tests."""

from __future__ import annotations

import json
from pathlib import Path

from session_browser.normalized import validate_normalized_session
from session_browser.normalized.agents.codex import parse_codex_rollout_file
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
