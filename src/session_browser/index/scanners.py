"""Scanning functions for the session index: full scan, incremental scan,
file locators, and Qoder project key normalization."""

from __future__ import annotations

import os
import time
from pathlib import Path

from session_browser.index.schema import _get_connection, init_schema
from session_browser.index.writers import upsert_session


# --- File location helpers ---------------------------------------------------


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
    from session_browser.config import CODEX_DATA_DIR

    if rollout_path:
        p = Path(rollout_path)
        if p.exists():
            return p

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

    Search order:
    1. Resolve short ID alias -> full UUID via canonical map, then search projects/.
    2. Search projects/ by session_id.
    3. Fall back to cache/projects/ -- recursive walk.
    """
    import re

    from session_browser.config import QODER_DATA_DIR
    from session_browser.sources import qoder as qoder_source

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

    # Step 2: search projects/ by original session_id
    projects_dir = QODER_DATA_DIR / "projects"
    if projects_dir.exists():
        candidate = projects_dir / project_key / f"{session_id}.jsonl"
        if candidate.exists():
            return candidate

    # Step 3: fall back to cache/projects/
    cache_dir = QODER_DATA_DIR / "cache" / "projects"
    if cache_dir.exists():
        for root, _dirs, files in os.walk(cache_dir):
            if f"{session_id}.jsonl" in files:
                return Path(root) / f"{session_id}.jsonl"

    return None


# --- Qoder cache project key normalization -----------------------------------


def _normalize_qoder_cache_projects(conn) -> None:
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


# --- Full scan ----------------------------------------------------------------


def full_scan(
    conn=None,
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
    from session_browser.sources import claude as claude_source
    from session_browser.sources import codex as codex_source
    from session_browser.sources import qoder as qoder_source

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
        # Pre-load history to build session->project mapping
        history = claude_source.parse_history()
        # Deduplicate by session_id -- history.jsonl can have multiple entries
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
                    print(f"  Skipping {sid}: no valid ended_at timestamp")
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
                    print(f"  Skipping {summary.session_id}: no valid ended_at timestamp")
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
        from session_browser.config import QODER_DATA_DIR

        if verbose:
            print("Scanning Qoder...")
        discovered = qoder_source._discover_sessions()
        cache_discovered = qoder_source._discover_cache_sessions()
        canonical_map = qoder_source._build_canonical_id_map()
        projects_ids = {sid.lower() for _pk, sid, _fp in discovered}
        all_discovered = list(discovered)
        for project_key, sid, fpath in cache_discovered:
            canonical_id = canonical_map.get(sid.lower(), sid)
            if canonical_id != sid.lower() and canonical_id in projects_ids:
                continue
            all_discovered.append((project_key, canonical_id, fpath))

        for project_key, sid, fpath in all_discovered:
            file_mtime = os.path.getmtime(fpath) if fpath.exists() else 0.0
            is_cache = str(fpath).startswith(str(QODER_DATA_DIR / "cache"))
            if is_cache:
                summary = qoder_source._parse_cache_session(
                    project_key, sid, fpath, file_mtime=file_mtime
                )
            else:
                summary, _msgs, _tcs, _sa = qoder_source.parse_session_detail(
                    project_key, sid, session_file=fpath, verbose=verbose
                )
                summary.subagent_instance_count = len(_sa)

            # Skip sessions with no valid timestamps
            if not summary.ended_at:
                if verbose:
                    print(f"  Skipping {summary.session_id}: no valid ended_at timestamp")
                continue

            file_path = str(fpath) if fpath and fpath.exists() else ""
            upsert_session(conn, summary, file_mtime=file_mtime, file_path=file_path)
            qoder_count += 1
            if verbose and qoder_count % 50 == 0:
                print(f"  Qoder: {qoder_count} sessions")

        conn.commit()

    # -- Normalize Qoder cache project keys --------------------------------
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


# --- Incremental scan ---------------------------------------------------------


def incremental_scan(
    conn=None,
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
    from session_browser.config import QODER_DATA_DIR
    from session_browser.sources import claude as claude_source
    from session_browser.sources import codex as codex_source
    from session_browser.sources import qoder as qoder_source

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

    # Load existing sessions from DB: session_key -> {ended_at, file_mtime, file_path, agent, model_execution_seconds, tool_execution_seconds, model}
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

    # Also load session_id -> project_key mapping from DB for Claude sessions
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

    # -- Scan Claude -------------------------------------------------------
    if scan_claude:
        history = claude_source.parse_history()
        # Deduplicate by session_id -- history.jsonl can have multiple entries
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

                # Check file mtime -- skip if unchanged.
                stored_mtime = info["file_mtime"]
                stored_path = info["file_path"]
                path_relocated = False
                if stored_path:
                    fpath = Path(stored_path)
                    if fpath.exists():
                        current_mtime = os.path.getmtime(fpath)
                        if current_mtime <= stored_mtime:
                            skipped_count += 1
                            continue
                    else:
                        # File deleted, try to locate it again
                        fpath = _locate_claude_session_file(project, sid)
                        if fpath and fpath.exists() and str(fpath) != stored_path:
                            path_relocated = True
                else:
                    skipped_count += 1
                    continue

                if fpath and fpath.exists():
                    current_mtime = os.path.getmtime(fpath)
                    # Skip unchanged files unless the stored path was relocated.
                    if current_mtime <= stored_mtime and not path_relocated:
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

    # -- Scan Codex --------------------------------------------------------
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
                path_relocated = False
                if stored_path:
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
                        if fpath and fpath.exists() and str(fpath) != stored_path:
                            path_relocated = True
                else:
                    skipped_count += 1
                    continue

                if fpath and fpath.exists():
                    current_mtime = os.path.getmtime(fpath)
                    # Skip unchanged files unless the stored path was relocated.
                    if current_mtime <= stored_mtime and not path_relocated:
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

    # -- Scan Qoder --------------------------------------------------------
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
                path_relocated = False
                if stored_path:
                    p = Path(stored_path)
                    if p.exists():
                        current_mtime = os.path.getmtime(p)
                        if current_mtime <= stored_mtime:
                            skipped_count += 1
                            continue
                    else:
                        # Stored path no longer valid -- relocate
                        fpath = _locate_qoder_session_file(project_key, sid)
                        if fpath and fpath.exists() and str(fpath) != stored_path:
                            path_relocated = True
                else:
                    skipped_count += 1
                    continue

                if fpath and fpath.exists():
                    current_mtime = os.path.getmtime(fpath)
                    # Skip unchanged files unless the stored path was relocated.
                    if current_mtime <= stored_mtime and not path_relocated:
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

    # -- Normalize Qoder cache project keys (same as full_scan) -----------
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
