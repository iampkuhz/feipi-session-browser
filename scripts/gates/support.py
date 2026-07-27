"""Gate 与检查脚本共用的路径、Git 输入和有界进程原语。"""

from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import socket
import stat
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

PROVIDER_ENV_PREFIXES = ('CODEX_', 'QODER_', 'CLAUDE_')
PROCESS_TAIL_BYTES = 4096
PROCESS_TERM_GRACE_SECONDS = 0.4
_SAFE_SEGMENT_RE = re.compile(r'[^A-Za-z0-9._-]+')


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec='seconds').replace('+00:00', 'Z')


def stable_hash(value: str | bytes) -> str:
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
        return bool(self.raw_session_id)

    @property
    def is_agent(self) -> bool:
        return bool(self.raw_agent_id)

    @property
    def has_run(self) -> bool:
        return bool(self.raw_run_id)


# Compatibility name for callers that only need the small execution identity contract.
RuntimeIdentity = ExecutionIdentity


def identity_from_values(
    agent_client: str | None = None,
    session_id: str | None = None,
    agent_id: str | None = None,
    run_id: str | None = None,
    worktree_id: str | None = None,
    **_unused: object,
) -> ExecutionIdentity:
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
    return repo_root / 'tmp' / 'agent_logs' / identity.client / identity.session_id


def run_root_dir(repo_root: Path, identity: ExecutionIdentity) -> Path:
    root = session_root_dir(repo_root, identity)
    return root / 'runs' / identity.run_id if identity.has_run else root


def session_main_log_dir(repo_root: Path, identity: ExecutionIdentity) -> Path:
    return run_root_dir(repo_root, identity) / 'main'


def agent_log_dir(repo_root: Path, identity: ExecutionIdentity | None = None) -> Path:
    selected = identity or identity_from_values()
    if selected.is_agent:
        return run_root_dir(repo_root, selected) / 'agents' / selected.agent_id
    return session_main_log_dir(repo_root, selected)


def session_log_dirs(
    repo_root: Path, identity: ExecutionIdentity, *, include_agents: bool = False
) -> list[Path]:
    if identity.is_agent:
        return [agent_log_dir(repo_root, identity)]
    result = [session_main_log_dir(repo_root, identity)]
    agents = run_root_dir(repo_root, identity) / 'agents'
    if include_agents and agents.is_dir():
        result.extend(sorted(path for path in agents.iterdir() if path.is_dir()))
    return result


def quality_dir(repo_root: Path, identity: ExecutionIdentity | None = None) -> Path:
    selected = identity or identity_from_values()
    root = repo_root / 'tmp' / 'quality' / selected.client / selected.session_id
    if selected.has_run:
        root = root / 'runs' / selected.run_id
    return root / 'agents' / selected.agent_id if selected.is_agent else root / 'main'


@dataclass(frozen=True)
class ExecutionPaths:
    agent_log_dir: Path


def build_paths(repo_root: Path, identity: ExecutionIdentity | None = None) -> ExecutionPaths:
    return ExecutionPaths(agent_log_dir(repo_root, identity))


def normalize_path(path: str) -> str:
    value = path.replace('\\', '/').strip()
    while value.startswith('./'):
        value = value[2:]
    return value.strip('/')


def dedupe_paths(paths: list[str]) -> list[str]:
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
    if value is None:
        return []
    try:
        parsed: Any = json.loads(value)
    except json.JSONDecodeError:
        return []
    return dedupe_paths([item for item in parsed if isinstance(item, str)]) if isinstance(parsed, list) else []


def read_recorded_changed_files_from_paths(
    paths: list[Path], session_id: str | None = None, agent_id: str | None = None
) -> list[str]:
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
    uid = (getattr(os, 'geteuid', None) or getattr(os, 'getuid'))()
    if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != uid:
        raise ValueError(f'unsafe private directory: {target}')
    os.chmod(target, 0o700)
    return target


def resolve_runtime_root(repo_root: Path) -> Path:
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


def sanitized_environment(
    overrides: Mapping[str, str | None] | None = None, *, base: Mapping[str, str] | None = None
) -> dict[str, str]:
    result = {str(key): str(value) for key, value in (os.environ if base is None else base).items()}
    for key, value in (overrides or {}).items():
        if value is None:
            result.pop(str(key), None)
        else:
            result[str(key)] = str(value)
    for key in tuple(result):
        if key.startswith(PROVIDER_ENV_PREFIXES):
            result.pop(key, None)
    return result


@dataclass(frozen=True, slots=True)
class BoundedRunResult:
    return_code: int | None
    exit_reason: str
    timed_out: bool
    command_fingerprint: str
    environment_fingerprint: str
    started_at: str
    finished_at: str
    duration_seconds: float
    child_pid: int | None
    log_path: str
    output_tail: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _terminate_process_group(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        process.wait(timeout=2)
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        pass
    deadline = time.monotonic() + PROCESS_TERM_GRACE_SECONDS
    while process.poll() is None and time.monotonic() < deadline:
        time.sleep(0.02)
    if process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    process.wait(timeout=2)


def _log_tail(path: Path, limit: int = PROCESS_TAIL_BYTES) -> str:
    try:
        with path.open('rb') as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - limit))
            return handle.read(limit).decode('utf-8', errors='replace')
    except OSError:
        return ''


def run_bounded(
    argv: Sequence[str], *, cwd: Path | str, timeout: float, env: Mapping[str, str | None] | None,
    log_path: Path | str
) -> BoundedRunResult:
    if isinstance(argv, (str, bytes)) or not argv or any(not isinstance(v, str) or not v or '\0' in v for v in argv):
        raise ValueError('argv must contain non-empty strings without NUL')
    if timeout <= 0:
        raise ValueError('timeout must be positive')
    command = tuple(argv)
    selected_log = Path(os.path.abspath(Path(log_path).expanduser()))
    selected_log.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, 'O_NOFOLLOW', 0)
    descriptor = os.open(selected_log, flags, 0o600)
    child_env = sanitized_environment(env)
    started_at = utc_now()
    started = time.monotonic()
    process: subprocess.Popen[bytes] | None = None
    return_code: int | None = None
    exit_reason = 'SPAWN_ERROR'
    timed_out = False
    with os.fdopen(descriptor, 'wb') as log:
        try:
            process = subprocess.Popen(
                command, cwd=Path(cwd).resolve(), env=child_env, stdin=subprocess.DEVNULL,
                stdout=log, stderr=subprocess.STDOUT, start_new_session=True, shell=False
            )
            try:
                return_code = process.wait(timeout=timeout)
                exit_reason = 'SIGNAL' if return_code < 0 else 'EXITED'
            except subprocess.TimeoutExpired:
                timed_out = True
                exit_reason = 'TIMEOUT'
                _terminate_process_group(process)
                return_code = process.returncode
        except OSError as exc:
            log.write(f'{type(exc).__name__}: {exc}\n'.encode(errors='replace'))
        except BaseException:
            if process is not None:
                _terminate_process_group(process)
            raise
        finally:
            log.flush()
            os.fsync(log.fileno())
    return BoundedRunResult(
        return_code, exit_reason, timed_out, stable_hash(json.dumps(command)),
        stable_hash(json.dumps(sorted(child_env.items()))), started_at, utc_now(),
        round(time.monotonic() - started, 6), process.pid if process else None,
        str(selected_log), _log_tail(selected_log)
    )


@dataclass
class PortAllocation:
    name: str
    port: int
    path: Path
    socket: socket.socket | None = None

    def close(self) -> None:
        if self.socket is not None:
            self.socket.close()
            self.socket = None
        self.path.unlink(missing_ok=True)


def reserve_port(repo_root: Path, name: str, *, hold_socket: bool = True) -> PortAllocation:
    root = resolve_runtime_root(repo_root) / 'ports'
    root.mkdir(parents=True, exist_ok=True)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
    sock.bind(('127.0.0.1', 0))
    port = int(sock.getsockname()[1])
    if not hold_socket:
        sock.close()
    run_id = os.environ.get('FEIPI_RUN_ID') or os.environ.get('FEIPI_SESSION_ID') or f'pid-{os.getpid()}'
    path = root / f'{_safe_segment(run_id)}-{_safe_segment(name)}.json'
    path.write_text(json.dumps({'runId': run_id, 'name': name, 'port': port}) + '\n')
    return PortAllocation(name, port, path, sock if hold_socket else None)
