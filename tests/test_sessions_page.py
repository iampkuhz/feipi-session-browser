"""Tests for Sessions page grid restructure."""

from __future__ import annotations

import os
import pytest

from session_browser.web.routes import _display_path

# Grid content is now in the partial template; combine both for selector checks.
_TEMPLATE_PATH = "src/session_browser/web/templates/sessions.html"
_PARTIAL_PATH = "src/session_browser/web/templates/partials/sessions_grid.html"


def _read_sessions_templates():
    """Read sessions.html and its grid partial, return combined content."""
    with open(_TEMPLATE_PATH) as f:
        main = f.read()
    with open(_PARTIAL_PATH) as f:
        partial = f.read()
    return main + "\n" + partial


class TestSessionsTemplateColumns:
    """Verify sessions.html has the correct restructured 8-column grid headers."""

    def test_has_session_column(self):
        content = _read_sessions_templates()
        assert "<div>Session</div>" in content

    def test_has_project_column(self):
        content = _read_sessions_templates()
        assert "<div>Project</div>" in content

    def test_has_agent_column(self):
        content = _read_sessions_templates()
        assert "<div>Agent</div>" in content

    def test_has_tokens_column(self):
        content = _read_sessions_templates()
        assert "Tokens" in content

    def test_has_duration_column(self):
        content = _read_sessions_templates()
        assert "Duration" in content

    def test_has_failures_column(self):
        content = _read_sessions_templates()
        assert "<div>Failures</div>" in content

    def test_has_rounds_column(self):
        content = _read_sessions_templates()
        assert "Rounds" in content

    def test_has_updated_column(self):
        content = _read_sessions_templates()
        assert "Updated" in content


class TestSessionsTemplateRemovedColumns:
    """Verify old table columns are no longer present in grid."""

    def test_no_table_element(self):
        """No <table> element in the grid area."""
        content = _read_sessions_templates()
        assert "<table" not in content

    def test_no_model_column(self):
        """Model column not in grid (kept as data-*)."""
        content = _read_sessions_templates()
        # Should not have Model as a visible column header
        assert "<div>Model</div>" not in content

    def test_no_anomaly_column(self):
        """Anomaly column not in grid (kept as data-*)."""
        content = _read_sessions_templates()
        assert "<div>Anomaly</div>" not in content

    def test_no_output_column(self):
        content = _read_sessions_templates()
        assert "<div>Output</div>" not in content

    def test_no_tools_column(self):
        content = _read_sessions_templates()
        assert "<div>Tools</div>" not in content

    def test_no_time_column(self):
        content = _read_sessions_templates()
        assert "<div>Time</div>" not in content

    def test_no_standalone_dot_column(self):
        """No empty dot th element."""
        content = _read_sessions_templates()
        assert "class=\"agent-dot" not in content

    def test_no_cache_r_column(self):
        content = _read_sessions_templates()
        assert ">Cache R</th>" not in content

    def test_no_cache_w_column(self):
        content = _read_sessions_templates()
        assert ">Cache W</th>" not in content

    def test_no_output_percent_column(self):
        content = _read_sessions_templates()
        assert ">Output%</th>" not in content

    def test_no_standalone_failed_column(self):
        content = _read_sessions_templates()
        assert ">Failed</th>" not in content

    def test_no_tools_per_round_column(self):
        content = _read_sessions_templates()
        assert ">Tools/R</th>" not in content


class TestSessionsTemplateGridStructure:
    """Verify the new div-based grid structure."""

    def test_has_data_sessions_grid(self):
        content = _read_sessions_templates()
        assert "data-sessions-grid" in content

    def test_has_table_head(self):
        content = _read_sessions_templates()
        assert 'class="table-head"' in content

    def test_has_table_row(self):
        content = _read_sessions_templates()
        assert "table-row" in content

    def test_has_cell_title(self):
        content = _read_sessions_templates()
        assert 'class="cell-title"' in content

    def test_has_cell_sub(self):
        """cell-sub class may exist elsewhere but NOT in Session column."""
        content = _read_sessions_templates()
        # cell-sub must not appear in the Session column (the first <div> after <!-- Session -->)
        # Extract the Session cell block and verify no cell-sub mono
        assert 'class="cell-sub mono"' not in content, \
            "Session column should not contain cell-sub mono for project path"

    def test_has_badge_agent(self):
        content = _read_sessions_templates()
        assert 'class="badge agent"' in content

    def test_has_diag_ok(self):
        content = _read_sessions_templates()
        assert 'class="diag ok"' in content

    def test_has_diag_err(self):
        content = _read_sessions_templates()
        assert 'class="diag err"' in content

    def test_no_data_table_enhanced(self):
        """data-table-enhanced attribute should be removed."""
        content = _read_sessions_templates()
        assert "data-table-enhanced" not in content


class TestSessionsTemplateFailuresMerged:
    """Verify failures column uses diag pills."""

    def test_diag_err_shown_when_failed(self):
        content = _read_sessions_templates()
        assert "diag err" in content

    def test_diag_ok_shown_when_zero(self):
        content = _read_sessions_templates()
        assert "diag ok" in content

    def test_failed_tool_count_used(self):
        content = _read_sessions_templates()
        assert "failed_tool_count" in content


class TestSessionsTemplateDataAttributes:
    """Verify data attributes are preserved and updated."""

    def test_has_total_tokens_data_attr(self):
        content = _read_sessions_templates()
        assert "data-total-tokens=" in content

    def test_has_rounds_data_attr(self):
        content = _read_sessions_templates()
        assert "data-rounds=" in content

    def test_has_data_agent(self):
        content = _read_sessions_templates()
        assert "data-agent=" in content

    def test_has_data_session_id(self):
        content = _read_sessions_templates()
        assert "data-session-id=" in content

    def test_has_data_model(self):
        """Model data retained as data-* attribute."""
        content = _read_sessions_templates()
        assert "data-model=" in content

    def test_has_data_anomaly(self):
        """Anomaly data retained as data-* attributes."""
        content = _read_sessions_templates()
        assert "data-has-anomalies=" in content

    def test_no_cache_data_attrs(self):
        content = _read_sessions_templates()
        assert "data-total-cache-r=" not in content
        assert "data-total-cache-w=" not in content


class TestSessionsTemplateAnomalyData:
    """Verify anomaly info retained in data-* attributes."""

    def test_anomaly_has_data_attribute(self):
        content = _read_sessions_templates()
        assert "data-anomaly-types=" in content

    def test_anomaly_limits_types(self):
        """Should limit anomaly types in data attribute."""
        content = _read_sessions_templates()
        assert "s.anomalies" in content


class TestSessionsTemplateSortOptions:
    """Verify sort-by select has been removed."""

    def test_no_sort_by_select(self):
        content = _read_sessions_templates()
        assert 'id="sort-by"' not in content

    def test_no_sort_select_options(self):
        content = _read_sessions_templates()
        assert "Sort: Last Active" not in content
        assert "Sort: Tokens" not in content
        assert "Sort: Duration" not in content


class TestHeaderSort:
    """Verify clickable header-based sorting."""

    def test_duration_is_sortable(self):
        content = _read_sessions_templates()
        assert 'data-sort-key="duration"' in content
        assert 'th-sortable' in content

    def test_tokens_is_sortable(self):
        content = _read_sessions_templates()
        assert 'data-sort-key="total-tokens"' in content

    def test_rounds_is_sortable(self):
        content = _read_sessions_templates()
        assert 'data-sort-key="rounds"' in content

    def test_updated_is_sortable(self):
        content = _read_sessions_templates()
        assert 'data-sort-key="ended-at"' in content

    def test_updated_has_default_desc(self):
        """Default sort should be Updated descending."""
        content = _read_sessions_templates()
        assert 'aria-sort=' in content
        assert 'descending' in content

    def test_four_sortable_headers(self):
        content = _read_sessions_templates()
        # Count data-sort-key attributes on sortable headers (not plain divs)
        assert content.count('data-sort-key="duration"') == 1
        assert content.count('data-sort-key="total-tokens"') == 1
        assert content.count('data-sort-key="rounds"') == 1
        assert content.count('data-sort-key="ended-at"') == 1

    def test_js_has_cycle_sort(self):
        content = _read_sessions_templates()
        assert "cycleSort" in content

    def test_js_has_update_header_states(self):
        content = _read_sessions_templates()
        assert "updateHeaderStates" in content

    def test_js_has_sort_cycle(self):
        """Sort should use cycleSort + server-side submit (no client-side comparator)."""
        content = _read_sessions_templates()
        assert "cycleSort" in content
        assert "submitFilters" in content

    def test_no_sort_by_in_save_filters(self):
        content = _read_sessions_templates()
        # No old sort-by select element
        assert 'id="sort-by"' not in content

    def test_save_filters_uses_sort_key(self):
        content = _read_sessions_templates()
        assert "sortKey:" in content
        assert "sortDir:" in content

    def test_default_sort_is_ended_at_desc(self):
        content = _read_sessions_templates()
        assert "DEFAULT_SORT_KEY = 'ended-at'" in content
        assert "DEFAULT_SORT_DIR = 'desc'" in content

    def test_non_sortable_headers_no_class(self):
        """Session, Agent, Project, Failures should not be sortable."""
        content = _read_sessions_templates()
        # Session, Agent, Project, Failures are plain <div>, no data-sort-key
        lines = content.split('\n')
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('<div>') and stripped.endswith('</div>'):
                text = stripped[5:-6]
                assert text not in ('Session', 'Agent', 'Project', 'Failures') or 'data-sort-key' not in line


class TestSessionsTemplateJS:
    """Verify JS selectors migrated to grid."""

    def test_js_uses_data_sessions_grid(self):
        content = _read_sessions_templates()
        assert "[data-sessions-grid]" in content

    def test_js_uses_table_row_selector(self):
        content = _read_sessions_templates()
        assert ".table-row" in content

    def test_no_tbody_selector(self):
        """Old tbody selector should be removed."""
        content = _read_sessions_templates()
        assert "#sessions-table tbody" not in content

    def test_no_tr_selector_in_filter(self):
        """Old 'tr' query selector should be removed."""
        content = _read_sessions_templates()
        # Make sure we're not using the old tbody.querySelectorAll('tr') pattern
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

    def test_js_has_init_row_click(self):
        """JS should have initRowClick for row-level navigation."""
        content = _read_sessions_templates()
        assert "initRowClick" in content

    def test_js_navigates_to_session_url(self):
        """JS click handler should build /sessions/<agent>/<session_id> URL."""
        content = _read_sessions_templates()
        assert "/sessions/" in content
        assert "row.dataset.agent" in content
        assert "row.dataset.sessionId" in content

    def test_js_skips_links_on_click(self):
        """JS should not hijack clicks on <a> elements."""
        content = _read_sessions_templates()
        # Should check for A tag and bail out
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

    def test_template_project_column_no_tooltip(self):
        """Project column should not have data-tooltip; hover effect shows full path via title/link."""
        content = _read_sessions_templates()
        assert 'project-cell' in content
        # No data-tooltip on project-cell div
        lines = content.split('\n')
        for line in lines:
            if 'project-cell' in line and 'class=' in line:
                assert 'data-tooltip' not in line, f"project-cell should not have data-tooltip: {line}"

    def test_data_project_keeps_raw_path(self):
        """data-project attribute must retain the original project_key."""
        content = _read_sessions_templates()
        assert 'data-project="{{ s.project_key }}"' in content


class TestProjectColumnTooltip:
    """Verify Project column shows project name with full-path tooltip."""

    def test_project_cell_has_project_cell_class(self):
        """Project column cell should have project-cell class for CSS targeting."""
        content = _read_sessions_templates()
        assert 'project-cell' in content

    def test_project_cell_no_data_tooltip(self):
        """Project cell should not use data-tooltip; hover background effect replaces tooltip."""
        content = _read_sessions_templates()
        assert 'project-cell' in content
        assert 'data-tooltip="{{ s.project_key | display_path }}"' not in content

    def test_project_link_href_uses_urlencode(self):
        """Project link href should point to /projects/<encoded project_key>."""
        content = _read_sessions_templates()
        assert 'href="/projects/{{ s.project_key | urlencode }}"' in content

    def test_project_link_uses_project_name(self):
        """Project link display text should use project_name (short name)."""
        content = _read_sessions_templates()
        assert '{{ s.project_name }}' in content

    def test_session_cell_no_project_path(self):
        """Session column should NOT contain cell-sub mono with project path."""
        content = _read_sessions_templates()
        # The pattern that used to show project path under Session title
        assert 'cell-sub mono' not in content

    def test_css_has_project_cell_rules(self):
        """CSS should define project-cell styling for truncation."""
        with open("src/session_browser/web/static/style.css") as f:
            content = f.read()
        assert '.project-cell' in content
