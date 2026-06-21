"""Domain model boundary and invariant tests."""

from __future__ import annotations

import pytest

from session_browser.domain.serializers import normalized_token_breakdown_to_dict, subagent_summary_to_dict
from session_browser.domain.models import (
    ChatMessage,
    LLMCall,
    NormalizedTokenBreakdown,
    SessionSummary,
    SubagentRun,
    SubagentSummary,
    TokenPrecision,
    TokenTotalSemantics,
    ToolCall,
)


def test_token_breakdown_recomputes_component_sum_total():
    bd = NormalizedTokenBreakdown(
        fresh_input_tokens=10,
        cache_read_tokens=3,
        cache_write_tokens=2,
        output_tokens=5,
        total_tokens=1,
        total_semantics=TokenTotalSemantics.EXCLUSIVE_COMPONENT_SUM,
    )

    assert bd.total_tokens == 20
    assert bd.component_total == 20
    assert "total_tokens aligned" in " ".join(bd.notes)


def test_token_breakdown_rejects_negative_component():
    with pytest.raises(ValueError, match="fresh_input_tokens"):
        NormalizedTokenBreakdown(fresh_input_tokens=-1)


def test_token_breakdown_rejects_invalid_precision():
    with pytest.raises(ValueError, match="precision"):
        NormalizedTokenBreakdown(precision="almost_exact")


def test_token_precision_is_string_enum_for_legacy_comparison():
    bd = NormalizedTokenBreakdown(precision="provider_reported")

    assert bd.precision == TokenPrecision.PROVIDER_REPORTED
    assert normalized_token_breakdown_to_dict(bd)["precision"] == "provider_reported"


def test_session_summary_computes_missing_total_from_components():
    summary = SessionSummary(
        agent="codex",
        session_id="s1",
        title="t",
        project_key="/repo",
        project_name="repo",
        cwd="/repo",
        started_at="2026-01-01T00:00:00Z",
        ended_at="2026-01-01T00:00:01Z",
        fresh_input_tokens=7,
        cache_read_tokens=2,
        cache_write_tokens=1,
        output_tokens=4,
    )

    assert summary.token_component_total == 14
    assert summary.total_tokens == 14
    assert summary.session_key == "codex:s1"


def test_session_summary_rejects_negative_duration():
    with pytest.raises(ValueError, match="duration_seconds"):
        SessionSummary(
            agent="codex",
            session_id="s1",
            title="t",
            project_key="/repo",
            project_name="repo",
            cwd="/repo",
            started_at="2026-01-01T00:00:00Z",
            ended_at="2026-01-01T00:00:01Z",
            duration_seconds=-0.1,
        )


def test_chat_message_rejects_out_of_range_token_ratio():
    with pytest.raises(ValueError, match="token_ratio"):
        ChatMessage(role="assistant", content="ok", timestamp="", token_ratio=1.5)


def test_llm_call_builds_composed_submodels_and_derived_total():
    call = LLMCall(
        id="call-1",
        model="gpt-test",
        scope="main",
        subagent_id="",
        round_index=0,
        parent_id="",
        parent_tool_name="",
        timestamp="2026-01-01T00:00:00Z",
        status="ok",
        input_tokens=10,
        cache_read_tokens=4,
        output_tokens=3,
    )

    assert call.total_tokens == 17
    assert call.identity.id == "call-1"
    assert call.usage.total_tokens == 17
    assert call.payload_refs.request_payload_raw == ""
    assert call.content.response_full == ""


def test_llm_call_rejects_tool_count_mismatch_when_collection_present():
    with pytest.raises(ValueError, match="tool_call_count"):
        LLMCall(
            id="call-1",
            model="gpt-test",
            scope="main",
            subagent_id="",
            round_index=0,
            parent_id="",
            parent_tool_name="",
            timestamp="2026-01-01T00:00:00Z",
            status="ok",
            tool_calls=[ToolCall(name="Read")],
            tool_call_count=2,
        )


def test_subagent_summary_validates_snapshot_counts_and_keeps_legacy_access():
    summary = SubagentSummary.from_dict({
        "agent_id": "agent-1",
        "agent_type": "implementer",
        "tool_call_count": 2,
        "failed_tool_count": 1,
        "tool_counts": {"Bash": 2},
        "unknown_runtime_field": "kept",
    })

    assert summary["agent_id"] == "agent-1"
    assert summary.get("agent_type") == "implementer"
    assert subagent_summary_to_dict(summary)["unknown_runtime_field"] == "kept"


def test_subagent_summary_rejects_negative_snapshot_count():
    with pytest.raises(ValueError, match="tool_call_count"):
        SubagentSummary(agent_id="agent-1", tool_call_count=-1)


def test_subagent_run_exposes_live_counts_from_tool_collection():
    run = SubagentRun(
        summary=SubagentSummary(agent_id="agent-1", tool_call_count=99),
        tool_calls=[
            ToolCall(name="Read"),
            ToolCall(name="Bash", status="error"),
        ],
    )

    assert run["summary"]["agent_id"] == "agent-1"
    assert run.live_tool_call_count == 2
    assert run.live_failed_tool_count == 1
