"""Qoder project path normalization contract tests.

Validates:
- cwd 存在时：project_key / project_name 使用 cwd 推导
- cwd 缺失时：path-text 不把 '.' 当作完整路径展示

Tests the P-21 scenario: path-text rendering should not show '.' as
a full project path when cwd is missing.
"""

from __future__ import annotations

import pytest
import json
import os
import sqlite3
import sys
from pathlib import Path, PurePosixPath

# ─── 常量 ──────────────────────────────────────────────────────────────

SESSION_ID = "path-test-session-001"
PROJECT_DIR_NAME = "my-cool-project"

# CLI 格式的最小化 Qoder JSONL 事件（含 cwd）
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

# 缓存格式的最小化 Qoder JSONL 事件（无 cwd 字段）
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

# 缺少 cwd 的 CLI 风格缓存格式事件（用户事件中无 cwd）
NO_CWD_CLI_JSONL_LINES = [
    json.dumps({
        "type": "user",
        "message": {"role": "user", "content": "Hello no cwd"},
        "timestamp": "2026-05-01T10:00:00.000Z",
        # 故意不包含 "cwd" 字段
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
    """设置 QODER_DATA_DIR 并重新加载依赖模块。"""
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
    """恢复原始的 QODER_DATA_DIR。"""
    if old is not None:
        os.environ["QODER_DATA_DIR"] = old
    else:
        os.environ.pop("QODER_DATA_DIR", None)


def _run_full_scan(data_dir: str, db_path: str) -> dict:
    """对 data_dir 运行 full_scan()，返回扫描统计。"""
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
    """按 session_key 查询会话并返回其行字典。"""
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
    """创建带 cwd 字段的 Qoder CLI 会话。"""
    data_dir = tmp_path / "qoder_cli_cwd"
    projects_dir = data_dir / "projects" / PROJECT_DIR_NAME
    projects_dir.mkdir(parents=True, exist_ok=True)
    (projects_dir / f"{SESSION_ID}.jsonl").write_text(CLI_JSONL_CONTENT)
    return data_dir, "/Users/zhehan/workspace/my-cool-project"


@pytest.fixture()
def no_cwd_cli_fixture(tmp_path: Path) -> tuple[Path, str]:
    """创建不带 cwd 字段的 Qoder CLI 会话。"""
    data_dir = tmp_path / "qoder_no_cwd_cli"
    projects_dir = data_dir / "projects" / PROJECT_DIR_NAME
    projects_dir.mkdir(parents=True, exist_ok=True)
    (projects_dir / f"{SESSION_ID}.jsonl").write_text(NO_CWD_CLI_JSONL_CONTENT)
    return data_dir, PROJECT_DIR_NAME


@pytest.fixture()
def cache_fixture(tmp_path: Path) -> tuple[Path, str]:
    """创建 Qoder cache 格式会话（无 cwd）。"""
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

    @pytest.mark.contract_case("DATA-INDEX-011")
    def test_cli_session_with_cwd_uses_cwd_as_project_key(self, cli_cwd_fixture, tmp_path):
        """当事件中存在 cwd 时，project_key 应从 cwd 推导，
        而非基于目录的 project_key。"""
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

    @pytest.mark.contract_case("DATA-INDEX-011")
    def test_no_cwd_session_uses_directory_name(self, no_cwd_cli_fixture, tmp_path):
        """当事件中不存在 cwd 时，project_key 应使用基于目录的
        project_key（来自 projects/ 的 URL 解码路径），且不应为 '.'。"""
        data_dir, expected_project_name = no_cwd_cli_fixture
        db_path = str(tmp_path / "index.sqlite")
        _run_full_scan(str(data_dir), db_path)

        session = _query_session(db_path, f"qoder:{SESSION_ID}")
        assert session is not None, "Session should be indexed"

        # 当事件中不存在时，cwd 应为空或缺失
        assert session["cwd"] == "", (
            f"cwd should be empty when not in events, got '{session['cwd']}'"
        )

        # project_key 应为目录名，而非 '.'
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

    @pytest.mark.contract_case("DATA-INDEX-011")
    def test_cache_session_no_cwd_project_key_not_dot(self, cache_fixture, tmp_path):
        """缓存格式的会话没有 cwd；project_key 绝不能为 '.'。"""
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

    @pytest.mark.contract_case("DATA-INDEX-011")
    def test_project_name_is_meaningful_folder_name(self, tmp_path):
        """project_name 应始终为最后一个有意义的路径段，
        而非 '.' 或空。"""
        data_dir = tmp_path / "qoder_project_name"
        # 在正常项目目录下创建会话
        projects_dir = data_dir / "projects" / "real-project-name"
        projects_dir.mkdir(parents=True, exist_ok=True)
        (projects_dir / f"{SESSION_ID}.jsonl").write_text(CLI_JSONL_CONTENT)

        db_path = str(tmp_path / "index.sqlite")
        _run_full_scan(str(data_dir), db_path)

        session = _query_session(db_path, f"qoder:{SESSION_ID}")
        assert session is not None

        # 当 cwd 存在时，project_name 从 cwd 推导
        assert session["project_name"] != ".", (
            f"project_name should never be '.', got '{session['project_name']}'"
        )
        assert len(session["project_name"]) > 1, (
            f"project_name should be meaningful (len > 1), "
            f"got '{session['project_name']}'"
        )
