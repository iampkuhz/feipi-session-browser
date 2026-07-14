"""负责 Lifecycle snapshot、CAS、audit 与 Attempt journal 的权威持久化。

不负责 Git 或 Gate 判定，由 controller 调用。每个 Session 使用独立的有界锁。状态先写 write-once audit/journal，再原子替换
snapshot；进程若在两步之间崩溃，后续读取会从 append-only audit 重放而不是猜测状态。
"""

from __future__ import annotations

import copy
import json
import os
import re
import stat
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

from scripts.agent_runtime.session.contract import ensure_private_directory
from scripts.agent_runtime.storage import StorageError, load_json, utc_now, write_json_atomic

from .model import (
    FINISHED_ATTEMPT_STATUSES,
    LIFECYCLE_SCHEMA_VERSION,
    ChangeCAS,
    LifecycleModelError,
    attempt_fingerprint,
    cas_matches,
    current_change,
    new_attempt,
    replace_change,
    transition_change,
    validate_attempt,
    validate_change,
    validate_session,
)
from .model import (
    finish_attempt as finish_attempt_model,
)
from .model import (
    mark_attempt_child_started as mark_attempt_child_started_model,
)
from .model import (
    roll_next_change as roll_next_change_model,
)
from .runtime import BoundedMetadataLock, LockBusyError, LockInvariantError

DEFAULT_LOCK_TIMEOUT_SECONDS = 2.0
# 平台 Session identity 可包含 launcher 使用的 ``:``；仍禁止 slash、反斜杠、NUL
# 与前导点，确保它只能成为单个 runtime 目录组件。
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}$")
_SESSION_IDENTITY_FIELDS = (
    "schemaVersion",
    "sessionId",
    "client",
    "agentId",
    "repoKey",
    "gitCommonDir",
    "worktreeId",
    "checkoutRoot",
    "checkoutKind",
    "branch",
    "detached",
    "targetBranch",
    "primaryRepoRoot",
)


class ChangeStoreError(RuntimeError):
    """表示 lifecycle store 无法安全读取、追加或原子发布状态。"""


class ChangeStoreCorruptionError(ChangeStoreError):
    """表示 schema、JSON、journal 顺序或 write-once 文件已经损坏。"""


class ChangeStoreBusyError(ChangeStoreError):
    """表示有界等待到期；错误携带当前 owner，调用方应返回 BUSY_RETRYABLE。"""

    def __init__(self, session_id: str, owner: Mapping[str, Any], waited_seconds: float):
        super().__init__(f"Session lifecycle lock busy: {session_id}")
        self.session_id = session_id
        self.owner = dict(owner)
        self.waited_seconds = waited_seconds


class DuplicateAttemptError(ChangeStoreError):
    """表示相同完整指纹已经有 Attempt，禁止再次启动重 Gate child。"""

    def __init__(self, attempt: Mapping[str, Any]):
        super().__init__(f"Attempt fingerprint already recorded: {attempt.get('fingerprint', '')}")
        self.attempt = copy.deepcopy(dict(attempt))


def _identifier(value: str, label: str) -> str:
    if not _IDENTIFIER.fullmatch(value):
        raise ChangeStoreError(f"invalid {label}: {value!r}")
    return value


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(
        path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_once_json(path: Path, value: Mapping[str, Any]) -> None:
    """先 fsync 临时 inode，再用 hard-link 原子发布 write-once journal event。"""
    ensure_private_directory(path.parent)
    payload = (json.dumps(dict(value), sort_keys=True, separators=(",", ":")) + "\n").encode()
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    temporary = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    try:
        descriptor = os.open(temporary, flags, 0o600)
    except FileExistsError as exc:
        raise ChangeStoreCorruptionError(f"journal temporary path exists: {temporary}") from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ChangeStoreCorruptionError(f"journal event is not a regular file: {temporary}")
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise ChangeStoreError(f"journal write made no progress: {temporary}")
            offset += written
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    try:
        # link 不覆盖既有 final path；读者只能看到完整 inode，不会观察到半写 JSON。
        os.link(temporary, path, follow_symlinks=False)
        _fsync_directory(path.parent)
    except FileExistsError as exc:
        raise ChangeStoreCorruptionError(
            f"append-only journal path already exists: {path}"
        ) from exc
    finally:
        temporary.unlink(missing_ok=True)


def _read_mapping(path: Path) -> dict[str, Any]:
    try:
        value = load_json(path)
    except (OSError, ValueError, StorageError) as exc:
        raise ChangeStoreCorruptionError(f"cannot read lifecycle JSON: {path}: {exc}") from exc
    if value.get("schemaVersion") != LIFECYCLE_SCHEMA_VERSION:
        raise ChangeStoreCorruptionError(
            f"unsupported lifecycle schemaVersion in {path}: {value.get('schemaVersion')!r}"
        )
    return value


class ChangeStore:
    """管理多个 Session 的原子 snapshot 和 append-only lifecycle journals。"""

    def __init__(self, root: Path, *, lock_timeout_seconds: float = DEFAULT_LOCK_TIMEOUT_SECONDS):
        if lock_timeout_seconds < 0:
            raise ValueError("lock_timeout_seconds must be non-negative")
        self.root = ensure_private_directory(Path(root))
        self.sessions_dir = ensure_private_directory(self.root / "sessions", root=self.root)
        self.locks_dir = ensure_private_directory(self.root / "locks", root=self.root)
        self.lock_timeout_seconds = float(lock_timeout_seconds)

    def _session_dir(self, session_id: str) -> Path:
        return self.sessions_dir / _identifier(session_id, "sessionId")

    def _snapshot_path(self, session_id: str) -> Path:
        return self._session_dir(session_id) / "snapshot.json"

    def _audit_dir(self, session_id: str) -> Path:
        return self._session_dir(session_id) / "audit"

    def _attempt_dir(self, session_id: str) -> Path:
        return self._session_dir(session_id) / "attempt-journal"

    def _lock_path(self, session_id: str) -> Path:
        """返回 Session 独占锁路径；不创建或获取锁。"""
        return self.locks_dir / f"{_identifier(session_id, 'sessionId')}.lock"

    @contextmanager
    def _locked(self, session_id: str, *, change_id: str, epoch: int) -> Iterable[dict[str, Any]]:
        """复用唯一 bounded runtime lock；Store 不再维护第二套 flock owner 语义。"""
        try:
            with BoundedMetadataLock(
                self._lock_path(session_id),
                session_id=session_id,
                change_id=change_id,
                epoch=epoch,
                timeout_seconds=self.lock_timeout_seconds,
            ) as lock:
                yield lock.metadata
        except LockBusyError as exc:
            raise ChangeStoreBusyError(session_id, exc.owner, exc.waited_seconds) from exc
        except LockInvariantError as exc:
            raise ChangeStoreCorruptionError(f"lifecycle lock invariant failed: {exc}") from exc

    @staticmethod
    def _journal_paths(directory: Path, label: str) -> list[tuple[int, Path]]:
        """只用文件名前缀校验完整 sequence；snapshot 热路径不反复解析旧 JSON。"""
        if not directory.exists():
            return []
        result: list[tuple[int, Path]] = []
        for path in sorted(directory.glob("*.json")):
            prefix = path.name.split('-', 1)[0]
            if len(prefix) != 20 or not prefix.isdigit():
                raise ChangeStoreCorruptionError(f"invalid {label} journal filename: {path}")
            result.append((int(prefix), path))
        sequences = [sequence for sequence, _path in result]
        if sequences != list(range(1, len(result) + 1)):
            raise ChangeStoreCorruptionError(f"{label} journal sequences must be contiguous")
        return result

    def _audit_events(self, session_id: str, *, after_sequence: int = 0) -> list[dict[str, Any]]:
        directory = self._audit_dir(session_id)
        paths = self._journal_paths(directory, "audit")
        events = [_read_mapping(path) for sequence, path in paths if sequence > after_sequence]
        seen: set[int] = set()
        previous = after_sequence
        for event in sorted(events, key=lambda item: int(item.get("sequence") or -1)):
            if event.get("journalType") != "AUDIT" or event.get("sessionId") != session_id:
                raise ChangeStoreCorruptionError("audit event identity does not match its Session")
            sequence = event.get("sequence")
            if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
                raise ChangeStoreCorruptionError("audit sequence must be a positive integer")
            if sequence in seen or sequence != previous + 1:
                raise ChangeStoreCorruptionError("audit sequences must be unique and contiguous")
            seen.add(sequence)
            previous = sequence
            after = event.get("sessionAfter")
            try:
                validate_session(after)
            except LifecycleModelError as exc:
                raise ChangeStoreCorruptionError(f"audit sessionAfter is invalid: {exc}") from exc
            if after["auditSequence"] != sequence:
                raise ChangeStoreCorruptionError("audit sessionAfter sequence does not match event")
        return sorted(events, key=lambda item: item["sequence"])

    def _load_unlocked(self, session_id: str) -> dict[str, Any]:
        """重放 snapshot 之后的 journal 尾部；调用者负责写入互斥。"""
        path = self._snapshot_path(session_id)
        if path.exists():
            snapshot = _read_mapping(path)
            try:
                validate_session(snapshot)
            except LifecycleModelError as exc:
                raise ChangeStoreCorruptionError(f"invalid lifecycle snapshot: {exc}") from exc
            events = self._audit_events(session_id, after_sequence=int(snapshot["auditSequence"]))
        else:
            events = self._audit_events(session_id)
        if not path.exists() and events:
            snapshot = copy.deepcopy(events[0]["sessionAfter"])
        elif not path.exists():
            raise ChangeStoreError(f"unknown lifecycle Session: {session_id}")
        for event in events:
            if event["sequence"] > snapshot["auditSequence"]:
                snapshot = copy.deepcopy(event["sessionAfter"])
        # Attempt event 先于 audit/snapshot fsync；若进程恰好在边界崩溃，用事件携带的
        # changeAfter 恢复 currentAttempt/state，禁止为同一指纹创建第二个 Attempt。
        for event in self._attempt_events(
            session_id, after_sequence=int(snapshot["attemptJournalSequence"])
        ):
            after = event.get("changeAfter")
            if after and event["sequence"] > snapshot["attemptJournalSequence"]:
                snapshot = replace_change(snapshot, after)
                snapshot["attemptJournalSequence"] = event["sequence"]
        validate_session(snapshot)
        return snapshot

    def load_session(self, session_id: str) -> dict[str, Any]:
        """读取 snapshot 并重放 fsync 后但尚未 materialize 的 audit tail。"""
        return self._load_unlocked(_identifier(session_id, "sessionId"))

    def _append_audit(
        self,
        session: Mapping[str, Any],
        *,
        event_type: str,
        details: Mapping[str, Any],
    ) -> dict[str, Any]:
        result = copy.deepcopy(dict(session))
        sequence = int(result["auditSequence"]) + 1
        result["auditSequence"] = sequence
        event = {
            "schemaVersion": LIFECYCLE_SCHEMA_VERSION,
            "journalType": "AUDIT",
            "eventType": event_type,
            "sessionId": result["sessionId"],
            "changeId": result["currentChangeId"],
            "sequence": sequence,
            "at": utc_now(),
            "details": copy.deepcopy(dict(details)),
            "sessionAfter": result,
        }
        path = self._audit_dir(result["sessionId"]) / f"{sequence:020d}-{uuid.uuid4().hex}.json"
        _write_once_json(path, event)
        return result

    def _append_attempt_event(
        self,
        session: Mapping[str, Any],
        *,
        event_type: str,
        attempt: Mapping[str, Any],
    ) -> dict[str, Any]:
        validate_attempt(attempt)
        result = copy.deepcopy(dict(session))
        sequence = int(result["attemptJournalSequence"]) + 1
        result["attemptJournalSequence"] = sequence
        event = {
            "schemaVersion": LIFECYCLE_SCHEMA_VERSION,
            "journalType": "ATTEMPT",
            "eventType": event_type,
            "sessionId": result["sessionId"],
            "changeId": attempt["changeId"],
            "attemptId": attempt["attemptId"],
            "sequence": sequence,
            "at": utc_now(),
            "attempt": copy.deepcopy(dict(attempt)),
            # Attempt journal 只携带恢复所需的当前 Change，避免长期 Session 的全部
            # 历史 Change 在每个 event 中二次膨胀；snapshot 仍保存完整 Session。
            "changeAfter": current_change(result),
            "attemptJournalSequence": sequence,
        }
        path = self._attempt_dir(result["sessionId"]) / (
            f"{sequence:020d}-{attempt['attemptId']}-{uuid.uuid4().hex}.json"
        )
        _write_once_json(path, event)
        return result

    def create_session(self, session: Mapping[str, Any]) -> dict[str, Any]:
        """首次创建 Session；相同 identity 重入幂等，冲突 identity 关闭失败。"""
        validate_session(session)
        session_id = str(session["sessionId"])
        with self._locked(session_id, change_id="session-bootstrap", epoch=1):
            path = self._snapshot_path(session_id)
            audit_exists = any(self._audit_dir(session_id).glob("*.json"))
            if path.exists() or audit_exists:
                existing = self._load_unlocked(session_id)
                if all(existing.get(key) == session.get(key) for key in _SESSION_IDENTITY_FIELDS):
                    return existing
                raise ChangeStoreError(f"lifecycle Session identity already exists: {session_id}")
            result = self._append_audit(session, event_type="SESSION_CREATED", details={})
            write_json_atomic(path, result)
            return result

    @staticmethod
    def _find_change(session: Mapping[str, Any], change_id: str) -> dict[str, Any]:
        for change in session["changes"]:
            if change["changeId"] == change_id:
                return copy.deepcopy(change)
        raise ChangeStoreError(f"unknown lifecycle Change: {change_id}")

    def transition(
        self,
        session_id: str,
        change_id: str,
        *,
        target_state: str,
        expected: ChangeCAS,
        updates: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """在 Session 锁内执行完整 CAS、追加 audit，再原子发布 snapshot。"""
        observed = self._load_unlocked(session_id)
        observed_change = self._find_change(observed, change_id)
        with self._locked(
            session_id, change_id=change_id, epoch=int(observed_change["changeEpoch"])
        ):
            session = self._load_unlocked(session_id)
            before = self._find_change(session, change_id)
            after = transition_change(
                before, target_state=target_state, expected=expected, updates=updates
            )
            if after == before:
                return session
            updated = replace_change(session, after)
            updated = self._append_audit(
                updated,
                event_type="CHANGE_TRANSITION",
                details={
                    "fromState": before["state"],
                    "toState": after["state"],
                    "fromVersion": before["stateVersion"],
                    "toVersion": after["stateVersion"],
                    "candidateTree": after["candidateTree"],
                    "attemptId": after["currentAttemptId"],
                    "commitSha": after["commitSha"],
                },
            )
            write_json_atomic(self._snapshot_path(session_id), updated)
            return updated

    def roll_next_change(self, session_id: str, **kwargs: Any) -> dict[str, Any]:
        """在同一 Session 内创建第一或下一 Change，并持久化单调 changeEpoch。"""
        observed = self._load_unlocked(session_id)
        next_epoch = int(observed["changeEpoch"]) + 1
        next_change_id = str(kwargs.get("change_id") or "next-change")
        with self._locked(session_id, change_id=next_change_id, epoch=next_epoch):
            session = self._load_unlocked(session_id)
            updated = roll_next_change_model(session, **kwargs)
            updated = self._append_audit(
                updated,
                event_type="CHANGE_EPOCH_CREATED",
                details={
                    "changeId": updated["currentChangeId"],
                    "changeEpoch": updated["changeEpoch"],
                },
            )
            write_json_atomic(self._snapshot_path(session_id), updated)
            return updated

    def _attempt_events(self, session_id: str, *, after_sequence: int = 0) -> list[dict[str, Any]]:
        directory = self._attempt_dir(session_id)
        paths = self._journal_paths(directory, "Attempt")
        events = [_read_mapping(path) for sequence, path in paths if sequence > after_sequence]
        previous = after_sequence
        for event in sorted(events, key=lambda item: int(item.get("sequence") or -1)):
            if event.get("journalType") != "ATTEMPT" or event.get("sessionId") != session_id:
                raise ChangeStoreCorruptionError("Attempt journal identity does not match Session")
            sequence = event.get("sequence")
            if (
                isinstance(sequence, bool)
                or not isinstance(sequence, int)
                or sequence != previous + 1
            ):
                raise ChangeStoreCorruptionError("Attempt journal sequences must be contiguous")
            previous = sequence
            try:
                validate_attempt(event.get("attempt"))
            except LifecycleModelError as exc:
                raise ChangeStoreCorruptionError(f"invalid Attempt journal event: {exc}") from exc
            after = event.get("changeAfter")
            try:
                validate_change(after)
            except LifecycleModelError as exc:
                raise ChangeStoreCorruptionError(f"invalid Attempt changeAfter: {exc}") from exc
            if event.get("attemptJournalSequence") != sequence:
                raise ChangeStoreCorruptionError("Attempt journal sequence does not match event")
        return sorted(events, key=lambda item: item["sequence"])

    def list_attempts(self, session_id: str, change_id: str | None = None) -> list[dict[str, Any]]:
        """归并 start/finish event，返回每个 Attempt 的最后持久结果。"""
        by_id: dict[str, dict[str, Any]] = {}
        order: list[str] = []
        for event in self._attempt_events(session_id):
            attempt = event["attempt"]
            if change_id is not None and attempt["changeId"] != change_id:
                continue
            attempt_id = attempt["attemptId"]
            if event["eventType"] == "ATTEMPT_STARTED":
                if attempt_id in by_id or attempt["status"] != "STARTED":
                    raise ChangeStoreCorruptionError(
                        "Attempt start event is duplicated or finished"
                    )
                by_id[attempt_id] = copy.deepcopy(attempt)
                order.append(attempt_id)
            elif event["eventType"] == "ATTEMPT_FINISHED":
                previous = by_id.get(attempt_id)
                if not previous or previous["status"] != "STARTED":
                    raise ChangeStoreCorruptionError("Attempt finish event has no unique start")
                for key in (
                    "sessionId",
                    "changeId",
                    "changeEpoch",
                    "attemptId",
                    "fingerprint",
                    "candidateTree",
                    "manifestHash",
                    "planFingerprint",
                    "commandFingerprint",
                    "environmentFingerprint",
                ):
                    if previous[key] != attempt[key]:
                        raise ChangeStoreCorruptionError(f"Attempt finish rewrites immutable {key}")
                by_id[attempt_id] = copy.deepcopy(attempt)
            elif event['eventType'] == 'ATTEMPT_CHILD_STARTED':
                previous = by_id.get(attempt_id)
                if not previous or previous['status'] != 'STARTED':
                    raise ChangeStoreCorruptionError('Attempt child start has no active Attempt')
                for key in (
                    'sessionId',
                    'changeId',
                    'changeEpoch',
                    'attemptId',
                    'fingerprint',
                    'candidateTree',
                    'manifestHash',
                    'planFingerprint',
                    'commandFingerprint',
                    'environmentFingerprint',
                ):
                    if previous[key] != attempt[key]:
                        raise ChangeStoreCorruptionError(
                            f'Attempt child start rewrites immutable {key}'
                        )
                if attempt['actualHeavyChildCount'] <= previous['actualHeavyChildCount']:
                    raise ChangeStoreCorruptionError(
                        'Attempt child count must increase monotonically'
                    )
                by_id[attempt_id] = copy.deepcopy(attempt)
            else:
                raise ChangeStoreCorruptionError(
                    f"unknown Attempt eventType: {event.get('eventType')}"
                )
        return [by_id[item] for item in order]

    def find_attempt_by_fingerprint(
        self, session_id: str, change_id: str, fingerprint: str
    ) -> dict[str, Any] | None:
        """查询相同 candidate/environment/plan/command 的权威缓存结果。"""
        for attempt in reversed(self.list_attempts(session_id, change_id)):
            if attempt["fingerprint"] == fingerprint:
                return attempt
        return None

    def mark_attempt_child_started(
        self,
        session_id: str,
        change_id: str,
        attempt_id: str,
        *,
        expected: ChangeCAS,
        child_count: int = 1,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """在 child 调用前持久化进程计数；fixture 失败不会伪造 heavy child。"""
        observed = self._load_unlocked(session_id)
        observed_change = self._find_change(observed, change_id)
        with self._locked(
            session_id, change_id=change_id, epoch=int(observed_change['changeEpoch'])
        ):
            session = self._load_unlocked(session_id)
            change = self._find_change(session, change_id)
            cas_matches(change, expected)
            attempts = {
                item['attemptId']: item for item in self.list_attempts(session_id, change_id)
            }
            started = attempts.get(attempt_id)
            if started is None:
                raise ChangeStoreError(f'unknown lifecycle Attempt: {attempt_id}')
            updated_attempt = mark_attempt_child_started_model(started, child_count=child_count)
            updated = self._append_attempt_event(
                session,
                event_type='ATTEMPT_CHILD_STARTED',
                attempt=updated_attempt,
            )
            updated = self._append_audit(
                updated,
                event_type='ATTEMPT_CHILD_STARTED',
                details={
                    'attemptId': attempt_id,
                    'actualHeavyChildCount': updated_attempt['actualHeavyChildCount'],
                },
            )
            write_json_atomic(self._snapshot_path(session_id), updated)
            return updated, updated_attempt

    def start_attempt(
        self,
        session_id: str,
        change_id: str,
        *,
        expected: ChangeCAS,
        candidate_tree: str,
        manifest_hash: str,
        plan_fingerprint: str,
        command_fingerprint: str,
        environment_fingerprint: str,
        receipt_path: str,
        artifact_path: str,
        heavy_child_started: bool = True,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """原子登记新 Attempt 并进入 VALIDATING；相同指纹已有记录时拒绝重跑。"""
        fingerprint = attempt_fingerprint(
            candidate_tree=candidate_tree,
            manifest_hash=manifest_hash,
            plan_fingerprint=plan_fingerprint,
            command_fingerprint=command_fingerprint,
            environment_fingerprint=environment_fingerprint,
        )
        observed = self._load_unlocked(session_id)
        observed_change = self._find_change(observed, change_id)
        with self._locked(
            session_id, change_id=change_id, epoch=int(observed_change["changeEpoch"])
        ):
            session = self._load_unlocked(session_id)
            existing = self.find_attempt_by_fingerprint(session_id, change_id, fingerprint)
            if existing is not None:
                raise DuplicateAttemptError(existing)
            before = self._find_change(session, change_id)
            sequence = int(before["attemptSequence"]) + 1
            attempt_id = f"attempt-{before['changeEpoch']}-{sequence:04d}"
            attempt = new_attempt(
                session_id=session_id,
                change_id=change_id,
                change_epoch=before["changeEpoch"],
                attempt_id=attempt_id,
                candidate_tree=candidate_tree,
                manifest_hash=manifest_hash,
                plan_fingerprint=plan_fingerprint,
                command_fingerprint=command_fingerprint,
                environment_fingerprint=environment_fingerprint,
                receipt_path=receipt_path,
                artifact_path=artifact_path,
                heavy_child_started=heavy_child_started,
            )
            after = transition_change(
                before,
                target_state="VALIDATING",
                expected=expected,
                updates={
                    "candidateTree": candidate_tree,
                    "manifestHash": manifest_hash,
                    "currentAttemptId": attempt_id,
                    "attemptSequence": sequence,
                },
            )
            updated = replace_change(session, after)
            updated = self._append_attempt_event(
                updated, event_type="ATTEMPT_STARTED", attempt=attempt
            )
            updated = self._append_audit(
                updated,
                event_type="ATTEMPT_STARTED",
                details={
                    "attemptId": attempt_id,
                    "fingerprint": fingerprint,
                    "candidateTree": candidate_tree,
                    "actualHeavyChildCount": attempt["actualHeavyChildCount"],
                },
            )
            write_json_atomic(self._snapshot_path(session_id), updated)
            return updated, attempt

    def finish_attempt(
        self,
        session_id: str,
        change_id: str,
        attempt_id: str,
        *,
        expected: ChangeCAS,
        status: str,
        independent_root_failures: Sequence[Mapping[str, Any]],
        dependent_blocked_count: int,
        receipt_path: str | None = None,
        artifact_path: str | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """完成当前 Attempt 并进入 VALIDATED 或 REPAIR_REQUIRED，旧 Attempt 被 CAS 拒绝。"""
        observed = self._load_unlocked(session_id)
        observed_change = self._find_change(observed, change_id)
        with self._locked(
            session_id, change_id=change_id, epoch=int(observed_change["changeEpoch"])
        ):
            session = self._load_unlocked(session_id)
            before = self._find_change(session, change_id)
            candidates = {
                item["attemptId"]: item for item in self.list_attempts(session_id, change_id)
            }
            started = candidates.get(attempt_id)
            if started is None:
                raise ChangeStoreError(f"unknown lifecycle Attempt: {attempt_id}")
            target_state = "VALIDATED" if status == "PASS" else "REPAIR_REQUIRED"
            # 先执行 Change CAS，再读取/结束 Attempt；这样旧 attemptId 即使已有结果，
            # 也只能得到 stale fencing，而不能覆盖当前正在运行的新 Attempt。
            after = transition_change(before, target_state=target_state, expected=expected)
            finished = finish_attempt_model(
                started,
                status=status,
                independent_root_failures=independent_root_failures,
                dependent_blocked_count=dependent_blocked_count,
                receipt_path=receipt_path,
                artifact_path=artifact_path,
            )
            updated = replace_change(session, after)
            updated = self._append_attempt_event(
                updated, event_type="ATTEMPT_FINISHED", attempt=finished
            )
            updated = self._append_audit(
                updated,
                event_type=f"ATTEMPT_{status}",
                details={
                    "attemptId": attempt_id,
                    "fingerprint": finished["fingerprint"],
                    "independentRootFailureCount": len(independent_root_failures),
                    "dependentBlockedCount": dependent_blocked_count,
                },
            )
            write_json_atomic(self._snapshot_path(session_id), updated)
            return updated, finished

    def attempt_metrics(self, session_id: str) -> dict[str, int]:
        """统计所有 PASS/FAIL/BLOCKED/STARTED Attempt 与真实重 Gate child。"""
        attempts = self.list_attempts(session_id)
        return {
            # Attempt 在 child 启动前已原子登记，所以 FAIL/BLOCKED/启动失败都属于唯一
            # 重 Gate 尝试；actualHeavyChildren 另行反映真正产生的子进程数。
            "uniqueHeavyAttempts": len(attempts),
            "actualHeavyChildren": sum(int(item["actualHeavyChildCount"]) for item in attempts),
            "passedAttempts": sum(item["status"] == "PASS" for item in attempts),
            "failedAttempts": sum(item["status"] == "FAIL" for item in attempts),
            "blockedAttempts": sum(item["status"] == "BLOCKED" for item in attempts),
            "unfinishedAttempts": sum(
                item["status"] not in FINISHED_ATTEMPT_STATUSES for item in attempts
            ),
        }
