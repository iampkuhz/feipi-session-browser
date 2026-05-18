"""Tests for Sessions page grid — HIFI v4 componentized layout."""

from __future__ import annotations

import os
import pytest

from session_browser.web.routes import _display_path

# Grid content is in the main template and the partial.
_TEMPLATE_PATH = "src/session_browser/web/templates/sessions.html"
_PARTIAL_PATH = "src/session_browser/web/templates/partials/sessions_grid.html"
_UI_PRIMITIVES_PATH = "src/session_browser/web/templates/components/ui_primitives.html"
_SL_COMPONENTS_PATH = "src/session_browser/web/templates/components/sessions_list_components.html"


def _read_sessions_templates():
    """Read sessions.html, its grid partial, and component macros, return combined content."""
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
    """Verify sessions.html has the correct 9-column grid headers."""

    def test_has_title_column(self):
        content = _read_sessions_templates()
        assert "th_static('Title')" in content

    def test_has_project_column(self):
        content = _read_sessions_templates()
        assert "th_static('Project')" in content

    def test_has_agent_column(self):
        content = _read_sessions_templates()
        assert "th_static('Agent')" in content

    def test_has_model_column(self):
        content = _read_sessions_templates()
        assert "th_static('Model')" in content

    def test_has_tokens_column(self):
        content = _read_sessions_templates()
        assert "th_sort('Tokens'" in content

    def test_has_rounds_column(self):
        content = _read_sessions_templates()
        assert "th_sort('Rounds'" in content

    def test_has_tools_column(self):
        content = _read_sessions_templates()
        assert "th_sort('Tools'" in content

    def test_has_duration_column(self):
        content = _read_sessions_templates()
        assert "th_sort('Duration'" in content

    def test_has_updated_column(self):
        content = _read_sessions_templates()
        assert "th_sort('Updated'" in content


class TestSessionsTemplateRemovedColumns:
    """Verify old table columns are no longer present in grid."""

    def test_no_failures_column(self):
        content = _read_sessions_templates()
        assert "<div>Failures</div>" not in content
        assert '<div class="th" role="columnheader">Failures</div>' not in content

    def test_no_output_column(self):
        content = _read_sessions_templates()
        assert "<div>Output</div>" not in content

    def test_no_msgs_column(self):
        content = _read_sessions_templates()
        assert "<div>Msgs</div>" not in content

    def test_no_cache_r_column(self):
        content = _read_sessions_templates()
        assert ">Cache R</th>" not in content
        assert '<div class="th" role="columnheader">Cache R</div>' not in content

    def test_no_cache_w_column(self):
        content = _read_sessions_templates()
        assert ">Cache W</th>" not in content
        assert '<div class="th" role="columnheader">Cache W</div>' not in content

    def test_no_output_percent_column(self):
        content = _read_sessions_templates()
        assert ">Output%</th>" not in content

    def test_no_signals_column(self):
        content = _read_sessions_templates()
        assert "<div>Signals</div>" not in content

    def test_no_hero(self):
        """No hero section in sessions list page."""
        content = _read_sessions_templates()
        assert "hero" not in content.lower()


class TestSessionsTemplateGridStructure:
    """Verify the new div-based grid structure."""

    def test_has_data_sessions_grid(self):
        content = _read_sessions_templates()
        assert "data-sessions-grid" in content

    def test_has_sessions_row(self):
        content = _read_sessions_templates()
        assert "sessions-row" in content

    def test_has_sessions_title(self):
        content = _read_sessions_templates()
        assert 'class="sessions-title"' in content

    def test_has_sessions_meta(self):
        content = _read_sessions_templates()
        assert 'class="sessions-meta"' in content

    def test_has_sessions_id(self):
        content = _read_sessions_templates()
        assert 'class="sessions-id"' in content

    def test_has_agent_badge(self):
        content = _read_sessions_templates()
        assert 'class="sessions-agent-badge"' in content

    def test_has_token_bar(self):
        """Token bar should be present in tokens cell."""
        content = _read_sessions_templates()
        assert 'class="sessions-token-bar"' in content

    def test_has_token_total(self):
        content = _read_sessions_templates()
        assert 'class="sessions-token-total"' in content

    def test_no_data_table_enhanced(self):
        """data-table-enhanced attribute should be removed."""
        content = _read_sessions_templates()
        assert "data-table-enhanced" not in content


class TestSortableHeaders:
    """Verify sortable / non-sortable header contract."""

    def test_title_not_sortable(self):
        """Title column should not be sortable."""
        content = _read_sessions_templates()
        assert "th_sort('Title'" not in content

    def test_project_not_sortable(self):
        content = _read_sessions_templates()
        assert "th_sort('Project'" not in content

    def test_agent_not_sortable(self):
        content = _read_sessions_templates()
        assert "th_sort('Agent'" not in content

    def test_model_not_sortable(self):
        content = _read_sessions_templates()
        assert "th_sort('Model'" not in content

    def test_tokens_is_sortable(self):
        content = _read_sessions_templates()
        assert "th_sort('Tokens', 'tokens'" in content

    def test_rounds_is_sortable(self):
        content = _read_sessions_templates()
        assert "th_sort('Rounds', 'rounds'" in content

    def test_tools_is_sortable(self):
        content = _read_sessions_templates()
        assert "th_sort('Tools', 'tools'" in content

    def test_duration_is_sortable(self):
        content = _read_sessions_templates()
        assert "th_sort('Duration', 'duration'" in content

    def test_updated_is_sortable(self):
        content = _read_sessions_templates()
        assert "th_sort('Updated', 'updated'" in content

    def test_five_sortable_headers(self):
        """Exactly 5 sortable header definitions in the table_header macro."""
        content = _read_sessions_templates()
        # Count th_sort calls in the table_header macro body (excluding the macro def line itself)
        assert content.count("ui.th_sort(") == 5

    def test_default_sort_aria(self):
        """Default sort column should have aria-sort set."""
        content = _read_sessions_templates()
        assert "aria-sort" in content

    def test_no_sortable_legend(self):
        """No Sortable / Info only legend in the template."""
        content = _read_sessions_templates()
        assert "legend-sort" not in content
        assert "legend-item" not in content
        assert "Info only" not in content

    def test_no_density_toggle(self):
        """No Compact / Comfort density toggle."""
        content = _read_sessions_templates()
        assert "density-toggle" not in content
        assert "Compact" not in content
        assert "Comfort" not in content


class TestFooter:
    """Verify footer layout."""

    def test_has_table_footer(self):
        content = _read_sessions_templates()
        assert 'class="sessions-table-footer"' in content

    def test_has_previous_button(self):
        content = _read_sessions_templates()
        assert "Previous" in content

    def test_has_next_button(self):
        content = _read_sessions_templates()
        assert "Next" in content

    def test_has_rows_range(self):
        content = _read_sessions_templates()
        assert 'class="sessions-page-range"' in content
        assert "Rows" in content

    def test_has_footer_total(self):
        content = _read_sessions_templates()
        assert 'class="sessions-footer-total"' in content
        assert "matching sessions" in content

    def test_has_footer_spacer(self):
        content = _read_sessions_templates()
        assert 'class="sessions-footer-spacer"' in content

    def test_no_sorted_by_in_footer(self):
        """Footer must not contain 'sorted by' text."""
        content = _read_sessions_templates()
        assert "sorted by" not in content.lower()


class TestSearch:
    """Verify search input contract."""

    def test_search_placeholder_session_id(self):
        content = _read_sessions_templates()
        assert "Search by Session ID" in content

    def test_search_hint_chinese(self):
        """Search hint should be in Chinese: 仅支持 Session ID."""
        content = _read_sessions_templates()
        assert "仅支持 Session ID" in content

    def test_search_hint_class(self):
        content = _read_sessions_templates()
        assert 'class="sessions-search-hint"' in content

    def test_no_broad_search_hint(self):
        """Search hint should NOT mention title, project, or prompt."""
        content = _read_sessions_templates()
        hint_section = content.split('sessions-search-hint')[1].split('<')[0] if 'sessions-search-hint' in content else ""
        assert "title" not in hint_section.lower()
        assert "project" not in hint_section.lower()
        assert "prompt" not in hint_section.lower()


class TestSessionsTemplateJS:
    """Verify JS selectors migrated to grid."""

    def test_js_uses_data_sessions_grid(self):
        content = _read_sessions_templates()
        assert "[data-sessions-grid]" in content

    def test_js_uses_sessions_row_selector(self):
        content = _read_sessions_templates()
        assert ".sessions-row" in content or "sessions-row" in content

    def test_no_tbody_selector(self):
        """Old tbody selector should be removed."""
        content = _read_sessions_templates()
        assert "#sessions-table tbody" not in content

    def test_no_tr_selector_in_filter(self):
        """Old 'tr' query selector should be removed."""
        content = _read_sessions_templates()
        assert "tbody.querySelectorAll" not in content


class TestSessionsListActions:
    """Verify triage action buttons have been removed."""

    def test_no_failed_only_button(self):
        content = _read_sessions_templates()
        assert "Failed only" not in content

    def test_no_high_token_button(self):
        content = _read_sessions_templates()
        assert "High token" not in content

    def test_no_open_selected_button(self):
        content = _read_sessions_templates()
        assert "Open selected" not in content
        assert 'id="open-selected-session"' not in content

    def test_no_top_actions(self):
        """The .top-actions container should not exist."""
        content = _read_sessions_templates()
        assert "top-actions" not in content

    def test_no_toggle_quick_filter_js(self):
        """toggleQuickFilter function should be removed."""
        content = _read_sessions_templates()
        assert "toggleQuickFilter" not in content

    def test_no_open_selected_session_js(self):
        """openSelectedSession function should be removed."""
        content = _read_sessions_templates()
        assert "openSelectedSession" not in content


class TestSessionsListRowClick:
    """Verify session row click navigates to detail page."""

    def test_row_has_data_agent(self):
        content = _read_sessions_templates()
        assert 'data-agent="{{ s.agent }}"' in content

    def test_row_has_data_session_id(self):
        content = _read_sessions_templates()
        assert 'data-session-id="{{ s.session_id }}"' in content

    def test_js_navigates_to_session_url(self):
        """JS click handler should build /sessions/<agent>/<session_id> URL."""
        content = _read_sessions_templates()
        assert "/sessions/" in content
        assert "row.dataset.agent" in content
        assert "row.dataset.sessionId" in content

    def test_js_skips_links_on_click(self):
        """JS should not hijack clicks on <a> elements."""
        content = _read_sessions_templates()
        assert "tagName === 'A'" in content or 'tagName === "A"' in content

    def test_no_selection_js_leftover(self):
        """Should not have .selected class manipulation or aria-selected."""
        content = _read_sessions_templates()
        assert ".selected" not in content
        assert "aria-selected" not in content
        assert "classList.add('selected')" not in content


class TestDisplayPathFilter:
    """Verify the display_path Jinja filter replaces home prefix with ~."""

    def test_home_path_becomes_tilde(self):
        home = os.path.expanduser("~")
        assert _display_path(home) == "~"

    def test_sub_home_path_becomes_tilde_slash(self):
        home = os.path.expanduser("~")
        result = _display_path(f"{home}/Documents/tools/feipi")
        assert result == "~/Documents/tools/feipi"

    def test_non_home_path_unchanged(self):
        assert _display_path("/opt/local/project") == "/opt/local/project"

    def test_empty_string_unchanged(self):
        assert _display_path("") == ""

    def test_none_returns_empty_string(self):
        assert _display_path(None) == ""

    def test_data_project_keeps_raw_path(self):
        """data-project attribute must retain the original project_key."""
        content = _read_sessions_templates()
        assert 'data-project="{{ s.project_key }}"' in content


class TestProjectColumn:
    """Verify Project column rendering."""

    def test_project_cell_has_project_name_class(self):
        content = _read_sessions_templates()
        assert 'sessions-project-name' in content

    def test_project_link_href_uses_urlencode(self):
        content = _read_sessions_templates()
        assert 'href="/projects/{{ s.project_key | urlencode }}"' in content

    def test_project_link_uses_project_name(self):
        content = _read_sessions_templates()
        assert '{{ s.project_name }}' in content


class TestPaginationTemplate:
    """Verify pagination-related template changes."""

    def test_no_client_side_apply_filters(self):
        """Old client-side applyFilters should be removed."""
        content = _read_sessions_templates()
        assert "function applyFilters()" not in content

    def test_submit_filters_function(self):
        content = _read_sessions_templates()
        assert "submitFilters" in content

    def test_go_to_page_function(self):
        content = _read_sessions_templates()
        assert "goToPage" in content

    def test_filter_form_has_name_attributes(self):
        content = _read_sessions_templates()
        assert 'name="q"' in content
        assert 'name="agent"' in content
        assert 'name="model"' in content
        assert 'name="project"' in content
        assert 'name="sort"' in content

    def test_disabled_attribute_on_prev(self):
        content = _read_sessions_templates()
        assert "{% if not has_prev %}disabled{% endif %}" in content

    def test_disabled_attribute_on_next(self):
        content = _read_sessions_templates()
        assert "{% if not has_next %}disabled{% endif %}" in content


class TestCSS:
    """Verify CSS selectors for HIFI v4."""

    def test_sessions_grid_css(self):
        with open("src/session_browser/web/static/css/sessions-list.css") as f:
            content = f.read()
        assert ".sessions-grid" in content

    def test_table_footer_css(self):
        with open("src/session_browser/web/static/css/sessions-list.css") as f:
            content = f.read()
        assert ".sessions-table-footer" in content

    def test_search_hint_css(self):
        with open("src/session_browser/web/static/css/sessions-list.css") as f:
            content = f.read()
        assert ".sessions-search-hint" in content

    def test_sessions_title_css(self):
        with open("src/session_browser/web/static/css/sessions-list.css") as f:
            content = f.read()
        assert ".sessions-title" in content

    def test_sessions_meta_css(self):
        with open("src/session_browser/web/static/css/sessions-list.css") as f:
            content = f.read()
        assert ".sessions-meta" in content

    def test_token_bar_css(self):
        with open("src/session_browser/web/static/css/sessions-list.css") as f:
            content = f.read()
        assert ".sessions-token-bar" in content

    def test_sort_icon_css(self):
        with open("src/session_browser/web/static/css/sessions-list.css") as f:
            content = f.read()
        assert ".sessions-sort-icon" in content

    def test_project_name_css(self):
        with open("src/session_browser/web/static/css/sessions-list.css") as f:
            content = f.read()
        assert ".sessions-project-name" in content
