"""统一解析 Claude、Codex 与 Qoder 的 Session/Run 身份。

本模块只负责把 payload、环境变量与 Registry 事实归一为不可变身份；
证据目录布局由 ``paths`` 负责，Registry 状态变更由 ``registry`` 负责。

不负责平台 Hook wrapper 配置；由 Hook 或 Stop runtime 调用。"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from typing import Any

SAFE_SEGMENT_RE = re.compile(r'[^A-Za-z0-9._-]+')
MAX_SEGMENT_LENGTH = 80


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
    root_hash = (
        hashlib.sha256(str(checkout_root or '').encode('utf-8')).hexdigest()[:16]
        if checkout_root
        else ''
    )
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
        from scripts.agent_runtime.paths import find_repo_root
        from scripts.agent_runtime.registry import resolve_bound_run_record

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
