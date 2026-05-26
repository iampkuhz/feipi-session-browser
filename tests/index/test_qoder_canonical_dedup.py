"""Canonical UUID dedup test for Qoder projects/cache sessions.

Validates that when the same Qoder session appears in both:
  - projects/<project>/<uuid>.jsonl  (CLI, full UUID)
  - cache/projects/<project>/conversation-history/<short>/<short>.jsonl  (GUI, short ID alias)

The sessions table should contain only ONE record keyed by the full UUID
canonical, not two separate records.

Tests the S-08 scenario: Qoder short ID vs full UUID dedup.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

import pytest

# ─── Fixtures ───────────────────────────────────────────────────────────────

# Full UUID canonical
FULL_UUID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"

# Short ID alias (same session, different key) — must be a prefix of FULL_UUID
# for exact UUID prefix match canonicalization
SHORT_ID = "a1b2c3d4"

PROJECT_NAME = "myproj"

# Minimal Qoder JSONL session content (valid events with timestamps + usage)
SESSION_JSONL_LINES = [
    json.dumps({
        "type": "user",
        "message": {"role": "user", "content": "Hello, help me write a test."},
        "timestamp": "2026-05-01T10:00:00.000Z",
        "cwd": "/tmp/myproj",
        "entrypoint": "cli",
        "sessionId": FULL_UUID,
        "version": "1.0.0",
    }),
    json.dumps({
        "type": "assistant",
        "message": {
            "model": "qwen3.6-plus",
            "role": "assistant",
            "content": [{"type": "text", "text": "Sure, here is a test."}],
            "usage": {"input_tokens": 100, "output_tokens": 50},
        },
        "timestamp": "2026-05-01T10:00:05.000Z",
        "sessionId": FULL_UUID,
        "version": "1.0.0",
    }),
    json.dumps({
        "type": "user",
        "message": {"role": "user", "content": "Thanks!"},
        "timestamp": "2026-05-01T10:00:10.000Z",
        "sessionId": FULL_UUID,
        "version": "1.0.0",
    }),
    json.dumps({
        "type": "assistant",
        "message": {
            "model": "qwen3.6-plus",
            "role": "assistant",
            "content": [{"type": "text", "text": "You are welcome!"}],
            "usage": {"input_tokens": 150, "output_tokens": 30},
        },
        "timestamp": "2026-05-01T10:00:15.000Z",
        "sessionId": FULL_UUID,
        "version": "1.0.0",
    }),
]

SESSION_JSONL_CONTENT = "\n".join(SESSION_JSONL_LINES) + "\n"


# ─── Helpers ────────────────────────────────────────────────────────────────

def _setup_qoder_env(data_dir: str):
    """Set QODER_DATA_DIR and reload dependent modules."""
    old = os.environ.get("QODER_DATA_DIR", None)
    os.environ["QODER_DATA_DIR"] = data_dir

    # Reload config + sources so they pick up the new env var
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


def _create_fixture(tmp_path: Path) -> Path:
    """Create temp Qoder data dir with projects + cache session files."""
    data_dir = tmp_path / "qoder_data"

    # projects/<project>/<FULL_UUID>.jsonl
    projects_dir = data_dir / "projects" / PROJECT_NAME
    projects_dir.mkdir(parents=True, exist_ok=True)
    (projects_dir / f"{FULL_UUID}.jsonl").write_text(SESSION_JSONL_CONTENT)

    # cache/projects/<project>/conversation-history/<SHORT_ID>/<SHORT_ID>.jsonl
    cache_dir = data_dir / "cache" / "projects" / PROJECT_NAME / "conversation-history" / SHORT_ID
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / f"{SHORT_ID}.jsonl").write_text(SESSION_JSONL_CONTENT)

    return data_dir


def _run_full_scan(data_dir: str, db_path: str) -> dict:
    """Run full_scan() against data_dir, returning scan statistics."""
    old_env = _setup_qoder_env(data_dir)
    try:
        from session_browser.index.indexer import full_scan

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        result = full_scan(conn, verbose=False, agent="qoder")
        conn.close()
        return result
    finally:
        _restore_qoder_env(old_env)


# ─── Tests ──────────────────────────────────────────────────────────────────

class TestQoderCanonicalDedup:
    """T012: Qoder short ID vs full UUID dedup — projects/cache overlap."""

    def test_no_duplicate_session_records(self, tmp_path):
        """When the same session exists in both projects/ and cache/,
        the sessions table should have only ONE record, not two.

        This is the core S-08 assertion: canonical UUID dedup must prevent
        two list entries for the same logical session.
        """
        data_dir = _create_fixture(tmp_path)
        db_path = str(tmp_path / "index.sqlite")
        result = _run_full_scan(str(data_dir), db_path)

        conn = sqlite3.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        conn.close()

        assert count == 1, (
            f"Expected 1 session record (canonical UUID dedup), got {count}. "
            f"Full UUID ({FULL_UUID}) and short ID ({SHORT_ID}) refer to the "
            f"same Qoder session and should not produce duplicate list entries."
        )

    def test_canonical_key_is_full_uuid(self, tmp_path):
        """The surviving session should be keyed by the full UUID, not the short ID alias."""
        data_dir = _create_fixture(tmp_path)
        db_path = str(tmp_path / "index.sqlite")
        _run_full_scan(str(data_dir), db_path)

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        canonical_key = f"qoder:{FULL_UUID}"
        row = conn.execute(
            "SELECT session_key, session_id FROM sessions WHERE session_key = ?",
            (canonical_key,),
        ).fetchone()

        assert row is not None, (
            f"Canonical session_key '{canonical_key}' not found. "
            f"The full UUID should be the canonical key, not the short ID."
        )
        assert row["session_id"] == FULL_UUID, (
            f"session_id should be the full UUID ({FULL_UUID}), "
            f"got '{row['session_id']}'."
        )

        # Short ID should NOT produce a separate record
        short_key = f"qoder:{SHORT_ID}"
        short_row = conn.execute(
            "SELECT session_key FROM sessions WHERE session_key = ?",
            (short_key,),
        ).fetchone()
        assert short_row is None, (
            f"Short ID key '{short_key}' should not exist as a separate record. "
            f"It is an alias of the full UUID canonical session."
        )

        conn.close()

    def test_total_count_matches_canonical(self, tmp_path):
        """full_scan total count should be 1, not 2."""
        data_dir = _create_fixture(tmp_path)
        db_path = str(tmp_path / "index.sqlite")
        result = _run_full_scan(str(data_dir), db_path)

        assert result["qoder_count"] == 1, (
            f"Expected qoder_count=1 after dedup, got {result['qoder_count']}"
        )
        assert result["total"] == 1, (
            f"Expected total=1 after dedup, got {result['total']}"
        )

    def test_fixture_data_isolated(self, tmp_path):
        """Scan should not touch real ~/.qoder/ when using fixture."""
        data_dir = _create_fixture(tmp_path)
        db_path = str(tmp_path / "index.sqlite")
        result = _run_full_scan(str(data_dir), db_path)

        # Should only see our 1 canonical session, nothing from real ~/.qoder/
        assert result["total"] == 1, (
            "Index should only contain the fixture session, not real data"
        )
