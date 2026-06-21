"""Manage SQLite schema and metadata tables for the session index.

Scan lifecycle code uses this module to open the index database, rebuild the
current schema, and maintain lightweight metadata such as scan logic version.
The SQL strings are kept here so index writers share one schema contract.
"""

from __future__ import annotations

import sqlite3
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


TIER_HOT_SECONDS = 30 * 60
TIER_HOT_INTERVAL = 30
TIER_WARM_SECONDS = 24 * 3600
TIER_WARM_INTERVAL = 5 * 60

SCAN_LOGIC_VERSION = 4
SCAN_LOGIC_VERSION_KEY = "scan_logic_version"


INDEX_METADATA_SCHEMA_SQL = """
    CREATE TABLE IF NOT EXISTS index_metadata (
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
        PRIMARY KEY(session_key, artifact_type),
        FOREIGN KEY(session_key) REFERENCES sessions(session_key) ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS idx_session_artifacts_type
        ON session_artifacts(artifact_type);
    CREATE INDEX IF NOT EXISTS idx_session_artifacts_path
        ON session_artifacts(path);
"""


def _get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """Open a configured SQLite connection for the session index.

    Scan and index setup code call this helper when no connection is supplied by
    the caller. It ensures the index directory exists, enables WAL mode, applies
    the busy timeout, and turns on foreign keys for writer operations.

    Args:
        db_path: Optional database path used by tests or alternate callers;
            defaults to the configured index path.

    Returns:
        SQLite connection configured with row access by column name.
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
    """Create the session artifact table and indexes if they are missing.

    Index setup and migration-safe callers use this helper to add artifact
    storage without changing existing session rows.

    Args:
        conn: Open SQLite connection for the session index.
    """
    conn.executescript(SESSION_ARTIFACTS_SCHEMA_SQL)


def ensure_index_metadata_schema(conn: sqlite3.Connection) -> None:
    """Create the global index metadata table if it is missing.

    Metadata readers and writers call this helper before touching the metadata
    table so incremental upgrades can run against older local databases.

    Args:
        conn: Open SQLite connection for the session index.
    """
    conn.executescript(INDEX_METADATA_SCHEMA_SQL)


def get_index_metadata(conn: sqlite3.Connection, key: str) -> str | None:
    """Read one metadata value from the index metadata table.

    Scan lifecycle code calls this function to inspect persisted version markers
    and other global index state. Missing keys return ``None``.

    Args:
        conn: Open SQLite connection for the session index.
        key: Metadata key to look up.

    Returns:
        Stored metadata value as a string, or ``None`` when the key is absent.
    """
    ensure_index_metadata_schema(conn)
    row = conn.execute(
        "SELECT value FROM index_metadata WHERE key = ?",
        (key,),
    ).fetchone()
    return str(row["value"]) if row else None


def set_index_metadata(conn: sqlite3.Connection, key: str, value: str) -> None:
    """Write one metadata value into the index metadata table.

    Scan lifecycle code calls this function to persist global index state. The
    function upserts by key and updates the timestamp using the current process
    clock.

    Args:
        conn: Open SQLite connection for the session index.
        key: Metadata key to create or update.
        value: Metadata value to store as text.
    """
    ensure_index_metadata_schema(conn)
    conn.execute(
        """
        INSERT INTO index_metadata (key, value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET
            value=excluded.value,
            updated_at=excluded.updated_at
        """,
        (key, str(value), time.time()),
    )


def get_stored_scan_logic_version(conn: sqlite3.Connection) -> str | None:
    """Read the persisted scan logic version from index metadata.

    Incremental scan orchestration calls this helper to decide whether local rows
    were produced by the current scan logic.

    Args:
        conn: Open SQLite connection for the session index.

    Returns:
        Stored scan logic version, or ``None`` when no marker exists.
    """
    return get_index_metadata(conn, SCAN_LOGIC_VERSION_KEY)


def set_stored_scan_logic_version(
    conn: sqlite3.Connection,
    version: int | str = SCAN_LOGIC_VERSION,
) -> None:
    """Persist the scan logic version into index metadata.

    Full schema initialization and scan lifecycle code call this after creating
    or validating rows so future scans can detect stale index data.

    Args:
        conn: Open SQLite connection for the session index.
        version: Version value to store; defaults to the current logic version.
    """
    set_index_metadata(conn, SCAN_LOGIC_VERSION_KEY, str(version))


def init_schema(conn: sqlite3.Connection | None = None) -> sqlite3.Connection:
    """Rebuild the current session index schema from scratch.

    Full reindex flows call this function when the local index must be reset. It
    drops existing index tables, recreates the current schema, initializes helper
    tables, commits the transaction, and returns the active connection.

    Args:
        conn: Existing SQLite connection to initialize; when omitted, a new index
            connection is opened with ``_get_connection``.

    Returns:
        SQLite connection containing the freshly initialized schema.
    """
    if conn is None:
        conn = _get_connection()

    conn.executescript("""
        DROP TABLE IF EXISTS session_artifacts;
        DROP TABLE IF EXISTS index_metadata;
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
    ensure_index_metadata_schema(conn)
    ensure_session_artifacts_schema(conn)
    conn.commit()
    return conn
