"""会话索引写入函数。"""

from __future__ import annotations

import sqlite3
import time

from session_browser.domain.models import SessionSummary
from session_browser.domain.normalizer import sanitize_list_title


def upsert_session(
    conn: sqlite3.Connection,
    summary: SessionSummary,
    file_mtime: float = 0,
    file_path: str = "",
) -> None:
    """写入或更新一条会话索引记录。"""
    conn.execute(
        """
        INSERT INTO sessions (
            session_key, agent, session_id, title, project_key, project_name,
            cwd, started_at, ended_at, duration_seconds, model_execution_seconds,
            tool_execution_seconds,
            model, git_branch, source, user_message_count, assistant_message_count,
            tool_call_count, output_tokens, fresh_input_tokens, cache_read_tokens,
            cache_write_tokens, total_tokens, failed_tool_count, subagent_instance_count, indexed_at,
            file_mtime, file_path
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            file_mtime,
            file_path,
        ),
    )


def upsert_session_artifact(
    conn: sqlite3.Connection,
    *,
    session_key: str,
    artifact_type: str,
    path: str,
    schema_version: str = "",
    source_path: str = "",
    source_mtime: float = 0,
    size_bytes: int = 0,
) -> None:
    """Insert or update a generated artifact associated with one session."""
    now = time.time()
    conn.execute(
        """
        INSERT INTO session_artifacts (
            session_key, artifact_type, path, schema_version, source_path,
            source_mtime, size_bytes, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(session_key, artifact_type) DO UPDATE SET
            path=excluded.path,
            schema_version=excluded.schema_version,
            source_path=excluded.source_path,
            source_mtime=excluded.source_mtime,
            size_bytes=excluded.size_bytes,
            created_at=session_artifacts.created_at,
            updated_at=excluded.updated_at
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
        ),
    )


def _row_to_summary(row: sqlite3.Row, truncate_title: bool = False) -> SessionSummary:
    """把当前 schema 的 DB 行转换为 SessionSummary。"""
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
        output_tokens=row["output_tokens"],
        fresh_input_tokens=row["fresh_input_tokens"],
        cache_read_tokens=row["cache_read_tokens"],
        cache_write_tokens=row["cache_write_tokens"],
        total_tokens=row["total_tokens"],
        failed_tool_count=row["failed_tool_count"],
        subagent_instance_count=row["subagent_instance_count"],
        file_path=row["file_path"],
    )
