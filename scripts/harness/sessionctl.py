#!/usr/bin/env python3
"""Registry, lease, Stop, and handoff CLI for an already selected checkout.

The client or external provider owns checkout creation and removal.  This
module only adopts the current Git checkout and manages run-scoped runtime
state; it never launches a client or creates, switches, or removes a worktree.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.harness.primary_session import (  # noqa: E402
    ACTIVE_WRITER_STATUSES,
    CHECKOUT_CREATORS,
    PrimarySessionValidationError,
    ensure_private_directory,
    resolve_checkout_identity,
    resolve_checkout_root,
    resolve_primary_repo_root,
    resolve_repo_key,
    stable_worktree_id,
    validate_checkout_record,
    validate_status_transition,
    resolve_runtime_root,
    validate_run_collisions,
    validate_run_record,
)
from scripts.harness.resource_lock import _pid_start_time, process_is_alive  # noqa: E402
from scripts.harness.stop_helpers import GitEvidenceError, collect_git_evidence  # noqa: E402

REGISTRY_VERSION = 2
DEFAULT_FORBIDDEN_PATHS = [".env", ".mcp.json", "data", "output", "tmp/agent_logs"]
IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
DEFAULT_LEASE_STALE_SECONDS = 300.0
LEASE_ACTIVE = "ACTIVE"
LEASE_RELEASED = "RELEASED"


class SessionctlError(RuntimeError):
    """Raised for expected CLI failures."""


class WriterLeaseConflict(SessionctlError):
    """Raised when another Session owns the checkout writer lease."""


class WriterLeaseFenced(SessionctlError):
    """Raised when a cached epoch/token no longer matches the checkout lease."""


# 识别工具调用的读写类别，并对未知命令采用保守判定。
def classify_tool_call(tool_name: str, tool_input: Mapping[str, Any] | None = None) -> str:
    """参数：
        tool_name: 工具名称。
        tool_input: 工具调用参数；未提供时按空输入处理。

    返回：
        返回 `mutation`、`read-only` 或 `validation` 分类。
    """

    normalized = re.sub(r"[^a-z]", "", tool_name.rsplit(".", 1)[-1].lower())
    if normalized in {"write", "edit", "multiedit", "applypatch", "patch"}:
        return "mutation"
    if normalized not in {"bash", "shell", "execcommand", "command"}:
        return "read-only"

    payload = tool_input or {}
    command = str(payload.get("command") or payload.get("cmd") or "").strip()
    if not command:
        return "read-only"
    compact = " ".join(command.split())
    lowered = compact.lower()

    validation_patterns = (
        r"(^|[;&|]\s*)(python3?\s+-m\s+pytest|pytest)(\s|$)",
        r"(^|[;&|]\s*)(mvnw?|gradlew?|gradle)(\s|$).*(\stest|\scheck)(\s|$)",
        r"(^|[;&|]\s*)bash\s+scripts/harness/doctor\.sh(\s|$)",
        r"(^|[;&|]\s*)[^;&|]*scripts/(quality|openspec)/[^;&|]*(validate|gate|test)",
        r"(^|[;&|]\s*)\./scripts/session-browser\.sh\s+test(\s|$)",
    )
    if any(re.search(pattern, lowered) for pattern in validation_patterns):
        return "validation"

    mutation_patterns = (
        r"(^|[;&|]\s*)(touch|rm|mv|cp|mkdir|rmdir|install|chmod|chown|truncate|tee)(\s|$)",
        r"(^|[;&|]\s*)(sed|perl)\s+[^;&|]*\s-i(?:\s|$)",
        r"(^|[;&|]\s*)git\s+(add|commit|checkout|switch|reset|merge|rebase|cherry-pick|am|apply|clean|restore)(\s|$)",
        r"(^|[;&|]\s*)git\s+worktree\s+(?!list(?:\s|$))\S+",
        r"(^|[;&|]\s*)(npm|pnpm|yarn|pip|pip3)\s+(install|add|remove|uninstall|update)(\s|$)",
        r"(^|[^<])>>?\s*[^&]",
        r"(^|[;&|]\s*)find\s+[^;&|]*\s-delete(?:\s|$)",
    )
    if any(re.search(pattern, lowered) for pattern in mutation_patterns):
        return "mutation"

    read_prefixes = (
        "cat ",
        "rg ",
        "grep ",
        "ls",
        "pwd",
        "head ",
        "tail ",
        "wc ",
        "find ",
        "stat ",
        "git status",
        "git diff",
        "git log",
        "git show",
        "git rev-parse",
        "git branch --show-current",
        "git worktree list",
        "sed -n ",
    )
    return "read-only" if lowered.startswith(read_prefixes) else "mutation"


# 判断工具调用是否必须受 checkout 写租约保护。
def requires_writer_lease(tool_name: str, tool_input: Mapping[str, Any] | None = None) -> bool:
    """参数：
        tool_name: 工具名称。
        tool_input: 工具调用参数；未提供时按空输入处理。

    返回：
        工具调用属于写操作时返回 true。
    """

    return classify_tool_call(tool_name, tool_input) == "mutation"


# 维护 git 函数行为。
def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或执行结果。
    """
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=check,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


# 维护 now_utc 函数行为。
def now_utc() -> str:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或执行结果。
    """
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


# 维护 write_json_atomic 函数行为。
def write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或执行结果。
    """
    ensure_private_directory(path.parent)
    try:
        existing = path.lstat()
    except FileNotFoundError:
        existing = None
    if existing is not None:
        if stat.S_ISLNK(existing.st_mode) or not stat.S_ISREG(existing.st_mode):
            raise SessionctlError(f"refusing unsafe JSON target: {path}")
        if hasattr(os, "geteuid") and existing.st_uid != os.geteuid():
            raise SessionctlError(f"JSON target is not owned by current user: {path}")
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(tmp, flags, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        payload = (json.dumps(data, indent=2, sort_keys=True) + "\n").encode("utf-8")
        with os.fdopen(descriptor, "wb", closefd=False) as handle:
            handle.write(payload)
            handle.flush()
        os.fsync(descriptor)
        os.replace(tmp, path)
        directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        directory = os.open(path.parent, directory_flags)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        os.close(descriptor)
        with contextlib.suppress(FileNotFoundError):
            tmp.unlink()


# 维护 load_json 函数行为。
def load_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或执行结果。
    """
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return default
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise SessionctlError(f"refusing unsafe JSON source: {path}")
    if hasattr(os, "geteuid") and metadata.st_uid != os.geteuid():
        raise SessionctlError(f"JSON source is not owned by current user: {path}")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        if opened.st_ino != metadata.st_ino or opened.st_dev != metadata.st_dev:
            raise SessionctlError(f"JSON source changed during open: {path}")
        with os.fdopen(descriptor, "r", encoding="utf-8", closefd=False) as handle:
            data = json.load(handle)
    finally:
        os.close(descriptor)
    if not isinstance(data, dict):
        raise SessionctlError(f"JSON source must contain an object: {path}")
    return data


# 校验运行时标识符，避免其逃逸 Registry 管理的文件名边界。
def _validate_identifier(value: str, label: str) -> str:
    """参数：
        value: 待校验的标识符。
        label: 错误消息使用的标识符名称。

    返回：
        通过校验的原始标识符。

    异常：
        SessionctlError: 标识符格式不合法时抛出。
    """
    if not IDENTIFIER_PATTERN.fullmatch(value):
        raise SessionctlError(f"invalid {label}: {value!r}")
    return value


class Registry:
    """Shared primary-run registry guarded by a repository runtime lock."""

    # 维护 __init__ 函数行为。
    def __init__(self, repo_root: Path):
        """参数：
            *args: 当前函数使用的输入参数。

        返回：
            当前函数计算或执行结果。
        """
        self.repo_root = resolve_checkout_root(repo_root)
        self.primary_repo_root = resolve_primary_repo_root(self.repo_root)
        self.repo_key = resolve_repo_key(self.repo_root)
        self.root = resolve_runtime_root(self.repo_root)
        self.runs_dir = ensure_private_directory(self.root / "runs", root=self.root)
        self.locks_dir = ensure_private_directory(self.root / "locks", root=self.root)
        self.writer_leases_dir = ensure_private_directory(self.root / "writer-leases", root=self.root)
        self.mutation_locks_dir = ensure_private_directory(
            self.locks_dir / "checkout-mutations", root=self.root
        )
        self.audit_dir = ensure_private_directory(self.root / "audit", root=self.root)
        self.index_path = self.runs_dir / "index.json"
        self.lock_path = self.locks_dir / "registry.lock"
        self._lock_descriptor: int | None = None
        self._lock_metadata: dict[str, Any] = {}

    # 计算稳定 checkout 身份对应的唯一写租约文档路径。
    def writer_lease_path(self, worktree_id: str) -> Path:
        """参数：
            worktree_id: 稳定的 checkout 标识符。

        返回：
            写租约文档路径。
        """

        return self.writer_leases_dir / f"{_validate_identifier(worktree_id, 'worktree id')}.json"

    # 在安全文件锁下串行执行单个 checkout 的租约变更。
    @contextmanager
    def checkout_mutation_locked(
        self,
        worktree_id: str,
        *,
        client: str,
        session_id: str,
        run_id: str,
    ) -> Iterable[None]:
        """参数：
            worktree_id: 稳定的 checkout 标识符。
            client: 持锁客户端名称。
            session_id: 持锁 Session 标识符。
            run_id: 持锁运行标识符。

        返回：
            持有变更锁期间使用的上下文管理器。
        """

        worktree_id = _validate_identifier(worktree_id, "worktree id")
        path = self.mutation_locks_dir / f"{worktree_id}.lock"
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags, 0o600)
        try:
            opened = os.fstat(descriptor)
            if not stat.S_ISREG(opened.st_mode):
                raise SessionctlError(f"checkout mutation lock is not a regular file: {path}")
            if hasattr(os, "geteuid") and opened.st_uid != os.geteuid():
                raise SessionctlError(f"checkout mutation lock is not owned by current user: {path}")
            os.fchmod(descriptor, 0o600)
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            previous = self._read_lock_metadata(descriptor)
            try:
                lock_epoch = int(previous.get("epoch") or 0) + 1
            except (TypeError, ValueError):
                lock_epoch = 1
            timestamp = now_utc()
            owner_uid = os.geteuid() if hasattr(os, "geteuid") else os.getuid()
            metadata = {
                "schemaVersion": REGISTRY_VERSION,
                "owner": f"uid:{owner_uid}",
                "ownerUid": owner_uid,
                "pid": os.getpid(),
                "processStartTime": _pid_start_time(os.getpid()),
                "client": client,
                "sessionId": session_id,
                "runId": run_id,
                "repoKey": self.repo_key,
                "worktreeId": worktree_id,
                "epoch": lock_epoch,
                "acquiredAt": timestamp,
                "updatedAt": timestamp,
            }

            # 将当前 checkout 变更锁元数据持久化到已加锁文件。
            def persist() -> None:
                payload = (json.dumps(metadata, indent=2, sort_keys=True) + "\n").encode("utf-8")
                os.lseek(descriptor, 0, os.SEEK_SET)
                os.ftruncate(descriptor, 0)
                remaining = memoryview(payload)
                while remaining:
                    written = os.write(descriptor, remaining)
                    if written <= 0:
                        raise SessionctlError("checkout mutation lock metadata write made no progress")
                    remaining = remaining[written:]
                os.fsync(descriptor)

            persist()
            try:
                yield
            finally:
                metadata["releasedAt"] = now_utc()
                metadata["updatedAt"] = metadata["releasedAt"]
                persist()
                fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)

    # 维护 locked 函数行为。
    @contextmanager
    def locked(self, *, client: str = "", session_id: str = "", run_id: str = "") -> Iterable[None]:
        """参数：
            *args: 当前函数使用的输入参数。

        返回：
            当前函数计算或执行结果。
        """
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(self.lock_path, flags, 0o600)
        try:
            opened = os.fstat(descriptor)
            if not stat.S_ISREG(opened.st_mode):
                raise SessionctlError(f"Registry lock is not a regular file: {self.lock_path}")
            if hasattr(os, "geteuid") and opened.st_uid != os.geteuid():
                raise SessionctlError(f"Registry lock is not owned by current user: {self.lock_path}")
            os.fchmod(descriptor, 0o600)
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            previous = self._read_lock_metadata(descriptor)
            try:
                epoch = int(previous.get("epoch") or 0) + 1
            except (TypeError, ValueError):
                epoch = 1
            timestamp = now_utc()
            owner_uid = os.geteuid() if hasattr(os, "geteuid") else os.getuid()
            self._lock_descriptor = descriptor
            self._lock_metadata = {
                "schemaVersion": REGISTRY_VERSION,
                "owner": f"uid:{owner_uid}",
                "ownerUid": owner_uid,
                "pid": os.getpid(),
                "processStartTime": _pid_start_time(os.getpid()),
                "client": client,
                "sessionId": session_id,
                "runId": run_id,
                "repoKey": self.repo_key,
                "checkoutRoot": str(self.repo_root),
                "epoch": epoch,
                "acquiredAt": timestamp,
                "updatedAt": timestamp,
            }
            self._write_lock_metadata()
            try:
                yield
            finally:
                self._lock_metadata["releasedAt"] = now_utc()
                self._lock_metadata["updatedAt"] = self._lock_metadata["releasedAt"]
                self._write_lock_metadata()
                self._lock_descriptor = None
                self._lock_metadata = {}
                fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)

    # 从已打开的 Registry 锁文件读取结构化元数据。
    @staticmethod
    def _read_lock_metadata(descriptor: int) -> dict[str, Any]:
        """参数：
            descriptor: 已打开的锁文件描述符。

        返回：
            可解析的锁元数据；空文件或非法内容返回空字典。
        """
        os.lseek(descriptor, 0, os.SEEK_SET)
        raw = os.read(descriptor, 64 * 1024)
        if not raw.strip():
            return {}
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    # 将内存中的 Registry 锁元数据写入当前持有的锁文件。
    def _write_lock_metadata(self) -> None:
        if self._lock_descriptor is None:
            raise SessionctlError("Registry lock metadata update requires held lock")
        payload = (json.dumps(self._lock_metadata, indent=2, sort_keys=True) + "\n").encode("utf-8")
        os.lseek(self._lock_descriptor, 0, os.SEEK_SET)
        os.ftruncate(self._lock_descriptor, 0)
        remaining = memoryview(payload)
        while remaining:
            written = os.write(self._lock_descriptor, remaining)
            if written <= 0:
                raise SessionctlError("Registry lock metadata write made no progress")
            remaining = remaining[written:]
        os.fsync(self._lock_descriptor)

    # 将已解析的 Session 和运行身份附加到当前 Registry 锁。
    def update_lock_context(self, *, client: str = "", session_id: str = "", run_id: str = "") -> None:
        """参数：
            client: 客户端名称；空值表示不更新。
            session_id: Session 标识符；空值表示不更新。
            run_id: 运行标识符；空值表示不更新。
        """
        if self._lock_descriptor is None:
            raise SessionctlError("Registry lock context update requires held lock")
        if client:
            self._lock_metadata["client"] = client
        if session_id:
            self._lock_metadata["sessionId"] = session_id
        if run_id:
            self._lock_metadata["runId"] = run_id
        self._lock_metadata["updatedAt"] = now_utc()
        self._write_lock_metadata()

    # 维护 _run_path 函数行为。
    def _run_path(self, run_id: str) -> Path:
        """参数：
            *args: 当前函数使用的输入参数。

        返回：
            当前函数计算或执行结果。
        """
        return self.runs_dir / f"{_validate_identifier(run_id, 'run id')}.json"

    # 维护 load_index 函数行为。
    def load_index(self) -> dict[str, Any]:
        """参数：
            *args: 当前函数使用的输入参数。

        返回：
            当前函数计算或执行结果。
        """
        return load_json(self.index_path, {"schemaVersion": REGISTRY_VERSION, "runs": []})

    # 维护 save_index 函数行为。
    def save_index(self, run_ids: list[str]) -> None:
        """参数：
            *args: 当前函数使用的输入参数。

        返回：
            当前函数计算或执行结果。
        """
        write_json_atomic(self.index_path, {"schemaVersion": REGISTRY_VERSION, "runs": sorted(set(run_ids))})

    # 维护 load_run 函数行为。
    def load_run(self, run_id: str) -> dict[str, Any]:
        """参数：
            *args: 当前函数使用的输入参数。

        返回：
            当前函数计算或执行结果。
        """
        path = self._run_path(run_id)
        record = load_json(path, {})
        if not record:
            raise SessionctlError(f"unknown run_id: {run_id}")
        return record

    # 维护 save_run 函数行为。
    def save_run(self, record: dict[str, Any]) -> None:
        """参数：
            *args: 当前函数使用的输入参数。

        返回：
            当前函数计算或执行结果。
        """
        validate_run_record(record)
        write_json_atomic(self._run_path(str(record["runId"])), record)
        index = self.load_index()
        run_ids = [str(item) for item in index.get("runs", [])]
        if str(record["runId"]) not in run_ids:
            run_ids.append(str(record["runId"]))
        self.save_index(run_ids)

    # 维护 all_runs 函数行为。
    def all_runs(self) -> list[dict[str, Any]]:
        """参数：
            *args: 当前函数使用的输入参数。

        返回：
            当前函数计算或执行结果。
        """
        index = self.load_index()
        records = []
        for run_id in index.get("runs", []):
            record = load_json(self._run_path(str(run_id)), {})
            if record:
                records.append(record)
        return records

    # 在 Registry 锁内按身份精确删除运行记录及索引项。
    def remove_run_record(
        self,
        run_id: str,
        *,
        expected_repo_key: str,
        expected_checkout_root: Path,
    ) -> None:
        """参数：
            run_id: 待删除的运行标识符。
            expected_repo_key: 预期的仓库键。
            expected_checkout_root: 预期的 checkout 根目录。

        异常：
            SessionctlError: 锁未持有或运行身份不匹配时抛出。
        """

        if self._lock_descriptor is None:
            raise SessionctlError("run record removal requires the Registry lock")
        current = self.load_run(run_id)
        if current.get("repoKey") != expected_repo_key or expected_repo_key != self.repo_key:
            raise SessionctlError("cleanup run does not belong to this Registry")
        recorded_checkout = Path(str(current.get("checkoutRoot") or "")).expanduser().resolve()
        if recorded_checkout != expected_checkout_root.resolve():
            raise SessionctlError("cleanup run checkout identity changed before removal")
        path = self._run_path(run_id)
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise SessionctlError(f"refusing unsafe run record removal: {path}")
        if hasattr(os, "geteuid") and metadata.st_uid != os.geteuid():
            raise SessionctlError(f"run record is not owned by current user: {path}")
        path.unlink()
        index = self.load_index()
        self.save_index(
            [str(item) for item in index.get("runs", []) if str(item) != run_id]
        )

    # 在 Registry 旁持久化一条不可变审计事件。
    def write_audit(self, event: dict[str, Any]) -> None:
        """参数：
            event: 待持久化的审计事件。
        """
        event_id = f"{int(time.time_ns())}-{uuid.uuid4().hex[:12]}"
        write_json_atomic(self.audit_dir / f"{event_id}.json", event)


# 维护 repo_root_from_arg 函数行为。
def repo_root_from_arg(value: str | None) -> Path:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或执行结果。
    """
    start = Path(value).resolve() if value else Path.cwd().resolve()
    try:
        out = git(start, "rev-parse", "--show-toplevel")
    except subprocess.CalledProcessError as exc:
        raise SessionctlError(f"not a git repository: {start}") from exc
    return Path(out.stdout.strip()).resolve()


# 维护 head_commit 函数行为。
def head_commit(repo: Path) -> str:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或执行结果。
    """
    return git(repo, "rev-parse", "HEAD").stdout.strip()


# 读取 bootstrap 使用的不可变 checkout 身份与初始 Git 事实。
def _checkout_snapshot(cwd: Path, *, checkout_creator: str = "unknown") -> dict[str, Any]:
    """参数：
        cwd: 当前 checkout 内的路径。
        checkout_creator: checkout 创建方。

    返回：
        checkout 身份与初始脏状态快照。
    """
    checkout_root = resolve_checkout_root(cwd)
    identity = resolve_checkout_identity(
        checkout_root,
        checkout_creator=checkout_creator,
    )
    porcelain = git(checkout_root, "status", "--porcelain=v1", "--untracked-files=all").stdout.splitlines()
    tracked = [line[3:] for line in porcelain if len(line) >= 4 and not line.startswith("??")]
    untracked = [line[3:] for line in porcelain if line.startswith("??") and len(line) >= 4]
    captured_at = now_utc()
    return {
        **identity,
        "initialDirtySnapshot": {
            "dirty": bool(porcelain),
            "porcelain": porcelain,
            "tracked": tracked,
            "untracked": untracked,
            "capturedAt": captured_at,
        },
    }


# 根据 checkout 快照构造尚未持久化的运行记录。
def _build_bootstrap_record(
    registry: Registry,
    *,
    client: str,
    session_id: str,
    hook_event: str,
    cwd: Path,
    run_id: str,
    checkout_creator: str = "unknown",
    facts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """参数：
        registry: 当前仓库的运行时 Registry。
        client: 客户端名称。
        session_id: Session 标识符。
        hook_event: 首次触发 bootstrap 的 hook 事件。
        cwd: 当前 checkout 内的路径。
        run_id: 待写入的运行标识符。
        checkout_creator: checkout 创建方。
        facts: 可复用的 checkout 身份快照。

    返回：
        满足运行时 schema 的初始运行记录。
    """
    snapshot = facts or _checkout_snapshot(cwd, checkout_creator=checkout_creator)
    if snapshot["repoKey"] != registry.repo_key:
        raise SessionctlError("bootstrap checkout does not belong to Registry repository")
    timestamp = now_utc()
    checkout_root = str(snapshot["checkoutRoot"])
    worktree_id = stable_worktree_id(registry.repo_key, checkout_root)
    target_branch = str(snapshot["branch"])
    primary = Path(str(snapshot["primaryRepoRoot"]))
    if snapshot["checkoutKind"] == "linked-worktree":
        observed_target = git(primary, "branch", "--show-current", check=False)
        target_branch = observed_target.stdout.strip() if observed_target.returncode == 0 else ""
    target_head = ""
    if target_branch:
        observed_head = git(
            primary,
            "rev-parse",
            "--verify",
            f"refs/heads/{target_branch}",
            check=False,
        )
        if observed_head.returncode == 0:
            target_head = observed_head.stdout.strip()
    return {
        "schemaVersion": REGISTRY_VERSION,
        "runId": _validate_identifier(run_id, "run id"),
        "repoKey": registry.repo_key,
        "client": client,
        "taskId": f"session:{session_id}",
        "sessionId": session_id,
        "worktreeId": worktree_id,
        "checkoutRoot": checkout_root,
        "checkoutKind": snapshot["checkoutKind"],
        "checkoutCreator": snapshot["checkoutCreator"],
        "gitCommonDir": snapshot["gitCommonDir"],
        "branch": snapshot["branch"],
        "detached": snapshot["detached"],
        "targetBranch": target_branch,
        "targetHeadAtBootstrap": target_head,
        "primaryRepoRoot": snapshot["primaryRepoRoot"],
        "baseCommit": snapshot["headCommit"],
        "headCommit": snapshot["headCommit"],
        "initialDirtySnapshot": snapshot["initialDirtySnapshot"],
        "changeAttribution": {
            "baseline": "initialDirtySnapshot",
            "preexistingChangesAttributedToRun": False,
            "requiresHandoffIfIndistinguishable": bool(snapshot["initialDirtySnapshot"]["dirty"]),
        },
        "changeId": "",
        "status": "BOOTSTRAPPED",
        "allowedPaths": ["."],
        "forbiddenPaths": list(DEFAULT_FORBIDDEN_PATHS),
        "writerLease": {},
        "hookActivation": {
            "confirmed": True,
            "client": client,
            "sessionId": session_id,
            "cwd": str(cwd.resolve()),
            "source": "sessionctl bootstrap",
        },
        "bootstrap": {
            "firstHookEvent": hook_event,
            "lastHookEvent": hook_event,
            "firstSeenAt": timestamp,
            "lastSeenAt": timestamp,
            "lastCwd": str(cwd.resolve()),
        },
        "auditEvents": [],
        "createdAt": timestamp,
        "updatedAt": timestamp,
    }


# 在首次写入前采用 Claude CwdChanged 最终选定的同仓库 checkout。
# 安全地将尚未写入的 Claude run 重绑到客户端最终 checkout。
def _rebind_pre_mutation_claude_checkout(
    registry: Registry,
    record: dict[str, Any],
    *,
    client: str,
    session_id: str,
    hook_event: str,
    checkout_creator: str,
    facts: dict[str, Any],
) -> dict[str, Any]:
    """参数：
        registry: 当前函数使用的输入参数。
        record: 当前函数使用的输入参数。
        client: 当前函数使用的输入参数。
        session_id: 当前函数使用的输入参数。
        hook_event: 当前函数使用的输入参数。
        checkout_creator: 当前函数使用的输入参数。
        facts: 当前函数使用的输入参数。

    返回：
        当前函数的计算结果。
    """
    if client != "claude" or hook_event != "CwdChanged":
        raise SessionctlError("Session is already bound to a different checkout")
    if record.get("status") not in {"BOOTSTRAPPED", "READ_ONLY_READY"}:
        raise SessionctlError("Session checkout cannot change after writer activation")
    if record.get("writerLease"):
        raise SessionctlError("Session checkout cannot change while writer lease exists")
    if record.get("releasedWriterLease"):
        raise SessionctlError("Session checkout cannot change after writer activation")
    if record.get("subagentSessions"):
        raise SessionctlError("Session checkout cannot change after subagent inheritance")
    if record.get("gitCommonDir") != facts.get("gitCommonDir"):
        raise SessionctlError("Session checkout change must stay in one Git common directory")

    previous_root = str(record.get("checkoutRoot") or "")
    previous_worktree_id = str(record.get("worktreeId") or "")
    rebound = _build_bootstrap_record(
        registry,
        client=client,
        session_id=session_id,
        hook_event=hook_event,
        cwd=Path(str(facts["checkoutRoot"])),
        run_id=str(record["runId"]),
        checkout_creator=checkout_creator,
        facts=facts,
    )
    rebound["taskId"] = record["taskId"]
    rebound["changeId"] = str(record.get("changeId") or "")
    rebound["allowedPaths"] = list(record.get("allowedPaths") or ["."])
    rebound["forbiddenPaths"] = list(
        record.get("forbiddenPaths") or DEFAULT_FORBIDDEN_PATHS
    )
    rebound["status"] = str(record["status"])
    rebound["createdAt"] = str(record["createdAt"])
    previous_bootstrap = record.get("bootstrap")
    if isinstance(previous_bootstrap, dict):
        rebound["bootstrap"]["firstHookEvent"] = str(
            previous_bootstrap.get("firstHookEvent") or hook_event
        )
        rebound["bootstrap"]["firstSeenAt"] = str(
            previous_bootstrap.get("firstSeenAt") or record["createdAt"]
        )
    previous_events = record.get("auditEvents")
    rebound["auditEvents"] = list(previous_events) if isinstance(previous_events, list) else []
    event = {
        "event": "SESSION_CHECKOUT_REBOUND",
        "runId": rebound["runId"],
        "sessionId": rebound["sessionId"],
        "fromCheckoutRoot": previous_root,
        "fromWorktreeId": previous_worktree_id,
        "toCheckoutRoot": rebound["checkoutRoot"],
        "toWorktreeId": rebound["worktreeId"],
        "hookEvent": hook_event,
        "at": now_utc(),
    }
    rebound["auditEvents"].append(event)
    registry.write_audit(event)
    return rebound


# 判断既有运行记录是否与本次 bootstrap 身份完全一致。
def _record_matches_bootstrap(
    record: Mapping[str, Any], *, client: str, session_id: str, facts: Mapping[str, Any]
) -> bool:
    """参数：
        record: 待比对的运行记录。
        client: 当前客户端名称。
        session_id: 当前 Session 标识符。
        facts: 当前 checkout 身份事实。

    返回：
        所有权威身份字段一致时返回 true。
    """
    return (
        record.get("repoKey") == facts["repoKey"]
        and record.get("client") == client
        and record.get("sessionId") == session_id
        and Path(str(record.get("checkoutRoot") or "")).resolve() == Path(str(facts["checkoutRoot"]))
        and record.get("gitCommonDir") == facts["gitCommonDir"]
        and record.get("checkoutKind") == facts["checkoutKind"]
        and record.get("primaryRepoRoot") == facts["primaryRepoRoot"]
        and record.get("worktreeId") == stable_worktree_id(
            str(facts["repoKey"]), str(facts["checkoutRoot"])
        )
    )


# 构造一条忽略非权威身份提示的审计事件。
def _identity_hint_event(
    *, source: str, field: str, value: str, expected: str, hook_event: str, run_id: str
) -> dict[str, Any]:
    """参数：
        source: 身份提示来源。
        field: 提示字段名。
        value: 提示值。
        expected: Registry 中的权威值。
        hook_event: 当前 hook 事件。
        run_id: 当前运行标识符。

    返回：
        可持久化的审计事件。
    """
    return {
        "event": "IDENTITY_HINT_IGNORED",
        "source": source,
        "field": field,
        "value": value,
        "expected": expected,
        "hookEvent": hook_event,
        "runId": run_id,
        "at": now_utc(),
    }


# 仅在身份完全匹配时接受运行标识提示指向的候选记录。
def _candidate_from_run_hint(
    registry: Registry,
    run_id: str,
    *,
    client: str,
    session_id: str,
    facts: Mapping[str, Any],
) -> dict[str, Any] | None:
    """参数：
        registry: 当前仓库的运行时 Registry。
        run_id: 非权威运行标识提示。
        client: 当前客户端名称。
        session_id: 当前 Session 标识符。
        facts: 当前 checkout 身份事实。

    返回：
        身份匹配的运行记录；提示无效或不匹配时返回 None。
    """
    if not run_id:
        return None
    try:
        candidate = registry.load_run(run_id)
    except SessionctlError:
        return None
    return candidate if _record_matches_bootstrap(candidate, client=client, session_id=session_id, facts=facts) else None


# 将不同客户端提供的身份提示归一为统一字段名。
def _normalize_identity_hints(hints: Mapping[str, Any] | None) -> dict[str, str]:
    """参数：
        hints: 客户端负载或环境中的非权威身份提示。

    返回：
        使用统一字段名和字符串值的身份提示。
    """
    source = hints or {}

    # 按别名优先级选取首个非空身份提示。
    def first(*names: str) -> str:
        """参数：
            names: 按优先级排列的候选字段名。

        返回：
            首个非空字段值；全部为空时返回空字符串。
        """
        for name in names:
            value = str(source.get(name) or "").strip()
            if value:
                return value
        return ""

    return {
        "runId": first("runId", "run_id", "FEIPI_RUN_ID"),
        "worktreeId": first("worktreeId", "worktree_id", "FEIPI_WORKTREE_ID"),
        "sessionId": first("sessionId", "session_id", "FEIPI_SESSION_ID"),
        "client": first("client", "agent_client", "FEIPI_CLIENT", "FEIPI_AGENT_CLIENT"),
        "changeId": first("changeId", "change_id", "ACTIVE_CHANGE_ID"),
    }


# 审计与 Registry 权威身份不一致的负载和环境提示。
def _audit_identity_hints(
    registry: Registry,
    record: dict[str, Any],
    *,
    hook_event: str,
    checkout_creator: str = "unknown",
    payload_hints: Mapping[str, str],
    env_hints: Mapping[str, str],
) -> None:
    """参数：
        registry: 当前仓库的运行时 Registry。
        record: 权威运行记录。
        hook_event: 当前 hook 事件。
        checkout_creator: checkout 创建方。
        payload_hints: 客户端负载中的身份提示。
        env_hints: 环境变量中的身份提示。
    """
    expected = {
        "runId": str(record["runId"]),
        "worktreeId": str(record["worktreeId"]),
        "sessionId": str(record["sessionId"]),
        "client": str(record["client"]),
        "changeId": str(record.get("changeId") or ""),
    }
    fields = {
        "runId": "runId",
        "worktreeId": "worktreeId",
        "sessionId": "sessionId",
        "client": "client",
        "changeId": "changeId",
    }
    events = record.setdefault("auditEvents", [])
    if not isinstance(events, list):
        raise SessionctlError("run auditEvents must be a list")
    for source, hints in (("payload", payload_hints), ("environment", env_hints)):
        for hint_field, record_field in fields.items():
            value = str(hints.get(hint_field) or "")
            if value and value != expected[record_field]:
                event = _identity_hint_event(
                    source=source,
                    field=hint_field,
                    value=value,
                    expected=expected[record_field],
                    hook_event=hook_event,
                    run_id=str(record["runId"]),
                )
                events.append(event)
                registry.write_audit(event)


# 为当前 Session checkout 创建或恢复唯一的 Registry 权威运行记录。
def bootstrap_session(
    *,
    client: str,
    session_id: str,
    cwd: Path,
    hook_event: str,
    checkout_creator: str = "unknown",
    payload_hints: Mapping[str, Any] | None = None,
    env_hints: Mapping[str, Any] | None = None,
    parent_run_id: str = "",
) -> dict[str, Any]:
    """参数：
        client: 客户端名称。
        session_id: Session 标识符。
        cwd: 当前 checkout 内的路径。
        hook_event: 触发 bootstrap 的 hook 事件。
        checkout_creator: checkout 创建方。
        payload_hints: 客户端负载中的非权威身份提示。
        env_hints: 环境变量中的非权威身份提示。
        parent_run_id: 子 agent 继承的父运行标识符。

    返回：
        创建、恢复或继承的权威运行记录。
    """
    client = client.strip()
    session_id = session_id.strip()
    hook_event = hook_event.strip()
    if not client or not session_id or not hook_event:
        raise SessionctlError("bootstrap requires non-empty client, session-id, and hook-event")
    if checkout_creator not in CHECKOUT_CREATORS:
        raise SessionctlError(f"invalid checkout creator: {checkout_creator}")
    checkout = resolve_checkout_root(cwd)
    facts = _checkout_snapshot(checkout, checkout_creator=checkout_creator)
    registry = Registry(checkout)
    payload = _normalize_identity_hints(payload_hints)
    environment = _normalize_identity_hints(env_hints)

    with registry.locked(client=client, session_id=session_id, run_id=payload.get("runId", "")):
        records = registry.all_runs()
        if parent_run_id:
            parent_run_id = _validate_identifier(parent_run_id, "parent run id")
            parent = registry.load_run(parent_run_id)
            if parent.get("client") != client:
                raise SessionctlError("subagent client does not match parent run")
            parent_root = Path(str(parent.get("checkoutRoot") or "")).resolve()
            if (
                parent.get("repoKey") != facts["repoKey"]
                or parent.get("worktreeId")
                != stable_worktree_id(str(facts["repoKey"]), str(facts["checkoutRoot"]))
                or parent_root != Path(str(facts["checkoutRoot"])).resolve()
            ):
                raise SessionctlError("subagent checkout does not match parent run")
            registry.update_lock_context(
                client=str(parent["client"]),
                session_id=str(parent["sessionId"]),
                run_id=str(parent["runId"]),
            )
            timestamp = now_utc()
            event = {
                "event": "SUBAGENT_RUN_INHERITED",
                "runId": parent["runId"],
                "sessionId": parent["sessionId"],
                "subagentSessionId": session_id,
                "worktreeId": parent["worktreeId"],
                "hookEvent": hook_event,
                "at": timestamp,
            }
            _append_run_audit(registry, parent, event)
            observations = parent.setdefault("subagentSessions", [])
            if not isinstance(observations, list):
                raise SessionctlError("run subagentSessions must be a list")
            if session_id not in observations:
                observations.append(session_id)
            parent["updatedAt"] = timestamp
            registry.save_run(parent)
            return parent
        exact = [
            item
            for item in records
            if _record_matches_bootstrap(item, client=client, session_id=session_id, facts=facts)
        ]
        if len(exact) > 1:
            raise SessionctlError("Registry contains duplicate client/session/checkout runs")
        same_session_elsewhere = [
            item
            for item in records
            if item.get("repoKey") == facts["repoKey"]
            and item.get("client") == client
            and item.get("sessionId") == session_id
            and not _record_matches_bootstrap(item, client=client, session_id=session_id, facts=facts)
        ]
        if exact:
            record = exact[0]
        elif same_session_elsewhere:
            if len(same_session_elsewhere) != 1:
                raise SessionctlError("Registry contains duplicate client/session runs")
            record = _rebind_pre_mutation_claude_checkout(
                registry,
                same_session_elsewhere[0],
                client=client,
                session_id=session_id,
                hook_event=hook_event,
                checkout_creator=checkout_creator,
                facts=facts,
            )
        else:
            record = _candidate_from_run_hint(
                registry,
                payload.get("runId", ""),
                client=client,
                session_id=session_id,
                facts=facts,
            ) or _candidate_from_run_hint(
                registry,
                environment.get("runId", ""),
                client=client,
                session_id=session_id,
                facts=facts,
            )
            if record is None:
                run_id = f"run-{uuid.uuid4().hex[:20]}"
                while any(item.get("runId") == run_id for item in records):
                    run_id = f"run-{uuid.uuid4().hex[:20]}"
                record = _build_bootstrap_record(
                    registry,
                    client=client,
                    session_id=session_id,
                    hook_event=hook_event,
                    cwd=checkout,
                    run_id=run_id,
                    checkout_creator=checkout_creator,
                    facts=facts,
                )
        registry.update_lock_context(client=client, session_id=session_id, run_id=str(record["runId"]))
        bootstrap = record.setdefault("bootstrap", {})
        if not isinstance(bootstrap, dict):
            raise SessionctlError("run bootstrap metadata must be an object")
        bootstrap.setdefault("firstHookEvent", hook_event)
        bootstrap.setdefault("firstSeenAt", record.get("createdAt") or now_utc())
        bootstrap["lastHookEvent"] = hook_event
        bootstrap["lastSeenAt"] = now_utc()
        bootstrap["lastCwd"] = str(checkout)
        if record.get("checkoutCreator") == "unknown" and checkout_creator != "unknown":
            record["checkoutCreator"] = checkout_creator
        record["updatedAt"] = now_utc()
        _audit_identity_hints(
            registry,
            record,
            hook_event=hook_event,
            payload_hints=payload,
            env_hints=environment,
        )
        registry.save_run(record)
    return record


LEASE_RECORD_FIELDS = (
    "leaseId",
    "holderRunId",
    "holderSessionId",
    "runId",
    "sessionId",
    "client",
    "repoKey",
    "worktreeId",
    "checkoutRoot",
    "checkoutKind",
    "epoch",
    "fencingToken",
    "state",
    "heartbeatAt",
    "acquiredAt",
    "updatedAt",
    "owner",
    "ownerUid",
    "pid",
    "processStartTime",
)


# 提取需持久化到运行记录的租约围栏与所有者字段。
def _lease_record_view(lease: Mapping[str, Any]) -> dict[str, Any]:
    """参数：
        lease: 完整的 checkout 写租约。

    返回：
        可嵌入运行记录的租约字段副本。
    """

    return {field: lease[field] for field in LEASE_RECORD_FIELDS if field in lease}


# 同时向运行记录和 Registry 审计目录追加事件。
def _append_run_audit(registry: Registry, record: dict[str, Any], event: dict[str, Any]) -> None:
    """参数：
        registry: 当前仓库的运行时 Registry。
        record: 待更新的运行记录。
        event: 待追加的审计事件。
    """
    events = record.setdefault("auditEvents", [])
    if not isinstance(events, list):
        raise SessionctlError("run auditEvents must be a list")
    events.append(event)
    registry.write_audit(event)


# 校验状态迁移后更新运行记录状态。
def _set_run_status(record: dict[str, Any], status: str) -> None:
    """参数：
        record: 待更新的运行记录。
        status: 目标生命周期状态。
    """
    previous = str(record.get("status") or "")
    if previous != status:
        validate_status_transition(previous, status)
        record["status"] = status


# 根据 checkout 类型选择本地或隔离写入状态。
def _writer_status(record: Mapping[str, Any]) -> str:
    """参数：
        record: 当前运行记录。

    返回：
        checkout 类型对应的写入状态。
    """
    return "LOCAL_WRITER" if record.get("checkoutKind") == "primary-checkout" else "ISOLATED_WRITER"


# 在新写操作开始时使既有 Stop 验证凭据失效。
def _invalidate_stop_validation_for_mutation(
    registry: Registry, record: dict[str, Any], *, timestamp: str
) -> None:
    """参数：
        registry: 当前仓库的运行时 Registry。
        record: 待恢复写入状态的运行记录。
        timestamp: 验证失效时间。
    """

    if record.get("status") != "VALIDATED":
        return
    _set_run_status(record, _writer_status(record))
    validation = record.get("stopValidation")
    if isinstance(validation, dict):
        validation["fresh"] = False
        validation["staleAt"] = timestamp
        validation["staleReason"] = "mutation requested after Stop validation"
    record["validationStaleAt"] = timestamp
    record["validationStaleReason"] = "mutation requested after Stop validation"
    _append_run_audit(
        registry,
        record,
        {
            "event": "STOP_VALIDATION_INVALIDATED",
            "runId": record["runId"],
            "sessionId": record["sessionId"],
            "worktreeId": record["worktreeId"],
            "reason": record["validationStaleReason"],
            "at": timestamp,
        },
    )


# 校验租约操作引用的运行记录与当前 checkout 身份一致。
def _validate_lease_checkout(registry: Registry, record: Mapping[str, Any]) -> Path:
    """参数：
        registry: 当前仓库的运行时 Registry。
        record: 待校验的运行记录。

    返回：
        通过身份校验的 checkout 根目录。
    """
    if record.get("repoKey") != registry.repo_key:
        raise SessionctlError("run and Registry repository identities do not match")
    checkout = Path(str(record.get("checkoutRoot") or ""))
    facts, errors = validate_checkout_record(checkout, dict(record))
    if errors:
        raise SessionctlError("checkout identity is invalid: " + "; ".join(errors))
    expected_id = stable_worktree_id(registry.repo_key, str(facts["checkoutRoot"]))
    if record.get("worktreeId") != expected_id:
        raise SessionctlError("run worktreeId is not the stable checkout identity")
    return Path(str(facts["checkoutRoot"]))


# 重新加载租约运行记录并拒绝并发身份漂移。
def _reload_lease_run(registry: Registry, supplied: Mapping[str, Any]) -> dict[str, Any]:
    """参数：
        registry: 当前仓库的运行时 Registry。
        supplied: 调用方持有的运行记录快照。

    返回：
        身份未漂移的最新运行记录。
    """
    current = registry.load_run(str(supplied.get("runId") or ""))
    for field in ("repoKey", "client", "sessionId", "worktreeId", "checkoutRoot"):
        if str(current.get(field) or "") != str(supplied.get(field) or ""):
            raise SessionctlError(f"run identity changed while mutating lease: {field}")
    _validate_lease_checkout(registry, current)
    return current


# 读取指定稳定 checkout 身份的写租约文档。
def _load_checkout_lease(registry: Registry, worktree_id: str) -> dict[str, Any]:
    """参数：
        registry: 当前仓库的运行时 Registry。
        worktree_id: 稳定的 checkout 标识符。

    返回：
        写租约内容；文档不存在时返回空字典。
    """
    return load_json(registry.writer_lease_path(worktree_id), {})


# 判断活动租约是否与预期运行身份和围栏凭据一致。
def _lease_fence_matches(
    lease: Mapping[str, Any], *, run_id: str, session_id: str, epoch: int, fencing_token: str
) -> bool:
    """参数：
        lease: 当前 checkout 写租约。
        run_id: 预期持有者运行标识符。
        session_id: 预期持有者 Session 标识符。
        epoch: 预期租约世代。
        fencing_token: 预期围栏令牌。

    返回：
        所有租约围栏字段完全匹配时返回 true。
    """
    try:
        actual_epoch = int(lease.get("epoch") or 0)
    except (TypeError, ValueError):
        return False
    return (
        lease.get("state") == LEASE_ACTIVE
        and lease.get("holderRunId") == run_id
        and lease.get("holderSessionId") == session_id
        and actual_epoch == epoch
        and bool(fencing_token)
        and lease.get("fencingToken") == fencing_token
    )


# 从运行记录读取缓存的租约世代与围栏令牌。
def _cached_fence(record: Mapping[str, Any]) -> tuple[int, str]:
    """参数：
        record: 当前运行记录。

    返回：
        租约世代与围栏令牌组成的元组。
    """
    cached = record.get("writerLease") if isinstance(record.get("writerLease"), Mapping) else {}
    try:
        epoch = int(cached.get("epoch") or 0)
    except (TypeError, ValueError):
        epoch = 0
    return epoch, str(cached.get("fencingToken") or "")


# 在围栏校验失败后阻断运行并记录审计证据。
def _block_fenced_run(
    registry: Registry,
    record: dict[str, Any],
    *,
    lease: Mapping[str, Any],
    operation: str,
    reason: str,
) -> None:
    """参数：
        registry: 当前仓库的运行时 Registry。
        record: 待阻断的运行记录。
        lease: 触发围栏冲突的 checkout 租约。
        operation: 失败的租约操作名称。
        reason: 可审计的阻断原因。
    """
    _set_run_status(record, "BLOCKED")
    record["leaseBlockReason"] = reason
    record["updatedAt"] = now_utc()
    event = {
        "event": "WRITER_LEASE_FENCED",
        "operation": operation,
        "runId": record["runId"],
        "sessionId": record["sessionId"],
        "worktreeId": record["worktreeId"],
        "recordEpoch": _cached_fence(record)[0],
        "leaseEpoch": lease.get("epoch", 0),
        "reason": reason,
        "at": now_utc(),
    }
    _append_run_audit(registry, record, event)
    registry.save_run(record)


# 将已 bootstrap 的 Session 标记为只读就绪且不创建租约。
def mark_read_only_ready(registry: Registry, record: dict[str, Any]) -> dict[str, Any]:
    """参数：
        registry: 当前仓库的运行时 Registry。
        record: 当前运行记录。

    返回：
        最新的只读运行记录。
    """

    with registry.locked(
        client=str(record.get("client") or ""),
        session_id=str(record.get("sessionId") or ""),
        run_id=str(record.get("runId") or ""),
    ):
        current = _reload_lease_run(registry, record)
        if current["status"] == "BOOTSTRAPPED":
            _set_run_status(current, "READ_ONLY_READY")
            current["writerLease"] = {}
            current["updatedAt"] = now_utc()
            registry.save_run(current)
        return current


# 原子获取 checkout 写租约，或幂等刷新本运行已持有的租约。
def acquire_writer_lease(
    registry: Registry,
    record: dict[str, Any],
    *,
    owner_pid: int | None = None,
    owner_start_time: str = "",
) -> tuple[dict[str, Any], dict[str, Any]]:
    """参数：
        registry: 当前仓库的运行时 Registry。
        record: 申请租约的运行记录。
        owner_pid: 租约所有者进程标识符。
        owner_start_time: 租约所有者进程启动时间。

    返回：
        最新运行记录与活动写租约。
    """

    checkout = _validate_lease_checkout(registry, record)
    worktree_id = str(record["worktreeId"])
    supplied_epoch, supplied_token = _cached_fence(record)
    pid = int(owner_pid if owner_pid is not None else os.getpid())
    if pid <= 0:
        raise SessionctlError("writer lease owner pid must be positive")
    process_start = owner_start_time or _pid_start_time(pid)
    with registry.checkout_mutation_locked(
        worktree_id,
        client=str(record["client"]),
        session_id=str(record["sessionId"]),
        run_id=str(record["runId"]),
    ):
        with registry.locked(
            client=str(record["client"]),
            session_id=str(record["sessionId"]),
            run_id=str(record["runId"]),
        ):
            current = _reload_lease_run(registry, record)
            lease = _load_checkout_lease(registry, worktree_id)
            current_epoch, current_token = _cached_fence(current)

            if supplied_epoch or supplied_token:
                if not _lease_fence_matches(
                    lease,
                    run_id=str(record["runId"]),
                    session_id=str(record["sessionId"]),
                    epoch=supplied_epoch,
                    fencing_token=supplied_token,
                ):
                    reason = "cached epoch/fencing token does not match current checkout lease"
                    _block_fenced_run(
                        registry, current, lease=lease, operation="acquire", reason=reason
                    )
                    raise WriterLeaseFenced(reason)

            if lease.get("state") == LEASE_ACTIVE:
                if lease.get("holderRunId") == current["runId"] and lease.get("holderSessionId") == current["sessionId"]:
                    if not _lease_fence_matches(
                        lease,
                        run_id=str(current["runId"]),
                        session_id=str(current["sessionId"]),
                        epoch=current_epoch,
                        fencing_token=current_token,
                    ):
                        # 并发的首次获取可能从同一空记录开始；此时已持久化记录就是权威结果。
                        persisted = current.get("writerLease")
                        if not supplied_epoch and not supplied_token and isinstance(persisted, dict):
                            current_epoch, current_token = _cached_fence(current)
                        if not _lease_fence_matches(
                            lease,
                            run_id=str(current["runId"]),
                            session_id=str(current["sessionId"]),
                            epoch=current_epoch,
                            fencing_token=current_token,
                        ):
                            reason = "run record fencing data does not match active checkout lease"
                            _block_fenced_run(
                                registry, current, lease=lease, operation="acquire", reason=reason
                            )
                            raise WriterLeaseFenced(reason)
                    timestamp = now_utc()
                    lease["heartbeatAt"] = timestamp
                    lease["updatedAt"] = timestamp
                    write_json_atomic(registry.writer_lease_path(worktree_id), lease)
                    _invalidate_stop_validation_for_mutation(
                        registry, current, timestamp=timestamp
                    )
                    current["writerLease"] = _lease_record_view(lease)
                    current["updatedAt"] = timestamp
                    registry.save_run(current)
                    return current, lease

                if current["status"] == "VALIDATED":
                    timestamp = now_utc()
                    validation = current.get("stopValidation")
                    if isinstance(validation, dict):
                        validation["fresh"] = False
                        validation["staleAt"] = timestamp
                        validation["staleReason"] = "mutation conflicted after Stop validation"
                    current["validationStaleAt"] = timestamp
                    current["validationStaleReason"] = "mutation conflicted after Stop validation"
                    _set_run_status(current, "READ_ONLY_CONFLICT")
                elif current["status"] not in {"BOOTSTRAPPED", "READ_ONLY_READY", "READ_ONLY_CONFLICT"}:
                    raise SessionctlError(
                        f"run status cannot enter writer conflict: {current['status']}"
                    )
                else:
                    _set_run_status(current, "READ_ONLY_CONFLICT")
                current["writerLease"] = {}
                current["writerLeaseConflict"] = {
                    "holderRunId": lease.get("holderRunId", ""),
                    "holderSessionId": lease.get("holderSessionId", ""),
                    "worktreeId": worktree_id,
                    "epoch": lease.get("epoch", 0),
                    "observedAt": now_utc(),
                }
                current["updatedAt"] = now_utc()
                event = {
                    "event": "WRITER_LEASE_CONFLICT",
                    "runId": current["runId"],
                    "sessionId": current["sessionId"],
                    "worktreeId": worktree_id,
                    "holderRunId": lease.get("holderRunId", ""),
                    "holderSessionId": lease.get("holderSessionId", ""),
                    "epoch": lease.get("epoch", 0),
                    "at": now_utc(),
                }
                _append_run_audit(registry, current, event)
                registry.save_run(current)
                raise WriterLeaseConflict(
                    f"checkout writer lease is held by run {lease.get('holderRunId', '')}"
                )

            if current["status"] == "BLOCKED":
                raise WriterLeaseFenced(
                    str(current.get("leaseBlockReason") or "blocked run cannot reacquire writer lease")
                )
            if current["status"] not in {
                "BOOTSTRAPPED",
                "READ_ONLY_READY",
                "READ_ONLY_CONFLICT",
                "VALIDATED",
            }:
                raise SessionctlError(f"run status cannot acquire writer lease: {current['status']}")

            try:
                previous_epoch = int(lease.get("epoch") or 0)
            except (TypeError, ValueError) as exc:
                raise SessionctlError("checkout lease epoch is invalid") from exc
            epoch = previous_epoch + 1
            timestamp = now_utc()
            owner_uid = os.geteuid() if hasattr(os, "geteuid") else os.getuid()
            lease = {
                "schemaVersion": REGISTRY_VERSION,
                "leaseId": f"lease-{uuid.uuid4().hex}",
                "holderRunId": current["runId"],
                "holderSessionId": current["sessionId"],
                "runId": current["runId"],
                "sessionId": current["sessionId"],
                "client": current["client"],
                "repoKey": registry.repo_key,
                "worktreeId": worktree_id,
                "checkoutRoot": str(checkout),
                "checkoutKind": current["checkoutKind"],
                "epoch": epoch,
                "fencingToken": uuid.uuid4().hex,
                "state": LEASE_ACTIVE,
                "owner": f"uid:{owner_uid}",
                "ownerUid": owner_uid,
                "pid": pid,
                "processStartTime": process_start,
                "acquiredAt": timestamp,
                "heartbeatAt": timestamp,
                "updatedAt": timestamp,
                "releasedAt": "",
            }
            write_json_atomic(registry.writer_lease_path(worktree_id), lease)
            _invalidate_stop_validation_for_mutation(registry, current, timestamp=timestamp)
            if current["status"] != _writer_status(current):
                _set_run_status(current, _writer_status(current))
            current["writerLease"] = _lease_record_view(lease)
            current.pop("writerLeaseConflict", None)
            current.pop("leaseBlockReason", None)
            current["updatedAt"] = timestamp
            event = {
                "event": "WRITER_LEASE_ACQUIRED",
                "runId": current["runId"],
                "sessionId": current["sessionId"],
                "worktreeId": worktree_id,
                "leaseId": lease["leaseId"],
                "epoch": epoch,
                "at": timestamp,
            }
            _append_run_audit(registry, current, event)
            registry.save_run(current)
            return current, lease


# 仅在世代与围栏令牌仍匹配时刷新所持写租约的心跳。
def heartbeat_writer_lease(
    registry: Registry,
    record: dict[str, Any],
    *,
    expected_epoch: int | None = None,
    fencing_token: str = "",
) -> tuple[dict[str, Any], dict[str, Any]]:
    """参数：
        registry: 当前仓库的运行时 Registry。
        record: 当前运行记录。
        expected_epoch: 预期租约世代。
        fencing_token: 预期围栏令牌。

    返回：
        最新运行记录与刷新后的活动写租约。
    """

    _validate_lease_checkout(registry, record)
    worktree_id = str(record["worktreeId"])
    cached_epoch, cached_token = _cached_fence(record)
    epoch = int(expected_epoch if expected_epoch is not None else cached_epoch)
    token = fencing_token or cached_token
    if epoch <= 0 or not token:
        raise WriterLeaseFenced("heartbeat requires expected epoch and fencing token")
    with registry.checkout_mutation_locked(
        worktree_id,
        client=str(record["client"]),
        session_id=str(record["sessionId"]),
        run_id=str(record["runId"]),
    ):
        with registry.locked(
            client=str(record["client"]),
            session_id=str(record["sessionId"]),
            run_id=str(record["runId"]),
        ):
            current = _reload_lease_run(registry, record)
            lease = _load_checkout_lease(registry, worktree_id)
            if not _lease_fence_matches(
                lease,
                run_id=str(current["runId"]),
                session_id=str(current["sessionId"]),
                epoch=epoch,
                fencing_token=token,
            ):
                reason = "heartbeat epoch/fencing token does not match current checkout lease"
                _block_fenced_run(
                    registry, current, lease=lease, operation="heartbeat", reason=reason
                )
                raise WriterLeaseFenced(reason)
            timestamp = now_utc()
            lease["heartbeatAt"] = timestamp
            lease["updatedAt"] = timestamp
            write_json_atomic(registry.writer_lease_path(worktree_id), lease)
            current["writerLease"] = _lease_record_view(lease)
            current["updatedAt"] = timestamp
            registry.save_run(current)
            return current, lease


# 精确释放本运行的写租约，并忽略子 agent 的继承式结束事件。
def release_writer_lease(
    registry: Registry,
    record: dict[str, Any],
    *,
    expected_epoch: int | None = None,
    fencing_token: str = "",
    reason: str = "SessionEnd",
    inherited: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """参数：
        registry: 当前仓库的运行时 Registry。
        record: 当前运行记录。
        expected_epoch: 预期租约世代。
        fencing_token: 预期围栏令牌。
        reason: 释放原因。
        inherited: 是否为子 agent 继承的 SessionEnd 事件。

    返回：
        最新运行记录与释放后的写租约。
    """

    _validate_lease_checkout(registry, record)
    worktree_id = str(record["worktreeId"])
    cached_epoch, cached_token = _cached_fence(record)
    epoch = int(expected_epoch if expected_epoch is not None else cached_epoch)
    token = fencing_token or cached_token
    with registry.checkout_mutation_locked(
        worktree_id,
        client=str(record["client"]),
        session_id=str(record["sessionId"]),
        run_id=str(record["runId"]),
    ):
        with registry.locked(
            client=str(record["client"]),
            session_id=str(record["sessionId"]),
            run_id=str(record["runId"]),
        ):
            current = _reload_lease_run(registry, record)
            lease = _load_checkout_lease(registry, worktree_id)
            if inherited:
                event = {
                    "event": "SUBAGENT_LEASE_RELEASE_SKIPPED",
                    "runId": current["runId"],
                    "sessionId": current["sessionId"],
                    "worktreeId": worktree_id,
                    "at": now_utc(),
                }
                _append_run_audit(registry, current, event)
                current["updatedAt"] = event["at"]
                registry.save_run(current)
                return current, lease

            owns_active = (
                lease.get("state") == LEASE_ACTIVE
                and lease.get("holderRunId") == current["runId"]
                and lease.get("holderSessionId") == current["sessionId"]
            )
            if not owns_active and not epoch and not token:
                return current, lease
            if epoch <= 0 or not token or not _lease_fence_matches(
                lease,
                run_id=str(current["runId"]),
                session_id=str(current["sessionId"]),
                epoch=epoch,
                fencing_token=token,
            ):
                reason_text = "release epoch/fencing token does not match current checkout lease"
                _block_fenced_run(
                    registry, current, lease=lease, operation="release", reason=reason_text
                )
                raise WriterLeaseFenced(reason_text)

            timestamp = now_utc()
            lease["state"] = LEASE_RELEASED
            lease["releasedAt"] = timestamp
            lease["heartbeatAt"] = timestamp
            lease["updatedAt"] = timestamp
            lease["releaseReason"] = reason
            write_json_atomic(registry.writer_lease_path(worktree_id), lease)
            if current.get("status") in ACTIVE_WRITER_STATUSES:
                _set_run_status(current, "READ_ONLY_READY")
            current["writerLease"] = {}
            current["releasedWriterLease"] = {
                "leaseId": lease["leaseId"],
                "worktreeId": worktree_id,
                "epoch": epoch,
                "state": LEASE_RELEASED,
                "releasedAt": timestamp,
            }
            current["updatedAt"] = timestamp
            event = {
                "event": "WRITER_LEASE_RELEASED",
                "runId": current["runId"],
                "sessionId": current["sessionId"],
                "worktreeId": worktree_id,
                "leaseId": lease["leaseId"],
                "epoch": epoch,
                "reason": reason,
                "at": timestamp,
            }
            _append_run_audit(registry, current, event)
            registry.save_run(current)
            return current, lease


# 在 checkout 变更锁下受控回收已失活的写租约。
def reclaim_writer_lease(
    registry: Registry,
    requester: dict[str, Any],
    *,
    expected_epoch: int,
    expected_holder_run_id: str = "",
    expected_holder_session_id: str = "",
    stale_after_seconds: float = DEFAULT_LEASE_STALE_SECONDS,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """参数：
        registry: 当前仓库的运行时 Registry。
        requester: 请求回收的运行记录。
        expected_epoch: 预期租约世代。
        expected_holder_run_id: 预期原持有者运行标识符。
        expected_holder_session_id: 预期原持有者 Session 标识符。
        stale_after_seconds: 判定心跳失活的秒数阈值。

    返回：
        最新请求者运行记录与回收后的租约。
    """

    checkout = _validate_lease_checkout(registry, requester)
    if expected_epoch <= 0:
        raise SessionctlError("reclaim requires a positive expected epoch")
    if stale_after_seconds < 0:
        raise SessionctlError("reclaim stale threshold must be non-negative")
    worktree_id = str(requester["worktreeId"])
    with registry.checkout_mutation_locked(
        worktree_id,
        client=str(requester["client"]),
        session_id=str(requester["sessionId"]),
        run_id=str(requester["runId"]),
    ):
        with registry.locked(
            client=str(requester["client"]),
            session_id=str(requester["sessionId"]),
            run_id=str(requester["runId"]),
        ):
            current = _reload_lease_run(registry, requester)
            lease = _load_checkout_lease(registry, worktree_id)
            try:
                lease_epoch = int(lease.get("epoch") or 0)
            except (TypeError, ValueError) as exc:
                raise SessionctlError("checkout lease epoch is invalid") from exc
            if lease.get("state") != LEASE_ACTIVE:
                raise SessionctlError("reclaim target is not an active writer lease")
            if lease_epoch != expected_epoch:
                raise WriterLeaseFenced(
                    f"reclaim expected epoch {expected_epoch}, current epoch is {lease_epoch}"
                )
            if expected_holder_run_id and lease.get("holderRunId") != expected_holder_run_id:
                raise SessionctlError("reclaim target run does not match active lease")
            if expected_holder_session_id and lease.get("holderSessionId") != expected_holder_session_id:
                raise SessionctlError("reclaim target Session does not match active lease")
            if lease.get("holderRunId") == current["runId"]:
                raise SessionctlError("lease owner must use release instead of reclaim")
            if (
                lease.get("repoKey") != registry.repo_key
                or lease.get("worktreeId") != worktree_id
                or Path(str(lease.get("checkoutRoot") or "")).resolve() != checkout
            ):
                raise SessionctlError("reclaim target lease checkout identity is invalid")
            if git(checkout, "status", "--porcelain=v1", "--untracked-files=all").stdout.strip():
                raise SessionctlError("reclaim requires a clean checkout")

            heartbeat = _parse_utc(str(lease.get("heartbeatAt") or ""))
            heartbeat_age = (
                (datetime.now(timezone.utc) - heartbeat).total_seconds()
                if heartbeat is not None
                else float("inf")
            )
            try:
                owner_pid = int(lease.get("pid") or 0)
            except (TypeError, ValueError):
                owner_pid = 0
            owner_alive = process_is_alive(
                owner_pid, str(lease.get("processStartTime") or "")
            )
            if heartbeat_age < stale_after_seconds:
                raise SessionctlError("reclaim refused: heartbeat is not stale")
            if owner_alive:
                raise SessionctlError("reclaim refused: lease owner process is still alive")

            previous_holder_run = str(lease.get("holderRunId") or "")
            previous_holder_session = str(lease.get("holderSessionId") or "")
            timestamp = now_utc()
            reclaimed = dict(lease)
            reclaimed.update(
                {
                    "epoch": expected_epoch + 1,
                    "fencingToken": uuid.uuid4().hex,
                    "state": LEASE_RELEASED,
                    "heartbeatAt": timestamp,
                    "updatedAt": timestamp,
                    "releasedAt": timestamp,
                    "releaseReason": "controlled-reclaim",
                    "reclaimedFromEpoch": expected_epoch,
                    "reclaimedByRunId": current["runId"],
                    "reclaimedBySessionId": current["sessionId"],
                    "reclaimedAt": timestamp,
                }
            )
            write_json_atomic(registry.writer_lease_path(worktree_id), reclaimed)

            if previous_holder_run:
                try:
                    previous = registry.load_run(previous_holder_run)
                except SessionctlError:
                    previous = None
                if previous is not None:
                    _set_run_status(previous, "BLOCKED")
                    previous["leaseBlockReason"] = (
                        f"writer lease epoch {expected_epoch} was reclaimed by {current['runId']}"
                    )
                    previous["updatedAt"] = timestamp
                    previous_event = {
                        "event": "WRITER_LEASE_RECLAIMED_FROM_RUN",
                        "runId": previous_holder_run,
                        "sessionId": previous_holder_session,
                        "worktreeId": worktree_id,
                        "epoch": expected_epoch,
                        "newEpoch": expected_epoch + 1,
                        "reclaimedByRunId": current["runId"],
                        "at": timestamp,
                    }
                    _append_run_audit(registry, previous, previous_event)
                    registry.save_run(previous)

            event = {
                "event": "WRITER_LEASE_RECLAIMED",
                "runId": current["runId"],
                "sessionId": current["sessionId"],
                "worktreeId": worktree_id,
                "previousHolderRunId": previous_holder_run,
                "previousHolderSessionId": previous_holder_session,
                "epoch": expected_epoch,
                "newEpoch": expected_epoch + 1,
                "ownerAlive": owner_alive,
                "heartbeatAgeSeconds": heartbeat_age,
                "at": timestamp,
            }
            _append_run_audit(registry, current, event)
            current["updatedAt"] = timestamp
            registry.save_run(current)
            return current, reclaimed


# 通过当前 Session 身份绑定 OpenSpec 变更，不接受调用方运行标识。
def set_change_for_session(
    *, client: str, session_id: str, cwd: Path, change_id: str, task_id: str = ""
) -> dict[str, Any]:
    """参数：
        client: 当前客户端名称。
        session_id: 当前 Session 标识符。
        cwd: 当前 checkout 内的路径。
        change_id: 待绑定的 OpenSpec 变更标识符。
        task_id: 可选任务标识符。

    返回：
        完成变更绑定的最新运行记录。
    """
    client = client.strip()
    session_id = session_id.strip()
    change_id = change_id.strip()
    if not client or not session_id or not change_id:
        raise SessionctlError("set-change requires non-empty client, session-id, and change-id")
    checkout = resolve_checkout_root(cwd)
    _validate_identifier(change_id, "change id")
    if not (checkout / "openspec" / "changes" / change_id).is_dir():
        raise SessionctlError(f"OpenSpec change does not exist in current checkout: {change_id}")
    facts = _checkout_snapshot(checkout)
    registry = Registry(checkout)
    with registry.locked(client=client, session_id=session_id):
        matches = [
            item
            for item in registry.all_runs()
            if _record_matches_bootstrap(item, client=client, session_id=session_id, facts=facts)
        ]
        if len(matches) != 1:
            raise SessionctlError("set-change requires exactly one current Session run")
        record = matches[0]
        registry.update_lock_context(run_id=str(record["runId"]))
        previous = str(record.get("changeId") or "")
        previous_task = str(record.get("taskId") or "")
        record["changeId"] = change_id
        if task_id.strip():
            record["taskId"] = task_id.strip()
        record["updatedAt"] = now_utc()
        event = {
            "event": "CHANGE_BOUND",
            "runId": record["runId"],
            "client": client,
            "sessionId": session_id,
            "previousChangeId": previous,
            "changeId": change_id,
            "previousTaskId": previous_task,
            "taskId": record["taskId"],
            "at": now_utc(),
        }
        audit = record.setdefault("auditEvents", [])
        if not isinstance(audit, list):
            raise SessionctlError("run auditEvents must be a list")
        audit.append(event)
        registry.write_audit(event)
        registry.save_run(record)
    return record


# 执行 bootstrap 子命令并输出权威运行记录。
def cmd_bootstrap(args: argparse.Namespace) -> int:
    """参数：
        args: 已解析的 bootstrap 命令参数。

    返回：
        命令成功时返回零。
    """
    payload_hints = {"runId": args.run_id or "", "worktreeId": args.worktree_id or ""}
    env_hints = {
        "runId": os.environ.get("FEIPI_RUN_ID", ""),
        "worktreeId": os.environ.get("FEIPI_WORKTREE_ID", ""),
        "sessionId": os.environ.get("FEIPI_SESSION_ID", ""),
        "client": os.environ.get("FEIPI_CLIENT", "") or os.environ.get("FEIPI_AGENT_CLIENT", ""),
        "changeId": os.environ.get("ACTIVE_CHANGE_ID", ""),
    }
    record = bootstrap_session(
        client=args.client,
        session_id=args.session_id,
        cwd=Path(args.cwd),
        hook_event=args.hook_event,
        checkout_creator=args.checkout_creator,
        payload_hints=payload_hints,
        env_hints=env_hints,
        parent_run_id=args.parent_run_id or "",
    )
    print(json.dumps(record, indent=2, sort_keys=True))
    return 0


# 执行变更绑定子命令并输出最新运行记录。
def cmd_set_change(args: argparse.Namespace) -> int:
    """参数：
        args: 已解析的变更绑定命令参数。

    返回：
        命令成功时返回零。
    """
    record = set_change_for_session(
        client=args.client,
        session_id=args.session_id,
        cwd=Path(args.cwd),
        change_id=args.change_id,
        task_id=args.task_id or "",
    )
    print(json.dumps(record, indent=2, sort_keys=True))
    return 0


# 解析租约子命令使用的唯一当前运行记录。
def _lease_cli_record(
    *, client: str, session_id: str, cwd: Path, parent_run_id: str = ""
) -> tuple[Registry, dict[str, Any], bool]:
    """参数：
        client: 当前客户端名称。
        session_id: 当前 Session 标识符。
        cwd: 当前 checkout 内的路径。
        parent_run_id: 子 agent 继承的父运行标识符。

    返回：
        Registry、权威运行记录与是否继承父运行的标记。
    """

    checkout = resolve_checkout_root(cwd)
    registry = Registry(checkout)
    with registry.locked(client=client, session_id=session_id, run_id=parent_run_id):
        if parent_run_id:
            record = registry.load_run(_validate_identifier(parent_run_id, "parent run id"))
            if record.get("client") != client:
                raise SessionctlError("subagent client does not match parent run")
            _validate_lease_checkout(registry, record)
            if Path(str(record["checkoutRoot"])).resolve() != checkout:
                raise SessionctlError("subagent checkout does not match parent run")
            return registry, record, True
        facts = _checkout_snapshot(checkout)
        matches = [
            item
            for item in registry.all_runs()
            if _record_matches_bootstrap(
                item, client=client, session_id=session_id, facts=facts
            )
        ]
        if len(matches) != 1:
            raise SessionctlError("lease operation requires exactly one current Session run")
        return registry, matches[0], False


# 执行只读就绪子命令并输出最新运行记录。
def cmd_mark_read_only_ready(args: argparse.Namespace) -> int:
    """参数：
        args: 已解析的只读就绪命令参数。

    返回：
        命令成功时返回零。
    """
    registry, record, _ = _lease_cli_record(
        client=args.client,
        session_id=args.session_id,
        cwd=Path(args.cwd),
        parent_run_id=args.parent_run_id or "",
    )
    updated = mark_read_only_ready(registry, record)
    print(json.dumps(updated, indent=2, sort_keys=True))
    return 0


# 执行写租约获取子命令并输出最新运行记录。
def cmd_acquire_writer_lease(args: argparse.Namespace) -> int:
    """参数：
        args: 已解析的写租约获取命令参数。

    返回：
        命令成功时返回零。
    """
    registry, record, _ = _lease_cli_record(
        client=args.client,
        session_id=args.session_id,
        cwd=Path(args.cwd),
        parent_run_id=args.parent_run_id or "",
    )
    owner_pid = args.owner_pid if args.owner_pid is not None else os.getppid()
    updated, _ = acquire_writer_lease(
        registry,
        record,
        owner_pid=owner_pid,
        owner_start_time=args.owner_start_time or _pid_start_time(owner_pid),
    )
    print(json.dumps(updated, indent=2, sort_keys=True))
    return 0


# 执行写租约心跳子命令并输出最新运行记录。
def cmd_heartbeat_writer_lease(args: argparse.Namespace) -> int:
    """参数：
        args: 已解析的写租约心跳命令参数。

    返回：
        命令成功时返回零。
    """
    registry, record, _ = _lease_cli_record(
        client=args.client,
        session_id=args.session_id,
        cwd=Path(args.cwd),
        parent_run_id=args.parent_run_id or "",
    )
    updated, _ = heartbeat_writer_lease(
        registry,
        record,
        expected_epoch=args.epoch,
        fencing_token=args.fencing_token,
    )
    print(json.dumps(updated, indent=2, sort_keys=True))
    return 0


# 执行写租约释放子命令并输出最新运行记录。
def cmd_release_writer_lease(args: argparse.Namespace) -> int:
    """参数：
        args: 已解析的写租约释放命令参数。

    返回：
        命令成功时返回零。
    """
    registry, record, inherited = _lease_cli_record(
        client=args.client,
        session_id=args.session_id,
        cwd=Path(args.cwd),
        parent_run_id=args.parent_run_id or "",
    )
    updated, _ = release_writer_lease(
        registry,
        record,
        expected_epoch=args.epoch,
        fencing_token=args.fencing_token,
        reason=args.reason,
        inherited=inherited,
    )
    print(json.dumps(updated, indent=2, sort_keys=True))
    return 0


# 执行写租约回收子命令并输出运行记录与租约。
def cmd_reclaim_writer_lease(args: argparse.Namespace) -> int:
    """参数：
        args: 已解析的写租约回收命令参数。

    返回：
        命令成功时返回零。
    """
    registry, record, inherited = _lease_cli_record(
        client=args.client,
        session_id=args.session_id,
        cwd=Path(args.cwd),
        parent_run_id="",
    )
    if inherited:
        raise SessionctlError("subagent cannot reclaim a parent writer lease")
    updated, lease = reclaim_writer_lease(
        registry,
        record,
        expected_epoch=args.expected_epoch,
        expected_holder_run_id=args.expected_holder_run_id,
        expected_holder_session_id=args.expected_holder_session_id,
        stale_after_seconds=args.stale_after_seconds,
    )
    print(json.dumps({"record": updated, "lease": lease}, indent=2, sort_keys=True))
    return 0


# 维护 cmd_list 函数行为。
def cmd_list(args: argparse.Namespace) -> int:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或执行结果。
    """
    repo = repo_root_from_arg(args.repo_root)
    registry = Registry(repo)
    with registry.locked():
        records = registry.all_runs()
    if args.json:
        print(json.dumps(records, indent=2, sort_keys=True))
    else:
        for record in records:
            print(f"{record['runId']}\t{record['client']}\t{record['status']}\t{record['branch']}\t{record['checkoutRoot']}")
    return 0


# 维护 enrich_status 函数行为。
def enrich_status(record: dict[str, Any]) -> dict[str, Any]:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或执行结果。
    """
    worktree = Path(record["checkoutRoot"])
    enriched = dict(record)
    checks: dict[str, Any] = {"worktreeExists": worktree.exists()}
    if worktree.exists():
        facts, identity_errors = validate_checkout_record(worktree, record)
        checks["checkoutIdentityMatches"] = not identity_errors
        checks["checkoutIdentityErrors"] = identity_errors
        checks["observedBranch"] = facts["branch"]
        checks["detached"] = facts["detached"]
        checks["baseCommitExists"] = facts["baseCommitExists"]
        checks["baseIsAncestorOfHead"] = facts["baseIsAncestorOfHead"]
        checks["dirty"] = bool(git(worktree, "status", "--porcelain").stdout.strip())
    enriched["checks"] = checks
    return enriched


# 维护 cmd_status 函数行为。
def cmd_status(args: argparse.Namespace) -> int:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或执行结果。
    """
    repo = repo_root_from_arg(args.repo_root)
    registry = Registry(repo)
    with registry.locked():
        record = registry.load_run(args.run_id)
    print(json.dumps(enrich_status(record), indent=2, sort_keys=True))
    return 0


# 解析 ISO-8601 UTC 时间戳。
def _parse_utc(value: str) -> datetime | None:
    """参数：
        value: 表示世界协调时的标准时间戳。

    返回：
        解析后的 datetime；失败时返回 None。
    """
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


# 校验单条运行记录并返回 runtime doctor 错误。
def doctor_record(record: dict[str, Any]) -> list[str]:
    """参数：
        record: 待校验的 run record。

    返回：
        runtime capability 阻断原因列表。
    """
    errors: list[str] = []
    try:
        validate_run_record(record)
    except PrimarySessionValidationError as exc:
        errors.append(str(exc))
        return errors
    worktree = Path(record["checkoutRoot"])
    if not worktree.exists():
        errors.append("worktree root does not exist")
        return errors
    facts, identity_errors = validate_checkout_record(worktree, record)
    errors.extend(identity_errors)
    if record.get("baseCommit") and not facts["baseCommitExists"]:
        errors.append("base commit does not exist in checkout repository")
    return errors


# 将 run record 和 doctor 结果映射为明确 runtime capability。
def runtime_capability(record: dict[str, Any], errors: list[str]) -> str:
    """参数：
        record: 当前 run record。
        errors: doctor 阻断原因列表。

    返回：
        返回可写就绪、只读就绪或阻断状态。
    """
    if errors:
        return "blocked"
    if record.get("status") in ACTIVE_WRITER_STATUSES:
        return "writable-ready"
    if record.get("status") != "BLOCKED":
        return "read-only-ready"
    return "blocked"


# 维护 cmd_doctor 函数行为。
def cmd_doctor(args: argparse.Namespace) -> int:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或执行结果。
    """
    repo = repo_root_from_arg(args.repo_root)
    registry = Registry(repo)
    with registry.locked():
        records = [registry.load_run(args.run_id)] if args.run_id else registry.all_runs()
        collisions = validate_run_collisions(records) if records else []
    if not records:
        print(json.dumps({"capability": "read-only-ready", "checkedRuns": [], "status": "read-only-ready"}, indent=2, sort_keys=True))
        return 0
    errors = [f"{c.kind}: {c.message}" for c in collisions]
    run_errors: dict[str, list[str]] = {}
    capabilities: dict[str, str] = {}
    collision_run_ids = {c.first_run_id for c in collisions} | {c.second_run_id for c in collisions}
    for record in records:
        record_errors = doctor_record(record)
        if str(record.get("runId")) in collision_run_ids:
            record_errors.append("writer lease collision detected")
        run_id = str(record["runId"])
        run_errors[run_id] = record_errors
        capabilities[run_id] = runtime_capability(record, record_errors)
        errors.extend(f"{run_id}: {msg}" for msg in record_errors)
    if errors:
        print(json.dumps({"status": "blocked", "capability": "blocked", "capabilities": capabilities, "errors": errors}, indent=2, sort_keys=True))
        return 2
    aggregate = "writable-ready" if any(value == "writable-ready" for value in capabilities.values()) else "read-only-ready"
    print(json.dumps({"status": aggregate, "capability": aggregate, "capabilities": capabilities, "checkedRuns": [r["runId"] for r in records]}, indent=2, sort_keys=True))
    return 0



# 仅在门禁通过的 Git 快照仍新鲜时持久化 Stop 结果。
def record_stop_result(
    repo_root: Path,
    run_id: str,
    *,
    stop_exit: int,
    summary_status: str,
    validated_facts: Mapping[str, Any],
    handoff_on_failure: bool = False,
    retryable_failure: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """参数：
        repo_root: 当前仓库根目录。
        run_id: 待更新的运行标识符。
        stop_exit: Stop 执行退出码。
        summary_status: Stop 摘要状态。
        validated_facts: 门禁验证时采集的 Git 事实。
        handoff_on_failure: 失败时是否转为交接状态。
        retryable_failure: 失败时是否保留当前 run 的安全修复能力。

    返回：
        最新运行记录与最终采用的 Git 事实。
    """

    registry = Registry(repo_root)
    with registry.locked():
        latest = registry.load_run(run_id)
        try:
            current_facts = _collect_git_facts(latest)
            evidence_error = ""
        except GitEvidenceError as exc:
            evidence_error = str(exc)
            current_facts = {
                "queryErrors": [evidence_error],
                "gitFactErrors": [evidence_error],
            }
        facts = dict(validated_facts)
        pass_requested = stop_exit == 0 and summary_status == "PASS"
        expected_fingerprint = str(facts.get("checkoutFingerprint") or "")
        current_fingerprint = str(current_facts.get("checkoutFingerprint") or "")
        if pass_requested and not evidence_error:
            if not expected_fingerprint:
                evidence_error = "Stop validation evidence has no checkout fingerprint"
            elif expected_fingerprint != current_fingerprint:
                evidence_error = "checkout Git snapshot changed after required gates"
            elif str(facts.get("headCommit") or "") != str(
                current_facts.get("headCommit") or ""
            ):
                evidence_error = "checkout HEAD changed after required gates"
        passed = pass_requested and not evidence_error
        if handoff_on_failure:
            failure_status = "HANDOFF_REQUIRED"
        elif retryable_failure:
            failure_status = (
                _writer_status(latest)
                if latest.get("status") in ACTIVE_WRITER_STATUSES
                and isinstance(latest.get("writerLease"), dict)
                and latest.get("writerLease")
                else "READ_ONLY_READY"
            )
        else:
            failure_status = "BLOCKED"
        final_status = "VALIDATED" if passed else failure_status
        receipt_facts = facts if passed else current_facts
        head = str(receipt_facts.get("headCommit") or latest.get("headCommit") or "")
        target_commit = str(
            (facts if pass_requested else receipt_facts).get("targetHead") or ""
        )
        fingerprint = expected_fingerprint if pass_requested else current_fingerprint
        result_key = hashlib.sha256(
            json.dumps(
                {
                    "runId": run_id,
                    "stopExit": stop_exit,
                    "summaryStatus": summary_status,
                    "headCommit": head,
                    "targetCommit": target_commit,
                    "checkoutFingerprint": fingerprint,
                    "evidenceError": evidence_error,
                    "retryableFailure": retryable_failure,
                },
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        if (
            latest.get("stopResultKey") == result_key
            and latest.get("status") == final_status
        ):
            stored_facts = latest.get("stopGitFacts")
            return latest, stored_facts if isinstance(stored_facts, dict) else receipt_facts

        if latest.get("status") != "VALIDATING":
            _set_run_status(latest, "VALIDATING")
        _set_run_status(latest, final_status)
        latest["headCommit"] = head
        latest["stopExitCode"] = stop_exit
        timestamp = now_utc()
        latest["stopValidation"] = {
            "status": "PASS" if passed else "FAIL",
            "summaryStatus": summary_status,
            "fresh": passed,
            "validatedAt": timestamp,
            "headCommit": head,
            "targetCommit": target_commit,
            "checkoutFingerprint": fingerprint,
            "evidenceError": evidence_error,
        }
        latest["stopGitFacts"] = receipt_facts
        latest["stopResultKey"] = result_key
        latest.pop("validationStaleAt", None)
        latest.pop("validationStaleReason", None)
        latest["updatedAt"] = timestamp
        outcome_event = (
            "STOP_VALIDATED"
            if passed
            else "STOP_HANDOFF_REQUIRED"
            if final_status == "HANDOFF_REQUIRED"
            else "STOP_RETRYABLE_BLOCKED"
            if retryable_failure
            else "STOP_BLOCKED"
        )
        _append_run_audit(
            registry,
            latest,
            {
                "event": outcome_event,
                "runId": latest["runId"],
                "sessionId": latest["sessionId"],
                "worktreeId": latest["worktreeId"],
                "headCommit": head,
                "targetCommit": target_commit,
                "stopExitCode": stop_exit,
                "evidenceError": evidence_error,
                "at": timestamp,
            },
        )
        registry.save_run(latest)
        return latest, receipt_facts


# 维护 cmd_stop 函数行为。
def cmd_stop(args: argparse.Namespace) -> int:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或执行结果。
    """
    repo = repo_root_from_arg(args.repo_root)
    registry = Registry(repo)
    with registry.locked():
        record = registry.load_run(args.run_id)
        record["stopRequestedAt"] = now_utc()
        _set_run_status(record, "VALIDATING")
        record["updatedAt"] = now_utc()
        registry.save_run(record)

    from scripts.harness.stop_entry import run_stop  # noqa: PLC0415 - avoid CLI import cycle

    payload = {
        "cwd": record["checkoutRoot"],
        "session_id": record.get("sessionId", ""),
        "sessionId": record.get("sessionId", ""),
        "run_id": record["runId"],
        "runId": record["runId"],
        "task_id": record["taskId"],
        "taskId": record["taskId"],
        "worktree_id": record["worktreeId"],
        "worktreeId": record["worktreeId"],
        "agent_client": record["client"],
        "client": record["client"],
    }
    stop_exit = run_stop(
        str(record["client"]),
        payload,
        handoff_on_failure=bool(getattr(args, "handoff_on_failure", False)),
        adapter_mode="cli",
    )

    with registry.locked():
        latest = registry.load_run(args.run_id)
    facts = latest.get("stopGitFacts")
    if not isinstance(facts, dict):
        try:
            facts = _collect_git_facts(latest)
        except GitEvidenceError as exc:
            facts = {"queryErrors": [str(exc)], "gitFactErrors": [str(exc)]}

    status = latest["status"]
    print(
        json.dumps(
            {
                "status": status,
                "runId": args.run_id,
                "stopExitCode": stop_exit,
                "killedProcess": False,
                "gitFacts": facts,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if status == "VALIDATED" else 2


# 维护 cmd_handoff 函数行为。
def cmd_handoff(args: argparse.Namespace) -> int:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或执行结果。
    """
    repo = repo_root_from_arg(args.repo_root)
    registry = Registry(repo)
    with registry.locked():
        record = registry.load_run(args.run_id)
        other_records = [
            item
            for item in registry.all_runs()
            if item.get("runId") != record.get("runId")
        ]
    facts = _collect_git_facts(record)
    blocking_failures = doctor_record(record)
    scope_overlaps = [
        f"{collision.kind}: {collision.message}"
        for collision in validate_run_collisions([record] + other_records)
        if record["runId"] in {collision.first_run_id, collision.second_run_id}
    ]
    report = {
        "status": record.get("status", ""),
        "runId": record["runId"],
        "taskId": record["taskId"],
        "client": record["client"],
        "sessionId": record.get("sessionId", ""),
        "worktreeId": record.get("worktreeId", ""),
        "checkoutRoot": record["checkoutRoot"],
        "branch": record["branch"],
        "observedBranch": facts["checkout"]["branch"],
        "detached": facts["checkout"]["detached"],
        "checkoutKind": facts["checkout"]["checkoutKind"],
        "checkoutCreator": facts["checkout"]["checkoutCreator"],
        "gitCommonDir": facts["checkout"]["gitCommonDir"],
        "primaryRepoRoot": record.get("primaryRepoRoot", ""),
        "baseCommit": record["baseCommit"],
        "mergeBase": facts["mergeBase"],
        "headCommit": facts["headCommit"],
        "targetBranch": record.get("targetBranch", ""),
        "changeId": record["changeId"],
        "changedFiles": facts["changedFiles"],
        "committedFiles": facts["committedFiles"],
        "uncommittedFiles": facts["uncommittedFiles"],
        "untrackedFiles": facts["untrackedFiles"],
        "commits": facts["commits"],
        "aheadBehind": facts["aheadBehind"],
        "initialDirtyBaseline": facts["initialDirtyBaseline"],
        "targetStatus": facts["targetStatus"],
        "primaryStatus": facts["primaryStatus"],
        "gitFacts": facts,
        "requiredTargetSummary": record.get("requiredTargetSummary", {"allowedPaths": record.get("allowedPaths", []), "forbiddenPaths": record.get("forbiddenPaths", [])}),
        "qualityArtifacts": record.get("qualityArtifacts", []),
        "artifactPaths": {
            "runRecord": str(registry._run_path(str(record["runId"]))),
            "runtimeRoot": str(registry.root),
            "checkoutRoot": record["checkoutRoot"],
        },
        "blockingFailures": blocking_failures,
        "mergeRisk": {
            "writeScopeOverlap": scope_overlaps,
            "dirtyWorktree": not facts["checkoutStatus"]["clean"],
            "initialDirtyAmbiguous": bool(
                isinstance(record.get("initialDirtySnapshot"), dict)
                and record["initialDirtySnapshot"].get("dirty")
            ),
        },
        "risks": record.get("risks", []) + scope_overlaps,
        "manualNextSteps": [
            "review changedFiles and blockingFailures",
            "run required gates before merge",
            f"python3 scripts/harness/sessionctl.py finalize --run-id {record['runId']}",
            "release only this run's lease; the provider-owned checkout is preserved",
        ],
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


# 仅返回由权威运行身份推导出的证据路径及其允许根目录。
def _cleanup_evidence_paths(
    registry: Registry, record: Mapping[str, Any]
) -> list[tuple[Path, Path]]:
    """参数：
        registry: 当前仓库的运行时 Registry。
        record: 待清理的权威运行记录。

    返回：
        精确证据路径及其允许根目录组成的列表。
    """

    validate_run_record(dict(record))
    run_id = _validate_identifier(str(record.get("runId") or ""), "run id")
    client = _validate_identifier(str(record.get("client") or ""), "client")
    session_id = _validate_identifier(str(record.get("sessionId") or ""), "session id")
    if record.get("repoKey") != registry.repo_key:
        raise SessionctlError("cleanup run does not belong to this Registry")
    checkout = resolve_checkout_root(Path(str(record.get("checkoutRoot") or "")))
    _, identity_errors = validate_checkout_record(checkout, dict(record))
    if identity_errors:
        raise SessionctlError("cleanup checkout identity mismatch: " + "; ".join(identity_errors))
    runtime = registry.root.resolve()
    return [
        (
            checkout
            / "tmp"
            / "agent_logs"
            / client
            / session_id
            / "runs"
            / run_id,
            checkout,
        ),
        (
            checkout
            / "tmp"
            / "quality"
            / client
            / session_id
            / "runs"
            / run_id,
            checkout,
        ),
        (registry.runs_dir / run_id, runtime),
        (runtime / "integration" / f"{run_id}.json", runtime),
        (runtime / "integration" / f"{run_id}.handoff.json", runtime),
    ]


# 在不跟随路径组件符号链接的前提下删除精确证据路径。
def _remove_exact_run_evidence(path: Path, *, allowed_root: Path) -> bool:
    """参数：
        path: 待删除的精确证据路径。
        allowed_root: 证据路径必须位于的允许根目录。

    返回：
        实际删除证据时返回 true；路径不存在时返回 false。
    """

    root = Path(os.path.abspath(allowed_root))
    candidate = Path(os.path.abspath(path))
    try:
        relative = candidate.relative_to(root)
    except ValueError as exc:
        raise SessionctlError(f"cleanup evidence escapes allowed root: {candidate}") from exc
    if not relative.parts:
        raise SessionctlError("cleanup refuses to remove an evidence root")
    cursor = root
    for component in relative.parts[:-1]:
        cursor /= component
        try:
            metadata = cursor.lstat()
        except FileNotFoundError:
            return False
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise SessionctlError(f"unsafe cleanup evidence ancestor: {cursor}")
    try:
        metadata = candidate.lstat()
    except FileNotFoundError:
        return False
    if stat.S_ISLNK(metadata.st_mode):
        raise SessionctlError(f"refusing symlink cleanup evidence: {candidate}")
    if hasattr(os, "geteuid") and metadata.st_uid != os.geteuid():
        raise SessionctlError(f"cleanup evidence is not owned by current user: {candidate}")
    if stat.S_ISDIR(metadata.st_mode):
        shutil.rmtree(candidate)
    elif stat.S_ISREG(metadata.st_mode):
        candidate.unlink()
    else:
        raise SessionctlError(f"refusing special cleanup evidence path: {candidate}")
    return True


# 执行单个运行的租约与证据清理，同时保留 provider 管理的 checkout。
def cmd_cleanup(args: argparse.Namespace) -> int:
    """参数：
        args: 已解析的清理命令参数。

    返回：
        预览或执行成功时返回零。
    """
    repo = repo_root_from_arg(args.repo_root)
    registry = Registry(repo)
    with registry.locked():
        record = registry.load_run(args.run_id)
        if record.get("runId") != args.run_id:
            raise SessionctlError("cleanup run id does not match Registry record")
        evidence = _cleanup_evidence_paths(registry, record)
    evidence_actions = [
        {"path": str(path), "exists": os.path.lexists(path)} for path, _ in evidence
    ]
    actions = {
        "releaseWriterLease": bool(record.get("writerLease")),
        "preserveCheckout": str(record["checkoutRoot"]),
        "removeCheckout": False,
        "removeBranch": False,
        "removeRunRecord": str(registry._run_path(str(record["runId"]))),
        "removeEvidence": evidence_actions,
        "dryRun": not args.execute,
    }
    if not args.execute:
        print(
            json.dumps(
                {"status": "dry-run", "runId": args.run_id, "actions": actions},
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    if record.get("writerLease"):
        release_writer_lease(registry, record, reason="cleanup")
    timestamp = now_utc()
    removed_evidence: list[str] = []
    with registry.locked():
        latest = registry.load_run(args.run_id)
        if latest.get("repoKey") != record.get("repoKey") or latest.get("worktreeId") != record.get("worktreeId"):
            raise SessionctlError("cleanup run identity changed before evidence removal")
        current_evidence = _cleanup_evidence_paths(registry, latest)
        for path, allowed_root in current_evidence:
            if _remove_exact_run_evidence(path, allowed_root=allowed_root):
                removed_evidence.append(str(path))
        event = {
            "event": "RUN_CLEANUP_EVIDENCE_REMOVED",
            "runId": latest["runId"],
            "sessionId": latest["sessionId"],
            "worktreeId": latest["worktreeId"],
            "checkoutPreserved": True,
            "removedEvidence": removed_evidence,
            "at": timestamp,
        }
        registry.write_audit(event)
        registry.remove_run_record(
            args.run_id,
            expected_repo_key=str(latest["repoKey"]),
            expected_checkout_root=Path(str(latest["checkoutRoot"])),
        )
    actions["dryRun"] = False
    actions["removedEvidence"] = removed_evidence
    print(
        json.dumps(
            {"status": "cleanup-complete", "runId": args.run_id, "actions": actions},
            indent=2,
            sort_keys=True,
        )
    )
    return 0


# 从 Git 事实中提取内容敏感的 checkout 指纹。
def _checkout_fingerprint(facts: Mapping[str, Any]) -> str:
    """参数：
        facts: 已采集的 Git 事实。

    返回：
        内容敏感的 checkout 指纹。

    异常：
        GitEvidenceError: 证据不含有效指纹时抛出。
    """
    fingerprint = str(facts.get("checkoutFingerprint") or "")
    if not fingerprint:
        snapshot = facts.get("checkoutSnapshot")
        if isinstance(snapshot, Mapping):
            fingerprint = str(snapshot.get("fingerprint") or "")
    if not fingerprint:
        raise GitEvidenceError("Git evidence has no content-sensitive checkout fingerprint")
    return fingerprint


# 为共享 Git 证据补充展示与新鲜度校验所需元数据。
def _collect_git_facts(record: Mapping[str, Any]) -> dict[str, Any]:
    """参数：
        record: 当前权威运行记录。

    返回：
        已补充 checkout 展示字段与指纹的 Git 事实。
    """

    facts = collect_git_evidence(
        Path(str(record.get("checkoutRoot") or "")), dict(record)
    )
    checkout_status = facts["checkoutStatus"]
    facts["checkout"] = {
        "checkoutKind": facts["checkoutKind"],
        "checkoutCreator": facts["checkoutCreator"],
        "branch": checkout_status["branch"],
        "detached": checkout_status["detached"],
        "gitCommonDir": record.get("gitCommonDir", ""),
    }
    facts["gitFactErrors"] = list(facts.get("queryErrors", []))
    facts["checkoutFingerprint"] = _checkout_fingerprint(facts)
    return facts


# 写入交接摘要。
def _write_handoff(registry: Registry, record: dict[str, Any], reason: str) -> Path:
    """参数：
        registry: 运行时注册表。
        record: 运行记录。
        reason: 交接原因。

    返回：
        交接摘要路径。
    """
    try:
        facts: dict[str, Any] = _collect_git_facts(record)
    except GitEvidenceError as exc:
        facts = {"queryErrors": [str(exc)], "gitFactErrors": [str(exc)]}
    report = {
        "schemaVersion": REGISTRY_VERSION,
        "status": "HANDOFF_REQUIRED",
        "reason": reason,
        "runId": record["runId"],
        "sessionId": record.get("sessionId", ""),
        "worktreeId": record.get("worktreeId", ""),
        "checkoutRoot": record.get("checkoutRoot", ""),
        "checkoutKind": record.get("checkoutKind", ""),
        "checkoutCreator": record.get("checkoutCreator", "unknown"),
        "targetBranch": record.get("targetBranch", ""),
        "branch": record["branch"],
        "baseCommit": record.get("baseCommit", ""),
        "headCommit": facts.get("headCommit", ""),
        "commits": facts.get("commits", []),
        "committedFiles": facts.get("committedFiles", []),
        "uncommittedFiles": facts.get("uncommittedFiles", []),
        "untrackedFiles": facts.get("untrackedFiles", []),
        "aheadBehind": facts.get("aheadBehind", {}),
        "mergeBase": facts.get("mergeBase", ""),
        "initialDirtyBaseline": facts.get(
            "initialDirtyBaseline", record.get("initialDirtySnapshot", {})
        ),
        "targetStatus": facts.get("targetStatus", {}),
        "primaryStatus": facts.get("primaryStatus", {}),
        "gitFacts": facts,
        "requiredGateStatus": record.get("stopExitCode", "unknown"),
        "mergeRisk": reason,
        "finalizeCommand": f"python3 scripts/harness/sessionctl.py finalize --run-id {record['runId']}",
    }
    path = registry.root / "integration" / f"{record['runId']}.handoff.json"
    write_json_atomic(path, report)
    return path


# 标记运行进入需要人工交接状态。
def _mark_handoff(registry: Registry, record: dict[str, Any], reason: str) -> None:
    """参数：
        registry: 运行时注册表。
        record: 运行记录。
        reason: 交接原因。
    """
    path = _write_handoff(registry, record, reason)
    if record.get("status") != "HANDOFF_REQUIRED":
        _set_run_status(record, "HANDOFF_REQUIRED")
    record["handoffSummary"] = str(path)
    timestamp = now_utc()
    record["updatedAt"] = timestamp
    _append_run_audit(
        registry,
        record,
        {
            "event": "FINALIZE_HANDOFF_REQUIRED",
            "runId": record["runId"],
            "sessionId": record["sessionId"],
            "worktreeId": record["worktreeId"],
            "reason": reason,
            "at": timestamp,
        },
    )
    registry.save_run(record)


# 持久化运行级交接摘要，并仅精确释放该运行租约。
def _finalize_handoff(registry: Registry, run_id: str, reason: str) -> int:
    """参数：
        registry: 当前仓库的运行时 Registry。
        run_id: 需要交接的运行标识符。
        reason: 交接原因。

    返回：
        表示需要人工交接的非零退出码。
    """

    with registry.locked():
        record = registry.load_run(run_id)
        _mark_handoff(registry, record, reason)
    if record.get("writerLease"):
        release_writer_lease(registry, record, reason="finalize-handoff")
    print(
        json.dumps(
            {"status": "HANDOFF_REQUIRED", "runId": run_id, "reason": reason},
            indent=2,
            sort_keys=True,
        )
    )
    return 2


# 判断一个 Git 提交是否为另一个提交的祖先。
def _git_is_ancestor(repo: Path, ancestor: str, descendant: str) -> bool:
    """参数：
        repo: 执行 Git 查询的仓库目录。
        ancestor: 候选祖先提交。
        descendant: 候选后代提交。

    返回：
        两个提交均非空且祖先关系成立时返回 true。
    """
    return bool(
        ancestor
        and descendant
        and git(
            repo,
            "merge-base",
            "--is-ancestor",
            ancestor,
            descendant,
            check=False,
        ).returncode
        == 0
    )


# 检查 Stop 验证凭据是否仍与当前 Git 事实一致。
def _fresh_validation_error(
    record: Mapping[str, Any], facts: Mapping[str, Any], *, require_target_match: bool
) -> str:
    """参数：
        record: 当前权威运行记录。
        facts: 当前 Git 事实。
        require_target_match: 是否同时要求目标提交完全匹配。

    返回：
        验证失效原因；凭据仍新鲜时返回空字符串。
    """
    if record.get("status") != "VALIDATED" or record.get("stopExitCode") != 0:
        return "required gates are not fresh PASS"
    validation = record.get("stopValidation")
    if not isinstance(validation, Mapping) or validation.get("status") != "PASS":
        return "required gates are not fresh PASS"
    if validation.get("fresh") is not True:
        return "Stop validation is stale"
    if str(validation.get("headCommit") or "") != str(facts.get("headCommit") or ""):
        return "checkout HEAD changed after Stop validation"
    if str(validation.get("checkoutFingerprint") or "") != _checkout_fingerprint(facts):
        return "checkout Git state changed after Stop validation"
    if require_target_match and str(validation.get("targetCommit") or "") != str(
        facts.get("targetHead") or ""
    ):
        return "target branch changed after Stop validation"
    return ""


# 在 finalize 流程中静默重新执行 Stop 验证。
def _revalidate_for_finalize(registry: Registry, record: Mapping[str, Any]) -> bool:
    """参数：
        registry: 当前仓库的运行时 Registry。
        record: 待重新验证的运行记录。

    返回：
        Stop 重新验证通过时返回 true。
    """
    with contextlib.redirect_stdout(io.StringIO()):
        result = cmd_stop(
            argparse.Namespace(
                repo_root=str(registry.primary_repo_root),
                run_id=str(record["runId"]),
                handoff_on_failure=True,
            )
        )
    return result == 0


# 安全集成运行 checkout 到目标分支。
def cmd_finalize(args: argparse.Namespace) -> int:
    """参数：
        args: 已解析的 finalize 命令参数。

    返回：
        安全集成完成时返回零；需要交接时返回非零。
    """

    selected_checkout = repo_root_from_arg(args.repo_root)
    registry = Registry(selected_checkout)
    lock_dir = ensure_private_directory(registry.root / "locks", root=registry.root)
    lock_path = lock_dir / "integration.lock"
    with lock_path.open("a+", encoding="utf-8") as lock:
        os.chmod(lock_path, 0o600)
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        with registry.locked():
            record = registry.load_run(args.run_id)
        if record.get("status") == "INTEGRATED":
            print(
                json.dumps(
                    {"status": "INTEGRATED", "runId": args.run_id, "idempotent": True},
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0

        checkout = Path(str(record.get("checkoutRoot") or ""))
        primary = Path(str(record.get("primaryRepoRoot") or ""))
        target = str(record.get("targetBranch") or "")
        if not checkout.exists():
            return _finalize_handoff(registry, args.run_id, "run checkout missing")
        if not primary.exists():
            return _finalize_handoff(registry, args.run_id, "primary checkout missing")
        if not target:
            return _finalize_handoff(registry, args.run_id, "missing target branch")
        if git(primary, "check-ref-format", "--branch", target, check=False).returncode != 0:
            return _finalize_handoff(registry, args.run_id, "invalid target branch")
        try:
            facts = _collect_git_facts(record)
        except GitEvidenceError as exc:
            return _finalize_handoff(registry, args.run_id, f"Git evidence unavailable: {exc}")

        initial_dirty = record.get("initialDirtySnapshot")
        if not isinstance(initial_dirty, Mapping) or initial_dirty.get("dirty"):
            return _finalize_handoff(
                registry,
                args.run_id,
                "initial dirty baseline cannot be safely attributed",
            )
        if not facts["targetStatus"]["exists"]:
            return _finalize_handoff(registry, args.run_id, "target branch is missing")
        if facts["primaryStatus"]["branch"] != target:
            return _finalize_handoff(
                registry,
                args.run_id,
                "primary checkout is not on the recorded target branch",
            )
        if not facts["primaryStatus"]["clean"]:
            return _finalize_handoff(registry, args.run_id, "primary checkout dirty")
        if not facts["checkoutStatus"]["clean"]:
            return _finalize_handoff(
                registry, args.run_id, "run checkout has uncommitted or untracked files"
            )
        if facts["checkoutStatus"]["detached"]:
            return _finalize_handoff(
                registry,
                args.run_id,
                "detached HEAD requires a provider-owned branch or manual handoff",
            )
        validation_error = _fresh_validation_error(
            record, facts, require_target_match=False
        )
        if validation_error:
            return _finalize_handoff(registry, args.run_id, validation_error)

        original_run_head = str(facts["headCommit"])
        validated_target = str(record["stopValidation"].get("targetCommit") or "")
        target_old = str(facts["targetHead"])
        strategy = "ff-only"
        if validated_target != target_old:
            if not _git_is_ancestor(checkout, validated_target, target_old):
                return _finalize_handoff(
                    registry,
                    args.run_id,
                    "target branch was rewritten or moved backwards after validation",
                )
            if not _git_is_ancestor(checkout, target_old, original_run_head):
                base = str(record.get("baseCommit") or "")
                if not (
                    _git_is_ancestor(checkout, base, target_old)
                    and _git_is_ancestor(checkout, base, original_run_head)
                ):
                    return _finalize_handoff(
                        registry,
                        args.run_id,
                        "target and result ancestry cannot be safely rebased",
                    )
                strategy = "rebase-then-ff"
                target_ref = f"refs/heads/{target}"
                rebase = git(checkout, "rebase", target_ref, check=False)
                if rebase.returncode != 0:
                    git(checkout, "rebase", "--abort", check=False)
                    return _finalize_handoff(
                        registry, args.run_id, "target advanced with conflicts"
                    )
            else:
                strategy = "revalidate-then-ff"
            if not _revalidate_for_finalize(registry, record):
                return _finalize_handoff(
                    registry, args.run_id, "revalidation failed after target advanced"
                )
            with registry.locked():
                record = registry.load_run(args.run_id)
            try:
                facts = _collect_git_facts(record)
            except GitEvidenceError as exc:
                return _finalize_handoff(
                    registry, args.run_id, f"Git evidence unavailable after revalidation: {exc}"
                )
            validation_error = _fresh_validation_error(
                record, facts, require_target_match=True
            )
            if validation_error:
                return _finalize_handoff(registry, args.run_id, validation_error)

        run_head = str(facts["headCommit"])
        target_old = str(facts["targetHead"])
        if not _git_is_ancestor(checkout, target_old, run_head):
            return _finalize_handoff(
                registry, args.run_id, "result is not a fast-forward of target"
            )

        if record.get("writerLease"):
            heartbeat_writer_lease(registry, record)
        with registry.locked():
            record = registry.load_run(args.run_id)
            _set_run_status(record, "INTEGRATING")
            record["headCommit"] = run_head
            record["updatedAt"] = now_utc()
            registry.save_run(record)

        try:
            before_merge = _collect_git_facts(record)
        except GitEvidenceError as exc:
            return _finalize_handoff(
                registry, args.run_id, f"Git evidence changed before integration: {exc}"
            )
        if (
            before_merge["targetHead"] != target_old
            or before_merge["primaryStatus"]["branch"] != target
            or not before_merge["primaryStatus"]["clean"]
            or not before_merge["checkoutStatus"]["clean"]
            or before_merge["headCommit"] != run_head
        ):
            return _finalize_handoff(
                registry, args.run_id, "Git state changed before integration"
            )

        same_checkout = checkout.resolve() == primary.resolve()
        if same_checkout:
            if target_old != run_head:
                return _finalize_handoff(
                    registry,
                    args.run_id,
                    "primary checkout target does not match validated HEAD",
                )
            strategy = "already-on-target"
        else:
            merge = git(primary, "merge", "--ff-only", run_head, check=False)
            if merge.returncode != 0:
                return _finalize_handoff(registry, args.run_id, "ff-only integration failed")

        target_new_result = git(
            primary, "rev-parse", "--verify", f"refs/heads/{target}", check=False
        )
        target_new = target_new_result.stdout.strip() if target_new_result.returncode == 0 else ""
        if target_new != run_head:
            return _finalize_handoff(
                registry, args.run_id, "target did not reach the validated result"
            )

        with registry.locked():
            record = registry.load_run(args.run_id)
        if record.get("writerLease"):
            record, _ = release_writer_lease(
                registry, record, reason="finalize-integrated"
            )
        timestamp = now_utc()
        summary = {
            "schemaVersion": REGISTRY_VERSION,
            "status": "INTEGRATED",
            "runId": args.run_id,
            "oldTarget": target_old,
            "baseCommit": record.get("baseCommit"),
            "originalRunHead": original_run_head,
            "integratedHead": target_new,
            "strategy": strategy,
            "checkoutRoot": str(checkout),
            "checkoutKind": record.get("checkoutKind", ""),
            "checkoutCreator": record.get("checkoutCreator", "unknown"),
            "checkoutPreserved": checkout.exists(),
            "pushed": False,
            "artifacts": record.get("qualityArtifacts", []),
            "integratedAt": timestamp,
        }
        summary_path = registry.root / "integration" / f"{args.run_id}.json"
        write_json_atomic(summary_path, summary)
        with registry.locked():
            record = registry.load_run(args.run_id)
            _set_run_status(record, "INTEGRATED")
            record["headCommit"] = target_new
            record["integrationSummary"] = str(summary_path)
            record["updatedAt"] = timestamp
            _append_run_audit(
                registry,
                record,
                {
                    "event": "RUN_INTEGRATED",
                    "runId": record["runId"],
                    "sessionId": record["sessionId"],
                    "worktreeId": record["worktreeId"],
                    "targetBranch": target,
                    "targetCommit": target_new,
                    "strategy": strategy,
                    "checkoutPreserved": True,
                    "at": timestamp,
                },
            )
            registry.save_run(record)
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0


# 维护 build_parser 函数行为。
def build_parser() -> argparse.ArgumentParser:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或执行结果。
    """
    parser = argparse.ArgumentParser(description="Manage Feipi adopted-checkout Session runtime")
    parser.add_argument("--repo-root", help="Git repository root; defaults to cwd")
    sub = parser.add_subparsers(dest="command", required=True)

    bootstrap = sub.add_parser("bootstrap")
    bootstrap.add_argument("--client", required=True, choices=["codex", "qoder", "claude"])
    bootstrap.add_argument("--session-id", required=True)
    bootstrap.add_argument("--cwd", required=True)
    bootstrap.add_argument("--hook-event", required=True)
    bootstrap.add_argument(
        "--checkout-creator",
        choices=sorted(CHECKOUT_CREATORS),
        default="unknown",
    )
    bootstrap.add_argument("--run-id", "--payload-run-id", dest="run_id")
    bootstrap.add_argument("--worktree-id", "--payload-worktree-id", dest="worktree_id")
    bootstrap.add_argument("--parent-run-id")
    bootstrap.set_defaults(func=cmd_bootstrap)

    set_change = sub.add_parser("set-change")
    set_change.add_argument("--client", required=True, choices=["codex", "qoder", "claude"])
    set_change.add_argument("--session-id", required=True)
    set_change.add_argument("--cwd", required=True)
    set_change.add_argument("--change-id", required=True)
    set_change.add_argument("--task-id")
    set_change.set_defaults(func=cmd_set_change)

    # 为租约子命令添加统一的 Session 与 checkout 身份参数。
    def add_lease_identity(command: argparse.ArgumentParser, *, parent: bool = True) -> None:
        """参数：
            command: 待扩展的子命令解析器。
            parent: 是否允许传入父运行标识符。
        """
        command.add_argument("--client", required=True, choices=["codex", "qoder", "claude"])
        command.add_argument("--session-id", required=True)
        command.add_argument("--cwd", required=True)
        if parent:
            command.add_argument("--parent-run-id")

    read_ready = sub.add_parser("mark-read-only-ready")
    add_lease_identity(read_ready)
    read_ready.set_defaults(func=cmd_mark_read_only_ready)

    acquire_lease = sub.add_parser("acquire-writer-lease")
    add_lease_identity(acquire_lease)
    acquire_lease.add_argument("--owner-pid", type=int)
    acquire_lease.add_argument("--owner-start-time")
    acquire_lease.set_defaults(func=cmd_acquire_writer_lease)

    heartbeat_lease = sub.add_parser("heartbeat-writer-lease")
    add_lease_identity(heartbeat_lease)
    heartbeat_lease.add_argument("--epoch", type=int)
    heartbeat_lease.add_argument("--fencing-token")
    heartbeat_lease.set_defaults(func=cmd_heartbeat_writer_lease)

    release_lease = sub.add_parser("release-writer-lease")
    add_lease_identity(release_lease)
    release_lease.add_argument("--epoch", type=int)
    release_lease.add_argument("--fencing-token")
    release_lease.add_argument("--reason", default="SessionEnd")
    release_lease.set_defaults(func=cmd_release_writer_lease)

    reclaim_lease = sub.add_parser("reclaim-writer-lease")
    add_lease_identity(reclaim_lease, parent=False)
    reclaim_lease.add_argument("--expected-epoch", required=True, type=int)
    reclaim_lease.add_argument("--expected-holder-run-id", required=True)
    reclaim_lease.add_argument("--expected-holder-session-id", required=True)
    reclaim_lease.add_argument(
        "--stale-after-seconds", type=float, default=DEFAULT_LEASE_STALE_SECONDS
    )
    reclaim_lease.set_defaults(func=cmd_reclaim_writer_lease)

    for name, func in [("list", cmd_list)]:
        p = sub.add_parser(name)
        p.add_argument("--json", action="store_true")
        p.set_defaults(func=func)

    for name, func in [("status", cmd_status), ("stop", cmd_stop), ("handoff", cmd_handoff)]:
        p = sub.add_parser(name)
        p.add_argument("--run-id", required=True)
        p.set_defaults(func=func)

    finalize = sub.add_parser("finalize")
    finalize.add_argument("--run-id", required=True)
    finalize.set_defaults(func=cmd_finalize)

    doctor = sub.add_parser("doctor")
    doctor.add_argument("--run-id", required=False)
    doctor.set_defaults(func=cmd_doctor)

    cleanup = sub.add_parser("cleanup")
    cleanup.add_argument("--run-id", required=True)
    cleanup.add_argument(
        "--execute",
        action="store_true",
        help="release this run and remove only its evidence; default is dry-run",
    )
    cleanup.set_defaults(func=cmd_cleanup)
    return parser


# 维护 main 函数行为。
def main(argv: list[str] | None = None) -> int:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或执行结果。
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (SessionctlError, subprocess.CalledProcessError, PrimarySessionValidationError, OSError) as exc:
        print(f"sessionctl: BLOCKED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
