"""Qoder 项目的规范 UUID 去重测试。

验证当同一个 Qoder 会话同时出现在以下两个位置时：
  - projects/<project>/<uuid>.jsonl  （CLI，完整 UUID）
  - cache/projects/<project>/conversation-history/<short>/<short>.jsonl  （GUI，短 ID 别名）

sessions 表应仅包含一条以完整 UUID 为键的记录，
而非两条独立的记录。

测试 S-08 场景：Qoder 短 ID 与完整 UUID 去重。
"""

from __future__ import annotations

import pytest
import json
import os
import sqlite3
import sys
from pathlib import Path

# ─── 测试夹具 ───────────────────────────────────────────────────────────

# 完整 UUID 规范键
FULL_UUID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"

# 短 ID 别名（同一会话，不同键）—— 必须是 FULL_UUID 的前缀
# 用于精确 UUID 前缀匹配规范化
SHORT_ID = "a1b2c3d4"

PROJECT_NAME = "myproj"

# 最小 Qoder JSONL 会话内容（含时间戳和 usage 的有效事件）
SESSION_JSONL_LINES = [
    json.dumps({
        "type": "user",
        "message": {"role": "user", "content": "Hello, help me write a test."},
        "timestamp": "2026-05-01T10:00:00.000Z",
        "cwd": "/tmp/myproj",
        "entrypoint": "cli",
        "sessionId": FULL_UUID,
        "version": "1.0.0",
    }),
    json.dumps({
        "type": "assistant",
        "message": {
            "model": "qwen3.6-plus",
            "role": "assistant",
            "content": [{"type": "text", "text": "Sure, here is a test."}],
            "usage": {"input_tokens": 100, "output_tokens": 50},
        },
        "timestamp": "2026-05-01T10:00:05.000Z",
        "sessionId": FULL_UUID,
        "version": "1.0.0",
    }),
    json.dumps({
        "type": "user",
        "message": {"role": "user", "content": "Thanks!"},
        "timestamp": "2026-05-01T10:00:10.000Z",
        "sessionId": FULL_UUID,
        "version": "1.0.0",
    }),
    json.dumps({
        "type": "assistant",
        "message": {
            "model": "qwen3.6-plus",
            "role": "assistant",
            "content": [{"type": "text", "text": "You are welcome!"}],
            "usage": {"input_tokens": 150, "output_tokens": 30},
        },
        "timestamp": "2026-05-01T10:00:15.000Z",
        "sessionId": FULL_UUID,
        "version": "1.0.0",
    }),
]

SESSION_JSONL_CONTENT = "\n".join(SESSION_JSONL_LINES) + "\n"


# ─── 辅助函数 ───────────────────────────────────────────────────────────

def _setup_qoder_env(data_dir: str):
    """设置 QODER_DATA_DIR 并重新加载依赖模块。"""
    old = os.environ.get("QODER_DATA_DIR", None)
    os.environ["QODER_DATA_DIR"] = data_dir

    # 重新加载 config + sources 以获取新的环境变量
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


def _create_fixture(tmp_path: Path) -> Path:
    """创建包含 projects + cache 会话文件的临时 Qoder 数据目录。"""
    data_dir = tmp_path / "qoder_data"

    # projects/<project>/<FULL_UUID>.jsonl
    projects_dir = data_dir / "projects" / PROJECT_NAME
    projects_dir.mkdir(parents=True, exist_ok=True)
    (projects_dir / f"{FULL_UUID}.jsonl").write_text(SESSION_JSONL_CONTENT)

    # cache/projects/<project>/conversation-history/<SHORT_ID>/<SHORT_ID>.jsonl
    cache_dir = data_dir / "cache" / "projects" / PROJECT_NAME / "conversation-history" / SHORT_ID
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / f"{SHORT_ID}.jsonl").write_text(SESSION_JSONL_CONTENT)

    return data_dir


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


# ─── 测试 ──────────────────────────────────────────────────────────────────

class TestQoderCanonicalDedup:
    """T012: Qoder short ID vs full UUID dedup — projects/cache overlap."""

    @pytest.mark.contract_case("DATA-INDEX-008")
    def test_no_duplicate_session_records(self, tmp_path):
        """当同一会话同时存在于 projects/ 和 cache/ 时，
        sessions 表应只有一条记录，而非两条。

        这是核心 S-08 断言：规范 UUID 去重必须防止
        同一逻辑会话产生两个列表条目。
        """
        data_dir = _create_fixture(tmp_path)
        db_path = str(tmp_path / "index.sqlite")
        result = _run_full_scan(str(data_dir), db_path)

        conn = sqlite3.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        conn.close()

        assert count == 1, (
            f"Expected 1 session record (canonical UUID dedup), got {count}. "
            f"Full UUID ({FULL_UUID}) and short ID ({SHORT_ID}) refer to the "
            f"same Qoder session and should not produce duplicate list entries."
        )

    @pytest.mark.contract_case("DATA-INDEX-008")
    def test_canonical_key_is_full_uuid(self, tmp_path):
        """存活的会话应以完整 UUID 为键，而非短 ID 别名。"""
        data_dir = _create_fixture(tmp_path)
        db_path = str(tmp_path / "index.sqlite")
        _run_full_scan(str(data_dir), db_path)

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        canonical_key = f"qoder:{FULL_UUID}"
        row = conn.execute(
            "SELECT session_key, session_id FROM sessions WHERE session_key = ?",
            (canonical_key,),
        ).fetchone()

        assert row is not None, (
            f"Canonical session_key '{canonical_key}' not found. "
            f"The full UUID should be the canonical key, not the short ID."
        )
        assert row["session_id"] == FULL_UUID, (
            f"session_id should be the full UUID ({FULL_UUID}), "
            f"got '{row['session_id']}'."
        )

        # 短 ID 不应产生独立的记录
        short_key = f"qoder:{SHORT_ID}"
        short_row = conn.execute(
            "SELECT session_key FROM sessions WHERE session_key = ?",
            (short_key,),
        ).fetchone()
        assert short_row is None, (
            f"Short ID key '{short_key}' should not exist as a separate record. "
            f"It is an alias of the full UUID canonical session."
        )

        conn.close()

    @pytest.mark.contract_case("DATA-INDEX-008")
    def test_total_count_matches_canonical(self, tmp_path):
        """full_scan 的总计数应为 1，而非 2。"""
        data_dir = _create_fixture(tmp_path)
        db_path = str(tmp_path / "index.sqlite")
        result = _run_full_scan(str(data_dir), db_path)

        assert result["qoder_count"] == 1, (
            f"Expected qoder_count=1 after dedup, got {result['qoder_count']}"
        )
        assert result["total"] == 1, (
            f"Expected total=1 after dedup, got {result['total']}"
        )

    @pytest.mark.contract_case("DATA-INDEX-008")
    def test_fixture_data_isolated(self, tmp_path):
        """使用 fixture 时，扫描不应触及真实的 ~/.qoder/。"""
        data_dir = _create_fixture(tmp_path)
        db_path = str(tmp_path / "index.sqlite")
        result = _run_full_scan(str(data_dir), db_path)

        # 应仅看到我们的 1 个规范会话，不包含真实 ~/.qoder/ 的数据
        assert result["total"] == 1, (
            "Index should only contain the fixture session, not real data"
        )
