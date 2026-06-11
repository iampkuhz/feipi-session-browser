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

    assert len(actual["calls"]) == 2
    c1, c2 = actual["calls"]

    assert c1["call_id"] == "qoder-msg-1"
    assert c1["response"]["content_refs"][0]["payload_type"] == "thinking"
    assert [b["canonical_category"] for b in c1["response"]["token_sources"]] == [
        "visible_text",
        "thinking",
        "tool_use",
        "unknown_output",
    ]
    assert c1["usage"]["raw_fields"]["qoder_input_tokens_total"] == 800
    assert actual["tool_executions"][0]["files_touched"] == ["diagram.puml"]

    assert c2["request"]["token_sources"][6]["agent_bucket"] == "Tool results"
    assert actual["tool_executions"][0]["tool_call_id"] == "toolu_qoder_write"
    assert actual["tool_executions"][0]["declared_by_call_id"] == "qoder-msg-1"
    assert actual["tool_executions"][0]["result_consumed_by_call_id"] == "qoder-msg-2"


def test_qoder_source_file_entrypoint_matches_adapter_snapshot():
    actual = parse_normalized_session_file(
        TOOL_LOOP_INPUT,
        project_key="/repo",
        session_id="session-qoder-001",
    )

    assert actual == _load_expected()
