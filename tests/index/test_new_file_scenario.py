"""新文件场景的增量扫描测试。

验证 incremental_scan() 能正确发现并索引
初始全量扫描后新出现的会话 JSONL 文件。
"""

import pytest
import json
import os
import shutil
import sqlite3
import sys
import time
from pathlib import Path

# ─── 常量 ─────────────────────────────────────────────────────────────────────

FIXTURE_ROOT = Path(__file__).parent.parent / "fixtures" / "index_corpus" / "full_scan_claude"

# ─── 辅助函数 ─────────────────────────────────────────────────────────────────


def _setup_claude_env(data_dir: str):
    """设置 CLAUDE_DATA_DIR 并重新加载依赖模块。"""
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
    """恢复原始的 CLAUDE_DATA_DIR。"""
    if old is not None:
        os.environ["CLAUDE_DATA_DIR"] = old
    else:
        os.environ.pop("CLAUDE_DATA_DIR", None)


def _run_full_scan(data_dir: str, db_path: str) -> dict:
    """对 data_dir 运行 full_scan()，返回扫描统计。"""
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
    """对 data_dir 运行 incremental_scan()，返回扫描统计。"""
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
    """写入最小有效会话 JSONL 文件（含 usage 数据）。"""
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


# ─── 测试 ─────────────────────────────────────────────────────────────────────


class TestNewFileScenario:
    """N01: incremental_scan 发现并索引新会话文件。"""

    @pytest.mark.contract_case("DATA-INDEX-004")
    def test_new_session_file_discovered_and_indexed(self, tmp_path):
        """初始扫描后添加新会话 JSONL 文件应被发现并索引。

        步骤：
        1. 使用 full_scan 建立初始索引（2 个会话）。
        2. 向 history.jsonl 追加新条目并创建对应的会话 JSONL 文件。
        3. 更新会话文件 mtime 以确保可检测。
        4. 运行 incremental_scan。
        5. 验证新会话被发现并索引。
        6. 验证索引计数恰好增加 1。
        """
        data_dir = tmp_path / "claude_data"
        shutil.copytree(str(FIXTURE_ROOT), str(data_dir))

        db_path = str(tmp_path / "index.sqlite")

        # 步骤 1: 建立初始索引
        _run_full_scan(str(data_dir), db_path)

        conn = sqlite3.connect(db_path)
        count_before = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        conn.close()
        assert count_before == 2, f"Expected 2 initial sessions, got {count_before}"

        # 步骤 2: 向 history.jsonl 追加新会话条目
        history_path = data_dir / "history.jsonl"
        new_history_entry = {
            "sessionId": "sess-003",
            "project": "proj-gamma",
            "timestamp": int(time.time() * 1000),
            "display": "New session test",
        }
        with open(str(history_path), "a") as f:
            f.write(json.dumps(new_history_entry) + "\n")

        # 在新项目目录下创建新会话文件
        proj_dir = data_dir / "projects" / "proj-gamma"
        proj_dir.mkdir(parents=True, exist_ok=True)
        new_session_file = proj_dir / "sess-003.jsonl"
        _create_valid_session_file(new_session_file)

        # 步骤 3: 更新 mtime 以确保可检测
        time.sleep(0.05)
        new_stat = os.stat(str(new_session_file))
        new_mtime = new_stat.st_mtime + 1.0
        os.utime(str(new_session_file), (new_mtime, new_mtime))

        # 步骤 4: 运行增量扫描
        result = _run_incremental_scan(str(data_dir), db_path)

        # 步骤 5: 验证新会话被发现
        assert result["new_count"] >= 1, (
            f"Expected at least 1 new session from incremental scan, "
            f"got new_count={result['new_count']}"
        )

        # 步骤 6: 验证索引计数恰好增加 1
        conn = sqlite3.connect(db_path)
        count_after = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        conn.close()

        assert count_after == count_before + 1, (
            f"Expected index count to increase by 1: {count_before} -> {count_before + 1}, "
            f"got {count_after}"
        )

    @pytest.mark.contract_case("DATA-INDEX-004")
    def test_new_session_queryable_in_db(self, tmp_path):
        """新索引的会话应可在 sessions 表中查询。

        验证新会话在增量扫描后以正确的 session_key
        和项目信息出现在数据库中。
        """
        data_dir = tmp_path / "claude_data"
        shutil.copytree(str(FIXTURE_ROOT), str(data_dir))

        db_path = str(tmp_path / "index.sqlite")
        _run_full_scan(str(data_dir), db_path)

        # 向 history.jsonl 追加新会话条目
        history_path = data_dir / "history.jsonl"
        new_history_entry = {
            "sessionId": "sess-003",
            "project": "proj-gamma",
            "timestamp": int(time.time() * 1000),
            "display": "New session test",
        }
        with open(str(history_path), "a") as f:
            f.write(json.dumps(new_history_entry) + "\n")

        # 创建新会话文件
        proj_dir = data_dir / "projects" / "proj-gamma"
        proj_dir.mkdir(parents=True, exist_ok=True)
        new_session_file = proj_dir / "sess-003.jsonl"
        _create_valid_session_file(new_session_file)

        time.sleep(0.05)
        new_stat = os.stat(str(new_session_file))
        new_mtime = new_stat.st_mtime + 1.0
        os.utime(str(new_session_file), (new_mtime, new_mtime))

        _run_incremental_scan(str(data_dir), db_path)

        # 查询新会话
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

    @pytest.mark.contract_case("DATA-INDEX-004")
    def test_multiple_new_sessions_discovered(self, tmp_path):
        """添加多个新会话文件应都被增量扫描发现。

        验证增量扫描能处理批量添加并正确索引所有新会话。
        """
        data_dir = tmp_path / "claude_data"
        shutil.copytree(str(FIXTURE_ROOT), str(data_dir))

        db_path = str(tmp_path / "index.sqlite")
        _run_full_scan(str(data_dir), db_path)

        conn = sqlite3.connect(db_path)
        count_before = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        conn.close()

        # 向 history.jsonl 追加新会话条目并创建会话文件
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
