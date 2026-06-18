"""Hero 区 subagent 数量测试。

验证 session detail hero 区域的 Subagents 计数正确:
- session_summary.subagent_count 必须等于 len(subagent_runs)
- 在 slim mode 下也必须正确计数（不能依赖 timeline_items）
- 无 subagent 的 session 必须显示 0
"""

import pytest

from session_browser.domain.models import (
    LLMCall, ChatMessage, ConversationRound, ToolCall,
)
from session_browser.web.routes import _build_v11_view_model


class _FakeSession:
    """测试用最小 session 对象。"""
    def __init__(self, **kwargs):
        self.agent = kwargs.get("agent", "claude_code")
        self.session_id = kwargs.get("session_id", "test-session-001")
        self.title = kwargs.get("title", "Test Session")
        self.model = kwargs.get("model", "claude-sonnet-4")
        self.git_branch = kwargs.get("git_branch", "main")
        self.started_at = kwargs.get("started_at", "2025-01-01T00:00:00Z")
        self.project_key = kwargs.get("project_key", "/tmp/test")
        self.project_name = kwargs.get("project_name", "test")
        self.output_tokens = kwargs.get("output_tokens", 5000)
        self.fresh_input_tokens = kwargs.get("fresh_input_tokens", 10000)
        self.cache_read_tokens = kwargs.get("cache_read_tokens", 5000)
        self.cache_write_tokens = kwargs.get("cache_write_tokens", 1000)
        self.total_tokens = kwargs.get("total_tokens", 21000)
        self.failed_tool_count = kwargs.get("failed_tool_count", 0)


class _FakeAnomalies:
    def __init__(self):
        self.anomalies = []


def _make_empty_round():
    """Create a minimal empty round."""
    user_msg = ChatMessage(
        role="user", content="Hello",
        timestamp="2025-01-01T00:00:00Z",
    )
    assistant_msg = ChatMessage(
        role="assistant", content="OK",
        timestamp="2025-01-01T00:00:01Z",
    )
    ro = ConversationRound(
        user_msg=user_msg,
        assistant_msg=assistant_msg,
        tool_calls=[],
        interactions=[],
        round_index=0,
    )
    ro.compute_preview()
    return ro


class TestHeroSubagentCount:
    """Hero 区 subagent_count 必须反映真实 subagent run 数量。"""

    @pytest.mark.contract_case("UI-SD-031")
    def test_subagent_count_matches_subagent_runs(self):
        """session_summary.subagent_count 必须等于 len(subagent_runs)。"""
        session = _FakeSession()
        ro = _make_empty_round()

        subagent_runs = [
            {"summary": {"agent_id": "sa-1", "agent_type": "test"}},
            {"summary": {"agent_id": "sa-2", "agent_type": "test"}},
            {"summary": {"agent_id": "sa-3", "agent_type": "test"}},
        ]

        vm = _build_v11_view_model(
            session=session,
            rounds=[ro],
            llm_calls=[],
            tool_calls=[],
            subagent_runs=subagent_runs,
            session_anomalies=_FakeAnomalies(),
        )

        assert vm["session_summary"]["subagent_count"] == 3, (
            f"subagent_count 应为 3，实际为 {vm['session_summary']['subagent_count']}"
        )

    @pytest.mark.contract_case("UI-SD-031")
    def test_subagent_count_zero_without_subagents(self):
        """无 subagent 的 session，subagent_count 必须为 0。"""
        session = _FakeSession()
        ro = _make_empty_round()

        vm = _build_v11_view_model(
            session=session,
            rounds=[ro],
            llm_calls=[],
            tool_calls=[],
            subagent_runs=[],
            session_anomalies=_FakeAnomalies(),
        )

        assert vm["session_summary"]["subagent_count"] == 0, (
            f"subagent_count 应为 0，实际为 {vm['session_summary']['subagent_count']}"
        )

    @pytest.mark.contract_case("UI-SD-031")
    def test_subagent_count_correct_in_slim_mode(self):
        """Slim mode 下 subagent_count 也必须正确（bug regression）。

        此前 bug: subagent_count 从 trace_rows[].timeline_items 计数，
        而 slim mode 下 timeline_items 为空，导致显示为 0。
        修复后应直接基于 subagent_runs 计数。
        """
        session = _FakeSession()
        ro = _make_empty_round()

        subagent_runs = [
            {"summary": {"agent_id": "sa-1", "agent_type": "test"}},
        ]

        vm = _build_v11_view_model(
            session=session,
            rounds=[ro],
            llm_calls=[],
            tool_calls=[],
            subagent_runs=subagent_runs,
            session_anomalies=_FakeAnomalies(),
            slim=True,  # slim mode 触发 bug
        )

        assert vm["session_summary"]["subagent_count"] == 1, (
            f"slim mode 下 subagent_count 应为 1，实际为 {vm['session_summary']['subagent_count']}"
        )

    @pytest.mark.contract_case("UI-SD-031")
    def test_subagent_count_single_run(self):
        """单个 subagent run 的场景。"""
        session = _FakeSession()
        ro = _make_empty_round()

        subagent_runs = [
            {"summary": {"agent_id": "sa-only", "agent_type": "test"}},
        ]

        vm = _build_v11_view_model(
            session=session,
            rounds=[ro],
            llm_calls=[],
            tool_calls=[],
            subagent_runs=subagent_runs,
            session_anomalies=_FakeAnomalies(),
        )

        assert vm["session_summary"]["subagent_count"] == 1
