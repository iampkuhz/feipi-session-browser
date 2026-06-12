"""测试 token 归一化。"""
import pytest
from session_browser.domain.token_normalizer import (
    normalize_tokens,
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


# ─── Claude Code tests ───────────────────────────────────────────────────


class TestClaudeCodeNormalization:
    """测试 Claude Code 归一化。

    语义：input_tokens = fresh（新输入）；cache buckets 是独立的；
    total = 4 个独立桶之和。
    """

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_basic_anthropic_usage(self):
        usage = {
            "input_tokens": 1000,
            "output_tokens": 500,
        }
        result = normalize_tokens(usage, provider=TokenProvider.ANTHROPIC)

        assert result.fresh_input_tokens == 1000
        assert result.cache_read_tokens == 0
        assert result.cache_write_tokens == 0
        assert result.output_tokens == 500
        assert result.total_tokens == 1500
        assert result.total_semantics == TokenTotalSemantics.EXCLUSIVE_COMPONENT_SUM
        assert result.precision == TokenPrecision.PROVIDER_REPORTED

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_anthropic_with_cache(self):
        usage = {
            "input_tokens": 1000,
            "cache_read_input_tokens": 2000,
            "cache_creation_input_tokens": 500,
            "output_tokens": 300,
        }
        result = normalize_tokens(usage, provider=TokenProvider.ANTHROPIC)

        assert result.fresh_input_tokens == 1000
        assert result.cache_read_tokens == 2000
        assert result.cache_write_tokens == 500
        assert result.output_tokens == 300
        assert result.total_tokens == 3800  # 1000 + 2000 + 500 + 300

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_qwen_anthropic_compatible(self):
        usage = {
            "input_tokens": 25728,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 27473,
            "output_tokens": 275,
        }
        result = normalize_tokens(usage, provider=TokenProvider.QWEN_ANTHROPIC_COMPATIBLE)

        assert result.fresh_input_tokens == 25728
        assert result.cache_read_tokens == 0
        assert result.cache_write_tokens == 27473
        assert result.output_tokens == 275

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_all_fields_are_int(self):
        usage = {"input_tokens": 100, "output_tokens": 50}
        result = normalize_tokens(usage, provider=TokenProvider.ANTHROPIC)

        assert isinstance(result.fresh_input_tokens, int)
        assert isinstance(result.cache_read_tokens, int)
        assert isinstance(result.cache_write_tokens, int)
        assert isinstance(result.output_tokens, int)
        assert isinstance(result.total_tokens, int)

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_empty_usage(self):
        result = normalize_tokens({}, provider=TokenProvider.ANTHROPIC)
        assert result.fresh_input_tokens == 0
        assert result.cache_read_tokens == 0
        assert result.cache_write_tokens == 0
        assert result.output_tokens == 0
        assert result.total_tokens == 0


# ─── OpenAI tests ────────────────────────────────────────────────────────


class TestOpenAINormalization:
    """测试 OpenAI 用量归一化。"""

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_basic_openai_usage(self):
        usage = {
            "prompt_tokens": 1000,
            "completion_tokens": 500,
        }
        result = normalize_tokens(usage, provider=TokenProvider.OPENAI)

        assert result.fresh_input_tokens == 1000
        assert result.output_tokens == 500
        assert result.cache_read_tokens == 0

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_openai_with_cached_tokens(self):
        usage = {
            "prompt_tokens": 5000,
            "completion_tokens": 300,
            "prompt_tokens_details": {"cached_tokens": 3000},
        }
        result = normalize_tokens(usage, provider=TokenProvider.OPENAI)

        assert result.cache_read_tokens == 3000
        assert result.fresh_input_tokens == 2000
        assert result.total_tokens == 5300

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_openai_with_reasoning_tokens(self):
        usage = {
            "prompt_tokens": 1000,
            "completion_tokens": 800,
            "completion_tokens_details": {"reasoning_tokens": 300},
        }
        result = normalize_tokens(usage, provider=TokenProvider.OPENAI)

        assert result.output_tokens == 800

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_openai_new_format(self):
        usage = {
            "input_tokens": 4000,
            "output_tokens": 600,
            "input_tokens_details": {"cached_tokens": 2000},
            "output_tokens_details": {"reasoning_tokens": 200},
        }
        result = normalize_tokens(usage, provider=TokenProvider.OPENAI)

        assert result.fresh_input_tokens == 2000
        assert result.cache_read_tokens == 2000
        assert result.output_tokens == 600


# ─── Codex tests ─────────────────────────────────────────────────────────


class TestCodexNormalization:
    """测试 Codex 用量归一化。

    语义：cached_input_tokens 是 input_tokens 的子集；Fresh 是非缓存输入。
    """

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_codex_total_only(self):
        usage = {"tokens_used": 10000}
        result = normalize_tokens(usage, provider=TokenProvider.CODEX)

        assert result.total_tokens == 10000
        assert result.total_semantics == TokenTotalSemantics.REPORTED_TOTAL

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_codex_with_components(self):
        usage = {
            "input_tokens": 5000,
            "cached_input_tokens": 3000,
            "output_tokens": 2000,
        }
        result = normalize_tokens(usage, provider=TokenProvider.CODEX)

        assert result.fresh_input_tokens == 2000
        assert result.cache_read_tokens == 3000
        assert result.output_tokens == 2000
        assert result.total_tokens == 7000
        assert result.total_semantics == TokenTotalSemantics.EXCLUSIVE_COMPONENT_SUM

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_codex_delta_values(self):
        usage = {
            "input_tokens": 800,
            "cache_read_input_tokens": 200,
            "output_tokens": 400,
        }
        result = normalize_tokens(usage, provider=TokenProvider.CODEX)

        assert result.fresh_input_tokens == 600
        assert result.cache_read_tokens == 200
        assert result.output_tokens == 400
        assert result.total_tokens == 1200

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_codex_empty_usage(self):
        result = normalize_tokens({}, provider=TokenProvider.CODEX)
        assert result.total_tokens == 0
        assert result.precision == TokenPrecision.UNKNOWN


# ─── Qoder tests ─────────────────────────────────────────────────────────


class TestQoderNormalization:
    """测试 Qoder 用量归一化。

    语义：input_tokens 是本次请求输入规模，cache read/write 单独展示。
    """

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_qoder_with_cache(self):
        usage = {
            "input_tokens": 5000,
            "cache_read_input_tokens": 2000,
            "cache_creation_input_tokens": 500,
            "output_tokens": 1500,
        }
        result = normalize_tokens(usage, provider=TokenProvider.QODER)

        assert result.fresh_input_tokens == 5000
        assert result.cache_read_tokens == 2000
        assert result.cache_write_tokens == 500
        assert result.output_tokens == 1500
        assert result.total_tokens == 9000

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_qoder_no_cache(self):
        usage = {
            "input_tokens": 1000,
            "output_tokens": 500,
        }
        result = normalize_tokens(usage, provider=TokenProvider.QODER)

        assert result.fresh_input_tokens == 1000
        assert result.cache_read_tokens == 0
        assert result.cache_write_tokens == 0
        assert result.output_tokens == 500

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_qoder_cache_exceeds_input(self):
        usage = {
            "input_tokens": 100,
            "cache_read_input_tokens": 500,
            "cache_creation_input_tokens": 200,
            "output_tokens": 50,
        }
        result = normalize_tokens(usage, provider=TokenProvider.QODER)

        assert result.fresh_input_tokens == 100
        assert result.cache_read_tokens == 500
        assert result.cache_write_tokens == 200
        assert result.total_tokens == 850

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_qoder_estimated_precision(self):
        usage = {
            "input_tokens": 500,
            "output_tokens": 200,
        }
        result = normalize_tokens(usage, provider=TokenProvider.QODER)

        assert result.fresh_input_tokens == 500
        assert result.output_tokens == 200
        assert result.precision == TokenPrecision.PROVIDER_REPORTED

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_qoder_empty_usage(self):
        result = normalize_tokens({}, provider=TokenProvider.QODER)
        assert result.fresh_input_tokens == 0
        assert result.output_tokens == 0
        assert result.precision == TokenPrecision.ESTIMATED


# ─── Qoder SQLite tests ──────────────────────────────────────────────────


class TestQoderSQLiteNormalization:
    """测试 Qoder SQLite token_info 归一化。"""

    def test_sqlite_basic(self):
        token_info = {
            "prompt_tokens": 10000,
            "cached_tokens": 4000,
            "completion_tokens": 3000,
        }
        result = normalize_qoder_sqlite_unified(token_info)

        assert result.cache_read_tokens == 4000
        assert result.cache_write_tokens == 0
        assert result.output_tokens == 3000
        assert result.fresh_input_tokens == 10000
        assert result.total_tokens == 17000
        assert result.source_kind == TokenSourceKind.QODER_SQLITE_TOKEN_INFO

    def test_sqlite_empty(self):
        result = normalize_qoder_sqlite_unified({})
        assert result.fresh_input_tokens == 0
        assert result.cache_read_tokens == 0
        assert result.cache_write_tokens == 0
        assert result.output_tokens == 0
        assert result.total_tokens == 0


# ─── Provider inference tests ────────────────────────────────────────────


class TestProviderInference:
    """测试从 model 字符串推断 provider。"""

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_qwen_model_inferred(self):
        usage = {"input_tokens": 100, "output_tokens": 50}
        result = normalize_tokens(usage, model="qwen3.6-plus")

        assert result.fresh_input_tokens == 100
        assert result.output_tokens == 50

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_claude_model_inferred(self):
        usage = {"input_tokens": 100, "output_tokens": 50}
        result = normalize_tokens(usage, model="claude-sonnet-4-20250514")

        assert result.fresh_input_tokens == 100
        assert result.output_tokens == 50

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_gpt_model_inferred(self):
        usage = {"prompt_tokens": 100, "completion_tokens": 50}
        result = normalize_tokens(usage, model="gpt-4o")

        assert result.fresh_input_tokens == 100
        assert result.output_tokens == 50

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_unknown_model(self):
        usage = {"input_tokens": 100}
        result = normalize_tokens(usage, model="some-unknown-model")

        assert result.fresh_input_tokens == 100


# ─── Edge cases and fallback ────────────────────────────────────────────


class TestEdgeCases:
    """测试边界情况和 fallback。"""

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_empty_usage(self):
        result = normalize_tokens({})
        assert result.precision == TokenPrecision.UNKNOWN
        assert result.total_tokens == 0

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_none_usage(self):
        result = normalize_tokens(None)
        assert result.precision == TokenPrecision.UNKNOWN
        assert result.total_tokens == 0

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_unknown_provider_fallback(self):
        usage = {"some_custom_field": 42}
        result = normalize_tokens(usage, provider="unknown-provider")

        assert result.precision == TokenPrecision.UNKNOWN
        assert result.total_tokens == 0

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_generic_with_known_fields(self):
        usage = {"input_tokens": 100, "output_tokens": 50}
        result = normalize_tokens(usage, provider="unknown_provider")

        assert result.fresh_input_tokens == 100
        assert result.output_tokens == 50
        assert result.total_tokens == 150

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_large_values(self):
        usage = {
            "input_tokens": 10_000_000,
            "cache_read_input_tokens": 50_000_000,
            "cache_creation_input_tokens": 10_000_000,
            "output_tokens": 5_000_000,
        }
        result = normalize_tokens(usage, provider=TokenProvider.ANTHROPIC)
        assert result.total_tokens == 75_000_000


# ─── NormalizedTokenBreakdown defaults ───────────────────────────────────


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


# ─── Format helpers ──────────────────────────────────────────────────────


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
