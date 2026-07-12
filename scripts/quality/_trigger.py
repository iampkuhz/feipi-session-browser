"""Check 脚本自感知工具：触发模式匹配与 CLI 参数解析。

每个 check_xxx.py 脚本通过定义 TRIGGER_PATTERNS 来声明「哪些文件变更时我应该运行」，
并使用 parse_check_args() 解析命令行参数。当 changed_files 不匹配 trigger 时，
脚本直接 SKIP 退出（exit 0），无需上层路由做判断。
"""

from __future__ import annotations

import argparse
import json
import re
import sys


# 规范化仓库路径。
def _normalize(path: str) -> str:
    """参数：
        path: 当前函数使用的输入参数。

    返回：
        当前函数的计算结果。
    """
    value = path.replace('\\', '/')
    while value.startswith('./'):
        value = value[2:]
    return value.strip('/')


# 判断仓库相对路径是否匹配通配规则。
def glob_match(path: str, pattern: str) -> bool:
    """参数：
        path: 当前函数使用的输入参数。
        pattern: 当前函数使用的输入参数。

    返回：
        当前函数的计算结果。
    """
    p = _normalize(path)
    pat = _normalize(pattern)
    regex = re.escape(pat)
    regex = regex.replace(r'\*\*', '\x00')
    regex = regex.replace(r'\*', '[^/]*')
    regex = regex.replace(r'\?', '.')
    regex = regex.replace('\x00/', '(?:.+/)?')
    regex = regex.replace('\x00', '.*')
    return bool(re.match(f'^{regex}$', p))


# 判断变更文件中是否有路径命中触发规则。
def should_run(
    changed_files: list[str] | None,
    trigger_patterns: list[str],
) -> bool:
    """参数：
        changed_files: 当前函数使用的输入参数。
        trigger_patterns: 当前函数使用的输入参数。

    返回：
        当前函数的计算结果。
    """
    if not changed_files:
        return True
    for f in changed_files:
        if any(glob_match(f, pat) for pat in trigger_patterns):
            return True
    return False


# 解析变更文件参数值。
def parse_changed_files(raw: str | None) -> list[str] | None:
    """参数：
        raw: 当前函数使用的输入参数。

    返回：
        当前函数的计算结果。
    """
    if raw is None:
        return None
    raw = raw.strip()
    if not raw:
        return None
    return json.loads(raw)


# 向命令行解析器添加变更文件参数。
def add_changed_files_arg(parser: argparse.ArgumentParser) -> None:
    """参数：
        parser: 当前函数使用的输入参数。

    返回：
        当前函数的计算结果。
    """
    parser.add_argument(
        '--changed-files',
        default=None,
        help='JSON array of changed file paths; empty or omitted means run unconditionally.',
    )


# 为检查脚本创建标准命令行解析器并解析参数。
def parse_check_args(
    description: str = '',
    *,
    extra_args: list[tuple[str, dict]] | None = None,
) -> argparse.Namespace:
    """参数：
        description: 当前函数使用的输入参数。
        extra_args: 当前函数使用的输入参数。

    返回：
        当前函数的计算结果。
    """
    parser = argparse.ArgumentParser(description=description)
    add_changed_files_arg(parser)
    if extra_args:
        for name, kwargs in extra_args:
            parser.add_argument(name, **kwargs)
    return parser.parse_args()


SKIP_EXIT_CODE = 0
PASS_EXIT_CODE = 0
FAIL_EXIT_CODE = 1


# 变更文件未命中触发规则时输出未触发结果并退出。
def skip_if_not_triggered(changed_files: list[str] | None, trigger_patterns: list[str]) -> None:
    """参数：
        changed_files: 当前函数使用的输入参数。
        trigger_patterns: 当前函数使用的输入参数。

    返回：
        当前函数的计算结果。
    """
    if not should_run(changed_files, trigger_patterns):
        print(
            f'[SKIP] no changed files match trigger patterns: {trigger_patterns[:3]}...',
            file=sys.stderr,
        )
        raise SystemExit(SKIP_EXIT_CODE)
