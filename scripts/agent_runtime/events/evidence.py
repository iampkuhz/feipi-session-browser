"""持久化 Hook 事件、文件变更与 Bash mutation 归因证据。

本模块只写入 ``paths.RepoPaths`` 指定的运行目录，不选择 Gate、不更新
Registry，也不负责平台 payload 解析。"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from scripts.agent_runtime.change.runtime import append_jsonl as append_jsonl_atomic
from scripts.agent_runtime.context import current_change_id
from scripts.agent_runtime.git_state import (
    GitStateError,
    checkout_content_snapshot,
    diff_paths,
    optional_value,
)
from scripts.agent_runtime.git_state import dirty_files as read_git_dirty_files
from scripts.agent_runtime.git_state import optional as git_optional
from scripts.agent_runtime.locks import FencedFileLock, read_lock_owner, release_owned_lock
from scripts.agent_runtime.paths import RepoPaths, build_paths, ensure_runtime_dirs, rel_to_repo
from scripts.agent_runtime.session.contract import snapshot_path_states
from scripts.agent_runtime.storage import load_json, utc_now, write_json_atomic
from scripts.gates.planner import classify_path

if TYPE_CHECKING:
    from scripts.agent_runtime.context import HookContext


# 01. 时间与 JSONL 基础函数
BASH_MUTATION_LOCK_STALE_SECONDS = 2 * 60 * 60


# 追加 JSONL 记录并避免重复事件。
def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    """持久化对应 Runtime 证据；写入范围由调用方身份路径约束。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    event_id = record.get('eventId')
    if event_id and path.exists():
        try:
            for line in path.read_text(encoding='utf-8').splitlines():
                if line.strip() and json.loads(line).get('eventId') == event_id:
                    return
        except (OSError, json.JSONDecodeError, AttributeError):
            pass
    # 单次 O_APPEND+fsync 消除无限 flock；重复 eventId 即使竞态追加也保持事实一致。
    append_jsonl_atomic(path, record)


# 计算 hook 事件的稳定 id。
def event_id_for(paths: RepoPaths, ctx: HookContext, event: str | None = None) -> str:
    """执行对应 Runtime 契约；不绕过身份、归因或 fail-closed 约束。"""
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
    """执行对应 Runtime 契约；不绕过身份、归因或 fail-closed 约束。"""
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
    """执行对应 Runtime 契约；不绕过身份、归因或 fail-closed 约束。"""
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
    """执行对应 Runtime 契约；不绕过身份、归因或 fail-closed 约束。"""
    try:
        return path.stat().st_size if path.exists() else None
    except Exception:
        return None


# 维护Bash snapshot key。
def _bash_snapshot_key(ctx: HookContext, client: str = '') -> str | None:
    """内部证据原语；无法证明事实时沿调用链关闭失败。"""
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
    """内部证据原语；无法证明事实时沿调用链关闭失败。"""
    key = _bash_snapshot_key(ctx, paths.identity.client)
    if not key:
        return None
    return paths.agent_log_dir / 'bash-snapshots' / f'{key}.json'


# 判断前置 Bash 事件是否说明缺失 snapshot 不是 mutation attribution gap。
def pre_bash_exempts_missing_snapshot(event: dict[str, Any] | None) -> bool:
    """执行对应 Runtime 契约；不绕过身份、归因或 fail-closed 约束。"""
    if not event:
        return False
    return event.get('status') == 'BLOCK' or event.get('bashMutationTracking') is False


# 查找同一 Bash 工具调用的 hook 记录。
def _matching_bash_event(
    paths: RepoPaths, ctx: HookContext, event_name: str
) -> dict[str, Any] | None:
    """内部证据原语；无法证明事实时沿调用链关闭失败。"""
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
        if event.get('toolUseId') == ctx.tool_use_id and event.get('event') == event_name:
            return event
    return None


# 维护Bash 锁 路径。
def _bash_lock_path(paths: RepoPaths) -> Path:
    """内部证据原语；无法证明事实时沿调用链关闭失败。"""
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


# 读取 Bash 变更锁详情。
def read_bash_mutation_lock_info(paths: RepoPaths) -> dict[str, Any] | None:
    """读取对应 Runtime 证据；缺失或损坏数据不伪造成功。"""
    lock_path = _bash_lock_path(paths)
    raw = read_lock_owner(lock_path)
    if raw is None:
        return None
    try:
        age = time.time() - lock_path.stat().st_mtime
    except OSError:
        return None
    raw['age_seconds'] = max(0.0, age)
    return raw


# 获取Bash mutation 锁。
def acquire_bash_mutation_lock(paths: RepoPaths, ctx: HookContext) -> bool:
    """用共享 no-clobber/fencing 原语获取 checkout 级 Bash mutation 锁。"""
    owner = _bash_snapshot_key(ctx, paths.identity.client)
    if not owner:
        return False
    lock_path = _bash_lock_path(paths)
    payload = {
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
    }
    return FencedFileLock(
        lock_path,
        payload,
        stale_seconds=BASH_MUTATION_LOCK_STALE_SECONDS,
        strict_scope=paths.identity.has_run,
        reclaim_event='BASH_MUTATION_LOCK_RECLAIMED',
    ).try_acquire()


# 释放Bash mutation 锁。
def release_bash_mutation_lock(paths: RepoPaths, ctx: HookContext) -> None:
    """仅在 owner、inode 与 fencing epoch 全匹配时释放 Bash mutation 锁。"""
    owner = _bash_snapshot_key(ctx, paths.identity.client)
    if not owner:
        return
    release_owned_lock(
        _bash_lock_path(paths),
        {
            'owner': owner,
            'runId': paths.identity.raw_run_id,
            'sessionId': ctx.session_id,
            'worktreeId': paths.identity.raw_worktree_id,
        },
    )


# 维护Git head。


# 维护Git diff 路径。


# 维护dirty state。
def _dirty_state(paths: RepoPaths) -> dict[str, dict[str, Any]]:
    """内部证据原语；无法证明事实时沿调用链关闭失败。"""
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
    """采集提交、索引、工作区与未跟踪内容的统一指纹；失败时关闭失败。"""
    try:
        return str(checkout_content_snapshot(repo_root)["fingerprint"])
    except GitStateError:
        return None


# 记录pre Bash snapshot。
def record_pre_bash_snapshot(
    paths: RepoPaths,
    ctx: HookContext,
    *,
    primary_root: Path | None = None,
    controlled_primary_write: bool = False,
) -> bool:
    """在 mutation 前记录 checkout 与 primary 内容指纹，缺失即不可归因。"""
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
        'head': optional_value(paths.repo_root, 'rev-parse', 'HEAD'),
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
    """对照前置快照记录 Bash 变更；primary 漂移或快照缺失时关闭失败。"""
    ensure_runtime_dirs(paths)
    try:
        snapshot_path = _bash_snapshot_path(paths, ctx)
        if snapshot_path is None or not snapshot_path.exists():
            if _matching_bash_event(paths, ctx, 'post-bash'):
                return []
            pre_event = _matching_bash_event(paths, ctx, 'pre-bash')
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
        head_after = optional_value(paths.repo_root, 'rev-parse', 'HEAD')
        if (
            isinstance(head_before, str)
            and head_before
            and head_after
            and head_before != head_after
        ):
            changed.extend(diff_paths(paths.repo_root, head_before, head_after))

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
    event = _matching_bash_event(paths, ctx, 'post-bash')
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
    """持久化对应 Runtime 证据；写入范围由调用方身份路径约束。"""
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
    """持久化对应 Runtime 证据；写入范围由调用方身份路径约束。"""
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
    """持久化对应 Runtime 证据；写入范围由调用方身份路径约束。"""
    records: list[dict[str, Any]] = []
    for file_path in ctx.candidate_paths:
        records.append(record_changed_file(paths, ctx, file_path))
    record_hook_event(paths, ctx, status='RECORDED', extra={'changedFileCount': len(records)})
    return records


# 读取changed-files 文件。
def read_changed_files(paths: RepoPaths) -> list[dict[str, Any]]:
    """读取对应 Runtime 证据；缺失或损坏数据不伪造成功。"""
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


def normalize_path(path: str) -> str:
    """规范化外部证据为稳定、去重的仓库相对表示。"""
    value = path.replace('\\', '/').strip()
    while value.startswith('./'):
        value = value[2:]
    return value.strip('/')


# 维护dedupe 路径。
def dedupe_paths(paths: list[str]) -> list[str]:
    """规范化外部证据为稳定、去重的仓库相对表示。"""
    result: list[str] = []
    seen: set[str] = set()
    for path in paths:
        normalized = normalize_path(path)
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


# 读取recorded changed-files 文件。
def read_recorded_changed_files(
    session_id: str | None = None,
    changed_files_path: Path = DEFAULT_CHANGED_FILES,
    agent_id: str | None = None,
) -> list[str]:
    """读取对应 Runtime 证据；缺失或损坏数据不伪造成功。"""
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
    """读取对应 Runtime 证据；缺失或损坏数据不伪造成功。"""
    files: list[str] = []
    for path in changed_files_paths:
        files.extend(read_recorded_changed_files(session_id, path, agent_id=agent_id))
    return dedupe_paths(files)


# 读取base commit。
def read_base_commit(base_commit_file: Path = DEFAULT_BASE_COMMIT_FILE) -> str | None:
    """读取对应 Runtime 证据；缺失或损坏数据不伪造成功。"""
    if not base_commit_file.exists():
        return None
    value = base_commit_file.read_text(encoding='utf-8').strip()
    return value or None


# 维护base dirty state 文件路径。
def base_dirty_state_file(
    base_commit_file: Path = DEFAULT_BASE_COMMIT_FILE,
) -> Path:
    """执行对应 Runtime 契约；不绕过身份、归因或 fail-closed 约束。"""
    return base_commit_file.with_name(DEFAULT_BASE_DIRTY_STATE_FILE.name)


# 读取base dirty state。
def read_base_dirty_state(
    base_commit_file: Path = DEFAULT_BASE_COMMIT_FILE,
) -> dict[str, dict[str, Any]] | None:
    """安全读取 session 起点 dirty snapshot；缺失或损坏返回 ``None``。"""
    try:
        return load_json(base_dirty_state_file(base_commit_file))
    except (OSError, ValueError):
        return None


# 写入缺失的起点脏状态。
def write_base_dirty_state_if_missing(
    repo_root: Path = REPO_ROOT,
    base_commit_file: Path = DEFAULT_BASE_COMMIT_FILE,
    *,
    overwrite: bool = False,
) -> dict[str, dict[str, Any]] | None:
    """持久化对应 Runtime 证据；写入范围由调用方身份路径约束。"""
    existing = read_base_dirty_state(base_commit_file)
    if existing is not None and not overwrite:
        return existing
    state = snapshot_path_states(repo_root, read_git_dirty_files(repo_root))
    try:
        write_json_atomic(base_dirty_state_file(base_commit_file), state)
        return state
    except OSError:
        return None


# 读取当前 head。


# 记录缺少基准提交的证据，供 Stop 报告定位。
def write_base_commit_if_missing(
    repo_root: Path = REPO_ROOT,
    base_commit_file: Path = DEFAULT_BASE_COMMIT_FILE,
    *,
    overwrite: bool = False,
) -> str | None:
    """持久化对应 Runtime 证据；写入范围由调用方身份路径约束。"""
    existing = read_base_commit(base_commit_file)
    if existing and not overwrite:
        return existing

    head = optional_value(repo_root, 'rev-parse', 'HEAD')
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
    """读取对应 Runtime 证据；缺失或损坏数据不伪造成功。"""
    base_commit = read_base_commit(base_commit_file)
    if not base_commit:
        return []
    diff = git_optional(repo_root, 'diff', '--name-only', '--diff-filter=ACMRD', base_commit)
    untracked = git_optional(repo_root, 'ls-files', '--others', '--exclude-standard')
    paths = diff.stdout.splitlines() if diff else []
    if untracked:
        paths.extend(untracked.stdout.splitlines())
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
    """合并身份审计、base commit 与 Git dirty 路径，并保持稳定去重。"""
    explicit_base_commit_file = base_commit_file is not None
    if base_commit_file is None:
        base_commit_file = changed_files_path.with_name(DEFAULT_BASE_COMMIT_FILE.name)
    paths = read_recorded_changed_files(session_id, changed_files_path, agent_id=agent_id)
    if include_git or explicit_base_commit_file:
        paths.extend(read_files_since_base_commit(repo_root, base_commit_file))
    return dedupe_paths(paths)


# 解析changed-files 文件 JSON。
def parse_changed_files_json(value: str | None) -> list[str]:
    """规范化外部证据为稳定、去重的仓库相对表示。"""
    if value is None:
        return []
    try:
        parsed: Any = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return dedupe_paths([item for item in parsed if isinstance(item, str)])
