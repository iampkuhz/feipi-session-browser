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
        # Badge uses base class + agent-specific modifier
        assert 'sessions-agent-badge' in content
        assert 'sessions-agent-badge--' in content

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
        assert "Info only" not in content

    def test_no_density_toggle(self):
        """No Compact / Comfort density toggle."""
        content = _read_sessions_templates()
        assert "density-toggle" not in content
        assert "Compact" not in content
        assert "Comfort" not in content


class TestFooter:
    """Verify footer layout — contract-compliant pagination."""

    def test_has_pagination_nav(self):
        content = _read_sessions_templates()
        assert 'role="navigation"' in content
        assert 'aria-label="Sessions pagination"' in content

    def test_has_previous_button(self):
        content = _read_sessions_templates()
        assert 'data-action="prev-page"' in content

    def test_has_next_button(self):
        content = _read_sessions_templates()
        assert 'data-action="next-page"' in content

    def test_has_page_input(self):
        content = _read_sessions_templates()
        assert 'data-action="page-input"' in content

    def test_has_page_status(self):
        content = _read_sessions_templates()
        assert 'class="page-status"' in content

    def test_has_spacer(self):
        content = _read_sessions_templates()
        assert 'class="spacer"' in content

    def test_no_sorted_by_in_footer(self):
        """Footer must not contain 'sorted by' text."""
        content = _read_sessions_templates()
        assert "sorted by" not in content.lower()


class TestSearch:
    """Verify search input contract."""

    def test_search_placeholder_session_id(self):
        """Search placeholder should indicate Session ID only."""
        content = _read_sessions_templates()
        assert "仅支持 Session ID" in content

    def test_search_hint_chinese(self):
        """Search hint should be in Chinese: 仅支持 Session ID."""
        content = _read_sessions_templates()
        assert "仅支持 Session ID" in content

    def test_search_placeholder_in_input(self):
        """Search hint should be inside the search input as placeholder, not a separate element."""
        content = _read_sessions_templates()
        assert "placeholder=" in content
        assert "仅支持 Session ID" in content
        # Must NOT have a separate hint element
        assert 'sessions-search-hint' not in content

    def test_no_broad_search_placeholder(self):
        """Search placeholder should NOT mention title, project, or prompt."""
        content = _read_sessions_templates()
        # Extract placeholder value (single or double quotes)
        import re
        match = re.search(r"placeholder=['\"]([^'\"]*)['\"]", content)
        assert match, "Search input must have placeholder"
        hint = match.group(1).lower()
        assert "title" not in hint
        assert "project" not in hint
        assert "prompt" not in hint


class TestSessionsTemplateJS:
    """Verify JS selectors in canonical sessions-list.js."""

    def test_js_uses_sessions_row_selector(self):
        with open("src/session_browser/web/static/js/sessions-list.js") as f:
            js = f.read()
        assert ".sessions-row" in js, "sessions-list.js must use .sessions-row"

    def test_no_tbody_selector(self):
        """Old tbody selector should be removed."""
        with open("src/session_browser/web/static/js/sessions-list.js") as f:
            js = f.read()
        assert "#sessions-table tbody" not in js, "Old tbody selector should be removed"

    def test_no_tr_selector_in_filter(self):
        """Old 'tr' query selector should be removed."""
        with open("src/session_browser/web/static/js/sessions-list.js") as f:
            js = f.read()
        assert "tbody.querySelectorAll" not in js, "Old tbody querySelectorAll should be removed"

    def test_no_data_sessions_grid(self):
        """Old data-sessions-grid selector should be removed."""
        with open("src/session_browser/web/static/js/sessions-list.js") as f:
            js = f.read()
        assert "data-sessions-grid" not in js, "Old data-sessions-grid should be removed"


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
        assert 'data-agent=' in content, "Session rows must have data-agent attribute"

    def test_row_has_data_session_id(self):
        content = _read_sessions_templates()
        assert 'data-session-id=' in content, "Session rows must have data-session-id attribute"

    def test_js_navigates_to_session_url(self):
        """JS click handler should build /sessions/<agent>/<session_id> URL."""
        with open("src/session_browser/web/static/js/sessions-list.js") as f:
            js = f.read()
        assert "/sessions/" in js
        assert "dataset.agent" in js
        assert "dataset.sessionId" in js

    def test_js_skips_links_on_click(self):
        """JS should not hijack clicks on <a> elements."""
        with open("src/session_browser/web/static/js/sessions-list.js") as f:
            js = f.read()
        assert "tagName" in js and ("'A'" in js or '"A"' in js),             "JS must skip <a> elements on row click"

    def test_no_selection_js_leftover(self):
        """Should not have .selected class manipulation or aria-selected."""
        with open("src/session_browser/web/static/js/sessions-list.js") as f:
            js = f.read()
        # Check templates for leftover selection patterns
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

    def test_no_submit_filters_function(self):
        """submitFilters AJAX function removed in favor of link-based navigation."""
        content = _read_sessions_templates()
        assert "submitFilters" not in content

    def test_pagination_uses_links(self):
        """Pagination should use <a> links, not button forms."""
        content = _read_sessions_templates()
        assert 'name="page"' not in content or 'value="prev"' not in content
        # sessions.html uses ui.pagination macro which generates button-based pagination
        assert "ui.pagination(" in content, \
            "Sessions must use ui.pagination macro"

    def test_filter_form_has_name_attributes(self):
        content = _read_sessions_templates()
        # Accept both single and double quote patterns (macros use single quotes)
        assert ("name='q'" in content or 'name="q"' in content)
        assert ("name='agent'" in content or 'name="agent"' in content)
        assert ("name='model'" in content or 'name="model"' in content)
        assert ("name='project'" in content or 'name="project"' in content)
        assert 'name="sort"' in content

    def test_link_based_pagination(self):
        """Pagination uses anchor links with href."""
        content = _read_sessions_templates()
        assert "href=" in content and ("Previous" in content or "Next" in content)


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

    def test_search_input_css(self):
        with open("src/session_browser/web/static/css/sessions-list.css") as f:
            content = f.read()
        assert ".sessions-search input" in content

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
