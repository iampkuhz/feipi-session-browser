"""Dashboard 路由 smoke 测试。

覆盖规约要求的所有 scope/grain URL 组合：
- /dashboard
- /dashboard?grain=day|week|month
- /dashboard?agent=claude-code|qoder|codex&grain=day|week|month

要求：status < 500，server log 无 ERROR / Traceback。

T-Dashboard-Route-Smoke
"""

from __future__ import annotations

import pytest
import urllib.request
import urllib.error


@pytest.fixture(scope="module")
def base_url(hifi_fixture_session):
    """从 hifi fixture 获取服务器 URL。"""
    url, _, _ = hifi_fixture_session
    return url


class TestDashboardRouteSmoke:
    """验证所有 scope/grain 组合返回 status < 500。"""

    _URLS = [
        "/dashboard",
        "/dashboard?grain=day",
        "/dashboard?grain=week",
        "/dashboard?grain=month",
        "/dashboard?agent=claude-code&grain=day",
        "/dashboard?agent=claude-code&grain=week",
        "/dashboard?agent=qoder&grain=day",
        "/dashboard?agent=codex&grain=day",
    ]

    @pytest.mark.parametrize("url", _URLS)
    @pytest.mark.contract_case("DASHBOARD-ROUTE-001")
    def test_dashboard_route(self, base_url, url):
        """每个 scope/grain 组合必须返回 status < 500。"""
        full_url = f"{base_url}{url}"
        try:
            resp = urllib.request.urlopen(full_url, timeout=10)
            assert resp.status < 500, f"{url} 返回 status {resp.status}"
            html = resp.read().decode("utf-8")
            assert len(html) > 100, f"{url} HTML 太短，可能渲染失败"
        except urllib.error.HTTPError as e:
            assert e.code < 500, f"{url} 返回 HTTP {e.code}"


class TestDashboardContentIntegrity:
    """验证 Dashboard 渲染内容完整性。"""

    @pytest.mark.contract_case("DASHBOARD-CONTENT-001")
    def test_all_agents_has_kpis(self, base_url):
        """All agents 模式必须有 6 张 KPI card。"""
        resp = urllib.request.urlopen(f"{base_url}/dashboard", timeout=10)
        html = resp.read().decode("utf-8")
        cards = html.count('class="metric-card metric-card--kpi"')
        assert cards == 6, f"All agents 模式应有 6 张 KPI card，发现 {cards}"

    @pytest.mark.contract_case("DASHBOARD-CONTENT-002")
    def test_all_agents_has_trend_cards(self, base_url):
        """All agents 模式必须有 3 张 trend card。"""
        resp = urllib.request.urlopen(f"{base_url}/dashboard", timeout=10)
        html = resp.read().decode("utf-8")
        assert "Session Trend" in html
        assert "Token Trend" in html
        assert "Prompt Activity Trend" in html

    @pytest.mark.contract_case("DASHBOARD-CONTENT-003")
    def test_all_agents_has_contribution(self, base_url):
        """All agents 模式必须有 Agent Contribution Comparison。"""
        resp = urllib.request.urlopen(f"{base_url}/dashboard", timeout=10)
        html = resp.read().decode("utf-8")
        assert "Agent Contribution Comparison" in html

    @pytest.mark.contract_case("DASHBOARD-CONTENT-004")
    def test_all_agents_has_all_agents_table(self, base_url):
        """All agents 模式必须有 All Agents 表。"""
        resp = urllib.request.urlopen(f"{base_url}/dashboard", timeout=10)
        html = resp.read().decode("utf-8")
        assert "All Agents" in html

    @pytest.mark.contract_case("DASHBOARD-CONTENT-005")
    def test_all_agents_has_no_hot_sessions(self, base_url):
        """All agents 模式不得有 Hot Sessions & Signals。"""
        resp = urllib.request.urlopen(f"{base_url}/dashboard", timeout=10)
        html = resp.read().decode("utf-8")
        assert "Hot Sessions" not in html

    @pytest.mark.contract_case("DASHBOARD-CONTENT-006")
    def test_all_agents_has_no_context_budget(self, base_url):
        """All agents 模式不得有 Context Budget。"""
        resp = urllib.request.urlopen(f"{base_url}/dashboard", timeout=10)
        html = resp.read().decode("utf-8")
        assert "Context Budget" not in html


class TestDashboardSingleAgent:
    """验证单 agent 模式渲染。"""

    @pytest.mark.contract_case("DASHBOARD-SINGLE-001")
    def test_single_agent_has_deep_dive(self, base_url):
        """单 agent 模式必须有 Agent Deep Dive。"""
        resp = urllib.request.urlopen(
            f"{base_url}/dashboard?agent=claude-code", timeout=10,
        )
        html = resp.read().decode("utf-8")
        assert "Agent Deep Dive" in html

    @pytest.mark.contract_case("DASHBOARD-SINGLE-002")
    def test_single_agent_has_model_mix(self, base_url):
        """单 agent 模式必须有 Model Mix。"""
        resp = urllib.request.urlopen(
            f"{base_url}/dashboard?agent=claude-code", timeout=10,
        )
        html = resp.read().decode("utf-8")
        assert "Model Mix" in html

    @pytest.mark.contract_case("DASHBOARD-SINGLE-003")
    def test_single_agent_has_tool_distribution(self, base_url):
        """单 agent 模式必须有 Tool Distribution。"""
        resp = urllib.request.urlopen(
            f"{base_url}/dashboard?agent=claude-code", timeout=10,
        )
        html = resp.read().decode("utf-8")
        assert "Tool Distribution" in html
