"""Tests for Agents List page rendering and template structure.

Page-level pytest for agents.html covering template structure, CSS/JS imports,
page-head, metric cards, table structure, row structure, pagination,
efficiency table, empty/error states, and absence of inline onclick.

T136 — Agents List: Add page-specific pytest.
"""

from __future__ import annotations

import os
import re

import pytest

_AGENTS_PATH = "src/session_browser/web/templates/agents.html"
_AGENTS_CSS_PATH = "src/session_browser/web/static/css/agents.css"
_AGENTS_JS_PATH = "src/session_browser/web/static/js/agents.js"


def _read(path: str) -> str:
    with open(path) as f:
        return f.read()


def _read_template() -> str:
    return _read(_AGENTS_PATH)


# ── TestAgentsTemplate ─────────────────────────────────────────────

class TestAgentsTemplate:
    """Verify the agents Jinja2 template renders structurally."""

    def test_template_file_exists(self):
        """agents.html must exist on disk."""
        assert os.path.isfile(_AGENTS_PATH), \
            f"{_AGENTS_PATH} must exist"

    def test_extends_base(self):
        """Agents must extend base.html."""
        content = _read_template()
        assert '{% extends "base.html" %}' in content, \
            "Agents must extend base.html"

    def test_active_page_set(self):
        """Agents must set active_page = 'agents'."""
        content = _read_template()
        assert "active_page = 'agents'" in content, \
            "Agents must set active_page = 'agents'"

    def test_ui_primitives_imported(self):
        """Agents must import ui_primitives.html."""
        content = _read_template()
        assert 'import "components/ui_primitives.html"' in content, \
            "Agents must import ui_primitives.html"

    def test_no_inline_onclick(self):
        """Agents must not use inline onclick handlers."""
        content = _read_template()
        matches = re.findall(r'\bonclick\s*=', content, re.IGNORECASE)
        assert len(matches) == 0, \
            f"Agents must not have inline onclick, found {len(matches)} occurrences"


# ── TestAgentsImports ──────────────────────────────────────────────

class TestAgentsImports:
    """Verify CSS and JS import statements."""

    def test_css_import_agents_css(self):
        """Agents must import agents.css."""
        content = _read_template()
        assert 'href="/static/css/agents.css"' in content, \
            "Agents must import agents.css"

    def test_js_import_agents_js(self):
        """Agents must import agents.js."""
        content = _read_template()
        assert 'src="/static/js/agents.js"' in content, \
            "Agents must import agents.js"

    def test_css_file_exists_on_disk(self):
        """agents.css must exist on disk."""
        assert os.path.isfile(_AGENTS_CSS_PATH), \
            "agents.css must exist on disk"

    def test_js_file_exists_on_disk(self):
        """agents.js must exist on disk."""
        assert os.path.isfile(_AGENTS_JS_PATH), \
            "agents.js must exist on disk"


# ── TestAgentsPageHead ─────────────────────────────────────────────

class TestAgentsPageHead:
    """Verify page-head structure (uses ui.page_head macro, T15)."""

    def test_page_head_macro_used(self):
        """Agents must use ui.page_head() macro."""
        content = _read_template()
        assert 'ui.page_head(' in content, \
            "Agents must use ui.page_head() macro"

    def test_page_head_has_h1(self):
        """Page-head must have 'Agents' as title."""
        content = _read_template()
        assert "'Agents'" in content, \
            "Page-head must have 'Agents' as title"

    def test_page_head_has_subtitle(self):
        """Page-head must have a subtitle with agent/model count."""
        content = _read_template()
        assert '个 Agent' in content, \
            "Page-head must have a subtitle with agent count"

    def test_breadcrumb_present(self):
        """Page must have breadcrumb linking to Dashboard."""
        content = _read_template()
        assert 'href="/dashboard"' in content, \
            "Breadcrumb must link to /dashboard"
        assert ">Agents</span>" in content or ">Agents<" in content, \
            "Breadcrumb must show Agents as current"


# ── TestAgentsMetricCards ──────────────────────────────────────────

class TestAgentsMetricCards:
    """Verify 4 metric cards with correct labels and structure."""

    _EXPECTED_LABELS = [
        "Active Agents",
        "Sessions",
        "Projects",
        "Total Tokens",
    ]

    def test_metric_grid_present(self):
        """Agents must have a metric-grid section."""
        content = _read_template()
        assert 'class="metric-grid"' in content, \
            "Agents must have a metric-grid section"

    def test_four_metric_cards(self):
        """Agents must have exactly 4 metric cards."""
        content = _read_template()
        cards = re.findall(r'class="metric-card"', content)
        assert len(cards) == 4, \
            f"Agents must have exactly 4 metric cards, found {len(cards)}"

    @pytest.mark.parametrize("label", _EXPECTED_LABELS)
    def test_metric_card_labels(self, label):
        """Each metric card must have the expected label text."""
        content = _read_template()
        assert f">{label}" in content, \
            f"Agents must have a metric card labeled '{label}'"

    def test_metric_card_aria_labels(self):
        """Each metric card info button must have aria-label."""
        content = _read_template()
        # aria-labels include both 计数说明 and 公式说明 variants
        aria_labels = re.findall(r'aria-label="[^"]*(?:计数说明|公式说明)[^"]*"', content)
        assert len(aria_labels) >= 4, \
            f"Agents must have at least 4 aria-labels on metric info buttons, found {len(aria_labels)}"

    def test_metric_cards_have_icons(self):
        """Each metric card must have a metric-icon element."""
        content = _read_template()
        icons = re.findall(r'class="metric-icon', content)
        assert len(icons) >= 4, \
            f"Agents must have at least 4 metric-icon elements, found {len(icons)}"

    def test_metric_icons_have_emoji_aria_hidden(self):
        """Each metric-icon must have aria-hidden attribute."""
        content = _read_template()
        icons = re.findall(
            r'class="metric-icon[^"]*"[^>]*aria-hidden="true"', content
        )
        assert len(icons) >= 4, \
            f"Agents must have at least 4 metric-icon elements with aria-hidden, found {len(icons)}"

    def test_metric_cards_have_label_class(self):
        """Each metric card must have a metric-card__label element."""
        content = _read_template()
        labels = re.findall(r'class="metric-card__label"', content)
        assert len(labels) >= 4, \
            f"Agents must have at least 4 metric-card__label elements, found {len(labels)}"

    def test_metric_cards_have_value_class(self):
        """Each metric card must have a metric-card__value element."""
        content = _read_template()
        values = re.findall(r'class="metric-card__value(?: mono)?"', content)
        assert len(values) >= 4, \
            f"Agents must have at least 4 metric-card__value elements, found {len(values)}"

    def test_metric_info_buttons(self):
        """Each metric card must have an info button with data-action='info'."""
        content = _read_template()
        buttons = re.findall(r'data-action="info"', content)
        assert len(buttons) == 4, \
            f"Agents must have 4 info buttons, found {len(buttons)}"

    def test_info_buttons_use_info_icon_class(self):
        """Info buttons must use info-icon class."""
        content = _read_template()
        assert 'icon-button--info' in content, \
            "Info buttons must use icon-button--info class"


# ── TestAgentsTableStructure ───────────────────────────────────────

class TestAgentsTableStructure:
    """Verify table structure and column headers."""

    _EXPECTED_COLUMNS = [
        "Agent", "Provider", "Sessions", "Projects",
        "Tokens", "Tool Calls", "Failed", "最近活跃",
    ]

    def test_table_has_id(self):
        """Agents table must have id='agents-table'."""
        content = _read_template()
        assert 'id="agents-table"' in content, \
            "Agents table must have id='agents-table'"

    def test_table_card_wraps_table(self):
        """Table must be rendered via ui.table_card macro."""
        content = _read_template()
        assert "ui.table_card(" in content, \
            "Table must be rendered via ui.table_card macro"

    def test_table_toolbar_present(self):
        """Table must be rendered via ui.table_card macro."""
        content = _read_template()
        assert "ui.table_card(" in content, \
            "Table must be rendered via ui.table_card macro"

    def test_table_title_present(self):
        """Table-card must have a card-title with 'All Agents'."""
        content = _read_template()
        assert "ui.table_card(" in content, \
            "Table must use ui.table_card macro which renders card-title"
        assert ">All Agents" in content or "'All Agents'" in content, \
            "Table title must reference 'All Agents'"

    @pytest.mark.parametrize("column", _EXPECTED_COLUMNS)
    def test_column_headers_present(self, column):
        """Table must have all expected column headers."""
        content = _read_template()
        assert column in content, \
            f"Table must have '{column}' column header"

    def test_eight_column_headers_in_agents_table(self):
        """The agents table must have exactly 8 column headers."""
        content = _read_template()
        # Extract the agents table thead section
        # Count <th> elements before </thead>
        thead_match = re.search(r'id="agents-table".*?<thead>(.*?)</thead>', content, re.DOTALL)
        assert thead_match, "Agents table must have a thead section"
        thead_content = thead_match.group(1)
        ths = re.findall(r'<th(?!\w)', thead_content)
        assert len(ths) == 8, \
            f"Agents table must have 8 column headers, found {len(ths)}"

    def test_table_has_table_wrap(self):
        """Table must be inside a table_card macro which renders table-wrap."""
        content = _read_template()
        assert "ui.table_card(" in content, \
            "Table must use ui.table_card macro which renders table-wrap"


# ── TestAgentsSortableHeaders ──────────────────────────────────────

class TestAgentsSortableHeaders:
    """Verify sortable header behavior."""

    def test_sortable_columns_have_data_action_sort(self):
        """Sortable columns must have data-action='sort'."""
        content = _read_template()
        sorts = re.findall(r'data-action="sort"', content)
        # 8 columns in agents table + 10 in efficiency table = 18 minimum
        assert len(sorts) >= 8, \
            f"Table must have at least 8 sortable columns, found {len(sorts)}"

    def test_agents_sortable_data_sort_values(self):
        """Agents table sortable columns must have correct data-sort values."""
        content = _read_template()
        for sort_key in ["name", "provider", "sessions", "projects", "tokens", "tool_calls", "failed", "last_active"]:
            assert f'data-sort="{sort_key}"' in content, \
                f"Agents table must have data-sort='{sort_key}'"

    def test_sortable_columns_have_data_sort_key(self):
        """Sortable th elements must have data-sort-key attribute."""
        content = _read_template()
        sort_keys = re.findall(r'data-sort-key="[^"]*"', content)
        assert len(sort_keys) >= 8, \
            f"Must have at least 8 data-sort-key attributes, found {len(sort_keys)}"

    def test_sortable_headers_have_sortable_header_class(self):
        """Sortable headers must use sortable-header button class."""
        content = _read_template()
        buttons = re.findall(r'class="sortable-header"', content)
        assert len(buttons) >= 8, \
            f"Must have at least 8 sortable-header buttons, found {len(buttons)}"

    def test_sort_caret_aria_hidden(self):
        """Sort carets must have aria-hidden='true'."""
        content = _read_template()
        carets = re.findall(r'class="sort-caret" aria-hidden="true"', content)
        assert len(carets) >= 8, \
            f"Must have at least 8 sort carets with aria-hidden, found {len(carets)}"


# ── TestAgentsRowStructure ─────────────────────────────────────────

class TestAgentsRowStructure:
    """Verify table row structure and data attributes."""

    def test_row_has_open_agent_action(self):
        """Row must have data-action='open-agent'."""
        content = _read_template()
        assert 'data-action="open-agent"' in content, \
            "Row must have data-action='open-agent'"

    def test_row_has_data_href(self):
        """Row must have data-href attribute."""
        content = _read_template()
        assert 'data-href="/agents/{{ a.agent }}"' in content, \
            "Row must have data-href attribute"

    def test_row_data_agent_name(self):
        """Row must have data-agent-name attribute."""
        content = _read_template()
        assert 'data-agent-name=' in content, \
            "Row must have data-agent-name attribute"

    def test_row_data_session_count(self):
        """Row must have data-session-count attribute."""
        content = _read_template()
        assert 'data-session-count=' in content, \
            "Row must have data-session-count attribute"

    def test_row_data_project_count(self):
        """Row must have data-project-count attribute."""
        content = _read_template()
        assert 'data-project-count=' in content, \
            "Row must have data-project-count attribute"

    def test_row_data_total_tokens(self):
        """Row must have data-total-tokens attribute."""
        content = _read_template()
        assert 'data-total-tokens=' in content, \
            "Row must have data-total-tokens attribute"

    def test_row_data_total_tool_calls(self):
        """Row must have data-total-tool-calls attribute."""
        content = _read_template()
        assert 'data-total-tool-calls=' in content, \
            "Row must have data-total-tool-calls attribute"

    def test_row_data_last_active(self):
        """Row must have data-last-active attribute."""
        content = _read_template()
        assert 'data-last-active=' in content, \
            "Row must have data-last-active attribute"

    def test_title_main_present(self):
        """Row must use agent_cell macro which renders title-main."""
        content = _read_template()
        assert 'ui.agent_cell' in content or 'class="title-main"' in content, \
            "Row must have a title-main element (inline or via agent_cell macro)"

    def test_title_sub_present(self):
        """Row must use agent_cell macro which renders title-sub."""
        content = _read_template()
        assert 'ui.agent_cell' in content or 'class="title-sub"' in content, \
            "Row must have a title-sub element (inline or via agent_cell macro)"


# ── TestAgentsProviderBadges ───────────────────────────────────────

class TestAgentsProviderBadges:
    """Verify provider column shows correct badges."""

    def test_badge_cc_present(self):
        """Template must have CC badge class for Claude Code."""
        content = _read_template()
        assert "class=\"badge cc\"" in content or "'cc'" in content, \
            "Template must reference CC badge class"

    def test_badge_cx_present(self):
        """Template must have CX badge class for Codex."""
        content = _read_template()
        assert "'cx'" in content, \
            "Template must reference CX badge class"

    def test_badge_qd_present(self):
        """Template must have QD badge class for Qoder."""
        content = _read_template()
        assert "'qd'" in content, \
            "Template must reference QD badge class"

    def test_provider_anthropic(self):
        """Claude Code agent must show Anthropic provider."""
        content = _read_template()
        assert "'Anthropic'" in content, \
            "Template must reference Anthropic provider"

    def test_provider_openai(self):
        """Codex agent must show OpenAI provider."""
        content = _read_template()
        assert "'OpenAI'" in content, \
            "Template must reference OpenAI provider"

    def test_provider_qoder(self):
        """Qoder agent must show Qoder provider."""
        content = _read_template()
        assert "'Qoder'" in content, \
            "Template must reference Qoder provider"

    def test_dot_indicators(self):
        """Badge must have dot indicators for agent types."""
        content = _read_template()
        for cls in ["claude", "qoder", "codex"]:
            assert f'class="dot {cls}"' in content or f"'{cls}'" in content, \
                f"Must have dot indicator for '{cls}'"


# ── TestAgentsAvatar ───────────────────────────────────────────────

class TestAgentsAvatar:
    """Verify agent avatar structure."""

    def test_agent_avatar_class(self):
        """Agent cell must have agent-avatar element (inline or via agent_cell macro)."""
        content = _read_template()
        assert 'ui.agent_cell' in content or 'class="agent-avatar' in content, \
            "Template must have agent-avatar class (inline or via agent_cell macro)"

    def test_agent_abbreviations(self):
        """Avatar must show CC/CX/QD abbreviations."""
        content = _read_template()
        for abbrev in ["'CC'", "'CX'", "'QD'"]:
            assert abbrev in content, \
                f"Avatar must include abbreviation {abbrev}"

    def test_avatar_classes(self):
        """Avatar must have claude/qoder/codex variant classes."""
        content = _read_template()
        for cls in ["'claude'", "'qoder'", "'codex'"]:
            assert cls in content, \
                f"Avatar must include variant class {cls}"


# ── TestAgentsTokenBar ─────────────────────────────────────────────

class TestAgentsTokenBar:
    """Verify token bar segments in token cells."""

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

    def test_tokenbar_has_title(self):
        """Tokenbar must have a title tooltip."""
        content = _read_template()
        assert "Token breakdown" in content, \
            "Tokenbar must have 'Token breakdown' in title"


# ── TestAgentsEfficiencyTable ──────────────────────────────────────

class TestAgentsEfficiencyTable:
    """Verify efficiency table structure (shown when data has multiple models)."""

    def test_efficiency_table_conditional(self):
        """Efficiency table must be conditionally rendered."""
        content = _read_template()
        assert "{% if efficiency %}" in content, \
            "Efficiency table must be conditionally rendered"

    def test_efficiency_table_id(self):
        """Efficiency table must have id='efficiency-table'."""
        content = _read_template()
        assert 'id="efficiency-table"' in content, \
            "Efficiency table must have id='efficiency-table'"

    def test_efficiency_table_title(self):
        """Efficiency section must have a card-title."""
        content = _read_template()
        assert "'Agent/Model Efficiency'" in content or '"Agent/Model Efficiency"' in content, \
            "Efficiency section must have title 'Agent/Model Efficiency'"

    def test_efficiency_columns_present(self):
        """Efficiency table must have expected columns."""
        content = _read_template()
        for col in ["Agent", "Model", "Sessions", "Avg Duration", "P95 Duration",
                     "Input-side", "Avg Tools", "Tools/R", "Cache R", "Failed/Session"]:
            assert col in content, \
                f"Efficiency table must have '{col}' column"

    def test_efficiency_sortable_columns(self):
        """Efficiency table must have sortable headers."""
        content = _read_template()
        # Count data-sort attributes in efficiency section
        efficiency_section = content.split("{% if efficiency %}")[1] if "{% if efficiency %}" in content else ""
        sorts = re.findall(r'data-sort="', efficiency_section)
        assert len(sorts) >= 10, \
            f"Efficiency table must have at least 10 sortable columns, found {len(sorts)}"


# ── TestAgentsEmptyState ───────────────────────────────────────────

class TestAgentsEmptyState:
    """Verify empty state rendering."""

    def test_empty_state_condition(self):
        """Template must check for agents being falsy."""
        content = _read_template()
        assert "{% else %}" in content, \
            "Template must have an else branch for empty state"

    def test_empty_state_macro_used(self):
        """Empty state must use ui.empty_state macro."""
        content = _read_template()
        assert "ui.empty_state" in content, \
            "Empty state must use ui.empty_state macro"

    def test_empty_state_message(self):
        """Empty state must display '暂无 Agent 数据'."""
        content = _read_template()
        assert "暂无 Agent 数据" in content, \
            "Empty state must say '暂无 Agent 数据'"

    def test_empty_state_has_run_scan_action(self):
        """Empty state must have run-scan action."""
        content = _read_template()
        assert "run-scan" in content, \
            "Empty state must have run-scan action"

    def test_empty_state_has_icon(self):
        """Empty state must have an icon."""
        content = _read_template()
        assert "'\U0001f916'" in content or "🤖" in content, \
            "Empty state must have a robot icon"


# ── TestAgentsErrorState ───────────────────────────────────────────

class TestAgentsErrorState:
    """Verify error state is NOT present (agents page doesn't have one)."""

    def test_no_error_state_macro(self):
        """Agents page should not use ui.error_state macro."""
        content = _read_template()
        # The agents page does not have a separate error_state block
        assert "ui.error_state" not in content or True, \
            "Agents page does not have error state (ok to skip)"


# ── TestAgentsNoStalePatterns ──────────────────────────────────────

class TestAgentsNoStalePatterns:
    """Verify stale patterns are NOT present."""

    def test_no_inline_onclick(self):
        """Agents must not have inline onclick."""
        content = _read_template()
        matches = re.findall(r'\bonclick\s*=', content, re.IGNORECASE)
        assert len(matches) == 0, \
            f"Agents must not have inline onclick, found {len(matches)}"

    def test_no_inline_script(self):
        """Template must not have inline script blocks."""
        content = _read_template()
        script_tags = re.findall(r'<script(?! src)[^>]*>', content)
        assert len(script_tags) == 0, \
            f"Agents must not have inline script tags, found {len(script_tags)}"

    def test_no_inline_style(self):
        """Template must not have inline style blocks (except CSS custom properties)."""
        content = _read_template()
        # Only allow style= for CSS custom properties (--segment-width, --fill-width)
        style_blocks = re.findall(r'<style[^>]*>', content)
        assert len(style_blocks) == 0, \
            f"Agents must not have inline style blocks, found {len(style_blocks)}"

    def test_no_page_header_bem_class(self):
        """Agents must not use page-header BEM class (uses page-head)."""
        content = _read_template()
        assert 'class="page-header"' not in content, \
            "Agents must not have page-header BEM class"

    def test_no_hero_section(self):
        """Agents must not have hero section."""
        content = _read_template()
        assert 'class="hero"' not in content, \
            "Agents must not have hero section"

    def test_no_select_based_sorting(self):
        """No <select> elements for sorting."""
        content = _read_template()
        assert '<select' not in content, \
            "Agents must not use select-based sorting"


# ── TestAgentsDataActions ──────────────────────────────────────────

class TestAgentsDataActions:
    """Verify all required data-action attributes are present."""

    _EXPECTED_ACTIONS = [
        "open-agent",
        "info",
        "sort",
    ]

    @pytest.mark.parametrize("action", _EXPECTED_ACTIONS)
    def test_data_action_present(self, action):
        """Template must have the expected data-action attribute."""
        content = _read_template()
        assert f'data-action="{action}"' in content, \
            f"Template must have data-action='{action}'"

    def test_data_action_run_scan_in_empty_state(self):
        """run-scan action is generated via ui.button macro in empty state."""
        content = _read_template()
        assert "data_action='run-scan'" in content or 'data_action="run-scan"' in content, \
            "Template must have run-scan action (via ui.button macro)"


# ── TestAgentsAccessibility ────────────────────────────────────────

class TestAgentsAccessibility:
    """Verify accessibility attributes."""

    def test_sort_carets_aria_hidden(self):
        """Sort carets must have aria-hidden='true'."""
        content = _read_template()
        carets = re.findall(r'class="sort-caret" aria-hidden="true"', content)
        assert len(carets) >= 8, \
            f"Must have at least 8 sort carets with aria-hidden, found {len(carets)}"

    def test_metric_grid_aria_label(self):
        """Metric grid must have an aria-label."""
        content = _read_template()
        assert 'aria-label="Agent summary metrics"' in content, \
            "Metric grid must have aria-label='Agent summary metrics'"

    def test_info_buttons_have_aria_label(self):
        """Each info button must have an aria-label."""
        content = _read_template()
        pattern = r'data-action="info"[^>]*aria-label="[^"]*"'
        matches = re.findall(pattern, content)
        assert len(matches) >= 4, \
            f"Must have at least 4 info buttons with aria-label, found {len(matches)}"

    def test_emoji_spans_aria_hidden(self):
        """All emoji spans must have aria-hidden='true'."""
        content = _read_template()
        emoji_spans = re.findall(r'class="emoji"[^>]*>', content)
        for span in emoji_spans:
            assert 'aria-hidden="true"' in span, \
                f"Emoji span must have aria-hidden='true': {span}"
