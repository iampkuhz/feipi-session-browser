"""Qoder credit attribution 测试。

验证 credit 估算安全性：
- exact credit 优先。
- 无 exact / 无 calibration 时 unavailable，不输出伪精确值。
- 有测试 calibration 时可 estimated，并清晰标注来源。
"""

from __future__ import annotations

from session_browser.attribution.api_families.qoder_broker.credit_parser import parse_qoder_credit_events
from session_browser.attribution.api_families.qoder_broker.credit_estimator import estimate_qoder_credits


class TestQoderCreditParser:
    def test_parse_exact_events(self):
        events = [
            {"type": "exact", "delta": 0.5, "model": "performance-tier"},
            {"type": "exact", "delta": 0.3, "model": "standard-tier"},
        ]
        result = parse_qoder_credit_events(events)
        assert result["total_credits"] == 0.8
        assert result["precision"] == "exact"
        assert len(result["by_model"]) == 2

    def test_parse_no_events(self):
        result = parse_qoder_credit_events(None)
        assert result["total_credits"] is None
        assert result["precision"] == "unavailable"

    def test_parse_empty_events(self):
        result = parse_qoder_credit_events([])
        assert result["total_credits"] is None


class TestQoderCreditEstimator:
    def test_no_calibration_returns_unavailable(self):
        """无校准费率时不输出伪精确估算值。"""
        result = estimate_qoder_credits(
            input_tokens=1000,
            output_tokens=500,
            model_tier="performance-tier",
        )
        assert result["total_credits"] is None
        assert result["precision"] == "unavailable"
        assert "校准" in result["note"] or "calibrat" in result["note"].lower()

    def test_unknown_tier_no_calibration(self):
        """未知 tier 无校准费率时也返回 unavailable。"""
        result = estimate_qoder_credits(
            input_tokens=100,
            output_tokens=0,
            model_tier="unknown",
        )
        assert result["total_credits"] is None
        assert result["precision"] == "unavailable"

    def test_with_calibration_returns_estimated(self):
        """有显式校准费率时可估算，并标注来源。"""
        rates = {"performance-tier": 0.0003}
        result = estimate_qoder_credits(
            input_tokens=1000,
            output_tokens=500,
            model_tier="performance-tier",
            calibration_rates=rates,
        )
        assert result["total_credits"] is not None
        assert result["total_credits"] > 0
        assert result["precision"] == "estimated"
        assert "calibrated" in result["source"]

    def test_exact_credit_priority(self):
        """exact credit events 优先于估算。"""
        events = [{"type": "exact", "delta": 1.5, "model": "performance-tier"}]
        parsed = parse_qoder_credit_events(events)
        assert parsed["total_credits"] == 1.5
        assert parsed["precision"] == "exact"
