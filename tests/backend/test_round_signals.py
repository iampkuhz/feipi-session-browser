"""Tests for round-level signal computation in the Timeline tab."""

from __future__ import annotations

import pytest

from session_browser.domain.models import (
    ChatMessage,
    ConversationRound,
    ToolCall,
)
from session_browser.web.routes import compute_round_signals


def _make_round(
    tool_calls: list[ToolCall] | None = None,
    llm_error_count: int = 0,
    usage: dict | None = None,
) -> ConversationRound:
    """Helper to build a ConversationRound with the given properties."""
    assistant = ChatMessage(
        role="assistant",
        content="",
        timestamp="",
        usage=usage or {},
    )
    user = ChatMessage(role="user", content="test", timestamp="")
    return ConversationRound(
        user_msg=user,
        assistant_msg=assistant,
        tool_calls=tool_calls or [],
        llm_error_count=llm_error_count,
    )


def _tc(name: str, status: str = "completed", exit_code: int | None = None, duration_ms: float = 0) -> ToolCall:
    return ToolCall(name=name, status=status, exit_code=exit_code, duration_ms=duration_ms)


def _signal_keys(signals: list[dict]) -> list[str]:
    return [s["key"] for s in signals]


# ── Critical signals ──────────────────────────────────────────────────


class TestFailedToolSignal:
    def test_one_failed_tool_triggers_warning(self):
        r = _make_round(tool_calls=[_tc("Bash", status="error", exit_code=1)])
        sigs = compute_round_signals(r, 1)
        assert "failed-tool" in _signal_keys(sigs)
        sig = next(s for s in sigs if s["key"] == "failed-tool")
        assert sig["severity"] == "warning"
        assert "1 failed tool" in sig["reason"]

    def test_two_failed_tools_triggers_warning(self):
        tools = [_tc("Read", status="error", exit_code=1), _tc("Bash", status="error", exit_code=2)]
        r = _make_round(tool_calls=tools)
        sigs = compute_round_signals(r, 1)
        assert "failed-tool" in _signal_keys(sigs)
        sig = next(s for s in sigs if s["key"] == "failed-tool")
        assert sig["severity"] == "warning"

    def test_three_failed_tools_triggers_critical(self):
        tools = [
            _tc("Read", status="error", exit_code=1),
            _tc("Bash", status="error", exit_code=2),
            _tc("Edit", status="error", exit_code=1),
        ]
        r = _make_round(tool_calls=tools)
        sigs = compute_round_signals(r, 1)
        assert "failed-tool" in _signal_keys(sigs)
        sig = next(s for s in sigs if s["key"] == "failed-tool")
        assert sig["severity"] == "critical"
        assert "3 failed tools" in sig["reason"]

    def test_no_failed_tools_no_signal(self):
        r = _make_round(tool_calls=[_tc("Read"), _tc("Bash")])
        sigs = compute_round_signals(r, 1)
        assert "failed-tool" not in _signal_keys(sigs)


class TestLLMErrorSignal:
    def test_one_llm_error_triggers_warning(self):
        r = _make_round(llm_error_count=1)
        sigs = compute_round_signals(r, 1)
        assert "llm-error" in _signal_keys(sigs)
        sig = next(s for s in sigs if s["key"] == "llm-error")
        assert sig["severity"] == "warning"

    def test_two_llm_errors_triggers_warning(self):
        r = _make_round(llm_error_count=2)
        sigs = compute_round_signals(r, 1)
        assert "llm-error" in _signal_keys(sigs)
        sig = next(s for s in sigs if s["key"] == "llm-error")
        assert sig["severity"] == "warning"

    def test_three_llm_errors_triggers_critical(self):
        r = _make_round(llm_error_count=3)
        sigs = compute_round_signals(r, 1)
        assert "llm-error" in _signal_keys(sigs)
        sig = next(s for s in sigs if s["key"] == "llm-error")
        assert sig["severity"] == "critical"

    def test_no_llm_error(self):
        r = _make_round(llm_error_count=0)
        sigs = compute_round_signals(r, 1)
        assert "llm-error" not in _signal_keys(sigs)


# ── Warning signals ───────────────────────────────────────────────────


class TestLongToolSignal:
    def test_tool_over_5_minutes(self):
        r = _make_round(tool_calls=[_tc("Bash", duration_ms=301_000)])
        sigs = compute_round_signals(r, 1)
        assert "long-tool" in _signal_keys(sigs)

    def test_tool_under_5_minutes(self):
        r = _make_round(tool_calls=[_tc("Bash", duration_ms=299_000)])
        sigs = compute_round_signals(r, 1)
        assert "long-tool" not in _signal_keys(sigs)

    def test_exactly_5_minutes(self):
        r = _make_round(tool_calls=[_tc("Bash", duration_ms=300_000)])
        sigs = compute_round_signals(r, 1)
        assert "long-tool" in _signal_keys(sigs)


class TestToolBurstSignal:
    def test_20_tools_diverse_names(self):
        tools = [_tc(f"Tool{i % 7}") for i in range(20)]
        r = _make_round(tool_calls=tools)
        sigs = compute_round_signals(r, 1)
        assert "tool-burst" in _signal_keys(sigs)

    def test_20_tools_tight_loop_suppressed(self):
        # All same tool name -> tight loop, should NOT trigger
        tools = [_tc("Read") for _ in range(25)]
        r = _make_round(tool_calls=tools)
        sigs = compute_round_signals(r, 1)
        assert "tool-burst" not in _signal_keys(sigs)

    def test_19_tools_no_signal(self):
        tools = [_tc(f"Tool{i}") for i in range(19)]
        r = _make_round(tool_calls=tools)
        sigs = compute_round_signals(r, 1)
        assert "tool-burst" not in _signal_keys(sigs)


class TestHighWriteSignal:
    def test_cache_write_300k(self):
        r = _make_round(usage={"cache_creation_input_tokens": 300_000})
        sigs = compute_round_signals(r, 1)
        assert "high-write" in _signal_keys(sigs)

    def test_cache_write_below_threshold(self):
        r = _make_round(usage={"cache_creation_input_tokens": 299_999})
        sigs = compute_round_signals(r, 1)
        assert "high-write" not in _signal_keys(sigs)


class TestLargeInputSignal:
    def test_large_input_meets_both_thresholds(self):
        # 200K input AND 50% of session
        r = _make_round(usage={
            "input_tokens": 200_000,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
        })
        sigs = compute_round_signals(r, 1, session_input_tokens=300_000)
        assert "large-input" in _signal_keys(sigs)

    def test_large_input_below_absolute_threshold(self):
        r = _make_round(usage={
            "input_tokens": 199_999,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
        })
        sigs = compute_round_signals(r, 1, session_input_tokens=300_000)
        assert "large-input" not in _signal_keys(sigs)

    def test_large_input_below_percentage_threshold(self):
        # 200K input but only 10% of session total
        r = _make_round(usage={
            "input_tokens": 200_000,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
        })
        sigs = compute_round_signals(r, 1, session_input_tokens=2_000_000)
        assert "large-input" not in _signal_keys(sigs)


# ── Removed signals must NOT appear ───────────────────────────────────


class TestRemovedSignals:
    """Verify that previously-existing low-value signals are no longer emitted."""

    REMOVED_KEYS = {"warm-up", "cache-hit", "low-output", "llm-burst"}

    def test_warm_up_not_emitted(self):
        # Old rule: first 3 rounds with no cache read -> "warm-up"
        r = _make_round(usage={
            "input_tokens": 5000,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
            "output_tokens": 200,
        })
        sigs = compute_round_signals(r, 1)
        assert "warm-up" not in _signal_keys(sigs)

    def test_cache_hit_not_emitted(self):
        # Old rule: cache_read > 50% of input -> "cache-hit"
        r = _make_round(usage={
            "input_tokens": 1000,
            "cache_read_input_tokens": 9000,
            "cache_creation_input_tokens": 0,
            "output_tokens": 200,
        })
        sigs = compute_round_signals(r, 1)
        assert "cache-hit" not in _signal_keys(sigs)

    def test_low_output_not_emitted(self):
        # Old rule: output < 100 with input > 10K -> "low-output"
        r = _make_round(usage={
            "input_tokens": 50000,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
            "output_tokens": 50,
        })
        sigs = compute_round_signals(r, 1)
        assert "low-output" not in _signal_keys(sigs)

    def test_llm_burst_not_emitted(self):
        # Old rule: llm_call_count > 10 -> "llm-burst"
        assistant = ChatMessage(role="assistant", content="", timestamp="", usage={})
        user = ChatMessage(role="user", content="test", timestamp="")
        r = ConversationRound(
            user_msg=user, assistant_msg=assistant, llm_call_count=15
        )
        sigs = compute_round_signals(r, 1)
        assert "llm-burst" not in _signal_keys(sigs)

    def test_old_low_threshold_high_write_not_emitted(self):
        # Old threshold was 10K; new threshold is 300K
        r = _make_round(usage={"cache_creation_input_tokens": 100_000})
        sigs = compute_round_signals(r, 1)
        assert "high-write" not in _signal_keys(sigs)

    def test_old_low_threshold_tool_burst_not_emitted(self):
        # Old threshold was > 5 tools; new threshold is >= 20
        tools = [_tc(f"Tool{i}") for i in range(6)]
        r = _make_round(tool_calls=tools)
        sigs = compute_round_signals(r, 1)
        assert "tool-burst" not in _signal_keys(sigs)


# ── Signal structure ──────────────────────────────────────────────────


class TestSignalStructure:
    def test_signal_has_required_fields(self):
        r = _make_round(tool_calls=[_tc("Bash", status="error", exit_code=1)])
        sigs = compute_round_signals(r, 1)
        for sig in sigs:
            assert "key" in sig
            assert "label" in sig
            assert "severity" in sig
            assert "reason" in sig
            assert sig["severity"] in ("critical", "warning")

    def test_empty_round_returns_empty_list(self):
        r = _make_round()
        sigs = compute_round_signals(r, 1)
        assert sigs == []
