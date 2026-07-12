"""Stop 恢复域：私有写入、FileLock、重入、fencing 与审计。

不负责平台 Hook wrapper 配置；由 Hook 或 Stop runtime 调用。"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.harness.primary_session import ensure_private_directory
from scripts.harness.resource_lock import (
    _atomic_publish_lock,
    _fsync_directory,
    _pid_start_time,
    _read_lock_snapshot,
    _same_lock_epoch,
    process_is_alive,
)

from .evidence import git_dirty_hash, git_lines


def utc_now() -> str:
    """返回 UTC ISO-8601 时间。"""
    return datetime.now(UTC).isoformat().replace('+00:00', 'Z')


def write_private_json(path: Path, data: dict[str, Any]) -> None:
    """以 owner-only 权限原子写入 JSON，拒绝符号链接目标。"""
    ensure_private_directory(path.parent)
    if path.exists() and path.is_symlink():
        raise OSError(f'refusing symlink JSON path: {path}')
    temp = path.with_name(f'.{path.name}.{uuid.uuid4().hex}.tmp')
    descriptor = os.open(temp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
        os.chmod(path, 0o600)
    finally:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass


@dataclass
class FileLock:
    """基于文件系统的排他锁，支持 stale owner 回收。"""

    path: Path
    owner: dict[str, Any]
    acquired: bool = False
    fencing_token: str = ''
    lock_device: int = 0
    lock_inode: int = 0
    grace_seconds: float = 2.0
    reclaimed_owner: dict[str, Any] = field(default_factory=dict)
    reclaim_audit: dict[str, Any] = field(default_factory=dict)

    # 不跟随符号链接且不接受所有者变更地读取锁负载。
    def _read_payload(self) -> dict[str, Any]:
        snapshot = _read_lock_snapshot(self.path)
        return dict(snapshot.data) if snapshot and snapshot.data is not None else {}

    # 尝试获取锁。
    def acquire(self) -> bool:
        """尝试获取锁。"""
        self._remove_stale()
        ensure_private_directory(self.path.parent)
        payload = dict(self.owner)
        self.fencing_token = uuid.uuid4().hex
        payload.update(
            {
                'pid': os.getpid(),
                'processStartTime': _pid_start_time(os.getpid()),
                'fencingToken': self.fencing_token,
                'createdAt': utc_now(),
                'heartbeatAt': utc_now(),
                'graceSeconds': max(0.0, self.grace_seconds),
                'reclaimAudit': dict(self.reclaim_audit),
            }
        )
        try:
            published, complete = _atomic_publish_lock(self.path, payload)
        except OSError:
            return False
        if not published:
            return False
        self.lock_device = int(complete['lockDevice'])
        self.lock_inode = int(complete['lockInode'])
        self.acquired = True
        return True

    # 释放锁（需 fencing token 匹配）。
    def release(self) -> bool:
        """释放锁（需 fencing token 匹配）。"""
        if not self.acquired:
            return False
        released = False
        try:
            snapshot = _read_lock_snapshot(self.path)
            if (
                snapshot is None
                or snapshot.device != self.lock_device
                or snapshot.inode != self.lock_inode
                or not snapshot.data
                or snapshot.data.get('fencingToken') != self.fencing_token
            ):
                return False
            data = snapshot.data
            for field_name in ('runId', 'sessionId', 'worktreeId'):
                if str(data.get(field_name) or '') != str(self.owner.get(field_name) or ''):
                    return False
            self.path.unlink()
            _fsync_directory(self.path.parent)
            released = True
        except FileNotFoundError:
            pass
        finally:
            self.acquired = False
            self.fencing_token = ''
            self.lock_device = 0
            self.lock_inode = 0
        return released

    def heartbeat(self) -> bool:
        """仅在 inode 与 fencing token 仍属当前 epoch 时刷新 lock mtime。"""
        if not self.acquired:
            return False
        snapshot = _read_lock_snapshot(self.path)
        if (
            snapshot is None
            or snapshot.device != self.lock_device
            or snapshot.inode != self.lock_inode
            or not snapshot.data
            or snapshot.data.get('fencingToken') != self.fencing_token
        ):
            return False
        os.utime(self.path, None, follow_symlinks=False)
        return True

    # 回收已死亡 owner 的锁。
    def _remove_stale(self) -> None:
        snapshot = _read_lock_snapshot(self.path)
        if snapshot is None or snapshot.state in {'unsafe', 'foreign-uid'}:
            return
        if time.time() - snapshot.mtime < max(0.0, self.grace_seconds):
            return
        data = snapshot.data
        if data:
            for field_name in ('runId', 'sessionId', 'worktreeId'):
                expected = str(self.owner.get(field_name) or '')
                actual = str(data.get(field_name) or '')
                if actual and (not expected or actual != expected):
                    return
            pid = data.get('pid')
            started = str(data.get('processStartTime') or '')
            if isinstance(pid, int) and pid > 0 and process_is_alive(pid, started):
                return
        if snapshot.state == 'valid' and data:
            for field_name in ('runId', 'sessionId', 'worktreeId'):
                if not str(self.owner.get(field_name) or ''):
                    return
        if not _same_lock_epoch(self.path, snapshot):
            return
        try:
            self.path.unlink()
            _fsync_directory(self.path.parent)
            self.reclaimed_owner = dict(data or {'lockState': snapshot.state})
            self.reclaim_audit = {
                'event': 'STOP_LOCK_RECLAIMED',
                'previousState': snapshot.state,
                'previousDevice': snapshot.device,
                'previousInode': snapshot.inode,
                'previousUid': snapshot.uid,
                'reclaimedAt': utc_now(),
            }
        except OSError:
            return


MAX_CONTINUATIONS = 2


# 计算失败列表的稳定指纹。
def fingerprint(failures: list[str]) -> str:
    """参数：
        failures: 失败消息列表。

    返回：
        排序后失败内容的短哈希指纹。
    """
    raw = json.dumps(sorted(failures), ensure_ascii=False)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]


# 提取用于隔离停止恢复状态的身份字段。
def recovery_scope(record: dict[str, Any]) -> dict[str, str]:
    """参数：
        record: 当前会话记录。

    返回：
        恢复状态身份范围字典。
    """
    return {
        'runId': str(record.get('runId') or ''),
        'sessionId': str(record.get('sessionId') or ''),
        'worktreeId': str(record.get('worktreeId') or ''),
        'checkoutRoot': str(Path(str(record.get('checkoutRoot') or '')).resolve()),
        'repoKey': str(record.get('repoKey') or ''),
    }


# 判断已保存的停止恢复状态是否属于指定身份范围。
def _scope_matches(state: dict[str, Any], scope: dict[str, str]) -> bool:
    """参数：
        state: 已保存的恢复状态。
        scope: 期望的身份范围。

    返回：
        身份字段全部一致时返回 true，否则返回 false。
    """
    stored = state.get('scope')
    return isinstance(stored, dict) and all(
        str(stored.get(key) or '') == value for key, value in scope.items()
    )


# 从磁盘安全读取重入状态。
def load_reentry(path: Path) -> dict[str, Any]:
    """参数：
        path: 重入状态路径。

    返回：
        已读取的重入状态；读取失败时返回初始状态。
    """
    try:
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            return {'continuationCount': 0}
        if hasattr(os, 'geteuid') and metadata.st_uid != os.geteuid():
            return {'continuationCount': 0}
        descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
        try:
            opened = os.fstat(descriptor)
            if opened.st_ino != metadata.st_ino or opened.st_dev != metadata.st_dev:
                return {'continuationCount': 0}
            raw = os.read(descriptor, 1024 * 1024)
        finally:
            os.close(descriptor)
        data = json.loads(raw.decode('utf-8'))
    except Exception:
        return {'continuationCount': 0}
    return data if isinstance(data, dict) else {'continuationCount': 0}


# 持久化停止恢复审计事件。
def write_recovery_audit(
    audit_dir: Path,
    *,
    event: str,
    scope: dict[str, str],
    state: dict[str, Any],
) -> None:
    """参数：
        audit_dir: 恢复审计目录。
        event: 审计事件名称。
        scope: 当前恢复状态身份范围。
        state: 当前恢复状态。

    返回：
        无返回值。
    """
    ensure_private_directory(audit_dir)
    payload = {
        'schemaVersion': 1,
        'event': event,
        **scope,
        'continuationCount': int(state.get('continuationCount') or 0),
        'failureFingerprint': str(state.get('lastFailureFingerprint') or ''),
        'circuitState': str((state.get('circuitBreaker') or {}).get('state') or 'CLOSED'),
        'at': utc_now(),
    }
    write_private_json(
        audit_dir / f'{time.time_ns()}-{uuid.uuid4().hex[:12]}.json',
        payload,
    )


# 计算排除熔断消息后的稳定重入签名。
def stop_signature(
    repo_root: Path,
    failures: list[str],
    *,
    change_id: str,
) -> dict[str, str]:
    """参数：
        repo_root: 仓库根目录。
        failures: 失败消息列表。
        change_id: 变更标识。

    返回：
        包含提交、工作区、变更和失败指纹的签名字典。
    """
    head = git_lines(repo_root, 'rev-parse', 'HEAD')
    dirty_hash = git_dirty_hash(repo_root)
    stable_failures = [
        f
        for f in failures
        if f != 'continuation limit reached for identical Stop failure fingerprint'
    ]
    environment = {
        'baseUrl': os.environ.get('BASE_URL', ''),
        'projectPython': (repo_root / '.venv' / 'bin' / 'python').exists(),
        'nodeModules': (repo_root / 'node_modules').exists(),
        'playwright': (repo_root / 'node_modules' / '.bin' / 'playwright').exists(),
        'javaHome': os.environ.get('JAVA_HOME', ''),
    }
    environment_fingerprint = hashlib.sha256(
        json.dumps(environment, sort_keys=True).encode('utf-8')
    ).hexdigest()[:16]
    return {
        'head': head[0] if head else '',
        'dirtyHash': dirty_hash,
        'changeId': change_id,
        'failureFingerprint': fingerprint(stable_failures),
        'environmentFingerprint': environment_fingerprint,
    }


# 判断当前仓库状态是否命中已保存的相同重入失败。
def matching_reentry_failure(
    path: Path,
    repo_root: Path,
    scope: dict[str, str],
    *,
    change_id: str,
) -> tuple[bool, dict[str, Any], bool]:
    """参数：
        path: 重入状态路径。
        repo_root: 仓库根目录。
        scope: 当前恢复状态身份范围。
        change_id: 变更标识。

    返回：
        是否命中、已保存状态以及身份范围是否一致。
    """
    if not path.exists():
        return False, {'schemaVersion': 1, 'scope': scope, 'continuationCount': 0}, True
    state = load_reentry(path)
    if not _scope_matches(state, scope):
        return False, state, False
    sig = state.get('lastSignature')
    if not isinstance(sig, dict):
        return False, state, True
    current = stop_signature(repo_root, [], change_id=change_id)
    return (
        sig.get('head') == current['head']
        and sig.get('dirtyHash') == current['dirtyHash']
        and sig.get('changeId') == current['changeId']
        and sig.get('environmentFingerprint') == current['environmentFingerprint']
        and bool(state.get('lastFailures')),
        state,
        True,
    )


# 更新停止流程重入状态并写入恢复审计。
def update_reentry(
    path: Path,
    repo_root: Path,
    failures: list[str],
    *,
    scope: dict[str, str],
    audit_dir: Path,
    change_id: str,
) -> tuple[int, list[str]]:
    """参数：
        path: 重入状态路径。
        repo_root: 仓库根目录。
        failures: 当前失败消息列表。
        scope: 当前恢复状态身份范围。
        audit_dir: 恢复审计目录。
        change_id: 变更标识。

    返回：
        连续失败次数和附加失败列表。
    """
    state = load_reentry(path)
    if path.exists() and not _scope_matches(state, scope):
        return 0, ['run-scoped Stop recovery identity mismatch']
    state['schemaVersion'] = 1
    state['scope'] = scope
    sig = stop_signature(repo_root, failures, change_id=change_id)
    fp = sig['failureFingerprint']
    count = int(state.get('continuationCount') or 0)
    extra: list[str] = []
    if failures:
        if state.get('lastFailureFingerprint') == fp:
            count += 1
        else:
            count = 1
        if count > MAX_CONTINUATIONS:
            extra.append('continuation limit reached for identical Stop failure fingerprint')
        circuit = {
            'state': 'OPEN' if count > MAX_CONTINUATIONS else 'CLOSED',
            'reason': 'identical Stop failure fingerprint' if count > MAX_CONTINUATIONS else '',
        }
        if count > MAX_CONTINUATIONS:
            circuit['openedAt'] = utc_now()
        state.update(
            {
                'continuationCount': count,
                'lastFailureFingerprint': fp,
                'lastFailures': failures,
                'lastSignature': sig,
                'lastAttemptAt': utc_now(),
                'circuitBreaker': circuit,
            }
        )
    else:
        count = 0
        state.update(
            {
                'continuationCount': 0,
                'lastFailureFingerprint': '',
                'lastFailures': [],
                'lastSignature': {},
                'lastAttemptAt': utc_now(),
                'circuitBreaker': {'state': 'CLOSED', 'reason': ''},
            }
        )
    write_private_json(path, state)
    write_recovery_audit(
        audit_dir,
        event='STOP_RECOVERY_FAILURE_RECORDED' if failures else 'STOP_RECOVERY_CLEARED',
        scope=scope,
        state=state,
    )
    return count, extra


# 计算质量目标所需的排他资源锁名称。
def resource_names(targets: list[str]) -> list[str]:
    """参数：
        targets: 质量目标列表。

    返回：
        去重后的排他资源锁名称列表。
    """
    from scripts.gates.planner import target_parallel_meta

    names: list[str] = []
    for target in targets:
        for name in target_parallel_meta(target).get('exclusive_resources', []):
            if isinstance(name, str) and name not in names:
                names.append(name)
    return names
