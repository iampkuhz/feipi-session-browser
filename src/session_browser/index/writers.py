"""Write and read SQLite rows for the session index.

Index scan code uses this module to upsert session summaries and generated
artifact records. Query code reuses ``_row_to_summary`` to convert SQLite rows
back into the domain summary shape without changing persistence semantics.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from session_browser.domain.models import SessionSummary
from session_browser.domain.normalizer import sanitize_list_title

if TYPE_CHECKING:
    import sqlite3


def upsert_session(
    conn: sqlite3.Connection,
    summary: SessionSummary,
    file_mtime: float = 0,
    file_path: str = "",
) -> None:
    """Insert or update one session summary row in the index.

    Full and incremental scans call this writer after normalizing a source
    session. It preserves the existing ``session_key`` conflict behavior and
    updates file metadata and ``indexed_at`` on every write.

    Args:
        conn: Open SQLite connection for the session index.
        summary: Normalized session summary to persist.
        file_mtime: Source file modification time associated with the row.
        file_path: Source file path associated with the row.
    """
    conn.execute(
        """
        INSERT INTO sessions (
            session_key, agent, session_id, title, project_key, project_name,
            cwd, started_at, ended_at, duration_seconds, model_execution_seconds,
            tool_execution_seconds,
            model, git_branch, source, user_message_count, assistant_message_count,
            tool_call_count, output_tokens, fresh_input_tokens, cache_read_tokens,
            cache_write_tokens, total_tokens, failed_tool_count,
            subagent_instance_count, indexed_at, file_mtime, file_path
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?
        )
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
    """Insert or update a generated artifact record for one session.

    Artifact generation flows call this writer after creating derived files. The
    keyword-only field list mirrors the artifact table columns, so keeping the
    explicit API avoids changing existing callers while preserving upsert
    semantics. ``content_hash`` 和 ``validation_status`` 为新增可选字段，
    用于记录 artifact 内容校验值和验证状态。

    Args:
        conn: Open SQLite connection for the session index.
        session_key: Stable key of the session that owns the artifact.
        artifact_type: Artifact category stored in the composite primary key.
        path: Stored artifact path.
        schema_version: Optional schema version associated with the artifact.
        source_path: Optional source path used to generate the artifact.
        source_mtime: Optional source modification time used for freshness.
        size_bytes: Optional artifact size in bytes.
        content_hash: 可选的 artifact 内容 SHA-256。
        validation_status: 可选的验证状态标记（ok/stale/corrupt/missing）。
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


# ---------------------------------------------------------------------------
# Artifact association: 只关联经过验证的成功结果
# ---------------------------------------------------------------------------

# 允许关联到 session_artifacts 的 bridge result status。
# 只有 verified WRITTEN/UNCHANGED artifact 才可以关联。
_ASSOCIABLE_STATUSES: frozenset[str] = frozenset({'WRITTEN', 'UNCHANGED'})


def associate_verified_artifact(
    conn: sqlite3.Connection,
    *,
    session_key: str,
    artifact_type: str,
    path: str,
    schema_version: str = '',
    source_path: str = '',
    source_mtime: float = 0,
    size_bytes: int = 0,
    content_hash: str = '',
    bridge_status: str = '',
) -> bool:
    """将经过验证的 bridge 成功结果关联到 session_artifacts。

    只有 ``bridge_status`` 为 WRITTEN 或 UNCHANGED 时才执行关联。
    FAILED/RETRYABLE/PROTOCOL_FATAL 不会写入 DB，也不会删除已有的有效行。
    多次调用同一成功结果不改变最终状态（幂等）。

    Args:
        conn: 已打开的 SQLite 连接。
        session_key: 会话的稳定标识。
        artifact_type: artifact 类别。
        path: artifact 文件路径。
        schema_version: normalized schema 版本。
        source_path: 源 transcript 路径。
        source_mtime: 源文件修改时间。
        size_bytes: artifact 文件大小。
        content_hash: artifact 内容 SHA-256。
        bridge_status: Java bridge 返回的状态字符串。

    Returns:
        True 表示已执行关联，False 表示 bridge_status 不可关联。
    """
    if bridge_status not in _ASSOCIABLE_STATUSES:
        return False
    upsert_session_artifact(
        conn,
        session_key=session_key,
        artifact_type=artifact_type,
        path=path,
        schema_version=schema_version,
        source_path=source_path,
        source_mtime=source_mtime,
        size_bytes=size_bytes,
        content_hash=content_hash,
        validation_status='ok',
    )
    return True


def associate_batch_results(
    conn: sqlite3.Connection,
    results: list,
    *,
    artifact_type: str = 'normalized_session_json',
) -> dict[str, int]:
    """批量关联 Java bridge 返回的成功结果。

    遍历 results，只对状态为 WRITTEN 或 UNCHANGED 的行执行关联。
    失败的结果不写入 DB 也不删除有效行。事务由调用方控制。

    Args:
        conn: 已打开的 SQLite 连接。
        results: ``BatchResult`` 对象列表（有 status/session_key/artifact_path 属性）。
        artifact_type: artifact 类别标识。

    Returns:
        统计 dict：associated、skipped 分别为关联和跳过的数量。
    """
    associated = 0
    skipped = 0
    for result in results:
        status_value = result.status.value if hasattr(result.status, 'value') else str(result.status)
        ok = associate_verified_artifact(
            conn,
            session_key=result.session_key,
            artifact_type=artifact_type,
            path=result.artifact_path,
            content_hash=result.content_hash,
            bridge_status=status_value,
        )
        if ok:
            associated += 1
        else:
            skipped += 1
    return {'associated': associated, 'skipped': skipped}


# ---------------------------------------------------------------------------
# 幂等 repair：修复 DB ↔ artifact 不一致
# ---------------------------------------------------------------------------

# validation_status 合法取值集合。
_VALID_STATUSES: frozenset[str] = frozenset({'ok', 'stale', 'corrupt', 'missing', ''})


def validate_artifact_row(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
) -> str:
    """检查单条 session_artifacts 行的 artifact 完整性。

    依次检查文件存在性、可读性、size 一致性和 content hash。
    不修改任何 DB 状态，只返回推导出的 validation_status。

    Args:
        conn: 已打开的 SQLite 连接（未使用，保留以便扩展）。
        row: session_artifacts 表的一行记录。

    Returns:
        推导出的验证状态：ok、missing、corrupt 或 stale。
    """
    import hashlib
    import json

    from pathlib import Path as _Path

    artifact_path = _Path(row['path'])
    if not artifact_path.exists():
        return 'missing'

    # 读取内容
    try:
        raw = artifact_path.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError):
        return 'corrupt'

    if not raw.strip():
        return 'corrupt'

    # 验证 JSON 可解析
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return 'corrupt'

    if not isinstance(data, dict):
        return 'corrupt'

    # 验证 size
    actual_size = artifact_path.stat().st_size
    recorded_size = int(row['size_bytes'] or 0)
    if recorded_size != actual_size:
        return 'corrupt'

    # 验证 content hash（仅在 DB 已记录 hash 时检查）
    recorded_hash = str(row['content_hash'] or '')
    if recorded_hash:
        actual_hash = hashlib.sha256(raw.encode('utf-8')).hexdigest()
        if recorded_hash != actual_hash:
            return 'corrupt'

    return 'ok'


def repair_artifact_associations(
    conn: sqlite3.Connection,
    *,
    session_keys: set[str] | None = None,
    artifact_type: str = 'normalized_session_json',
) -> dict[str, int]:
    """幂等修复 artifact 关联。

    对每条 session_artifacts 行验证 artifact 完整性：
    - 文件存在且完整 → 确保 validation_status = 'ok'
    - 文件缺失 → 删除 DB 行（下次 scan 重建）
    - 文件损坏 → 标记为 corrupt 并删除行（下次 scan 重建）

    重复调用不改变正确结果：已 ok 的行不变，缺失/损坏的行删除后
    再次调用时已无该行可处理。DB failure 不会删除磁盘上有效的 artifact。

    Args:
        conn: 已打开的 SQLite 连接。
        session_keys: 可选的 session_key 集合，限制 repair 范围。
            None 时修复所有指定 artifact_type 的行。
        artifact_type: 要修复的 artifact 类别。

    Returns:
        统计 dict：repaired（标记为 ok）、removed（删除的行）。
    """
    if session_keys is not None and not session_keys:
        return {'repaired': 0, 'removed': 0}

    if session_keys is not None:
        placeholders = ','.join('?' * len(session_keys))
        rows = conn.execute(
            f'SELECT * FROM session_artifacts '
            f'WHERE artifact_type = ? AND session_key IN ({placeholders})',
            [artifact_type, *session_keys],
        ).fetchall()
    else:
        rows = conn.execute(
            'SELECT * FROM session_artifacts WHERE artifact_type = ?',
            (artifact_type,),
        ).fetchall()

    repaired = 0
    removed = 0

    for row in rows:
        status = validate_artifact_row(conn, row)

        if status == 'ok':
            # 确保 validation_status 已更新为 ok
            if row['validation_status'] != 'ok':
                conn.execute(
                    "UPDATE session_artifacts SET validation_status = 'ok', "
                    "updated_at = ? WHERE session_key = ? AND artifact_type = ?",
                    (time.time(), row['session_key'], artifact_type),
                )
                repaired += 1
        else:
            # 文件缺失或损坏 → 删除行，下次 scan 会重建
            # 不删除磁盘上的 artifact 文件（可能部分损坏但还有用）
            conn.execute(
                "DELETE FROM session_artifacts "
                "WHERE session_key = ? AND artifact_type = ?",
                (row['session_key'], artifact_type),
            )
            removed += 1

    return {'repaired': repaired, 'removed': removed}


def safe_upsert_after_bridge(
    conn: sqlite3.Connection,
    *,
    session_key: str,
    artifact_type: str,
    path: str,
    schema_version: str = '',
    source_path: str = '',
    source_mtime: float = 0,
    size_bytes: int = 0,
    content_hash: str = '',
) -> None:
    """Bridge 输出循环中的安全关联：事务失败不删除有效 artifact。

    本函数只执行 upsert，不执行 DELETE。当 DB commit 失败时，
    artifact 文件仍然存在于磁盘上，下次 scan 的 repair 路径会
    幂等恢复关联。调用方在循环中逐条调用并在循环外 commit。

    Args:
        conn: 已打开的 SQLite 连接。
        session_key: 会话标识。
        artifact_type: artifact 类别。
        path: artifact 路径。
        schema_version: schema 版本。
        source_path: 源文件路径。
        source_mtime: 源文件修改时间。
        size_bytes: 文件大小。
        content_hash: 内容 hash。
    """
    upsert_session_artifact(
        conn,
        session_key=session_key,
        artifact_type=artifact_type,
        path=path,
        schema_version=schema_version,
        source_path=source_path,
        source_mtime=source_mtime,
        size_bytes=size_bytes,
        content_hash=content_hash,
        validation_status='ok',
    )


def _row_to_summary(row: sqlite3.Row, truncate_title: bool = False) -> SessionSummary:
    """Convert one SQLite session row into a ``SessionSummary`` object.

    Query helpers call this after reading rows from the current schema. The
    optional truncation flag preserves list-view title behavior while leaving the
    stored row untouched.

    Args:
        row: SQLite row from the ``sessions`` table.
        truncate_title: Whether to sanitize the title for list display.

    Returns:
        Domain ``SessionSummary`` populated from the row columns.
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
