"""Tests for Sessions page grid restructure."""

from __future__ import annotations

import os
import pytest

from session_browser.web.routes import _display_path


class TestSessionsTemplateColumns:
    """Verify sessions.html has the correct restructured 8-column grid headers."""

    def test_has_session_column(self):
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert "<div>Session</div>" in content

    def test_has_project_column(self):
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert "<div>Project</div>" in content

    def test_has_agent_column(self):
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert "<div>Agent</div>" in content

    def test_has_tokens_column(self):
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert "Tokens" in content

    def test_has_duration_column(self):
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert "Duration" in content

    def test_has_failures_column(self):
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert "<div>Failures</div>" in content

    def test_has_rounds_column(self):
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert "Rounds" in content

    def test_has_updated_column(self):
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert "Updated" in content


class TestSessionsTemplateRemovedColumns:
    """Verify old table columns are no longer present in grid."""

    def test_no_table_element(self):
        """No <table> element in the grid area."""
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert "<table" not in content

    def test_no_model_column(self):
        """Model column not in grid (kept as data-*)."""
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        # Should not have Model as a visible column header
        assert "<div>Model</div>" not in content

    def test_no_anomaly_column(self):
        """Anomaly column not in grid (kept as data-*)."""
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert "<div>Anomaly</div>" not in content

    def test_no_output_column(self):
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert "<div>Output</div>" not in content

    def test_no_tools_column(self):
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert "<div>Tools</div>" not in content

    def test_no_time_column(self):
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert "<div>Time</div>" not in content

    def test_no_standalone_dot_column(self):
        """No empty dot th element."""
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert "class=\"agent-dot" not in content

    def test_no_cache_r_column(self):
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert ">Cache R</th>" not in content

    def test_no_cache_w_column(self):
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert ">Cache W</th>" not in content

    def test_no_output_percent_column(self):
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert ">Output%</th>" not in content

    def test_no_standalone_failed_column(self):
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert ">Failed</th>" not in content

    def test_no_tools_per_round_column(self):
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert ">Tools/R</th>" not in content


class TestSessionsTemplateGridStructure:
    """Verify the new div-based grid structure."""

    def test_has_data_sessions_grid(self):
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert "data-sessions-grid" in content

    def test_has_table_head(self):
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert 'class="table-head"' in content

    def test_has_table_row(self):
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert "table-row" in content

    def test_has_cell_title(self):
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert 'class="cell-title"' in content

    def test_has_cell_sub(self):
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert 'class="cell-sub' in content

    def test_has_badge_agent(self):
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert 'class="badge agent"' in content

    def test_has_diag_ok(self):
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert 'class="diag ok"' in content

    def test_has_diag_err(self):
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert 'class="diag err"' in content

    def test_no_data_table_enhanced(self):
        """data-table-enhanced attribute should be removed."""
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert "data-table-enhanced" not in content


class TestSessionsTemplateFailuresMerged:
    """Verify failures column uses diag pills."""

    def test_diag_err_shown_when_failed(self):
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert "diag err" in content

    def test_diag_ok_shown_when_zero(self):
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert "diag ok" in content

    def test_failed_tool_count_used(self):
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert "failed_tool_count" in content


class TestSessionsTemplateDataAttributes:
    """Verify data attributes are preserved and updated."""

    def test_has_total_tokens_data_attr(self):
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert "data-total-tokens=" in content

    def test_has_rounds_data_attr(self):
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert "data-rounds=" in content

    def test_has_data_agent(self):
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert "data-agent=" in content

    def test_has_data_session_id(self):
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert "data-session-id=" in content

    def test_has_data_model(self):
        """Model data retained as data-* attribute."""
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert "data-model=" in content

    def test_has_data_anomaly(self):
        """Anomaly data retained as data-* attributes."""
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert "data-has-anomalies=" in content

    def test_no_cache_data_attrs(self):
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert "data-total-cache-r=" not in content
        assert "data-total-cache-w=" not in content


class TestSessionsTemplateAnomalyData:
    """Verify anomaly info retained in data-* attributes."""

    def test_anomaly_has_data_attribute(self):
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert "data-anomaly-types=" in content

    def test_anomaly_limits_types(self):
        """Should limit anomaly types in data attribute."""
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert "s.anomalies" in content


class TestSessionsTemplateSortOptions:
    """Verify sort-by select has been removed."""

    def test_no_sort_by_select(self):
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert 'id="sort-by"' not in content

    def test_no_sort_select_options(self):
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert "Sort: Last Active" not in content
        assert "Sort: Tokens" not in content
        assert "Sort: Duration" not in content


class TestHeaderSort:
    """Verify clickable header-based sorting."""

    def test_duration_is_sortable(self):
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert 'data-sort-key="duration"' in content
        assert 'th-sortable' in content

    def test_tokens_is_sortable(self):
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert 'data-sort-key="total-tokens"' in content

    def test_rounds_is_sortable(self):
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert 'data-sort-key="rounds"' in content

    def test_updated_is_sortable(self):
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert 'data-sort-key="ended-at"' in content

    def test_updated_has_default_desc(self):
        """Default sort should be Updated descending."""
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert 'aria-sort=' in content
        assert 'descending' in content

    def test_four_sortable_headers(self):
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        # Count data-sort-key attributes on sortable headers (not plain divs)
        assert content.count('data-sort-key="duration"') == 1
        assert content.count('data-sort-key="total-tokens"') == 1
        assert content.count('data-sort-key="rounds"') == 1
        assert content.count('data-sort-key="ended-at"') == 1

    def test_js_has_cycle_sort(self):
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert "cycleSort" in content

    def test_js_has_update_header_states(self):
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert "updateHeaderStates" in content

    def test_js_has_sort_comparator(self):
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert "sortComparator" in content

    def test_no_sort_by_in_save_filters(self):
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        # No old sort-by select element
        assert 'id="sort-by"' not in content

    def test_save_filters_uses_sort_key(self):
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert "sortKey:" in content
        assert "sortDir:" in content

    def test_default_sort_is_ended_at_desc(self):
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert "DEFAULT_SORT_KEY = 'ended-at'" in content
        assert "DEFAULT_SORT_DIR = 'desc'" in content

    def test_non_sortable_headers_no_class(self):
        """Session, Agent, Project, Failures should not be sortable."""
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
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
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert "[data-sessions-grid]" in content

    def test_js_uses_table_row_selector(self):
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert ".table-row" in content

    def test_no_tbody_selector(self):
        """Old tbody selector should be removed."""
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert "#sessions-table tbody" not in content

    def test_no_tr_selector_in_filter(self):
        """Old 'tr' query selector should be removed."""
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        # Make sure we're not using the old tbody.querySelectorAll('tr') pattern
        assert "tbody.querySelectorAll" not in content


class TestSessionsListActions:
    """Verify triage action buttons have been removed."""

    def test_no_failed_only_button(self):
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert "Failed only" not in content

    def test_no_high_token_button(self):
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert "High token" not in content

    def test_no_open_selected_button(self):
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert "Open selected" not in content
        assert 'id="open-selected-session"' not in content

    def test_no_top_actions(self):
        """The .top-actions container should not exist."""
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert "top-actions" not in content

    def test_no_toggle_quick_filter_js(self):
        """toggleQuickFilter function should be removed."""
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert "toggleQuickFilter" not in content

    def test_no_open_selected_session_js(self):
        """openSelectedSession function should be removed."""
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert "openSelectedSession" not in content


class TestSessionsListRowClick:
    """Verify session row click navigates to detail page."""

    def test_row_has_data_agent(self):
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert 'data-agent="{{ s.agent }}"' in content

    def test_row_has_data_session_id(self):
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert 'data-session-id="{{ s.session_id }}"' in content

    def test_js_has_init_row_click(self):
        """JS should have initRowClick for row-level navigation."""
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert "initRowClick" in content

    def test_js_navigates_to_session_url(self):
        """JS click handler should build /sessions/<agent>/<session_id> URL."""
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert "/sessions/" in content
        assert "row.dataset.agent" in content
        assert "row.dataset.sessionId" in content

    def test_js_skips_links_on_click(self):
        """JS should not hijack clicks on <a> elements."""
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        # Should check for A tag and bail out
        assert "tagName === 'A'" in content or 'tagName === "A"' in content

    def test_no_selection_js_leftover(self):
        """Should not have .selected class manipulation or aria-selected."""
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
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

    def test_template_uses_display_path_on_cell_sub(self):
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert "display_path" in content

    def test_data_project_keeps_raw_path(self):
        """data-project attribute must retain the original project_key."""
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert 'data-project="{{ s.project_key }}"' in content
