#!/usr/bin/env python3
"""三平台 Hook 的唯一输入适配器。

本文件只负责校验 checkout、选择项目 Python、保留 stdin 并把事件转发给
唯一 Hook 权威入口；不承载策略、evidence 或 Gate 业务。
"""

from __future__ import annotations

import argparse
import io
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.agent_runtime.events.adapter import RUNTIME_EVENTS  # noqa: E402
from scripts.harness.python_env import resolve_python  # noqa: E402

CLIENTS = frozenset({'claude', 'codex', 'qoder'})


def trusted_root() -> Path:
    """校验 dispatcher 所在目录是当前 Git checkout root。"""
    result = subprocess.run(
        ['git', '-C', str(ROOT), 'rev-parse', '--show-toplevel'],
        text=True,
        capture_output=True,
        check=False,
        timeout=2,
    )
    observed = Path(result.stdout.strip()).resolve() if result.returncode == 0 else None
    if observed != ROOT:
        raise RuntimeError('hook dispatcher is not inside a trusted Git checkout root')
    return ROOT


def _executable_path(command: str) -> Path | None:
    candidate = shutil.which(command) if os.sep not in command else command
    return Path(candidate).resolve() if candidate else None


def ensure_project_python(argv: list[str]) -> None:
    """如当前解释器不是项目解析结果，保留 stdin 并原地 re-exec。"""
    selected = resolve_python(ROOT)
    if _executable_path(selected) == Path(sys.executable).resolve():
        return
    if os.environ.get('FEIPI_HOOK_DISPATCH_REEXEC') == '1':
        raise RuntimeError('project Python re-exec did not converge')
    env = dict(os.environ, FEIPI_HOOK_DISPATCH_REEXEC='1')
    os.execvpe(selected, [selected, str(Path(__file__).resolve()), *argv], env)


def dispatch(client: str, event: str, payload: str) -> int:
    """保留 payload 字节内容并转发到唯一 Hook 入口。"""
    if client not in CLIENTS or event not in RUNTIME_EVENTS:
        raise ValueError(f'unsupported hook dispatch: client={client} event={event}')
    os.environ['FEIPI_AGENT_CLIENT'] = client
    os.environ.setdefault('FEIPI_HOOK_CWD', os.getcwd())
    original_stdin = sys.stdin
    try:
        sys.stdin = io.StringIO(payload)
        from scripts.agent_runtime.hook_entry import main as hook_main

        return hook_main([event])
    finally:
        sys.stdin = original_stdin


def main(argv: list[str] | None = None) -> int:
    """解析 client/event，选择项目 Python 并完整转发 stdin。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--client', choices=sorted(CLIENTS), required=True)
    parser.add_argument('--event', choices=sorted(RUNTIME_EVENTS), required=True)
    args = parser.parse_args(argv)
    try:
        trusted_root()
        ensure_project_python(argv if argv is not None else sys.argv[1:])
        return dispatch(args.client, args.event, sys.stdin.read())
    except (OSError, RuntimeError, ValueError) as exc:
        print(f'[hook_dispatch] BLOCK: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
