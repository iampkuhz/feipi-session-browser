"""Subagent fixture tests for session detail presenter.

验证 subagent 在 session detail 中正确显示:
- subagent 在 build_llm_calls 中被正确构建 (scope="subagent")
- 成功和失败的 subagent 状态正确区分
- subagent 的 token 和执行时间正确聚合
- 嵌套 subagent 层次结构被正确处理
- assign_interactions_to_rounds 正确将 subagent 分配到对应 round
"""
import pytest
import json
import os
import sys

# 确保 src 可导入
SB_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if SB_ROOT not in sys.path:
    sys.path.insert(0, os.path.join(SB_ROOT, "src"))

from session_browser.domain.models import (
    ChatMessage,
    ToolCall,
)
from session_browser.web.presenters.session_detail import (
    build_rounds,
    build_llm_calls,
    assign_interactions_to_rounds,
    _build_subagent_interactions,
)


# ─── Fixtures ───────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def subagent_fixture():
    """Load subagent scenario fixture data."""
    fixture_path = os.path.join(
        SB_ROOT, "tests", "fixtures", "session_detail", "subagent_scenario.json"
    )
    with open(fixture_path, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def fixture_messages(subagent_fixture):
    """Convert fixture messages to ChatMessage objects."""
    msgs = []
    for m in subagent_fixture["messages"]:
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


@pytest.fixture(scope="module")
def fixture_tool_calls(subagent_fixture):
    """Convert fixture tool_calls to ToolCall objects."""
    tcs = []
    for tc in subagent_fixture["tool_calls"]:
        tcs.append(ToolCall(
            name=tc["name"],
            parameters=tc.get("parameters", {}),
            result=tc.get("result", ""),
            status=tc.get("status", "completed"),
            duration_ms=tc.get("duration_ms", 0),
            timestamp=tc.get("timestamp", ""),
            exit_code=tc.get("exit_code"),
            error_message=tc.get("error_message", ""),
            tool_use_id=tc.get("tool_use_id", ""),
            scope=tc.get("scope", "main"),
            llm_call_count=tc.get("llm_call_count", 0),
            llm_error_count=tc.get("llm_error_count", 0),
            subagent_id=tc.get("subagent_id", ""),
            subagent_summary=tc.get("subagent_summary", {}),
        ))
    # Also include subagent internal tool calls
    for run in subagent_fixture.get("subagent_runs", []):
        for tc in run.get("tool_calls", []):
            tcs.append(ToolCall(
                name=tc["name"],
                parameters=tc.get("parameters", {}),
                result=tc.get("result", ""),
                status=tc.get("status", "completed"),
                duration_ms=tc.get("duration_ms", 0),
                timestamp=tc.get("timestamp", ""),
                exit_code=tc.get("exit_code"),
                error_message=tc.get("error_message", ""),
                tool_use_id=tc.get("tool_use_id", ""),
                scope=tc.get("scope", "subagent"),
                llm_call_count=tc.get("llm_call_count", 0),
                llm_error_count=tc.get("llm_error_count", 0),
                subagent_id=tc.get("subagent_id", ""),
                subagent_summary=tc.get("subagent_summary", {}),
            ))
    return tcs


@pytest.fixture(scope="module")
def fixture_subagent_runs(subagent_fixture):
    """Return subagent_runs from fixture with messages converted to ChatMessage objects."""
    runs = subagent_fixture.get("subagent_runs", [])
    converted = []
    for run in runs:
        converted_msgs = []
        for m in run.get("messages", []):
            converted_msgs.append(ChatMessage(
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
        converted.append({
            "summary": run["summary"],
            "messages": converted_msgs,
            "tool_calls": run.get("tool_calls", []),
        })
    return converted


@pytest.fixture(scope="module")
def fixture_nested_subagent_runs(subagent_fixture):
    """Return nested subagent runs from fixture."""
    return subagent_fixture.get("nested_subagent_runs", [])


@pytest.fixture(scope="module")
def fixture_session(subagent_fixture):
    """Return session metadata."""
    return subagent_fixture["session"]


@pytest.fixture(scope="module")
def built_rounds(fixture_messages, fixture_tool_calls, fixture_session):
    """Build rounds from fixture data."""
    def identity_md(text):
        return text

    session = fixture_session
    return build_rounds(
        messages=fixture_messages,
        tool_calls=fixture_tool_calls,
        session_input_tokens=session["input_tokens"],
        session_output_tokens=session["output_tokens"],
        session_cached_tokens=session["cached_input_tokens"],
        session_cache_write_tokens=session["cached_output_tokens"],
        agent=session["agent"],
        md_filter=identity_md,
    )


@pytest.fixture(scope="module")
def built_llm_calls(fixture_messages, fixture_tool_calls, built_rounds, fixture_subagent_runs):
    """Build LLM calls from fixture data including subagents."""
    return build_llm_calls(
        messages=fixture_messages,
        tool_calls=fixture_tool_calls,
        rounds=built_rounds,
        subagent_runs=fixture_subagent_runs,
    )


@pytest.fixture(scope="module")
def final_rounds(built_rounds, built_llm_calls, fixture_tool_calls, fixture_subagent_runs):
    """Rounds with interactions assigned (including subagents)."""
    assign_interactions_to_rounds(
        rounds=built_rounds,
        llm_calls=built_llm_calls,
        tool_calls=fixture_tool_calls,
        subagent_runs=fixture_subagent_runs,
    )
    return built_rounds


# ─── Tests: Subagent Presence in Session Detail ─────────────────────────


class TestSubagentPresence:
    """验证 subagent 在 session detail 中正确显示。"""

    @pytest.mark.contract_case("DATA-SOURCE-004")
    def test_fixture_contains_two_subagent_runs(self, fixture_subagent_runs):
        """Fixture 必须包含至少 2 个 subagent run。"""
        assert len(fixture_subagent_runs) >= 2, (
            f"Fixture 应包含至少 2 个 subagent run，实际 {len(fixture_subagent_runs)}"
        )

    @pytest.mark.contract_case("DATA-SOURCE-004")
    def test_llm_calls_include_subagent_scope(self, built_llm_calls):
        """build_llm_calls 必须生成 scope='subagent' 的 LLMCall。"""
        sub_calls = [c for c in built_llm_calls if c.scope == "subagent"]
        assert len(sub_calls) >= 1, (
            "LLM calls 中必须包含至少一个 scope='subagent' 的调用"
        )

    @pytest.mark.contract_case("DATA-SOURCE-004")
    def test_main_and_subagent_calls_separated(self, built_llm_calls):
        """Main 和 subagent 的 LLMCall 必须通过 scope 字段区分。"""
        main_calls = [c for c in built_llm_calls if c.scope == "main"]
        sub_calls = [c for c in built_llm_calls if c.scope == "subagent"]
        # 两者都应该有
        assert len(main_calls) >= 1, "必须包含 main scope 的调用"
        assert len(sub_calls) >= 1, "必须包含 subagent scope 的调用"
        # 不应有重叠
        main_ids = {c.id for c in main_calls}
        sub_ids = {c.id for c in sub_calls}
        assert not (main_ids & sub_ids), "main 和 subagent 调用 ID 不应重叠"

    @pytest.mark.contract_case("DATA-SOURCE-004")
    def test_subagent_calls_have_agent_id(self, built_llm_calls):
        """Subagent LLMCall 的 subagent_id 必须非空且与 agent_id 匹配。"""
        sub_calls = [c for c in built_llm_calls if c.scope == "subagent"]
        for sc in sub_calls:
            assert sc.subagent_id != "", (
                f"Subagent LLMCall {sc.id} 的 subagent_id 为空"
            )
            # subagent_id 应该是 fixture 中定义的某个 agent_id
            valid_ids = {"explore-agent-001", "code-agent-002"}
            assert sc.subagent_id in valid_ids, (
                f"subagent_id '{sc.subagent_id}' 不在预期 ID 集合中: {valid_ids}"
            )

    @pytest.mark.contract_case("DATA-SOURCE-004")
    def test_subagent_has_parent_tool_name(self, built_llm_calls):
        """Subagent LLMCall 应有 parent_tool_name='Agent'。"""
        sub_calls = [c for c in built_llm_calls if c.scope == "subagent"]
        for sc in sub_calls:
            assert sc.parent_tool_name == "Agent", (
                f"Subagent {sc.id} 的 parent_tool_name 应为 'Agent'，实际 '{sc.parent_tool_name}'"
            )


# ─── Tests: Subagent Status (Success/Failed) ───────────────────────────


class TestSubagentStatus:
    """验证 subagent 状态（成功/失败）正确反映。"""

    @pytest.mark.contract_case("DATA-SOURCE-004")
    def test_successful_subagent_in_fixture(self, fixture_subagent_runs):
        """Fixture 必须包含至少一个成功的 subagent。"""
        successful = [
            r for r in fixture_subagent_runs
            if r["summary"].get("status") == "success"
        ]
        assert len(successful) >= 1, "Fixture 必须包含至少一个 status='success' 的 subagent"

    @pytest.mark.contract_case("DATA-SOURCE-004")
    def test_failed_subagent_in_fixture(self, fixture_subagent_runs):
        """Fixture 必须包含至少一个失败的 subagent。"""
        failed = [
            r for r in fixture_subagent_runs
            if r["summary"].get("status") == "failed"
        ]
        assert len(failed) >= 1, "Fixture 必须包含至少一个 status='failed' 的 subagent"

    @pytest.mark.contract_case("DATA-SOURCE-004")
    def test_failed_subagent_tool_call_has_error(self, fixture_tool_calls):
        """失败的 subagent 对应的 Agent tool call 应有 error_message。"""
        agent_tools = [
            tc for tc in fixture_tool_calls
            if tc.name == "Agent" and tc.scope == "main" and tc.subagent_summary
        ]
        failed_agents = [tc for tc in agent_tools if tc.subagent_summary.get("status") == "failed"]
        assert len(failed_agents) >= 1, "必须包含至少一个失败的 Agent tool call"
        for fa in failed_agents:
            assert fa.status == "error", (
                f"失败 subagent 的 Agent tool call status 应为 'error'，实际 '{fa.status}'"
            )
            assert fa.error_message and len(fa.error_message.strip()) > 0, (
                f"失败 subagent 的 Agent tool call error_message 为空"
            )

    @pytest.mark.contract_case("DATA-SOURCE-004")
    def test_successful_subagent_tool_call_completed(self, fixture_tool_calls):
        """成功的 subagent 对应的 Agent tool call 应为 completed。"""
        agent_tools = [
            tc for tc in fixture_tool_calls
            if tc.name == "Agent" and tc.scope == "main" and tc.subagent_summary
        ]
        success_agents = [
            tc for tc in agent_tools
            if tc.subagent_summary.get("status") == "success"
        ]
        assert len(success_agents) >= 1, "必须包含至少一个成功的 Agent tool call"
        for sa in success_agents:
            assert sa.status == "completed", (
                f"成功 subagent 的 Agent tool call status 应为 'completed'，实际 '{sa.status}'"
            )

    @pytest.mark.contract_case("DATA-SOURCE-004")
    def test_subagent_interactions_built_for_successful_run(
        self, fixture_tool_calls, built_llm_calls, fixture_subagent_runs
    ):
        """成功的 subagent run 必须构建对应的 LLMCall interactions。"""
        sub_calls = [c for c in built_llm_calls if c.scope == "subagent"]
        explore_calls = [c for c in sub_calls if c.subagent_id == "explore-agent-001"]
        assert len(explore_calls) >= 1, (
            "成功的 explore-agent-001 必须有对应的 LLMCall interaction"
        )


# ─── Tests: Subagent Token and Timing ──────────────────────────────────


class TestSubagentTokenAndTiming:
    """验证 subagent 的 token 和执行时间。"""

    @pytest.mark.contract_case("DATA-SOURCE-004")
    def test_subagent_llm_calls_have_tokens(self, built_llm_calls):
        """Subagent LLMCall 必须有非零的 token 计数。"""
        sub_calls = [c for c in built_llm_calls if c.scope == "subagent"]
        for sc in sub_calls:
            total = sc.input_tokens + sc.output_tokens
            assert total > 0, (
                f"Subagent LLMCall {sc.id} 的 token 总数为 0"
            )

    @pytest.mark.contract_case("DATA-SOURCE-004")
    def test_successful_subagent_token_aggregation(
        self, built_llm_calls, fixture_subagent_runs
    ):
        """成功 subagent 的 aggregated LLMCall 应有正确的 token 聚合。"""
        sub_calls = [c for c in built_llm_calls if c.scope == "subagent"]
        explore_calls = [c for c in sub_calls if c.subagent_id == "explore-agent-001"]
        assert len(explore_calls) >= 1, "explore-agent-001 应有聚合后的 LLMCall"

        agg = explore_calls[0]
        # 聚合后的 input_tokens 应该是所有内部调用之和
        assert agg.input_tokens > 0, "聚合后的 input_tokens 应为正数"
        assert agg.output_tokens > 0, "聚合后的 output_tokens 应为正数"
        # 聚合后的 cache_read_tokens 也应为正数（fixture 中有缓存数据）
        assert agg.cache_read_tokens > 0, "聚合后的 cache_read_tokens 应为正数"

    @pytest.mark.contract_case("DATA-SOURCE-004")
    def test_subagent_has_cache_write_tokens(self, built_llm_calls):
        """Subagent LLMCall 应有 cache_write_tokens（cache_creation_input_tokens）。"""
        sub_calls = [c for c in built_llm_calls if c.scope == "subagent"]
        has_cache_write = any(sc.cache_write_tokens > 0 for sc in sub_calls)
        assert has_cache_write, (
            "至少一个 subagent LLMCall 应有 cache_write_tokens > 0"
        )

    @pytest.mark.contract_case("DATA-SOURCE-004")
    def test_failed_subagent_still_has_tokens(self, built_llm_calls):
        """即使失败的 subagent 也应有 token 记录（已发生的 LLM 调用）。"""
        sub_calls = [c for c in built_llm_calls if c.scope == "subagent"]
        code_calls = [c for c in sub_calls if c.subagent_id == "code-agent-002"]
        # code-agent-002 有 2 条 assistant messages，所以应该有聚合
        if len(code_calls) >= 1:
            agg = code_calls[0]
            assert agg.input_tokens > 0, "失败 subagent 也应有 input_tokens"
            assert agg.output_tokens > 0, "失败 subagent 也应有 output_tokens"


# ─── Tests: Nested Subagent Hierarchy ───────────────────────────────────


class TestNestedSubagentHierarchy:
    """验证嵌套 subagent 层次结构。"""

    @pytest.mark.contract_case("DATA-SOURCE-004")
    def test_fixture_has_nested_subagent_runs(self, fixture_nested_subagent_runs):
        """Fixture 必须包含嵌套 subagent runs。"""
        assert len(fixture_nested_subagent_runs) >= 1, (
            "Fixture 必须包含至少一个嵌套 subagent run"
        )

    @pytest.mark.contract_case("DATA-SOURCE-004")
    def test_nested_subagent_has_parent_in_explore(self, fixture_subagent_runs):
        """嵌套 subagent 的父级应该是 explore-agent-001 的 tool_calls 中引用的。"""
        # explore-agent-001 应该有一个 Agent 类型的 tool call 引用 nested-explore-001
        explore_run = None
        for r in fixture_subagent_runs:
            if r["summary"]["agent_id"] == "explore-agent-001":
                explore_run = r
                break
        assert explore_run is not None, "explore-agent-001 run 必须存在"

        nested_refs = [
            tc for tc in explore_run.get("tool_calls", [])
            if tc.get("name") == "Agent" and tc.get("subagent_summary", {}).get("agent_id")
        ]
        assert len(nested_refs) >= 1, (
            "explore-agent-001 必须引用至少一个嵌套 subagent"
        )

    @pytest.mark.contract_case("DATA-SOURCE-004")
    def test_nested_subagent_tool_has_subagent_scope(self, fixture_tool_calls):
        """嵌套 subagent 的 tool call 应有 scope='subagent'。"""
        nested_tools = [
            tc for tc in fixture_tool_calls
            if tc.scope == "subagent" and tc.subagent_id == "explore-agent-001"
            and tc.name == "Agent"
        ]
        assert len(nested_tools) >= 1, (
            "explore-agent-001 下必须有 scope='subagent' 的嵌套 Agent tool call"
        )
        for nt in nested_tools:
            assert nt.subagent_summary.get("agent_id") == "nested-explore-001", (
                "嵌套 Agent tool call 的 subagent_summary.agent_id 应为 'nested-explore-001'"
            )

    @pytest.mark.contract_case("DATA-SOURCE-004")
    def test_three_level_hierarchy(self, fixture_tool_calls):
        """验证 main -> explore-agent-001 -> nested-explore-001 三层结构。"""
        # Main agent 的 Agent tool call -> explore-agent-001
        main_to_explore = [
            tc for tc in fixture_tool_calls
            if tc.scope == "main" and tc.name == "Agent"
            and tc.subagent_summary.get("agent_id") == "explore-agent-001"
        ]
        assert len(main_to_explore) >= 1, "Main agent 必须引用 explore-agent-001"

        # Explore agent 的 Agent tool call -> nested-explore-001
        explore_to_nested = [
            tc for tc in fixture_tool_calls
            if tc.scope == "subagent" and tc.subagent_id == "explore-agent-001"
            and tc.name == "Agent"
            and tc.subagent_summary.get("agent_id") == "nested-explore-001"
        ]
        assert len(explore_to_nested) >= 1, "Explore agent 必须引用 nested-explore-001"

# ─── Tests: Subagent Round Assignment ───────────────────────────────────


class TestSubagentRoundAssignment:
    """验证 subagent 被正确分配到对应的 round。"""

    @pytest.mark.contract_case("DATA-SOURCE-004")
    def test_subagent_interactions_after_main_in_round(self, final_rounds):
        """在同一 round 中，subagent interactions 应在 main calls 之后。"""
        for r in final_rounds:
            sub_ixs = [ix for ix in r.interactions if ix.scope == "subagent"]
            main_ixs = [ix for ix in r.interactions if ix.scope == "main"]
            if sub_ixs and main_ixs:
                # 第一个 subagent interaction 的 index 应大于最后一个 main interaction
                first_sub_idx = r.interactions.index(sub_ixs[0])
                last_main_idx = r.interactions.index(main_ixs[-1])
                assert first_sub_idx > last_main_idx, (
                    f"Round {r.round_index}: subagent interactions 应在 main calls 之后"
                )
