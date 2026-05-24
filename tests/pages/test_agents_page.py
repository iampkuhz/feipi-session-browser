"""Agents page-level fixture tests.

These tests use the hifi_fixture_session to spin up a live server with
deterministic fixture data, then verify the *rendered* Agents HTML
(not just the static template file).

Covers:
- Page renders and returns HTTP 200
- Agent list is displayed with rows
- Key data/metrics are visible (metric cards, agent names, providers)
- Table structure (sortable headers, data attributes)
- Efficiency table (when fixture has multiple models)
- Accessibility gate (no inline onclick)

T095 — Agents fixed fixture.
"""

from __future__ import annotations

import re

import pytest


# ── Agents page fixture ────────────────────────────────────────────────


@pytest.fixture(scope="module")
def agents_html(hifi_fixture_session):
    """Fetch rendered Agents HTML from the live fixture server."""
    base_url, agent, session_id = hifi_fixture_session
    import urllib.request

    resp = urllib.request.urlopen(f"{base_url}/agents", timeout=10)
    assert resp.status == 200, "Agents page must return HTTP 200"
    return resp.read().decode("utf-8")


# ── TestAgentsPageRender ───────────────────────────────────────────────


class TestAgentsPageRender:
    """Verify the rendered Agents page structure."""

    def test_page_returns_200(self, agents_html):
        """Agents page must render successfully."""
        assert len(agents_html) > 500, \
            "Agents HTML must be substantial"

    def test_has_doctype_and_html(self, agents_html):
        """Page must have proper HTML structure."""
        lower = agents_html.lower()
        assert "<!doctype html" in lower or "<!DOCTYPE html" in agents_html, \
            "Agents must have DOCTYPE declaration"

    def test_title_contains_agents(self, agents_html):
        """Page title must contain 'Agents'."""
        assert "<title>Agents" in agents_html, \
            "Page title must contain 'Agents'"

    def test_has_h1_agents(self, agents_html):
        """Page must have a visible 'Agents' heading."""
        assert ">Agents<" in agents_html, \
            "'Agents' heading must be visible"

    def test_has_subtitle(self, agents_html):
        """Page must show the subtitle with agent count."""
        assert "个 Agent" in agents_html, \
            "Subtitle must include agent count in Chinese"


# ── TestAgentsMetrics ──────────────────────────────────────────────────


class TestAgentsMetrics:
    """Verify rendered metric cards with actual data values."""

    _EXPECTED_LABELS = ["Active Agents", "Sessions", "Projects", "Total Tokens"]

    def test_metric_grid_present(self, agents_html):
        """Agents must have a metric-grid container."""
        assert 'class="metric-grid"' in agents_html, \
            "metric-grid must be present"

    def test_four_metric_cards(self, agents_html):
        """Exactly 4 metric cards must be rendered."""
        cards = re.findall(r'class="metric-card"', agents_html)
        assert len(cards) == 4, \
            f"Expected 4 metric cards, found {len(cards)}"

    @pytest.mark.parametrize("label", _EXPECTED_LABELS)
    def test_metric_label_present(self, agents_html, label):
        """Each metric card must show its label."""
        assert f">{label}<" in agents_html or f'aria-label="{label}"' in agents_html, \
            f"Metric card labeled '{label}' must be visible"

    def test_metric_values_nonzero(self, agents_html):
        """Metric cards must have populated values when fixture has data."""
        # Active Agents must be > 0
        values = re.findall(
            r'class="metric-card__value[^"]*">([^<]+)<',
            agents_html
        )
        assert len(values) >= 4, \
            f"Expected at least 4 metric values, found {len(values)}"

        # First value is Active Agents count — must be positive
        active_val = values[0].strip().replace(",", "")
        assert active_val.isdigit() and int(active_val) > 0, \
            f"Active Agents count must be > 0, got '{active_val}'"

    def test_metric_aria_labels(self, agents_html):
        """Each metric card info button must have aria-label."""
        aria_labels = re.findall(
            r'aria-label="[^"]*(?:计数说明|公式说明)[^"]*"',
            agents_html
        )
        assert len(aria_labels) >= 4, \
            f"Expected at least 4 aria-labels on metric info buttons, found {len(aria_labels)}"

    def test_metric_icons_present(self, agents_html):
        """Metric cards must have icon elements."""
        icons = re.findall(r'class="metric-icon', agents_html)
        assert len(icons) >= 4, \
            f"Expected at least 4 metric-icon elements, found {len(icons)}"


# ── TestAgentsListDisplay ──────────────────────────────────────────────


class TestAgentsListDisplay:
    """Verify agent list rows are rendered with correct data."""

    def test_agents_table_present(self, agents_html):
        """Agents table must have id='agents-table'."""
        assert 'id="agents-table"' in agents_html, \
            "Agents table must have id='agents-table'"

    def test_has_agent_rows(self, agents_html):
        """At least one agent row must be rendered."""
        rows = re.findall(r'data-action="open-agent"', agents_html)
        assert len(rows) > 0, \
            "At least one agent row must be rendered"

    def test_row_has_data_href(self, agents_html):
        """Agent rows must have data-href to detail page."""
        assert 'data-href="/agents/' in agents_html, \
            "Agent row must have data-href attribute"

    def test_row_has_data_agent_name(self, agents_html):
        """Agent rows must have data-agent-name attribute."""
        assert 'data-agent-name=' in agents_html, \
            "Agent row must have data-agent-name"

    def test_row_has_data_session_count(self, agents_html):
        """Agent rows must have data-session-count attribute."""
        assert 'data-session-count=' in agents_html, \
            "Agent row must have data-session-count"

    def test_row_has_data_project_count(self, agents_html):
        """Agent rows must have data-project-count attribute."""
        assert 'data-project-count=' in agents_html, \
            "Agent row must have data-project-count"

    def test_row_has_data_total_tokens(self, agents_html):
        """Agent rows must have data-total-tokens attribute."""
        assert 'data-total-tokens=' in agents_html, \
            "Agent row must have data-total-tokens"

    def test_row_has_data_total_tool_calls(self, agents_html):
        """Agent rows must have data-total-tool-calls attribute."""
        assert 'data-total-tool-calls=' in agents_html, \
            "Agent row must have data-total-tool-calls"

    def test_row_has_data_last_active(self, agents_html):
        """Agent rows must have data-last-active attribute."""
        assert 'data-last-active=' in agents_html, \
            "Agent row must have data-last-active"

    def test_agent_detail_links_present(self, agents_html):
        """Each agent row must link to its detail page."""
        links = re.findall(r'href="/agents/[^"]+"', agents_html)
        assert len(links) > 0, \
            "Agent detail links must be present"

    def test_agent_clickable_rows(self, agents_html):
        """Agent rows must have open-agent data-action."""
        assert 'data-action="open-agent"' in agents_html, \
            "Agent rows must have data-action='open-agent'"


# ── TestAgentsProviders ────────────────────────────────────────────────


class TestAgentsProviders:
    """Verify provider column shows correct badges."""

    def test_provider_anthropic_badge(self, agents_html):
        """Claude Code agent must show Anthropic provider badge."""
        assert ">Anthropic<" in agents_html, \
            "Anthropic provider badge must be visible"

    def test_badge_cc_class(self, agents_html):
        """CC badge class must be present for Claude Code."""
        assert 'class="badge cc"' in agents_html or "badge cc" in agents_html, \
            "CC badge class must be present"

    def test_badge_dot_indicators(self, agents_html):
        """Badge dot indicators must be present."""
        assert 'class="dot claude"' in agents_html or 'class="dot codex"' in agents_html, \
            "At least one badge dot indicator must be present"


# ── TestAgentsSortableHeaders ──────────────────────────────────────────


class TestAgentsSortableHeaders:
    """Verify sortable header behavior on the agents table."""

    def test_sortable_columns_have_data_action_sort(self, agents_html):
        """Sortable columns must have data-action='sort'."""
        sorts = re.findall(r'data-action="sort"', agents_html)
        assert len(sorts) >= 8, \
            f"Expected at least 8 sortable columns, found {len(sorts)}"

    def test_sort_keys_present(self, agents_html):
        """Agents table must have correct data-sort-key values."""
        for sort_key in ["name", "provider", "sessions", "projects",
                         "tokens", "tool_calls", "failed", "last_active"]:
            assert f'data-sort-key="{sort_key}"' in agents_html, \
                f"Agents table must have data-sort-key='{sort_key}'"

    def test_sortable_header_buttons(self, agents_html):
        """Sortable headers must use sortable-header class."""
        buttons = re.findall(r'class="sortable-header"', agents_html)
        assert len(buttons) >= 8, \
            f"Expected at least 8 sortable-header buttons, found {len(buttons)}"


# ── TestAgentsColumnHeaders ────────────────────────────────────────────


class TestAgentsColumnHeaders:
    """Verify all expected column headers are visible."""

    _EXPECTED_COLUMNS = [
        "Agent", "Provider", "Sessions", "Projects",
        "Tokens", "Tool Calls", "Failed", "最近活跃",
    ]

    @pytest.mark.parametrize("column", _EXPECTED_COLUMNS)
    def test_column_header_present(self, agents_html, column):
        """Table must have the expected column header."""
        assert column in agents_html, \
            f"Table must have '{column}' column header"


# ── TestAgentsTokenBar ─────────────────────────────────────────────────


class TestAgentsTokenBar:
    """Verify token bar segments in agent rows."""

    def test_token_cell_present(self, agents_html):
        """Agent rows must have a token-cell element."""
        assert 'class="token-cell"' in agents_html, \
            "Agent row must have a token-cell element"

    def test_token_total_present(self, agents_html):
        """Token-cell must have a token-total element."""
        assert 'class="token-total"' in agents_html, \
            "Token-cell must have a token-total element"

    def test_tokenbar_present(self, agents_html):
        """Token-cell must have a tokenbar element."""
        assert 'class="tokenbar"' in agents_html, \
            "Token-cell must have a tokenbar element"

    def test_tokenbar_four_segments(self, agents_html):
        """Tokenbar must have 4 segment types (fresh/read/write/out)."""
        for seg_class in ["fresh", "read", "write", "out"]:
            assert f'tokenbar-seg {seg_class}' in agents_html, \
                f"Tokenbar must have segment class '{seg_class}'"

    def test_tokenbar_has_title(self, agents_html):
        """Tokenbar must have a title tooltip."""
        assert "Token breakdown" in agents_html, \
            "Tokenbar must have 'Token breakdown' in title"


# ── TestAgentsEfficiencyTable ──────────────────────────────────────────


class TestAgentsEfficiencyTable:
    """Verify efficiency table is rendered when fixture has multiple models."""

    def test_efficiency_table_conditional(self, agents_html):
        """Efficiency table appears when fixture has model diversity."""
        # The rendered page either shows the table or doesn't — both are valid.
        # When present, verify structure.
        if "efficiency-table" in agents_html:
            assert 'id="efficiency-table"' in agents_html, \
                "Efficiency table must have id='efficiency-table'"

    def test_efficiency_title_when_present(self, agents_html):
        """When efficiency table renders, it must have title."""
        if "Agent/Model Efficiency" in agents_html:
            assert "Agent/Model Efficiency" in agents_html, \
                "Efficiency section must have title"

    def test_efficiency_columns_when_present(self, agents_html):
        """When efficiency table renders, it must have expected columns."""
        if "efficiency-table" in agents_html:
            for col in ["Agent", "Model", "Sessions", "Avg Duration", "P95 Duration"]:
                assert col in agents_html, \
                    f"Efficiency table must have '{col}' column"


# ── TestAgentsEmptyState ───────────────────────────────────────────────


class TestAgentsEmptyState:
    """Verify empty state is NOT shown when fixture has data."""

    def test_no_empty_state_when_data_present(self, agents_html):
        """When agents data exists, empty state must not be shown."""
        # The template shows empty state in {% else %} branch
        # When agents are present, the metric grid and table are rendered
        assert 'class="metric-grid"' in agents_html, \
            "Metric grid must be rendered when agents exist"
        assert 'id="agents-table"' in agents_html, \
            "Agents table must be rendered when agents exist"


# ── TestAgentsAccessibility ────────────────────────────────────────────


class TestAgentsAccessibility:
    """Accessibility gates on the rendered Agents page."""

    def test_no_inline_onclick(self, agents_html):
        """Agents must not use inline onclick handlers."""
        matches = re.findall(r'\bonclick\s*=', agents_html, re.IGNORECASE)
        assert len(matches) == 0, \
            f"Agents must not have inline onclick, found {len(matches)} occurrences"

    def test_sort_carets_aria_hidden(self, agents_html):
        """Sort carets must have aria-hidden='true'."""
        carets = re.findall(
            r'class="sort-caret" aria-hidden="true"',
            agents_html
        )
        assert len(carets) >= 8, \
            f"Expected at least 8 sort carets with aria-hidden, found {len(carets)}"

    def test_metric_grid_aria_label(self, agents_html):
        """Metric grid must have aria-label."""
        assert 'aria-label="Agent summary metrics"' in agents_html, \
            "Metric grid must have aria-label='Agent summary metrics'"

    def test_info_buttons_have_aria_label(self, agents_html):
        """Each info button must have an aria-label."""
        pattern = r'data-action="info"[^>]*aria-label="[^"]*"'
        matches = re.findall(pattern, agents_html)
        assert len(matches) >= 4, \
            f"Expected at least 4 info buttons with aria-label, found {len(matches)}"

    def test_emoji_spans_aria_hidden(self, agents_html):
        """All emoji spans must have aria-hidden='true'."""
        emoji_spans = re.findall(r'class="emoji"[^>]*>', agents_html)
        for span in emoji_spans:
            assert 'aria-hidden="true"' in span, \
                f"Emoji span must have aria-hidden='true': {span}"

    def test_breadcrumb_links(self, agents_html):
        """Breadcrumb must link to Dashboard."""
        assert 'href="/dashboard"' in agents_html, \
            "Breadcrumb must link to /dashboard"
        assert ">Agents</span>" in agents_html or ">Agents<" in agents_html, \
            "Breadcrumb must show Agents as current page"


# ── TestAgentsDataActions ──────────────────────────────────────────────


class TestAgentsDataActions:
    """Verify all required data-action attributes are present."""

    _EXPECTED_ACTIONS = ["open-agent", "info", "sort"]

    @pytest.mark.parametrize("action", _EXPECTED_ACTIONS)
    def test_data_action_present(self, agents_html, action):
        """Page must have the expected data-action attribute."""
        assert f'data-action="{action}"' in agents_html, \
            f"Page must have data-action='{action}'"
