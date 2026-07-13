#!/usr/bin/env python3
"""检查 Java 主源码中是否存在 @SuppressWarnings("PMD.") 压制自定义 PMD 规则。

不负责修复被检查对象；由 Gate executor 或维护者命令行调用。"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from scripts.checks._framework import argument_parser, repository_root

if TYPE_CHECKING:
    from pathlib import Path

REPO_ROOT = repository_root()


# 只扫描主源码，测试源码不在此门禁范围（PMD 也不扫描测试源码）。
SCAN_GLOB = 'java/**/src/main/java/**/*.java'

# 已审批的豁免：文件路径前缀 → 允许的规则。
# 仅当 PMD 无法识别合法模式（如 Java 21 try-with-resources 绑定已有变量）时使用。
ALLOWED_SUPPRESSIONS: dict[str, list[str]] = {
    'java/scan-engine/src/main/java/com/feipi/session/browser/scan/engine/BackgroundScanner.java': [
        'PMD.CloseResource',
    ],
}

# 定义 _PMD_SUPPRESS_RE 常量配置。
_PMD_SUPPRESS_RE = re.compile(r'@SuppressWarnings\s*\(\s*(?:\{[^}]*?)?["\']PMD\.')


# 维护扫描 Java 源码。
def scan_java_sources() -> list[tuple[Path, int, str]]:
    """返回：
    结果列表。
    """
    violations: list[tuple[Path, int, str]] = []
    java_root = REPO_ROOT / 'java'
    if not java_root.exists():
        return violations

    for java_file in java_root.glob('**/src/main/java/**/*.java'):
        rel_path = str(java_file.relative_to(REPO_ROOT))
        # 检查是否在豁免列表中
        allowed_rules = []
        for prefix, rules in ALLOWED_SUPPRESSIONS.items():
            if rel_path == prefix or rel_path.startswith(prefix):
                allowed_rules = rules
                break

        try:
            lines = java_file.read_text(encoding='utf-8').splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in enumerate(lines, start=1):
            if _PMD_SUPPRESS_RE.search(line):
                # 检查是否为已审批的豁免
                if any(rule in line for rule in allowed_rules):
                    continue
                violations.append((java_file.relative_to(REPO_ROOT), lineno, line.strip()))
    return violations


# 解析命令行参数并运行脚本入口。
def main() -> int:
    """返回：
    进程退出码。
    """
    parser = argument_parser(description='检查 Java 主源码中 @SuppressWarnings("PMD.") 的使用')
    parser.parse_args()

    violations = scan_java_sources()
    if not violations:
        return 0

    print(f'FAIL: found {len(violations)} @SuppressWarnings("PMD.") usage(s):')
    for path, lineno, line in violations:
        print(f'  {path}:{lineno}: {line}')
    print()
    print('仓库规约：不使用 @SuppressWarnings 压制自定义 PMD 规则。')
    print('请修复源码以消除 PMD 违规，而非压制规则。')
    return 1
