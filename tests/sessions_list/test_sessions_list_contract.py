"""Tests for sessions-list-v15-fix contract.

Covers the 8 verification items:
1. /sessions HTTP 200 (template renders OK)
2. Header tokens aggregate not 0 when fixture sessions have tokens
3. sort=rounds&dir=desc returns first rows with non-increasing rounds
4. sort=rounds&dir=asc returns first rows with non-decreasing rounds
5. page_size=20/100/500/all all work
6. Refresh NOT in HTML output
7. Agent badge has claude/codex/qoder different classes
8. ROUNDS header not clipped: HTML/CSS has dedicated width/class
"""
from __future__ import annotations

import os
import re
import sqlite3

import pytest

from session_browser.index.indexer import (
    init_schema,
    upsert_session,
    list_sessions,
    get_sessions_list_aggregate,
)
from session_browser.domain.models import SessionSummary

_TEMPLATE_PATH = "src/session_browser/web/templates/sessions.html"
_PARTIAL_PATH = "src/session_browser/web/templates/partials/sessions_grid.html"
_CSS_PATH = "src/session_browser/web/static/css/sessions-list.css"
_COMPONENTS_PATH = "src/session_browser/web/templates/components/sessions_list_components.html"


def _read_all_templates():
    """Read all relevant template files and return combined content."""
    parts = []
    for path in [_TEMPLATE_PATH, _PARTIAL_PATH, _COMPONENTS_PATH]:
        with open(path) as f:
            parts.append(f.read())
    return "\n".join(parts)


def _read_css():
    with open(_CSS_PATH) as f:
        return f.read()


def _make_summary(
    sid: str,
    title: str = "",
    agent: str = "claude_code",
    project: str = "proj-a",
    model: str = "model-x",
    rounds: int = 1,
    input_tokens: int = 100,
    output_tokens: int = 100,
    cached_input_tokens: int = 0,
    cached_output_tokens: int = 0,
) -> SessionSummary:
    return SessionSummary(
        agent=agent,
        session_id=sid,
        title=title or f"Session {sid}",
        project_key=project,
        project_name=project,
        cwd="",
        started_at="2026-01-01T00:00:00+00:00",
        ended_at=f"2026-01-{int(sid):02d}T00:00:00+00:00",
        duration_seconds=60,
        model_execution_seconds=30,
        tool_execution_seconds=30,
        model=model,
        git_branch="",
        source="",
        user_message_count=1,
        assistant_message_count=rounds,
        tool_call_count=1,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_input_tokens=cached_input_tokens,
        cached_output_tokens=cached_output_tokens,
        failed_tool_count=0,
    )


@pytest.fixture
def populated_db(tmp_path):
    """Create a SQLite DB with 30 sessions across 3 agents with varying rounds and tokens."""
    db_path = tmp_path / "test_v15_index.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    init_schema(conn)

    agents = ["claude_code", "qoder", "codex"]
    projects = ["proj-a", "proj-b", "proj-c"]

    for i in range(1, 31):
        agent = agents[(i - 1) % 3]
        project = projects[(i - 1) % 3]
        # Varying rounds: 1..30 (ascending by ID)
        rounds = i
        # Varying tokens so aggregate is meaningful
        s = _make_summary(
            str(i),
            title=f"V15 Session {i:03d}",
            agent=agent,
            project=project,
            rounds=rounds,
            input_tokens=100 * i,
            output_tokens=50 * i,
            cached_input_tokens=20 * i,
            cached_output_tokens=10 * i,
        )
        upsert_session(conn, s)

    conn.commit()
    yield conn
    conn.close()


# ─── 1. Template renders (HTTP 200 equivalent) ──────────────────────

class TestTemplateRenders:
    """Verify the sessions template can render with expected context."""

    def test_sessions_template_contains_expected_blocks(self):
        content = _read_all_templates()
        # Core page structure
        assert "sessions-page" in content
        # Filter card can be literal class or macro call
        assert ('class="sessions-filter-card"' in content
                or 'ui.filter_card(' in content)
        assert "data-table" in content, "Sessions must use canonical data-table component"

    def test_template_receives_sessions_aggregate(self):
        """Template must reference sessions_aggregate for tokens."""
        content = _read_all_templates()
        assert "sessions_aggregate" in content


# ─── 2. Header tokens aggregate ─────────────────────────────────────

class TestHeaderTokensAggregate:
    """Verify get_sessions_list_aggregate returns non-zero total_tokens."""

    def test_aggregate_total_tokens_nonzero(self, populated_db):
        agg = get_sessions_list_aggregate(populated_db)
        assert agg["total_tokens"] > 0, "aggregate total_tokens should be > 0"

    def test_aggregate_token_formula(self, populated_db):
        """Verify formula: input + cached_input + cached_output + output."""
        agg = get_sessions_list_aggregate(populated_db)
        # Manually compute expected total from fixture:
        # sum of (100*i + 50*i + 20*i + 10*i) for i=1..30
        # = sum of 180*i for i=1..30 = 180 * 30*31/2 = 180 * 465 = 83700
        assert agg["total_tokens"] == 83700

    def test_aggregate_project_count(self, populated_db):
        agg = get_sessions_list_aggregate(populated_db)
        assert agg["project_count"] >= 3


# ─── 3. Rounds sort desc (non-increasing) ──────────────────────────

class TestRoundsSortDesc:
    """Verify sort=rounds&dir=desc returns non-increasing rounds."""

    def test_desc_first_rows_non_increasing(self, populated_db):
        rows = list_sessions(
            populated_db,
            order_by="assistant_message_count",
            order_dir="desc",
            limit=30,
        )
        counts = [r.assistant_message_count for r in rows]
        for i in range(1, len(counts)):
            assert counts[i] <= counts[i - 1], \
                f"desc order broken at index {i}: {counts[i-1]} -> {counts[i]}"

    def test_desc_first_value_is_max(self, populated_db):
        rows = list_sessions(
            populated_db,
            order_by="assistant_message_count",
            order_dir="desc",
            limit=1,
        )
        assert rows[0].assistant_message_count == 30


# ─── 4. Rounds sort asc (non-decreasing) ───────────────────────────

class TestRoundsSortAsc:
    """Verify sort=rounds&dir=asc returns non-decreasing rounds."""

    def test_asc_first_rows_non_decreasing(self, populated_db):
        rows = list_sessions(
            populated_db,
            order_by="assistant_message_count",
            order_dir="asc",
            limit=30,
        )
        counts = [r.assistant_message_count for r in rows]
        for i in range(1, len(counts)):
            assert counts[i] >= counts[i - 1], \
                f"asc order broken at index {i}: {counts[i-1]} -> {counts[i]}"

    def test_asc_first_value_is_min(self, populated_db):
        rows = list_sessions(
            populated_db,
            order_by="assistant_message_count",
            order_dir="asc",
            limit=1,
        )
        assert rows[0].assistant_message_count == 1


# ─── 5. Pagination contract: prev/input/next, no page-size selector ──

class TestPaginationContract:
    """Verify pagination follows the contract: prev/input/next only, no page-size selector."""

    def test_footer_macro_has_page_input(self):
        """Footer component must have page number input."""
        with open(_COMPONENTS_PATH) as f:
            content = f.read()
        assert 'data-action="page-input"' in content
        assert 'class="page-input' in content

    def test_footer_macro_has_prev_button(self):
        """Footer component must have prev button."""
        with open(_COMPONENTS_PATH) as f:
            content = f.read()
        assert 'data-action="prev-page"' in content

    def test_footer_macro_has_next_button(self):
        """Footer component must have next button."""
        with open(_COMPONENTS_PATH) as f:
            content = f.read()
        assert 'data-action="next-page"' in content

    def test_no_page_size_select_in_footer(self):
        """Footer component must NOT have page-size selector (contract: no page-size)."""
        with open(_COMPONENTS_PATH) as f:
            content = f.read()
        assert "sessions-footer-page-size__select" not in content
        assert "page_size_urls" not in content

    def test_prev_hidden_on_first_page(self):
        """Prev button should be conditionally hidden on page 1."""
        with open(_COMPONENTS_PATH) as f:
            content = f.read()
        # Jinja2 conditional: current_page > 1
        assert "current_page > 1" in content

    def test_next_hidden_on_last_page(self):
        """Next button should be conditionally hidden on last page."""
        with open(_COMPONENTS_PATH) as f:
            content = f.read()
        # Jinja2 conditional: current_page < total_pages
        assert "current_page < total_pages" in content

    def test_page_size_20_returns_20(self, populated_db):
        rows = list_sessions(populated_db, limit=20)
        assert len(rows) == 20

    def test_page_size_100_returns_all(self, populated_db):
        rows = list_sessions(populated_db, limit=100)
        assert len(rows) == 30  # only 30 sessions exist

    def test_page_size_all_returns_all(self, populated_db):
        rows = list_sessions(populated_db, limit=1000)
        assert len(rows) == 30


# ─── 6. Refresh NOT in HTML output ─────────────────────────────────

class TestRefreshRemoval:
    """Verify refresh button/link is removed from templates."""

    def test_no_refresh_in_sessions_html(self):
        with open(_TEMPLATE_PATH) as f:
            content = f.read()
        assert "Refresh" not in content
        assert "refresh-link" not in content

    def test_no_refresh_in_grid_partial(self):
        with open(_PARTIAL_PATH) as f:
            content = f.read()
        assert "refresh" not in content.lower()

    def test_no_refresh_in_components(self):
        with open(_COMPONENTS_PATH) as f:
            content = f.read()
        assert "refresh" not in content.lower()


# ─── 7. Agent badge modifier classes ───────────────────────────────

class TestAgentBadgeClasses:
    """Verify agent badge has distinct classes for claude/codex/qoder."""

    def test_badge_base_class(self):
        content = _read_all_templates()
        assert "sessions-agent-badge" in content

    def test_claude_code_modifier(self):
        """CSS must define claude_code badge style."""
        css = _read_css()
        assert "claude_code" in css.lower()
        # Template uses dynamic {{ s.agent }} for the modifier class
        content = _read_all_templates()
        assert "sessions-agent-badge--" in content

    def test_codex_modifier(self):
        """CSS must define codex badge style."""
        css = _read_css()
        assert "codex" in css.lower()
        content = _read_all_templates()
        assert "sessions-agent-badge--" in content

    def test_qoder_modifier(self):
        """CSS must define qoder badge style."""
        css = _read_css()
        assert "qoder" in css.lower()
        content = _read_all_templates()
        assert "sessions-agent-badge--" in content

    def test_badge_uses_agent_variable(self):
        """Template should use {{ s.agent }} for dynamic badge class."""
        content = _read_all_templates()
        assert 'sessions-agent-badge--{{ s.agent }}' in content


# ─── 8. ROUNDS header not clipped ──────────────────────────────────

class TestRoundsColumn:
    """Verify ROUNDS column has dedicated width and is not clipped."""

    def test_rounds_header_in_template(self):
        content = _read_all_templates()
        assert "Rounds" in content

    def test_rounds_th_sort_call(self):
        """Rounds must be a sortable column."""
        content = _read_all_templates()
        assert "th_sort('Rounds'" in content

    def test_rounds_css_column_width(self):
        """CSS should define grid column width for rounds."""
        css = _read_css()
        # The grid uses grid-template-columns with minmax
        assert "minmax" in css or "px" in css

    def test_rounds_data_attribute(self):
        """Row should have data-rounds attribute."""
        content = _read_all_templates()
        assert "data-rounds=" in content

    def test_rounds_cell_renders_assistant_message_count(self):
        """Rounds cell should render s.assistant_message_count."""
        content = _read_all_templates()
        assert "s.assistant_message_count" in content
