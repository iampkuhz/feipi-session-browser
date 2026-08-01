"""本模块负责 Gate 共用的身份路径、Git 输入和隔离运行目录。

不负责 Gate 选择、进程执行或状态归约；由 CLI、executor 和少量领域工具调用。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import stat
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_SAFE_SEGMENT_RE = re.compile(r'[^A-Za-z0-9._-]+')


def utc_now() -> str:
    """返回秒级 UTC 时间戳，供运行目录与锁证据使用。"""
    return datetime.now(UTC).isoformat(timespec='seconds').replace('+00:00', 'Z')


def stable_hash(value: str | bytes) -> str:
    """计算文本或字节内容的稳定 SHA-256。"""
    payload = value.encode() if isinstance(value, str) else value
    return hashlib.sha256(payload).hexdigest()


def _safe_segment(value: str | None, fallback: str = 'unknown') -> str:
    raw = str(value or '').strip() or fallback
    cleaned = _SAFE_SEGMENT_RE.sub('-', raw).strip('.-_/') or fallback
    if cleaned == raw and len(cleaned) <= 80 and '/' not in cleaned:
        return cleaned
    digest = stable_hash(raw)[:12]
    return f"{cleaned[:67].rstrip('.-')}-{digest}"


@dataclass(frozen=True)
class ExecutionIdentity:
    """保存路径安全 identity 与仅供匹配证据的原始 identity。"""

    client: str
    session_id: str
    agent_id: str = ''
    run_id: str = ''
    worktree_id: str = ''
    raw_session_id: str = ''
    raw_agent_id: str = ''
    raw_run_id: str = ''
    raw_worktree_id: str = ''

    @property
    def has_session(self) -> bool:
        """判断调用方是否提供了原始 session identity。"""
        return bool(self.raw_session_id)

    @property
    def is_agent(self) -> bool:
        """判断当前 identity 是否对应子 agent。"""
        return bool(self.raw_agent_id)

    @property
    def has_run(self) -> bool:
        """判断调用方是否提供了独立 run identity。"""
        return bool(self.raw_run_id)


def identity_from_values(
    agent_client: str | None = None,
    session_id: str | None = None,
    agent_id: str | None = None,
    run_id: str | None = None,
    worktree_id: str | None = None,
) -> ExecutionIdentity:
    """合并显式值与环境变量，并生成可安全用于路径的执行身份。"""
    client = agent_client if agent_client is not None else os.environ.get('FEIPI_AGENT_CLIENT')
    raw_session = session_id if session_id is not None else os.environ.get('FEIPI_SESSION_ID', '')
    raw_agent = agent_id if agent_id is not None else os.environ.get('FEIPI_AGENT_ID', '')
    raw_run = run_id if run_id is not None else os.environ.get('FEIPI_RUN_ID', '')
    raw_worktree = (
        worktree_id if worktree_id is not None else os.environ.get('FEIPI_WORKTREE_ID', '')
    )
    return ExecutionIdentity(
        client=_safe_segment(client, 'unknown'),
        session_id=_safe_segment(raw_session, 'unknown'),
        agent_id=_safe_segment(raw_agent, '') if raw_agent else '',
        run_id=_safe_segment(raw_run, '') if raw_run else '',
        worktree_id=_safe_segment(raw_worktree, '') if raw_worktree else '',
        raw_session_id=raw_session,
        raw_agent_id=raw_agent,
        raw_run_id=raw_run,
        raw_worktree_id=raw_worktree,
    )


def session_root_dir(repo_root: Path, identity: ExecutionIdentity) -> Path:
    """返回当前 client/session 的日志根目录。"""
    return repo_root / 'tmp' / 'agent_logs' / identity.client / identity.session_id


def run_root_dir(repo_root: Path, identity: ExecutionIdentity) -> Path:
    """返回 session 根目录，存在 run identity 时追加隔离层。"""
    root = session_root_dir(repo_root, identity)
    return root / 'runs' / identity.run_id if identity.has_run else root


def session_main_log_dir(repo_root: Path, identity: ExecutionIdentity) -> Path:
    """返回当前 run 主 agent 的日志目录。"""
    return run_root_dir(repo_root, identity) / 'main'


def agent_log_dir(repo_root: Path, identity: ExecutionIdentity | None = None) -> Path:
    """按 identity 返回主 agent 或子 agent 的日志目录。"""
    selected = identity or identity_from_values()
    if selected.is_agent:
        return run_root_dir(repo_root, selected) / 'agents' / selected.agent_id
    return session_main_log_dir(repo_root, selected)


def session_log_dirs(
    repo_root: Path, identity: ExecutionIdentity, *, include_agents: bool = False
) -> list[Path]:
    """返回当前 identity 可读取的日志目录，并可显式包含全部子 agent。"""
    if identity.is_agent:
        return [agent_log_dir(repo_root, identity)]
    result = [session_main_log_dir(repo_root, identity)]
    agents = run_root_dir(repo_root, identity) / 'agents'
    if include_agents and agents.is_dir():
        result.extend(sorted(path for path in agents.iterdir() if path.is_dir()))
    return result


def quality_dir(repo_root: Path, identity: ExecutionIdentity | None = None) -> Path:
    """返回按 client/session/run/agent 隔离的质量产物目录。"""
    selected = identity or identity_from_values()
    root = repo_root / 'tmp' / 'quality' / selected.client / selected.session_id
    if selected.has_run:
        root = root / 'runs' / selected.run_id
    return root / 'agents' / selected.agent_id if selected.is_agent else root / 'main'


def normalize_path(path: str) -> str:
    """规范化 repository-relative 路径的分隔符与相对前缀。"""
    value = path.replace('\\', '/').strip()
    while value.startswith('./'):
        value = value[2:]
    return value.strip('/')


def dedupe_paths(paths: list[str]) -> list[str]:
    """保持输入顺序，规范化并去重非空 repository-relative 路径。"""
    result: list[str] = []
    seen: set[str] = set()
    for path in paths:
        normalized = normalize_path(path)
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def _git(repo_root: Path, *args: str) -> subprocess.CompletedProcess[str] | None:
    try:
        result = subprocess.run(
            ['git', *args], cwd=repo_root, text=True, capture_output=True, timeout=30, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result if result.returncode == 0 else None


def read_git_dirty_files(repo_root: Path) -> list[str]:
    """读取 Git dirty 文件；Git 不可用或失败时返回空列表。"""
    result = _git(repo_root, 'status', '--short', '--untracked-files=all')
    if result is None:
        return []
    paths: list[str] = []
    for line in result.stdout.splitlines():
        value = line[3:].strip() if len(line) >= 4 else ''
        if ' -> ' in value:
            paths.extend(part.strip().strip('"') for part in value.split(' -> ', 1))
        elif value:
            paths.append(value.strip('"'))
    return sorted(dedupe_paths(paths))


def parse_changed_files_json(value: str | None) -> list[str]:
    """解析 changed-files JSON array；格式无效时 fail-closed 为空列表。"""
    if value is None:
        return []
    try:
        parsed: Any = json.loads(value)
    except json.JSONDecodeError:
        return []
    return (
        dedupe_paths([item for item in parsed if isinstance(item, str)])
        if isinstance(parsed, list)
        else []
    )


def read_recorded_changed_files_from_paths(
    paths: list[Path], session_id: str | None = None, agent_id: str | None = None
) -> list[str]:
    """从 evidence 文件读取匹配 identity 的 changed files，并忽略损坏记录。"""
    files: list[str] = []
    for path in paths:
        try:
            lines = path.read_text(encoding='utf-8').splitlines()
        except OSError:
            continue
        for line in lines:
            try:
                record = json.loads(line)
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(record, dict):
                continue
            if session_id and record.get('sessionId') != session_id:
                continue
            if agent_id and (record.get('agentId') or '') != agent_id:
                continue
            value = record.get('file') or record.get('file_path')
            if isinstance(value, str):
                files.append(value)
    return dedupe_paths(files)


def read_files_since_base_commit(repo_root: Path, base_commit_file: Path) -> list[str]:
    """读取 base commit 后的 tracked 与 untracked 文件；证据不可用时返回空列表。"""
    try:
        base = base_commit_file.read_text(encoding='utf-8').strip()
    except OSError:
        return []
    if not base:
        return []
    diff = _git(repo_root, 'diff', '--name-only', '--diff-filter=ACMRD', base)
    untracked = _git(repo_root, 'ls-files', '--others', '--exclude-standard')
    paths = diff.stdout.splitlines() if diff else []
    if untracked:
        paths.extend(untracked.stdout.splitlines())
    return dedupe_paths(paths)


def _reject_symlink_components(path: Path) -> None:
    for component in [*reversed(path.parents), path]:
        if component == Path(component.anchor):
            continue
        try:
            metadata = component.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(metadata.st_mode):
            raise ValueError(f'private directory contains symbolic link: {component}')


def ensure_private_directory(path: Path, *, root: Path | None = None) -> Path:
    """创建仅当前用户可访问的目录，并拒绝越界、符号链接或属主异常。"""
    target = Path(os.path.abspath(path.expanduser()))
    boundary = Path(os.path.abspath(root.expanduser())) if root is not None else target
    try:
        target.relative_to(boundary)
    except ValueError as exc:
        raise ValueError(f'private directory escapes root: {target}') from exc
    if root is not None and boundary != target:
        ensure_private_directory(boundary)
    _reject_symlink_components(target)
    target.mkdir(parents=True, exist_ok=True, mode=0o700)
    _reject_symlink_components(target)
    metadata = target.lstat()
    uid = (getattr(os, 'geteuid', None) or os.getuid)()
    if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != uid:
        raise ValueError(f'unsafe private directory: {target}')
    os.chmod(target, 0o700)
    return target


def resolve_runtime_root(repo_root: Path) -> Path:
    """解析 checkout 共享的私有 runtime 根目录，并执行目录安全校验。"""
    override = os.environ.get('FEIPI_AGENT_RUNTIME_ROOT', '').strip()
    if override:
        return ensure_private_directory(Path(override).expanduser().resolve())
    common = _git(repo_root, 'rev-parse', '--git-common-dir')
    raw_common = common.stdout.strip() if common else str(repo_root.resolve())
    common_path = Path(raw_common)
    if not common_path.is_absolute():
        common_path = repo_root / common_path
    repo_key = stable_hash(str(common_path.resolve()))
    base = Path(os.environ.get('TMPDIR') or tempfile.gettempdir()).expanduser().resolve()
    root = base / 'feipi-gate-runtime' / repo_key
    return ensure_private_directory(root, root=ensure_private_directory(root.parent))


@dataclass
class PortAllocation:
    """保存 loopback 端口、run-scoped 记录与可选的占用 socket。"""

    name: str
    port: int
    path: Path
    socket: socket.socket | None = None

    def close(self) -> None:
        """关闭保留 socket，并删除对应的 run-scoped 端口记录。"""
        if self.socket is not None:
            self.socket.close()
            self.socket = None
        self.path.unlink(missing_ok=True)


def reserve_port(repo_root: Path, name: str, *, hold_socket: bool = True) -> PortAllocation:
    """预留 loopback 端口并写入 run-scoped 记录，可选择持续持有 socket。"""
    root = resolve_runtime_root(repo_root) / 'ports'
    root.mkdir(parents=True, exist_ok=True)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
    sock.bind(('127.0.0.1', 0))
    port = int(sock.getsockname()[1])
    if not hold_socket:
        sock.close()
    run_id = (
        os.environ.get('FEIPI_RUN_ID') or os.environ.get('FEIPI_SESSION_ID') or f'pid-{os.getpid()}'
    )
    checkout_id = stable_hash(str(repo_root.resolve()))[:12]
    path = root / f'{_safe_segment(run_id)}-{checkout_id}-{_safe_segment(name)}.json'
    path.write_text(json.dumps({'runId': run_id, 'name': name, 'port': port}) + '\n')
    return PortAllocation(name, port, path, sock if hold_socket else None)
