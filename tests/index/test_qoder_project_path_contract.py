"""Qoder project path normalization contract tests.

Validates:
- cwd 存在时：project_key / project_name 使用 cwd 推导
- cwd 缺失时：path-text 不把 '.' 当作完整路径展示

Tests the P-21 scenario: path-text rendering should not show '.' as
a full project path when cwd is missing.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path, PurePosixPath

import pytest

# ─── Constants ──────────────────────────────────────────────────────────────

SESSION_ID = "path-test-session-001"
PROJECT_DIR_NAME = "my-cool-project"

# Minimal Qoder JSONL events for CLI format (has cwd)
CLI_JSONL_LINES = [
    json.dumps({
        "type": "user",
        "message": {"role": "user", "content": "Hello"},
        "timestamp": "2026-05-01T10:00:00.000Z",
        "cwd": "/Users/zhehan/workspace/my-cool-project",
        "entrypoint": "cli",
        "sessionId": SESSION_ID,
        "version": "1.0.0",
    }),
    json.dumps({
        "type": "assistant",
        "message": {
            "model": "qwen3.6-plus",
            "role": "assistant",
            "content": [{"type": "text", "text": "Hi there!"}],
            "usage": {"input_tokens": 50, "output_tokens": 20},
        },
        "timestamp": "2026-05-01T10:00:05.000Z",
        "sessionId": SESSION_ID,
        "version": "1.0.0",
    }),
]

CLI_JSONL_CONTENT = "\n".join(CLI_JSONL_LINES) + "\n"

# Minimal Qoder cache-format JSONL events (no cwd field)
CACHE_JSONL_LINES = [
    json.dumps({
        "role": "user",
        "message": {"content": "Hello from cache"},
    }),
    json.dumps({
        "role": "assistant",
        "message": {"content": [{"type": "text", "text": "Cache response"}]},
    }),
]

CACHE_JSONL_CONTENT = "\n".join(CACHE_JSONL_LINES) + "\n"

# Cache format with cwd-missing CLI-style events (no cwd in user event)
NO_CWD_CLI_JSONL_LINES = [
    json.dumps({
        "type": "user",
        "message": {"role": "user", "content": "Hello no cwd"},
        "timestamp": "2026-05-01T10:00:00.000Z",
        # Deliberately no "cwd" field
        "entrypoint": "cli",
        "sessionId": SESSION_ID,
        "version": "1.0.0",
    }),
    json.dumps({
        "type": "assistant",
        "message": {
            "model": "qwen3.6-plus",
            "role": "assistant",
            "content": [{"type": "text", "text": "Response without cwd"}],
            "usage": {"input_tokens": 30, "output_tokens": 10},
        },
        "timestamp": "2026-05-01T10:00:05.000Z",
        "sessionId": SESSION_ID,
        "version": "1.0.0",
    }),
]

NO_CWD_CLI_JSONL_CONTENT = "\n".join(NO_CWD_CLI_JSONL_LINES) + "\n"


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


def _query_session(db_path: str, session_key: str) -> dict | None:
    """Query a session by session_key and return its row as a dict."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM sessions WHERE session_key = ?",
        (session_key,),
    ).fetchone()
    result = dict(row) if row else None
    conn.close()
    return result


# ─── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture()
def cli_cwd_fixture(tmp_path: Path) -> tuple[Path, str]:
    """Create a Qoder CLI session with cwd field."""
    data_dir = tmp_path / "qoder_cli_cwd"
    projects_dir = data_dir / "projects" / PROJECT_DIR_NAME
    projects_dir.mkdir(parents=True, exist_ok=True)
    (projects_dir / f"{SESSION_ID}.jsonl").write_text(CLI_JSONL_CONTENT)
    return data_dir, "/Users/zhehan/workspace/my-cool-project"


@pytest.fixture()
def no_cwd_cli_fixture(tmp_path: Path) -> tuple[Path, str]:
    """Create a Qoder CLI session without cwd field."""
    data_dir = tmp_path / "qoder_no_cwd_cli"
    projects_dir = data_dir / "projects" / PROJECT_DIR_NAME
    projects_dir.mkdir(parents=True, exist_ok=True)
    (projects_dir / f"{SESSION_ID}.jsonl").write_text(NO_CWD_CLI_JSONL_CONTENT)
    return data_dir, PROJECT_DIR_NAME


@pytest.fixture()
def cache_fixture(tmp_path: Path) -> tuple[Path, str]:
    """Create a Qoder cache-format session (no cwd)."""
    data_dir = tmp_path / "qoder_cache"
    cache_dir = data_dir / "cache" / "projects" / PROJECT_DIR_NAME / "conversation-history" / SESSION_ID
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / f"{SESSION_ID}.jsonl").write_text(CACHE_JSONL_CONTENT)
    return data_dir, PROJECT_DIR_NAME


# ─── Tests ──────────────────────────────────────────────────────────────────

class TestQoderProjectPathContract:
    """T027: Qoder project path normalization contract.

    P-21: path-text 渲染应该只显示有意义的仓库文件夹名或完整路径，
    不应把 '.' 当作完整路径展示。
    """

    def test_cli_session_with_cwd_uses_cwd_as_project_key(self, cli_cwd_fixture, tmp_path):
        """When cwd exists in events, project_key should be derived from cwd,
        not from the directory-based project_key."""
        data_dir, expected_cwd = cli_cwd_fixture
        db_path = str(tmp_path / "index.sqlite")
        _run_full_scan(str(data_dir), db_path)

        session = _query_session(db_path, f"qoder:{SESSION_ID}")
        assert session is not None, "Session should be indexed"

        assert session["cwd"] == expected_cwd, (
            f"cwd should be '{expected_cwd}', got '{session['cwd']}'"
        )
        assert session["project_key"] == expected_cwd, (
            f"project_key should be cwd '{expected_cwd}', "
            f"got '{session['project_key']}'"
        )
        assert session["project_name"] == "my-cool-project", (
            f"project_name should be last segment of cwd, "
            f"got '{session['project_name']}'"
        )

    def test_no_cwd_session_uses_directory_name(self, no_cwd_cli_fixture, tmp_path):
        """When cwd is missing, project_key should use the directory-based
        project_key (URL-decoded path from projects/), and should NOT be '.'."""
        data_dir, expected_project_name = no_cwd_cli_fixture
        db_path = str(tmp_path / "index.sqlite")
        _run_full_scan(str(data_dir), db_path)

        session = _query_session(db_path, f"qoder:{SESSION_ID}")
        assert session is not None, "Session should be indexed"

        # cwd should be empty or missing when not present in events
        assert session["cwd"] == "", (
            f"cwd should be empty when not in events, got '{session['cwd']}'"
        )

        # project_key should be the directory name, NOT '.'
        assert session["project_key"] != ".", (
            f"project_key should not be '.', got '{session['project_key']}'"
        )
        assert session["project_key"] == PROJECT_DIR_NAME, (
            f"project_key should be directory name '{PROJECT_DIR_NAME}', "
            f"got '{session['project_key']}'"
        )
        assert session["project_name"] == PROJECT_DIR_NAME, (
            f"project_name should be '{PROJECT_DIR_NAME}', "
            f"got '{session['project_name']}'"
        )

    def test_cache_session_no_cwd_project_key_not_dot(self, cache_fixture, tmp_path):
        """Cache-format sessions have no cwd; project_key must not be '.'."""
        data_dir, expected_project_name = cache_fixture
        db_path = str(tmp_path / "index.sqlite")
        _run_full_scan(str(data_dir), db_path)

        session = _query_session(db_path, f"qoder:{SESSION_ID}")
        assert session is not None, "Cache session should be indexed"

        assert session["cwd"] == "", (
            f"cache session cwd should be empty, got '{session['cwd']}'"
        )
        assert session["project_key"] != ".", (
            f"cache session project_key should not be '.', "
            f"got '{session['project_key']}'"
        )
        assert session["project_key"] == PROJECT_DIR_NAME, (
            f"cache session project_key should be '{PROJECT_DIR_NAME}', "
            f"got '{session['project_key']}'"
        )

    def test_project_name_is_meaningful_folder_name(self, tmp_path):
        """project_name should always be the last meaningful path segment,
        not '.' or empty."""
        data_dir = tmp_path / "qoder_project_name"
        # Create a session under a normal project directory
        projects_dir = data_dir / "projects" / "real-project-name"
        projects_dir.mkdir(parents=True, exist_ok=True)
        (projects_dir / f"{SESSION_ID}.jsonl").write_text(CLI_JSONL_CONTENT)

        db_path = str(tmp_path / "index.sqlite")
        _run_full_scan(str(data_dir), db_path)

        session = _query_session(db_path, f"qoder:{SESSION_ID}")
        assert session is not None

        # When cwd exists, project_name is derived from cwd
        assert session["project_name"] != ".", (
            f"project_name should never be '.', got '{session['project_name']}'"
        )
        assert len(session["project_name"]) > 1, (
            f"project_name should be meaningful (len > 1), "
            f"got '{session['project_name']}'"
        )
