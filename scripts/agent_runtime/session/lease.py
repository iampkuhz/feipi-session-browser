"""负责 checkout writer lease 的获取、心跳、fencing 释放与受控回收；不负责资源锁；由 Hook、Session CLI 和 finalize 调用。"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from scripts.agent_runtime.git_state import run as git
from scripts.agent_runtime.locks import _pid_start_time, process_is_alive
from scripts.agent_runtime.storage import load_json, write_json_atomic
from scripts.agent_runtime.storage import utc_now as now_utc

from .common import (
    _lease_record_view,
    _parse_utc,
    _set_run_status,
    _writer_status,
    audit_run,
    emit_json,
)
from .contract import (
    ACTIVE_WRITER_STATUSES,
    resolve_checkout_root,
    stable_worktree_id,
    validate_checkout_record,
)
from .errors import SessionctlError, WriterLeaseConflictError, WriterLeaseFencedError
from .lifecycle import _checkout_snapshot, _record_matches_bootstrap
from .registry import REGISTRY_VERSION, Registry, _validate_identifier

if TYPE_CHECKING:
    import argparse

DEFAULT_LEASE_STALE_SECONDS = 300.0
LEASE_ACTIVE = "ACTIVE"
LEASE_RELEASED = "RELEASED"


@contextmanager
def _lease_transaction(
    registry: Registry, record: Mapping[str, Any]
) -> Iterator[tuple[dict[str, Any], dict[str, Any]]]:
    """按 checkout-mutation → Registry 固定顺序持锁，避免状态与 lease 分叉。"""
    worktree_id = str(record["worktreeId"])
    identity = {
        "client": str(record["client"]),
        "session_id": str(record["sessionId"]),
        "run_id": str(record["runId"]),
    }
    with registry.checkout_mutation_locked(worktree_id, **identity):
        with registry.locked(**identity):
            current = _reload_lease_run(registry, record)
            yield current, _load_checkout_lease(registry, worktree_id)


def _invalidate_stop_validation_for_mutation(
    registry: Registry, record: dict[str, Any], *, timestamp: str
) -> None:
    """写操作前使已有 Stop 回执失效并审计原因，禁止复用旧验证结果。"""
    if record.get('status') != 'VALIDATED':
        return
    _set_run_status(record, _writer_status(record))
    validation = record.get('stopValidation')
    if isinstance(validation, dict):
        validation['fresh'] = False
        validation['staleAt'] = timestamp
        validation['staleReason'] = 'mutation requested after Stop validation'
    record['validationStaleAt'] = timestamp
    record['validationStaleReason'] = 'mutation requested after Stop validation'
    audit_run(
        registry,
        record,
        'STOP_VALIDATION_INVALIDATED',
        at=timestamp,
        reason=record['validationStaleReason'],
    )


def _validate_lease_checkout(registry: Registry, record: Mapping[str, Any]) -> Path:
    """复核运行记录、仓库键和 worktree 身份，防止跨 checkout 操作 lease。"""
    if record.get('repoKey') != registry.repo_key:
        raise SessionctlError('run and Registry repository identities do not match')
    checkout = Path(str(record.get('checkoutRoot') or ''))
    facts, errors = validate_checkout_record(checkout, dict(record))
    if errors:
        raise SessionctlError('checkout identity is invalid: ' + '; '.join(errors))
    expected_id = stable_worktree_id(registry.repo_key, str(facts['checkoutRoot']))
    if record.get('worktreeId') != expected_id:
        raise SessionctlError('run worktreeId is not the stable checkout identity')
    return Path(str(facts['checkoutRoot']))


def _reload_lease_run(registry: Registry, supplied: Mapping[str, Any]) -> dict[str, Any]:
    """持锁重读运行记录并对照调用者身份，拒绝锁等待期间发生的身份切换。"""
    current = registry.load_run(str(supplied.get('runId') or ''))
    for field in ('repoKey', 'client', 'sessionId', 'worktreeId', 'checkoutRoot'):
        if str(current.get(field) or '') != str(supplied.get(field) or ''):
            raise SessionctlError(f'run identity changed while mutating lease: {field}')
    _validate_lease_checkout(registry, current)
    return current


def _load_checkout_lease(registry: Registry, worktree_id: str) -> dict[str, Any]:
    """读取 worktree 的权威 lease 文件；缺失时返回空映射供状态机判定。"""
    return load_json(registry.writer_lease_path(worktree_id), {})


def _lease_fence_matches(
    lease: Mapping[str, Any], *, run_id: str, session_id: str, epoch: int, fencing_token: str
) -> bool:
    """同时核对活动状态、run、Session、epoch 与 token，证明调用者仍持有 lease。"""
    try:
        actual_epoch = int(lease.get('epoch') or 0)
    except (TypeError, ValueError):
        return False
    return (
        lease.get('state') == LEASE_ACTIVE
        and lease.get('holderRunId') == run_id
        and (lease.get('holderSessionId') == session_id)
        and (actual_epoch == epoch)
        and bool(fencing_token)
        and (lease.get('fencingToken') == fencing_token)
    )


def _cached_fence(record: Mapping[str, Any]) -> tuple[int, str]:
    """从运行记录提取缓存 epoch 与 token；非法 epoch 归零并由后续操作关闭失败。"""
    cached = record.get('writerLease') if isinstance(record.get('writerLease'), Mapping) else {}
    try:
        epoch = int(cached.get('epoch') or 0)
    except (TypeError, ValueError):
        epoch = 0
    return (epoch, str(cached.get('fencingToken') or ''))


def _block_fenced_run(
    registry: Registry,
    record: dict[str, Any],
    *,
    lease: Mapping[str, Any],
    operation: str,
    reason: str,
) -> None:
    """把 fencing 失败的运行转为 BLOCKED，写入权威审计后再抛出异常。"""
    _set_run_status(record, 'BLOCKED')
    record['leaseBlockReason'] = reason
    record['updatedAt'] = now_utc()
    audit_run(
        registry,
        record,
        'WRITER_LEASE_FENCED',
        operation=operation,
        recordEpoch=_cached_fence(record)[0],
        leaseEpoch=lease.get('epoch', 0),
        reason=reason,
    )
    registry.save_run(record)


def mark_read_only_ready(registry: Registry, record: dict[str, Any]) -> dict[str, Any]:
    """在 Registry 锁内将新运行置为只读就绪，不创建或继承 writer lease。"""
    with registry.locked(
        client=str(record.get('client') or ''),
        session_id=str(record.get('sessionId') or ''),
        run_id=str(record.get('runId') or ''),
    ):
        current = _reload_lease_run(registry, record)
        if current['status'] == 'BOOTSTRAPPED':
            _set_run_status(current, 'READ_ONLY_READY')
            current['writerLease'] = {}
            current['updatedAt'] = now_utc()
            registry.save_run(current)
        return current


def acquire_writer_lease(
    registry: Registry,
    record: dict[str, Any],
    *,
    owner_pid: int | None = None,
    owner_start_time: str = '',
) -> tuple[dict[str, Any], dict[str, Any]]:
    """按 checkout-mutation 与 Registry 锁序获取唯一 writer lease，并生成新 fencing epoch。"""
    checkout = _validate_lease_checkout(registry, record)
    worktree_id = str(record['worktreeId'])
    supplied_epoch, supplied_token = _cached_fence(record)
    pid = int(owner_pid if owner_pid is not None else os.getpid())
    if pid <= 0:
        raise SessionctlError('writer lease owner pid must be positive')
    process_start = owner_start_time or _pid_start_time(pid)
    with _lease_transaction(registry, record) as (current, lease):
        current_epoch, current_token = _cached_fence(current)
        if supplied_epoch or supplied_token:
            if not _lease_fence_matches(
                lease,
                run_id=str(record['runId']),
                session_id=str(record['sessionId']),
                epoch=supplied_epoch,
                fencing_token=supplied_token,
            ):
                reason = 'cached epoch/fencing token does not match current checkout lease'
                _block_fenced_run(
                    registry, current, lease=lease, operation='acquire', reason=reason
                )
                raise WriterLeaseFencedError(reason)
        if lease.get('state') == LEASE_ACTIVE:
            if (
                lease.get('holderRunId') == current['runId']
                and lease.get('holderSessionId') == current['sessionId']
            ):
                if not _lease_fence_matches(
                    lease,
                    run_id=str(current['runId']),
                    session_id=str(current['sessionId']),
                    epoch=current_epoch,
                    fencing_token=current_token,
                ):
                    reason = 'run record fencing data does not match active checkout lease'
                    _block_fenced_run(
                        registry, current, lease=lease, operation='acquire', reason=reason
                    )
                    raise WriterLeaseFencedError(reason)
                timestamp = now_utc()
                lease['heartbeatAt'] = timestamp
                lease['updatedAt'] = timestamp
                write_json_atomic(registry.writer_lease_path(worktree_id), lease)
                _invalidate_stop_validation_for_mutation(registry, current, timestamp=timestamp)
                current['writerLease'] = _lease_record_view(lease)
                current['updatedAt'] = timestamp
                registry.save_run(current)
                return (current, lease)
            if current['status'] == 'VALIDATED':
                timestamp = now_utc()
                validation = current.get('stopValidation')
                if isinstance(validation, dict):
                    validation['fresh'] = False
                    validation['staleAt'] = timestamp
                    validation['staleReason'] = 'mutation conflicted after Stop validation'
                current['validationStaleAt'] = timestamp
                current['validationStaleReason'] = 'mutation conflicted after Stop validation'
                _set_run_status(current, 'READ_ONLY_CONFLICT')
            elif current['status'] not in {
                'BOOTSTRAPPED',
                'READ_ONLY_READY',
                'READ_ONLY_CONFLICT',
            }:
                raise SessionctlError(
                    f"run status cannot enter writer conflict: {current['status']}"
                )
            else:
                _set_run_status(current, 'READ_ONLY_CONFLICT')
            current['writerLease'] = {}
            timestamp = now_utc()
            current['writerLeaseConflict'] = {
                'holderRunId': lease.get('holderRunId', ''),
                'holderSessionId': lease.get('holderSessionId', ''),
                'worktreeId': worktree_id,
                'epoch': lease.get('epoch', 0),
                'observedAt': timestamp,
            }
            current['updatedAt'] = timestamp
            audit_run(
                registry,
                current,
                'WRITER_LEASE_CONFLICT',
                holderRunId=lease.get('holderRunId', ''),
                holderSessionId=lease.get('holderSessionId', ''),
                epoch=lease.get('epoch', 0),
            )
            registry.save_run(current)
            raise WriterLeaseConflictError(
                f"checkout writer lease is held by run {lease.get('holderRunId', '')}"
            )
        if current['status'] == 'BLOCKED':
            raise WriterLeaseFencedError(
                str(current.get('leaseBlockReason') or 'blocked run cannot reacquire writer lease')
            )
        if current['status'] not in {
            'BOOTSTRAPPED',
            'READ_ONLY_READY',
            'READ_ONLY_CONFLICT',
            'VALIDATED',
        }:
            raise SessionctlError(f"run status cannot acquire writer lease: {current['status']}")
        try:
            previous_epoch = int(lease.get('epoch') or 0)
        except (TypeError, ValueError) as exc:
            raise SessionctlError('checkout lease epoch is invalid') from exc
        epoch = previous_epoch + 1
        timestamp = now_utc()
        owner_uid = os.geteuid() if hasattr(os, 'geteuid') else os.getuid()
        lease = {
            'schemaVersion': REGISTRY_VERSION,
            'leaseId': f'lease-{uuid.uuid4().hex}',
            'holderRunId': current['runId'],
            'holderSessionId': current['sessionId'],
            'runId': current['runId'],
            'sessionId': current['sessionId'],
            'client': current['client'],
            'repoKey': registry.repo_key,
            'worktreeId': worktree_id,
            'checkoutRoot': str(checkout),
            'checkoutKind': current['checkoutKind'],
            'epoch': epoch,
            'fencingToken': uuid.uuid4().hex,
            'state': LEASE_ACTIVE,
            'owner': f'uid:{owner_uid}',
            'ownerUid': owner_uid,
            'pid': pid,
            'processStartTime': process_start,
            'acquiredAt': timestamp,
            'heartbeatAt': timestamp,
            'updatedAt': timestamp,
            'releasedAt': '',
        }
        write_json_atomic(registry.writer_lease_path(worktree_id), lease)
        _invalidate_stop_validation_for_mutation(registry, current, timestamp=timestamp)
        if current['status'] != _writer_status(current):
            _set_run_status(current, _writer_status(current))
        current['writerLease'] = _lease_record_view(lease)
        current.pop('writerLeaseConflict', None)
        current.pop('leaseBlockReason', None)
        current['updatedAt'] = timestamp
        audit_run(
            registry,
            current,
            'WRITER_LEASE_ACQUIRED',
            at=timestamp,
            leaseId=lease['leaseId'],
            epoch=epoch,
        )
        registry.save_run(current)
        return (current, lease)


def heartbeat_writer_lease(
    registry: Registry,
    record: dict[str, Any],
    *,
    expected_epoch: int | None = None,
    fencing_token: str = '',
) -> tuple[dict[str, Any], dict[str, Any]]:
    """仅凭匹配的 epoch 与 token 刷新权威 lease；失配时封禁旧运行。"""
    _validate_lease_checkout(registry, record)
    worktree_id = str(record['worktreeId'])
    cached_epoch, cached_token = _cached_fence(record)
    epoch = int(expected_epoch if expected_epoch is not None else cached_epoch)
    token = fencing_token or cached_token
    if epoch <= 0 or not token:
        raise WriterLeaseFencedError('heartbeat requires expected epoch and fencing token')
    with _lease_transaction(registry, record) as (current, lease):
        if not _lease_fence_matches(
            lease,
            run_id=str(current['runId']),
            session_id=str(current['sessionId']),
            epoch=epoch,
            fencing_token=token,
        ):
            reason = 'heartbeat epoch/fencing token does not match current checkout lease'
            _block_fenced_run(registry, current, lease=lease, operation='heartbeat', reason=reason)
            raise WriterLeaseFencedError(reason)
        timestamp = now_utc()
        lease['heartbeatAt'] = timestamp
        lease['updatedAt'] = timestamp
        write_json_atomic(registry.writer_lease_path(worktree_id), lease)
        current['writerLease'] = _lease_record_view(lease)
        current['updatedAt'] = timestamp
        registry.save_run(current)
        return (current, lease)


def release_writer_lease(
    registry: Registry,
    record: dict[str, Any],
    *,
    expected_epoch: int | None = None,
    fencing_token: str = '',
    reason: str = 'SessionEnd',
    inherited: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """仅由当前 fencing owner 释放 lease；继承型 subagent 不得释放父运行所有权。"""
    _validate_lease_checkout(registry, record)
    worktree_id = str(record['worktreeId'])
    cached_epoch, cached_token = _cached_fence(record)
    epoch = int(expected_epoch if expected_epoch is not None else cached_epoch)
    token = fencing_token or cached_token
    with _lease_transaction(registry, record) as (current, lease):
        if inherited:
            event = audit_run(registry, current, 'SUBAGENT_LEASE_RELEASE_SKIPPED')
            current['updatedAt'] = event['at']
            registry.save_run(current)
            return (current, lease)
        owns_active = (
            lease.get('state') == LEASE_ACTIVE
            and lease.get('holderRunId') == current['runId']
            and (lease.get('holderSessionId') == current['sessionId'])
        )
        if not owns_active and (not epoch) and (not token):
            return (current, lease)
        if (
            epoch <= 0
            or not token
            or (
                not _lease_fence_matches(
                    lease,
                    run_id=str(current['runId']),
                    session_id=str(current['sessionId']),
                    epoch=epoch,
                    fencing_token=token,
                )
            )
        ):
            reason_text = 'release epoch/fencing token does not match current checkout lease'
            _block_fenced_run(
                registry, current, lease=lease, operation='release', reason=reason_text
            )
            raise WriterLeaseFencedError(reason_text)
        timestamp = now_utc()
        lease['state'] = LEASE_RELEASED
        lease['releasedAt'] = timestamp
        lease['heartbeatAt'] = timestamp
        lease['updatedAt'] = timestamp
        lease['releaseReason'] = reason
        write_json_atomic(registry.writer_lease_path(worktree_id), lease)
        if current.get('status') in ACTIVE_WRITER_STATUSES:
            _set_run_status(current, 'READ_ONLY_READY')
        current['writerLease'] = {}
        current['releasedWriterLease'] = {
            'leaseId': lease['leaseId'],
            'worktreeId': worktree_id,
            'epoch': epoch,
            'state': LEASE_RELEASED,
            'releasedAt': timestamp,
        }
        current['updatedAt'] = timestamp
        audit_run(
            registry,
            current,
            'WRITER_LEASE_RELEASED',
            at=timestamp,
            leaseId=lease['leaseId'],
            epoch=epoch,
            reason=reason,
        )
        registry.save_run(current)
        return (current, lease)


def reclaim_writer_lease(
    registry: Registry,
    requester: dict[str, Any],
    *,
    expected_epoch: int,
    expected_holder_run_id: str = '',
    expected_holder_session_id: str = '',
    stale_after_seconds: float = DEFAULT_LEASE_STALE_SECONDS,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """仅在 checkout 干净、心跳过期且 owner 进程死亡时受控回收并推进 epoch。"""
    checkout = _validate_lease_checkout(registry, requester)
    if expected_epoch <= 0:
        raise SessionctlError('reclaim requires a positive expected epoch')
    if stale_after_seconds < 0:
        raise SessionctlError('reclaim stale threshold must be non-negative')
    worktree_id = str(requester['worktreeId'])
    with _lease_transaction(registry, requester) as (current, lease):
        try:
            lease_epoch = int(lease.get('epoch') or 0)
        except (TypeError, ValueError) as exc:
            raise SessionctlError('checkout lease epoch is invalid') from exc
        if lease.get('state') != LEASE_ACTIVE:
            raise SessionctlError('reclaim target is not an active writer lease')
        if lease_epoch != expected_epoch:
            raise WriterLeaseFencedError(
                f'reclaim expected epoch {expected_epoch}, current epoch is {lease_epoch}'
            )
        if expected_holder_run_id and lease.get('holderRunId') != expected_holder_run_id:
            raise SessionctlError('reclaim target run does not match active lease')
        if (
            expected_holder_session_id
            and lease.get('holderSessionId') != expected_holder_session_id
        ):
            raise SessionctlError('reclaim target Session does not match active lease')
        if lease.get('holderRunId') == current['runId']:
            raise SessionctlError('lease owner must use release instead of reclaim')
        if (
            lease.get('repoKey') != registry.repo_key
            or lease.get('worktreeId') != worktree_id
            or Path(str(lease.get('checkoutRoot') or '')).resolve() != checkout
        ):
            raise SessionctlError('reclaim target lease checkout identity is invalid')
        if git(checkout, 'status', '--porcelain=v1', '--untracked-files=all').stdout.strip():
            raise SessionctlError('reclaim requires a clean checkout')
        heartbeat = _parse_utc(str(lease.get('heartbeatAt') or ''))
        heartbeat_age = (
            (datetime.now(UTC) - heartbeat).total_seconds()
            if heartbeat is not None
            else float('inf')
        )
        try:
            owner_pid = int(lease.get('pid') or 0)
        except (TypeError, ValueError):
            owner_pid = 0
        owner_alive = process_is_alive(owner_pid, str(lease.get('processStartTime') or ''))
        if heartbeat_age < stale_after_seconds:
            raise SessionctlError('reclaim refused: heartbeat is not stale')
        if owner_alive:
            raise SessionctlError('reclaim refused: lease owner process is still alive')
        previous_holder_run = str(lease.get('holderRunId') or '')
        previous_holder_session = str(lease.get('holderSessionId') or '')
        timestamp = now_utc()
        reclaimed = dict(lease)
        reclaimed.update(
            {
                'epoch': expected_epoch + 1,
                'fencingToken': uuid.uuid4().hex,
                'state': LEASE_RELEASED,
                'heartbeatAt': timestamp,
                'updatedAt': timestamp,
                'releasedAt': timestamp,
                'releaseReason': 'controlled-reclaim',
                'reclaimedFromEpoch': expected_epoch,
                'reclaimedByRunId': current['runId'],
                'reclaimedBySessionId': current['sessionId'],
                'reclaimedAt': timestamp,
            }
        )
        write_json_atomic(registry.writer_lease_path(worktree_id), reclaimed)
        if previous_holder_run:
            try:
                previous = registry.load_run(previous_holder_run)
            except SessionctlError:
                previous = None
            if previous is not None:
                _set_run_status(previous, 'BLOCKED')
                previous['leaseBlockReason'] = (
                    f"writer lease epoch {expected_epoch} was reclaimed by {current['runId']}"
                )
                previous['updatedAt'] = timestamp
                audit_run(
                    registry,
                    previous,
                    'WRITER_LEASE_RECLAIMED_FROM_RUN',
                    at=timestamp,
                    epoch=expected_epoch,
                    newEpoch=expected_epoch + 1,
                    reclaimedByRunId=current['runId'],
                )
                registry.save_run(previous)
        audit_run(
            registry,
            current,
            'WRITER_LEASE_RECLAIMED',
            at=timestamp,
            previousHolderRunId=previous_holder_run,
            previousHolderSessionId=previous_holder_session,
            epoch=expected_epoch,
            newEpoch=expected_epoch + 1,
            ownerAlive=owner_alive,
            heartbeatAgeSeconds=heartbeat_age,
        )
        current['updatedAt'] = timestamp
        registry.save_run(current)
        return (current, reclaimed)


def _lease_cli_record(
    *, client: str, session_id: str, cwd: Path, parent_run_id: str = ''
) -> tuple[Registry, dict[str, Any], bool]:
    """按 CLI 身份解析唯一当前运行；subagent 仅可继承已验证的父运行记录。"""
    checkout = resolve_checkout_root(cwd)
    registry = Registry(checkout)
    with registry.locked(client=client, session_id=session_id, run_id=parent_run_id):
        if parent_run_id:
            record = registry.load_run(_validate_identifier(parent_run_id, 'parent run id'))
            if record.get('client') != client:
                raise SessionctlError('subagent client does not match parent run')
            _validate_lease_checkout(registry, record)
            if Path(str(record['checkoutRoot'])).resolve() != checkout:
                raise SessionctlError('subagent checkout does not match parent run')
            return (registry, record, True)
        facts = _checkout_snapshot(checkout)
        matches = [
            item
            for item in registry.all_runs()
            if _record_matches_bootstrap(item, client=client, session_id=session_id, facts=facts)
        ]
        if len(matches) != 1:
            raise SessionctlError('lease operation requires exactly one current Session run')
        return (registry, matches[0], False)


def cmd_lease(args: argparse.Namespace) -> int:
    """把 lease 子命令分派到状态机服务，并以统一 JSON 返回更新后的权威记录。"""
    parent_run_id = '' if args.lease_action == 'reclaim' else args.parent_run_id or ''
    registry, record, inherited = _lease_cli_record(
        client=args.client,
        session_id=args.session_id,
        cwd=Path(args.cwd),
        parent_run_id=parent_run_id,
    )
    action = args.lease_action
    if action == 'read-ready':
        payload = mark_read_only_ready(registry, record)
    elif action == 'acquire':
        owner_pid = args.owner_pid if args.owner_pid is not None else os.getppid()
        payload, _ = acquire_writer_lease(
            registry,
            record,
            owner_pid=owner_pid,
            owner_start_time=args.owner_start_time or _pid_start_time(owner_pid),
        )
    elif action == 'heartbeat':
        payload, _ = heartbeat_writer_lease(
            registry, record, expected_epoch=args.epoch, fencing_token=args.fencing_token
        )
    elif action == 'release':
        payload, _ = release_writer_lease(
            registry,
            record,
            expected_epoch=args.epoch,
            fencing_token=args.fencing_token,
            reason=args.reason,
            inherited=inherited,
        )
    else:
        updated, lease = reclaim_writer_lease(
            registry,
            record,
            expected_epoch=args.expected_epoch,
            expected_holder_run_id=args.expected_holder_run_id,
            expected_holder_session_id=args.expected_holder_session_id,
            stale_after_seconds=args.stale_after_seconds,
        )
        payload = {'record': updated, 'lease': lease}
    emit_json(payload)
    return 0
