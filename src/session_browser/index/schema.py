"""session index SQLite 数据库的 schema 和连接管理。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

# 说明：--- Tiered background scan config -------------------------------------------

TIER_HOT_SECONDS = 30 * 60       # 说明：ended_at < 30min -> scan every 30s
TIER_HOT_INTERVAL = 30            # 说明：seconds between hot scans
TIER_WARM_SECONDS = 24 * 3600    # 说明：ended_at 30min~24h -> scan every 5min
TIER_WARM_INTERVAL = 5 * 60       # 说明：seconds between warm scans


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
        PRIMARY KEY(session_key, artifact_type),
        FOREIGN KEY(session_key) REFERENCES sessions(session_key) ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS idx_session_artifacts_type
        ON session_artifacts(artifact_type);
    CREATE INDEX IF NOT EXISTS idx_session_artifacts_path
        ON session_artifacts(path);
"""


def _get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """打开会话索引 SQLite 连接。"""
    from session_browser.config import INDEX_PATH, ensure_index_dir

    ensure_index_dir()
    path = db_path or INDEX_PATH
    conn = sqlite3.connect(str(path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def ensure_session_artifacts_schema(conn: sqlite3.Connection) -> None:
    """创建会话产物附表，不修改 session 行。"""
    conn.executescript(SESSION_ARTIFACTS_SCHEMA_SQL)


def init_schema(conn: sqlite3.Connection | None = None) -> sqlite3.Connection:
    """重建当前索引结构。

    本函数会清空旧数据并创建当前 schema；升级后请重新执行 full scan。
    """
    if conn is None:
        conn = _get_connection()

    conn.executescript("""
        DROP TABLE IF EXISTS session_artifacts;
        DROP TABLE IF EXISTS sessions;
        DROP TABLE IF EXISTS scan_log;

        CREATE TABLE sessions (
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

        CREATE INDEX idx_sessions_project ON sessions(project_key);
        CREATE INDEX idx_sessions_agent ON sessions(agent);
        CREATE INDEX idx_sessions_ended_at ON sessions(ended_at DESC);
        CREATE INDEX idx_sessions_model ON sessions(model);
        CREATE INDEX idx_sessions_title ON sessions(title);

        CREATE TABLE scan_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at REAL NOT NULL,
            finished_at REAL,
            claude_count INTEGER DEFAULT 0,
            codex_count INTEGER DEFAULT 0,
            qoder_count INTEGER DEFAULT 0,
            mode TEXT DEFAULT 'full',
            status TEXT DEFAULT 'running'
        );
    """)
    ensure_session_artifacts_schema(conn)
    conn.commit()
    return conn
