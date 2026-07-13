#!/usr/bin/env python3
"""提供 检查 no new product python 脚本能力。

不负责修复被检查对象；由 Gate executor 或维护者命令行调用。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from scripts.checks._framework import repository_root

if TYPE_CHECKING:
    from pathlib import Path


# 维护扫描 产品 Python。
def _scan_product_python(repo_root: Path) -> list[str]:
    """参数：
        repo_root: 仓库根目录。

    返回：
        结果列表。
    """
    src_dir = repo_root / "src" / "session_browser"
    if not src_dir.is_dir():
        return []
    results: list[str] = []
    for py_file in sorted(src_dir.rglob("*.py")):
        # 判断 "__pycache__" in py_file.parts 是否满足。
        if "__pycache__" in py_file.parts:
            continue
        rel = py_file.relative_to(repo_root).as_posix()
        results.append(rel)
    return results


def check_product_python() -> list[str]:
    """返回退役目录中残留的产品 Python 源码。"""
    return [
        f"产品 Python 已退役，但文件仍存在: {path}"
        for path in _scan_product_python(repository_root())
    ]
