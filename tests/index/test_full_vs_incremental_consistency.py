"""Full vs Incremental scan consistency tests.

Validates that incremental_scan produces the same indexed state as a full_scan
when applied after targeted file modifications. This ensures the incremental
path does not diverge from the canonical full re-index.
"""

import pytest
import json
import os
import shutil
import sqlite3
import sys
import time
from pathlib import Path

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


def _snapshot_db(db_path: str) -> dict:
    """Snapshot the sessions table as a dict keyed by session_key."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM sessions").fetchall()
    snapshot = {}
    for row in rows:
        key = row["session_key"]
        snapshot[key] = dict(row)
    conn.close()
    return snapshot


def _touch_file(file_path: Path, delta_seconds: float = 1.0):
    """Advance a file's mtime by delta_seconds."""
    current_stat = os.stat(str(file_path))
    new_mtime = current_stat.st_mtime + delta_seconds
    os.utime(str(file_path), (new_mtime, new_mtime))


# ─── Tests ──────────────────────────────────────────────────────────────────

class TestFullVsIncrementalConsistency:
    """Consistency assertions between full and incremental scan paths.

    Pipeline: full_scan (baseline) -> modify mtime -> incremental_scan
              -> full_scan (re-baseline) -> assert equality.
    """

    @pytest.mark.contract_case("DATA-INDEX-003")
    def test_single_file_modified_consistency(self, tmp_path):
        """After touching one file, incremental + full re-scan must match.

        Steps:
        1. full_scan establishes baseline (2 sessions).
        2. Touch sess-001's mtime.
        3. incremental_scan re-indexes only sess-001.
        4. full_scan rebuilds everything.
        5. Assert: DB state after incremental matches DB state after full re-scan.
        """
        data_dir = tmp_path / "claude_data"
        shutil.copytree(str(FIXTURE_ROOT), str(data_dir))

        # Step 1: baseline full scan
        db_a = str(tmp_path / "index_a.sqlite")
        _run_full_scan(str(data_dir), db_a)

        snapshot_full_1 = _snapshot_db(db_a)
        assert len(snapshot_full_1) == 2, "Baseline should have 2 sessions"

        # Step 2: touch one file
        time.sleep(0.05)
        sess001_file = data_dir / "projects" / "proj-alpha" / "sess-001.jsonl"
        _touch_file(sess001_file)

        # Step 3: incremental scan
        _run_incremental_scan(str(data_dir), db_a)
        snapshot_incr = _snapshot_db(db_a)
        assert len(snapshot_incr) == 2, "Incremental should still have 2 sessions"

        # Step 4: full re-scan on a fresh DB
        db_b = str(tmp_path / "index_b.sqlite")
        _run_full_scan(str(data_dir), db_b)
        snapshot_full_2 = _snapshot_db(db_b)
        assert len(snapshot_full_2) == 2, "Full re-scan should have 2 sessions"

        # Step 5: assert consistency
        assert set(snapshot_incr.keys()) == set(snapshot_full_2.keys()), (
            f"Session keys mismatch: incr={sorted(snapshot_incr.keys())} "
            f"vs full={sorted(snapshot_full_2.keys())}"
        )

        for key in snapshot_full_2:
            incr_row = snapshot_incr[key]
            full_row = snapshot_full_2[key]
            # Compare key metrics that should be identical
            assert incr_row["input_tokens"] == full_row["input_tokens"], (
                f"input_tokens mismatch for {key}: incr={incr_row['input_tokens']} "
                f"vs full={full_row['input_tokens']}"
            )
            assert incr_row["output_tokens"] == full_row["output_tokens"], (
                f"output_tokens mismatch for {key}"
            )
            assert incr_row["user_message_count"] == full_row["user_message_count"], (
                f"user_message_count mismatch for {key}"
            )
            assert incr_row["assistant_message_count"] == full_row["assistant_message_count"], (
                f"assistant_message_count mismatch for {key}"
            )
            assert incr_row["title"] == full_row["title"], (
                f"title mismatch for {key}: incr='{incr_row['title']}' "
                f"vs full='{full_row['title']}'"
            )
            assert incr_row["agent"] == full_row["agent"], (
                f"agent mismatch for {key}"
            )
            assert incr_row["project_key"] == full_row["project_key"], (
                f"project_key mismatch for {key}"
            )

    @pytest.mark.contract_case("DATA-INDEX-003")
    def test_all_files_modified_consistency(self, tmp_path):
        """After touching all files, incremental must match full re-scan.

        Same pipeline as test_single_file_modified_consistency but touches
        every session file to verify full incremental re-index parity.
        """
        data_dir = tmp_path / "claude_data"
        shutil.copytree(str(FIXTURE_ROOT), str(data_dir))

        # Step 1: baseline full scan
        db_a = str(tmp_path / "index_a.sqlite")
        _run_full_scan(str(data_dir), db_a)

        # Step 2: touch all files
        time.sleep(0.05)
        for proj, sess in [("proj-alpha", "sess-001"), ("proj-beta", "sess-002")]:
            fpath = data_dir / "projects" / proj / f"{sess}.jsonl"
            _touch_file(fpath)

        # Step 3: incremental scan (should re-index both)
        result_incr = _run_incremental_scan(str(data_dir), db_a)
        assert result_incr["claude_count"] == 2, (
            f"Expected 2 re-indexed, got {result_incr['claude_count']}"
        )

        snapshot_incr = _snapshot_db(db_a)

        # Step 4: full re-scan
        db_b = str(tmp_path / "index_b.sqlite")
        _run_full_scan(str(data_dir), db_b)
        snapshot_full = _snapshot_db(db_b)

        # Step 5: consistency assertions
        assert len(snapshot_incr) == len(snapshot_full) == 2

        for key in snapshot_full:
            incr_row = snapshot_incr[key]
            full_row = snapshot_full[key]
            assert incr_row["input_tokens"] == full_row["input_tokens"], (
                f"input_tokens mismatch for {key}"
            )
            assert incr_row["output_tokens"] == full_row["output_tokens"], (
                f"output_tokens mismatch for {key}"
            )
            assert incr_row["title"] == full_row["title"], (
                f"title mismatch for {key}"
            )
            assert incr_row["started_at"] == full_row["started_at"], (
                f"started_at mismatch for {key}"
            )
            assert incr_row["ended_at"] == full_row["ended_at"], (
                f"ended_at mismatch for {key}"
            )

    @pytest.mark.contract_case("DATA-INDEX-003")
    def test_new_session_discovered_consistency(self, tmp_path):
        """After adding a new session, incremental + full must yield same set.

        Steps:
        1. full_scan baseline (2 sessions).
        2. Add a 3rd session file.
        3. incremental_scan discovers it.
        4. full_scan on fresh DB.
        5. Assert: both have 3 sessions with matching metrics.
        """
        data_dir = tmp_path / "claude_data"
        shutil.copytree(str(FIXTURE_ROOT), str(data_dir))

        # Step 1: baseline full scan
        db_a = str(tmp_path / "index_a.sqlite")
        _run_full_scan(str(data_dir), db_a)
        snapshot_full_1 = _snapshot_db(db_a)
        assert len(snapshot_full_1) == 2

        # Step 2: add a new session
        now_iso = "2025-01-15T10:00:00+00:00"
        history_path = data_dir / "history.jsonl"
        new_entry = {
            "sessionId": "sess-003",
            "project": "proj-gamma",
            "timestamp": int(time.time() * 1000),
            "display": "New session test"
        }
        with open(str(history_path), "a") as f:
            f.write(json.dumps(new_entry) + "\n")

        proj_dir = data_dir / "projects" / "proj-gamma"
        proj_dir.mkdir(parents=True, exist_ok=True)
        sess_file = proj_dir / "sess-003.jsonl"

        msg_user = {
            "type": "user",
            "message": {"role": "user", "content": "Hello new session"},
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
                "content": [{"type": "text", "text": "Hi!"}],
                "usage": {"input_tokens": 300, "output_tokens": 100}
            },
            "timestamp": now_iso
        }
        with open(str(sess_file), "w") as f:
            f.write(json.dumps(msg_user) + "\n")
            f.write(json.dumps(msg_assistant) + "\n")

        # Step 3: incremental scan
        result_incr = _run_incremental_scan(str(data_dir), db_a)
        assert result_incr["new_count"] >= 1, (
            f"Expected new session discovery, got new_count={result_incr['new_count']}"
        )
        snapshot_incr = _snapshot_db(db_a)

        # Step 4: full re-scan
        db_b = str(tmp_path / "index_b.sqlite")
        _run_full_scan(str(data_dir), db_b)
        snapshot_full = _snapshot_db(db_b)

        # Step 5: consistency
        assert len(snapshot_incr) == 3, (
            f"Expected 3 sessions after incremental, got {len(snapshot_incr)}"
        )
        assert len(snapshot_full) == 3, (
            f"Expected 3 sessions after full, got {len(snapshot_full)}"
        )
        assert set(snapshot_incr.keys()) == set(snapshot_full.keys()), (
            "Session key sets differ between incremental and full"
        )

        # All three sessions must match on key metrics
        for key in snapshot_full:
            incr_row = snapshot_incr[key]
            full_row = snapshot_full[key]
            assert incr_row["input_tokens"] == full_row["input_tokens"], (
                f"input_tokens mismatch for {key}"
            )
            assert incr_row["output_tokens"] == full_row["output_tokens"], (
                f"output_tokens mismatch for {key}"
            )
            assert incr_row["user_message_count"] == full_row["user_message_count"], (
                f"user_message_count mismatch for {key}"
            )
            assert incr_row["assistant_message_count"] == full_row["assistant_message_count"], (
                f"assistant_message_count mismatch for {key}"
            )

    @pytest.mark.contract_case("DATA-INDEX-003")
    def test_no_changes_consistency(self, tmp_path):
        """With zero file changes, incremental should not alter DB state.

        Steps:
        1. full_scan baseline.
        2. incremental_scan (no changes) -> 0 re-indexed.
        3. full_scan fresh DB.
        4. Assert: both DBs identical.
        """
        data_dir = tmp_path / "claude_data"
        shutil.copytree(str(FIXTURE_ROOT), str(data_dir))

        # Step 1: baseline full scan
        db_a = str(tmp_path / "index_a.sqlite")
        result_full_1 = _run_full_scan(str(data_dir), db_a)
        assert result_full_1["claude_count"] == 2

        # Step 2: incremental with no changes
        result_incr = _run_incremental_scan(str(data_dir), db_a)
        assert result_incr["claude_count"] == 0, (
            f"Expected 0 re-indexed (no changes), got {result_incr['claude_count']}"
        )
        assert result_incr["skipped"] == 2, (
            f"Expected 2 skipped, got {result_incr['skipped']}"
        )

        snapshot_incr = _snapshot_db(db_a)

        # Step 3: full re-scan
        db_b = str(tmp_path / "index_b.sqlite")
        result_full_2 = _run_full_scan(str(data_dir), db_b)

        snapshot_full = _snapshot_db(db_b)

        # Step 4: consistency
        assert len(snapshot_incr) == len(snapshot_full) == 2
        assert set(snapshot_incr.keys()) == set(snapshot_full.keys())

        for key in snapshot_full:
            incr_row = snapshot_incr[key]
            full_row = snapshot_full[key]
            assert incr_row["input_tokens"] == full_row["input_tokens"]
            assert incr_row["output_tokens"] == full_row["output_tokens"]
            assert incr_row["title"] == full_row["title"]

    @pytest.mark.contract_case("DATA-INDEX-003")
    def test_scan_log_mode_full_then_incremental(self, tmp_path):
        """Verify scan_log records full then incremental correctly.

        Pipeline: full_scan -> incremental_scan -> assert scan_log shows
        [full, incremental]. Note: a second full_scan would reset scan_log
        because full_scan calls init_schema() which drops and recreates the
        table. So we only test the full->incremental sequence.
        """
        data_dir = tmp_path / "claude_data"
        shutil.copytree(str(FIXTURE_ROOT), str(data_dir))

        db_path = str(tmp_path / "index.sqlite")

        _run_full_scan(str(data_dir), db_path)

        time.sleep(0.05)
        sess001_file = data_dir / "projects" / "proj-alpha" / "sess-001.jsonl"
        _touch_file(sess001_file)

        _run_incremental_scan(str(data_dir), db_path)

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        logs = conn.execute(
            "SELECT mode FROM scan_log ORDER BY id ASC"
        ).fetchall()
        conn.close()

        modes = [row["mode"] for row in logs]
        assert len(modes) == 2, f"Expected 2 scan_log entries, got {len(modes)}"
        assert modes == ["full", "incremental"], (
            f"Expected mode sequence [full, incremental], got {modes}"
        )
