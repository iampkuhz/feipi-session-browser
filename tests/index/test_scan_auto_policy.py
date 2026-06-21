"""scan auto/full/incremental decision policy tests."""

from __future__ import annotations

from contextlib import contextmanager
import argparse
import sqlite3

import pytest

from session_browser.cli import _decide_scan_mode, cmd_scan
from session_browser.domain.models import SessionSummary
from session_browser.index.schema import (
    SCAN_LOGIC_VERSION,
    get_stored_scan_logic_version,
    init_schema,
    set_stored_scan_logic_version,
)
from session_browser.index.writers import upsert_session


def _args(**overrides) -> argparse.Namespace:
    values = {
        "full": False,
        "incremental": False,
        "agent": None,
        "force": True,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def _connect(path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _seed_current_session(conn: sqlite3.Connection) -> None:
    summary = SessionSummary(
        agent="codex",
        session_id="scan-policy",
        title="scan policy",
        project_key="/repo",
        project_name="repo",
        cwd="/repo",
        started_at="2026-06-20T00:00:00+00:00",
        ended_at="2026-06-20T00:01:00+00:00",
    )
    upsert_session(conn, summary, file_mtime=1, file_path="/tmp/scan-policy.jsonl")
    conn.commit()


def test_auto_scan_prefers_incremental_for_current_existing_index(tmp_path, monkeypatch):
    monkeypatch.delenv("SESSION_BROWSER_DEV_SCAN_LOGIC_VERSION_GATE", raising=False)
    monkeypatch.delenv("SESSION_BROWSER_ENABLE_SCAN_LOGIC_VERSION_GATE", raising=False)
    conn = _connect(tmp_path / "index.sqlite")
    init_schema(conn)
    _seed_current_session(conn)

    assert _decide_scan_mode(conn, _args()) == ("incremental", "auto")

    conn.close()


def test_auto_scan_uses_full_for_empty_or_incompatible_index(tmp_path, monkeypatch):
    monkeypatch.delenv("SESSION_BROWSER_DEV_SCAN_LOGIC_VERSION_GATE", raising=False)
    monkeypatch.delenv("SESSION_BROWSER_ENABLE_SCAN_LOGIC_VERSION_GATE", raising=False)
    conn = _connect(tmp_path / "index.sqlite")

    assert _decide_scan_mode(conn, _args()) == ("full", "index schema missing")

    init_schema(conn)
    assert _decide_scan_mode(conn, _args()) == ("full", "index empty")

    conn.execute("ALTER TABLE sessions RENAME TO sessions_current")
    conn.execute("CREATE TABLE sessions (session_key TEXT PRIMARY KEY)")
    conn.commit()
    assert _decide_scan_mode(conn, _args()) == ("full", "index schema incompatible")

    conn.close()


def test_explicit_scan_modes_override_auto_decision(tmp_path, monkeypatch):
    monkeypatch.setenv("SESSION_BROWSER_DEV_SCAN_LOGIC_VERSION_GATE", "1")
    conn = _connect(tmp_path / "index.sqlite")
    init_schema(conn)
    _seed_current_session(conn)
    set_stored_scan_logic_version(conn, "older")

    assert _decide_scan_mode(conn, _args(full=True)) == ("full", "explicit --full")
    assert _decide_scan_mode(conn, _args(incremental=True)) == (
        "incremental",
        "explicit --incremental",
    )

    conn.close()


def test_dev_scan_logic_version_mismatch_triggers_full(tmp_path, monkeypatch):
    monkeypatch.setenv("SESSION_BROWSER_DEV_SCAN_LOGIC_VERSION_GATE", "1")
    conn = _connect(tmp_path / "index.sqlite")
    init_schema(conn)
    _seed_current_session(conn)
    set_stored_scan_logic_version(conn, "1")

    mode, reason = _decide_scan_mode(conn, _args())

    assert mode == "full"
    assert reason == f"scan logic version changed 1 -> {SCAN_LOGIC_VERSION}"

    set_stored_scan_logic_version(conn)
    assert _decide_scan_mode(conn, _args()) == ("incremental", "auto")

    conn.close()


def test_full_schema_rebuild_clears_stale_logic_version(tmp_path):
    """失败的 full scan 不能留下可使下次 auto 误判的 current version。"""
    conn = _connect(tmp_path / "index.sqlite")
    init_schema(conn)
    _seed_current_session(conn)
    set_stored_scan_logic_version(conn)
    conn.commit()

    init_schema(conn)

    assert get_stored_scan_logic_version(conn) is None
    conn.close()


def test_successful_full_all_agent_scan_writes_logic_version(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SESSION_BROWSER_DEV_SCAN_LOGIC_VERSION_GATE", "1")
    db_path = tmp_path / "index.sqlite"

    _patch_cmd_scan_runtime(monkeypatch, db_path)

    cmd_scan(_args(full=True))
    capsys.readouterr()

    conn = _connect(db_path)
    try:
        assert get_stored_scan_logic_version(conn) == str(SCAN_LOGIC_VERSION)
    finally:
        conn.close()


def test_failed_or_partial_full_scan_does_not_write_global_logic_version(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SESSION_BROWSER_DEV_SCAN_LOGIC_VERSION_GATE", "1")

    partial_db = tmp_path / "partial.sqlite"
    _patch_cmd_scan_runtime(monkeypatch, partial_db)
    cmd_scan(_args(full=True, agent="codex"))
    capsys.readouterr()
    conn = _connect(partial_db)
    try:
        assert get_stored_scan_logic_version(conn) is None
    finally:
        conn.close()

    failed_db = tmp_path / "failed.sqlite"
    _patch_cmd_scan_runtime(monkeypatch, failed_db, fail_full=True)
    with pytest.raises(RuntimeError):
        cmd_scan(_args(full=True))
    conn = _connect(failed_db)
    try:
        assert get_stored_scan_logic_version(conn) is None
    finally:
        conn.close()


def _patch_cmd_scan_runtime(monkeypatch, db_path, *, fail_full: bool = False) -> None:
    from session_browser import cli
    from session_browser.index import indexer

    @contextmanager
    def fake_scan_lock(*_args, **_kwargs):
        yield

    def fake_full_scan(_conn, *, verbose: bool, agent: str | None):
        if fail_full:
            raise RuntimeError("forced full scan failure")
        return {
            "claude_count": 1 if agent is None else 0,
            "codex_count": 1 if agent in (None, "codex") else 0,
            "qoder_count": 1 if agent is None else 0,
            "total": 3 if agent is None else 1,
        }

    def fake_incremental_scan(*_args, **_kwargs):  # pragma: no cover - defensive
        raise AssertionError("expected full scan")

    monkeypatch.setattr(cli, "_find_running_scan_pid", lambda: None)
    monkeypatch.setattr(cli, "_scan_lock", fake_scan_lock)
    monkeypatch.setattr(indexer, "_get_connection", lambda: _connect(db_path))
    monkeypatch.setattr(indexer, "full_scan", fake_full_scan)
    monkeypatch.setattr(indexer, "incremental_scan", fake_incremental_scan)
