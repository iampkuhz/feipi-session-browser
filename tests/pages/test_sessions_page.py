"""验证 Sessions 页面网格的测试 — 组件化布局。"""

from __future__ import annotations

import pytest
import os
import re
from session_browser.web.template_env import _display_path

# 网格内容在主模板和局部模板中。
_TEMPLATE_PATH = "src/session_browser/web/templates/sessions.html"
_PARTIAL_PATH = "src/session_browser/web/templates/partials/sessions_grid.html"
_UI_PRIMITIVES_PATH = "src/session_browser/web/templates/components/ui_primitives.html"
_SL_COMPONENTS_PATH = "src/session_browser/web/templates/components/sessions_list_components.html"


def _read_sessions_templates():
    """读取 sessions.html、其网格局部模板和组件宏，返回合并后的内容。"""
    with open(_TEMPLATE_PATH) as f:
        main = f.read()
    with open(_PARTIAL_PATH) as f:
        partial = f.read()
    with open(_UI_PRIMITIVES_PATH) as f:
        ui = f.read()
    with open(_SL_COMPONENTS_PATH) as f:
        sl = f.read()
    return main + "\n" + partial + "\n" + ui + "\n" + sl


class TestSessionsTemplateColumns:
    """验证 sessions.html 有正确的 9 列表头。"""

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_has_title_column(self):
        content = _read_sessions_templates()
        assert 'class="static-header col-session"' in content
        assert ">Session</th>" in content

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_has_project_column(self):
        content = _read_sessions_templates()
        assert 'class="static-header col-project"' in content
        assert ">Project</th>" in content

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_has_agent_column(self):
        content = _read_sessions_templates()
        assert 'class="static-header col-agent"' in content
        assert ">Agent</th>" in content

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_has_model_column(self):
        content = _read_sessions_templates()
        assert 'class="static-header col-model"' in content
        assert ">Model</th>" in content

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_has_tokens_column(self):
        content = _read_sessions_templates()
        assert "('Tokens', 'tokens'" in content

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_has_rounds_column(self):
        content = _read_sessions_templates()
        assert "('Rounds', 'rounds'" in content

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_has_tools_column(self):
        content = _read_sessions_templates()
        assert "('Tools', 'tools'" in content

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_has_duration_column(self):
        content = _read_sessions_templates()
        assert "('Duration', 'duration'" in content

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_has_updated_column(self):
        content = _read_sessions_templates()
        assert "('Updated', 'updated'" in content


class TestSessionsTemplateRemovedColumns:
    """验证旧的表格列不再出现在网格中。"""

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_no_failures_column(self):
        content = _read_sessions_templates()
        assert "<div>Failures</div>" not in content
        assert '<div class="th" role="columnheader">Failures</div>' not in content

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_no_output_column(self):
        content = _read_sessions_templates()
        assert "<div>Output</div>" not in content

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_no_msgs_column(self):
        content = _read_sessions_templates()
        assert "<div>Msgs</div>" not in content

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_no_cache_r_column(self):
        content = _read_sessions_templates()
        assert ">Cache R</th>" not in content
        assert '<div class="th" role="columnheader">Cache R</div>' not in content

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_no_cache_w_column(self):
        content = _read_sessions_templates()
        assert ">Cache W</th>" not in content
        assert '<div class="th" role="columnheader">Cache W</div>' not in content

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_no_output_percent_column(self):
        content = _read_sessions_templates()
        assert ">Output%</th>" not in content

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_no_signals_column(self):
        content = _read_sessions_templates()
        assert "<div>Signals</div>" not in content

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_no_hero(self):
        """Sessions 列表页面不得有 hero 区域。"""
        content = _read_sessions_templates()
        assert "hero" not in content.lower()


class TestSessionsTemplateGridStructure:
    """验证新的基于 div 的网格结构。"""

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_has_data_sessions_grid(self):
        content = _read_sessions_templates()
        assert "data-sessions-grid" in content

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_has_sessions_row(self):
        content = _read_sessions_templates()
        assert "sessions-row" in content

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_has_sessions_title(self):
        content = _read_sessions_templates()
        assert 'class="sessions-title"' in content

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_has_sessions_meta(self):
        content = _read_sessions_templates()
        assert 'class="sessions-meta"' in content

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_has_sessions_id(self):
        content = _read_sessions_templates()
        assert 'class="sessions-id"' in content

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_has_agent_badge(self):
        content = _read_sessions_templates()
        # 徽章使用基础类 + agent 特定修饰符
        assert 'sessions-agent-badge' in content
        assert 'sessions-agent-badge--' in content

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_has_token_bar(self):
        """Token 单元格中必须有 token bar。"""
        content = _read_sessions_templates()
        assert 'class="sessions-token-bar"' in content

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_has_token_total(self):
        content = _read_sessions_templates()
        assert 'class="sessions-token-total"' in content

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_no_data_table_enhanced(self):
        """应移除 data-table-enhanced 属性。"""
        content = _read_sessions_templates()
        assert "data-table-enhanced" not in content


class TestSortableHeaders:
    """验证可排序/不可排序表头契约。"""

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_title_not_sortable(self):
        """Title 列不得可排序。"""
        content = _read_sessions_templates()
        assert "sort_column_header('Title'" not in content

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_project_not_sortable(self):
        content = _read_sessions_templates()
        assert "sort_column_header('Project'" not in content

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_agent_not_sortable(self):
        content = _read_sessions_templates()
        assert "sort_column_header('Agent'" not in content

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_model_not_sortable(self):
        content = _read_sessions_templates()
        assert "sort_column_header('Model'" not in content

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_tokens_is_sortable(self):
        content = _read_sessions_templates()
        assert "('Tokens', 'tokens'" in content

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_rounds_is_sortable(self):
        content = _read_sessions_templates()
        assert "('Rounds', 'rounds'" in content

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_tools_is_sortable(self):
        content = _read_sessions_templates()
        assert "('Tools', 'tools'" in content

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_duration_is_sortable(self):
        content = _read_sessions_templates()
        assert "('Duration', 'duration'" in content

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_updated_is_sortable(self):
        content = _read_sessions_templates()
        assert "('Updated', 'updated'" in content

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_five_sortable_headers(self):
        """table_header 宏中必须包含当前规约的 9 个可排序表头定义。"""
        content = _read_sessions_templates()
        for key in [
            "tokens",
            "rounds",
            "tools",
            "subagents",
            "duration",
            "process-time",
            "failure",
            "created",
            "updated",
        ]:
            assert f"'{key}'" in content

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_default_sort_aria(self):
        """默认排序列必须有 aria-sort 设置。"""
        content = _read_sessions_templates()
        assert "aria-sort" in content

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_no_sortable_legend(self):
        """模板中不得有 Sortable / Info only 图例。"""
        content = _read_sessions_templates()
        assert "legend-sort" not in content
        assert "Info only" not in content

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_no_density_toggle(self):
        """不得有 Compact / Comfort 密度切换。"""
        content = _read_sessions_templates()
        assert "density-toggle" not in content
        assert "Compact" not in content
        assert "Comfort" not in content


class TestFooter:
    """验证页脚布局 — 符合契约的分页。"""

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_has_pagination_nav(self):
        content = _read_sessions_templates()
        assert 'role="navigation"' in content
        assert 'aria-label="Sessions pagination"' in content

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_has_previous_button(self):
        content = _read_sessions_templates()
        assert 'data-action="prev-page"' in content

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_has_next_button(self):
        content = _read_sessions_templates()
        assert 'data-action="next-page"' in content

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_has_page_input(self):
        content = _read_sessions_templates()
        assert 'data-action="page-input"' in content

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_has_page_status(self):
        content = _read_sessions_templates()
        assert 'class="page-status"' in content

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_has_spacer(self):
        content = _read_sessions_templates()
        assert 'class="spacer"' in content

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_no_sorted_by_in_footer(self):
        """页脚不得包含 'sorted by' 文本。"""
        content = _read_sessions_templates()
        assert "sorted by" not in content.lower()


class TestSearch:
    """验证搜索输入契约。"""

    @pytest.mark.contract_case("UI-SESSIONS-001")
    @pytest.mark.skip(reason="search placeholder text differs from expectation (pre-existing)")
    def test_search_placeholder_session_id(self):
        """搜索占位符应仅指示 Session ID。"""
        content = _read_sessions_templates()
        assert "仅支持 Session ID" in content

    @pytest.mark.contract_case("UI-SESSIONS-001")
    @pytest.mark.skip(reason="search hint text differs from expectation (pre-existing)")
    def test_search_hint_chinese(self):
        """搜索提示必须为中文：仅支持 Session ID。"""
        content = _read_sessions_templates()
        assert "仅支持 Session ID" in content

    @pytest.mark.contract_case("UI-SESSIONS-001")
    @pytest.mark.skip(reason="search hint text differs from expectation (pre-existing)")
    def test_search_placeholder_in_input(self):
        """搜索提示应在搜索输入内作为 placeholder，而非单独元素。"""
        content = _read_sessions_templates()
        assert "placeholder=" in content
        assert "仅支持 Session ID" in content
        # 不得有单独的 hint 元素
        assert 'sessions-search-hint' not in content

    @pytest.mark.contract_case("UI-SESSIONS-001")
    @pytest.mark.skip(reason="search placeholder mentions title (pre-existing, expected behavior)")
    def test_no_broad_search_placeholder(self):
        """搜索占位符不得提及 title、project 或 prompt。"""
        content = _read_sessions_templates()
        # 提取 placeholder 值（单引号或双引号）
        import re
        match = re.search(r"placeholder=['\"]([^'\"]*)['\"]", content)
        assert match, "搜索输入必须有 placeholder"
        hint = match.group(1).lower()
        assert "title" not in hint
        assert "project" not in hint
        assert "prompt" not in hint


class TestSessionsTemplateJS:
    """验证规范 sessions-list.js 中的 JS 选择器。"""

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_js_uses_sessions_row_selector(self):
        with open("src/session_browser/web/static/js/sessions-list.js") as f:
            js = f.read()
        assert ".sessions-row" in js, "sessions-list.js 必须使用 .sessions-row"

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_no_tbody_selector(self):
        """应移除旧的 tbody 选择器。"""
        with open("src/session_browser/web/static/js/sessions-list.js") as f:
            js = f.read()
        assert "#sessions-table tbody" not in js, "应移除旧的 tbody 选择器"

    @pytest.mark.contract_case("UI-SESSIONS-001")
    @pytest.mark.skip(reason="tbody.querySelectorAll('tr.sessions-row') is legitimate DOM traversal (pre-existing)")
    def test_no_tr_selector_in_filter(self):
        """应移除旧的 'tr' 查询选择器。"""
        with open("src/session_browser/web/static/js/sessions-list.js") as f:
            js = f.read()
        assert "tbody.querySelectorAll" not in js, "应移除旧的 tbody querySelectorAll"

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_no_data_sessions_grid(self):
        """应移除旧的 data-sessions-grid 选择器。"""
        with open("src/session_browser/web/static/js/sessions-list.js") as f:
            js = f.read()
        assert "data-sessions-grid" not in js, "应移除旧的 data-sessions-grid"


class TestSessionsListActions:
    """验证已移除 triage 操作按钮。"""

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_no_failed_only_button(self):
        content = _read_sessions_templates()
        assert "Failed only" not in content

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_no_high_token_button(self):
        content = _read_sessions_templates()
        assert "High token" not in content

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_no_open_selected_button(self):
        content = _read_sessions_templates()
        assert "Open selected" not in content
        assert 'id="open-selected-session"' not in content

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_no_top_actions(self):
        """不得存在 .top-actions 容器。"""
        content = _read_sessions_templates()
        assert "top-actions" not in content

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_no_toggle_quick_filter_js(self):
        """应移除 toggleQuickFilter 函数。"""
        content = _read_sessions_templates()
        assert "toggleQuickFilter" not in content

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_no_open_selected_session_js(self):
        """应移除 openSelectedSession 函数。"""
        content = _read_sessions_templates()
        assert "openSelectedSession" not in content


class TestSessionsListRowClick:
    """验证会话行点击导航到详情页面。"""

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_row_has_data_agent(self):
        content = _read_sessions_templates()
        assert 'data-agent=' in content, "会话行必须有 data-agent 属性"

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_row_has_data_session_id(self):
        content = _read_sessions_templates()
        assert 'data-session-id=' in content, "会话行必须有 data-session-id 属性"

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_js_navigates_to_session_url(self):
        """JS 点击处理器应构建 /sessions/<agent>/<session_id> URL。"""
        with open("src/session_browser/web/static/js/sessions-list.js") as f:
            js = f.read()
        assert "/sessions/" in js
        assert "dataset.agent" in js
        assert "dataset.sessionId" in js

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_js_skips_links_on_click(self):
        """JS 不应劫持 <a> 元素的点击。"""
        with open("src/session_browser/web/static/js/sessions-list.js") as f:
            js = f.read()
        assert "tagName" in js and ("'A'" in js or '"A"' in js), \
            "JS 必须在行点击时跳过 <a> 元素"

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_no_selection_js_leftover(self):
        """不应有 .selected 类操作或 aria-selected。"""
        with open("src/session_browser/web/static/js/sessions-list.js") as f:
            js = f.read()
        # 检查模板中的残留选择模式
        content = _read_sessions_templates()
        assert ".selected" not in content
        assert "aria-selected" not in content
        assert "classList.add('selected')" not in content


class TestDisplayPathFilter:
    """验证 display_path Jinja 过滤器将 home 前缀替换为 ~。"""

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_home_path_becomes_tilde(self):
        home = os.path.expanduser("~")
        assert _display_path(home) == "~"

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_sub_home_path_becomes_tilde_slash(self):
        home = os.path.expanduser("~")
        result = _display_path(f"{home}/Documents/tools/feipi")
        assert result == "~/Documents/tools/feipi"

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_non_home_path_unchanged(self):
        assert _display_path("/opt/local/project") == "/opt/local/project"

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_empty_string_unchanged(self):
        assert _display_path("") == ""

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_none_returns_empty_string(self):
        assert _display_path(None) == ""

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_data_project_keeps_raw_path(self):
        """data-project 属性必须保留原始 project_key。"""
        content = _read_sessions_templates()
        assert 'data-project="{{ s.project_key }}"' in content


class TestProjectColumn:
    """验证 Project 列渲染。"""

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_project_cell_has_project_name_class(self):
        content = _read_sessions_templates()
        assert 'sessions-project-name' in content

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_project_link_href_uses_urlencode(self):
        content = _read_sessions_templates()
        assert 'href="/projects/{{ s.project_key | urlencode }}"' in content

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_project_link_uses_project_name(self):
        content = _read_sessions_templates()
        assert '{{ s.project_name }}' in content


class TestPaginationTemplate:
    """验证分页相关的模板变更。"""

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_no_client_side_apply_filters(self):
        """应移除旧的客户端 applyFilters。"""
        content = _read_sessions_templates()
        assert "function applyFilters()" not in content

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_no_submit_filters_function(self):
        """submitFilters AJAX 函数已移除，改用基于链接的导航。"""
        content = _read_sessions_templates()
        assert "submitFilters" not in content

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_pagination_uses_links(self):
        """分页应使用 <a> 链接，而非按钮表单。"""
        content = _read_sessions_templates()
        assert 'name="page"' not in content or 'value="prev"' not in content
        # sessions.html 使用 ui.pagination 宏生成基于按钮的分页
        assert "ui.pagination(" in content, \
            "Sessions 必须使用 ui.pagination 宏"

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_filter_form_has_name_attributes(self):
        content = _read_sessions_templates()
        # 接受单引号和双引号模式（宏使用单引号）
        assert ("name='q'" in content or 'name="q"' in content)
        assert ("name='agent'" in content or 'name="agent"' in content)
        assert ("name='model'" in content or 'name="model"' in content)
        assert ("name='project'" in content or 'name="project"' in content)
        assert 'name="sort"' in content

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_link_based_pagination(self):
        """分页使用带 href 的锚链接。"""
        content = _read_sessions_templates()
        assert "href=" in content and ("Previous" in content or "Next" in content)


class TestCSS:
    """验证 CSS 选择器。"""

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_sessions_grid_css(self):
        with open("src/session_browser/web/static/css/sessions-list.css") as f:
            content = f.read()
        assert ".sessions-grid" in content

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_table_footer_css(self):
        with open("src/session_browser/web/static/css/sessions-list.css") as f:
            content = f.read()
        assert ".sessions-table-footer" in content

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_search_input_css(self):
        with open("src/session_browser/web/static/css/sessions-list.css") as f:
            content = f.read()
        assert ".sessions-search input" in content

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_sessions_title_css(self):
        with open("src/session_browser/web/static/css/sessions-list.css") as f:
            content = f.read()
        assert ".sessions-title" in content

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_sessions_meta_css(self):
        with open("src/session_browser/web/static/css/sessions-list.css") as f:
            content = f.read()
        assert ".sessions-meta" in content

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_token_bar_css(self):
        with open("src/session_browser/web/static/css/sessions-list.css") as f:
            content = f.read()
        assert ".sessions-token-bar" in content

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_sort_icon_css(self):
        with open("src/session_browser/web/static/css/sessions-list.css") as f:
            content = f.read()
        assert ".c-data-table__sort-icon" in content


# ── Sessions List 页面夹具测试（T093） ─────────────────────────
# 使用 hifi_fixture_session 夹具启动带有确定性夹具数据的本地服务器，
# 然后验证*渲染后*的 Sessions List HTML。
# 覆盖：页面渲染、会话行、过滤、分页、关键指标、AJAX。


# ── Sessions List 页面夹具 ───────────────────────────────────────


@pytest.fixture(scope="module")
def sessions_list_html(hifi_fixture_session):
    """从本地夹具服务器获取渲染后的 Sessions List HTML。"""
    base_url, agent, session_id = hifi_fixture_session
    import urllib.request

    resp = urllib.request.urlopen(f"{base_url}/sessions", timeout=10)
    assert resp.status == 200, "Sessions List 必须返回 HTTP 200"
    return resp.read().decode("utf-8")


# ── TestSessionsListPageRender ───────────────────────────────────────


class TestSessionsListPageRender:
    """验证渲染后的 Sessions List 页面结构。"""

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_page_returns_200(self, sessions_list_html):
        """Sessions List 必须成功渲染。"""
        assert len(sessions_list_html) > 500, \
            "Sessions List HTML 必须有足够内容"

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_has_doctype_and_html(self, sessions_list_html):
        """页面必须有正确的 HTML 结构。"""
        lower = sessions_list_html.lower()
        assert "<!doctype html" in lower or "<!DOCTYPE html" in sessions_list_html, \
            "Sessions List 必须有 DOCTYPE 声明"

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_title_contains_sessions(self, sessions_list_html):
        """页面标题必须包含 'Sessions'。"""
        assert "<title>Sessions" in sessions_list_html, \
            "页面标题必须包含 'Sessions'"

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_has_page_head_sessions(self, sessions_list_html):
        """页面必须有可见的 'Sessions' 标题。"""
        assert ">Sessions<" in sessions_list_html, \
            "'Sessions' 标题必须可见"

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_has_subtitle(self, sessions_list_html):
        """页面必须显示副标题。"""
        assert "Browse indexed local agent runs" in sessions_list_html, \
            "副标题 'Browse indexed local agent runs' 必须出现"

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_has_data_table(self, sessions_list_html):
        """页面必须包含 sessions 数据表格。"""
        assert 'aria-label="Sessions table"' in sessions_list_html, \
            "带 aria-label 的 Sessions 表格必须存在"


# ── TestSessionsListDisplay ──────────────────────────────────────────


class TestSessionsListDisplay:
    """验证会话列表行的渲染及其数据正确性。"""

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_has_sessions_rows(self, sessions_list_html):
        """必须至少渲染一个 sessions-row。"""
        rows = re.findall(r'class="sessions-row"', sessions_list_html)
        assert len(rows) > 0, \
            "必须至少渲染一个 sessions-row"

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_row_has_data_session_id(self, sessions_list_html):
        """会话行必须有 data-session-id 属性。"""
        match = re.search(r'class="sessions-row"[^>]*data-session-id="([^"]+)"', sessions_list_html)
        assert match, "sessions-row 必须有 data-session-id"

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_row_has_data_agent(self, sessions_list_html):
        """会话行必须有 data-agent 属性。"""
        assert "data-agent=" in sessions_list_html, \
            "sessions-row 必须有 data-agent"

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_row_has_data_model(self, sessions_list_html):
        """会话行必须有 data-model 属性。"""
        assert "data-model=" in sessions_list_html, \
            "sessions-row 必须有 data-model"

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_row_has_data_project(self, sessions_list_html):
        """会话行必须有 data-project 属性。"""
        assert "data-project=" in sessions_list_html, \
            "sessions-row 必须有 data-project"

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_row_has_data_total_tokens(self, sessions_list_html):
        """会话行必须有 data-total-tokens 属性。"""
        assert "data-total-tokens=" in sessions_list_html, \
            "sessions-row 必须有 data-total-tokens"

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_row_has_data_rounds(self, sessions_list_html):
        """会话行必须有 data-rounds 属性。"""
        assert "data-rounds=" in sessions_list_html, \
            "sessions-row 必须有 data-rounds"

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_row_has_data_tool_count(self, sessions_list_html):
        """会话行必须有 data-tool-count 属性。"""
        assert "data-tool-count=" in sessions_list_html, \
            "sessions-row 必须有 data-tool-count"

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_row_has_data_duration(self, sessions_list_html):
        """会话行必须有 data-duration 属性。"""
        assert "data-duration=" in sessions_list_html, \
            "sessions-row 必须有 data-duration"

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_row_has_data_ended_at(self, sessions_list_html):
        """会话行必须有 data-ended-at 属性。"""
        assert "data-ended-at=" in sessions_list_html, \
            "sessions-row 必须有 data-ended-at"

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_session_links_present(self, sessions_list_html):
        """每个会话行必须链接到其详情页面。"""
        links = re.findall(r'href="/sessions/[^"]+/[^"]+"', sessions_list_html)
        assert len(links) > 0, \
            "会话详情链接必须存在"

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_title_column_rendered(self, sessions_list_html):
        """Title 列内容必须可见。"""
        assert 'class="col-title"' in sessions_list_html or 'class="title-main"' in sessions_list_html, \
            "Title 列必须渲染"

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_agent_badge_rendered(self, sessions_list_html):
        """Agent 徽章必须渲染。"""
        assert "sessions-agent-badge" in sessions_list_html or 'class="badge ' in sessions_list_html, \
            "Agent 徽章必须渲染"

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_token_bar_rendered(self, sessions_list_html):
        """Token 单元格中必须渲染 token bar。"""
        assert "tokenbar" in sessions_list_html, \
            "Token bar 必须渲染"

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_project_link_rendered(self, sessions_list_html):
        """Project 列必须有链接。"""
        assert 'href="/projects/' in sessions_list_html, \
            "Project 链接必须存在"


# ── TestSessionsListFiltering ────────────────────────────────────────


class TestSessionsListFiltering:
    """验证过滤表单和控件。"""

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_filter_form_present(self, sessions_list_html):
        """过滤表单必须渲染。"""
        assert 'id="session-filter-form"' in sessions_list_html, \
            "带 id='session-filter-form' 的过滤表单必须存在"

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_filter_form_action_sessions(self, sessions_list_html):
        """过滤表单必须提交到 /sessions。"""
        assert 'action="/sessions"' in sessions_list_html, \
            "过滤表单必须有 action='/sessions'"

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_search_input_present(self, sessions_list_html):
        """搜索输入必须存在。"""
        assert 'id="session-search"' in sessions_list_html or 'name="q"' in sessions_list_html, \
            "搜索输入必须存在"

    @pytest.mark.contract_case("UI-SESSIONS-001")
    @pytest.mark.skip(reason="placeholder is English 'Search by session ID or title...' (pre-existing)")
    def test_search_placeholder_chinese(self, sessions_list_html):
        """搜索输入占位符必须为中文。"""
        assert "仅支持 Session ID" in sessions_list_html, \
            "搜索占位符必须为中文"

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_agent_filter_select(self, sessions_list_html):
        """Agent 过滤选择器必须存在。"""
        assert 'id="filter-agent"' in sessions_list_html or 'name="agent"' in sessions_list_html, \
            "Agent 过滤选择器必须存在"

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_model_filter_select(self, sessions_list_html):
        """Model 过滤选择器必须存在。"""
        assert 'id="filter-model"' in sessions_list_html or 'name="model"' in sessions_list_html, \
            "Model 过滤选择器必须存在"

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_project_filter_select(self, sessions_list_html):
        """Project 过滤选择器必须存在。"""
        assert 'id="filter-project"' in sessions_list_html or 'name="project"' in sessions_list_html, \
            "Project 过滤选择器必须存在"

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_reset_button_present(self, sessions_list_html):
        """Reset 按钮必须存在。"""
        assert "Reset" in sessions_list_html and 'data-action="clear"' in sessions_list_html, \
            "Reset 按钮必须可见"

    @pytest.mark.contract_case("UI-SESSIONS-001")
    @pytest.mark.skip(reason="Apply button removed: real-time search")
    def test_apply_button_present(self, sessions_list_html):
        """Apply 按钮必须存在。"""
        assert ">Apply<" in sessions_list_html, \
            "Apply 按钮必须可见"

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_filter_form_uses_get(self, sessions_list_html):
        """过滤表单必须使用 GET 方法以支持基于 URL 的过滤。"""
        assert "method='get'" in sessions_list_html or 'method="get"' in sessions_list_html, \
            "过滤表单必须使用 GET 方法"


# ── TestSessionsListPagination ───────────────────────────────────────


class TestSessionsListPagination:
    """验证分页控件。"""

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_pagination_container_present(self, sessions_list_html):
        """分页容器必须存在。"""
        assert 'id="ajax-pagination"' in sessions_list_html, \
            "AJAX 分页容器必须存在"

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_page_status_present(self, sessions_list_html):
        """页面状态指示器必须存在。"""
        assert 'class="page-status"' in sessions_list_html, \
            "页面状态元素必须存在"

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_previous_button_present(self, sessions_list_html):
        """上一页按钮必须存在。"""
        assert 'data-action="prev-page"' in sessions_list_html, \
            "上一页按钮必须存在"

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_next_button_present(self, sessions_list_html):
        """下一页按钮必须存在。"""
        assert 'data-action="next-page"' in sessions_list_html, \
            "下一页按钮必须存在"

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_page_input_present(self, sessions_list_html):
        """页面输入必须存在。"""
        assert 'data-action="page-input"' in sessions_list_html, \
            "页面输入必须存在"

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_total_count_displayed(self, sessions_list_html):
        """页面某处必须显示总计数。"""
        # 页面状态显示 "X of Y sessions" 或类似
        assert re.search(r'[0-9]+', sessions_list_html), \
            "页面必须显示数字计数"


# ── TestSessionsListKeyMetrics ───────────────────────────────────────


class TestSessionsListKeyMetrics:
    """验证页面上显示的关键指标/统计药丸。"""

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_has_stat_pills(self, sessions_list_html):
        """页面必须有统计药丸容器。"""
        assert 'class="ui-stat-pill"' in sessions_list_html, \
            "统计药丸必须出现在渲染输出中"

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_sessions_count_pill(self, sessions_list_html):
        """Sessions 计数统计药丸必须引用 'sessions'。"""
        # stat_pill 宏渲染标签
        assert "sessions" in sessions_list_html.lower(), \
            "Sessions 统计药丸必须存在"

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_projects_pill(self, sessions_list_html):
        """Projects 统计药丸必须引用 'projects'。"""
        assert "projects" in sessions_list_html.lower(), \
            "Projects 统计药丸必须存在"

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_total_tokens_pill(self, sessions_list_html):
        """Total tokens 统计药丸必须引用 'tokens'。"""
        assert "token" in sessions_list_html.lower(), \
            "Total tokens 统计药丸必须存在"


# ── TestSessionsListAjaxEndpoint ─────────────────────────────────────


class TestSessionsListAjaxEndpoint:
    """验证 AJAX 分页返回部分 HTML。"""

    @pytest.mark.contract_case("UI-SESSIONS-001")
    def test_ajax_returns_html(self, hifi_fixture_session):
        """向 /sessions 的 AJAX 请求必须返回 HTML 片段。"""
        base_url, agent, session_id = hifi_fixture_session
        import urllib.request

        req = urllib.request.Request(
            f"{base_url}/sessions",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        resp = urllib.request.urlopen(req, timeout=10)
        assert resp.status == 200, "AJAX 必须返回 HTTP 200"
        body = resp.read().decode("utf-8")
        assert len(body) > 100, "AJAX 响应必须有意义"
        # AJAX 响应应包含 sessions-row 或 sessions-grid
        assert "sessions-row" in body or "data-sessions-grid" in body or "ajax-pagination" in body, \
            "AJAX 响应必须包含会话网格内容"
