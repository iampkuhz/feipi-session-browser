"""Page-specific sessions list tests for sessions.html.

Verifies the Jinja2 template structure, CSS/JS imports, filter bar,
data table with sortable headers, token bar rendering, pagination,
empty states, and absence of inline onclick.

T080 — Sessions List page-specific pytest.
"""

from __future__ import annotations

import os
import re

import pytest

_SESSIONS_PATH = "src/session_browser/web/templates/sessions.html"
_SESSIONS_CSS_PATH = "src/session_browser/web/static/css/sessions-list.css"
_SESSIONS_JS_PATH = "src/session_browser/web/static/js/sessions-list.js"


def _read(path: str) -> str:
    with open(path) as f:
        return f.read()


def _read_sessions() -> str:
    return _read(_SESSIONS_PATH)


# ── TestSessionsTemplate ─────────────────────────────────────────────

class TestSessionsTemplate:
    """Verify the sessions Jinja2 template renders structurally."""

    def test_template_file_exists(self):
        assert os.path.isfile(_SESSIONS_PATH), \
            f"{_SESSIONS_PATH} must exist"

    def test_extends_base(self):
        content = _read_sessions()
        assert '{% extends "base.html" %}' in content, \
            "Sessions must extend base.html"

    def test_active_page_set(self):
        content = _read_sessions()
        assert "active_page = 'sessions'" in content, \
            "Sessions must set active_page = 'sessions'"

    def test_ui_primitives_imported(self):
        content = _read_sessions()
        assert 'import "components/ui_primitives.html"' in content, \
            "Sessions must import ui_primitives.html"

    def test_no_inline_onclick(self):
        """Sessions must not use inline onclick handlers."""
        content = _read_sessions()
        matches = re.findall(r'\bonclick\s*=', content, re.IGNORECASE)
        assert len(matches) == 0, \
            f"Sessions must not have inline onclick, found {len(matches)} occurrences"


# ── TestSessionsImports ──────────────────────────────────────────────

class TestSessionsImports:
    """Verify CSS and JS import statements."""

    def test_css_import_sessions_list_css(self):
        content = _read_sessions()
        assert 'href="/static/css/sessions-list.css"' in content, \
            "Sessions must import sessions-list.css"

    def test_css_import_ui_primitives_css(self):
        content = _read_sessions()
        assert 'href="/static/css/ui-primitives.css"' in content, \
            "Sessions must import ui-primitives.css"

    def test_js_import_sessions_list_js(self):
        content = _read_sessions()
        assert 'src="/static/js/sessions-list.js"' in content, \
            "Sessions must import sessions-list.js"

    def test_js_import_ui_primitives_js(self):
        content = _read_sessions()
        assert 'src="/static/js/ui_primitives.js"' in content, \
            "Sessions must import ui_primitives.js"

    def test_css_file_exists_on_disk(self):
        assert os.path.isfile(_SESSIONS_CSS_PATH), \
            "sessions-list.css must exist on disk"

    def test_js_file_exists_on_disk(self):
        assert os.path.isfile(_SESSIONS_JS_PATH), \
            "sessions-list.js must exist on disk"


# ── TestSessionsPageHead ─────────────────────────────────────────────

class TestSessionsPageHead:
    """Verify page-head structure."""

    def test_page_head_section_present(self):
        content = _read_sessions()
        assert 'class="page-head"' in content, \
            "Sessions must have a page-head section"

    def test_page_head_has_h1(self):
        content = _read_sessions()
        assert "<h1>Sessions</h1>" in content, \
            "Page-head must contain <h1>Sessions</h1>"

    def test_page_head_has_subtitle(self):
        content = _read_sessions()
        assert "Browse indexed local agent runs" in content, \
            "Page-head must have subtitle about browsing sessions"


# ── TestSessionsFilterBar ────────────────────────────────────────────

class TestSessionsFilterBar:
    """Verify filter row with search + dropdowns."""

    def test_filter_form_exists(self):
        content = _read_sessions()
        assert 'id="session-filter-form"' in content, \
            "Sessions must have a filter form"

    def test_search_input(self):
        content = _read_sessions()
        assert 'id="session-search"' in content, \
            "Filter bar must have search input"
        assert 'data-search="session-id"' in content, \
            "Search input must have data-search attribute"

    def test_agent_dropdown(self):
        content = _read_sessions()
        assert 'id="filter-agent"' in content, \
            "Filter bar must have agent dropdown"
        assert "All Agents" in content, \
            "Agent dropdown must have 'All Agents' default"
        assert "claude_code" in content, \
            "Agent dropdown must have claude_code option"
        assert "codex" in content, \
            "Agent dropdown must have codex option"
        assert "qoder" in content, \
            "Agent dropdown must have qoder option"

    def test_model_dropdown(self):
        content = _read_sessions()
        assert 'id="filter-model"' in content, \
            "Filter bar must have model dropdown"
        assert "All Models" in content, \
            "Model dropdown must have 'All Models' default"

    def test_project_dropdown(self):
        content = _read_sessions()
        assert 'id="filter-project"' in content, \
            "Filter bar must have project dropdown"
        assert "All Projects" in content, \
            "Project dropdown must have 'All Projects' default"

    def test_apply_button(self):
        content = _read_sessions()
        assert "data_action='apply'" in content, \
            "Filter bar must have apply button with data_action"
        assert "'Apply'" in content, \
            "Apply button text must be present as macro argument"

    def test_clear_all_button_conditional(self):
        content = _read_sessions()
        assert "filter_q or filter_agent or filter_model or filter_project" in content, \
            "Clear All button must be conditional on active filters"
        assert "data_action='clear'" in content, \
            "Clear All must use data_action='clear'"


# ── TestSessionsDataTable ────────────────────────────────────────────

class TestSessionsDataTable:
    """Verify data table with sortable headers."""

    def test_data_table_present(self):
        content = _read_sessions()
        assert 'class="data-table"' in content, \
            "Sessions must have a data-table"
        assert 'role="table"' in content, \
            "Data table must have role='table'"

    def test_table_headers(self):
        content = _read_sessions()
        for header in ["Title", "Project", "Agent", "Model", "Tokens", "Rounds", "Tools", "Duration", "Updated"]:
            assert header in content, \
                f"Table must have '{header}' column header"

    def test_sortable_columns(self):
        content = _read_sessions()
        sortable = re.findall(r'class="num sortable"', content)
        # Tokens, Rounds, Tools are num sortable
        assert len(sortable) >= 3, \
            f"Must have at least 3 sortable columns, found {len(sortable)}"

    def test_sort_buttons_with_data_action(self):
        content = _read_sessions()
        sort_buttons = re.findall(r'data-action="sort"', content)
        assert len(sort_buttons) >= 4, \
            f"Must have at least 4 sort buttons, found {len(sort_buttons)}"

    def test_sort_icons_present(self):
        content = _read_sessions()
        assert 'class="sort-icon"' in content, \
            "Sort buttons must have sort-icon class"

    def test_static_headers(self):
        content = _read_sessions()
        static = re.findall(r'class="static-header"', content)
        assert len(static) >= 3, \
            f"Must have at least 3 static (non-sortable) headers, found {len(static)}"

    def test_aria_sort_on_active(self):
        content = _read_sessions()
        assert 'aria-sort=' in content, \
            "Active sort button must have aria-sort attribute"


# ── TestSessionsTokenBar ─────────────────────────────────────────────

class TestSessionsTokenBar:
    """Verify token bar rendering in token column."""

    def test_token_cell_class(self):
        content = _read_sessions()
        assert 'class="token-cell"' in content, \
            "Must have token-cell class"

    def test_token_total_value(self):
        content = _read_sessions()
        assert 'class="token-total__value"' in content, \
            "Must have token-total__value display"
        assert "format_compact_token" in content, \
            "Token value must use format_compact_token filter"

    def test_tokenbar_container(self):
        content = _read_sessions()
        assert 'class="tokenbar"' in content, \
            "Must have tokenbar container"

    def test_tokenbar_segments(self):
        content = _read_sessions()
        for seg_class in ["tokenbar-seg fresh", "tokenbar-seg read", "tokenbar-seg write", "tokenbar-seg out"]:
            assert seg_class in content, \
                f"Tokenbar must have segment: {seg_class}"

    def test_tokenbar_has_four_segments(self):
        content = _read_sessions()
        segments = re.findall(r'class="tokenbar-seg ', content)
        assert len(segments) == 4, \
            f"Tokenbar must have 4 segments, found {len(segments)}"


# ── TestSessionsPagination ───────────────────────────────────────────

class TestSessionsPagination:
    """Verify pagination prev/input/next structure."""

    def test_pagination_nav_present(self):
        content = _read_sessions()
        assert 'class="pagination' in content, \
            "Sessions must have pagination nav"
        assert 'role="navigation"' in content, \
            "Pagination must have role='navigation'"

    def test_prev_button(self):
        content = _read_sessions()
        assert 'data-action="prev-page"' in content, \
            "Pagination must have prev-page button"

    def test_page_input(self):
        content = _read_sessions()
        assert 'data-action="page-input"' in content, \
            "Pagination must have page-input field"
        assert 'class="page-input' in content, \
            "Page input must have page-input class"

    def test_next_button(self):
        content = _read_sessions()
        assert 'data-action="next-page"' in content, \
            "Pagination must have next-page button"

    def test_page_status(self):
        content = _read_sessions()
        assert 'class="page-status"' in content, \
            "Pagination must have page-status spans"

    def test_pagination_conditional(self):
        content = _read_sessions()
        assert "total_count > 0" in content, \
            "Pagination must only render when total_count > 0"


# ── TestSessionsEmptyState ───────────────────────────────────────────

class TestSessionsEmptyState:
    """Verify empty state rendering."""

    def test_empty_state_condition(self):
        content = _read_sessions()
        assert "{% if has_active_filter %}" in content or \
               "{% if has_active_filter" in content or \
               "has_active_filter" in content, \
            "Sessions must check for active filter in empty state"

    def test_empty_state_uses_ui_macro(self):
        content = _read_sessions()
        assert "ui.empty_state" in content, \
            "Empty state must use ui.empty_state macro"

    def test_filtered_empty_message(self):
        content = _read_sessions()
        assert "No sessions match your current filters" in content, \
            "Must show message for filtered empty state"

    def test_true_empty_message(self):
        content = _read_sessions()
        assert "No sessions indexed yet" in content, \
            "Must show message for true empty state"

    def test_filtered_empty_has_clear_button(self):
        content = _read_sessions()
        assert "Clear All Filters" in content, \
            "Filtered empty state must have clear filters button"


# ── TestSessionsRowData ──────────────────────────────────────────────

class TestSessionsRowData:
    """Verify data attributes on session rows."""

    def test_row_data_action(self):
        content = _read_sessions()
        assert 'data-action="row"' in content, \
            "Session rows must have data-action='row'"

    def test_row_data_attributes(self):
        content = _read_sessions()
        for attr in ["data-agent", "data-model", "data-project", "data-session-id"]:
            assert attr in content, \
                f"Session row must have {attr}"

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

    def test_breadcrumb_has_dashboard_link(self):
        content = _read_sessions()
        assert 'href="/dashboard"' in content, \
            "Breadcrumb must link to /dashboard"

    def test_breadcrumb_has_current(self):
        content = _read_sessions()
        assert 'class="current"' in content, \
            "Breadcrumb must have current page indicator"
