"""Schema and connection management for the session index SQLite database."""

from __future__ import annotations

import sqlite3
from pathlib import Path

# --- Tiered background scan config -------------------------------------------

TIER_HOT_SECONDS = 30 * 60       # ended_at < 30min -> scan every 30s
TIER_HOT_INTERVAL = 30            # seconds between hot scans
TIER_WARM_SECONDS = 24 * 3600    # ended_at 30min~24h -> scan every 5min
TIER_WARM_INTERVAL = 5 * 60       # seconds between warm scans


def _get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """Get a SQLite connection to the index database."""
    from session_browser.config import INDEX_PATH, ensure_index_dir

    ensure_index_dir()
    path = db_path or INDEX_PATH
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_schema(conn: sqlite3.Connection | None = None) -> sqlite3.Connection:
    """Drop old schema and recreate with current structure.

    Adds file_mtime and file_path columns for incremental scan support.
    NOTE: This drops all existing data -- run a full scan afterwards.
    """
    if conn is None:
        conn = _get_connection()

    conn.executescript("""
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
            input_tokens INTEGER NOT NULL DEFAULT 0,
            output_tokens INTEGER NOT NULL DEFAULT 0,
            cached_input_tokens INTEGER NOT NULL DEFAULT 0,
            cached_output_tokens INTEGER NOT NULL DEFAULT 0,
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
    conn.commit()
    return conn
