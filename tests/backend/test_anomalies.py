"""会话级异常检测测试。"""

from __future__ import annotations

import pytest
from session_browser.index.anomalies import (
    detect_session_anomalies,
    AnomalyType,
)
from session_browser.index.diagnostics import (
    SESSION_ANOMALY_DEFINITIONS,
    ROUND_SIGNAL_DEFINITIONS,
    get_session_anomaly_keys,
    get_round_signal_keys,
)


def _session(overrides: dict | None = None) -> dict:
    """构建带默认值的最小会话字典。"""
    base = {
        "session_key": "test:abc123",
        "session_id": "abc123",
        "agent": "claude_code",
        "title": "Test Session",
        "model": "claude-sonnet-4-6-20250514",
        "project_name": "test-project",
        "project_key": "/tmp/test",
        "ended_at": "2026-01-01T00:00:00Z",
        "duration_seconds": 0,
        "model_execution_seconds": 0,
        "tool_execution_seconds": 0,
        "tool_call_count": 0,
        "failed_tool_count": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cached_input_tokens": 0,
        "cache_write_tokens": 0,
        "assistant_message_count": 0,
    }
    if overrides:
        base.update(overrides)
    return base


def _anomaly_types(sa) -> set[str]:
    return {a.type for a in sa.anomalies}


def _anomaly_severities(sa, type_key: str) -> set[str]:
    return {a.severity for a in sa.anomalies if a.type == type_key}


# ── 长时间运行（基于组合活跃时间：model + tool） ──────────


class TestLongDuration:
    @pytest.mark.contract_case("DATA-INDEX-001")
    def test_3599_seconds_no_trigger(self):
        sa = detect_session_anomalies(_session({"model_execution_seconds": 3599}))
        assert AnomalyType.LONG_DURATION not in _anomaly_types(sa)

    @pytest.mark.contract_case("DATA-INDEX-001")
    def test_3600_seconds_triggers_warning(self):
        sa = detect_session_anomalies(_session({"model_execution_seconds": 3600}))
        assert AnomalyType.LONG_DURATION in _anomaly_types(sa)
        assert "warning" in _anomaly_severities(sa, AnomalyType.LONG_DURATION)

    @pytest.mark.contract_case("DATA-INDEX-001")
    def test_7200_seconds_triggers_critical(self):
        sa = detect_session_anomalies(_session({"model_execution_seconds": 7200}))
        assert AnomalyType.LONG_DURATION in _anomaly_types(sa)
        assert "critical" in _anomaly_severities(sa, AnomalyType.LONG_DURATION)

    @pytest.mark.contract_case("DATA-INDEX-001")
    def test_zero_duration_no_trigger(self):
        sa = detect_session_anomalies(_session({"model_execution_seconds": 0}))
        assert AnomalyType.LONG_DURATION not in _anomaly_types(sa)

    @pytest.mark.contract_case("DATA-INDEX-001")
    def test_high_wall_clock_low_exec_no_trigger(self):
        """墙钟 2 小时但模型执行仅 10 分钟——不应触发。"""
        sa = detect_session_anomalies(_session({
            "duration_seconds": 7200,
            "model_execution_seconds": 600,
        }))
        assert AnomalyType.LONG_DURATION not in _anomaly_types(sa)

    @pytest.mark.contract_case("DATA-INDEX-001")
    def test_combined_model_tool_triggers(self):
        """模型 30 分钟 + 工具 31 分钟 = 总计 61 分钟——触发警告。"""
        sa = detect_session_anomalies(_session({
            "model_execution_seconds": 1800,
            "tool_execution_seconds": 1860,
        }))
        assert AnomalyType.LONG_DURATION in _anomaly_types(sa)
        assert "warning" in _anomaly_severities(sa, AnomalyType.LONG_DURATION)

    @pytest.mark.contract_case("DATA-INDEX-001")
    def test_tool_only_triggers(self):
        """工具执行单独 1 小时——触发警告。"""
        sa = detect_session_anomalies(_session({
            "model_execution_seconds": 0,
            "tool_execution_seconds": 3600,
        }))
        assert AnomalyType.LONG_DURATION in _anomaly_types(sa)
        assert "warning" in _anomaly_severities(sa, AnomalyType.LONG_DURATION)


# ── 失败运行 ─────────────────────────────────────────────────────────


class TestFailedRun:
    @pytest.mark.contract_case("DATA-INDEX-001")
    def test_10pct_ratio_no_trigger(self):
        """1 失败 / 10 工具 = 10% 比率——低于 15% 阈值。"""
        sa = detect_session_anomalies(_session({
            "failed_tool_count": 1,
            "tool_call_count": 10,
        }))
        assert AnomalyType.FAILED_RUN not in _anomaly_types(sa)

    @pytest.mark.contract_case("DATA-INDEX-001")
    def test_16pct_ratio_triggers_warning(self):
        """4 失败 / 25 工具 = 16% 比率——高于 15% 警告阈值。"""
        sa = detect_session_anomalies(_session({
            "failed_tool_count": 4,
            "tool_call_count": 25,
        }))
        assert AnomalyType.FAILED_RUN in _anomaly_types(sa)
        assert "warning" in _anomaly_severities(sa, AnomalyType.FAILED_RUN)
        assert "critical" not in _anomaly_severities(sa, AnomalyType.FAILED_RUN)

    @pytest.mark.contract_case("DATA-INDEX-001")
    def test_30pct_ratio_triggers_critical(self):
        """6 失败 / 20 工具 = 30% 比率——高于 25% 严重阈值。"""
        sa = detect_session_anomalies(_session({
            "failed_tool_count": 6,
            "tool_call_count": 20,
        }))
        assert AnomalyType.FAILED_RUN in _anomaly_types(sa)
        assert "critical" in _anomaly_severities(sa, AnomalyType.FAILED_RUN)

    @pytest.mark.contract_case("DATA-INDEX-001")
    def test_high_ratio_low_count_triggers(self):
        """1 失败 / 2 工具 = 50% 比率——仅凭比率触发严重。"""
        sa = detect_session_anomalies(_session({
            "failed_tool_count": 1,
            "tool_call_count": 2,
        }))
        assert AnomalyType.FAILED_RUN in _anomaly_types(sa)
        assert "critical" in _anomaly_severities(sa, AnomalyType.FAILED_RUN)


# ── 已移除的异常类型 ──────────────────────────────────────────────


class TestRemovedAnomalyTypes:
    """验证低价值会话异常类型已不再产生。"""

    @pytest.mark.contract_case("DATA-INDEX-001")
    def test_low_cache_reuse_not_in_anomaly_types(self):
        sa = detect_session_anomalies(_session({
            "cached_input_tokens": 100,
            "input_tokens": 50000,
        }))
        assert "low_cache_reuse" not in _anomaly_types(sa)

    @pytest.mark.contract_case("DATA-INDEX-001")
    def test_low_output_ratio_not_in_anomaly_types(self):
        sa = detect_session_anomalies(_session({
            "input_tokens": 50000,
            "output_tokens": 50,
        }))
        assert "low_output_ratio" not in _anomaly_types(sa)

    @pytest.mark.contract_case("DATA-INDEX-001")
    def test_tool_spike_not_in_default_results(self):
        """高工具计数默认不应触发会话异常。"""
        sa = detect_session_anomalies(_session({
            "tool_call_count": 300,
            "failed_tool_count": 0,
        }))
        assert "tool_spike" not in _anomaly_types(sa)


# ── 缓存创建 ──────────────────────────────────────────────────────


class TestCacheWriteHotspot:
    @pytest.mark.contract_case("DATA-INDEX-001")
    def test_label_is_cache_creation(self):
        sa = detect_session_anomalies(_session({
            "cache_write_tokens": 250_000,
        }))
        hotspot_anomalies = [a for a in sa.anomalies if a.type == AnomalyType.CACHE_WRITE_SPIKE]
        assert len(hotspot_anomalies) == 1
        assert hotspot_anomalies[0].label == "Cache Creation"

    @pytest.mark.contract_case("DATA-INDEX-001")
    def test_below_threshold(self):
        sa = detect_session_anomalies(_session({
            "cache_write_tokens": 100_000,
        }))
        assert AnomalyType.CACHE_WRITE_SPIKE not in _anomaly_types(sa)


# ── 诊断注册表 ───────────────────────────────────────────────


class TestDiagnosticsRegistry:
    """验证中心化标签注册表的完整性。"""

    @pytest.mark.contract_case("DATA-INDEX-001")
    def test_session_anomaly_filter_no_low_cache(self):
        keys = get_session_anomaly_keys()
        assert "low_cache_reuse" not in keys

    @pytest.mark.contract_case("DATA-INDEX-001")
    def test_session_anomaly_filter_no_low_output(self):
        keys = get_session_anomaly_keys()
        assert "low_output_ratio" not in keys

    @pytest.mark.contract_case("DATA-INDEX-001")
    def test_session_anomaly_filter_no_tool_spike(self):
        keys = get_session_anomaly_keys()
        assert "tool_spike" not in keys

    @pytest.mark.contract_case("DATA-INDEX-001")
    def test_round_signal_has_failed_tool(self):
        keys = get_round_signal_keys()
        assert "failed-tool" in keys

    @pytest.mark.contract_case("DATA-INDEX-001")
    def test_session_and_round_keys_do_not_overlap(self):
        """会话异常和轮次信号的键集合应互不重叠。"""
        overlap = get_session_anomaly_keys() & get_round_signal_keys()
        assert overlap == set(), f"Overlapping keys: {overlap}"
