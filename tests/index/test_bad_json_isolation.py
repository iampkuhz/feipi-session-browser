"""Bad JSON isolation tests for Claude Code indexer.

Validates that:
- Bad JSON lines do not crash the parser (isolation)
- Good JSON lines are still correctly parsed and indexed
- Diagnostics record the bad lines with line numbers
- No uncaught exceptions propagate
- The session is still indexed with diagnostic metadata

Corresponds to V9 长跑 task 054.
"""

import pytest
import os
import shutil
import sqlite3
import sys
from pathlib import Path

# ─── Constants ──────────────────────────────────────────────────────────────

FIXTURE_ROOT = Path(__file__).parent.parent / "fixtures" / "index_corpus" / "bad_json_session"

# Known bad lines in the fixture (by 1-based line number)
BAD_LINE_NUMBERS = {2, 4, 6}
GOOD_LINE_COUNT = 6  # 6 valid JSON objects in the fixture


# ─── Helpers ────────────────────────────────────────────────────────────────

def _setup_claude_env(data_dir: str):
    """Set CLAUDE_DATA_DIR and reload dependent modules."""
    old = os.environ.get("CLAUDE_DATA_DIR", None)
    os.environ["CLAUDE_DATA_DIR"] = data_dir

    for _mod in list(sys.modules):
        if _mod.startswith("session_browser.config"):
            del sys.modules[_mod]
        if _mod.startswith("session_browser.sources"):
            del sys.modules[_mod]
        if _mod.startswith("session_browser.index.indexer"):
            del sys.modules[_mod]

    return old


def _restore_claude_env(old: str | None):
    """Restore original CLAUDE_DATA_DIR."""
    if old is not None:
        os.environ["CLAUDE_DATA_DIR"] = old
    else:
        os.environ.pop("CLAUDE_DATA_DIR", None)


def _run_full_scan(data_dir: str, db_path: str) -> dict:
    """Run full_scan() against data_dir, returning scan statistics."""
    old_env = _setup_claude_env(data_dir)
    try:
        from session_browser.index.indexer import full_scan

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        result = full_scan(conn, verbose=False, agent="claude_code")
        conn.close()
        return result
    finally:
        _restore_claude_env(old_env)


# ─── Tests: jsonl_reader level ─────────────────────────────────────────────

class TestJsonlReaderBadJsonIsolation:
    """Validate that parse_jsonl_events isolates bad JSON lines."""

    @pytest.mark.contract_case("DATA-INDEX-006")
    def test_bad_lines_do_not_crash_parser(self, tmp_path):
        """Parsing a file with bad JSON lines must not raise an exception."""
        from session_browser.sources.jsonl_reader import parse_jsonl_events

        # Copy fixture to a temp location
        src = FIXTURE_ROOT / "projects" / "bad-proj" / "bad-sess-001.jsonl"
        assert src.exists(), "Fixture file missing"

        events, diagnostics = parse_jsonl_events(src, verbose=False)

        # Must complete without exception
        assert events is not None
        assert diagnostics is not None

    @pytest.mark.contract_case("DATA-INDEX-006")
    def test_good_lines_still_parsed(self, tmp_path):
        """Valid JSON lines should still produce events."""
        from session_browser.sources.jsonl_reader import parse_jsonl_events

        src = FIXTURE_ROOT / "projects" / "bad-proj" / "bad-sess-001.jsonl"
        events, diagnostics = parse_jsonl_events(src, verbose=False)

        # We have 5 valid JSON objects in the fixture
        assert diagnostics.events_parsed == GOOD_LINE_COUNT, (
            f"Expected {GOOD_LINE_COUNT} parsed events, got {diagnostics.events_parsed}"
        )

    @pytest.mark.contract_case("DATA-INDEX-006")
    def test_diagnostics_record_bad_lines(self, tmp_path):
        """Diagnostics should record the bad/unparseable lines."""
        from session_browser.sources.jsonl_reader import parse_jsonl_events

        src = FIXTURE_ROOT / "projects" / "bad-proj" / "bad-sess-001.jsonl"
        events, diagnostics = parse_jsonl_events(src, verbose=False)

        # We have 3 known bad lines in the fixture
        assert diagnostics.events_skipped == len(BAD_LINE_NUMBERS), (
            f"Expected {len(BAD_LINE_NUMBERS)} skipped events, got {diagnostics.events_skipped}"
        )

        # Bad line numbers should match expected set
        bad_line_nos = {issue.line_no for issue in diagnostics.issues}
        assert bad_line_nos == BAD_LINE_NUMBERS, (
            f"Expected bad lines at {BAD_LINE_NUMBERS}, got {bad_line_nos}"
        )

    @pytest.mark.contract_case("DATA-INDEX-006")
    def test_bad_json_issues_have_correct_severity(self, tmp_path):
        """Each bad JSON issue should be marked as ERROR severity."""
        from session_browser.sources.jsonl_reader import (
            parse_jsonl_events, ParseIssue, ParseSeverity,
        )

        src = FIXTURE_ROOT / "projects" / "bad-proj" / "bad-sess-001.jsonl"
        events, diagnostics = parse_jsonl_events(src, verbose=False)

        for issue in diagnostics.issues:
            assert issue.issue == ParseIssue.BAD_JSON
            assert issue.severity == ParseSeverity.ERROR

    @pytest.mark.contract_case("DATA-INDEX-006")
    def test_bad_json_issues_have_preview(self, tmp_path):
        """Each issue should carry a preview of the offending line."""
        from session_browser.sources.jsonl_reader import parse_jsonl_events

        src = FIXTURE_ROOT / "projects" / "bad-proj" / "bad-sess-001.jsonl"
        events, diagnostics = parse_jsonl_events(src, verbose=False)

        for issue in diagnostics.issues:
            assert issue.preview != "", f"Issue at line {issue.line_no} has empty preview"
            assert len(issue.preview) > 0

    @pytest.mark.contract_case("DATA-INDEX-006")
    def test_no_uncaught_exception(self, tmp_path):
        """Parser must never raise uncaught exceptions on bad JSON."""
        from session_browser.sources.jsonl_reader import parse_jsonl_events

        src = FIXTURE_ROOT / "projects" / "bad-proj" / "bad-sess-001.jsonl"

        # This should complete cleanly — if it raises, the test fails
        events, diagnostics = parse_jsonl_events(src, verbose=False)

        # Verify we got at least some events
        assert len(events) > 0, "Expected at least some events to be parsed"

    @pytest.mark.contract_case("DATA-INDEX-006")
    def test_event_types_are_correct(self, tmp_path):
        """Parsed events should have correct 'type' field."""
        from session_browser.sources.jsonl_reader import parse_jsonl_events

        src = FIXTURE_ROOT / "projects" / "bad-proj" / "bad-sess-001.jsonl"
        events, diagnostics = parse_jsonl_events(src, verbose=False)

        event_types = [ev.get("type") for ev in events]
        assert "user" in event_types, "Expected at least one 'user' event"
        assert "assistant" in event_types, "Expected at least one 'assistant' event"


# ─── Tests: full scan / indexer level ──────────────────────────────────────

class TestBadJsonSessionIndexing:
    """Validate that a session with bad JSON lines is still indexed."""

    @pytest.mark.contract_case("DATA-INDEX-006")
    def test_session_indexed_despite_bad_json(self, tmp_path):
        """full_scan() should index the session even with bad JSON lines."""
        data_dir = tmp_path / "claude_data"
        shutil.copytree(str(FIXTURE_ROOT), str(data_dir))

        db_path = str(tmp_path / "index.sqlite")

        # Must not raise
        result = _run_full_scan(str(data_dir), db_path)

        assert result["claude_count"] == 1, (
            f"Expected 1 Claude session, got {result['claude_count']}"
        )

    @pytest.mark.contract_case("DATA-INDEX-006")
    def test_session_key_present_in_db(self, tmp_path):
        """The bad-JSON session should appear in the sessions table."""
        data_dir = tmp_path / "claude_data"
        shutil.copytree(str(FIXTURE_ROOT), str(data_dir))

        db_path = str(tmp_path / "index.sqlite")
        _run_full_scan(str(data_dir), db_path)

        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT session_key FROM sessions WHERE session_key = ?",
            ("claude_code:bad-sess-001",),
        ).fetchone()
        conn.close()

        assert row is not None, "Session key claude_code:bad-sess-001 not found in index"

    @pytest.mark.contract_case("DATA-INDEX-006")
    def test_session_has_valid_title(self, tmp_path):
        """Indexed session should have a title derived from user message."""
        data_dir = tmp_path / "claude_data"
        shutil.copytree(str(FIXTURE_ROOT), str(data_dir))

        db_path = str(tmp_path / "index.sqlite")
        _run_full_scan(str(data_dir), db_path)

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT title FROM sessions WHERE session_key = ?",
            ("claude_code:bad-sess-001",),
        ).fetchone()
        conn.close()

        assert row is not None
        assert "bug" in row["title"].lower(), (
            f"Expected title to contain 'bug', got '{row['title']}'"
        )

    @pytest.mark.contract_case("DATA-INDEX-006")
    def test_session_has_correct_message_counts(self, tmp_path):
        """Message counts should reflect only good (parsed) lines."""
        data_dir = tmp_path / "claude_data"
        shutil.copytree(str(FIXTURE_ROOT), str(data_dir))

        db_path = str(tmp_path / "index.sqlite")
        _run_full_scan(str(data_dir), db_path)

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT user_message_count, assistant_message_count FROM sessions WHERE session_key = ?",
            ("claude_code:bad-sess-001",),
        ).fetchone()
        conn.close()

        assert row is not None
        # Fixture: 1 user message with human text (line 1).
        # Line 7 is a user event but only carries tool_result (no human text),
        # so _extract_user_text returns empty and user_count stays at 1.
        assert row["user_message_count"] == 1, (
            f"Expected 1 user message, got {row['user_message_count']}"
        )
        # Fixture: 4 assistant message fragments (lines 3, 5, 8, 9)
        # but _assistant_records merges by message id, so we have 4 distinct records
        assert row["assistant_message_count"] == 4, (
            f"Expected 4 assistant messages, got {row['assistant_message_count']}"
        )

    @pytest.mark.contract_case("DATA-INDEX-006")
    def test_session_has_token_data_from_good_lines(self, tmp_path):
        """Token counts should be derived from good lines only."""
        data_dir = tmp_path / "claude_data"
        shutil.copytree(str(FIXTURE_ROOT), str(data_dir))

        db_path = str(tmp_path / "index.sqlite")
        _run_full_scan(str(data_dir), db_path)

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT input_tokens, output_tokens FROM sessions WHERE session_key = ?",
            ("claude_code:bad-sess-001",),
        ).fetchone()
        conn.close()

        assert row is not None
        # input_tokens: 150 + 200 + 180 + 100 = 630 (from 4 assistant records)
        assert row["input_tokens"] == 630, (
            f"Expected 630 input tokens, got {row['input_tokens']}"
        )
        # output_tokens: 80 + 60 + 70 + 40 = 250
        assert row["output_tokens"] == 250, (
            f"Expected 250 output tokens, got {row['output_tokens']}"
        )

    @pytest.mark.contract_case("DATA-INDEX-006")
    def test_scan_log_records_success(self, tmp_path):
        """scan_log should show successful scan even with bad JSON."""
        data_dir = tmp_path / "claude_data"
        shutil.copytree(str(FIXTURE_ROOT), str(data_dir))

        db_path = str(tmp_path / "index.sqlite")
        _run_full_scan(str(data_dir), db_path)

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        log = conn.execute(
            "SELECT * FROM scan_log ORDER BY id DESC LIMIT 1"
        ).fetchone()
        conn.close()

        assert log is not None
        assert log["status"] == "done", f"Expected status 'done', got '{log['status']}'"
        assert log["claude_count"] == 1

    @pytest.mark.contract_case("DATA-INDEX-006")
    def test_no_other_sessions_indexed(self, tmp_path):
        """Only the fixture session should be indexed — no leakage."""
        data_dir = tmp_path / "claude_data"
        shutil.copytree(str(FIXTURE_ROOT), str(data_dir))

        db_path = str(tmp_path / "index.sqlite")
        _run_full_scan(str(data_dir), db_path)

        conn = sqlite3.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        conn.close()

        assert count == 1, f"Expected exactly 1 session, got {count}"
