"""持久化 Hook 事件、文件变更与 Bash mutation 归因证据。

本模块只写入 ``paths.RepoPaths`` 指定的运行目录，不选择 Gate、不更新
Registry，也不负责平台 payload 解析。"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from scripts.agent_runtime.context import current_change_id
from scripts.agent_runtime.paths import RepoPaths, build_paths, ensure_runtime_dirs, rel_to_repo
from scripts.gates.planner import classify_path

if TYPE_CHECKING:
    from scripts.agent_runtime.context import HookContext


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
    raw = '|'.join(
        [
            paths.identity.client,
            ctx.session_id or paths.identity.raw_session_id,
            paths.identity.raw_run_id,
            ctx.turn_id or paths.identity.raw_turn_id,
            ctx.tool_use_id,
            event or ctx.event_name,
        ]
    )
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
            part
            for part in [client or ctx.agent_client, ctx.session_id, ctx.agent_id, ctx.command]
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
        return (
            paths.repo_root
            / 'tmp'
            / 'agent_logs'
            / paths.identity.client
            / paths.identity.session_id
            / 'runs'
            / paths.identity.run_id
            / 'writer'
            / 'bash-mutation.lock'
        )
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
    return dedupe_paths([line for line in (proc.stdout or '').splitlines() if line.strip()])


# 维护dirty state。
def _dirty_state(paths: RepoPaths) -> dict[str, dict[str, Any]]:
    """参数：
        paths: 待检查的路径列表。

    返回：
        结果映射。
    """
    result: dict[str, dict[str, Any]] = {}
    runtime_rel = rel_to_repo(paths.agent_log_dir, paths.repo_root)
    for rel in read_git_dirty_files(paths.repo_root):
        if rel == runtime_rel or rel.startswith(f'{runtime_rel}/'):
            continue
        absolute = paths.repo_root / rel
        result[rel] = {
            'exists': absolute.exists(),
            'sha256': file_sha256(absolute),
            'size': file_size(absolute),
        }
    return result


def checkout_content_fingerprint(repo_root: Path) -> str | None:
    """计算 checkout 的提交、索引、工作区和未跟踪内容指纹，失败时关闭失败。"""
    try:
        # 延迟导入避免 Stop evidence 在模块初始化时反向导入本模块。
        from scripts.agent_runtime.stop.evidence import checkout_content_snapshot

        return str(checkout_content_snapshot(repo_root).get('fingerprint') or '') or None
    except Exception:
        return None


# 记录pre Bash snapshot。
def record_pre_bash_snapshot(
    paths: RepoPaths,
    ctx: HookContext,
    *,
    primary_root: Path | None = None,
    controlled_primary_write: bool = False,
) -> bool:
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
    primary_fingerprint = None
    if primary_root is not None:
        primary_fingerprint = checkout_content_fingerprint(primary_root)
        if not primary_fingerprint:
            return False
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
        'primaryRoot': str(primary_root.resolve()) if primary_root is not None else '',
        'primaryFingerprint': primary_fingerprint,
        'controlledPrimaryWrite': controlled_primary_write,
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
        if (
            isinstance(head_before, str)
            and head_before
            and head_after
            and head_before != head_after
        ):
            changed.extend(_git_diff_paths(paths, head_before, head_after))

        records = [record_changed_file(paths, ctx, rel) for rel in dedupe_paths(changed)]
        primary_before = str(before.get('primaryFingerprint') or '')
        primary_root_raw = str(before.get('primaryRoot') or '')
        primary_after = (
            checkout_content_fingerprint(Path(primary_root_raw)) if primary_root_raw else None
        )
        primary_changed = bool(primary_before and primary_after and primary_before != primary_after)
        primary_unavailable = bool(primary_root_raw and not primary_after)
        controlled = before.get('controlledPrimaryWrite') is True
        status = 'RECORDED'
        if primary_changed and not controlled:
            status = 'PRIMARY_FINGERPRINT_CHANGED'
        elif primary_unavailable:
            status = 'PRIMARY_FINGERPRINT_UNAVAILABLE'
        record_hook_event(
            paths,
            ctx,
            status=status,
            extra={
                'changedFileCount': len(records),
                'mutationSource': 'bash',
                'primaryFingerprintBefore': primary_before or None,
                'primaryFingerprintAfter': primary_after,
                'primaryFingerprintChanged': primary_changed,
                'controlledPrimaryWrite': controlled,
            },
        )
        try:
            snapshot_path.unlink()
        except OSError:
            pass
        return records
    finally:
        release_bash_mutation_lock(paths, ctx)


def post_bash_isolation_failure(paths: RepoPaths, ctx: HookContext) -> str:
    """返回同一 Bash 调用的 primary 指纹阻断原因；没有违规时返回空字符串。"""
    event = _matching_post_bash_event(paths, ctx)
    if not event:
        return ''
    status = str(event.get('status') or '')
    if status == 'PRIMARY_FINGERPRINT_CHANGED':
        return 'Bash 绕过预解析并修改了 primary checkout；primary fingerprint audit BLOCK。'
    if status == 'PRIMARY_FINGERPRINT_UNAVAILABLE':
        return 'Bash 后无法复核 primary checkout fingerprint；fail-closed。'
    return ''


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
    cls = classify_path(rel)
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


# 08. changed-files 聚合公共 API
REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_PATHS = build_paths(REPO_ROOT)
DEFAULT_CHANGED_FILES = _DEFAULT_PATHS.changed_files
DEFAULT_SESSION_ID_FILE = _DEFAULT_PATHS.agent_log_dir / 'session-id.txt'
DEFAULT_BASE_COMMIT_FILE = _DEFAULT_PATHS.agent_log_dir / 'base-commit.txt'
DEFAULT_BASE_DIRTY_STATE_FILE = _DEFAULT_PATHS.agent_log_dir / 'base-dirty-state.json'
GIT_STATUS_PATH_OFFSET = 3
GIT_STATUS_MIN_LINE_LENGTH = GIT_STATUS_PATH_OFFSET + 1


def normalize_path(path: str) -> str:
    """参数：
        path: 待检查的路径。

    返回：
        normalize 路径 字符串。
    """
    value = path.replace('\\', '/').strip()
    while value.startswith('./'):
        value = value[2:]
    return value.strip('/')


# 维护dedupe 路径。
def dedupe_paths(paths: list[str]) -> list[str]:
    """参数：
        paths: 待检查的路径列表。

    返回：
        结果列表。
    """
    result: list[str] = []
    seen: set[str] = set()
    for path in paths:
        normalized = normalize_path(path)
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


# 读取session id。
def read_session_id(session_id_file: Path = DEFAULT_SESSION_ID_FILE) -> str | None:
    """参数：
        session_id_file: session id file 参数。

    返回：
        read session id 字符串。
    """
    if not session_id_file.exists():
        return None
    value = session_id_file.read_text(encoding='utf-8').strip()
    return value or None


# 读取recorded changed-files 文件。
def read_recorded_changed_files(
    session_id: str | None = None,
    changed_files_path: Path = DEFAULT_CHANGED_FILES,
    agent_id: str | None = None,
) -> list[str]:
    """参数：
        session_id: 可选session id used到filter hook record。
        changed_files_path: 路径到 changed-文件 JSONL 文件。
        agent_id: 可选agent id used到filter record到a specific agent。

    返回：
        结果列表。
    """
    if not changed_files_path.exists():
        return []

    files: list[str] = []
    for raw_line in changed_files_path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            record: Any = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue
        if session_id and record.get('sessionId') != session_id:
            continue
        if agent_id:
            record_agent_id = record.get('agentId') or ''
            if record_agent_id != agent_id:
                continue
        file_path = record.get('file') or record.get('file_path')
        if isinstance(file_path, str) and file_path:
            files.append(file_path)
    return dedupe_paths(files)


# 读取recorded changed-files 文件 路径。
def read_recorded_changed_files_from_paths(
    changed_files_paths: list[Path],
    session_id: str | None = None,
    agent_id: str | None = None,
) -> list[str]:
    """参数：
        changed_files_paths: 待检查的路径列表。
        session_id: 用于筛选记录的 session id。
        agent_id: 用于筛选记录的 agent id。

    返回：
        结果列表。
    """
    files: list[str] = []
    for path in changed_files_paths:
        files.extend(read_recorded_changed_files(session_id, path, agent_id=agent_id))
    return dedupe_paths(files)


# 解析Git 状态 路径。
def parse_git_status_paths(output: str) -> list[str]:
    """解析Git 状态 路径。"""
    files: list[str] = []
    for line in output.splitlines():
        if not line.strip() or len(line) < GIT_STATUS_MIN_LINE_LENGTH:
            continue
        path_text = line[GIT_STATUS_PATH_OFFSET:].strip()
        if not path_text:
            continue
        if ' -> ' in path_text:
            files.extend(part.strip().strip('"') for part in path_text.split(' -> ', 1))
        else:
            files.append(path_text.strip('"'))
    return dedupe_paths(files)


# 读取Git dirty 文件。
def read_git_dirty_files(repo_root: Path = REPO_ROOT) -> list[str]:
    """参数：
        repo_root: 仓库根目录。

    返回：
        结果列表。
    """
    try:
        proc = subprocess.run(
            ['git', 'status', '--short', '--untracked-files=all'],
            cwd=repo_root,
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
    return parse_git_status_paths(proc.stdout or '')


# 计算文件 sha256。
def _file_sha256(path: Path) -> str | None:
    """参数：
        path: 待计算 hash 的文件路径。

    返回：
        文件 sha256；无法读取时返回 None。
    """
    try:
        if not path.is_file():
            return None
        h = hashlib.sha256()
        with path.open('rb') as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b''):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


# 读取Git dirty 文件状态。
def read_git_dirty_state(repo_root: Path = REPO_ROOT) -> dict[str, dict[str, Any]]:
    """参数：
        repo_root: 仓库根目录。

    返回：
        dirty path 到 exists/size/hash 元数据的映射，不包含文件内容。
    """
    state: dict[str, dict[str, Any]] = {}
    for rel in read_git_dirty_files(repo_root):
        absolute = repo_root / rel
        try:
            exists = absolute.exists()
            size = absolute.stat().st_size if absolute.is_file() else None
        except OSError:
            exists = False
            size = None
        state[rel] = {
            'exists': exists,
            'size': size,
            'sha256': _file_sha256(absolute),
        }
    return state


# 读取base commit。
def read_base_commit(base_commit_file: Path = DEFAULT_BASE_COMMIT_FILE) -> str | None:
    """参数：
        base_commit_file: base commit sentinel 文件路径。

    返回：
        读取到的 base commit 字符串。
    """
    if not base_commit_file.exists():
        return None
    value = base_commit_file.read_text(encoding='utf-8').strip()
    return value or None


# 维护base dirty state 文件路径。
def base_dirty_state_file(
    base_commit_file: Path = DEFAULT_BASE_COMMIT_FILE,
) -> Path:
    """参数：
        base_commit_file: base commit sentinel 文件路径。

    返回：
        与 base commit 同目录的 dirty-state sentinel 路径。
    """
    return base_commit_file.with_name(DEFAULT_BASE_DIRTY_STATE_FILE.name)


# 读取base dirty state。
def read_base_dirty_state(
    base_commit_file: Path = DEFAULT_BASE_COMMIT_FILE,
) -> dict[str, dict[str, Any]] | None:
    """参数：
        base_commit_file: base commit sentinel 文件路径。

    返回：
        session 起点 dirty state；缺失或损坏时返回 None。
    """
    path = base_dirty_state_file(base_commit_file)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


# 写入缺失的起点脏状态。
def write_base_dirty_state_if_missing(
    repo_root: Path = REPO_ROOT,
    base_commit_file: Path = DEFAULT_BASE_COMMIT_FILE,
    *,
    overwrite: bool = False,
) -> dict[str, dict[str, Any]] | None:
    """参数：
        repo_root: 仓库根目录。
        base_commit_file: base commit sentinel 文件路径。
        overwrite: overwrite 参数。

    返回：
        写入或已有的 dirty state。
    """
    existing = read_base_dirty_state(base_commit_file)
    if existing is not None and not overwrite:
        return existing
    state = read_git_dirty_state(repo_root)
    path = base_dirty_state_file(base_commit_file)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(state, ensure_ascii=False, sort_keys=True) + '\n',
            encoding='utf-8',
        )
    except OSError:
        return None
    return state


# 读取当前 head。
def read_current_head(repo_root: Path = REPO_ROOT) -> str | None:
    """参数：
        repo_root: 仓库根目录。

    返回：
        读取到的当前 HEAD 字符串。
    """
    try:
        proc = subprocess.run(
            ['git', 'rev-parse', 'HEAD'],
            cwd=repo_root,
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


# 记录缺少基准提交的证据，供 Stop 报告定位。
def write_base_commit_if_missing(
    repo_root: Path = REPO_ROOT,
    base_commit_file: Path = DEFAULT_BASE_COMMIT_FILE,
    *,
    overwrite: bool = False,
) -> str | None:
    """参数：
        repo_root: 仓库根目录。
        base_commit_file: base commit sentinel 文件路径。
        overwrite: overwrite 参数。

    返回：
        缺失时写入的 base commit 字符串。
    """
    existing = read_base_commit(base_commit_file)
    if existing and not overwrite:
        return existing

    head = read_current_head(repo_root)
    if not head:
        return None
    try:
        base_commit_file.parent.mkdir(parents=True, exist_ok=True)
        base_commit_file.write_text(head + '\n', encoding='utf-8')
        write_base_dirty_state_if_missing(repo_root, base_commit_file, overwrite=True)
    except OSError:
        return None
    return head


# 读取基准提交之后变更的文件列表。
def read_files_since_base_commit(
    repo_root: Path = REPO_ROOT,
    base_commit_file: Path = DEFAULT_BASE_COMMIT_FILE,
) -> list[str]:
    """参数：
        repo_root: 仓库根目录。
        base_commit_file: base commit sentinel 文件路径。

    返回：
        结果列表。

    说明：
        不 仅 ``base.HEAD``. This fail-closed behavior is 必需 so Bash。
    """
    base_commit = read_base_commit(base_commit_file)
    if not base_commit:
        return []
    paths: list[str] = []
    try:
        proc = subprocess.run(
            ['git', 'diff', '--name-only', '--diff-filter=ACMRD', base_commit],
            cwd=repo_root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=30,
            check=False,
        )
    except Exception:
        return []
    if proc.returncode == 0:
        paths.extend(line for line in (proc.stdout or '').splitlines() if line.strip())

    try:
        untracked = subprocess.run(
            ['git', 'ls-files', '--others', '--exclude-standard'],
            cwd=repo_root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=30,
            check=False,
        )
    except Exception:
        untracked = None
    if untracked is not None and untracked.returncode == 0:
        paths.extend(line for line in (untracked.stdout or '').splitlines() if line.strip())

    return dedupe_paths(paths)


# 收集当前 session/agent 需要纳入 stop gate 的 changed files。
def collect_changed_files(
    session_id: str | None = None,
    *,
    include_git: bool = True,
    repo_root: Path = REPO_ROOT,
    changed_files_path: Path = DEFAULT_CHANGED_FILES,
    base_commit_file: Path | None = None,
    agent_id: str | None = None,
) -> list[str]:
    """参数：
        session_id: 可选session id used到filter hook record。
        include_git: include git 参数。
        repo_root: repo root用于git 命令。
        changed_files_path: 路径到 changed-文件 JSONL 文件。
        base_commit_file: base commit sentinel 文件路径。
        agent_id: 可选agent id到filter hook record到a specific agent。

    返回：
        结果列表。

    说明：
        commit sentinel exists, arbitrary pre-现有 dirty 文件 are 不 routed。
    """
    explicit_base_commit_file = base_commit_file is not None
    if base_commit_file is None:
        base_commit_file = changed_files_path.with_name(DEFAULT_BASE_COMMIT_FILE.name)
    paths = read_recorded_changed_files(session_id, changed_files_path, agent_id=agent_id)
    if include_git or explicit_base_commit_file:
        paths.extend(read_files_since_base_commit(repo_root, base_commit_file))
    return dedupe_paths(paths)


# 解析changed-files 文件 JSON。
def parse_changed_files_json(value: str | None) -> list[str]:
    """参数：
        value: value 参数。

    返回：
        结果列表。
    """
    if value is None:
        return []
    try:
        parsed: Any = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return dedupe_paths([item for item in parsed if isinstance(item, str)])
