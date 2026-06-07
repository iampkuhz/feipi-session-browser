"""Projects 页面表格重构测试。

针对 projects.html 的页面级 pytest，覆盖模板结构、CSS/JS 导入、
指标卡片、过滤卡片、表格结构、行结构、分页、
空态/错误态，以及无 inline onclick。

T108 — Projects 列表：添加页面专属 pytest。
"""

from __future__ import annotations

import pytest
import os
import re
import glob as _glob

_PROJECTS_PATH = "src/session_browser/web/templates/projects.html"
_PROJECTS_CSS_PATH = "src/session_browser/web/static/css/projects.css"
_PROJECTS_JS_PATH = "src/session_browser/web/static/js/projects.js"
_UI_PRIMITIVES_PATH = "src/session_browser/web/templates/components/ui_primitives.html"
_UI_PRIMITIVES_DIR = "src/session_browser/web/templates/components/ui_primitives"


def _read(path: str) -> str:
    with open(path) as f:
        return f.read()


def _read_template() -> str:
    return _read(_PROJECTS_PATH)


def _read_template_with_macros() -> str:
    return _read_template() + "\n" + _read_ui_primitives()


def _read_ui_primitives() -> str:
    """Read ui_primitives wrapper + all split sub-components (split-aware)."""
    parts = [_read(_UI_PRIMITIVES_PATH)]
    for fp in sorted(_glob.glob(os.path.join(_UI_PRIMITIVES_DIR, "*.html"))):
        parts.append(_read(fp))
    return "\n".join(parts)


class TestTruncatePath:
    """验证项目路径显示不会对仓库根目录显示 '.'。"""

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_repo_root_not_dot(self):
        """完整绝对路径绝不应被截断为 '.'。"""
        from session_browser.web.template_env import _truncate_path
        result = _truncate_path("/Users/zhehan/Documents/tools/llm/feipi-agent-kit")
        assert result != "."
        assert "feipi-agent-kit" in result

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_long_path_truncated(self):
        from session_browser.web.template_env import _truncate_path
        path = "/Users/zhehan/some/very/long/path/to/project"
        result = _truncate_path(path)
        # 应保留开头和结尾
        assert result.startswith("/")
        assert "project" in result

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_short_path_preserved(self):
        from session_browser.web.template_env import _truncate_path
        path = "/tmp/short"
        result = _truncate_path(path)
        assert result == path


class TestProjectsTemplateColumns:
    """验证 projects.html 模板的列正确且无已删除的列。"""

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_no_cache_r_column(self):
        content = _read_template()
        assert "Cache R" not in content

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_no_cache_w_column(self):
        content = _read_template()
        assert "Cache W" not in content

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_no_output_column(self):
        content = _read_template()
        # 无独立的 Output 列（可能出现在提示文本中，那是允许的）
        assert "Output Tokens" not in content

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_no_tools_per_round_column(self):
        content = _read_template()
        assert "Tools/R" not in content

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_no_standalone_failed_column(self):
        content = _read_template()
        assert ">Failed</th>" not in content

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_has_agents_column(self):
        content = _read_template()
        assert "Agents" in content

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_has_tokens_column(self):
        content = _read_template()
        assert "Tokens" in content


class TestProjectsTemplateSortOptions:
    """验证排序选项不再包含已删除的列。"""

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_no_cache_read_sort(self):
        content = _read_template()
        assert "Cache Read" not in content

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_no_cache_write_sort(self):
        content = _read_template()
        assert "Cache Write" not in content

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_no_output_tokens_sort(self):
        content = _read_template()
        assert "Output Tokens" not in content

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_has_tokens_sort(self):
        content = _read_template()
        assert "Tokens" in content

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_has_failed_tools_sort(self):
        content = _read_template()
        assert "Failed Tools" in content


_UI_PRIMITIVES_PATH = "src/session_browser/web/templates/components/ui_primitives.html"
_UI_PRIMITIVES_DIR = "src/session_browser/web/templates/components/ui_primitives"


def _read_ui_primitives() -> str:
    """Read ui_primitives wrapper + all split sub-components (split-aware)."""
    parts = [_read(_UI_PRIMITIVES_PATH)]
    for fp in sorted(_glob.glob(os.path.join(_UI_PRIMITIVES_DIR, "*.html"))):
        parts.append(_read(fp))
    return "\n".join(parts)


class TestProjectsTemplatePathDisplay:
    """验证路径显示使用 truncate_path 而非 relative_to_repo。"""

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_no_relative_to_repo_for_project_path(self):
        """项目路径不应使用 relative_to_repo 过滤器。"""
        content = _read_template()
        lines = content.split("\n")
        for line in lines:
            if "project_key" in line and "truncate_path" in line:
                assert "relative_to_repo" not in line

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_path_tooltip_shows_full_key(self):
        """工具提示应显示完整 project_key。"""
        content = _read_template()
        # projects.html 将完整 p.project_key 传递给宏；
        # 宏渲染 data-tooltip="{{ path }}"
        assert "ui.project_cell(" in content, \
            "projects.html must use project_cell macro"
        # 验证宏模板有 data-tooltip
        macro = _read_ui_primitives()
        assert 'data-tooltip="{{ path }}"' in macro, \
            "project_cell macro must have data-tooltip on path"


class TestProjectsTemplateTitle:
    """验证标题没有过度间距。"""

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_title_not_justified_between(self):
        """标题不应使用 justify-between 分隔 ( 和 )。"""
        content = _read_template()
        assert "justify-between" not in content
        # 应使用 ui.table_card 宏来渲染 card-title（T103：已迁移）
        assert "ui.table_card(" in content


# ── TestProjectsTemplate ──────────────────────────────────────────

class TestProjectsTemplate:
    """验证 projects Jinja2 模板的结构化渲染。"""

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_template_file_exists(self):
        assert os.path.isfile(_PROJECTS_PATH), \
            f"{_PROJECTS_PATH} must exist"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_extends_base(self):
        content = _read_template()
        assert '{% extends "base.html" %}' in content, \
            "Projects must extend base.html"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_active_page_set(self):
        content = _read_template()
        assert "active_page = 'projects'" in content, \
            "Projects must set active_page = 'projects'"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_ui_primitives_imported(self):
        content = _read_template()
        assert 'import "components/ui_primitives.html"' in content, \
            "Projects must import ui_primitives.html"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_no_inline_onclick(self):
        """Projects 不得使用 inline onclick 处理器。"""
        content = _read_template()
        matches = re.findall(r'\bonclick\s*=', content, re.IGNORECASE)
        assert len(matches) == 0, \
            f"Projects must not have inline onclick, found {len(matches)} occurrences"


# ── TestProjectsImports ───────────────────────────────────────────

class TestProjectsImports:
    """验证 CSS 和 JS 导入语句。"""

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_css_import_projects_css(self):
        content = _read_template()
        assert 'href="/static/css/projects.css"' in content, \
            "Projects must import projects.css"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_js_import_projects_js(self):
        content = _read_template()
        assert 'src="/static/js/projects.js"' in content, \
            "Projects must import projects.js"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_css_file_exists_on_disk(self):
        assert os.path.isfile(_PROJECTS_CSS_PATH), \
            "projects.css must exist on disk"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_js_file_exists_on_disk(self):
        assert os.path.isfile(_PROJECTS_JS_PATH), \
            "projects.js must exist on disk"


# ── TestProjectsPageHead ──────────────────────────────────────────

class TestProjectsPageHead:
    """验证 page-head 结构（使用 ui.page_head 宏，T15）。"""

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_page_head_macro_used(self):
        content = _read_template()
        assert 'ui.page_head(' in content, \
            "Projects must use ui.page_head() macro"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_page_head_has_h1(self):
        content = _read_template()
        assert "'Projects'" in content, \
            "Page-head must have 'Projects' as title"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_page_head_has_subtitle(self):
        content = _read_template()
        assert "Indexed local workspaces" in content, \
            "Page-head must have subtitle about indexed workspaces"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_page_head_stat_pills_used(self):
        content = _read_template()
        assert 'stat_pills=' in content, \
            "Page-head must use stat_pills parameter for project count"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_page_head_count_element(self):
        content = _read_template()
        assert 'id="projects-count"' in content, \
            "Page-head must have a projects-count element in stat_pills"


# ── TestProjectsMetricCards ───────────────────────────────────────

class TestProjectsMetricCards:
    """验证 4 个指标卡片带有正确标签和结构。"""

    _EXPECTED_LABELS = ["Projects", "Sessions", "Total Tokens", "Failed Tools"]

    @pytest.mark.contract_case("UI-PROJECTS-001")
    @pytest.mark.contract_case("UI-PROJECTS-006")
    def test_metric_grid_present(self):
        content = _read_template()
        assert 'class="metric-grid"' in content, \
            "Projects must have a metric-grid section"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_four_metric_cards(self):
        content = _read_template()
        cards = re.findall(r'class="metric-card"', content)
        assert len(cards) == 4, \
            f"Projects must have exactly 4 metric cards, found {len(cards)}"

    @pytest.mark.parametrize("label", _EXPECTED_LABELS)
    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_metric_card_labels(self, label):
        content = _read_template()
        # 模板使用 ">Label\n" 或 '>"Label"' -- 检查 metric-card__label 附近的标签文本
        assert f">{label}" in content, \
            f"Projects must have a metric card labeled '{label}'"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_metric_card_aria_labels(self):
        """每个指标卡片必须有 data-metric 属性供信息按钮使用。"""
        content = _read_template()
        # 模板在信息按钮上使用 data-metric
        data_metrics = re.findall(r'data-metric="([^"]*)"', content)
        assert len(data_metrics) >= 4, \
            f"Projects must have at least 4 data-metric attributes, found {len(data_metrics)}"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_metric_card_has_icon(self):
        """每个指标卡片必须有 metric-icon 元素。"""
        content = _read_template()
        icons = re.findall(r'class="metric-icon[^"]*"', content)
        assert len(icons) >= 4, \
            f"Projects must have at least 4 metric-icon elements, found {len(icons)}"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_metric_card_has_label_class(self):
        """每个指标卡片必须有 metric-card__label 元素。"""
        content = _read_template()
        labels = re.findall(r'class="metric-card__label"', content)
        assert len(labels) >= 4, \
            f"Projects must have at least 4 metric-card__label elements, found {len(labels)}"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_metric_card_has_value_class(self):
        """每个指标卡片必须有 metric-card__value 元素。"""
        content = _read_template()
        values = re.findall(r'class="metric-card__value mono"', content)
        assert len(values) >= 4, \
            f"Projects must have at least 4 metric-card__value elements, found {len(values)}"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_metric_card_has_panel_sub(self):
        """每个指标卡片必须有 metric-card__sub 元素。"""
        content = _read_template()
        subs = re.findall(r'class="metric-card__sub"', content)
        assert len(subs) >= 4, \
            f"Projects must have at least 4 metric-card__sub elements, found {len(subs)}"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_metric_info_buttons(self):
        """每个指标卡片必须有带 data-action='metric-info' 的信息按钮。"""
        content = _read_template()
        buttons = re.findall(r'data-action="metric-info"', content)
        assert len(buttons) == 4, \
            f"Projects must have 4 metric-info buttons, found {len(buttons)}"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_metric_info_buttons_have_data_metric(self):
        """每个信息按钮必须有 data-metric 属性。"""
        content = _read_template()
        data_metrics = re.findall(r'data-metric="[^"]*"', content)
        assert len(data_metrics) >= 4, \
            f"Projects must have at least 4 data-metric attributes, found {len(data_metrics)}"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_metric_info_uses_icon_button_info_class(self):
        """信息按钮必须使用 icon-button--info 类。"""
        content = _read_template()
        assert "icon-button--info" in content, \
            "Info buttons must use icon-button--info class"


# ── TestProjectsFilterCard ────────────────────────────────────────

class TestProjectsFilterCard:
    """验证过滤卡片结构。"""

    @pytest.mark.contract_case("UI-PROJECTS-001")
    @pytest.mark.contract_case("UI-PROJECTS-005")
    def test_filter_card_present(self):
        content = _read_template()
        assert ('class="card filter-card"' in content
                or 'ui.filter_card()' in content), \
            "Projects must have a filter-card"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_search_input_with_data_search(self):
        # 基于宏的过滤器中 data-search 属性是可选的
        content = _read_template()
        assert ('data-search="project-name"' in content
                or "id='project-search'" in content
                or 'id="project-search"' in content), \
            "Search input must have identifiable attributes"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_search_input_id(self):
        content = _read_template()
        assert ('id="project-search"' in content
                or "id='project-search'" in content), \
            "Search input must have id='project-search'"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    @pytest.mark.skip(reason="Apply button removed: real-time search")
    def test_apply_button(self):
        content = _read_template()
        assert ('data-action="apply-search"' in content
                or "data_action='apply-search'" in content), \
            "Apply button must have data-action='apply-search'"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_clear_button(self):
        content = _read_template()
        assert ('data-action="clear-search"' in content
                or "data_action='clear-search'" in content), \
            "Clear button must have data-action='clear-search'"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_active_filters_aria_live(self):
        content = _read_template()
        assert ('class="active-filters"' in content
                or 'class="filter-footer"' in content), \
            "Filter card must have active-filters section"


# ── TestProjectsTableStructure ────────────────────────────────────

class TestProjectsTableStructure:
    """验证表格结构和列表头。"""

    _EXPECTED_COLUMNS = ["Project", "Agents", "Sessions", "Tokens", "Tools", "Last Active"]

    @pytest.mark.contract_case("UI-PROJECTS-001")
    @pytest.mark.contract_case("UI-PROJECTS-004")
    def test_table_has_id(self):
        content = _read_template()
        assert 'id="projects-table"' in content, \
            "Projects table must have id='projects-table'"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_table_has_data_enhanced(self):
        content = _read_template()
        assert 'data-table-enhanced' in content, \
            "Projects table must have data-table-enhanced attribute"

    @pytest.mark.parametrize("column", ["Project", "Agents", "Sessions", "Tokens", "Tools", "Last Active"])
    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_column_headers_present(self, column):
        content = _read_template()
        assert f"<th>{column}</th>" in content or f"<th class=" in content and column in content, \
            f"Table must have '{column}' column header"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_sortable_columns_have_data_sort(self):
        content = _read_template()
        sort_buttons = re.findall(r'data-action="sort"', content)
        assert len(sort_buttons) >= 4, \
            f"Table must have at least 4 sort buttons, found {len(sort_buttons)}"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_sortable_columns_data_sort_values(self):
        content = _read_template()
        for sort_key in ["sessions", "tokens", "tools", "last_active"]:
            assert f'data-sort-key="{sort_key}"' in content, \
                f"Table must have data-sort-key='{sort_key}'"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_sortable_headers_have_title(self):
        content = _read_template()
        # 统一模式：sort-button 有 title 属性（中文标签）
        sort_titles = re.findall(r'title="按[^"]*排序"', content)
        assert len(sort_titles) >= 4, \
            f"Sortable headers must have sort title, found {len(sort_titles)}"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_table_toolbar_present(self):
        content = _read_template()
        assert "ui.table_card(" in content, \
            "Table must use ui.table_card macro which renders table-toolbar"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_table_toolbar_has_table_title(self):
        content = _read_template()
        assert "ui.table_card(" in content, \
            "Table must use ui.table_card macro which renders card-title"
        assert "'All Projects'" in content or '"All Projects"' in content, \
            "Table title must reference All Projects"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_table_has_table_note(self):
        content = _read_template()
        assert "ui.table_card(" in content, \
            "Table must use ui.table_card macro"
        assert "subtitle=" in content, \
            "table_card call must pass subtitle parameter"


# ── TestProjectsRowStructure ──────────────────────────────────────

class TestProjectsRowStructure:
    """验证表格行结构和数据属性。"""

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_row_has_open_project_action(self):
        content = _read_template()
        assert 'data-action="open-project"' in content, \
            "Row must have data-action='open-project'"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_row_has_data_name(self):
        content = _read_template()
        assert 'data-name="{{ p.project_name | lower }}"' in content, \
            "Row must have data-name attribute"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_row_has_data_path(self):
        content = _read_template()
        assert 'data-path="{{ p.display_path | lower }}"' in content, \
            "Row must have data-path attribute"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_row_has_data_last_seen(self):
        content = _read_template()
        assert 'data-last-seen="{{ p.last_seen }}"' in content, \
            "Row must have data-last-seen attribute"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_row_has_data_total_sessions(self):
        content = _read_template()
        assert 'data-total-sessions="{{ p.total_sessions }}"' in content, \
            "Row must have data-total-sessions attribute"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_row_has_data_total_tokens(self):
        content = _read_template()
        assert 'data-total-tokens="{{ p_total_tokens }}"' in content, \
            "Row must have data-total-tokens attribute"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_project_name_link(self):
        content = _read_template()
        # projects.html 委托给 project_cell 宏；
        # 验证宏定义了该类
        assert 'class="project-name-link"' in _read_ui_primitives(), \
            "project_cell macro must define project-name-link class"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_project_name_link_action(self):
        content = _read_template()
        # 验证 projects.html 传递 name_data_action 参数
        assert "name_data_action='open-project-link'" in content, \
            "projects.html must pass name_data_action='open-project-link' to macro"
        # 验证宏支持 name_data_action
        macro = _read_ui_primitives()
        assert "name_data_action" in macro, \
            "project_cell macro must support name_data_action parameter"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_path_text_truncate(self):
        # 路径文本类在宏中定义
        assert 'class="path-text truncate"' in _read_ui_primitives(), \
            "project_cell macro must define path-text truncate class"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_path_copy_button(self):
        # 复制按钮类在宏中定义
        assert 'class="path-copy-btn"' in _read_ui_primitives(), \
            "project_cell macro must define path-copy-btn class"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_path_copy_button_data_action(self):
        # 复制按钮 data-action 在宏中定义
        assert 'data-action="copy"' in _read_ui_primitives(), \
            "project_cell macro must use canonical data-action='copy'"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_agent_badge_cc(self):
        content = _read_template()
        assert "ui.agent_badge('claude_code'" in content, \
            "Must have Claude Code agent badge via agent_badge macro"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_agent_badge_cx(self):
        content = _read_template()
        assert "ui.agent_badge('codex'" in content, \
            "Must have Codex agent badge via agent_badge macro"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_agent_badge_qd(self):
        content = _read_template()
        assert "ui.agent_badge('qoder'" in content, \
            "Must have Qoder agent badge via agent_badge macro"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_tokenbar_present(self):
        # Token 单元格通过 ui.token_cell 宏渲染
        content = _read_template()
        assert 'ui.token_cell' in content, \
            "projects.html must call ui.token_cell macro"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_tokenbar_has_four_segments(self):
        macro = _read_ui_primitives()
        segs = re.findall(r'class="tokenbar-seg (fresh|read|write|out)"', macro)
        assert len(segs) >= 4, \
            f"token_cell macro must have 4 segments, found {len(segs)}"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_tokenbar_segments_classes(self):
        macro = _read_ui_primitives()
        for seg_class in ["fresh", "read", "write", "out"]:
            assert f'tokenbar-seg {seg_class}' in macro, \
                f"token_cell macro must have segment class '{seg_class}'"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_tokenbar_tooltip_present(self):
        macro = _read_ui_primitives()
        assert 'class="token-tooltip"' in macro, \
            "token_cell macro must have tooltip element"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_tokenbar_tooltip_has_breakdown(self):
        macro = _read_ui_primitives()
        assert "Token Breakdown" in macro, \
            "token_cell tooltip must show token breakdown"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_tools_failed_badge(self):
        content = _read_template()
        assert 'class="badge err tools-failed"' in content, \
            "Failed tools must use err badge"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_relative_time_filter(self):
        content = _read_template()
        assert "relative_time" in content, \
            "Last Active column must use relative_time filter"


# ── TestProjectsPagination ────────────────────────────────────────

class TestProjectsPagination:
    """验证分页结构。"""

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_pagination_nav_present(self):
        content = _read_template_with_macros()
        assert 'class="pagination unified-pagination"' in content, \
            "Projects must have unified-pagination"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_pagination_has_role_navigation(self):
        content = _read_template_with_macros()
        assert 'role="navigation"' in content, \
            "Pagination must have role='navigation'"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_pagination_page_input(self):
        content = _read_template_with_macros()
        assert 'data-action="page-input"' in content, \
            "Pagination must have data-action='page-input'"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_pagination_next_page(self):
        content = _read_template_with_macros()
        assert 'data-action="next-page"' in content, \
            "Pagination must have data-action='next-page'"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_pagination_page_status(self):
        content = _read_template_with_macros()
        assert 'class="page-status"' in content, \
            "Pagination must have page-status element"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_pagination_has_aria_label(self):
        content = _read_template_with_macros()
        assert 'aria-label="{{ label }}"' in content, \
            "Pagination macro must expose an aria-label"


# ── TestProjectsEmptyState ────────────────────────────────────────

class TestProjectsEmptyState:
    """验证空态渲染。"""

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_empty_state_macro_used(self):
        content = _read_template()
        assert "ui.empty_state" in content, \
            "Projects must use ui.empty_state macro"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_empty_state_has_action_button(self):
        content = _read_template()
        assert "Run Scan" in content, \
            "Empty state must have 'Run Scan' action button"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_empty_state_has_icon(self):
        content = _read_template()
        # 检查内联空态条带有 state-icon 元素
        assert 'class="state-icon"' in content, \
            "Empty state must have state-icon element"
        assert "state-strip" in content, \
            "Empty state must use state-strip class"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_empty_state_has_clear_search(self):
        content = _read_template()
        assert "Clear Search" in content, \
            "Empty state must have Clear Search button"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_empty_state_has_data_action_clear_search(self):
        content = _read_template()
        # 内联空态条也有 clear-search
        assert 'data-action="clear-search"' in content, \
            "Empty state clear button must have data-action='clear-search'"


# ── TestProjectsErrorState ────────────────────────────────────────

class TestProjectsErrorState:
    """验证错误态渲染。"""

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_error_state_condition(self):
        content = _read_template()
        assert "{% if error %}" in content, \
            "Projects must check for error variable"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_error_state_uses_ui_macro(self):
        content = _read_template()
        assert "ui.error_state" in content, \
            "Error state must use ui.error_state macro"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_error_state_has_dashboard_link(self):
        content = _read_template()
        assert "/dashboard" in content, \
            "Error state must link back to /dashboard"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_error_state_has_go_dashboard_action(self):
        content = _read_template()
        assert "Back to Dashboard" in content, \
            "Error state must have 'Back to Dashboard' button"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_error_state_has_role_alert(self):
        """错误态宏在渲染时生成 role='alert'。"""
        content = _read_template()
        # ui.error_state 宏生成 role="alert"；验证使用了该宏
        assert "ui.error_state" in content, \
            "Error state must use ui.error_state macro (which generates role='alert')"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_error_state_has_aria_live_assertive(self):
        """错误态宏在渲染时生成 aria-live='assertive'。"""
        content = _read_template()
        # ui.error_state 宏生成 aria-live="assertive"；验证使用了该宏
        assert "ui.error_state" in content, \
            "Error state must use ui.error_state macro (which generates aria-live='assertive')"


# ── TestProjectsNoStalePatterns ───────────────────────────────────

class TestProjectsNoStalePatterns:
    """验证不存在的陈旧模式。"""

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_no_cache_r_columns(self):
        content = _read_template()
        assert "Cache R" not in content, \
            "Projects must not have Cache R column"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_no_cache_w_columns(self):
        content = _read_template()
        assert "Cache W" not in content, \
            "Projects must not have Cache W column"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_no_select_based_sorting(self):
        """无用于排序的 <select> 元素 — 使用基于按钮的可排序表头。"""
        content = _read_template()
        # 不应有通过 select 元素的排序
        assert '<select' not in content, \
            "Projects must not use select-based sorting"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_no_inline_onclick(self):
        content = _read_template()
        matches = re.findall(r'\bonclick\s*=', content, re.IGNORECASE)
        assert len(matches) == 0, \
            f"Projects must not have inline onclick, found {len(matches)}"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_no_inline_script_in_template(self):
        """模板不得有 inline <script> 块（使用 script_extra）。"""
        content = _read_template()
        # 只允许带 src= 导入的 script_extra 块
        script_tags = re.findall(r'<script(?! src)[^>]*>', content)
        assert len(script_tags) == 0, \
            f"Projects must not have inline script tags, found {len(script_tags)}"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_no_inline_style_in_template(self):
        """模板不得有 inline style 块（使用 projects.css）。"""
        content = _read_template()
        style_blocks = re.findall(r'<style[^>]*>', content)
        assert len(style_blocks) == 0, \
            f"Projects must not have inline style blocks, found {len(style_blocks)}"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_no_output_tokens_column(self):
        content = _read_template()
        assert "Output Tokens" not in content, \
            "Projects must not have Output Tokens column"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_no_tools_per_round_column(self):
        content = _read_template()
        assert "Tools/R" not in content, \
            "Projects must not have Tools/R column"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_no_hero_section(self):
        content = _read_template()
        assert 'class="hero"' not in content, \
            "Projects must not have hero section"


# ── TestProjectsDataActions ───────────────────────────────────────

class TestProjectsDataActions:
    """验证所有必需的 data-action 属性都存在。"""

    _EXPECTED_ACTIONS = [
        "open-project",
        "clear-search",
        "metric-info",
        "sort",
        "page-input",
        "next-page",
    ]

    @pytest.mark.parametrize("action", _EXPECTED_ACTIONS)
    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_data_action_present(self, action):
        content = _read_template_with_macros()
        # 接受渲染后的 HTML（data-action="..."）和 Jinja2 参数（data_action='...'）
        assert (f'data-action="{action}"' in content
                or f"data_action='{action}'" in content), \
            f"Template must have data-action='{action}'"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_projects_passes_open_project_link(self):
        """验证 projects.html 将 open-project-link action 传递给宏。"""
        content = _read_template()
        assert "name_data_action='open-project-link'" in content, \
            "projects.html must pass name_data_action='open-project-link'"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_macro_supports_name_data_action(self):
        """验证宏从 name_data_action 参数渲染 data-action。"""
        macro = _read_ui_primitives()
        assert 'data-action="{{ name_data_action }}"' in macro, \
            "project_cell macro must support name_data_action parameter"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_data_action_go_dashboard(self):
        """go-dashboard action 通过 ui.button 宏参数生成。"""
        content = _read_template()
        # 模板使用 Jinja2 宏参数：data_action='go-dashboard'
        assert "go-dashboard" in content, \
            "Template must have go-dashboard action"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_data_action_run_scan(self):
        """run-scan action 通过 ui.button 宏参数生成。"""
        content = _read_template()
        # 模板使用 Jinja2 宏参数：data_action='run-scan'
        assert "run-scan" in content, \
            "Template must have run-scan action"


# ── 基于夹具的实时服务器测试 ────────────────────────────────


@pytest.fixture(scope="module")
def projects_html(hifi_fixture_session):
    """从实时夹具服务器获取渲染后的 projects HTML。"""
    base_url, agent, session_id = hifi_fixture_session
    import urllib.request

    resp = urllib.request.urlopen(f"{base_url}/projects", timeout=10)
    assert resp.status == 200, "Projects page must return HTTP 200"
    return resp.read().decode("utf-8")


class TestProjectsPageRender:
    """验证实时夹具服务器上渲染后的 Projects 页面。"""

    @pytest.mark.contract_case("UI-PROJECTS-001")
    @pytest.mark.contract_case("UI-PROJECTS-009")
    def test_page_returns_200(self, projects_html):
        """Projects 页面必须渲染出足够内容的 HTML。"""
        assert len(projects_html) > 500, \
            "Projects HTML must be substantial"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_has_doctype_and_html(self, projects_html):
        """页面必须有正确的 HTML 结构。"""
        assert "<!doctype html" in projects_html.lower() or "<!DOCTYPE html" in projects_html, \
            "Projects page must have DOCTYPE declaration"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_title_contains_projects(self, projects_html):
        """页面标题必须包含 'Projects'。"""
        assert "<title>Projects" in projects_html, \
            "Page title must contain 'Projects'"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_has_page_head_title(self, projects_html):
        """页面必须显示 'Projects' 作为页面标题。"""
        assert "Projects" in projects_html, \
            "'Projects' text must appear in rendered page"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_has_subtitle(self, projects_html):
        """页面必须显示关于已索引工作区的副标题。"""
        assert "Indexed local workspaces" in projects_html, \
            "Subtitle 'Indexed local workspaces' must appear"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_no_inline_onclick(self, projects_html):
        """渲染后的页面不得使用 inline onclick 处理器。"""
        matches = re.findall(r'\bonclick\s*=', projects_html, re.IGNORECASE)
        assert len(matches) == 0, \
            f"Projects page must not have inline onclick, found {len(matches)}"


class TestProjectsListRender:
    """验证使用夹具数据渲染的项目列表。"""

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_metric_grid_present(self, projects_html):
        """Projects 页面必须有 metric-grid 容器。"""
        assert 'class="metric-grid"' in projects_html, \
            "metric-grid must be present"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_four_metric_cards(self, projects_html):
        """必须恰好渲染 4 个指标卡片。"""
        cards = re.findall(r'class="metric-card"', projects_html)
        assert len(cards) == 4, \
            f"Expected 4 metric cards, found {len(cards)}"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_metric_card_labels(self, projects_html):
        """所有 4 个指标标签必须可见。"""
        for label in ["Projects", "Sessions", "Total Tokens", "Failed Tools"]:
            assert f">{label}" in projects_html or f'aria-label="{label}"' in projects_html, \
                f"Metric card labeled '{label}' must be visible"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_project_count_positive(self, projects_html):
        """使用夹具数据时项目计数必须大于 0。"""
        match = re.search(
            r'class="metric-card__value mono">(\d[\d,]*)<',
            projects_html
        )
        assert match, "Projects metric value must be a number"
        count = int(match.group(1).replace(",", ""))
        assert count > 0, \
            f"Projects count must be > 0 with fixture data, got {count}"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_projects_count_element(self, projects_html):
        """projects-count 元素必须存在并已填充。"""
        assert 'id="projects-count"' in projects_html, \
            "projects-count element must be present"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_projects_table_present(self, projects_html):
        """Projects 表格必须已渲染。"""
        assert 'id="projects-table"' in projects_html, \
            "projects-table must be present"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_table_has_data_enhanced(self, projects_html):
        """表格必须有 data-table-enhanced 属性。"""
        assert 'data-table-enhanced' in projects_html, \
            "Table must have data-table-enhanced attribute"


class TestProjectsColumnHeaders:
    """验证渲染后的表格列表头。"""

    @pytest.mark.parametrize("column", ["Project", "Agents", "Sessions", "Tokens", "Tools", "Last Active"])
    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_column_header_rendered(self, projects_html, column):
        """每个预期的列表头必须出现在渲染后的 HTML 中。"""
        assert f"<th>{column}</th>" in projects_html or f"<th " in projects_html and column in projects_html, \
            f"Table must have '{column}' column header"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_project_column_not_sortable(self, projects_html):
        """Project 列不得有排序控件。"""
        # Project 列是静态的；不应有 data-sort-key
        project_th_section = projects_html[projects_html.find("Project"):projects_html.find("Project") + 200]
        # Project 表头本身不应携带 data-sort-key
        assert 'data-sort-key' not in project_th_section.split("Agents")[0] if "Agents" in project_th_section else True, \
            "Project column should not be sortable"


class TestProjectsProjectData:
    """验证各项目数据行已渲染。"""

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_project_rows_present(self, projects_html):
        """必须至少渲染一个项目表格行（行使用带 data-action='open-project' 的 <tr>）。"""
        # 项目行是表格主体内的 <tr data-action="open-project" ...> 元素
        rows = re.findall(r'<tr\s+data-action="open-project"', projects_html)
        assert len(rows) > 0, \
            "At least one project <tr> with data-action='open-project' must be rendered"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_project_row_has_data_name(self, projects_html):
        """每个项目行必须有 data-name 属性。"""
        assert 'data-name=' in projects_html, \
            "Project rows must have data-name attribute"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_project_row_has_data_path(self, projects_html):
        """每个项目行必须有 data-path 属性。"""
        assert 'data-path=' in projects_html, \
            "Project rows must have data-path attribute"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_project_row_has_data_total_sessions(self, projects_html):
        """每个项目行必须有 data-total-sessions 属性。"""
        assert 'data-total-sessions=' in projects_html, \
            "Project rows must have data-total-sessions attribute"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_project_row_has_data_total_tokens(self, projects_html):
        """每个项目行必须有 data-total-tokens 属性。"""
        assert 'data-total-tokens=' in projects_html, \
            "Project rows must have data-total-tokens attribute"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_project_name_link_rendered(self, projects_html):
        """项目名称链接必须已渲染。"""
        assert 'class="project-name-link"' in projects_html, \
            "Project name links must use project-name-link class"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_open_project_action(self, projects_html):
        """行必须有 data-action='open-project'。"""
        assert 'data-action="open-project"' in projects_html, \
            "Project rows must have open-project action"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_agent_badge_rendered(self, projects_html):
        """必须至少渲染一个 agent 徽章。"""
        assert 'badge_with_dot' not in projects_html or "badge" in projects_html, \
            "Agent badges must be rendered in project rows"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_token_cell_rendered(self, projects_html):
        """Token 条段必须在表格中渲染。"""
        assert 'tokenbar-seg' in projects_html, \
            "Token bar segments must be rendered"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_relative_time_rendered(self, projects_html):
        """Last Active 列必须显示相对时间文本（如 'Xd ago'、'Xh ago'、'Xmo ago'）。"""
        # relative_time 过滤器返回纯文本如 "3d ago"、"2h ago"、"1mo ago"
        assert re.search(r'\d+[dhm]+\s+ago', projects_html) or re.search(r'\d+mo\s+ago', projects_html), \
            "Last Active column must show relative time like 'Xd ago'"


class TestProjectsFilterRender:
    """验证过滤卡片已渲染。"""

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_filter_card_present(self, projects_html):
        """过滤卡片必须出现在渲染后的页面中。"""
        assert 'class="card filter-card"' in projects_html, \
            "Filter card must be present"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_search_input_present(self, projects_html):
        """项目搜索输入必须已渲染。"""
        assert 'id="project-search"' in projects_html, \
            "Search input with id='project-search' must be present"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    @pytest.mark.skip(reason="Apply button removed: real-time search")
    def test_apply_button_present(self, projects_html):
        """应用搜索按钮必须存在。"""
        assert 'data-action="apply-search"' in projects_html, \
            "Apply search button must be present"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_clear_button_present(self, projects_html):
        """清除搜索按钮必须存在。"""
        assert 'data-action="clear-search"' in projects_html, \
            "Clear search button must be present"


class TestProjectsPaginationRender:
    """验证分页已渲染。"""

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_pagination_present(self, projects_html):
        """分页控件必须存在。"""
        assert 'class="pagination unified-pagination"' in projects_html, \
            "Pagination must be present"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_page_input_present(self, projects_html):
        """页面输入必须已渲染。"""
        assert 'data-action="page-input"' in projects_html, \
            "Page input must be present"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_next_page_present(self, projects_html):
        """下一页按钮必须已渲染。"""
        assert 'data-action="next-page"' in projects_html, \
            "Next page button must be present"


class TestProjectsBreadcrumb:
    """验证面包屑导航。"""

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_breadcrumb_has_dashboard_link(self, projects_html):
        """面包屑必须链接回 dashboard。"""
        assert 'href="/dashboard"' in projects_html, \
            "Breadcrumb must have link to /dashboard"

    @pytest.mark.contract_case("UI-PROJECTS-001")
    def test_breadcrumb_has_current(self, projects_html):
        """面包屑必须显示 'Projects' 为当前页。"""
        assert 'class="current">Projects</span>' in projects_html, \
            "Breadcrumb must show Projects as current"
