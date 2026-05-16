"""Tests for Qoder token estimation in qoder.py.

Covers:
a. No usage -> each assistant message gets estimated usage.
b. Multi-turn: later assistant input_tokens > earlier (context accumulation).
c. Session summary tokens == per-message usage sum.
d. Real usage present -> no estimation, no overwrite.
e. Long tool_result/text does not crash; estimation stays fast.
"""

from __future__ import annotations

import json
import time

import pytest

from session_browser.sources.qoder import (
    _count_tokens,
    _estimate_tokens_from_events,
    _fill_estimates,
    _cap_text,
    _ESTIMATE_TEXT_CAP,
    _extract_messages,
    _assistant_records,
    _build_summary_from_events,
    _extract_tool_calls,
)


def _make_event(typ: str, message: dict, **extra) -> dict:
    """Helper to build a minimal Qoder event dict."""
    ev = {"type": typ, "message": message, "timestamp": "2025-01-01T00:00:00Z"}
    ev.update(extra)
    return ev


def _assistant_event(text: str = "", tool_use: dict | None = None, usage: dict | None = None, msg_id: str = "msg-1", timestamp: str = "") -> dict:
    """Build an assistant event with optional text, tool_use, and usage."""
    content = []
    if text:
        content.append({"type": "text", "text": text})
    if tool_use:
        content.append(tool_use)
    msg = {"id": msg_id, "content": content}
    if usage:
        msg["usage"] = usage
    return _make_event("assistant", msg, **({"timestamp": timestamp} if timestamp else {}))


def _user_event(text: str = "", content_override=None, **extra) -> dict:
    """Build a user event."""
    msg = {"content": content_override if content_override is not None else text}
    ev = _make_event("user", msg)
    ev.update(extra)
    return ev


# ─── Test: text cap ──────────────────────────────────────────────────────


class TestTextCap:
    def test_short_text_not_truncated(self):
        s = "hello world"
        assert _cap_text(s) == s

    def test_long_text_is_capped(self):
        # Create text that exceeds 128KB
        s = "a" * (_ESTIMATE_TEXT_CAP + 1000)
        capped = _cap_text(s)
        assert len(capped.encode("utf-8")) <= _ESTIMATE_TEXT_CAP

    def test_empty_string(self):
        assert _cap_text("") == ""
        assert _cap_text(None) == ""


class TestCountTokens:
    def test_basic_english(self):
        tok = _count_tokens("hello world")
        assert tok > 0

    def test_chinese_text(self):
        tok = _count_tokens("你好世界")
        assert tok > 0

    def test_empty_text(self):
        tok = _count_tokens("")
        assert tok == 1  # max(1, ...) via byte heuristic

    def test_long_text_is_fast(self):
        """Counting a very long string should not hang."""
        s = "x" * 1_000_000
        start = time.monotonic()
        tok = _count_tokens(s)
        elapsed = time.monotonic() - start
        assert elapsed < 1.0  # Should complete in well under 1 second
        assert tok > 0


# ─── Test: estimated usage when no real usage ────────────────────────────


class TestEstimatedUsage:
    def test_no_usage_generates_estimates(self):
        """When no assistant event has real usage, per-message estimates are generated."""
        events = [
            _user_event("hello"),
            _assistant_event(text="hi there", msg_id="msg-1"),
            _user_event("what is 2+2?"),
            _assistant_event(text="it's 4", msg_id="msg-2"),
        ]

        assistant_by_id = {rec["id"]: rec for rec in _assistant_records(events)}
        est_input = {}
        est_output = {}
        _fill_estimates(events, assistant_by_id, est_input, est_output)

        # Both messages should have estimates
        assert "msg-1" in est_input
        assert "msg-1" in est_output
        assert "msg-2" in est_input
        assert "msg-2" in est_output
        # All estimated values should be non-negative
        assert est_input["msg-1"] >= 0
        assert est_output["msg-1"] > 0
        assert est_input["msg-2"] >= 0
        assert est_output["msg-2"] > 0

    def test_context_accumulation(self):
        """Second turn input_tokens should be >= first turn input + first output."""
        events = [
            _user_event("hello"),
            _assistant_event(text="hi", msg_id="msg-1"),
            _user_event("next question"),
            _assistant_event(text="answer", msg_id="msg-2"),
        ]

        est_input = {}
        est_output = {}
        _fill_estimates(events, {}, est_input, est_output)

        # msg-2 input should be >= msg-1 input + msg-1 output + user("next question")
        second_input = est_input["msg-2"]
        first_total = est_input["msg-1"] + est_output["msg-1"]
        assert second_input >= first_total, (
            f"msg-2 input ({second_input}) should be >= msg-1 total ({first_total})"
        )

    def test_session_summary_matches_per_message_sum(self):
        """Session-level estimated tokens should equal sum of per-message estimates."""
        events = [
            _user_event("hello"),
            _assistant_event(text="response one", msg_id="msg-1"),
            _user_event("follow up"),
            _assistant_event(text="response two", msg_id="msg-2"),
        ]

        # Session-level estimate
        est_input, est_output, has_estimated = _estimate_tokens_from_events(events)
        assert has_estimated

        # Per-message estimates
        assistant_by_id = {rec["id"]: rec for rec in _assistant_records(events)}
        est_input_map = {}
        est_output_map = {}
        _fill_estimates(events, assistant_by_id, est_input_map, est_output_map)

        sum_input = sum(est_input_map.values())
        sum_output = sum(est_output_map.values())

        assert est_input == sum_input, (
            f"Session input {est_input} != sum of per-message {sum_input}"
        )
        assert est_output == sum_output, (
            f"Session output {est_output} != sum of per-message {sum_output}"
        )


# ─── Test: real usage is preserved ───────────────────────────────────────


class TestRealUsagePreserved:
    def test_real_usage_skips_estimation(self):
        """When an assistant event has real usage, estimation is skipped."""
        events = [
            _user_event("hello"),
            _assistant_event(
                text="hi",
                msg_id="msg-1",
                usage={"input_tokens": 100, "output_tokens": 50},
            ),
        ]

        est_input, est_output, has_estimated = _estimate_tokens_from_events(events)
        assert not has_estimated
        assert est_input == 0
        assert est_output == 0

    def test_extract_messages_uses_real_usage(self):
        """_extract_messages should use real usage, not estimates, when present."""
        events = [
            _user_event("hello"),
            _assistant_event(
                text="hi",
                msg_id="msg-1",
                usage={"input_tokens": 100, "output_tokens": 50},
            ),
        ]

        messages = _extract_messages(events)
        assistant_msgs = [m for m in messages if m.role == "assistant"]
        assert len(assistant_msgs) == 1
        msg = assistant_msgs[0]
        # Real usage should be present, not estimated
        assert msg.usage is not None
        assert msg.usage.get("input_tokens") == 100
        assert msg.usage.get("output_tokens") == 50
        assert msg.usage.get("estimated") is None  # No estimated flag for real usage


# ─── Test: long text handling ────────────────────────────────────────────


class TestLongTextHandling:
    def test_long_tool_result_no_crash(self):
        """A very long tool_result should not crash estimation."""
        long_text = "x" * 500_000
        events = [
            _user_event("hello"),
            _assistant_event(text="checking", msg_id="msg-1"),
            _user_event(""),  # user event with tool_result
        ]
        # Inject a tool_result into the user event message content
        events[2]["message"]["content"] = [
            {"type": "tool_result", "content": long_text}
        ]

        # Should not crash
        est_input, est_output, has_estimated = _estimate_tokens_from_events(events)
        assert has_estimated

    def test_long_assistant_text_no_crash(self):
        """A very long assistant text should not crash estimation."""
        long_text = "x" * 500_000
        events = [
            _user_event("write a long essay"),
            _assistant_event(text=long_text, msg_id="msg-1"),
        ]

        est_input, est_output, has_estimated = _estimate_tokens_from_events(events)
        assert has_estimated
        # Output should be capped, not the full 500K characters worth of tokens
        assert est_output < _count_tokens(long_text) + 10  # Should be close to capped count

    def test_estimation_is_fast_on_large_text(self):
        """Estimation should complete in well under 1 second for large events."""
        long_text = "x" * 1_000_000
        events = [
            _user_event("prompt"),
            _assistant_event(text=long_text, msg_id="msg-1"),
            _user_event("followup"),
            _assistant_event(text="short answer", msg_id="msg-2"),
        ]

        start = time.monotonic()
        est_input, est_output, has_estimated = _estimate_tokens_from_events(events)
        elapsed = time.monotonic() - start

        assert elapsed < 2.0, f"Estimation took {elapsed:.2f}s"
        assert has_estimated


# ─── Test: multi-fragment messages ───────────────────────────────────────


class TestMultiFragmentMessages:
    def test_fragments_merged_output(self):
        """Multiple assistant fragments with same msg_id should accumulate output tokens."""
        events = [
            _user_event("hello"),
            _assistant_event(text="part one", msg_id="msg-1"),
            _assistant_event(text=" part two", msg_id="msg-1"),
        ]

        est_input = {}
        est_output = {}
        _fill_estimates(events, {}, est_input, est_output)

        # Only one message key
        assert "msg-1" in est_input
        assert "msg-1" in est_output
        # Input should be set only once (from first fragment)
        assert est_input["msg-1"] >= 0
        # Output should be sum of both fragments
        combined = "part one part two"
        expected_output = _count_tokens(combined)
        assert est_output["msg-1"] == _count_tokens("part one") + _count_tokens(" part two")

    def test_different_message_ids(self):
        """Different msg_ids should get separate estimates."""
        events = [
            _user_event("hello"),
            _assistant_event(text="response A", msg_id="msg-A"),
            _user_event("follow up"),
            _assistant_event(text="response B", msg_id="msg-B"),
        ]

        est_input = {}
        est_output = {}
        _fill_estimates(events, {}, est_input, est_output)

        assert "msg-A" in est_input
        assert "msg-B" in est_input
        assert "msg-A" in est_output
        assert "msg-B" in est_output
        assert len(est_input) == 2
        assert len(est_output) == 2


# ─── Test: _extract_messages injects estimated usage ─────────────────────


class TestExtractMessagesEstimatedUsage:
    def test_estimated_usage_injected(self):
        """When no real usage, _extract_messages should inject estimated usage dicts."""
        events = [
            _user_event("hello"),
            _assistant_event(text="hi", msg_id="msg-1"),
        ]

        messages = _extract_messages(events)
        assistant_msgs = [m for m in messages if m.role == "assistant"]
        assert len(assistant_msgs) == 1
        msg = assistant_msgs[0]

        assert msg.usage is not None
        assert "input_tokens" in msg.usage
        assert "output_tokens" in msg.usage
        assert msg.usage.get("estimated") is True
        assert msg.usage.get("estimation_method") == "qoder-fast-bytes-v1"
        assert msg.usage.get("cache_read_input_tokens") == 0
        assert msg.usage.get("cache_creation_input_tokens") == 0

    def test_multi_turn_estimated_usage(self):
        """Multiple turns should all have estimated usage with increasing input tokens."""
        events = [
            _user_event("hello"),
            _assistant_event(text="hi", msg_id="msg-1"),
            _user_event("tell me more"),
            _assistant_event(text="sure", msg_id="msg-2"),
        ]

        messages = _extract_messages(events)
        assistant_msgs = [m for m in messages if m.role == "assistant"]
        assert len(assistant_msgs) == 2

        # Both should have estimated usage
        for msg in assistant_msgs:
            assert msg.usage is not None
            assert msg.usage.get("estimated") is True

        # Second message input should be >= first message total
        first_input = assistant_msgs[0].usage["input_tokens"]
        first_output = assistant_msgs[0].usage["output_tokens"]
        second_input = assistant_msgs[1].usage["input_tokens"]
        assert second_input >= first_input + first_output


# ─── Test: Qoder tool execution time ─────────────────────────────────────


class TestToolExecutionTime:
    def test_non_overlapping_tools(self):
        """Two sequential tool calls: tool_execution_seconds should be sum of durations."""
        events = [
            _user_event("hello", timestamp="2025-01-01T00:00:00.000Z"),
            _assistant_event(
                text="using tools", msg_id="msg-1",
                tool_use={"type": "tool_use", "id": "tu-1", "name": "Read"},
                timestamp="2025-01-01T00:00:01.000Z",
            ),
            _user_event("", content_override=[
                {"type": "tool_result", "tool_use_id": "tu-1", "content": "file content"}
            ], timestamp="2025-01-01T00:00:11.000Z"),
            _assistant_event(
                text="using tools", msg_id="msg-2",
                tool_use={"type": "tool_use", "id": "tu-2", "name": "Bash"},
                timestamp="2025-01-01T00:00:12.000Z",
            ),
            _user_event("", content_override=[
                {"type": "tool_result", "tool_use_id": "tu-2", "content": "output"}
            ], timestamp="2025-01-01T00:00:22.000Z"),
        ]

        summary = _build_summary_from_events(events, "sess-1", "/tmp")
        # Each tool ran 10s, sequential -> 20s total
        assert summary.tool_execution_seconds == 20.0, (
            f"Expected 20s but got {summary.tool_execution_seconds}"
        )

    def test_overlapping_tools_merged(self):
        """Two overlapping tool calls: tool_execution_seconds should be merged wall-clock time."""
        events = [
            _user_event("hello", timestamp="2025-01-01T00:00:00.000Z"),
            _assistant_event(
                text="using tools", msg_id="msg-1",
                tool_use={"type": "tool_use", "id": "tu-1", "name": "Read"},
                timestamp="2025-01-01T00:00:01.000Z",
            ),
            _assistant_event(
                text="using tools", msg_id="msg-1",
                tool_use={"type": "tool_use", "id": "tu-2", "name": "Bash"},
                timestamp="2025-01-01T00:00:03.000Z",
            ),
            _user_event("", content_override=[
                {"type": "tool_result", "tool_use_id": "tu-1", "content": "content A"}
            ], timestamp="2025-01-01T00:00:11.000Z"),
            _user_event("", content_override=[
                {"type": "tool_result", "tool_use_id": "tu-2", "content": "content B"}
            ], timestamp="2025-01-01T00:00:08.000Z"),
        ]

        summary = _build_summary_from_events(events, "sess-1", "/tmp")
        # tu-1: 1s -> 11s (10s), tu-2: 3s -> 8s (5s)
        # Overlap: [1,11] and [3,8] -> merged = [1,11] = 10s (not 15s)
        assert summary.tool_execution_seconds == 10.0, (
            f"Expected 10s (merged) but got {summary.tool_execution_seconds}"
        )

    def test_no_tool_results_gives_zero(self):
        """Assistant with tool_use but no tool_result should not fabricate intervals."""
        events = [
            _user_event("hello", timestamp="2025-01-01T00:00:00.000Z"),
            _assistant_event(
                text="using tools", msg_id="msg-1",
                tool_use={"type": "tool_use", "id": "tu-1", "name": "Read"},
                timestamp="2025-01-01T00:00:01.000Z",
            ),
        ]

        summary = _build_summary_from_events(events, "sess-1", "/tmp")
        assert summary.tool_execution_seconds == 0.0

    def test_tool_call_duration_ms(self):
        """ToolCall.duration_ms should be computed from tool_use/tool_result timestamps."""
        events = [
            _user_event("hello", timestamp="2025-01-01T00:00:00.000Z"),
            _assistant_event(
                text="using tool", msg_id="msg-1",
                tool_use={"type": "tool_use", "id": "tu-1", "name": "Bash"},
                timestamp="2025-01-01T00:00:01.000Z",
            ),
            _user_event("", content_override=[
                {"type": "tool_result", "tool_use_id": "tu-1", "content": "output"}
            ], timestamp="2025-01-01T00:00:11.000Z"),
        ]

        messages = _extract_messages(events)
        tool_calls = _extract_tool_calls(events, messages)
        assert len(tool_calls) == 1
        assert tool_calls[0].duration_ms == 10000, (
            f"Expected 10000ms but got {tool_calls[0].duration_ms}"
        )
