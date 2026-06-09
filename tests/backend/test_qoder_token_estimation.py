"""测试 qoder.py 中的 Qoder token 估算。

覆盖范围：
a. 无用量 -> 每条 assistant 消息获得估算用量。
b. 多轮对话：后续 assistant input_tokens > 前面（上下文累积）。
c. 会话摘要 token == 逐消息用量之和。
d. 存在真实用量 -> 不估算，不覆盖。
e. 长 tool_result/text 不崩溃；估算保持快速。
"""

from __future__ import annotations

import pytest
import json
import time

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
    """构建最小 Qoder 事件字典的辅助函数。"""
    ev = {"type": typ, "message": message, "timestamp": "2025-01-01T00:00:00Z"}
    ev.update(extra)
    return ev


def _assistant_event(text: str = "", tool_use: dict | None = None, usage: dict | None = None, msg_id: str = "msg-1", timestamp: str = "") -> dict:
    """构建带可选 text、tool_use 和 usage 的 assistant 事件。"""
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
    """构建 user 事件。"""
    msg = {"content": content_override if content_override is not None else text}
    ev = _make_event("user", msg)
    ev.update(extra)
    return ev


# ─── 测试：文本截断 ──────────────────────────────────────────────────────


class TestTextCap:
    @pytest.mark.contract_case("DATA-SOURCE-010", "DATA-SOURCE-013")
    def test_short_text_not_truncated(self):
        s = "hello world"
        assert _cap_text(s) == s

    @pytest.mark.contract_case("DATA-SOURCE-010", "DATA-SOURCE-013")
    def test_long_text_is_capped(self):
        # 创建超过 128KB 的文本
        s = "a" * (_ESTIMATE_TEXT_CAP + 1000)
        capped = _cap_text(s)
        assert len(capped.encode("utf-8")) <= _ESTIMATE_TEXT_CAP

    @pytest.mark.contract_case("DATA-SOURCE-010", "DATA-SOURCE-013")
    def test_empty_string(self):
        assert _cap_text("") == ""
        assert _cap_text(None) == ""


class TestCountTokens:
    @pytest.mark.contract_case("DATA-SOURCE-010", "DATA-SOURCE-013")
    def test_basic_english(self):
        tok = _count_tokens("hello world")
        assert tok > 0

    @pytest.mark.contract_case("DATA-SOURCE-010", "DATA-SOURCE-013")
    def test_chinese_text(self):
        tok = _count_tokens("你好世界")
        assert tok > 0

    @pytest.mark.contract_case("DATA-SOURCE-010", "DATA-SOURCE-013")
    def test_empty_text(self):
        tok = _count_tokens("")
        assert tok == 1  # max(1, ...) 通过字节启发式

    @pytest.mark.contract_case("DATA-SOURCE-010", "DATA-SOURCE-013")
    def test_long_text_is_fast(self):
        """统计极长字符串不应卡住。"""
        s = "x" * 1_000_000
        start = time.monotonic()
        tok = _count_tokens(s)
        elapsed = time.monotonic() - start
        assert elapsed < 1.0  # 应在远低于 1 秒内完成
        assert tok > 0


# ─── 测试：无真实用量时的估算 ────────────────────────────────────────────


class TestEstimatedUsage:
    @pytest.mark.contract_case("DATA-SOURCE-010", "DATA-SOURCE-013")
    def test_no_usage_generates_estimates(self):
        """无真实用量的 assistant 事件应生成逐消息估算。"""
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

        # 两条消息都应获得估算
        assert "msg-1" in est_input
        assert "msg-1" in est_output
        assert "msg-2" in est_input
        assert "msg-2" in est_output
        # 所有估算值应为非负数
        assert est_input["msg-1"] >= 0
        assert est_output["msg-1"] > 0
        assert est_input["msg-2"] >= 0
        assert est_output["msg-2"] > 0

    @pytest.mark.contract_case("DATA-SOURCE-010", "DATA-SOURCE-013")
    def test_context_accumulation(self):
        """第二轮 input_tokens 应 >= 第一轮 input + 第一轮 output。"""
        events = [
            _user_event("hello"),
            _assistant_event(text="hi", msg_id="msg-1"),
            _user_event("next question"),
            _assistant_event(text="answer", msg_id="msg-2"),
        ]

        est_input = {}
        est_output = {}
        _fill_estimates(events, {}, est_input, est_output)

        # msg-2 的 input 应 >= msg-1 的 input + msg-1 的 output + user("next question")
        second_input = est_input["msg-2"]
        first_total = est_input["msg-1"] + est_output["msg-1"]
        assert second_input >= first_total, (
            f"msg-2 的 input ({second_input}) 应 >= msg-1 的总计 ({first_total})"
        )

    @pytest.mark.contract_case("DATA-SOURCE-010", "DATA-SOURCE-013")
    def test_session_summary_matches_per_message_sum(self):
        """会话级估算 token 应等于逐消息估算之和。"""
        events = [
            _user_event("hello"),
            _assistant_event(text="response one", msg_id="msg-1"),
            _user_event("follow up"),
            _assistant_event(text="response two", msg_id="msg-2"),
        ]

        # 会话级估算
        est_input, est_output, has_estimated = _estimate_tokens_from_events(events)
        assert has_estimated

        # 逐消息估算
        assistant_by_id = {rec["id"]: rec for rec in _assistant_records(events)}
        est_input_map = {}
        est_output_map = {}
        _fill_estimates(events, assistant_by_id, est_input_map, est_output_map)

        sum_input = sum(est_input_map.values())
        sum_output = sum(est_output_map.values())

        assert est_input == sum_input, (
            f"会话 input {est_input} != 逐消息之和 {sum_input}"
        )
        assert est_output == sum_output, (
            f"会话 output {est_output} != 逐消息之和 {sum_output}"
        )


# ─── 测试：真实用量保留 ────────────────────────────────────────────────


class TestRealUsagePreserved:
    @pytest.mark.contract_case("DATA-SOURCE-010", "DATA-SOURCE-013")
    def test_real_usage_skips_estimation(self):
        """assistant 事件有真实用量时应跳过估算。"""
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

    @pytest.mark.contract_case("DATA-SOURCE-010", "DATA-SOURCE-013")
    def test_extract_messages_uses_real_usage(self):
        """_extract_messages 有真实用量时应使用真实用量而非估算。"""
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
        # 真实用量应存在，而非估算
        assert msg.usage is not None
        assert msg.usage.get("input_tokens") == 100
        assert msg.usage.get("output_tokens") == 50
        assert msg.usage.get("estimated") is None  # 真实用量不应设置 estimated 标志

    @pytest.mark.contract_case("DATA-SOURCE-010", "DATA-SOURCE-013")
    def test_qoder_provider_usage_normalized_to_canonical_buckets(self):
        """Qoder provider input_tokens 应保留为 Fresh request input size。

        关键：provider-reported cache_creation_input_tokens=0 不能被下一条
        cache_read 差值覆盖。推断值只进入 qoder_cache_write_inferred_tokens。
        """
        events = [
            _user_event("hello"),
            _assistant_event(
                text="first",
                msg_id="msg-1",
                usage={
                    "input_tokens": 1000,
                    "cache_read_input_tokens": 0,
                    "cache_creation_input_tokens": 0,
                    "output_tokens": 10,
                },
            ),
            _user_event("next"),
            _assistant_event(
                text="second",
                msg_id="msg-2",
                usage={
                    "input_tokens": 1200,
                    "cache_read_input_tokens": 990,
                    "cache_creation_input_tokens": 0,
                    "output_tokens": 20,
                },
            ),
        ]

        records = _assistant_records(events)
        # Call 1: Fresh 保留 provider request input，cache_write 保持 provider-reported 0
        assert records[0]["usage"]["input_tokens"] == 1000
        assert records[0]["usage"]["cache_creation_input_tokens"] == 0  # 不被推断覆盖
        assert records[0]["usage"]["qoder_input_tokens_total"] == 1000
        # 推断值进入单独字段
        assert records[0]["usage"].get("qoder_cache_write_inferred_tokens") == 990
        assert records[0]["usage"].get("qoder_cache_write_inferred") is True
        # Call 2: Fresh 仍为 request input，不扣减 cache read
        assert records[1]["usage"]["input_tokens"] == 1200
        assert records[1]["usage"]["cache_read_input_tokens"] == 990

        summary = _build_summary_from_events(events, "sess-1", "/tmp")
        # input_tokens 是各 call Fresh 之和: 1000 + 1200 = 2200
        assert summary.input_tokens == 2200
        assert summary.cached_input_tokens == 990
        # cached_output_tokens 是 cache_creation_input_tokens 之和: 0 + 0 = 0
        assert summary.cached_output_tokens == 0
        assert summary.output_tokens == 30
        assert summary.total_tokens == 3220

    @pytest.mark.contract_case("DATA-SOURCE-010", "DATA-SOURCE-013")
    def test_extract_messages_uses_normalized_qoder_provider_usage(self):
        events = [
            _user_event("hello"),
            _assistant_event(
                text="hi",
                msg_id="msg-1",
                usage={
                    "input_tokens": 1000,
                    "cache_read_input_tokens": 900,
                    "cache_creation_input_tokens": 50,
                    "output_tokens": 25,
                },
            ),
        ]

        messages = _extract_messages(events)
        assistant_msgs = [m for m in messages if m.role == "assistant"]
        assert len(assistant_msgs) == 1
        usage = assistant_msgs[0].usage
        assert usage["input_tokens"] == 1000
        assert usage["cache_read_input_tokens"] == 900
        assert usage["cache_creation_input_tokens"] == 50
        assert usage["qoder_input_tokens_total"] == 1000

    @pytest.mark.contract_case("DATA-SOURCE-010", "DATA-SOURCE-013")
    def test_qoder_same_message_fragments_use_request_input_and_accounting_snapshot(self):
        events = [
            _user_event("hello"),
            _assistant_event(
                text="thinking",
                msg_id="msg-1",
                usage={"input_tokens": 5000, "output_tokens": 0},
            ),
            _assistant_event(
                text="tool",
                msg_id="msg-1",
                usage={
                    "input_tokens": 6,
                    "cache_read_input_tokens": 1100,
                    "cache_creation_input_tokens": 250,
                    "output_tokens": 70,
                },
            ),
        ]

        records = _assistant_records(events)

        assert len(records) == 1
        assert records[0]["usage"]["input_tokens"] == 5000
        assert records[0]["usage"]["cache_read_input_tokens"] == 1100
        assert records[0]["usage"]["cache_creation_input_tokens"] == 250
        assert records[0]["usage"]["output_tokens"] == 70


# ─── 测试：长文本处理 ────────────────────────────────────────────────


class TestLongTextHandling:
    @pytest.mark.contract_case("DATA-SOURCE-010", "DATA-SOURCE-013")
    def test_long_tool_result_no_crash(self):
        """超长 tool_result 不应导致估算崩溃。"""
        long_text = "x" * 500_000
        events = [
            _user_event("hello"),
            _assistant_event(text="checking", msg_id="msg-1"),
            _user_event(""),  # 带 tool_result 的 user 事件
        ]
        # 向 user 事件注入 tool_result
        events[2]["message"]["content"] = [
            {"type": "tool_result", "content": long_text}
        ]

        # 不应崩溃
        est_input, est_output, has_estimated = _estimate_tokens_from_events(events)
        assert has_estimated

    @pytest.mark.contract_case("DATA-SOURCE-010", "DATA-SOURCE-013")
    def test_long_assistant_text_no_crash(self):
        """超长 assistant 文本不应导致估算崩溃。"""
        long_text = "x" * 500_000
        events = [
            _user_event("write a long essay"),
            _assistant_event(text=long_text, msg_id="msg-1"),
        ]

        est_input, est_output, has_estimated = _estimate_tokens_from_events(events)
        assert has_estimated
        # output 应被截断，而非完整 500K 字符对应的 token 数
        assert est_output < _count_tokens(long_text) + 10  # 应接近截断后的计数

    @pytest.mark.contract_case("DATA-SOURCE-010", "DATA-SOURCE-013")
    def test_estimation_is_fast_on_large_text(self):
        """大事件估算应在远低于 1 秒内完成。"""
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


# ─── 测试：多片段消息 ────────────────────────────────────────────────


class TestMultiFragmentMessages:
    @pytest.mark.contract_case("DATA-SOURCE-010", "DATA-SOURCE-013")
    def test_fragments_merged_output(self):
        """相同 msg_id 的多个 assistant 片段应累加 output tokens。"""
        events = [
            _user_event("hello"),
            _assistant_event(text="part one", msg_id="msg-1"),
            _assistant_event(text=" part two", msg_id="msg-1"),
        ]

        est_input = {}
        est_output = {}
        _fill_estimates(events, {}, est_input, est_output)

        # 只有一个消息键
        assert "msg-1" in est_input
        assert "msg-1" in est_output
        # input 只设置一次（来自第一个片段）
        assert est_input["msg-1"] >= 0
        # output 应为两个片段之和
        combined = "part one part two"
        expected_output = _count_tokens(combined)
        assert est_output["msg-1"] == _count_tokens("part one") + _count_tokens(" part two")

    @pytest.mark.contract_case("DATA-SOURCE-010", "DATA-SOURCE-013")
    def test_different_message_ids(self):
        """不同 msg_id 应得到独立估算。"""
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


# ─── 测试：_extract_messages 注入估算用量 ─────────────────────────────


class TestExtractMessagesEstimatedUsage:
    @pytest.mark.contract_case("DATA-SOURCE-010", "DATA-SOURCE-013")
    def test_estimated_usage_injected(self):
        """无真实用量时 _extract_messages 应注入估算用量字典。"""
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

    @pytest.mark.contract_case("DATA-SOURCE-010", "DATA-SOURCE-013")
    def test_multi_turn_estimated_usage(self):
        """多轮对话都应具有估算用量，且 input tokens 递增。"""
        events = [
            _user_event("hello"),
            _assistant_event(text="hi", msg_id="msg-1"),
            _user_event("tell me more"),
            _assistant_event(text="sure", msg_id="msg-2"),
        ]

        messages = _extract_messages(events)
        assistant_msgs = [m for m in messages if m.role == "assistant"]
        assert len(assistant_msgs) == 2

        # 都应具有估算用量
        for msg in assistant_msgs:
            assert msg.usage is not None
            assert msg.usage.get("estimated") is True

        # 第二条消息的 input 应 >= 第一条消息的总计
        first_input = assistant_msgs[0].usage["input_tokens"]
        first_output = assistant_msgs[0].usage["output_tokens"]
        second_input = assistant_msgs[1].usage["input_tokens"]
        assert second_input >= first_input + first_output


# ─── 测试：Qoder 工具执行时间 ─────────────────────────────────────────────


class TestToolExecutionTime:
    @pytest.mark.contract_case("DATA-SOURCE-010", "DATA-SOURCE-013")
    def test_non_overlapping_tools(self):
        """两个顺序工具调用：tool_execution_seconds 应为时长之和。"""
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
        # 每个工具运行 10s，顺序执行 -> 总计 20s
        assert summary.tool_execution_seconds == 20.0, (
            f"期望 20s 但得到 {summary.tool_execution_seconds}"
        )

    @pytest.mark.contract_case("DATA-SOURCE-010", "DATA-SOURCE-013")
    def test_overlapping_tools_merged(self):
        """两个重叠工具调用：tool_execution_seconds 应为合并后的墙钟时间。"""
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
        # 重叠：[1,11] 和 [3,8] -> 合并 = [1,11] = 10s（非 15s）
        assert summary.tool_execution_seconds == 10.0, (
            f"期望 10s（合并后）但得到 {summary.tool_execution_seconds}"
        )

    @pytest.mark.contract_case("DATA-SOURCE-010", "DATA-SOURCE-013")
    def test_no_tool_results_gives_zero(self):
        """有 tool_use 但无 tool_result 时不应捏造时间区间。"""
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

    @pytest.mark.contract_case("DATA-SOURCE-010", "DATA-SOURCE-013")
    def test_tool_call_duration_ms(self):
        """ToolCall.duration_ms 应从 tool_use/tool_result 时间戳计算。"""
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
            f"期望 10000ms 但得到 {tool_calls[0].duration_ms}"
        )


# ─── 测试：Qoder cache 值绝不捏造 ───────────────────────────────────


class TestCacheNoFabrication:
    """Qoder 会话只有 fresh input 和 output tokens——无 cache
    read/write。解析器绝不能捏造 cache 值来满足 UI 需求。

    参见任务 T057。
    """

    @pytest.mark.contract_case("DATA-SOURCE-010", "DATA-SOURCE-013")
    def test_summary_cache_zero_when_estimated(self):
        """token 为估算时，会话摘要 cache_read/output 必须为 0。"""
        events = [
            _user_event("hello"),
            _assistant_event(text="hi", msg_id="msg-1"),
            _user_event("what is 2+2?"),
            _assistant_event(text="it's 4", msg_id="msg-2"),
        ]

        summary = _build_summary_from_events(events, "sess-1", "/tmp")

        assert summary.cached_input_tokens == 0, (
            f"cached_input_tokens 应为 0，实际为 {summary.cached_input_tokens}"
        )
        assert summary.cached_output_tokens == 0, (
            f"cached_output_tokens 应为 0，实际为 {summary.cached_output_tokens}"
        )
        # token 仍应被估算（非零）
        assert summary.input_tokens > 0
        assert summary.output_tokens > 0

    @pytest.mark.contract_case("DATA-SOURCE-010", "DATA-SOURCE-013")
    def test_summary_cache_zero_when_real_usage_no_cache(self):
        """即使有真实用量，若来源无 cache 字段，摘要 cache 仍为 0。"""
        events = [
            _user_event("hello"),
            _assistant_event(
                text="hi",
                msg_id="msg-1",
                usage={"input_tokens": 100, "output_tokens": 50},
            ),
        ]

        summary = _build_summary_from_events(events, "sess-1", "/tmp")

        assert summary.cached_input_tokens == 0
        assert summary.cached_output_tokens == 0
        assert summary.input_tokens == 100
        assert summary.output_tokens == 50

    @pytest.mark.contract_case("DATA-SOURCE-010", "DATA-SOURCE-013")
    def test_per_message_cache_zero_when_estimated(self):
        """_extract_messages 注入的逐消息用量字典 cache 必须为 0。"""
        events = [
            _user_event("hello"),
            _assistant_event(text="hi", msg_id="msg-1"),
            _user_event("tell me more"),
            _assistant_event(text="sure", msg_id="msg-2"),
        ]

        messages = _extract_messages(events)
        assistant_msgs = [m for m in messages if m.role == "assistant"]

        for msg in assistant_msgs:
            assert msg.usage is not None
            assert msg.usage.get("cache_read_input_tokens") == 0, (
                f"cache_read should be 0 for estimated message {msg.llm_call_id}"
            )
            assert msg.usage.get("cache_creation_input_tokens") == 0, (
                f"cache_write should be 0 for estimated message {msg.llm_call_id}"
            )
