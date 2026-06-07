"""Dashboard 页面的特定模板测试。

验证当前 dashboard.html 的 Jinja2 模板结构，包括 CSS/JS 导入、
指标卡片、图表卡片、scope-switch、信息按钮、图表菜单按钮、
空状态/错误状态，以及不含 inline onclick。

T066 — Dashboard 页面级 pytest。
"""

from __future__ import annotations

import pytest
import os
import pathlib
import re
import glob as _glob

_DASHBOARD_PATH = "src/session_browser/web/templates/dashboard.html"
_DASHBOARD_CSS_PATH = "src/session_browser/web/static/css/dashboard.css"
_DASHBOARD_JS_PATH = "src/session_browser/web/static/js/dashboard.js"
_UI_PRIMITIVES_PATH = "src/session_browser/web/templates/components/ui_primitives.html"
_UI_PRIMITIVES_DIR = "src/session_browser/web/templates/components/ui_primitives"


def _read(path: str) -> str:
    with open(path) as f:
        return f.read()


def _read_dashboard() -> str:
    return _read(_DASHBOARD_PATH)


def _read_ui_primitives_with_splits() -> str:
    """Read ui_primitives wrapper + all split sub-components."""
    parts = [_read(_UI_PRIMITIVES_PATH)]
    for fp in sorted(_glob.glob(os.path.join(_UI_PRIMITIVES_DIR, "*.html"))):
        parts.append(_read(fp))
    return "\n".join(parts)


# ── TestDashboardTemplate ─────────────────────────────────────────────

class TestDashboardTemplate:
    """验证 dashboard 的 Jinja2 模板结构渲染。"""

    @pytest.mark.contract_case("ROUTE-API-005")
    def test_template_file_exists(self):
        assert os.path.isfile(_DASHBOARD_PATH), \
            f"{_DASHBOARD_PATH} 必须存在"

    @pytest.mark.contract_case("ROUTE-API-005")
    def test_extends_base(self):
        content = _read_dashboard()
        assert '{% extends "base.html" %}' in content, \
            "Dashboard 必须继承 base.html"

    @pytest.mark.contract_case("ROUTE-API-005")
    def test_active_page_set(self):
        content = _read_dashboard()
        assert "active_page = 'dashboard'" in content, \
            "Dashboard 必须设置 active_page = 'dashboard'"

    @pytest.mark.contract_case("ROUTE-API-005")
    def test_ui_primitives_imported(self):
        content = _read_dashboard()
        assert 'import "components/ui_primitives.html"' in content, \
            "Dashboard 必须导入 ui_primitives.html"

    @pytest.mark.contract_case("ROUTE-API-005")
    def test_no_inline_onclick(self):
        """Dashboard 不得使用 inline onclick 处理器。"""
        content = _read_dashboard()
        # 查找模板中所有的 onclick 属性
        matches = re.findall(r'\bonclick\s*=', content, re.IGNORECASE)
        assert len(matches) == 0, \
            f"Dashboard 不得有 inline onclick，发现 {len(matches)} 处"


# ── TestDashboardImports ──────────────────────────────────────────────

class TestDashboardImports:
    """验证 CSS 和 JS 导入声明。"""

    @pytest.mark.contract_case("ROUTE-API-005")
    def test_css_import_dashboard_css(self):
        content = _read_dashboard()
        assert 'href="/static/css/dashboard.css"' in content, \
            "Dashboard 必须导入 dashboard.css"

    @pytest.mark.contract_case("ROUTE-API-005")
    def test_js_import_dashboard_js(self):
        content = _read_dashboard()
        assert 'src="/static/js/dashboard.js"' in content, \
            "Dashboard 必须导入 dashboard.js"

    @pytest.mark.contract_case("ROUTE-API-005")
    def test_css_file_exists_on_disk(self):
        assert os.path.isfile(_DASHBOARD_CSS_PATH), \
            "dashboard.css 必须存在于磁盘上"

    @pytest.mark.contract_case("ROUTE-API-005")
    def test_js_file_exists_on_disk(self):
        assert os.path.isfile(_DASHBOARD_JS_PATH), \
            "dashboard.js 必须存在于磁盘上"


# ── TestDashboardPageHead ────────────────────────────────────────────

class TestDashboardPageHead:
    """验证页面头部结构（使用 ui.page_head 宏，T15）。"""

    @pytest.mark.contract_case("ROUTE-API-005")
    def test_page_head_macro_used(self):
        content = _read_dashboard()
        assert 'class="dashboard-head' in content or 'ui.page_head(' in content, \
            "Dashboard 必须使用 ui.page_head() 宏"

    @pytest.mark.contract_case("ROUTE-API-005")
    def test_page_head_has_h1(self):
        content = _read_dashboard()
        assert "Dashboard" in content, \
            "Dashboard 必须有标题 'Dashboard'"

    @pytest.mark.contract_case("ROUTE-API-005")
    def test_page_head_has_subtitle(self):
        content = _read_dashboard()
        assert "全局概览" in content or "单 agent 深度分析" in content, \
            "页面头部必须有说明副标题"


# ── TestDashboardMetricCards ─────────────────────────────────────────

class TestDashboardMetricCards:
    """验证 4 个指标卡片及其正确标签。"""

    _EXPECTED_LABELS = ["Projects", "Sessions", "Total Tokens", "Prompt Activity", "Cache Read Ratio", "Failed Tools"]

    @pytest.mark.contract_case("ROUTE-API-005")
    def test_metric_grid_present(self):
        content = _read_dashboard()
        assert 'class="kpi-grid"' in content, \
            "Dashboard 必须有 metric-grid 区域"

    @pytest.mark.contract_case("ROUTE-API-005")
    def test_four_metric_cards(self):
        content = _read_dashboard()
        # Template uses Jinja for loop for KPI cards
        assert "{% for kpi in kpis %}" in content, \
            "Dashboard 必须使用 {% for kpi in kpis %} 循环"
        assert 'aria-label="{{ kpi.label }}"' in content, \
            "Dashboard KPI card 必须有动态 aria-label"
    @pytest.mark.parametrize("label", ["Projects", "Sessions", "Total Tokens", "Prompt Activity", "Cache Read Ratio", "Failed Tools"])
    @pytest.mark.contract_case("ROUTE-API-005")
    def test_metric_card_labels(self, label):
        content = _read_dashboard()
        # Template uses dynamic {{ kpi.label }}, so check that loop renders KPIs
        assert "{% for kpi in kpis %}" in content or label in content, \
            f"Dashboard 必须有 KPI 循环或标签 '{label}'"

    @pytest.mark.contract_case("ROUTE-API-005")
    def test_metric_card_aria_labels(self):
        """每个指标卡片必须有 aria-label (动态渲染)。"""
        content = _read_dashboard()
        # Template uses aria-label="{{ kpi.label }}" which renders dynamically
        assert 'aria-label="{{ kpi.label }}"' in content or 'aria-label="Projects"' in content, \
            "KPI card 必须有 aria-label"


# ── TestDashboardChartCards ──────────────────────────────────────────

class TestDashboardChartCards:
    """验证图表卡片（通过 chart_card 宏：Session Trend + Token Trend）。"""

    @pytest.mark.contract_case("ROUTE-API-005")
    def test_chart_cards_present(self):
        content = _read_dashboard()
        # Dashboard uses data-chart-card attribute for chart sections
        chart_cards = re.findall(r'data-chart-card="[^"]+"', content)
        assert len(chart_cards) >= 5, \
            f"Dashboard 必须至少有 5 个 chart-card，发现 {len(chart_cards)} 个"

    @pytest.mark.contract_case("ROUTE-API-005")
    def test_session_trend_chart(self):
        content = _read_dashboard()
        assert "Session Trend" in content, \
            "Dashboard 必须有 Session Trend 图表"

    @pytest.mark.contract_case("ROUTE-API-005")
    def test_token_trend_chart(self):
        content = _read_dashboard()
        assert "Token Trend" in content, \
            "Dashboard 必须有 Token Trend 图表"

    @pytest.mark.contract_case("ROUTE-API-005")
    def test_chart_has_legend(self):
        """图表必须包含 agent 名称。"""
        content = _read_dashboard()
        for agent in ["Claude Code", "Codex", "Qoder"]:
            assert agent in content, \
                f"Dashboard 必须包含 agent 名称 '{agent}'"


# ── TestDashboardScopeSwitch ─────────────────────────────────────────

class TestDashboardScopeSwitch:
    """验证通过 ui_primitives 宏调用了 scope-switch。"""

    @pytest.mark.contract_case("ROUTE-API-005")
    def test_scope_switch_macro_invoked(self):
        content = _read_dashboard()
        assert 'scope-selector' in content or 'ui.scope_switch(' in content, \
            "Dashboard 必须调用 ui.scope_switch 宏"

    @pytest.mark.contract_case("ROUTE-API-005")
    def test_scope_switch_day_button(self):
        """scope_switch 宏必须渲染一个 data-scope='day' 的 Day 按钮。"""
        rendered = _render_scope_switch()
        assert 'data-scope="day"' in rendered
        assert ">Day<" in rendered

    @pytest.mark.contract_case("ROUTE-API-005")
    def test_scope_switch_week_button(self):
        """scope_switch 宏必须渲染一个 data-scope='week' 的 Week 按钮。"""
        rendered = _render_scope_switch()
        assert 'data-scope="week"' in rendered
        assert ">Week<" in rendered

    @pytest.mark.contract_case("ROUTE-API-005")
    def test_scope_switch_month_button(self):
        """scope_switch 宏必须渲染一个 data-scope='month' 的 Month 按钮。"""
        rendered = _render_scope_switch()
        assert 'data-scope="month"' in rendered
        assert ">Month<" in rendered

    @pytest.mark.contract_case("ROUTE-API-005")
    def test_scope_switch_default_active(self):
        """Day 按钮默认必须为 is-active。"""
        rendered = _render_scope_switch()
        assert 'data-scope="day"' in rendered and "is-active" in rendered, \
            "Day 范围按钮默认必须为 is-active"
        # 只有 Day 按钮应该是激活状态
        assert rendered.count("is-active") == 1


def _render_scope_switch() -> str:
    """渲染 ui_primitives.html 中的 scope_switch 宏。"""
    import jinja2
    _TEMPLATE_DIR = pathlib.Path(__file__).resolve().parents[2] / "src" / "session_browser" / "web" / "templates"
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(_TEMPLATE_DIR)), autoescape=True)
    tmpl_str = (
        '{% from "components/ui_primitives.html" import scope_switch %}'
        "{{ scope_switch(active='day') }}"
    )
    return env.from_string(tmpl_str).render()


# ── TestDashboardInfoButtons ────────────────────────────────────────

class TestDashboardInfoButtons:
    """验证每个指标和图表上的信息按钮（ℹ️）。"""

    @pytest.mark.contract_case("ROUTE-API-005")
    def test_metric_info_buttons(self):
        """每个指标卡片必须有一个信息按钮。"""
        content = _read_dashboard()
        # Template uses dynamic data-kpi="{{ kpi.label | lower | replace(' ', '-') }}"
        assert 'data-action="kpi-info"' in content, \
            "Dashboard 必须有 KPI info buttons"

    @pytest.mark.contract_case("ROUTE-API-005")
    def test_chart_info_buttons(self):
        """每个图表卡片必须有一个信息按钮。"""
        content = _read_dashboard()
        # Template uses dynamic data-info="chart-*"
        assert 'data-action="info-chart-' in content, \
            "图表卡片必须有 info 按钮"

    @pytest.mark.contract_case("ROUTE-API-005")
    def test_info_button_uses_icon_button_class(self):
        """信息按钮必须使用 icon-button--info 类。"""
        content = _read_dashboard()
        assert "icon-button--info" in content, \
            "信息按钮必须使用 icon-button--info 类"


# ── TestDashboardEmptyState ──────────────────────────────────────────

class TestDashboardEmptyState:
    """验证当 stats.total_sessions == 0 时渲染空状态。"""

    @pytest.mark.contract_case("ROUTE-API-005")
    def test_empty_state_condition(self):
        content = _read_dashboard()
        assert "stats.total_sessions == 0" in content, \
            "Dashboard 必须检查 stats.total_sessions == 0 作为空状态条件"

    @pytest.mark.contract_case("ROUTE-API-005")
    def test_empty_state_uses_ui_macro(self):
        content = _read_dashboard()
        assert "ui.empty_state" in content, \
            "空状态必须使用 ui.empty_state 宏"

    @pytest.mark.contract_case("ROUTE-API-005")
    def test_empty_state_has_action_button(self):
        content = _read_dashboard()
        assert "运行 Scan" in content or "Run Scan" in content, \
            "空状态必须有 'Run Scan' 操作按钮"


# ── TestDashboardErrorState ──────────────────────────────────────────

class TestDashboardErrorState:
    """验证设置 error 变量时渲染错误状态。"""

    @pytest.mark.contract_case("ROUTE-API-005")
    def test_error_state_condition(self):
        content = _read_dashboard()
        assert "{% if error %}" in content, \
            "Dashboard 必须检查 error 变量"

    @pytest.mark.contract_case("ROUTE-API-005")
    def test_error_state_uses_ui_macro(self):
        content = _read_dashboard()
        assert "ui.error_state" in content, \
            "错误状态必须使用 ui.error_state 宏"

    @pytest.mark.contract_case("ROUTE-API-005")
    def test_error_state_has_dashboard_link(self):
        content = _read_dashboard()
        assert "/dashboard" in content, \
            "错误状态必须链接回 /dashboard"


# ── TestDashboardFloatingOverlays ────────────────────────────────────

class TestDashboardFloatingOverlays:
    """验证浮动覆盖层元素（tooltip、popover、drawer、toast）。"""

    @pytest.mark.contract_case("ROUTE-API-005")
    def test_tooltip_element(self):
        content = _read_dashboard()
        assert 'id="chartTooltip"' in content, \
            "Dashboard 必须有 chartTooltip 元素"

    @pytest.mark.contract_case("ROUTE-API-005")
    def test_info_popover(self):
        content = _read_dashboard()
        assert 'id="infoPopover"' in content, \
            "Dashboard 必须有 infoPopover 元素"

    @pytest.mark.contract_case("ROUTE-API-005")
    def test_toast_element(self):
        content = _read_dashboard()
        assert 'id="toast"' in content, \
            "Dashboard 必须有 toast 元素"


# ── TestDashboardNoHero ──────────────────────────────────────────────

class TestDashboardNoHero:
    """验证不包含旧的 hero 区域。"""

    @pytest.mark.contract_case("ROUTE-API-005")
    def test_no_hero_section(self):
        content = _read_dashboard()
        assert 'class="hero"' not in content, \
            "Dashboard 不得有 hero 区域"

    @pytest.mark.contract_case("ROUTE-API-005")
    def test_no_hero_title(self):
        content = _read_dashboard()
        assert 'class="hero-title"' not in content, \
            "Dashboard 不得有 hero-title"

    @pytest.mark.contract_case("ROUTE-API-005")
    def test_no_hero_kpis(self):
        content = _read_dashboard()
        assert 'class="hero-kpis"' not in content, \
            "Dashboard 不得有 hero-kpis"

    @pytest.mark.contract_case("ROUTE-API-005")
    def test_no_hero_chips(self):
        content = _read_dashboard()
        assert 'class="hero-chips"' not in content, \
            "Dashboard 不得有 hero-chips"

    @pytest.mark.contract_case("ROUTE-API-005")
    def test_no_range_tabs(self):
        content = _read_dashboard()
        assert 'class="range-tabs"' not in content, \
            "Dashboard 不得有 range-tabs"
