"""Record Claude hook events and changed-file evidence.

PostToolUse write hooks call this module after Write, Edit, MultiEdit, or NotebookEdit
operations. It writes JSONL evidence with file hashes, sizes, classification metadata,
and active change ids. Failures are intentionally best-effort so evidence collection
cannot corrupt user work or block unrelated hook events.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from .active_change import current_change_id
from .classify import classify_file
from .paths import ensure_runtime_dirs, rel_to_repo

if TYPE_CHECKING:
    from pathlib import Path

    from .hook_io import HookContext
    from .paths import RepoPaths


# 01. 时间与 JSONL 基础函数
def utc_now() -> str:
    """Return an ISO-8601 UTC timestamp for hook evidence records.

    Returns:
        Current UTC timestamp as an ISO-8601 string.
    """
    return datetime.now(timezone.utc).isoformat()


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    """Append one JSON object to a hook evidence JSONL file.

    Args:
        path: Destination JSONL file.
        record: Serializable hook evidence record.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8') as f:
        f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + '\n')


# 02. 文件摘要
def file_sha256(path: Path) -> str | None:
    """Calculate the SHA-256 digest of a changed file after a write hook.

    Args:
        path: File path to hash.

    Returns:
        Hex digest for an existing regular file, or ``None`` when the file is absent or
        unreadable. Returning ``None`` preserves hook failure semantics as non-blocking
        evidence collection.
    """
    try:
        if not path.exists() or not path.is_file():
            return None
        h = hashlib.sha256()
        with path.open('rb') as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b''):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None


def file_size(path: Path) -> int | None:
    """Return the post-write file size for hook evidence.

    Args:
        path: File path to inspect.

    Returns:
        File size in bytes, or ``None`` if the file is absent or cannot be statted.
    """
    try:
        return path.stat().st_size if path.exists() else None
    except Exception:
        return None


# 03. Hook 事件记录
def record_hook_event(
    paths: RepoPaths,
    ctx: HookContext,
    status: str = 'OBSERVED',
    extra: dict[str, Any] | None = None,
) -> None:
    """Record a Claude hook lifecycle event.

    Args:
        paths: Repository runtime paths used for JSONL destinations.
        ctx: Parsed Claude hook stdin context.
        status: Hook decision or observation status, such as ``PASS`` or ``BLOCK``.
        extra: Optional event fields supplied by a policy evaluator.
    """
    ensure_runtime_dirs(paths)
    record = {
        'schemaVersion': 1,
        'ts': utc_now(),
        'event': ctx.event_name,
        'hookEventName': ctx.hook_event_name,
        'toolName': ctx.tool_name,
        'toolUseId': ctx.tool_use_id,
        'sessionId': ctx.session_id,
        'agentId': ctx.agent_id,
        'agentType': ctx.agent_type,
        'status': status,
        'parseError': ctx.parse_error,
    }
    if extra:
        record.update(extra)
    append_jsonl(paths.hook_events, record)


# 04. 变更 evidence 记录
def record_changed_file(paths: RepoPaths, ctx: HookContext, file_path: str) -> dict[str, Any]:
    """Record one changed file after a write hook completes.

    Args:
        paths: Repository runtime paths used for JSONL destinations.
        ctx: Parsed Claude hook stdin context for the write event.
        file_path: File path reported by the write tool input.

    Returns:
        JSON-serializable evidence record appended to changed-files and task evidence.
    """
    ensure_runtime_dirs(paths)
    rel = rel_to_repo(file_path, paths.repo_root)
    cls = classify_file(rel)
    absolute = paths.repo_root / cls.file
    change_id = current_change_id(paths)
    record = {
        'schemaVersion': 1,
        'ts': utc_now(),
        'event': ctx.event_name,
        'toolName': ctx.tool_name,
        'toolUseId': ctx.tool_use_id,
        'sessionId': ctx.session_id,
        'agentId': ctx.agent_id,
        'agentType': ctx.agent_type,
        'changeId': change_id,
        'file': cls.file,
        'category': cls.category,
        'requiresQualityGate': cls.requires_quality_gate,
        'qualityTarget': cls.quality_target,
        'riskLevel': cls.risk_level,
        'allowedByDefault': cls.allowed_by_default,
        'sha256After': file_sha256(absolute),
        'sizeAfter': file_size(absolute),
    }
    append_jsonl(paths.changed_files, record)
    append_jsonl(paths.task_evidence_dir / f'{change_id}.jsonl', record)
    return record


# 05. PostToolUse 批量记录
def record_post_write(paths: RepoPaths, ctx: HookContext) -> list[dict[str, Any]]:
    """Record all candidate files from a post-write Claude hook event.

    Args:
        paths: Repository runtime paths used for JSONL destinations.
        ctx: Parsed Claude hook stdin context for Write, Edit, MultiEdit, or NotebookEdit.

    Returns:
        Evidence records for each unique candidate path. An empty list is valid when the
        hook input has no file path.
    """
    records: list[dict[str, Any]] = []
    for file_path in ctx.candidate_paths:
        records.append(record_changed_file(paths, ctx, file_path))
    record_hook_event(paths, ctx, status='RECORDED', extra={'changedFileCount': len(records)})
    return records


# 06. 读取 changed-files
def read_changed_files(paths: RepoPaths) -> list[dict[str, Any]]:
    """Read changed-file evidence for stop-hook quality inference.

    Args:
        paths: Repository runtime paths that locate ``changed-files.jsonl``.

    Returns:
        Parsed evidence records. Malformed lines are ignored by returning records parsed
        so far, because stop-hook prompting should degrade gracefully on corrupt JSONL.
    """
    result: list[dict[str, Any]] = []
    try:
        if not paths.changed_files.exists():
            return []
        for line in paths.changed_files.read_text(encoding='utf-8').splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            if isinstance(item, dict):
                result.append(item)
    except Exception:
        return result
    return result
