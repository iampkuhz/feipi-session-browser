"""增量扫描 fixture 测试。

验证 incremental_scan() 能正确检测文件 mtime 变化，
仅重新索引修改过的会话，并跳过未变化的会话。
"""

import importlib
import os
import shutil
import sqlite3
import sys
import time
from pathlib import Path

import pytest

# ─── 常量 ──────────────────────────────────────────────────────────────

FIXTURE_ROOT = Path(__file__).parent.parent / "fixtures" / "index_corpus" / "full_scan_claude"

EXPECTED_SESSIONS = [
    {"session_id": "sess-001", "project_key": "proj-alpha"},
    {"session_id": "sess-002", "project_key": "proj-beta"},
]


# ─── 辅助函数 ───────────────────────────────────────────────────────────


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


# ─── 测试 ─────────────────────────────────────────────────────────────────────


class TestIncrementalScanMtime:
    """I01: incremental_scan 检测 mtime 变化并仅重新索引修改过的文件。"""

    @pytest.mark.contract_case("DATA-INDEX-002")
    def test_no_changes_all_skipped(self, tmp_path):
        """文件无变化时，incremental_scan() 应跳过所有会话。"""
        data_dir = tmp_path / "claude_data"
        shutil.copytree(str(FIXTURE_ROOT), str(data_dir))

        db_path = str(tmp_path / "index.sqlite")
        _run_full_scan(str(data_dir), db_path)

        # 无文件变化 —— 增量扫描应跳过所有内容
        result = _run_incremental_scan(str(data_dir), db_path)

        assert result["claude_count"] == 0, (
            f"Expected 0 re-indexed sessions (no changes), got {result['claude_count']}"
        )
        assert result["skipped"] == 2, f"Expected 2 skipped sessions, got {result['skipped']}"

    @pytest.mark.contract_case("DATA-INDEX-002")
    def test_one_file_changed_reindexed_only(self, tmp_path):
        """修改一个文件的 mtime 应仅导致该会话被重新索引。"""
        data_dir = tmp_path / "claude_data"
        shutil.copytree(str(FIXTURE_ROOT), str(data_dir))

        db_path = str(tmp_path / "index.sqlite")
        _run_full_scan(str(data_dir), db_path)

        # 推进时间以确保 mtime 差异可检测
        time.sleep(0.05)

        # 仅触碰 sess-001 的文件以使其 mtime 更新
        sess001_file = data_dir / "projects" / "proj-alpha" / "sess-001.jsonl"
        current_stat = os.stat(str(sess001_file))
        new_mtime = current_stat.st_mtime + 1.0
        os.utime(str(sess001_file), (new_mtime, new_mtime))

        result = _run_incremental_scan(str(data_dir), db_path)

        assert result["claude_count"] == 1, (
            f"Expected 1 re-indexed session, got {result['claude_count']}"
        )
        assert result["skipped"] == 1, f"Expected 1 skipped session, got {result['skipped']}"

        # 验证正确的会话被重新索引，通过检查 indexed_at 发生变化
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        row1 = conn.execute(
            "SELECT * FROM sessions WHERE session_key = 'claude_code:sess-001'"
        ).fetchone()
        row2 = conn.execute(
            "SELECT * FROM sessions WHERE session_key = 'claude_code:sess-002'"
        ).fetchone()

        # 两个会话都存在于数据库中
        assert row1 is not None, "sess-001 should still be in DB"
        assert row2 is not None, "sess-002 should still be in DB"

        # 验证 sess-001 被重新索引，检查其 indexed_at 已更新
        # （两个会话都由 full_scan 索引，然后只有 sess-001 被重新索引）
        indexed_at_1 = row1["indexed_at"]
        indexed_at_2 = row2["indexed_at"]
        assert indexed_at_1 > indexed_at_2, (
            f"sess-001 indexed_at ({indexed_at_1}) should be newer than sess-002 ({indexed_at_2})"
        )

        conn.close()

    @pytest.mark.contract_case("DATA-INDEX-002")
    def test_all_files_changed_all_reindexed(self, tmp_path):
        """触碰所有文件应导致所有会话被重新索引。"""
        data_dir = tmp_path / "claude_data"
        shutil.copytree(str(FIXTURE_ROOT), str(data_dir))

        db_path = str(tmp_path / "index.sqlite")
        _run_full_scan(str(data_dir), db_path)

        time.sleep(0.05)

        # 触碰两个会话文件
        for proj, sess in [("proj-alpha", "sess-001"), ("proj-beta", "sess-002")]:
            fpath = data_dir / "projects" / proj / f"{sess}.jsonl"
            current_stat = os.stat(str(fpath))
            new_mtime = current_stat.st_mtime + 1.0
            os.utime(str(fpath), (new_mtime, new_mtime))

        result = _run_incremental_scan(str(data_dir), db_path)

        assert result["claude_count"] == 2, (
            f"Expected 2 re-indexed sessions, got {result['claude_count']}"
        )
        assert result["skipped"] == 0, f"Expected 0 skipped sessions, got {result['skipped']}"

    @pytest.mark.contract_case("DATA-INDEX-002")
    def test_new_session_discovered(self, tmp_path):
        """初始扫描后添加新会话文件应被发现。"""
        data_dir = tmp_path / "claude_data"
        shutil.copytree(str(FIXTURE_ROOT), str(data_dir))

        db_path = str(tmp_path / "index.sqlite")
        _run_full_scan(str(data_dir), db_path)

        # 向 history.jsonl 添加新会话条目（第 3 个会话）
        # 并创建对应的会话文件
        history_path = data_dir / "history.jsonl"
        import json

        new_entry = {
            "sessionId": "sess-003",
            "project": "proj-gamma",
            "timestamp": int(time.time() * 1000),
            "display": "New session test",
        }
        with open(str(history_path), "a") as f:
            f.write(json.dumps(new_entry) + "\n")

        # 创建会话文件
        proj_dir = data_dir / "projects" / "proj-gamma"
        proj_dir.mkdir(parents=True, exist_ok=True)
        sess_file = proj_dir / "sess-003.jsonl"
        # 写入包含 usage 数据的最小有效会话
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
        with open(str(sess_file), "w") as f:
            f.write(json.dumps(msg_user) + "\n")
            f.write(json.dumps(msg_assistant) + "\n")

        result = _run_incremental_scan(str(data_dir), db_path)

        assert result["new_count"] >= 1, (
            f"Expected at least 1 new session, got new_count={result['new_count']}"
        )

        # 验证新会话在数据库中
        conn = sqlite3.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        conn.close()

        assert count == 3, f"Expected 3 sessions in DB after adding new one, got {count}"

    @pytest.mark.contract_case("DATA-INDEX-002")
    def test_scan_log_incr_mode(self, tmp_path):
        """incremental_scan 应记录 scan_log，mode='incremental'。"""
        data_dir = tmp_path / "claude_data"
        shutil.copytree(str(FIXTURE_ROOT), str(data_dir))

        db_path = str(tmp_path / "index.sqlite")
        _run_full_scan(str(data_dir), db_path)
        _run_incremental_scan(str(data_dir), db_path)

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        # 应至少有 2 条日志记录（full + incremental）
        logs = conn.execute("SELECT * FROM scan_log ORDER BY id DESC LIMIT 2").fetchall()
        assert len(logs) >= 2, f"Expected at least 2 scan_log entries, got {len(logs)}"

        # 最近的应为 incremental
        assert logs[0]["mode"] == "incremental", (
            f"Expected most recent scan_log mode='incremental', got '{logs[0]['mode']}'"
        )
        # 第二近的应为 full
        assert logs[1]["mode"] == "full", (
            f"Expected second scan_log mode='full', got '{logs[1]['mode']}'"
        )

        conn.close()

    @pytest.mark.contract_case("DATA-INDEX-002")
    def test_index_count_unchanged_after_incr_skip(self, tmp_path):
        """无变化时增量扫描不应改变总行数。"""
        data_dir = tmp_path / "claude_data"
        shutil.copytree(str(FIXTURE_ROOT), str(data_dir))

        db_path = str(tmp_path / "index.sqlite")
        _run_full_scan(str(data_dir), db_path)

        conn = sqlite3.connect(db_path)
        count_before = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        conn.close()

        _run_incremental_scan(str(data_dir), db_path)

        conn = sqlite3.connect(db_path)
        count_after = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        conn.close()

        assert count_before == count_after, (
            f"Session count changed: {count_before} -> {count_after} (expected unchanged)"
        )
