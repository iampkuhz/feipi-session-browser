#!/usr/bin/env python3
"""静态资源契约检查。

Exit 1 仅针对真正阻塞性问题（!important 等）。
position: fixed 和 innerHTML 作为警告输出，不阻塞提交。
"""
from __future__ import annotations

from pathlib import Path
import re


def check_static(repo_root: Path) -> tuple[list[str], list[str]]:
    """返回 (errors, warnings)。"""
    errors: list[str] = []
    warnings: list[str] = []
    static = repo_root / "src/session_browser/web/static"
    if not static.exists():
        return [f"静态资源目录不存在：{static}"], []

    for path in list(static.rglob("*.css")) + list(static.rglob("*.js")):
        text = path.read_text(encoding="utf-8", errors="replace")
        rel = path.relative_to(repo_root).as_posix()

        if path.suffix == ".css":
            if re.search(r"!important", text):
                errors.append(f"{rel}: 避免新增 !important，除非有明确 contract 说明。")
            if re.search(r"position\s*:\s*fixed", text):
                if "modal" not in rel.lower() and rel not in (
                    "src/session_browser/web/static/css/session-detail.css",
                    "src/session_browser/web/static/css/ui-primitives.css",
                ):
                    warnings.append(f"{rel}: fixed 布局需确认是否符合桌面端 contract。")

        if path.suffix == ".js":
            if "eval(" in text:
                errors.append(f"{rel}: 禁止 eval。")
            if "innerHTML" in text and "sanitize" not in text.lower():
                warnings.append(f"{rel}: innerHTML 需要 sanitize 或 contract 说明。")
    return errors, warnings


def main() -> int:
    errors, warnings = check_static(Path.cwd())
    for item in warnings:
        print(f"[WARN] {item}")
    if errors:
        for item in errors:
            print(item)
        return 1
    print("static contract PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
