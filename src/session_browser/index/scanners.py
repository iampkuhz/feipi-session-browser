"""Scanning functions，用于 该 session index: full scan, incremental scan,
file locators, and Qoder project key normalization."""

from __future__ import annotations

import os
import time
from pathlib import Path

from session_browser.index.schema import _get_connection, ensure_session_artifacts_schema, init_schema
from session_browser.index.writers import upsert_session
from session_browser.normalized.artifacts import (
    persist_current_normalized_session_artifact_reference,
    persist_normalized_session_artifact,
)


SCAN_COMMIT_EVERY = 25


def _commit_periodically(conn, count: int) -> None:
    if count > 0 and count % SCAN_COMMIT_EVERY == 0:
        conn.commit()


# 说明：--- File location helpers ---------------------------------------------------


def _locate_claude_session_file(project_key: str, session_id: str) -> Path | None:
    """查找 一个 Claude session .jsonl file on disk."""
    from session_browser.config import CLAUDE_DATA_DIR

    projects_dir = CLAUDE_DATA_DIR / "projects"
    if not projects_dir.exists():
        return None

    # 说明：Try direct match
    candidate = projects_dir / project_key / f"{session_id}.jsonl"
    if candidate.exists():
        return candidate

    # 搜索 所有 project directories
    for proj_dir in projects_dir.iterdir():
        if not proj_dir.is_dir():
            continue
        candidate = proj_dir / f"{session_id}.jsonl"
        if candidate.exists():
            return candidate
    return None


def _locate_codex_session_file(session_id: str, rollout_path: str = "") -> Path | None:
    """查找 一个 Codex session .jsonl file on disk."""
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
    """查找 一个 Qoder session .jsonl file on disk.

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

    # 说明：Step 1: resolve short ID alias -> full UUID, then try projects/ direct
    if not uuid_pattern.match(session_id):
        canonical_map = qoder_source._build_canonical_id_map()
        resolved_id = canonical_map.get(session_id.lower(), session_id)
        if resolved_id != session_id.lower():
            projects_dir = QODER_DATA_DIR / "projects"
            if projects_dir.exists():
                candidate = projects_dir / project_key / f"{resolved_id}.jsonl"
                if candidate.exists():
                    return candidate

    # 说明：Step 2: search projects/ by original session_id
    projects_dir = QODER_DATA_DIR / "projects"
    if projects_dir.exists():
        candidate = projects_dir / project_key / f"{session_id}.jsonl"
        if candidate.exists():
            return candidate

    # 说明：Step 3: fall back to cache/projects/
    cache_dir = QODER_DATA_DIR / "cache" / "projects"
    if cache_dir.exists():
        for root, _dirs, files in os.walk(cache_dir):
            if f"{session_id}.jsonl" in files:
                return Path(root) / f"{session_id}.jsonl"

    return None


def _persist_normalized_artifact_safe(
    conn,
    *,
    session_key: str,
    file_path: str,
    file_mtime: float,
    build_normalized,
    verbose: bool,
) -> None:
    """Persist normalized JSON，用于 一个 session without blocking 该 index scan."""
    if not file_path:
        return
    try:
        index_dir = _index_dir_from_connection(conn)
        if not _should_force_normalized_artifact_rebuild():
            reused = persist_current_normalized_session_artifact_reference(
                conn,
                session_key=session_key,
                source_path=file_path,
                source_mtime=file_mtime,
                index_dir=index_dir,
            )
            if reused is not None:
                return
        normalized = build_normalized()
        persist_normalized_session_artifact(
            conn,
            normalized,
            source_path=file_path,
            source_mtime=file_mtime,
            index_dir=index_dir,
            validate=_should_validate_normalized_artifacts(),
        )
    except Exception as exc:
        if verbose:
            print(f"  Normalized JSON skipped for {session_key}: {exc}")


def _index_dir_from_connection(conn) -> Path | None:
    """返回 该 directory containing 该 active SQLite main database."""
    try:
        for row in conn.execute("PRAGMA database_list").fetchall():
            seq = row[0]
            name = row[1]
            db_file = row[2]
            if (name == "main" or seq == 0) and db_file:
                return Path(db_file).parent
    except Exception:
        return None
    return None


def _should_validate_normalized_artifacts() -> bool:
    return os.environ.get("SESSION_BROWSER_VALIDATE_NORMALIZED_ARTIFACTS", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "y",
        "on",
    }


def _should_force_normalized_artifact_rebuild() -> bool:
    return os.environ.get("SESSION_BROWSER_FORCE_NORMALIZED_ARTIFACTS", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "y",
        "on",
    }


# 说明：--- Qoder cache project key normalization -----------------------------------


def _normalize_qoder_cache_projects(conn) -> None:
    """说明：Fix Qoder cache session project_keys to match other agents.

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
            # Look，用于 一个 unique absolute project_key，来源于 sessions
            # 说明：that already have proper paths. Priority: Claude Code + Codex
            # 说明：first, then Qoder CLI (which has cwd != '').
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


# 说明：--- Full scan ----------------------------------------------------------------


def full_scan(
    conn=None,
    verbose: bool = False,
    agent: str | None = None,
) -> dict:
    """Run 一个 full scan of both Claude Code 和 Codex data sources.

    Args:
        conn: SQLite connection. If None, creates a new one.
        verbose: Print progress messages.
        agent: If provided, only scan this agent ("claude_code" or "codex").

    Returns a dict with scan statistics.
    """
    from session_browser.sources import claude as claude_source
    from session_browser.sources import codex_session_source as codex_source
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

    # 扫描 Claude Code
    if scan_claude:
        if verbose:
            print("Scanning Claude Code...")
        # 说明：Pre-load history to build session->project mapping
        history = claude_source.parse_history()
        # 去重 by session_id -- history.jsonl can have multiple entries
        # for 该 same session (continuations). Keep 该 last (most recent).
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

            # 跳过 sessions，使用 no valid timestamps (e.g., 所有 events were non-dict JSON)
            if not summary.ended_at:
                if verbose:
                    print(f"  Skipping {sid}: no valid ended_at timestamp")
                continue

            # 记录 file mtime + path，用于 future incremental scans
            file_mtime = 0.0
            file_path = ""
            fpath = _locate_claude_session_file(project, sid)
            if fpath and fpath.exists():
                file_path = str(fpath)
                file_mtime = os.path.getmtime(fpath)

            upsert_session(conn, summary, file_mtime=file_mtime, file_path=file_path)
            _persist_normalized_artifact_safe(
                conn,
                session_key=summary.session_key,
                file_path=file_path,
                file_mtime=file_mtime,
                build_normalized=lambda: claude_source.build_normalized_session(
                    summary=summary,
                    messages=_msgs,
                    tool_calls=_tcs,
                    subagent_runs=_sa,
                    source_path=file_path,
                ),
                verbose=verbose,
            )
            claude_count += 1
            _commit_periodically(conn, claude_count)
            if verbose and claude_count % 50 == 0:
                print(f"  Claude: {claude_count} sessions")

        conn.commit()

    # 扫描 Codex (pre-load threads DB once)
    if scan_codex:
        if verbose:
            print("Scanning Codex...")
        threads_db = codex_source.read_threads_db()
        index_entries = {e["id"]: e for e in codex_source.parse_session_index()}
        codex_ids = list(threads_db.keys())
        codex_ids.extend(sid for sid in index_entries if sid not in threads_db)
        for sid in codex_ids:
            if sid in threads_db:
                parse_threads_db = threads_db
                thread_info = threads_db.get(sid, {})
            else:
                idx_entry = index_entries.get(sid, {})
                thread_info = {
                    "id": sid,
                    "title": idx_entry.get("thread_name", ""),
                    "cwd": "",
                    "model": "",
                    "tokens_used": 0,
                    "created_at": 0,
                    "updated_at": 0,
                    "git_branch": "",
                    "source": "",
                    "model_provider": "",
                    "cli_version": "",
                    "rollout_path": "",
                    "first_user_message": "",
                }
                parse_threads_db = {sid: thread_info}

            summary, _msgs, _tcs, _sa, normalized, session_file = (
                codex_source.parse_session_detail_with_normalized(
                    sid,
                    parse_threads_db,
                    verbose=verbose,
                )
            )
            # Enrich title，来源于 index，如果 empty, matching scan_all_sessions.
            if not summary.title:
                idx_entry = index_entries.get(sid)
                if idx_entry and idx_entry.get("thread_name"):
                    summary.title = idx_entry["thread_name"][:120]
                elif thread_info.get("first_user_message"):
                    summary.title = thread_info["first_user_message"][:120]
            if normalized and summary.title and not (normalized.get("session") or {}).get("title"):
                normalized["session"]["title"] = summary.title[:160]

            # 跳过 sessions，使用 no valid timestamps
            if not summary.ended_at:
                if verbose:
                    print(f"  Skipping {summary.session_id}: no valid ended_at timestamp")
                continue

            # 记录 file mtime + path，用于 future incremental scans
            file_mtime = 0.0
            file_path = ""
            fpath = session_file
            if fpath and fpath.exists():
                file_path = str(fpath)
                file_mtime = os.path.getmtime(fpath)

            upsert_session(conn, summary, file_mtime=file_mtime, file_path=file_path)
            _persist_normalized_artifact_safe(
                conn,
                session_key=summary.session_key,
                file_path=file_path,
                file_mtime=file_mtime,
                build_normalized=lambda: normalized,
                verbose=verbose,
            )
            codex_count += 1
            _commit_periodically(conn, codex_count)
            if verbose and codex_count % 50 == 0:
                print(f"  Codex: {codex_count} sessions")

        conn.commit()

    # 扫描 Qoder (walk projects/ directory)
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
            summary, _msgs, _tcs, _sa = qoder_source.parse_session_detail(
                project_key, sid, session_file=fpath, verbose=verbose
            )
            summary.subagent_instance_count = len(_sa)
            if is_cache:
                summary.file_path = str(fpath)

            # 跳过 sessions，使用 no valid timestamps
            if not summary.ended_at:
                if verbose:
                    print(f"  Skipping {summary.session_id}: no valid ended_at timestamp")
                continue

            file_path = str(fpath) if fpath and fpath.exists() else ""
            upsert_session(conn, summary, file_mtime=file_mtime, file_path=file_path)
            _persist_normalized_artifact_safe(
                conn,
                session_key=summary.session_key,
                file_path=file_path,
                file_mtime=file_mtime,
                build_normalized=lambda: qoder_source.build_normalized_session(
                    summary=summary,
                    messages=_msgs,
                    tool_calls=_tcs,
                    subagent_runs=_sa,
                    source_path=file_path,
                ),
                verbose=verbose,
            )
            qoder_count += 1
            _commit_periodically(conn, qoder_count)
            if verbose and qoder_count % 50 == 0:
                print(f"  Qoder: {qoder_count} sessions")

        conn.commit()

    # 说明：-- Normalize Qoder cache project keys --------------------------------
    # 说明：Qoder cache sessions (from ~/.qoder/cache/projects/) have no cwd
    # and use 一个 hash-stripped directory name as project_key (e.g.
    # "openspec-research-blockchain").  This diverges，来源于 Claude Code
    # and Codex which use 该 full filesystem path as project_key.
    # After 所有 agents are scanned, look up matching project paths from
    # non-Qoder sessions 和 update Qoder cache sessions so 该 same
    # repo is grouped under 一个 single project_key.
    if scan_qoder:
        _normalize_qoder_cache_projects(conn)

    # 说明：Update log
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


# 说明：--- Incremental scan ---------------------------------------------------------


def incremental_scan(
    conn=None,
    verbose: bool = False,
    agent: str | None = None,
    max_age_seconds: float | None = None,
) -> dict:
    """扫描 仅 sessions whose source files have changed.

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
    from session_browser.sources import codex_session_source as codex_source
    from session_browser.sources import qoder as qoder_source

    if conn is None:
        conn = _get_connection()

    ensure_session_artifacts_schema(conn)
    conn.commit()

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

    # 加载 existing sessions，来源于 DB: session_key -> {ended_at, file_mtime, file_path, agent, model_execution_seconds, tool_execution_seconds, model}
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

    # Also load session_id -> project_key mapping，来源于 DB，用于 Claude sessions
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

    # -- 扫描 Claude Code --------------------------------------------------
    if scan_claude:
        history = claude_source.parse_history()
        # history.jsonl 可能为同一 session 记录多次 continuation；保留最后一条作为最新入口。
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

            # 已索引 session 先检查年龄窗口，过旧时本轮增量扫描不再解析源文件。
            info = existing.get(skey)
            if info:
                ended_at = info["ended_at"] or ""
                if cutoff_iso and ended_at < cutoff_iso:
                    skipped_count += 1
                    continue

                # mtime 未变化即可跳过；路径失效时尝试重新定位，避免移动文件后永久失联。
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
                        # 记录路径已删除时，用 project/session_id 再定位一次源文件。
                        fpath = _locate_claude_session_file(project, sid)
                        if fpath and fpath.exists() and str(fpath) != stored_path:
                            path_relocated = True
                else:
                    skipped_count += 1
                    continue

                if fpath and fpath.exists():
                    current_mtime = os.path.getmtime(fpath)
                    # 路径迁移即使 mtime 未变也要重写索引中的 file_path。
                    if current_mtime <= stored_mtime and not path_relocated:
                        skipped_count += 1
                        continue
                else:
                    # 找不到源文件时只能跳过，避免用旧路径覆盖当前索引。
                    skipped_count += 1
                    continue
            else:
                new_count += 1

            # 只有新增、变更或重新定位的 session 才解析详情。
            summary, _msgs, _tcs, _sa = claude_source.parse_session_detail(
                project, sid, history_entry=entry
            )
            summary.subagent_instance_count = len(_sa)
            if not summary.title and entry.get("display"):
                summary.title = claude_source._extract_readable_title(entry["display"])

            # 记录当前源文件路径和 mtime，供下一轮增量扫描判定。
            file_mtime = 0.0
            file_path_str = ""
            fpath = _locate_claude_session_file(project, sid)
            if fpath and fpath.exists():
                file_path_str = str(fpath)
                file_mtime = os.path.getmtime(fpath)

            upsert_session(conn, summary, file_mtime=file_mtime, file_path=file_path_str)
            _persist_normalized_artifact_safe(
                conn,
                session_key=summary.session_key,
                file_path=file_path_str,
                file_mtime=file_mtime,
                build_normalized=lambda: claude_source.build_normalized_session(
                    summary=summary,
                    messages=_msgs,
                    tool_calls=_tcs,
                    subagent_runs=_sa,
                    source_path=file_path_str,
                ),
                verbose=verbose,
            )
            claude_count += 1
            _commit_periodically(conn, claude_count)

        conn.commit()

    # -- 扫描 Codex --------------------------------------------------------
    if scan_codex:
        threads_db = codex_source.read_threads_db()
        # threads DB 不完整时，用 session_index.jsonl 作为发现兜底。
        index_entries = {e["id"]: e for e in codex_source.parse_session_index()}

        all_ids = list(threads_db.keys())
        all_ids.extend(sid for sid in index_entries if sid not in threads_db)
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
                        # rollout 文件被移动或删除时，结合 threads DB 路径提示重新定位。
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
                    # 路径迁移即使 mtime 未变也要刷新 DB 中的 file_path。
                    if current_mtime <= stored_mtime and not path_relocated:
                        skipped_count += 1
                        continue
                else:
                    skipped_count += 1
                    continue
            else:
                new_count += 1

            # 同一次 rollout 读取同时产出 summary 和 normalized JSON，避免重复读大文件。
            if sid in threads_db:
                thread_info = threads_db.get(sid, {})
                parse_threads_db = threads_db
            else:
                idx_entry = index_entries.get(sid, {})
                thread_info = {
                    "id": sid,
                    "title": idx_entry.get("thread_name", ""),
                    "cwd": "",
                    "model": "",
                    "tokens_used": 0,
                    "created_at": 0,
                    "updated_at": 0,
                    "git_branch": "",
                    "source": "",
                    "model_provider": "",
                    "cli_version": "",
                    "rollout_path": "",
                    "first_user_message": "",
                }
                parse_threads_db = {sid: thread_info}
            summary, _msgs, _tcs, _sa, normalized, session_file = (
                codex_source.parse_session_detail_with_normalized(
                    sid,
                    parse_threads_db,
                )
            )
            # Enrich title，来源于 index，如果 empty
            if not summary.title:
                idx_entry = index_entries.get(sid)
                if idx_entry and idx_entry.get("thread_name"):
                    summary.title = idx_entry["thread_name"][:120]
                elif thread_info.get("first_user_message"):
                    summary.title = thread_info["first_user_message"][:120]
            if normalized and summary.title and not (normalized.get("session") or {}).get("title"):
                normalized["session"]["title"] = summary.title[:160]

            # 记录 file info
            file_mtime = 0.0
            file_path_str = ""
            fpath = session_file
            if fpath and fpath.exists():
                file_path_str = str(fpath)
                file_mtime = os.path.getmtime(fpath)

            upsert_session(conn, summary, file_mtime=file_mtime, file_path=file_path_str)
            _persist_normalized_artifact_safe(
                conn,
                session_key=summary.session_key,
                file_path=file_path_str,
                file_mtime=file_mtime,
                build_normalized=lambda: normalized,
                verbose=verbose,
            )
            codex_count += 1
            _commit_periodically(conn, codex_count)

        conn.commit()

    # -- 扫描 Qoder --------------------------------------------------------
    if scan_qoder:
        discovered = qoder_source._discover_sessions()
        cache_discovered = qoder_source._discover_cache_sessions()
        # cache 目录可能只有短 ID，先映射到 canonical UUID 再和 projects/ 结果去重。
        canonical_map = qoder_source._build_canonical_id_map()
        # projects/ 中已有完整 session 时，跳过同一 UUID 对应的 cache 副本。
        projects_ids = {sid.lower() for _pk, sid, _fp in discovered}
        all_discovered = []
        for project_key, sid, fpath in discovered:
            all_discovered.append((project_key, sid, fpath))
        for project_key, sid, fpath in cache_discovered:
            canonical_id = canonical_map.get(sid.lower(), sid)
            # 跳过 cache sessions that resolve to 一个 projects/ session
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
                        # 记录路径失效时重新定位，防止 cache/projects 迁移后索引卡在旧路径。
                        fpath = _locate_qoder_session_file(project_key, sid)
                        if fpath and fpath.exists() and str(fpath) != stored_path:
                            path_relocated = True
                else:
                    skipped_count += 1
                    continue

                if fpath and fpath.exists():
                    current_mtime = os.path.getmtime(fpath)
                    # 路径迁移即使 mtime 未变也要刷新 DB 中的 file_path。
                    if current_mtime <= stored_mtime and not path_relocated:
                        skipped_count += 1
                        continue
                else:
                    skipped_count += 1
                    continue
            else:
                new_count += 1

            # Qoder cache session 格式较简化，缺少完整 timing 数据。
            is_cache = str(fpath).startswith(str(QODER_DATA_DIR / "cache"))
            file_mtime = 0.0
            file_path_str = ""
            if fpath and fpath.exists():
                file_path_str = str(fpath)
                file_mtime = os.path.getmtime(fpath)

            if is_cache:
                summary, _msgs, _tcs, _sa = qoder_source.parse_session_detail(
                    project_key, sid, session_file=fpath
                )
            else:
                summary, _msgs, _tcs, _sa = qoder_source.parse_session_detail(
                    project_key, sid, session_file=fpath
                )
            summary.subagent_instance_count = len(_sa)

            upsert_session(conn, summary, file_mtime=file_mtime, file_path=file_path_str)
            _persist_normalized_artifact_safe(
                conn,
                session_key=summary.session_key,
                file_path=file_path_str,
                file_mtime=file_mtime,
                build_normalized=lambda: qoder_source.build_normalized_session(
                    summary=summary,
                    messages=_msgs,
                    tool_calls=_tcs,
                    subagent_runs=_sa,
                    source_path=file_path_str,
                ),
                verbose=verbose,
            )
            qoder_count += 1
            _commit_periodically(conn, qoder_count)

        conn.commit()

    # 说明：-- Normalize Qoder cache project keys (same as full_scan) -----------
    if scan_qoder:
        _normalize_qoder_cache_projects(conn)

    # 说明：Update log
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
