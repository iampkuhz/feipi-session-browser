"""构建 Claude/Codex/Qoder 跨平台 runtime identity and evidence paths。"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


SAFE_SEGMENT_RE = re.compile(r'[^A-Za-z0-9._-]+')
MAX_SEGMENT_LENGTH = 80


# 01. 数据结构
@dataclass(frozen=True)
class RuntimeIdentity:
    """表示 Claude/Codex/Qoder 跨平台 runtime identity。

    属性：
        client: agent client 适配器名称。
        session_id: 隔离运行数据的 session id。
        agent_id: 可选 subagent id。
        raw_session_id: 原始 session id。
        raw_agent_id: 原始 agent id。
    """

    client: str
    session_id: str
    agent_id: str = ''
    run_id: str = ''
    task_id: str = ''
    worktree_id: str = ''
    turn_id: str = ''
    stop_hook_active: bool = False
    raw_session_id: str = ''
    raw_agent_id: str = ''
    raw_run_id: str = ''
    raw_task_id: str = ''
    raw_worktree_id: str = ''
    raw_turn_id: str = ''
    change_id: str = ''
    branch: str = ''
    base_commit: str = ''
    checkout_root_hash: str = ''
    identity_warnings: tuple[str, ...] = ()

    # 判断是否存在session。
    @property
    def has_session(self) -> bool:
        """返回：
            满足条件时返回 true，否则返回 false。
        """
        return bool(self.raw_session_id)

    # 判断是否agent。
    @property
    def is_agent(self) -> bool:
        """返回：
            满足条件时返回 true，否则返回 false。
        """
        return bool(self.raw_agent_id)

    # 判断是否存在运行 id。
    @property
    def has_run(self) -> bool:
        """返回：
            存在运行 id 时返回 true，否则返回 false。
        """
        return bool(self.raw_run_id)


@dataclass(frozen=True)
class RepoPaths:
    """表示 RepoPaths。

    属性：
        repo_root: 仓库根目录。
        agent_log_dir: 当前 runtime 的 hook evidence 目录。
        identity: 当前 hook runtime identity。
    """

    repo_root: Path
    agent_log_dir: Path
    identity: RuntimeIdentity = field(
        default_factory=lambda: identity_from_values(
            agent_client='unknown', session_id='', agent_id=''
        )
    )

    # 维护changed-files 文件。
    @property
    def changed_files(self) -> Path:
        """返回：
            解析后的 HookContext；失败时携带 parse_error。
        """
        return self.agent_log_dir / 'changed-files.jsonl'

    # 维护session id 文件。
    @property
    def session_id_file(self) -> Path:
        """返回：
            解析后的 HookContext；失败时携带 parse_error。
        """
        return self.agent_log_dir / 'session-id.txt'

    # 维护base commit。
    @property
    def base_commit(self) -> Path:
        """返回：
            解析后的 HookContext；失败时携带 parse_error。
        """
        return self.agent_log_dir / 'base-commit.txt'

    # 维护hook event。
    @property
    def hook_events(self) -> Path:
        """返回：
            解析后的 HookContext；失败时携带 parse_error。
        """
        return self.agent_log_dir / 'hook-events.jsonl'

    # 维护命令 event。
    @property
    def command_events(self) -> Path:
        """返回：
            解析后的 HookContext；失败时携带 parse_error。
        """
        return self.agent_log_dir / 'command-events.jsonl'

    # 维护任务 evidence 目录。
    @property
    def task_evidence_dir(self) -> Path:
        """返回：
            解析后的 HookContext；失败时携带 parse_error。
        """
        return self.agent_log_dir / 'task-evidence'

    # 维护quality 目录。
    @property
    def quality_dir(self) -> Path:
        """返回：
            解析后的 HookContext；失败时携带 parse_error。
        """
        return quality_dir(self.repo_root, self.identity)

    # 维护stop summary。
    @property
    def stop_summary(self) -> Path:
        """返回：
            解析后的 HookContext；失败时携带 parse_error。
        """
        return self.agent_log_dir / 'stop-check-summary.json'

    # 维护active change。
    @property
    def active_change(self) -> Path:
        """返回：
            解析后的 HookContext；失败时携带 parse_error。
        """
        return self.active_change_candidates[0]

    # 维护active change 候选项。
    @property
    def active_change_candidates(self) -> list[Path]:
        """返回：
            结果列表。
        """
        repo_openspec = self.repo_root / 'openspec' / 'active_change.json'
        if not self.identity.has_session:
            return [repo_openspec, legacy_active_change_path(self.repo_root)]
        session_main = session_main_log_dir(self.repo_root, self.identity) / 'active_change.json'
        if self.identity.is_agent:
            return [self.agent_log_dir / 'active_change.json', session_main, repo_openspec]
        return [session_main, repo_openspec]


# 查找repo 根目录。
def find_repo_root(start: str | Path | None = None) -> Path:
    """参数：
        start: 可选路径 used as starting point用于git root detection。

    返回：
        解析后的 HookContext；失败时携带 parse_error。
    """
    start_path = Path.cwd() if start is None else Path(start).resolve()
    try:
        out = subprocess.check_output(
            ['git', '-C', str(start_path), 'rev-parse', '--show-toplevel'],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        if out:
            return Path(out).resolve()
    except Exception:
        pass
    return start_path


QUALITY_DIR_NAME = 'quality'


# 维护清理 路径 片段。
def sanitize_path_segment(value: str | None, fallback: str = 'unknown') -> str:
    """参数：
        value: value 参数。
        fallback: fallback 参数。

    返回：
        sanitize 路径 segment 字符串。
    """
    raw = str(value or '').strip()
    if not raw:
        raw = fallback
    cleaned = SAFE_SEGMENT_RE.sub('-', raw).strip('.-_/')
    if not cleaned:
        cleaned = fallback
    if cleaned in {'.', '..'}:
        cleaned = fallback
    if cleaned == raw and len(cleaned) <= MAX_SEGMENT_LENGTH and '/' not in cleaned:
        return cleaned
    digest = hashlib.sha256(raw.encode('utf-8')).hexdigest()[:12]
    prefix = cleaned[: max(1, MAX_SEGMENT_LENGTH - 13)].rstrip('.-')
    return f'{prefix}-{digest}'


# 维护identity 值。
def identity_from_values(
    agent_client: str | None = None,
    session_id: str | None = None,
    agent_id: str | None = None,
    run_id: str | None = None,
    task_id: str | None = None,
    worktree_id: str | None = None,
    turn_id: str | None = None,
    stop_hook_active: bool | None = None,
    change_id: str = '',
    branch: str = '',
    base_commit: str = '',
    checkout_root: str = '',
    identity_warnings: tuple[str, ...] = (),
) -> RuntimeIdentity:
    """参数：
        agent_client: agent client 参数。
        session_id: 用于筛选记录的 session id。
        agent_id: 用于筛选记录的 agent id。

    返回：
        解析后的 HookContext；失败时携带 parse_error。
    """
    raw_client = agent_client if agent_client is not None else os.environ.get('FEIPI_AGENT_CLIENT')
    raw_client = raw_client or 'unknown'
    raw_session = session_id if session_id is not None else os.environ.get('FEIPI_SESSION_ID', '')
    raw_agent = agent_id if agent_id is not None else os.environ.get('FEIPI_AGENT_ID', '')
    raw_run = run_id if run_id is not None else os.environ.get('FEIPI_RUN_ID', '')
    raw_task = task_id if task_id is not None else os.environ.get('FEIPI_TASK_ID', '')
    raw_worktree = (
        worktree_id if worktree_id is not None else os.environ.get('FEIPI_WORKTREE_ID', '')
    )
    raw_turn = turn_id if turn_id is not None else os.environ.get('FEIPI_TURN_ID', '')
    active = (
        bool(stop_hook_active)
        if stop_hook_active is not None
        else os.environ.get('FEIPI_STOP_HOOK_ACTIVE', '').lower() in {'1', 'true', 'yes', 'on'}
    )
    root_hash = hashlib.sha256(str(checkout_root or '').encode('utf-8')).hexdigest()[:16] if checkout_root else ''
    effective_warnings = list(identity_warnings)
    return RuntimeIdentity(
        client=sanitize_path_segment(raw_client, fallback='unknown'),
        session_id=sanitize_path_segment(raw_session, fallback='unknown'),
        agent_id=sanitize_path_segment(raw_agent, fallback='') if raw_agent else '',
        run_id=sanitize_path_segment(raw_run, fallback='') if raw_run else '',
        task_id=sanitize_path_segment(raw_task, fallback='') if raw_task else '',
        worktree_id=sanitize_path_segment(raw_worktree, fallback='') if raw_worktree else '',
        turn_id=sanitize_path_segment(raw_turn, fallback='') if raw_turn else '',
        stop_hook_active=active,
        raw_session_id=raw_session,
        raw_agent_id=raw_agent,
        raw_run_id=raw_run,
        raw_task_id=raw_task,
        raw_worktree_id=raw_worktree,
        raw_turn_id=raw_turn,
        change_id=change_id,
        branch=branch,
        base_commit=base_commit,
        checkout_root_hash=root_hash,
        identity_warnings=tuple(effective_warnings),
    )


# 判断缺失 session id 是否必须 fail-closed。
def identity_requires_fail_closed(
    identity: RuntimeIdentity,
    *,
    operation: str,
    protected: bool,
    mutating: bool,
) -> bool:
    """参数：
        identity: 当前 hook 运行身份。
        operation: 操作名称（当前未使用）。
        protected: 是否为受保护写入操作。
        mutating: 是否为变更操作。

    返回：
        缺失 session id 时是否必须故障关闭。

    Claude/Codex/Qoder 对受保护写入和变更操作共享同一策略：没有 session id
    时不能写入共享证据目录；只读操作允许继续。
    """
    del operation
    return not identity.raw_session_id and (protected or mutating)


# 维护identity hook context。
def identity_from_hook_context(ctx: Any, agent_client: str | None = None) -> RuntimeIdentity:
    """参数：
        ctx: ctx 参数。
        agent_client: agent client 参数。

    返回：
        解析后的 HookContext；失败时携带 parse_error。
    """
    client = (
        agent_client
        or getattr(ctx, 'agent_client', '')
        or os.environ.get('FEIPI_AGENT_CLIENT')
        or 'unknown'
    )
    payload_session = getattr(ctx, 'session_id', None)
    payload_run = getattr(ctx, 'run_id', None)
    payload_task = getattr(ctx, 'task_id', None)
    payload_worktree = getattr(ctx, 'worktree_id', None)
    payload_turn = getattr(ctx, 'turn_id', None)
    record: dict[str, Any] = {}
    warnings: list[str] = []
    try:
        from scripts.harness.primary_session import resolve_bound_run_record
        repo_hint = getattr(ctx, 'cwd', '') or None
        root = find_repo_root(repo_hint)
        lookup_session = payload_session or ''
        # Registry 中与 client/session/current checkout 一致的记录优先；payload
        # run id 只在一致时作为提示，不能劫持已经登记的 Session。
        record = resolve_bound_run_record(root, client, lookup_session, '') or {}
        if not record and payload_run:
            record = resolve_bound_run_record(root, client, lookup_session, payload_run) or {}
    except Exception:
        record = {}
    run_id = str(record.get('runId') or payload_run or '')
    if record and payload_run and payload_run != record.get('runId'):
        warnings.append('payload run_id hint ignored because Registry identity is authoritative')
    session_id = payload_session or str(record.get('sessionId') or '')
    return identity_from_values(
        agent_client=client,
        session_id=session_id,
        agent_id=getattr(ctx, 'agent_id', None),
        run_id=run_id,
        task_id=payload_task or str(record.get('taskId') or ''),
        worktree_id=str(record.get('worktreeId') or payload_worktree or ''),
        turn_id=payload_turn or '',
        stop_hook_active=getattr(ctx, 'stop_hook_active', None),
        change_id=str(record.get('changeId') or ''),
        branch=str(record.get('branch') or ''),
        base_commit=str(record.get('baseCommit') or ''),
        checkout_root=str(record.get('checkoutRoot') or ''),
        identity_warnings=tuple(warnings),
    )


# 维护legacy active change 路径。
def legacy_active_change_path(repo_root: Path) -> Path:
    """参数：
        repo_root: 仓库根目录。

    返回：
        解析后的 HookContext；失败时携带 parse_error。
    """
    return repo_root / 'tmp' / 'active_change.json'


# 维护session 根目录 目录。
def session_root_dir(repo_root: Path, identity: RuntimeIdentity) -> Path:
    """参数：
        repo_root: 仓库根目录。
        identity: 当前 hook 运行time identity。

    返回：
        解析后的 HookContext；失败时携带 parse_error。
    """
    return repo_root / 'tmp' / 'agent_logs' / identity.client / identity.session_id


# 返回运行级根目录。
def run_root_dir(repo_root: Path, identity: RuntimeIdentity) -> Path:
    """参数：
        repo_root: 仓库根目录。
        identity: 当前 hook 运行时 identity。

    返回：
        当前运行的根目录。
    """
    base = session_root_dir(repo_root, identity)
    if identity.has_run:
        return base / 'runs' / identity.run_id
    return base


# 返回主 session 日志目录。
def session_main_log_dir(repo_root: Path, identity: RuntimeIdentity) -> Path:
    """参数：
        repo_root: 仓库根目录。
        identity: 当前 hook 运行time identity。

    返回：
        解析后的 HookContext；失败时携带 parse_error。
    """
    return run_root_dir(repo_root, identity) / 'main'


# 维护agent log 目录。
def agent_log_dir(repo_root: Path, identity: RuntimeIdentity | None = None) -> Path:
    """参数：
        repo_root: repo root 路径。
        identity: 当前 hook 运行time identity。

    返回：
        运行time 日志 目录用于当前 hook session。
    """
    identity = identity or identity_from_values()
    if identity.is_agent:
        return run_root_dir(repo_root, identity) / 'agents' / identity.agent_id
    return session_main_log_dir(repo_root, identity)


# 维护session log 目录。
def session_log_dirs(
    repo_root: Path,
    identity: RuntimeIdentity,
    *,
    include_agents: bool = False,
) -> list[Path]:
    """参数：
        repo_root: 仓库根目录。
        identity: 当前 hook 运行time identity。
        include_agents: 是否包含 agent 目录。

    返回：
        结果列表。
    """
    if identity.is_agent:
        return [agent_log_dir(repo_root, identity)]
    dirs = [session_main_log_dir(repo_root, identity)]
    if include_agents:
        agents_root = run_root_dir(repo_root, identity) / 'agents'
        if agents_root.exists():
            dirs.extend(sorted(p for p in agents_root.iterdir() if p.is_dir()))
    return dirs


# 维护quality 目录。
def quality_dir(repo_root: Path, identity: RuntimeIdentity | None = None) -> Path:
    """参数：
        repo_root: repo root 路径。
        identity: 当前 hook 运行time identity。

    返回：
        路径到 ``tmp/quality``。
    """
    identity = identity or identity_from_values()
    base = repo_root / 'tmp' / QUALITY_DIR_NAME / identity.client / identity.session_id
    if identity.has_run:
        base = base / 'runs' / identity.run_id
    if identity.is_agent:
        return base / 'agents' / identity.agent_id
    return base / 'main'


# 构建路径。
def build_paths(
    repo_root: str | Path | None = None,
    identity: RuntimeIdentity | None = None,
) -> RepoPaths:
    """参数：
        repo_root: 可选repo root override用于tests。
        identity: 当前 hook 运行time identity。

    返回：
        ``RepoPaths`` containing repo root 和 当前 agent 日志 目录。
    """
    root = find_repo_root(repo_root)
    resolved_identity = identity or identity_from_values()
    log_dir = agent_log_dir(root, resolved_identity)
    return RepoPaths(repo_root=root, agent_log_dir=log_dir, identity=resolved_identity)


# 确保runtime 目录。
def ensure_runtime_dirs(paths: RepoPaths) -> None:
    """参数：
        paths: Repository 运行time 路径 whose 日志 目录 should exist。
    """
    for path in [
        paths.agent_log_dir,
        paths.task_evidence_dir,
        paths.quality_dir,
        paths.agent_log_dir / 'config',
    ]:
        path.mkdir(parents=True, exist_ok=True)


# 维护相对 repo。
def rel_to_repo(path: str | Path, repo_root: str | Path) -> str:
    """参数：
        path: Absolute 或 relative 路径从hook 输入。
        repo_root: 用于把绝对路径转为相对路径的 repo root。

    返回：
        repository-relative POSIX 路径, 或 original absolute 路径 字符串 当 the。 输入 is outside repository。
    """
    p = Path(path)
    root = Path(repo_root).resolve()
    if not p.is_absolute():
        return str(p.as_posix()).lstrip('./')
    try:
        return str(p.resolve().relative_to(root).as_posix())
    except Exception:
        return str(p)
