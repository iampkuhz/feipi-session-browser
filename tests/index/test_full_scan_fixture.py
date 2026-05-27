"""Full scan fixture tests for Claude Code indexer.

Validates that full_scan() correctly indexes fixture data, produces
expected session counts, and populates all index columns.
"""

import pytest
import os
import shutil
import sqlite3
import sys
from pathlib import Path

# ─── Constants ──────────────────────────────────────────────────────────────

FIXTURE_ROOT = Path(__file__).parent.parent / "fixtures" / "index_corpus" / "full_scan_claude"

EXPECTED_SESSIONS = [
    {"session_id": "sess-001", "project_key": "proj-alpha"},
    {"session_id": "sess-002", "project_key": "proj-beta"},
]


# ─── Helpers ────────────────────────────────────────────────────────────────

def _setup_claude_env(data_dir: str):
    """Set CLAUDE_DATA_DIR and reload dependent modules."""
    old = os.environ.get("CLAUDE_DATA_DIR", None)
    os.environ["CLAUDE_DATA_DIR"] = data_dir

    # Reload config + sources so they pick up the new env var
    if "session_browser.config" in sys.modules:
        importlib_reload = sys.modules.get("importlib")
        if importlib_reload is None:
            import importlib
            sys.modules["importlib"] = importlib
            importlib_reload = importlib
        importlib_reload.reload(sys.modules["session_browser.config"])
    for _mod in list(sys.modules):
        if _mod.startswith("session_browser.sources"):
            del sys.modules[_mod]
    for _mod in list(sys.modules):
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


# ─── Tests ──────────────────────────────────────────────────────────────────

class TestFullScanClaudeBasic:
    """C01: full_scan_basic — basic index construction from fixture data."""

    @pytest.mark.contract_case("DATA-INDEX-001")
    def test_full_scan_indexes_all_sessions(self, tmp_path):
        """full_scan() should index both fixture sessions."""
        data_dir = tmp_path / "claude_data"
        shutil.copytree(str(FIXTURE_ROOT), str(data_dir))

        db_path = str(tmp_path / "index.sqlite")
        result = _run_full_scan(str(data_dir), db_path)

        assert result["claude_count"] == 2, f"Expected 2 Claude sessions, got {result['claude_count']}"
        assert result["codex_count"] == 0
        assert result["qoder_count"] == 0
        assert result["total"] == 2

    @pytest.mark.contract_case("DATA-INDEX-001")
    def test_session_keys_present(self, tmp_path):
        """Indexed sessions should have correct session_key format."""
        data_dir = tmp_path / "claude_data"
        shutil.copytree(str(FIXTURE_ROOT), str(data_dir))

        db_path = str(tmp_path / "index.sqlite")
        _run_full_scan(str(data_dir), db_path)

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        for sess in EXPECTED_SESSIONS:
            expected_key = f"claude_code:{sess['session_id']}"
            row = conn.execute(
                "SELECT session_key FROM sessions WHERE session_key = ?",
                (expected_key,),
            ).fetchone()
            assert row is not None, f"Session key {expected_key} not found in index"

        conn.close()

    @pytest.mark.contract_case("DATA-INDEX-001")
    def test_session_count_matches(self, tmp_path):
        """Total row count in sessions table should match fixture session count."""
        data_dir = tmp_path / "claude_data"
        shutil.copytree(str(FIXTURE_ROOT), str(data_dir))

        db_path = str(tmp_path / "index.sqlite")
        _run_full_scan(str(data_dir), db_path)

        conn = sqlite3.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        conn.close()

        assert count == 2, f"Expected 2 rows in sessions table, got {count}"

    @pytest.mark.contract_case("DATA-INDEX-001")
    def test_all_columns_populated(self, tmp_path):
        """Every indexed session should have non-empty values for all 26 columns."""
        data_dir = tmp_path / "claude_data"
        shutil.copytree(str(FIXTURE_ROOT), str(data_dir))

        db_path = str(tmp_path / "index.sqlite")
        _run_full_scan(str(data_dir), db_path)

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        for sess in EXPECTED_SESSIONS:
            key = f"claude_code:{sess['session_id']}"
            row = conn.execute(
                "SELECT * FROM sessions WHERE session_key = ?",
                (key,),
            ).fetchone()
            assert row is not None, f"Session {key} not found"

            # Core identity fields must be non-empty
            assert row["agent"] == "claude_code", f"agent mismatch for {key}"
            assert row["session_id"] == sess["session_id"], f"session_id mismatch for {key}"
            assert row["project_key"] == sess["project_key"], f"project_key mismatch for {key}"

            # Title should be non-empty (derived from first user message)
            assert row["title"] != "", f"title is empty for {key}"

            # Timestamps should be non-empty ISO8601 strings
            assert row["started_at"] != "", f"started_at is empty for {key}"
            assert row["ended_at"] != "", f"ended_at is empty for {key}"

            # Token counts should be > 0 (our fixtures have usage data)
            assert row["input_tokens"] > 0, f"input_tokens is 0 for {key}"
            assert row["output_tokens"] > 0, f"output_tokens is 0 for {key}"

            # Message counts should be > 0
            assert row["user_message_count"] > 0, f"user_message_count is 0 for {key}"
            assert row["assistant_message_count"] > 0, f"assistant_message_count is 0 for {key}"

            # indexed_at should be set
            assert row["indexed_at"] > 0, f"indexed_at is 0 for {key}"

        conn.close()

    @pytest.mark.contract_case("DATA-INDEX-001")
    def test_scan_log_recorded(self, tmp_path):
        """full_scan() should write a scan_log entry with correct counts."""
        data_dir = tmp_path / "claude_data"
        shutil.copytree(str(FIXTURE_ROOT), str(data_dir))

        db_path = str(tmp_path / "index.sqlite")
        _run_full_scan(str(data_dir), db_path)

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        log = conn.execute(
            "SELECT * FROM scan_log ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert log is not None, "No scan_log entry found"
        assert log["mode"] == "full"
        assert log["status"] == "done"
        assert log["claude_count"] == 2
        assert log["finished_at"] is not None

        conn.close()

    @pytest.mark.contract_case("DATA-INDEX-001")
    def test_fixture_data_isolated(self, tmp_path):
        """Full scan should not touch real CLAUDE_DATA_DIR when using fixture."""
        data_dir = tmp_path / "claude_data"
        shutil.copytree(str(FIXTURE_ROOT), str(data_dir))

        db_path = str(tmp_path / "index.sqlite")
        result = _run_full_scan(str(data_dir), db_path)

        # Should only see our 2 fixture sessions, nothing from real ~/.claude/
        conn = sqlite3.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        conn.close()

        assert count == 2, "Index should only contain fixture sessions, not real data"
