"""Token breakdown fixture tests for session detail presenter.

验证 token breakdown 数据结构和计算逻辑:
- token breakdown 数据结构正确 (所有字段类型正确)
- input/output/cache token 分类正确
- round 级 token 聚合正确
- session 级 token 总计正确
"""
import pytest
import json
import os
import sys

# Ensure src is importable
SB_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if SB_ROOT not in sys.path:
    sys.path.insert(0, os.path.join(SB_ROOT, "src"))

from session_browser.domain.models import (
    TokenBreakdown,
    TokenPrecision,
    TokenProvider,
    ChatMessage,
    ConversationRound,
)


# ─── Fixtures ───────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def token_breakdown_fixture():
    """Load token breakdown scenario fixture data."""
    fixture_path = os.path.join(
        SB_ROOT, "tests", "fixtures", "session_detail", "token_breakdown_scenario.json"
    )
    with open(fixture_path, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def fixture_messages(token_breakdown_fixture):
    """Convert fixture messages to ChatMessage objects."""
    msgs = []
    for m in token_breakdown_fixture["messages"]:
        msgs.append(ChatMessage(
            role=m["role"],
            content=m["content"],
            timestamp=m["timestamp"],
            model=m.get("model", ""),
            tool_calls=m.get("tool_calls", []),
            usage=m.get("usage"),
            llm_call_id=m.get("llm_call_id", ""),
            llm_status=m.get("llm_status", "ok"),
            stop_reason=m.get("stop_reason", ""),
        ))
    return msgs


# ─── Test 1: Token breakdown 数据结构正确 ──────────────────────────────

class TestTokenBreakdownStructure:
    """验证 token breakdown 数据结构正确."""

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_full_breakdown_all_fields_present(self, token_breakdown_fixture):
        """full_breakdown 场景: 所有 breakdown 字段都应存在."""
        scenario = token_breakdown_fixture["token_breakdown_scenarios"][0]
        assert scenario["name"] == "full_breakdown"
        data = scenario["data"]

        # 所有字段都应非 None
        assert data["input_fresh"] is not None
        assert data["input_cache_read"] is not None
        assert data["input_cache_write"] is not None
        assert data["output_visible"] is not None
        assert data["output_reasoning"] is not None
        assert data["output_thinking"] is not None
        assert data["tool_definition_input"] is not None
        assert data["tool_call_output"] is not None
        assert data["tool_result_input"] is not None
        assert data["total_input"] is not None
        assert data["total_output"] is not None
        assert data["precision"] is not None
        assert data["provider"] is not None

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_minimal_breakdown_nullable_fields(self, token_breakdown_fixture):
        """minimal_breakdown 场景: 可选字段应为 None."""
        scenario = token_breakdown_fixture["token_breakdown_scenarios"][1]
        data = scenario["data"]

        assert data["input_fresh"] is not None
        assert data["output_visible"] is not None
        # 这些字段应显式为 None
        assert data["input_cache_read"] is None
        assert data["input_cache_write"] is None
        assert data["output_reasoning"] is None
        assert data["output_thinking"] is None
        assert data["tool_definition_input"] is None
        assert data["tool_call_output"] is None
        assert data["tool_result_input"] is None

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_token_breakdown_dataclass_instantiation(self):
        """TokenBreakdown dataclass 可以正确实例化."""
        tb = TokenBreakdown(
            input_fresh=5000,
            input_cache_read=10000,
            input_cache_write=3000,
            output_visible=800,
            output_reasoning=200,
            output_thinking=50,
            precision=TokenPrecision.PROVIDER_REPORTED,
            provider=TokenProvider.ANTHROPIC,
        )
        assert tb.input_fresh == 5000
        assert tb.input_cache_read == 10000
        assert tb.input_cache_write == 3000
        assert tb.output_visible == 800
        assert tb.output_reasoning == 200
        assert tb.output_thinking == 50
        assert tb.precision == TokenPrecision.PROVIDER_REPORTED
        assert tb.provider == TokenProvider.ANTHROPIC

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_token_breakdown_default_values(self):
        """TokenBreakdown 默认值应为 None/UNKNOWN."""
        tb = TokenBreakdown()
        assert tb.input_fresh is None
        assert tb.input_cache_read is None
        assert tb.input_cache_write is None
        assert tb.output_visible is None
        assert tb.output_reasoning is None
        assert tb.output_thinking is None
        assert tb.tool_definition_input is None
        assert tb.tool_call_output is None
        assert tb.tool_result_input is None
        assert tb.total_input is None
        assert tb.total_output is None
        assert tb.precision == TokenPrecision.UNKNOWN
        assert tb.provider is None


# ─── Test 2: input/output/cache token 分类 ──────────────────────────────

class TestTokenCategoryClassification:
    """验证 input/output/cache token 分类."""

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_input_side_categories(self, token_breakdown_fixture):
        """Input 侧应包含 fresh、cache_read、cache_write 三个子分类."""
        scenario = token_breakdown_fixture["token_breakdown_scenarios"][0]
        data = scenario["data"]

        # input_fresh 是新鲜输入
        assert data["input_fresh"] == 5000
        # input_cache_read 是缓存读取
        assert data["input_cache_read"] == 10000
        # input_cache_write 是缓存写入
        assert data["input_cache_write"] == 3000

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_output_side_categories(self, token_breakdown_fixture):
        """Output 侧应包含 visible、reasoning、thinking 三个子分类."""
        scenario = token_breakdown_fixture["token_breakdown_scenarios"][0]
        data = scenario["data"]

        # output_visible 是可见输出
        assert data["output_visible"] == 800
        # output_reasoning 是推理输出
        assert data["output_reasoning"] == 200
        # output_thinking 是 thinking 输出
        assert data["output_thinking"] == 50

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_tool_related_categories(self, token_breakdown_fixture):
        """Tool 相关应包含 definition_input、call_output、result_input."""
        scenario = token_breakdown_fixture["token_breakdown_scenarios"][0]
        data = scenario["data"]

        assert data["tool_definition_input"] == 1000
        assert data["tool_call_output"] == 500
        assert data["tool_result_input"] == 1500

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_precision_values(self, token_breakdown_fixture):
        """不同场景应使用正确的 precision 值."""
        scenarios = token_breakdown_fixture["token_breakdown_scenarios"]

        full = scenarios[0]
        assert full["data"]["precision"] == TokenPrecision.PROVIDER_REPORTED

        minimal = scenarios[1]
        assert minimal["data"]["precision"] == TokenPrecision.ESTIMATED

        codex = scenarios[2]
        assert codex["data"]["precision"] == TokenPrecision.EXACT

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_provider_values(self, token_breakdown_fixture):
        """不同场景应使用正确的 provider 值."""
        scenarios = token_breakdown_fixture["token_breakdown_scenarios"]

        full = scenarios[0]
        assert full["data"]["provider"] == TokenProvider.ANTHROPIC

        codex = scenarios[2]
        assert codex["data"]["provider"] == TokenProvider.OPENAI

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_chat_message_usage_fields_map_to_categories(self, fixture_messages):
        """ChatMessage.usage 字段应映射到正确的 token 分类."""
        # Round 1 assistant (msg-main-002)
        assistant_r1 = fixture_messages[1]
        assert assistant_r1.usage is not None
        assert assistant_r1.usage["input_tokens"] == 8000
        assert assistant_r1.usage["output_tokens"] == 100
        assert assistant_r1.usage["cache_read_input_tokens"] == 0
        assert assistant_r1.usage["cache_creation_input_tokens"] == 5000

        # Round 2 assistant (msg-main-004)
        assistant_r2 = fixture_messages[3]
        assert assistant_r2.usage is not None
        assert assistant_r2.usage["input_tokens"] == 12000
        assert assistant_r2.usage["output_tokens"] == 800
        assert assistant_r2.usage["cache_read_input_tokens"] == 10000
        assert assistant_r2.usage["cache_creation_input_tokens"] == 3000


# ─── Test 3: round 级 token 聚合 ────────────────────────────────────────

class TestRoundLevelTokenAggregation:
    """验证 round 级 token 聚合正确."""

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_round1_token_counts(self, fixture_messages):
        """Round 1 (msg-main-002) 的 token 计数正确."""
        assistant = fixture_messages[1]
        usage = assistant.usage
        assert usage is not None

        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        cache_read = usage.get("cache_read_input_tokens", 0)
        cache_write = usage.get("cache_creation_input_tokens", 0)

        assert input_tokens == 8000
        assert output_tokens == 100
        assert cache_read == 0
        assert cache_write == 5000
        # Round 总 tokens
        assert input_tokens + output_tokens + cache_read + cache_write == 13100

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_round2_token_counts(self, fixture_messages):
        """Round 2 (msg-main-004) 的 token 计数正确."""
        assistant = fixture_messages[3]
        usage = assistant.usage
        assert usage is not None

        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        cache_read = usage.get("cache_read_input_tokens", 0)
        cache_write = usage.get("cache_creation_input_tokens", 0)

        assert input_tokens == 12000
        assert output_tokens == 800
        assert cache_read == 10000
        assert cache_write == 3000
        assert input_tokens + output_tokens + cache_read + cache_write == 25800

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_round3_token_counts(self, fixture_messages):
        """Round 3 (msg-main-006) 的 token 计数正确."""
        assistant = fixture_messages[5]
        usage = assistant.usage
        assert usage is not None

        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        cache_read = usage.get("cache_read_input_tokens", 0)
        cache_write = usage.get("cache_creation_input_tokens", 0)

        assert input_tokens == 25000
        assert output_tokens == 2100
        assert cache_read == 18000
        assert cache_write == 4000
        assert input_tokens + output_tokens + cache_read + cache_write == 49100

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_token_breakdown_compute_totals(self):
        """TokenBreakdown.compute_totals() 应正确计算总计."""
        tb = TokenBreakdown(
            input_fresh=5000,
            input_cache_read=10000,
            input_cache_write=3000,
            output_visible=800,
            output_reasoning=200,
            output_thinking=50,
        )
        tb.compute_totals()

        assert tb.total_input == 18000  # 5000 + 10000 + 3000
        assert tb.total_output == 1050   # 800 + 200 + 50

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_token_breakdown_compute_totals_with_none(self):
        """TokenBreakdown.compute_totals() 应正确处理 None 值."""
        tb = TokenBreakdown(
            input_fresh=3000,
            input_cache_read=None,
            input_cache_write=None,
            output_visible=500,
            output_reasoning=None,
            output_thinking=None,
        )
        tb.compute_totals()

        assert tb.total_input == 3000  # 只有 input_fresh
        assert tb.total_output == 500   # 只有 output_visible

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_token_breakdown_compute_totals_all_none(self):
        """TokenBreakdown.compute_totals() 全 None 时不设置总计."""
        tb = TokenBreakdown()
        tb.compute_totals()

        assert tb.total_input is None
        assert tb.total_output is None


# ─── Test 4: session 级 token 总计 ─────────────────────────────────────

class TestSessionLevelTokenTotals:
    """验证 session 级 token 总计正确."""

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_session_summary_token_fields(self, token_breakdown_fixture):
        """session 级摘要应包含所有 token 字段."""
        session = token_breakdown_fixture["session"]

        assert session["input_tokens"] == 45000
        assert session["output_tokens"] == 3000
        assert session["cached_input_tokens"] == 28000
        assert session["cached_output_tokens"] == 12000

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_session_token_breakdown(self, token_breakdown_fixture):
        """session 级 token breakdown 应包含完整分类."""
        tb = token_breakdown_fixture["session"]["token_breakdown"]

        assert tb["input_fresh"] == 17000
        assert tb["input_cache_read"] == 28000
        assert tb["input_cache_write"] == 12000
        assert tb["output_visible"] == 2500
        assert tb["output_reasoning"] == 400
        assert tb["output_thinking"] == 100
        assert tb["total_input"] == 57000
        assert tb["total_output"] == 3000
        assert tb["precision"] == "provider-reported"
        assert tb["provider"] == "anthropic"

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_session_total_rounds_aggregation(self, fixture_messages):
        """所有 round 的 token 聚合应等于 session 总计 (按 fixture 数据)."""
        # 获取所有 assistant messages
        assistants = [m for m in fixture_messages if m.role == "assistant" and m.usage]

        total_input = sum(m.usage.get("input_tokens", 0) for m in assistants)
        total_output = sum(m.usage.get("output_tokens", 0) for m in assistants)
        total_cache_read = sum(m.usage.get("cache_read_input_tokens", 0) for m in assistants)
        total_cache_write = sum(m.usage.get("cache_creation_input_tokens", 0) for m in assistants)

        # Round 聚合
        assert total_input == 45000   # 8000 + 12000 + 25000
        assert total_output == 3000   # 100 + 800 + 2100
        assert total_cache_read == 28000  # 0 + 10000 + 18000
        assert total_cache_write == 12000  # 5000 + 3000 + 4000

        # 全局总计
        grand_total = total_input + total_output + total_cache_read + total_cache_write
        assert grand_total == 88000

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_session_token_breakdown_from_fixture_dataclass(self, token_breakdown_fixture):
        """从 fixture 数据构建 TokenBreakdown dataclass 后计算 totals."""
        tb_data = token_breakdown_fixture["session"]["token_breakdown"]
        tb = TokenBreakdown(
            input_fresh=tb_data["input_fresh"],
            input_cache_read=tb_data["input_cache_read"],
            input_cache_write=tb_data["input_cache_write"],
            output_visible=tb_data["output_visible"],
            output_reasoning=tb_data["output_reasoning"],
            output_thinking=tb_data["output_thinking"],
            tool_definition_input=tb_data["tool_definition_input"],
            tool_call_output=tb_data["tool_call_output"],
            tool_result_input=tb_data["tool_result_input"],
            precision=tb_data["precision"],
            provider=tb_data["provider"],
        )
        tb.compute_totals()

        assert tb.total_input == tb_data["total_input"]
        assert tb.total_output == tb_data["total_output"]
