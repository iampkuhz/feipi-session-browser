"""Session artifact schema and normalized JSON persistence tests."""

from __future__ import annotations

import sqlite3

from session_browser.cli import _ensure_schema_exists
from session_browser.domain.models import SessionSummary
from session_browser.index.schema import init_schema
from session_browser.index.writers import upsert_session
from session_browser.normalized.artifacts import (
    NORMALIZED_SESSION_ARTIFACT_TYPE,
    persist_current_normalized_session_artifact_reference,
    persist_normalized_session_artifact,
    read_normalized_session_artifact,
)
from session_browser.normalized.schema import NORMALIZED_SCHEMA_VERSION


def test_persist_normalized_session_artifact_writes_file_and_db_row(tmp_path):
    db_path = tmp_path / "index.sqlite"
    index_dir = tmp_path / "index"
    source_path = tmp_path / "source" / "rollout.jsonl"
    source_path.parent.mkdir(parents=True)
    source_path.write_text('{"type":"session_meta"}\n', encoding="utf-8")
    source_mtime = source_path.stat().st_mtime
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    init_schema(conn)

    summary = SessionSummary(
        agent="codex",
        session_id="session/unsafe",
        title="artifact test",
        project_key="/tmp/project",
        project_name="project",
        cwd="/tmp/project",
        started_at="2026-06-10T00:00:00+00:00",
        ended_at="2026-06-10T00:01:00+00:00",
        total_tokens=42,
    )
    upsert_session(
        conn,
        summary,
        file_mtime=source_mtime,
        file_path=str(source_path),
    )

    normalized = {
        "schema_version": NORMALIZED_SCHEMA_VERSION,
        "agent": "codex",
        "session": {
            "session_key": "codex:session/unsafe",
            "session_id": "session/unsafe",
            "agent": "codex",
        },
        "rounds": [],
        "tool_result_links": [],
        "payload_index": {"items": []},
        "diagnostics": {"token_timeline": []},
    }
    artifact_path = persist_normalized_session_artifact(
        conn,
        normalized,
        source_path=str(source_path),
        source_mtime=source_mtime,
        index_dir=index_dir,
    )
    conn.commit()

    assert artifact_path == index_dir / "artifacts" / "normalized-sessions" / "codex" / "session_unsafe.json"
    assert read_normalized_session_artifact(artifact_path) == normalized
    meta_path = artifact_path.with_suffix(artifact_path.suffix + ".meta.json")
    assert meta_path.is_file()

    row = conn.execute(
        """
        SELECT * FROM session_artifacts
        WHERE session_key = ? AND artifact_type = ?
        """,
        ("codex:session/unsafe", NORMALIZED_SESSION_ARTIFACT_TYPE),
    ).fetchone()
    assert row is not None
    assert row["path"] == str(artifact_path)
    assert row["schema_version"] == NORMALIZED_SCHEMA_VERSION
    assert row["source_path"] == str(source_path)
    assert row["source_mtime"] == source_mtime
    assert row["size_bytes"] == artifact_path.stat().st_size
    assert row["created_at"] > 0
    assert row["updated_at"] >= row["created_at"]

    conn.close()


def test_persist_current_normalized_artifact_reference_reuses_matching_sidecar(tmp_path):
    db_path = tmp_path / "index.sqlite"
    index_dir = tmp_path / "index"
    source_path = tmp_path / "source.jsonl"
    source_path.write_text('{"type":"session_meta"}\n', encoding="utf-8")
    source_mtime = source_path.stat().st_mtime

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    summary = SessionSummary(
        agent="codex",
        session_id="reuse",
        title="artifact reuse",
        project_key="/tmp/project",
        project_name="project",
        cwd="/tmp/project",
        started_at="2026-06-10T00:00:00+00:00",
        ended_at="2026-06-10T00:01:00+00:00",
    )
    upsert_session(conn, summary, file_mtime=source_mtime, file_path=str(source_path))
    normalized = {
        "schema_version": NORMALIZED_SCHEMA_VERSION,
        "agent": "codex",
        "session": {
            "session_key": "codex:reuse",
            "session_id": "reuse",
            "agent": "codex",
        },
        "rounds": [],
        "tool_result_links": [],
        "payload_index": {"items": []},
        "diagnostics": {"token_timeline": []},
    }
    artifact_path = persist_normalized_session_artifact(
        conn,
        normalized,
        source_path=str(source_path),
        source_mtime=source_mtime,
        index_dir=index_dir,
    )
    conn.execute("DELETE FROM session_artifacts")

    reused_path = persist_current_normalized_session_artifact_reference(
        conn,
        session_key="codex:reuse",
        source_path=str(source_path),
        source_mtime=source_mtime,
        index_dir=index_dir,
    )

    assert reused_path == artifact_path
    row = conn.execute(
        "SELECT path, size_bytes FROM session_artifacts WHERE session_key = 'codex:reuse'"
    ).fetchone()
    assert row is not None
    assert row["path"] == str(artifact_path)
    assert row["size_bytes"] == artifact_path.stat().st_size
    conn.close()


def test_ensure_schema_exists_creates_artifact_table_for_incremental_scan(tmp_path):
    conn = sqlite3.connect(str(tmp_path / "index.sqlite"))
    conn.row_factory = sqlite3.Row

    _ensure_schema_exists(conn)

    tables = {
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    assert "sessions" in tables
    assert "scan_log" in tables
    assert "session_artifacts" in tables

    session_columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(sessions)").fetchall()
    }
    assert {
        "fresh_input_tokens",
        "cache_read_tokens",
        "cache_write_tokens",
        "total_tokens",
    }.issubset(session_columns)

    artifact_columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(session_artifacts)").fetchall()
    }
    assert {
        "session_key",
        "artifact_type",
        "path",
        "schema_version",
        "source_path",
        "source_mtime",
        "size_bytes",
        "created_at",
        "updated_at",
    }.issubset(artifact_columns)

    conn.close()
