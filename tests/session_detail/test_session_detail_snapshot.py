"""Session detail snapshot 测试。

端到端测试，调用 presenter 从 fixture 数据生成完整的 session detail
视图模型，然后将关键指标与预期 JSON snapshot 进行比较。

覆盖范围:
- Round 数量、token 总计、subagent 数量
- Tool 调用次数、失败 tool 次数、tool 名称多样性
- LLM 调用次数（main vs subagent）
- Round 级信号
- Session 异常检测

snapshot fixture 位于 tests/fixtures/session_detail/*.expected.json。
运行方式: pytest tests/session_detail/test_session_detail_snapshot.py -v
"""

from __future__ import annotations

import pytest
import json
import os
import sys
from pathlib import Path

SB_ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURES_DIR = SB_ROOT / "tests" / "fixtures" / "session_detail"
HIFFI_FIXTURE_DIR = SB_ROOT / "tests" / "fixtures" / "session_hifi_fixture"


def _set_fixture_env():
    """将 CLAUDE_DATA_DIR 指向 hifi fixture 并重新加载配置。"""
    import importlib

    old_data_dir = os.environ.get("CLAUDE_DATA_DIR", "")
    os.environ["CLAUDE_DATA_DIR"] = str(HIFFI_FIXTURE_DIR)

    # 重新加载配置以读取 CLAUDE_DATA_DIR
    if "session_browser.config" in sys.modules:
        importlib.reload(sys.modules["session_browser.config"])
    # 清除 source 模块以强制重新扫描 fixture
    for _mod in list(sys.modules):
        if _mod.startswith("session_browser.sources"):
            del sys.modules[_mod]

    return old_data_dir


def _restore_env(old_data_dir: str):
    if old_data_dir:
        os.environ["CLAUDE_DATA_DIR"] = old_data_dir
    else:
        os.environ.pop("CLAUDE_DATA_DIR", None)


# 将 src 添加到路径
sys.path.insert(0, str(SB_ROOT / "src"))


def _build_view_model():
    """解析 fixture，构建 presenter 视图模型，返回结构化 snapshot 数据。"""
    old_data_dir = _set_fixture_env()
    try:
        from session_browser.sources.claude import parse_session_detail
        from session_browser.web.presenters.session_detail import (
            build_rounds,
            build_llm_calls,
            assign_interactions_to_rounds,
        )
        from session_browser.web.routes import compute_round_signals
        from session_browser.index.metrics import compute_derived_metrics
        from session_browser.index.anomalies import detect_session_anomalies

        summary, messages, tool_calls, subagent_runs = parse_session_detail(
            "test-hifi-project", "hifi-viz-session-001"
        )
        assert summary is not None, "parse_session_detail returned None summary"

        agent = "claude_code"

        # 简单 md_filter（snapshot 不做实际 markdown 渲染）
        def md_filter(text: str) -> str:
            return text

        rounds = build_rounds(
            messages,
            tool_calls,
            summary.input_tokens,
            summary.output_tokens,
            summary.cached_input_tokens,
            summary.cached_output_tokens,
            agent,
            md_filter=md_filter,
        )

        llm_calls = build_llm_calls(messages, tool_calls, rounds, subagent_runs)
        assign_interactions_to_rounds(rounds, llm_calls, tool_calls, subagent_runs)

        for r in rounds:
            r.compute_preview()

        # ── 构建 snapshot 字典 ──────────────────────────────────────

        # 摘要
        total_tokens = (
            summary.input_tokens
            + summary.output_tokens
            + summary.cached_input_tokens
            + summary.cached_output_tokens
        )

        # 消息
        assistant_msgs = [m for m in messages if m.role == "assistant"]
        assistant_with_content = [m for m in assistant_msgs if m.content]
        assistant_with_llm_call_id = [m for m in assistant_msgs if m.llm_call_id]

        # Tool 调用
        tool_names = sorted(set(tc.name for tc in tool_calls))
        failed_tools = sorted(set(tc.name for tc in tool_calls if tc.is_failed))

        # Subagent 运行
        subagent_run_details = []
        for run in subagent_runs:
            s = run["summary"]
            sub_msgs = run["messages"]
            sub_assistant = [m for m in sub_msgs if m.role == "assistant" and m.llm_call_id]
            sub_input = sum((m.usage or {}).get("input_tokens", 0) for m in sub_assistant)
            sub_output = sum((m.usage or {}).get("output_tokens", 0) for m in sub_assistant)
            subagent_run_details.append({
                "agent_id": s["agent_id"],
                "message_count": len(sub_msgs),
                "assistant_turn_count": len(sub_assistant),
                "assistant_turn_llm_call_ids": [m.llm_call_id for m in sub_assistant],
                "total_input_tokens": sub_input,
                "total_output_tokens": sub_output,
            })

        # 轮次
        round_details = []
        for i, r in enumerate(rounds):
            signals = compute_round_signals(r, i + 1, summary.input_tokens)
            round_details.append({
                "index": i,
                "tool_count": len(r.tool_calls),
                "total_tokens": r.total_tokens,
                "llm_call_count": r.llm_call_count,
                "llm_error_count": r.llm_error_count,
                "interaction_count": len(r.interactions),
                "signal_count": len(signals),
            })

        # LLM 调用
        main_calls = [c for c in llm_calls if c.scope == "main"]
        sub_calls = [c for c in llm_calls if c.scope == "subagent"]

        # 异常
        session_data = compute_derived_metrics(summary.to_dict())
        sa = detect_session_anomalies(session_data)

        # Round 信号
        signals_by_round = {}
        total_signal_count = 0
        for i, r in enumerate(rounds):
            signals = compute_round_signals(r, i + 1, summary.input_tokens)
            total_signal_count += len(signals)
            if signals:
                signals_by_round[str(i + 1)] = [
                    {"key": s["key"], "severity": s["severity"]} for s in signals
                ]

        snapshot = {
            "fixture_id": "hifi-viz-session-001",
            "agent": summary.agent,
            "session_id": summary.session_id,
            "project_key": summary.project_key,
            "summary": {
                "title": summary.title,
                "model": summary.model,
                "input_tokens": summary.input_tokens,
                "output_tokens": summary.output_tokens,
                "cached_input_tokens": summary.cached_input_tokens,
                "cached_output_tokens": summary.cached_output_tokens,
                "total_tokens": total_tokens,
                "user_message_count": summary.user_message_count,
                "assistant_message_count": summary.assistant_message_count,
                "tool_call_count": summary.tool_call_count,
                "failed_tool_count": summary.failed_tool_count,
                "duration_seconds": summary.duration_seconds,
            },
            "messages": {
                "total_count": len(messages),
                "assistant_count": len(assistant_msgs),
                "assistant_with_content": len(assistant_with_content),
                "assistant_with_llm_call_id": len(assistant_with_llm_call_id),
            },
            "tool_calls": {
                "total_count": len(tool_calls),
                "unique_tool_names": tool_names,
                "failed_count": len(failed_tools),
                "failed_tools": failed_tools,
                "scope_main_count": len([tc for tc in tool_calls if tc.scope == "main"]),
                "scope_subagent_count": len([tc for tc in tool_calls if tc.scope == "subagent"]),
            },
            "subagent_runs": {
                "count": len(subagent_runs),
                "runs": subagent_run_details,
            },
            "rounds": {
                "count": len(rounds),
                "rounds": round_details,
            },
            "llm_calls": {
                "total_count": len(llm_calls),
                "main_count": len(main_calls),
                "subagent_count": len(sub_calls),
                "aggregate_input_tokens": sum(c.input_tokens for c in llm_calls),
                "aggregate_output_tokens": sum(c.output_tokens for c in llm_calls),
                "aggregate_cache_read_tokens": sum(c.cache_read_tokens for c in llm_calls),
                "aggregate_cache_write_tokens": sum(c.cache_write_tokens for c in llm_calls),
            },
            "anomalies": {
                "session_anomaly_count": len(sa.anomalies),
                "session_anomaly_types": sorted(
                    set(a.type.value if hasattr(a.type, "value") else str(a.type) for a in sa.anomalies)
                ),
            },
            "round_signals": {
                "total_signal_count": total_signal_count,
                "signals_by_round": signals_by_round,
            },
        }

        return snapshot

    finally:
        _restore_env(old_data_dir)


def _load_expected():
    """加载预期的 snapshot JSON。"""
    expected_path = FIXTURES_DIR / "hifi-viz-session-001.expected.json"
    with open(expected_path, "r", encoding="utf-8") as fh:
        return json.load(fh)


class TestSessionDetailSnapshot:
    """Session detail 视图模型的端到端 snapshot 测试。"""

    @pytest.fixture(autouse=True)
    def snapshot(self):
        """构建视图模型，每个测试类执行一次。"""
        return _build_view_model()

    # ── 摘要 ────────────────────────────────────────────────────

    @pytest.mark.contract_case("UI-SD-015")
    def test_summary_identity(self, snapshot):
        """Agent、session_id、project_key 必须与预期值匹配。"""
        expected = _load_expected()
        assert snapshot["agent"] == expected["agent"]
        assert snapshot["session_id"] == expected["session_id"]
        assert snapshot["project_key"] == expected["project_key"]

    @pytest.mark.contract_case("UI-SD-015")
    def test_summary_title_and_model(self, snapshot):
        """Title 和 model 必须与预期值匹配。"""
        expected = _load_expected()
        assert snapshot["summary"]["title"] == expected["summary"]["title"]
        assert snapshot["summary"]["model"] == expected["summary"]["model"]

    # ── Token totals ──────────────────────────────────────────────

    @pytest.mark.contract_case("UI-SD-015")
    def test_token_totals(self, snapshot):
        """所有 token 类别总计必须与预期值匹配。"""
        expected = _load_expected()
        for key in (
            "input_tokens", "output_tokens",
            "cached_input_tokens", "cached_output_tokens", "total_tokens",
        ):
            assert snapshot["summary"][key] == expected["summary"][key], \
                f"Token '{key}' mismatch: {snapshot['summary'][key]} != {expected['summary'][key]}"

    @pytest.mark.contract_case("UI-SD-015")
    def test_llm_call_token_aggregates(self, snapshot):
        """所有 LLM 调用的聚合 token 计数必须与预期值匹配。"""
        expected = _load_expected()
        for key in (
            "aggregate_input_tokens", "aggregate_output_tokens",
            "aggregate_cache_read_tokens", "aggregate_cache_write_tokens",
        ):
            assert snapshot["llm_calls"][key] == expected["llm_calls"][key], \
                f"LLM call token '{key}' mismatch"

    # ── Message counts ────────────────────────────────────────────

    @pytest.mark.contract_case("UI-SD-015")
    def test_message_counts(self, snapshot):
        """消息计数必须与预期值匹配。"""
        expected = _load_expected()
        for key in ("total_count", "assistant_count", "assistant_with_content", "assistant_with_llm_call_id"):
            assert snapshot["messages"][key] == expected["messages"][key], \
                f"Message '{key}' mismatch"

    # ── Round count and structure ─────────────────────────────────

    @pytest.mark.contract_case("UI-SD-015")
    def test_round_count(self, snapshot):
        """Round 数量必须与预期值匹配。"""
        expected = _load_expected()
        assert snapshot["rounds"]["count"] == expected["rounds"]["count"], \
            f"Expected {expected['rounds']['count']} rounds, got {snapshot['rounds']['count']}"

    @pytest.mark.contract_case("UI-SD-015")
    def test_round_details(self, snapshot):
        """每个 round 的 tool 数量、token 总计、交互次数必须匹配。"""
        expected = _load_expected()
        assert len(snapshot["rounds"]["rounds"]) == len(expected["rounds"]["rounds"])
        for i, (actual_r, expected_r) in enumerate(
            zip(snapshot["rounds"]["rounds"], expected["rounds"]["rounds"])
        ):
            for key in ("tool_count", "total_tokens", "llm_call_count", "llm_error_count", "interaction_count"):
                assert actual_r[key] == expected_r[key], \
                    f"Round {i} '{key}' mismatch: {actual_r[key]} != {expected_r[key]}"

    # ── Tool calls ────────────────────────────────────────────────

    @pytest.mark.contract_case("UI-SD-015")
    def test_tool_call_count(self, snapshot):
        """Tool 调用总次数必须与预期值匹配。"""
        expected = _load_expected()
        assert snapshot["tool_calls"]["total_count"] == expected["tool_calls"]["total_count"]

    @pytest.mark.contract_case("UI-SD-015")
    def test_tool_name_diversity(self, snapshot):
        """Tool 名称集合必须与预期值匹配（验证 fixture 多样性）。"""
        expected = _load_expected()
        assert sorted(snapshot["tool_calls"]["unique_tool_names"]) == sorted(
            expected["tool_calls"]["unique_tool_names"]
        ), f"Tool names mismatch: {snapshot['tool_calls']['unique_tool_names']}"

    @pytest.mark.contract_case("UI-SD-015")
    def test_failed_tool_count(self, snapshot):
        """失败 tool 的次数和名称必须与预期值匹配。"""
        expected = _load_expected()
        assert snapshot["tool_calls"]["failed_count"] == expected["tool_calls"]["failed_count"]
        assert sorted(snapshot["tool_calls"]["failed_tools"]) == sorted(
            expected["tool_calls"]["failed_tools"]
        )

    # ── LLM calls ─────────────────────────────────────────────────

    @pytest.mark.contract_case("UI-SD-015")
    def test_llm_call_counts(self, snapshot):
        """Main 和 subagent LLM 调用次数必须与预期值匹配。"""
        expected = _load_expected()
        assert snapshot["llm_calls"]["total_count"] == expected["llm_calls"]["total_count"]
        assert snapshot["llm_calls"]["main_count"] == expected["llm_calls"]["main_count"]
        assert snapshot["llm_calls"]["subagent_count"] == expected["llm_calls"]["subagent_count"]

    # ── Subagent runs ─────────────────────────────────────────────

    @pytest.mark.contract_case("UI-SD-015")
    def test_subagent_run_count(self, snapshot):
        """Subagent run count must match expected."""
        expected = _load_expected()
        assert snapshot["subagent_runs"]["count"] == expected["subagent_runs"]["count"]

    @pytest.mark.contract_case("UI-SD-015")
    def test_subagent_run_details(self, snapshot):
        """Subagent run agent_id and turn count must match expected."""
        expected = _load_expected()
        assert len(snapshot["subagent_runs"]["runs"]) == len(expected["subagent_runs"]["runs"])
        for actual_run, expected_run in zip(
            snapshot["subagent_runs"]["runs"], expected["subagent_runs"]["runs"]
        ):
            assert actual_run["agent_id"] == expected_run["agent_id"]
            assert actual_run["assistant_turn_count"] == expected_run["assistant_turn_count"]
            assert actual_run["message_count"] == expected_run["message_count"]

    # ── Anomalies ─────────────────────────────────────────────────

    @pytest.mark.contract_case("UI-SD-015")
    def test_session_anomaly_count(self, snapshot):
        """Session anomaly count must match expected."""
        expected = _load_expected()
        assert snapshot["anomalies"]["session_anomaly_count"] == expected["anomalies"]["session_anomaly_count"]

    @pytest.mark.contract_case("UI-SD-015")
    def test_session_anomaly_types(self, snapshot):
        """Session anomaly types must match expected."""
        expected = _load_expected()
        assert sorted(snapshot["anomalies"]["session_anomaly_types"]) == sorted(
            expected["anomalies"]["session_anomaly_types"]
        )

    # ── Round signals ─────────────────────────────────────────────

    @pytest.mark.contract_case("UI-SD-015")
    def test_round_signal_count(self, snapshot):
        """Total round signal count must match expected."""
        expected = _load_expected()
        assert snapshot["round_signals"]["total_signal_count"] == expected["round_signals"]["total_signal_count"]

    @pytest.mark.contract_case("UI-SD-015")
    def test_round_signals_by_round(self, snapshot):
        """Per-round signal keys and severities must match expected."""
        expected = _load_expected()
        actual_by_round = snapshot["round_signals"]["signals_by_round"]
        expected_by_round = expected["round_signals"]["signals_by_round"]
        assert set(actual_by_round.keys()) == set(expected_by_round.keys()), \
            f"Signal rounds mismatch: {set(actual_by_round.keys())} vs {set(expected_by_round.keys())}"
        for round_key in expected_by_round:
            actual_signals = actual_by_round.get(round_key, [])
            expected_signals = expected_by_round[round_key]
            assert len(actual_signals) == len(expected_signals), \
                f"Round {round_key} signal count mismatch"
            for act_sig, exp_sig in zip(actual_signals, expected_signals):
                assert act_sig["key"] == exp_sig["key"]
                assert act_sig["severity"] == exp_sig["severity"]

    # ── Duration ──────────────────────────────────────────────────

    @pytest.mark.contract_case("UI-SD-015")
    def test_duration(self, snapshot):
        """Session duration must match expected."""
        expected = _load_expected()
        assert snapshot["summary"]["duration_seconds"] == expected["summary"]["duration_seconds"]

    # ── Message count summary ─────────────────────────────────────

    @pytest.mark.contract_case("UI-SD-015")
    def test_summary_message_counts(self, snapshot):
        """Summary message/tool counts must match expected."""
        expected = _load_expected()
        for key in ("user_message_count", "assistant_message_count", "tool_call_count", "failed_tool_count"):
            assert snapshot["summary"][key] == expected["summary"][key], \
                f"Summary '{key}' mismatch"
