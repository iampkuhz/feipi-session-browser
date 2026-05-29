"""测试 token 归一化。"""
import pytest
from session_browser.domain.token_normalizer import (
    normalize_tokens,
    normalize_tokens_unified,
    normalize_qoder_sqlite_unified,
    format_tokens,
    precision_label,
    TokenPrecision,
    TokenProvider,
)
from session_browser.domain.models import (
    NormalizedTokenBreakdown,
    TokenTotalSemantics,
    TokenSourceKind,
)


class TestAnthropicNormalization:
    """测试 Anthropic 用量归一化。"""

    @pytest.mark.contract_case("DATA-PRESENTER-008")
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

    @pytest.mark.contract_case("DATA-PRESENTER-008")
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

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_anthropic_cache_read_not_double_counted(self):
        """Cache read 不应加入 inputFresh。"""
        usage = {
            "input_tokens": 1000,
            "cache_read_input_tokens": 5000,
            "output_tokens": 200,
        }
        result = normalize_tokens(usage, provider=TokenProvider.ANTHROPIC)

        assert result.input_fresh == 1000
        assert result.input_cache_read == 5000
        assert result.total_input == 6000  # 1000 + 5000, NOT 1000 + 5000 + 1000

    @pytest.mark.contract_case("DATA-PRESENTER-008")
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
    """测试 OpenAI 用量归一化。"""

    @pytest.mark.contract_case("DATA-PRESENTER-008")
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

    @pytest.mark.contract_case("DATA-PRESENTER-008")
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

    @pytest.mark.contract_case("DATA-PRESENTER-008")
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

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_openai_new_format(self):
        """测试较新的 OpenAI 格式（带 input_tokens/output_tokens）。"""
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
    """测试 Codex 用量归一化。"""

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_codex_total_only(self):
        usage = {"tokens_used": 10000}
        result = normalize_tokens(usage, provider=TokenProvider.CODEX)

        assert result.total_input == 10000
        assert result.precision == TokenPrecision.PROVIDER_REPORTED  # tokens_used 直接来自 provider
        assert result.provider == TokenProvider.CODEX

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_codex_missing(self):
        usage = {}
        result = normalize_tokens(usage, provider=TokenProvider.CODEX)

        assert result.total_input is None
        assert result.precision == TokenPrecision.UNKNOWN  # no data at all


class TestQoderNormalization:
    """测试 Qoder 用量归一化。

    Qoder token 始终为 ESTIMATED；cache 字段原样保留（通常为 0）。
    """

    @pytest.mark.contract_case("DATA-PRESENTER-008")
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

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_qoder_missing_usage(self):
        usage = {}
        result = normalize_tokens(usage, provider=TokenProvider.QODER)

        assert result.input_fresh is None
        assert result.output_visible is None
        assert result.precision == TokenPrecision.ESTIMATED
        assert result.provider == TokenProvider.QODER

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_qoder_estimated_flag_in_usage(self):
        """qoder.py 中的 estimated 标志应保留在 raw_fields 中。"""
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
    """测试缺失和未知字段的处理。"""

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_empty_usage(self):
        result = normalize_tokens({})
        assert result.precision == TokenPrecision.UNKNOWN

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_none_usage(self):
        result = normalize_tokens(None)
        assert result.precision == TokenPrecision.UNKNOWN

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_missing_fields_are_none_not_zero(self):
        usage = {"input_tokens": 1000}
        result = normalize_tokens(usage, provider=TokenProvider.ANTHROPIC)

        assert result.input_fresh == 1000
        assert result.input_cache_read is None  # 不是 0
        assert result.input_cache_write is None  # 不是 0
        assert result.output_visible is None  # 不是 0

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_unknown_provider_fallback(self):
        usage = {"some_custom_field": 42}
        result = normalize_tokens(usage, provider="unknown-provider")

        assert result.precision == TokenPrecision.ESTIMATED


class TestProviderInference:
    """测试从 model 字符串推断 provider。"""

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_qwen_model_inferred(self):
        usage = {"input_tokens": 100, "output_tokens": 50}
        result = normalize_tokens(usage, model="qwen3.6-plus")

        assert result.provider == TokenProvider.QWEN_ANTHROPIC_COMPATIBLE

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_claude_model_inferred(self):
        usage = {"input_tokens": 100, "output_tokens": 50}
        result = normalize_tokens(usage, model="claude-sonnet-4-20250514")

        assert result.provider == TokenProvider.ANTHROPIC

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_gpt_model_inferred(self):
        usage = {"prompt_tokens": 100, "completion_tokens": 50}
        result = normalize_tokens(usage, model="gpt-4o")

        assert result.provider == TokenProvider.OPENAI

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_unknown_model(self):
        usage = {"input_tokens": 100}
        result = normalize_tokens(usage, model="some-unknown-model")

        assert result.provider == TokenProvider.UNKNOWN


class TestFormatHelpers:
    """测试格式化辅助函数。"""

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_format_tokens_none(self):
        assert format_tokens(None) == "—"

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_format_tokens_small(self):
        assert format_tokens(500) == "500"

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_format_tokens_k(self):
        assert format_tokens(1500) == "1.5K"

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_format_tokens_m(self):
        assert format_tokens(1500000) == "1.5M"

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_precision_label(self):
        assert precision_label(TokenPrecision.EXACT) == "exact"
        assert precision_label(TokenPrecision.PROVIDER_REPORTED) == "provider-reported"
        assert precision_label(TokenPrecision.ESTIMATED) == "estimated"
        assert precision_label(TokenPrecision.UNKNOWN) == "unknown"


# ─── Unified 5-field breakdown tests ──────────────────────────────────


class TestUnifiedClaudeCode:
    """测试 Claude Code 统一 5 字段归一化。

    语义：input_tokens = fresh（新输入）；cache buckets 是独立的；
    total = 4 个独立桶之和。
    """

    def test_claude_code_basic(self):
        usage = {
            "input_tokens": 1000,
            "output_tokens": 500,
        }
        result = normalize_tokens_unified(usage, provider=TokenProvider.ANTHROPIC)

        assert result.fresh_input_tokens == 1000
        assert result.cache_read_tokens == 0
        assert result.cache_write_tokens == 0
        assert result.output_tokens == 500
        assert result.total_tokens == 1500
        assert result.total_semantics == TokenTotalSemantics.EXCLUSIVE_COMPONENT_SUM
        assert result.precision == TokenPrecision.PROVIDER_REPORTED

    def test_claude_code_with_cache(self):
        usage = {
            "input_tokens": 1000,
            "cache_read_input_tokens": 2000,
            "cache_creation_input_tokens": 500,
            "output_tokens": 300,
        }
        result = normalize_tokens_unified(usage, provider=TokenProvider.ANTHROPIC)

        assert result.fresh_input_tokens == 1000
        assert result.cache_read_tokens == 2000
        assert result.cache_write_tokens == 500
        assert result.output_tokens == 300
        assert result.total_tokens == 3800  # 1000 + 2000 + 500 + 300

    def test_claude_code_zero_fields(self):
        """所有字段必须为整数，不能为 None。"""
        usage = {"input_tokens": 100, "output_tokens": 50}
        result = normalize_tokens_unified(usage, provider=TokenProvider.ANTHROPIC)

        assert isinstance(result.fresh_input_tokens, int)
        assert isinstance(result.cache_read_tokens, int)
        assert isinstance(result.cache_write_tokens, int)
        assert isinstance(result.output_tokens, int)
        assert isinstance(result.total_tokens, int)

    def test_claude_code_empty_usage(self):
        result = normalize_tokens_unified({}, provider=TokenProvider.ANTHROPIC)
        assert result.fresh_input_tokens == 0
        assert result.cache_read_tokens == 0
        assert result.cache_write_tokens == 0
        assert result.output_tokens == 0
        assert result.total_tokens == 0

    def test_qwen_anthropic_compatible(self):
        """Qwen Anthropic 兼容模型应使用与 Claude 相同的归一化。"""
        usage = {
            "input_tokens": 25728,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 27473,
            "output_tokens": 275,
        }
        result = normalize_tokens_unified(usage, provider=TokenProvider.QWEN_ANTHROPIC_COMPATIBLE)

        assert result.fresh_input_tokens == 25728
        assert result.cache_read_tokens == 0
        assert result.cache_write_tokens == 27473
        assert result.output_tokens == 275


class TestUnifiedCodex:
    """测试 Codex 统一 5 字段归一化。

    语义：input_tokens 是包含缓存的总量；cached_input_tokens 是子集。
    """

    def test_codex_total_only(self):
        usage = {"tokens_used": 10000}
        result = normalize_tokens_unified(usage, provider=TokenProvider.CODEX)

        assert result.total_tokens == 10000
        assert result.total_semantics == TokenTotalSemantics.REPORTED_TOTAL

    def test_codex_with_components(self):
        """当有组件时，Codex 的 input_tokens 是包含缓存的总量。"""
        usage = {
            "input_tokens": 5000,
            "cached_input_tokens": 3000,
            "output_tokens": 2000,
        }
        result = normalize_tokens_unified(usage, provider=TokenProvider.CODEX)

        # fresh = input - cached (inclusive decomposition)
        assert result.fresh_input_tokens == 2000  # 5000 - 3000
        assert result.cache_read_tokens == 3000
        assert result.output_tokens == 2000
        assert result.total_semantics == TokenTotalSemantics.REPORTED_CUMULATIVE_DELTA

    def test_codex_delta_last_token_usage(self):
        """直接 delta 值归一化。"""
        usage = {
            "input_tokens": 800,
            "cache_read_input_tokens": 200,
            "output_tokens": 400,
        }
        result = normalize_tokens_unified(usage, provider=TokenProvider.CODEX)

        assert result.fresh_input_tokens == 600  # 800 - 200
        assert result.cache_read_tokens == 200
        assert result.output_tokens == 400

    def test_codex_empty_usage(self):
        result = normalize_tokens_unified({}, provider=TokenProvider.CODEX)
        assert result.total_tokens == 0
        assert result.precision == TokenPrecision.UNKNOWN


class TestUnifiedQoder:
    """测试 Qoder 统一 5 字段归一化。

    语义：input_tokens 通常是包含缓存的总量，需要分解为 fresh。
    字段名使用 cache_read_input_tokens / cache_creation_input_tokens。
    """

    def test_qoder_with_cache(self):
        usage = {
            "input_tokens": 5000,
            "cache_read_input_tokens": 2000,
            "cache_creation_input_tokens": 500,
            "output_tokens": 1500,
        }
        result = normalize_tokens_unified(usage, provider=TokenProvider.QODER)

        # fresh = input - cache_read - cache_write
        assert result.fresh_input_tokens == 2500  # 5000 - 2000 - 500
        assert result.cache_read_tokens == 2000
        assert result.cache_write_tokens == 500
        assert result.output_tokens == 1500
        assert result.total_tokens == 6500  # 2500 + 2000 + 500 + 1500

    def test_qoder_no_cache(self):
        usage = {
            "input_tokens": 1000,
            "output_tokens": 500,
        }
        result = normalize_tokens_unified(usage, provider=TokenProvider.QODER)

        assert result.fresh_input_tokens == 1000
        assert result.cache_read_tokens == 0
        assert result.cache_write_tokens == 0
        assert result.output_tokens == 500

    def test_qoder_cache_exceeds_input(self):
        """当缓存超过 input 时，fresh 应保持为 input（不产生负数）。"""
        usage = {
            "input_tokens": 100,
            "cache_read_input_tokens": 500,
            "cache_creation_input_tokens": 200,
            "output_tokens": 50,
        }
        result = normalize_tokens_unified(usage, provider=TokenProvider.QODER)

        assert result.fresh_input_tokens == 100  # capped at input_tokens
        assert result.cache_read_tokens == 500
        assert result.cache_write_tokens == 200

    def test_qoder_estimated_precision(self):
        """Qoder 非空 usage 的 precision 为 provider_reported_normalized。"""
        usage = {
            "input_tokens": 500,
            "output_tokens": 200,
        }
        result = normalize_tokens_unified(usage, provider=TokenProvider.QODER)

        assert result.fresh_input_tokens == 500
        assert result.output_tokens == 200
        assert result.precision == TokenPrecision.PROVIDER_REPORTED_NORMALIZED

    def test_qoder_empty_usage(self):
        """Qoder 空 usage 应返回 ESTIMATED 精度。"""
        result = normalize_tokens_unified({}, provider=TokenProvider.QODER)
        assert result.fresh_input_tokens == 0
        assert result.output_tokens == 0
        assert result.precision == TokenPrecision.ESTIMATED


class TestQoderSQLiteUnified:
    """测试 Qoder SQLite token_info 统一归一化。"""

    def test_sqlite_basic(self):
        token_info = {
            "prompt_tokens": 10000,
            "cached_tokens": 4000,
            "completion_tokens": 3000,
        }
        result = normalize_qoder_sqlite_unified(token_info)

        # SQLite token_info uses flat fields: prompt_tokens includes cached_tokens
        assert result.cache_read_tokens == 4000
        assert result.cache_write_tokens == 0
        assert result.output_tokens == 3000
        assert result.fresh_input_tokens == 6000  # 10000 - 4000
        assert result.total_tokens == 13000  # 6000 + 4000 + 0 + 3000
        assert result.source_kind == TokenSourceKind.QODER_SQLITE_TOKEN_INFO

    def test_sqlite_empty(self):
        result = normalize_qoder_sqlite_unified({})
        assert result.fresh_input_tokens == 0
        assert result.cache_read_tokens == 0
        assert result.cache_write_tokens == 0
        assert result.output_tokens == 0
        assert result.total_tokens == 0


class TestNormalizedTokenBreakdownDefaults:
    """测试 NormalizedTokenBreakdown 默认值。"""

    def test_all_defaults_zero(self):
        bd = NormalizedTokenBreakdown()
        assert bd.fresh_input_tokens == 0
        assert bd.cache_read_tokens == 0
        assert bd.cache_write_tokens == 0
        assert bd.output_tokens == 0
        assert bd.total_tokens == 0

    def test_metadata_defaults(self):
        bd = NormalizedTokenBreakdown()
        assert bd.precision == TokenPrecision.UNKNOWN
        assert bd.total_semantics == TokenTotalSemantics.EXCLUSIVE_COMPONENT_SUM
        assert bd.source_kind == TokenSourceKind.UNKNOWN
        assert bd.notes == []
        assert bd.raw_fields == {}


class TestUnifiedEdgeCases:
    """测试统一归一化的边界情况。"""

    def test_none_usage(self):
        result = normalize_tokens_unified(None, provider=TokenProvider.ANTHROPIC)
        assert result.total_tokens == 0

    def test_unknown_provider_fallback(self):
        """未知 provider 应使用 generic 归一化。"""
        result = normalize_tokens_unified(
            {"input_tokens": 100, "output_tokens": 50},
            provider="unknown_provider"
        )
        assert result.fresh_input_tokens == 100
        assert result.output_tokens == 50
        assert result.total_tokens == 150

    def test_large_values(self):
        usage = {
            "input_tokens": 10_000_000,
            "cache_read_input_tokens": 50_000_000,
            "cache_creation_input_tokens": 10_000_000,
            "output_tokens": 5_000_000,
        }
        result = normalize_tokens_unified(usage, provider=TokenProvider.ANTHROPIC)
        assert result.total_tokens == 75_000_000

    def test_model_inferred_provider(self):
        """通过 model 字符串推断 provider。"""
        result = normalize_tokens_unified(
            {"input_tokens": 100, "output_tokens": 50},
            model="claude-sonnet-4-20250514"
        )
        assert result.fresh_input_tokens == 100
        assert result.total_tokens == 150
