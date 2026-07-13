"""负责在属主私有目录持久化 Session 记录、锁元数据与审计事件；不负责判定 Git 事实；由 lifecycle、lease 与 finalize 调用。"""

from __future__ import annotations

import fcntl
import json
import os
import re
import stat
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

from scripts.agent_runtime.locks import _pid_start_time
from scripts.agent_runtime.storage import load_json, write_json_atomic
from scripts.agent_runtime.storage import utc_now as now_utc

from .contract import (
    ensure_private_directory,
    resolve_checkout_root,
    resolve_primary_repo_root,
    resolve_repo_key,
    resolve_runtime_root,
    validate_run_record,
)
from .errors import SessionctlError

if TYPE_CHECKING:
    from collections.abc import Iterable

REGISTRY_VERSION = 2
IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _validate_identifier(value: str, label: str) -> str:
    if not IDENTIFIER_PATTERN.fullmatch(value):
        raise SessionctlError(f'invalid {label}: {value!r}')
    return value


class Registry:
    """管理仓库隔离的运行记录、writer lease 路径、锁元数据与审计文件。"""

    def __init__(self, repo_root: Path):
        self.repo_root = resolve_checkout_root(repo_root)
        self.primary_repo_root = resolve_primary_repo_root(self.repo_root)
        self.repo_key = resolve_repo_key(self.repo_root)
        self.root = resolve_runtime_root(self.repo_root)
        self.runs_dir = ensure_private_directory(self.root / 'runs', root=self.root)
        self.locks_dir = ensure_private_directory(self.root / 'locks', root=self.root)
        self.writer_leases_dir = ensure_private_directory(
            self.root / 'writer-leases', root=self.root
        )
        self.mutation_locks_dir = ensure_private_directory(
            self.locks_dir / 'checkout-mutations', root=self.root
        )
        self.audit_dir = ensure_private_directory(self.root / 'audit', root=self.root)
        self.index_path = self.runs_dir / 'index.json'
        self.lock_path = self.locks_dir / 'registry.lock'
        self._lock_descriptor: int | None = None
        self._lock_metadata: dict[str, Any] = {}

    def writer_lease_path(self, worktree_id: str) -> Path:
        """校验 worktree 标识符后返回权威 writer lease 路径，阻止路径注入。"""
        return self.writer_leases_dir / f"{_validate_identifier(worktree_id, 'worktree id')}.json"

    @contextmanager
    def _metadata_locked(self, path: Path, metadata: dict[str, Any]) -> Iterable[int]:
        """以 flock 独占文件并持久化 owner 与递增 epoch；退出前记录释放时间。"""
        flags = os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0)
        descriptor = os.open(path, flags, 0o600)
        try:
            opened = os.fstat(descriptor)
            if not stat.S_ISREG(opened.st_mode):
                raise SessionctlError(f'lock is not a regular file: {path}')
            if hasattr(os, 'geteuid') and opened.st_uid != os.geteuid():
                raise SessionctlError(f'lock is not owned by current user: {path}')
            os.fchmod(descriptor, 0o600)
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            try:
                previous = self._read_lock_metadata(descriptor)
                try:
                    epoch = int(previous.get('epoch') or 0) + 1
                except (TypeError, ValueError):
                    epoch = 1
                timestamp = now_utc()
                owner_uid = os.geteuid() if hasattr(os, 'geteuid') else os.getuid()
                metadata.update(
                    schemaVersion=REGISTRY_VERSION,
                    owner=f'uid:{owner_uid}',
                    ownerUid=owner_uid,
                    pid=os.getpid(),
                    processStartTime=_pid_start_time(os.getpid()),
                    repoKey=self.repo_key,
                    epoch=epoch,
                    acquiredAt=timestamp,
                    updatedAt=timestamp,
                )
                self._persist_lock_metadata(descriptor, metadata)
                yield descriptor
            finally:
                metadata['releasedAt'] = now_utc()
                metadata['updatedAt'] = metadata['releasedAt']
                self._persist_lock_metadata(descriptor, metadata)
                fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)

    @contextmanager
    def checkout_mutation_locked(
        self, worktree_id: str, *, client: str, session_id: str, run_id: str
    ) -> Iterable[None]:
        """按 worktree 获取变更互斥锁，作为 writer lease 操作的第一层锁。"""
        worktree_id = _validate_identifier(worktree_id, 'worktree id')
        path = self.mutation_locks_dir / f'{worktree_id}.lock'
        metadata = {
            'client': client,
            'sessionId': session_id,
            'runId': run_id,
            'worktreeId': worktree_id,
        }
        with self._metadata_locked(path, metadata):
            yield

    @contextmanager
    def locked(self, *, client: str = '', session_id: str = '', run_id: str = '') -> Iterable[None]:
        """获取 Registry 全局锁并暴露当前 descriptor，供锁内更新 owner 上下文。"""
        metadata = {
            'client': client,
            'sessionId': session_id,
            'runId': run_id,
            'checkoutRoot': str(self.repo_root),
        }
        with self._metadata_locked(self.lock_path, metadata) as descriptor:
            self._lock_descriptor = descriptor
            self._lock_metadata = metadata
            try:
                yield
            finally:
                self._lock_descriptor = None
                self._lock_metadata = {}

    @staticmethod
    def _read_lock_metadata(descriptor: int) -> dict[str, Any]:
        """从已打开 descriptor 读取锁元数据；空值、坏编码和非映射均视为空。"""
        os.lseek(descriptor, 0, os.SEEK_SET)
        raw = os.read(descriptor, 64 * 1024)
        if not raw.strip():
            return {}
        try:
            data = json.loads(raw.decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _persist_lock_metadata(descriptor: int, metadata: dict[str, Any]) -> None:
        """在持锁 descriptor 上截断、完整写入并 fsync 元数据，拒绝短写停滞。"""
        payload = (json.dumps(metadata, indent=2, sort_keys=True) + '\n').encode('utf-8')
        os.lseek(descriptor, 0, os.SEEK_SET)
        os.ftruncate(descriptor, 0)
        remaining = memoryview(payload)
        while remaining:
            written = os.write(descriptor, remaining)
            if written <= 0:
                raise SessionctlError('Registry lock metadata write made no progress')
            remaining = remaining[written:]
        os.fsync(descriptor)

    def _write_lock_metadata(self) -> None:
        """要求 Registry 锁仍被当前实例持有，再持久化最新锁上下文。"""
        if self._lock_descriptor is None:
            raise SessionctlError('Registry lock metadata update requires held lock')
        self._persist_lock_metadata(self._lock_descriptor, self._lock_metadata)

    def update_lock_context(
        self, *, client: str = '', session_id: str = '', run_id: str = ''
    ) -> None:
        """在已持锁期间补充 client、Session 与 run 身份并刷新元数据。"""
        if self._lock_descriptor is None:
            raise SessionctlError('Registry lock context update requires held lock')
        if client:
            self._lock_metadata['client'] = client
        if session_id:
            self._lock_metadata['sessionId'] = session_id
        if run_id:
            self._lock_metadata['runId'] = run_id
        self._lock_metadata['updatedAt'] = now_utc()
        self._write_lock_metadata()

    def _run_path(self, run_id: str) -> Path:
        return self.runs_dir / f"{_validate_identifier(run_id, 'run id')}.json"

    def load_index(self) -> dict[str, Any]:
        """读取运行索引；缺失时返回带当前 schema 的空索引。"""
        return load_json(self.index_path, {'schemaVersion': REGISTRY_VERSION, 'runs': []})

    def save_index(self, run_ids: list[str]) -> None:
        """去重排序 run 标识符并原子写入 Registry 索引。"""
        write_json_atomic(
            self.index_path, {'schemaVersion': REGISTRY_VERSION, 'runs': sorted(set(run_ids))}
        )

    def load_run(self, run_id: str) -> dict[str, Any]:
        """读取指定 run 记录；未知标识符显式抛错而不返回伪造默认值。"""
        path = self._run_path(run_id)
        record = load_json(path, {})
        if not record:
            raise SessionctlError(f'unknown run_id: {run_id}')
        return record

    def save_run(self, record: dict[str, Any]) -> None:
        """先验证完整运行契约，再原子写记录并确保索引包含该 run。"""
        validate_run_record(record)
        write_json_atomic(self._run_path(str(record['runId'])), record)
        index = self.load_index()
        run_ids = [str(item) for item in index.get('runs', [])]
        if str(record['runId']) not in run_ids:
            run_ids.append(str(record['runId']))
        self.save_index(run_ids)

    def all_runs(self) -> list[dict[str, Any]]:
        """按索引读取现存运行记录，忽略已消失文件但不扫描未登记记录。"""
        index = self.load_index()
        records = []
        for run_id in index.get('runs', []):
            record = load_json(self._run_path(str(run_id)), {})
            if record:
                records.append(record)
        return records

    def remove_run_record(
        self, run_id: str, *, expected_repo_key: str, expected_checkout_root: Path
    ) -> None:
        """在持锁和身份复核后删除精确 run 文件，并同步更新索引。"""
        if self._lock_descriptor is None:
            raise SessionctlError('run record removal requires the Registry lock')
        current = self.load_run(run_id)
        if current.get('repoKey') != expected_repo_key or expected_repo_key != self.repo_key:
            raise SessionctlError('cleanup run does not belong to this Registry')
        recorded_checkout = Path(str(current.get('checkoutRoot') or '')).expanduser().resolve()
        if recorded_checkout != expected_checkout_root.resolve():
            raise SessionctlError('cleanup run checkout identity changed before removal')
        path = self._run_path(run_id)
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise SessionctlError(f'refusing unsafe run record removal: {path}')
        if hasattr(os, 'geteuid') and metadata.st_uid != os.geteuid():
            raise SessionctlError(f'run record is not owned by current user: {path}')
        path.unlink()
        index = self.load_index()
        self.save_index([str(item) for item in index.get('runs', []) if str(item) != run_id])

    def write_audit(self, event: dict[str, Any]) -> None:
        """为审计事件生成不可预测文件名并原子持久化，避免覆盖既有证据。"""
        event_id = f'{int(time.time_ns())}-{uuid.uuid4().hex[:12]}'
        write_json_atomic(self.audit_dir / f'{event_id}.json', event)
