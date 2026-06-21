"""Claude Code normalized adapter 快照测试。"""

from __future__ import annotations

import json
from pathlib import Path

from session_browser.normalized import validate_normalized_session
from session_browser.normalized.agents.claude_code_normalization import parse_claude_code_session_file
from session_browser.attribution.context import _hydrate_normalized_call
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
    }

    assert child1["scope"] == "subagent"
    assert child2["scope"] == "subagent"
    assert c1["response"]["tool_call_ids"] == ["toolu_bash_1", "toolu_agent_1"]
    assert c2["request"]["tool_result_ids"] == ["toolu_bash_1", "toolu_agent_1"]
    assert [(t["tool_call_id"], t["declared_by_call_id"], t["result_consumed_by_call_id"], t.get("subagent_id", "")) for t in actual["tool_executions"]] == [
        ("toolu_bash_1", "msg-main-1", "msg-main-2", ""),
        ("toolu_agent_1", "msg-main-1", "msg-main-2", "child"),
        ("toolu_child_read", "msg-child-1", "msg-child-2", "child"),
    ]
    assert "content_refs" not in c1["request"]
    assert "type" not in actual["tool_executions"][0]
    assert "status" not in actual["tool_executions"][0]
    assert "availability" not in c1["request"]
    assert "payload_ref" not in c1["request"]
    assert "token_sources" not in c1["request"]
    assert "payload_index" not in actual
    assert "context_sources" not in actual
    assert "parse_diagnostics" not in actual
    assert actual["source_unit_catalog"]
    assert all("source_units" not in call for call in actual["calls"])
    assert all("attribution_candidates" not in call for call in actual["calls"])
    c1h = _hydrate_normalized_call(actual, c1)
    c2h = _hydrate_normalized_call(actual, c2)
    _assert_source_units(c1h, request={"user_input", "runtime_context"}, response={"assistant_output", "tool_calls"})
    _assert_source_units(c2h, request={"tool_results", "conversation_history", "runtime_context"}, response={"assistant_output"})


def test_claude_code_source_file_entrypoint_matches_adapter_snapshot():
    actual = parse_normalized_session_file(
        SUBAGENT_INPUT,
        project_key="/repo",
        session_id="session-claude-001",
    )

    assert actual == _load_expected()


def test_claude_code_away_summary_leaf_uuid_becomes_call_without_sidecar(tmp_path):
    session_file = tmp_path / "session-away-summary.jsonl"
    events = [
        {
            "type": "user",
            "uuid": "user-1",
            "timestamp": "2026-06-13T00:00:00.000Z",
            "cwd": "/repo",
            "sessionId": "session-away-summary",
            "message": {"role": "user", "content": "finish"},
        },
        {
            "type": "assistant",
            "uuid": "assistant-event-1",
            "timestamp": "2026-06-13T00:00:01.000Z",
            "sessionId": "session-away-summary",
            "message": {
                "model": "qwen3.7-plus",
                "id": "msg-main",
                "role": "assistant",
                "type": "message",
                "content": [{"type": "text", "text": "done"}],
                "usage": {"input_tokens": 10, "output_tokens": 2},
                "stop_reason": "end_turn",
            },
        },
        {
            "type": "system",
            "subtype": "away_summary",
            "uuid": "recap-1",
            "timestamp": "2026-06-13T00:00:02.000Z",
            "sessionId": "session-away-summary",
            "content": "recap text",
        },
        {
            "type": "last-prompt",
            "leafUuid": "recap-1",
            "sessionId": "session-away-summary",
            "lastPrompt": "finish",
        },
    ]
    session_file.write_text(
        "\n".join(json.dumps(event, ensure_ascii=False) for event in events) + "\n",
        encoding="utf-8",
    )

    actual = parse_claude_code_session_file(
        session_file,
        project_key="/repo",
        session_id="session-away-summary",
    )

    validate_normalized_session(actual)
    assert [call["call_id"] for call in actual["calls"]] == ["msg-main", "recap-1"]
    assert actual["calls"][1]["usage"] == {
        "fresh": 2,
        "cache_read": 0,
        "cache_write": 0,
        "output": 3,
        "total": 5,
    }
    assert actual["calls"][1]["usage_source"] == {
        "kind": "estimated",
        "method": "chars_div_4",
        "reason": "provider_usage_missing",
    }
    assert actual["diagnostics"] == [{
        "kind": "away_summary_usage_estimated",
        "message": "Claude Code away_summary 表示一次 recap LLM call，但本地 JSONL 没有 provider usage；usage 由 lastPrompt 和 summary 文本估算。",
        "record_index": 3,
        "call_id": "recap-1",
    }]


def test_claude_code_compact_source_units_stay_linear_and_hydrate_last_call(tmp_path, monkeypatch):
    from session_browser.normalized.agents import claude_code_normalization as claude_norm

    rounds = 24
    session_file = tmp_path / "session-linear.jsonl"
    events = _linear_claude_events(rounds)
    session_file.write_text(
        "\n".join(json.dumps(event, ensure_ascii=False) for event in events) + "\n",
        encoding="utf-8",
    )
    original = claude_norm.draft_to_catalog_unit
    finalize_count = 0

    def counted_draft_to_catalog_unit(draft):
        nonlocal finalize_count
        finalize_count += 1
        return original(draft)

    monkeypatch.setattr(claude_norm, "draft_to_catalog_unit", counted_draft_to_catalog_unit)

    actual = parse_claude_code_session_file(
        session_file,
        project_key="/repo",
        session_id="session-linear",
    )

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


def _linear_claude_events(rounds: int) -> list[dict]:
    events: list[dict] = []
    for idx in range(1, rounds + 1):
        events.append({
            "type": "user",
            "uuid": f"user-{idx}",
            "timestamp": f"2026-06-13T00:{idx:02d}:00.000Z",
            "cwd": "/repo",
            "sessionId": "session-linear",
            "message": {"role": "user", "content": f"request {idx}"},
        })
        events.append({
            "type": "assistant",
            "uuid": f"assistant-event-{idx}",
            "timestamp": f"2026-06-13T00:{idx:02d}:01.000Z",
            "sessionId": "session-linear",
            "message": {
                "model": "claude-test",
                "id": f"msg-{idx}",
                "role": "assistant",
                "type": "message",
                "content": [{"type": "text", "text": f"answer {idx}"}],
                "usage": {"input_tokens": 100 + idx, "output_tokens": 10 + idx},
                "stop_reason": "end_turn",
            },
        })
    return events


def _assert_source_units(call: dict, *, request: set[str], response: set[str]) -> None:
    units = call.get("source_units") or []
    assert units
    required = {
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
    for unit in units:
        assert required <= set(unit)
    by_direction = {
        "request": {u["candidate"] for u in units if u["direction"] == "request"},
        "response": {u["candidate"] for u in units if u["direction"] == "response"},
    }
    assert request <= by_direction["request"]
    assert response <= by_direction["response"]
