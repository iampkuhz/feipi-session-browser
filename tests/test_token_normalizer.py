"""Tests for token normalizer."""

from session_browser.domain.token_normalizer import (
    normalize_tokens,
    format_tokens,
    precision_label,
    TokenPrecision,
    TokenProvider,
)


class TestAnthropicNormalization:
    """Test Anthropic usage normalization."""

    def test_basic_anthropic_usage(self):
        usage = {
            "input_tokens": 1000,
            "output_tokens": 500,
        }
        result = normalize_tokens(usage, provider=TokenProvider.ANTHROPIC)

        assert result.input_fresh == 1000
        assert result.input_cache_read is None
        assert result.input_cache_write is None
        assert result.output_visible == 500
        assert result.output_reasoning is None
        assert result.total_input == 1000
        assert result.total_output == 500
        assert result.precision == TokenPrecision.PROVIDER_REPORTED
        assert result.provider == TokenProvider.ANTHROPIC

    def test_anthropic_with_cache_read(self):
        usage = {
            "input_tokens": 1000,
            "cache_read_input_tokens": 2000,
            "cache_creation_input_tokens": 500,
            "output_tokens": 300,
        }
        result = normalize_tokens(usage, provider=TokenProvider.ANTHROPIC)

        assert result.input_fresh == 1000
        assert result.input_cache_read == 2000
        assert result.input_cache_write == 500
        assert result.output_visible == 300
        assert result.total_input == 3500  # 1000 + 2000 + 500
        assert result.total_output == 300

    def test_anthropic_cache_read_not_double_counted(self):
        """Cache read must not be added to inputFresh."""
        usage = {
            "input_tokens": 1000,
            "cache_read_input_tokens": 5000,
            "output_tokens": 200,
        }
        result = normalize_tokens(usage, provider=TokenProvider.ANTHROPIC)

        assert result.input_fresh == 1000
        assert result.input_cache_read == 5000
        assert result.total_input == 6000  # 1000 + 5000, NOT 1000 + 5000 + 1000

    def test_qwen_anthropic_compatible(self):
        usage = {
            "input_tokens": 25728,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 27473,
            "output_tokens": 275,
        }
        result = normalize_tokens(usage, provider=TokenProvider.QWEN_ANTHROPIC_COMPATIBLE)

        assert result.input_fresh == 25728
        assert result.input_cache_read == 0
        assert result.input_cache_write == 27473
        assert result.output_visible == 275
        assert result.provider == TokenProvider.QWEN_ANTHROPIC_COMPATIBLE


class TestOpenAINormalization:
    """Test OpenAI usage normalization."""

    def test_basic_openai_usage(self):
        usage = {
            "prompt_tokens": 1000,
            "completion_tokens": 500,
        }
        result = normalize_tokens(usage, provider=TokenProvider.OPENAI)

        assert result.input_fresh == 1000
        assert result.output_visible == 500
        assert result.input_cache_read is None
        assert result.output_reasoning is None

    def test_openai_with_cached_tokens(self):
        usage = {
            "prompt_tokens": 5000,
            "completion_tokens": 300,
            "prompt_tokens_details": {"cached_tokens": 3000},
        }
        result = normalize_tokens(usage, provider=TokenProvider.OPENAI)

        assert result.input_cache_read == 3000
        assert result.input_fresh == 2000  # 5000 - 3000
        assert result.total_input == 5000  # 2000 + 3000

    def test_openai_with_reasoning_tokens(self):
        usage = {
            "prompt_tokens": 1000,
            "completion_tokens": 800,
            "completion_tokens_details": {"reasoning_tokens": 300},
        }
        result = normalize_tokens(usage, provider=TokenProvider.OPENAI)

        assert result.output_reasoning == 300
        assert result.output_visible == 500  # 800 - 300
        assert result.total_output == 800  # 500 + 300

    def test_openai_new_format(self):
        """Test newer OpenAI format with input_tokens/output_tokens."""
        usage = {
            "input_tokens": 4000,
            "output_tokens": 600,
            "input_tokens_details": {"cached_tokens": 2000},
            "output_tokens_details": {"reasoning_tokens": 200},
        }
        result = normalize_tokens(usage, provider=TokenProvider.OPENAI)

        assert result.input_fresh == 2000  # 4000 - 2000
        assert result.input_cache_read == 2000
        assert result.output_visible == 400  # 600 - 200
        assert result.output_reasoning == 200
        assert result.total_input == 4000
        assert result.total_output == 600


class TestCodexNormalization:
    """Test Codex usage normalization."""

    def test_codex_total_only(self):
        usage = {"tokens_used": 10000}
        result = normalize_tokens(usage, provider=TokenProvider.CODEX)

        assert result.total_input == 10000
        assert result.precision == TokenPrecision.PROVIDER_REPORTED  # tokens_used is directly from provider
        assert result.provider == TokenProvider.CODEX

    def test_codex_missing(self):
        usage = {}
        result = normalize_tokens(usage, provider=TokenProvider.CODEX)

        assert result.total_input is None
        assert result.precision == TokenPrecision.UNKNOWN  # no data at all


class TestQoderNormalization:
    """Test Qoder usage normalization.

    Qoder tokens are always ESTIMATED; cache fields are preserved as-is (usually 0).
    """

    def test_qoder_estimated_usage(self):
        usage = {
            "input_tokens": 500,
            "output_tokens": 200,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
            "estimated": True,
            "estimation_method": "qoder-fast-bytes-v1",
        }
        result = normalize_tokens(usage, provider=TokenProvider.QODER)

        assert result.input_fresh == 500
        assert result.output_visible == 200
        assert result.input_cache_read == 0
        assert result.input_cache_write == 0
        assert result.total_input == 500
        assert result.total_output == 200
        assert result.precision == TokenPrecision.ESTIMATED
        assert result.provider == TokenProvider.QODER

    def test_qoder_missing_usage(self):
        usage = {}
        result = normalize_tokens(usage, provider=TokenProvider.QODER)

        assert result.input_fresh is None
        assert result.output_visible is None
        assert result.precision == TokenPrecision.ESTIMATED
        assert result.provider == TokenProvider.QODER

    def test_qoder_estimated_flag_in_usage(self):
        """Estimated flag from qoder.py should be preserved in raw_fields."""
        usage = {
            "input_tokens": 100,
            "output_tokens": 50,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
            "estimated": True,
            "estimation_method": "qoder-fast-bytes-v1",
        }
        result = normalize_tokens(usage, provider=TokenProvider.QODER)

        assert result.precision == TokenPrecision.ESTIMATED
        assert "estimated" in result.raw_fields


class TestMissingAndUnknownFields:
    """Test handling of missing and unknown fields."""

    def test_empty_usage(self):
        result = normalize_tokens({})
        assert result.precision == TokenPrecision.UNKNOWN

    def test_none_usage(self):
        result = normalize_tokens(None)
        assert result.precision == TokenPrecision.UNKNOWN

    def test_missing_fields_are_none_not_zero(self):
        usage = {"input_tokens": 1000}
        result = normalize_tokens(usage, provider=TokenProvider.ANTHROPIC)

        assert result.input_fresh == 1000
        assert result.input_cache_read is None  # Not 0
        assert result.input_cache_write is None  # Not 0
        assert result.output_visible is None  # Not 0

    def test_unknown_provider_fallback(self):
        usage = {"some_custom_field": 42}
        result = normalize_tokens(usage, provider="unknown-provider")

        assert result.precision == TokenPrecision.ESTIMATED


class TestProviderInference:
    """Test provider inference from model string."""

    def test_qwen_model_inferred(self):
        usage = {"input_tokens": 100, "output_tokens": 50}
        result = normalize_tokens(usage, model="qwen3.6-plus")

        assert result.provider == TokenProvider.QWEN_ANTHROPIC_COMPATIBLE

    def test_claude_model_inferred(self):
        usage = {"input_tokens": 100, "output_tokens": 50}
        result = normalize_tokens(usage, model="claude-sonnet-4-20250514")

        assert result.provider == TokenProvider.ANTHROPIC

    def test_gpt_model_inferred(self):
        usage = {"prompt_tokens": 100, "completion_tokens": 50}
        result = normalize_tokens(usage, model="gpt-4o")

        assert result.provider == TokenProvider.OPENAI

    def test_unknown_model(self):
        usage = {"input_tokens": 100}
        result = normalize_tokens(usage, model="some-unknown-model")

        assert result.provider == TokenProvider.UNKNOWN


class TestFormatHelpers:
    """Test formatting helper functions."""

    def test_format_tokens_none(self):
        assert format_tokens(None) == "—"

    def test_format_tokens_small(self):
        assert format_tokens(500) == "500"

    def test_format_tokens_k(self):
        assert format_tokens(1500) == "1.5K"

    def test_format_tokens_m(self):
        assert format_tokens(1500000) == "1.5M"

    def test_precision_label(self):
        assert precision_label(TokenPrecision.EXACT) == "exact"
        assert precision_label(TokenPrecision.PROVIDER_REPORTED) == "provider-reported"
        assert precision_label(TokenPrecision.ESTIMATED) == "estimated"
        assert precision_label(TokenPrecision.UNKNOWN) == "unknown"
