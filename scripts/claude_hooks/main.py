"""提供 主流程 脚本能力。"""

from __future__ import annotations

import sys
import os
import shlex
import subprocess
from pathlib import Path

from .evidence import (
    acquire_bash_mutation_lock,
    read_bash_mutation_lock_info,
    record_hook_event,
    record_post_bash,
    record_post_write,
    record_pre_bash_snapshot,
)
from .hook_io import HookContext, read_stdin_json
from .paths import RepoPaths, build_paths, ensure_runtime_dirs, identity_from_hook_context
from .policy.bash_policy import evaluate_command, is_read_only_command
from .policy.config_policy import record_config_change
from .policy.file_policy import evaluate_write_path, pre_write_payload_block_reason
from .policy.session_context import handle_session_start
from .result import HookResult, emit
from .self_test import run_self_test
from scripts.quality import changed_files as changed_file_utils
from scripts.agent_runtime.policy import is_protected_path
from scripts.harness.primary_session import (
    load_run_record,
    validate_run_write_authorization,
)


# 维护 _is_deterministic_validation_command 函数行为。
def _is_deterministic_validation_command(command: str) -> bool:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    normalized = ' '.join(command.strip().split())
    while '=' in normalized.split(' ', 1)[0]:
        parts = normalized.split(' ', 1)
        if len(parts) == 1:
            return False
        normalized = parts[1]
    deterministic_exact = {
        'python scripts/quality/check_hook_payload_compat.py',
        'python3 scripts/quality/check_hook_payload_compat.py',
        'python -m pytest tests/test_hook_payload_compat.py',
        'python3 -m pytest tests/test_hook_payload_compat.py',
        'python scripts/quality/check_agent_runtime_worktree.py',
        'python3 scripts/quality/check_agent_runtime_worktree.py',
        'bash scripts/harness/doctor.sh',
    }
    if normalized in deterministic_exact:
        return True
    deterministic_prefixes = (
        'python scripts/openspec/validate_active_change.py ',
        'python3 scripts/openspec/validate_active_change.py ',
        'python scripts/quality/run_required_quality_gates.py ',
        'python3 scripts/quality/run_required_quality_gates.py ',
    )
    return any(normalized.startswith(prefix) for prefix in deterministic_prefixes)


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
            record = load_run_record(paths.repo_root, paths.identity.raw_run_id)
        except Exception:
            record = None
        if record and record.get('worktreeRoot'):
            hint = _context_repo_hint(ctx)
            if hint:
                hinted_root = build_paths(repo_root=hint, identity=paths.identity)
                if hinted_root.repo_root.resolve() != Path(str(record['worktreeRoot'])).resolve():
                    return hinted_root
            return build_paths(repo_root=str(record['worktreeRoot']), identity=paths.identity)
    hint = _context_repo_hint(ctx)
    if not hint:
        return paths
    return build_paths(repo_root=hint, identity=paths.identity)



# Codex/Qoder 首个安全 hook 可把启动器注入的运行标识绑定到真实会话。
def _maybe_lazy_bind_session(paths: RepoPaths, ctx: HookContext) -> None:
    """返回：
        无返回值；无法证明激活时后续写授权保持故障关闭。
    """
    if paths.identity.client not in {'codex', 'qoder'}:
        return
    run_id = ctx.run_id or os.environ.get('FEIPI_RUN_ID', '')
    session_id = ctx.session_id or os.environ.get('FEIPI_SESSION_ID', '')
    cwd = ctx.cwd or os.environ.get('FEIPI_HOOK_CWD', '') or str(paths.repo_root)
    if not run_id or not session_id:
        return
    try:
        proc = subprocess.run(
            [
                sys.executable,
                str(paths.repo_root / 'scripts' / 'harness' / 'sessionctl.py'),
                '--repo-root',
                str(paths.repo_root),
                'bind-session',
                '--run-id',
                run_id,
                '--session-id',
                session_id,
                '--client',
                paths.identity.client,
                '--cwd',
                cwd,
            ],
            cwd=paths.repo_root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )
    except Exception as exc:
        record_hook_event(paths, ctx, status='LAZY_BIND_BLOCKED', extra={'event': 'hook-activation', 'reason': str(exc)})
        return
    if proc.returncode == 0:
        record_hook_event(paths, ctx, status='LAZY_BIND', extra={'event': 'hook-activation', 'source': 'first-safe-hook'})
    else:
        reason = (proc.stderr or proc.stdout).strip() or 'sessionctl bind-session failed'
        record_hook_event(paths, ctx, status='LAZY_BIND_BLOCKED', extra={'event': 'hook-activation', 'reason': reason})



# 判断是否显式启用 legacy 单写兼容。
# 校验运行级写入授权并按需阻断。
def _run_mutation_block(paths: RepoPaths, ctx: HookContext, candidate_paths: list[str] | None = None) -> HookResult | None:
    """参数：
        paths: 当前仓库路径上下文。
        ctx: 当前 hook 输入上下文。
        candidate_paths: 候选写入路径列表。

    返回：
        需要阻断时返回 HookResult；允许继续时返回 None。
    """
    if not paths.identity.has_run:
        display_client = paths.identity.client.capitalize() if paths.identity.client == 'codex' else paths.identity.client
        reason = (
            f'unbound {display_client} session is read-only-unbound; mutating operation requires '
            'a managed-worktree run with FEIPI_RUN_ID and confirmed hook activation'
        )
        record_hook_event(paths, ctx, status='BLOCK', extra={'reason': reason, 'mode': 'read-only-unbound'})
        return HookResult(status='BLOCK', exit_code=2, message=reason)
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
        extra={'reason': reason, 'runOwnership': {'runId': paths.identity.raw_run_id, 'errors': errors}},
    )
    return HookResult(status='BLOCK', exit_code=2, message=reason)

# 分发 PreToolUse Bash 事件。
def handle_pre_bash(paths: RepoPaths, ctx: HookContext) -> HookResult:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    if ctx.parse_error:
        reason = f'pre-bash hook payload JSON 解析失败；fail-closed: {ctx.parse_error}'
        record_hook_event(paths, ctx, status='BLOCK', extra={'reason': reason})
        return HookResult(status='BLOCK', exit_code=2, message=reason)

    paths = _paths_for_context(paths, ctx)
    decision = evaluate_command(ctx.command)
    snapshot_written = False
    mutation_tracking = False
    if decision.allowed:
        changed_file_utils.write_base_commit_if_missing(paths.repo_root, paths.base_commit)
        mutation_tracking = not is_read_only_command(
            ctx.command
        ) and not _is_deterministic_validation_command(ctx.command)
        if mutation_tracking and not ctx.session_id:
            reason = 'mutating Bash 缺少 session id；fail-closed，避免 mutation attribution 静默 PASS。'
            record_hook_event(paths, ctx, status='BLOCK', extra={'reason': reason})
            return HookResult(status='BLOCK', exit_code=2, message=reason)
        if mutation_tracking:
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
            snapshot_written = record_pre_bash_snapshot(paths, ctx)
    record_hook_event(
        paths,
        ctx,
        status=decision.status,
        extra={
            'reason': decision.reason,
            'warnings': decision.warnings,
            'bashSnapshot': snapshot_written,
            'bashMutationTracking': mutation_tracking,
            'worktree': {'authority': 'run-record'} if mutation_tracking else None,
        },
    )
    if not decision.allowed:
        return HookResult(status='BLOCK', exit_code=2, message=decision.reason)
    return HookResult(status='PASS', warnings=decision.warnings)


# 分发 PreToolUse 写入事件。
def handle_pre_write(paths: RepoPaths, ctx: HookContext) -> HookResult:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    warnings: list[str] = []
    paths = _paths_for_context(paths, ctx)
    changed_file_utils.write_base_commit_if_missing(paths.repo_root, paths.base_commit)
    payload_reason = pre_write_payload_block_reason(ctx, paths.repo_root)
    if payload_reason:
        reason = payload_reason
        record_hook_event(paths, ctx, status='BLOCK', extra={'reason': reason})
        return HookResult(status='BLOCK', exit_code=2, message=reason)
    run_block = _run_mutation_block(paths, ctx, ctx.candidate_paths)
    if run_block is not None:
        return run_block
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
    record_hook_event(
        paths, ctx, status='PASS', extra={'candidatePathCount': len(ctx.candidate_paths)}
    )
    return HookResult(status='PASS', warnings=warnings)


# 分发 PostToolUse 写入事件。
def handle_post_write(paths: RepoPaths, ctx: HookContext) -> HookResult:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    paths = _paths_for_context(paths, ctx)
    records = record_post_write(paths, ctx)
    for raw_path in ctx.candidate_paths:
        candidate = Path(raw_path)
        if not candidate.is_absolute():
            candidate = paths.repo_root / candidate
        if str(candidate).endswith(('/.claude/settings.local.json', '/.mcp.json')):
            reason = f'personal local config was modified: {raw_path}'
            record_hook_event(paths, ctx, status='BLOCK', extra={'reason': reason, 'file': raw_path})
            return HookResult(status='BLOCK', exit_code=2, message=reason)
        if candidate.suffix == '.sh' and candidate.exists():
            proc = subprocess.run(['bash', '-n', str(candidate)], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            if proc.returncode != 0:
                reason = f'shell syntax check failed: {raw_path}'
                record_hook_event(paths, ctx, status='BLOCK', extra={'reason': reason, 'file': raw_path})
                return HookResult(status='BLOCK', exit_code=2, message=reason)
        if candidate.suffix == '.json' and candidate.exists():
            proc = subprocess.run([sys.executable, '-m', 'json.tool', str(candidate)], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            if proc.returncode != 0:
                reason = f'json syntax check failed: {raw_path}'
                record_hook_event(paths, ctx, status='BLOCK', extra={'reason': reason, 'file': raw_path})
                return HookResult(status='BLOCK', exit_code=2, message=reason)
    return HookResult(status='PASS', details={'changedFileCount': len(records)})


# 分发 PostToolUse Bash 事件。
def handle_post_bash(paths: RepoPaths, ctx: HookContext) -> HookResult:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    paths = _paths_for_context(paths, ctx)
    records = record_post_bash(paths, ctx)
    return HookResult(status='PASS', details={'changedFileCount': len(records)})


# 分发默认 hook 事件。
def handle_default(paths: RepoPaths, ctx: HookContext, label: str) -> HookResult:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    if label.lower() in {'stop', 'session-stop'} and ctx.empty_input:
        dirty = changed_file_utils.read_git_dirty_files(paths.repo_root)
        if dirty:
            reason = 'Stop hook stdin 为空且 git workspace 非 clean；fail-closed。'
            record_hook_event(paths, ctx, status='BLOCK', extra={'reason': reason, 'dirtyCount': len(dirty)})
            return HookResult(status='BLOCK', exit_code=2, message=reason)
    if label in {'session-start', 'subagent-start'}:
        handle_session_start(paths, ctx, label)
        if label == 'session-start':
            if not paths.identity.has_run:
                if paths.identity.raw_session_id:
                    marker = paths.repo_root / 'tmp' / 'agent_logs' / paths.identity.client / paths.identity.raw_session_id / 'read-only-unbound.json'
                    marker.parent.mkdir(parents=True, exist_ok=True)
                    marker.write_text(
                        '{"schemaVersion":1,"client":"%s","sessionId":"%s","status":"read-only-unbound","reason":"FEIPI_RUN_ID missing; mutations require managed run"}\n'
                        % (paths.identity.client, paths.identity.raw_session_id),
                        encoding='utf-8',
                    )
                record_hook_event(paths, ctx, status='READ_ONLY_UNBOUND', extra={'mode': 'read-only-unbound'})
    elif label == 'config-change':
        record_config_change(paths, ctx)
        record_hook_event(paths, ctx, status='CONFIG')
    elif label == 'tool-failure' and ctx.tool_name == 'Bash':
        records = record_post_bash(paths, ctx)
        return HookResult(status='PASS', details={'changedFileCount': len(records)})
    else:
        record_hook_event(paths, ctx, status='OBSERVED')
    return HookResult(status='PASS')


# 解析命令行参数并运行脚本入口。
def main(argv: list[str] | None = None) -> int:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    argv = argv if argv is not None else sys.argv[1:]
    event_name = argv[0] if argv else 'unknown'

    # --self-test 不需要 stdin，必须在 read_stdin_json 之前分发，
    # 否则 sys.stdin.read() 会在没有管道输入时阻塞等待 EOF。
    if event_name == '--self-test':
        run_self_test()
        print('scripts.claude_hooks self-test PASS')
        return 0

    ctx = read_stdin_json(event_name)
    identity = identity_from_hook_context(ctx)
    paths = build_paths(repo_root=ctx.cwd or None, identity=identity)
    ensure_runtime_dirs(paths)
    _maybe_lazy_bind_session(paths, ctx)

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
