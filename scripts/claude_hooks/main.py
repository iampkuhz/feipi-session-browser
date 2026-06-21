"""Dispatch Claude hook events to policy evaluators and evidence writers.

The shell hook entry points invoke this module with an event label such as ``pre-bash``,
``pre-write``, or ``post-write``. Handlers convert policy decisions into concise hook
output: PASS returns zero, BLOCK returns exit code 2, and observed/default events only
record evidence.
"""

from __future__ import annotations

import sys

from .evidence import record_hook_event, record_post_write
from .hook_io import HookContext, read_stdin_json
from .paths import RepoPaths, build_paths, ensure_runtime_dirs
from .policy.bash_policy import evaluate_command
from .policy.config_policy import record_config_change
from .policy.file_policy import evaluate_write_path
from .policy.session_context import handle_session_start
from .result import HookResult, emit
from .self_test import run_self_test


# 01. 事件处理: pre-bash
def handle_pre_bash(paths: RepoPaths, ctx: HookContext) -> HookResult:
    """Evaluate a Bash command before Claude executes it.

    Args:
        paths: Repository runtime paths for evidence output.
        ctx: Parsed pre-bash hook context containing the command.

    Returns:
        PASS with warnings for allowed commands, or BLOCK with exit code 2 for commands
        that match destructive or secret-reading patterns.
    """
    decision = evaluate_command(ctx.command)
    record_hook_event(
        paths,
        ctx,
        status=decision.status,
        extra={'reason': decision.reason, 'warnings': decision.warnings},
    )
    if not decision.allowed:
        return HookResult(status='BLOCK', exit_code=2, message=decision.reason)
    return HookResult(status='PASS', warnings=decision.warnings)


# 02. 事件处理: pre-write
def handle_pre_write(paths: RepoPaths, ctx: HookContext) -> HookResult:
    """Evaluate candidate write paths before Claude edits files.

    Args:
        paths: Repository runtime paths and repository root.
        ctx: Parsed pre-write hook context containing candidate file paths.

    Returns:
        PASS when all paths are allowed, possibly with warnings for generated/runtime
        files. BLOCK with exit code 2 is returned for sensitive directories.
    """
    warnings: list[str] = []
    for path in ctx.candidate_paths:
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


# 03. 事件处理: post-write
def handle_post_write(paths: RepoPaths, ctx: HookContext) -> HookResult:
    """Record changed-file evidence after Claude writes files.

    Args:
        paths: Repository runtime paths for changed-file evidence.
        ctx: Parsed post-write hook context containing candidate file paths.

    Returns:
        PASS with the number of changed-file evidence records written.
    """
    records = record_post_write(paths, ctx)
    return HookResult(status='PASS', details={'changedFileCount': len(records)})


# 04. 通用事件
def handle_default(paths: RepoPaths, ctx: HookContext, label: str) -> HookResult:
    """Record non-blocking hook events that have no dedicated policy.

    Args:
        paths: Repository runtime paths for event evidence.
        ctx: Parsed hook context.
        label: Event label supplied by the CLI wrapper.

    Returns:
        PASS because default events only record evidence and never block execution.
    """
    if label in {'session-start', 'subagent-start'}:
        handle_session_start(paths, ctx, label)
    elif label == 'config-change':
        record_config_change(paths, ctx)
        record_hook_event(paths, ctx, status='CONFIG')
    else:
        record_hook_event(paths, ctx, status='OBSERVED')
    return HookResult(status='PASS')


# 06. CLI 入口
def main(argv: list[str] | None = None) -> int:
    """Run the Claude hook dispatcher from CLI arguments and stdin.

    Args:
        argv: Optional argument list whose first item is the hook event label.

    Returns:
        Process exit code for the hook wrapper. Zero means pass, while two is used for
        policy blocks.
    """
    argv = argv if argv is not None else sys.argv[1:]
    event_name = argv[0] if argv else 'unknown'
    paths = build_paths()
    ensure_runtime_dirs(paths)
    ctx = read_stdin_json(event_name)

    if event_name == 'pre-bash':
        return emit(handle_pre_bash(paths, ctx))
    if event_name == 'pre-write':
        return emit(handle_pre_write(paths, ctx))
    if event_name == 'post-write':
        return emit(handle_post_write(paths, ctx))
    if event_name == '--self-test':
        run_self_test()
        print('scripts.claude_hooks self-test PASS')
        return 0

    return emit(handle_default(paths, ctx, event_name))


# 07. 模块执行
if __name__ == '__main__':
    raise SystemExit(main())
