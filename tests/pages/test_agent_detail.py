"""Agent 详情页（agent.html）测试。

agent.html 的页面级 pytest，覆盖模板结构、头部、
指标卡片、信息按钮、模型细分表、会话表、
搜索输入、分页、空状态/错误状态，以及无过时模式。

T150 -- Agent 详情页：添加页面专属 pytest。
"""

from __future__ import annotations

import pytest
import os
import re
import glob as _glob

_AGENT_PATH = "src/session_browser/web/templates/agent.html"
_UI_PRIMITIVES_PATH = "src/session_browser/web/templates/components/ui_primitives.html"
_UI_PRIMITIVES_DIR = "src/session_browser/web/templates/components/ui_primitives"


def _read(path: str) -> str:
    with open(path) as f:
        return f.read()


def _read_template() -> str:
    return _read(_AGENT_PATH)


def _read_ui_primitives_with_splits() -> str:
    """Read ui_primitives wrapper + all split sub-components."""
    parts = [_read(_UI_PRIMITIVES_PATH)]
    for fp in sorted(_glob.glob(os.path.join(_UI_PRIMITIVES_DIR, "*.html"))):
        parts.append(_read(fp))
    return "\n".join(parts)


# -- TestAgentDetailTemplate ------------------------------------------------

class TestAgentDetailTemplate:
    """验证 agent Jinja2 模板的结构渲染。"""

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_template_file_exists(self):
        """agent.html 必须存在于磁盘上。"""
        assert os.path.isfile(_AGENT_PATH), \
            f"{_AGENT_PATH} 必须存在"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_extends_base(self):
        """Agent 必须继承 base.html。"""
        content = _read_template()
        assert '{% extends "base.html" %}' in content, \
            "Agent 必须继承 base.html"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_active_page_set(self):
        """Agent 必须设置 active_page = 'agents'。"""
        content = _read_template()
        assert "active_page = 'agents'" in content, \
            "Agent 必须设置 active_page = 'agents'"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_ui_primitives_imported(self):
        """Agent 必须导入 ui_primitives.html。"""
        content = _read_template()
        assert 'import "components/ui_primitives.html"' in content, \
            "Agent 必须导入 ui_primitives.html"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_no_inline_onclick(self):
        """Agent 不能使用内联 onclick 处理程序。"""
        content = _read_template()
        matches = re.findall(r'\bonclick\s*=', content, re.IGNORECASE)
        assert len(matches) == 0, \
            f"Agent 不得有 inline onclick，发现 {len(matches)} 次"


# -- TestAgentDetailImports -------------------------------------------------

class TestAgentDetailImports:
    """验证 CSS 和 JS 导入方式。

    Agent 详情页依赖 base.html 提供共享 CSS/JS，
    没有自己页面专属的 CSS/JS 文件。
    """

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_relies_on_base_for_css_js(self):
        """Agent 必须继承提供共享 CSS/JS 的 base.html。"""
        content = _read_template()
        assert '{% extends "base.html" %}' in content, \
            "Agent 必须继承 base.html 以获取共享 CSS/JS"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_no_page_specific_css_import(self):
        """Agent 不能导入页面专属 CSS（使用 base 共享 CSS）。"""
        content = _read_template()
        assert 'href="/static/css/agent.css"' not in content, \
            "Agent 不应导入页面专属 CSS"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_no_page_specific_js_import(self):
        """Agent 不能导入页面专属 JS（使用 base 共享 JS）。"""
        content = _read_template()
        assert 'src="/static/js/agent.js"' not in content, \
            "Agent 不应导入页面专属 JS"


# -- TestAgentDetailHeader --------------------------------------------------

class TestAgentDetailHeader:
    """验证头部结构。"""

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_header_section_present(self):
        """Agent 必须有 header 区域。"""
        content = _read_template()
        assert 'class="header"' in content, \
            "Agent 必须有 header 区域"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_back_button_present(self):
        """Header 必须使用带 data-action='back' 的 ui.back_button 宏。"""
        content = _read_template()
        assert "ui.back_button(" in content, \
            "Header 必须使用 ui.back_button 宏"
        assert "data_action='back'" in content, \
            "返回按钮必须有 data-action='back'"
        assert "'/agents'" in content, \
            "返回按钮必须链接到 /agents"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_agent_title_present(self):
        """Header 必须包含 agent-title。"""
        content = _read_template()
        assert 'class="agent-title"' in content, \
            "Header 必须有 agent-title"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_agent_subtitle_present(self):
        """Header 必须包含 agent-subtitle。"""
        content = _read_template()
        assert 'class="agent-subtitle"' in content, \
            "Header 必须有 agent-subtitle"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_breadcrumb_present(self):
        """面包屑必须链接到 Dashboard 和 Agents。"""
        content = _read_template()
        assert 'href="/dashboard"' in content, \
            "面包屑必须链接到 /dashboard"
        assert 'href="/agents"' in content, \
            "面包屑必须链接到 /agents"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_emoji_aria_hidden_in_title(self):
        """Agent 标题的 emoji 必须有 aria-hidden='true'。"""
        content = _read_template()
        assert 'class="emoji" aria-hidden="true"' in content, \
            "Agent 标题 emoji 必须有 aria-hidden='true'"


# -- TestAgentDetailMetricCards ---------------------------------------------

class TestAgentDetailMetricCards:
    """验证 6 个指标卡片的标签和结构。"""

    _EXPECTED_LABELS = [
        "Sessions",
        "Projects",
        "Input-side Tokens",
        "Output Tokens",
        "Cache Reuse",
        "Failed Tools",
    ]

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_metric_grid_present(self):
        """Agent 必须有 metric-grid 区域。"""
        content = _read_template()
        assert 'class="metric-grid"' in content, \
            "Agent 必须有 metric-grid 区域"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_metric_grid_aria_label(self):
        """指标网格必须有 aria-label。"""
        content = _read_template()
        assert 'aria-label="Agent detail metrics"' in content, \
            "指标网格必须有 aria-label='Agent detail metrics'"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_six_metric_cards(self):
        """Agent 必须恰好有 6 个指标卡片。"""
        content = _read_template()
        cards = re.findall(r'class="metric-card"', content)
        assert len(cards) == 6, \
            f"Agent 必须恰好有 6 个指标卡片，发现 {len(cards)} 个"

    @pytest.mark.parametrize("label", _EXPECTED_LABELS)
    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_metric_card_labels(self, label):
        """每个指标卡片必须有预期的标签文本。"""
        content = _read_template()
        assert f">{label}" in content or f">{label} " in content, \
            f"Agent 必须有标签为 '{label}' 的指标卡片"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_metric_cards_have_icons(self):
        """每个指标卡片必须有 metric-icon 元素。"""
        content = _read_template()
        icons = re.findall(r'class="metric-icon', content)
        assert len(icons) >= 6, \
            f"Agent 必须至少有 6 个 metric-icon 元素，发现 {len(icons)} 个"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_metric_icons_have_emoji_aria_hidden(self):
        """每个 metric-icon 必须有 aria-hidden 属性。"""
        content = _read_template()
        icons = re.findall(
            r'class="metric-icon[^"]*"[^>]*aria-hidden="true"', content
        )
        assert len(icons) >= 6, \
            f"Agent 必须至少有 6 个带 aria-hidden 的 metric-icon 元素，发现 {len(icons)} 个"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_metric_cards_have_label_class(self):
        """每个指标卡片必须有 metric-card__label 元素。"""
        content = _read_template()
        labels = re.findall(r'class="metric-card__label"', content)
        assert len(labels) >= 6, \
            f"Agent 必须至少有 6 个 metric-card__label 元素，发现 {len(labels)} 个"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_metric_cards_have_value_class(self):
        """每个指标卡片必须有 metric-card__value 元素。"""
        content = _read_template()
        values = re.findall(r'class="[^"]*metric-card__value', content)
        assert len(values) >= 6, \
            f"Agent 必须至少有 6 个 metric-card__value 元素，发现 {len(values)} 个"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_six_info_buttons_on_metrics(self):
        """每个指标卡片必须有带 data-action='info' 的信息按钮。"""
        content = _read_template()
        buttons = re.findall(r'data-action="info"', content)
        # 指标上 6 个 + 模型细分 1 个 + 会话 1 个 = 至少 8 个
        assert len(buttons) >= 8, \
            f"Agent 必须至少有 8 个信息按钮，发现 {len(buttons)} 个"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_info_buttons_use_info_icon_class(self):
        """信息按钮必须使用 icon-button--info 类。"""
        content = _read_template()
        assert 'icon-button--info' in content, \
            "信息按钮必须使用 icon-button--info 类"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_info_buttons_have_aria_label(self):
        """每个信息按钮必须有 aria-label（title 属性）。"""
        content = _read_template()
        # icon-button--info 按钮使用 title 作为工具提示文本
        pattern = r'icon-button--info"[^>]*data-action="info"'
        matches = re.findall(pattern, content)
        assert len(matches) >= 6, \
            f"必须至少有 6 个带 data-action 的 icon-button--info 按钮，发现 {len(matches)} 个"


# -- TestAgentDetailModelBreakdown ------------------------------------------

class TestAgentDetailModelBreakdown:
    """验证 Model Breakdown 区域结构。"""

    _EXPECTED_COLUMNS = [
        "Model", "Sessions", "Tokens", "Cache Reuse",
        "Tools", "Failed", "Avg Duration",
    ]

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_section_head_present(self):
        """Model breakdown 必须使用渲染 table-toolbar 的 ui.table_card 宏。"""
        content = _read_template()
        assert "ui.table_card(" in content, \
            "Model breakdown 必须使用 ui.table_card 宏"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_section_title_present(self):
        """Model breakdown 必须通过 table_card 有 card-title。"""
        content = _read_template()
        assert "ui.table_card(" in content, \
            "Model breakdown 必须使用 ui.table_card 宏，该宏渲染 card-title"
        assert "Model Breakdown" in content, \
            "章节标题必须包含 'Model Breakdown'"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_section_sub_present(self):
        """Model breakdown 必须通过 table_card 的 subtitle 参数有 card-sub。"""
        content = _read_template()
        assert "ui.table_card(" in content, \
            "Model breakdown 必须使用 ui.table_card 宏，该宏渲染 card-sub"
        assert "Avg Duration" in content, \
            "Model breakdown subtitle must mention Avg Duration"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_model_breakdown_conditional(self):
        """Model breakdown 必须在 models > 1 时条件渲染。"""
        content = _read_template()
        assert "{% if models | length > 1 %}" in content, \
            "Model breakdown must be conditionally rendered"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_card_section_class(self):
        """Model breakdown 必须使用渲染 card table-card 类的 ui.table_card 宏。"""
        content = _read_template()
        assert "ui.table_card(" in content, \
            "Model breakdown must use ui.table_card macro which renders 'card table-card'"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_data_table_class(self):
        """Model breakdown 表必须使用 data-table 类。"""
        content = _read_template()
        assert 'class="data-table"' in content, \
            "Model breakdown table must use data-table class"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_table_wrap_present(self):
        """Model breakdown 表必须在渲染 table-wrap 的 ui.table_card 内。"""
        content = _read_template()
        assert "ui.table_card(" in content, \
            "Model breakdown must use ui.table_card macro which renders table-wrap"

    @pytest.mark.parametrize("column", _EXPECTED_COLUMNS)
    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_column_headers_present(self, column):
        """Model breakdown 表必须有所有预期的列标题。"""
        content = _read_template()
        assert column in content, \
            f"Model breakdown table must have '{column}' column header"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_seven_column_headers_in_model_table(self):
        """Model breakdown 表必须恰好有 7 个列标题。"""
        content = _read_template()
        # 提取模型细分部分（在 {% if models | length > 1 %} 和 {% endif %} 之间）
        model_start = content.find("{% if models | length > 1 %}")
        assert model_start != -1, "Must have model breakdown conditional"
        # 找到该块对应的 {% endif %}
        rest = content[model_start:]
        # 模型细分在第一个 {% endif %} 结束
        model_end = rest.find("{% endif %}")
        assert model_end != -1, "Model breakdown must have endif"
        model_section = rest[:model_end]
        ths = re.findall(r'<th(?!\w)', model_section)
        assert len(ths) == 7, \
            f"Model breakdown table must have 7 column headers, found {len(ths)}"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_tokenbar_in_model_table(self):
        """Model breakdown 的 tokens 列必须有 tokenbar。"""
        content = _read_template()
        assert 'class="tokenbar"' in content, \
            "Model breakdown must have a tokenbar"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_tokenbar_has_four_segments(self):
        """Tokenbar 必须有 4 个分段（fresh/read/write/out）。"""
        content = _read_template()
        segs = re.findall(
            r'class="t-(fresh|read|write|out)"', content
        )
        assert len(segs) >= 4, \
            f"Tokenbar must have 4 segment types, found {len(segs)}"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_sortable_columns_in_model_table(self):
        """Model breakdown 表必须有可排序列。"""
        content = _read_template()
        sorts = re.findall(r'data-action="sort"', content)
        assert len(sorts) >= 7, \
            f"Model breakdown must have at least 7 sortable columns, found {len(sorts)}"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_sort_keys_in_model_table(self):
        """Model breakdown 可排序列必须有 data-sort-key。"""
        content = _read_template()
        for sort_key in ["model_name", "model_sessions", "model_tokens",
                         "cache_reuse", "model_tools", "model_failed",
                         "avg_duration"]:
            assert f'data-sort-key="{sort_key}"' in content, \
                f"Model table must have data-sort-key='{sort_key}'"


# -- TestAgentDetailSessionsSection -----------------------------------------

class TestAgentDetailSessionsSection:
    """验证 Sessions 区域结构。"""

    _EXPECTED_COLUMNS = [
        "Title", "Project", "Model", "Tokens",
        "Rounds", "Tools", "Failed", "Duration", "Updated",
    ]

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_sessions_section_head_present(self):
        """Sessions 必须使用渲染 table-toolbar 的 ui.table_card 宏。"""
        content = _read_template()
        # agent.html 有两个 table_card 调用：Model Breakdown + Sessions
        count = content.count("ui.table_card(")
        assert count >= 2, \
            f"Agent must have at least 2 ui.table_card calls, found {count}"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_sessions_section_title(self):
        """Sessions 区域标题必须包含 'Sessions'。"""
        content = _read_template()
        assert ">Sessions" in content, \
            "Sessions section must have 'Sessions' title"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_search_input_present(self):
        """Sessions 区域必须通过 table_card search_placeholder 有搜索输入。"""
        content = _read_template()
        # Sessions table_card 传入 search_placeholder 来渲染输入框
        assert "search_placeholder=" in content, \
            "Sessions must pass search_placeholder to table_card"
        # HIFI 契约：搜索输入不能有 id 或 data-search 属性
        assert 'id="session-search"' not in content, \
            "HIFI contract: search input must NOT have id='session-search'"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_search_input_no_data_search(self):
        """HIFI 契约：搜索输入不能有 data-search 属性。"""
        content = _read_template()
        assert 'data-search=' not in content, \
            "HIFI contract: search input must NOT have data-search attribute"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_search_input_has_placeholder(self):
        """搜索输入必须有占位符。"""
        content = _read_template()
        assert 'placeholder=' in content, \
            "Search input must have a placeholder"
        assert "Search" in content, \
            "Search placeholder must mention Search"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_search_input_aria_label(self):
        """搜索输入必须通过 table_card 宏有 aria-label。"""
        content = _read_template()
        assert "search_placeholder=" in content, \
            "Sessions must pass search_placeholder to table_card"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_sessions_table_has_id(self):
        """Sessions 表必须有 id='agent-sessions-table'。"""
        content = _read_template()
        assert 'id="agent-sessions-table"' in content, \
            "Sessions table must have id='agent-sessions-table'"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_card_section_for_sessions(self):
        """Sessions 区域必须使用渲染 card table-card 类的 ui.table_card 宏。"""
        content = _read_template()
        assert "ui.table_card(" in content, \
            "Sessions section must use ui.table_card macro which renders 'card table-card'"

    @pytest.mark.parametrize("column", _EXPECTED_COLUMNS)
    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_column_headers_present(self, column):
        """Sessions 表必须有所有预期的列标题。"""
        content = _read_template()
        assert column in content, \
            f"Sessions table must have '{column}' column header"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_nine_column_headers(self):
        """Sessions 表必须恰好有 9 个列标题。"""
        content = _read_template()
        ths = re.findall(r'<th(?!\w)', content)
        # 模型细分 7 个 + 会话 9 个 = 共 16 个
        assert len(ths) == 16, \
            f"Agent must have 16 total th elements (7 model + 9 sessions), found {len(ths)}"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_sortable_columns_in_sessions_table(self):
        """Sessions 表必须有可排序列（9 列中 7 个可排序）。"""
        content = _read_template()
        for sort_key in ["model", "tokens", "rounds", "tools",
                         "failed", "duration", "updated"]:
            assert f'data-sort-key="{sort_key}"' in content, \
                f"Sessions table must have data-sort-key='{sort_key}'"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_row_has_open_session_action(self):
        """会话行必须有 data-action='open-session'。"""
        content = _read_template()
        assert 'data-action="open-session"' in content, \
            "Session rows must have data-action='open-session'"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_row_has_data_href(self):
        """会话行必须有 data-href 属性。"""
        content = _read_template()
        assert 'data-href="/sessions/' in content, \
            "Session rows must have data-href attribute"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_title_main_present(self):
        """会话行必须有 title-main 元素。"""
        content = _read_template()
        assert 'class="title-main"' in content, \
            "Session row must have a title-main element"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_title_sub_present(self):
        """会话行必须有 title-sub 元素。"""
        content = _read_template()
        assert 'class="title-sub mono"' in content, \
            "Session row must have a title-sub mono element"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_project_link_present(self):
        """会话行必须链接到项目。"""
        content = _read_template()
        assert 'href="/projects/' in content, \
            "Session row must link to project"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_failed_badge_err_class(self):
        """失败的工具必须使用 badge err 类。"""
        content = _read_template()
        assert 'class="badge err"' in content, \
            "Failed tools must use badge err class"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_row_failed_conditional_class(self):
        """行必须有 row--failed 条件类。"""
        content = _read_template()
        assert "row--failed" in content, \
            "Row must have row--failed conditional class"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_relative_time_filter_used(self):
        """Updated 列必须使用 relative_time 过滤器。"""
        content = _read_template()
        assert "relative_time" in content, \
            "Table must use relative_time filter"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_token_cell_in_sessions(self):
        """会话行必须有 token-cell。"""
        content = _read_template()
        assert 'class="token-col token-cell"' in content or 'class="token-cell"' in content, \
            "Session rows must have token-cell"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_token_total_in_sessions(self):
        """Token-cell 必须有 token-total。"""
        content = _read_template()
        assert 'class="token-total"' in content, \
            "Token-cell must have token-total"


# -- TestAgentDetailPagination ----------------------------------------------

class TestAgentDetailPagination:
    """验证分页使用 ui.pagination 宏。"""

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_unified_pagination_present(self):
        """Agent 必须使用 ui.pagination 宏。"""
        content = _read_template()
        assert "ui.pagination(" in content, \
            "Agent must use ui.pagination macro for pagination"


# -- TestAgentDetailEmptyState ----------------------------------------------

class TestAgentDetailEmptyState:
    """验证空状态渲染。"""

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_empty_state_condition(self):
        """模板必须检查 sessions 为假值。"""
        content = _read_template()
        assert "{% else %}" in content, \
            "Template must have an else branch for empty state"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_empty_state_macro_used(self):
        """空状态必须使用 ui.empty_state 宏。"""
        content = _read_template()
        assert "ui.empty_state" in content, \
            "Empty state must use ui.empty_state macro"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_empty_state_message(self):
        """空状态必须显示 '暂无该 Agent 的 Session 数据'。"""
        content = _read_template()
        assert "暂无该 Agent 的 Session 数据" in content, \
            "Empty state must say '暂无该 Agent 的 Session 数据'"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_empty_state_has_back_action(self):
        """空状态必须有返回操作。"""
        content = _read_template()
        assert "data_action='back'" in content or 'data_action="back"' in content, \
            "Empty state must have back action (via ui.button macro)"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_empty_state_has_icon(self):
        """空状态必须有机器人图标。"""
        content = _read_template()
        assert "'\U0001f916'" in content or "\U0001f916" in content, \
            "Empty state must have a robot icon"


# -- TestAgentDetailErrorState ----------------------------------------------

class TestAgentDetailErrorState:
    """验证错误状态渲染。"""

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_error_state_condition(self):
        """模板必须检查 error 变量。"""
        content = _read_template()
        assert "{% if error %}" in content, \
            "Template must check for error variable"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_error_state_uses_ui_macro(self):
        """错误状态必须使用 ui.error_state 宏。"""
        content = _read_template()
        assert "ui.error_state" in content, \
            "Error state must use ui.error_state macro"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_error_state_has_refresh_action(self):
        """错误状态必须有刷新操作。"""
        content = _read_template()
        assert "data_action='refresh'" in content or 'data_action="refresh"' in content, \
            "Error state must have refresh action (via ui.button macro)"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_error_state_has_warning_icon(self):
        """错误状态必须有警告图标。"""
        content = _read_template()
        assert "'⚠️'" in content or "⚠️" in content, \
            "Error state must have a warning icon"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_error_state_has_detail_param(self):
        """错误状态必须传递 detail 参数。"""
        content = _read_template()
        assert "detail=" in content, \
            "Error state must pass detail parameter"


# -- TestAgentDetailNoStalePatterns -----------------------------------------

class TestAgentDetailNoStalePatterns:
    """验证不存在过时模式。"""

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_no_inline_onclick(self):
        """Agent 不能有内联 onclick。"""
        content = _read_template()
        matches = re.findall(r'\bonclick\s*=', content, re.IGNORECASE)
        assert len(matches) == 0, \
            f"Agent must not have inline onclick, found {len(matches)}"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_no_inline_script(self):
        """模板不能有内联脚本块。"""
        content = _read_template()
        script_tags = re.findall(r'<script(?! src)[^>]*>', content)
        assert len(script_tags) == 0, \
            f"Agent must not have inline script tags, found {len(script_tags)}"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_no_inline_style_blocks(self):
        """模板不能有内联样式块。"""
        content = _read_template()
        style_blocks = re.findall(r'<style[^>]*>', content)
        assert len(style_blocks) == 0, \
            f"Agent must not have inline style blocks, found {len(style_blocks)}"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_no_page_header_bem_class(self):
        """Agent 不能使用 page-header BEM 类（使用 header）。"""
        content = _read_template()
        assert 'class="page-header"' not in content, \
            "Agent must not have page-header BEM class"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_no_page_head_class(self):
        """Agent 不能使用 page-head 类（使用 header）。"""
        content = _read_template()
        assert 'class="page-head"' not in content, \
            "Agent must not have page-head class"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_no_hero_section(self):
        """Agent 不能有 hero 区域。"""
        content = _read_template()
        assert 'class="hero"' not in content, \
            "Agent must not have hero section"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_no_select_elements(self):
        """不能有 <select> 元素。"""
        content = _read_template()
        assert '<select' not in content, \
            "Agent must not use select elements"


# -- TestAgentDetailDataActions ---------------------------------------------

class TestAgentDetailDataActions:
    """验证所有必需的 data-action 属性都存在。"""

    _EXPECTED_ACTIONS = [
        "back",
        "info",
        "sort",
        "open-session",
    ]

    @pytest.mark.parametrize("action", _EXPECTED_ACTIONS)
    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_data_action_present(self, action):
        """模板必须有预期的 data-action 属性。"""
        content = _read_template()
        # 同时接受 HTML 属性形式（data-action="back"）和
        # Jinja2 宏关键字形式（data_action='back'）。
        html_form = f'data-action="{action}"'
        macro_form_single = f"data_action='{action}'"
        macro_form_double = f'data_action="{action}"'
        assert html_form in content or macro_form_single in content or macro_form_double in content, \
            f"Template must have data-action='{action}'"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_data_action_back_in_empty_state(self):
        """空状态使用 Jinja2 宏参数 data_action='back'。"""
        content = _read_template()
        assert "data_action='back'" in content or 'data_action="back"' in content, \
            "Template must have back action (via ui.button macro)"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_data_action_refresh_in_error_state(self):
        """错误状态使用 Jinja2 宏参数 data_action='refresh'。"""
        content = _read_template()
        assert "data_action='refresh'" in content or 'data_action="refresh"' in content, \
            "Template must have refresh action (via ui.button macro)"


# -- TestAgentDetailAccessibility -------------------------------------------

class TestAgentDetailAccessibility:
    """验证可访问性属性。"""

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_emoji_spans_aria_hidden(self):
        """所有 emoji span 必须有 aria-hidden='true'。"""
        content = _read_template()
        emoji_spans = re.findall(r'class="emoji"[^>]*>', content)
        for span in emoji_spans:
            assert 'aria-hidden="true"' in span, \
                f"Emoji span must have aria-hidden='true': {span}"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_sort_mark_aria_hidden(self):
        """排序标记必须有 aria-hidden='true'。"""
        content = _read_template()
        # sort-mark 元素是空 span，由 JS 填充
        assert 'class="sort-mark"' in content, \
            "Sortable headers must have sort-mark elements"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_search_input_aria_label(self):
        """搜索输入必须通过 table_card 宏有 aria-label。"""
        content = _read_template()
        assert "search_placeholder=" in content, \
            "Sessions must pass search_placeholder to table_card"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_page_input_aria_label(self):
        """分页组件必须在页码输入上有 aria-label。"""
        # ui_primitives.html 中的 ui.pagination 宏提供 aria-label
        assert "ui.pagination" in _read_template(), \
            "Agent must use ui.pagination for pagination"
        # 验证宏定义中有 aria-label（split-aware: 搜索 wrapper + 子组件）
        primitives = _read_ui_primitives_with_splits()
        assert 'aria-label="Page number"' in primitives, \
            "Pagination macro must have aria-label on page input"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_pagination_aria_label(self):
        """分页必须有 aria-label。"""
        content = _read_template()
        assert 'aria-label="Agent sessions pagination"' in content, \
            "Pagination must have aria-label='Agent sessions pagination'"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_metric_grid_aria_label(self):
        """指标网格必须有 aria-label。"""
        content = _read_template()
        assert 'aria-label="Agent detail metrics"' in content, \
            "指标网格必须有 aria-label='Agent detail metrics'"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_tokenbar_aria_label(self):
        """Tokenbar 必须有 aria-label。"""
        content = _read_template()
        assert 'aria-label="Token breakdown tooltip"' in content, \
            "Tokenbar must have aria-label='Token breakdown tooltip'"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_info_icon_has_title(self):
        """信息图标必须有 title 属性用于工具提示。"""
        content = _read_template()
        # icon-button--info span 使用 title 作为工具提示文本
        pattern = r'class="[^"]*icon-button--info[^"]*"[^>]*title="[^"]*"'
        matches = re.findall(pattern, content)
        assert len(matches) >= 6, \
            f"Must have at least 6 icon-button--info icons with title, found {len(matches)}"


# -- TestAgentDetailTokenFormatting -----------------------------------------

class TestAgentDetailTokenFormatting:
    """验证模型表和会话表中的 token 格式化结构。"""

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_tokenbar_width_style_pattern(self):
        """Tokenbar 分段必须使用带 Jinja 百分比的 width 样式。"""
        content = _read_template()
        # 验证 tokenbar 分段上存在 style="width:{{ ... }}%" 模式
        width_pattern = r'style="width:\{\{[^}]+\}\}%"'
        matches = re.findall(width_pattern, content)
        assert len(matches) >= 8, \
            f"Tokenbar must have at least 8 width-style segments, found {len(matches)}"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_format_compact_token_filter_used(self):
        """模板必须使用 format_compact_token 进行 token 显示。"""
        content = _read_template()
        assert "format_compact_token" in content, \
            "Template must use format_compact_token filter"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_token_total_display(self):
        """Token-cell 必须显示 token 总数。"""
        content = _read_template()
        assert 'class="token-total"' in content, \
            "Token-cell must have token-total element"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_tokenbar_four_segment_types(self):
        """Tokenbar 必须恰好有 4 种 CSS 分段类型。"""
        content = _read_template()
        for seg in ["t-fresh", "t-read", "t-write", "t-out"]:
            assert f'class="{seg}"' in content, \
                f"Tokenbar must have {seg} segment"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_token_tooltip_tip_rows(self):
        """Token 工具提示必须有用于细分的 tip-row 元素。"""
        content = _read_template()
        tip_rows = re.findall(r'class="tip-row"', content)
        assert len(tip_rows) >= 4, \
            f"Token tooltip must have at least 4 tip-rows, found {len(tip_rows)}"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_format_number_filter_used(self):
        """模板必须使用 format_number 进行计数显示。"""
        content = _read_template()
        assert "format_number" in content, \
            "Template must use format_number filter"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_format_duration_filter_used(self):
        """模板必须使用 format_duration 进行持续时间显示。"""
        content = _read_template()
        assert "format_duration" in content, \
            "Template must use format_duration filter"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_format_1d_filter_used(self):
        """模板必须使用 format_1d 进行一位小数百分比显示。"""
        content = _read_template()
        assert "format_1d" in content, \
            "Template must use format_1d filter"


# -- TestAgentDetailTableStructure ------------------------------------------

class TestAgentDetailTableStructure:
    """验证表的 colgroup 和列结构。"""

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_model_table_colgroup(self):
        """Model breakdown 表必须使用带命名列的 colgroup。"""
        content = _read_template()
        assert "<colgroup>" in content, \
            "Model table must use colgroup"
        col_classes = [
            "col-model-name", "col-sessions", "col-token-md",
            "col-cache", "col-tools", "col-failed", "col-avg",
        ]
        for cls in col_classes:
            assert f'class="{cls}"' in content, \
                f"Model table must have col with class '{cls}'"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_sessions_table_colgroup(self):
        """Sessions 表必须使用带命名列的 colgroup。"""
        content = _read_template()
        # sessions 表 colgroup
        col_classes = [
            "col-title", "col-project", "col-model", "col-token",
            "col-num-sm", "col-duration", "col-updated",
        ]
        for cls in col_classes:
            assert f'class="{cls}"' in content, \
                f"Sessions table must have col with class '{cls}'"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_mono_class_on_numeric_cells(self):
        """数值单元格必须使用 mono 类来应用等宽字体。"""
        content = _read_template()
        assert 'class="col-num mono"' in content or 'class="mono"' in content, \
            "Numeric cells must use mono class"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_col_num_class_on_number_columns(self):
        """表必须对数字列使用 col-num 类。"""
        content = _read_template()
        assert 'class="col-num"' in content, \
            "Table must use col-num class for number columns"


# -- TestAgentDetailModelBreakdownInsight -----------------------------------

class TestAgentDetailModelBreakdownInsight:
    """验证模型细分的洞察行。"""

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_insight_span_present(self):
        """Model breakdown 必须向 table_card 传递 insight 参数。"""
        content = _read_template()
        assert "insight=" in content, \
            "Model breakdown must pass insight param to table_card"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_most_active_model_text(self):
        """Model breakdown 必须显示 'Most active model' 文本。"""
        content = _read_template()
        assert "Most active model" in content, \
            "Model breakdown must show 'Most active model' text"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_section_sub_mentions_duration(self):
        """Model breakdown 的 section-sub 必须提到 Avg Duration。"""
        content = _read_template()
        assert "Avg Duration" in content, \
            "Model breakdown sub must mention Avg Duration"


# -- TestAgentDetailSessionsEmptyState --------------------------------------

class TestAgentDetailSessionsEmptyState:
    """验证会话专属空状态（agent_info 存在但无会话）。"""

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_sessions_conditional_render(self):
        """Sessions 区域必须使用 {% if sessions %} 条件。"""
        content = _read_template()
        assert "{% if sessions %}" in content, \
            "Sessions must be conditionally rendered"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_sessions_else_empty_state(self):
        """Sessions {% else %} 分支必须使用 ui.empty_state 宏。"""
        content = _read_template()
        # 会话空状态出现在表和分页之后，
        # 包裹在 {% if sessions %} ... {% else %} ... {% endif %} 中
        # 使用更简单的方法：文件以分页结尾，然后
        # 末尾附近有 {% else %} ... 空状态 ... {% endif %}。
        # 找到最后一个 {% endif %} 之前的 {% else %}
        last_endif = content.rfind("{% endif %}")
        assert last_endif != -1, "Template must have endif"
        before_endif = content[:last_endif]
        last_else = before_endif.rfind("{% else %}")
        assert last_else != -1, "Template must have an else branch"
        sessions_else = content[last_else:last_endif]
        assert "ui.empty_state" in sessions_else, \
            "Sessions empty state must use ui.empty_state macro"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_sessions_empty_says_no_session_data(self):
        """会话空状态必须显示 '暂无该 Agent 的 Session 数据'。"""
        content = _read_template()
        assert "暂无该 Agent 的 Session 数据" in content, \
            "Sessions empty state must mention no session data"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_sessions_empty_back_to_agents(self):
        """会话空状态必须链接回 /agents。"""
        content = _read_template()
        # 会话空状态的返回按钮
        assert "返回 Agents" in content, \
            "Sessions empty state must say '返回 Agents'"


# -- TestAgentDetailAgentInfoEmptyState -------------------------------------

class TestAgentDetailAgentInfoEmptyState:
    """验证 agent_info 空状态（未找到 agent / 完全无数据）。"""

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_agent_info_not_found_condition(self):
        """模板必须检查 {% elif not agent_info %}。"""
        content = _read_template()
        assert "{% elif not agent_info %}" in content, \
            "Template must check for missing agent_info"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_agent_info_empty_message(self):
        """Agent info 空状态必须显示 '未找到该 Agent 的数据'。"""
        content = _read_template()
        assert "未找到该 Agent 的数据" in content, \
            "Agent info empty state must say '未找到该 Agent 的数据'"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_agent_info_empty_has_back_button(self):
        """Agent info 空状态必须有返回 agents 链接。"""
        content = _read_template()
        assert "href='/agents'" in content or 'href="/agents"' in content, \
            "Agent info empty state must link to /agents"


# -- TestAgentDetailFailedBadge ---------------------------------------------

class TestAgentDetailFailedBadge:
    """验证失败工具数徽章渲染。"""

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_failed_badge_conditional(self):
        """失败徽章必须以 failed_tool_count > 0 为条件。"""
        content = _read_template()
        assert "failed_tool_count > 0" in content, \
            "Failed badge must be conditional on failed_tool_count > 0"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_failed_zero_shows_mono_zero(self):
        """无失败时，必须显示 <span class='mono'>0</span>。"""
        content = _read_template()
        assert '<span class="mono">0</span>' in content, \
            "Zero failures must show mono 0"

    @pytest.mark.contract_case("UI-AGENTS-002")
    def test_row_failed_class_conditional(self):
        """行必须以 row--failed 类为条件。"""
        content = _read_template()
        assert "row--failed" in content, \
            "Row must have row--failed conditional class"
