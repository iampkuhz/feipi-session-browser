"""Qoder credit attribution 测试。"""

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
    def test_estimate_from_tokens(self):
        result = estimate_qoder_credits(
            input_tokens=1000,
            output_tokens=500,
            model_tier="performance-tier",
        )
        assert result["precision"] == "estimated"
        assert result["total_credits"] > 0
        assert "performance-tier" in result["source"]

    def test_estimate_unknown_tier(self):
        result = estimate_qoder_credits(
            input_tokens=100,
            output_tokens=0,
            model_tier="unknown",
        )
        assert result["precision"] == "estimated"
        assert result["total_credits"] > 0
