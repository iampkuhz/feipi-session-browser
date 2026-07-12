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


def _normalize(path: str) -> str:
    """规范化 repo 路径。"""
    value = path.replace('\\', '/')
    while value.startswith('./'):
        value = value[2:]
    return value.strip('/')


def glob_match(path: str, pattern: str) -> bool:
    """判断 repo-relative 路径是否匹配 glob pattern。"""
    p = _normalize(path)
    pat = _normalize(pattern)
    regex = re.escape(pat)
    regex = regex.replace(r'\*\*', '\x00')
    regex = regex.replace(r'\*', '[^/]*')
    regex = regex.replace(r'\?', '.')
    regex = regex.replace('\x00/', '(?:.+/)?')
    regex = regex.replace('\x00', '.*')
    return bool(re.match(f'^{regex}$', p))


def should_run(
    changed_files: list[str] | None,
    trigger_patterns: list[str],
) -> bool:
    """判断 changed_files 中是否有文件命中 trigger_patterns。

    - changed_files 为 None 或空列表时返回 True（全量运行）。
    - 有 changed_files 但至少一个匹配时返回 True。
    - 全部不匹配时返回 False（SKIP）。
    """
    if not changed_files:
        return True
    for f in changed_files:
        if any(glob_match(f, pat) for pat in trigger_patterns):
            return True
    return False


def parse_changed_files(raw: str | None) -> list[str] | None:
    """解析 --changed-files 参数值。

    - None → 返回 None（全量运行）
    - JSON 数组字符串 → 解析后的列表
    - 空字符串 → 返回 None
    """
    if raw is None:
        return None
    raw = raw.strip()
    if not raw:
        return None
    return json.loads(raw)


def add_changed_files_arg(parser: argparse.ArgumentParser) -> None:
    """向 argparse parser 添加 --changed-files 参数。"""
    parser.add_argument(
        '--changed-files',
        default=None,
        help='JSON array of changed file paths; empty or omitted means run unconditionally.',
    )


def parse_check_args(
    description: str = '',
    *,
    extra_args: list[tuple[str, dict]] | None = None,
) -> argparse.Namespace:
    """为 check 脚本创建标准 argparse 解析器并解析参数。

    所有 check 脚本统一支持 --changed-files；extra_args 可追加脚本特有参数。
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


def skip_if_not_triggered(changed_files: list[str] | None, trigger_patterns: list[str]) -> None:
    """如果 changed_files 不匹配 trigger_patterns，打印 SKIP 并退出。

    在 check 脚本的 main() 开头调用即可实现自感知跳过。
    """
    if not should_run(changed_files, trigger_patterns):
        print(
            f'[SKIP] no changed files match trigger patterns: {trigger_patterns[:3]}...',
            file=sys.stderr,
        )
        raise SystemExit(SKIP_EXIT_CODE)
