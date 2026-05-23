from __future__ import annotations

import sys

from .hook_io import read_stdin_json
from .paths import build_paths, ensure_runtime_dirs
from .evidence import record_hook_event, record_post_write
from .result import HookResult, emit
from .policy.bash_policy import evaluate_command
from .policy.file_policy import evaluate_write_path
from .policy.stop_policy import check_stop, write_stop_summary
from .policy.session_context import handle_session_start
from .policy.config_policy import record_config_change


# 01. 事件处理：pre-bash
def handle_pre_bash(paths, ctx) -> HookResult:
    decision = evaluate_command(ctx.command)
    record_hook_event(paths, ctx, status=decision.status, extra={"reason": decision.reason, "warnings": decision.warnings})
    if not decision.allowed:
        return HookResult(status="BLOCK", exit_code=2, message=decision.reason)
    return HookResult(status="PASS", warnings=decision.warnings)


# 02. 事件处理：pre-write
def handle_pre_write(paths, ctx) -> HookResult:
    warnings: list[str] = []
    for path in ctx.candidate_paths:
        decision = evaluate_write_path(path, paths.repo_root)
        warnings.extend(decision.warnings)
        if not decision.allowed:
            record_hook_event(paths, ctx, status="BLOCK", extra={"reason": decision.reason, "file": path})
            return HookResult(status="BLOCK", exit_code=2, message=decision.reason)
    record_hook_event(paths, ctx, status="PASS", extra={"candidatePathCount": len(ctx.candidate_paths)})
    return HookResult(status="PASS", warnings=warnings)


# 03. 事件处理：post-write
def handle_post_write(paths, ctx) -> HookResult:
    records = record_post_write(paths, ctx)
    return HookResult(status="PASS", details={"changedFileCount": len(records)})


# 04. 事件处理：stop
def handle_stop(paths, ctx) -> HookResult:
    result = check_stop(paths)
    write_stop_summary(paths, result)
    if not result.passed:
        return HookResult(
            status="FAIL",
            exit_code=2,
            message="deterministic quality gate 未通过。",
            details={
                "changeId": result.change_id,
                "requiredTargets": result.required_targets,
                "blockingFailures": result.blocking_failures,
            },
        )
    return HookResult(status="PASS", warnings=result.warnings)


# 05. 通用事件
def handle_default(paths, ctx, label: str) -> HookResult:
    if label in {"session-start", "subagent-start"}:
        handle_session_start(paths, ctx, label)
    elif label == "config-change":
        record_config_change(paths, ctx)
        record_hook_event(paths, ctx, status="CONFIG")
    else:
        record_hook_event(paths, ctx, status="OBSERVED")
    return HookResult(status="PASS")


# 06. CLI 入口
def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    event_name = argv[0] if argv else "unknown"
    paths = build_paths()
    ensure_runtime_dirs(paths)
    ctx = read_stdin_json(event_name)

    if event_name == "pre-bash":
        return emit(handle_pre_bash(paths, ctx))
    if event_name == "pre-write":
        return emit(handle_pre_write(paths, ctx))
    if event_name == "post-write":
        return emit(handle_post_write(paths, ctx))
    if event_name == "stop" or event_name == "subagent-stop":
        return emit(handle_stop(paths, ctx))
    if event_name == "--self-test":
        from .self_test import run_self_test
        run_self_test()
        print("scripts.claude_hooks self-test PASS")
        return 0

    return emit(handle_default(paths, ctx, event_name))


# 07. 模块执行
if __name__ == "__main__":
    raise SystemExit(main())
