"""Tests for sessions list pagination — HIFI v3 footer."""

from __future__ import annotations

import os
import sqlite3
import pytest

from session_browser.index.indexer import (
    init_schema,
    upsert_session,
    list_sessions,
    count_sessions,
)
from session_browser.domain.models import SessionSummary

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


def _make_summary(sid: str, title: str = "", agent: str = "claude_code",
                  project: str = "proj-a", model: str = "model-x") -> SessionSummary:
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
        assistant_message_count=1,
        tool_call_count=1,
        input_tokens=100,
        output_tokens=100,
        cached_input_tokens=0,
        cached_output_tokens=0,
        failed_tool_count=0,
    )


@pytest.fixture
def populated_db(tmp_path):
    """Create a SQLite DB with 55 sessions across 3 agents and 3 projects."""
    db_path = tmp_path / "test_index.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    init_schema(conn)

    agents = ["claude_code", "qoder", "codex"]
    projects = ["proj-a", "proj-b", "proj-c"]
    models = ["model-x", "model-y"]

    for i in range(1, 56):
        agent = agents[(i - 1) % 3]
        project = projects[(i - 1) % 3]
        model = models[i % 2]
        s = _make_summary(str(i), title=f"Test Session {i:03d}",
                          agent=agent, project=project, model=model)
        upsert_session(conn, s)

    conn.commit()
    yield conn
    conn.close()


# ─── Pagination: limit / offset ──────────────────────────────────────────

class TestListSessionsPagination:
    def test_default_limit_returns_50(self, populated_db):
        rows = list_sessions(populated_db)
        assert len(rows) == 50

    def test_limit_20_returns_20(self, populated_db):
        rows = list_sessions(populated_db, limit=20)
        assert len(rows) == 20

    def test_offset_skips_first_page(self, populated_db):
        first_page = list_sessions(populated_db, limit=20, offset=0)
        second_page = list_sessions(populated_db, limit=20, offset=20)
        first_ids = {r.session_id for r in first_page}
        second_ids = {r.session_id for r in second_page}
        assert first_ids.isdisjoint(second_ids)

    def test_offset_20_returns_remaining(self, populated_db):
        rows = list_sessions(populated_db, limit=20, offset=20)
        assert len(rows) == 20

    def test_offset_50_returns_last_5(self, populated_db):
        rows = list_sessions(populated_db, limit=20, offset=50)
        assert len(rows) == 5

    def test_offset_beyond_data_returns_empty(self, populated_db):
        rows = list_sessions(populated_db, limit=20, offset=100)
        assert len(rows) == 0


# ─── Count with filters ──────────────────────────────────────────────────

class TestCountSessionsFilters:
    def test_total_count(self, populated_db):
        assert count_sessions(populated_db) == 55

    def test_count_by_agent(self, populated_db):
        count = count_sessions(populated_db, agent="claude_code")
        assert count > 0

    def test_count_by_model(self, populated_db):
        count = count_sessions(populated_db, model="model-x")
        assert count > 0

    def test_count_by_title(self, populated_db):
        count = count_sessions(populated_db, title_like="Test Session 001")
        assert count == 1

    def test_count_by_title_wildcard(self, populated_db):
        # Sessions 001-009 all have "Session 00" in their title
        count = count_sessions(populated_db, title_like="Session 00")
        assert count == 9  # 001-009

    def test_count_combined_filters(self, populated_db):
        count = count_sessions(populated_db, agent="claude_code", model="model-x")
        assert count > 0


# ─── Pagination with filters ─────────────────────────────────────────────

class TestListSessionsWithFilters:
    def test_filter_by_agent(self, populated_db):
        rows = list_sessions(populated_db, agent="claude_code", limit=100)
        assert all(r.agent == "claude_code" for r in rows)

    def test_filter_by_model(self, populated_db):
        rows = list_sessions(populated_db, model="model-y", limit=100)
        assert all(r.model == "model-y" for r in rows)

    def test_filter_by_title_like(self, populated_db):
        rows = list_sessions(populated_db, title_like="Test Session 00", limit=100)
        assert all("Test Session 00" in r.title for r in rows)


# ─── Template: footer controls ───────────────────────────────────────────

class TestFooterTemplate:
    """Verify sessions.html contains contract-compliant pagination."""

    def test_pagination_nav(self):
        content = _read_sessions_templates()
        assert 'class="pagination unified-pagination"' in content
        assert 'role="navigation"' in content
        assert 'aria-label="Sessions pagination"' in content

    def test_prev_button(self):
        content = _read_sessions_templates()
        assert 'data-action="prev-page"' in content

    def test_next_button(self):
        content = _read_sessions_templates()
        assert 'data-action="next-page"' in content

    def test_page_input(self):
        content = _read_sessions_templates()
        assert 'data-action="page-input"' in content

    def test_page_status(self):
        content = _read_sessions_templates()
        assert 'class="page-status"' in content

    def test_no_sorted_by(self):
        """Footer must not contain 'sorted by' text."""
        content = _read_sessions_templates()
        assert "sorted by" not in content.lower()

    def test_no_page_size_select_in_footer(self):
        """HIFI v4 footer does not have page size select."""
        content = _read_sessions_templates()
        assert "sessions-footer-page-size__select" not in content

    def test_no_page_info_text(self):
        """No 'Page X of Y' static text — uses page-status + page-input instead."""
        content = _read_sessions_templates()
        assert 'Page {{ page }} of {{ total_pages }}' not in content

    def test_pagination_prev_conditional(self):
        """Prev button is conditionally rendered (hidden on page 1)."""
        content = _read_sessions_templates()
        assert "current_page > 1" in content

    def test_pagination_next_conditional(self):
        """Next button is conditionally rendered (hidden on last page)."""
        content = _read_sessions_templates()
        assert "current_page < total_pages" in content

    def test_no_button_based_pagination(self):
        """No button with name=page (old form-based pagination)."""
        content = _read_sessions_templates()
        assert 'name="page"' not in content or 'value="prev"' not in content

    def test_filter_form_has_name_attributes(self):
        content = _read_sessions_templates()
        assert 'name="q"' in content
        assert 'name="agent"' in content
        assert 'name="model"' in content
        assert 'name="project"' in content
        assert 'name="sort"' in content

    def test_filter_form_uses_preselected_values(self):
        content = _read_sessions_templates()
        assert "filter_agent" in content
        assert "filter_model" in content
        assert "filter_project" in content
        assert "filter_q" in content

    def test_no_client_side_apply_filters(self):
        """Old client-side applyFilters should be removed."""
        content = _read_sessions_templates()
        assert "function applyFilters()" not in content

    def test_no_submit_filters_function(self):
        """submitFilters removed in favor of link-based navigation."""
        content = _read_sessions_templates()
        assert "submitFilters" not in content

    def test_actions_dict_passed(self):
        """Template must receive actions dict for URL building."""
        content = _read_sessions_templates()
        assert "actions." in content
