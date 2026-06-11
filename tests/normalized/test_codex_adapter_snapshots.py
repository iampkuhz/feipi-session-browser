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

    assert len(actual["rounds"]) == 2
    assert [r["main_call"]["call_id"] for r in actual["rounds"]] == [
        "codex-call-0001",
        "codex-call-0002",
    ]

    r1, r2 = actual["rounds"]
    assert r1["request_attribution"]["buckets"][0]["bucket"] == "Developer instructions"
    assert r1["request_attribution"]["buckets"][1]["bucket"] == "Project/environment context"
    assert r1["request_attribution"]["buckets"][2]["bucket"] == "Current user prompt"
    assert {b["bucket"] for b in r1["response_attribution"]["buckets"]} == {
        "Visible text",
        "Tool use",
        "Reasoning",
    }
    assert r1["steps"][0]["type"] == "user_context"
    assert r1["steps"][1]["type"] == "llm_call"
    assert r1["steps"][2]["type"] == "tool_batch"

    assert r2["request"]["rendered"]["blocks"] == [{
        "type": "tool_result",
        "tool_call_id": "call_run_tests",
        "text": "2 passed",
    }]
    assert r2["request_attribution"]["buckets"][0]["bucket"] == "Tool results"
    assert actual["tool_result_links"] == [{
        "source_tool_call_id": "call_run_tests",
        "consumed_by_call_id": "codex-call-0002",
        "consumed_by_round_id": 2,
    }]


def test_codex_source_file_entrypoint_matches_adapter_snapshot():
    actual = parse_normalized_session_file(TOOL_LOOP_INPUT, thread_info=_thread_info())
    expected = _load_expected()

    assert actual == expected
