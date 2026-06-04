"""Qoder token distribution 测试。"""

from __future__ import annotations

from session_browser.attribution.api_families.qoder_broker.usage_parser import parse_qoder_broker_usage
from session_browser.attribution.mapping.call_mapping_resolver import resolve_call_mapping


class TestQoderTokenDistribution:
    def test_anthropic_like_distribution(self):
        usage = {
            "cache_read_input_tokens": 3000,
            "cache_creation_input_tokens": 500,
            "input_tokens": 1000,
            "output_tokens": 400,
        }
        decision = resolve_call_mapping(
            agent="qoder",
            usage=usage,
            model="performance-tier",
        )
        assert decision.api_family == "qoder_broker"
        assert decision.underlying_provider == "anthropic"
        assert decision.confidence >= 0.8

    def test_openai_like_distribution(self):
        usage = {
            "input_tokens": 2500,
            "output_tokens": 350,
            "input_tokens_details": {"cached_tokens": 800},
        }
        decision = resolve_call_mapping(
            agent="qoder",
            usage=usage,
            model="standard-tier",
        )
        assert decision.api_family == "qoder_broker"
        assert decision.underlying_provider == "openai"

    def test_no_usage_estimate_only(self):
        decision = resolve_call_mapping(
            agent="qoder",
            usage=None,
            model="unknown",
        )
        # 无 usage 时走 estimate_only
        assert decision.api_family in ("estimate_only", "qoder_broker")
