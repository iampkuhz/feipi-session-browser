"""SQLite 连接与 schema 辅助（只读路径）。

Web 查询和 attribution 代码使用本模块打开 SQLite 连接并确保
schema 表存在。Python scan 写路径已退休，schema 创建和迁移
由 Java scan 接管。
"""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


INDEX_METADATA_SCHEMA_SQL = """
    CREATE TABLE IF not EXISTS index_metadata (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL DEFAULT '',
        updated_at REAL NOT NULL DEFAULT 0
    );
"""

SESSION_ARTIFACTS_SCHEMA_SQL = """
    CREATE TABLE IF NOT EXISTS session_artifacts (
        session_key TEXT NOT NULL,
        artifact_type TEXT NOT NULL,
        path TEXT NOT NULL,
        schema_version TEXT NOT NULL DEFAULT '',
        source_path TEXT NOT NULL DEFAULT '',
        source_mtime REAL NOT NULL DEFAULT 0,
        size_bytes INTEGER NOT NULL DEFAULT 0,
        created_at REAL NOT NULL DEFAULT 0,
        updated_at REAL NOT NULL DEFAULT 0,
        content_hash TEXT NOT NULL DEFAULT '',
        validation_status TEXT NOT NULL DEFAULT '',
        PRIMARY KEY(session_key, artifact_type),
        FOREIGN KEY(session_key) REFERENCES sessions(session_key) ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS idx_session_artifacts_type
        ON session_artifacts(artifact_type);
    CREATE INDEX IF NOT EXISTS idx_session_artifacts_path
        ON session_artifacts(path);
"""


def _get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """打开会话索引的 SQLite 连接。

    Web 查询和 attribution 代码在需要数据库访问时调用此辅助函数。
    确保索引目录存在，启用 WAL 模式，设置 busy 超时，并打开外键。

    Args:
        db_path: 可选的数据库路径，供测试或替代调用方使用；
            默认使用配置的索引路径。

    Returns:
        配置好的 SQLite 连接，支持按列名访问行。
    """
    from session_browser.config import INDEX_PATH, ensure_index_dir  # noqa: PLC0415

    ensure_index_dir()
    path = db_path or INDEX_PATH
    conn = sqlite3.connect(str(path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def ensure_session_artifacts_schema(conn: sqlite3.Connection) -> None:
    """确保 session_artifacts 表和索引存在。

    Attribution 代码在写入 artifact 关联前调用此辅助函数。
    使用 ``CREATE TABLE IF NOT EXISTS`` 保证幂等。

    Args:
        conn: 已打开的 SQLite 连接。
    """
    conn.executescript(SESSION_ARTIFACTS_SCHEMA_SQL)


def ensure_index_metadata_schema(conn: sqlite3.Connection) -> None:
    """确保全局索引元数据表存在。

    元数据读取方在访问元数据表前调用此辅助函数。

    Args:
        conn: 已打开的 SQLite 连接。
    """
    conn.executescript(INDEX_METADATA_SCHEMA_SQL)
