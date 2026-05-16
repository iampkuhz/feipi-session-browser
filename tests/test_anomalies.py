"""Tests for session-level anomaly detection."""

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
    """Build a minimal session dict with defaults."""
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
        "cached_output_tokens": 0,
        "assistant_message_count": 0,
    }
    if overrides:
        base.update(overrides)
    return base


def _anomaly_types(sa) -> set[str]:
    return {a.type for a in sa.anomalies}


def _anomaly_severities(sa, type_key: str) -> set[str]:
    return {a.severity for a in sa.anomalies if a.type == type_key}


# ── Long Duration (based on combined active time: model + tool) ──────────


class TestLongDuration:
    def test_3599_seconds_no_trigger(self):
        sa = detect_session_anomalies(_session({"model_execution_seconds": 3599}))
        assert AnomalyType.LONG_DURATION not in _anomaly_types(sa)

    def test_3600_seconds_triggers_warning(self):
        sa = detect_session_anomalies(_session({"model_execution_seconds": 3600}))
        assert AnomalyType.LONG_DURATION in _anomaly_types(sa)
        assert "warning" in _anomaly_severities(sa, AnomalyType.LONG_DURATION)

    def test_7200_seconds_triggers_critical(self):
        sa = detect_session_anomalies(_session({"model_execution_seconds": 7200}))
        assert AnomalyType.LONG_DURATION in _anomaly_types(sa)
        assert "critical" in _anomaly_severities(sa, AnomalyType.LONG_DURATION)

    def test_zero_duration_no_trigger(self):
        sa = detect_session_anomalies(_session({"model_execution_seconds": 0}))
        assert AnomalyType.LONG_DURATION not in _anomaly_types(sa)

    def test_high_wall_clock_low_exec_no_trigger(self):
        """Wall clock 2h but model exec only 10min — should not trigger."""
        sa = detect_session_anomalies(_session({
            "duration_seconds": 7200,
            "model_execution_seconds": 600,
        }))
        assert AnomalyType.LONG_DURATION not in _anomaly_types(sa)

    def test_combined_model_tool_triggers(self):
        """Model 30min + tool 31min = 61min total — triggers warning."""
        sa = detect_session_anomalies(_session({
            "model_execution_seconds": 1800,
            "tool_execution_seconds": 1860,
        }))
        assert AnomalyType.LONG_DURATION in _anomaly_types(sa)
        assert "warning" in _anomaly_severities(sa, AnomalyType.LONG_DURATION)

    def test_tool_only_triggers(self):
        """Tool exec 1h alone — triggers warning."""
        sa = detect_session_anomalies(_session({
            "model_execution_seconds": 0,
            "tool_execution_seconds": 3600,
        }))
        assert AnomalyType.LONG_DURATION in _anomaly_types(sa)
        assert "warning" in _anomaly_severities(sa, AnomalyType.LONG_DURATION)


# ── Failed Run ─────────────────────────────────────────────────────────


class TestFailedRun:
    def test_10pct_ratio_no_trigger(self):
        """1 failed / 10 tools = 10% ratio — below 15% threshold."""
        sa = detect_session_anomalies(_session({
            "failed_tool_count": 1,
            "tool_call_count": 10,
        }))
        assert AnomalyType.FAILED_RUN not in _anomaly_types(sa)

    def test_16pct_ratio_triggers_warning(self):
        """4 failed / 25 tools = 16% ratio — above 15% warning threshold."""
        sa = detect_session_anomalies(_session({
            "failed_tool_count": 4,
            "tool_call_count": 25,
        }))
        assert AnomalyType.FAILED_RUN in _anomaly_types(sa)
        assert "warning" in _anomaly_severities(sa, AnomalyType.FAILED_RUN)
        assert "critical" not in _anomaly_severities(sa, AnomalyType.FAILED_RUN)

    def test_30pct_ratio_triggers_critical(self):
        """6 failed / 20 tools = 30% ratio — above 25% critical threshold."""
        sa = detect_session_anomalies(_session({
            "failed_tool_count": 6,
            "tool_call_count": 20,
        }))
        assert AnomalyType.FAILED_RUN in _anomaly_types(sa)
        assert "critical" in _anomaly_severities(sa, AnomalyType.FAILED_RUN)

    def test_high_ratio_low_count_triggers(self):
        """1 failed / 2 tools = 50% ratio — ratio-only triggers critical."""
        sa = detect_session_anomalies(_session({
            "failed_tool_count": 1,
            "tool_call_count": 2,
        }))
        assert AnomalyType.FAILED_RUN in _anomaly_types(sa)
        assert "critical" in _anomaly_severities(sa, AnomalyType.FAILED_RUN)


# ── Removed anomaly types ─────────────────────────────────────────────


class TestRemovedAnomalyTypes:
    """Verify that low-value session anomaly types are no longer emitted."""

    def test_low_cache_reuse_not_in_anomaly_types(self):
        sa = detect_session_anomalies(_session({
            "cached_input_tokens": 100,
            "input_tokens": 50000,
        }))
        assert "low_cache_reuse" not in _anomaly_types(sa)

    def test_low_output_ratio_not_in_anomaly_types(self):
        sa = detect_session_anomalies(_session({
            "input_tokens": 50000,
            "output_tokens": 50,
        }))
        assert "low_output_ratio" not in _anomaly_types(sa)

    def test_tool_spike_not_in_default_results(self):
        """High tool count should not trigger session anomaly by default."""
        sa = detect_session_anomalies(_session({
            "tool_call_count": 300,
            "failed_tool_count": 0,
        }))
        assert "tool_spike" not in _anomaly_types(sa)


# ── Cache Creation ─────────────────────────────────────────────────────


class TestCacheWriteHotspot:
    def test_label_is_cache_creation(self):
        sa = detect_session_anomalies(_session({
            "cached_output_tokens": 250_000,
        }))
        hotspot_anomalies = [a for a in sa.anomalies if a.type == AnomalyType.CACHE_WRITE_SPIKE]
        assert len(hotspot_anomalies) == 1
        assert hotspot_anomalies[0].label == "Cache Creation"

    def test_below_threshold(self):
        sa = detect_session_anomalies(_session({
            "cached_output_tokens": 100_000,
        }))
        assert AnomalyType.CACHE_WRITE_SPIKE not in _anomaly_types(sa)


# ── Diagnostics Registry ───────────────────────────────────────────────


class TestDiagnosticsRegistry:
    """Verify centralized tag registry integrity."""

    def test_session_anomaly_filter_no_low_cache(self):
        keys = get_session_anomaly_keys()
        assert "low_cache_reuse" not in keys

    def test_session_anomaly_filter_no_low_output(self):
        keys = get_session_anomaly_keys()
        assert "low_output_ratio" not in keys

    def test_session_anomaly_filter_no_tool_spike(self):
        keys = get_session_anomaly_keys()
        assert "tool_spike" not in keys

    def test_round_signal_has_failed_tool(self):
        keys = get_round_signal_keys()
        assert "failed-tool" in keys

    def test_session_and_round_keys_do_not_overlap(self):
        """Session anomaly and round signal keys should be disjoint."""
        overlap = get_session_anomaly_keys() & get_round_signal_keys()
        assert overlap == set(), f"Overlapping keys: {overlap}"
