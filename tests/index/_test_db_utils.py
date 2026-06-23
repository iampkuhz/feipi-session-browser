"""测试用 SQLite schema 初始化和数据写入工具。

本模块提供测试 fixture 所需的 schema 创建和行写入功能。
Python 生产 scan 写路径已退休，这些功能仅供测试使用。
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from session_browser.domain.models import SessionSummary


# 完整 sessions 表 DDL，与 Java scan 创建的 schema 保持一致。
_SESSIONS_DDL = """
    CREATE TABLE IF NOT EXISTS sessions (
        session_key TEXT PRIMARY KEY,
        agent TEXT NOT NULL CHECK(agent <> ''),
        session_id TEXT NOT NULL CHECK(session_id <> ''),
        title TEXT NOT NULL DEFAULT '',
        project_key TEXT NOT NULL CHECK(project_key <> ''),
        project_name TEXT NOT NULL DEFAULT '',
        cwd TEXT NOT NULL DEFAULT '',
        started_at TEXT NOT NULL DEFAULT '',
        ended_at TEXT NOT NULL CHECK(ended_at <> ''),
        duration_seconds REAL NOT NULL DEFAULT 0,
        model_execution_seconds REAL NOT NULL DEFAULT 0,
        tool_execution_seconds REAL NOT NULL DEFAULT 0,
        model TEXT NOT NULL DEFAULT '',
        git_branch TEXT NOT NULL DEFAULT '',
        source TEXT NOT NULL DEFAULT '',
        user_message_count INTEGER NOT NULL DEFAULT 0,
        assistant_message_count INTEGER NOT NULL DEFAULT 0,
        tool_call_count INTEGER NOT NULL DEFAULT 0,
        output_tokens INTEGER NOT NULL DEFAULT 0,
        fresh_input_tokens INTEGER NOT NULL DEFAULT 0,
        cache_read_tokens INTEGER NOT NULL DEFAULT 0,
        cache_write_tokens INTEGER NOT NULL DEFAULT 0,
        total_tokens INTEGER NOT NULL DEFAULT 0,
        failed_tool_count INTEGER NOT NULL DEFAULT 0,
        subagent_instance_count INTEGER NOT NULL DEFAULT 0,
        indexed_at REAL NOT NULL DEFAULT 0,
        file_mtime REAL NOT NULL DEFAULT 0,
        file_path TEXT NOT NULL DEFAULT ''
    );
"""

_SESSIONS_INDEXES_DDL = """
    CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project_key);
    CREATE INDEX IF NOT EXISTS idx_sessions_agent ON sessions(agent);
    CREATE INDEX IF NOT EXISTS idx_sessions_ended_at ON sessions(ended_at DESC);
    CREATE INDEX IF NOT EXISTS idx_sessions_model ON sessions(model);
    CREATE INDEX IF NOT EXISTS idx_sessions_title ON sessions(title);
"""

_SCAN_LOG_DDL = """
    CREATE TABLE IF NOT EXISTS scan_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        started_at REAL NOT NULL,
        finished_at REAL,
        claude_count INTEGER DEFAULT 0,
        codex_count INTEGER DEFAULT 0,
        qoder_count INTEGER DEFAULT 0,
        mode TEXT DEFAULT 'full',
        status TEXT DEFAULT 'running'
    );
"""

_INDEX_METADATA_DDL = """
    CREATE TABLE IF NOT EXISTS index_metadata (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL DEFAULT '',
        updated_at REAL NOT NULL DEFAULT 0
    );
"""

_SESSION_ARTIFACTS_DDL = """
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


def init_test_schema(conn: sqlite3.Connection) -> None:
    """为测试初始化完整 SQLite schema。

    测试 fixture 在写入测试数据前调用此函数。
    先删除已有表再重建，确保测试隔离。

    Args:
        conn: 已打开的 SQLite 连接。
    """
    conn.executescript("""
        DROP TABLE IF EXISTS session_artifacts;
        DROP TABLE IF EXISTS index_metadata;
        DROP TABLE IF EXISTS sessions;
        DROP TABLE IF EXISTS scan_log;
    """)
    conn.executescript(
        _SESSIONS_DDL
        + _SESSIONS_INDEXES_DDL
        + _SCAN_LOG_DDL
        + _INDEX_METADATA_DDL
        + _SESSION_ARTIFACTS_DDL
    )
    conn.commit()


def insert_test_session(conn: sqlite3.Connection, summary: SessionSummary) -> None:
    """为测试插入一个会话行。

    测试 fixture 使用此函数填充测试数据。

    Args:
        conn: 已打开的 SQLite 连接。
        summary: 要插入的会话摘要。
    """
    conn.execute(
        """
        INSERT INTO sessions (
            session_key, agent, session_id, title, project_key, project_name,
            cwd, started_at, ended_at, duration_seconds, model_execution_seconds,
            tool_execution_seconds,
            model, git_branch, source, user_message_count, assistant_message_count,
            tool_call_count, output_tokens, fresh_input_tokens, cache_read_tokens,
            cache_write_tokens, total_tokens, failed_tool_count,
            subagent_instance_count, indexed_at, file_mtime, file_path
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?
        )
        ON CONFLICT(session_key) DO UPDATE SET
            title=excluded.title,
            project_key=excluded.project_key,
            project_name=excluded.project_name,
            cwd=excluded.cwd,
            started_at=excluded.started_at,
            ended_at=excluded.ended_at,
            duration_seconds=excluded.duration_seconds,
            model_execution_seconds=excluded.model_execution_seconds,
            tool_execution_seconds=excluded.tool_execution_seconds,
            model=excluded.model,
            git_branch=excluded.git_branch,
            source=excluded.source,
            user_message_count=excluded.user_message_count,
            assistant_message_count=excluded.assistant_message_count,
            tool_call_count=excluded.tool_call_count,
            output_tokens=excluded.output_tokens,
            fresh_input_tokens=excluded.fresh_input_tokens,
            cache_read_tokens=excluded.cache_read_tokens,
            cache_write_tokens=excluded.cache_write_tokens,
            total_tokens=excluded.total_tokens,
            failed_tool_count=excluded.failed_tool_count,
            subagent_instance_count=excluded.subagent_instance_count,
            indexed_at=excluded.indexed_at,
            file_mtime=excluded.file_mtime,
            file_path=excluded.file_path
        """,
        (
            summary.session_key,
            summary.agent,
            summary.session_id,
            summary.title,
            summary.project_key,
            summary.project_name,
            summary.cwd,
            summary.started_at,
            summary.ended_at,
            summary.duration_seconds,
            summary.model_execution_seconds,
            summary.tool_execution_seconds,
            summary.model,
            summary.git_branch,
            summary.source,
            summary.user_message_count,
            summary.assistant_message_count,
            summary.tool_call_count,
            summary.output_tokens,
            summary.fresh_input_tokens,
            summary.cache_read_tokens,
            summary.cache_write_tokens,
            summary.total_tokens,
            summary.failed_tool_count,
            summary.subagent_instance_count,
            time.time(),
            0,
            '',
        ),
    )


def insert_test_artifact(  # noqa: PLR0913
    conn: sqlite3.Connection,
    *,
    session_key: str,
    artifact_type: str,
    path: str,
    schema_version: str = '',
    source_path: str = '',
    source_mtime: float = 0,
    size_bytes: int = 0,
    content_hash: str = '',
    validation_status: str = '',
) -> None:
    """为测试插入一个 artifact 行。

    Args:
        conn: 已打开的 SQLite 连接。
        session_key: 会话标识。
        artifact_type: artifact 类别。
        path: artifact 路径。
        schema_version: schema 版本。
        source_path: 源文件路径。
        source_mtime: 源文件修改时间。
        size_bytes: 文件大小。
        content_hash: 内容 hash。
        validation_status: 验证状态。
    """
    now = time.time()
    conn.execute(
        """
        INSERT INTO session_artifacts (
            session_key, artifact_type, path, schema_version, source_path,
            source_mtime, size_bytes, created_at, updated_at,
            content_hash, validation_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(session_key, artifact_type) DO UPDATE SET
            path=excluded.path,
            schema_version=excluded.schema_version,
            source_path=excluded.source_path,
            source_mtime=excluded.source_mtime,
            size_bytes=excluded.size_bytes,
            created_at=session_artifacts.created_at,
            updated_at=excluded.updated_at,
            content_hash=excluded.content_hash,
            validation_status=excluded.validation_status
        """,
        (
            session_key,
            artifact_type,
            path,
            schema_version,
            source_path,
            source_mtime,
            size_bytes,
            now,
            now,
            content_hash,
            validation_status,
        ),
    )


def create_test_connection(db_path: str | Path | None = None) -> sqlite3.Connection:
    """为测试创建配置好的 SQLite 连接。

    Args:
        db_path: 可选的数据库路径。省略时使用临时文件。

    Returns:
        配置了 row_factory 和外键的 SQLite 连接。
    """
    if db_path is None:
        conn = sqlite3.connect(':memory:')
    else:
        conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn
