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

    assert len(actual["rounds"]) == 2
    r1, r2 = actual["rounds"]

    assert r1["main_call"]["call_id"] == "msg-main-1"
    assert r1["metrics"]["subagent_count"] == 1
    assert r1["metrics"]["tokens"] == {
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

    subagent_step = r1["steps"][-1]
    assert subagent_step["type"] == "subagent_run"
    assert subagent_step["parent_tool_call_id"] == "toolu_agent_1"
    assert subagent_step["subagent_id"] == "child"
    assert [sr["main_call"]["call_id"] for sr in subagent_step["sub_rounds"]] == [
        "msg-child-1",
        "msg-child-2",
    ]
    first_sub_llm_step = next(
        step for step in subagent_step["sub_rounds"][0]["steps"]
        if step["type"] == "llm_call"
    )
    assert first_sub_llm_step["scope"] == "subagent"

    assert r2["request"]["rendered"]["blocks"] == [
        {
            "type": "tool_result",
            "tool_call_id": "toolu_bash_1",
            "text": "README.md\nsrc\ntests",
        },
        {
            "type": "tool_result",
            "tool_call_id": "toolu_agent_1",
            "text": "子 agent 完成测试范围总结。",
        },
    ]
    assert actual["tool_result_links"] == [
        {
            "source_tool_call_id": "toolu_bash_1",
            "consumed_by_call_id": "msg-main-2",
            "consumed_by_round_id": 2,
        },
        {
            "source_tool_call_id": "toolu_agent_1",
            "consumed_by_call_id": "msg-main-2",
            "consumed_by_round_id": 2,
        },
    ]


def test_claude_code_source_file_entrypoint_matches_adapter_snapshot():
    actual = parse_normalized_session_file(
        SUBAGENT_INPUT,
        project_key="/repo",
        session_id="session-claude-001",
    )

    assert actual == _load_expected()
