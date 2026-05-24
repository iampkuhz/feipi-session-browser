"""Incremental scan fixture tests.

Validates that incremental_scan() correctly detects file mtime changes,
re-indexes only modified sessions, and skips unchanged ones.
"""

import importlib
import os
import shutil
import sqlite3
import sys
import time
from pathlib import Path

import pytest

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

    for _mod in list(sys.modules):
        if _mod.startswith("session_browser.config"):
            del sys.modules[_mod]
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


def _run_incremental_scan(data_dir: str, db_path: str) -> dict:
    """Run incremental_scan() against data_dir, returning scan statistics."""
    old_env = _setup_claude_env(data_dir)
    try:
        from session_browser.index.indexer import incremental_scan

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        result = incremental_scan(conn, verbose=False, agent="claude_code")
        conn.close()
        return result
    finally:
        _restore_claude_env(old_env)


# ─── Tests ──────────────────────────────────────────────────────────────────

class TestIncrementalScanMtime:
    """I01: incremental_scan detects mtime changes and re-indexes only modified files."""

    def test_no_changes_all_skipped(self, tmp_path):
        """incremental_scan() with no file changes should skip all sessions."""
        data_dir = tmp_path / "claude_data"
        shutil.copytree(str(FIXTURE_ROOT), str(data_dir))

        db_path = str(tmp_path / "index.sqlite")
        _run_full_scan(str(data_dir), db_path)

        # No file changes — incremental should skip everything
        result = _run_incremental_scan(str(data_dir), db_path)

        assert result["claude_count"] == 0, (
            f"Expected 0 re-indexed sessions (no changes), got {result['claude_count']}"
        )
        assert result["skipped"] == 2, (
            f"Expected 2 skipped sessions, got {result['skipped']}"
        )

    def test_one_file_changed_reindexed_only(self, tmp_path):
        """Modifying one file's mtime should cause only that session to be re-indexed."""
        data_dir = tmp_path / "claude_data"
        shutil.copytree(str(FIXTURE_ROOT), str(data_dir))

        db_path = str(tmp_path / "index.sqlite")
        _run_full_scan(str(data_dir), db_path)

        # Advance time to ensure mtime difference is detectable
        time.sleep(0.05)

        # Touch only sess-001's file to make its mtime newer
        sess001_file = data_dir / "projects" / "proj-alpha" / "sess-001.jsonl"
        current_stat = os.stat(str(sess001_file))
        new_mtime = current_stat.st_mtime + 1.0
        os.utime(str(sess001_file), (new_mtime, new_mtime))

        result = _run_incremental_scan(str(data_dir), db_path)

        assert result["claude_count"] == 1, (
            f"Expected 1 re-indexed session, got {result['claude_count']}"
        )
        assert result["skipped"] == 1, (
            f"Expected 1 skipped session, got {result['skipped']}"
        )

        # Verify the correct session was re-indexed by checking indexed_at changed
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        row1 = conn.execute(
            "SELECT * FROM sessions WHERE session_key = 'claude_code:sess-001'"
        ).fetchone()
        row2 = conn.execute(
            "SELECT * FROM sessions WHERE session_key = 'claude_code:sess-002'"
        ).fetchone()

        # Both sessions exist in DB
        assert row1 is not None, "sess-001 should still be in DB"
        assert row2 is not None, "sess-002 should still be in DB"

        # Verify sess-001 was re-indexed by checking its indexed_at was updated
        # (both sessions were indexed by full_scan, then only sess-001 was re-indexed)
        indexed_at_1 = row1["indexed_at"]
        indexed_at_2 = row2["indexed_at"]
        assert indexed_at_1 > indexed_at_2, (
            f"sess-001 indexed_at ({indexed_at_1}) should be newer than sess-002 ({indexed_at_2})"
        )

        conn.close()

    def test_all_files_changed_all_reindexed(self, tmp_path):
        """Touching all files should cause all sessions to be re-indexed."""
        data_dir = tmp_path / "claude_data"
        shutil.copytree(str(FIXTURE_ROOT), str(data_dir))

        db_path = str(tmp_path / "index.sqlite")
        _run_full_scan(str(data_dir), db_path)

        time.sleep(0.05)

        # Touch both session files
        for proj, sess in [("proj-alpha", "sess-001"), ("proj-beta", "sess-002")]:
            fpath = data_dir / "projects" / proj / f"{sess}.jsonl"
            current_stat = os.stat(str(fpath))
            new_mtime = current_stat.st_mtime + 1.0
            os.utime(str(fpath), (new_mtime, new_mtime))

        result = _run_incremental_scan(str(data_dir), db_path)

        assert result["claude_count"] == 2, (
            f"Expected 2 re-indexed sessions, got {result['claude_count']}"
        )
        assert result["skipped"] == 0, (
            f"Expected 0 skipped sessions, got {result['skipped']}"
        )

    def test_new_session_discovered(self, tmp_path):
        """Adding a new session file after initial scan should be discovered."""
        data_dir = tmp_path / "claude_data"
        shutil.copytree(str(FIXTURE_ROOT), str(data_dir))

        db_path = str(tmp_path / "index.sqlite")
        _run_full_scan(str(data_dir), db_path)

        # Add a new session entry to history.jsonl (a 3rd session)
        # and create the corresponding session file
        history_path = data_dir / "history.jsonl"
        import json
        new_entry = {
            "sessionId": "sess-003",
            "project": "proj-gamma",
            "timestamp": int(time.time() * 1000),
            "display": "New session test"
        }
        with open(str(history_path), "a") as f:
            f.write(json.dumps(new_entry) + "\n")

        # Create the session file
        proj_dir = data_dir / "projects" / "proj-gamma"
        proj_dir.mkdir(parents=True, exist_ok=True)
        sess_file = proj_dir / "sess-003.jsonl"
        # Write a minimal valid session with usage data
        now_iso = "2025-01-15T10:00:00+00:00"
        msg_user = {
            "type": "user",
            "message": {"role": "user", "content": "Hello world"},
            "timestamp": now_iso,
            "cwd": "/tmp/test",
            "entrypoint": "cli",
            "gitBranch": "main"
        }
        msg_assistant = {
            "type": "assistant",
            "message": {
                "type": "message",
                "model": "claude-sonnet-4-20250514",
                "role": "assistant",
                "content": [{"type": "text", "text": "Hi there!"}],
                "usage": {"input_tokens": 500, "output_tokens": 200}
            },
            "timestamp": now_iso
        }
        with open(str(sess_file), "w") as f:
            f.write(json.dumps(msg_user) + "\n")
            f.write(json.dumps(msg_assistant) + "\n")

        result = _run_incremental_scan(str(data_dir), db_path)

        assert result["new_count"] >= 1, (
            f"Expected at least 1 new session, got new_count={result['new_count']}"
        )

        # Verify the new session is in DB
        conn = sqlite3.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        conn.close()

        assert count == 3, f"Expected 3 sessions in DB after adding new one, got {count}"

    def test_scan_log_incr_mode(self, tmp_path):
        """incremental_scan should record scan_log with mode='incremental'."""
        data_dir = tmp_path / "claude_data"
        shutil.copytree(str(FIXTURE_ROOT), str(data_dir))

        db_path = str(tmp_path / "index.sqlite")
        _run_full_scan(str(data_dir), db_path)
        _run_incremental_scan(str(data_dir), db_path)

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        # Should have at least 2 log entries (full + incremental)
        logs = conn.execute(
            "SELECT * FROM scan_log ORDER BY id DESC LIMIT 2"
        ).fetchall()
        assert len(logs) >= 2, f"Expected at least 2 scan_log entries, got {len(logs)}"

        # Most recent should be incremental
        assert logs[0]["mode"] == "incremental", (
            f"Expected most recent scan_log mode='incremental', got '{logs[0]['mode']}'"
        )
        # Second most recent should be full
        assert logs[1]["mode"] == "full", (
            f"Expected second scan_log mode='full', got '{logs[1]['mode']}'"
        )

        conn.close()

    def test_index_count_unchanged_after_incr_skip(self, tmp_path):
        """Incremental scan with no changes should not alter total row count."""
        data_dir = tmp_path / "claude_data"
        shutil.copytree(str(FIXTURE_ROOT), str(data_dir))

        db_path = str(tmp_path / "index.sqlite")
        _run_full_scan(str(data_dir), db_path)

        conn = sqlite3.connect(db_path)
        count_before = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        conn.close()

        _run_incremental_scan(str(data_dir), db_path)

        conn = sqlite3.connect(db_path)
        count_after = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        conn.close()

        assert count_before == count_after, (
            f"Session count changed: {count_before} -> {count_after} (expected unchanged)"
        )
