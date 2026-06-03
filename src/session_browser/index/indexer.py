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

from session_browser.config import INDEX_PATH, QODER_DATA_DIR, ensure_index_dir
from session_browser.domain.models import SessionSummary, ProjectStats
from session_browser.domain.normalizer import sanitize_list_title
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
            cached_output_tokens, fresh_input_tokens, cache_read_tokens,
            cache_write_tokens, total_tokens, failed_tool_count, subagent_instance_count, indexed_at,
            file_mtime, file_path
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            summary.input_tokens,
            summary.output_tokens,
            summary.cached_input_tokens,
            summary.cached_output_tokens,
            summary.fresh_input_tokens,
            summary.cache_read_tokens,
            summary.cache_write_tokens,
            summary.total_tokens,
            summary.failed_tool_count,
            summary.subagent_instance_count,
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
        # Deduplicate by session_id — history.jsonl can have multiple entries
        # for the same session (continuations). Keep the last (most recent).
        seen = {}
        for entry in history:
            seen[entry["session_id"]] = entry
        unique_history = list(seen.values())

        session_projects = {e["session_id"]: e["project"] for e in unique_history}

        for entry in unique_history:
            sid = entry["session_id"]
            project = entry["project"]
            summary, _msgs, _tcs, _sa = claude_source.parse_session_detail(
                project, sid, history_entry=entry, verbose=verbose
            )
            summary.subagent_instance_count = len(_sa)
            if not summary.title and entry.get("display"):
                summary.title = claude_source._extract_readable_title(entry["display"])

            # Skip sessions with no valid timestamps (e.g., all events were non-dict JSON)
            if not summary.ended_at:
                if verbose:
                    print(f"  ⏭ Skipping {sid}: no valid ended_at timestamp")
                continue

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
        for summary in codex_source.scan_all_sessions(threads_db, verbose=verbose):
            # Skip sessions with no valid timestamps
            if not summary.ended_at:
                if verbose:
                    print(f"  ⏭ Skipping {summary.session_id}: no valid ended_at timestamp")
                continue

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
        for summary in qoder_source.scan_all_sessions(verbose=verbose):
            # Skip sessions with no valid timestamps
            if not summary.ended_at:
                if verbose:
                    print(f"  ⏭ Skipping {summary.session_id}: no valid ended_at timestamp")
                continue

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

    # ── Normalize Qoder cache project keys ─────────────────────────
    # Qoder cache sessions (from ~/.qoder/cache/projects/) have no cwd
    # and use a hash-stripped directory name as project_key (e.g.
    # "openspec-research-blockchain").  This diverges from Claude Code
    # and Codex which use the full filesystem path as project_key.
    # After all agents are scanned, look up matching project paths from
    # non-Qoder sessions and update Qoder cache sessions so the same
    # repo is grouped under a single project_key.
    if scan_qoder:
        _normalize_qoder_cache_projects(conn)

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
    """Find a Qoder session .jsonl file on disk.

    Searches both projects/ (CLI) and cache/projects/ (GUI) directories.

    Search order (optimised for old-index scenarios where file_path is missing):
    1. Resolve short ID alias -> full UUID via canonical map, then search projects/.
    2. Search projects/ by session_id — direct match then recursive.
    3. Fall back to cache/projects/ — recursive walk.
    """
    import re
    from session_browser.config import QODER_DATA_DIR

    uuid_pattern = re.compile(
        r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
    )

    # Step 1: resolve short ID alias -> full UUID, then try projects/ direct
    if not uuid_pattern.match(session_id):
        canonical_map = qoder_source._build_canonical_id_map()
        resolved_id = canonical_map.get(session_id.lower(), session_id)
        if resolved_id != session_id.lower():
            projects_dir = QODER_DATA_DIR / "projects"
            if projects_dir.exists():
                candidate = projects_dir / project_key / f"{resolved_id}.jsonl"
                if candidate.exists():
                    return candidate
                for root, _dirs, files in os.walk(projects_dir):
                    if f"{resolved_id}.jsonl" in files:
                        return Path(root) / f"{resolved_id}.jsonl"

    # Step 2: search projects/ by original session_id
    projects_dir = QODER_DATA_DIR / "projects"
    if projects_dir.exists():
        candidate = projects_dir / project_key / f"{session_id}.jsonl"
        if candidate.exists():
            return candidate
        for root, _dirs, files in os.walk(projects_dir):
            if f"{session_id}.jsonl" in files:
                return Path(root) / f"{session_id}.jsonl"

    # Step 3: fall back to cache/projects/
    cache_dir = QODER_DATA_DIR / "cache" / "projects"
    if cache_dir.exists():
        for root, _dirs, files in os.walk(cache_dir):
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

    # Load existing sessions from DB: session_key → {ended_at, file_mtime, file_path, agent, model_execution_seconds, tool_execution_seconds, model}
    existing = {}
    columns = [r[1] for r in conn.execute("PRAGMA table_info(sessions)").fetchall()]
    has_model_exec = "model_execution_seconds" in columns
    has_tool_exec = "tool_execution_seconds" in columns
    for row in conn.execute(
        "SELECT session_key, ended_at, file_mtime, file_path, agent, model"
        + (", model_execution_seconds" if has_model_exec else "")
        + (", tool_execution_seconds" if has_tool_exec else "")
        + " FROM sessions"
    ).fetchall():
        existing[row["session_key"]] = {
            "ended_at": row["ended_at"],
            "file_mtime": row["file_mtime"],
            "file_path": row["file_path"],
            "agent": row["agent"],
            "model": row["model"],
            "model_execution_seconds": row["model_execution_seconds"] if has_model_exec else 0,
            "tool_execution_seconds": row["tool_execution_seconds"] if has_tool_exec else 0,
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
        # Deduplicate by session_id — history.jsonl can have multiple entries
        # for the same session (continuations). Keep the last (most recent).
        seen = {}
        for entry in history:
            seen[entry["session_id"]] = entry
        unique_history = list(seen.values())
        if verbose:
            print(f"Incremental scan: {len(unique_history)} Claude sessions in history...")

        for entry in unique_history:
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
                stored_model = info.get("model", "")
                stored_model_exec = info.get("model_execution_seconds", 0)
                stored_tool_exec = info.get("tool_execution_seconds", 0)
                has_timing_data = (stored_model_exec and stored_model_exec > 0 and
                                   stored_tool_exec and stored_tool_exec > 0)
                # A record needs rebuild if it is missing file_path, model, or timing data.
                # This ensures old records can get file_path/model 补全 without
                # re-parsing all normal existing records on every scan.
                needs_rebuild = (not stored_path or not stored_model or not has_timing_data)
                path_relocated = False
                if stored_path:
                    fpath = Path(stored_path)
                    if fpath.exists():
                        current_mtime = os.path.getmtime(fpath)
                        # Only skip when file unchanged AND record is complete
                        if current_mtime <= stored_mtime and not needs_rebuild:
                            skipped_count += 1
                            continue
                    else:
                        # File deleted, try to locate it again
                        fpath = _locate_claude_session_file(project, sid)
                        if fpath and fpath.exists() and str(fpath) != stored_path:
                            path_relocated = True
                else:
                    # No stored path — try to locate
                    fpath = _locate_claude_session_file(project, sid)

                if fpath and fpath.exists():
                    current_mtime = os.path.getmtime(fpath)
                    # Skip only if file unchanged AND record is complete AND path unchanged
                    if current_mtime <= stored_mtime and not needs_rebuild and not path_relocated:
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
            summary.subagent_instance_count = len(_sa)
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
                stored_model = info.get("model", "")
                stored_model_exec = info.get("model_execution_seconds", 0)
                stored_tool_exec = info.get("tool_execution_seconds", 0)
                has_timing_data = (stored_model_exec and stored_model_exec > 0 and
                                   stored_tool_exec and stored_tool_exec > 0)
                # A record needs rebuild if it is missing file_path, model, or timing data.
                needs_rebuild = (not stored_path or not stored_model or not has_timing_data)
                path_relocated = False
                if stored_path:
                    fpath = Path(stored_path)
                    if fpath.exists():
                        current_mtime = os.path.getmtime(fpath)
                        # Only skip when file unchanged AND record is complete
                        if current_mtime <= stored_mtime and not needs_rebuild:
                            skipped_count += 1
                            continue
                    else:
                        # File moved/deleted, try to locate again
                        thread_info = threads_db.get(sid, {})
                        rollout_path = thread_info.get("rollout_path", "")
                        fpath = _locate_codex_session_file(sid, rollout_path)
                        if fpath and fpath.exists() and str(fpath) != stored_path:
                            path_relocated = True
                else:
                    thread_info = threads_db.get(sid, {})
                    rollout_path = thread_info.get("rollout_path", "")
                    fpath = _locate_codex_session_file(sid, rollout_path)

                if fpath and fpath.exists():
                    current_mtime = os.path.getmtime(fpath)
                    # Skip only if file unchanged AND record is complete AND path unchanged
                    if current_mtime <= stored_mtime and not needs_rebuild and not path_relocated:
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
        cache_discovered = qoder_source._discover_cache_sessions()
        # Canonicalize short IDs to full UUIDs before processing
        canonical_map = qoder_source._build_canonical_id_map()
        # Collect all projects/ session IDs to detect full overlap
        projects_ids = {sid.lower() for _pk, sid, _fp in discovered}
        all_discovered = []
        for project_key, sid, fpath in discovered:
            all_discovered.append((project_key, sid, fpath))
        for project_key, sid, fpath in cache_discovered:
            canonical_id = canonical_map.get(sid.lower(), sid)
            # Skip cache sessions that resolve to a projects/ session
            if canonical_id != sid.lower() and canonical_id in projects_ids:
                continue
            all_discovered.append((project_key, canonical_id, fpath))
        if verbose:
            print(f"Incremental scan: {len(all_discovered)} Qoder sessions...")

        for project_key, sid, fpath in all_discovered:
            skey = f"qoder:{sid}"

            info = existing.get(skey)
            if info:
                ended_at = info["ended_at"] or ""
                if cutoff_iso and ended_at < cutoff_iso:
                    skipped_count += 1
                    continue

                stored_mtime = info["file_mtime"]
                stored_path = info["file_path"]
                stored_model = info.get("model", "")
                stored_model_exec = info.get("model_execution_seconds", 0)
                stored_tool_exec = info.get("tool_execution_seconds", 0)
                has_timing_data = (stored_model_exec and stored_model_exec > 0 and
                                   stored_tool_exec and stored_tool_exec > 0)
                # A record needs rebuild if it is missing file_path, model, or timing data.
                # This ensures old records can get file_path/model 补全 without
                # re-parsing all normal existing records on every scan.
                needs_rebuild = (not stored_path or not stored_model or not has_timing_data)
                path_relocated = False
                if stored_path:
                    p = Path(stored_path)
                    if p.exists():
                        current_mtime = os.path.getmtime(p)
                        # Only skip when file unchanged AND record is complete
                        if current_mtime <= stored_mtime and not needs_rebuild:
                            skipped_count += 1
                            continue
                    else:
                        # Stored path no longer valid — relocate
                        fpath = _locate_qoder_session_file(project_key, sid)
                        if fpath and fpath.exists() and str(fpath) != stored_path:
                            path_relocated = True
                else:
                    fpath = _locate_qoder_session_file(project_key, sid)

                if fpath and fpath.exists():
                    current_mtime = os.path.getmtime(fpath)
                    # Skip only if file unchanged AND record is complete AND path unchanged
                    if current_mtime <= stored_mtime and not needs_rebuild and not path_relocated:
                        skipped_count += 1
                        continue
                else:
                    skipped_count += 1
                    continue
            else:
                new_count += 1

            # Cache sessions use a simpler format without timing data
            is_cache = str(fpath).startswith(str(QODER_DATA_DIR / "cache"))
            file_mtime = 0.0
            file_path_str = ""
            if fpath and fpath.exists():
                file_path_str = str(fpath)
                file_mtime = os.path.getmtime(fpath)

            if is_cache:
                summary = qoder_source._parse_cache_session(
                    project_key, sid, fpath, file_mtime=file_mtime
                )
            else:
                summary, _msgs, _tcs, _sa = qoder_source.parse_session_detail(
                    project_key, sid, session_file=fpath
                )
                summary.subagent_instance_count = len(_sa)

            upsert_session(conn, summary, file_mtime=file_mtime, file_path=file_path_str)
            qoder_count += 1

        conn.commit()

    # ── Normalize Qoder cache project keys (same as full_scan) ─────
    if scan_qoder:
        _normalize_qoder_cache_projects(conn)

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


# ─── Qoder cache project key normalization ─────────────────────────────


def _normalize_qoder_cache_projects(conn: sqlite3.Connection) -> None:
    """Fix Qoder cache session project_keys to match other agents.

    Qoder cache sessions (from ~/.qoder/cache/projects/) have no ``cwd``
    and use a hash-stripped directory name as ``project_key`` (e.g.
    ``"openspec-research-blockchain"``).  Claude Code and Codex use the
    full filesystem path (e.g.
    ``"/Users/zhehan/Documents/tools/llm/openspec/openspec-research-blockchain"``).

    When a Qoder cache session's ``cwd`` is empty and its ``project_key``
    does **not** start with ``/`` (i.e. it's a cache directory name), look
    up a matching project path from sessions that already have an absolute
    ``project_key`` (Claude Code, Codex, or Qoder CLI) by ``project_name``.
    If exactly one match exists, update the session's ``project_key`` so
    the same repo is grouped under a single project.
    """
    rows = conn.execute(
        "SELECT session_key, project_key, project_name "
        "FROM sessions "
        "WHERE agent = 'qoder' AND cwd = '' "
        "AND project_key NOT LIKE '/%'"
    ).fetchall()

    if not rows:
        return

    resolved_cache: dict[str, str | None] = {}

    for row in rows:
        project_name = row["project_name"]
        if project_name in resolved_cache:
            resolved = resolved_cache[project_name]
        else:
            # Look for a unique absolute project_key from sessions
            # that already have proper paths. Priority: Claude Code + Codex
            # first, then Qoder CLI (which has cwd != '').
            matches = conn.execute(
                "SELECT DISTINCT project_key FROM sessions "
                "WHERE project_name = ? "
                "AND (agent IN ('claude_code', 'codex') "
                "     OR (agent = 'qoder' AND cwd != '')) "
                "AND project_key LIKE '/%'",
                (project_name,),
            ).fetchall()
            resolved = matches[0]["project_key"] if len(matches) == 1 else None
            resolved_cache[project_name] = resolved

        if resolved is not None:
            conn.execute(
                "UPDATE sessions SET project_key = ? WHERE session_key = ?",
                (resolved, row["session_key"]),
            )

    conn.commit()


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
    title_like: str | None = None,
    limit: int = 50,
    offset: int = 0,
    order_by: str = "ended_at",
    order_dir: str = "desc",
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
    if title_like:
        # NOTE: title_like now searches both title and session_id,
        # case-insensitively.
        clauses.append(
            "(LOWER(title) LIKE LOWER(?) OR LOWER(session_id) LIKE LOWER(?))"
        )
        pattern = f"%{title_like}%"
        params.append(pattern)
        params.append(pattern)

    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    valid_orders = {
        "ended_at": "ended_at",
        "input_tokens": "input_tokens",
        "total_tokens": "total_tokens",
        "assistant_message_count": "assistant_message_count",
        "tool_call_count": "tool_call_count",
        "duration_seconds": "duration_seconds",
        "failed_tool_count": "failed_tool_count",
        "subagent_instance_count": "subagent_instance_count",
    }
    order_expr = valid_orders.get(order_by, "ended_at")
    safe_dir = "ASC" if order_dir == "asc" else "DESC"
    order = f"{order_expr} {safe_dir}"

    query = f"SELECT * FROM sessions {where} ORDER BY {order} LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = conn.execute(query, params).fetchall()
    return [_row_to_summary(r, truncate_title=True) for r in rows]


def count_sessions(
    conn: sqlite3.Connection,
    agent: str | None = None,
    project_key: str | None = None,
    model: str | None = None,
    title_like: str | None = None,
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
    if model:
        clauses.append("model = ?")
        params.append(model)
    if title_like:
        # NOTE: title_like now searches both title and session_id,
        # case-insensitively.
        clauses.append(
            "(LOWER(title) LIKE LOWER(?) OR LOWER(session_id) LIKE LOWER(?))"
        )
        pattern = f"%{title_like}%"
        params.append(pattern)
        params.append(pattern)
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    row = conn.execute(f"SELECT COUNT(*) FROM sessions {where}", params).fetchone()
    return row[0]


def get_sessions_list_aggregate(
    conn: sqlite3.Connection,
    agent: str | None = None,
    project_key: str | None = None,
    model: str | None = None,
    title_like: str | None = None,
) -> dict:
    """Get aggregate stats for filtered sessions list."""
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
    if title_like:
        # NOTE: title_like now searches both title and session_id,
        # case-insensitively.
        clauses.append(
            "(LOWER(title) LIKE LOWER(?) OR LOWER(session_id) LIKE LOWER(?))"
        )
        pattern = f"%{title_like}%"
        params.append(pattern)
        params.append(pattern)
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    row = conn.execute(
        f"SELECT COUNT(*) as session_count, "
        f"COUNT(DISTINCT project_key) as project_count, "
        f"COALESCE(SUM(total_tokens), 0) as total_tokens "
        f"FROM sessions {where}",
        params,
    ).fetchone()
    return {
        "session_count": row["session_count"],
        "project_count": row["project_count"],
        "total_tokens": row["total_tokens"],
    }


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
            COALESCE(SUM(cache_write_tokens), 0) as total_cache_write_tokens,
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


def count_projects(conn: sqlite3.Connection) -> int:
    """Count total number of distinct projects."""
    row = conn.execute(
        "SELECT COUNT(DISTINCT project_key) FROM sessions"
    ).fetchone()
    return row[0]


def list_projects(
    conn: sqlite3.Connection,
    limit: int = 20,
    offset: int = 0,
) -> list[ProjectStats]:
    """List projects sorted by most recent activity with pagination."""
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
            COALESCE(SUM(cache_write_tokens), 0) as total_cache_write_tokens,
            COALESCE(SUM(tool_call_count), 0) as total_tool_calls,
            COALESCE(SUM(failed_tool_count), 0) as total_failed_tools,
            COALESCE(SUM(user_message_count), 0) as total_user_messages,
            COALESCE(SUM(assistant_message_count), 0) as total_assistant_messages
        FROM sessions
        GROUP BY project_key
        ORDER BY MAX(ended_at) DESC
        LIMIT ? OFFSET ?
        """,
        (limit, offset),
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
            COALESCE(SUM(total_tokens), 0) as total_tokens,
            COALESCE(SUM(fresh_input_tokens), 0) as total_fresh_input_tokens,
            COALESCE(SUM(cache_read_tokens), 0) as total_cache_read_tokens,
            COALESCE(SUM(cache_write_tokens), 0) as total_cache_write_tokens,
            COALESCE(SUM(output_tokens), 0) as total_output_tokens,
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
        "total_tokens": row["total_tokens"],
        "total_fresh_input_tokens": row["total_fresh_input_tokens"],
        "total_cache_read_tokens": row["total_cache_read_tokens"],
        "total_cache_write_tokens": row["total_cache_write_tokens"],
        "total_output_tokens": row["total_output_tokens"],
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
            COALESCE(NULLIF(DATE(ended_at), ''), DATE('now')) as day,
            SUM(CASE WHEN agent='claude_code' THEN 1 ELSE 0 END) as claude_count,
            SUM(CASE WHEN agent='codex' THEN 1 ELSE 0 END) as codex_count,
            SUM(CASE WHEN agent='qoder' THEN 1 ELSE 0 END) as qoder_count,
            COALESCE(SUM(fresh_input_tokens), 0) as fresh_input_tokens,
            COALESCE(SUM(cache_read_tokens), 0) as cache_read_tokens,
            COALESCE(SUM(cache_write_tokens), 0) as cache_write_tokens,
            COALESCE(SUM(output_tokens), 0) as output_tokens,
            COALESCE(SUM(total_tokens), 0) as total_tokens,
            COALESCE(SUM(tool_call_count), 0) as tool_calls,
            COALESCE(SUM(failed_tool_count), 0) as failed_tools,
            COUNT(*) as total_count
        FROM sessions
        WHERE (ended_at >= date('now', ?) OR ended_at = '' OR ended_at IS NULL)
        GROUP BY COALESCE(NULLIF(DATE(ended_at), ''), DATE('now'))
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
            "fresh_input_tokens": r["fresh_input_tokens"],
            "cache_read_tokens": r["cache_read_tokens"],
            "cache_write_tokens": r["cache_write_tokens"],
            "output_tokens": r["output_tokens"],
            "total_tokens": r["total_tokens"],
            "cache_read_tokens": r["cache_read_tokens"],
            "cache_write_tokens": r["cache_write_tokens"],
            "tool_calls": r["tool_calls"],
            "failed_tools": r["failed_tools"],
            "total_count": r["total_count"],
        }
        for r in rows
    ]


def get_prompt_activity_trend(conn: sqlite3.Connection, days: int = 30) -> list[dict]:
    """Get daily user message counts for the last N days, broken down by agent.

    Returns list of {date, claude_prompts, codex_prompts, qoder_prompts, total_prompts}.
    """
    rows = conn.execute(
        """
        SELECT
            COALESCE(NULLIF(DATE(ended_at), ''), DATE('now')) as day,
            COALESCE(SUM(CASE WHEN agent='claude_code' THEN user_message_count ELSE 0 END), 0) as claude_prompts,
            COALESCE(SUM(CASE WHEN agent='codex' THEN user_message_count ELSE 0 END), 0) as codex_prompts,
            COALESCE(SUM(CASE WHEN agent='qoder' THEN user_message_count ELSE 0 END), 0) as qoder_prompts,
            COALESCE(SUM(user_message_count), 0) as total_prompts
        FROM sessions
        WHERE (ended_at >= date('now', ?) OR ended_at = '' OR ended_at IS NULL)
        GROUP BY COALESCE(NULLIF(DATE(ended_at), ''), DATE('now'))
        ORDER BY day
        """,
        (f"-{days} days",),
    ).fetchall()

    return [
        {
            "date": r["day"],
            "claude_prompts": r["claude_prompts"],
            "codex_prompts": r["codex_prompts"],
            "qoder_prompts": r["qoder_prompts"],
            "total_prompts": r["total_prompts"],
        }
        for r in rows
    ]


def list_agents(conn: sqlite3.Connection) -> list[dict]:
    """List all agents with session counts.

    Returns list of {agent, session_count, last_active, total_tokens,
                     total_fresh_input_tokens, total_cache_read_tokens, total_cache_write_tokens,
                     total_output_tokens, total_tool_calls, total_failed_tools,
                     total_assistant_messages, project_count}.
    """
    rows = conn.execute(
        """
        SELECT
            agent,
            COUNT(*) as session_count,
            MAX(ended_at) as last_active,
            COALESCE(SUM(total_tokens), 0) as total_tokens,
            COALESCE(SUM(fresh_input_tokens), 0) as total_fresh_input_tokens,
            COALESCE(SUM(cache_read_tokens), 0) as total_cache_read_tokens,
            COALESCE(SUM(cache_write_tokens), 0) as total_cache_write_tokens,
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


# ─── Helpers ───────────────────────────────────────────────────────────────


def _row_to_summary(row: sqlite3.Row, truncate_title: bool = False) -> SessionSummary:
    """Convert a DB row to SessionSummary."""
    title = row["title"]
    if truncate_title:
        title = sanitize_list_title(title)
    return SessionSummary(
        agent=row["agent"],
        session_id=row["session_id"],
        title=title,
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
        fresh_input_tokens=row["fresh_input_tokens"],
        cache_read_tokens=row["cache_read_tokens"],
        cache_write_tokens=row["cache_write_tokens"],
        total_tokens=row["total_tokens"],
        failed_tool_count=row["failed_tool_count"],
        subagent_instance_count=row["subagent_instance_count"],
        file_path=row["file_path"],
    )
