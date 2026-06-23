"""Scan local agent session files into the SQLite session index.

This module owns full and incremental scan lifecycles for Claude Code, Codex,
and Qoder.  The scanner locates source JSONL files, reuses fresh normalized
artifacts when possible, writes index rows, records scan logs, and normalizes
Qoder cache project keys after scan completion.
"""

from __future__ import annotations

import hashlib
import importlib
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from session_browser.domain.models import SessionSummary
from session_browser.index.schema import (
    _get_connection,
    ensure_session_artifacts_schema,
    init_schema,
)
from session_browser.index.writers import upsert_session
from session_browser.normalized.artifacts import (
    find_current_normalized_session_artifact,
    persist_current_normalized_session_artifact_reference,
    read_normalized_session_artifact,
)
from session_browser.normalized.java_bridge import ResultStatus
from session_browser.normalized.normalized_batch import (
    NormalizedBatchOutcome,
    NormalizedBatchRequest,
    execute_java_normalized_batch,
    map_source_id,
)
from session_browser.sources import claude as claude_source
from session_browser.sources import codex_session_source as codex_source
from session_browser.sources import qoder as qoder_source
from session_browser.sources.qoder_parts import discovery as qoder_discovery
from session_browser.sources.qoder_parts import model_config as qoder_model_config
from session_browser.sources.qoder_parts import parse as qoder_parse

if TYPE_CHECKING:
    import sqlite3
    from types import ModuleType
    from typing import Any

SCAN_COMMIT_EVERY = 25


def _runtime_config() -> ModuleType:
    """Return the currently loaded config module.

    Tests reload ``session_browser.config`` after changing data-directory
    environment variables.  Scanner helpers call this instead of holding a
    module reference captured at import time so each scan reads the active
    runtime configuration.

    Returns:
        Current ``session_browser.config`` module from ``sys.modules``.
    """
    return importlib.import_module("session_browser.config")


def _sync_source_data_dirs() -> ModuleType:
    """Refresh source module data directories after test or CLI config reloads.

    Index tests and command wrappers update environment variables and reload
    ``session_browser.config`` between scans.  Because this module imports
    source adapters at module load time to satisfy lint import rules, scan entry
    points call this helper before source discovery so adapters keep using the
    current configured directories.  It mutates only module-level directory
    constants.

    Returns:
        Current ``session_browser.config`` module used for the synchronization.
    """
    cfg = _runtime_config()
    claude_source.CLAUDE_DATA_DIR = cfg.CLAUDE_DATA_DIR
    codex_source.CODEX_DATA_DIR = cfg.CODEX_DATA_DIR
    qoder_source.QODER_DATA_DIR = cfg.QODER_DATA_DIR
    qoder_discovery.QODER_DATA_DIR = cfg.QODER_DATA_DIR
    qoder_model_config.QODER_DATA_DIR = cfg.QODER_DATA_DIR
    qoder_parse.QODER_DATA_DIR = cfg.QODER_DATA_DIR
    return cfg


def _commit_periodically(conn: sqlite3.Connection, count: int) -> None:
    """Commit batched scan writes after every configured number of rows.

    Full and incremental scan loops call this after each successful index
    upsert.  The helper has no return value; its side effect is a SQLite commit
    when ``count`` is a positive multiple of ``SCAN_COMMIT_EVERY``.

    Args:
        conn: SQLite connection used by the active scan.
        count: Number of rows written by the current scan loop.
    """
    if count > 0 and count % SCAN_COMMIT_EVERY == 0:
        conn.commit()


def _delete_indexed_sessions(
    conn: sqlite3.Connection,
    agent: str,
    session_ids: set[str] | list[str],
) -> int:
    """Delete stale indexed sessions that should no longer be listed.

    Incremental Codex scans call this when a previously indexed top-level
    session is later classified as a subagent thread.  It deletes artifact rows
    before session rows and returns the number of session rows removed; SQLite
    errors propagate to the scan caller.

    Args:
        conn: SQLite connection that owns the current index.
        agent: Agent prefix used to build ``session_key`` values.
        session_ids: Session IDs that should be removed from the top-level
            index.

    Returns:
        Number of deleted rows from the ``sessions`` table.
    """
    deleted = 0
    for sid in session_ids:
        session_key = f"{agent}:{sid}"
        conn.execute("DELETE FROM session_artifacts WHERE session_key = ?", (session_key,))
        cur = conn.execute("DELETE FROM sessions WHERE session_key = ?", (session_key,))
        if cur.rowcount and cur.rowcount > 0:
            deleted += cur.rowcount
    return deleted


# --- File location helpers ---------------------------------------------------


def _locate_claude_session_file(project_key: str, session_id: str) -> Path | None:
    """Locate a Claude Code source JSONL file for scan parsing.

    Full and incremental scans call this with a history entry's project key and
    session ID before parsing details.  It first checks the direct
    ``projects/<project_key>/<session_id>.jsonl`` path, then searches other
    project folders for continuation history; it returns ``None`` when no
    source file is available and does not mutate the index.

    Args:
        project_key: Claude project directory key from history.
        session_id: Claude session UUID to locate.

    Returns:
        Path to the JSONL source file, or ``None`` when it is absent.
    """
    cfg = _sync_source_data_dirs()
    projects_dir = cfg.CLAUDE_DATA_DIR / "projects"
    if not projects_dir.exists():
        return None

    # Prefer the project recorded by history.jsonl before scanning fallbacks.
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
    """Locate a Codex rollout JSONL file for a scan candidate.

    Codex scans use the thread database rollout path when available, then walk
    the dated sessions directory for ``rollout-*-<session_id>.jsonl``.  The
    function returns the first matching path or ``None`` and has no database
    side effects.

    Args:
        session_id: Codex thread ID to locate.
        rollout_path: Optional rollout path recorded in the threads database.

    Returns:
        Path to the rollout JSONL file, or ``None`` when no match is found.
    """
    if rollout_path:
        p = Path(rollout_path)
        if p.exists():
            return p

    cfg = _sync_source_data_dirs()
    sessions_dir = cfg.CODEX_DATA_DIR / "sessions"
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
    """Locate a Qoder source JSONL file across CLI and GUI storage.

    Incremental scans call this when a stored Qoder path disappeared.  It
    resolves short cache IDs through Qoder's canonical map, checks
    ``projects/`` for direct CLI sessions, then recursively searches
    ``cache/projects/`` for GUI sessions.  It returns ``None`` if the source
    file is not present and does not write to the index.

    Args:
        project_key: Qoder project key or cache project directory.
        session_id: Qoder session ID or short cache alias.

    Returns:
        Path to the Qoder JSONL source file, or ``None`` when not found.
    """
    cfg = _sync_source_data_dirs()
    uuid_pattern = re.compile(
        r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-"
        r"[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$",
    )

    # Step 1: resolve short ID alias to full UUID, then try projects/ directly.
    if not uuid_pattern.match(session_id):
        canonical_map = qoder_source._build_canonical_id_map()
        resolved_id = canonical_map.get(session_id.lower(), session_id)
        if resolved_id != session_id.lower():
            projects_dir = cfg.QODER_DATA_DIR / "projects"
            if projects_dir.exists():
                candidate = projects_dir / project_key / f"{resolved_id}.jsonl"
                if candidate.exists():
                    return candidate

    # Step 2: search projects/ by original session_id.
    projects_dir = cfg.QODER_DATA_DIR / "projects"
    if projects_dir.exists():
        candidate = projects_dir / project_key / f"{session_id}.jsonl"
        if candidate.exists():
            return candidate

    # Step 3: fall back to cache/projects/.
    cache_dir = cfg.QODER_DATA_DIR / "cache" / "projects"
    if cache_dir.exists():
        for root, _dirs, files in os.walk(cache_dir):
            if f"{session_id}.jsonl" in files:
                return Path(root) / f"{session_id}.jsonl"

    return None


def _summary_from_current_artifact(
    *,
    session_key: str,
    file_path: str,
    file_mtime: float,
    index_dir: Path | None,
) -> SessionSummary | None:
    """Build an index row from a current normalized artifact.

    Full and incremental scans call this before reparsing source JSONL.  It
    checks whether the normalized artifact matches the source path and mtime,
    reads that artifact if present, and returns a ``SessionSummary`` for
    ``upsert_session``.  Missing or unreadable artifacts return ``None`` so the
    caller can fall back to source parsing.

    Args:
        session_key: Stable ``agent:session_id`` key for artifact lookup.
        file_path: Source JSONL path recorded for the candidate session.
        file_mtime: Source file modification time used for freshness checks.
        index_dir: Directory containing the SQLite index and artifact store.

    Returns:
        Reconstructed summary, or ``None`` when reuse is unavailable.
    """
    artifact_path = find_current_normalized_session_artifact(
        session_key=session_key,
        source_path=file_path,
        source_mtime=file_mtime,
        index_dir=index_dir,
    )
    if artifact_path is None:
        return None
    try:
        normalized = read_normalized_session_artifact(artifact_path)
    except Exception:
        return None
    return _summary_from_normalized_artifact(normalized)


def _summary_from_normalized_artifact(
    normalized: dict[str, Any],
) -> SessionSummary | None:
    """Translate a normalized artifact payload back into index summary fields.

    Artifact reuse calls this after reading normalized JSON from disk.  It
    derives token counts, duration, project labels, and subagent counts from
    normalized calls plus the optional ``index_summary`` snapshot.  It returns
    ``None`` when mandatory agent or session identifiers are missing and does
    not mutate the normalized payload.

    Args:
        normalized: Normalized session artifact payload read from disk.

    Returns:
        Reconstructed session summary, or ``None`` for invalid payloads.
    """
    session = normalized.get("session") if isinstance(normalized.get("session"), dict) else {}
    index_summary = (
        normalized.get("index_summary") if isinstance(normalized.get("index_summary"), dict) else {}
    )
    agent = str(normalized.get("agent") or session.get("agent") or "")
    session_id = str(session.get("session_id") or "")
    if not agent or not session_id:
        return None
    calls = normalized.get("calls") if isinstance(normalized.get("calls"), list) else []
    tools = (
        normalized.get("tool_executions")
        if isinstance(normalized.get("tool_executions"), list)
        else []
    )
    usage_totals = {"fresh": 0, "cache_read": 0, "cache_write": 0, "output": 0, "total": 0}
    for call in calls:
        if not isinstance(call, dict):
            continue
        usage = call.get("usage") if isinstance(call.get("usage"), dict) else {}
        for key in usage_totals:
            usage_totals[key] += _int_or_zero(usage.get(key))

    started_at = str(session.get("started_at") or "")
    ended_at = str(session.get("ended_at") or "")
    duration_seconds = _duration_seconds(started_at, ended_at)
    subagent_ids = {
        str(call.get("subagent_id") or "")
        for call in calls
        if isinstance(call, dict) and str(call.get("scope") or "") == "subagent"
    }
    project_key = str(session.get("project_key") or session.get("cwd") or "")
    project_name = str(
        session.get("project_name") or (Path(project_key).name if project_key else ""),
    )
    return SessionSummary(
        agent=agent,
        session_id=session_id,
        title=str(index_summary.get("title") or session.get("title") or ""),
        project_key=project_key,
        project_name=project_name,
        cwd=str(session.get("cwd") or ""),
        started_at=started_at,
        ended_at=ended_at,
        duration_seconds=_float_or_zero(index_summary.get("duration_seconds")) or duration_seconds,
        model_execution_seconds=_float_or_zero(index_summary.get("model_execution_seconds")),
        tool_execution_seconds=_float_or_zero(index_summary.get("tool_execution_seconds")),
        model=str(session.get("model") or ""),
        git_branch=str(session.get("git_branch") or ""),
        source=str(session.get("source") or ""),
        user_message_count=_summary_count(
            index_summary,
            "user_message_count",
            max(1, len(calls)) if calls else 0,
        ),
        assistant_message_count=_summary_count(
            index_summary,
            "assistant_message_count",
            len(calls),
        ),
        tool_call_count=_summary_count(index_summary, "tool_call_count", len(tools)),
        output_tokens=_summary_count(index_summary, "output_tokens", usage_totals["output"]),
        fresh_input_tokens=_summary_count(
            index_summary,
            "fresh_input_tokens",
            usage_totals["fresh"],
        ),
        cache_read_tokens=_summary_count(
            index_summary,
            "cache_read_tokens",
            usage_totals["cache_read"],
        ),
        cache_write_tokens=_summary_count(
            index_summary,
            "cache_write_tokens",
            usage_totals["cache_write"],
        ),
        total_tokens=_summary_count(
            index_summary,
            "total_tokens",
            usage_totals["total"]
            or sum(usage_totals[k] for k in ("fresh", "cache_read", "cache_write", "output")),
        ),
        failed_tool_count=_summary_count(index_summary, "failed_tool_count", 0),
        subagent_instance_count=_summary_count(
            index_summary,
            "subagent_instance_count",
            len([sid for sid in subagent_ids if sid]),
        ),
    )


def _summary_payload(summary: SessionSummary) -> dict[str, Any]:
    """Serialize index-only fields into a normalized artifact.

    Normalized artifact persistence calls this after each source parse.  The
    returned dictionary preserves scan-time facts that are expensive or lossy to
    recompute from raw calls, such as final title and aggregate counters; it has
    no database side effects.

    Args:
        summary: Parsed session summary whose index-only fields should be
            stored with the normalized artifact.

    Returns:
        JSON-serializable mapping of summary fields for artifact reuse.
    """
    return {
        "title": summary.title,
        "duration_seconds": summary.duration_seconds,
        "model_execution_seconds": summary.model_execution_seconds,
        "tool_execution_seconds": summary.tool_execution_seconds,
        "user_message_count": summary.user_message_count,
        "assistant_message_count": summary.assistant_message_count,
        "tool_call_count": summary.tool_call_count,
        "output_tokens": summary.output_tokens,
        "fresh_input_tokens": summary.fresh_input_tokens,
        "cache_read_tokens": summary.cache_read_tokens,
        "cache_write_tokens": summary.cache_write_tokens,
        "total_tokens": summary.total_tokens,
        "failed_tool_count": summary.failed_tool_count,
        "subagent_instance_count": summary.subagent_instance_count,
    }


def _summary_count(index_summary: dict[str, Any], key: str, fallback: int) -> int:
    """Read an integer count from artifact metadata with scan fallback.

    Artifact reuse uses this for each aggregate counter in ``SessionSummary``.
    If ``key`` is absent, the caller-provided fallback is returned; malformed
    values are coerced to zero by ``_int_or_zero``.

    Args:
        index_summary: Optional summary mapping stored in a normalized artifact.
        key: Counter name to read.
        fallback: Value to return when the counter is absent.

    Returns:
        Integer counter value for the rebuilt index row.
    """
    if key in index_summary:
        return _int_or_zero(index_summary.get(key))
    return fallback


def _duration_seconds(started_at: str, ended_at: str) -> float:
    """Compute a non-negative scan duration from ISO timestamps.

    Normalized artifact reuse calls this when no stored duration is available.
    It accepts ``Z`` or offset ISO strings, returns seconds rounded to one
    decimal, and returns ``0`` for missing or invalid timestamps.

    Args:
        started_at: ISO timestamp for the first session event.
        ended_at: ISO timestamp for the final session event.

    Returns:
        Non-negative duration in seconds, or ``0`` when timestamps are invalid.
    """
    try:
        if not started_at or not ended_at:
            return 0
        start = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        end = datetime.fromisoformat(ended_at.replace("Z", "+00:00"))
        return max(0.0, round((end - start).total_seconds(), 1))
    except ValueError:
        return 0


def _int_or_zero(value: object) -> int:
    """Coerce a normalized numeric field to ``int`` for index counters.

    Scan summary construction uses this for token and message totals.  Missing
    or invalid values return ``0`` instead of raising so corrupt optional
    counters do not block artifact reuse.

    Args:
        value: Raw value read from normalized artifact metadata.

    Returns:
        Integer representation of ``value``, or ``0`` on failure.
    """
    try:
        if value is None:
            return 0
        return int(value)
    except (TypeError, ValueError):
        return 0


def _float_or_zero(value: object) -> float:
    """Coerce a normalized numeric field to ``float`` for timing metrics.

    Artifact reuse uses this for model and tool execution seconds.  Missing or
    invalid values return ``0`` and do not affect database state.

    Args:
        value: Raw value read from normalized artifact metadata.

    Returns:
        Floating point representation of ``value``, or ``0`` on failure.
    """
    try:
        if value is None:
            return 0
        return float(value)
    except (TypeError, ValueError):
        return 0


def _build_codex_normalized_for_scan(
    codex_source_module: ModuleType,
    summary: SessionSummary,
    thread_info: dict[str, Any],
    file_path: str,
) -> dict[str, Any]:
    """Build Codex normalized artifact only after reuse checks fail.

    Incremental Codex scans pass this as the artifact builder when a rollout has
    changed.  It merges thread metadata with the parsed summary, delegates to
    the Codex source parser, and backfills the session title when the normalized
    payload omitted one.  Parser exceptions propagate to the safe persistence
    wrapper, which logs and skips artifact persistence.

    Args:
        codex_source_module: Imported Codex source module that owns the parser.
        summary: Parsed session summary used to seed normalized metadata.
        thread_info: Threads database metadata for this Codex session.
        file_path: Rollout JSONL path to normalize.

    Returns:
        Normalized Codex session payload ready for artifact persistence.
    """
    normalized_thread_info = dict(thread_info or {})
    normalized_thread_info.setdefault("id", summary.session_id)
    normalized_thread_info.setdefault("title", summary.title)
    normalized_thread_info.setdefault("cwd", summary.cwd)
    normalized_thread_info.setdefault("git_branch", summary.git_branch)
    normalized_thread_info.setdefault("model", summary.model)
    normalized = codex_source_module.parse_normalized_session_file(
        file_path,
        thread_info=normalized_thread_info,
    )
    if normalized and summary.title and not (normalized.get("session") or {}).get("title"):
        normalized["session"]["title"] = summary.title[:160]
    return normalized


def _index_dir_from_connection(conn: sqlite3.Connection) -> Path | None:
    """Return the directory that contains the active SQLite main database.

    Artifact persistence calls this so normalized files can live beside the
    index database.  It inspects ``PRAGMA database_list`` and returns ``None``
    when the connection is in-memory or cannot be queried.

    Args:
        conn: SQLite connection whose main database path should be inspected.

    Returns:
        Parent directory of the main database file, or ``None`` when unknown.
    """
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


# --- Qoder cache project key normalization -----------------------------------


def _normalize_qoder_cache_projects(conn: sqlite3.Connection) -> None:
    """Fix Qoder cache session project keys after scan writes finish.

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
    the same repo is grouped under a single project; ambiguous matches are left
    unchanged and SQLite errors propagate to the scan caller.

    Args:
        conn: SQLite connection containing the sessions table to normalize.
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
            # Prefer project paths from agents that already have reliable cwd.
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


# --- Full scan batch post-processing ------------------------------------------


def _process_full_scan_batch_results(
    conn: sqlite3.Connection,
    outcome: NormalizedBatchOutcome,
    batch_context: dict[str, dict[str, Any]],
    index_dir: Path,
    verbose: bool,
) -> dict[str, int]:
    """处理 Java batch 结果，关联成功的 artifact 到 session_artifacts。

    遍历 Java batch 结果，对每个 WRITTEN 状态的结果：
    1. 验证 artifact 文件存在且可读
    2. 计算 size 和 content hash
    3. 调用 upsert_session_artifact 建立关联

    Java failure 不提供 Python fallback。FAILED/RETRYABLE 结果不写入 DB。

    Args:
        conn: SQLite connection。
        outcome: Java batch 执行结果。
        batch_context: request_id 到 session 元数据的映射。
        index_dir: artifact 存储根目录。
        verbose: 是否打印详细信息。

    Returns:
        统计 dict：associated、failed、retryable。
    """
    from session_browser.index.writers import upsert_session_artifact
    from session_browser.normalized.artifacts import NORMALIZED_SESSION_ARTIFACT_TYPE
    from session_browser.normalized.constants import NORMALIZED_SCHEMA_VERSION

    associated = 0
    failed = 0
    retryable = 0

    for result in outcome.results:
        ctx = batch_context.get(result.request_id)
        if ctx is None:
            continue

        if result.status == ResultStatus.WRITTEN and result.artifact_path:
            artifact_path = Path(result.artifact_path)
            if not artifact_path.exists():
                if verbose:
                    print(f"  Artifact missing after Java write: {result.artifact_path}")
                failed += 1
                continue

            try:
                size_bytes = artifact_path.stat().st_size
                raw = artifact_path.read_text(encoding='utf-8')
                content_hash = hashlib.sha256(raw.encode('utf-8')).hexdigest()
            except (OSError, UnicodeDecodeError) as exc:
                if verbose:
                    print(f"  Artifact read failed for {result.session_key}: {exc}")
                failed += 1
                continue

            upsert_session_artifact(
                conn,
                session_key=result.session_key,
                artifact_type=NORMALIZED_SESSION_ARTIFACT_TYPE,
                path=result.artifact_path,
                schema_version=NORMALIZED_SCHEMA_VERSION,
                source_path=ctx['file_path'],
                source_mtime=ctx['file_mtime'],
                size_bytes=size_bytes,
                content_hash=content_hash,
            )
            associated += 1
        elif result.status == ResultStatus.FAILED:
            if verbose:
                print(f"  Java failed for {result.session_key}: {result.error}")
            failed += 1
        elif result.status == ResultStatus.RETRYABLE:
            if verbose:
                print(f"  Java retryable for {result.session_key}: {result.error}")
            retryable += 1

    if associated > 0:
        conn.commit()

    return {'associated': associated, 'failed': failed, 'retryable': retryable}


# --- Shared scan helpers ------------------------------------------------------


def _collect_batch_request(
    batch_requests: list[NormalizedBatchRequest],
    batch_context: dict[str, dict[str, Any]],
    *,
    agent: str,
    session_key: str,
    file_path: str,
    file_mtime: float,
) -> None:
    """收集一条 Java batch 归一化请求。

    full/incremental scan 在每个 session upsert 后调用。
    只在 file_path 非空时追加请求。

    Args:
        batch_requests: 累积的请求列表（就地追加）。
        batch_context: request_id 到 session 元数据的映射（就地追加）。
        agent: agent 标识，用于 source_id 映射。
        session_key: canonical session key，同时作为 request_id。
        file_path: source JSONL 路径。
        file_mtime: source 文件修改时间。
    """
    if not file_path:
        return
    batch_requests.append(NormalizedBatchRequest(
        request_id=session_key,
        source_id=map_source_id(agent),
        root_path=file_path,
        session_key=session_key,
    ))
    batch_context[session_key] = {
        'file_path': file_path,
        'file_mtime': file_mtime,
    }


def _finalize_scan(
    conn: sqlite3.Connection,
    *,
    batch_requests: list[NormalizedBatchRequest],
    batch_context: dict[str, dict[str, Any]],
    index_dir: Path | None,
    scan_qoder: bool,
    log_id: int,
    claude_count: int,
    codex_count: int,
    qoder_count: int,
    verbose: bool,
) -> None:
    """执行 batch、规范化 Qoder 项目 key、更新 scan log。

    full_scan 和 incremental_scan 在各自 agent 循环结束后调用。

    Args:
        conn: SQLite connection。
        batch_requests: 收集的归一化请求。
        batch_context: request_id 到 session 元数据的映射。
        index_dir: artifact 存储根目录。
        scan_qoder: 是否需要 Qoder 项目 key 规范化。
        log_id: scan_log 行 id。
        claude_count: Claude session 计数。
        codex_count: Codex session 计数。
        qoder_count: Qoder session 计数。
        verbose: 是否打印详细信息。
    """
    # Java batch: 单个 JVM 处理本轮所有归一化请求。
    if batch_requests and index_dir is not None:
        try:
            outcome = execute_java_normalized_batch(
                batch_requests,
                output_dir=index_dir,
            )
            _process_full_scan_batch_results(
                conn, outcome, batch_context, index_dir, verbose,
            )
        except Exception as exc:
            # Java failure: 无 Python writer fallback。
            if verbose:
                print(f"  Java batch failed: {exc}")

    # Normalize Qoder cache project keys after all agent scans.
    if scan_qoder:
        _normalize_qoder_cache_projects(conn)

    # Update scan log.
    conn.execute(
        "UPDATE scan_log SET finished_at=?, claude_count=?, codex_count=?, "
        "qoder_count=?, status='done' WHERE id=?",
        (time.time(), claude_count, codex_count, qoder_count, log_id),
    )
    conn.commit()


# --- Full scan ----------------------------------------------------------------


def full_scan(  # noqa: PLR0912, PLR0915 - Public scan lifecycle coordinates all agents.
    conn: sqlite3.Connection | None = None,
    verbose: bool = False,
    agent: str | None = None,
) -> dict[str, int]:
    """Run the full source discovery and index rebuild lifecycle.

    CLI and application startup flows call this when the index needs to inspect
    every configured agent source.  It initializes schema, records a running
    scan log, discovers Claude Code, Codex, and Qoder sessions subject to the
    optional agent filter, upserts session rows, persists normalized artifacts,
    normalizes Qoder cache project keys, and marks the scan log done.

    Args:
        conn: SQLite connection. If None, creates a new one.
        verbose: Print progress messages.
        agent: If provided, only scan this agent.

    Returns:
        Counts for each agent and the total number of indexed sessions.
    """
    cfg = _sync_source_data_dirs()
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
    index_dir = _index_dir_from_connection(conn)

    scan_claude = agent is None or agent == "claude_code"
    scan_codex = agent is None or agent == "codex"
    scan_qoder = agent is None or agent == "qoder"

    # Java batch 收集：full scan 使用单个 JVM 处理所有 normalized artifact 生产。
    batch_requests: list[NormalizedBatchRequest] = []
    batch_context: dict[str, dict[str, Any]] = {}

    # Scan Claude Code.
    if scan_claude:
        if verbose:
            print("Scanning Claude Code...")
        # Pre-load history to build session-to-project mapping.
        history = claude_source.parse_history()
        # history.jsonl can contain repeated continuations; keep the latest.
        seen = {}
        for entry in history:
            seen[entry["session_id"]] = entry
        unique_history = list(seen.values())

        for entry in unique_history:
            sid = entry["session_id"]
            project = entry["project"]
            file_mtime = 0.0
            file_path = ""
            fpath = _locate_claude_session_file(project, sid)
            if fpath and fpath.exists():
                file_path = str(fpath)
                file_mtime = fpath.stat().st_mtime

            cached_summary = (
                _summary_from_current_artifact(
                    session_key=f"claude_code:{sid}",
                    file_path=file_path,
                    file_mtime=file_mtime,
                    index_dir=index_dir,
                )
                if file_path
                else None
            )
            if cached_summary is not None:
                if not cached_summary.title and entry.get("display"):
                    cached_summary.title = claude_source._extract_readable_title(entry["display"])
                upsert_session(conn, cached_summary, file_mtime=file_mtime, file_path=file_path)
                persist_current_normalized_session_artifact_reference(
                    conn,
                    session_key=cached_summary.session_key,
                    source_path=file_path,
                    source_mtime=file_mtime,
                    index_dir=index_dir,
                )
                claude_count += 1
                _commit_periodically(conn, claude_count)
                if verbose and claude_count % 50 == 0:
                    print(f"  Claude: {claude_count} sessions")
                continue

            summary, _msgs, _tcs, _sa = claude_source.parse_session_detail(
                project, sid, history_entry=entry, verbose=verbose
            )
            summary.subagent_instance_count = len(_sa)
            if not summary.title and entry.get("display"):
                summary.title = claude_source._extract_readable_title(entry["display"])

            # Skip sessions with no valid timestamps, such as non-dict JSON events.
            if not summary.ended_at:
                if verbose:
                    print(f"  Skipping {sid}: no valid ended_at timestamp")
                continue

            upsert_session(conn, summary, file_mtime=file_mtime, file_path=file_path)
            # full scan 不再使用 Python persist，改为收集 batch 请求交给 Java。
            _collect_batch_request(
                batch_requests,
                batch_context,
                agent='claude_code',
                session_key=summary.session_key,
                file_path=file_path,
                file_mtime=file_mtime,
            )
            claude_count += 1
            _commit_periodically(conn, claude_count)
            if verbose and claude_count % 50 == 0:
                print(f"  Claude: {claude_count} sessions")

        conn.commit()

    # Scan Codex after preloading the threads DB once.
    if scan_codex:
        if verbose:
            print("Scanning Codex...")
        codex_source.clear_codex_subagent_index_cache()
        threads_db = codex_source.read_threads_db()
        index_entries = {e["id"]: e for e in codex_source.parse_session_index()}
        subagent_ids = {
            sid
            for sid, info in threads_db.items()
            if codex_source.is_codex_subagent_thread_info(info)
        }
        codex_ids = [sid for sid in threads_db if sid not in subagent_ids]
        codex_ids.extend(sid for sid in index_entries if sid not in threads_db)
        for sid in codex_ids:
            if sid in threads_db:
                parse_threads_db = threads_db
                thread_info = threads_db.get(sid, {})
                fallback_file = None
            else:
                fallback_file = _locate_codex_session_file(sid, "")
                if codex_source.is_codex_subagent_session_file(fallback_file):
                    if verbose:
                        print(f"  Skipping Codex subagent thread {sid}")
                    continue
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

            fpath = fallback_file or _locate_codex_session_file(
                sid,
                thread_info.get("rollout_path", ""),
            )
            file_mtime = 0.0
            file_path = ""
            if fpath and fpath.exists():
                file_path = str(fpath)
                file_mtime = fpath.stat().st_mtime
            cached_summary = (
                _summary_from_current_artifact(
                    session_key=f"codex:{sid}",
                    file_path=file_path,
                    file_mtime=file_mtime,
                    index_dir=index_dir,
                )
                if file_path
                else None
            )
            if cached_summary is not None:
                if not cached_summary.title:
                    idx_entry = index_entries.get(sid)
                    if idx_entry and idx_entry.get("thread_name"):
                        cached_summary.title = idx_entry["thread_name"][:120]
                    elif thread_info.get("first_user_message"):
                        cached_summary.title = thread_info["first_user_message"][:120]
                upsert_session(conn, cached_summary, file_mtime=file_mtime, file_path=file_path)
                persist_current_normalized_session_artifact_reference(
                    conn,
                    session_key=cached_summary.session_key,
                    source_path=file_path,
                    source_mtime=file_mtime,
                    index_dir=index_dir,
                )
                codex_count += 1
                _commit_periodically(conn, codex_count)
                if verbose and codex_count % 50 == 0:
                    print(f"  Codex: {codex_count} sessions")
                continue

            summary, _msgs, _tcs, _sa, normalized, session_file = (
                codex_source.parse_session_detail_with_normalized(
                    sid,
                    parse_threads_db,
                    verbose=verbose,
                )
            )
            # Enrich empty titles from the session index, matching scan_all_sessions.
            if not summary.title:
                idx_entry = index_entries.get(sid)
                if idx_entry and idx_entry.get("thread_name"):
                    summary.title = idx_entry["thread_name"][:120]
                elif thread_info.get("first_user_message"):
                    summary.title = thread_info["first_user_message"][:120]
            # Skip sessions with no valid timestamps.
            if not summary.ended_at:
                if verbose:
                    print(f"  Skipping {summary.session_id}: no valid ended_at timestamp")
                continue

            # Store file mtime and path for future incremental scans.
            fpath = session_file or (Path(summary.file_path) if summary.file_path else fpath)
            if fpath and fpath.exists():
                file_path = str(fpath)
                file_mtime = fpath.stat().st_mtime

            upsert_session(conn, summary, file_mtime=file_mtime, file_path=file_path)
            # full scan 不再使用 Python persist，改为收集 batch 请求交给 Java。
            _collect_batch_request(
                batch_requests,
                batch_context,
                agent='codex',
                session_key=summary.session_key,
                file_path=file_path,
                file_mtime=file_mtime,
            )
            codex_count += 1
            _commit_periodically(conn, codex_count)
            if verbose and codex_count % 50 == 0:
                print(f"  Codex: {codex_count} sessions")

        conn.commit()

    # Scan Qoder from projects/ and cache/projects/.
    if scan_qoder:
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
            file_mtime = fpath.stat().st_mtime if fpath.exists() else 0.0
            file_path = str(fpath) if fpath and fpath.exists() else ""
            cached_summary = (
                _summary_from_current_artifact(
                    session_key=f"qoder:{sid}",
                    file_path=file_path,
                    file_mtime=file_mtime,
                    index_dir=index_dir,
                )
                if file_path
                else None
            )
            if cached_summary is not None:
                upsert_session(conn, cached_summary, file_mtime=file_mtime, file_path=file_path)
                persist_current_normalized_session_artifact_reference(
                    conn,
                    session_key=cached_summary.session_key,
                    source_path=file_path,
                    source_mtime=file_mtime,
                    index_dir=index_dir,
                )
                qoder_count += 1
                _commit_periodically(conn, qoder_count)
                if verbose and qoder_count % 50 == 0:
                    print(f"  Qoder: {qoder_count} sessions")
                continue

            is_cache = str(fpath).startswith(str(cfg.QODER_DATA_DIR / "cache"))
            summary, _msgs, _tcs, _sa = qoder_source.parse_session_detail(
                project_key, sid, session_file=fpath, verbose=verbose
            )
            summary.subagent_instance_count = len(_sa)
            if is_cache:
                summary.file_path = str(fpath)

            # Skip sessions with no valid timestamps.
            if not summary.ended_at:
                if verbose:
                    print(f"  Skipping {summary.session_id}: no valid ended_at timestamp")
                continue

            upsert_session(conn, summary, file_mtime=file_mtime, file_path=file_path)
            # full scan 不再使用 Python persist，改为收集 batch 请求交给 Java。
            _collect_batch_request(
                batch_requests,
                batch_context,
                agent='qoder',
                session_key=summary.session_key,
                file_path=file_path,
                file_mtime=file_mtime,
            )
            qoder_count += 1
            _commit_periodically(conn, qoder_count)
            if verbose and qoder_count % 50 == 0:
                print(f"  Qoder: {qoder_count} sessions")

        conn.commit()

    _finalize_scan(
        conn,
        batch_requests=batch_requests,
        batch_context=batch_context,
        index_dir=index_dir,
        scan_qoder=scan_qoder,
        log_id=log_id,
        claude_count=claude_count,
        codex_count=codex_count,
        qoder_count=qoder_count,
        verbose=verbose,
    )

    return {
        "claude_count": claude_count,
        "codex_count": codex_count,
        "qoder_count": qoder_count,
        "total": claude_count + codex_count + qoder_count,
    }


# --- Incremental scan ---------------------------------------------------------


def incremental_scan(  # noqa: PLR0912, PLR0915 - Incremental scan must coordinate all agent stores.
    conn: sqlite3.Connection | None = None,
    verbose: bool = False,
    agent: str | None = None,
    max_age_seconds: float | None = None,
) -> dict[str, int]:
    """Scan only sessions whose source files changed since the last index.

    CLI refresh flows call this for routine updates.  It compares stored file
    mtimes and paths against Claude Code, Codex, and Qoder sources, skips rows
    outside the optional age window, reparses changed or newly discovered
    sessions, prunes Codex subagent rows, writes normalized artifacts, and
    closes the scan log with per-agent counters.

    Args:
        conn: SQLite connection.
        verbose: Print progress messages.
        agent: If provided, only scan this agent.
        max_age_seconds: If set, only scan sessions whose ended_at is within
            this many seconds from now. Sessions older than this are skipped.

    Returns:
        Counts for updated sessions, new sessions, skipped sessions, and pruned
        Codex subagent rows.
    """
    cfg = _sync_source_data_dirs()
    if conn is None:
        conn = _get_connection()

    ensure_session_artifacts_schema(conn)
    conn.commit()

    log_id = conn.execute(
        "INSERT INTO scan_log (started_at, mode, status) VALUES (?, 'incremental', 'running')",
        (time.time(),),
    ).lastrowid
    conn.commit()

    cutoff_iso = None
    if max_age_seconds is not None:
        cutoff_dt = datetime.now(timezone.utc) - timedelta(seconds=max_age_seconds)
        cutoff_iso = cutoff_dt.isoformat()

    # Load existing sessions keyed by session_key for mtime and age decisions.
    existing: dict[str, dict[str, Any]] = {}
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

    claude_count = 0
    codex_count = 0
    qoder_count = 0
    new_count = 0
    skipped_count = 0
    pruned_subagent_count = 0
    index_dir = _index_dir_from_connection(conn)

    # Java batch 收集：incremental scan 只收集 changed candidates，
    # 一个 JVM 处理本轮所有 normalized artifact 生产。
    batch_requests: list[NormalizedBatchRequest] = []
    batch_context: dict[str, dict[str, Any]] = {}

    scan_claude = agent is None or agent == "claude_code"
    scan_codex = agent is None or agent == "codex"
    scan_qoder = agent is None or agent == "qoder"

    # -- Scan Claude Code --------------------------------------------------
    if scan_claude:
        history = claude_source.parse_history()
        # history.jsonl can contain repeated continuations; keep the latest.
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

            # Existing sessions outside the age window are not reparsed.
            info = existing.get(skey)
            if info:
                ended_at = info["ended_at"] or ""
                if cutoff_iso and ended_at < cutoff_iso:
                    skipped_count += 1
                    continue

                # Relocate missing source paths so moved files can refresh.
                stored_mtime = info["file_mtime"]
                stored_path = info["file_path"]
                path_relocated = False
                if stored_path:
                    fpath = Path(stored_path)
                    if fpath.exists():
                        current_mtime = fpath.stat().st_mtime
                        if current_mtime <= stored_mtime:
                            skipped_count += 1
                            continue
                    else:
                        # Relocate deleted paths by project and session ID.
                        fpath = _locate_claude_session_file(project, sid)
                        if fpath and fpath.exists() and str(fpath) != stored_path:
                            path_relocated = True
                else:
                    skipped_count += 1
                    continue

                if fpath and fpath.exists():
                    current_mtime = fpath.stat().st_mtime
                    # Path relocation rewrites file_path even if mtime is unchanged.
                    if current_mtime <= stored_mtime and not path_relocated:
                        skipped_count += 1
                        continue
                else:
                    # Missing sources are skipped to avoid overwriting valid paths.
                    skipped_count += 1
                    continue
            else:
                new_count += 1

            # Only new, changed, or relocated sessions need source parsing.
            summary, _msgs, _tcs, _sa = claude_source.parse_session_detail(
                project, sid, history_entry=entry
            )
            summary.subagent_instance_count = len(_sa)
            if not summary.title and entry.get("display"):
                summary.title = claude_source._extract_readable_title(entry["display"])

            # Store source path and mtime for the next incremental scan.
            file_mtime = 0.0
            file_path_str = ""
            fpath = _locate_claude_session_file(project, sid)
            if fpath and fpath.exists():
                file_path_str = str(fpath)
                file_mtime = fpath.stat().st_mtime

            upsert_session(conn, summary, file_mtime=file_mtime, file_path=file_path_str)
            # incremental scan 不再使用 Python persist，改为收集 batch 请求交给 Java。
            _collect_batch_request(
                batch_requests,
                batch_context,
                agent='claude_code',
                session_key=summary.session_key,
                file_path=file_path_str,
                file_mtime=file_mtime,
            )
            claude_count += 1
            _commit_periodically(conn, claude_count)

        conn.commit()

    # -- Scan Codex --------------------------------------------------------
    if scan_codex:
        codex_source.clear_codex_subagent_index_cache()
        threads_db = codex_source.read_threads_db()
        # Fall back to session_index.jsonl when threads DB is incomplete.
        index_entries = {e["id"]: e for e in codex_source.parse_session_index()}

        subagent_ids = {
            sid
            for sid, info in threads_db.items()
            if codex_source.is_codex_subagent_thread_info(info)
        }
        pruned = _delete_indexed_sessions(conn, "codex", subagent_ids)
        if pruned:
            pruned_subagent_count += pruned
            conn.commit()

        all_ids = [sid for sid in threads_db if sid not in subagent_ids]
        all_ids.extend(sid for sid in index_entries if sid not in threads_db)
        if verbose:
            print(f"Incremental scan: {len(all_ids)} Codex sessions...")

        for sid in all_ids:
            skey = f"codex:{sid}"
            info = existing.get(skey)

            if sid not in threads_db:
                stored_path = (info or {}).get("file_path", "")
                fallback_file = (
                    Path(stored_path)
                    if stored_path and Path(stored_path).exists()
                    else _locate_codex_session_file(sid, "")
                )
                if codex_source.is_codex_subagent_session_file(fallback_file):
                    pruned_subagent_count += _delete_indexed_sessions(conn, "codex", [sid])
                    skipped_count += 1
                    continue

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
                        current_mtime = fpath.stat().st_mtime
                        if current_mtime <= stored_mtime:
                            skipped_count += 1
                            continue
                    else:
                        # Relocate moved rollouts with the threads DB path hint.
                        thread_info = threads_db.get(sid, {})
                        rollout_path = thread_info.get("rollout_path", "")
                        fpath = _locate_codex_session_file(sid, rollout_path)
                        if fpath and fpath.exists() and str(fpath) != stored_path:
                            path_relocated = True
                else:
                    skipped_count += 1
                    continue

                if fpath and fpath.exists():
                    current_mtime = fpath.stat().st_mtime
                    # Path relocation refreshes file_path even if mtime is unchanged.
                    if current_mtime <= stored_mtime and not path_relocated:
                        skipped_count += 1
                        continue
                else:
                    skipped_count += 1
                    continue
            else:
                new_count += 1

            # One rollout read produces the summary and normalized JSON inputs.
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
            summary, _msgs, _tcs, _sa = codex_source.parse_session_detail(
                sid,
                parse_threads_db,
            )
            # Enrich empty titles from the session index.
            if not summary.title:
                idx_entry = index_entries.get(sid)
                if idx_entry and idx_entry.get("thread_name"):
                    summary.title = idx_entry["thread_name"][:120]
                elif thread_info.get("first_user_message"):
                    summary.title = thread_info["first_user_message"][:120]

            # Store file info for the next incremental scan.
            file_mtime = 0.0
            file_path_str = ""
            fpath = Path(summary.file_path) if summary.file_path else None
            if fpath and fpath.exists():
                file_path_str = str(fpath)
                file_mtime = fpath.stat().st_mtime

            upsert_session(conn, summary, file_mtime=file_mtime, file_path=file_path_str)
            # incremental scan 不再使用 Python persist，改为收集 batch 请求交给 Java。
            _collect_batch_request(
                batch_requests,
                batch_context,
                agent='codex',
                session_key=summary.session_key,
                file_path=file_path_str,
                file_mtime=file_mtime,
            )
            codex_count += 1
            _commit_periodically(conn, codex_count)

        conn.commit()

    # -- Scan Qoder --------------------------------------------------------
    if scan_qoder:
        discovered = qoder_source._discover_sessions()
        cache_discovered = qoder_source._discover_cache_sessions()
        # Cache can expose short IDs; map them to canonical UUIDs before dedupe.
        canonical_map = qoder_source._build_canonical_id_map()
        # Skip cache duplicates when projects/ already has the full session.
        projects_ids = {sid.lower() for _pk, sid, _fp in discovered}
        all_discovered = []
        for project_key, sid, fpath in discovered:
            all_discovered.append((project_key, sid, fpath))
        for project_key, sid, fpath in cache_discovered:
            canonical_id = canonical_map.get(sid.lower(), sid)
            # Skip cache sessions that resolve to a projects/ session.
            if canonical_id != sid.lower() and canonical_id in projects_ids:
                continue
            all_discovered.append((project_key, canonical_id, fpath))
        if verbose:
            print(f"Incremental scan: {len(all_discovered)} Qoder sessions...")

        for project_key, sid, source_file in all_discovered:
            skey = f"qoder:{sid}"
            active_file = source_file

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
                        current_mtime = p.stat().st_mtime
                        if current_mtime <= stored_mtime:
                            skipped_count += 1
                            continue
                    else:
                        # Relocate missing paths so cache migrations refresh.
                        relocated_path = _locate_qoder_session_file(project_key, sid)
                        if (
                            relocated_path
                            and relocated_path.exists()
                            and str(relocated_path) != stored_path
                        ):
                            active_file = relocated_path
                            path_relocated = True
                else:
                    skipped_count += 1
                    continue

                if active_file and active_file.exists():
                    current_mtime = active_file.stat().st_mtime
                    # Path relocation refreshes file_path even if mtime is unchanged.
                    if current_mtime <= stored_mtime and not path_relocated:
                        skipped_count += 1
                        continue
                else:
                    skipped_count += 1
                    continue
            else:
                new_count += 1

            # Qoder cache sessions have simplified timing data.
            file_mtime = 0.0
            file_path_str = ""
            if active_file and active_file.exists():
                file_path_str = str(active_file)
                file_mtime = active_file.stat().st_mtime

            summary, _msgs, _tcs, _sa = qoder_source.parse_session_detail(
                project_key, sid, session_file=active_file
            )
            summary.subagent_instance_count = len(_sa)

            upsert_session(conn, summary, file_mtime=file_mtime, file_path=file_path_str)
            # incremental scan 不再使用 Python persist，改为收集 batch 请求交给 Java。
            _collect_batch_request(
                batch_requests,
                batch_context,
                agent='qoder',
                session_key=summary.session_key,
                file_path=file_path_str,
                file_mtime=file_mtime,
            )
            qoder_count += 1
            _commit_periodically(conn, qoder_count)

        conn.commit()

    _finalize_scan(
        conn,
        batch_requests=batch_requests,
        batch_context=batch_context,
        index_dir=index_dir,
        scan_qoder=scan_qoder,
        log_id=log_id,
        claude_count=claude_count,
        codex_count=codex_count,
        qoder_count=qoder_count,
        verbose=verbose,
    )

    return {
        "claude_count": claude_count,
        "codex_count": codex_count,
        "qoder_count": qoder_count,
        "total": claude_count + codex_count + qoder_count,
        "new_count": new_count,
        "skipped": skipped_count,
        "pruned_subagents": pruned_subagent_count,
    }
