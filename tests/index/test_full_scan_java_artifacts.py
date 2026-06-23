"""Full scan Java artifact producer tests.

验证 full_scan 使用 Java bridge 生产 normalized artifact：
- Full scan canonical JSON/meta 仅由 Java 写
- 单次 full scan 一个 JVM
- Java failure 无 Python writer fallback
- SQLite 结果与冻结 contract 一致
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ─── 常量 ─────────────────────────────────────────────────────────────────────

FIXTURE_ROOT = Path(__file__).parent.parent / "fixtures" / "index_corpus" / "full_scan_claude"


# ─── 辅助函数 ─────────────────────────────────────────────────────────────────


def _setup_claude_env(data_dir: str):
    """设置 CLAUDE_DATA_DIR 并重新加载依赖模块。"""
    old = os.environ.get("CLAUDE_DATA_DIR", None)
    os.environ["CLAUDE_DATA_DIR"] = data_dir

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


# ─── 测试：Java batch 集成 ──────────────────────────────────────────────────


class TestFullScanJavaBatch:
    """验证 full_scan 使用 Java bridge 生产 artifact。"""

    def test_full_scan_collects_batch_requests(self, tmp_path):
        """full_scan 应为每个 session 收集 batch 请求。"""
        data_dir = tmp_path / "claude_data"
        shutil.copytree(str(FIXTURE_ROOT), str(data_dir))

        with patch("session_browser.index.scanners.execute_java_normalized_batch") as mock_batch:
            # 返回空结果，模拟 Java 不可用
            from session_browser.normalized.java_bridge import BatchSummary
            from session_browser.normalized.normalized_batch import NormalizedBatchOutcome

            mock_batch.return_value = NormalizedBatchOutcome(
                results=[],
                summary=BatchSummary(),
                success_count=0,
                unchanged_count=0,
                failed_count=0,
            )

            db_path = str(tmp_path / "index.sqlite")
            _run_full_scan(str(data_dir), db_path)

            # 验证 batch 被调用
            assert mock_batch.called
            call_args = mock_batch.call_args
            requests = call_args[0][0]  # 第一个位置参数
            assert len(requests) == 2, "应为 2 个 session 收集请求"

            # 验证请求格式
            for req in requests:
                assert req.source_id == "CLAUDE_CODE"
                assert req.root_path.endswith(".jsonl")
                assert req.session_key.startswith("claude_code:")

    def test_full_scan_single_jvm(self, tmp_path):
        """单次 full scan 只启动一个 JVM。"""
        data_dir = tmp_path / "claude_data"
        shutil.copytree(str(FIXTURE_ROOT), str(data_dir))

        with patch("session_browser.index.scanners.execute_java_normalized_batch") as mock_batch:
            from session_browser.normalized.java_bridge import BatchSummary
            from session_browser.normalized.normalized_batch import NormalizedBatchOutcome

            mock_batch.return_value = NormalizedBatchOutcome(
                results=[],
                summary=BatchSummary(),
                success_count=0,
                unchanged_count=0,
                failed_count=0,
            )

            db_path = str(tmp_path / "index.sqlite")
            _run_full_scan(str(data_dir), db_path)

            # 验证只调用一次
            assert mock_batch.call_count == 1

    def test_full_scan_no_python_fallback_on_java_failure(self, tmp_path):
        """Java failure 时不 fallback 到 Python writer，scan 正常完成。"""
        data_dir = tmp_path / "claude_data"
        shutil.copytree(str(FIXTURE_ROOT), str(data_dir))

        with patch("session_browser.index.scanners.execute_java_normalized_batch") as mock_batch:
            # 模拟 Java 异常
            mock_batch.side_effect = RuntimeError("Java not available")

            db_path = str(tmp_path / "index.sqlite")
            # 不应抛出异常
            result = _run_full_scan(str(data_dir), db_path)

            # 验证 scan 仍然完成（虽然 artifact 未生成）
            assert result["claude_count"] == 2

    def test_full_scan_associates_successful_artifacts(self, tmp_path):
        """Java 成功时，full_scan 关联 artifact 到 session_artifacts。"""
        data_dir = tmp_path / "claude_data"
        shutil.copytree(str(FIXTURE_ROOT), str(data_dir))

        # 创建临时 artifact 文件
        artifact_dir = tmp_path / "artifacts" / "normalized-sessions" / "claude_code"
        artifact_dir.mkdir(parents=True, exist_ok=True)

        artifact1 = artifact_dir / "sess-001.json"
        artifact1_data = {
            "schema_version": "session-detail.normalized.v3",
            "agent": "claude_code",
            "session": {"session_id": "sess-001", "session_key": "claude_code:sess-001"},
        }
        artifact1.write_text(json.dumps(artifact1_data), encoding="utf-8")

        artifact2 = artifact_dir / "sess-002.json"
        artifact2_data = {
            "schema_version": "session-detail.normalized.v3",
            "agent": "claude_code",
            "session": {"session_id": "sess-002", "session_key": "claude_code:sess-002"},
        }
        artifact2.write_text(json.dumps(artifact2_data), encoding="utf-8")

        with patch("session_browser.index.scanners.execute_java_normalized_batch") as mock_batch:
            from session_browser.normalized.java_bridge import BatchResult, BatchSummary, ResultStatus
            from session_browser.normalized.normalized_batch import NormalizedBatchOutcome

            # 模拟 Java 返回成功结果
            mock_batch.return_value = NormalizedBatchOutcome(
                results=[
                    BatchResult(
                        request_id="claude_code:sess-001",
                        status=ResultStatus.WRITTEN,
                        session_key="claude_code:sess-001",
                        artifact_path=str(artifact1),
                        content_hash=hashlib.sha256(json.dumps(artifact1_data).encode()).hexdigest(),
                    ),
                    BatchResult(
                        request_id="claude_code:sess-002",
                        status=ResultStatus.WRITTEN,
                        session_key="claude_code:sess-002",
                        artifact_path=str(artifact2),
                        content_hash=hashlib.sha256(json.dumps(artifact2_data).encode()).hexdigest(),
                    ),
                ],
                summary=BatchSummary(total=2, written=2, unchanged=0, failed=0),
                success_count=2,
                unchanged_count=0,
                failed_count=0,
            )

            db_path = str(tmp_path / "index.sqlite")
            _run_full_scan(str(data_dir), db_path)

            # 验证 session_artifacts 表有记录
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT * FROM session_artifacts
                WHERE artifact_type = 'normalized_session_json'
                ORDER BY session_key
                """
            ).fetchall()
            conn.close()

            assert len(rows) == 2
            assert rows[0]["session_key"] == "claude_code:sess-001"
            assert rows[1]["session_key"] == "claude_code:sess-002"
            assert rows[0]["path"] == str(artifact1)
            assert rows[1]["path"] == str(artifact2)
            assert rows[0]["content_hash"] != ""
            assert rows[1]["content_hash"] != ""

    def test_full_scan_skips_failed_artifacts(self, tmp_path):
        """Java 失败时，full_scan 不关联失败的 artifact。"""
        data_dir = tmp_path / "claude_data"
        shutil.copytree(str(FIXTURE_ROOT), str(data_dir))

        with patch("session_browser.index.scanners.execute_java_normalized_batch") as mock_batch:
            from session_browser.normalized.java_bridge import BatchResult, BatchSummary, ResultStatus
            from session_browser.normalized.normalized_batch import NormalizedBatchOutcome

            # 模拟 Java 返回一个失败结果
            mock_batch.return_value = NormalizedBatchOutcome(
                results=[
                    BatchResult(
                        request_id="claude_code:sess-001",
                        status=ResultStatus.FAILED,
                        session_key="claude_code:sess-001",
                        error="Parse error",
                    ),
                ],
                summary=BatchSummary(total=2, written=0, unchanged=0, failed=2),
                success_count=0,
                unchanged_count=0,
                failed_count=2,
            )

            db_path = str(tmp_path / "index.sqlite")
            _run_full_scan(str(data_dir), db_path)

            # 验证 session_artifacts 表无记录
            conn = sqlite3.connect(db_path)
            rows = conn.execute(
                "SELECT COUNT(*) FROM session_artifacts WHERE artifact_type = 'normalized_session_json'"
            ).fetchone()
            conn.close()

            assert rows[0] == 0

    def test_full_scan_artifact_only_by_java(self, tmp_path):
        """验证 full_scan 模块不再包含 Python artifact writer 引用。"""
        import session_browser.index.scanners as scanners_mod

        # writer 函数不应存在于 scanners 模块命名空间
        assert not hasattr(scanners_mod, 'persist_normalized_session_artifact'), (
            'scanners 模块不应包含 persist_normalized_session_artifact'
        )
        assert not hasattr(scanners_mod, 'write_normalized_session_artifact'), (
            'scanners 模块不应包含 write_normalized_session_artifact'
        )
        assert not hasattr(scanners_mod, '_persist_normalized_artifact_safe'), (
            'scanners 模块不应包含 _persist_normalized_artifact_safe'
        )
