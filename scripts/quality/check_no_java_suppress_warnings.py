#!/usr/bin/env python3
"""检查 Java 主源码中是否存在 @SuppressWarnings("PMD.") 压制自定义 PMD 规则。

仓库规约：不使用 @SuppressWarnings 压制自定义 PMD 规则，遇到违规时直接修复源码。
Java 标准编译器告警（unchecked、deprecation 等）的 @SuppressWarnings 不受此限制。

Exit codes:
    0 — 未发现违规
    1 — 发现 @SuppressWarnings("PMD.") 用法
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# 只扫描主源码，测试源码不在此门禁范围（PMD 也不扫描测试源码）。
SCAN_GLOB = 'java/**/src/main/java/**/*.java'

# 匹配 @SuppressWarnings("PMD.") 或 @SuppressWarnings({"PMD.", ...})
_PMD_SUPPRESS_RE = re.compile(r'@SuppressWarnings\s*\(\s*(?:\{[^}]*?)?["\']PMD\.')


def scan_java_sources() -> list[tuple[Path, int, str]]:
    """扫描 Java 主源码，返回 (文件路径, 行号, 匹配行) 列表。"""
    violations: list[tuple[Path, int, str]] = []
    java_root = REPO_ROOT / 'java'
    if not java_root.exists():
        return violations

    for java_file in java_root.glob('**/src/main/java/**/*.java'):
        try:
            lines = java_file.read_text(encoding='utf-8').splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in enumerate(lines, start=1):
            if _PMD_SUPPRESS_RE.search(line):
                violations.append((java_file.relative_to(REPO_ROOT), lineno, line.strip()))
    return violations


def main() -> int:
    violations = scan_java_sources()
    if not violations:
        print(f'PASS: no @SuppressWarnings("PMD.") found in main sources')
        return 0

    print(f'FAIL: found {len(violations)} @SuppressWarnings("PMD.") usage(s):')
    for path, lineno, line in violations:
        print(f'  {path}:{lineno}: {line}')
    print()
    print('仓库规约：不使用 @SuppressWarnings 压制自定义 PMD 规则。')
    print('请修复源码以消除 PMD 违规，而非压制规则。')
    return 1


if __name__ == '__main__':
    sys.exit(main())
