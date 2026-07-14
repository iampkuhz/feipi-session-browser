#!/usr/bin/env python3
"""负责唯一 lifecycle controller 的稳定 CLI；不负责业务，只输出紧凑 JSON。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.agent_runtime.change.controller import (  # noqa: E402
    LifecycleController,
    map_controller_exception,
)
from scripts.agent_runtime.change.protocol import (  # noqa: E402
    EXIT_CODES,
    compact_payload,
    encode_compact,
)
from scripts.agent_runtime.git_state import run as git  # noqa: E402


def _repo(value: str | None) -> Path:
    start = Path(value).resolve() if value else Path.cwd().resolve()
    result = git(start, 'rev-parse', '--show-toplevel', timeout=2)
    return Path(result.stdout.strip()).resolve()


def build_parser() -> argparse.ArgumentParser:
    """构造公开命令解析器；不读取仓库或运行 controller。"""
    parser = argparse.ArgumentParser(description='Manage one deterministic Change lifecycle')
    parser.add_argument('--repo-root')
    parser.add_argument('--verbose', action='store_true')
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('ensure-session', 'status'):
        command = commands.add_parser(name)
        command.add_argument('--run-id', required=True)
        if name == 'ensure-session':
            command.add_argument('--event', choices=('start', 'prompt', 'status'), default='start')
            command.add_argument('--task-key', default='')
            command.add_argument('--task-title', default='')
        else:
            command.add_argument('--compact', action='store_true')
    for name in ('on-stop', 'resume'):
        command = commands.add_parser(name)
        command.add_argument('--run-id', required=True)
        command.add_argument('--message', required=True)
        command.add_argument('--expect-manifest-hash', default='')
        command.add_argument('--expect-candidate-tree', default='')
    next_change = commands.add_parser('next-change')
    next_change.add_argument('--run-id', required=True)
    next_change.add_argument('--task-key', required=True)
    next_change.add_argument('--task-title', default='')
    abort = commands.add_parser('abort')
    abort.add_argument('--run-id', required=True)
    return parser


def execute(args: argparse.Namespace) -> dict[str, Any]:
    """把已解析命令委托 controller；不展开 artifact 或改写结果。"""
    controller = LifecycleController.from_run_id(_repo(args.repo_root), args.run_id)
    if args.command == 'ensure-session':
        session = controller.ensure_session(
            event=args.event, task_key=args.task_key, task_title=args.task_title
        )
        return controller._payload(  # noqa: SLF001 - CLI 是 controller 的同包适配面
            session, status='PASS', code='SESSION_ENSURED', next_action='CONTINUE'
        )
    if args.command == 'status':
        return controller.status()
    if args.command in {'on-stop', 'resume'}:
        return controller.on_stop(
            message=args.message,
            expect_manifest_hash=args.expect_manifest_hash,
            expect_candidate_tree=args.expect_candidate_tree,
        )
    if args.command == 'next-change':
        return controller.next_change(task_key=args.task_key, task_title=args.task_title)
    if args.command == 'abort':
        return controller.abort()
    raise AssertionError(args.command)


def main(argv: Sequence[str] | None = None) -> int:
    """输出单个协议 JSON 和集中退出码；异常不打印完整诊断。"""
    args = build_parser().parse_args(argv)
    try:
        payload = execute(args)
    except BaseException as raw:
        error = map_controller_exception(raw)
        payload = compact_payload(
            status=error.status,
            state='UNKNOWN',
            code=error.code,
            root_failure={'code': error.code, 'message': str(error)},
            next_action='RETRY' if error.status.endswith('RETRYABLE') else 'MANUAL_RECOVERY',
            repair_argv=error.repair_argv,
        )
        print(encode_compact(payload))
        return EXIT_CODES[error.status]
    print(encode_compact(payload))
    if args.verbose and payload.get('artifactPath'):
        print(
            json.dumps({'artifactPath': payload['artifactPath']}, ensure_ascii=False),
            file=sys.stderr,
        )
    return EXIT_CODES.get(str(payload.get('status')), 70)


if __name__ == '__main__':
    raise SystemExit(main())
