#!/usr/bin/env python3
"""负责把稳定 CLI 参数适配到 agent_runtime Session 服务；不负责实现状态机或持久化；由 Hook、完成脚本和维护者命令行调用。"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.agent_runtime.session.completion import (  # noqa: E402
    cmd_adopt_current,
    cmd_begin_change,
    cmd_completion_status,
)
from scripts.agent_runtime.session.contract import (  # noqa: E402
    CHECKOUT_CREATORS,
    PrimarySessionValidationError,
)
from scripts.agent_runtime.session.errors import SessionctlError  # noqa: E402
from scripts.agent_runtime.session.finalize import cmd_finalize  # noqa: E402
from scripts.agent_runtime.session.lease import DEFAULT_LEASE_STALE_SECONDS, cmd_lease  # noqa: E402
from scripts.agent_runtime.session.lifecycle import (  # noqa: E402
    cmd_bootstrap,
    cmd_cleanup,
    cmd_doctor,
    cmd_handoff,
    cmd_list,
    cmd_set_change,
    cmd_status,
    cmd_stop,
)


def build_parser() -> argparse.ArgumentParser:
    """定义稳定 Session CLI 参数面；所有业务处理都委托 agent_runtime 服务。"""
    parser = argparse.ArgumentParser(description='Manage Feipi adopted-checkout Session runtime')
    parser.add_argument('--repo-root', help='Git repository root; defaults to cwd')
    sub = parser.add_subparsers(dest='command', required=True)
    bootstrap = sub.add_parser('bootstrap')
    bootstrap.add_argument('--client', required=True, choices=['codex', 'qoder', 'claude'])
    bootstrap.add_argument('--session-id', required=True)
    bootstrap.add_argument('--cwd', required=True)
    bootstrap.add_argument('--hook-event', required=True)
    bootstrap.add_argument(
        '--checkout-creator', choices=sorted(CHECKOUT_CREATORS), default='unknown'
    )
    bootstrap.add_argument('--run-id', '--payload-run-id', dest='run_id')
    bootstrap.add_argument('--worktree-id', '--payload-worktree-id', dest='worktree_id')
    bootstrap.add_argument('--parent-run-id')
    bootstrap.set_defaults(func=cmd_bootstrap)
    set_change = sub.add_parser('set-change')
    set_change.add_argument('--client', required=True, choices=['codex', 'qoder', 'claude'])
    set_change.add_argument('--session-id', required=True)
    set_change.add_argument('--cwd', required=True)
    set_change.add_argument('--change-id', required=True)
    set_change.add_argument('--task-id')
    set_change.set_defaults(func=cmd_set_change)
    begin = sub.add_parser('begin-change')
    begin.add_argument('--run-id', required=True)
    begin.add_argument('--cwd', required=True)
    begin.add_argument('--activation-source', required=True)
    begin.add_argument('--start-enforced', action='store_true')
    begin.set_defaults(func=cmd_begin_change)
    adopt = sub.add_parser('adopt-current')
    adopt.add_argument('--run-id', required=True)
    adopt.add_argument('--cwd', required=True)
    adopt.add_argument('--base', required=True)
    adopt.add_argument('--file', action='append', required=True)
    adopt.add_argument('--confirmation', required=True)
    adopt.set_defaults(func=cmd_adopt_current)
    completion = sub.add_parser('completion-status')
    completion.add_argument('--run-id', required=True)
    completion.set_defaults(func=cmd_completion_status)

    def add_lease_identity(command: argparse.ArgumentParser, *, parent: bool = True) -> None:
        """参数：
        command: 待扩展的子命令解析器。
        parent: 是否允许传入父运行标识符。
        """
        command.add_argument('--client', required=True, choices=['codex', 'qoder', 'claude'])
        command.add_argument('--session-id', required=True)
        command.add_argument('--cwd', required=True)
        if parent:
            command.add_argument('--parent-run-id')

    read_ready = sub.add_parser('mark-read-only-ready')
    add_lease_identity(read_ready)
    read_ready.set_defaults(func=cmd_lease, lease_action='read-ready')
    acquire_lease = sub.add_parser('acquire-writer-lease')
    add_lease_identity(acquire_lease)
    acquire_lease.add_argument('--owner-pid', type=int)
    acquire_lease.add_argument('--owner-start-time')
    acquire_lease.set_defaults(func=cmd_lease, lease_action='acquire')
    heartbeat_lease = sub.add_parser('heartbeat-writer-lease')
    add_lease_identity(heartbeat_lease)
    heartbeat_lease.add_argument('--epoch', type=int)
    heartbeat_lease.add_argument('--fencing-token')
    heartbeat_lease.set_defaults(func=cmd_lease, lease_action='heartbeat')
    release_lease = sub.add_parser('release-writer-lease')
    add_lease_identity(release_lease)
    release_lease.add_argument('--epoch', type=int)
    release_lease.add_argument('--fencing-token')
    release_lease.add_argument('--reason', default='SessionEnd')
    release_lease.set_defaults(func=cmd_lease, lease_action='release')
    reclaim_lease = sub.add_parser('reclaim-writer-lease')
    add_lease_identity(reclaim_lease, parent=False)
    reclaim_lease.add_argument('--expected-epoch', required=True, type=int)
    reclaim_lease.add_argument('--expected-holder-run-id', required=True)
    reclaim_lease.add_argument('--expected-holder-session-id', required=True)
    reclaim_lease.add_argument(
        '--stale-after-seconds', type=float, default=DEFAULT_LEASE_STALE_SECONDS
    )
    reclaim_lease.set_defaults(func=cmd_lease, lease_action='reclaim')
    for name, func in [('list', cmd_list)]:
        p = sub.add_parser(name)
        p.add_argument('--json', action='store_true')
        p.set_defaults(func=func)
    for name, func in [('status', cmd_status), ('stop', cmd_stop), ('handoff', cmd_handoff)]:
        p = sub.add_parser(name)
        p.add_argument('--run-id', required=True)
        p.set_defaults(func=func)
    finalize = sub.add_parser('finalize')
    finalize.add_argument('--run-id', required=True)
    finalize.set_defaults(func=cmd_finalize)
    doctor = sub.add_parser('doctor')
    doctor.add_argument('--run-id', required=False)
    doctor.set_defaults(func=cmd_doctor)
    cleanup = sub.add_parser('cleanup')
    cleanup.add_argument('--run-id', required=True)
    cleanup.add_argument(
        '--execute',
        action='store_true',
        help='release this run and remove only its evidence; default is dry-run',
    )
    cleanup.set_defaults(func=cmd_cleanup)
    return parser


def main(argv: list[str] | None = None) -> int:
    """解析 CLI 并统一把契约、Git 与系统错误映射为 BLOCKED 退出码。"""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (
        SessionctlError,
        subprocess.CalledProcessError,
        PrimarySessionValidationError,
        OSError,
    ) as exc:
        print(f'sessionctl: BLOCKED: {exc}', file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
