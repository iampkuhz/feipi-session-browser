"""Sessions List 页面级测试，针对 sessions.html 模板。

验证 Jinja2 模板结构、CSS/JS 引入、筛选栏、
带可排序表头的数据表格、token 栏渲染、分页、
空状态，以及无内联 onclick。

T080 — Sessions List 页面级 pytest。
"""

from __future__ import annotations

import os
import re

import pytest

_SESSIONS_PATH = 'src/session_browser/web/templates/sessions.html'
_SESSIONS_CSS_PATH = 'src/session_browser/web/static/css/sessions-list.css'
_SESSIONS_JS_PATH = 'src/session_browser/web/static/js/sessions-list.js'
_SESSIONS_COMPONENTS_PATH = (
    'src/session_browser/web/templates/components/sessions_list_components.html'
)
_SESSIONS_TABLE_BODY_PATH = 'src/session_browser/web/templates/partials/sessions_table_body.html'
_UI_PRIMITIVES_PATH = 'src/session_browser/web/templates/components/ui_primitives.html'
_UI_PRIMITIVES_DIR = 'src/session_browser/web/templates/components/ui_primitives'


def _read(path: str) -> str:
    with open(path) as f:
        return f.read()


def _read_sessions() -> str:
    parts = [_read(_SESSIONS_PATH)]
    for path in (_SESSIONS_COMPONENTS_PATH, _SESSIONS_TABLE_BODY_PATH):
        if os.path.exists(path):
            parts.append(_read(path))
    return '\n'.join(parts)


def _read_ui_primitives() -> str:
    """Read ui_primitives with split-aware reading."""
    parts = []
    if os.path.exists(_UI_PRIMITIVES_PATH):
        parts.append(_read(_UI_PRIMITIVES_PATH))
    if os.path.isdir(_UI_PRIMITIVES_DIR):
        for f in sorted(__import__('glob').glob(os.path.join(_UI_PRIMITIVES_DIR, '*.html'))):
            parts.append(_read(f))
    return '\n'.join(parts)


def _read_base_html() -> str:
    return _read('src/session_browser/web/templates/base.html')


# ── TestSessionsTemplate（模板结构）────────────────────────────────────────────


class TestSessionsTemplate:
    """验证 sessions Jinja2 模板结构正确渲染。"""

    @pytest.mark.contract_case('UI-SESSIONS-001', 'UI-SESSIONS-017')
    @pytest.mark.contract_case('UI-SESSIONS-011')
    def test_template_file_exists(self):
        assert os.path.isfile(_SESSIONS_PATH), f'{_SESSIONS_PATH} must exist'

    @pytest.mark.contract_case('UI-SESSIONS-001', 'UI-SESSIONS-017')
    @pytest.mark.contract_case('UI-SESSIONS-014')
    def test_extends_base(self):
        content = _read_sessions()
        assert '{% extends "base.html" %}' in content, 'Sessions must extend base.html'

    @pytest.mark.contract_case('UI-SESSIONS-001', 'UI-SESSIONS-017')
    def test_active_page_set(self):
        content = _read_sessions()
        assert "active_page = 'sessions'" in content, "Sessions must set active_page = 'sessions'"

    @pytest.mark.contract_case('UI-SESSIONS-001', 'UI-SESSIONS-017')
    def test_ui_primitives_imported(self):
        content = _read_sessions()
        assert 'import "components/ui_primitives.html"' in content, (
            'Sessions must import ui_primitives.html'
        )

    @pytest.mark.contract_case('UI-SESSIONS-001', 'UI-SESSIONS-017')
    def test_no_inline_onclick(self):
        """Sessions 不得使用内联 onclick 处理器。"""
        content = _read_sessions()
        matches = re.findall(r'\bonclick\s*=', content, re.IGNORECASE)
        assert len(matches) == 0, (
            f'Sessions must not have inline onclick, found {len(matches)} occurrences'
        )


# ── TestSessionsImports（CSS/JS 引入）─────────────────────────────────────────────


class TestSessionsImports:
    """验证 CSS 和 JS 引入语句。"""

    @pytest.mark.contract_case('UI-SESSIONS-001', 'UI-SESSIONS-017')
    def test_css_import_sessions_list_css(self):
        content = _read_sessions()
        assert 'href="/static/css/sessions-list.css"' in content, (
            'Sessions must import sessions-list.css'
        )

    @pytest.mark.contract_case('UI-SESSIONS-001', 'UI-SESSIONS-017')
    def test_css_import_ui_primitives_css(self):
        """ui-primitives.css 由 base.html 加载，页面模板不重复引入。
        验证 base.html 已加载它（页面模板继承）。
        """
        base = _read_base_html()
        assert 'href="/static/css/ui-primitives.css"' in base, (
            'base.html must load ui-primitives.css'
        )
        # 页面模板不得重复引入（由 static_contract_check 检查）
        content = _read_sessions()
        assert 'href="/static/css/ui-primitives.css"' not in content, (
            'Sessions must not duplicate ui-primitives.css already loaded by base.html'
        )

    @pytest.mark.contract_case('UI-SESSIONS-001', 'UI-SESSIONS-017')
    def test_js_import_sessions_list_js(self):
        content = _read_sessions()
        assert 'src="/static/js/sessions-list.js"' in content, (
            'Sessions must import sessions-list.js'
        )

    @pytest.mark.contract_case('UI-SESSIONS-001', 'UI-SESSIONS-017')
    def test_js_import_ui_primitives_js(self):
        # ui_primitives.js is loaded globally via base.html, not sessions.html
        content = _read_base_html()
        assert 'src="/static/js/ui_primitives.js"' in content, (
            'base.html must load ui_primitives.js globally'
        )

    @pytest.mark.contract_case('UI-SESSIONS-001', 'UI-SESSIONS-017')
    def test_css_file_exists_on_disk(self):
        assert os.path.isfile(_SESSIONS_CSS_PATH), 'sessions-list.css must exist on disk'

    @pytest.mark.contract_case('UI-SESSIONS-001', 'UI-SESSIONS-017')
    def test_js_file_exists_on_disk(self):
        assert os.path.isfile(_SESSIONS_JS_PATH), 'sessions-list.js must exist on disk'


# ── TestSessionsPageHead（页面头部）────────────────────────────────────────────


class TestSessionsPageHead:
    """验证页面头部结构。"""

    @pytest.mark.contract_case('UI-SESSIONS-001', 'UI-SESSIONS-017')
    def test_page_head_section_present(self):
        content = _read_sessions()
        assert 'ui.page_head(' in content, 'Sessions must use ui.page_head() macro for page header'

    @pytest.mark.contract_case('UI-SESSIONS-001', 'UI-SESSIONS-017')
    def test_page_head_has_h1(self):
        content = _read_sessions()
        assert "'Sessions'" in content, "Page-head must use 'Sessions' as title argument"

    @pytest.mark.contract_case('UI-SESSIONS-001', 'UI-SESSIONS-017')
    def test_page_head_has_subtitle(self):
        content = _read_sessions()
        assert 'Browse indexed local agent runs' in content, (
            'Page-head must have subtitle about browsing sessions'
        )


# ── TestSessionsFilterBar（筛选栏）───────────────────────────────────────────


class TestSessionsFilterBar:
    """验证带搜索和下拉的筛选行。"""

    @pytest.mark.contract_case('UI-SESSIONS-001', 'UI-SESSIONS-017')
    def test_filter_form_exists(self):
        content = _read_sessions()
        assert 'id="session-filter-form"' in content or "id='session-filter-form'" in content, (
            'Sessions must have a filter form'
        )

    @pytest.mark.contract_case('UI-SESSIONS-001', 'UI-SESSIONS-017')
    def test_search_input(self):
        content = _read_sessions()
        assert 'id="session-search"' in content or "id='session-search'" in content, (
            'Filter bar must have search input'
        )

    @pytest.mark.contract_case('UI-SESSIONS-001', 'UI-SESSIONS-017')
    def test_agent_dropdown(self):
        content = _read_sessions()
        assert 'id="filter-agent"' in content or "id='filter-agent'" in content, (
            'Filter bar must have agent dropdown'
        )
        assert 'All Agents' in content or 'all_label' in content, (
            "Agent dropdown must have 'All Agents' default"
        )
        assert 'claude_code' in content, 'Agent dropdown must have claude_code option'
        assert 'codex' in content, 'Agent dropdown must have codex option'
        assert 'qoder' in content, 'Agent dropdown must have qoder option'

    @pytest.mark.contract_case('UI-SESSIONS-001', 'UI-SESSIONS-017')
    def test_model_dropdown(self):
        content = _read_sessions()
        assert 'id="filter-model"' in content or "id='filter-model'" in content, (
            'Filter bar must have model dropdown'
        )
        assert 'All Models' in content or 'all_label' in content, (
            "Model dropdown must have 'All Models' default"
        )

    @pytest.mark.contract_case('UI-SESSIONS-001', 'UI-SESSIONS-017')
    def test_project_dropdown(self):
        content = _read_sessions()
        assert 'id="filter-project"' in content or "id='filter-project'" in content, (
            'Filter bar must have project dropdown'
        )
        assert 'All Projects' in content or 'all_label' in content, (
            "Project dropdown must have 'All Projects' default"
        )

    @pytest.mark.contract_case('UI-SESSIONS-001', 'UI-SESSIONS-017')
    def test_apply_button(self):
        content = _read_sessions()
        assert "data_action='apply'" not in content, (
            'Real-time filtering must not render a stale apply button'
        )
        assert "'Apply'" not in content, 'Apply button text must not be present'

    @pytest.mark.contract_case('UI-SESSIONS-001', 'UI-SESSIONS-017')
    def test_clear_all_button_conditional(self):
        content = _read_sessions()
        assert (
            'filter_q or filter_agent or filter_model or filter_project' in content
            or 'has_active_filter' in content
        ), 'Clear All button must be conditional on active filters'
        assert "data_action='clear'" in content, "Clear All must use data_action='clear'"

    @pytest.mark.contract_case('UI-SESSIONS-001', 'UI-SESSIONS-017')
    def test_active_filters_excludes_search_chip(self):
        content = _read(_SESSIONS_COMPONENTS_PATH)
        assert 'Search:' not in content, 'Active filters must not render search as a filter chip'

    @pytest.mark.contract_case('UI-SESSIONS-001', 'UI-SESSIONS-017')
    def test_filter_controls_have_compact_classes(self):
        content = _read_sessions()
        for cls in [
            'sessions-filter-select--agent',
            'sessions-filter-select--model',
            'sessions-filter-select--project',
            'sessions-filter-select--status',
        ]:
            assert cls in content, f'Missing compact filter class {cls}'


# ── TestSessionsDataTable（数据表格）───────────────────────────────────────────


class TestSessionsDataTable:
    """验证带可排序表头的数据表格。"""

    @pytest.mark.contract_case('UI-SESSIONS-001', 'UI-SESSIONS-017')
    def test_data_table_present(self):
        content = _read_sessions()
        assert 'class="data-table"' in content, 'Sessions must have a data-table'
        assert 'role="table"' in content, "Data table must have role='table'"

    @pytest.mark.contract_case('UI-SESSIONS-001', 'UI-SESSIONS-017')
    def test_table_headers(self):
        content = _read_sessions()
        for header in [
            'Session',
            'Project',
            'Agent',
            'Model',
            'Tokens',
            'Rounds',
            'Tools',
            'Subagents',
            'Duration',
            'Process Time',
            'Failure',
            'Created',
            'Updated',
        ]:
            assert header in content, f"Table must have '{header}' column header"

    @pytest.mark.contract_case('UI-SESSIONS-001', 'UI-SESSIONS-017')
    def test_sortable_columns(self):
        content = _read_sessions()
        for sort_key in [
            'tokens',
            'rounds',
            'tools',
            'subagents',
            'duration',
            'process-time',
            'failure',
            'created',
            'updated',
        ]:
            assert f"'{sort_key}'" in content, f"Must include sortable column key '{sort_key}'"

    @pytest.mark.contract_case('UI-SESSIONS-001', 'UI-SESSIONS-017')
    def test_sort_buttons_with_data_action(self):
        content = _read_sessions()
        assert 'data-action="sort"' in content, (
            "Sortable header macro must render data-action='sort'"
        )
        assert 'data-sort-key="{{ col[1] }}"' in content, (
            'Sortable header macro must bind each column sort key'
        )

    @pytest.mark.contract_case('UI-SESSIONS-001', 'UI-SESSIONS-017')
    def test_sort_icons_present(self):
        content = _read_sessions()
        assert 'c-data-table__sort-icon' in content, (
            'Sort buttons must use the canonical c-data-table__sort-icon'
        )

    @pytest.mark.contract_case('UI-SESSIONS-001', 'UI-SESSIONS-017')
    def test_static_headers(self):
        content = _read_sessions()
        # static-header 可独立出现或与 col-* 类组合
        static = re.findall(r'static-header', content)
        assert len(static) >= 3, (
            f'Must have at least 3 static (non-sortable) headers, found {len(static)}'
        )

    @pytest.mark.contract_case('UI-SESSIONS-001', 'UI-SESSIONS-017')
    def test_aria_sort_on_active(self):
        content = _read_sessions()
        # 统一模式：data-sort-dir 跟踪当前排序状态（替代 aria-sort）
        assert 'data-sort-dir=' in content, 'Active sortable th must have data-sort-dir attribute'


# ── TestSessionsTokenBar（Token 进度条）────────────────────────────────────────────


class TestSessionsTokenBar:
    """验证 token 列中的 tokenbar 渲染。

    Token 单元格现在通过 ui_primitives.html 中的 ui.token_cell 宏渲染。
    测试验证 sessions.html 调用了该宏，且宏提供了正确的 HTML。
    """

    @pytest.mark.contract_case('UI-SESSIONS-001', 'UI-SESSIONS-017')
    def test_token_cell_class(self):
        content = _read_sessions()
        assert 'ui.token_cell' in content, 'sessions.html must call ui.token_cell macro'

    @pytest.mark.contract_case('UI-SESSIONS-001', 'UI-SESSIONS-017')
    def test_token_total_value(self):
        macro = _read_ui_primitives()
        assert 'class="token-total__value"' in macro, (
            'token_cell macro must have token-total__value'
        )
        assert 'class="token-cell"' in macro, 'token_cell macro must have token-cell class'
        assert 'format_compact_token' in macro, 'Token value must use format_compact_token filter'

    @pytest.mark.contract_case('UI-SESSIONS-001', 'UI-SESSIONS-017')
    def test_tokenbar_container(self):
        macro = _read_ui_primitives()
        assert 'class="tokenbar"' in macro, 'token_cell macro must have tokenbar container'

    @pytest.mark.contract_case('UI-SESSIONS-001', 'UI-SESSIONS-017')
    def test_tokenbar_segments(self):
        macro = _read_ui_primitives()
        for seg_class in [
            'tokenbar-seg fresh',
            'tokenbar-seg read',
            'tokenbar-seg write',
            'tokenbar-seg out',
        ]:
            assert seg_class in macro, f'token_cell macro must have segment: {seg_class}'

    @pytest.mark.contract_case('UI-SESSIONS-001', 'UI-SESSIONS-017')
    def test_tokenbar_has_four_segments(self):
        # In split structure, token_cell body is in _helpers.html;
        # the wrapper in ui_primitives.html delegates to it.
        # Search for the actual implementation with tokenbar-seg spans.
        macro = _read_ui_primitives()
        # Find ALL macro definitions and check the one with actual content
        all_starts = [m.start() for m in re.finditer(r'\{%\s*macro\s+token_cell\(', macro)]
        for start_pos in all_starts:
            end_pos = macro.find('{%- endmacro %}', start_pos)
            if end_pos == -1:
                end_pos = macro.find('{% endmacro %}', start_pos)
            macro_body = macro[start_pos:end_pos]
            segments = re.findall(r'class="tokenbar-seg ', macro_body)
            if segments:
                assert len(segments) == 4, (
                    f'token_cell macro must have 4 segments, found {len(segments)}'
                )
                return
        pytest.fail('token_cell macro with tokenbar-seg segments not found')


# ── TestSessionsPagination（分页）──────────────────────────────────────────


class TestSessionsPagination:
    """验证分页使用 ui.pagination 宏。"""

    @pytest.mark.contract_case('UI-SESSIONS-001', 'UI-SESSIONS-017')
    def test_pagination_uses_macro(self):
        content = _read_sessions()
        assert 'ui.pagination(' in content, 'Sessions must use ui.pagination macro for pagination'

    @pytest.mark.contract_case('UI-SESSIONS-001', 'UI-SESSIONS-017')
    def test_pagination_passes_page_params(self):
        content = _read_sessions()
        assert 'current_page' in content, 'Pagination macro call must pass current_page'
        assert 'total_pages' in content, 'Pagination macro call must pass total_pages'

    @pytest.mark.contract_case('UI-SESSIONS-001', 'UI-SESSIONS-017')
    def test_pagination_passes_page_size(self):
        content = _read_sessions()
        assert 'page_size' in content, (
            'Pagination macro call must pass page_size for page size selector'
        )

    @pytest.mark.contract_case('UI-SESSIONS-001', 'UI-SESSIONS-017')
    def test_pagination_conditional(self):
        content = _read_sessions()
        assert 'total_count > 0' in content, 'Pagination must only render when total_count > 0'


# ── TestSessionsEmptyState（空状态）──────────────────────────────────────────


class TestSessionsEmptyState:
    """验证空状态渲染。"""

    @pytest.mark.contract_case('UI-SESSIONS-001', 'UI-SESSIONS-017')
    def test_empty_state_condition(self):
        content = _read_sessions()
        assert (
            '{% if has_active_filter %}' in content
            or '{% if has_active_filter' in content
            or 'has_active_filter' in content
        ), 'Sessions must check for active filter in empty state'

    @pytest.mark.contract_case('UI-SESSIONS-001', 'UI-SESSIONS-017')
    def test_empty_state_uses_ui_macro(self):
        content = _read_sessions()
        assert 'ui.empty_state' in content, 'Empty state must use ui.empty_state macro'

    @pytest.mark.contract_case('UI-SESSIONS-001', 'UI-SESSIONS-017')
    def test_filtered_empty_message(self):
        content = _read_sessions()
        assert 'No sessions match your current filters' in content, (
            'Must show message for filtered empty state'
        )

    @pytest.mark.contract_case('UI-SESSIONS-001', 'UI-SESSIONS-017')
    def test_true_empty_message(self):
        content = _read_sessions()
        assert 'No sessions indexed yet' in content, 'Must show message for true empty state'

    @pytest.mark.contract_case('UI-SESSIONS-001', 'UI-SESSIONS-017')
    def test_filtered_empty_has_clear_button(self):
        content = _read_sessions()
        assert 'Clear All Filters' in content, 'Filtered empty state must have clear filters button'


# ── TestSessionsRowData（行数据属性）─────────────────────────────────────────────


class TestSessionsRowData:
    """验证会话行上的 data 属性。"""

    @pytest.mark.contract_case('UI-SESSIONS-001', 'UI-SESSIONS-017')
    def test_row_data_action(self):
        content = _read_sessions()
        assert 'data-action="row"' in content, "Session rows must have data-action='row'"

    @pytest.mark.contract_case('UI-SESSIONS-001', 'UI-SESSIONS-017')
    def test_row_data_attributes(self):
        content = _read_sessions()
        for attr in ['data-agent', 'data-model', 'data-project', 'data-session-id']:
            assert attr in content, f'Session row must have {attr}'

    @pytest.mark.contract_case('UI-SESSIONS-001', 'UI-SESSIONS-017')
    def test_row_has_encoded_detail_url(self):
        content = _read('src/session_browser/web/templates/partials/sessions_table_body.html')
        assert 'data-detail-url' in content, 'Session rows must expose a stable detail URL'
        assert "urlencode('')" in content, (
            'Session detail URLs must URL-encode agent and session id'
        )
        assert 'data-session-link' in content, (
            'Session title link must be identifiable for opening feedback'
        )

    @pytest.mark.contract_case('UI-SESSIONS-001', 'UI-SESSIONS-017')
    def test_row_click_opening_feedback(self):
        js = _read(_SESSIONS_JS_PATH)
        css = _read(_SESSIONS_CSS_PATH)
        assert 'markRowOpening' in js
        assert 'is-opening' in js
        assert 'is-opening' in css

    @pytest.mark.contract_case('UI-SESSIONS-001', 'UI-SESSIONS-017')
    def test_agent_badge(self):
        # Badge rendering logic lives in ui_primitives split module
        content = _read_ui_primitives()
        assert 'badge' in content, 'Sessions must have agent badges'
        for badge_class in ['cc', 'cx', 'qd']:
            assert badge_class in content, f"Must have agent badge class '{badge_class}'"


class TestSessionsWideLayout:
    """验证 Sessions 页面宽屏内容区契约。"""

    @pytest.mark.contract_case('UI-SESSIONS-001', 'UI-SESSIONS-017')
    def test_wide_max_width_expands(self):
        css = _read(_SESSIONS_CSS_PATH)
        assert 'max-width: 1880px' in css, 'Sessions content must expand on wide screens'

    @pytest.mark.contract_case('UI-SESSIONS-001', 'UI-SESSIONS-017')
    def test_page_css_does_not_define_body_shell_state(self):
        css = _read(_SESSIONS_CSS_PATH)
        assert 'body.hide-left' not in css
        assert 'body.focus' not in css


# ── TestSessionsBreadcrumb（面包屑导航）──────────────────────────────────────────


class TestSessionsBreadcrumb:
    """验证面包屑导航。"""

    @pytest.mark.contract_case('UI-SESSIONS-001', 'UI-SESSIONS-017')
    def test_breadcrumb_has_dashboard_link(self):
        content = _read_sessions()
        assert 'href="/dashboard"' in content, 'Breadcrumb must link to /dashboard'

    @pytest.mark.contract_case('UI-SESSIONS-001', 'UI-SESSIONS-017')
    def test_breadcrumb_has_current(self):
        content = _read_sessions()
        assert 'class="current"' in content, 'Breadcrumb must have current page indicator'
