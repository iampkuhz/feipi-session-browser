"""负责适配三平台 Stop payload；不负责生命周期业务，只调用 LifecycleController。"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from scripts.agent_runtime.session.completion import START_ENFORCED, begin_change
from scripts.agent_runtime.session.lifecycle import bootstrap_session

from .controller import LifecycleController, map_controller_exception
from .protocol import EXIT_CODES, compact_payload, encode_compact


def read_stdin_once() -> tuple[str, dict[str, Any]]:
    """一次性读取平台输入；无效 JSON 仅返回空对象，不猜测字段。"""
    raw = sys.stdin.read()
    if not raw.strip():
        return raw, {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return raw, {}
    return raw, payload if isinstance(payload, dict) else {}


def _value(payload: dict[str, Any], *names: str) -> str:
    for name in names:
        value = payload.get(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ''


def run_stop_payload(agent: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """Stop 缺失时幂等 bootstrap/begin；dirty 且无基线时按归因不变量关闭失败。"""
    try:
        cwd = Path(_value(payload, 'cwd') or Path.cwd()).resolve()
        session_id = _value(payload, 'session_id', 'sessionId')
        if not session_id:
            raise ValueError('Stop payload requires session_id')
        record = bootstrap_session(
            client=agent,
            session_id=session_id,
            cwd=cwd,
            hook_event='Stop',
            checkout_creator=agent if agent in {'codex', 'claude', 'qoder'} else 'unknown',
            payload_hints={
                'runId': _value(payload, 'run_id', 'runId'),
                'worktreeId': _value(payload, 'worktree_id', 'worktreeId'),
            },
        )
        if not isinstance(record.get('changeBegin'), dict):
            record = begin_change(
                cwd,
                str(record['runId']),
                activation_source=f'hook:{agent}:Stop-self-heal',
                capability=START_ENFORCED,
            )
        controller = LifecycleController(cwd, record)
        message = _value(payload, 'commit_message', 'commitMessage') or (
            f"chore(agent): complete {_value(payload, 'task_id', 'taskId') or record['runId']}"
        )
        result = controller.on_stop(message=message)
        return EXIT_CODES.get(str(result.get('status')), 70), result
    except BaseException as raw:
        error = map_controller_exception(raw)
        result = compact_payload(
            status=error.status,
            state='UNKNOWN',
            code=error.code,
            root_failure={'code': error.code, 'message': str(error)},
            next_action='RETRY' if error.status.endswith('RETRYABLE') else 'MANUAL_RECOVERY',
            repair_argv=error.repair_argv,
        )
        return EXIT_CODES[error.status], result


def main(argv: list[str] | None = None) -> int:
    """解析平台身份并输出单个紧凑 JSON；不展开 artifact 内容。"""
    import argparse

    parser = argparse.ArgumentParser(description='Run canonical lifecycle on-stop adapter')
    parser.add_argument('--agent', choices=('codex', 'claude', 'qoder'), required=True)
    parser.add_argument('--agent-id', default='')
    args = parser.parse_args(argv)
    _raw, payload = read_stdin_once()
    if args.agent_id and not _value(payload, 'agent_id', 'agentId'):
        payload['agent_id'] = args.agent_id
    exit_code, result = run_stop_payload(args.agent, payload)
    print(encode_compact(result))
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
