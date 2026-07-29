"""负责调度共享 repository check 并统一输出；不负责实现领域规则；由模块命令行入口调用。"""

from __future__ import annotations

import argparse

from scripts.checks._framework import invoke
from scripts.checks._registry import CHECKS, get_check


def build_parser() -> argparse.ArgumentParser:
    """构造唯一公共参数解析器。"""
    parser = argparse.ArgumentParser(prog='python3 -m scripts.checks')
    parser.add_argument('check_id', choices=sorted(CHECKS))
    parser.add_argument('arguments', nargs=argparse.REMAINDER, help='领域参数，原样传给 check 函数')
    return parser


def main(argv: list[str] | None = None) -> int:
    """执行一个 check 并统一输出状态、诊断与退出码。"""
    args = build_parser().parse_args(argv)
    result = invoke(get_check(args.check_id), args.arguments)
    if result.passed:
        print(f'[{result.check_id}] PASS')
        return 0
    for diagnostic in result.diagnostics:
        print(f'[{result.check_id}] FAIL: {diagnostic.render()}')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
