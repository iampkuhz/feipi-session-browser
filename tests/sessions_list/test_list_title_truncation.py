"""Tests for list-view title sanitization.

Covers:
- ``sanitize_list_title`` utility (unit).
- ``list_sessions`` returns truncated titles (integration).
- ``get_session`` returns full titles (no truncation).
"""

from __future__ import annotations

import os
import sqlite3
import textwrap

import pytest

from session_browser.domain.normalizer import sanitize_list_title
from session_browser.index.indexer import (
    _row_to_summary,
    get_session,
    init_schema,
    list_sessions,
    upsert_session,
)
from session_browser.domain.models import SessionSummary


# ─── Unit: sanitize_list_title ─────────────────────────────────────────────


class TestSanitizeListTitle:
    """Unit tests for the title sanitization helper."""

    def test_empty_string(self):
        assert sanitize_list_title("") == ""

    def test_none_returns_empty(self):
        assert sanitize_list_title(None) == ""  # type: ignore[arg-type]

    def test_short_title_unchanged(self):
        assert sanitize_list_title("Fix login bug") == "Fix login bug"

    def test_newline_replaced_by_space(self):
        title = "Line one\nLine two\nLine three"
        result = sanitize_list_title(title)
        assert "\n" not in result
        assert result == "Line one Line two Line three"

    def test_whitespace_collapsed(self):
        title = "hello   world\t\ttest"
        assert sanitize_list_title(title) == "hello world test"

    def test_leading_trailing_stripped(self):
        title = "  hello world  "
        assert sanitize_list_title(title) == "hello world"

    def test_only_whitespace_returns_empty(self):
        assert sanitize_list_title("   \n\n\t  ") == ""

    def test_long_title_truncated(self):
        title = "x" * 200
        result = sanitize_list_title(title)
        assert len(result) == 121  # 120 chars + "…"
        assert result.endswith("…")

    def test_truncated_title_does_not_cut_mid_char_at_boundary(self):
        # Boundary: 120 chars — trailing whitespace strip ensures we don't
        # have a dangling space before the ellipsis.
        title = "a" * 120 + " extra"
        result = sanitize_list_title(title)
        assert len(result) == 121  # 120 + "…"
        assert result.startswith("a" * 120)
        assert result.endswith("…")

    def test_exact_max_len_no_ellipsis(self):
        title = "a" * 120
        result = sanitize_list_title(title)
        assert result == title  # exactly max_len → no truncation

    def test_one_over_max_len_gets_ellipsis(self):
        title = "a" * 121
        result = sanitize_list_title(title)
        assert len(result) == 121  # 120 chars + "…"
        assert result.endswith("…")

    def test_custom_max_len(self):
        title = "a" * 50
        result = sanitize_list_title(title, max_len=30)
        assert len(result) == 31  # 30 + "…"
        assert result.endswith("…")

    def test_multiline_long_text(self):
        """Realistic case: a multi-sentence user message spanning lines."""
        title = textwrap.dedent("""\
            Create a comprehensive API documentation
            that includes all endpoints, request/response formats,
            error handling, rate limits, authentication methods,
            pagination, filtering, and example code snippets in Python.
            Make sure to cover both REST and GraphQL APIs.
        """)
        result = sanitize_list_title(title)
        assert "\n" not in result
        assert len(result) <= 121  # 120 + "…"
        # Should start with the first part
        assert result.startswith("Create a comprehensive API")

    def test_mixed_whitespace_types(self):
        """Mix of spaces, tabs, newlines, non-breaking spaces."""
        title = "hello\t\tworld\n\nfoo\rbar"
        result = sanitize_list_title(title)
        assert result == "hello world foo bar"


# ─── Integration: list_sessions truncates, get_session does not ────────────


@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary DB with test sessions."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    init_schema(conn)

    # Insert sessions with various titles
    long_title = "This is a very long title that should definitely be truncated because it contains way too many characters for a list view " + "extra padding here"
    sessions = [
        SessionSummary(
            agent="claude_code", session_id="sess-1", title="Short title",
            project_key="/tmp/p", project_name="p", cwd="/tmp/p",
            started_at="2026-01-01T00:00:00Z", ended_at="2026-01-01T00:01:00Z",
        ),
        SessionSummary(
            agent="claude_code", session_id="sess-2", title=long_title,
            project_key="/tmp/p", project_name="p", cwd="/tmp/p",
            started_at="2026-01-01T00:00:00Z", ended_at="2026-01-01T00:02:00Z",
        ),
        SessionSummary(
            agent="codex", session_id="sess-3", title="",
            project_key="/tmp/p", project_name="p", cwd="/tmp/p",
            started_at="2026-01-01T00:00:00Z", ended_at="2026-01-01T00:03:00Z",
        ),
        SessionSummary(
            agent="qoder", session_id="sess-4",
            title="Title with\nnewlines\nand\ttabs",
            project_key="/tmp/p", project_name="p", cwd="/tmp/p",
            started_at="2026-01-01T00:00:00Z", ended_at="2026-01-01T00:04:00Z",
        ),
    ]
    for s in sessions:
        upsert_session(conn, s)
    conn.commit()
    return db_path


class TestListSessionsTruncatesTitle:
    """Integration tests: list_sessions should return sanitized titles."""

    def test_short_title_unchanged(self, tmp_db):
        conn = sqlite3.connect(str(tmp_db))
        conn.row_factory = sqlite3.Row
        sessions = list_sessions(conn, limit=50)
        conn.close()
        short = next(s for s in sessions if s.session_id == "sess-1")
        assert short.title == "Short title"

    def test_long_title_truncated(self, tmp_db):
        conn = sqlite3.connect(str(tmp_db))
        conn.row_factory = sqlite3.Row
        sessions = list_sessions(conn, limit=50)
        conn.close()
        long_sess = next(s for s in sessions if s.session_id == "sess-2")
        assert len(long_sess.title) <= 121  # 120 + "…"
        assert long_sess.title.endswith("…")

    def test_empty_title_stays_empty(self, tmp_db):
        conn = sqlite3.connect(str(tmp_db))
        conn.row_factory = sqlite3.Row
        sessions = list_sessions(conn, limit=50)
        conn.close()
        empty = next(s for s in sessions if s.session_id == "sess-3")
        assert empty.title == ""

    def test_newlines_collapsed(self, tmp_db):
        conn = sqlite3.connect(str(tmp_db))
        conn.row_factory = sqlite3.Row
        sessions = list_sessions(conn, limit=50)
        conn.close()
        nl = next(s for s in sessions if s.session_id == "sess-4")
        assert "\n" not in nl.title
        assert "\t" not in nl.title
        assert " " in nl.title  # newlines replaced by spaces


class TestGetSessionFullTitle:
    """get_session should return the original full title."""

    def test_long_title_not_truncated(self, tmp_db):
        conn = sqlite3.connect(str(tmp_db))
        conn.row_factory = sqlite3.Row
        session = get_session(conn, "claude_code:sess-2")
        conn.close()
        assert session is not None
        assert len(session.title) > 120  # full title preserved