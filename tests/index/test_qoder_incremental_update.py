"""Qoder 增量扫描：未变化会话跳过测试。

验证 incremental_scan 能正确：
1. 对已索引且 mtime 未变化的记录保持跳过。
2. 不在每次扫描时重复解析完整记录。

测试使用 monkeypatch 的临时 QODER_DATA_DIR —— 不涉及真实用户数据。
"""

from __future__ import annotations

import pytest
import json
import os
import sqlite3
import sys
from pathlib import Path

# ─── 常量 ─────────────────────────────────────────────────────────────────────

FULL_UUID = "b2c3d4e5-f6a7-8901-bcde-f23456789012"
PROJECT_NAME = "testproj"

# 最小 Qoder CLI JSONL（含 usage 数据 + tool 调用，可产生 timing + model）
CLI_JSONL_LINES = [
    json.dumps({
        "type": "user",
        "message": {"role": "user", "content": "Hello"},
        "timestamp": "2026-05-01T10:00:00.000Z",
        "cwd": "/tmp/testproj",
        "entrypoint": "cli",
        "sessionId": FULL_UUID,
        "version": "1.0.0",
    }),
    json.dumps({
        "type": "assistant",
        "message": {
            "model": "qwen3.6-plus",
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": "tool-001", "name": "Read", "input": {"file_path": "/tmp/test.py"}}
            ],
            "usage": {"input_tokens": 50, "output_tokens": 20},
        },
        "timestamp": "2026-05-01T10:00:02.000Z",
        "sessionId": FULL_UUID,
        "version": "1.0.0",
    }),
    json.dumps({
        "type": "user",
        "message": {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": "tool-001", "content": "file content"}],
        },
        "timestamp": "2026-05-01T10:00:04.000Z",
        "sessionId": FULL_UUID,
        "version": "1.0.0",
    }),
    json.dumps({
        "type": "assistant",
        "message": {
            "model": "qwen3.6-plus",
            "role": "assistant",
            "content": [{"type": "text", "text": "Hi there!"}],
            "usage": {"input_tokens": 100, "output_tokens": 30},
        },
        "timestamp": "2026-05-01T10:00:05.000Z",
        "sessionId": FULL_UUID,
        "version": "1.0.0",
    }),
]
CLI_JSONL_CONTENT = "\n".join(CLI_JSONL_LINES) + "\n"


# ─── 辅助函数 ─────────────────────────────────────────────────────────────────

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
    """仅对 Qoder 运行 full_scan。"""
    old = _setup_qoder_env(data_dir)
    try:
        from session_browser.index.indexer import full_scan

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        result = full_scan(conn, verbose=False, agent="qoder")
        conn.close()
        return result
    finally:
        _restore_qoder_env(old)


def _run_incremental_scan(data_dir: str, db_path: str) -> dict:
    """仅对 Qoder 运行 incremental_scan。"""
    old = _setup_qoder_env(data_dir)
    try:
        from session_browser.index.indexer import incremental_scan

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        result = incremental_scan(conn, verbose=False, agent="qoder")
        conn.close()
        return result
    finally:
        _restore_qoder_env(old)


def _create_qoder_project(data_dir: Path, project_name: str, session_id: str,
                          jsonl_content: str) -> Path:
    """创建 Qoder 项目目录及会话文件。"""
    proj_dir = data_dir / "projects" / project_name
    proj_dir.mkdir(parents=True, exist_ok=True)
    sess_file = proj_dir / f"{session_id}.jsonl"
    sess_file.write_text(jsonl_content)
    return sess_file


# ─── 测试 ─────────────────────────────────────────────────────────────────────

class TestQoderIncrementalCurrentRecords:
    """验证增量扫描跳过未变化的完整记录。"""

    @pytest.mark.contract_case("DATA-INDEX-009")
    def test_complete_record_still_skipped_on_unchanged_mtime(self, tmp_path):
        """完整记录（file_path + model + timing）仍应被跳过。

        验证性能契约：正常记录不应在每次增量扫描时被重新解析。
        """
        data_dir = tmp_path / "qoder_data"
        _create_qoder_project(data_dir, PROJECT_NAME, FULL_UUID, CLI_JSONL_CONTENT)

        db_path = str(tmp_path / "index.sqlite")

        # 步骤 1: 全量扫描
        _run_full_scan(str(data_dir), db_path)

        # 验证记录完整
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        skey = f"qoder:{FULL_UUID}"
        row = conn.execute(
            "SELECT file_path, model, model_execution_seconds, tool_execution_seconds "
            "FROM sessions WHERE session_key = ?",
            (skey,),
        ).fetchone()
        assert row["file_path"] != "", "Precondition: file_path should be set"
        assert row["model"] != "", "Precondition: model should be set"
        conn.close()

        # 步骤 2: 增量扫描，无任何文件变化
        result = _run_incremental_scan(str(data_dir), db_path)

        # 记录应被跳过（而非重新索引）
        assert result["qoder_count"] == 0, (
            f"Expected 0 re-indexed sessions (complete record, no change), "
            f"got qoder_count={result['qoder_count']}"
        )
        assert result["skipped"] >= 1, (
            f"Expected at least 1 skipped session, got skipped={result.get('skipped', 0)}"
        )
