"""Change Start/Complete 配对状态与轻量 Git attestation。

本模块只保存 change-scoped baseline、完成状态和 commit 证据；不执行重型 Gate，
不创建或删除 worktree，也不修改 primary checkout。Harness CLI、Hook guard 与
``complete_change`` 共用这里的同一份服务。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from scripts.agent_runtime.git_state import run as git
from scripts.agent_runtime.storage import utc_now

from .common import _append_run_audit, emit_json
from .errors import SessionctlError
from .registry import Registry

START_ENFORCED = 'START_ENFORCED'
START_NOT_ENFORCED = 'START_NOT_ENFORCED'
ADOPT_CONFIRMATION = 'I_CONFIRM_ADOPT_CURRENT'


def exact_files_hash(paths: Iterable[str]) -> str:
    """对排序后的 exact manifest 生成稳定哈希，不受 CLI 参数顺序影响。"""
    encoded = json.dumps(sorted(set(paths)), ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(encoded.encode('utf-8')).hexdigest()


def _dirty_paths(repo: Path) -> list[str]:
    output = git(repo, 'status', '--porcelain=v1', '-z', '--untracked-files=all').stdout
    paths: list[str] = []
    for entry in output.split('\0'):
        if not entry:
            continue
        value = entry[3:] if len(entry) >= 4 else ''
        if ' -> ' in value:
            paths.extend(value.split(' -> ', 1))
        elif value:
            paths.append(value)
    return sorted(set(paths))


def _begin_payload(
    record: Mapping[str, Any], *, activation_source: str, capability: str
) -> dict[str, Any]:
    initial = record.get('initialDirtySnapshot')
    if not isinstance(initial, Mapping):
        raise SessionctlError('begin-change requires an initial dirty snapshot')
    return {
        'status': 'ATTESTED' if capability == START_ENFORCED else START_NOT_ENFORCED,
        'capability': capability,
        'repoKey': record.get('repoKey', ''),
        'worktreeId': record.get('worktreeId', ''),
        'checkoutRoot': record.get('checkoutRoot', ''),
        'checkoutKind': record.get('checkoutKind', ''),
        'detached': bool(record.get('detached')),
        'client': record.get('client', ''),
        'sessionId': record.get('sessionId', ''),
        'runId': record.get('runId', ''),
        'baseCommit': record.get('baseCommit', ''),
        'targetBranch': record.get('targetBranch', ''),
        'targetHead': record.get('targetHeadAtBootstrap', ''),
        'initialDirtySnapshot': dict(initial),
        'allowedPaths': list(record.get('allowedPaths') or []),
        'forbiddenPaths': list(record.get('forbiddenPaths') or []),
        'startedAt': utc_now(),
        'activationEvidence': activation_source,
    }


def begin_change(
    repo_root: Path,
    run_id: str,
    *,
    activation_source: str,
    capability: str = START_ENFORCED,
) -> dict[str, Any]:
    """在 mutation 前幂等保存 change baseline；Codex App 未验证时诚实降级。"""
    if capability not in {START_ENFORCED, START_NOT_ENFORCED}:
        raise SessionctlError(f'unsupported start capability: {capability}')
    registry = Registry(repo_root)
    with registry.locked():
        record = registry.load_run(run_id)
        existing = record.get('changeBegin')
        if isinstance(existing, Mapping):
            if (
                existing.get('runId') != run_id
                or existing.get('checkoutRoot') != record.get('checkoutRoot')
                or existing.get('baseCommit') != record.get('baseCommit')
            ):
                raise SessionctlError('begin-change identity conflicts with existing attestation')
            return record
        initial = record.get('initialDirtySnapshot')
        if not isinstance(initial, Mapping):
            raise SessionctlError('begin-change has no initial baseline')
        current_head = git(repo_root, 'rev-parse', 'HEAD').stdout.strip()
        if current_head != str(record.get('baseCommit') or ''):
            raise SessionctlError('ADOPT_REQUIRED: HEAD changed before begin-change')
        actual_dirty = _dirty_paths(repo_root)
        initial_dirty = sorted(
            set(list(initial.get('tracked') or []) + list(initial.get('untracked') or []))
        )
        if actual_dirty != initial_dirty or actual_dirty:
            raise SessionctlError(
                'ADOPT_REQUIRED: late begin-change found pre-existing dirty content'
            )
        begin = _begin_payload(
            record,
            activation_source=activation_source,
            capability=capability,
        )
        record['changeBegin'] = begin
        timestamp = utc_now()
        record['updatedAt'] = timestamp
        _append_run_audit(
            registry,
            record,
            {
                'event': 'CHANGE_BEGIN_ATTESTED'
                if capability == START_ENFORCED
                else 'START_NOT_ENFORCED',
                'runId': run_id,
                'sessionId': record.get('sessionId', ''),
                'capability': capability,
                'activationEvidence': activation_source,
                'at': timestamp,
            },
        )
        registry.save_run(record)
        return record


def adopt_current(
    repo_root: Path,
    run_id: str,
    *,
    base_commit: str,
    exact_files: Iterable[str],
    confirmation: str,
) -> dict[str, Any]:
    """显式接管 late dirty checkout；base、manifest、用户确认缺一不可。"""
    expected = sorted(set(exact_files))
    if confirmation != ADOPT_CONFIRMATION:
        raise SessionctlError('adopt-current requires explicit user confirmation')
    if not expected:
        raise SessionctlError('adopt-current requires an exact non-empty manifest')
    registry = Registry(repo_root)
    with registry.locked():
        record = registry.load_run(run_id)
        if base_commit != str(record.get('baseCommit') or ''):
            raise SessionctlError('adopt-current base does not match run base')
        if git(repo_root, 'rev-parse', 'HEAD').stdout.strip() != base_commit:
            raise SessionctlError('adopt-current HEAD does not match confirmed base')
        actual = _dirty_paths(repo_root)
        if actual != expected:
            raise SessionctlError(
                f'adopt-current exact manifest mismatch: expected={expected}, actual={actual}'
            )
        begin = _begin_payload(
            record,
            activation_source='explicit-adopt-current',
            capability=START_ENFORCED,
        )
        begin.update(
            {
                'status': 'ATTESTED',
                'adopted': True,
                'adoptedFiles': expected,
                'adoptedFilesHash': exact_files_hash(expected),
                'userConfirmation': confirmation,
            }
        )
        record['changeBegin'] = begin
        record['changeAttribution'] = {
            'baseline': 'explicit-adopt-current',
            'preexistingChangesAttributedToRun': True,
            'requiresHandoffIfIndistinguishable': False,
        }
        timestamp = utc_now()
        record['updatedAt'] = timestamp
        _append_run_audit(
            registry,
            record,
            {
                'event': 'CURRENT_CHECKOUT_ADOPTED',
                'runId': run_id,
                'baseCommit': base_commit,
                'exactFilesHash': begin['adoptedFilesHash'],
                'confirmation': confirmation,
                'at': timestamp,
            },
        )
        registry.save_run(record)
        return record


def require_mutation_baseline(repo_root: Path, record: dict[str, Any]) -> None:
    """在第一次 mutation 前 fail closed，并记录一次 activation 证据。"""
    begin = record.get('changeBegin')
    if not isinstance(begin, Mapping):
        raise SessionctlError('START_NOT_ENFORCED: begin-change baseline is missing')
    if begin.get('status') != 'ATTESTED':
        raise SessionctlError(str(begin.get('status') or START_NOT_ENFORCED))
    if record.get('firstMutationAt'):
        return
    adopted = bool(begin.get('adopted'))
    expected = sorted(begin.get('adoptedFiles') or []) if adopted else []
    if _dirty_paths(repo_root) != expected:
        raise SessionctlError('mutation baseline changed before first authorized write')


def activate_first_mutation(registry: Registry, record: dict[str, Any]) -> None:
    """baseline 复核后原子标记首次 mutation，重复 guard 不重写时间。"""
    if record.get('firstMutationAt'):
        return
    timestamp = utc_now()
    record['firstMutationAt'] = timestamp
    record['updatedAt'] = timestamp
    _append_run_audit(
        registry,
        record,
        {'event': 'FIRST_MUTATION_AUTHORIZED', 'runId': record['runId'], 'at': timestamp},
    )
    registry.save_run(record)


def completion_requirement(repo_root: Path, record: Mapping[str, Any]) -> dict[str, Any]:
    """兼容查询 canonical Change 状态；修复命令是可解析 argv，不含占位符。"""
    dirty = _dirty_paths(repo_root)
    base = str(record.get('baseCommit') or '')
    head = git(repo_root, 'rev-parse', 'HEAD').stdout.strip()
    committed = (
        sorted(
            set(
                git(
                    repo_root,
                    'diff',
                    '--name-only',
                    '--no-renames',
                    f'{base}...{head}',
                ).stdout.splitlines()
            )
        )
        if base and head != base
        else []
    )
    task_changes = sorted(set(dirty + committed))
    from scripts.agent_runtime.change.controller import LifecycleController
    from scripts.agent_runtime.change.model import current_change

    controller = LifecycleController(repo_root, record)
    session = controller.ensure_session(event='status')
    change = current_change(session)
    state = str(change.get('state') or '') if change else 'WORKING'
    commit_sha = str(change.get('commitSha') or '') if change else ''
    if task_changes and (
        state not in {'COMMITTED', 'COMMITTED_HANDOFF', 'INTEGRATED'} or not commit_sha
    ):
        return {
            'status': 'COMMIT_REQUIRED',
            'runId': record.get('runId', ''),
            'changedFiles': task_changes,
            'recoveryArgv': [
                'python3',
                'scripts/harness/change.py',
                'resume',
                '--run-id',
                str(record.get('runId', '')),
                '--message',
                'chore(agent): resume change',
            ],
        }
    return {
        'status': state or 'WORKING',
        'runId': record.get('runId', ''),
        'commitSha': commit_sha,
    }


def cmd_begin_change(args: Any) -> int:
    """稳定 CLI adapter：调用共享 begin service 并输出 baseline 事实。"""
    repo = Path(args.repo_root or args.cwd).resolve()
    capability = START_ENFORCED if args.start_enforced else START_NOT_ENFORCED
    record = begin_change(
        repo,
        args.run_id,
        activation_source=args.activation_source,
        capability=capability,
    )
    emit_json(
        {
            'status': record['changeBegin']['status'],
            'runId': record['runId'],
            'changeBegin': record['changeBegin'],
        }
    )
    return 0 if record['changeBegin']['status'] == 'ATTESTED' else 2


def cmd_adopt_current(args: Any) -> int:
    """稳定 CLI adapter：显式审计接管当前 dirty manifest。"""
    repo = Path(args.repo_root or args.cwd).resolve()
    record = adopt_current(
        repo,
        args.run_id,
        base_commit=args.base,
        exact_files=args.file,
        confirmation=args.confirmation,
    )
    emit_json(
        {
            'status': 'ADOPTED',
            'runId': record['runId'],
            'changeBegin': record['changeBegin'],
        }
    )
    return 0


def cmd_completion_status(args: Any) -> int:
    """供 Stop/SessionEnd/launcher post-exit 共用的 normal completion 检查。"""
    repo = Path(args.repo_root).resolve() if args.repo_root else Path.cwd().resolve()
    registry = Registry(repo)
    record = registry.load_run(args.run_id)
    result = completion_requirement(repo, record)
    emit_json(result)
    return 2 if result['status'] == 'COMMIT_REQUIRED' else 0
