"""提供 evidence 脚本能力。"""

from __future__ import annotations

import hashlib
import json
import fcntl
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .active_change import current_change_id
from .classify import classify_file
from .paths import RepoPaths, build_paths, ensure_runtime_dirs, rel_to_repo
from scripts.quality import changed_files as changed_file_utils

if TYPE_CHECKING:
    from .hook_io import HookContext


# 01. 时间与 JSONL 基础函数
BASH_MUTATION_LOCK_STALE_SECONDS = 2 * 60 * 60


# 返回当前 UTC timestamp。
def utc_now() -> str:
    """返回：
        当前 UTC timestamp as ISO-8601 字符串。
    """
    return datetime.now(timezone.utc).isoformat()


# 追加 JSONL 记录并避免重复事件。
def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    """参数：
        path: JSONL 文件路径。
        record: 待追加的事件记录。

    返回：
        无返回值。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + '.lock')
    event_id = record.get('eventId')
    with lock_path.open('a+', encoding='utf-8') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            if event_id and path.exists():
                try:
                    for line in path.read_text(encoding='utf-8').splitlines():
                        if not line.strip():
                            continue
                        item = json.loads(line)
                        if isinstance(item, dict) and item.get('eventId') == event_id:
                            return
                except Exception:
                    pass
            with path.open('a', encoding='utf-8') as f:
                f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + '\n')
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


# 计算 hook 事件的稳定 id。
def event_id_for(paths: RepoPaths, ctx: HookContext, event: str | None = None) -> str:
    """参数：
        paths: 当前仓库路径上下文。
        ctx: 当前 hook 输入上下文。
        event: 可选事件名称。

    返回：
        SHA-256 事件 id。
    """
    raw = '|'.join([
        paths.identity.client,
        ctx.session_id or paths.identity.raw_session_id,
        paths.identity.raw_run_id,
        ctx.turn_id or paths.identity.raw_turn_id,
        ctx.tool_use_id,
        event or ctx.event_name,
    ])
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


# 构造运行期 evidence 通用字段。
def runtime_fields(paths: RepoPaths, ctx: HookContext, event: str | None = None) -> dict[str, Any]:
    """参数：
        paths: 当前仓库路径上下文。
        ctx: 当前 hook 输入上下文。
        event: 可选事件名称。

    返回：
        运行期 evidence 字段映射。
    """
    identity = paths.identity
    return {
        'runId': identity.raw_run_id,
        'taskId': identity.raw_task_id,
        'worktreeId': identity.raw_worktree_id,
        'checkoutRootHash': identity.checkout_root_hash,
        'branch': identity.branch,
        'baseCommit': identity.base_commit,
        'turnId': ctx.turn_id or identity.raw_turn_id,
        'changeId': identity.change_id or current_change_id(paths),
        'eventId': event_id_for(paths, ctx, event),
        'identityWarnings': list(identity.identity_warnings),
    }


# 维护文件 SHA-256。
def file_sha256(path: Path) -> str | None:
    """参数：
        path: 文件路径到hash。

    返回：
        file sha256 字符串。
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


# 维护文件 大小。
def file_size(path: Path) -> int | None:
    """参数：
        path: 文件路径以检查。

    返回：
        文件 size in bytes, 或 ``None`` 如果 文件 缺失 或 cannot be statted。
    """
    try:
        return path.stat().st_size if path.exists() else None
    except Exception:
        return None


# 维护Bash snapshot key。
def _bash_snapshot_key(ctx: HookContext, client: str = '') -> str | None:
    """参数：
        ctx: ctx 参数。
        client: client 参数。

    返回：
        bash snapshot key 字符串。
    """
    identity_parts = [
        client or ctx.agent_client,
        ctx.session_id,
        ctx.run_id,
        ctx.agent_id,
        ctx.tool_use_id,
    ]
    raw_key = '|'.join(part for part in identity_parts if part)
    if not raw_key:
        raw_key = '|'.join(
            part for part in [client or ctx.agent_client, ctx.session_id, ctx.agent_id, ctx.command]
            if part
        )
    if not raw_key:
        return None
    return hashlib.sha256(raw_key.encode('utf-8')).hexdigest()


# 维护Bash snapshot 路径。
def _bash_snapshot_path(paths: RepoPaths, ctx: HookContext) -> Path | None:
    """参数：
        paths: 待检查的路径列表。
        ctx: ctx 参数。

    返回：
        解析后的 HookContext；失败时携带 parse_error。
    """
    key = _bash_snapshot_key(ctx, paths.identity.client)
    if not key:
        return None
    return paths.agent_log_dir / 'bash-snapshots' / f'{key}.json'


# 判断前置 Bash 事件是否说明缺失 snapshot 不是 mutation attribution gap。
def pre_bash_exempts_missing_snapshot(event: dict[str, Any] | None) -> bool:
    """参数：
        event: 匹配同一 toolUseId 的 pre-bash 事件。

    返回：
        当前 post-bash 缺少 snapshot 但不应 fail-closed 时返回 true。
    """
    if not event:
        return False
    return event.get('status') == 'BLOCK' or event.get('bashMutationTracking') is False


# 查找同一 Bash 工具调用的前置 hook 记录。
def _matching_pre_bash_event(paths: RepoPaths, ctx: HookContext) -> dict[str, Any] | None:
    """参数：
        paths: 仓库运行时路径集合。
        ctx: 当前后置 Bash hook 上下文。

    返回：
        最近一条匹配同一 toolUseId 的前置 Bash 事件；找不到则返回 None。
    """
    if not ctx.tool_use_id or not paths.hook_events.exists():
        return None
    try:
        lines = paths.hook_events.read_text(encoding='utf-8').splitlines()
    except OSError:
        return None
    for raw_line in reversed(lines):
        if not raw_line.strip():
            continue
        try:
            event = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get('toolUseId') != ctx.tool_use_id:
            continue
        if event.get('event') != 'pre-bash':
            continue
        return event
    return None

# 查找同一 Bash 工具调用已经记录过的后置 hook 记录。
def _matching_post_bash_event(paths: RepoPaths, ctx: HookContext) -> dict[str, Any] | None:
    """参数：
        paths: 仓库运行时路径集合。
        ctx: 当前后置 Bash hook 上下文。

    返回：
        最近一条匹配同一 toolUseId 的 post-bash 事件；找不到则返回 None。
    """
    if not ctx.tool_use_id or not paths.hook_events.exists():
        return None
    try:
        lines = paths.hook_events.read_text(encoding='utf-8').splitlines()
    except OSError:
        return None
    for raw_line in reversed(lines):
        if not raw_line.strip():
            continue
        try:
            event = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get('toolUseId') != ctx.tool_use_id:
            continue
        if event.get('event') != 'post-bash':
            continue
        return event
    return None

# 维护Bash 锁 路径。
def _bash_lock_path(paths: RepoPaths) -> Path:
    """参数：
        paths: 待检查的路径列表。

    返回：
        解析后的 HookContext；失败时携带 parse_error。
    """
    # 工作区级锁：同一个工作区的所有 agent 共享 Git 脏差异，
    # 因此同一时刻只允许一个变更 Bash 命令拍摄前后快照。
    if paths.identity.has_run:
        return paths.repo_root / 'tmp' / 'agent_logs' / paths.identity.client / paths.identity.session_id / 'runs' / paths.identity.run_id / 'writer' / 'bash-mutation.lock'
    return paths.repo_root / 'tmp' / 'agent_logs' / 'bash-mutation.lock'


# 维护Bash 锁 owner。
def _bash_lock_owner(paths: RepoPaths, ctx: HookContext) -> str | None:
    """参数：
        paths: 待检查的路径列表。
        ctx: ctx 参数。

    返回：
        bash lock owner 字符串。
    """
    return _bash_snapshot_key(ctx, paths.identity.client)


# 判断 Bash 锁 owner 进程是否已经退出。
def _bash_lock_owner_process_dead(path: Path) -> bool:
    """参数：
        path: Bash 变更锁文件路径。

    返回：
        锁文件记录的 owner 进程明确不存在时返回 true。
    """
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return False
    if not isinstance(data, dict):
        return False
    pid = data.get('pid')
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    except (PermissionError, OSError):
        return False
    return False


# 移除过期或 owner 进程已退出的 Bash 锁。
def _remove_stale_bash_lock(path: Path) -> None:
    """参数：
        path: 待检查的路径。
    """
    try:
        age = time.time() - path.stat().st_mtime
    except FileNotFoundError:
        return
    except OSError:
        return
    if age <= BASH_MUTATION_LOCK_STALE_SECONDS and not _bash_lock_owner_process_dead(path):
        return
    try:
        path.unlink()
    except OSError:
        pass


# 读取 Bash 变更锁详情。
def read_bash_mutation_lock_info(paths: RepoPaths) -> dict[str, Any] | None:
    """参数：
        paths: 仓库路径集合。

    返回：
        变更锁详情字典，包含锁持有者、时间和年龄等信息；无法读取时返回 None。
    """
    lock_path = _bash_lock_path(paths)
    try:
        raw = json.loads(lock_path.read_text(encoding='utf-8'))
        stat = lock_path.stat()
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    if not isinstance(raw, dict):
        return None
    raw = dict(raw)
    raw['age_seconds'] = max(0.0, time.time() - stat.st_mtime)
    return raw


# 获取Bash mutation 锁。
def acquire_bash_mutation_lock(paths: RepoPaths, ctx: HookContext) -> bool:
    """参数：
        paths: 待检查的路径列表。
        ctx: ctx 参数。

    返回：
        满足条件时返回 true，否则返回 false。
    """
    owner = _bash_lock_owner(paths, ctx)
    if not owner:
        return False
    lock_path = _bash_lock_path(paths)
    _remove_stale_bash_lock(lock_path)
    payload = {
        'schemaVersion': 1,
        'ts': utc_now(),
        'owner': owner,
        'sessionId': ctx.session_id,
        'agentId': ctx.agent_id,
        'agentType': ctx.agent_type,
        'toolUseId': ctx.tool_use_id,
        'client': paths.identity.client,
        'runId': paths.identity.raw_run_id,
        'taskId': paths.identity.raw_task_id,
        'worktreeId': paths.identity.raw_worktree_id,
        'pid': os.getpid(),
    }
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False
    except OSError:
        return False
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + '\n')
    return True


# 释放Bash mutation 锁。
def release_bash_mutation_lock(paths: RepoPaths, ctx: HookContext) -> None:
    """参数：
        paths: 待检查的路径列表。
        ctx: ctx 参数。
    """
    owner = _bash_lock_owner(paths, ctx)
    if not owner:
        return
    lock_path = _bash_lock_path(paths)
    try:
        data = json.loads(lock_path.read_text(encoding='utf-8'))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return
    if not isinstance(data, dict) or data.get('owner') != owner:
        return
    try:
        lock_path.unlink()
    except OSError:
        pass


# 维护Git head。
def _git_head(paths: RepoPaths) -> str | None:
    """参数：
        paths: 待检查的路径列表。

    返回：
        git head 字符串。
    """
    try:
        proc = subprocess.run(
            ['git', 'rev-parse', 'HEAD'],
            cwd=paths.repo_root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=30,
            check=False,
        )
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    value = (proc.stdout or '').strip()
    return value or None


# 维护Git diff 路径。
def _git_diff_paths(paths: RepoPaths, before: str, after: str) -> list[str]:
    """参数：
        paths: 待检查的路径列表。
        before: 之前 参数。
        after: 之后 参数。

    返回：
        结果列表。
    """
    try:
        proc = subprocess.run(
            ['git', 'diff', '--name-only', '--diff-filter=ACMRD', before, after],
            cwd=paths.repo_root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=30,
            check=False,
        )
    except Exception:
        return []
    if proc.returncode != 0:
        return []
    return changed_file_utils.dedupe_paths(
        [line for line in (proc.stdout or '').splitlines() if line.strip()]
    )


# 维护dirty state。
def _dirty_state(paths: RepoPaths) -> dict[str, dict[str, Any]]:
    """参数：
        paths: 待检查的路径列表。

    返回：
        结果映射。
    """
    result: dict[str, dict[str, Any]] = {}
    runtime_rel = rel_to_repo(paths.agent_log_dir, paths.repo_root)
    for rel in changed_file_utils.read_git_dirty_files(paths.repo_root):
        if rel == runtime_rel or rel.startswith(f'{runtime_rel}/'):
            continue
        absolute = paths.repo_root / rel
        result[rel] = {
            'exists': absolute.exists(),
            'sha256': file_sha256(absolute),
            'size': file_size(absolute),
        }
    return result


# 记录pre Bash snapshot。
def record_pre_bash_snapshot(paths: RepoPaths, ctx: HookContext) -> bool:
    """参数：
        paths: 待检查的路径列表。
        ctx: ctx 参数。

    返回：
        满足条件时返回 true，否则返回 false。
    """
    ensure_runtime_dirs(paths)
    snapshot_path = _bash_snapshot_path(paths, ctx)
    if snapshot_path is None:
        return False
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        'schemaVersion': 1,
        'ts': utc_now(),
        'client': paths.identity.client,
        'sessionId': ctx.session_id,
        'agentId': ctx.agent_id,
        'agentType': ctx.agent_type,
        'toolUseId': ctx.tool_use_id,
        'head': _git_head(paths),
        'dirty': _dirty_state(paths),
        **runtime_fields(paths, ctx, 'pre-bash-snapshot'),
    }
    snapshot_path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True),
        encoding='utf-8',
    )
    return True


# 记录post Bash。
def record_post_bash(paths: RepoPaths, ctx: HookContext) -> list[dict[str, Any]]:
    """参数：
        paths: 待检查的路径列表。
        ctx: ctx 参数。

    返回：
        结果列表。
    """
    ensure_runtime_dirs(paths)
    try:
        snapshot_path = _bash_snapshot_path(paths, ctx)
        if snapshot_path is None or not snapshot_path.exists():
            if _matching_post_bash_event(paths, ctx):
                return []
            pre_event = _matching_pre_bash_event(paths, ctx)
            if pre_bash_exempts_missing_snapshot(pre_event):
                record_hook_event(
                    paths,
                    ctx,
                    status='OBSERVED',
                    extra={
                        'changedFileCount': 0,
                        'mutationSource': 'bash',
                        'bashMutationTracking': False,
                        'preStatus': pre_event.get('status'),
                    },
                )
                return []
            record_hook_event(
                paths,
                ctx,
                status='BASH_SNAPSHOT_MISSING',
                extra={
                    'mutationSource': 'bash',
                    'bashMutationTracking': True,
                    'bashSnapshotRequired': True,
                    'preStatus': pre_event.get('status') if pre_event else None,
                },
            )
            return []

        try:
            before = json.loads(snapshot_path.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, OSError):
            before = {}

        before_dirty = before.get('dirty') if isinstance(before, dict) else {}
        if not isinstance(before_dirty, dict):
            before_dirty = {}
        after_dirty = _dirty_state(paths)

        changed: list[str] = []
        for rel in sorted(set(before_dirty) | set(after_dirty)):
            if before_dirty.get(rel) != after_dirty.get(rel):
                changed.append(rel)

        head_before = before.get('head') if isinstance(before, dict) else None
        head_after = _git_head(paths)
        if isinstance(head_before, str) and head_before and head_after and head_before != head_after:
            changed.extend(_git_diff_paths(paths, head_before, head_after))

        records = [
            record_changed_file(paths, ctx, rel)
            for rel in changed_file_utils.dedupe_paths(changed)
        ]
        record_hook_event(
            paths,
            ctx,
            status='RECORDED',
            extra={'changedFileCount': len(records), 'mutationSource': 'bash'},
        )
        try:
            snapshot_path.unlink()
        except OSError:
            pass
        return records
    finally:
        release_bash_mutation_lock(paths, ctx)


# 记录hook event。
def record_hook_event(
    paths: RepoPaths,
    ctx: HookContext,
    status: str = 'OBSERVED',
    extra: dict[str, Any] | None = None,
) -> None:
    """参数：
        paths: Repository 运行time 路径 used用于JSONL destinations。
        ctx: 已解析的Claude hook stdin context。
        status: hook decision 或 observation 状态，例如 ``PASS`` 或 ``BLOCK``。
        extra: extra 参数。
    """
    ensure_runtime_dirs(paths)
    record = {
        'schemaVersion': 1,
        'ts': utc_now(),
        'client': paths.identity.client,
        'event': ctx.event_name,
        'hookEventName': ctx.hook_event_name,
        'toolName': ctx.tool_name,
        'toolUseId': ctx.tool_use_id,
        'sessionId': ctx.session_id,
        'agentId': ctx.agent_id,
        'agentType': ctx.agent_type,
        'status': status,
        'parseError': ctx.parse_error,
        **runtime_fields(paths, ctx, f'hook-event:{ctx.event_name}:{status}'),
    }
    if extra:
        record.update(extra)
    append_jsonl(paths.hook_events, record)


# 记录changed-files 文件。
def record_changed_file(paths: RepoPaths, ctx: HookContext, file_path: str) -> dict[str, Any]:
    """参数：
        paths: Repository 运行time 路径 used用于JSONL destinations。
        ctx: ctx 参数。
        file_path: 文件路径 reported by 写入 tool 输入。

    返回：
        结果映射。
    """
    ensure_runtime_dirs(paths)
    rel = rel_to_repo(file_path, paths.repo_root)
    cls = classify_file(rel)
    absolute = paths.repo_root / cls.file
    change_id = paths.identity.change_id or current_change_id(paths)
    record = {
        'schemaVersion': 1,
        'ts': utc_now(),
        'client': paths.identity.client,
        'event': ctx.event_name,
        'toolName': ctx.tool_name,
        'toolUseId': ctx.tool_use_id,
        'sessionId': ctx.session_id,
        'agentId': ctx.agent_id,
        'agentType': ctx.agent_type,
        **runtime_fields(paths, ctx, f'changed-file:{cls.file}'),
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


# 记录post write。
def record_post_write(paths: RepoPaths, ctx: HookContext) -> list[dict[str, Any]]:
    """参数：
        paths: Repository 运行time 路径 used用于JSONL destinations。
        ctx: 已解析的Claude hook stdin context用于Write, Edit, MultiEdit, 或 NotebookEdit。

    返回：
        evidence record用于each 去重后的 candidate 路径. 空 列表 is 有效 当 the。 hook 输入 has no 文件路径。
    """
    records: list[dict[str, Any]] = []
    for file_path in ctx.candidate_paths:
        records.append(record_changed_file(paths, ctx, file_path))
    record_hook_event(paths, ctx, status='RECORDED', extra={'changedFileCount': len(records)})
    return records


# 读取changed-files 文件。
def read_changed_files(paths: RepoPaths) -> list[dict[str, Any]]:
    """参数：
        paths: Repository 运行time 路径 that locate ``changed-文件.jsonl``。

    返回：
        结果列表。
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
