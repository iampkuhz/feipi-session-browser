"""SQLite 行转换与 artifact 关联（半写路径）。

查询代码使用本模块将 SQLite 行转换为领域对象。
scan 写路径已退休，由 Java scan 接管。
artifact 关联仍由 attribution 代码使用。
"""

from __future__ import annotations

import sqlite3
import time

from session_browser.domain.models import SessionSummary
from session_browser.domain.normalizer import sanitize_list_title


def _row_to_summary(row: sqlite3.Row, truncate_title: bool = False) -> SessionSummary:
    """将 SQLite 会话行转换为 SessionSummary。

    查询辅助函数在读取行后调用此函数。
    可选的截断标志保留列表视图的标题行为。

    Args:
        row: sessions 表的 SQLite 行。
        truncate_title: 是否对列表显示进行标题清理。

    Returns:
        从行列填充的 SessionSummary。
    """
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


def upsert_session_artifact(  # noqa: PLR0913
    conn: sqlite3.Connection,
    *,
    session_key: str,
    artifact_type: str,
    path: str,
    schema_version: str = "",
    source_path: str = "",
    source_mtime: float = 0,
    size_bytes: int = 0,
    content_hash: str = "",
    validation_status: str = "",
) -> None:
    """插入或更新一个会话的 artifact 记录。

    Attribution artifact 生成流在创建派生文件后调用此函数。
    scan 会话写路径（upsert_session）已退休，此函数仅用于 artifact 关联。

    Args:
        conn: 已打开的 SQLite 连接。
        session_key: 拥有此 artifact 的会话标识。
        artifact_type: artifact 类别。
        path: artifact 文件路径。
        schema_version: 可选的 schema 版本。
        source_path: 可选的源文件路径。
        source_mtime: 可选的源文件修改时间。
        size_bytes: 可选的 artifact 大小。
        content_hash: 可选的 artifact 内容 SHA-256。
        validation_status: 可选的验证状态。
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
