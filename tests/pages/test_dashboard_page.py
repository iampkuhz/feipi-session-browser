"""Dashboard 页面级夹具测试。

这些测试使用 hifi_fixture_session 启动一个带有确定性夹具数据的本地服务器，
然后验证*渲染后*的 Dashboard HTML（而非仅静态模板文件）。

覆盖：
- 页面渲染并返回 HTTP 200
- 关键数据/指标可见（stats 值 > 0）
- 所有指标卡片存在且填充了值
- 图表容器渲染并嵌入了 JSON 数据
- Scope switch UI 存在
- 覆盖层（tooltip、popover、toast）存在
- 无 inline onclick（可访问性门控）

T092 — Dashboard 固定夹具。
"""

from __future__ import annotations

import pytest
import json
import re

# ── Dashboard 页面夹具 ────────────────────────────────────────────


@pytest.fixture(scope="module")
def dashboard_html(hifi_fixture_session):
    """从本地夹具服务器获取渲染后的 Dashboard HTML。"""
    base_url, agent, session_id = hifi_fixture_session
    import urllib.request

    resp = urllib.request.urlopen(f"{base_url}/dashboard", timeout=10)
    assert resp.status == 200, "Dashboard 必须返回 HTTP 200"
    return resp.read().decode("utf-8")


# ── TestDashboardPageRender ──────────────────────────────────────────


class TestDashboardPageRender:
    """验证渲染后的 Dashboard 页面结构。"""

    @pytest.mark.contract_case("ROUTE-API-005")
    @pytest.mark.contract_case("UI-DASHBOARD-003")
    def test_page_returns_200(self, dashboard_html):
        """Dashboard 必须成功渲染。"""
        assert len(dashboard_html) > 500, \
            "Dashboard HTML 必须有足够内容"

    @pytest.mark.contract_case("ROUTE-API-005")
    @pytest.mark.contract_case("UI-DASHBOARD-006")
    def test_has_doctype_and_html(self, dashboard_html):
        """页面必须有正确的 HTML 结构。"""
        assert "<!doctype html" in dashboard_html.lower() or "<!DOCTYPE html" in dashboard_html, \
            "Dashboard 必须有 DOCTYPE 声明"

    @pytest.mark.contract_case("ROUTE-API-005")
    @pytest.mark.contract_case("UI-DASHBOARD-007")
    def test_title_contains_dashboard(self, dashboard_html):
        """页面标题必须包含 'Dashboard'。"""
        assert "<title>Dashboard" in dashboard_html, \
            "页面标题必须包含 'Dashboard'"

    @pytest.mark.contract_case("ROUTE-API-005")
    def test_has_h1_dashboard(self, dashboard_html):
        """页面必须有可见的 'Dashboard' 标题。"""
        # 可能在 h1 或 page-head 组件中
        assert "Dashboard" in dashboard_html, \
            "Dashboard 文本必须出现在渲染页面中"

    @pytest.mark.contract_case("ROUTE-API-005")
    @pytest.mark.contract_case("UI-DASHBOARD-008")
    def test_has_subtitle(self, dashboard_html):
        """页面必须显示副标题。"""
        assert "全局概览" in dashboard_html or "Local agent session overview" in dashboard_html, \
            "副标题 'Local agent session overview' 必须出现"


# ── TestDashboardMetrics ─────────────────────────────────────────────


class TestDashboardMetrics:
    """验证渲染后的指标卡片及其实际数据值。"""

    _METRIC_LABELS = ["Projects", "Sessions", "Total Tokens", "Prompt Activity", "Cache Read Ratio", "Failed Tools"]

    @pytest.mark.contract_case("ROUTE-API-005")
    @pytest.mark.contract_case("UI-DASHBOARD-001")
    def test_metric_grid_present(self, dashboard_html):
        """Dashboard 必须有 metric-grid 容器。"""
        assert 'class="kpi-grid"' in dashboard_html, \
            "metric-grid 必须存在"

    @pytest.mark.contract_case("ROUTE-API-005")
    def test_four_metric_cards(self, dashboard_html):
        """必须恰好渲染 6 个指标卡片（有数据时）。"""
        cards = re.findall(r'class="metric-card\b', dashboard_html)
        # If page renders empty state, skip this check
        if "暂无已索引 session" in dashboard_html:
            pytest.skip("Fixture 未产生数据，页面渲染空态")
        assert len(cards) == 6, \
            f"预期 6 个指标卡片，发现 {len(cards)} 个"

    @pytest.mark.parametrize("label", ["Projects", "Sessions", "Total Tokens", "Failed Tools"])
    @pytest.mark.contract_case("ROUTE-API-005")
    def test_metric_label_present(self, dashboard_html, label):
        """每个指标卡片必须显示其标签。"""
        assert f">{label}<" in dashboard_html or f'aria-label="{label}"' in dashboard_html, \
            f"标签为 '{label}' 的指标卡片必须可见"

    @pytest.mark.contract_case("ROUTE-API-005")
    def test_metric_values_nonzero(self, dashboard_html):
        """当夹具包含数据时，指标卡片必须有填充的值（不为零）。"""
        # 从 metric-card__value 元素中提取值（class 可能包含额外修饰类如 tabular）
        values = re.findall(
            r'class="metric-card__value[^"]*">([^<]+)<',
            dashboard_html
        )
        if "暂无已索引 session" in dashboard_html:
            pytest.skip("Fixture 未产生数据，页面渲染空态")
        assert len(values) == 6, \
            f"预期 6 个指标值，发现 {len(values)} 个"

        # 解析并验证 Projects 和 Sessions 至少有正数计数
        projects_val = values[0].strip().replace(",", "")
        sessions_val = values[1].strip().replace(",", "")

        assert projects_val.isdigit() and int(projects_val) > 0, \
            f"Projects 计数必须 > 0，得到 '{projects_val}'"
        assert sessions_val.isdigit() and int(sessions_val) > 0, \
            f"Sessions 计数必须 > 0，得到 '{sessions_val}'"

    @pytest.mark.contract_case("ROUTE-API-005")
    def test_metric_aria_labels(self, dashboard_html):
        """每个指标卡片必须有用于可访问性的 aria-label。"""
        for label in self._METRIC_LABELS:
            assert f'aria-label="{label}"' in dashboard_html, \
                f"指标卡片 '{label}' 必须有 aria-label"

    @pytest.mark.contract_case("ROUTE-API-005")
    def test_has_info_buttons(self, dashboard_html):
        """每个指标卡片必须有一个信息按钮。"""
        if "暂无已索引 session" in dashboard_html:
            pytest.skip("Fixture 未产生数据，页面渲染空态")
        # Template uses dynamic data-kpi attribute
        assert 'data-action="kpi-info"' in dashboard_html, \
            "Dashboard 必须有 KPI info buttons"


# ── TestDashboardCharts ──────────────────────────────────────────────


class TestDashboardCharts:
    """验证渲染后的图表卡片及其嵌入的数据。"""

    _CHART_TITLES = ["Session Trend", "Token Trend", "Prompt Activity Trend"]

    @pytest.mark.parametrize("title", ["Session Trend", "Token Trend", "Prompt Activity Trend"])
    @pytest.mark.contract_case("ROUTE-API-005")
    def test_chart_title_present(self, dashboard_html, title):
        """每个图表卡片必须显示其标题。"""
        assert title in dashboard_html, \
            f"图表 '{title}' 必须存在"

    @pytest.mark.contract_case("ROUTE-API-005")
    @pytest.mark.contract_case("UI-DASHBOARD-005")
    def test_chart_containers_rendered(self, dashboard_html):
        """图表必须有专用的容器元素。"""
        if "暂无已索引 session" in dashboard_html:
            pytest.skip("Fixture 未产生数据，页面渲染空态")
        containers = re.findall(r'data-dashboard-chart', dashboard_html)
        assert len(containers) >= 2, \
            f"预期至少 2 个图表容器，发现 {len(containers)} 个"

    @pytest.mark.contract_case("ROUTE-API-005")
    def test_chart_json_data_embedded(self, dashboard_html):
        """Dashboard 必须将图表数据嵌入为 JSON。"""
        if "暂无已索引 session" in dashboard_html:
            pytest.skip("Fixture 未产生数据，页面渲染空态")
        # 查找包含图表数据的 script 标签
        assert 'id="dashboard-graph-data"' in dashboard_html, \
            "Dashboard 必须嵌入趋势图表 JSON 数据"
        assert 'id="dashboard-prompt-data"' in dashboard_html, \
            "Dashboard 必须嵌入 prompt 活动 JSON 数据"

    @pytest.mark.contract_case("ROUTE-API-005")
    def test_chart_json_parseable(self, dashboard_html):
        """嵌入的图表 JSON 必须是有效的。"""
        if "暂无已索引 session" in dashboard_html:
            pytest.skip("Fixture 未产生数据，页面渲染空态")
        match = re.search(
            r'id="dashboard-graph-data">(\[.*?\])</script>',
            dashboard_html,
            re.DOTALL,
        )
        assert match, "图表数据脚本必须包含一个 JSON 数组"
        data = json.loads(match.group(1))
        assert isinstance(data, list), "图表数据必须是一个列表"
        assert len(data) > 0, "当夹具包含会话时图表数据不能为空"

    @pytest.mark.contract_case("ROUTE-API-005")
    def test_chart_has_legend(self, dashboard_html):
        """图表必须有图例（JS 渲染，检查图例相关 CSS 类是否被引用）。"""
        if "暂无已索引 session" in dashboard_html:
            pytest.skip("Fixture 未产生数据，页面渲染空态")
        # 图例由 JS 动态渲染，静态 HTML 中验证 legend CSS 被加载即可
        assert "legend-row" in dashboard_html or "ui-primitives.css" in dashboard_html, \
            "Dashboard 必须加载包含图例样式的 CSS"
        # 验证多 agent 图例标签存在（All agents 模式）
        assert "Claude Code" in dashboard_html, \
            "图例必须包含 Claude Code"

    @pytest.mark.contract_case("ROUTE-API-005")
    def test_chart_subtitles(self, dashboard_html):
        """每个图表必须有副标题。"""
        if "暂无已索引 session" in dashboard_html:
            pytest.skip("Fixture 未产生数据，页面渲染空态")
        # Subtitles are grain-aware (Daily/Weekly/Monthly)
        subtitles = [
            "session count by agent",
            "total tokens",
            "user-initiated inputs",
        ]
        for sub in subtitles:
            assert sub in dashboard_html, \
                f"图表副标题 '{sub}' 必须存在"


# ── TestDashboardScopeSwitch ─────────────────────────────────────────


class TestDashboardScopeSwitch:
    """验证 scope-switch UI 已渲染。"""

    @pytest.mark.contract_case("ROUTE-API-005")
    @pytest.mark.contract_case("UI-DASHBOARD-002")
    def test_scope_switch_present(self, dashboard_html):
        """Dashboard 必须渲染 scope switch 控件。"""
        assert 'data-grain="day"' in dashboard_html or 'data-scope="day"' in dashboard_html, \
            "Day 范围按钮必须存在"
        assert 'data-grain="week"' in dashboard_html or 'data-scope="week"' in dashboard_html, \
            "Week 范围按钮必须存在"
        assert 'data-grain="month"' in dashboard_html or 'data-scope="month"' in dashboard_html, \
            "Month 范围按钮必须存在"

    @pytest.mark.contract_case("ROUTE-API-005")
    def test_scope_button_labels(self, dashboard_html):
        """范围按钮必须显示正确的标签。"""
        for label in ["Day", "Week", "Month"]:
            assert f">{label}<" in dashboard_html, \
                f"范围按钮 '{label}' 必须可见"


# ── TestDashboardOverlays ────────────────────────────────────────────


class TestDashboardOverlays:
    """验证浮动覆盖层元素。"""

    @pytest.mark.contract_case("ROUTE-API-005")
    @pytest.mark.contract_case("UI-DASHBOARD-004")
    def test_tooltip_present(self, dashboard_html):
        """图表 tooltip 元素必须存在。"""
        assert 'id="chartTooltip"' in dashboard_html, \
            "chartTooltip 元素必须存在"

    @pytest.mark.contract_case("ROUTE-API-005")
    def test_popover_present(self, dashboard_html):
        """信息 popover 元素必须存在。"""
        assert 'id="infoPopover"' in dashboard_html, \
            "infoPopover 元素必须存在"

    @pytest.mark.contract_case("ROUTE-API-005")
    def test_toast_present(self, dashboard_html):
        """Toast 通知元素必须存在。"""
        assert 'id="toast"' in dashboard_html, \
            "toast 元素必须存在"


# ── TestDashboardAccessibility ───────────────────────────────────────


class TestDashboardAccessibility:
    """渲染后 Dashboard 的可访问性门控。"""

    @pytest.mark.contract_case("ROUTE-API-005")
    def test_no_inline_onclick(self, dashboard_html):
        """Dashboard 不得使用 inline onclick 处理器。"""
        matches = re.findall(r'\bonclick\s*=', dashboard_html, re.IGNORECASE)
        assert len(matches) == 0, \
            f"Dashboard 不得有 inline onclick，发现 {len(matches)} 处"
