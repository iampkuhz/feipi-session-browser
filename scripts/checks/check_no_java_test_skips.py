#!/usr/bin/env python3
"""检查 Java test result XML 中是否存在 skipped、failed、errored 或 aborted。

不负责修复被检查对象；由 Gate executor 或维护者命令行调用。"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from scripts.checks._framework import argument_parser, repository_root

REPO_ROOT = repository_root()


# 判断模块是否包含 Java/Kotlin 测试源码。
def _has_test_sources(module_root: Path) -> bool:
    """参数：
        module_root: Java 子模块根目录。

    返回：
        存在测试源码时返回 True，否则返回 False。
    """
    for rel in ('src/test/java', 'src/test/kotlin'):
        source_root = module_root / rel
        if not source_root.exists():
            continue
        for path in source_root.rglob('*'):
            if path.is_file() and path.suffix in {'.java', '.kt'}:
                return True
    return False


# 列出包含测试源码的 Java 子模块。
def _test_modules(repo_root: Path) -> list[Path]:
    """参数：
        repo_root: 仓库根目录。

    返回：
        包含测试源码的模块路径列表。
    """
    modules: list[Path] = []
    for build_file in sorted((repo_root / 'java').glob('**/build.gradle.kts')):
        module_root = build_file.parent
        if _has_test_sources(module_root):
            modules.append(module_root)
    return modules


# 读取 testsuite 数值属性，缺失或非法时按 0 处理。
def _int_attr(element: ET.Element, name: str) -> int:
    """参数：
        element: XML 元素。
        name: 属性名。

    返回：
        解析后的整数值。
    """
    try:
        return int(element.attrib.get(name, '0'))
    except ValueError:
        return 0


# 扫描 Java 测试 XML 并返回进程退出码。
def check(repo_root: Path) -> int:
    """参数：
        repo_root: 仓库根目录。

    返回：
        0 表示通过，非 0 表示发现阻塞问题。
    """
    modules = _test_modules(repo_root)
    missing: list[str] = []
    files_found = 0
    total_tests = 0
    total_skipped = 0
    total_failures = 0
    total_errors = 0
    total_aborted = 0
    bad_files: list[str] = []

    for module_root in modules:
        result_dir = module_root / 'build' / 'test-results' / 'test'
        xml_files = sorted(result_dir.glob('TEST-*.xml')) if result_dir.exists() else []
        if not xml_files:
            missing.append(str(module_root.relative_to(repo_root)))
            continue
        for xml_file in xml_files:
            files_found += 1
            try:
                root = ET.parse(xml_file).getroot()
            except ET.ParseError as exc:
                bad_files.append(f'{xml_file.relative_to(repo_root)}: parse error: {exc}')
                total_errors += 1
                continue
            tests = _int_attr(root, 'tests')
            skipped = _int_attr(root, 'skipped')
            failures = _int_attr(root, 'failures')
            errors = _int_attr(root, 'errors')
            content = xml_file.read_text(encoding='utf-8', errors='ignore')
            aborted = 1 if ('aborted' in content.lower() or 'TestAborted' in content) else 0
            total_tests += tests
            total_skipped += skipped
            total_failures += failures
            total_errors += errors
            total_aborted += aborted
            if skipped or failures or errors or aborted:
                bad_files.append(
                    f'{xml_file.relative_to(repo_root)}: tests={tests} failures={failures} '
                    f'errors={errors} skipped={skipped} aborted={aborted}'
                )

    if missing:
        print('Missing Java test result XML for module(s) with test sources:')
        for module in missing[:40]:
            print(f'  {module}')
        if len(missing) > 40:
            print(f'  ... {len(missing) - 40} more')
        return 1
    if files_found > 0 and total_tests == 0:
        print(f'Found 0 Java tests in {files_found} test result XML file(s).')
        return 1
    if bad_files:
        print(
            'Java test XML contains disallowed outcomes: '
            f'failed={total_failures}, errored={total_errors}, '
            f'skipped={total_skipped}, aborted={total_aborted}'
        )
        for item in bad_files[:40]:
            print(f'  {item}')
        if len(bad_files) > 40:
            print(f'  ... {len(bad_files) - 40} more')
        return 1
    print(
        f'noJavaTestSkips: {total_tests} test(s) in {files_found} XML file(s), '
        '0 failed, 0 errored, 0 skipped, 0 aborted.'
    )
    return 0


# 命令行入口。
def main(argv: list[str] | None = None) -> int:
    """参数：
        argv: 可选命令行参数。

    返回：
        进程退出码。
    """
    parser = argument_parser()
    parser.add_argument('--root', default='.', help='repository root')
    args = parser.parse_args(argv)

    return check(Path(args.root).resolve())
