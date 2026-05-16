"""SQLite indexer for session-browser.

Manages a local SQLite index of all sessions from both Claude Code and Codex.
Supports:
- Full initial scan (drops old schema, rebuilds)
- Incremental refresh (mtime-based: only re-parse changed .jsonl files)
- Tiered background scanning (hot/warm/cold by session age)
- Query interface for dashboard, project, and session pages
"""

from __future__ import annotations

import os
import json
import sqlite3
import time
from pathlib import Path
from typing import Optional

from session_browser.config import INDEX_PATH, ensure_index_dir
from session_browser.domain.models import SessionSummary, ProjectStats
from session_browser.sources import claude as claude_source
from session_browser.sources import codex as codex_source
from session_browser.sources import qoder as qoder_source

# ─── Tiered background scan config ────────────────────────────────────────

TIER_HOT_SECONDS = 30 * 60       # ended_at < 30min → scan every 30s
TIER_HOT_INTERVAL = 30            # seconds between hot scans
TIER_WARM_SECONDS = 24 * 3600    # ended_at 30min~24h → scan every 5min
TIER_WARM_INTERVAL = 5 * 60       # seconds between warm scans


def _get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """Get a SQLite connection to the index database."""
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
    NOTE: This drops all existing data — run a full scan afterwards.
    """
    if conn is None:
        conn = _get_connection()

    conn.executescript("""
        DROP TABLE IF EXISTS sessions;
        DROP TABLE IF EXISTS scan_log;

        CREATE TABLE sessions (
            session_key TEXT PRIMARY KEY,
            agent TEXT NOT NULL,
            session_id TEXT NOT NULL,
            title TEXT NOT NULL DEFAULT '',
            project_key TEXT NOT NULL,
            project_name TEXT NOT NULL DEFAULT '',
            cwd TEXT NOT NULL DEFAULT '',
            started_at TEXT NOT NULL DEFAULT '',
            ended_at TEXT NOT NULL DEFAULT '',
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
            failed_tool_count INTEGER NOT NULL DEFAULT 0,
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


def upsert_session(
    conn: sqlite3.Connection,
    summary: SessionSummary,
    file_mtime: float = 0,
    file_path: str = "",
) -> None:
    """Insert or update a single session in the index."""
    conn.execute(
        """
        INSERT INTO sessions (
            session_key, agent, session_id, title, project_key, project_name,
            cwd, started_at, ended_at, duration_seconds, model_execution_seconds,
            tool_execution_seconds,
            model, git_branch, source, user_message_count, assistant_message_count,
            tool_call_count, input_tokens, output_tokens, cached_input_tokens,
            cached_output_tokens, failed_tool_count, indexed_at, file_mtime, file_path
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            input_tokens=excluded.input_tokens,
            output_tokens=excluded.output_tokens,
            cached_input_tokens=excluded.cached_input_tokens,
            cached_output_tokens=excluded.cached_output_tokens,
            failed_tool_count=excluded.failed_tool_count,
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
            summary.input_tokens,
            summary.output_tokens,
            summary.cached_input_tokens,
            summary.cached_output_tokens,
            summary.failed_tool_count,
            time.time(),
            file_mtime,
            file_path,
        ),
    )


def full_scan(
    conn: sqlite3.Connection | None = None,
    verbose: bool = False,
    agent: str | None = None,
) -> dict:
    """Run a full scan of both Claude Code and Codex data sources.

    Args:
        conn: SQLite connection. If None, creates a new one.
        verbose: Print progress messages.
        agent: If provided, only scan this agent ("claude_code" or "codex").

    Returns a dict with scan statistics.
    """
    if conn is None:
        conn = _get_connection()

    init_schema(conn)

    log_id = conn.execute(
        "INSERT INTO scan_log (started_at, mode, status) VALUES (?, 'full', 'running')",
        (time.time(),),
    ).lastrowid
    conn.commit()

    claude_count = 0
    codex_count = 0
    qoder_count = 0

    scan_claude = agent is None or agent == "claude_code"
    scan_codex = agent is None or agent == "codex"
    scan_qoder = agent is None or agent == "qoder"

    # Scan Claude Code
    if scan_claude:
        if verbose:
            print("Scanning Claude Code...")
        # Pre-load history to build session→project mapping
        history = claude_source.parse_history()
        session_projects = {e["session_id"]: e["project"] for e in history}

        for entry in history:
            sid = entry["session_id"]
            project = entry["project"]
            summary, _msgs, _tcs, _sa = claude_source.parse_session_detail(
                project, sid, history_entry=entry
            )
            if not summary.title and entry.get("display"):
                summary.title = claude_source._extract_readable_title(entry["display"])

            # Record file mtime + path for future incremental scans
            file_mtime = 0.0
            file_path = ""
            fpath = _locate_claude_session_file(project, sid)
            if fpath and fpath.exists():
                file_path = str(fpath)
                file_mtime = os.path.getmtime(fpath)

            upsert_session(conn, summary, file_mtime=file_mtime, file_path=file_path)
            claude_count += 1
            if verbose and claude_count % 50 == 0:
                print(f"  Claude: {claude_count} sessions")

        conn.commit()

    # Scan Codex (pre-load threads DB once)
    if scan_codex:
        if verbose:
            print("Scanning Codex...")
        threads_db = codex_source.read_threads_db()
        for summary in codex_source.scan_all_sessions(threads_db):
            # Record file mtime + path for future incremental scans
            file_mtime = 0.0
            file_path = ""
            thread_info = threads_db.get(summary.session_id, {})
            rollout_path = thread_info.get("rollout_path", "")
            fpath = _locate_codex_session_file(summary.session_id, rollout_path)
            if fpath and fpath.exists():
                file_path = str(fpath)
                file_mtime = os.path.getmtime(fpath)

            upsert_session(conn, summary, file_mtime=file_mtime, file_path=file_path)
            codex_count += 1
            if verbose and codex_count % 50 == 0:
                print(f"  Codex: {codex_count} sessions")

        conn.commit()

    # Scan Qoder (walk projects/ directory)
    if scan_qoder:
        if verbose:
            print("Scanning Qoder...")
        for summary in qoder_source.scan_all_sessions():
            # Record file mtime + path for future incremental scans
            file_mtime = 0.0
            file_path = ""
            fpath = _locate_qoder_session_file(summary.project_key, summary.session_id)
            if fpath and fpath.exists():
                file_path = str(fpath)
                file_mtime = os.path.getmtime(fpath)

            upsert_session(conn, summary, file_mtime=file_mtime, file_path=file_path)
            qoder_count += 1
            if verbose and qoder_count % 50 == 0:
                print(f"  Qoder: {qoder_count} sessions")

        conn.commit()

    # Update log
    conn.execute(
        "UPDATE scan_log SET finished_at=?, claude_count=?, codex_count=?, qoder_count=?, status='done' WHERE id=?",
        (time.time(), claude_count, codex_count, qoder_count, log_id),
    )
    conn.commit()

    return {
        "claude_count": claude_count,
        "codex_count": codex_count,
        "qoder_count": qoder_count,
        "total": claude_count + codex_count + qoder_count,
    }


# ─── File location helpers ────────────────────────────────────────────────


def _locate_claude_session_file(project_key: str, session_id: str) -> Path | None:
    """Find a Claude session .jsonl file on disk."""
    from session_browser.config import CLAUDE_DATA_DIR

    projects_dir = CLAUDE_DATA_DIR / "projects"
    if not projects_dir.exists():
        return None

    # Try direct match
    candidate = projects_dir / project_key / f"{session_id}.jsonl"
    if candidate.exists():
        return candidate

    # Search all project directories
    for proj_dir in projects_dir.iterdir():
        if not proj_dir.is_dir():
            continue
        candidate = proj_dir / f"{session_id}.jsonl"
        if candidate.exists():
            return candidate
    return None


def _locate_codex_session_file(session_id: str, rollout_path: str = "") -> Path | None:
    """Find a Codex session .jsonl file on disk."""
    if rollout_path:
        p = Path(rollout_path)
        if p.exists():
            return p

    from session_browser.config import CODEX_DATA_DIR

    sessions_dir = CODEX_DATA_DIR / "sessions"
    if not sessions_dir.exists():
        return None

    for year_dir in sorted(sessions_dir.iterdir()):
        if not year_dir.is_dir():
            continue
        for month_dir in sorted(year_dir.iterdir()):
            if not month_dir.is_dir():
                continue
            for day_dir in sorted(month_dir.iterdir()):
                if not day_dir.is_dir():
                    continue
                found = list(day_dir.glob(f"rollout-*-{session_id}.jsonl"))
                if found:
                    return found[0]
    return None


def _locate_qoder_session_file(project_key: str, session_id: str) -> Path | None:
    """Find a Qoder session .jsonl file on disk."""
    from session_browser.config import QODER_DATA_DIR

    projects_dir = QODER_DATA_DIR / "projects"
    if not projects_dir.exists():
        return None

    # Try direct match
    candidate = projects_dir / project_key / f"{session_id}.jsonl"
    if candidate.exists():
        return candidate

    # Walk all subdirectories
    for root, _dirs, files in os.walk(projects_dir):
        if f"{session_id}.jsonl" in files:
            return Path(root) / f"{session_id}.jsonl"
    return None


# ─── Incremental scan ─────────────────────────────────────────────────────


def incremental_scan(
    conn: sqlite3.Connection | None = None,
    verbose: bool = False,
    agent: str | None = None,
    max_age_seconds: float | None = None,
) -> dict:
    """Scan only sessions whose source files have changed.

    Uses file mtime comparison to skip sessions that haven't been modified
    since the last index. Only scans sessions within max_age_seconds (by
    ended_at) if specified; older sessions are skipped.

    Args:
        conn: SQLite connection.
        verbose: Print progress messages.
        agent: If provided, only scan this agent.
        max_age_seconds: If set, only scan sessions whose ended_at is within
            this many seconds from now. Sessions older than this are skipped.

    Returns a dict with scan statistics.
    """
    if conn is None:
        conn = _get_connection()

    log_id = conn.execute(
        "INSERT INTO scan_log (started_at, mode, status) VALUES (?, 'incremental', 'running')",
        (time.time(),),
    ).lastrowid
    conn.commit()

    now = time.time()
    cutoff_iso = None
    if max_age_seconds is not None:
        from datetime import datetime, timezone, timedelta
        cutoff_dt = datetime.now(timezone.utc) - timedelta(seconds=max_age_seconds)
        cutoff_iso = cutoff_dt.isoformat()

    # Load existing sessions from DB: session_key → {ended_at, file_mtime, file_path, agent, model_execution_seconds, tool_execution_seconds}
    existing = {}
    columns = [r[0] for r in conn.execute("PRAGMA table_info(sessions)").fetchall()]
    has_model_exec = "model_execution_seconds" in columns
    has_tool_exec = "tool_execution_seconds" in columns
    for row in conn.execute(
        "SELECT session_key, ended_at, file_mtime, file_path, agent FROM sessions"
    ).fetchall():
        existing[row["session_key"]] = {
            "ended_at": row["ended_at"],
            "file_mtime": row["file_mtime"],
            "file_path": row["file_path"],
            "agent": row["agent"],
            "model_execution_seconds": row[5] if has_model_exec else 0,
            "tool_execution_seconds": row[6] if len(row) > 6 and has_tool_exec else 0,
        }

    # Also load session_id → project_key mapping from DB for Claude sessions
    claude_project_map = {}
    for row in conn.execute(
        "SELECT session_id, project_key FROM sessions WHERE agent='claude_code'"
    ).fetchall():
        claude_project_map[row["session_id"]] = row["project_key"]

    claude_count = 0
    codex_count = 0
    qoder_count = 0
    new_count = 0
    skipped_count = 0

    scan_claude = agent is None or agent == "claude_code"
    scan_codex = agent is None or agent == "codex"
    scan_qoder = agent is None or agent == "qoder"

    # ── Scan Claude ──────────────────────────────────────────────────
    if scan_claude:
        history = claude_source.parse_history()
        if verbose:
            print(f"Incremental scan: {len(history)} Claude sessions in history...")

        for entry in history:
            sid = entry["session_id"]
            project = entry["project"]
            skey = f"claude_code:{sid}"

            # Check if session exists in DB and is within age window
            info = existing.get(skey)
            if info:
                ended_at = info["ended_at"] or ""
                if cutoff_iso and ended_at < cutoff_iso:
                    skipped_count += 1
                    continue

                # Check file mtime — skip if unchanged and already has execution times
                stored_mtime = info["file_mtime"]
                stored_path = info["file_path"]
                stored_model_exec = info.get("model_execution_seconds", 0)
                stored_tool_exec = info.get("tool_execution_seconds", 0)
                has_timing_data = (stored_model_exec and stored_model_exec > 0 and
                                   stored_tool_exec and stored_tool_exec > 0)
                if stored_path and has_timing_data:
                    fpath = Path(stored_path)
                    if fpath.exists():
                        current_mtime = os.path.getmtime(fpath)
                        if current_mtime <= stored_mtime:
                            skipped_count += 1
                            continue
                        # File changed — re-parse
                    else:
                        # File deleted, try to locate it again
                        fpath = _locate_claude_session_file(project, sid)
                else:
                    # No stored path — try to locate
                    fpath = _locate_claude_session_file(project, sid)

                if fpath and fpath.exists():
                    current_mtime = os.path.getmtime(fpath)
                    # Always re-process if execution times are missing
                    if has_timing_data and current_mtime <= stored_mtime:
                        skipped_count += 1
                        continue
                else:
                    # Can't find file, skip
                    skipped_count += 1
                    continue
            else:
                new_count += 1

            # Parse session detail
            summary, _msgs, _tcs, _sa = claude_source.parse_session_detail(
                project, sid, history_entry=entry
            )
            if not summary.title and entry.get("display"):
                summary.title = claude_source._extract_readable_title(entry["display"])

            # Record file info
            file_mtime = 0.0
            file_path_str = ""
            fpath = _locate_claude_session_file(project, sid)
            if fpath and fpath.exists():
                file_path_str = str(fpath)
                file_mtime = os.path.getmtime(fpath)

            upsert_session(conn, summary, file_mtime=file_mtime, file_path=file_path_str)
            claude_count += 1

        conn.commit()

    # ── Scan Codex ───────────────────────────────────────────────────
    if scan_codex:
        threads_db = codex_source.read_threads_db()
        # Also load session_index.jsonl for fallback discovery
        index_entries = {e["id"]: e for e in codex_source.parse_session_index()}

        all_ids = set(threads_db.keys()) | set(index_entries.keys())
        if verbose:
            print(f"Incremental scan: {len(all_ids)} Codex sessions...")

        for sid in all_ids:
            skey = f"codex:{sid}"

            info = existing.get(skey)
            if info:
                ended_at = info["ended_at"] or ""
                if cutoff_iso and ended_at < cutoff_iso:
                    skipped_count += 1
                    continue

                stored_mtime = info["file_mtime"]
                stored_path = info["file_path"]
                stored_model_exec = info.get("model_execution_seconds", 0)
                stored_tool_exec = info.get("tool_execution_seconds", 0)
                has_timing_data = (stored_model_exec and stored_model_exec > 0 and
                                   stored_tool_exec and stored_tool_exec > 0)
                if stored_path and has_timing_data:
                    fpath = Path(stored_path)
                    if fpath.exists():
                        current_mtime = os.path.getmtime(fpath)
                        if current_mtime <= stored_mtime:
                            skipped_count += 1
                            continue
                    else:
                        # File moved/deleted, try to locate again
                        thread_info = threads_db.get(sid, {})
                        rollout_path = thread_info.get("rollout_path", "")
                        fpath = _locate_codex_session_file(sid, rollout_path)
                else:
                    thread_info = threads_db.get(sid, {})
                    rollout_path = thread_info.get("rollout_path", "")
                    fpath = _locate_codex_session_file(sid, rollout_path)

                if fpath and fpath.exists():
                    current_mtime = os.path.getmtime(fpath)
                    # Always re-process if execution times are missing
                    if has_timing_data and current_mtime <= stored_mtime:
                        skipped_count += 1
                        continue
                else:
                    skipped_count += 1
                    continue
            else:
                new_count += 1

            # Parse session
            thread_info = threads_db.get(sid, {})
            summary, _msgs, _tcs, _sa = codex_source.parse_session_detail(
                sid, threads_db
            )
            # Enrich title from index if empty
            if not summary.title:
                idx_entry = index_entries.get(sid)
                if idx_entry and idx_entry.get("thread_name"):
                    summary.title = idx_entry["thread_name"][:120]
                elif thread_info.get("first_user_message"):
                    summary.title = thread_info["first_user_message"][:120]

            # Record file info
            file_mtime = 0.0
            file_path_str = ""
            rollout_path = thread_info.get("rollout_path", "")
            fpath = _locate_codex_session_file(sid, rollout_path)
            if fpath and fpath.exists():
                file_path_str = str(fpath)
                file_mtime = os.path.getmtime(fpath)

            upsert_session(conn, summary, file_mtime=file_mtime, file_path=file_path_str)
            codex_count += 1

        conn.commit()

    # ── Scan Qoder ───────────────────────────────────────────────────
    if scan_qoder:
        discovered = qoder_source._discover_sessions()
        if verbose:
            print(f"Incremental scan: {len(discovered)} Qoder sessions...")

        for project_key, sid, fpath in discovered:
            skey = f"qoder:{sid}"

            info = existing.get(skey)
            if info:
                ended_at = info["ended_at"] or ""
                if cutoff_iso and ended_at < cutoff_iso:
                    skipped_count += 1
                    continue

                stored_mtime = info["file_mtime"]
                stored_path = info["file_path"]
                stored_model_exec = info.get("model_execution_seconds", 0)
                stored_tool_exec = info.get("tool_execution_seconds", 0)
                has_timing_data = (stored_model_exec and stored_model_exec > 0 and
                                   stored_tool_exec and stored_tool_exec > 0)
                if stored_path and has_timing_data:
                    p = Path(stored_path)
                    if p.exists():
                        current_mtime = os.path.getmtime(p)
                        if current_mtime <= stored_mtime:
                            skipped_count += 1
                            continue
                    else:
                        fpath = _locate_qoder_session_file(project_key, sid)
                else:
                    fpath = _locate_qoder_session_file(project_key, sid)

                if fpath and fpath.exists():
                    current_mtime = os.path.getmtime(fpath)
                    # Always re-process if execution times are missing
                    if has_timing_data and current_mtime <= stored_mtime:
                        skipped_count += 1
                        continue
                else:
                    skipped_count += 1
                    continue
            else:
                new_count += 1

            summary, _msgs, _tcs, _sa = qoder_source.parse_session_detail(
                project_key, sid, session_file=fpath
            )

            file_mtime = 0.0
            file_path_str = ""
            if fpath and fpath.exists():
                file_path_str = str(fpath)
                file_mtime = os.path.getmtime(fpath)

            upsert_session(conn, summary, file_mtime=file_mtime, file_path=file_path_str)
            qoder_count += 1

        conn.commit()

    # Update log
    conn.execute(
        "UPDATE scan_log SET finished_at=?, claude_count=?, codex_count=?, qoder_count=?, status='done' WHERE id=?",
        (time.time(), claude_count, codex_count, qoder_count, log_id),
    )
    conn.commit()

    return {
        "claude_count": claude_count,
        "codex_count": codex_count,
        "qoder_count": qoder_count,
        "total": claude_count + codex_count + qoder_count,
        "new_count": new_count,
        "skipped": skipped_count,
    }


# ─── Query interface ───────────────────────────────────────────────────────


def get_session(conn: sqlite3.Connection, session_key: str) -> SessionSummary | None:
    """Get a single session by key."""
    row = conn.execute(
        "SELECT * FROM sessions WHERE session_key = ?", (session_key,)
    ).fetchone()
    if row is None:
        return None
    return _row_to_summary(row)


def list_sessions(
    conn: sqlite3.Connection,
    agent: str | None = None,
    project_key: str | None = None,
    model: str | None = None,
    limit: int = 50,
    offset: int = 0,
    order_by: str = "ended_at",  # "ended_at" | "input_tokens" | "tool_call_count" | "duration_seconds" | "failed_tool_count"
) -> list[SessionSummary]:
    """List sessions with filtering and pagination."""
    clauses = []
    params: list = []

    if agent:
        clauses.append("agent = ?")
        params.append(agent)
    if project_key:
        clauses.append("project_key = ?")
        params.append(project_key)
    if model:
        clauses.append("model = ?")
        params.append(model)

    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    valid_orders = {
        "ended_at": "ended_at DESC",
        "input_tokens": "input_tokens DESC",
        "tool_call_count": "tool_call_count DESC",
        "duration_seconds": "duration_seconds DESC",
        "failed_tool_count": "failed_tool_count DESC",
    }
    order = valid_orders.get(order_by, "ended_at DESC")

    query = f"SELECT * FROM sessions {where} ORDER BY {order} LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = conn.execute(query, params).fetchall()
    return [_row_to_summary(r) for r in rows]


def count_sessions(
    conn: sqlite3.Connection,
    agent: str | None = None,
    project_key: str | None = None,
) -> int:
    """Count sessions with optional filtering."""
    clauses = []
    params: list = []
    if agent:
        clauses.append("agent = ?")
        params.append(agent)
    if project_key:
        clauses.append("project_key = ?")
        params.append(project_key)
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    row = conn.execute(f"SELECT COUNT(*) FROM sessions {where}", params).fetchone()
    return row[0]


def get_project_stats(conn: sqlite3.Connection, project_key: str) -> ProjectStats:
    """Get aggregated statistics for a project."""
    row = conn.execute(
        """
        SELECT
            project_key,
            project_name,
            COUNT(*) as total_sessions,
            SUM(CASE WHEN agent='claude_code' THEN 1 ELSE 0 END) as claude_sessions,
            SUM(CASE WHEN agent='codex' THEN 1 ELSE 0 END) as codex_sessions,
            SUM(CASE WHEN agent='qoder' THEN 1 ELSE 0 END) as qoder_sessions,
            MIN(started_at) as first_seen,
            MAX(ended_at) as last_seen,
            COALESCE(SUM(input_tokens), 0) as total_input_tokens,
            COALESCE(SUM(output_tokens), 0) as total_output_tokens,
            COALESCE(SUM(cached_input_tokens), 0) as total_cached_tokens,
            COALESCE(SUM(cached_output_tokens), 0) as total_cache_write_tokens,
            COALESCE(SUM(tool_call_count), 0) as total_tool_calls,
            COALESCE(SUM(failed_tool_count), 0) as total_failed_tools,
            COALESCE(SUM(user_message_count), 0) as total_user_messages,
            COALESCE(SUM(assistant_message_count), 0) as total_assistant_messages
        FROM sessions
        WHERE project_key = ?
        GROUP BY project_key
        """,
        (project_key,),
    ).fetchone()

    if row is None:
        return ProjectStats(project_key=project_key, project_name="")

    return ProjectStats(
        project_key=row["project_key"],
        project_name=row["project_name"],
        total_sessions=row["total_sessions"],
        claude_sessions=row["claude_sessions"],
        codex_sessions=row["codex_sessions"],
        qoder_sessions=row["qoder_sessions"],
        first_seen=row["first_seen"] or "",
        last_seen=row["last_seen"] or "",
        total_input_tokens=row["total_input_tokens"],
        total_output_tokens=row["total_output_tokens"],
        total_cached_tokens=row["total_cached_tokens"],
        total_cache_write_tokens=row["total_cache_write_tokens"],
        total_tool_calls=row["total_tool_calls"],
        total_failed_tools=row["total_failed_tools"],
        total_user_messages=row["total_user_messages"],
        total_assistant_messages=row["total_assistant_messages"],
    )


def list_projects(conn: sqlite3.Connection, limit: int = 20) -> list[ProjectStats]:
    """List projects sorted by most recent activity."""
    rows = conn.execute(
        """
        SELECT
            project_key,
            project_name,
            COUNT(*) as total_sessions,
            SUM(CASE WHEN agent='claude_code' THEN 1 ELSE 0 END) as claude_sessions,
            SUM(CASE WHEN agent='codex' THEN 1 ELSE 0 END) as codex_sessions,
            SUM(CASE WHEN agent='qoder' THEN 1 ELSE 0 END) as qoder_sessions,
            MIN(started_at) as first_seen,
            MAX(ended_at) as last_seen,
            COALESCE(SUM(input_tokens), 0) as total_input_tokens,
            COALESCE(SUM(output_tokens), 0) as total_output_tokens,
            COALESCE(SUM(cached_input_tokens), 0) as total_cached_tokens,
            COALESCE(SUM(cached_output_tokens), 0) as total_cache_write_tokens,
            COALESCE(SUM(tool_call_count), 0) as total_tool_calls,
            COALESCE(SUM(failed_tool_count), 0) as total_failed_tools,
            COALESCE(SUM(user_message_count), 0) as total_user_messages,
            COALESCE(SUM(assistant_message_count), 0) as total_assistant_messages
        FROM sessions
        GROUP BY project_key
        ORDER BY MAX(ended_at) DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()

    return [
        ProjectStats(
            project_key=r["project_key"],
            project_name=r["project_name"],
            total_sessions=r["total_sessions"],
            claude_sessions=r["claude_sessions"],
            codex_sessions=r["codex_sessions"],
            qoder_sessions=r["qoder_sessions"],
            first_seen=r["first_seen"] or "",
            last_seen=r["last_seen"] or "",
            total_input_tokens=r["total_input_tokens"],
            total_output_tokens=r["total_output_tokens"],
            total_cached_tokens=r["total_cached_tokens"],
            total_cache_write_tokens=r["total_cache_write_tokens"],
            total_tool_calls=r["total_tool_calls"],
            total_failed_tools=r["total_failed_tools"],
            total_user_messages=r["total_user_messages"],
            total_assistant_messages=r["total_assistant_messages"],
        )
        for r in rows
    ]


def get_dashboard_stats(conn: sqlite3.Connection) -> dict:
    """Get dashboard-level aggregated stats."""
    row = conn.execute(
        """
        SELECT
            COUNT(*) as total_sessions,
            SUM(CASE WHEN agent='claude_code' THEN 1 ELSE 0 END) as claude_sessions,
            SUM(CASE WHEN agent='codex' THEN 1 ELSE 0 END) as codex_sessions,
            SUM(CASE WHEN agent='qoder' THEN 1 ELSE 0 END) as qoder_sessions,
            COUNT(DISTINCT project_key) as project_count,
            COALESCE(SUM(input_tokens), 0) as total_input_tokens,
            COALESCE(SUM(output_tokens), 0) as total_output_tokens,
            COALESCE(SUM(cached_input_tokens), 0) as total_cached_input_tokens,
            COALESCE(SUM(cached_output_tokens), 0) as total_cached_output_tokens,
            COALESCE(SUM(tool_call_count), 0) as total_tool_calls,
            COALESCE(SUM(failed_tool_count), 0) as total_failed_tools
        FROM sessions
        """
    ).fetchone()

    return {
        "total_sessions": row["total_sessions"],
        "claude_sessions": row["claude_sessions"],
        "codex_sessions": row["codex_sessions"],
        "qoder_sessions": row["qoder_sessions"],
        "project_count": row["project_count"],
        "total_input_tokens": row["total_input_tokens"],
        "total_output_tokens": row["total_output_tokens"],
        "total_cached_input_tokens": row["total_cached_input_tokens"],
        "total_cached_output_tokens": row["total_cached_output_tokens"],
        "total_tool_calls": row["total_tool_calls"],
        "total_failed_tools": row["total_failed_tools"],
    }


def get_trend_data(
    conn: sqlite3.Connection,
    days: int = 30,
) -> list[dict]:
    """Get daily session/trend counts for the last N days.

    Returns list of {date, claude_count, codex_count, input_tokens, output_tokens,
                      cache_read, cache_write, tool_calls, failed_tools}.
    """
    rows = conn.execute(
        """
        SELECT
            DATE(ended_at) as day,
            SUM(CASE WHEN agent='claude_code' THEN 1 ELSE 0 END) as claude_count,
            SUM(CASE WHEN agent='codex' THEN 1 ELSE 0 END) as codex_count,
            SUM(CASE WHEN agent='qoder' THEN 1 ELSE 0 END) as qoder_count,
            COALESCE(SUM(input_tokens), 0) as input_tokens,
            COALESCE(SUM(output_tokens), 0) as output_tokens,
            COALESCE(SUM(cached_input_tokens), 0) as cache_read_tokens,
            COALESCE(SUM(cached_output_tokens), 0) as cache_write_tokens,
            COALESCE(SUM(tool_call_count), 0) as tool_calls,
            COALESCE(SUM(failed_tool_count), 0) as failed_tools,
            COUNT(*) as total_count
        FROM sessions
        WHERE ended_at >= date('now', ?)
        GROUP BY DATE(ended_at)
        ORDER BY day
        """,
        (f"-{days} days",),
    ).fetchall()

    return [
        {
            "date": r["day"],
            "claude_count": r["claude_count"],
            "codex_count": r["codex_count"],
            "qoder_count": r["qoder_count"],
            "input_tokens": r["input_tokens"],
            "output_tokens": r["output_tokens"],
            "cache_read_tokens": r["cache_read_tokens"],
            "cache_write_tokens": r["cache_write_tokens"],
            "tool_calls": r["tool_calls"],
            "failed_tools": r["failed_tools"],
            "total_count": r["total_count"],
        }
        for r in rows
    ]


def list_agents(conn: sqlite3.Connection) -> list[dict]:
    """List all agents with session counts.

    Returns list of {agent, session_count, last_active, total_tokens,
                     total_input_tokens, total_cached_tokens, total_cache_write_tokens,
                     total_output_tokens, total_tool_calls, total_failed_tools,
                     total_assistant_messages, project_count}.
    """
    rows = conn.execute(
        """
        SELECT
            agent,
            COUNT(*) as session_count,
            MAX(ended_at) as last_active,
            COALESCE(SUM(input_tokens + output_tokens + cached_input_tokens + cached_output_tokens), 0) as total_tokens,
            COALESCE(SUM(input_tokens), 0) as total_input_tokens,
            COALESCE(SUM(cached_input_tokens), 0) as total_cached_tokens,
            COALESCE(SUM(cached_output_tokens), 0) as total_cache_write_tokens,
            COALESCE(SUM(output_tokens), 0) as total_output_tokens,
            COALESCE(SUM(tool_call_count), 0) as total_tool_calls,
            COALESCE(SUM(failed_tool_count), 0) as total_failed_tools,
            COALESCE(SUM(assistant_message_count), 0) as total_assistant_messages,
            COUNT(DISTINCT project_key) as project_count
        FROM sessions
        GROUP BY agent
        ORDER BY MAX(ended_at) DESC
        """
    ).fetchall()
    return [dict(r) for r in rows]


def search_sessions(
    conn: sqlite3.Connection,
    query: str,
    limit: int = 50,
) -> list[SessionSummary]:
    """Search sessions by title, project, or model."""
    q = f"%{query}%"
    rows = conn.execute(
        """
        SELECT * FROM sessions
        WHERE title LIKE ? OR project_key LIKE ? OR project_name LIKE ? OR model LIKE ?
        ORDER BY ended_at DESC
        LIMIT ?
        """,
        (q, q, q, q, limit),
    ).fetchall()
    return [_row_to_summary(r) for r in rows]


# ─── Helpers ───────────────────────────────────────────────────────────────


def _row_to_summary(row: sqlite3.Row) -> SessionSummary:
    """Convert a DB row to SessionSummary."""
    return SessionSummary(
        agent=row["agent"],
        session_id=row["session_id"],
        title=row["title"],
        project_key=row["project_key"],
        project_name=row["project_name"],
        cwd=row["cwd"],
        started_at=row["started_at"],
        ended_at=row["ended_at"],
        duration_seconds=row["duration_seconds"],
        model_execution_seconds=row["model_execution_seconds"],
        tool_execution_seconds=row["tool_execution_seconds"],
        model=row["model"],
        git_branch=row["git_branch"],
        source=row["source"],
        user_message_count=row["user_message_count"],
        assistant_message_count=row["assistant_message_count"],
        tool_call_count=row["tool_call_count"],
        input_tokens=row["input_tokens"],
        output_tokens=row["output_tokens"],
        cached_input_tokens=row["cached_input_tokens"],
        cached_output_tokens=row["cached_output_tokens"],
        failed_tool_count=row["failed_tool_count"],
    )
