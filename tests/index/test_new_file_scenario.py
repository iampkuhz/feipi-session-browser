"""New file scenario tests for incremental scan.

Validates that incremental_scan() correctly discovers and indexes
new session JSONL files that appear after the initial full scan.
"""

import json
import os
import shutil
import sqlite3
import sys
import time
from pathlib import Path

import pytest

# ─── Constants ──────────────────────────────────────────────────────────────

FIXTURE_ROOT = Path(__file__).parent.parent / "fixtures" / "index_corpus" / "full_scan_claude"

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


def _create_valid_session_file(path: Path):
    """Write a minimal valid session JSONL file with usage data."""
    now_iso = "2025-01-15T10:00:00+00:00"
    msg_user = {
        "type": "user",
        "message": {"role": "user", "content": "Hello world"},
        "timestamp": now_iso,
        "cwd": "/tmp/test",
        "entrypoint": "cli",
        "gitBranch": "main",
    }
    msg_assistant = {
        "type": "assistant",
        "message": {
            "type": "message",
            "model": "claude-sonnet-4-20250514",
            "role": "assistant",
            "content": [{"type": "text", "text": "Hi there!"}],
            "usage": {"input_tokens": 500, "output_tokens": 200},
        },
        "timestamp": now_iso,
    }
    with open(str(path), "w") as f:
        f.write(json.dumps(msg_user) + "\n")
        f.write(json.dumps(msg_assistant) + "\n")


# ─── Tests ──────────────────────────────────────────────────────────────────


class TestNewFileScenario:
    """N01: incremental_scan discovers and indexes new session files."""

    def test_new_session_file_discovered_and_indexed(self, tmp_path):
        """Adding a new session JSONL file after initial scan should be discovered and indexed.

        Steps:
        1. Build initial index with full_scan (2 sessions).
        2. Append a new entry to history.jsonl and create the corresponding session JSONL file.
        3. Update the session file mtime to ensure detectability.
        4. Run incremental_scan.
        5. Verify the new session is discovered and indexed.
        6. Verify index count increased by exactly 1.
        """
        data_dir = tmp_path / "claude_data"
        shutil.copytree(str(FIXTURE_ROOT), str(data_dir))

        db_path = str(tmp_path / "index.sqlite")

        # Step 1: Build initial index
        _run_full_scan(str(data_dir), db_path)

        conn = sqlite3.connect(db_path)
        count_before = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        conn.close()
        assert count_before == 2, f"Expected 2 initial sessions, got {count_before}"

        # Step 2: Append new session entry to history.jsonl
        history_path = data_dir / "history.jsonl"
        new_history_entry = {
            "sessionId": "sess-003",
            "project": "proj-gamma",
            "timestamp": int(time.time() * 1000),
            "display": "New session test",
        }
        with open(str(history_path), "a") as f:
            f.write(json.dumps(new_history_entry) + "\n")

        # Create the new session file under a new project directory
        proj_dir = data_dir / "projects" / "proj-gamma"
        proj_dir.mkdir(parents=True, exist_ok=True)
        new_session_file = proj_dir / "sess-003.jsonl"
        _create_valid_session_file(new_session_file)

        # Step 3: Update mtime to ensure it is detectable
        time.sleep(0.05)
        new_stat = os.stat(str(new_session_file))
        new_mtime = new_stat.st_mtime + 1.0
        os.utime(str(new_session_file), (new_mtime, new_mtime))

        # Step 4: Run incremental scan
        result = _run_incremental_scan(str(data_dir), db_path)

        # Step 5: Verify new session is discovered
        assert result["new_count"] >= 1, (
            f"Expected at least 1 new session from incremental scan, "
            f"got new_count={result['new_count']}"
        )

        # Step 6: Verify index count increased by exactly 1
        conn = sqlite3.connect(db_path)
        count_after = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        conn.close()

        assert count_after == count_before + 1, (
            f"Expected index count to increase by 1: {count_before} -> {count_before + 1}, "
            f"got {count_after}"
        )

    def test_new_session_queryable_in_db(self, tmp_path):
        """A newly indexed session should be queryable from the sessions table.

        Verifies that the new session appears in the database with correct
        session_key and project information after incremental scan.
        """
        data_dir = tmp_path / "claude_data"
        shutil.copytree(str(FIXTURE_ROOT), str(data_dir))

        db_path = str(tmp_path / "index.sqlite")
        _run_full_scan(str(data_dir), db_path)

        # Append new session entry to history.jsonl
        history_path = data_dir / "history.jsonl"
        new_history_entry = {
            "sessionId": "sess-003",
            "project": "proj-gamma",
            "timestamp": int(time.time() * 1000),
            "display": "New session test",
        }
        with open(str(history_path), "a") as f:
            f.write(json.dumps(new_history_entry) + "\n")

        # Create new session file
        proj_dir = data_dir / "projects" / "proj-gamma"
        proj_dir.mkdir(parents=True, exist_ok=True)
        new_session_file = proj_dir / "sess-003.jsonl"
        _create_valid_session_file(new_session_file)

        time.sleep(0.05)
        new_stat = os.stat(str(new_session_file))
        new_mtime = new_stat.st_mtime + 1.0
        os.utime(str(new_session_file), (new_mtime, new_mtime))

        _run_incremental_scan(str(data_dir), db_path)

        # Query the new session
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM sessions WHERE session_key = 'claude_code:sess-003'"
        ).fetchone()
        conn.close()

        assert row is not None, "New session 'sess-003' should be queryable in DB"
        assert row["session_id"] == "sess-003", (
            f"Expected session_id='sess-003', got '{row['session_id']}'"
        )
        assert row["project_key"] == "proj-gamma", (
            f"Expected project_key='proj-gamma', got '{row['project_key']}'"
        )

    def test_multiple_new_sessions_discovered(self, tmp_path):
        """Adding multiple new session files should all be discovered by incremental scan.

        Verifies that incremental scan can handle batch additions
        and correctly indexes all new sessions.
        """
        data_dir = tmp_path / "claude_data"
        shutil.copytree(str(FIXTURE_ROOT), str(data_dir))

        db_path = str(tmp_path / "index.sqlite")
        _run_full_scan(str(data_dir), db_path)

        conn = sqlite3.connect(db_path)
        count_before = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        conn.close()

        # Append new session entries to history.jsonl and create session files
        history_path = data_dir / "history.jsonl"
        for proj, sess in [("proj-gamma", "sess-003"), ("proj-delta", "sess-004")]:
            new_history_entry = {
                "sessionId": sess,
                "project": proj,
                "timestamp": int(time.time() * 1000),
                "display": f"New session {sess}",
            }
            with open(str(history_path), "a") as f:
                f.write(json.dumps(new_history_entry) + "\n")

            proj_dir = data_dir / "projects" / proj
            proj_dir.mkdir(parents=True, exist_ok=True)
            new_session_file = proj_dir / f"{sess}.jsonl"
            _create_valid_session_file(new_session_file)

            time.sleep(0.05)
            new_stat = os.stat(str(new_session_file))
            new_mtime = new_stat.st_mtime + 1.0
            os.utime(str(new_session_file), (new_mtime, new_mtime))

        result = _run_incremental_scan(str(data_dir), db_path)

        assert result["new_count"] >= 2, (
            f"Expected at least 2 new sessions, got new_count={result['new_count']}"
        )

        conn = sqlite3.connect(db_path)
        count_after = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        conn.close()

        assert count_after == count_before + 2, (
            f"Expected index count to increase by 2: {count_before} -> {count_before + 2}, "
            f"got {count_after}"
        )
