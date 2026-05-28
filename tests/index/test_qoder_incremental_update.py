"""Qoder 增量扫描：file_path/model 更新测试。

验证 incremental_scan 能正确：
1. 更新有 timing 数据但缺少 file_path 的旧记录。
2. 重新解析 model 为空的记录以填充（无需 mtime 变化）。
3. 在 mtime 未变时仍跳过完整记录（file_path + model + timing）。

测试使用 monkeypatch 的临时 QODER_DATA_DIR —— 不涉及真实用户数据。
"""

from __future__ import annotations

import pytest
import json
import os
import sqlite3
import sys
import time
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

class TestQoderIncrementalFilepathUpdate:
    """验证增量扫描更新旧记录的 file_path。"""

    @pytest.mark.contract_case("DATA-INDEX-009")
    def test_empty_file_path_gets_populated_without_mtime_change(self, tmp_path):
        """有 timing 数据但 file_path 为空的旧记录应被更新。

        场景：full_scan 存在未保存 file_path 的 bug，
        或 file_path 被清空。增量扫描应定位文件并更新
        file_path，无需 mtime 变化。
        """
        data_dir = tmp_path / "qoder_data"
        _create_qoder_project(data_dir, PROJECT_NAME, FULL_UUID, CLI_JSONL_CONTENT)

        db_path = str(tmp_path / "index.sqlite")

        # 步骤 1: 全量扫描创建记录
        _run_full_scan(str(data_dir), db_path)

        # 步骤 2: 手动清空 file_path 以模拟 bug 场景
        conn = sqlite3.connect(db_path)
        skey = f"qoder:{FULL_UUID}"
        conn.execute(
            "UPDATE sessions SET file_path = '' WHERE session_key = ?",
            (skey,),
        )
        conn.commit()

        # 验证 file_path 为空
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT file_path, model, model_execution_seconds, tool_execution_seconds FROM sessions WHERE session_key = ?",
            (skey,),
        ).fetchone()
        assert row["file_path"] == "", "Precondition: file_path should be empty"
        assert row["model"] != "", "Precondition: model should be set"
        conn.close()

        # 步骤 3: 运行增量扫描，无任何文件变化
        result = _run_incremental_scan(str(data_dir), db_path)

        # 记录应被重新处理（而非跳过）
        assert result["qoder_count"] >= 1, (
            f"Expected at least 1 re-indexed Qoder session (file_path update), "
            f"got qoder_count={result['qoder_count']}, skipped={result.get('skipped', 0)}"
        )

        # 验证 file_path 已被填充
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT file_path FROM sessions WHERE session_key = ?",
            (skey,),
        ).fetchone()
        assert row["file_path"] != "", (
            f"file_path should be populated after incremental scan, got: '{row['file_path']}'"
        )
        assert FULL_UUID in row["file_path"], (
            f"file_path should contain session ID, got: '{row['file_path']}'"
        )
        conn.close()

    @pytest.mark.contract_case("DATA-INDEX-009")
    def test_empty_model_gets_reparsed_without_mtime_change(self, tmp_path):
        """有 timing 数据但 model 为空的旧记录应被重新解析。

        场景：model 字段因解析 bug 为空。增量扫描应重新解析
        以填充 model，无需 mtime 变化。
        """
        data_dir = tmp_path / "qoder_data"
        _create_qoder_project(data_dir, PROJECT_NAME, FULL_UUID, CLI_JSONL_CONTENT)

        db_path = str(tmp_path / "index.sqlite")

        # 步骤 1: 全量扫描
        _run_full_scan(str(data_dir), db_path)

        # 步骤 2: 手动清空 model 以模拟 bug 场景
        conn = sqlite3.connect(db_path)
        skey = f"qoder:{FULL_UUID}"
        conn.execute(
            "UPDATE sessions SET model = '' WHERE session_key = ?",
            (skey,),
        )
        conn.commit()

        # 验证 model 为空
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT model, file_path FROM sessions WHERE session_key = ?",
            (skey,),
        ).fetchone()
        assert row["model"] == "", "Precondition: model should be empty"
        assert row["file_path"] != "", "Precondition: file_path should be set"
        conn.close()

        # 步骤 3: 增量扫描，无文件变化
        result = _run_incremental_scan(str(data_dir), db_path)

        # 记录应被重新处理（而非跳过），因为 model 为空
        assert result["qoder_count"] >= 1, (
            f"Expected at least 1 re-indexed Qoder session (model fill), "
            f"got qoder_count={result['qoder_count']}, skipped={result.get('skipped', 0)}"
        )

        # 验证 model 已被填充
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT model FROM sessions WHERE session_key = ?",
            (skey,),
        ).fetchone()
        assert row["model"] != "", (
            f"model should be populated after incremental scan, got: '{row['model']}'"
        )
        assert "qwen" in row["model"].lower(), (
            f"model should contain the correct model name, got: '{row['model']}'"
        )
        conn.close()

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

    @pytest.mark.contract_case("DATA-INDEX-009")
    def test_deleted_file_path_gets_relocated(self, tmp_path):
        """file_path 指向已删除文件的记录应被重新定位。

        场景：会话文件被移动到其他项目目录。
        增量扫描应找到新位置并更新 file_path。
        """
        data_dir = tmp_path / "qoder_data"

        # 在原始项目中创建会话
        sess_file = _create_qoder_project(
            data_dir, PROJECT_NAME, FULL_UUID, CLI_JSONL_CONTENT
        )

        db_path = str(tmp_path / "index.sqlite")

        # 步骤 1: 全量扫描
        _run_full_scan(str(data_dir), db_path)

        # 步骤 2: 将文件移动到其他项目目录
        new_proj = "movedproj"
        new_proj_dir = data_dir / "projects" / new_proj
        new_proj_dir.mkdir(parents=True, exist_ok=True)
        new_file = new_proj_dir / f"{FULL_UUID}.jsonl"
        sess_file.rename(new_file)

        # 步骤 3: 增量扫描
        result = _run_incremental_scan(str(data_dir), db_path)

        # 记录应被重新处理（文件已迁移）
        assert result["qoder_count"] >= 1, (
            f"Expected at least 1 re-indexed session (file relocation), "
            f"got qoder_count={result['qoder_count']}"
        )

        # 验证 file_path 已更新到新位置
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        skey = f"qoder:{FULL_UUID}"
        row = conn.execute(
            "SELECT file_path FROM sessions WHERE session_key = ?",
            (skey,),
        ).fetchone()
        assert new_proj in row["file_path"], (
            f"file_path should contain new project name '{new_proj}', "
            f"got: '{row['file_path']}'"
        )
        conn.close()

    @pytest.mark.contract_case("DATA-INDEX-009")
    def test_both_empty_filepath_and_model_reparsed(self, tmp_path):
        """file_path 和 model 都为空的记录应被重新解析。"""
        data_dir = tmp_path / "qoder_data"
        _create_qoder_project(data_dir, PROJECT_NAME, FULL_UUID, CLI_JSONL_CONTENT)

        db_path = str(tmp_path / "index.sqlite")

        # 步骤 1: 全量扫描
        _run_full_scan(str(data_dir), db_path)

        # 步骤 2: 清空 file_path 和 model
        conn = sqlite3.connect(db_path)
        skey = f"qoder:{FULL_UUID}"
        conn.execute(
            "UPDATE sessions SET file_path = '', model = '' WHERE session_key = ?",
            (skey,),
        )
        conn.commit()
        conn.close()

        # 步骤 3: 增量扫描
        result = _run_incremental_scan(str(data_dir), db_path)

        # 应被重新处理
        assert result["qoder_count"] >= 1, (
            f"Expected at least 1 re-indexed session (both fields empty), "
            f"got qoder_count={result['qoder_count']}"
        )

        # 验证两个字段都已恢复
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT file_path, model FROM sessions WHERE session_key = ?",
            (skey,),
        ).fetchone()
        assert row["file_path"] != "", "file_path should be populated"
        assert row["model"] != "", "model should be populated"
        conn.close()
