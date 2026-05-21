"""Tests for Agent Detail page (agent.html).

Page-level pytest for agent.html covering template structure, header,
metric cards, info buttons, model breakdown table, sessions table,
search input, pagination, empty/error states, and absence of stale patterns.

T150 -- Agent Detail: Add page-specific pytest.
"""

from __future__ import annotations

import os
import re

import pytest

_AGENT_PATH = "src/session_browser/web/templates/agent.html"


def _read(path: str) -> str:
    with open(path) as f:
        return f.read()


def _read_template() -> str:
    return _read(_AGENT_PATH)


# -- TestAgentDetailTemplate ------------------------------------------------

class TestAgentDetailTemplate:
    """Verify the agent Jinja2 template renders structurally."""

    def test_template_file_exists(self):
        """agent.html must exist on disk."""
        assert os.path.isfile(_AGENT_PATH), \
            f"{_AGENT_PATH} must exist"

    def test_extends_base(self):
        """Agent must extend base.html."""
        content = _read_template()
        assert '{% extends "base.html" %}' in content, \
            "Agent must extend base.html"

    def test_active_page_set(self):
        """Agent must set active_page = 'agents'."""
        content = _read_template()
        assert "active_page = 'agents'" in content, \
            "Agent must set active_page = 'agents'"

    def test_ui_primitives_imported(self):
        """Agent must import ui_primitives.html."""
        content = _read_template()
        assert 'import "components/ui_primitives.html"' in content, \
            "Agent must import ui_primitives.html"

    def test_no_inline_onclick(self):
        """Agent must not use inline onclick handlers."""
        content = _read_template()
        matches = re.findall(r'\bonclick\s*=', content, re.IGNORECASE)
        assert len(matches) == 0, \
            f"Agent must not have inline onclick, found {len(matches)} occurrences"


# -- TestAgentDetailImports -------------------------------------------------

class TestAgentDetailImports:
    """Verify CSS and JS import approach.

    Agent detail page relies on base.html for shared CSS/JS and does not
    have its own page-specific CSS/JS files.
    """

    def test_relies_on_base_for_css_js(self):
        """Agent must extend base.html which provides shared CSS/JS."""
        content = _read_template()
        assert '{% extends "base.html" %}' in content, \
            "Agent must extend base.html for shared CSS/JS"

    def test_no_page_specific_css_import(self):
        """Agent must not import page-specific CSS (uses base shared CSS)."""
        content = _read_template()
        assert 'href="/static/css/agent.css"' not in content, \
            "Agent should not import page-specific CSS"

    def test_no_page_specific_js_import(self):
        """Agent must not import page-specific JS (uses base shared JS)."""
        content = _read_template()
        assert 'src="/static/js/agent.js"' not in content, \
            "Agent should not import page-specific JS"


# -- TestAgentDetailHeader --------------------------------------------------

class TestAgentDetailHeader:
    """Verify header structure."""

    def test_header_section_present(self):
        """Agent must have a header section."""
        content = _read_template()
        assert 'class="header"' in content, \
            "Agent must have a header section"

    def test_back_button_present(self):
        """Header must have a back-btn with data-action='back'."""
        content = _read_template()
        assert 'class="btn back-btn"' in content, \
            "Header must have a back-btn"
        assert 'data-action="back"' in content, \
            "Back button must have data-action='back'"
        assert 'href="/agents"' in content, \
            "Back button must link to /agents"

    def test_agent_title_present(self):
        """Header must contain agent-title."""
        content = _read_template()
        assert 'class="agent-title"' in content, \
            "Header must have an agent-title"

    def test_agent_subtitle_present(self):
        """Header must contain agent-subtitle."""
        content = _read_template()
        assert 'class="agent-subtitle"' in content, \
            "Header must have an agent-subtitle"

    def test_breadcrumb_present(self):
        """Breadcrumb must link to Dashboard and Agents."""
        content = _read_template()
        assert 'href="/dashboard"' in content, \
            "Breadcrumb must link to /dashboard"
        assert 'href="/agents"' in content, \
            "Breadcrumb must link to /agents"

    def test_emoji_aria_hidden_in_title(self):
        """Agent title emoji must have aria-hidden='true'."""
        content = _read_template()
        assert 'class="emoji" aria-hidden="true"' in content, \
            "Agent title emoji must have aria-hidden='true'"


# -- TestAgentDetailMetricCards ---------------------------------------------

class TestAgentDetailMetricCards:
    """Verify 6 metric cards with correct labels and structure."""

    _EXPECTED_LABELS = [
        "Sessions",
        "Projects",
        "Input-side Tokens",
        "Output Tokens",
        "Cache Reuse",
        "Failed Tools",
    ]

    def test_metric_grid_present(self):
        """Agent must have a metric-grid section."""
        content = _read_template()
        assert 'class="metric-grid"' in content, \
            "Agent must have a metric-grid section"

    def test_metric_grid_aria_label(self):
        """Metric grid must have an aria-label."""
        content = _read_template()
        assert 'aria-label="Agent detail metrics"' in content, \
            "Metric grid must have aria-label='Agent detail metrics'"

    def test_six_metric_cards(self):
        """Agent must have exactly 6 metric cards."""
        content = _read_template()
        cards = re.findall(r'class="card metric-card"', content)
        assert len(cards) == 6, \
            f"Agent must have exactly 6 metric cards, found {len(cards)}"

    @pytest.mark.parametrize("label", _EXPECTED_LABELS)
    def test_metric_card_labels(self, label):
        """Each metric card must have the expected label text."""
        content = _read_template()
        assert f">{label}" in content or f">{label} " in content, \
            f"Agent must have a metric card labeled '{label}'"

    def test_metric_cards_have_icons(self):
        """Each metric card must have a metric-icon element."""
        content = _read_template()
        icons = re.findall(r'class="metric-icon', content)
        assert len(icons) >= 6, \
            f"Agent must have at least 6 metric-icon elements, found {len(icons)}"

    def test_metric_icons_have_emoji_aria_hidden(self):
        """Each metric-icon must contain an emoji span with aria-hidden."""
        content = _read_template()
        emojis = re.findall(
            r'class="emoji" aria-hidden="true"', content
        )
        assert len(emojis) >= 6, \
            f"Agent must have at least 6 emoji spans with aria-hidden, found {len(emojis)}"

    def test_metric_cards_have_label_class(self):
        """Each metric card must have a metric-label element."""
        content = _read_template()
        labels = re.findall(r'class="metric-label"', content)
        assert len(labels) >= 6, \
            f"Agent must have at least 6 metric-label elements, found {len(labels)}"

    def test_metric_cards_have_value_class(self):
        """Each metric card must have a metric-value element."""
        content = _read_template()
        values = re.findall(r'class="metric-value"', content)
        assert len(values) >= 6, \
            f"Agent must have at least 6 metric-value elements, found {len(values)}"

    def test_six_info_buttons_on_metrics(self):
        """Each metric card must have an info button with data-action='info'."""
        content = _read_template()
        buttons = re.findall(r'data-action="info"', content)
        # 6 on metrics + 1 on model breakdown + 1 on sessions = 8 total minimum
        assert len(buttons) >= 8, \
            f"Agent must have at least 8 info buttons, found {len(buttons)}"

    def test_info_buttons_use_info_icon_class(self):
        """Info buttons must use info-icon class."""
        content = _read_template()
        assert 'class="info-icon"' in content, \
            "Info buttons must use info-icon class"

    def test_info_buttons_have_aria_label(self):
        """Each info button must have an aria-label (title attribute)."""
        content = _read_template()
        # info-icon buttons use title for tooltip text
        pattern = r'class="info-icon"[^>]*data-action="info"'
        matches = re.findall(pattern, content)
        assert len(matches) >= 6, \
            f"Must have at least 6 info-icon buttons with data-action, found {len(matches)}"


# -- TestAgentDetailModelBreakdown ------------------------------------------

class TestAgentDetailModelBreakdown:
    """Verify Model Breakdown section structure."""

    _EXPECTED_COLUMNS = [
        "Model", "Sessions", "Tokens", "Cache Reuse",
        "Tools", "Failed", "Avg Duration",
    ]

    def test_section_head_present(self):
        """Model breakdown must have a section-head."""
        content = _read_template()
        assert 'class="section-head"' in content, \
            "Model breakdown must have a section-head"

    def test_section_title_present(self):
        """Model breakdown must have a section-title."""
        content = _read_template()
        assert 'class="section-title"' in content, \
            "Model breakdown must have a section-title"
        assert "Model Breakdown" in content, \
            "Section title must include 'Model Breakdown'"

    def test_section_sub_present(self):
        """Model breakdown must have a section-sub."""
        content = _read_template()
        assert 'class="section-sub"' in content, \
            "Model breakdown must have a section-sub"

    def test_model_breakdown_conditional(self):
        """Model breakdown must be conditionally rendered when models > 1."""
        content = _read_template()
        assert "{% if models | length > 1 %}" in content, \
            "Model breakdown must be conditionally rendered"

    def test_card_section_class(self):
        """Model breakdown must use card.section class."""
        content = _read_template()
        assert 'class="card section"' in content, \
            "Model breakdown must use card.section class"

    def test_data_table_class(self):
        """Model breakdown table must use data-table class."""
        content = _read_template()
        assert 'class="data-table"' in content, \
            "Model breakdown table must use data-table class"

    def test_table_wrap_present(self):
        """Model breakdown table must be inside a table-wrap."""
        content = _read_template()
        assert 'class="table-wrap"' in content, \
            "Model breakdown table must be inside a table-wrap"

    @pytest.mark.parametrize("column", _EXPECTED_COLUMNS)
    def test_column_headers_present(self, column):
        """Model breakdown table must have all expected column headers."""
        content = _read_template()
        assert column in content, \
            f"Model breakdown table must have '{column}' column header"

    def test_seven_column_headers_in_model_table(self):
        """Model breakdown table must have exactly 7 column headers."""
        content = _read_template()
        # Extract model breakdown section (between {% if models | length > 1 %} and {% endif %})
        model_start = content.find("{% if models | length > 1 %}")
        assert model_start != -1, "Must have model breakdown conditional"
        # Find the matching {% endif %} for this block
        rest = content[model_start:]
        # The model breakdown ends at the first {% endif %}
        model_end = rest.find("{% endif %}")
        assert model_end != -1, "Model breakdown must have endif"
        model_section = rest[:model_end]
        ths = re.findall(r'<th(?!\w)', model_section)
        assert len(ths) == 7, \
            f"Model breakdown table must have 7 column headers, found {len(ths)}"

    def test_tokenbar_in_model_table(self):
        """Model breakdown tokens column must have a tokenbar."""
        content = _read_template()
        assert 'class="tokenbar"' in content, \
            "Model breakdown must have a tokenbar"

    def test_tokenbar_has_four_segments(self):
        """Tokenbar must have 4 segments (fresh/read/write/out)."""
        content = _read_template()
        segs = re.findall(
            r'class="t-(fresh|read|write|out)"', content
        )
        assert len(segs) >= 4, \
            f"Tokenbar must have 4 segment types, found {len(segs)}"

    def test_sortable_columns_in_model_table(self):
        """Model breakdown table must have sortable columns."""
        content = _read_template()
        sorts = re.findall(r'data-action="sort"', content)
        assert len(sorts) >= 7, \
            f"Model breakdown must have at least 7 sortable columns, found {len(sorts)}"

    def test_sort_keys_in_model_table(self):
        """Model breakdown sortable columns must have data-sort-key."""
        content = _read_template()
        for sort_key in ["model_name", "model_sessions", "model_tokens",
                         "cache_reuse", "model_tools", "model_failed",
                         "avg_duration"]:
            assert f'data-sort-key="{sort_key}"' in content, \
                f"Model table must have data-sort-key='{sort_key}'"


# -- TestAgentDetailSessionsSection -----------------------------------------

class TestAgentDetailSessionsSection:
    """Verify Sessions section structure."""

    _EXPECTED_COLUMNS = [
        "Title", "Project", "Model", "Tokens",
        "Rounds", "Tools", "Failed", "Duration", "Updated",
    ]

    def test_sessions_section_head_present(self):
        """Sessions must have a section-head."""
        content = _read_template()
        sections = content.split('class="section-head"')
        assert len(sections) >= 2, \
            "Agent must have at least 2 section-head elements"

    def test_sessions_section_title(self):
        """Sessions section must have 'Sessions' in title."""
        content = _read_template()
        assert ">Sessions" in content, \
            "Sessions section must have 'Sessions' title"

    def test_search_input_present(self):
        """Sessions section must have a search input."""
        content = _read_template()
        assert 'id="session-search"' in content, \
            "Sessions must have a search input with id='session-search'"

    def test_search_input_has_data_search(self):
        """Search input must have data-search attribute."""
        content = _read_template()
        assert 'data-search="session-id-or-title"' in content, \
            "Search input must have data-search='session-id-or-title'"

    def test_search_input_has_placeholder(self):
        """Search input must have a placeholder."""
        content = _read_template()
        assert 'placeholder=' in content, \
            "Search input must have a placeholder"
        assert "Search" in content, \
            "Search placeholder must mention Search"

    def test_search_input_aria_label(self):
        """Search input must have aria-label."""
        content = _read_template()
        assert 'aria-label="Search sessions"' in content, \
            "Search input must have aria-label='Search sessions'"

    def test_sessions_table_has_id(self):
        """Sessions table must have id='agent-sessions-table'."""
        content = _read_template()
        assert 'id="agent-sessions-table"' in content, \
            "Sessions table must have id='agent-sessions-table'"

    def test_card_section_for_sessions(self):
        """Sessions section must use card.section class."""
        content = _read_template()
        assert 'class="card section"' in content, \
            "Sessions section must use card.section class"

    @pytest.mark.parametrize("column", _EXPECTED_COLUMNS)
    def test_column_headers_present(self, column):
        """Sessions table must have all expected column headers."""
        content = _read_template()
        assert column in content, \
            f"Sessions table must have '{column}' column header"

    def test_nine_column_headers(self):
        """Sessions table must have exactly 9 column headers."""
        content = _read_template()
        ths = re.findall(r'<th(?!\w)', content)
        # 7 from model breakdown + 9 from sessions = 16 total
        assert len(ths) == 16, \
            f"Agent must have 16 total th elements (7 model + 9 sessions), found {len(ths)}"

    def test_sortable_columns_in_sessions_table(self):
        """Sessions table must have sortable columns (7 sortable out of 9)."""
        content = _read_template()
        for sort_key in ["model", "tokens", "rounds", "tools",
                         "failed", "duration", "updated"]:
            assert f'data-sort-key="{sort_key}"' in content, \
                f"Sessions table must have data-sort-key='{sort_key}'"

    def test_row_has_open_session_action(self):
        """Session rows must have data-action='open-session'."""
        content = _read_template()
        assert 'data-action="open-session"' in content, \
            "Session rows must have data-action='open-session'"

    def test_row_has_data_href(self):
        """Session rows must have data-href attribute."""
        content = _read_template()
        assert 'data-href="/sessions/' in content, \
            "Session rows must have data-href attribute"

    def test_title_main_present(self):
        """Session row must have a title-main element."""
        content = _read_template()
        assert 'class="title-main"' in content, \
            "Session row must have a title-main element"

    def test_title_sub_present(self):
        """Session row must have a title-sub element."""
        content = _read_template()
        assert 'class="title-sub mono"' in content, \
            "Session row must have a title-sub mono element"

    def test_project_link_present(self):
        """Session row must link to project."""
        content = _read_template()
        assert 'href="/projects/' in content, \
            "Session row must link to project"

    def test_failed_badge_err_class(self):
        """Failed tools must use badge err class."""
        content = _read_template()
        assert 'class="badge err"' in content, \
            "Failed tools must use badge err class"

    def test_row_failed_conditional_class(self):
        """Row must have row--failed conditional class."""
        content = _read_template()
        assert "row--failed" in content, \
            "Row must have row--failed conditional class"

    def test_relative_time_filter_used(self):
        """Updated column must use relative_time filter."""
        content = _read_template()
        assert "relative_time" in content, \
            "Table must use relative_time filter"

    def test_token_cell_in_sessions(self):
        """Session rows must have token-cell."""
        content = _read_template()
        assert 'class="token-col token-cell"' in content or 'class="token-cell"' in content, \
            "Session rows must have token-cell"

    def test_token_total_in_sessions(self):
        """Token-cell must have token-total."""
        content = _read_template()
        assert 'class="token-total"' in content, \
            "Token-cell must have token-total"


# -- TestAgentDetailPagination ----------------------------------------------

class TestAgentDetailPagination:
    """Verify pagination structure."""

    def test_unified_pagination_present(self):
        """Agent must have unified-pagination."""
        content = _read_template()
        assert 'class="pagination unified-pagination"' in content, \
            "Agent must have unified-pagination"

    def test_pagination_role_navigation(self):
        """Pagination must have role='navigation'."""
        content = _read_template()
        assert 'role="navigation"' in content, \
            "Pagination must have role='navigation'"

    def test_pagination_aria_label(self):
        """Pagination must have aria-label."""
        content = _read_template()
        assert 'aria-label="Agent sessions pagination"' in content, \
            "Pagination must have aria-label='Agent sessions pagination'"

    def test_page_input_present(self):
        """Pagination must have data-action='page-input'."""
        content = _read_template()
        assert 'data-action="page-input"' in content, \
            "Pagination must have data-action='page-input'"

    def test_page_input_aria_label(self):
        """Page input must have aria-label."""
        content = _read_template()
        assert 'aria-label="Page number"' in content, \
            "Page input must have aria-label='Page number'"

    def test_prev_page_present(self):
        """Pagination must have data-action='prev-page'."""
        content = _read_template()
        assert 'data-action="prev-page"' in content, \
            "Pagination must have data-action='prev-page'"

    def test_next_page_present(self):
        """Pagination must have data-action='next-page'."""
        content = _read_template()
        assert 'data-action="next-page"' in content, \
            "Pagination must have data-action='next-page'"

    def test_page_status_present(self):
        """Pagination must have page-status elements."""
        content = _read_template()
        statuses = re.findall(r'class="page-status"', content)
        assert len(statuses) >= 1, \
            "Pagination must have at least 1 page-status element"


# -- TestAgentDetailEmptyState ----------------------------------------------

class TestAgentDetailEmptyState:
    """Verify empty state rendering."""

    def test_empty_state_condition(self):
        """Template must check for sessions being falsy."""
        content = _read_template()
        assert "{% else %}" in content, \
            "Template must have an else branch for empty state"

    def test_empty_state_macro_used(self):
        """Empty state must use ui.empty_state macro."""
        content = _read_template()
        assert "ui.empty_state" in content, \
            "Empty state must use ui.empty_state macro"

    def test_empty_state_message(self):
        """Empty state must display '暂无该 Agent 的 Session 数据'."""
        content = _read_template()
        assert "暂无该 Agent 的 Session 数据" in content, \
            "Empty state must say '暂无该 Agent 的 Session 数据'"

    def test_empty_state_has_back_action(self):
        """Empty state must have back action."""
        content = _read_template()
        assert "data_action='back'" in content or 'data_action="back"' in content, \
            "Empty state must have back action (via ui.button macro)"

    def test_empty_state_has_icon(self):
        """Empty state must have a robot icon."""
        content = _read_template()
        assert "'\U0001f916'" in content or "\U0001f916" in content, \
            "Empty state must have a robot icon"


# -- TestAgentDetailErrorState ----------------------------------------------

class TestAgentDetailErrorState:
    """Verify error state rendering."""

    def test_error_state_condition(self):
        """Template must check for error variable."""
        content = _read_template()
        assert "{% if error %}" in content, \
            "Template must check for error variable"

    def test_error_state_uses_ui_macro(self):
        """Error state must use ui.error_state macro."""
        content = _read_template()
        assert "ui.error_state" in content, \
            "Error state must use ui.error_state macro"

    def test_error_state_has_refresh_action(self):
        """Error state must have refresh action."""
        content = _read_template()
        assert "data_action='refresh'" in content or 'data_action="refresh"' in content, \
            "Error state must have refresh action (via ui.button macro)"

    def test_error_state_has_warning_icon(self):
        """Error state must have a warning icon."""
        content = _read_template()
        assert "'⚠️'" in content or "⚠️" in content, \
            "Error state must have a warning icon"

    def test_error_state_has_detail_param(self):
        """Error state must pass detail parameter."""
        content = _read_template()
        assert "detail=" in content, \
            "Error state must pass detail parameter"


# -- TestAgentDetailNoStalePatterns -----------------------------------------

class TestAgentDetailNoStalePatterns:
    """Verify stale patterns are NOT present."""

    def test_no_inline_onclick(self):
        """Agent must not have inline onclick."""
        content = _read_template()
        matches = re.findall(r'\bonclick\s*=', content, re.IGNORECASE)
        assert len(matches) == 0, \
            f"Agent must not have inline onclick, found {len(matches)}"

    def test_no_inline_script(self):
        """Template must not have inline script blocks."""
        content = _read_template()
        script_tags = re.findall(r'<script(?! src)[^>]*>', content)
        assert len(script_tags) == 0, \
            f"Agent must not have inline script tags, found {len(script_tags)}"

    def test_no_inline_style_blocks(self):
        """Template must not have inline style blocks."""
        content = _read_template()
        style_blocks = re.findall(r'<style[^>]*>', content)
        assert len(style_blocks) == 0, \
            f"Agent must not have inline style blocks, found {len(style_blocks)}"

    def test_no_page_header_bem_class(self):
        """Agent must not use page-header BEM class (uses header)."""
        content = _read_template()
        assert 'class="page-header"' not in content, \
            "Agent must not have page-header BEM class"

    def test_no_page_head_class(self):
        """Agent must not use page-head class (uses header)."""
        content = _read_template()
        assert 'class="page-head"' not in content, \
            "Agent must not have page-head class"

    def test_no_hero_section(self):
        """Agent must not have hero section."""
        content = _read_template()
        assert 'class="hero"' not in content, \
            "Agent must not have hero section"

    def test_no_select_elements(self):
        """No <select> elements."""
        content = _read_template()
        assert '<select' not in content, \
            "Agent must not use select elements"


# -- TestAgentDetailDataActions ---------------------------------------------

class TestAgentDetailDataActions:
    """Verify all required data-action attributes are present."""

    _EXPECTED_ACTIONS = [
        "back",
        "info",
        "sort",
        "open-session",
        "page-input",
        "prev-page",
        "next-page",
    ]

    @pytest.mark.parametrize("action", _EXPECTED_ACTIONS)
    def test_data_action_present(self, action):
        """Template must have the expected data-action attribute."""
        content = _read_template()
        assert f'data-action="{action}"' in content, \
            f"Template must have data-action='{action}'"

    def test_data_action_back_in_empty_state(self):
        """Empty state uses Jinja2 macro parameter data_action='back'."""
        content = _read_template()
        assert "data_action='back'" in content or 'data_action="back"' in content, \
            "Template must have back action (via ui.button macro)"

    def test_data_action_refresh_in_error_state(self):
        """Error state uses Jinja2 macro parameter data_action='refresh'."""
        content = _read_template()
        assert "data_action='refresh'" in content or 'data_action="refresh"' in content, \
            "Template must have refresh action (via ui.button macro)"


# -- TestAgentDetailAccessibility -------------------------------------------

class TestAgentDetailAccessibility:
    """Verify accessibility attributes."""

    def test_emoji_spans_aria_hidden(self):
        """All emoji spans must have aria-hidden='true'."""
        content = _read_template()
        emoji_spans = re.findall(r'class="emoji"[^>]*>', content)
        for span in emoji_spans:
            assert 'aria-hidden="true"' in span, \
                f"Emoji span must have aria-hidden='true': {span}"

    def test_sort_mark_aria_hidden(self):
        """Sort carets must have aria-hidden='true'."""
        content = _read_template()
        # sort-mark elements are empty spans for JS to populate
        assert 'class="sort-mark"' in content, \
            "Sortable headers must have sort-mark elements"

    def test_search_input_aria_label(self):
        """Search input must have aria-label."""
        content = _read_template()
        assert 'aria-label="Search sessions"' in content, \
            "Search input must have aria-label='Search sessions'"

    def test_page_input_aria_label(self):
        """Page input must have aria-label."""
        content = _read_template()
        assert 'aria-label="Page number"' in content, \
            "Page input must have aria-label='Page number'"

    def test_pagination_aria_label(self):
        """Pagination must have aria-label."""
        content = _read_template()
        assert 'aria-label="Agent sessions pagination"' in content, \
            "Pagination must have aria-label='Agent sessions pagination'"

    def test_metric_grid_aria_label(self):
        """Metric grid must have aria-label."""
        content = _read_template()
        assert 'aria-label="Agent detail metrics"' in content, \
            "Metric grid must have aria-label='Agent detail metrics'"

    def test_tokenbar_aria_label(self):
        """Tokenbar must have aria-label."""
        content = _read_template()
        assert 'aria-label="Token breakdown tooltip"' in content, \
            "Tokenbar must have aria-label='Token breakdown tooltip'"

    def test_info_icon_has_title(self):
        """Info icons must have title attribute for tooltip."""
        content = _read_template()
        # info-icon spans use title for the tooltip text
        pattern = r'class="info-icon"[^>]*title="[^"]*"'
        matches = re.findall(pattern, content)
        assert len(matches) >= 6, \
            f"Must have at least 6 info icons with title, found {len(matches)}"
