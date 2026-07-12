"""Check 脚本自感知工具：触发模式匹配与 CLI 参数解析。

每个 check_xxx.py 脚本通过定义 TRIGGER_PATTERNS 来声明「哪些文件变更时我应该运行」，
并使用 parse_check_args() 解析命令行参数。当 changed_files 不匹配 trigger 时，
脚本直接 SKIP 退出（exit 0），无需上层路由做判断。

不负责修复被检查对象；由 Gate executor 或维护者命令行调用。"""

from __future__ import annotations

import argparse
import json
import re
import sys


# 规范化仓库路径。
def _normalize(path: str) -> str:
    """参数：
        path: 待规范化的路径。

    返回：
        规范化后的仓库相对路径。
    """
    value = path.replace('\\', '/')
    while value.startswith('./'):
        value = value[2:]
    return value.strip('/')


# 判断仓库相对路径是否匹配通配模式。
def glob_match(path: str, pattern: str) -> bool:
    """参数：
        path: 待匹配的仓库相对路径。
        pattern: 通配模式。

    返回：
        匹配时返回 true，否则返回 false。
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


# 判断变更文件是否命中触发模式。
def should_run(
    changed_files: list[str] | None,
    trigger_patterns: list[str],
) -> bool:
    """参数：
        changed_files: 变更文件列表；为空时表示全量运行。
        trigger_patterns: 触发模式列表。

    返回：
        全量运行或至少一个文件匹配时返回 true，否则返回 false。
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
        raw: 原始参数值。

    返回：
        解析后的文件列表；未提供内容时返回 None。
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
        parser: 待扩展的命令行解析器。

    返回：
        无返回值。
    """
    parser.add_argument(
        '--changed-files',
        default=None,
        help='JSON array of changed file paths; empty or omitted means run unconditionally.',
    )


# 创建检查脚本的标准命令行解析器并解析参数。
def parse_check_args(
    description: str = '',
    *,
    extra_args: list[tuple[str, dict]] | None = None,
) -> argparse.Namespace:
    """参数：
        description: 命令行解析器说明。
        extra_args: 脚本特有的附加参数定义。

    返回：
        解析后的命令行参数命名空间。
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


# 在变更文件不匹配触发模式时打印跳过原因并退出。
def skip_if_not_triggered(changed_files: list[str] | None, trigger_patterns: list[str]) -> None:
    """参数：
        changed_files: 变更文件列表；为空时表示全量运行。
        trigger_patterns: 触发模式列表。

    返回：
        无返回值。

    异常：
        SystemExit: 变更文件均不匹配时以跳过状态退出。
    """
    if not should_run(changed_files, trigger_patterns):
        print(
            f'[SKIP] no changed files match trigger patterns: {trigger_patterns[:3]}...',
            file=sys.stderr,
        )
        raise SystemExit(SKIP_EXIT_CODE)
