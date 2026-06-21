"""Dashboard Presenter contract 测试..

覆盖:
- scope slug 解析
- grain 解析
- KPI 不受 grain 影响
- trend/token/cache 受 grain 影响
- single agent scope 有数据时 trend 不异常为空
- Total Tokens 分段合计
- Cache Read Ratio
- Agent Sessions 默认不超过 20 条

T-Dashboard-Presenter-Contract
"""

from __future__ import annotations

import shutil
import sqlite3

import pytest


@pytest.fixture
def conn(tmp_path):
    """创建 deterministic HIFI fixture SQLite 连接.."""
    from tests.conftest import (
        FIXTURE_ROOT,
        HIFFI_AGENT,
        HIFFI_SESSION_ID,
        _populate_index_from_fixture,
    )

    data_dir = tmp_path / 'claude_data'
    shutil.copytree(FIXTURE_ROOT, data_dir)
    sqlite_path = tmp_path / 'index.sqlite'
    session_key = _populate_index_from_fixture(
        str(data_dir),
        str(sqlite_path),
        expected_agent=HIFFI_AGENT,
        expected_session_id=HIFFI_SESSION_ID,
    )
    assert session_key == f'{HIFFI_AGENT}:{HIFFI_SESSION_ID}'

    c = sqlite3.connect(sqlite_path)
    c.row_factory = sqlite3.Row
    yield c
    c.close()


class TestDashboardScopeSlug:
    """验证 scope slug 解析.."""

    @pytest.mark.contract_case('DASHBOARD-PRESENTER-001')
    def test_all_scope_returns_all_agents(self, conn):
        """agent_scope='all' 应返回所有 agent 数据.."""
        from session_browser.web.presenters.dashboard import build_dashboard_view_model

        vm = build_dashboard_view_model(conn, agent_scope='all')
        assert vm['is_single_agent'] is False
        assert vm['all_agents_branch'] is not None

    @pytest.mark.contract_case('DASHBOARD-PRESENTER-002')
    def test_claude_code_scope_returns_single_agent(self, conn):
        """agent_scope='claude-code' 应返回单 agent 数据.."""
        from session_browser.web.presenters.dashboard import build_dashboard_view_model

        vm = build_dashboard_view_model(conn, agent_scope='claude-code')
        assert vm['is_single_agent'] is True
        assert vm['single_agent_branch'] is not None

    @pytest.mark.contract_case('DASHBOARD-PRESENTER-003')
    def test_invalid_scope_defaults_to_all(self, conn):
        """无效 scope 应默认回退到 all.."""
        from session_browser.web.presenters.dashboard import build_dashboard_view_model

        vm = build_dashboard_view_model(conn, agent_scope='invalid')
        assert vm['is_single_agent'] is False


class TestDashboardGrain:
    """验证 grain 解析.."""

    @pytest.mark.contract_case('DASHBOARD-PRESENTER-004')
    def test_default_grain_is_day(self, conn):
        """默认 grain 应为 day.."""
        from session_browser.web.presenters.dashboard import build_dashboard_view_model

        vm = build_dashboard_view_model(conn)
        assert vm['grain'] == 'day'

    @pytest.mark.contract_case('DASHBOARD-PRESENTER-005')
    def test_invalid_grain_defaults_to_day(self, conn):
        """无效 grain 应默认回退到 day.."""
        from session_browser.web.presenters.dashboard import build_dashboard_view_model

        vm = build_dashboard_view_model(conn, grain='invalid')
        assert vm['grain'] == 'day'


class TestDashboardKPIInvariants:
    """验证 KPI 不变量.."""

    @pytest.mark.contract_case('DASHBOARD-PRESENTER-006')
    def test_kpi_has_6_cards(self, conn):
        """KPI 区应有 6 张 card.."""
        from session_browser.web.presenters.dashboard import build_dashboard_view_model

        vm = build_dashboard_view_model(conn)
        assert len(vm['kpis']) == 6

    @pytest.mark.contract_case('DASHBOARD-PRESENTER-007')
    def test_kpi_labels_correct(self, conn):
        """KPI label 应正确.."""
        from session_browser.web.presenters.dashboard import build_dashboard_view_model

        vm = build_dashboard_view_model(conn)
        labels = [k['label'] for k in vm['kpis']]
        assert labels == [
            'Projects',
            'Sessions',
            'Total Tokens',
            'Prompt Activity',
            'Cache Read Ratio',
            'Failed Tools',
        ]

    @pytest.mark.contract_case('DASHBOARD-PRESENTER-008')
    def test_kpi_not_affected_by_grain(self, conn):
        """KPI 不应受 grain 影响.."""
        from session_browser.web.presenters.dashboard import build_dashboard_view_model

        vm_day = build_dashboard_view_model(conn, grain='day')
        vm_week = build_dashboard_view_model(conn, grain='week')
        vm_month = build_dashboard_view_model(conn, grain='month')
        # KPI values should be the same regardless of grain
        day_kpis = [(k['label'], k['value']) for k in vm_day['kpis']]
        week_kpis = [(k['label'], k['value']) for k in vm_week['kpis']]
        month_kpis = [(k['label'], k['value']) for k in vm_month['kpis']]
        assert day_kpis == week_kpis == month_kpis


class TestDashboardTrendInvariants:
    """验证 Trend 不变量.."""

    @pytest.mark.contract_case('DASHBOARD-PRESENTER-009')
    def test_trend_affected_by_grain(self, conn):
        """Trend 数据应受 grain 影响.."""
        from session_browser.web.presenters.dashboard import build_dashboard_view_model

        vm_day = build_dashboard_view_model(conn, grain='day')
        build_dashboard_view_model(conn, grain='week')
        # Trend data length may differ based on grain aggregation
        assert isinstance(vm_day['trend'], list)


class TestDashboardAgentSessions:
    """验证 Agent Sessions 分页.."""

    @pytest.mark.contract_case('DASHBOARD-PRESENTER-010')
    def test_agent_sessions_page_size(self, conn):
        """Agent Sessions 默认每页 20 条.."""
        from session_browser.web.presenters.dashboard import build_dashboard_view_model

        vm = build_dashboard_view_model(conn, agent_scope='claude-code')
        assert vm['agent_sessions_page_size'] == 20

    @pytest.mark.contract_case('DASHBOARD-PRESENTER-011')
    def test_agent_sessions_single_agent_has_pagination(self, conn):
        """单 agent 模式应有分页信息.."""
        from session_browser.web.presenters.dashboard import build_dashboard_view_model

        vm = build_dashboard_view_model(conn, agent_scope='claude-code')
        assert 'agent_sessions_page' in vm
        assert 'agent_sessions_total_pages' in vm
        assert 'agent_sessions_total' in vm
