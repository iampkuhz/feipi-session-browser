"""测试 token 归一化."""

import pytest

from session_browser.domain.models import (
    NormalizedTokenBreakdown,
    TokenSourceKind,
    TokenTotalSemantics,
)
from session_browser.domain.token_normalizer import (
    TokenPrecision,
    TokenProvider,
    format_tokens,
    normalize_qoder_sqlite_unified,
    normalize_tokens,
    precision_label,
)
from session_browser.domain.token_normalizers.codex_token_normalizer import (
    codex_is_duplicate_cumulative,
    codex_usage_delta,
    normalize_codex_usage,
)

# ─── Claude Code tests ───────────────────────────────────────────────────


class TestClaudeCodeNormalization:
    """测试 Claude Code 归一化.

    语义:input_tokens = fresh(新输入);cache buckets 是独立的;
    total = 4 个独立桶之和.
    """

    @pytest.mark.contract_case('DATA-PRESENTER-008')
    def test_basic_anthropic_usage(self) -> None:
        """Anthropic 基础 usage 应映射 fresh input/output 并用组件和作为 total."""
        usage = {
            'input_tokens': 1000,
            'output_tokens': 500,
        }
        result = normalize_tokens(usage, provider=TokenProvider.ANTHROPIC)

        assert result.fresh_input_tokens == usage['input_tokens']
        assert result.cache_read_tokens == 0
        assert result.cache_write_tokens == 0
        assert result.output_tokens == usage['output_tokens']
        assert result.total_tokens == usage['input_tokens'] + usage['output_tokens']
        assert result.total_semantics == TokenTotalSemantics.EXCLUSIVE_COMPONENT_SUM
        assert result.precision == TokenPrecision.PROVIDER_REPORTED

    @pytest.mark.contract_case('DATA-PRESENTER-008')
    def test_anthropic_with_cache(self) -> None:
        """Anthropic cache read/write 桶应独立计入 total, 不扣减 fresh input."""
        usage = {
            'input_tokens': 1000,
            'cache_read_input_tokens': 2000,
            'cache_creation_input_tokens': 500,
            'output_tokens': 300,
        }
        result = normalize_tokens(usage, provider=TokenProvider.ANTHROPIC)

        assert result.fresh_input_tokens == usage['input_tokens']
        assert result.cache_read_tokens == usage['cache_read_input_tokens']
        assert result.cache_write_tokens == usage['cache_creation_input_tokens']
        assert result.output_tokens == usage['output_tokens']
        assert result.total_tokens == sum(usage.values())

    @pytest.mark.contract_case('DATA-PRESENTER-008')
    def test_qwen_anthropic_compatible(self) -> None:
        """Qwen Anthropic-compatible usage 应沿用 Claude cache 字段语义."""
        usage = {
            'input_tokens': 25728,
            'cache_read_input_tokens': 0,
            'cache_creation_input_tokens': 27473,
            'output_tokens': 275,
        }
        result = normalize_tokens(usage, provider=TokenProvider.QWEN_ANTHROPIC_COMPATIBLE)

        assert result.fresh_input_tokens == usage['input_tokens']
        assert result.cache_read_tokens == usage['cache_read_input_tokens']
        assert result.cache_write_tokens == usage['cache_creation_input_tokens']
        assert result.output_tokens == usage['output_tokens']

    @pytest.mark.contract_case('DATA-PRESENTER-008')
    def test_all_fields_are_int(self) -> None:
        """归一化后的 Claude token 桶应始终暴露为整数, 便于 UI 聚合."""
        usage = {'input_tokens': 100, 'output_tokens': 50}
        result = normalize_tokens(usage, provider=TokenProvider.ANTHROPIC)

        assert isinstance(result.fresh_input_tokens, int)
        assert isinstance(result.cache_read_tokens, int)
        assert isinstance(result.cache_write_tokens, int)
        assert isinstance(result.output_tokens, int)
        assert isinstance(result.total_tokens, int)

    @pytest.mark.contract_case('DATA-PRESENTER-008')
    def test_empty_usage(self) -> None:
        """空 Anthropic usage 应归零而不是产生缺字段异常."""
        result = normalize_tokens({}, provider=TokenProvider.ANTHROPIC)
        assert result.fresh_input_tokens == 0
        assert result.cache_read_tokens == 0
        assert result.cache_write_tokens == 0
        assert result.output_tokens == 0
        assert result.total_tokens == 0


# ─── OpenAI tests ────────────────────────────────────────────────────────


class TestOpenAINormalization:
    """测试 OpenAI 用量归一化."""

    @pytest.mark.contract_case('DATA-PRESENTER-008')
    def test_basic_openai_usage(self) -> None:
        """OpenAI legacy prompt/completion 字段应映射为 fresh input 和 output."""
        usage = {
            'prompt_tokens': 1000,
            'completion_tokens': 500,
        }
        result = normalize_tokens(usage, provider=TokenProvider.OPENAI)

        assert result.fresh_input_tokens == usage['prompt_tokens']
        assert result.output_tokens == usage['completion_tokens']
        assert result.cache_read_tokens == 0

    @pytest.mark.contract_case('DATA-PRESENTER-008')
    def test_openai_with_cached_tokens(self) -> None:
        """OpenAI cached prompt tokens 应从 fresh input 中扣除并作为 cache read 展示."""
        usage = {
            'prompt_tokens': 5000,
            'completion_tokens': 300,
            'prompt_tokens_details': {'cached_tokens': 3000},
        }
        result = normalize_tokens(usage, provider=TokenProvider.OPENAI)

        cached_tokens = usage['prompt_tokens_details']['cached_tokens']
        assert result.cache_read_tokens == cached_tokens
        assert result.fresh_input_tokens == usage['prompt_tokens'] - cached_tokens
        assert result.total_tokens == usage['prompt_tokens'] + usage['completion_tokens']

    @pytest.mark.contract_case('DATA-PRESENTER-008')
    def test_openai_with_reasoning_tokens(self) -> None:
        """OpenAI reasoning tokens 是 completion 明细, 不应从 output tokens 中扣减."""
        usage = {
            'prompt_tokens': 1000,
            'completion_tokens': 800,
            'completion_tokens_details': {'reasoning_tokens': 300},
        }
        result = normalize_tokens(usage, provider=TokenProvider.OPENAI)

        assert result.output_tokens == usage['completion_tokens']

    @pytest.mark.contract_case('DATA-PRESENTER-008')
    def test_openai_new_format(self) -> None:
        """OpenAI responses input/output 新格式应保持 cached_tokens 子集语义."""
        usage = {
            'input_tokens': 4000,
            'output_tokens': 600,
            'input_tokens_details': {'cached_tokens': 2000},
            'output_tokens_details': {'reasoning_tokens': 200},
        }
        result = normalize_tokens(usage, provider=TokenProvider.OPENAI)

        cached_tokens = usage['input_tokens_details']['cached_tokens']
        assert result.fresh_input_tokens == usage['input_tokens'] - cached_tokens
        assert result.cache_read_tokens == cached_tokens
        assert result.output_tokens == usage['output_tokens']


# ─── Codex tests ─────────────────────────────────────────────────────────


class TestCodexNormalization:
    """测试 Codex 用量归一化.

    语义:cached_input_tokens 是 input_tokens 的子集;Fresh 是非缓存输入.
    """

    @pytest.mark.contract_case('DATA-PRESENTER-008')
    def test_codex_total_only(self) -> None:
        """Codex 仅上报 tokens_used 时应保留 reported total 语义."""
        usage = {'tokens_used': 10000}
        result = normalize_tokens(usage, provider=TokenProvider.CODEX)

        assert result.total_tokens == usage['tokens_used']
        assert result.total_semantics == TokenTotalSemantics.REPORTED_TOTAL

    @pytest.mark.contract_case('DATA-PRESENTER-008')
    def test_codex_with_components(self) -> None:
        """Codex 组件 usage 应把 cached input 视为 input 子集, 避免重复计算."""
        usage = {
            'input_tokens': 5000,
            'cached_input_tokens': 3000,
            'output_tokens': 2000,
        }
        result = normalize_tokens(usage, provider=TokenProvider.CODEX)

        assert result.fresh_input_tokens == usage['input_tokens'] - usage['cached_input_tokens']
        assert result.cache_read_tokens == usage['cached_input_tokens']
        assert result.output_tokens == usage['output_tokens']
        assert result.total_tokens == usage['input_tokens'] + usage['output_tokens']
        assert result.total_semantics == TokenTotalSemantics.EXCLUSIVE_COMPONENT_SUM

    @pytest.mark.contract_case('DATA-PRESENTER-008')
    def test_codex_cached_input_subset_does_not_double_count_total(self) -> None:
        """Codex cached_input_tokens 大于零时 total 仍只由 input 加 output 组成."""
        usage = {
            'input_tokens': 100,
            'cached_input_tokens': 40,
            'output_tokens': 10,
        }
        result = normalize_tokens(usage, provider=TokenProvider.CODEX)

        assert result.fresh_input_tokens == usage['input_tokens'] - usage['cached_input_tokens']
        assert result.cache_read_tokens == usage['cached_input_tokens']
        assert result.output_tokens == usage['output_tokens']
        assert result.total_tokens == usage['input_tokens'] + usage['output_tokens']

    @pytest.mark.contract_case('DATA-PRESENTER-008')
    def test_codex_delta_values(self) -> None:
        """Codex delta 字段应把 cache_read_input_tokens 当作 input 子集计算 fresh."""
        usage = {
            'input_tokens': 800,
            'cache_read_input_tokens': 200,
            'output_tokens': 400,
        }
        result = normalize_tokens(usage, provider=TokenProvider.CODEX)

        assert result.fresh_input_tokens == usage['input_tokens'] - usage['cache_read_input_tokens']
        assert result.cache_read_tokens == usage['cache_read_input_tokens']
        assert result.output_tokens == usage['output_tokens']
        assert result.total_tokens == usage['input_tokens'] + usage['output_tokens']

    def test_codex_specific_normalizer_keeps_reasoning_in_output(self) -> None:
        """Codex 专用归一化应保留 reasoning_output_tokens 原始字段供追溯."""
        usage = {
            'input_tokens': 4000,
            'cached_input_tokens': 2000,
            'output_tokens': 600,
            'reasoning_output_tokens': 200,
        }
        result = normalize_codex_usage(usage)

        cached_tokens = usage['cached_input_tokens']
        assert result.fresh_input_tokens == usage['input_tokens'] - cached_tokens
        assert result.cache_read_tokens == cached_tokens
        assert result.output_tokens == usage['output_tokens']
        assert result.raw_fields['reasoning_output_tokens'] == usage['reasoning_output_tokens']

    def test_codex_specific_normalizer_reasoning_only_fallback(self) -> None:
        """Codex 缺 output_tokens 时应使用 reasoning_output_tokens 作为 output fallback."""
        usage = {
            'input_tokens': 1000,
            'cached_input_tokens': 500,
            'reasoning_output_tokens': 80,
        }
        result = normalize_codex_usage(usage)

        assert result.fresh_input_tokens == usage['input_tokens'] - usage['cached_input_tokens']
        assert result.cache_read_tokens == usage['cached_input_tokens']
        assert result.output_tokens == usage['reasoning_output_tokens']

    def test_codex_cumulative_delta_and_duplicate_detection(self) -> None:
        """Codex 累计快照 delta 和重复检测应按字段差值保护增量视图."""
        previous = {
            'input_tokens': 5000,
            'cached_input_tokens': 3000,
            'output_tokens': 100,
            'reasoning_output_tokens': 20,
            'total_tokens': 5100,
        }
        current = {
            'input_tokens': 7000,
            'cached_input_tokens': 3500,
            'output_tokens': 160,
            'reasoning_output_tokens': 40,
            'total_tokens': 7160,
        }

        delta = codex_usage_delta(current, previous)

        assert delta['input_tokens'] == current['input_tokens'] - previous['input_tokens']
        assert delta['cached_input_tokens'] == (
            current['cached_input_tokens'] - previous['cached_input_tokens']
        )
        assert delta['output_tokens'] == current['output_tokens'] - previous['output_tokens']
        assert delta['reasoning_output_tokens'] == (
            current['reasoning_output_tokens'] - previous['reasoning_output_tokens']
        )
        assert codex_is_duplicate_cumulative(current, current)

    @pytest.mark.contract_case('DATA-PRESENTER-008')
    def test_codex_empty_usage(self) -> None:
        """空 Codex usage 应产生 unknown precision 且 total 为零."""
        result = normalize_tokens({}, provider=TokenProvider.CODEX)
        assert result.total_tokens == 0
        assert result.precision == TokenPrecision.UNKNOWN


# ─── Qoder tests ─────────────────────────────────────────────────────────


class TestQoderNormalization:
    """测试 Qoder 用量归一化.

    语义:input_tokens 是本次请求输入规模,cache read/write 单独展示.
    """

    @pytest.mark.contract_case('DATA-PRESENTER-008')
    def test_qoder_with_cache(self) -> None:
        """Qoder provider usage 应把 request input 与 cache read/write 分桶相加展示."""
        usage = {
            'input_tokens': 5000,
            'cache_read_input_tokens': 2000,
            'cache_creation_input_tokens': 500,
            'output_tokens': 1500,
        }
        result = normalize_tokens(usage, provider=TokenProvider.QODER)

        assert result.fresh_input_tokens == usage['input_tokens']
        assert result.cache_read_tokens == usage['cache_read_input_tokens']
        assert result.cache_write_tokens == usage['cache_creation_input_tokens']
        assert result.output_tokens == usage['output_tokens']
        assert result.total_tokens == sum(usage.values())

    @pytest.mark.contract_case('DATA-PRESENTER-008')
    def test_qoder_no_cache(self) -> None:
        """Qoder 无 cache 字段时应保持 cache read/write 为零."""
        usage = {
            'input_tokens': 1000,
            'output_tokens': 500,
        }
        result = normalize_tokens(usage, provider=TokenProvider.QODER)

        assert result.fresh_input_tokens == usage['input_tokens']
        assert result.cache_read_tokens == 0
        assert result.cache_write_tokens == 0
        assert result.output_tokens == usage['output_tokens']

    @pytest.mark.contract_case('DATA-PRESENTER-008')
    def test_qoder_cache_exceeds_input(self) -> None:
        """Qoder cache 可大于 request input, 归一化不得扣减 fresh input."""
        usage = {
            'input_tokens': 100,
            'cache_read_input_tokens': 500,
            'cache_creation_input_tokens': 200,
            'output_tokens': 50,
        }
        result = normalize_tokens(usage, provider=TokenProvider.QODER)

        assert result.fresh_input_tokens == usage['input_tokens']
        assert result.cache_read_tokens == usage['cache_read_input_tokens']
        assert result.cache_write_tokens == usage['cache_creation_input_tokens']
        assert result.total_tokens == sum(usage.values())

    @pytest.mark.contract_case('DATA-PRESENTER-008')
    def test_qoder_estimated_precision(self) -> None:
        """Qoder 有 provider usage 时应标记为 provider_reported precision."""
        usage = {
            'input_tokens': 500,
            'output_tokens': 200,
        }
        result = normalize_tokens(usage, provider=TokenProvider.QODER)

        assert result.fresh_input_tokens == usage['input_tokens']
        assert result.output_tokens == usage['output_tokens']
        assert result.precision == TokenPrecision.PROVIDER_REPORTED

    @pytest.mark.contract_case('DATA-PRESENTER-008')
    def test_qoder_empty_usage(self) -> None:
        """空 Qoder usage 应进入估算 precision 且 token 桶归零."""
        result = normalize_tokens({}, provider=TokenProvider.QODER)
        assert result.fresh_input_tokens == 0
        assert result.output_tokens == 0
        assert result.precision == TokenPrecision.ESTIMATED


# ─── Qoder SQLite tests ──────────────────────────────────────────────────


class TestQoderSQLiteNormalization:
    """测试 Qoder SQLite token_info 归一化."""

    def test_sqlite_basic(self) -> None:
        """Qoder SQLite token_info 应映射 prompt/cached/completion 到统一 token 桶."""
        token_info = {
            'prompt_tokens': 10000,
            'cached_tokens': 4000,
            'completion_tokens': 3000,
        }
        result = normalize_qoder_sqlite_unified(token_info)

        assert result.cache_read_tokens == token_info['cached_tokens']
        assert result.cache_write_tokens == 0
        assert result.output_tokens == token_info['completion_tokens']
        assert result.fresh_input_tokens == token_info['prompt_tokens']
        assert result.total_tokens == sum(token_info.values())
        assert result.source_kind == TokenSourceKind.QODER_SQLITE_TOKEN_INFO

    def test_sqlite_empty(self) -> None:
        """空 Qoder SQLite token_info 应全部归零并保持可展示."""
        result = normalize_qoder_sqlite_unified({})
        assert result.fresh_input_tokens == 0
        assert result.cache_read_tokens == 0
        assert result.cache_write_tokens == 0
        assert result.output_tokens == 0
        assert result.total_tokens == 0


# ─── Provider inference tests ────────────────────────────────────────────


class TestProviderInference:
    """测试从 model 字符串推断 provider."""

    @pytest.mark.contract_case('DATA-PRESENTER-008')
    def test_qwen_model_inferred(self) -> None:
        """Qwen 模型名应推断为 Anthropic-compatible provider 并保留输入输出."""
        usage = {'input_tokens': 100, 'output_tokens': 50}
        result = normalize_tokens(usage, model='qwen3.6-plus')

        assert result.fresh_input_tokens == usage['input_tokens']
        assert result.output_tokens == usage['output_tokens']

    @pytest.mark.contract_case('DATA-PRESENTER-008')
    def test_claude_model_inferred(self) -> None:
        """Claude 模型名应推断为 Anthropic provider 并读取 input/output 字段."""
        usage = {'input_tokens': 100, 'output_tokens': 50}
        result = normalize_tokens(usage, model='claude-sonnet-4-20250514')

        assert result.fresh_input_tokens == usage['input_tokens']
        assert result.output_tokens == usage['output_tokens']

    @pytest.mark.contract_case('DATA-PRESENTER-008')
    def test_gpt_model_inferred(self) -> None:
        """GPT 模型名应推断为 OpenAI provider 并读取 prompt/completion 字段."""
        usage = {'prompt_tokens': 100, 'completion_tokens': 50}
        result = normalize_tokens(usage, model='gpt-4o')

        assert result.fresh_input_tokens == usage['prompt_tokens']
        assert result.output_tokens == usage['completion_tokens']

    @pytest.mark.contract_case('DATA-PRESENTER-008')
    def test_unknown_model(self) -> None:
        """未知模型名应使用 generic fallback 保留已知 input 字段."""
        usage = {'input_tokens': 100}
        result = normalize_tokens(usage, model='some-unknown-model')

        assert result.fresh_input_tokens == usage['input_tokens']


# ─── Edge cases and fallback ────────────────────────────────────────────


class TestEdgeCases:
    """测试边界情况和 fallback."""

    @pytest.mark.contract_case('DATA-PRESENTER-008')
    def test_empty_usage(self) -> None:
        """未指定 provider 的空 usage 应返回 unknown precision 和零 total."""
        result = normalize_tokens({})
        assert result.precision == TokenPrecision.UNKNOWN
        assert result.total_tokens == 0

    @pytest.mark.contract_case('DATA-PRESENTER-008')
    def test_none_usage(self) -> None:
        """None usage 应被视为空输入, 不触发归一化异常."""
        result = normalize_tokens(None)
        assert result.precision == TokenPrecision.UNKNOWN
        assert result.total_tokens == 0

    @pytest.mark.contract_case('DATA-PRESENTER-008')
    def test_unknown_provider_fallback(self) -> None:
        """未知 provider 且无标准字段时应安全返回零 total."""
        usage = {'some_custom_field': 42}
        result = normalize_tokens(usage, provider='unknown-provider')

        assert result.precision == TokenPrecision.UNKNOWN
        assert result.total_tokens == 0

    @pytest.mark.contract_case('DATA-PRESENTER-008')
    def test_generic_with_known_fields(self) -> None:
        """未知 provider 但含标准 input/output 字段时应走 generic 归一化."""
        usage = {'input_tokens': 100, 'output_tokens': 50}
        result = normalize_tokens(usage, provider='unknown_provider')

        assert result.fresh_input_tokens == usage['input_tokens']
        assert result.output_tokens == usage['output_tokens']
        assert result.total_tokens == sum(usage.values())

    @pytest.mark.contract_case('DATA-PRESENTER-008')
    def test_large_values(self) -> None:
        """大 token 值应按整数精确聚合, 不溢出或截断."""
        usage = {
            'input_tokens': 10_000_000,
            'cache_read_input_tokens': 50_000_000,
            'cache_creation_input_tokens': 10_000_000,
            'output_tokens': 5_000_000,
        }
        result = normalize_tokens(usage, provider=TokenProvider.ANTHROPIC)
        assert result.total_tokens == sum(usage.values())


# ─── NormalizedTokenBreakdown defaults ───────────────────────────────────


class TestNormalizedTokenBreakdownDefaults:
    """测试 NormalizedTokenBreakdown 默认值."""

    def test_all_defaults_zero(self) -> None:
        """NormalizedTokenBreakdown 默认数值桶应全部为零."""
        bd = NormalizedTokenBreakdown()
        assert bd.fresh_input_tokens == 0
        assert bd.cache_read_tokens == 0
        assert bd.cache_write_tokens == 0
        assert bd.output_tokens == 0
        assert bd.total_tokens == 0

    def test_metadata_defaults(self) -> None:
        """NormalizedTokenBreakdown 默认 metadata 应保持 unknown/source 空状态."""
        bd = NormalizedTokenBreakdown()
        assert bd.precision == TokenPrecision.UNKNOWN
        assert bd.total_semantics == TokenTotalSemantics.EXCLUSIVE_COMPONENT_SUM
        assert bd.source_kind == TokenSourceKind.UNKNOWN
        assert bd.notes == []
        assert bd.raw_fields == {}


# ─── Format helpers ──────────────────────────────────────────────────────


class TestFormatHelpers:
    """测试格式化辅助函数."""

    @pytest.mark.contract_case('DATA-PRESENTER-008')
    def test_format_tokens_none(self) -> None:
        """None token 值应格式化为 UI 占位符."""
        assert format_tokens(None) == '—'

    @pytest.mark.contract_case('DATA-PRESENTER-008')
    def test_format_tokens_small(self) -> None:
        """小 token 值应原样格式化, 不追加单位."""
        assert format_tokens(500) == '500'

    @pytest.mark.contract_case('DATA-PRESENTER-008')
    def test_format_tokens_k(self) -> None:
        """千级 token 值应格式化为 K 单位."""
        assert format_tokens(1500) == '1.5K'

    @pytest.mark.contract_case('DATA-PRESENTER-008')
    def test_format_tokens_m(self) -> None:
        """百万级 token 值应格式化为 M 单位."""
        assert format_tokens(1500000) == '1.5M'

    @pytest.mark.contract_case('DATA-PRESENTER-008')
    def test_precision_label(self) -> None:
        """Token precision 枚举应稳定映射为展示标签."""
        assert precision_label(TokenPrecision.EXACT) == 'exact'
        assert precision_label(TokenPrecision.PROVIDER_REPORTED) == 'provider_reported'
        assert precision_label(TokenPrecision.ESTIMATED) == 'estimated'
        assert precision_label(TokenPrecision.UNKNOWN) == 'unavailable'
