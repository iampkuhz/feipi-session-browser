"""Full scan 与 Incremental scan 一致性测试。

验证在针对性文件修改后，incremental_scan 产生的索引状态与 full_scan 一致。
这确保增量路径不会偏离规范的完整重索引。
"""

import pytest
import json
import os
import shutil
import sqlite3
import sys
import time
from pathlib import Path

# ─── 常量 ───────────────────────────────────────────────────────────────

FIXTURE_ROOT = Path(__file__).parent.parent / "fixtures" / "index_corpus" / "full_scan_claude"


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


def _snapshot_db(db_path: str) -> dict:
    """快照 sessions 表，返回以 session_key 为键的字典。"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM sessions").fetchall()
    snapshot = {}
    for row in rows:
        key = row["session_key"]
        snapshot[key] = dict(row)
    conn.close()
    return snapshot


def _touch_file(file_path: Path, delta_seconds: float = 1.0):
    """将文件的 mtime 推进 delta_seconds。"""
    current_stat = os.stat(str(file_path))
    new_mtime = current_stat.st_mtime + delta_seconds
    os.utime(str(file_path), (new_mtime, new_mtime))


# ─── 测试 ──────────────────────────────────────────────────────────────────

class TestFullVsIncrementalConsistency:
    """full scan 与 incremental scan 路径之间的一致性断言。

    流程：full_scan（基线） -> 修改 mtime -> incremental_scan
          -> full_scan（重新基线） -> 断言相等。
    """

    @pytest.mark.contract_case("DATA-INDEX-003")
    def test_single_file_modified_consistency(self, tmp_path):
        """修改一个文件后，incremental 与 full 重新扫描必须一致。

        步骤：
        1. full_scan 建立基线（2 个会话）。
        2. 推进 sess-001 的 mtime。
        3. incremental_scan 仅重新索引 sess-001。
        4. full_scan 重建所有内容。
        5. 断言：incremental 后的数据库状态与 full 重新扫描后的状态匹配。
        """
        data_dir = tmp_path / "claude_data"
        shutil.copytree(str(FIXTURE_ROOT), str(data_dir))

        # 步骤 1: 基线全量扫描
        db_a = str(tmp_path / "index_a.sqlite")
        _run_full_scan(str(data_dir), db_a)

        snapshot_full_1 = _snapshot_db(db_a)
        assert len(snapshot_full_1) == 2, "Baseline should have 2 sessions"

        # 步骤 2: 修改文件时间戳
        time.sleep(0.05)
        sess001_file = data_dir / "projects" / "proj-alpha" / "sess-001.jsonl"
        _touch_file(sess001_file)

        # 步骤 3: 增量扫描
        _run_incremental_scan(str(data_dir), db_a)
        snapshot_incr = _snapshot_db(db_a)
        assert len(snapshot_incr) == 2, "Incremental should still have 2 sessions"

        # 步骤 4: 全量重新扫描 on a fresh DB
        db_b = str(tmp_path / "index_b.sqlite")
        _run_full_scan(str(data_dir), db_b)
        snapshot_full_2 = _snapshot_db(db_b)
        assert len(snapshot_full_2) == 2, "Full re-scan should have 2 sessions"

        # 步骤 5: 一致性断言
        assert set(snapshot_incr.keys()) == set(snapshot_full_2.keys()), (
            f"Session keys mismatch: incr={sorted(snapshot_incr.keys())} "
            f"vs full={sorted(snapshot_full_2.keys())}"
        )

        for key in snapshot_full_2:
            incr_row = snapshot_incr[key]
            full_row = snapshot_full_2[key]
        # 对比应一致的关键指标
            assert incr_row["input_tokens"] == full_row["input_tokens"], (
                f"input_tokens mismatch for {key}: incr={incr_row['input_tokens']} "
                f"vs full={full_row['input_tokens']}"
            )
            assert incr_row["output_tokens"] == full_row["output_tokens"], (
                f"output_tokens mismatch for {key}"
            )
            assert incr_row["user_message_count"] == full_row["user_message_count"], (
                f"user_message_count mismatch for {key}"
            )
            assert incr_row["assistant_message_count"] == full_row["assistant_message_count"], (
                f"assistant_message_count mismatch for {key}"
            )
            assert incr_row["title"] == full_row["title"], (
                f"title mismatch for {key}: incr='{incr_row['title']}' "
                f"vs full='{full_row['title']}'"
            )
            assert incr_row["agent"] == full_row["agent"], (
                f"agent mismatch for {key}"
            )
            assert incr_row["project_key"] == full_row["project_key"], (
                f"project_key mismatch for {key}"
            )

    @pytest.mark.contract_case("DATA-INDEX-003")
    def test_all_files_modified_consistency(self, tmp_path):
        """全量文件修改后，增量扫描必须与全量重新扫描一致。

        与 test_single_file_modified_consistency 流程相同，但修改
        所有会话文件，以验证完整的增量重新索引一致性。
        """
        data_dir = tmp_path / "claude_data"
        shutil.copytree(str(FIXTURE_ROOT), str(data_dir))

        # 步骤 1: 基线全量扫描
        db_a = str(tmp_path / "index_a.sqlite")
        _run_full_scan(str(data_dir), db_a)

        # 步骤 2: 修改所有文件时间戳
        time.sleep(0.05)
        for proj, sess in [("proj-alpha", "sess-001"), ("proj-beta", "sess-002")]:
            fpath = data_dir / "projects" / proj / f"{sess}.jsonl"
            _touch_file(fpath)

        # 步骤 3: 增量扫描（应重新索引两个）
        result_incr = _run_incremental_scan(str(data_dir), db_a)
        assert result_incr["claude_count"] == 2, (
            f"Expected 2 re-indexed, got {result_incr['claude_count']}"
        )

        snapshot_incr = _snapshot_db(db_a)

        # 步骤 4: 全量重新扫描
        db_b = str(tmp_path / "index_b.sqlite")
        _run_full_scan(str(data_dir), db_b)
        snapshot_full = _snapshot_db(db_b)

        # 步骤 5: 一致性断言
        assert len(snapshot_incr) == len(snapshot_full) == 2

        for key in snapshot_full:
            incr_row = snapshot_incr[key]
            full_row = snapshot_full[key]
            assert incr_row["input_tokens"] == full_row["input_tokens"], (
                f"input_tokens mismatch for {key}"
            )
            assert incr_row["output_tokens"] == full_row["output_tokens"], (
                f"output_tokens mismatch for {key}"
            )
            assert incr_row["title"] == full_row["title"], (
                f"title mismatch for {key}"
            )
            assert incr_row["started_at"] == full_row["started_at"], (
                f"started_at mismatch for {key}"
            )
            assert incr_row["ended_at"] == full_row["ended_at"], (
                f"ended_at mismatch for {key}"
            )

    @pytest.mark.contract_case("DATA-INDEX-003")
    def test_new_session_discovered_consistency(self, tmp_path):
        """发现新会话后，增量扫描与全量扫描必须产生相同结果。

        步骤：
        1. 全量扫描基线（2 个会话）。
        2. 添加第 3 个会话文件。
        3. 增量扫描发现新会话。
        4. 新数据库上的全量扫描。
        5. 断言：两者都有 3 个会话且指标一致。
        """
        data_dir = tmp_path / "claude_data"
        shutil.copytree(str(FIXTURE_ROOT), str(data_dir))

        # 步骤 1: 基线全量扫描
        db_a = str(tmp_path / "index_a.sqlite")
        _run_full_scan(str(data_dir), db_a)
        snapshot_full_1 = _snapshot_db(db_a)
        assert len(snapshot_full_1) == 2

        # 步骤 2: 添加一个新会话
        now_iso = "2025-01-15T10:00:00+00:00"
        history_path = data_dir / "history.jsonl"
        new_entry = {
            "sessionId": "sess-003",
            "project": "proj-gamma",
            "timestamp": int(time.time() * 1000),
            "display": "New session test"
        }
        with open(str(history_path), "a") as f:
            f.write(json.dumps(new_entry) + "\n")

        proj_dir = data_dir / "projects" / "proj-gamma"
        proj_dir.mkdir(parents=True, exist_ok=True)
        sess_file = proj_dir / "sess-003.jsonl"

        msg_user = {
            "type": "user",
            "message": {"role": "user", "content": "Hello new session"},
            "timestamp": now_iso,
            "cwd": "/tmp/test",
            "entrypoint": "cli",
            "gitBranch": "main"
        }
        msg_assistant = {
            "type": "assistant",
            "message": {
                "type": "message",
                "model": "claude-sonnet-4-20250514",
                "role": "assistant",
                "content": [{"type": "text", "text": "Hi!"}],
                "usage": {"input_tokens": 300, "output_tokens": 100}
            },
            "timestamp": now_iso
        }
        with open(str(sess_file), "w") as f:
            f.write(json.dumps(msg_user) + "\n")
            f.write(json.dumps(msg_assistant) + "\n")

        # 步骤 3: 增量扫描
        result_incr = _run_incremental_scan(str(data_dir), db_a)
        assert result_incr["new_count"] >= 1, (
            f"Expected new session discovery, got new_count={result_incr['new_count']}"
        )
        snapshot_incr = _snapshot_db(db_a)

        # 步骤 4: 全量重新扫描
        db_b = str(tmp_path / "index_b.sqlite")
        _run_full_scan(str(data_dir), db_b)
        snapshot_full = _snapshot_db(db_b)

        # 步骤 5: 一致性
        assert len(snapshot_incr) == 3, (
            f"Expected 3 sessions after incremental, got {len(snapshot_incr)}"
        )
        assert len(snapshot_full) == 3, (
            f"Expected 3 sessions after full, got {len(snapshot_full)}"
        )
        assert set(snapshot_incr.keys()) == set(snapshot_full.keys()), (
            "Session key sets differ between incremental and full"
        )

        # 三个会话的关键指标都必须一致
        for key in snapshot_full:
            incr_row = snapshot_incr[key]
            full_row = snapshot_full[key]
            assert incr_row["input_tokens"] == full_row["input_tokens"], (
                f"input_tokens mismatch for {key}"
            )
            assert incr_row["output_tokens"] == full_row["output_tokens"], (
                f"output_tokens mismatch for {key}"
            )
            assert incr_row["user_message_count"] == full_row["user_message_count"], (
                f"user_message_count mismatch for {key}"
            )
            assert incr_row["assistant_message_count"] == full_row["assistant_message_count"], (
                f"assistant_message_count mismatch for {key}"
            )

    @pytest.mark.contract_case("DATA-INDEX-003")
    def test_no_changes_consistency(self, tmp_path):
        """无文件变化时，增量扫描不应改变数据库状态。

        步骤：
        1. 全量扫描基线。
        2. 增量扫描（无变化）-> 0 个重新索引。
        3. 新数据库上的全量扫描。
        4. 断言：两个数据库完全相同。
        """
        data_dir = tmp_path / "claude_data"
        shutil.copytree(str(FIXTURE_ROOT), str(data_dir))

        # 步骤 1: 基线全量扫描
        db_a = str(tmp_path / "index_a.sqlite")
        result_full_1 = _run_full_scan(str(data_dir), db_a)
        assert result_full_1["claude_count"] == 2

        # 步骤 2: 无变化时执行增量扫描
        result_incr = _run_incremental_scan(str(data_dir), db_a)
        assert result_incr["claude_count"] == 0, (
            f"Expected 0 re-indexed (no changes), got {result_incr['claude_count']}"
        )
        assert result_incr["skipped"] == 2, (
            f"Expected 2 skipped, got {result_incr['skipped']}"
        )

        snapshot_incr = _snapshot_db(db_a)

        # 步骤 3: 全量重新扫描
        db_b = str(tmp_path / "index_b.sqlite")
        result_full_2 = _run_full_scan(str(data_dir), db_b)

        snapshot_full = _snapshot_db(db_b)

        # 步骤 4: 一致性
        assert len(snapshot_incr) == len(snapshot_full) == 2
        assert set(snapshot_incr.keys()) == set(snapshot_full.keys())

        for key in snapshot_full:
            incr_row = snapshot_incr[key]
            full_row = snapshot_full[key]
            assert incr_row["input_tokens"] == full_row["input_tokens"]
            assert incr_row["output_tokens"] == full_row["output_tokens"]
            assert incr_row["title"] == full_row["title"]

    @pytest.mark.contract_case("DATA-INDEX-003")
    def test_scan_log_mode_full_then_incremental(self, tmp_path):
        """验证 scan_log 正确记录全量和增量扫描模式。

        流程：全量扫描 -> 增量扫描 -> 断言 scan_log 显示
        [full, incremental]。注意：第二次全量扫描会重置 scan_log，
        因为 full_scan 调用 init_schema() 会删除并重建该表。
        因此只测试全量 -> 增量的序列。
        """
        data_dir = tmp_path / "claude_data"
        shutil.copytree(str(FIXTURE_ROOT), str(data_dir))

        db_path = str(tmp_path / "index.sqlite")

        _run_full_scan(str(data_dir), db_path)

        time.sleep(0.05)
        sess001_file = data_dir / "projects" / "proj-alpha" / "sess-001.jsonl"
        _touch_file(sess001_file)

        _run_incremental_scan(str(data_dir), db_path)

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        logs = conn.execute(
            "SELECT mode FROM scan_log ORDER BY id ASC"
        ).fetchall()
        conn.close()

        modes = [row["mode"] for row in logs]
        assert len(modes) == 2, f"Expected 2 scan_log entries, got {len(modes)}"
        assert modes == ["full", "incremental"], (
            f"Expected mode sequence [full, incremental], got {modes}"
        )
