"""Qoder incremental scan: file_path/model update tests.

Validates that incremental_scan correctly:
1. Updates file_path for old records that have timing data but missing file_path.
2. Re-parses records with empty model to fill it in (without mtime change).
3. Still skips complete records (file_path + model + timing) when mtime unchanged.

Tests use monkeypatched tmp QODER_DATA_DIR -- no real user data.
"""

from __future__ import annotations

import pytest
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

# ─── Constants ──────────────────────────────────────────────────────────────

FULL_UUID = "b2c3d4e5-f6a7-8901-bcde-f23456789012"
PROJECT_NAME = "testproj"

# Minimal Qoder CLI JSONL with usage data + tool calls (produces timing + model)
CLI_JSONL_LINES = [
    json.dumps({
        "type": "user",
        "message": {"role": "user", "content": "Hello"},
        "timestamp": "2026-05-01T10:00:00.000Z",
        "cwd": "/tmp/testproj",
        "entrypoint": "cli",
        "sessionId": FULL_UUID,
        "version": "1.0.0",
    }),
    json.dumps({
        "type": "assistant",
        "message": {
            "model": "qwen3.6-plus",
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": "tool-001", "name": "Read", "input": {"file_path": "/tmp/test.py"}}
            ],
            "usage": {"input_tokens": 50, "output_tokens": 20},
        },
        "timestamp": "2026-05-01T10:00:02.000Z",
        "sessionId": FULL_UUID,
        "version": "1.0.0",
    }),
    json.dumps({
        "type": "user",
        "message": {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": "tool-001", "content": "file content"}],
        },
        "timestamp": "2026-05-01T10:00:04.000Z",
        "sessionId": FULL_UUID,
        "version": "1.0.0",
    }),
    json.dumps({
        "type": "assistant",
        "message": {
            "model": "qwen3.6-plus",
            "role": "assistant",
            "content": [{"type": "text", "text": "Hi there!"}],
            "usage": {"input_tokens": 100, "output_tokens": 30},
        },
        "timestamp": "2026-05-01T10:00:05.000Z",
        "sessionId": FULL_UUID,
        "version": "1.0.0",
    }),
]
CLI_JSONL_CONTENT = "\n".join(CLI_JSONL_LINES) + "\n"


# ─── Helpers ────────────────────────────────────────────────────────────────

def _setup_qoder_env(data_dir: str):
    """Set QODER_DATA_DIR and reload dependent modules."""
    old = os.environ.get("QODER_DATA_DIR", None)
    os.environ["QODER_DATA_DIR"] = data_dir

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


def _restore_qoder_env(old: str | None):
    """Restore original QODER_DATA_DIR."""
    if old is not None:
        os.environ["QODER_DATA_DIR"] = old
    else:
        os.environ.pop("QODER_DATA_DIR", None)


def _run_full_scan(data_dir: str, db_path: str) -> dict:
    """Run full_scan for Qoder only."""
    old = _setup_qoder_env(data_dir)
    try:
        from session_browser.index.indexer import full_scan

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        result = full_scan(conn, verbose=False, agent="qoder")
        conn.close()
        return result
    finally:
        _restore_qoder_env(old)


def _run_incremental_scan(data_dir: str, db_path: str) -> dict:
    """Run incremental_scan for Qoder only."""
    old = _setup_qoder_env(data_dir)
    try:
        from session_browser.index.indexer import incremental_scan

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        result = incremental_scan(conn, verbose=False, agent="qoder")
        conn.close()
        return result
    finally:
        _restore_qoder_env(old)


def _create_qoder_project(data_dir: Path, project_name: str, session_id: str,
                          jsonl_content: str) -> Path:
    """Create a Qoder project directory with a session file."""
    proj_dir = data_dir / "projects" / project_name
    proj_dir.mkdir(parents=True, exist_ok=True)
    sess_file = proj_dir / f"{session_id}.jsonl"
    sess_file.write_text(jsonl_content)
    return sess_file


# ─── Tests ──────────────────────────────────────────────────────────────────

class TestQoderIncrementalFilepathUpdate:
    """Validate that incremental scan updates file_path for old records."""

    @pytest.mark.contract_case("DATA-INDEX-009")
    def test_empty_file_path_gets_populated_without_mtime_change(self, tmp_path):
        """Old record with timing data but empty file_path should be updated.

        Scenario: full_scan was run with a bug that didn't save file_path,
        or file_path was cleared. Incremental scan should locate the file
        and update file_path WITHOUT requiring an mtime change.
        """
        data_dir = tmp_path / "qoder_data"
        _create_qoder_project(data_dir, PROJECT_NAME, FULL_UUID, CLI_JSONL_CONTENT)

        db_path = str(tmp_path / "index.sqlite")

        # Step 1: full scan to create the record
        _run_full_scan(str(data_dir), db_path)

        # Step 2: Manually clear file_path to simulate the bug scenario
        conn = sqlite3.connect(db_path)
        skey = f"qoder:{FULL_UUID}"
        conn.execute(
            "UPDATE sessions SET file_path = '' WHERE session_key = ?",
            (skey,),
        )
        conn.commit()

        # Verify file_path is empty
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT file_path, model, model_execution_seconds, tool_execution_seconds FROM sessions WHERE session_key = ?",
            (skey,),
        ).fetchone()
        assert row["file_path"] == "", "Precondition: file_path should be empty"
        assert row["model"] != "", "Precondition: model should be set"
        conn.close()

        # Step 3: Run incremental scan WITHOUT any file change
        result = _run_incremental_scan(str(data_dir), db_path)

        # The record should have been re-processed (not skipped)
        assert result["qoder_count"] >= 1, (
            f"Expected at least 1 re-indexed Qoder session (file_path update), "
            f"got qoder_count={result['qoder_count']}, skipped={result.get('skipped', 0)}"
        )

        # Verify file_path is now populated
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT file_path FROM sessions WHERE session_key = ?",
            (skey,),
        ).fetchone()
        assert row["file_path"] != "", (
            f"file_path should be populated after incremental scan, got: '{row['file_path']}'"
        )
        assert FULL_UUID in row["file_path"], (
            f"file_path should contain session ID, got: '{row['file_path']}'"
        )
        conn.close()

    @pytest.mark.contract_case("DATA-INDEX-009")
    def test_empty_model_gets_reparsed_without_mtime_change(self, tmp_path):
        """Old record with timing data but empty model should be re-parsed.

        Scenario: model field was empty due to a parsing bug. Incremental
        scan should re-parse to fill in the model WITHOUT requiring mtime change.
        """
        data_dir = tmp_path / "qoder_data"
        _create_qoder_project(data_dir, PROJECT_NAME, FULL_UUID, CLI_JSONL_CONTENT)

        db_path = str(tmp_path / "index.sqlite")

        # Step 1: full scan
        _run_full_scan(str(data_dir), db_path)

        # Step 2: Manually clear model to simulate the bug scenario
        conn = sqlite3.connect(db_path)
        skey = f"qoder:{FULL_UUID}"
        conn.execute(
            "UPDATE sessions SET model = '' WHERE session_key = ?",
            (skey,),
        )
        conn.commit()

        # Verify model is empty
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT model, file_path FROM sessions WHERE session_key = ?",
            (skey,),
        ).fetchone()
        assert row["model"] == "", "Precondition: model should be empty"
        assert row["file_path"] != "", "Precondition: file_path should be set"
        conn.close()

        # Step 3: incremental scan WITHOUT file change
        result = _run_incremental_scan(str(data_dir), db_path)

        # Record should be re-processed (not skipped) because model is empty
        assert result["qoder_count"] >= 1, (
            f"Expected at least 1 re-indexed Qoder session (model fill), "
            f"got qoder_count={result['qoder_count']}, skipped={result.get('skipped', 0)}"
        )

        # Verify model is now populated
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT model FROM sessions WHERE session_key = ?",
            (skey,),
        ).fetchone()
        assert row["model"] != "", (
            f"model should be populated after incremental scan, got: '{row['model']}'"
        )
        assert "qwen" in row["model"].lower(), (
            f"model should contain the correct model name, got: '{row['model']}'"
        )
        conn.close()

    @pytest.mark.contract_case("DATA-INDEX-009")
    def test_complete_record_still_skipped_on_unchanged_mtime(self, tmp_path):
        """Complete record (file_path + model + timing) should still be skipped.

        This validates the performance contract: normal records should NOT
        be re-parsed on every incremental scan.
        """
        data_dir = tmp_path / "qoder_data"
        _create_qoder_project(data_dir, PROJECT_NAME, FULL_UUID, CLI_JSONL_CONTENT)

        db_path = str(tmp_path / "index.sqlite")

        # Step 1: full scan
        _run_full_scan(str(data_dir), db_path)

        # Verify record is complete
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        skey = f"qoder:{FULL_UUID}"
        row = conn.execute(
            "SELECT file_path, model, model_execution_seconds, tool_execution_seconds "
            "FROM sessions WHERE session_key = ?",
            (skey,),
        ).fetchone()
        assert row["file_path"] != "", "Precondition: file_path should be set"
        assert row["model"] != "", "Precondition: model should be set"
        conn.close()

        # Step 2: incremental scan WITHOUT any file change
        result = _run_incremental_scan(str(data_dir), db_path)

        # Record should be skipped (not re-indexed)
        assert result["qoder_count"] == 0, (
            f"Expected 0 re-indexed sessions (complete record, no change), "
            f"got qoder_count={result['qoder_count']}"
        )
        assert result["skipped"] >= 1, (
            f"Expected at least 1 skipped session, got skipped={result.get('skipped', 0)}"
        )

    @pytest.mark.contract_case("DATA-INDEX-009")
    def test_deleted_file_path_gets_relocated(self, tmp_path):
        """Record with file_path pointing to deleted file should relocate.

        Scenario: session file was moved to a different project directory.
        Incremental scan should find the new location and update file_path.
        """
        data_dir = tmp_path / "qoder_data"

        # Create session in original project
        sess_file = _create_qoder_project(
            data_dir, PROJECT_NAME, FULL_UUID, CLI_JSONL_CONTENT
        )

        db_path = str(tmp_path / "index.sqlite")

        # Step 1: full scan
        _run_full_scan(str(data_dir), db_path)

        # Step 2: Move the file to a different project directory
        new_proj = "movedproj"
        new_proj_dir = data_dir / "projects" / new_proj
        new_proj_dir.mkdir(parents=True, exist_ok=True)
        new_file = new_proj_dir / f"{FULL_UUID}.jsonl"
        sess_file.rename(new_file)

        # Step 3: incremental scan
        result = _run_incremental_scan(str(data_dir), db_path)

        # Record should be re-processed (file was relocated)
        assert result["qoder_count"] >= 1, (
            f"Expected at least 1 re-indexed session (file relocation), "
            f"got qoder_count={result['qoder_count']}"
        )

        # Verify file_path is updated to new location
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        skey = f"qoder:{FULL_UUID}"
        row = conn.execute(
            "SELECT file_path FROM sessions WHERE session_key = ?",
            (skey,),
        ).fetchone()
        assert new_proj in row["file_path"], (
            f"file_path should contain new project name '{new_proj}', "
            f"got: '{row['file_path']}'"
        )
        conn.close()

    @pytest.mark.contract_case("DATA-INDEX-009")
    def test_both_empty_filepath_and_model_reparsed(self, tmp_path):
        """Record with both empty file_path and model should be re-parsed."""
        data_dir = tmp_path / "qoder_data"
        _create_qoder_project(data_dir, PROJECT_NAME, FULL_UUID, CLI_JSONL_CONTENT)

        db_path = str(tmp_path / "index.sqlite")

        # Step 1: full scan
        _run_full_scan(str(data_dir), db_path)

        # Step 2: Clear both file_path and model
        conn = sqlite3.connect(db_path)
        skey = f"qoder:{FULL_UUID}"
        conn.execute(
            "UPDATE sessions SET file_path = '', model = '' WHERE session_key = ?",
            (skey,),
        )
        conn.commit()
        conn.close()

        # Step 3: incremental scan
        result = _run_incremental_scan(str(data_dir), db_path)

        # Should be re-processed
        assert result["qoder_count"] >= 1, (
            f"Expected at least 1 re-indexed session (both fields empty), "
            f"got qoder_count={result['qoder_count']}"
        )

        # Verify both fields are restored
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT file_path, model FROM sessions WHERE session_key = ?",
            (skey,),
        ).fetchone()
        assert row["file_path"] != "", "file_path should be populated"
        assert row["model"] != "", "model should be populated"
        conn.close()
