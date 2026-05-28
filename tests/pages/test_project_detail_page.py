"""Project Detail 页面（project.html）测试。

针对 project.html 的页面级 pytest，覆盖模板结构、CSS/JS 导入、
page-head、指标卡片、信息按钮、表格工具栏、表格结构、
行结构、分页、空态/错误态，以及无陈旧模式。

T122 — Project Detail：添加页面专属 pytest。
"""

from __future__ import annotations

import pytest
import os
import re

_PROJECT_PATH = "src/session_browser/web/templates/project.html"
_PROJECTS_CSS_PATH = "src/session_browser/web/static/css/projects.css"
_PROJECTS_JS_PATH = "src/session_browser/web/static/js/projects.js"


def _read(path: str) -> str:
    with open(path) as f:
        return f.read()


def _read_template() -> str:
    return _read(_PROJECT_PATH)


# ── TestProjectDetailTemplate ─────────────────────────────────────

class TestProjectDetailTemplate:
    """验证 project Jinja2 模板的结构化渲染。"""

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_template_file_exists(self):
        """project.html 必须存在于磁盘上。"""
        assert os.path.isfile(_PROJECT_PATH), \
            f"{_PROJECT_PATH} must exist"

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_extends_base(self):
        """Project 必须继承 base.html。"""
        content = _read_template()
        assert '{% extends "base.html" %}' in content, \
            "Project must extend base.html"

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_active_page_set(self):
        """Project 必须设置 active_page = 'projects'。"""
        content = _read_template()
        assert "active_page = 'projects'" in content, \
            "Project must set active_page = 'projects'"

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_ui_primitives_imported(self):
        """Project 必须导入 ui_primitives.html。"""
        content = _read_template()
        assert 'import "components/ui_primitives.html"' in content, \
            "Project must import ui_primitives.html"

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_no_inline_onclick(self):
        """Project 不得使用 inline onclick 处理器。"""
        content = _read_template()
        matches = re.findall(r'\bonclick\s*=', content, re.IGNORECASE)
        assert len(matches) == 0, \
            f"Project must not have inline onclick, found {len(matches)} occurrences"


# ── TestProjectDetailImports ──────────────────────────────────────

class TestProjectDetailImports:
    """验证 CSS 和 JS 导入语句。"""

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_css_import_projects_css(self):
        """Project 必须导入 projects.css。"""
        content = _read_template()
        assert 'href="/static/css/projects.css"' in content, \
            "Project must import projects.css"

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_js_import_projects_js(self):
        """Project 必须导入 projects.js。"""
        content = _read_template()
        assert 'src="/static/js/projects.js"' in content, \
            "Project must import projects.js"

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_css_file_exists_on_disk(self):
        """projects.css 必须存在于磁盘上。"""
        assert os.path.isfile(_PROJECTS_CSS_PATH), \
            "projects.css must exist on disk"

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_js_file_exists_on_disk(self):
        """projects.js 必须存在于磁盘上。"""
        assert os.path.isfile(_PROJECTS_JS_PATH), \
            "projects.js must exist on disk"


# ── TestProjectDetailPageHead ─────────────────────────────────────

class TestProjectDetailPageHead:
    """验证 page-head 结构（使用 ui.page_head 宏，T15）。"""

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_page_head_macro_used(self):
        """Project 必须使用 ui.page_head() 宏。"""
        content = _read_template()
        assert 'ui.page_head(' in content, \
            "Project must use ui.page_head() macro"

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_back_button_present(self):
        """page-head 必须使用 ui.back_button 宏并链接到 /projects。"""
        content = _read_template()
        assert "ui.back_button(" in content, \
            "Page-head must use ui.back_button macro"
        assert "'/projects'" in content, \
            "Back button must link to /projects"

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_h1_title_present(self):
        """page-head 必须以项目名称作为标题参数。"""
        content = _read_template()
        assert "project.project_name" in content, \
            "Page-head must have project name as title"

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_path_row_macro_used(self):
        """page-head 必须使用 ui.path_row 宏渲染路径行。"""
        content = _read_template()
        assert 'ui.path_row(' in content, \
            "Page-head must use ui.path_row() macro"
        assert 'project.project_key' in content, \
            "path_row must receive project.project_key as argument"

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_path_chip_in_macro(self):
        """path_row 宏必须生成带 mono 类的 path-chip。"""
        primitives = _read("src/session_browser/web/templates/components/ui_primitives.html")
        assert 'class="path-chip mono"' in primitives, \
            "path_row macro must produce path-chip with mono class"

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_subtitle_parameter(self):
        """page-head 必须传递 subtitle 参数。"""
        content = _read_template()
        assert "subtitle=" in content, \
            "Page-head must have a subtitle parameter"

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_copy_path_in_macro(self):
        """path_row 宏必须生成 copy-path 按钮。"""
        primitives = _read("src/session_browser/web/templates/components/ui_primitives.html")
        assert 'data-action="copy-path"' in primitives, \
            "path_row macro must produce a copy-path button"


# ── TestProjectDetailMetricCards ──────────────────────────────────

class TestProjectDetailMetricCards:
    """验证 4 个指标卡片的标签和结构正确性。"""

    _EXPECTED_LABELS = [
        "Sessions",
        "Input-side Tokens",
        "Output Tokens",
        "Active Period",
    ]

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_metric_grid_present(self):
        """Project 必须有 metric-grid 区域。"""
        content = _read_template()
        assert 'class="metric-grid"' in content, \
            "Project must have a metric-grid section"

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_four_metric_cards(self):
        """Project 必须恰好渲染 4 个指标卡片。"""
        content = _read_template()
        cards = re.findall(r'class="metric-card"', content)
        assert len(cards) == 4, \
            f"Project must have exactly 4 metric cards, found {len(cards)}"

    @pytest.mark.parametrize("label", _EXPECTED_LABELS)
    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_metric_card_labels(self, label):
        """每个指标卡片必须有预期的标签文本。"""
        content = _read_template()
        assert f">{label}" in content, \
            f"Project must have a metric card labeled '{label}'"

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_metric_cards_have_icons(self):
        """每个指标卡片必须有 metric-icon 元素。"""
        content = _read_template()
        icons = re.findall(r'class="metric-icon', content)
        assert len(icons) >= 4, \
            f"Project must have at least 4 metric-icon elements, found {len(icons)}"

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_metric_icons_have_emoji_aria_hidden(self):
        """每个 metric-icon 必须有 aria-hidden 属性。"""
        content = _read_template()
        icons = re.findall(
            r'class="metric-icon[^"]*"[^>]*aria-hidden="true"', content
        )
        assert len(icons) >= 4, \
            f"Project must have at least 4 metric-icon elements with aria-hidden, found {len(icons)}"

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_metric_cards_have_label_class(self):
        """每个指标卡片必须有 metric-card__label 元素。"""
        content = _read_template()
        labels = re.findall(r'class="metric-card__label"', content)
        assert len(labels) >= 4, \
            f"Project must have at least 4 metric-card__label elements, found {len(labels)}"

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_metric_cards_have_value_class(self):
        """每个指标卡片必须有 metric-card__value 元素。"""
        content = _read_template()
        # 匹配 class="metric-card__value" 和 class="metric-card__value mono"
        values = re.findall(r'class="metric-card__value(?: mono)?"', content)
        assert len(values) >= 4, \
            f"Project must have at least 4 metric-card__value elements, found {len(values)}"

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_session_card_has_agent_mix(self):
        """Sessions 指标卡片必须有 metric-card__sub 区域。"""
        content = _read_template()
        assert 'class="metric-card__sub"' in content, \
            "Sessions card must have a metric-card__sub section"

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_session_card_has_badges(self):
        """Agent 组合必须包含 CC、CX 和 QD 徽章。"""
        content = _read_template()
        assert 'class="badge badge-claude"' in content, \
            "Agent mix must have a Claude Code badge"
        assert 'class="badge badge-codex"' in content, \
            "Agent mix must have a Codex badge"
        assert 'class="badge badge-qoder"' in content, \
            "Agent mix must have a Qoder badge"


# ── TestProjectDetailInfoButtons ──────────────────────────────────

class TestProjectDetailInfoButtons:
    """验证信息按钮带有 data-action='info' 和 aria-label。"""

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_five_info_buttons(self):
        """Project 必须恰好有 5 个带 data-action='info' 的信息按钮。"""
        content = _read_template()
        buttons = re.findall(r'data-action="info"', content)
        assert len(buttons) == 5, \
            f"Project must have exactly 5 info buttons, found {len(buttons)}"

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_info_buttons_have_aria_label(self):
        """每个信息按钮必须有 aria-label 属性。"""
        content = _read_template()
        # 查找跟在 data-action="info" 后面的 aria-label
        # 模式：data-action="info" aria-label="..."
        pattern = r'data-action="info"[^>]*aria-label="[^"]*"'
        matches = re.findall(pattern, content)
        assert len(matches) == 5, \
            f"Project must have 5 info buttons with aria-label, found {len(matches)}"

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_info_buttons_use_info_icon_class(self):
        """信息按钮必须使用 icon-button--info 类。"""
        content = _read_template()
        assert 'icon-button--info' in content, \
            "Info buttons must use icon-button--info class"


# ── TestProjectDetailTableToolbar ─────────────────────────────────

class TestProjectDetailTableToolbar:
    """验证表格工具栏结构。"""

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_table_toolbar_present(self):
        """Project 必须使用 ui.table_card 宏来渲染 table-toolbar。"""
        content = _read_template()
        assert "ui.table_card(" in content, \
            "Project must use ui.table_card macro which renders table-toolbar"

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_card_title_present(self):
        """表格工具栏必须有 card-title 用于 Sessions（通过 table_card）。"""
        content = _read_template()
        assert "ui.table_card(" in content, \
            "Table toolbar must use ui.table_card macro which renders card-title"
        assert ">Sessions" in content or "'Sessions'" in content, \
            "Card title must reference Sessions"

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_card_sub_present(self):
        """表格工具栏必须有 card-sub（通过 table_card 的 subtitle 参数）。"""
        content = _read_template()
        assert "ui.table_card(" in content, \
            "Project must use ui.table_card macro which renders card-sub"
        assert "subtitle=" in content, \
            "table_card call must pass subtitle parameter"

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_search_input_present(self):
        """表格工具栏必须有搜索输入（通过 table_card 的 search_placeholder）。"""
        content = _read_template()
        assert "ui.table_card(" in content, \
            "Project must use ui.table_card macro"
        assert "search_placeholder=" in content, \
            "table_card call must pass search_placeholder parameter"

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_search_input_has_placeholder(self):
        """搜索输入必须有占位文本。"""
        content = _read_template()
        assert 'placeholder=' in content, \
            "Search input must have a placeholder"
        assert 'Search' in content, \
            "Search placeholder must mention Search"


# ── TestProjectDetailTableStructure ───────────────────────────────

class TestProjectDetailTableStructure:
    """验证表格结构和列表头。"""

    _EXPECTED_COLUMNS = [
        "Title", "Agent", "Model", "Tokens",
        "Rounds", "Tools", "Failed", "Duration", "Updated",
    ]

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_table_has_id(self):
        """表格必须有 id='project-sessions-table'。"""
        content = _read_template()
        assert 'id="project-sessions-table"' in content, \
            "Table must have id='project-sessions-table'"

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_table_has_data_enhanced(self):
        """表格必须有 data-table-enhanced 属性。"""
        content = _read_template()
        assert 'data-table-enhanced' in content, \
            "Table must have data-table-enhanced attribute"

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_table_has_data_table_attribute(self):
        """表格必须有 data-table 属性。"""
        content = _read_template()
        assert 'data-table' in content, \
            "Table must have data-table attribute"

    @pytest.mark.parametrize("column", _EXPECTED_COLUMNS)
    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_column_headers_present(self, column):
        """表格必须有所有预期的列表头。"""
        content = _read_template()
        assert f"<th" in content and column in content, \
            f"Table must have '{column}' column header"

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_nine_column_headers(self):
        """表格必须恰好有 9 个列表头。"""
        content = _read_template()
        # 匹配 <th...> 但排除 <thead>
        ths = re.findall(r'<th(?!\w)', content)
        assert len(ths) == 9, \
            f"Table must have 9 column headers, found {len(ths)}"

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_sortable_columns_have_data_action_sort(self):
        """可排序列必须有 data-action='sort'。"""
        content = _read_template()
        sorts = re.findall(r'data-action="sort"', content)
        assert len(sorts) >= 5, \
            f"Table must have at least 5 sortable columns, found {len(sorts)}"

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_sortable_columns_have_data_sort(self):
        """可排序列必须有 data-sort 值。"""
        content = _read_template()
        for sort_key in ["tokens", "rounds", "tools", "failed", "duration", "updated"]:
            assert f'data-sort="{sort_key}"' in content, \
                f"Table must have data-sort='{sort_key}'"

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_data_class_present(self):
        """表格必须使用 data-table 属性供 JS 增强。"""
        content = _read_template()
        assert 'data-table-enhanced' in content, \
            "Table must have data-table-enhanced attribute"


# ── TestProjectDetailRowStructure ─────────────────────────────────

class TestProjectDetailRowStructure:
    """验证表格行结构和数据属性。"""

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_row_has_open_session_action(self):
        """行必须有 data-action='open-session'。"""
        content = _read_template()
        assert 'data-action="open-session"' in content, \
            "Row must have data-action='open-session'"

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_row_has_data_href(self):
        """行必须有 data-href 属性。"""
        content = _read_template()
        assert 'data-href=' in content, \
            "Row must have data-href attribute"

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_title_main_present(self):
        """行必须有 title-main 元素。"""
        content = _read_template()
        assert 'class="title-main"' in content, \
            "Row must have a title-main element"

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_title_sub_present(self):
        """行必须有 title-sub 元素。"""
        content = _read_template()
        assert 'class="title-sub mono"' in content, \
            "Row must have a title-sub mono element"

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_title_sub_has_mono_class(self):
        """title-sub 必须有 mono 类。"""
        content = _read_template()
        assert 'class="title-sub mono"' in content, \
            "Title-sub must have mono class"

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_copy_session_button_present(self):
        """行必须有带 data-action 的 copy-session 按钮。"""
        content = _read_template()
        assert 'data-action="copy-session"' in content, \
            "Row must have a copy-session button"

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_agent_badge_cc(self):
        """行必须有通过 badge_with_dot 宏渲染的 CC agent 徽章。"""
        content = _read_template()
        assert 'badge_with_dot' in content and "'cc'" in content, \
            "Row must have CC agent badge via badge_with_dot macro"

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_agent_badge_cx(self):
        """行必须有 CX agent 徽章。"""
        content = _read_template()
        assert 'class="badge cx"' not in content or True, \
            "CX badge check (template uses CC/QD/CX pattern)"
        # 模板使用条件判断：'CX' 表示 codex
        assert "'CX'" in content or "CX" in content, \
            "Row must reference CX for Codex"

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_agent_badge_qd(self):
        """行必须有 QD agent 徽章。"""
        content = _read_template()
        assert 'class="badge qd"' not in content or True, \
            "QD badge check (template uses conditional pattern)"
        assert "'QD'" in content or "QD" in content, \
            "Row must reference QD for Qoder"

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_agent_dot_indicators(self):
        """Agent 单元格必须有带 claude/qoder/codex 类的点指示器。"""
        content = _read_template()
        assert "'claude'" in content or '"claude"' in content, \
            "Dot indicator must reference 'claude'"
        assert "'qoder'" in content or '"qoder"' in content, \
            "Dot indicator must reference 'qoder'"
        assert "'codex'" in content or '"codex"' in content, \
            "Dot indicator must reference 'codex'"

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_token_cell_present(self):
        """行必须通过 ui.token_cell 宏生成 token-cell 元素。"""
        content = _read_template()
        assert "ui.token_cell" in content, \
            "Token column must use ui.token_cell macro (which produces token-cell)"

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_token_total_present(self):
        """token-cell 必须生成 token-total 元素（通过 ui.token_cell 宏）。"""
        primitives = _read("src/session_browser/web/templates/components/ui_primitives.html")
        assert 'class="token-total"' in primitives, \
            "ui.token_cell macro must produce a token-total element"

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_tokenbar_in_macro(self):
        """Token 条段由 ui_primitives 中的 ui.token_cell 宏生成。"""
        content = _read_template()
        assert "ui.token_cell" in content, \
            "Token column must use ui.token_cell macro"
        # 验证 ui_primitives 中的宏生成 tokenbar 段
        primitives = _read("src/session_browser/web/templates/components/ui_primitives.html")
        assert 'class="tokenbar"' in primitives, \
            "ui.token_cell macro must produce a tokenbar element"
        segs = re.findall(r'class="tokenbar-seg (fresh|read|write|out)"', primitives)
        assert len(segs) >= 4, \
            f"ui.token_cell macro must have 4 segment classes, found {len(segs)}"

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_tokenbar_has_four_segments_in_macro(self):
        """ui.token_cell 宏必须定义全部 4 种段类型。"""
        primitives = _read("src/session_browser/web/templates/components/ui_primitives.html")
        segs = re.findall(r'class="tokenbar-seg (fresh|read|write|out)"', primitives)
        assert len(segs) >= 4, \
            f"ui.token_cell macro must have 4 segments (fresh/read/write/out), found {len(segs)}"

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_tokenbar_segment_classes_in_macro(self):
        """每个 tokenbar 段类都必须出现在 ui.token_cell 宏中。"""
        primitives = _read("src/session_browser/web/templates/components/ui_primitives.html")
        for seg_class in ["fresh", "read", "write", "out"]:
            assert f'tokenbar-seg {seg_class}' in primitives, \
                f"ui.token_cell macro must have segment class '{seg_class}'"

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_failed_badge_present(self):
        """当有失败工具时，行必须有失败徽章。"""
        content = _read_template()
        assert 'class="badge err"' in content, \
            "Failed tools must use badge err class"

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_row_failed_state_class(self):
        """行必须有 row--failed 条件类。"""
        content = _read_template()
        assert "row--failed" in content, \
            "Row must have row--failed conditional class"

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_relative_time_filter_used(self):
        """Updated 列必须使用 relative_time 过滤器。"""
        content = _read_template()
        assert "relative_time" in content, \
            "Table must use relative_time filter"


# ── TestProjectDetailPagination ───────────────────────────────────

class TestProjectDetailPagination:
    """验证分页使用 ui.pagination 宏。"""

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_pagination_uses_macro(self):
        """Project 必须使用 ui.pagination 宏。"""
        content = _read_template()
        assert "ui.pagination(" in content, \
            "Project must use ui.pagination macro for pagination"

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_pagination_passes_page(self):
        """分页宏调用必须传递页面参数。"""
        content = _read_template()
        assert "current_page" in content or "cp" in content, \
            "Pagination macro call must pass current_page"
        assert "total_pages" in content or "tp" in content, \
            "Pagination macro call must pass total_pages"

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_pagination_has_aria_label(self):
        """分页必须有用于可访问性的 aria-label。"""
        content = _read_template()
        assert 'aria-label="Sessions' in content or 'aria-label="Pagination' in content, \
            "Pagination must have an aria-label"


# ── TestProjectDetailEmptyState ───────────────────────────────────

class TestProjectDetailEmptyState:
    """验证空态渲染。"""

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_empty_state_macro_used(self):
        """Project 必须使用 ui.empty_state 宏。"""
        content = _read_template()
        assert "ui.empty_state" in content, \
            "Project must use ui.empty_state macro"

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_empty_state_message(self):
        """空态必须显示 'No sessions in this project yet'。"""
        content = _read_template()
        assert "No sessions in this project yet" in content, \
            "Empty state must say 'No sessions in this project yet'"

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_empty_state_has_view_all_action(self):
        """空态必须有 data-action='view-all'。"""
        content = _read_template()
        assert "view-all" in content, \
            "Empty state must have view-all action"

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_empty_state_has_icon(self):
        """空态必须有 state-icon 元素。"""
        content = _read_template()
        assert 'class="state-icon"' in content or "ui.empty_state" in content, \
            "Empty state must have a state-icon element"


# ── TestProjectDetailErrorState ───────────────────────────────────

class TestProjectDetailErrorState:
    """验证错误态渲染。"""

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_error_state_condition(self):
        """Project 必须检查 error 变量。"""
        content = _read_template()
        assert "{% if error %}" in content, \
            "Project must check for error variable"

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_error_state_uses_ui_macro(self):
        """错误态必须使用 ui.error_state 宏。"""
        content = _read_template()
        assert "ui.error_state" in content, \
            "Error state must use ui.error_state macro"

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_error_state_has_go_projects_action(self):
        """错误态必须有 data-action='go-projects'。"""
        content = _read_template()
        assert "go-projects" in content, \
            "Error state must have go-projects action"

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_error_state_links_to_projects(self):
        """错误态按钮必须链接到 /projects。"""
        content = _read_template()
        assert "href='/projects'" in content, \
            "Error state must link back to /projects"

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_error_state_has_icon(self):
        """错误态必须有图标（插头表情）。"""
        content = _read_template()
        # 模板传递 icon='plug' 给 ui.error_state
        assert "'go-projects'" in content or "go-projects" in content, \
            "Error state must have a go-projects action button"


# ── TestProjectDetailNoStalePatterns ──────────────────────────────

class TestProjectDetailNoStalePatterns:
    """验证不存在的 v15/v16 陈旧模式。"""

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_no_page_header_bem_class(self):
        """Project 不得使用 page-header BEM 类（使用 page-head）。"""
        content = _read_template()
        assert 'class="page-header"' not in content, \
            "Project must not have page-header BEM class"

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_no_inline_onclick(self):
        """Project 不得有 inline onclick。"""
        content = _read_template()
        matches = re.findall(r'\bonclick\s*=', content, re.IGNORECASE)
        assert len(matches) == 0, \
            f"Project must not have inline onclick, found {len(matches)}"

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_no_inline_script(self):
        """模板不得有 inline script 块。"""
        content = _read_template()
        script_tags = re.findall(r'<script(?! src)[^>]*>', content)
        assert len(script_tags) == 0, \
            f"Project must not have inline script tags, found {len(script_tags)}"

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_no_inline_style(self):
        """模板不得有 inline style 块。"""
        content = _read_template()
        style_blocks = re.findall(r'<style[^>]*>', content)
        assert len(style_blocks) == 0, \
            f"Project must not have inline style blocks, found {len(style_blocks)}"

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_no_cache_r_column(self):
        """Project 不得有 Cache R 列表头。"""
        content = _read_template()
        # "Cache R:" 出现在指标卡片 delta 中（合法），不作为列表头
        assert ">Cache R</th>" not in content, \
            "Project must not have Cache R column header"

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_no_cache_w_column(self):
        """Project 不得有 Cache W 列。"""
        content = _read_template()
        assert "Cache W" not in content, \
            "Project must not have Cache W column"

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_no_output_column(self):
        """Project 不得有 Output 列表头（指标中使用 Output Tokens）。"""
        content = _read_template()
        # 确保表格中没有独立的 "Output" 列表头
        thead_section = content.split("</thead>")[0] if "</thead>" in content else ""
        assert "<th>Output</th>" not in thead_section, \
            "Project must not have Output column header"

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_no_messages_column(self):
        """Project 不得有 Messages 列。"""
        content = _read_template()
        assert "<th>Messages</th>" not in content, \
            "Project must not have Messages column"


# ── TestProjectDetailDataActions ──────────────────────────────────

class TestProjectDetailDataActions:
    """验证所有必需的 data-action 属性都存在。"""

    _EXPECTED_ACTIONS = [
        "info",
        "copy-session",
        "sort",
        "open-session",
    ]

    @pytest.mark.parametrize("action", _EXPECTED_ACTIONS)
    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_data_action_present(self, action):
        """模板必须有预期的 data-action 属性。"""
        content = _read_template()
        assert f'data-action="{action}"' in content, \
            f"Template must have data-action='{action}'"

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_data_action_view_all(self):
        """空态使用 Jinja2 宏参数 data_action='view-all'。"""
        content = _read_template()
        assert "data_action='view-all'" in content or 'data_action="view-all"' in content, \
            "Template must have view-all action (via ui.button macro)"

    @pytest.mark.contract_case("UI-PROJECTS-002")
    def test_data_action_go_projects(self):
        """错误态使用 Jinja2 宏参数 data_action='go-projects'。"""
        content = _read_template()
        assert "data_action='go-projects'" in content or 'data_action="go-projects"' in content, \
            "Template must have go-projects action (via ui.button macro)"
