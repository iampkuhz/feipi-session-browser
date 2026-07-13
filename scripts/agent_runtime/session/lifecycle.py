"""负责 Session bootstrap、状态诊断、Stop 回执与清理生命周期；不负责执行 Gate 或远端集成；由 Hook、sessionctl 和 finalize 调用。"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

from scripts.agent_runtime.git_state import run as git
from scripts.agent_runtime.stop.evidence import GitEvidenceError, collect_git_evidence
from scripts.agent_runtime.storage import utc_now as now_utc

from .common import _append_run_audit, _set_run_status, _writer_status, emit_json
from .contract import (
    ACTIVE_WRITER_STATUSES,
    CHECKOUT_CREATORS,
    PrimarySessionValidationError,
    capture_primary_head_snapshot,
    resolve_checkout_identity,
    resolve_checkout_root,
    snapshot_path_states,
    stable_worktree_id,
    validate_checkout_record,
    validate_run_collisions,
    validate_run_record,
)
from .errors import SessionctlError
from .handoff import build_handoff_report
from .registry import REGISTRY_VERSION, Registry, _validate_identifier

if TYPE_CHECKING:
    import argparse

DEFAULT_FORBIDDEN_PATHS = [".env", ".mcp.json", "data", "output", "tmp/agent_logs"]


def classify_tool_call(tool_name: str, tool_input: Mapping[str, Any] | None = None) -> str:
    """将工具调用判定为只读、验证或修改，未知 shell 命令按修改处理以关闭失败。"""
    normalized = re.sub('[^a-z]', '', tool_name.rsplit('.', 1)[-1].lower())
    if normalized in {'write', 'edit', 'multiedit', 'applypatch', 'patch'}:
        return 'mutation'
    if normalized not in {'bash', 'shell', 'execcommand', 'command'}:
        return 'read-only'
    payload = tool_input or {}
    command = str(payload.get('command') or payload.get('cmd') or '').strip()
    if not command:
        return 'read-only'
    compact = ' '.join(command.split())
    lowered = compact.lower()
    validation_patterns = (
        '(^|[;&|]\\s*)(python3?\\s+-m\\s+pytest|pytest)(\\s|$)',
        '(^|[;&|]\\s*)(mvnw?|gradlew?|gradle)(\\s|$).*(\\stest|\\scheck)(\\s|$)',
        '(^|[;&|]\\s*)bash\\s+scripts/harness/doctor\\.sh(\\s|$)',
        '(^|[;&|]\\s*)[^;&|]*scripts/(quality|openspec)/[^;&|]*(validate|gate|test)',
        '(^|[;&|]\\s*)\\./scripts/session-browser\\.sh\\s+test(\\s|$)',
    )
    if any(re.search(pattern, lowered) for pattern in validation_patterns):
        return 'validation'
    mutation_patterns = (
        '(^|[;&|]\\s*)(touch|rm|mv|cp|mkdir|rmdir|install|chmod|chown|truncate|tee)(\\s|$)',
        '(^|[;&|]\\s*)(sed|perl)\\s+[^;&|]*\\s-i(?:\\s|$)',
        '(^|[;&|]\\s*)git\\s+(add|commit|checkout|switch|reset|merge|rebase|cherry-pick|am|apply|clean|restore)(\\s|$)',
        '(^|[;&|]\\s*)git\\s+worktree\\s+(?!list(?:\\s|$))\\S+',
        '(^|[;&|]\\s*)(npm|pnpm|yarn|pip|pip3)\\s+(install|add|remove|uninstall|update)(\\s|$)',
        '(^|[^<])>>?\\s*[^&]',
        '(^|[;&|]\\s*)find\\s+[^;&|]*\\s-delete(?:\\s|$)',
    )
    if any(re.search(pattern, lowered) for pattern in mutation_patterns):
        return 'mutation'
    read_prefixes = (
        'cat ',
        'rg ',
        'grep ',
        'ls',
        'pwd',
        'head ',
        'tail ',
        'wc ',
        'find ',
        'stat ',
        'git status',
        'git diff',
        'git log',
        'git show',
        'git rev-parse',
        'git branch --show-current',
        'git worktree list',
        'sed -n ',
    )
    return 'read-only' if lowered.startswith(read_prefixes) else 'mutation'


def repo_root_from_arg(value: str | None) -> Path:
    """从显式路径或当前目录解析 Git 根；非仓库输入转换为 SessionctlError。"""
    start = Path(value).resolve() if value else Path.cwd().resolve()
    try:
        out = git(start, 'rev-parse', '--show-toplevel')
    except subprocess.CalledProcessError as exc:
        raise SessionctlError(f'not a git repository: {start}') from exc
    return Path(out.stdout.strip()).resolve()


def _checkout_snapshot(cwd: Path, *, checkout_creator: str = 'unknown') -> dict[str, Any]:
    checkout_root = resolve_checkout_root(cwd)
    identity = resolve_checkout_identity(checkout_root, checkout_creator=checkout_creator)
    porcelain = git(
        checkout_root, 'status', '--porcelain=v1', '--untracked-files=all'
    ).stdout.splitlines()
    tracked = [line[3:] for line in porcelain if len(line) >= 4 and (not line.startswith('??'))]
    untracked = [line[3:] for line in porcelain if line.startswith('??') and len(line) >= 4]
    captured_at = now_utc()
    dirty_paths = [*tracked, *untracked]
    return {
        **identity,
        'initialDirtySnapshot': {
            'dirty': bool(porcelain),
            'porcelain': porcelain,
            'tracked': tracked,
            'untracked': untracked,
            'pathStates': snapshot_path_states(checkout_root, dirty_paths),
            'capturedAt': captured_at,
        },
    }


def _build_bootstrap_record(
    registry: Registry,
    *,
    client: str,
    session_id: str,
    hook_event: str,
    cwd: Path,
    run_id: str,
    checkout_creator: str = 'unknown',
    facts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    snapshot = facts or _checkout_snapshot(cwd, checkout_creator=checkout_creator)
    if snapshot['repoKey'] != registry.repo_key:
        raise SessionctlError('bootstrap checkout does not belong to Registry repository')
    timestamp = now_utc()
    checkout_root = str(snapshot['checkoutRoot'])
    worktree_id = stable_worktree_id(registry.repo_key, checkout_root)
    base_evidence = snapshot.get('worktreeBase')
    target_branch = str(snapshot['branch'])
    primary = Path(str(snapshot['primaryRepoRoot']))
    if isinstance(base_evidence, dict):
        target_branch = str(base_evidence['expectedBranch'])
    elif snapshot['checkoutKind'] == 'linked-worktree':
        observed_target = git(primary, 'branch', '--show-current', check=False)
        target_branch = observed_target.stdout.strip() if observed_target.returncode == 0 else ''
    target_head = (
        str(base_evidence.get('expectedHead') or '') if isinstance(base_evidence, dict) else ''
    )
    if target_branch and (not target_head):
        observed_head = git(
            primary, 'rev-parse', '--verify', f'refs/heads/{target_branch}', check=False
        )
        if observed_head.returncode == 0:
            target_head = observed_head.stdout.strip()
    return {
        'schemaVersion': REGISTRY_VERSION,
        'runId': _validate_identifier(run_id, 'run id'),
        'repoKey': registry.repo_key,
        'client': client,
        'taskId': f'session:{session_id}',
        'sessionId': session_id,
        'worktreeId': worktree_id,
        'checkoutRoot': checkout_root,
        'checkoutKind': snapshot['checkoutKind'],
        'checkoutCreator': snapshot['checkoutCreator'],
        'gitCommonDir': snapshot['gitCommonDir'],
        'branch': snapshot['branch'],
        'detached': snapshot['detached'],
        'targetBranch': target_branch,
        'targetHeadAtBootstrap': target_head,
        'worktreeBase': base_evidence
        or {
            'policy': 'primary-head',
            'expectedBranch': target_branch,
            'expectedHead': target_head,
            'actualHead': str(snapshot['headCommit']),
            'matched': not target_head or target_head == str(snapshot['headCommit']),
        },
        'primaryRepoRoot': snapshot['primaryRepoRoot'],
        'baseCommit': snapshot['headCommit'],
        'headCommit': snapshot['headCommit'],
        'initialDirtySnapshot': snapshot['initialDirtySnapshot'],
        'changeAttribution': {
            'baseline': 'initialDirtySnapshot',
            'preexistingChangesAttributedToRun': False,
            'requiresHandoffIfIndistinguishable': bool(snapshot['initialDirtySnapshot']['dirty']),
        },
        'changeId': '',
        'status': 'BOOTSTRAPPED',
        'allowedPaths': ['.'],
        'forbiddenPaths': list(DEFAULT_FORBIDDEN_PATHS),
        'writerLease': {},
        'hookActivation': {
            'confirmed': True,
            'client': client,
            'sessionId': session_id,
            'cwd': str(cwd.resolve()),
            'source': 'sessionctl bootstrap',
        },
        'bootstrap': {
            'firstHookEvent': hook_event,
            'lastHookEvent': hook_event,
            'firstSeenAt': timestamp,
            'lastSeenAt': timestamp,
            'lastCwd': str(cwd.resolve()),
        },
        'auditEvents': [],
        'createdAt': timestamp,
        'updatedAt': timestamp,
    }


def _enforce_new_client_worktree_base(facts: dict[str, Any], *, client: str) -> None:
    if client not in {'claude', 'codex'} or facts['checkoutKind'] != 'linked-worktree':
        return
    snapshot = capture_primary_head_snapshot(Path(str(facts['checkoutRoot'])))
    actual_head = str(facts['headCommit'])
    evidence = {
        'policy': 'primary-head',
        'expectedBranch': snapshot.branch,
        'expectedHead': snapshot.head_commit,
        'actualHead': actual_head,
        'matched': actual_head == snapshot.head_commit,
    }
    facts['worktreeBase'] = evidence
    if not evidence['matched']:
        detail = json.dumps(evidence, ensure_ascii=False, sort_keys=True)
        raise SessionctlError(
            f'WORKTREE_BASE_MISMATCH: linked worktree must be recreated from the primary checkout current branch HEAD; {detail}'
        )


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
    """仅允许尚未获取 writer lease 的 Claude Session 在 CwdChanged 时重绑同仓 checkout。"""
    if client != 'claude' or hook_event != 'CwdChanged':
        raise SessionctlError('Session is already bound to a different checkout')
    if record.get('status') not in {'BOOTSTRAPPED', 'READ_ONLY_READY'}:
        raise SessionctlError('Session checkout cannot change after writer activation')
    if record.get('writerLease'):
        raise SessionctlError('Session checkout cannot change while writer lease exists')
    if record.get('releasedWriterLease'):
        raise SessionctlError('Session checkout cannot change after writer activation')
    if record.get('subagentSessions'):
        raise SessionctlError('Session checkout cannot change after subagent inheritance')
    if record.get('gitCommonDir') != facts.get('gitCommonDir'):
        raise SessionctlError('Session checkout change must stay in one Git common directory')
    previous_root = str(record.get('checkoutRoot') or '')
    previous_worktree_id = str(record.get('worktreeId') or '')
    rebound = _build_bootstrap_record(
        registry,
        client=client,
        session_id=session_id,
        hook_event=hook_event,
        cwd=Path(str(facts['checkoutRoot'])),
        run_id=str(record['runId']),
        checkout_creator=checkout_creator,
        facts=facts,
    )
    rebound['taskId'] = record['taskId']
    rebound['changeId'] = str(record.get('changeId') or '')
    rebound['allowedPaths'] = list(record.get('allowedPaths') or ['.'])
    rebound['forbiddenPaths'] = list(record.get('forbiddenPaths') or DEFAULT_FORBIDDEN_PATHS)
    rebound['status'] = str(record['status'])
    rebound['createdAt'] = str(record['createdAt'])
    previous_bootstrap = record.get('bootstrap')
    if isinstance(previous_bootstrap, dict):
        rebound['bootstrap']['firstHookEvent'] = str(
            previous_bootstrap.get('firstHookEvent') or hook_event
        )
        rebound['bootstrap']['firstSeenAt'] = str(
            previous_bootstrap.get('firstSeenAt') or record['createdAt']
        )
    previous_events = record.get('auditEvents')
    rebound['auditEvents'] = list(previous_events) if isinstance(previous_events, list) else []
    event = {
        'event': 'SESSION_CHECKOUT_REBOUND',
        'runId': rebound['runId'],
        'sessionId': rebound['sessionId'],
        'fromCheckoutRoot': previous_root,
        'fromWorktreeId': previous_worktree_id,
        'toCheckoutRoot': rebound['checkoutRoot'],
        'toWorktreeId': rebound['worktreeId'],
        'hookEvent': hook_event,
        'at': now_utc(),
    }
    rebound['auditEvents'].append(event)
    registry.write_audit(event)
    return rebound


def _record_matches_bootstrap(
    record: Mapping[str, Any], *, client: str, session_id: str, facts: Mapping[str, Any]
) -> bool:
    return (
        record.get('repoKey') == facts['repoKey']
        and record.get('client') == client
        and (record.get('sessionId') == session_id)
        and (
            Path(str(record.get('checkoutRoot') or '')).resolve()
            == Path(str(facts['checkoutRoot']))
        )
        and (record.get('gitCommonDir') == facts['gitCommonDir'])
        and (record.get('checkoutKind') == facts['checkoutKind'])
        and (record.get('primaryRepoRoot') == facts['primaryRepoRoot'])
        and (
            record.get('worktreeId')
            == stable_worktree_id(str(facts['repoKey']), str(facts['checkoutRoot']))
        )
    )


def _identity_hint_event(
    *, source: str, field: str, value: str, expected: str, hook_event: str, run_id: str
) -> dict[str, Any]:
    return {
        'event': 'IDENTITY_HINT_IGNORED',
        'source': source,
        'field': field,
        'value': value,
        'expected': expected,
        'hookEvent': hook_event,
        'runId': run_id,
        'at': now_utc(),
    }


def _candidate_from_run_hint(
    registry: Registry, run_id: str, *, client: str, session_id: str, facts: Mapping[str, Any]
) -> dict[str, Any] | None:
    if not run_id:
        return None
    try:
        candidate = registry.load_run(run_id)
    except SessionctlError:
        return None
    return (
        candidate
        if _record_matches_bootstrap(candidate, client=client, session_id=session_id, facts=facts)
        else None
    )


def _claim_launcher_run(
    registry: Registry,
    run_id: str,
    *,
    client: str,
    session_id: str,
    facts: Mapping[str, Any],
) -> dict[str, Any] | None:
    """把 launcher 的 pending identity 原子交给真实 SessionStart payload。"""
    if not run_id:
        return None
    try:
        candidate = registry.load_run(run_id)
    except SessionctlError:
        return None
    completion = candidate.get('completion')
    if (
        candidate.get('launcherPending') is not True
        or candidate.get('client') != client
        or candidate.get('repoKey') != facts.get('repoKey')
        or Path(str(candidate.get('checkoutRoot') or '')).resolve()
        != Path(str(facts.get('checkoutRoot') or '')).resolve()
        or candidate.get('writerLease')
        or (isinstance(completion, Mapping) and completion.get('firstMutationAt'))
    ):
        return None
    previous_session = str(candidate.get('sessionId') or '')
    candidate['sessionId'] = session_id
    candidate['launcherPending'] = False
    begin = candidate.get('changeBegin')
    if isinstance(begin, dict):
        begin['sessionId'] = session_id
        begin['claimedAt'] = now_utc()
    event = {
        'event': 'LAUNCHER_RUN_CLAIMED',
        'runId': run_id,
        'previousSessionId': previous_session,
        'sessionId': session_id,
        'at': now_utc(),
    }
    _append_run_audit(registry, candidate, event)
    return candidate


def _normalize_identity_hints(hints: Mapping[str, Any] | None) -> dict[str, str]:
    source = hints or {}

    def first(*names: str) -> str:
        """按可信度顺序选择首个非空身份提示，不把空字符串当作事实。"""
        for name in names:
            value = str(source.get(name) or '').strip()
            if value:
                return value
        return ''

    return {
        'runId': first('runId', 'run_id', 'FEIPI_RUN_ID'),
        'worktreeId': first('worktreeId', 'worktree_id', 'FEIPI_WORKTREE_ID'),
        'sessionId': first('sessionId', 'session_id', 'FEIPI_SESSION_ID'),
        'client': first('client', 'agent_client', 'FEIPI_CLIENT', 'FEIPI_AGENT_CLIENT'),
        'changeId': first('changeId', 'change_id', 'ACTIVE_CHANGE_ID'),
    }


def _audit_identity_hints(
    registry: Registry,
    record: dict[str, Any],
    *,
    hook_event: str,
    checkout_creator: str = 'unknown',
    payload_hints: Mapping[str, str],
    env_hints: Mapping[str, str],
) -> None:
    expected = {
        'runId': str(record['runId']),
        'worktreeId': str(record['worktreeId']),
        'sessionId': str(record['sessionId']),
        'client': str(record['client']),
        'changeId': str(record.get('changeId') or ''),
    }
    fields = {
        'runId': 'runId',
        'worktreeId': 'worktreeId',
        'sessionId': 'sessionId',
        'client': 'client',
        'changeId': 'changeId',
    }
    events = record.setdefault('auditEvents', [])
    if not isinstance(events, list):
        raise SessionctlError('run auditEvents must be a list')
    for source, hints in (('payload', payload_hints), ('environment', env_hints)):
        for hint_field, record_field in fields.items():
            value = str(hints.get(hint_field) or '')
            if value and value != expected[record_field]:
                event = _identity_hint_event(
                    source=source,
                    field=hint_field,
                    value=value,
                    expected=expected[record_field],
                    hook_event=hook_event,
                    run_id=str(record['runId']),
                )
                events.append(event)
                registry.write_audit(event)


def bootstrap_session(
    *,
    client: str,
    session_id: str,
    cwd: Path,
    hook_event: str,
    checkout_creator: str = 'unknown',
    payload_hints: Mapping[str, Any] | None = None,
    env_hints: Mapping[str, Any] | None = None,
    parent_run_id: str = '',
) -> dict[str, Any]:
    """在 Registry 锁内创建或复用唯一 Session run，并审计不一致的外部身份提示。"""
    client = client.strip()
    session_id = session_id.strip()
    hook_event = hook_event.strip()
    if not client or not session_id or (not hook_event):
        raise SessionctlError('bootstrap requires non-empty client, session-id, and hook-event')
    if checkout_creator not in CHECKOUT_CREATORS:
        raise SessionctlError(f'invalid checkout creator: {checkout_creator}')
    checkout = resolve_checkout_root(cwd)
    facts = _checkout_snapshot(checkout, checkout_creator=checkout_creator)
    registry = Registry(checkout)
    payload = _normalize_identity_hints(payload_hints)
    environment = _normalize_identity_hints(env_hints)
    with registry.locked(client=client, session_id=session_id, run_id=payload.get('runId', '')):
        records = registry.all_runs()
        if parent_run_id:
            parent_run_id = _validate_identifier(parent_run_id, 'parent run id')
            parent = registry.load_run(parent_run_id)
            if parent.get('client') != client:
                raise SessionctlError('subagent client does not match parent run')
            parent_root = Path(str(parent.get('checkoutRoot') or '')).resolve()
            if (
                parent.get('repoKey') != facts['repoKey']
                or parent.get('worktreeId')
                != stable_worktree_id(str(facts['repoKey']), str(facts['checkoutRoot']))
                or parent_root != Path(str(facts['checkoutRoot'])).resolve()
            ):
                raise SessionctlError('subagent checkout does not match parent run')
            registry.update_lock_context(
                client=str(parent['client']),
                session_id=str(parent['sessionId']),
                run_id=str(parent['runId']),
            )
            timestamp = now_utc()
            event = {
                'event': 'SUBAGENT_RUN_INHERITED',
                'runId': parent['runId'],
                'sessionId': parent['sessionId'],
                'subagentSessionId': session_id,
                'worktreeId': parent['worktreeId'],
                'hookEvent': hook_event,
                'at': timestamp,
            }
            _append_run_audit(registry, parent, event)
            observations = parent.setdefault('subagentSessions', [])
            if not isinstance(observations, list):
                raise SessionctlError('run subagentSessions must be a list')
            if session_id not in observations:
                observations.append(session_id)
            parent['updatedAt'] = timestamp
            registry.save_run(parent)
            return parent
        exact = [
            item
            for item in records
            if _record_matches_bootstrap(item, client=client, session_id=session_id, facts=facts)
        ]
        if len(exact) > 1:
            raise SessionctlError('Registry contains duplicate client/session/checkout runs')
        same_session_elsewhere = [
            item
            for item in records
            if item.get('repoKey') == facts['repoKey']
            and item.get('client') == client
            and (item.get('sessionId') == session_id)
            and (
                not _record_matches_bootstrap(
                    item, client=client, session_id=session_id, facts=facts
                )
            )
        ]
        if exact:
            record = exact[0]
        elif same_session_elsewhere:
            _enforce_new_client_worktree_base(facts, client=client)
            if len(same_session_elsewhere) != 1:
                raise SessionctlError('Registry contains duplicate client/session runs')
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
            _enforce_new_client_worktree_base(facts, client=client)
            record = (
                _candidate_from_run_hint(
                    registry,
                    payload.get('runId', ''),
                    client=client,
                    session_id=session_id,
                    facts=facts,
                )
                or _candidate_from_run_hint(
                    registry,
                    environment.get('runId', ''),
                    client=client,
                    session_id=session_id,
                    facts=facts,
                )
                or _claim_launcher_run(
                    registry,
                    payload.get('runId', '') or environment.get('runId', ''),
                    client=client,
                    session_id=session_id,
                    facts=facts,
                )
            )
            if record is None:
                run_id = f'run-{uuid.uuid4().hex[:20]}'
                while any(item.get('runId') == run_id for item in records):
                    run_id = f'run-{uuid.uuid4().hex[:20]}'
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
        registry.update_lock_context(
            client=client, session_id=session_id, run_id=str(record['runId'])
        )
        bootstrap = record.setdefault('bootstrap', {})
        if not isinstance(bootstrap, dict):
            raise SessionctlError('run bootstrap metadata must be an object')
        bootstrap.setdefault('firstHookEvent', hook_event)
        bootstrap.setdefault('firstSeenAt', record.get('createdAt') or now_utc())
        bootstrap['lastHookEvent'] = hook_event
        bootstrap['lastSeenAt'] = now_utc()
        bootstrap['lastCwd'] = str(checkout)
        if record.get('checkoutCreator') == 'unknown' and checkout_creator != 'unknown':
            record['checkoutCreator'] = checkout_creator
        record['updatedAt'] = now_utc()
        _audit_identity_hints(
            registry, record, hook_event=hook_event, payload_hints=payload, env_hints=environment
        )
        registry.save_run(record)
    return record


def set_change_for_session(
    *, client: str, session_id: str, cwd: Path, change_id: str, task_id: str = ''
) -> dict[str, Any]:
    """把当前唯一 Session run 绑定到已存在的 OpenSpec change，并记录前后任务身份。"""
    client = client.strip()
    session_id = session_id.strip()
    change_id = change_id.strip()
    if not client or not session_id or (not change_id):
        raise SessionctlError('set-change requires non-empty client, session-id, and change-id')
    checkout = resolve_checkout_root(cwd)
    _validate_identifier(change_id, 'change id')
    if not (checkout / 'openspec' / 'changes' / change_id).is_dir():
        raise SessionctlError(f'OpenSpec change does not exist in current checkout: {change_id}')
    facts = _checkout_snapshot(checkout)
    registry = Registry(checkout)
    with registry.locked(client=client, session_id=session_id):
        matches = [
            item
            for item in registry.all_runs()
            if _record_matches_bootstrap(item, client=client, session_id=session_id, facts=facts)
        ]
        if len(matches) != 1:
            raise SessionctlError('set-change requires exactly one current Session run')
        record = matches[0]
        registry.update_lock_context(run_id=str(record['runId']))
        previous = str(record.get('changeId') or '')
        previous_task = str(record.get('taskId') or '')
        record['changeId'] = change_id
        if task_id.strip():
            record['taskId'] = task_id.strip()
        record['updatedAt'] = now_utc()
        event = {
            'event': 'CHANGE_BOUND',
            'runId': record['runId'],
            'client': client,
            'sessionId': session_id,
            'previousChangeId': previous,
            'changeId': change_id,
            'previousTaskId': previous_task,
            'taskId': record['taskId'],
            'at': now_utc(),
        }
        audit = record.setdefault('auditEvents', [])
        if not isinstance(audit, list):
            raise SessionctlError('run auditEvents must be a list')
        audit.append(event)
        registry.write_audit(event)
        registry.save_run(record)
    return record


def cmd_bootstrap(args: argparse.Namespace) -> int:
    """把 CLI 和环境身份提示适配到 bootstrap 服务并输出权威运行记录。"""
    payload_hints = {'runId': args.run_id or '', 'worktreeId': args.worktree_id or ''}
    env_hints = {
        'runId': os.environ.get('FEIPI_RUN_ID', ''),
        'worktreeId': os.environ.get('FEIPI_WORKTREE_ID', ''),
        'sessionId': os.environ.get('FEIPI_SESSION_ID', ''),
        'client': os.environ.get('FEIPI_CLIENT', '') or os.environ.get('FEIPI_AGENT_CLIENT', ''),
        'changeId': os.environ.get('ACTIVE_CHANGE_ID', ''),
    }
    record = bootstrap_session(
        client=args.client,
        session_id=args.session_id,
        cwd=Path(args.cwd),
        hook_event=args.hook_event,
        checkout_creator=args.checkout_creator,
        payload_hints=payload_hints,
        env_hints=env_hints,
        parent_run_id=args.parent_run_id or '',
    )
    emit_json(record)
    return 0


def cmd_set_change(args: argparse.Namespace) -> int:
    """把 CLI change 参数适配到绑定服务并输出更新后的运行记录。"""
    record = set_change_for_session(
        client=args.client,
        session_id=args.session_id,
        cwd=Path(args.cwd),
        change_id=args.change_id,
        task_id=args.task_id or '',
    )
    emit_json(record)
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    """列出当前仓库 Registry 运行；JSON 与表格模式共享同一持锁快照。"""
    repo = repo_root_from_arg(args.repo_root)
    registry = Registry(repo)
    with registry.locked():
        records = registry.all_runs()
    if args.json:
        emit_json(records)
    else:
        for record in records:
            print(
                f"{record['runId']}\t{record['client']}\t{record['status']}\t{record['branch']}\t{record['checkoutRoot']}"
            )
    return 0


def enrich_status(record: dict[str, Any]) -> dict[str, Any]:
    """以当前 Git 事实补充运行记录状态，不修改 Registry 或 checkout。"""
    worktree = Path(record['checkoutRoot'])
    enriched = dict(record)
    checks: dict[str, Any] = {'worktreeExists': worktree.exists()}
    if worktree.exists():
        facts, identity_errors = validate_checkout_record(worktree, record)
        checks['checkoutIdentityMatches'] = not identity_errors
        checks['checkoutIdentityErrors'] = identity_errors
        checks['observedBranch'] = facts['branch']
        checks['detached'] = facts['detached']
        checks['baseCommitExists'] = facts['baseCommitExists']
        checks['baseIsAncestorOfHead'] = facts['baseIsAncestorOfHead']
        checks['dirty'] = bool(git(worktree, 'status', '--porcelain').stdout.strip())
    enriched['checks'] = checks
    return enriched


def cmd_status(args: argparse.Namespace) -> int:
    """持锁读取指定 run，随后输出包含实时 checkout 检查的状态。"""
    repo = repo_root_from_arg(args.repo_root)
    registry = Registry(repo)
    with registry.locked():
        record = registry.load_run(args.run_id)
    emit_json(enrich_status(record))
    return 0


def doctor_record(record: dict[str, Any]) -> list[str]:
    """验证单条运行记录和 checkout 身份，汇总所有可操作错误而不自动修复。"""
    errors: list[str] = []
    try:
        validate_run_record(record)
    except PrimarySessionValidationError as exc:
        errors.append(str(exc))
        return errors
    worktree = Path(record['checkoutRoot'])
    if not worktree.exists():
        errors.append('worktree root does not exist')
        return errors
    facts, identity_errors = validate_checkout_record(worktree, record)
    errors.extend(identity_errors)
    if record.get('baseCommit') and (not facts['baseCommitExists']):
        errors.append('base commit does not exist in checkout repository')
    return errors


def runtime_capability(record: dict[str, Any], errors: list[str]) -> str:
    """根据验证错误和 writer 状态投影只读、可写或 blocked 能力。"""
    if errors:
        return 'blocked'
    if record.get('status') in ACTIVE_WRITER_STATUSES:
        return 'writable-ready'
    if record.get('status') != 'BLOCKED':
        return 'read-only-ready'
    return 'blocked'


def cmd_doctor(args: argparse.Namespace) -> int:
    """检查选定或全部运行的身份与 writer 冲突，以聚合能力决定退出码。"""
    repo = repo_root_from_arg(args.repo_root)
    registry = Registry(repo)
    with registry.locked():
        records = [registry.load_run(args.run_id)] if args.run_id else registry.all_runs()
        collisions = validate_run_collisions(records) if records else []
    if not records:
        emit_json({'capability': 'read-only-ready', 'checkedRuns': [], 'status': 'read-only-ready'})
        return 0
    errors = [f'{c.kind}: {c.message}' for c in collisions]
    run_errors: dict[str, list[str]] = {}
    capabilities: dict[str, str] = {}
    collision_run_ids = {c.first_run_id for c in collisions} | {c.second_run_id for c in collisions}
    for record in records:
        record_errors = doctor_record(record)
        if str(record.get('runId')) in collision_run_ids:
            record_errors.append('writer lease collision detected')
        run_id = str(record['runId'])
        run_errors[run_id] = record_errors
        capabilities[run_id] = runtime_capability(record, record_errors)
        errors.extend(f'{run_id}: {msg}' for msg in record_errors)
    if errors:
        emit_json(
            {
                'status': 'blocked',
                'capability': 'blocked',
                'capabilities': capabilities,
                'errors': errors,
            }
        )
        return 2
    aggregate = (
        'writable-ready'
        if any(value == 'writable-ready' for value in capabilities.values())
        else 'read-only-ready'
    )
    emit_json(
        {
            'status': aggregate,
            'capability': aggregate,
            'capabilities': capabilities,
            'checkedRuns': [r['runId'] for r in records],
        }
    )
    return 0


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
    """在 Registry 锁内对照 gated 与当前 Git 指纹，持久化新鲜或失败的 Stop 回执。"""
    registry = Registry(repo_root)
    with registry.locked():
        latest = registry.load_run(run_id)
        try:
            current_facts = _collect_git_facts(latest)
            evidence_error = ''
        except GitEvidenceError as exc:
            evidence_error = str(exc)
            current_facts = {'queryErrors': [evidence_error], 'gitFactErrors': [evidence_error]}
        facts = dict(validated_facts)
        pass_requested = stop_exit == 0 and summary_status == 'PASS'
        expected_fingerprint = str(facts.get('checkoutFingerprint') or '')
        current_fingerprint = str(current_facts.get('checkoutFingerprint') or '')
        if pass_requested and (not evidence_error):
            if not expected_fingerprint:
                evidence_error = 'Stop validation evidence has no checkout fingerprint'
            elif expected_fingerprint != current_fingerprint:
                evidence_error = 'checkout Git snapshot changed after required gates'
            elif str(facts.get('headCommit') or '') != str(current_facts.get('headCommit') or ''):
                evidence_error = 'checkout HEAD changed after required gates'
        passed = pass_requested and (not evidence_error)
        if handoff_on_failure:
            failure_status = 'HANDOFF_REQUIRED'
        elif retryable_failure:
            failure_status = (
                _writer_status(latest)
                if latest.get('status') in ACTIVE_WRITER_STATUSES
                and isinstance(latest.get('writerLease'), dict)
                and latest.get('writerLease')
                else 'READ_ONLY_READY'
            )
        else:
            failure_status = 'BLOCKED'
        final_status = 'VALIDATED' if passed else failure_status
        receipt_facts = facts if passed else current_facts
        head = str(receipt_facts.get('headCommit') or latest.get('headCommit') or '')
        target_commit = str((facts if pass_requested else receipt_facts).get('targetHead') or '')
        fingerprint = expected_fingerprint if pass_requested else current_fingerprint
        checkout_content_fingerprint = str(receipt_facts.get('checkoutContentFingerprint') or '')
        primary_fingerprint = str(receipt_facts.get('primaryFingerprint') or '')
        result_key = hashlib.sha256(
            json.dumps(
                {
                    'runId': run_id,
                    'stopExit': stop_exit,
                    'summaryStatus': summary_status,
                    'headCommit': head,
                    'targetCommit': target_commit,
                    'checkoutFingerprint': fingerprint,
                    'checkoutContentFingerprint': checkout_content_fingerprint,
                    'primaryFingerprint': primary_fingerprint,
                    'evidenceError': evidence_error,
                    'retryableFailure': retryable_failure,
                },
                sort_keys=True,
            ).encode('utf-8')
        ).hexdigest()
        if latest.get('stopResultKey') == result_key and latest.get('status') == final_status:
            stored_facts = latest.get('stopGitFacts')
            return (latest, stored_facts if isinstance(stored_facts, dict) else receipt_facts)
        if latest.get('status') != 'VALIDATING':
            _set_run_status(latest, 'VALIDATING')
        _set_run_status(latest, final_status)
        latest['headCommit'] = head
        latest['stopExitCode'] = stop_exit
        timestamp = now_utc()
        latest['stopValidation'] = {
            'status': 'PASS' if passed else 'FAIL',
            'summaryStatus': summary_status,
            'fresh': passed,
            'validatedAt': timestamp,
            'headCommit': head,
            'targetCommit': target_commit,
            'checkoutFingerprint': fingerprint,
            'checkoutContentFingerprint': checkout_content_fingerprint,
            'primaryFingerprint': primary_fingerprint,
            'evidenceError': evidence_error,
            'candidateTree': str(receipt_facts.get('candidateTree') or ''),
            'gateReceiptPaths': list(receipt_facts.get('gateReceiptPaths') or []),
            'gateArtifactPath': str(receipt_facts.get('gateArtifactPath') or ''),
            'gateReused': bool(receipt_facts.get('gateReused')),
        }
        latest['stopGitFacts'] = receipt_facts
        latest['stopResultKey'] = result_key
        latest.pop('validationStaleAt', None)
        latest.pop('validationStaleReason', None)
        latest['updatedAt'] = timestamp
        outcome_event = (
            'STOP_VALIDATED'
            if passed
            else 'STOP_HANDOFF_REQUIRED'
            if final_status == 'HANDOFF_REQUIRED'
            else 'STOP_RETRYABLE_BLOCKED'
            if retryable_failure
            else 'STOP_BLOCKED'
        )
        _append_run_audit(
            registry,
            latest,
            {
                'event': outcome_event,
                'runId': latest['runId'],
                'sessionId': latest['sessionId'],
                'worktreeId': latest['worktreeId'],
                'headCommit': head,
                'targetCommit': target_commit,
                'stopExitCode': stop_exit,
                'evidenceError': evidence_error,
                'at': timestamp,
            },
        )
        registry.save_run(latest)
        return (latest, receipt_facts)


def cmd_stop(args: argparse.Namespace) -> int:
    """先标记运行进入 VALIDATING，再调用唯一 Stop pipeline 并输出最终回执事实。"""
    repo = repo_root_from_arg(args.repo_root)
    registry = Registry(repo)
    with registry.locked():
        record = registry.load_run(args.run_id)
        if record.get('status') == 'BLOCKED':
            _append_run_audit(
                registry,
                record,
                {
                    'event': 'BLOCKED_RUN_RETRY_REQUESTED',
                    'runId': record['runId'],
                    'sessionId': record['sessionId'],
                    'worktreeId': record['worktreeId'],
                    'at': now_utc(),
                },
            )
        record['stopRequestedAt'] = now_utc()
        _set_run_status(record, 'VALIDATING')
        record['updatedAt'] = now_utc()
        registry.save_run(record)
    from scripts.agent_runtime.stop.pipeline import run_stop

    payload = {
        'cwd': record['checkoutRoot'],
        'session_id': record.get('sessionId', ''),
        'sessionId': record.get('sessionId', ''),
        'run_id': record['runId'],
        'runId': record['runId'],
        'task_id': record['taskId'],
        'taskId': record['taskId'],
        'worktree_id': record['worktreeId'],
        'worktreeId': record['worktreeId'],
        'agent_client': record['client'],
        'client': record['client'],
        'completionCandidate': bool(getattr(args, 'candidate_mode', False)),
    }
    stop_exit = run_stop(
        str(record['client']),
        payload,
        handoff_on_failure=bool(getattr(args, 'handoff_on_failure', False)),
        adapter_mode='cli',
    )
    with registry.locked():
        latest = registry.load_run(args.run_id)
    facts = latest.get('stopGitFacts')
    if not isinstance(facts, dict):
        try:
            facts = _collect_git_facts(latest)
        except GitEvidenceError as exc:
            facts = {'queryErrors': [str(exc)], 'gitFactErrors': [str(exc)]}
    status = latest['status']
    emit_json(
        {
            'status': status,
            'runId': args.run_id,
            'stopExitCode': stop_exit,
            'killedProcess': False,
            'gitFacts': facts,
        }
    )
    return 0 if status == 'VALIDATED' else 2


def cmd_handoff(args: argparse.Namespace) -> int:
    """基于当前 Git 事实、doctor 错误和作用域冲突生成只读 handoff 报告。"""
    repo = repo_root_from_arg(args.repo_root)
    registry = Registry(repo)
    with registry.locked():
        record = registry.load_run(args.run_id)
        other_records = [
            item for item in registry.all_runs() if item.get('runId') != record.get('runId')
        ]
    facts = _collect_git_facts(record)
    blocking_failures = doctor_record(record)
    scope_overlaps = [
        f'{collision.kind}: {collision.message}'
        for collision in validate_run_collisions([record, *other_records])
        if record['runId'] in {collision.first_run_id, collision.second_run_id}
    ]
    report = build_handoff_report(
        registry,
        record,
        facts,
        scope_overlaps=scope_overlaps,
        blocking_failures=blocking_failures,
    )
    emit_json(report)
    return 0


def _cleanup_evidence_paths(
    registry: Registry, record: Mapping[str, Any]
) -> list[tuple[Path, Path]]:
    """从已验证运行身份推导精确证据路径和允许根，禁止通配清理。"""
    validate_run_record(dict(record))
    run_id = _validate_identifier(str(record.get('runId') or ''), 'run id')
    client = _validate_identifier(str(record.get('client') or ''), 'client')
    session_id = _validate_identifier(str(record.get('sessionId') or ''), 'session id')
    if record.get('repoKey') != registry.repo_key:
        raise SessionctlError('cleanup run does not belong to this Registry')
    checkout = resolve_checkout_root(Path(str(record.get('checkoutRoot') or '')))
    _, identity_errors = validate_checkout_record(checkout, dict(record))
    if identity_errors:
        raise SessionctlError('cleanup checkout identity mismatch: ' + '; '.join(identity_errors))
    runtime = registry.root.resolve()
    return [
        (checkout / 'tmp' / 'agent_logs' / client / session_id / 'runs' / run_id, checkout),
        (checkout / 'tmp' / 'quality' / client / session_id / 'runs' / run_id, checkout),
        (registry.runs_dir / run_id, runtime),
        (runtime / 'integration' / f'{run_id}.json', runtime),
        (runtime / 'integration' / f'{run_id}.handoff.json', runtime),
    ]


def _remove_exact_run_evidence(path: Path, *, allowed_root: Path) -> bool:
    """逐级拒绝符号链接、异主和越界路径后，仅删除指定 run 证据。"""
    root = Path(os.path.abspath(allowed_root))
    candidate = Path(os.path.abspath(path))
    try:
        relative = candidate.relative_to(root)
    except ValueError as exc:
        raise SessionctlError(f'cleanup evidence escapes allowed root: {candidate}') from exc
    if not relative.parts:
        raise SessionctlError('cleanup refuses to remove an evidence root')
    cursor = root
    for component in relative.parts[:-1]:
        cursor /= component
        try:
            metadata = cursor.lstat()
        except FileNotFoundError:
            return False
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise SessionctlError(f'unsafe cleanup evidence ancestor: {cursor}')
    try:
        metadata = candidate.lstat()
    except FileNotFoundError:
        return False
    if stat.S_ISLNK(metadata.st_mode):
        raise SessionctlError(f'refusing symlink cleanup evidence: {candidate}')
    if hasattr(os, 'geteuid') and metadata.st_uid != os.geteuid():
        raise SessionctlError(f'cleanup evidence is not owned by current user: {candidate}')
    if stat.S_ISDIR(metadata.st_mode):
        shutil.rmtree(candidate)
    elif stat.S_ISREG(metadata.st_mode):
        candidate.unlink()
    else:
        raise SessionctlError(f'refusing special cleanup evidence path: {candidate}')
    return True


def cmd_cleanup(args: argparse.Namespace) -> int:
    """默认只预览证据清理；执行模式先释放 lease，再复核身份并删除精确记录。"""
    repo = repo_root_from_arg(args.repo_root)
    registry = Registry(repo)
    with registry.locked():
        record = registry.load_run(args.run_id)
        if record.get('runId') != args.run_id:
            raise SessionctlError('cleanup run id does not match Registry record')
        evidence = _cleanup_evidence_paths(registry, record)
    evidence_actions = [
        {'path': str(path), 'exists': os.path.lexists(path)} for path, _ in evidence
    ]
    actions = {
        'releaseWriterLease': bool(record.get('writerLease')),
        'preserveCheckout': str(record['checkoutRoot']),
        'removeCheckout': False,
        'removeBranch': False,
        'removeRunRecord': str(registry._run_path(str(record['runId']))),
        'removeEvidence': evidence_actions,
        'dryRun': not args.execute,
    }
    if not args.execute:
        emit_json({'status': 'dry-run', 'runId': args.run_id, 'actions': actions})
        return 0
    if record.get('writerLease'):
        from .lease import release_writer_lease

        release_writer_lease(registry, record, reason='cleanup')
    timestamp = now_utc()
    removed_evidence: list[str] = []
    with registry.locked():
        latest = registry.load_run(args.run_id)
        if latest.get('repoKey') != record.get('repoKey') or latest.get('worktreeId') != record.get(
            'worktreeId'
        ):
            raise SessionctlError('cleanup run identity changed before evidence removal')
        current_evidence = _cleanup_evidence_paths(registry, latest)
        for path, allowed_root in current_evidence:
            if _remove_exact_run_evidence(path, allowed_root=allowed_root):
                removed_evidence.append(str(path))
        event = {
            'event': 'RUN_CLEANUP_EVIDENCE_REMOVED',
            'runId': latest['runId'],
            'sessionId': latest['sessionId'],
            'worktreeId': latest['worktreeId'],
            'checkoutPreserved': True,
            'removedEvidence': removed_evidence,
            'at': timestamp,
        }
        registry.write_audit(event)
        registry.remove_run_record(
            args.run_id,
            expected_repo_key=str(latest['repoKey']),
            expected_checkout_root=Path(str(latest['checkoutRoot'])),
        )
    actions['dryRun'] = False
    actions['removedEvidence'] = removed_evidence
    emit_json({'status': 'cleanup-complete', 'runId': args.run_id, 'actions': actions})
    return 0


def _checkout_fingerprint(facts: Mapping[str, Any]) -> str:
    fingerprint = str(facts.get('checkoutFingerprint') or '')
    if not fingerprint:
        snapshot = facts.get('checkoutSnapshot')
        if isinstance(snapshot, Mapping):
            fingerprint = str(snapshot.get('fingerprint') or '')
    if not fingerprint:
        raise GitEvidenceError('Git evidence has no content-sensitive checkout fingerprint')
    return fingerprint


def _collect_git_facts(record: Mapping[str, Any]) -> dict[str, Any]:
    facts = collect_git_evidence(Path(str(record.get('checkoutRoot') or '')), dict(record))
    checkout_status = facts['checkoutStatus']
    facts['checkout'] = {
        'checkoutKind': facts['checkoutKind'],
        'checkoutCreator': facts['checkoutCreator'],
        'branch': checkout_status['branch'],
        'detached': checkout_status['detached'],
        'gitCommonDir': record.get('gitCommonDir', ''),
    }
    facts['gitFactErrors'] = list(facts.get('queryErrors', []))
    facts['checkoutFingerprint'] = _checkout_fingerprint(facts)
    return facts
