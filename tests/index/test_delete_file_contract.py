"""源文件删除场景契约测试。

验证会话 JSONL 源文件被删除后索引的行为。记录两个已知限制：

1. incremental_scan 检测到文件删除后跳过重新索引，但不清理数据库中的陈旧条目。
2. full_scan 通过 _session_from_history 回退到 history.jsonl 元数据，
   即使源文件已删除也会重新索引该会话（设计意图）。

两者都不会在源文件删除后从索引中移除会话条目。

契约缺口：
- 没有机制从索引中清理已删除源文件的会话。
- 只有通过手动删除数据库记录或从 history.jsonl 中移除条目才能清理。
"""

import json
import os
import shutil
import sqlite3
import sys
import time
from pathlib import Path

import pytest

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


# ─── 测试 ─────────────────────────────────────────────────────────────────────


class TestDeleteFileContract:
    """D01: 源文件删除 — 两种扫描方式都不会从索引中移除已删除的会话。

    契约：
    - incremental_scan 检测到文件删除后跳过重新索引，但保留数据库中的陈旧条目。
    - full_scan 通过 _session_from_history 回退到 history.jsonl，
      仍然索引已删除的会话（设计意图：只要 history.jsonl 有记录就保留索引）。
    """

    @pytest.mark.contract_case("DATA-INDEX-007")
    def test_incremental_scan_does_not_clean_deleted_files_known_limitation(self, tmp_path):
        """D01-A: incremental_scan 不清理已删除文件的陈旧条目。

        已知限制：incremental_scan 跳过已删除文件的重新索引，
        但不删除数据库中的对应行。
        """
        data_dir = tmp_path / "claude_data"
        shutil.copytree(str(FIXTURE_ROOT), str(data_dir))

        db_path = str(tmp_path / "index.sqlite")

        # 步骤 1: 建立初始索引
        _run_full_scan(str(data_dir), db_path)

        conn = sqlite3.connect(db_path)
        count_before = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        assert count_before == 2, f"Expected 2 sessions after full_scan, got {count_before}"

        # 步骤 2: 删除一个会话文件（proj-alpha 下的 sess-001）
        sess001_file = data_dir / "projects" / "proj-alpha" / "sess-001.jsonl"
        assert sess001_file.exists(), "Fixture file should exist before deletion"
        sess001_file.unlink()
        assert not sess001_file.exists(), "Fixture file should be deleted"

        # 步骤 3: 运行增量扫描
        result = _run_incremental_scan(str(data_dir), db_path)

        # 步骤 4: 验证当前行为 —— 陈旧条目仍然存在
        count_after = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]

        # 已知限制：incremental_scan 不会清理已删除的会话
        # sess-001 的陈旧行仍保留在数据库中。
        assert count_after == 2, (
            f"KNOWN LIMITATION: incremental_scan does not clean deleted files. "
            f"Expected 2 (stale entry remains), got {count_after}"
        )

        # 验证 sess-001 仍在数据库中（陈旧）
        row = conn.execute(
            "SELECT session_key, file_path FROM sessions WHERE session_key = 'claude_code:sess-001'"
        ).fetchone()
        assert row is not None, (
            "KNOWN LIMITATION: sess-001 should still be in DB after incremental_scan "
            "(stale entry NOT cleaned up)"
        )

        # 验证扫描结果包含 skipped 计数（文件被检测为缺失）
        assert result["skipped"] >= 1, (
            f"Expected at least 1 skipped session (deleted file), got {result['skipped']}"
        )

        conn.close()

    @pytest.mark.contract_case("DATA-INDEX-007")
    def test_full_scan_also_keeps_deleted_sessions_via_history_fallback(self, tmp_path):
        """D01-B: full_scan 也保留已删除的会话（通过 history.jsonl 回退）。

        full_scan 调用 parse_session_detail，当 JSONL 文件不存在时，
        回退到 _session_from_history，从 history.jsonl 元数据构建会话摘要。
        因此即使源文件已删除，会话仍然出现在索引中。

        这是设计意图：只要 history.jsonl 中有记录，会话就保留在索引中。
        """
        data_dir = tmp_path / "claude_data"
        shutil.copytree(str(FIXTURE_ROOT), str(data_dir))

        db_path = str(tmp_path / "index.sqlite")

        # 步骤 1: 建立初始索引
        _run_full_scan(str(data_dir), db_path)

        conn = sqlite3.connect(db_path)
        count_before = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        assert count_before == 2

        # 步骤 2: 删除 sess-001
        sess001_file = data_dir / "projects" / "proj-alpha" / "sess-001.jsonl"
        sess001_file.unlink()

        # 步骤 3: 运行全量扫描（重建索引）
        result = _run_full_scan(str(data_dir), db_path)

        # 已知限制：full_scan 仍通过 _session_from_history 索引已删除的会话
        # 会话从 history.jsonl 元数据重新索引（无事件数据）
        assert result["claude_count"] == 2, (
            f"KNOWN LIMITATION: full_scan still indexes deleted sessions via history fallback. "
            f"Expected 2 (re-indexed from history.jsonl), got {result['claude_count']}"
        )

        count_after = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        assert count_after == 2, (
            f"Expected 2 rows in DB after full_scan (deleted session re-indexed from history), "
            f"got {count_after}"
        )

        # 验证 sess-001 仍在数据库中（从 history 重新索引，而非从文件）
        row001 = conn.execute(
            "SELECT session_key, file_path FROM sessions WHERE session_key = 'claude_code:sess-001'"
        ).fetchone()
        assert row001 is not None, (
            "KNOWN LIMITATION: sess-001 should still be in DB after full_scan "
            "(re-indexed from history.jsonl)"
        )

        # 从 history 重新索引的会话将有空的 file_path
        # （没有实际文件存在）
        row002 = conn.execute(
            "SELECT session_key FROM sessions WHERE session_key = 'claude_code:sess-002'"
        ).fetchone()
        assert row002 is not None, "sess-002 should still be in DB after full_scan"

        conn.close()

    @pytest.mark.contract_case("DATA-INDEX-007")
    def test_incremental_scan_skipped_count_includes_deleted(self, tmp_path):
        """D01-C: incremental_scan 在 skipped 计数中报告已删除文件。

        当源文件被删除时，incremental_scan 应将其计为
        skipped（不重新索引），但目前不会删除数据库中的行。
        """
        data_dir = tmp_path / "claude_data"
        shutil.copytree(str(FIXTURE_ROOT), str(data_dir))

        db_path = str(tmp_path / "index.sqlite")
        _run_full_scan(str(data_dir), db_path)

        # 删除一个会话文件
        sess001_file = data_dir / "projects" / "proj-alpha" / "sess-001.jsonl"
        sess001_file.unlink()

        result = _run_incremental_scan(str(data_dir), db_path)

        # 已删除的文件应计入 skipped
        assert result["skipped"] >= 1, (
            f"Expected deleted session to be counted as skipped, got skipped={result['skipped']}"
        )

        # claude_count 应为 0（未发生重新索引）
        assert result["claude_count"] == 0, (
            f"Expected 0 re-indexed sessions (file deleted), got {result['claude_count']}"
        )

    @pytest.mark.contract_case("DATA-INDEX-007")
    def test_incremental_scan_all_files_deleted(self, tmp_path):
        """D01-D: 所有会话文件被删除 — incremental_scan 全部跳过。

        当所有源文件都被删除时，incremental_scan 应跳过
        所有会话。数据库保留陈旧条目（已知限制）。
        """
        data_dir = tmp_path / "claude_data"
        shutil.copytree(str(FIXTURE_ROOT), str(data_dir))

        db_path = str(tmp_path / "index.sqlite")
        _run_full_scan(str(data_dir), db_path)

        # 删除所有会话文件
        for proj in ["proj-alpha", "proj-beta"]:
            for sess in ["sess-001", "sess-002"]:
                fpath = data_dir / "projects" / proj / f"{sess}.jsonl"
                if fpath.exists():
                    fpath.unlink()

        result = _run_incremental_scan(str(data_dir), db_path)

        # 所有会话都应被跳过
        assert result["skipped"] >= 2, (
            f"Expected all 2 sessions skipped (all files deleted), got skipped={result['skipped']}"
        )
        assert result["claude_count"] == 0, f"Expected 0 re-indexed, got {result['claude_count']}"

        # 已知限制：陈旧条目仍然保留
        conn = sqlite3.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        assert count == 2, (
            f"KNOWN LIMITATION: DB still has {count} stale entries after all files deleted"
        )
        conn.close()

    @pytest.mark.contract_case("DATA-INDEX-007")
    def test_full_scan_after_incremental_also_keeps_deleted(self, tmp_path):
        """D01-E: full_scan 也不清理 incremental_scan 留下的陈旧条目。

        已知限制：full_scan 通过 history.jsonl 回退重新索引已删除的会话，
        因此不会清理 incremental_scan 留下的陈旧条目。两种扫描方式
        都无法从索引中移除已删除源文件的会话。
        """
        data_dir = tmp_path / "claude_data"
        shutil.copytree(str(FIXTURE_ROOT), str(data_dir))

        db_path = str(tmp_path / "index.sqlite")

        # 构建初始索引
        _run_full_scan(str(data_dir), db_path)

        # 删除 sess-001
        sess001_file = data_dir / "projects" / "proj-alpha" / "sess-001.jsonl"
        sess001_file.unlink()

        # incremental_scan 留下陈旧条目
        incr_result = _run_incremental_scan(str(data_dir), db_path)
        conn = sqlite3.connect(db_path)
        count_after_incr = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        assert count_after_incr == 2, (
            f"Expected 2 after incremental_scan (stale), got {count_after_incr}"
        )
        conn.close()

        # 已知限制：full_scan 也通过 history 回退保留已删除的会话
        full_result = _run_full_scan(str(data_dir), db_path)
        assert full_result["claude_count"] == 2, (
            f"KNOWN LIMITATION: full_scan also keeps deleted sessions via history fallback. "
            f"Expected 2, got {full_result['claude_count']}"
        )

        conn = sqlite3.connect(db_path)
        count_after_full = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        assert count_after_full == 2, (
            f"KNOWN LIMITATION: DB still has {count_after_full} entries after full_scan "
            f"(deleted session re-indexed from history.jsonl)"
        )
        conn.close()
