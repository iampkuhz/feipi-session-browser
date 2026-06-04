"""Qoder broker usage parser 测试。"""

from __future__ import annotations

from session_browser.attribution.api_families.qoder_broker.usage_parser import parse_qoder_broker_usage


class TestQoderBrokerUsageParser:
    def test_anthropic_like_usage(self):
        usage = {
            "cache_read_input_tokens": 4200,
            "cache_creation_input_tokens": 800,
            "input_tokens": 1500,
            "output_tokens": 620,
        }
        result = parse_qoder_broker_usage(usage)
        assert result.total_input == 6500  # 4200 + 800 + 1500
        assert result.cache_read == 4200
        assert result.cache_write == 800
        assert result.fresh_input == 1500
        assert result.output == 620
        assert "qoder_broker" in result.usage_source

    def test_openai_like_usage(self):
        usage = {
            "input_tokens": 3500,
            "output_tokens": 780,
            "input_tokens_details": {"cached_tokens": 1200},
        }
        result = parse_qoder_broker_usage(usage)
        assert result.total_input == 3500
        assert result.cache_read == 1200
        assert result.cache_write is None  # OpenAI 无 cache_write
        assert result.fresh_input == 2300  # 3500 - 1200

    def test_no_usage_data(self):
        result = parse_qoder_broker_usage(None)
        assert result.precision == "unavailable"
        assert result.total_input is None

    def test_basic_tokens_only(self):
        usage = {"input_tokens": 1000, "output_tokens": 200}
        result = parse_qoder_broker_usage(usage)
        assert result.total_input == 1000
        assert result.output == 200
        assert result.cache_read is None
        assert result.cache_write is None
