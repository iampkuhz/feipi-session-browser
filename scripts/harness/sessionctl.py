#!/usr/bin/env python3
"""Primary-session worktree lifecycle CLI.

This command intentionally orchestrates local Git worktrees and registry records
only. It never starts a real provider session unless the caller supplies an
explicit local client command.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import fcntl
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.harness.primary_session import (  # noqa: E402
    ACTIVE_WRITER_STATUSES,
    PrimarySessionValidationError,
    validate_status_transition,
    resolve_runtime_root,
    validate_run_collisions,
    validate_run_record,
)
from scripts.harness.resource_lock import _pid_start_time, process_is_alive  # noqa: E402

REGISTRY_VERSION = 1
DEFAULT_FORBIDDEN_PATHS = [".env", ".mcp.json", "data", "output", "tmp/agent_logs"]


class SessionctlError(RuntimeError):
    """Raised for expected CLI failures."""


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


# 维护 slugify 函数行为。
def slugify(value: str) -> str:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或执行结果。
    """
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip().lower()).strip("-.")
    return slug[:48] or "task"


# 维护 write_json_atomic 函数行为。
def write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或执行结果。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


# 维护 load_json 函数行为。
def load_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或执行结果。
    """
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


class Registry:
    """Shared primary-run registry guarded by a repository runtime lock."""

    # 维护 __init__ 函数行为。
    def __init__(self, repo_root: Path):
        """参数：
            *args: 当前函数使用的输入参数。

        返回：
            当前函数计算或执行结果。
        """
        self.repo_root = repo_root.resolve()
        self.root = resolve_runtime_root(self.repo_root)
        self.runs_dir = self.root / "runs"
        self.index_path = self.runs_dir / "index.json"
        self.lock_path = self.root / "locks" / "registry.lock"

    # 维护 locked 函数行为。
    @contextmanager
    def locked(self) -> Iterable[None]:
        """参数：
            *args: 当前函数使用的输入参数。

        返回：
            当前函数计算或执行结果。
        """
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    # 维护 _run_path 函数行为。
    def _run_path(self, run_id: str) -> Path:
        """参数：
            *args: 当前函数使用的输入参数。

        返回：
            当前函数计算或执行结果。
        """
        return self.runs_dir / f"{run_id}.json"

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
        if not path.exists():
            raise SessionctlError(f"unknown run_id: {run_id}")
        return json.loads(path.read_text(encoding="utf-8"))

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
            path = self._run_path(str(run_id))
            if path.exists():
                records.append(json.loads(path.read_text(encoding="utf-8")))
        return records

    # 维护 remove_run_record 函数行为。
    def remove_run_record(self, run_id: str) -> None:
        """参数：
            *args: 当前函数使用的输入参数。

        返回：
            当前函数计算或执行结果。
        """
        path = self._run_path(run_id)
        if path.exists():
            path.unlink()
        index = self.load_index()
        self.save_index([str(item) for item in index.get("runs", []) if str(item) != run_id])


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


# 维护 current_branch 函数行为。
def current_branch(repo: Path) -> str:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或执行结果。
    """
    out = git(repo, "branch", "--show-current")
    return out.stdout.strip()


# 维护 head_commit 函数行为。
def head_commit(repo: Path) -> str:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或执行结果。
    """
    return git(repo, "rev-parse", "HEAD").stdout.strip()


# 维护 branch_exists 函数行为。
def branch_exists(repo: Path, branch: str) -> bool:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或执行结果。
    """
    return git(repo, "show-ref", "--verify", f"refs/heads/{branch}", check=False).returncode == 0


# 维护 git_worktrees 函数行为。
def git_worktrees(repo: Path) -> list[dict[str, str]]:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或执行结果。
    """
    out = git(repo, "worktree", "list", "--porcelain").stdout
    items: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for line in out.splitlines():
        if not line:
            if current:
                items.append(current)
                current = {}
            continue
        key, _, value = line.partition(" ")
        current[key] = value
    if current:
        items.append(current)
    return items


# 维护 ensure_no_collisions 函数行为。
def ensure_no_collisions(registry: Registry, candidate: dict[str, Any]) -> None:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或执行结果。
    """
    records = registry.all_runs() + [candidate]
    collisions = validate_run_collisions(records)
    for collision in collisions:
        if collision.second_run_id == candidate["runId"] or collision.first_run_id == candidate["runId"]:
            raise SessionctlError(f"{collision.kind}: {collision.message}")


# 解析 运行记录的目标分支。
def _target_branch_from_args(args: argparse.Namespace, repo: Path) -> str:
    """参数：
        args: 命令行参数对象。
        repo: 仓库根目录。

    返回：
        运行记录使用的目标分支。
    """
    target = getattr(args, "target_branch", None)
    if target:
        return str(target)
    base_ref = str(getattr(args, "base_ref", "") or "")
    if base_ref.startswith("origin/"):
        return base_ref.split("/", 1)[1]
    if base_ref and base_ref not in {"HEAD", "@"}:
        return base_ref
    branch = current_branch(repo)
    return branch or "main_java"


# 创建运行记录 JSON 对象。
def make_record(args: argparse.Namespace, repo: Path, run_id: str, worktree_id: str, branch: str, worktree_root: Path) -> dict[str, Any]:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或执行结果。
    """
    base_commit = git(repo, "rev-parse", args.base_ref).stdout.strip()
    timestamp = now_utc()
    target_branch = _target_branch_from_args(args, repo)
    return {
        "schemaVersion": 1,
        "runId": run_id,
        "client": args.client,
        "taskId": args.task_id,
        "sessionId": "",
        "worktreeId": worktree_id,
        "worktreeRoot": str(worktree_root.resolve()),
        "branch": branch,
        "targetBranch": target_branch,
        "primaryRepoRoot": str(repo.resolve()),
        "baseCommit": base_commit,
        "headCommit": base_commit,
        "changeId": args.change_id,
        "mode": args.mode,
        "primarySessionMode": "managed-worktree",
        "status": "CREATED",
        "allowedPaths": args.allowed_path or [],
        "forbiddenPaths": args.forbidden_path or DEFAULT_FORBIDDEN_PATHS,
        "resourceAllocations": {"ports": [], "paths": [str(worktree_root.resolve())]},
        "writerLease": {"leaseId": f"lease-{run_id}", "holderRunId": run_id} if args.mode == "writable" else {},
        "hookActivation": {"confirmed": False, "client": args.client, "evidence": []},
        "processes": [],
        "createdAt": timestamp,
        "updatedAt": timestamp,
    }


# 维护 default_worktree_parent 函数行为。
def default_worktree_parent(repo: Path) -> Path:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或执行结果。
    """
    return repo.parent / f".{repo.name}-agent-worktrees" / "sessionctl"


# 维护 cmd_create 函数行为。
def cmd_create(args: argparse.Namespace) -> int:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或执行结果。
    """
    repo = repo_root_from_arg(args.repo_root)
    registry = Registry(repo)
    run_id = f"run-{uuid.uuid4().hex[:16]}"
    worktree_id = f"wt-{uuid.uuid4().hex[:12]}"
    branch = args.branch or f"agent/{args.client}/{slugify(args.task_id)}-{run_id[-8:]}"
    parent = Path(args.worktree_parent).expanduser().resolve() if args.worktree_parent else default_worktree_parent(repo).resolve()
    worktree_root = Path(args.worktree_root).expanduser().resolve() if args.worktree_root else parent / worktree_id
    record = make_record(args, repo, run_id, worktree_id, branch, worktree_root)

    with registry.locked():
        if branch_exists(repo, branch):
            raise SessionctlError(f"branch already exists: {branch}")
        for wt in git_worktrees(repo):
            if Path(wt.get("worktree", "")).resolve() == worktree_root:
                raise SessionctlError(f"worktree path already owned by git: {worktree_root}")
        ensure_no_collisions(registry, record)
        parent.mkdir(parents=True, exist_ok=True)
        try:
            git(repo, "worktree", "add", "-b", branch, str(worktree_root), args.base_ref)
            if current_branch(worktree_root) != branch:
                raise SessionctlError("created worktree branch mismatch")
            if head_commit(worktree_root) != record["baseCommit"]:
                raise SessionctlError("created worktree base commit mismatch")
            ensure_no_collisions(registry, record)
            registry.save_run(record)
        except Exception:
            registry.remove_run_record(run_id)
            # 只清理由本命令刚创建且仍保持干净的 worktree。
            if worktree_root.exists():
                status = git(worktree_root, "status", "--porcelain", check=False)
                if status.returncode == 0 and not status.stdout.strip():
                    git(repo, "worktree", "remove", str(worktree_root), check=False)
            if branch_exists(repo, branch):
                git(repo, "branch", "-D", branch, check=False)
            raise
    print(json.dumps(record, indent=2, sort_keys=True))
    return 0


# 创建受管工作树并保存运行记录。
def create_run_record(args: argparse.Namespace, repo: Path, registry: Registry) -> dict[str, Any]:
    """参数：
        args: 命令行参数对象。
        repo: 主检出仓库根目录。
        registry: 运行时注册表。

    返回：
        已创建并保存的运行记录。
    """
    run_id = f"run-{uuid.uuid4().hex[:16]}"
    worktree_id = f"wt-{uuid.uuid4().hex[:12]}"
    branch = args.branch or f"agent/{args.client}/{slugify(args.task_id)}-{run_id[-8:]}"
    parent = Path(args.worktree_parent).expanduser().resolve() if args.worktree_parent else default_worktree_parent(repo).resolve()
    worktree_root = Path(args.worktree_root).expanduser().resolve() if args.worktree_root else parent / worktree_id
    record = make_record(args, repo, run_id, worktree_id, branch, worktree_root)
    if branch_exists(repo, branch):
        raise SessionctlError(f"branch already exists: {branch}")
    for wt in git_worktrees(repo):
        if Path(wt.get("worktree", "")).resolve() == worktree_root:
            raise SessionctlError(f"worktree path already owned by git: {worktree_root}")
    ensure_no_collisions(registry, record)
    parent.mkdir(parents=True, exist_ok=True)
    try:
        git(repo, "worktree", "add", "-b", branch, str(worktree_root), args.base_ref)
        if current_branch(worktree_root) != branch:
            raise SessionctlError("created worktree branch mismatch")
        if head_commit(worktree_root) != record["baseCommit"]:
            raise SessionctlError("created worktree base commit mismatch")
        ensure_no_collisions(registry, record)
        registry.save_run(record)
    except Exception:
        registry.remove_run_record(run_id)
        if worktree_root.exists():
            status = git(worktree_root, "status", "--porcelain", check=False)
            if status.returncode == 0 and not status.stdout.strip():
                git(repo, "worktree", "remove", str(worktree_root), check=False)
        if branch_exists(repo, branch):
            git(repo, "branch", "-D", branch, check=False)
        raise
    return record


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
            print(f"{record['runId']}\t{record['client']}\t{record['status']}\t{record['branch']}\t{record['worktreeRoot']}")
    return 0


# 维护 enrich_status 函数行为。
def enrich_status(record: dict[str, Any]) -> dict[str, Any]:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或执行结果。
    """
    worktree = Path(record["worktreeRoot"])
    enriched = dict(record)
    checks: dict[str, Any] = {"worktreeExists": worktree.exists()}
    if worktree.exists():
        checks["branchMatches"] = current_branch(worktree) == record["branch"]
        checks["baseCommitMatches"] = git(worktree, "merge-base", "--is-ancestor", record["baseCommit"], "HEAD", check=False).returncode == 0
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


HOOK_ACTIVATION_TTL_SECONDS = 24 * 60 * 60


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


# 判断客户端 executable 是否可用。
def _client_executable_available(client: str) -> bool:
    """参数：
        client: agent client 名称。

    返回：
        可执行入口是否能被本机 PATH 解析。
    """
    override = os.environ.get(f"FEIPI_SESSIONCTL_{client.upper()}_COMMAND", "").strip()
    if override:
        return bool(shutil.which(shlex.split(override)[0]))
    # 已 bind 的 writable run 代表真实 hook 已触发；本地没有安装对应 CLI 时不阻断
    # repository-only doctor，避免把未启动客户端的静态环境误判为失败。
    return True


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
    worktree = Path(record["worktreeRoot"])
    if not worktree.exists():
        errors.append("worktree root does not exist")
        return errors
    if current_branch(worktree) != record["branch"]:
        errors.append("worktree branch mismatch")
    if git(worktree, "merge-base", "--is-ancestor", record["baseCommit"], "HEAD", check=False).returncode != 0:
        errors.append("base commit is not an ancestor of worktree HEAD")
    if record.get("mode") == "writable" and record.get("status") in {"RUNNING", "VALIDATING", "VALIDATED", "COMMITTED"}:
        if not _client_executable_available(str(record.get("client") or "")):
            errors.append("client executable unavailable for writable-ready run")
        activation = record.get("hookActivation", {}) if isinstance(record.get("hookActivation"), dict) else {}
        if activation.get("confirmed") is not True:
            errors.append("hook activation unconfirmed for writable-ready run")
        marker = activation.get("marker") if isinstance(activation, dict) else None
        marker_path = Path(str(marker.get("path") or "")) if isinstance(marker, dict) else None
        if not marker_path or not marker_path.is_file():
            errors.append("hook activation marker missing for writable-ready run")
        else:
            try:
                marker_data = json.loads(marker_path.read_text(encoding="utf-8"))
            except Exception:
                marker_data = {}
            expected_hash = activation_config_hash(worktree, str(record.get("client") or ""))
            if marker_data.get("configHash") != expected_hash:
                errors.append("hook activation config hash mismatch")
            if marker_data.get("sessionId") != record.get("sessionId"):
                errors.append("hook activation session mismatch")
            activated = _parse_utc(str(marker_data.get("activatedAt") or marker.get("activatedAt") or ""))
            if not activated:
                errors.append("hook activation marker missing activatedAt")
            elif (datetime.now(timezone.utc) - activated).total_seconds() > HOOK_ACTIVATION_TTL_SECONDS:
                errors.append("hook activation marker expired")
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
    if record.get("mode") == "read-only":
        return "read-only-ready"
    if record.get("mode") == "writable" and record.get("status") in {"RUNNING", "VALIDATING", "VALIDATED", "COMMITTED"}:
        return "writable-ready"
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



# 计算激活绑定配置文件的 SHA-256。
def file_sha256(path: Path) -> str:
    """参数：
        path: 配置文件路径。

    返回：
        文件 SHA-256 十六进制字符串。
    """
    h = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


# 计算用于证明项目级 hook 激活的配置哈希。
def activation_config_hash(repo: Path, client: str) -> dict[str, str]:
    """参数：
        repo: 仓库根目录。
        client: agent client 名称。

    返回：
        配置相对路径到 SHA-256 的映射。
    """
    client_files = {
        'claude': [Path('.claude/settings.json')],
        'codex': [Path('.codex/hooks.json'), Path('.codex/config.toml')],
        'qoder': [Path('.qoder/settings.json'), Path('.qoder/hook-bindings.md')],
    }
    files = client_files.get(client, [Path(f'.{client}/hooks.json'), Path(f'.{client}/config.toml')])
    result: dict[str, str] = {}
    for rel in files:
        full = repo / rel
        if full.is_file():
            result[str(rel)] = file_sha256(full)
    return result


# 写入可由 doctor 校验的 hook 激活 marker。
def write_activation_marker(repo: Path, record: dict[str, Any], session_id: str, cwd: Path) -> dict[str, Any]:
    """参数：
        repo: 仓库根目录。
        record: 当前运行记录。
        session_id: 绑定的真实会话标识。
        cwd: hook 触发时的工作目录。

    返回：
        marker 路径、配置哈希和激活时间。
    """
    marker = resolve_runtime_root(repo) / 'runs' / str(record['runId']) / 'hook-activation.json'
    payload = {
        'schemaVersion': 1,
        'runId': record['runId'],
        'client': record['client'],
        'sessionId': session_id,
        'cwd': str(cwd),
        'configHash': activation_config_hash(repo, str(record['client'])),
        'activatedAt': now_utc(),
        'source': 'sessionctl bind-session',
    }
    write_json_atomic(marker, payload)
    return {'path': str(marker), 'configHash': payload['configHash'], 'activatedAt': payload['activatedAt']}

# 维护 safe_command_env 函数行为。
def safe_command_env(record: dict[str, Any]) -> dict[str, str]:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或执行结果。
    """
    return {
        "FEIPI_RUN_ID": record["runId"],
        "FEIPI_TASK_ID": record["taskId"],
        "FEIPI_WORKTREE_ID": record["worktreeId"],
        "FEIPI_AGENT_RUNTIME_ROOT": str(resolve_runtime_root(Path(record["worktreeRoot"]))),
        "ACTIVE_CHANGE_ID": record["changeId"],
        "FEIPI_CLIENT": record["client"],
        "FEIPI_AGENT_CLIENT": record["client"],
        "FEIPI_SESSION_ID": record.get("sessionId", ""),
        "FEIPI_PRIMARY_SESSION_MODE": "managed-worktree",
    }


# 维护 cmd_start 函数行为。
def cmd_start(args: argparse.Namespace) -> int:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或执行结果。
    """
    repo = repo_root_from_arg(args.repo_root)
    registry = Registry(repo)
    with registry.locked():
        if args.run_id:
            record = registry.load_run(args.run_id)
        else:
            if not args.client or not args.task_id or not args.change_id:
                raise SessionctlError("start requires --run-id or --client --task-id --change-id")
            record = create_run_record(args, repo, registry)
        if record["status"] not in {"CREATED", "BLOCKED", "HANDOFF_REQUIRED"}:
            raise SessionctlError(f"run is not startable from status {record['status']}")
        errors = doctor_record(record)
        if errors and args.run_id:
            raise SessionctlError("doctor blocked start: " + "; ".join(errors))
        command = args.client_command or os.environ.get(f"FEIPI_SESSIONCTL_{record['client'].upper()}_COMMAND", "")
        env = safe_command_env(record)
        if args.print_command:
            prefix = " ".join(f"{k}={shlex.quote(v)}" for k, v in env.items())
            print(f"cd {shlex.quote(record['worktreeRoot'])} && {prefix} {command or '<client-command>'}")
            return 0
        if not command:
            record["status"] = "BLOCKED"
            record["updatedAt"] = now_utc()
            record["startBlockedReason"] = "client command unavailable"
            registry.save_run(record)
            raise SessionctlError("client command unavailable; configure --client-command or FEIPI_SESSIONCTL_<CLIENT>_COMMAND")
        record["status"] = "STARTING"
        record["updatedAt"] = now_utc()
        registry.save_run(record)
    child_env = os.environ.copy()
    child_env.update(env)
    client_log = registry.root / "runs" / str(record["runId"]) / "client-start.log"
    client_log.parent.mkdir(parents=True, exist_ok=True)
    with client_log.open("ab") as log_handle:
        proc = subprocess.Popen(  # noqa: S603 - explicit local command.
            shlex.split(command),
            cwd=record["worktreeRoot"],
            env=child_env,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
        )
    with registry.locked():
        latest = registry.load_run(str(record["runId"]))
        latest["processes"] = list(latest.get("processes") or []) + [{
            "pid": proc.pid,
            "processStartTime": _pid_start_time(proc.pid),
            "command": shlex.split(command)[0],
            "log": str(client_log),
            "startedAt": now_utc(),
        }]
        latest["updatedAt"] = now_utc()
        registry.save_run(latest)
    print(json.dumps({"status": "STARTING", "runId": record["runId"], "pid": proc.pid}, indent=2, sort_keys=True))
    return 0


# 维护 cmd_bind_session 函数行为。
def cmd_bind_session(args: argparse.Namespace) -> int:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或执行结果。
    """
    repo = repo_root_from_arg(args.repo_root)
    cwd = Path(args.cwd).resolve()
    registry = Registry(repo)
    with registry.locked():
        record = registry.load_run(args.run_id)
        if record["client"] != args.client:
            raise SessionctlError("client mismatch")
        if Path(record["worktreeRoot"]).resolve() != cwd:
            raise SessionctlError("bind-session cwd does not match run worktree root")
        if current_branch(cwd) != record["branch"]:
            raise SessionctlError("bind-session branch mismatch")
        if head_commit(cwd) != record["baseCommit"]:
            raise SessionctlError("bind-session base commit mismatch")
        existing = str(record.get("sessionId") or "")
        if existing and existing != args.session_id and record.get("status") in ACTIVE_WRITER_STATUSES:
            raise SessionctlError("run already bound to a different active primary session")
        activation = write_activation_marker(repo, record, args.session_id, cwd)
        record["sessionId"] = args.session_id
        record["hookActivation"] = {"confirmed": True, "client": args.client, "sessionId": args.session_id, "cwd": str(cwd), "marker": activation}
        record["status"] = "RUNNING"
        record["updatedAt"] = now_utc()
        registry.save_run(record)
        mirror = cwd / "tmp" / "agent_logs" / record["client"] / args.session_id / "runs" / record["runId"] / "main" / "active_change.json"
        mirror.parent.mkdir(parents=True, exist_ok=True)
        write_json_atomic(mirror, {
            "schemaVersion": 1,
            "changeId": record["changeId"],
            "runId": record["runId"],
            "taskId": record["taskId"],
            "source": "sessionctl bind-session",
            "legacyWarning": "run-scoped active change mirror; global tmp/active_change.json is legacy-only",
        })
    print(json.dumps({"status": "RUNNING", "runId": args.run_id, "sessionId": args.session_id}, indent=2, sort_keys=True))
    return 0


# 维护 changed_files 函数行为。
def changed_files(worktree: Path) -> list[str]:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或执行结果。
    """
    lines = git(worktree, "status", "--short").stdout.splitlines()
    return [line[3:] if len(line) > 3 else line for line in lines]


# 读取最新 Stop summary 状态。
def _load_latest_stop_status(worktree: Path, record: dict[str, Any]) -> str:
    """参数：
        worktree: 运行工作树根目录。
        record: 运行记录。

    返回：
        Stop summary 中的状态；读取失败时返回空字符串。
    """
    session = str(record.get("sessionId") or "unknown")
    client = str(record.get("client") or "unknown")
    run_id = str(record.get("runId") or "")
    summary = worktree / "tmp" / "agent_logs" / client / session / "runs" / run_id / "main" / "stop-check-summary.json"
    try:
        data = json.loads(summary.read_text(encoding="utf-8"))
    except Exception:
        return ""
    return str(data.get("status") or "")


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
        record["status"] = "VALIDATING"
        record["updatedAt"] = now_utc()
        registry.save_run(record)

    from scripts.harness.stop_entry import run_stop  # noqa: PLC0415 - avoid CLI import cycle

    payload = {
        "cwd": record["worktreeRoot"],
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
    stop_exit = run_stop(str(record["client"]), payload)

    with registry.locked():
        latest = registry.load_run(args.run_id)
        latest["status"] = "VALIDATED" if stop_exit == 0 and _load_latest_stop_status(Path(str(latest["worktreeRoot"])), latest) == "PASS" else "BLOCKED"
        latest["headCommit"] = head_commit(Path(str(latest["worktreeRoot"])))
        latest["stopExitCode"] = stop_exit
        latest["updatedAt"] = now_utc()
        registry.save_run(latest)

    status = latest["status"]
    print(json.dumps({"status": status, "runId": args.run_id, "stopExitCode": stop_exit, "killedProcess": False}, indent=2, sort_keys=True))
    return 0 if stop_exit == 0 else 2


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
    worktree = Path(record["worktreeRoot"])
    committed = _committed_changed_files(worktree, str(record.get("baseCommit") or "")) if worktree.exists() else []
    dirty_state = _dirty_untracked(worktree) if worktree.exists() else {"dirty": [], "untracked": []}
    run_changed = sorted(set(committed + dirty_state["dirty"] + dirty_state["untracked"]))
    blocking_failures = doctor_record(record)
    scope_overlaps = [
        f"{collision.kind}: {collision.message}"
        for collision in validate_run_collisions([record] + [item for item in registry.all_runs() if item.get("runId") != record.get("runId")])
        if record["runId"] in {collision.first_run_id, collision.second_run_id}
    ]
    report = {
        "runId": record["runId"],
        "taskId": record["taskId"],
        "client": record["client"],
        "sessionId": record.get("sessionId", ""),
        "worktreeId": record.get("worktreeId", ""),
        "worktreeRoot": record["worktreeRoot"],
        "branch": record["branch"],
        "baseCommit": record["baseCommit"],
        "headCommit": head_commit(worktree) if worktree.exists() else "",
        "targetBranch": record.get("targetBranch", ""),
        "changeId": record["changeId"],
        "primarySessionMode": record.get("primarySessionMode", "managed-worktree"),
        "changedFiles": run_changed,
        "baseToHeadFiles": committed,
        "commits": git(worktree, "log", "--oneline", f"{record['baseCommit']}..HEAD", check=False).stdout.splitlines() if worktree.exists() else [],
        "aheadBehind": _ahead_behind(worktree, str(record.get("targetBranch") or "HEAD"), "HEAD") if worktree.exists() else {},
        "dirty": dirty_state["dirty"],
        "untracked": dirty_state["untracked"],
        "requiredTargetSummary": record.get("requiredTargetSummary", {"allowedPaths": record.get("allowedPaths", []), "forbiddenPaths": record.get("forbiddenPaths", [])}),
        "qualityArtifacts": record.get("qualityArtifacts", []),
        "artifactPaths": {
            "runRecord": str(registry._run_path(str(record["runId"]))),
            "runtimeRoot": str(registry.root),
            "worktreeRoot": record["worktreeRoot"],
        },
        "blockingFailures": blocking_failures,
        "mergeRisk": {
            "writeScopeOverlap": scope_overlaps,
            "dirtyWorktree": bool(dirty_state["dirty"] or dirty_state["untracked"]),
        },
        "risks": record.get("risks", []) + scope_overlaps,
        "manualNextSteps": [
            "review changedFiles and blockingFailures",
            "run required gates before merge",
            f"./scripts/agent-session finalize --run-id {record['runId']}",
            "use sessionctl cleanup dry-run first; do not delete dirty worktrees",
        ],
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


# 维护 cmd_cleanup 函数行为。
def cmd_cleanup(args: argparse.Namespace) -> int:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或执行结果。
    """
    repo = repo_root_from_arg(args.repo_root)
    registry = Registry(repo)
    with registry.locked():
        record = registry.load_run(args.run_id)
        worktree = Path(record["worktreeRoot"])
        active_pids = []
        for process in record.get("processes", []) if isinstance(record.get("processes"), list) else []:
            if not isinstance(process, dict):
                continue
            pid = process.get("pid")
            start_time = str(process.get("processStartTime") or "")
            if isinstance(pid, int) and process_is_alive(pid, start_time):
                active_pids.append(pid)
        if active_pids:
            raise SessionctlError("cleanup refused: active process still attached to run: " + ", ".join(str(pid) for pid in active_pids))
        if worktree.resolve() == Path.cwd().resolve():
            raise SessionctlError("cleanup refused: worktree is current process cwd")
        if worktree.exists() and git(worktree, "status", "--porcelain").stdout.strip():
            raise SessionctlError("cleanup refused: dirty worktree")
        if record.get("status") != "INTEGRATED" and worktree.exists():
            ahead = git(worktree, "rev-list", "--count", f"{record['baseCommit']}..HEAD", check=False)
            if ahead.returncode == 0 and int((ahead.stdout or "0").strip() or "0") > 0:
                raise SessionctlError("cleanup refused: unintegrated commits remain")
        if args.delete_branch and record.get("status") != "INTEGRATED":
            raise SessionctlError("cleanup refused: branch deletion requires INTEGRATED status")
        actions = {"removeWorktree": str(worktree), "deleteBranch": bool(args.delete_branch), "dryRun": not args.execute}
        if not args.execute:
            print(json.dumps({"status": "dry-run", "runId": args.run_id, "actions": actions}, indent=2, sort_keys=True))
            return 0
        record["status"] = "CLEANED" if not args.execute else record["status"]
        record["updatedAt"] = now_utc()
        registry.save_run(record)
        if worktree.exists():
            git(repo, "worktree", "remove", str(worktree))
        if args.delete_branch and branch_exists(repo, record["branch"]):
            git(repo, "branch", "-d", record["branch"])
        record["status"] = "CLEANED"
        record["updatedAt"] = now_utc()
        registry.save_run(record)
    print(json.dumps({"status": "CLEANED", "runId": args.run_id, "actions": actions}, indent=2, sort_keys=True))
    return 0


# 判断仓库是否干净。
def _repo_clean(repo: Path) -> bool:
    """参数：
        repo: 仓库根目录。

    返回：
        工作区没有脏文件或未追踪文件时返回 True。
    """
    return not git(repo, "status", "--porcelain").stdout.strip()


# 读取基准到当前提交之间的已提交变更文件。
def _committed_changed_files(worktree: Path, base: str) -> list[str]:
    """参数：
        worktree: 运行工作树根目录。
        base: 基准提交。

    返回：
        已提交变更文件列表。
    """
    return [line for line in git(worktree, "diff", "--name-only", f"{base}...HEAD").stdout.splitlines() if line.strip()]


# 读取脏文件和未追踪文件。
def _dirty_untracked(worktree: Path) -> dict[str, list[str]]:
    """参数：
        worktree: 运行工作树根目录。

    返回：
        脏文件与未追踪文件列表映射。
    """
    dirty = [line for line in git(worktree, "diff", "--name-only").stdout.splitlines() if line.strip()]
    untracked = [line for line in git(worktree, "ls-files", "--others", "--exclude-standard").stdout.splitlines() if line.strip()]
    return {"dirty": dirty, "untracked": untracked}


# 计算两个 Git 引用的前后差异。
def _ahead_behind(repo: Path, left: str, right: str) -> dict[str, int]:
    """参数：
        repo: 仓库根目录。
        left: 左侧 Git 引用。
        right: 右侧 Git 引用。

    返回：
        前进与落后提交计数。
    """
    out = git(repo, "rev-list", "--left-right", "--count", f"{left}...{right}", check=False)
    if out.returncode != 0:
        return {"ahead": 0, "behind": 0}
    parts = out.stdout.split()
    if len(parts) != 2:
        return {"ahead": 0, "behind": 0}
    return {"ahead": int(parts[0]), "behind": int(parts[1])}


# 写入交接摘要。
def _write_handoff(registry: Registry, record: dict[str, Any], reason: str) -> Path:
    """参数：
        registry: 运行时注册表。
        record: 运行记录。
        reason: 交接原因。

    返回：
        交接摘要路径。
    """
    worktree = Path(str(record["worktreeRoot"]))
    target = str(record.get("targetBranch") or "")
    base = str(record.get("baseCommit") or "")
    report = {
        "schemaVersion": 1,
        "status": "HANDOFF_REQUIRED",
        "reason": reason,
        "runId": record["runId"],
        "targetBranch": target,
        "branch": record["branch"],
        "baseCommit": base,
        "headCommit": head_commit(worktree) if worktree.exists() else "",
        "baseToHeadFiles": _committed_changed_files(worktree, base) if worktree.exists() and base else [],
        "commits": git(worktree, "log", "--oneline", f"{base}..HEAD", check=False).stdout.splitlines() if worktree.exists() and base else [],
        "aheadBehind": _ahead_behind(worktree, target, "HEAD") if worktree.exists() and target else {},
        **(_dirty_untracked(worktree) if worktree.exists() else {"dirty": [], "untracked": []}),
        "requiredGateStatus": record.get("stopExitCode", "unknown"),
        "mergeRisk": reason,
        "finalizeCommand": f"./scripts/agent-session finalize --run-id {record['runId']}",
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
    record["status"] = "HANDOFF_REQUIRED"
    record["handoffSummary"] = str(path)
    record["updatedAt"] = now_utc()
    registry.save_run(record)


# 安全集成运行分支到目标分支。
def cmd_finalize(args: argparse.Namespace) -> int:
    """参数：
        args: 命令行参数对象。

    返回：
        进程退出码。
    """
    repo = repo_root_from_arg(args.repo_root)
    registry = Registry(repo)
    lock_path = registry.root / "locks" / "integration.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        with registry.locked():
            record = registry.load_run(args.run_id)
        worktree = Path(str(record["worktreeRoot"]))
        target = str(record.get("targetBranch") or "")
        if record.get("status") == "INTEGRATED":
            print(json.dumps({"status": "INTEGRATED", "runId": args.run_id, "idempotent": True}, indent=2, sort_keys=True))
            return 0
        if not target:
            with registry.locked():
                _mark_handoff(registry, record, "missing target branch")
            print("HANDOFF_REQUIRED missing target branch")
            return 2
        if not _repo_clean(repo):
            with registry.locked():
                _mark_handoff(registry, record, "primary checkout dirty")
            print("HANDOFF_REQUIRED primary checkout dirty")
            return 2
        if not worktree.exists():
            with registry.locked():
                _mark_handoff(registry, record, "run worktree missing")
            print("HANDOFF_REQUIRED run worktree missing")
            return 2
        if not _repo_clean(worktree):
            if args.commit:
                if not args.message:
                    with registry.locked():
                        _mark_handoff(registry, record, "--commit requires --message")
                    print("HANDOFF_REQUIRED --commit requires --message")
                    return 2
                git(worktree, "add", "-A")
                git(worktree, "commit", "-m", args.message)
            else:
                with registry.locked():
                    _mark_handoff(registry, record, "run worktree has uncommitted changes")
                print("HANDOFF_REQUIRED run worktree has uncommitted changes")
                return 2
        run_head = head_commit(worktree)
        target_old = git(repo, "rev-parse", target).stdout.strip()
        if record.get("status") not in {"VALIDATED", "COMMITTED"} and not args.allow_unvalidated:
            with registry.locked():
                _mark_handoff(registry, record, "required gates are not fresh PASS")
            print("HANDOFF_REQUIRED required gates are not fresh PASS")
            return 2
        with registry.locked():
            record = registry.load_run(args.run_id)
            record["status"] = "INTEGRATING"
            record["headCommit"] = run_head
            record["updatedAt"] = now_utc()
            registry.save_run(record)
        strategy = "ff-only"
        try:
            if git(repo, "merge-base", "--is-ancestor", target, run_head, check=False).returncode != 0:
                strategy = "rebase-then-ff"
                rebase = git(worktree, "rebase", target, check=False)
                if rebase.returncode != 0:
                    git(worktree, "rebase", "--abort", check=False)
                    with registry.locked():
                        record = registry.load_run(args.run_id)
                        _mark_handoff(registry, record, "target advanced with conflicts")
                    print("HANDOFF_REQUIRED target advanced with conflicts")
                    return 2
                run_head = head_commit(worktree)
                stop = cmd_stop(argparse.Namespace(repo_root=str(repo), run_id=args.run_id))
                if stop != 0:
                    with registry.locked():
                        record = registry.load_run(args.run_id)
                        _mark_handoff(registry, record, "revalidation failed after rebase")
                    print("HANDOFF_REQUIRED revalidation failed after rebase")
                    return 2
            git(repo, "switch", target)
            git(repo, "merge", "--ff-only", run_head)
        except subprocess.CalledProcessError as exc:
            with registry.locked():
                record = registry.load_run(args.run_id)
                _mark_handoff(registry, record, f"integration failed: {exc}")
            print("HANDOFF_REQUIRED integration failed")
            return 2
        target_new = head_commit(repo)
        summary = {
            "schemaVersion": 1,
            "status": "INTEGRATED",
            "runId": args.run_id,
            "oldTarget": target_old,
            "base": record.get("baseCommit"),
            "oldHead": run_head,
            "newHead": target_new,
            "strategy": strategy,
            "artifacts": record.get("qualityArtifacts", []),
            "integratedAt": now_utc(),
        }
        summary_path = registry.root / "integration" / f"{args.run_id}.json"
        write_json_atomic(summary_path, summary)
        with registry.locked():
            record = registry.load_run(args.run_id)
            record["status"] = "INTEGRATED"
            record["headCommit"] = target_new
            record["integrationSummary"] = str(summary_path)
            record["updatedAt"] = now_utc()
            registry.save_run(record)
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0


# 只读导入旧 marker 并创建新运行记录。
def cmd_recover_legacy(args: argparse.Namespace) -> int:
    """参数：
        args: 命令行参数对象。

    返回：
        进程退出码。
    """
    repo = repo_root_from_arg(args.repo_root)
    registry = Registry(repo)
    runtime_root = resolve_runtime_root(repo)
    marker = runtime_root / "worktrees" / args.client / f"{args.session}.json"
    data: dict[str, Any] = {}
    if marker.exists():
        data = load_json(marker, {})
    raw_worktree = args.worktree_root or data.get("worktreePath") or data.get("worktreeRoot")
    if not raw_worktree:
        raise SessionctlError("recover-legacy requires --worktree-root when legacy marker is absent")
    worktree = Path(str(raw_worktree)).expanduser().resolve()
    if not worktree.exists():
        raise SessionctlError(f"legacy worktree missing: {worktree}")
    common_repo = git(repo, "rev-parse", "--git-common-dir").stdout.strip()
    common_worktree = git(worktree, "rev-parse", "--git-common-dir").stdout.strip()
    if Path(common_repo).resolve() != (worktree / common_worktree).resolve() and Path(common_repo).resolve() != Path(common_worktree).resolve():
        raise SessionctlError("legacy worktree is not in same git-common-dir")
    branch = current_branch(worktree)
    if not branch:
        branch = f"agent/recovery/{args.client}-{slugify(args.session)}-{uuid.uuid4().hex[:8]}"
        git(worktree, "switch", "-c", branch)
    ns = argparse.Namespace(
        client=args.client,
        task_id=args.task_id or f"recover-{args.session}",
        change_id=args.change_id,
        base_ref=args.target,
        target_branch=args.target,
        mode="writable",
        allowed_path=args.allowed_path or [],
        forbidden_path=args.forbidden_path or DEFAULT_FORBIDDEN_PATHS,
    )
    base_commit = git(repo, "rev-parse", args.target).stdout.strip()
    run_id = f"run-{uuid.uuid4().hex[:16]}"
    record = make_record(ns, repo, run_id, f"wt-recovery-{uuid.uuid4().hex[:8]}", branch, worktree)
    record["sessionId"] = args.session
    record["baseCommit"] = base_commit
    record["headCommit"] = head_commit(worktree)
    record["status"] = "RUNNING"
    record["hookActivation"] = {"confirmed": True, "client": args.client, "sessionId": args.session, "source": "recover-legacy"}
    record["auditEvents"] = [{"event": "MIGRATED", "source": str(marker), "at": now_utc()}]
    with registry.locked():
        ensure_no_collisions(registry, record)
        registry.save_run(record)
    print(json.dumps(record, indent=2, sort_keys=True))
    return 0


# 维护 build_parser 函数行为。
def build_parser() -> argparse.ArgumentParser:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或执行结果。
    """
    parser = argparse.ArgumentParser(description="Manage Feipi primary-session worktrees")
    parser.add_argument("--repo-root", help="Git repository root; defaults to cwd")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create")
    create.add_argument("--client", required=True, choices=["codex", "qoder", "claude"])
    create.add_argument("--task-id", required=True)
    create.add_argument("--change-id", required=True)
    create.add_argument("--base-ref", default="HEAD")
    create.add_argument("--target-branch")
    create.add_argument("--mode", choices=["writable", "read-only"], default="writable")
    create.add_argument("--allowed-path", action="append", default=[])
    create.add_argument("--forbidden-path", action="append", default=[])
    create.add_argument("--worktree-parent")
    create.add_argument("--worktree-root")
    create.add_argument("--branch")
    create.set_defaults(func=cmd_create)

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
    finalize.add_argument("--commit", action="store_true")
    finalize.add_argument("--message")
    finalize.add_argument("--allow-unvalidated", action="store_true")
    finalize.set_defaults(func=cmd_finalize)

    recover = sub.add_parser("recover-legacy")
    recover.add_argument("--client", required=True, choices=["codex", "qoder", "claude"])
    recover.add_argument("--session", required=True)
    recover.add_argument("--target", required=True)
    recover.add_argument("--change-id", required=True)
    recover.add_argument("--task-id")
    recover.add_argument("--worktree-root")
    recover.add_argument("--allowed-path", action="append", default=[])
    recover.add_argument("--forbidden-path", action="append", default=[])
    recover.set_defaults(func=cmd_recover_legacy)

    doctor = sub.add_parser("doctor")
    doctor.add_argument("--run-id", required=False)
    doctor.set_defaults(func=cmd_doctor)

    start = sub.add_parser("start")
    start.add_argument("--run-id")
    start.add_argument("--client", choices=["codex", "qoder", "claude"])
    start.add_argument("--task-id")
    start.add_argument("--change-id")
    start.add_argument("--base-ref", default="HEAD")
    start.add_argument("--target-branch")
    start.add_argument("--mode", choices=["writable", "read-only"], default="writable")
    start.add_argument("--allowed-path", action="append", default=[])
    start.add_argument("--forbidden-path", action="append", default=[])
    start.add_argument("--worktree-parent")
    start.add_argument("--worktree-root")
    start.add_argument("--branch")
    start.add_argument("--print-command", action="store_true")
    start.add_argument("--client-command")
    start.set_defaults(func=cmd_start)

    bind = sub.add_parser("bind-session")
    bind.add_argument("--run-id", required=True)
    bind.add_argument("--session-id", required=True)
    bind.add_argument("--client", required=True)
    bind.add_argument("--cwd", required=True)
    bind.set_defaults(func=cmd_bind_session)

    cleanup = sub.add_parser("cleanup")
    cleanup.add_argument("--run-id", required=True)
    cleanup.add_argument("--execute", action="store_true", help="perform cleanup; default is dry-run")
    cleanup.add_argument("--delete-branch", action="store_true")
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
