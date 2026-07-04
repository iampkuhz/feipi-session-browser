"""提供 主流程 脚本能力。"""

from __future__ import annotations

import sys

from .evidence import (
    acquire_bash_mutation_lock,
    record_hook_event,
    record_post_bash,
    record_post_write,
    record_pre_bash_snapshot,
)
from .hook_io import HookContext, read_stdin_json
from .paths import RepoPaths, build_paths, ensure_runtime_dirs, identity_from_hook_context
from .policy.bash_policy import evaluate_command, is_read_only_command
from .policy.config_policy import record_config_change
from .policy.file_policy import evaluate_write_path
from .policy.session_context import handle_session_start
from .result import HookResult, emit
from .self_test import run_self_test
from scripts.quality import changed_files as changed_file_utils


# 分发 PreToolUse Bash 事件。
def handle_pre_bash(paths: RepoPaths, ctx: HookContext) -> HookResult:
    """参数：
        paths: Repository 运行time 路径用于evidence 输出。
        ctx: 已解析的pre-bash hook context containing 命令。

    返回：
        解析后的 HookContext；失败时携带 parse_error。
    """
    decision = evaluate_command(ctx.command)
    snapshot_written = False
    mutation_tracking = False
    if decision.allowed:
        changed_file_utils.write_base_commit_if_missing(paths.repo_root, paths.base_commit)
        mutation_tracking = not is_read_only_command(ctx.command)
        if mutation_tracking and not acquire_bash_mutation_lock(paths, ctx):
            reason = '另一个 Bash mutation attribution 正在运行；请稍后重试该命令。'
            record_hook_event(
                paths,
                ctx,
                status='BLOCK',
                extra={'reason': reason, 'bashMutationLock': 'busy'},
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
        },
    )
    if not decision.allowed:
        return HookResult(status='BLOCK', exit_code=2, message=decision.reason)
    return HookResult(status='PASS', warnings=decision.warnings)


# 分发 PreToolUse 写入事件。
def handle_pre_write(paths: RepoPaths, ctx: HookContext) -> HookResult:
    """参数：
        paths: 待检查的路径列表。
        ctx: 已解析的pre-写入 hook context containing candidate 文件路径s。

    返回：
        PASS 当 all 路径 are allowed, possibly带warning用于generated/运行time。 文件. BLOCK带exit code 2 is returned用于sensitive 目录。
    """
    warnings: list[str] = []
    changed_file_utils.write_base_commit_if_missing(paths.repo_root, paths.base_commit)
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


# 分发 PostToolUse 写入事件。
def handle_post_write(paths: RepoPaths, ctx: HookContext) -> HookResult:
    """参数：
        paths: Repository 运行time 路径用于changed-文件 evidence。
        ctx: 已解析的post-写入 hook context containing candidate 文件路径s。

    返回：
        PASS带the 数字 of changed-文件 evidence record written。
    """
    records = record_post_write(paths, ctx)
    return HookResult(status='PASS', details={'changedFileCount': len(records)})


# 分发 PostToolUse Bash 事件。
def handle_post_bash(paths: RepoPaths, ctx: HookContext) -> HookResult:
    """参数：
        paths: 待检查的路径列表。
        ctx: ctx 参数。

    返回：
        解析后的 HookContext；失败时携带 parse_error。
    """
    records = record_post_bash(paths, ctx)
    return HookResult(status='PASS', details={'changedFileCount': len(records)})


# 分发默认 hook 事件。
def handle_default(paths: RepoPaths, ctx: HookContext, label: str) -> HookResult:
    """参数：
        paths: Repository 运行time 路径用于event evidence。
        ctx: 已解析的hook context。
        label: 输出中显示的人类可读标签。

    返回：
        PASS because 默认 events 仅 record evidence 和 绝不 block execution。
    """
    if label in {'session-start', 'subagent-start'}:
        handle_session_start(paths, ctx, label)
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
        argv: 可选参数 列表 whose first item is hook event label。

    返回：
        进程退出码。
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
    paths = build_paths(identity=identity_from_hook_context(ctx))
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
