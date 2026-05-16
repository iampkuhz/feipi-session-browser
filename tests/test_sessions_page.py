"""Tests for Sessions page grid restructure."""

from __future__ import annotations

import pytest


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
        assert "<div>Tokens</div>" in content

    def test_has_duration_column(self):
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert "<div>Duration</div>" in content

    def test_has_failures_column(self):
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert "<div>Failures</div>" in content

    def test_has_rounds_column(self):
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert "<div>Rounds</div>" in content

    def test_has_updated_column(self):
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert "<div>Updated</div>" in content


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
    """Verify sort options are correct."""

    def test_has_total_tokens_sort(self):
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert "Sort: Tokens" in content

    def test_no_input_tokens_sort(self):
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert "Sort: Input Tokens" not in content

    def test_has_failed_tools_sort(self):
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert "Sort: Failed Tools" in content


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
    """Verify triage action buttons exist."""

    def test_has_failed_only_button(self):
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert "Failed only" in content
        assert 'data-quick-filter="failed"' in content

    def test_has_high_token_button(self):
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert "High token" in content
        assert 'data-quick-filter="high-token"' in content

    def test_has_open_selected_button(self):
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert "Open selected" in content
        assert 'id="open-selected-session"' in content

    def test_action_buttons_use_action_btn_class(self):
        """Triage buttons should use .action-btn, not old .filter-chip."""
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert 'class="action-btn"' in content
        assert 'class="action-btn primary"' in content

    def test_open_selected_has_click_handler(self):
        """Open selected should have JS wiring."""
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert "openSelectedSession" in content
        assert "open-selected-session" in content


class TestSessionsListSelection:
    """Verify row selection state support."""

    def test_selected_css_exists(self):
        """style.css should have .table-row.selected styling."""
        with open("src/session_browser/web/static/style.css") as f:
            content = f.read()
        assert ".table-row.selected" in content or ".table-row.selected" in content.replace(" ", "")

    def test_js_sets_selected_class(self):
        """JS should add/remove .selected class on rows."""
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert "classList.add('selected')" in content or 'classList.add("selected")' in content

    def test_js_sets_aria_selected(self):
        """JS should set aria-selected attribute."""
        with open("src/session_browser/web/templates/sessions.html") as f:
            content = f.read()
        assert "aria-selected" in content

    def test_action_btn_active_state(self):
        """Quick filter active state should use .action-btn.active."""
        with open("src/session_browser/web/static/style.css") as f:
            content = f.read()
        assert ".action-btn.active" in content or ".action-btn.active" in content.replace(" ", "")
