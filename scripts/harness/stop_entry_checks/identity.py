"""身份校验：run/session identity 提取、record 验证、checkout 事实校验。"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from scripts.claude_hooks import paths as runtime_paths
from scripts.claude_hooks.hook_io import HookContext
from scripts.harness.primary_session import (
    load_run_record,
    validate_checkout_record,
    validate_run_record,
)


def _repo_root(ctx: dict[str, Any]) -> Path:
    """从 hook context 提取仓库根目录。"""
    raw = ctx.get('cwd') or ctx.get('workingDirectory') or ''
    return runtime_paths.find_repo_root(raw or Path.cwd())


def validate_run_identity(
    agent: str,
    raw_ctx: dict[str, Any],
    repo_root: Path,
) -> tuple[HookContext, Any, Any, Any] | None:
    """校验 run/session identity 和 record。

    返回 (ctx, identity, record, checkout_facts) 四元组；校验失败时打印 BLOCK 并返回 None。
    """
    ctx = HookContext('Stop', raw_ctx)
    identity = runtime_paths.identity_from_hook_context(ctx, agent_client=agent)
    if not identity.has_run or not identity.has_session:
        print('[stop_entry] BLOCK authoritative run/session identity is required', file=sys.stderr)
        return None
    record = load_run_record(repo_root, identity.raw_run_id)
    if not record:
        print('[stop_entry] BLOCK run record not found for run_id', file=sys.stderr)
        return None
    try:
        validate_run_record(record)
        checkout_facts, checkout_errors = validate_checkout_record(repo_root, record)
    except Exception as exc:
        print(f'[stop_entry] BLOCK run identity cannot be proven: {exc}', file=sys.stderr)
        return None
    if checkout_errors:
        print(
            '[stop_entry] BLOCK checkout identity: ' + '; '.join(checkout_errors),
            file=sys.stderr,
        )
        return None
    return ctx, identity, record, checkout_facts
