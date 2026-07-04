#!/usr/bin/env python3
"""提供 检查 no new product python 脚本能力。"""

from __future__ import annotations

import sys
from pathlib import Path

# 定义 _SCRIPT_DIR 常量配置。
_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent.parent


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


# 解析命令行参数并运行脚本入口。
def main() -> int:
    """返回：
        进程退出码。
    """
    repo_root = _REPO_ROOT
    all_py = _scan_product_python(repo_root)

    if all_py:
        print(
            "FAIL: check_no_new_product_python -- "
            f"found {len(all_py)} product Python file(s) in src/session_browser/:",
            file=sys.stderr,
        )
        for v in all_py:
            print(f"  - {v}", file=sys.stderr)
        print(
            "\nPython retirement policy (P40/P43) prohibits product Python.\n"
            "All product functionality has been migrated to Java.\n"
            "Write new functionality in Java instead.",
            file=sys.stderr,
        )
        return 1

    print(
        "PASS: check_no_new_product_python -- "
        "no product Python files found (src/session_browser/ removed)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
