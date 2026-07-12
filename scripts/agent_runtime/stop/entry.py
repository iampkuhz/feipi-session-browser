#!/usr/bin/env python3
"""解析 Stop CLI/payload，并把业务唯一委托给 typed pipeline。

不负责平台 Hook wrapper 配置；由 Hook 或 Stop runtime 调用。"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .pipeline import run_stop


def read_stdin_once() -> tuple[str, dict[str, Any]]:
    """只读取一次标准输入；无效 JSON 作为空 Hook context 处理。"""
    raw = sys.stdin.read()
    if not raw.strip():
        return raw, {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return raw, {}
    return raw, data if isinstance(data, dict) else {}


def main(argv: list[str] | None = None) -> int:
    """解析公开 CLI 参数并返回 Stop 稳定退出码。"""
    parser = argparse.ArgumentParser(description='Run unified Stop entry.')
    parser.add_argument('--agent', default='unknown')
    parser.add_argument('--agent-id', default=None)
    args = parser.parse_args(argv)
    _raw, context = read_stdin_once()
    if args.agent_id and 'agent_id' not in context and 'agentId' not in context:
        context['agent_id'] = args.agent_id
    try:
        return run_stop(args.agent, context)
    except BaseException as exc:
        print(f'[stop_entry] FAIL unhandled stop exception: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
