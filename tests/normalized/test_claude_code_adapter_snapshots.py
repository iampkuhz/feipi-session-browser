"""Claude Code normalized adapter snapshot tests."""

from __future__ import annotations

import json
from pathlib import Path

from session_browser.normalized import validate_normalized_session
from session_browser.normalized.agents.claude_code import parse_claude_code_session_file
from session_browser.sources.claude import parse_normalized_session_file


FIXTURE_DIR = Path("tests/fixtures/normalized/claude_code")
SUBAGENT_INPUT = FIXTURE_DIR / "subagent_tool.input" / "session-claude-001.jsonl"
SUBAGENT_EXPECTED = FIXTURE_DIR / "subagent_tool.expected.json"


def _load_expected() -> dict:
    return json.loads(SUBAGENT_EXPECTED.read_text(encoding="utf-8"))


def test_claude_code_subagent_snapshot_matches_expected_json():
    actual = parse_claude_code_session_file(
        SUBAGENT_INPUT,
        project_key="/repo",
        session_id="session-claude-001",
    )

    assert actual == _load_expected()


def test_claude_code_subagent_normalized_semantics():
    actual = parse_claude_code_session_file(
        SUBAGENT_INPUT,
        project_key="/repo",
        session_id="session-claude-001",
    )

    validate_normalized_session(actual)

    assert [(c["call_id"], c["scope"], c["parent_call_id"], c["parent_tool_call_id"]) for c in actual["calls"]] == [
        ("msg-main-1", "main", "", ""),
        ("msg-child-1", "subagent", "msg-main-1", "toolu_agent_1"),
        ("msg-child-2", "subagent", "msg-main-1", "toolu_agent_1"),
        ("msg-main-2", "main", "", ""),
    ]
    c1, child1, child2, c2 = actual["calls"]

    assert c1["call_id"] == "msg-main-1"
    assert c1["usage"] == {
        "fresh": 1000,
        "cache_read": 100,
        "cache_write": 200,
        "output": 60,
        "total": 1360,
        "source_total": 1360,
        "total_semantics": "component_sum",
        "quality": {
            "source": "claude_code_jsonl_usage",
            "precision": "provider_reported",
            "status": "available",
        },
        "raw_fields": {
            "input_tokens": 1000,
            "cache_creation_input_tokens": 200,
            "cache_read_input_tokens": 100,
            "output_tokens": 60,
        },
    }

    assert child1["scope"] == "subagent"
    assert child2["scope"] == "subagent"
    assert c2["request"]["tool_result_ids"] == ["toolu_bash_1", "toolu_agent_1"]
    assert c2["request"]["token_sources"][6]["agent_bucket"] == "Tool results"
    assert [(t["tool_call_id"], t["declared_by_call_id"], t["result_consumed_by_call_id"], t["subagent_id"]) for t in actual["tool_executions"]] == [
        ("toolu_bash_1", "msg-main-1", "msg-main-2", ""),
        ("toolu_agent_1", "msg-main-1", "msg-main-2", "child"),
        ("toolu_child_read", "msg-child-1", "msg-child-2", "child"),
    ]


def test_claude_code_source_file_entrypoint_matches_adapter_snapshot():
    actual = parse_normalized_session_file(
        SUBAGENT_INPUT,
        project_key="/repo",
        session_id="session-claude-001",
    )

    assert actual == _load_expected()
