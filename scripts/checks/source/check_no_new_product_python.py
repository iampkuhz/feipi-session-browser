"""检查退役的产品 Python 目录是否重新出现源码。

这项检查防止已经迁移到 Java 的产品实现回流。公开入口是 ``check(arguments)``，失败表示
``src/session_browser`` 下仍有必须移除的 Python 源码。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from scripts.checks._framework import CheckResult, argument_parser, repository_root

if TYPE_CHECKING:
    from pathlib import Path


def _scan_product_python(repo_root: Path) -> list[str]:
    """列出产品 Python 目录中的源码；目录不存在时视为没有违规。"""
    src_dir = repo_root / "src" / "session_browser"
    if not src_dir.is_dir():
        return []
    results: list[str] = []
    for py_file in sorted(src_dir.rglob("*.py")):
        if "__pycache__" in py_file.parts:
            continue
        rel = py_file.relative_to(repo_root).as_posix()
        results.append(rel)
    return results


def check(arguments: list[str]) -> CheckResult:
    """解析统一入口参数并返回退役目录中的产品 Python 源码诊断。"""
    parser = argument_parser(description="检查退役产品 Python 目录")
    parser.parse_args(arguments)
    return CheckResult.from_errors(
        f"产品 Python 已退役，但文件仍存在: {path}"
        for path in _scan_product_python(repository_root())
    )
