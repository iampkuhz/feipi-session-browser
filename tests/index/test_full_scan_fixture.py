"""Claude Code 索引器 full scan fixture 测试。

验证 full_scan() 能正确索引 fixture 数据、产生预期的会话计数，
并填充所有索引列。
"""

import pytest
import os
import shutil
import sqlite3
import sys
from pathlib import Path

# ─── 常量 ─────────────────────────────────────────────────────────────────────

FIXTURE_ROOT = Path(__file__).parent.parent / "fixtures" / "index_corpus" / "full_scan_claude"

EXPECTED_SESSIONS = [
    {"session_id": "sess-001", "project_key": "proj-alpha"},
    {"session_id": "sess-002", "project_key": "proj-beta"},
]


# ─── 辅助函数 ─────────────────────────────────────────────────────────────────

def _setup_claude_env(data_dir: str):
    """设置 CLAUDE_DATA_DIR 并重新加载依赖模块。"""
    old = os.environ.get("CLAUDE_DATA_DIR", None)
    os.environ["CLAUDE_DATA_DIR"] = data_dir

    # 重新加载 config + sources 以获取新的环境变量
    if "session_browser.config" in sys.modules:
        importlib_reload = sys.modules.get("importlib")
        if importlib_reload is None:
            import importlib
            sys.modules["importlib"] = importlib
            importlib_reload = importlib
        importlib_reload.reload(sys.modules["session_browser.config"])
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


# ─── 测试 ──────────────────────────────────────────────────────────────────

class TestFullScanClaudeBasic:
    """C01: full_scan_basic —— 从 fixture 数据构建基本索引。"""

    @pytest.mark.contract_case("DATA-INDEX-001")
    def test_full_scan_indexes_all_sessions(self, tmp_path):
        """full_scan() 应索引所有 fixture 会话。"""
        data_dir = tmp_path / "claude_data"
        shutil.copytree(str(FIXTURE_ROOT), str(data_dir))

        db_path = str(tmp_path / "index.sqlite")
        result = _run_full_scan(str(data_dir), db_path)

        assert result["claude_count"] == 2, f"Expected 2 Claude sessions, got {result['claude_count']}"
        assert result["codex_count"] == 0
        assert result["qoder_count"] == 0
        assert result["total"] == 2

    @pytest.mark.contract_case("DATA-INDEX-001")
    def test_session_keys_present(self, tmp_path):
        """被索引的会话应具有正确的 session_key 格式。"""
        data_dir = tmp_path / "claude_data"
        shutil.copytree(str(FIXTURE_ROOT), str(data_dir))

        db_path = str(tmp_path / "index.sqlite")
        _run_full_scan(str(data_dir), db_path)

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        for sess in EXPECTED_SESSIONS:
            expected_key = f"claude_code:{sess['session_id']}"
            row = conn.execute(
                "SELECT session_key FROM sessions WHERE session_key = ?",
                (expected_key,),
            ).fetchone()
            assert row is not None, f"Session key {expected_key} not found in index"

        conn.close()

    @pytest.mark.contract_case("DATA-INDEX-001")
    def test_session_count_matches(self, tmp_path):
        """sessions 表的总行数应与 fixture 会话数匹配。"""
        data_dir = tmp_path / "claude_data"
        shutil.copytree(str(FIXTURE_ROOT), str(data_dir))

        db_path = str(tmp_path / "index.sqlite")
        _run_full_scan(str(data_dir), db_path)

        conn = sqlite3.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        conn.close()

        assert count == 2, f"Expected 2 rows in sessions table, got {count}"

    @pytest.mark.contract_case("DATA-INDEX-001")
    def test_all_columns_populated(self, tmp_path):
        """每个被索引的会话在所有 26 列中都应有非空值。"""
        data_dir = tmp_path / "claude_data"
        shutil.copytree(str(FIXTURE_ROOT), str(data_dir))

        db_path = str(tmp_path / "index.sqlite")
        _run_full_scan(str(data_dir), db_path)

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        for sess in EXPECTED_SESSIONS:
            key = f"claude_code:{sess['session_id']}"
            row = conn.execute(
                "SELECT * FROM sessions WHERE session_key = ?",
                (key,),
            ).fetchone()
            assert row is not None, f"Session {key} not found"

            # 核心标识字段必须非空
            assert row["agent"] == "claude_code", f"agent mismatch for {key}"
            assert row["session_id"] == sess["session_id"], f"session_id mismatch for {key}"
            assert row["project_key"] == sess["project_key"], f"project_key mismatch for {key}"

            # 标题应非空（从第一条用户消息派生）
            assert row["title"] != "", f"title is empty for {key}"

            # 时间戳应非空 ISO8601 字符串
            assert row["started_at"] != "", f"started_at is empty for {key}"
            assert row["ended_at"] != "", f"ended_at is empty for {key}"

            # Token 计数应 > 0（我们的 fixture 包含 usage 数据）
            assert row["input_tokens"] > 0, f"input_tokens is 0 for {key}"
            assert row["output_tokens"] > 0, f"output_tokens is 0 for {key}"

            # 消息计数应 > 0
            assert row["user_message_count"] > 0, f"user_message_count is 0 for {key}"
            assert row["assistant_message_count"] > 0, f"assistant_message_count is 0 for {key}"

            # indexed_at 应已设置
            assert row["indexed_at"] > 0, f"indexed_at is 0 for {key}"

        conn.close()

    @pytest.mark.contract_case("DATA-INDEX-001")
    def test_scan_log_recorded(self, tmp_path):
        """full_scan() 应写入 scan_log 条目并包含正确的计数。"""
        data_dir = tmp_path / "claude_data"
        shutil.copytree(str(FIXTURE_ROOT), str(data_dir))

        db_path = str(tmp_path / "index.sqlite")
        _run_full_scan(str(data_dir), db_path)

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        log = conn.execute(
            "SELECT * FROM scan_log ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert log is not None, "No scan_log entry found"
        assert log["mode"] == "full"
        assert log["status"] == "done"
        assert log["claude_count"] == 2
        assert log["finished_at"] is not None

        conn.close()

    @pytest.mark.contract_case("DATA-INDEX-001")
    def test_fixture_data_isolated(self, tmp_path):
        """Full scan 在使用 fixture 时不应触碰真实的 CLAUDE_DATA_DIR。"""
        data_dir = tmp_path / "claude_data"
        shutil.copytree(str(FIXTURE_ROOT), str(data_dir))

        db_path = str(tmp_path / "index.sqlite")
        result = _run_full_scan(str(data_dir), db_path)

        # 应仅看到 2 个 fixture 会话，不包含真实 ~/.claude/ 的数据
        conn = sqlite3.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        conn.close()

        assert count == 2, "Index should only contain fixture sessions, not real data"
