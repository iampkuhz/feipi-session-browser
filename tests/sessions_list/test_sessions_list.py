"""Page-specific sessions list tests for sessions.html.

Verifies the Jinja2 template structure, CSS/JS imports, filter bar,
data table with sortable headers, token bar rendering, pagination,
empty states, and absence of inline onclick.

T080 — Sessions List page-specific pytest.
"""

from __future__ import annotations

import pytest
import os
import re

_SESSIONS_PATH = "src/session_browser/web/templates/sessions.html"
_SESSIONS_CSS_PATH = "src/session_browser/web/static/css/sessions-list.css"
_SESSIONS_JS_PATH = "src/session_browser/web/static/js/sessions-list.js"
_UI_PRIMITIVES_PATH = "src/session_browser/web/templates/components/ui_primitives.html"


def _read(path: str) -> str:
    with open(path) as f:
        return f.read()


def _read_sessions() -> str:
    return _read(_SESSIONS_PATH)


def _read_ui_primitives() -> str:
    return _read(_UI_PRIMITIVES_PATH)


def _read_base_html() -> str:
    return _read("src/session_browser/web/templates/base.html")


# ── TestSessionsTemplate ─────────────────────────────────────────────

class TestSessionsTemplate:
    """Verify the sessions Jinja2 template renders structurally."""

    @pytest.mark.contract_case("UI-SESSIONS-001", "UI-SESSIONS-017")
    @pytest.mark.contract_case("UI-SESSIONS-011")
    def test_template_file_exists(self):
        assert os.path.isfile(_SESSIONS_PATH), \
            f"{_SESSIONS_PATH} must exist"

    @pytest.mark.contract_case("UI-SESSIONS-001", "UI-SESSIONS-017")
    @pytest.mark.contract_case("UI-SESSIONS-014")
    def test_extends_base(self):
        content = _read_sessions()
        assert '{% extends "base.html" %}' in content, \
            "Sessions must extend base.html"

    @pytest.mark.contract_case("UI-SESSIONS-001", "UI-SESSIONS-017")
    def test_active_page_set(self):
        content = _read_sessions()
        assert "active_page = 'sessions'" in content, \
            "Sessions must set active_page = 'sessions'"

    @pytest.mark.contract_case("UI-SESSIONS-001", "UI-SESSIONS-017")
    def test_ui_primitives_imported(self):
        content = _read_sessions()
        assert 'import "components/ui_primitives.html"' in content, \
            "Sessions must import ui_primitives.html"

    @pytest.mark.contract_case("UI-SESSIONS-001", "UI-SESSIONS-017")
    def test_no_inline_onclick(self):
        """Sessions must not use inline onclick handlers."""
        content = _read_sessions()
        matches = re.findall(r'\bonclick\s*=', content, re.IGNORECASE)
        assert len(matches) == 0, \
            f"Sessions must not have inline onclick, found {len(matches)} occurrences"


# ── TestSessionsImports ──────────────────────────────────────────────

class TestSessionsImports:
    """Verify CSS and JS import statements."""

    @pytest.mark.contract_case("UI-SESSIONS-001", "UI-SESSIONS-017")
    def test_css_import_sessions_list_css(self):
        content = _read_sessions()
        assert 'href="/static/css/sessions-list.css"' in content, \
            "Sessions must import sessions-list.css"

    @pytest.mark.contract_case("UI-SESSIONS-001", "UI-SESSIONS-017")
    def test_css_import_ui_primitives_css(self):
        """ui-primitives.css is loaded by base.html, not duplicated by page templates.
        Verify that base.html loads it (page templates inherit it)."""
        base = _read_base_html()
        assert 'href="/static/css/ui-primitives.css"' in base, \
            "base.html must load ui-primitives.css"
        # Page template must NOT duplicate it (checked by static_contract_check)
        content = _read_sessions()
        assert 'href="/static/css/ui-primitives.css"' not in content, \
            "Sessions must not duplicate ui-primitives.css already loaded by base.html"

    @pytest.mark.contract_case("UI-SESSIONS-001", "UI-SESSIONS-017")
    def test_js_import_sessions_list_js(self):
        content = _read_sessions()
        assert 'src="/static/js/sessions-list.js"' in content, \
            "Sessions must import sessions-list.js"

    @pytest.mark.contract_case("UI-SESSIONS-001", "UI-SESSIONS-017")
    def test_js_import_ui_primitives_js(self):
        content = _read_sessions()
        assert 'src="/static/js/ui_primitives.js"' in content, \
            "Sessions must import ui_primitives.js"

    @pytest.mark.contract_case("UI-SESSIONS-001", "UI-SESSIONS-017")
    def test_css_file_exists_on_disk(self):
        assert os.path.isfile(_SESSIONS_CSS_PATH), \
            "sessions-list.css must exist on disk"

    @pytest.mark.contract_case("UI-SESSIONS-001", "UI-SESSIONS-017")
    def test_js_file_exists_on_disk(self):
        assert os.path.isfile(_SESSIONS_JS_PATH), \
            "sessions-list.js must exist on disk"


# ── TestSessionsPageHead ─────────────────────────────────────────────

class TestSessionsPageHead:
    """Verify page-head structure."""

    @pytest.mark.contract_case("UI-SESSIONS-001", "UI-SESSIONS-017")
    def test_page_head_section_present(self):
        content = _read_sessions()
        assert 'ui.page_head(' in content, \
            "Sessions must use ui.page_head() macro for page header"

    @pytest.mark.contract_case("UI-SESSIONS-001", "UI-SESSIONS-017")
    def test_page_head_has_h1(self):
        content = _read_sessions()
        assert "'Sessions'" in content, \
            "Page-head must use 'Sessions' as title argument"

    @pytest.mark.contract_case("UI-SESSIONS-001", "UI-SESSIONS-017")
    def test_page_head_has_subtitle(self):
        content = _read_sessions()
        assert "Browse indexed local agent runs" in content, \
            "Page-head must have subtitle about browsing sessions"


# ── TestSessionsFilterBar ────────────────────────────────────────────

class TestSessionsFilterBar:
    """Verify filter row with search + dropdowns."""

    @pytest.mark.contract_case("UI-SESSIONS-001", "UI-SESSIONS-017")
    def test_filter_form_exists(self):
        content = _read_sessions()
        assert 'id="session-filter-form"' in content or "id='session-filter-form'" in content, \
            "Sessions must have a filter form"

    @pytest.mark.contract_case("UI-SESSIONS-001", "UI-SESSIONS-017")
    def test_search_input(self):
        content = _read_sessions()
        assert 'id="session-search"' in content or "id='session-search'" in content, \
            "Filter bar must have search input"

    @pytest.mark.contract_case("UI-SESSIONS-001", "UI-SESSIONS-017")
    def test_agent_dropdown(self):
        content = _read_sessions()
        assert 'id="filter-agent"' in content or "id='filter-agent'" in content, \
            "Filter bar must have agent dropdown"
        assert "All Agents" in content or "all_label" in content, \
            "Agent dropdown must have 'All Agents' default"
        assert "claude_code" in content, \
            "Agent dropdown must have claude_code option"
        assert "codex" in content, \
            "Agent dropdown must have codex option"
        assert "qoder" in content, \
            "Agent dropdown must have qoder option"

    @pytest.mark.contract_case("UI-SESSIONS-001", "UI-SESSIONS-017")
    def test_model_dropdown(self):
        content = _read_sessions()
        assert 'id="filter-model"' in content or "id='filter-model'" in content, \
            "Filter bar must have model dropdown"
        assert "All Models" in content or "all_label" in content, \
            "Model dropdown must have 'All Models' default"

    @pytest.mark.contract_case("UI-SESSIONS-001", "UI-SESSIONS-017")
    def test_project_dropdown(self):
        content = _read_sessions()
        assert 'id="filter-project"' in content or "id='filter-project'" in content, \
            "Filter bar must have project dropdown"
        assert "All Projects" in content or "all_label" in content, \
            "Project dropdown must have 'All Projects' default"

    @pytest.mark.contract_case("UI-SESSIONS-001", "UI-SESSIONS-017")
    def test_apply_button(self):
        content = _read_sessions()
        assert "data_action='apply'" in content, \
            "Filter bar must have apply button with data_action"
        assert "'Apply'" in content, \
            "Apply button text must be present as macro argument"

    @pytest.mark.contract_case("UI-SESSIONS-001", "UI-SESSIONS-017")
    def test_clear_all_button_conditional(self):
        content = _read_sessions()
        assert "filter_q or filter_agent or filter_model or filter_project" in content, \
            "Clear All button must be conditional on active filters"
        assert "data_action='clear'" in content, \
            "Clear All must use data_action='clear'"


# ── TestSessionsDataTable ────────────────────────────────────────────

class TestSessionsDataTable:
    """Verify data table with sortable headers."""

    @pytest.mark.contract_case("UI-SESSIONS-001", "UI-SESSIONS-017")
    def test_data_table_present(self):
        content = _read_sessions()
        assert 'class="data-table"' in content, \
            "Sessions must have a data-table"
        assert 'role="table"' in content, \
            "Data table must have role='table'"

    @pytest.mark.contract_case("UI-SESSIONS-001", "UI-SESSIONS-017")
    def test_table_headers(self):
        content = _read_sessions()
        for header in ["Title", "Project", "Agent", "Model", "Tokens", "Rounds", "Tools", "Duration", "Updated"]:
            assert header in content, \
                f"Table must have '{header}' column header"

    @pytest.mark.contract_case("UI-SESSIONS-001", "UI-SESSIONS-017")
    def test_sortable_columns(self):
        content = _read_sessions()
        # Unified pattern: col-num sortable or just sortable
        sortable = re.findall(r'class="[^"]*sortable[^"]*"', content)
        # Tokens, Rounds, Tools, Duration, Updated are sortable
        assert len(sortable) >= 4, \
            f"Must have at least 4 sortable columns, found {len(sortable)}"

    @pytest.mark.contract_case("UI-SESSIONS-001", "UI-SESSIONS-017")
    def test_sort_buttons_with_data_action(self):
        content = _read_sessions()
        sort_buttons = re.findall(r'data-action="sort"', content)
        assert len(sort_buttons) >= 4, \
            f"Must have at least 4 sort buttons, found {len(sort_buttons)}"

    @pytest.mark.contract_case("UI-SESSIONS-001", "UI-SESSIONS-017")
    def test_sort_icons_present(self):
        content = _read_sessions()
        # Unified pattern: .sort-mark is the arrow container
        assert 'class="sort-mark"' in content, \
            "Sort buttons must have sort-mark class for arrow injection"

    @pytest.mark.contract_case("UI-SESSIONS-001", "UI-SESSIONS-017")
    def test_static_headers(self):
        content = _read_sessions()
        # static-header can appear as standalone or combined with col-* classes
        static = re.findall(r'static-header', content)
        assert len(static) >= 3, \
            f"Must have at least 3 static (non-sortable) headers, found {len(static)}"

    @pytest.mark.contract_case("UI-SESSIONS-001", "UI-SESSIONS-017")
    def test_aria_sort_on_active(self):
        content = _read_sessions()
        # Unified pattern: data-sort-dir tracks active sort state (replaces aria-sort)
        assert 'data-sort-dir=' in content, \
            "Active sortable th must have data-sort-dir attribute"


# ── TestSessionsTokenBar ─────────────────────────────────────────────

class TestSessionsTokenBar:
    """Verify token bar rendering in token column.

    Token cells are now rendered via ui.token_cell macro in ui_primitives.html.
    Tests verify sessions.html calls the macro, and the macro provides the HTML.
    """

    @pytest.mark.contract_case("UI-SESSIONS-001", "UI-SESSIONS-017")
    def test_token_cell_class(self):
        content = _read_sessions()
        assert 'ui.token_cell' in content, \
            "sessions.html must call ui.token_cell macro"

    @pytest.mark.contract_case("UI-SESSIONS-001", "UI-SESSIONS-017")
    def test_token_total_value(self):
        macro = _read_ui_primitives()
        assert 'class="token-total__value"' in macro, \
            "token_cell macro must have token-total__value"
        assert 'class="token-cell"' in macro, \
            "token_cell macro must have token-cell class"
        assert "format_compact_token" in macro, \
            "Token value must use format_compact_token filter"

    @pytest.mark.contract_case("UI-SESSIONS-001", "UI-SESSIONS-017")
    def test_tokenbar_container(self):
        macro = _read_ui_primitives()
        assert 'class="tokenbar"' in macro, \
            "token_cell macro must have tokenbar container"

    @pytest.mark.contract_case("UI-SESSIONS-001", "UI-SESSIONS-017")
    def test_tokenbar_segments(self):
        macro = _read_ui_primitives()
        for seg_class in ["tokenbar-seg fresh", "tokenbar-seg read", "tokenbar-seg write", "tokenbar-seg out"]:
            assert seg_class in macro, \
                f"token_cell macro must have segment: {seg_class}"

    @pytest.mark.contract_case("UI-SESSIONS-001", "UI-SESSIONS-017")
    def test_tokenbar_has_four_segments(self):
        macro = _read_ui_primitives()
        # Find the token_cell macro definition and count segments within it
        macro_start = macro.find('{% macro token_cell(')
        macro_end = macro.find('{%- endmacro %}', macro_start)
        if macro_end == -1:
            macro_end = macro.find('{% endmacro %}', macro_start)
        macro_body = macro[macro_start:macro_end]
        segments = re.findall(r'class="tokenbar-seg ', macro_body)
        assert len(segments) == 4, \
            f"token_cell macro must have 4 segments, found {len(segments)}"


# ── TestSessionsPagination ───────────────────────────────────────────

class TestSessionsPagination:
    """Verify pagination uses ui.pagination macro."""

    @pytest.mark.contract_case("UI-SESSIONS-001", "UI-SESSIONS-017")
    def test_pagination_uses_macro(self):
        content = _read_sessions()
        assert "ui.pagination(" in content, \
            "Sessions must use ui.pagination macro for pagination"

    @pytest.mark.contract_case("UI-SESSIONS-001", "UI-SESSIONS-017")
    def test_pagination_passes_page_params(self):
        content = _read_sessions()
        assert "current_page" in content, \
            "Pagination macro call must pass current_page"
        assert "total_pages" in content, \
            "Pagination macro call must pass total_pages"

    @pytest.mark.contract_case("UI-SESSIONS-001", "UI-SESSIONS-017")
    def test_pagination_passes_page_size(self):
        content = _read_sessions()
        assert "page_size" in content, \
            "Pagination macro call must pass page_size for page size selector"

    @pytest.mark.contract_case("UI-SESSIONS-001", "UI-SESSIONS-017")
    def test_pagination_conditional(self):
        content = _read_sessions()
        assert "total_count > 0" in content, \
            "Pagination must only render when total_count > 0"


# ── TestSessionsEmptyState ───────────────────────────────────────────

class TestSessionsEmptyState:
    """Verify empty state rendering."""

    @pytest.mark.contract_case("UI-SESSIONS-001", "UI-SESSIONS-017")
    @pytest.mark.contract_case("UI-SESSIONS-010")
    def test_empty_state_condition(self):
        content = _read_sessions()
        assert "{% if has_active_filter %}" in content or \
               "{% if has_active_filter" in content or \
               "has_active_filter" in content, \
            "Sessions must check for active filter in empty state"

    @pytest.mark.contract_case("UI-SESSIONS-001", "UI-SESSIONS-017")
    def test_empty_state_uses_ui_macro(self):
        content = _read_sessions()
        assert "ui.empty_state" in content, \
            "Empty state must use ui.empty_state macro"

    @pytest.mark.contract_case("UI-SESSIONS-001", "UI-SESSIONS-017")
    def test_filtered_empty_message(self):
        content = _read_sessions()
        assert "No sessions match your current filters" in content, \
            "Must show message for filtered empty state"

    @pytest.mark.contract_case("UI-SESSIONS-001", "UI-SESSIONS-017")
    def test_true_empty_message(self):
        content = _read_sessions()
        assert "No sessions indexed yet" in content, \
            "Must show message for true empty state"

    @pytest.mark.contract_case("UI-SESSIONS-001", "UI-SESSIONS-017")
    def test_filtered_empty_has_clear_button(self):
        content = _read_sessions()
        assert "Clear All Filters" in content, \
            "Filtered empty state must have clear filters button"


# ── TestSessionsRowData ──────────────────────────────────────────────

class TestSessionsRowData:
    """Verify data attributes on session rows."""

    @pytest.mark.contract_case("UI-SESSIONS-001", "UI-SESSIONS-017")
    def test_row_data_action(self):
        content = _read_sessions()
        assert 'data-action="row"' in content, \
            "Session rows must have data-action='row'"

    @pytest.mark.contract_case("UI-SESSIONS-001", "UI-SESSIONS-017")
    def test_row_data_attributes(self):
        content = _read_sessions()
        for attr in ["data-agent", "data-model", "data-project", "data-session-id"]:
            assert attr in content, \
                f"Session row must have {attr}"

    @pytest.mark.contract_case("UI-SESSIONS-001", "UI-SESSIONS-017")
    def test_agent_badge(self):
        content = _read_sessions()
        assert 'class="badge ' in content, \
            "Sessions must have agent badges"
        for badge_class in ["cc", "cx", "qd"]:
            assert badge_class in content, \
                f"Must have agent badge class '{badge_class}'"


# ── TestSessionsBreadcrumb ───────────────────────────────────────────

class TestSessionsBreadcrumb:
    """Verify breadcrumb navigation."""

    @pytest.mark.contract_case("UI-SESSIONS-001", "UI-SESSIONS-017")
    def test_breadcrumb_has_dashboard_link(self):
        content = _read_sessions()
        assert 'href="/dashboard"' in content, \
            "Breadcrumb must link to /dashboard"

    @pytest.mark.contract_case("UI-SESSIONS-001", "UI-SESSIONS-017")
    def test_breadcrumb_has_current(self):
        content = _read_sessions()
        assert 'class="current"' in content, \
            "Breadcrumb must have current page indicator"
