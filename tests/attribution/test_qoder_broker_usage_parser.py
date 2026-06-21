"""Qoder broker usage parser 测试。

Qoder broker-reported usage 中 ``input_tokens`` 是本次请求输入规模，
cache read/write 是独立组件。
"""

from __future__ import annotations

from session_browser.attribution.api_families.qoder_broker.usage_parser import (
    parse_qoder_broker_usage,
)


class TestQoderBrokerUsageParser:
    """测试 Qoder broker usage 解析。"""

    def test_raw_anthropic_like_request_input(self):
        """原始 Qoder GUI usage：input_tokens 是 request input。"""
        usage = {
            'input_tokens': 18316,
            'cache_read_input_tokens': 18310,
            'cache_creation_input_tokens': 0,
            'output_tokens': 54,
        }
        result = parse_qoder_broker_usage(usage)
        assert result.total_input == 36626
        assert result.fresh_input == 18316
        assert result.cache_read == 18310
        assert result.cache_write == 0
        assert result.output == 54
        assert 'qoder_broker' in result.usage_source
        assert result.precision == 'provider_reported'

    def test_normalized_with_total_marker(self):
        """带 marker 的 usage：marker 只追溯原始 input，不覆盖组件合计。"""
        usage = {
            'qoder_input_tokens_total': 18316,
            'input_tokens': 18316,
            'cache_read_input_tokens': 18310,
            'cache_creation_input_tokens': 0,
            'output_tokens': 54,
        }
        result = parse_qoder_broker_usage(usage)
        assert result.total_input == 36626
        assert result.fresh_input == 18316
        assert result.cache_read == 18310
        assert result.cache_write == 0
        assert result.output == 54

    def test_provider_cache_write_explicit(self):
        """Provider 显式报告 cache_creation_input_tokens > 0。"""
        usage = {
            'input_tokens': 1000,
            'cache_read_input_tokens': 300,
            'cache_creation_input_tokens': 200,
            'output_tokens': 40,
        }
        result = parse_qoder_broker_usage(usage)
        assert result.total_input == 1500
        assert result.fresh_input == 1000
        assert result.cache_read == 300
        assert result.cache_write == 200
        assert result.output == 40

    def test_openai_like_usage(self):
        """Qoder broker: OpenAI-like usage。"""
        usage = {
            'input_tokens': 3500,
            'output_tokens': 780,
            'input_tokens_details': {'cached_tokens': 1200},
        }
        result = parse_qoder_broker_usage(usage)
        assert result.total_input == 4700
        assert result.cache_read == 1200
        assert result.cache_write is None  # OpenAI 无 cache_write
        assert result.fresh_input == 3500

    def test_no_usage_data(self):
        """无 usage 数据。"""
        result = parse_qoder_broker_usage(None)
        assert result.precision == 'unavailable'
        assert result.total_input is None

    def test_basic_tokens_only(self):
        """只有 basic tokens，无 cache 信息。"""
        usage = {'input_tokens': 1000, 'output_tokens': 200}
        result = parse_qoder_broker_usage(usage)
        assert result.total_input == 1000
        assert result.fresh_input == 1000
        assert result.output == 200
        assert result.cache_read is None
        assert result.cache_write is None

    def test_zero_values_are_valid(self):
        """0 是有效值，不能变成 unavailable 或 None。"""
        usage = {
            'input_tokens': 100,
            'cache_read_input_tokens': 0,
            'cache_creation_input_tokens': 0,
            'output_tokens': 50,
        }
        result = parse_qoder_broker_usage(usage)
        assert result.total_input == 100
        assert result.fresh_input == 100
        assert result.cache_read == 0
        assert result.cache_write == 0
        assert result.output == 50
