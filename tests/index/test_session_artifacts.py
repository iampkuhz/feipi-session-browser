"""Session artifact schema 与只读 consumer 测试。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from session_browser.cli import _ensure_schema_exists
from session_browser.domain.models import SessionSummary
from session_browser.index.schema import init_schema
from session_browser.index.writers import upsert_session
from session_browser.normalized.artifacts import (
    NORMALIZED_SESSION_ARTIFACT_TYPE,
    persist_current_normalized_session_artifact_reference,
    read_normalized_session_artifact,
)
from session_browser.normalized.schema import NORMALIZED_SCHEMA_VERSION


def _minimal_normalized(agent: str, session_id: str) -> dict:
    return {
        "schema_version": NORMALIZED_SCHEMA_VERSION,
        "agent": agent,
        "source": {
            "files": [],
        },
        "session": {
            "session_key": f"{agent}:{session_id}",
            "session_id": session_id,
            "agent": agent,
        },
        "calls": [],
        "tool_executions": [],
        "diagnostics": [],
    }


def test_persist_current_normalized_artifact_reference_reuses_matching_sidecar(tmp_path):
    """reader freshness 匹配时，persist_current_reference 正确关联 SQLite 行。"""
    import json

    index_dir = tmp_path / "index"
    index_dir.mkdir()
    db_path = index_dir / "index.sqlite"
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

    # 手动写入 artifact JSON 和 sidecar meta（模拟 Java producer 输出）。
    normalized = _minimal_normalized("codex", "reuse")
    artifact_dir = index_dir / "artifacts" / "normalized-sessions" / "codex"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_dir / "reuse.json"
    artifact_path.write_text(
        json.dumps(normalized, ensure_ascii=False, separators=(',', ':')) + '\n',
        encoding='utf-8',
    )
    meta = {
        'artifact_type': NORMALIZED_SESSION_ARTIFACT_TYPE,
        'generator_version': 'normalized-session-artifact.v6',
        'schema_version': NORMALIZED_SCHEMA_VERSION,
        'source_path': str(source_path),
        'source_mtime': source_mtime,
        'source_size': source_path.stat().st_size,
        'size_bytes': artifact_path.stat().st_size,
    }
    meta_path = artifact_path.with_suffix(artifact_path.suffix + '.meta.json')
    meta_path.write_text(
        json.dumps(meta, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n',
        encoding='utf-8',
    )

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
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    }
    assert "sessions" in tables
    assert "scan_log" in tables
    assert "session_artifacts" in tables
    assert "index_metadata" in tables

    session_columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(sessions)").fetchall()
    }
    assert {
        "fresh_input_tokens",
        "cache_read_tokens",
        "cache_write_tokens",
        "total_tokens",
        "subagent_instance_count",
    }.issubset(session_columns)

    artifact_columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(session_artifacts)").fetchall()
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
