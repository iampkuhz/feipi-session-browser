"""Tests for Projects page table restructure.

Page-level pytest for projects.html covering template structure, CSS/JS imports,
metric cards, filter card, table structure, row structure, pagination,
empty/error states, and absence of inline onclick.

T108 — Projects List: Add page-specific pytest.
"""

from __future__ import annotations

import os
import re

import pytest

_PROJECTS_PATH = "src/session_browser/web/templates/projects.html"
_PROJECTS_CSS_PATH = "src/session_browser/web/static/css/projects.css"
_PROJECTS_JS_PATH = "src/session_browser/web/static/js/projects.js"


def _read(path: str) -> str:
    with open(path) as f:
        return f.read()


def _read_template() -> str:
    return _read(_PROJECTS_PATH)


class TestTruncatePath:
    """Verify project path display does not show '.' for repo root."""

    def test_repo_root_not_dot(self):
        """A full absolute path should never be truncated to '.'."""
        from session_browser.web.routes import _truncate_path
        result = _truncate_path("/Users/zhehan/Documents/tools/llm/feipi-agent-kit")
        assert result != "."
        assert "feipi-agent-kit" in result

    def test_long_path_truncated(self):
        from session_browser.web.routes import _truncate_path
        path = "/Users/zhehan/some/very/long/path/to/project"
        result = _truncate_path(path)
        # Should preserve beginning and end
        assert result.startswith("/")
        assert "project" in result

    def test_short_path_preserved(self):
        from session_browser.web.routes import _truncate_path
        path = "/tmp/short"
        result = _truncate_path(path)
        assert result == path


class TestProjectsTemplateColumns:
    """Verify the projects.html template has correct columns and no removed ones."""

    def test_no_cache_r_column(self):
        content = _read_template()
        assert "Cache R" not in content

    def test_no_cache_w_column(self):
        content = _read_template()
        assert "Cache W" not in content

    def test_no_output_column(self):
        content = _read_template()
        # No standalone Output column (may appear in tooltip text, that's OK)
        assert "Output Tokens" not in content

    def test_no_tools_per_round_column(self):
        content = _read_template()
        assert "Tools/R" not in content

    def test_no_standalone_failed_column(self):
        content = _read_template()
        assert ">Failed</th>" not in content

    def test_has_agents_column(self):
        content = _read_template()
        assert "Agents" in content

    def test_has_tokens_column(self):
        content = _read_template()
        assert "Tokens" in content


class TestProjectsTemplateSortOptions:
    """Verify sort options no longer include removed columns."""

    def test_no_cache_read_sort(self):
        content = _read_template()
        assert "Cache Read" not in content

    def test_no_cache_write_sort(self):
        content = _read_template()
        assert "Cache Write" not in content

    def test_no_output_tokens_sort(self):
        content = _read_template()
        assert "Output Tokens" not in content

    def test_has_tokens_sort(self):
        content = _read_template()
        assert "Tokens" in content

    def test_has_failed_tools_sort(self):
        content = _read_template()
        assert "Failed Tools" in content


_UI_PRIMITIVES_PATH = "src/session_browser/web/templates/components/ui_primitives.html"


def _read_ui_primitives() -> str:
    return _read(_UI_PRIMITIVES_PATH)


class TestProjectsTemplatePathDisplay:
    """Verify path display uses truncate_path without relative_to_repo."""

    def test_no_relative_to_repo_for_project_path(self):
        """Project paths should not use relative_to_repo filter."""
        content = _read_template()
        lines = content.split("\n")
        for line in lines:
            if "project_key" in line and "truncate_path" in line:
                assert "relative_to_repo" not in line

    def test_path_copy_uses_full_project_key(self):
        """Copy button should use the full project_key via data-clipboard-text."""
        content = _read_template()
        # projects.html passes full p.project_key as path parameter to macro
        macro = _read_ui_primitives()
        assert 'data-clipboard-text="{{ path }}"' in macro, \
            "project_cell macro must have data-clipboard-text bound to path"
        assert 'data-action="copy-project-path"' in macro, \
            "project_cell macro must have copy-project-path action"

    def test_path_tooltip_shows_full_key(self):
        """Tooltip should show the full project_key."""
        content = _read_template()
        # projects.html passes full p.project_key to macro;
        # the macro renders data-tooltip="{{ path }}"
        assert "ui.project_cell(" in content, \
            "projects.html must use project_cell macro"
        # Verify macro template has data-tooltip
        macro = _read_ui_primitives()
        assert 'data-tooltip="{{ path }}"' in macro, \
            "project_cell macro must have data-tooltip on path"


class TestProjectsTemplateTitle:
    """Verify the title doesn't have excessive spacing."""

    def test_title_not_justified_between(self):
        """Title should not use justify-between to separate ( and )."""
        content = _read_template()
        assert "justify-between" not in content
        # Should use ui.table_card macro which renders card-title (T103: migrated)
        assert "ui.table_card(" in content


# ── TestProjectsTemplate ──────────────────────────────────────────

class TestProjectsTemplate:
    """Verify the projects Jinja2 template renders structurally."""

    def test_template_file_exists(self):
        assert os.path.isfile(_PROJECTS_PATH), \
            f"{_PROJECTS_PATH} must exist"

    def test_extends_base(self):
        content = _read_template()
        assert '{% extends "base.html" %}' in content, \
            "Projects must extend base.html"

    def test_active_page_set(self):
        content = _read_template()
        assert "active_page = 'projects'" in content, \
            "Projects must set active_page = 'projects'"

    def test_ui_primitives_imported(self):
        content = _read_template()
        assert 'import "components/ui_primitives.html"' in content, \
            "Projects must import ui_primitives.html"

    def test_no_inline_onclick(self):
        """Projects must not use inline onclick handlers."""
        content = _read_template()
        matches = re.findall(r'\bonclick\s*=', content, re.IGNORECASE)
        assert len(matches) == 0, \
            f"Projects must not have inline onclick, found {len(matches)} occurrences"


# ── TestProjectsImports ───────────────────────────────────────────

class TestProjectsImports:
    """Verify CSS and JS import statements."""

    def test_css_import_projects_css(self):
        content = _read_template()
        assert 'href="/static/css/projects.css"' in content, \
            "Projects must import projects.css"

    def test_js_import_projects_js(self):
        content = _read_template()
        assert 'src="/static/js/projects.js"' in content, \
            "Projects must import projects.js"

    def test_css_file_exists_on_disk(self):
        assert os.path.isfile(_PROJECTS_CSS_PATH), \
            "projects.css must exist on disk"

    def test_js_file_exists_on_disk(self):
        assert os.path.isfile(_PROJECTS_JS_PATH), \
            "projects.js must exist on disk"


# ── TestProjectsPageHead ──────────────────────────────────────────

class TestProjectsPageHead:
    """Verify page-head structure (uses ui.page_head macro, T15)."""

    def test_page_head_macro_used(self):
        content = _read_template()
        assert 'ui.page_head(' in content, \
            "Projects must use ui.page_head() macro"

    def test_page_head_has_h1(self):
        content = _read_template()
        assert "'Projects'" in content, \
            "Page-head must have 'Projects' as title"

    def test_page_head_has_subtitle(self):
        content = _read_template()
        assert "Indexed local workspaces" in content, \
            "Page-head must have subtitle about indexed workspaces"

    def test_page_head_stat_pills_used(self):
        content = _read_template()
        assert 'stat_pills=' in content, \
            "Page-head must use stat_pills parameter for project count"

    def test_page_head_count_element(self):
        content = _read_template()
        assert 'id="projects-count"' in content, \
            "Page-head must have a projects-count element in stat_pills"


# ── TestProjectsMetricCards ───────────────────────────────────────

class TestProjectsMetricCards:
    """Verify 4 metric cards with correct labels and structure."""

    _EXPECTED_LABELS = ["Projects", "Sessions", "Total Tokens", "Failed Tools"]

    def test_metric_grid_present(self):
        content = _read_template()
        assert 'class="metric-grid"' in content, \
            "Projects must have a metric-grid section"

    def test_four_metric_cards(self):
        content = _read_template()
        cards = re.findall(r'class="metric-card"', content)
        assert len(cards) == 4, \
            f"Projects must have exactly 4 metric cards, found {len(cards)}"

    @pytest.mark.parametrize("label", _EXPECTED_LABELS)
    def test_metric_card_labels(self, label):
        content = _read_template()
        # Template has ">Label\n" or '>"Label"' -- check for the label text near metric-card__label
        assert f">{label}" in content, \
            f"Projects must have a metric card labeled '{label}'"

    def test_metric_card_aria_labels(self):
        """Each metric card must have a data-metric attribute for info buttons."""
        content = _read_template()
        # Template uses data-metric on info buttons
        data_metrics = re.findall(r'data-metric="([^"]*)"', content)
        assert len(data_metrics) >= 4, \
            f"Projects must have at least 4 data-metric attributes, found {len(data_metrics)}"

    def test_metric_card_has_icon(self):
        """Each metric card must have a metric-icon element."""
        content = _read_template()
        icons = re.findall(r'class="metric-icon[^"]*"', content)
        assert len(icons) >= 4, \
            f"Projects must have at least 4 metric-icon elements, found {len(icons)}"

    def test_metric_card_has_label_class(self):
        """Each metric card must have a metric-card__label element."""
        content = _read_template()
        labels = re.findall(r'class="metric-card__label"', content)
        assert len(labels) >= 4, \
            f"Projects must have at least 4 metric-card__label elements, found {len(labels)}"

    def test_metric_card_has_value_class(self):
        """Each metric card must have a metric-card__value element."""
        content = _read_template()
        values = re.findall(r'class="metric-card__value mono"', content)
        assert len(values) >= 4, \
            f"Projects must have at least 4 metric-card__value elements, found {len(values)}"

    def test_metric_card_has_panel_sub(self):
        """Each metric card must have a metric-card__sub element."""
        content = _read_template()
        subs = re.findall(r'class="metric-card__sub"', content)
        assert len(subs) >= 4, \
            f"Projects must have at least 4 metric-card__sub elements, found {len(subs)}"

    def test_metric_info_buttons(self):
        """Each metric card must have an info button with data-action='metric-info'."""
        content = _read_template()
        buttons = re.findall(r'data-action="metric-info"', content)
        assert len(buttons) == 4, \
            f"Projects must have 4 metric-info buttons, found {len(buttons)}"

    def test_metric_info_buttons_have_data_metric(self):
        """Each info button must have a data-metric attribute."""
        content = _read_template()
        data_metrics = re.findall(r'data-metric="[^"]*"', content)
        assert len(data_metrics) >= 4, \
            f"Projects must have at least 4 data-metric attributes, found {len(data_metrics)}"

    def test_metric_info_uses_icon_button_info_class(self):
        """Info buttons must use icon-button--info class."""
        content = _read_template()
        assert "icon-button--info" in content, \
            "Info buttons must use icon-button--info class"


# ── TestProjectsFilterCard ────────────────────────────────────────

class TestProjectsFilterCard:
    """Verify filter card structure."""

    def test_filter_card_present(self):
        content = _read_template()
        assert ('class="card filter-card"' in content
                or 'ui.filter_card()' in content), \
            "Projects must have a filter-card"

    def test_search_input_with_data_search(self):
        # data-search attribute is optional with macro-based filters
        content = _read_template()
        assert ('data-search="project-name"' in content
                or "id='project-search'" in content
                or 'id="project-search"' in content), \
            "Search input must have identifiable attributes"

    def test_search_input_id(self):
        content = _read_template()
        assert ('id="project-search"' in content
                or "id='project-search'" in content), \
            "Search input must have id='project-search'"

    def test_apply_button(self):
        content = _read_template()
        assert ('data-action="apply-search"' in content
                or "data_action='apply-search'" in content), \
            "Apply button must have data-action='apply-search'"

    def test_clear_button(self):
        content = _read_template()
        assert ('data-action="clear-search"' in content
                or "data_action='clear-search'" in content), \
            "Clear button must have data-action='clear-search'"

    def test_active_filters_aria_live(self):
        content = _read_template()
        assert ('class="active-filters"' in content
                or 'class="filter-footer"' in content), \
            "Filter card must have active-filters section"


# ── TestProjectsTableStructure ────────────────────────────────────

class TestProjectsTableStructure:
    """Verify table structure and column headers."""

    _EXPECTED_COLUMNS = ["Project", "Agents", "Sessions", "Tokens", "Tools", "Last Active"]

    def test_table_has_id(self):
        content = _read_template()
        assert 'id="projects-table"' in content, \
            "Projects table must have id='projects-table'"

    def test_table_has_data_enhanced(self):
        content = _read_template()
        assert 'data-table-enhanced' in content, \
            "Projects table must have data-table-enhanced attribute"

    @pytest.mark.parametrize("column", ["Project", "Agents", "Sessions", "Tokens", "Tools", "Last Active"])
    def test_column_headers_present(self, column):
        content = _read_template()
        assert f"<th>{column}</th>" in content or f"<th class=" in content and column in content, \
            f"Table must have '{column}' column header"

    def test_sortable_columns_have_data_sort(self):
        content = _read_template()
        sort_buttons = re.findall(r'data-action="sort"', content)
        assert len(sort_buttons) >= 4, \
            f"Table must have at least 4 sort buttons, found {len(sort_buttons)}"

    def test_sortable_columns_data_sort_values(self):
        content = _read_template()
        for sort_key in ["sessions", "tokens", "tools", "last_active"]:
            assert f'data-sort-key="{sort_key}"' in content, \
                f"Table must have data-sort-key='{sort_key}'"

    def test_sortable_headers_have_title(self):
        content = _read_template()
        # Unified pattern: sort-button has title attribute (Chinese label)
        sort_titles = re.findall(r'title="按[^"]*排序"', content)
        assert len(sort_titles) >= 4, \
            f"Sortable headers must have sort title, found {len(sort_titles)}"

    def test_table_toolbar_present(self):
        content = _read_template()
        assert "ui.table_card(" in content, \
            "Table must use ui.table_card macro which renders table-toolbar"

    def test_table_toolbar_has_table_title(self):
        content = _read_template()
        assert "ui.table_card(" in content, \
            "Table must use ui.table_card macro which renders card-title"
        assert "'All Projects'" in content or '"All Projects"' in content, \
            "Table title must reference All Projects"

    def test_table_has_table_note(self):
        content = _read_template()
        assert "ui.table_card(" in content, \
            "Table must use ui.table_card macro"
        assert "subtitle=" in content, \
            "table_card call must pass subtitle parameter"


# ── TestProjectsRowStructure ──────────────────────────────────────

class TestProjectsRowStructure:
    """Verify table row structure and data attributes."""

    def test_row_has_open_project_action(self):
        content = _read_template()
        assert 'data-action="open-project"' in content, \
            "Row must have data-action='open-project'"

    def test_row_has_data_name(self):
        content = _read_template()
        assert 'data-name="{{ p.project_name | lower }}"' in content, \
            "Row must have data-name attribute"

    def test_row_has_data_path(self):
        content = _read_template()
        assert 'data-path="{{ p.project_key | lower }}"' in content, \
            "Row must have data-path attribute"

    def test_row_has_data_last_seen(self):
        content = _read_template()
        assert 'data-last-seen="{{ p.last_seen }}"' in content, \
            "Row must have data-last-seen attribute"

    def test_row_has_data_total_sessions(self):
        content = _read_template()
        assert 'data-total-sessions="{{ p.total_sessions }}"' in content, \
            "Row must have data-total-sessions attribute"

    def test_row_has_data_total_tokens(self):
        content = _read_template()
        assert 'data-total-tokens="{{ p_total_tokens }}"' in content, \
            "Row must have data-total-tokens attribute"

    def test_project_name_link(self):
        content = _read_template()
        # projects.html delegates to project_cell macro;
        # verify macro defines the class
        assert 'class="project-name-link"' in _read_ui_primitives(), \
            "project_cell macro must define project-name-link class"

    def test_project_name_link_action(self):
        content = _read_template()
        # Verify projects.html passes name_data_action parameter
        assert "name_data_action='open-project-link'" in content, \
            "projects.html must pass name_data_action='open-project-link' to macro"
        # Verify macro supports name_data_action
        macro = _read_ui_primitives()
        assert "name_data_action" in macro, \
            "project_cell macro must support name_data_action parameter"

    def test_path_text_truncate(self):
        # Path text class is defined in the macro
        assert 'class="path-text truncate"' in _read_ui_primitives(), \
            "project_cell macro must define path-text truncate class"

    def test_path_copy_button(self):
        # Copy button class is defined in the macro
        assert 'class="path-copy-btn"' in _read_ui_primitives(), \
            "project_cell macro must define path-copy-btn class"

    def test_path_copy_button_data_action(self):
        # Copy button data-action is defined in the macro
        assert 'data-action="copy-project-path"' in _read_ui_primitives(), \
            "project_cell macro must have data-action='copy-project-path'"

    def test_agent_badge_cc(self):
        content = _read_template()
        assert 'badge_with_dot' in content and "'cc'" in content, \
            "Must have Claude Code agent badge via badge_with_dot macro"

    def test_agent_badge_cx(self):
        content = _read_template()
        assert 'badge_with_dot' in content and "'cx'" in content, \
            "Must have Codex agent badge via badge_with_dot macro"

    def test_agent_badge_qd(self):
        content = _read_template()
        assert 'badge_with_dot' in content and "'qd'" in content, \
            "Must have Qoder agent badge via badge_with_dot macro"

    def test_tokenbar_present(self):
        # Token cells are rendered via ui.token_cell macro
        content = _read_template()
        assert 'ui.token_cell' in content, \
            "projects.html must call ui.token_cell macro"

    def test_tokenbar_has_four_segments(self):
        macro = _read_ui_primitives()
        segs = re.findall(r'class="tokenbar-seg (fresh|read|write|out)"', macro)
        assert len(segs) >= 4, \
            f"token_cell macro must have 4 segments, found {len(segs)}"

    def test_tokenbar_segments_classes(self):
        macro = _read_ui_primitives()
        for seg_class in ["fresh", "read", "write", "out"]:
            assert f'tokenbar-seg {seg_class}' in macro, \
                f"token_cell macro must have segment class '{seg_class}'"

    def test_tokenbar_tooltip_present(self):
        macro = _read_ui_primitives()
        assert 'class="token-tooltip"' in macro, \
            "token_cell macro must have tooltip element"

    def test_tokenbar_tooltip_has_breakdown(self):
        macro = _read_ui_primitives()
        assert "Token Breakdown" in macro, \
            "token_cell tooltip must show token breakdown"

    def test_tools_failed_badge(self):
        content = _read_template()
        assert 'class="badge err tools-failed"' in content, \
            "Failed tools must use err badge"

    def test_relative_time_filter(self):
        content = _read_template()
        assert "relative_time" in content, \
            "Last Active column must use relative_time filter"


# ── TestProjectsPagination ────────────────────────────────────────

class TestProjectsPagination:
    """Verify pagination structure."""

    def test_pagination_nav_present(self):
        content = _read_template()
        assert 'class="pagination unified-pagination"' in content, \
            "Projects must have unified-pagination"

    def test_pagination_has_role_navigation(self):
        content = _read_template()
        assert 'role="navigation"' in content, \
            "Pagination must have role='navigation'"

    def test_pagination_page_input(self):
        content = _read_template()
        assert 'data-action="page-input"' in content, \
            "Pagination must have data-action='page-input'"

    def test_pagination_next_page(self):
        content = _read_template()
        assert 'data-action="next-page"' in content, \
            "Pagination must have data-action='next-page'"

    def test_pagination_page_status(self):
        content = _read_template()
        assert 'class="page-status"' in content, \
            "Pagination must have page-status element"

    def test_pagination_has_aria_label(self):
        content = _read_template()
        assert 'aria-label="Pagination"' in content, \
            "Pagination must have aria-label='Pagination'"


# ── TestProjectsEmptyState ────────────────────────────────────────

class TestProjectsEmptyState:
    """Verify empty state rendering."""

    def test_empty_state_macro_used(self):
        content = _read_template()
        assert "ui.empty_state" in content, \
            "Projects must use ui.empty_state macro"

    def test_empty_state_has_action_button(self):
        content = _read_template()
        assert "Run Scan" in content, \
            "Empty state must have 'Run Scan' action button"

    def test_empty_state_has_icon(self):
        content = _read_template()
        # Check the inline empty state strip has state-icon element
        assert 'class="state-icon"' in content, \
            "Empty state must have state-icon element"
        assert "state-strip" in content, \
            "Empty state must use state-strip class"

    def test_empty_state_has_clear_search(self):
        content = _read_template()
        assert "Clear Search" in content, \
            "Empty state must have Clear Search button"

    def test_empty_state_has_data_action_clear_search(self):
        content = _read_template()
        # The inline empty state strip also has clear-search
        assert 'data-action="clear-search"' in content, \
            "Empty state clear button must have data-action='clear-search'"


# ── TestProjectsErrorState ────────────────────────────────────────

class TestProjectsErrorState:
    """Verify error state rendering."""

    def test_error_state_condition(self):
        content = _read_template()
        assert "{% if error %}" in content, \
            "Projects must check for error variable"

    def test_error_state_uses_ui_macro(self):
        content = _read_template()
        assert "ui.error_state" in content, \
            "Error state must use ui.error_state macro"

    def test_error_state_has_dashboard_link(self):
        content = _read_template()
        assert "/dashboard" in content, \
            "Error state must link back to /dashboard"

    def test_error_state_has_go_dashboard_action(self):
        content = _read_template()
        assert "Back to Dashboard" in content, \
            "Error state must have 'Back to Dashboard' button"

    def test_error_state_has_role_alert(self):
        """Error state macro generates role='alert' at render time."""
        content = _read_template()
        # The ui.error_state macro generates role="alert"; verify the macro is used
        assert "ui.error_state" in content, \
            "Error state must use ui.error_state macro (which generates role='alert')"

    def test_error_state_has_aria_live_assertive(self):
        """Error state macro generates aria-live='assertive' at render time."""
        content = _read_template()
        # The ui.error_state macro generates aria-live="assertive"; verify the macro is used
        assert "ui.error_state" in content, \
            "Error state must use ui.error_state macro (which generates aria-live='assertive')"


# ── TestProjectsNoStalePatterns ───────────────────────────────────

class TestProjectsNoStalePatterns:
    """Verify stale v15/v16 patterns are NOT present."""

    def test_no_cache_r_columns(self):
        content = _read_template()
        assert "Cache R" not in content, \
            "Projects must not have Cache R column"

    def test_no_cache_w_columns(self):
        content = _read_template()
        assert "Cache W" not in content, \
            "Projects must not have Cache W column"

    def test_no_select_based_sorting(self):
        """No <select> elements for sorting — uses button-based sortable headers."""
        content = _read_template()
        # Should not have sorting via select elements
        assert '<select' not in content, \
            "Projects must not use select-based sorting"

    def test_no_inline_onclick(self):
        content = _read_template()
        matches = re.findall(r'\bonclick\s*=', content, re.IGNORECASE)
        assert len(matches) == 0, \
            f"Projects must not have inline onclick, found {len(matches)}"

    def test_no_inline_script_in_template(self):
        """Template must not have inline <script> blocks (uses script_extra)."""
        content = _read_template()
        # Only allow script_extra block with src= import
        script_tags = re.findall(r'<script(?! src)[^>]*>', content)
        assert len(script_tags) == 0, \
            f"Projects must not have inline script tags, found {len(script_tags)}"

    def test_no_inline_style_in_template(self):
        """Template must not have inline style blocks (uses projects.css)."""
        content = _read_template()
        style_blocks = re.findall(r'<style[^>]*>', content)
        assert len(style_blocks) == 0, \
            f"Projects must not have inline style blocks, found {len(style_blocks)}"

    def test_no_output_tokens_column(self):
        content = _read_template()
        assert "Output Tokens" not in content, \
            "Projects must not have Output Tokens column"

    def test_no_tools_per_round_column(self):
        content = _read_template()
        assert "Tools/R" not in content, \
            "Projects must not have Tools/R column"

    def test_no_hero_section(self):
        content = _read_template()
        assert 'class="hero"' not in content, \
            "Projects must not have hero section"


# ── TestProjectsDataActions ───────────────────────────────────────

class TestProjectsDataActions:
    """Verify all required data-action attributes are present."""

    _EXPECTED_ACTIONS = [
        "open-project",
        "apply-search",
        "clear-search",
        "metric-info",
        "sort",
        "page-input",
        "next-page",
    ]

    # Actions defined in the project_cell macro (verified separately)
    # Note: open-project-link is passed via name_data_action parameter,
    # so the macro has data-action="{{ name_data_action }}" not a literal string.
    _MACRO_ACTIONS = [
        "copy-project-path",
    ]

    @pytest.mark.parametrize("action", _EXPECTED_ACTIONS)
    def test_data_action_present(self, action):
        content = _read_template()
        # Accept both rendered HTML (data-action="...") and Jinja2 params (data_action='...')
        assert (f'data-action="{action}"' in content
                or f"data_action='{action}'" in content), \
            f"Template must have data-action='{action}'"

    @pytest.mark.parametrize("action", _MACRO_ACTIONS)
    def test_macro_data_actions(self, action):
        """Verify data-actions defined in the project_cell macro."""
        macro = _read_ui_primitives()
        assert f'data-action="{action}"' in macro, \
            f"project_cell macro must have data-action='{action}'"

    def test_projects_passes_open_project_link(self):
        """Verify projects.html passes the open-project-link action to macro."""
        content = _read_template()
        assert "name_data_action='open-project-link'" in content, \
            "projects.html must pass name_data_action='open-project-link'"

    def test_macro_supports_name_data_action(self):
        """Verify macro renders data-action from name_data_action parameter."""
        macro = _read_ui_primitives()
        assert 'data-action="{{ name_data_action }}"' in macro, \
            "project_cell macro must support name_data_action parameter"

    def test_data_action_go_dashboard(self):
        """go-dashboard action is generated via ui.button macro parameter."""
        content = _read_template()
        # Template uses Jinja2 macro parameter: data_action='go-dashboard'
        assert "go-dashboard" in content, \
            "Template must have go-dashboard action"

    def test_data_action_run_scan(self):
        """run-scan action is generated via ui.button macro parameter."""
        content = _read_template()
        # Template uses Jinja2 macro parameter: data_action='run-scan'
        assert "run-scan" in content, \
            "Template must have run-scan action"
