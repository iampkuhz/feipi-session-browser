"""提供所有领域 Check 的唯一命令行入口。

命令行根据 check ID 找到一个 `check_*.py` 模块，把剩余参数交给该模块唯一的 `check(arguments)`
函数，最后统一输出 PASS、FAIL 和诊断；这里不包含任何领域规则。
"""

from __future__ import annotations

import argparse

from scripts.gates.checks._framework import CheckStatus, invoke
from scripts.gates.checks._registry import CHECKS, get_check


def build_parser() -> argparse.ArgumentParser:
    """构造唯一公共参数解析器。"""
    parser = argparse.ArgumentParser(prog='python3 -m scripts.gates.checks')
    parser.add_argument('check_id', choices=sorted(CHECKS))
    parser.add_argument('arguments', nargs=argparse.REMAINDER, help='领域参数，原样传给 check 函数')
    return parser


def main(argv: list[str] | None = None) -> int:
    """执行一个 check 并统一输出状态、诊断与退出码。"""
    args = build_parser().parse_args(argv)
    result = invoke(get_check(args.check_id), args.arguments)
    if result.status is CheckStatus.PASS:
        print(f'GATE_RESULT status=PASS check={args.check_id}')
        return 0
    for diagnostic in result.diagnostics:
        print(f'[{args.check_id}] {result.status}: {diagnostic.render()}')
    if result.status is CheckStatus.BLOCKED:
        print(f'GATE_RESULT status=BLOCKED check={args.check_id}')
        return 1
    print(
        f'GATE_RESULT status=FAIL reason={result.reason or "outcome-unknown"} check={args.check_id}'
    )
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
