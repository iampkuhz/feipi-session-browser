"""Qoder normalized adapter snapshot tests."""

from __future__ import annotations

import json
from pathlib import Path

from session_browser.normalized import validate_normalized_session
from session_browser.normalized.agents.qoder import parse_qoder_session_file
from session_browser.sources.qoder import parse_normalized_session_file


FIXTURE_DIR = Path("tests/fixtures/normalized/qoder")
TOOL_LOOP_INPUT = FIXTURE_DIR / "tool_loop.input" / "session-qoder-001.jsonl"
TOOL_LOOP_EXPECTED = FIXTURE_DIR / "tool_loop.expected.json"


def _load_expected() -> dict:
    return json.loads(TOOL_LOOP_EXPECTED.read_text(encoding="utf-8"))


def test_qoder_tool_loop_snapshot_matches_expected_json():
    actual = parse_qoder_session_file(
        TOOL_LOOP_INPUT,
        project_key="/repo",
        session_id="session-qoder-001",
    )

    assert actual == _load_expected()


def test_qoder_tool_loop_normalized_semantics():
    actual = parse_qoder_session_file(
        TOOL_LOOP_INPUT,
        project_key="/repo",
        session_id="session-qoder-001",
    )

    validate_normalized_session(actual)

    assert len(actual["rounds"]) == 2
    r1, r2 = actual["rounds"]

    assert r1["main_call"]["call_id"] == "qoder-msg-1"
    assert r1["response"]["rendered"]["blocks"][0]["type"] == "thinking"
    assert [b["bucket"] for b in r1["response_attribution"]["buckets"]] == [
        "Visible text",
        "Thinking",
        "Tool use",
        "Unknown output",
    ]
    assert r1["metrics"]["tokens"]["raw_fields"]["qoder_input_tokens_total"] == 800
    assert r1["steps"][2]["tools"][0]["files_touched"] == ["diagram.puml"]

    assert r2["request_attribution"]["buckets"][0]["bucket"] == "Tool results"
    assert actual["tool_result_links"] == [{
        "source_tool_call_id": "toolu_qoder_write",
        "consumed_by_call_id": "qoder-msg-2",
        "consumed_by_round_id": 2,
    }]


def test_qoder_source_file_entrypoint_matches_adapter_snapshot():
    actual = parse_normalized_session_file(
        TOOL_LOOP_INPUT,
        project_key="/repo",
        session_id="session-qoder-001",
    )

    assert actual == _load_expected()
