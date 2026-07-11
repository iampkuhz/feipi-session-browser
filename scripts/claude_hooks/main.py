"""提供 主流程 脚本能力。"""

from __future__ import annotations

import sys
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
from scripts.agent_runtime.worktree import check_session_worktree


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
        'python -m pytest tests/test_agent_runtime_worktree.py',
        'python3 -m pytest tests/test_agent_runtime_worktree.py',
        'python -m pytest -q tests/test_agent_runtime_worktree.py',
        'python3 -m pytest -q tests/test_agent_runtime_worktree.py',
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
    hint = _context_repo_hint(ctx)
    if not hint:
        return paths
    return build_paths(repo_root=hint, identity=paths.identity)


# 变更类工具必须运行在 main session 分配的 worktree 中。
def _worktree_mutation_block(paths: RepoPaths, ctx: HookContext) -> HookResult | None:
    """参数：
        paths: Repository 运行time 路径。
        ctx: 当前 hook payload。

    返回：
        需要阻断时返回 HookResult；允许继续时返回 None。
    """
    decision = check_session_worktree(paths.repo_root, paths.identity, create=True)
    if decision.allowed:
        return None
    reason = decision.reason or 'main agent session must use its assigned git worktree'
    record_hook_event(
        paths,
        ctx,
        status='BLOCK',
        extra={'reason': reason, 'worktree': decision.as_dict()},
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
            worktree_block = _worktree_mutation_block(paths, ctx)
            if worktree_block is not None:
                return worktree_block
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
            'worktree': check_session_worktree(paths.repo_root, paths.identity).as_dict()
            if mutation_tracking
            else None,
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
    worktree_block = _worktree_mutation_block(paths, ctx)
    if worktree_block is not None:
        return worktree_block
    for path in ctx.candidate_paths:
        if is_protected_path(path, paths.repo_root):
            guard = subprocess.run(
                [
                    sys.executable,
                    str(paths.repo_root / 'scripts' / 'hooks' / 'guard_openspec_change.py'),
                    '--path',
                    path,
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
            decision = check_session_worktree(paths.repo_root, paths.identity, create=True)
            if decision.required:
                record_hook_event(
                    paths,
                    ctx,
                    status='WORKTREE_READY' if decision.assigned else 'WORKTREE_PENDING',
                    extra={'worktree': decision.as_dict()},
                )
                if not decision.allowed and decision.reason:
                    return HookResult(status='PASS', warnings=[decision.reason])
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
