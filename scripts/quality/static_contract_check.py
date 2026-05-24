#!/usr/bin/env python3
"""静态资源契约检查。

Exit 1 仅针对真正阻塞性问题（!important、load order、dead CSS 等）。
position: fixed 和 innerHTML 作为警告输出，不阻塞提交。

纯函数拆出以支持单测：
- check_no_important(css_files)
- check_css_load_order(base_html_text)
- check_no_dead_css(css_files)
"""
from __future__ import annotations

from pathlib import Path
import re


# ── Pure functions ─────────────────────────────────────────────────────


def check_no_important(css_files: list[Path]) -> list[str]:
    """检查 CSS 文件中是否有 !important。BLOCK。"""
    errors: list[str] = []
    for path in css_files:
        text = path.read_text(encoding="utf-8", errors="replace")
        if re.search(r"!important", text):
            errors.append(f"{path}: 禁止 !important（contract: payload-modal-contract）。")
    return errors


def check_css_load_order(base_html_text: str) -> list[str]:
    """检查 base.html 中 CSS link 顺序是否符合 contract。BLOCK。

    期望顺序：
    1. /static/style.css
    2. /static/css/ui-primitives.css
    3. /static/css/legacy-aliases.css
    4. {% block head_extra %}
    """
    errors: list[str] = []
    expected = [
        "/static/style.css",
        "/static/css/ui-primitives.css",
        "/static/css/legacy-aliases.css",
        "{% block head_extra %}",
    ]

    positions: list[int] = []
    for item in expected:
        idx = base_html_text.find(item)
        if idx == -1:
            errors.append(f"css-load-order-contract: 缺失必需项 '{item}'")
            return errors
        positions.append(idx)

    for i in range(len(positions) - 1):
        if positions[i] >= positions[i + 1]:
            errors.append(
                f"css-load-order-contract: '{expected[i]}' 必须在 "
                f"'{expected[i+1]}' 之前加载（位置 {positions[i]} vs {positions[i+1]}）。"
            )

    return errors


def check_no_dead_css(css_files: list[Path]) -> list[str]:
    """检查是否存在 0 有效规则的 CSS 文件。BLOCK。

    去掉注释和空白后，如果没有 '{' 和 '}'，判定为 dead CSS。
    """
    errors: list[str] = []
    for path in css_files:
        text = path.read_text(encoding="utf-8", errors="replace")
        # 去掉 CSS 注释
        stripped = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
        # 去掉空白
        stripped = stripped.strip()
        if not stripped:
            errors.append(f"{path}: 死 CSS 文件（只有注释或空白，无有效规则）。")
        elif "{" not in stripped and "}" not in stripped:
            errors.append(f"{path}: 死 CSS 文件（无 CSS rule body）。")
    return errors


# ── Composite check ────────────────────────────────────────────────────


def check_static(repo_root: Path) -> tuple[list[str], list[str]]:
    """返回 (errors, warnings)。"""
    errors: list[str] = []
    warnings: list[str] = []
    static = repo_root / "src/session_browser/web/static"
    if not static.exists():
        return [f"静态资源目录不存在：{static}"], []

    css_files = list(static.rglob("*.css"))
    js_files = list(static.rglob("*.js"))

    # BLOCK: no-important
    errors.extend(check_no_important(css_files))

    # BLOCK: css-load-order-contract
    base_html = static.parent / "templates" / "base.html"
    if base_html.exists():
        errors.extend(check_css_load_order(base_html.read_text(encoding="utf-8")))
    else:
        errors.append(f"css-load-order-contract: base.html 不存在：{base_html}")

    # BLOCK: no-dead-css-file
    errors.extend(check_no_dead_css(css_files))

    # WARN: position:fixed (non-blocking)
    for path in css_files:
        rel = path.relative_to(repo_root).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        if re.search(r"position\s*:\s*fixed", text):
            if "modal" not in rel.lower() and rel not in (
                "src/session_browser/web/static/css/session-detail.css",
                "src/session_browser/web/static/css/ui-primitives.css",
            ):
                warnings.append(f"{rel}: fixed 布局需确认是否符合桌面端 contract。")

    # WARN/BLOCK: JS safety
    for path in js_files:
        rel = path.relative_to(repo_root).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        if "eval(" in text:
            errors.append(f"{rel}: 禁止 eval。")
        if "innerHTML" in text and "sanitize" not in text.lower():
            warnings.append(f"{rel}: innerHTML 需要 sanitize 或 contract 说明。")

    return errors, warnings


# ── CLI ────────────────────────────────────────────────────────────────


def main() -> int:
    errors, warnings = check_static(Path.cwd())
    for item in warnings:
        print(f"[WARN] {item}")
    if errors:
        for item in errors:
            print(f"[BLOCK] {item}")
        return 1
    print("static contract PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
