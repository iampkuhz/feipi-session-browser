"""三平台 Hook 的唯一 Python CLI 与事件分发入口。

共享 dispatcher 只转发 payload 到本模块；本模块编排 adapter、Registry、
策略与 evidence，但不执行 Stop pipeline 或 Gate executor。

不负责平台 Hook 配置；由共享 dispatcher 或 Stop runtime 调用。"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

from scripts.agent_runtime.context import HookContext, read_stdin_json
from scripts.agent_runtime.events import evidence as changed_file_utils
from scripts.agent_runtime.events.adapter import HookAdapterError, build_bootstrap_request
from scripts.agent_runtime.events.evidence import (
    acquire_bash_mutation_lock,
    post_bash_isolation_failure,
    read_bash_mutation_lock_info,
    record_hook_event,
    record_post_bash,
    record_post_write,
    record_pre_bash_snapshot,
    release_bash_mutation_lock,
)
from scripts.agent_runtime.events.output import HookResult, emit
from scripts.agent_runtime.events.policy.bash import (
    evaluate_command,
    is_read_only_command,
    primary_write_reason,
)
from scripts.agent_runtime.events.policy.config import record_config_change
from scripts.agent_runtime.events.policy.file import (
    evaluate_write_path,
    pre_write_payload_block_reason,
)
from scripts.agent_runtime.events.policy.session import handle_session_start
from scripts.agent_runtime.identity import identity_from_hook_context
from scripts.agent_runtime.paths import RepoPaths, build_paths, ensure_runtime_dirs
from scripts.agent_runtime.policy import is_protected_path
from scripts.agent_runtime.registry import (
    ACTIVE_WRITER_STATUSES,
    Registry,
    SessionctlError,
    WriterLeaseConflictError,
    WriterLeaseFencedError,
    acquire_writer_lease,
    bootstrap_session,
    classify_tool_call,
    heartbeat_writer_lease,
    mark_read_only_ready,
    release_writer_lease,
    resolve_bound_run_record,
    validate_run_write_authorization,
)
from scripts.agent_runtime.session.completion import (
    START_ENFORCED,
    START_NOT_ENFORCED,
    activate_first_mutation,
    begin_change,
    completion_requirement,
    require_mutation_baseline,
)
from scripts.gates.planner import classify_path


# 解析 Bash 命令开头的简单 cd 路径。
def _leading_cd_path(command: str) -> str:
    """参数：
        command: 待执行的 Bash 命令。

    返回：
        命令以简单 cd 开头时返回目标路径，否则返回空字符串。
    """
    first = command.strip()
    for separator in ('&&', ';'):
        if separator in first:
            first = first.split(separator, 1)[0].strip()
            break
    if not first.startswith('cd '):
        return ''
    try:
        tokens = shlex.split(first)
    except ValueError:
        return ''
    if len(tokens) == 2 and tokens[0] == 'cd':
        return tokens[1]
    return ''


# 从 hook payload 推导本次工具实际检出根目录。
def _context_repo_hint(ctx: HookContext) -> str:
    """参数：
        ctx: 当前 hook payload。

    返回：
        可用于 git root detection 的路径提示。
    """
    if ctx.event_name == 'pre-bash':
        cd_path = _leading_cd_path(ctx.command)
        if cd_path:
            return cd_path
    if ctx.cwd:
        return ctx.cwd
    for candidate in ctx.candidate_paths:
        path = Path(candidate)
        if path.is_absolute():
            return str(path.parent)
    return ''


# 为当前 hook context 选择实际 RepoPaths。
def _paths_for_context(paths: RepoPaths, ctx: HookContext) -> RepoPaths:
    """参数：
        paths: 默认仓库路径对象。
        ctx: 当前 hook payload。

    返回：
        使用实际 cwd 或绝对目标路径解析后的 repository paths。
    """
    if paths.identity.has_run:
        try:
            record = resolve_bound_run_record(
                paths.repo_root,
                paths.identity.client,
                paths.identity.raw_session_id,
                paths.identity.raw_run_id,
            )
        except Exception:
            record = None
        if record and record.get('checkoutRoot'):
            hint = _context_repo_hint(ctx)
            if hint:
                hinted_root = build_paths(repo_root=hint, identity=paths.identity)
                if hinted_root.repo_root.resolve() != Path(str(record['checkoutRoot'])).resolve():
                    return hinted_root
            return build_paths(repo_root=str(record['checkoutRoot']), identity=paths.identity)
    hint = _context_repo_hint(ctx)
    if not hint:
        return paths
    return build_paths(repo_root=hint, identity=paths.identity)


# 将任一平台的生命周期 payload 交给统一 bootstrap service。
def _bootstrap_hook_session(
    ctx: HookContext,
    *,
    wrapper_client: str = '',
) -> dict | None:
    """参数：
        ctx: 当前 Hook 输入。
        wrapper_client: dispatcher 声明的客户端。

    返回：
        Registry run record；事件不触发 bootstrap 时返回 None。
    """

    request = build_bootstrap_request(ctx, wrapper_client=wrapper_client)
    if request is None:
        return None
    record = bootstrap_session(
        client=request.client,
        session_id=request.session_id,
        cwd=Path(request.cwd),
        hook_event=request.hook_event,
        checkout_creator=request.checkout_creator,
        payload_hints=request.payload_hints,
        env_hints=os.environ,
        parent_run_id=request.parent_run_id,
    )
    if request.hook_event == 'SessionStart' and not request.parent_run_id:
        capability = (
            START_NOT_ENFORCED if request.adapter.surface == 'codex-app' else START_ENFORCED
        )
        record = begin_change(
            Path(request.cwd),
            str(record['runId']),
            activation_source=f'hook:{request.adapter.surface}:SessionStart',
            capability=capability,
        )
    return record


# 从 Registry 权威解析当前 Session run。
def _bound_record(paths: RepoPaths, ctx: HookContext) -> dict | None:
    """参数：
        paths: 当前仓库与 Runtime 路径。
        ctx: 当前 Hook 输入。

    返回：
        已绑定的 run record；未绑定时返回 None。
    """

    return resolve_bound_run_record(
        paths.repo_root,
        paths.identity.client,
        ctx.session_id or paths.identity.raw_session_id,
        ctx.run_id or paths.identity.raw_run_id,
    )


# 将 writer lease 异常记录为可机读的阻断结果。
def _lease_block_result(
    paths: RepoPaths,
    ctx: HookContext,
    *,
    operation: str,
    error: Exception,
) -> HookResult:
    """参数：
        paths: 当前仓库与 Runtime 路径。
        ctx: 当前 Hook 输入。
        operation: 失败的 lease 操作。
        error: 原始异常。

    返回：
        退出码为 2 的 Hook 阻断结果。
    """
    reason = f'checkout writer lease {operation} BLOCK: {error}'
    record_hook_event(
        paths,
        ctx,
        status='BLOCK',
        extra={
            'reason': reason,
            'writerLease': {
                'operation': operation,
                'errorType': type(error).__name__,
                'runId': paths.identity.raw_run_id,
            },
        },
    )
    return HookResult(status='BLOCK', exit_code=2, message=reason)


# 推进 reader 状态或对已持有的 lease 发送 heartbeat。
def _observe_writer_lease(
    paths: RepoPaths,
    ctx: HookContext,
    *,
    fail_closed: bool,
) -> HookResult | None:
    """参数：
        paths: 当前仓库与 Runtime 路径。
        ctx: 当前 Hook 输入。
        fail_closed: lease 异常时是否立即阻断。

    返回：
        需要阻断时返回 HookResult；否则返回 None。
    """

    record = _bound_record(paths, ctx)
    if not record:
        return None
    try:
        registry = Registry(paths.repo_root)
        if record.get('status') in ACTIVE_WRITER_STATUSES:
            heartbeat_writer_lease(registry, record)
        elif record.get('status') == 'BOOTSTRAPPED':
            mark_read_only_ready(registry, record)
    except (SessionctlError, OSError, ValueError) as exc:
        if fail_closed:
            return _lease_block_result(paths, ctx, operation='heartbeat', error=exc)
        record_hook_event(
            paths,
            ctx,
            status='LEASE_HEARTBEAT_BLOCKED',
            extra={'reason': str(exc), 'errorType': type(exc).__name__},
        )
    return None


# 在 SessionEnd 精确释放当前主 Session 的 writer lease。
def _release_session_writer_lease(paths: RepoPaths, ctx: HookContext) -> HookResult | None:
    """参数：
        paths: 当前仓库与 Runtime 路径。
        ctx: 当前 Hook 输入。

    返回：
        释放失败时的 Hook 阻断结果；无 lease 或释放成功时返回 None。
    """

    record = _bound_record(paths, ctx)
    if not record or not record.get('writerLease'):
        return None
    try:
        release_writer_lease(
            Registry(paths.repo_root),
            record,
            reason='SessionEnd',
            inherited=bool(ctx.agent_id),
        )
    except (SessionctlError, OSError, ValueError) as exc:
        return _lease_block_result(paths, ctx, operation='release', error=exc)
    return None


# 校验运行级写入授权并按需阻断。
def _run_mutation_block(
    paths: RepoPaths, ctx: HookContext, candidate_paths: list[str] | None = None
) -> HookResult | None:
    """参数：
        paths: 当前仓库路径上下文。
        ctx: 当前 hook 输入上下文。
        candidate_paths: 候选写入路径列表。

    返回：
        需要阻断时返回 HookResult；允许继续时返回 None。
    """
    if not paths.identity.has_run:
        reason = (
            f'unbound {paths.identity.client} session cannot mutate; automatic bootstrap '
            'requires a valid session_id and cwd payload'
        )
        record_hook_event(paths, ctx, status='BLOCK', extra={'reason': reason})
        return HookResult(status='BLOCK', exit_code=2, message=reason)
    record = _bound_record(paths, ctx)
    if not record:
        reason = 'Registry has no run bound to this Session and physical checkout'
        return _lease_block_result(
            paths,
            ctx,
            operation='acquire',
            error=SessionctlError(reason),
        )
    registry = Registry(paths.repo_root)
    try:
        with registry.locked():
            record = registry.load_run(str(record['runId']))
            require_mutation_baseline(paths.repo_root, record)
            activate_first_mutation(registry, record)
    except (SessionctlError, OSError, ValueError) as exc:
        return _lease_block_result(paths, ctx, operation='begin-change', error=exc)
    try:
        acquire_writer_lease(registry, record)
    except (
        WriterLeaseConflictError,
        WriterLeaseFencedError,
        SessionctlError,
        OSError,
        ValueError,
    ) as exc:
        return _lease_block_result(paths, ctx, operation='acquire', error=exc)
    allowed, errors, record = validate_run_write_authorization(
        paths.repo_root,
        client=paths.identity.client,
        session_id=ctx.session_id or paths.identity.raw_session_id,
        run_id=paths.identity.raw_run_id,
        change_id=paths.identity.change_id,
        candidate_paths=candidate_paths or [],
    )
    if allowed:
        return None
    reason = 'run-scoped writable ownership BLOCK: ' + '; '.join(errors)
    record_hook_event(
        paths,
        ctx,
        status='BLOCK',
        extra={
            'reason': reason,
            'runOwnership': {'runId': paths.identity.raw_run_id, 'errors': errors},
        },
    )
    return HookResult(status='BLOCK', exit_code=2, message=reason)


def _controlled_primary_command(ctx: HookContext, record: dict) -> bool:
    """只认可当前 run 的 finalize 或完整受控收口入口，拒绝 shell 组合命令。"""
    if any(operator in ctx.command for operator in ('&&', '||', ';', '|', '>', '<', '`', '$(')):
        return False
    try:
        tokens = shlex.split(ctx.command)
    except ValueError:
        return False
    script_index = next(
        (index for index, token in enumerate(tokens) if token.endswith('.py')),
        -1,
    )
    if script_index < 0:
        return False
    script = Path(tokens[script_index]).as_posix()
    try:
        run_index = tokens.index('--run-id', script_index + 1)
        requested_run = tokens[run_index + 1]
    except (ValueError, IndexError):
        return False
    if requested_run != str(record.get('runId') or ''):
        return False
    if script.endswith('scripts/harness/complete_change.py'):
        # 该公开入口内部仍必须依次取得两次 Stop receipt 后才能调用 finalize。
        return True
    if not script.endswith('scripts/harness/sessionctl.py'):
        return False
    if 'finalize' not in tokens[script_index + 1 :]:
        return False
    validation = record.get('stopValidation')
    return bool(
        record.get('status') == 'VALIDATED'
        and record.get('stopExitCode') == 0
        and isinstance(validation, dict)
        and validation.get('status') == 'PASS'
        and validation.get('fresh') is True
    )


def _primary_isolation_policy(
    paths: RepoPaths,
    ctx: HookContext,
) -> tuple[str, Path | None, bool]:
    """按 Registry 的 Git 身份检查 primary 写入，并返回指纹审计上下文。"""
    record = _bound_record(paths, ctx)
    if not record:
        return '', None, False
    checkout_raw = str(record.get('checkoutRoot') or '')
    primary_raw = str(record.get('primaryRepoRoot') or '')
    if not checkout_raw or not primary_raw:
        return 'run record 缺少 checkout/primary Git 身份；禁止 mutation。', None, False
    checkout = Path(checkout_raw)
    primary = Path(primary_raw)
    try:
        if checkout.resolve(strict=True) == primary.resolve(strict=True):
            return '', None, False
    except OSError:
        return '无法复核 checkout/primary Git 身份；禁止 mutation。', None, False
    controlled = _controlled_primary_command(ctx, record)
    reason = primary_write_reason(
        ctx.command,
        cwd=Path(ctx.cwd or paths.repo_root),
        checkout_root=checkout,
        primary_root=primary,
    )
    return ('' if reason and controlled else reason), primary, controlled


# 分发 PreToolUse Bash 事件。
def handle_pre_bash(paths: RepoPaths, ctx: HookContext) -> HookResult:
    """分发 PreToolUse Bash 事件。"""
    if ctx.parse_error:
        reason = f'pre-bash hook payload JSON 解析失败；fail-closed: {ctx.parse_error}'
        record_hook_event(paths, ctx, status='BLOCK', extra={'reason': reason})
        return HookResult(status='BLOCK', exit_code=2, message=reason)

    paths = _paths_for_context(paths, ctx)
    decision = evaluate_command(ctx.command)
    snapshot_written = False
    mutation_tracking = False
    primary_root: Path | None = None
    controlled_primary = False
    call_kind = classify_tool_call('Bash', ctx.tool_input)
    if decision.allowed:
        changed_file_utils.write_base_commit_if_missing(paths.repo_root, paths.base_commit)
        call_kind = (
            'validation'
            if call_kind == 'validation'
            else 'read-only'
            if is_read_only_command(ctx.command)
            else 'mutation'
        )
        mutation_tracking = call_kind != 'read-only'
        if mutation_tracking and not ctx.session_id:
            reason = (
                'mutating Bash 缺少 session id；fail-closed，避免 mutation attribution 静默 PASS。'
            )
            record_hook_event(paths, ctx, status='BLOCK', extra={'reason': reason})
            return HookResult(status='BLOCK', exit_code=2, message=reason)
        if mutation_tracking:
            primary_reason, primary_root, controlled_primary = _primary_isolation_policy(paths, ctx)
            if primary_reason:
                record_hook_event(
                    paths,
                    ctx,
                    status='BLOCK',
                    extra={'reason': primary_reason, 'primaryIsolation': 'pre-bash'},
                )
                return HookResult(status='BLOCK', exit_code=2, message=primary_reason)
            if not controlled_primary:
                run_block = _run_mutation_block(paths, ctx)
                if run_block is not None:
                    return run_block
        if mutation_tracking and not acquire_bash_mutation_lock(paths, ctx):
            reason = '另一个 Bash mutation attribution 正在运行；请稍后重试该命令。'
            lock_info = read_bash_mutation_lock_info(paths) or {}
            busy = {
                'state': 'busy',
                'owner': lock_info.get('owner'),
                'sessionId': lock_info.get('sessionId'),
                'agentId': lock_info.get('agentId'),
                'age_seconds': lock_info.get('age_seconds'),
            }
            record_hook_event(
                paths,
                ctx,
                status='BLOCK',
                extra={'reason': reason, 'bashMutationLock': busy},
            )
            return HookResult(status='BLOCK', exit_code=2, message=reason)
        if mutation_tracking:
            snapshot_written = record_pre_bash_snapshot(
                paths,
                ctx,
                primary_root=primary_root,
                controlled_primary_write=controlled_primary,
            )
            if not snapshot_written:
                release_bash_mutation_lock(paths, ctx)
                reason = '无法记录 checkout/primary mutation 前指纹；fail-closed。'
                record_hook_event(paths, ctx, status='BLOCK', extra={'reason': reason})
                return HookResult(status='BLOCK', exit_code=2, message=reason)
        else:
            lease_block = _observe_writer_lease(paths, ctx, fail_closed=False)
            if lease_block is not None:
                return lease_block
    record_hook_event(
        paths,
        ctx,
        status=decision.status,
        extra={
            'reason': decision.reason,
            'warnings': decision.warnings,
            'bashSnapshot': snapshot_written,
            'bashMutationTracking': mutation_tracking,
            'toolCallKind': call_kind,
            'worktree': {'authority': 'run-record'} if mutation_tracking else None,
        },
    )
    if not decision.allowed:
        return HookResult(status='BLOCK', exit_code=2, message=decision.reason)
    return HookResult(status='PASS', warnings=decision.warnings)


# 分发 PreToolUse 写入事件。
def handle_pre_write(paths: RepoPaths, ctx: HookContext) -> HookResult:
    """分发 PreToolUse 写入事件。"""
    warnings: list[str] = []
    paths = _paths_for_context(paths, ctx)
    changed_file_utils.write_base_commit_if_missing(paths.repo_root, paths.base_commit)
    payload_reason = pre_write_payload_block_reason(ctx, paths.repo_root)
    if payload_reason:
        reason = payload_reason
        record_hook_event(paths, ctx, status='BLOCK', extra={'reason': reason})
        return HookResult(status='BLOCK', exit_code=2, message=reason)
    for path in ctx.candidate_paths:
        if is_protected_path(path, paths.repo_root):
            guard = subprocess.run(
                [
                    sys.executable,
                    str(paths.repo_root / 'scripts' / 'hooks' / 'guard_openspec_change.py'),
                    '--path',
                    path,
                    '--run-id',
                    paths.identity.raw_run_id,
                    '--session-id',
                    ctx.session_id or paths.identity.raw_session_id,
                    '--client',
                    paths.identity.client,
                ],
                cwd=paths.repo_root,
                text=True,
                capture_output=True,
                check=False,
            )
            if guard.returncode != 0:
                reason = (guard.stderr or guard.stdout).strip() or 'OpenSpec guard BLOCK'
                record_hook_event(
                    paths, ctx, status='BLOCK', extra={'reason': reason, 'file': path}
                )
                return HookResult(status='BLOCK', exit_code=2, message=reason)
        decision = evaluate_write_path(path, paths.repo_root)
        warnings.extend(decision.warnings)
        if not decision.allowed:
            record_hook_event(
                paths, ctx, status='BLOCK', extra={'reason': decision.reason, 'file': path}
            )
            return HookResult(status='BLOCK', exit_code=2, message=decision.reason)
    run_block = _run_mutation_block(paths, ctx, ctx.candidate_paths)
    if run_block is not None:
        return run_block
    record_hook_event(
        paths, ctx, status='PASS', extra={'candidatePathCount': len(ctx.candidate_paths)}
    )
    return HookResult(status='PASS', warnings=warnings)


# 分发 PostToolUse 写入事件。
def handle_post_write(paths: RepoPaths, ctx: HookContext) -> HookResult:
    """分发 PostToolUse 写入事件。"""
    paths = _paths_for_context(paths, ctx)
    records = record_post_write(paths, ctx)
    lease_block = _observe_writer_lease(paths, ctx, fail_closed=True)
    if lease_block is not None:
        return lease_block
    for raw_path in ctx.candidate_paths:
        candidate = Path(raw_path)
        if not candidate.is_absolute():
            candidate = paths.repo_root / candidate
        if str(candidate).endswith(('/.claude/settings.local.json', '/.mcp.json')):
            reason = f'personal local config was modified: {raw_path}'
            record_hook_event(
                paths, ctx, status='BLOCK', extra={'reason': reason, 'file': raw_path}
            )
            return HookResult(status='BLOCK', exit_code=2, message=reason)
        if candidate.suffix == '.sh' and candidate.exists():
            proc = subprocess.run(
                ['bash', '-n', str(candidate)],
                text=True,
                capture_output=True,
                check=False,
            )
            if proc.returncode != 0:
                reason = f'shell syntax check failed: {raw_path}'
                record_hook_event(
                    paths, ctx, status='BLOCK', extra={'reason': reason, 'file': raw_path}
                )
                return HookResult(status='BLOCK', exit_code=2, message=reason)
        if candidate.suffix == '.json' and candidate.exists():
            proc = subprocess.run(
                [sys.executable, '-m', 'json.tool', str(candidate)],
                text=True,
                capture_output=True,
                check=False,
            )
            if proc.returncode != 0:
                reason = f'json syntax check failed: {raw_path}'
                record_hook_event(
                    paths, ctx, status='BLOCK', extra={'reason': reason, 'file': raw_path}
                )
                return HookResult(status='BLOCK', exit_code=2, message=reason)
    return HookResult(status='PASS', details={'changedFileCount': len(records)})


# 分发 PostToolUse Bash 事件。
def handle_post_bash(paths: RepoPaths, ctx: HookContext) -> HookResult:
    """分发 PostToolUse Bash 事件。"""
    paths = _paths_for_context(paths, ctx)
    records = record_post_bash(paths, ctx)
    isolation_failure = post_bash_isolation_failure(paths, ctx)
    if isolation_failure:
        return HookResult(status='BLOCK', exit_code=2, message=isolation_failure)
    lease_block = _observe_writer_lease(
        paths,
        ctx,
        fail_closed=not is_read_only_command(ctx.command),
    )
    if lease_block is not None:
        return lease_block
    return HookResult(status='PASS', details={'changedFileCount': len(records)})


# 分发默认 hook 事件。
def handle_default(paths: RepoPaths, ctx: HookContext, label: str) -> HookResult:
    """分发默认 hook 事件。"""
    normalized_label = label.lower()
    if normalized_label in {'stop', 'session-stop'} and ctx.empty_input:
        dirty = changed_file_utils.read_git_dirty_files(paths.repo_root)
        if dirty:
            reason = 'Stop hook stdin 为空且 git workspace 非 clean；fail-closed。'
            record_hook_event(
                paths, ctx, status='BLOCK', extra={'reason': reason, 'dirtyCount': len(dirty)}
            )
            return HookResult(status='BLOCK', exit_code=2, message=reason)
    if normalized_label in {'session-end', 'sessionend'}:
        record = _bound_record(paths, ctx)
        if record:
            required = completion_requirement(paths.repo_root, record)
            if required['status'] == 'COMMIT_REQUIRED':
                reason = f"COMMIT_REQUIRED: {required['recoveryCommand']}"
                record_hook_event(paths, ctx, status='BLOCK', extra=required)
                return HookResult(status='BLOCK', exit_code=2, message=reason)
        release_block = _release_session_writer_lease(paths, ctx)
        if release_block is not None:
            return release_block
    elif label in {
        'session-start',
        'subagent-start',
        'user-prompt-submit',
        'cwd-changed',
        'pre-tool-bootstrap',
    }:
        if label in {'session-start', 'subagent-start'}:
            handle_session_start(paths, ctx, label)
        else:
            record_hook_event(
                paths,
                ctx,
                status='BOOTSTRAP_CONFIRMED',
                extra={'source': label, 'runId': paths.identity.raw_run_id},
            )
        _observe_writer_lease(paths, ctx, fail_closed=False)
    elif label == 'config-change':
        record_config_change(paths, ctx)
        record_hook_event(paths, ctx, status='CONFIG')
    elif label == 'tool-failure' and ctx.tool_name == 'Bash':
        records = record_post_bash(paths, ctx)
        return HookResult(status='PASS', details={'changedFileCount': len(records)})
    else:
        record_hook_event(paths, ctx, status='OBSERVED')
    return HookResult(status='PASS')


def _run_self_test() -> None:
    """运行唯一 Hook CLI 的轻量烟测，不创建持久化 runtime evidence。"""

    ctx = read_stdin_json(
        'pre-bash',
        '{"tool_name":"Bash","tool_input":{"command":"pytest -q"}}',
    )
    assert ctx.command == 'pytest -q'
    assert (
        classify_path('docs/acceptance-contracts/features/DATA_PRESENTERS.md').quality_target
        == 'acceptance-contracts'
    )
    assert not evaluate_command('rm -rf /').allowed
    with tempfile.TemporaryDirectory() as directory:
        assert evaluate_write_path(
            'java/web/src/main/java/com/feipi/Foo.java', Path(directory)
        ).allowed


# 解析命令行参数并运行脚本入口。
def main(argv: list[str] | None = None) -> int:
    """解析命令行参数并运行脚本入口。"""
    argv = argv if argv is not None else sys.argv[1:]
    event_name = argv[0] if argv else 'unknown'

    # --self-test 不需要 stdin，必须在 read_stdin_json 之前分发，
    # 否则 sys.stdin.read() 会在没有管道输入时阻塞等待 EOF。
    if event_name == '--self-test':
        _run_self_test()
        print('scripts.agent_runtime.hook_entry self-test PASS')
        return 0

    ctx = read_stdin_json(event_name)
    wrapper_client = os.environ.get('FEIPI_AGENT_CLIENT', '')
    try:
        _bootstrap_hook_session(ctx, wrapper_client=wrapper_client)
    except (HookAdapterError, SessionctlError, OSError, ValueError) as exc:
        return emit(
            HookResult(
                status='BLOCK',
                exit_code=2,
                message=f'hook Session bootstrap BLOCK: {exc}',
            )
        )
    identity = identity_from_hook_context(ctx, agent_client=wrapper_client or None)
    paths = build_paths(repo_root=ctx.cwd or None, identity=identity)
    ensure_runtime_dirs(paths)

    if event_name == 'pre-bash':
        return emit(handle_pre_bash(paths, ctx))
    if event_name == 'pre-write':
        return emit(handle_pre_write(paths, ctx))
    if event_name == 'post-write':
        return emit(handle_post_write(paths, ctx))
    if event_name == 'post-bash':
        return emit(handle_post_bash(paths, ctx))

    return emit(handle_default(paths, ctx, event_name))


# 07. 模块执行
if __name__ == '__main__':
    raise SystemExit(main())
