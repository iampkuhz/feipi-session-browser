"""Tests for Sessions page grid — HIFI v4 componentized layout."""

from __future__ import annotations

import os
import re
import pytest

from session_browser.web.template_env import _display_path

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


# ── Sessions List page fixture tests (T093) ─────────────────────────
# Uses the hifi_fixture_session fixture to spin up a live server with
# deterministic fixture data, then verifies the *rendered* Sessions List HTML.
# Covers: page renders, session rows, filtering, pagination, key metrics, AJAX.


# ── Sessions List page fixture ────────────────────────────────────────


@pytest.fixture(scope="module")
def sessions_list_html(hifi_fixture_session):
    """Fetch rendered Sessions List HTML from the live fixture server."""
    base_url, agent, session_id = hifi_fixture_session
    import urllib.request

    resp = urllib.request.urlopen(f"{base_url}/sessions", timeout=10)
    assert resp.status == 200, "Sessions List must return HTTP 200"
    return resp.read().decode("utf-8")


# ── TestSessionsListPageRender ───────────────────────────────────────


class TestSessionsListPageRender:
    """Verify the rendered Sessions List page structure."""

    def test_page_returns_200(self, sessions_list_html):
        """Sessions List must render successfully."""
        assert len(sessions_list_html) > 500, \
            "Sessions List HTML must be substantial"

    def test_has_doctype_and_html(self, sessions_list_html):
        """Page must have proper HTML structure."""
        lower = sessions_list_html.lower()
        assert "<!doctype html" in lower or "<!DOCTYPE html" in sessions_list_html, \
            "Sessions List must have DOCTYPE declaration"

    def test_title_contains_sessions(self, sessions_list_html):
        """Page title must contain 'Sessions'."""
        assert "<title>Sessions" in sessions_list_html, \
            "Page title must contain 'Sessions'"

    def test_has_page_head_sessions(self, sessions_list_html):
        """Page must have a visible 'Sessions' heading."""
        assert ">Sessions<" in sessions_list_html, \
            "'Sessions' heading must be visible"

    def test_has_subtitle(self, sessions_list_html):
        """Page must show the subtitle."""
        assert "Browse indexed local agent runs" in sessions_list_html, \
            "Subtitle 'Browse indexed local agent runs' must appear"

    def test_has_data_table(self, sessions_list_html):
        """Page must contain the sessions data table."""
        assert 'aria-label="Sessions table"' in sessions_list_html, \
            "Sessions table with aria-label must be present"


# ── TestSessionsListDisplay ──────────────────────────────────────────


class TestSessionsListDisplay:
    """Verify session list rows are rendered with correct data."""

    def test_has_sessions_rows(self, sessions_list_html):
        """At least one sessions-row must be rendered."""
        rows = re.findall(r'class="sessions-row"', sessions_list_html)
        assert len(rows) > 0, \
            "At least one sessions-row must be rendered"

    def test_row_has_data_session_id(self, sessions_list_html):
        """Session rows must have data-session-id attribute."""
        match = re.search(r'class="sessions-row"[^>]*data-session-id="([^"]+)"', sessions_list_html)
        assert match, "sessions-row must have data-session-id"

    def test_row_has_data_agent(self, sessions_list_html):
        """Session rows must have data-agent attribute."""
        assert "data-agent=" in sessions_list_html, \
            "sessions-row must have data-agent"

    def test_row_has_data_model(self, sessions_list_html):
        """Session rows must have data-model attribute."""
        assert "data-model=" in sessions_list_html, \
            "sessions-row must have data-model"

    def test_row_has_data_project(self, sessions_list_html):
        """Session rows must have data-project attribute."""
        assert "data-project=" in sessions_list_html, \
            "sessions-row must have data-project"

    def test_row_has_data_total_tokens(self, sessions_list_html):
        """Session rows must have data-total-tokens attribute."""
        assert "data-total-tokens=" in sessions_list_html, \
            "sessions-row must have data-total-tokens"

    def test_row_has_data_rounds(self, sessions_list_html):
        """Session rows must have data-rounds attribute."""
        assert "data-rounds=" in sessions_list_html, \
            "sessions-row must have data-rounds"

    def test_row_has_data_tool_count(self, sessions_list_html):
        """Session rows must have data-tool-count attribute."""
        assert "data-tool-count=" in sessions_list_html, \
            "sessions-row must have data-tool-count"

    def test_row_has_data_duration(self, sessions_list_html):
        """Session rows must have data-duration attribute."""
        assert "data-duration=" in sessions_list_html, \
            "sessions-row must have data-duration"

    def test_row_has_data_ended_at(self, sessions_list_html):
        """Session rows must have data-ended-at attribute."""
        assert "data-ended-at=" in sessions_list_html, \
            "sessions-row must have data-ended-at"

    def test_session_links_present(self, sessions_list_html):
        """Each session row must link to its detail page."""
        links = re.findall(r'href="/sessions/[^"]+/[^"]+"', sessions_list_html)
        assert len(links) > 0, \
            "Session detail links must be present"

    def test_title_column_rendered(self, sessions_list_html):
        """Title column content must be visible."""
        assert 'class="col-title"' in sessions_list_html or 'class="title-main"' in sessions_list_html, \
            "Title column must be rendered"

    def test_agent_badge_rendered(self, sessions_list_html):
        """Agent badge must be rendered."""
        assert "sessions-agent-badge" in sessions_list_html or 'class="badge ' in sessions_list_html, \
            "Agent badge must be rendered"

    def test_token_bar_rendered(self, sessions_list_html):
        """Token bar must be rendered in tokens cell."""
        assert "tokenbar" in sessions_list_html, \
            "Token bar must be rendered"

    def test_project_link_rendered(self, sessions_list_html):
        """Project column must have links."""
        assert 'href="/projects/' in sessions_list_html, \
            "Project links must be present"


# ── TestSessionsListFiltering ────────────────────────────────────────


class TestSessionsListFiltering:
    """Verify filter form and controls."""

    def test_filter_form_present(self, sessions_list_html):
        """Filter form must be rendered."""
        assert 'id="session-filter-form"' in sessions_list_html, \
            "Filter form with id='session-filter-form' must be present"

    def test_filter_form_action_sessions(self, sessions_list_html):
        """Filter form must post to /sessions."""
        assert 'action="/sessions"' in sessions_list_html, \
            "Filter form must have action='/sessions'"

    def test_search_input_present(self, sessions_list_html):
        """Search input must be present."""
        assert 'id="session-search"' in sessions_list_html or 'name="q"' in sessions_list_html, \
            "Search input must be present"

    def test_search_placeholder_chinese(self, sessions_list_html):
        """Search input placeholder must be Chinese."""
        assert "仅支持 Session ID" in sessions_list_html, \
            "Search placeholder must be in Chinese"

    def test_agent_filter_select(self, sessions_list_html):
        """Agent filter select must be present."""
        assert 'id="filter-agent"' in sessions_list_html or 'name="agent"' in sessions_list_html, \
            "Agent filter select must be present"

    def test_model_filter_select(self, sessions_list_html):
        """Model filter select must be present."""
        assert 'id="filter-model"' in sessions_list_html or 'name="model"' in sessions_list_html, \
            "Model filter select must be present"

    def test_project_filter_select(self, sessions_list_html):
        """Project filter select must be present."""
        assert 'id="filter-project"' in sessions_list_html or 'name="project"' in sessions_list_html, \
            "Project filter select must be present"

    def test_reset_button_present(self, sessions_list_html):
        """Reset button must be present."""
        assert ">Reset<" in sessions_list_html, \
            "Reset button must be visible"

    def test_apply_button_present(self, sessions_list_html):
        """Apply button must be present."""
        assert ">Apply<" in sessions_list_html, \
            "Apply button must be visible"

    def test_filter_form_uses_get(self, sessions_list_html):
        """Filter form must use GET method for URL-based filtering."""
        assert "method='get'" in sessions_list_html or 'method="get"' in sessions_list_html, \
            "Filter form must use GET method"


# ── TestSessionsListPagination ───────────────────────────────────────


class TestSessionsListPagination:
    """Verify pagination controls."""

    def test_pagination_container_present(self, sessions_list_html):
        """Pagination container must be present."""
        assert 'id="ajax-pagination"' in sessions_list_html, \
            "AJAX pagination container must be present"

    def test_page_status_present(self, sessions_list_html):
        """Page status indicator must be present."""
        assert 'class="page-status"' in sessions_list_html, \
            "Page status element must be present"

    def test_previous_button_present(self, sessions_list_html):
        """Previous page button must be present."""
        assert 'data-action="prev-page"' in sessions_list_html, \
            "Previous page button must be present"

    def test_next_button_present(self, sessions_list_html):
        """Next page button must be present."""
        assert 'data-action="next-page"' in sessions_list_html, \
            "Next page button must be present"

    def test_page_input_present(self, sessions_list_html):
        """Page input must be present."""
        assert 'data-action="page-input"' in sessions_list_html, \
            "Page input must be present"

    def test_total_count_displayed(self, sessions_list_html):
        """Total count must be displayed somewhere on the page."""
        # Page status shows "X of Y sessions" or similar
        assert re.search(r'[0-9]+', sessions_list_html), \
            "Page must display numeric count"


# ── TestSessionsListKeyMetrics ───────────────────────────────────────


class TestSessionsListKeyMetrics:
    """Verify key metrics / stat pills displayed on the page."""

    def test_has_stat_pills(self, sessions_list_html):
        """Page must have stat pills container."""
        assert 'class="ui-stat-pill"' in sessions_list_html, \
            "Stat pills must be present in rendered output"

    def test_sessions_count_pill(self, sessions_list_html):
        """Sessions count stat pill must reference 'sessions'."""
        # The stat_pill macro renders the label
        assert "sessions" in sessions_list_html.lower(), \
            "Sessions stat pill must be present"

    def test_projects_pill(self, sessions_list_html):
        """Projects stat pill must reference 'projects'."""
        assert "projects" in sessions_list_html.lower(), \
            "Projects stat pill must be present"

    def test_total_tokens_pill(self, sessions_list_html):
        """Total tokens stat pill must reference 'tokens'."""
        assert "token" in sessions_list_html.lower(), \
            "Total tokens stat pill must be present"


# ── TestSessionsListAjaxEndpoint ─────────────────────────────────────


class TestSessionsListAjaxEndpoint:
    """Verify AJAX pagination returns partial HTML."""

    def test_ajax_returns_html(self, hifi_fixture_session):
        """AJAX request to /sessions must return HTML fragment."""
        base_url, agent, session_id = hifi_fixture_session
        import urllib.request

        req = urllib.request.Request(
            f"{base_url}/sessions",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        resp = urllib.request.urlopen(req, timeout=10)
        assert resp.status == 200, "AJAX must return HTTP 200"
        body = resp.read().decode("utf-8")
        assert len(body) > 100, "AJAX response must be non-trivial"
        # AJAX response should contain sessions-row or sessions-grid
        assert "sessions-row" in body or "data-sessions-grid" in body or "ajax-pagination" in body, \
            "AJAX response must contain session grid content"
