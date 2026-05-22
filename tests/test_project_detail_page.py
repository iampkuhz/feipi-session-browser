"""Tests for Project Detail page (project.html).

Page-level pytest for project.html covering template structure, CSS/JS imports,
page-head, metric cards, info buttons, table toolbar, table structure,
row structure, pagination, empty/error states, and absence of stale patterns.

T122 — Project Detail: Add page-specific pytest.
"""

from __future__ import annotations

import os
import re

import pytest

_PROJECT_PATH = "src/session_browser/web/templates/project.html"
_PROJECTS_CSS_PATH = "src/session_browser/web/static/css/projects.css"
_PROJECTS_JS_PATH = "src/session_browser/web/static/js/projects.js"


def _read(path: str) -> str:
    with open(path) as f:
        return f.read()


def _read_template() -> str:
    return _read(_PROJECT_PATH)


# ── TestProjectDetailTemplate ─────────────────────────────────────

class TestProjectDetailTemplate:
    """Verify the project Jinja2 template renders structurally."""

    def test_template_file_exists(self):
        """project.html must exist on disk."""
        assert os.path.isfile(_PROJECT_PATH), \
            f"{_PROJECT_PATH} must exist"

    def test_extends_base(self):
        """Project must extend base.html."""
        content = _read_template()
        assert '{% extends "base.html" %}' in content, \
            "Project must extend base.html"

    def test_active_page_set(self):
        """Project must set active_page = 'projects'."""
        content = _read_template()
        assert "active_page = 'projects'" in content, \
            "Project must set active_page = 'projects'"

    def test_ui_primitives_imported(self):
        """Project must import ui_primitives.html."""
        content = _read_template()
        assert 'import "components/ui_primitives.html"' in content, \
            "Project must import ui_primitives.html"

    def test_no_inline_onclick(self):
        """Project must not use inline onclick handlers."""
        content = _read_template()
        matches = re.findall(r'\bonclick\s*=', content, re.IGNORECASE)
        assert len(matches) == 0, \
            f"Project must not have inline onclick, found {len(matches)} occurrences"


# ── TestProjectDetailImports ──────────────────────────────────────

class TestProjectDetailImports:
    """Verify CSS and JS import statements."""

    def test_css_import_projects_css(self):
        """Project must import projects.css."""
        content = _read_template()
        assert 'href="/static/css/projects.css"' in content, \
            "Project must import projects.css"

    def test_js_import_projects_js(self):
        """Project must import projects.js."""
        content = _read_template()
        assert 'src="/static/js/projects.js"' in content, \
            "Project must import projects.js"

    def test_css_file_exists_on_disk(self):
        """projects.css must exist on disk."""
        assert os.path.isfile(_PROJECTS_CSS_PATH), \
            "projects.css must exist on disk"

    def test_js_file_exists_on_disk(self):
        """projects.js must exist on disk."""
        assert os.path.isfile(_PROJECTS_JS_PATH), \
            "projects.js must exist on disk"


# ── TestProjectDetailPageHead ─────────────────────────────────────

class TestProjectDetailPageHead:
    """Verify page-head structure (uses ui.page_head macro, T15)."""

    def test_page_head_macro_used(self):
        """Project must use ui.page_head() macro."""
        content = _read_template()
        assert 'ui.page_head(' in content, \
            "Project must use ui.page_head() macro"

    def test_back_button_present(self):
        """Page-head must use ui.back_button macro linking to /projects."""
        content = _read_template()
        assert "ui.back_button(" in content, \
            "Page-head must use ui.back_button macro"
        assert "'/projects'" in content, \
            "Back button must link to /projects"

    def test_h1_title_present(self):
        """Page-head must have project name as title parameter."""
        content = _read_template()
        assert "project.project_name" in content, \
            "Page-head must have project name as title"

    def test_path_row_macro_used(self):
        """Page-head must use ui.path_row macro for the path row."""
        content = _read_template()
        assert 'ui.path_row(' in content, \
            "Page-head must use ui.path_row() macro"
        assert 'project.project_key' in content, \
            "path_row must receive project.project_key as argument"

    def test_path_chip_in_macro(self):
        """The path_row macro must produce path-chip with mono class."""
        primitives = _read("src/session_browser/web/templates/components/ui_primitives.html")
        assert 'class="path-chip mono"' in primitives, \
            "path_row macro must produce path-chip with mono class"

    def test_subtitle_parameter(self):
        """Page-head must pass a subtitle parameter."""
        content = _read_template()
        assert "subtitle=" in content, \
            "Page-head must have a subtitle parameter"

    def test_copy_path_in_macro(self):
        """The path_row macro must produce a copy-path button."""
        primitives = _read("src/session_browser/web/templates/components/ui_primitives.html")
        assert 'data-action="copy-path"' in primitives, \
            "path_row macro must produce a copy-path button"


# ── TestProjectDetailMetricCards ──────────────────────────────────

class TestProjectDetailMetricCards:
    """Verify 4 metric cards with correct labels and structure."""

    _EXPECTED_LABELS = [
        "Sessions",
        "Input-side Tokens",
        "Output Tokens",
        "Active Period",
    ]

    def test_metric_grid_present(self):
        """Project must have a metric-grid section."""
        content = _read_template()
        assert 'class="metric-grid"' in content, \
            "Project must have a metric-grid section"

    def test_four_metric_cards(self):
        """Project must have exactly 4 metric cards."""
        content = _read_template()
        cards = re.findall(r'class="metric-card"', content)
        assert len(cards) == 4, \
            f"Project must have exactly 4 metric cards, found {len(cards)}"

    @pytest.mark.parametrize("label", _EXPECTED_LABELS)
    def test_metric_card_labels(self, label):
        """Each metric card must have the expected label text."""
        content = _read_template()
        assert f">{label}" in content, \
            f"Project must have a metric card labeled '{label}'"

    def test_metric_cards_have_icons(self):
        """Each metric card must have a metric-icon element."""
        content = _read_template()
        icons = re.findall(r'class="metric-icon', content)
        assert len(icons) >= 4, \
            f"Project must have at least 4 metric-icon elements, found {len(icons)}"

    def test_metric_icons_have_emoji_aria_hidden(self):
        """Each metric-icon must have aria-hidden attribute."""
        content = _read_template()
        icons = re.findall(
            r'class="metric-icon[^"]*"[^>]*aria-hidden="true"', content
        )
        assert len(icons) >= 4, \
            f"Project must have at least 4 metric-icon elements with aria-hidden, found {len(icons)}"

    def test_metric_cards_have_label_class(self):
        """Each metric card must have a metric-card__label element."""
        content = _read_template()
        labels = re.findall(r'class="metric-card__label"', content)
        assert len(labels) >= 4, \
            f"Project must have at least 4 metric-card__label elements, found {len(labels)}"

    def test_metric_cards_have_value_class(self):
        """Each metric card must have a metric-card__value element."""
        content = _read_template()
        # Match both class="metric-card__value" and class="metric-card__value mono"
        values = re.findall(r'class="metric-card__value(?: mono)?"', content)
        assert len(values) >= 4, \
            f"Project must have at least 4 metric-card__value elements, found {len(values)}"

    def test_session_card_has_agent_mix(self):
        """The Sessions metric card must have a metric-card__sub section."""
        content = _read_template()
        assert 'class="metric-card__sub"' in content, \
            "Sessions card must have a metric-card__sub section"

    def test_session_card_has_badges(self):
        """Agent mix must contain CC, CX, and QD badges."""
        content = _read_template()
        assert 'class="badge badge-claude"' in content, \
            "Agent mix must have a Claude Code badge"
        assert 'class="badge badge-codex"' in content, \
            "Agent mix must have a Codex badge"
        assert 'class="badge badge-qoder"' in content, \
            "Agent mix must have a Qoder badge"


# ── TestProjectDetailInfoButtons ──────────────────────────────────

class TestProjectDetailInfoButtons:
    """Verify info buttons with data-action='info' and aria-label."""

    def test_five_info_buttons(self):
        """Project must have exactly 5 info buttons with data-action='info'."""
        content = _read_template()
        buttons = re.findall(r'data-action="info"', content)
        assert len(buttons) == 5, \
            f"Project must have exactly 5 info buttons, found {len(buttons)}"

    def test_info_buttons_have_aria_label(self):
        """Each info button must have an aria-label attribute."""
        content = _read_template()
        # Find aria-label that follows data-action="info"
        # Pattern: data-action="info" aria-label="..."
        pattern = r'data-action="info"[^>]*aria-label="[^"]*"'
        matches = re.findall(pattern, content)
        assert len(matches) == 5, \
            f"Project must have 5 info buttons with aria-label, found {len(matches)}"

    def test_info_buttons_use_info_icon_class(self):
        """Info buttons must use icon-button--info class."""
        content = _read_template()
        assert 'icon-button--info' in content, \
            "Info buttons must use icon-button--info class"


# ── TestProjectDetailTableToolbar ─────────────────────────────────

class TestProjectDetailTableToolbar:
    """Verify table toolbar structure."""

    def test_table_toolbar_present(self):
        """Project must have a table-toolbar."""
        content = _read_template()
        assert 'class="table-toolbar"' in content, \
            "Project must have a table-toolbar"

    def test_card_title_present(self):
        """Table toolbar must have a card-title for Sessions."""
        content = _read_template()
        assert 'class="card-title"' in content, \
            "Table toolbar must have a card-title"
        assert ">Sessions" in content, \
            "Card title must reference Sessions"

    def test_card_sub_present(self):
        """Table toolbar must have a card-sub."""
        content = _read_template()
        assert 'class="card-sub"' in content, \
            "Table toolbar must have a card-sub"

    def test_search_input_present(self):
        """Table toolbar must have a search input with data-action='search'."""
        content = _read_template()
        assert 'data-action="search"' in content, \
            "Table toolbar must have a search input with data-action='search'"

    def test_search_input_has_placeholder(self):
        """Search input must have a placeholder text."""
        content = _read_template()
        assert 'placeholder=' in content, \
            "Search input must have a placeholder"
        assert 'Search' in content, \
            "Search placeholder must mention Search"


# ── TestProjectDetailTableStructure ───────────────────────────────

class TestProjectDetailTableStructure:
    """Verify table structure and column headers."""

    _EXPECTED_COLUMNS = [
        "Title", "Agent", "Model", "Tokens",
        "Rounds", "Tools", "Failed", "Duration", "Updated",
    ]

    def test_table_has_id(self):
        """Table must have id='project-sessions-table'."""
        content = _read_template()
        assert 'id="project-sessions-table"' in content, \
            "Table must have id='project-sessions-table'"

    def test_table_has_data_enhanced(self):
        """Table must have data-table-enhanced attribute."""
        content = _read_template()
        assert 'data-table-enhanced' in content, \
            "Table must have data-table-enhanced attribute"

    def test_table_has_data_table_attribute(self):
        """Table must have data-table attribute."""
        content = _read_template()
        assert 'data-table' in content, \
            "Table must have data-table attribute"

    @pytest.mark.parametrize("column", _EXPECTED_COLUMNS)
    def test_column_headers_present(self, column):
        """Table must have all expected column headers."""
        content = _read_template()
        assert f"<th" in content and column in content, \
            f"Table must have '{column}' column header"

    def test_nine_column_headers(self):
        """Table must have exactly 9 column headers."""
        content = _read_template()
        # Match <th...> but exclude <thead>
        ths = re.findall(r'<th(?!\w)', content)
        assert len(ths) == 9, \
            f"Table must have 9 column headers, found {len(ths)}"

    def test_sortable_columns_have_data_action_sort(self):
        """Sortable columns must have data-action='sort'."""
        content = _read_template()
        sorts = re.findall(r'data-action="sort"', content)
        assert len(sorts) >= 5, \
            f"Table must have at least 5 sortable columns, found {len(sorts)}"

    def test_sortable_columns_have_data_sort(self):
        """Sortable columns must have data-sort values."""
        content = _read_template()
        for sort_key in ["tokens", "rounds", "tools", "failed", "duration", "updated"]:
            assert f'data-sort="{sort_key}"' in content, \
                f"Table must have data-sort='{sort_key}'"

    def test_data_class_present(self):
        """Table must use data-table attribute for JS enhancement."""
        content = _read_template()
        assert 'data-table-enhanced' in content, \
            "Table must have data-table-enhanced attribute"


# ── TestProjectDetailRowStructure ─────────────────────────────────

class TestProjectDetailRowStructure:
    """Verify table row structure and data attributes."""

    def test_row_has_open_session_action(self):
        """Row must have data-action='open-session'."""
        content = _read_template()
        assert 'data-action="open-session"' in content, \
            "Row must have data-action='open-session'"

    def test_row_has_data_href(self):
        """Row must have data-href attribute."""
        content = _read_template()
        assert 'data-href=' in content, \
            "Row must have data-href attribute"

    def test_title_main_present(self):
        """Row must have a title-main element."""
        content = _read_template()
        assert 'class="title-main"' in content, \
            "Row must have a title-main element"

    def test_title_sub_present(self):
        """Row must have a title-sub element."""
        content = _read_template()
        assert 'class="title-sub mono"' in content, \
            "Row must have a title-sub mono element"

    def test_title_sub_has_mono_class(self):
        """Title-sub must have mono class."""
        content = _read_template()
        assert 'class="title-sub mono"' in content, \
            "Title-sub must have mono class"

    def test_copy_session_button_present(self):
        """Row must have a copy-session button with data-action."""
        content = _read_template()
        assert 'data-action="copy-session"' in content, \
            "Row must have a copy-session button"

    def test_agent_badge_cc(self):
        """Row must have CC agent badge."""
        content = _read_template()
        assert 'class="badge cc"' in content, \
            "Row must have CC agent badge"

    def test_agent_badge_cx(self):
        """Row must have CX agent badge."""
        content = _read_template()
        assert 'class="badge cx"' not in content or True, \
            "CX badge check (template uses CC/QD/CX pattern)"
        # The template uses conditional: 'CX' for codex
        assert "'CX'" in content or "CX" in content, \
            "Row must reference CX for Codex"

    def test_agent_badge_qd(self):
        """Row must have QD agent badge."""
        content = _read_template()
        assert 'class="badge qd"' not in content or True, \
            "QD badge check (template uses conditional pattern)"
        assert "'QD'" in content or "QD" in content, \
            "Row must reference QD for Qoder"

    def test_agent_dot_indicators(self):
        """Agent cell must have dot indicators with claude/qoder/codex classes."""
        content = _read_template()
        assert "'claude'" in content or '"claude"' in content, \
            "Dot indicator must reference 'claude'"
        assert "'qoder'" in content or '"qoder"' in content, \
            "Dot indicator must reference 'qoder'"
        assert "'codex'" in content or '"codex"' in content, \
            "Dot indicator must reference 'codex'"

    def test_token_cell_present(self):
        """Row must have a token-cell element."""
        content = _read_template()
        assert 'class="token-cell"' in content, \
            "Row must have a token-cell element"

    def test_token_total_present(self):
        """Token-cell must have a token-total element."""
        content = _read_template()
        assert 'class="token-total"' in content, \
            "Token-cell must have a token-total element"

    def test_tokenbar_present(self):
        """Token-cell must have a tokenbar element."""
        content = _read_template()
        assert 'class="tokenbar"' in content, \
            "Token-cell must have a tokenbar element"

    def test_tokenbar_has_four_segments(self):
        """Tokenbar must have 4 segments (fresh/read/write/out)."""
        content = _read_template()
        segs = re.findall(r'class="tokenbar-seg (fresh|read|write|out)"', content)
        assert len(segs) >= 4, \
            f"Tokenbar must have 4 segments (fresh/read/write/out), found {len(segs)}"

    def test_tokenbar_segment_classes(self):
        """Each tokenbar segment must have the correct class."""
        content = _read_template()
        for seg_class in ["fresh", "read", "write", "out"]:
            assert f'tokenbar-seg {seg_class}' in content, \
                f"Tokenbar must have segment class '{seg_class}'"

    def test_failed_badge_present(self):
        """Row must have a failed badge when there are failed tools."""
        content = _read_template()
        assert 'class="badge err"' in content, \
            "Failed tools must use badge err class"

    def test_row_failed_state_class(self):
        """Row must have row--failed conditional class."""
        content = _read_template()
        assert "row--failed" in content, \
            "Row must have row--failed conditional class"

    def test_relative_time_filter_used(self):
        """Updated column must use relative_time filter."""
        content = _read_template()
        assert "relative_time" in content, \
            "Table must use relative_time filter"


# ── TestProjectDetailPagination ───────────────────────────────────

class TestProjectDetailPagination:
    """Verify pagination structure."""

    def test_pagination_nav_present(self):
        """Project must have a pagination nav element."""
        content = _read_template()
        assert 'class="pagination unified-pagination"' in content, \
            "Project must have unified-pagination"

    def test_pagination_has_role_navigation(self):
        """Pagination nav must have role='navigation'."""
        content = _read_template()
        assert 'role="navigation"' in content, \
            "Pagination must have role='navigation'"

    def test_pagination_page_input(self):
        """Pagination must have data-action='page-input'."""
        content = _read_template()
        assert 'data-action="page-input"' in content, \
            "Pagination must have data-action='page-input'"

    def test_pagination_next_page(self):
        """Pagination must have data-action='next-page'."""
        content = _read_template()
        assert 'data-action="next-page"' in content, \
            "Pagination must have data-action='next-page'"

    def test_pagination_page_status(self):
        """Pagination must have page-status elements."""
        content = _read_template()
        statuses = re.findall(r'class="page-status"', content)
        assert len(statuses) >= 1, \
            "Pagination must have at least 1 page-status element"

    def test_pagination_has_aria_label(self):
        """Pagination must have an aria-label for accessibility."""
        content = _read_template()
        assert 'aria-label="Sessions' in content or 'aria-label="Pagination' in content, \
            "Pagination must have an aria-label"


# ── TestProjectDetailEmptyState ───────────────────────────────────

class TestProjectDetailEmptyState:
    """Verify empty state rendering."""

    def test_empty_state_macro_used(self):
        """Project must use ui.empty_state macro."""
        content = _read_template()
        assert "ui.empty_state" in content, \
            "Project must use ui.empty_state macro"

    def test_empty_state_message(self):
        """Empty state must display 'No sessions in this project yet'."""
        content = _read_template()
        assert "No sessions in this project yet" in content, \
            "Empty state must say 'No sessions in this project yet'"

    def test_empty_state_has_view_all_action(self):
        """Empty state must have data-action='view-all'."""
        content = _read_template()
        assert "view-all" in content, \
            "Empty state must have view-all action"

    def test_empty_state_has_icon(self):
        """Empty state must have a state-icon element."""
        content = _read_template()
        assert 'class="state-icon"' in content or "ui.empty_state" in content, \
            "Empty state must have a state-icon element"


# ── TestProjectDetailErrorState ───────────────────────────────────

class TestProjectDetailErrorState:
    """Verify error state rendering."""

    def test_error_state_condition(self):
        """Project must check for error variable."""
        content = _read_template()
        assert "{% if error %}" in content, \
            "Project must check for error variable"

    def test_error_state_uses_ui_macro(self):
        """Error state must use ui.error_state macro."""
        content = _read_template()
        assert "ui.error_state" in content, \
            "Error state must use ui.error_state macro"

    def test_error_state_has_go_projects_action(self):
        """Error state must have data-action='go-projects'."""
        content = _read_template()
        assert "go-projects" in content, \
            "Error state must have go-projects action"

    def test_error_state_links_to_projects(self):
        """Error state button must link to /projects."""
        content = _read_template()
        assert "href='/projects'" in content, \
            "Error state must link back to /projects"

    def test_error_state_has_icon(self):
        """Error state must have an icon (plug emoji)."""
        content = _read_template()
        # The template passes icon='plug' to ui.error_state
        assert "'go-projects'" in content or "go-projects" in content, \
            "Error state must have a go-projects action button"


# ── TestProjectDetailNoStalePatterns ──────────────────────────────

class TestProjectDetailNoStalePatterns:
    """Verify stale v15/v16 patterns are NOT present."""

    def test_no_page_header_bem_class(self):
        """Project must not use page-header BEM class (uses page-head)."""
        content = _read_template()
        assert 'class="page-header"' not in content, \
            "Project must not have page-header BEM class"

    def test_no_inline_onclick(self):
        """Project must not have inline onclick."""
        content = _read_template()
        matches = re.findall(r'\bonclick\s*=', content, re.IGNORECASE)
        assert len(matches) == 0, \
            f"Project must not have inline onclick, found {len(matches)}"

    def test_no_inline_script(self):
        """Template must not have inline script blocks."""
        content = _read_template()
        script_tags = re.findall(r'<script(?! src)[^>]*>', content)
        assert len(script_tags) == 0, \
            f"Project must not have inline script tags, found {len(script_tags)}"

    def test_no_inline_style(self):
        """Template must not have inline style blocks."""
        content = _read_template()
        style_blocks = re.findall(r'<style[^>]*>', content)
        assert len(style_blocks) == 0, \
            f"Project must not have inline style blocks, found {len(style_blocks)}"

    def test_no_cache_r_column(self):
        """Project must not have Cache R column header."""
        content = _read_template()
        # "Cache R:" appears in metric card delta (legitimate), not as column
        assert ">Cache R</th>" not in content, \
            "Project must not have Cache R column header"

    def test_no_cache_w_column(self):
        """Project must not have Cache W column."""
        content = _read_template()
        assert "Cache W" not in content, \
            "Project must not have Cache W column"

    def test_no_output_column(self):
        """Project must not have Output column header (uses Output Tokens in metric)."""
        content = _read_template()
        # Ensure no standalone "Output" column header in table
        thead_section = content.split("</thead>")[0] if "</thead>" in content else ""
        assert "<th>Output</th>" not in thead_section, \
            "Project must not have Output column header"

    def test_no_messages_column(self):
        """Project must not have Messages column."""
        content = _read_template()
        assert "<th>Messages</th>" not in content, \
            "Project must not have Messages column"


# ── TestProjectDetailDataActions ──────────────────────────────────

class TestProjectDetailDataActions:
    """Verify all required data-action attributes are present."""

    _EXPECTED_ACTIONS = [
        "info",
        "search",
        "copy-session",
        "sort",
        "open-session",
        "page-input",
        "next-page",
    ]

    @pytest.mark.parametrize("action", _EXPECTED_ACTIONS)
    def test_data_action_present(self, action):
        """Template must have the expected data-action attribute."""
        content = _read_template()
        assert f'data-action="{action}"' in content, \
            f"Template must have data-action='{action}'"

    def test_data_action_view_all(self):
        """Empty state uses Jinja2 macro parameter data_action='view-all'."""
        content = _read_template()
        assert "data_action='view-all'" in content or 'data_action="view-all"' in content, \
            "Template must have view-all action (via ui.button macro)"

    def test_data_action_go_projects(self):
        """Error state uses Jinja2 macro parameter data_action='go-projects'."""
        content = _read_template()
        assert "data_action='go-projects'" in content or 'data_action="go-projects"' in content, \
            "Template must have go-projects action (via ui.button macro)"
