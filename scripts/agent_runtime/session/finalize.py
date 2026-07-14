"""负责旧 finalize CLI 的薄适配；不负责收口业务，只调用 canonical controller。"""

from __future__ import annotations

from scripts.agent_runtime.change.controller import LifecycleController, map_controller_exception
from scripts.agent_runtime.change.protocol import EXIT_CODES, encode_compact
from scripts.agent_runtime.session.lifecycle import repo_root_from_arg


def cmd_finalize(args):
    """把旧 finalize 参数转给 controller；不直接修改 Git 或状态。"""
    try:
        repo = repo_root_from_arg(getattr(args, 'repo_root', None))
        controller = LifecycleController.from_run_id(repo, args.run_id)
        result = controller.on_stop(message=f'chore(agent): resume {args.run_id}')
        print(encode_compact(result))
        return EXIT_CODES.get(str(result.get('status')), 70)
    except BaseException as raw:
        error = map_controller_exception(raw)
        print(encode_compact({'status': error.status, 'state': 'UNKNOWN', 'code': error.code}))
        return EXIT_CODES[error.status]


__all__ = ['cmd_finalize']
