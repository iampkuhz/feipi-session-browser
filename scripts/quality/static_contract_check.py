#!/usr/bin/env python3
"""静态资源契约检查。

Exit 1 仅针对真正阻塞性问题（!important、load order、dead CSS、duplicate base CSS 等）。
position: fixed、payload-modal ownership、shell ownership 作为警告输出，不阻塞提交。

纯函数拆出以支持单测：
- check_no_important(css_files)
- check_css_load_order(base_html_text)
- check_no_dead_css(css_files)
- check_no_duplicate_base_css(html_files)
- check_payload_modal_ownership(css_files) -> (errors, warnings)
- check_shell_ownership(css_files)
- check_innerhtml_safety(js_files)
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


def check_no_duplicate_base_css(html_files: list[Path]) -> list[str]:
    """检查页面模板是否重复加载 base 已加载的 CSS。BLOCK。

    base.html 已经加载 tokens.css、base.css、shell.css、ui-primitives.css、legacy-aliases.css，
    页面模板不得在 head_extra 或其他位置重复 link 这些文件。
    """
    errors: list[str] = []
    base_names = {"tokens.css", "base.css", "shell.css", "ui-primitives.css", "legacy-aliases.css"}
    for path in html_files:
        text = path.read_text(encoding="utf-8", errors="replace")
        # 排除 base.html 自身
        if path.name == "base.html":
            continue
        # 找出所有 stylesheet link 的 href
        links = re.findall(r'href="([^"]*\.css[^"]*)"', text)
        found_duplicates = []
        for link in links:
            basename = link.split("/")[-1].split("?")[0]
            if basename in base_names:
                found_duplicates.append(basename)
        if found_duplicates:
            errors.append(
                f"{path}: 页面模板重复加载 base 已加载的 CSS: {', '.join(sorted(set(found_duplicates)))}。"
            )
    return errors


def check_css_load_order(base_html_text: str) -> list[str]:
    """检查 base.html 中 CSS link 顺序是否符合 contract。BLOCK。

    期望顺序：
    1. /static/css/tokens.css
    2. /static/css/base.css
    3. /static/css/shell.css
    4. /static/css/ui-primitives.css
    5. /static/css/legacy-aliases.css
    6. {% block head_extra %}
    """
    errors: list[str] = []
    expected = [
        "/static/css/tokens.css",
        "/static/css/base.css",
        "/static/css/shell.css",
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


def check_payload_modal_ownership(css_files: list[Path]) -> tuple[list[str], list[str]]:
    """检查 payload-modal 裸定义的位置。

    权威来源应为 ui-primitives.css。
    - legacy-aliases.css 作为兼容层允许存在（WARN）
    - 其他页面 CSS 出现裸定义时 BLOCK
    - 不以 page-contract 前缀开头的定义视为裸定义
    """
    errors: list[str] = []
    warnings: list[str] = []
    # Bare .payload-modal or #payload-modal selector at start of a CSS rule (not in comments, not with modifier suffix, not page-specific sd- prefix)
    bare_pattern = re.compile(
        r"^(?!\s*/\*|\s*\*|\s*\.session-detail-page|\s*\.sd-page|\s*\.sd-shell|\s*\.sd-payload-modal)"
        r"\s*(?:\.payload-modal\b(?![-_:\s]*--)|#payload-modal\b)",
        re.MULTILINE,
    )
    for path in css_files:
        rel = path.relative_to(path.parent.parent.parent.parent).as_posix() if path.parent.name == "css" else path.name
        name = path.name
        # 权威来源跳过
        if name in ("ui-primitives.css", "tokens.css", "base.css"):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        matches = bare_pattern.findall(text)
        if not matches:
            continue
        # legacy-aliases.css 作为兼容层允许，只 WARN
        if name == "legacy-aliases.css":
            warnings.append(
                f"{path}: payload-modal 兼容层定义（{len(matches)} 处），计划后续删除。"
            )
        else:
            errors.append(
                f"{path}: 禁止裸 payload-modal 定义（{len(matches)} 处），应收敛至 ui-primitives.css。"
            )
    return errors, warnings


def check_shell_ownership(css_files: list[Path]) -> list[str]:
    """检查 page CSS 是否出现 shell 级选择器。WARN。

    shell 层选择器（.app-shell, .shell, body.hide-left 等）应由专属 shell.css 定义，
    页面 CSS 不应覆盖。
    历史存在可以 WARN；新增应在后续 diff gate 中 BLOCK。
    """
    warnings: list[str] = []
    shell_selectors = [
        ".app-shell", ".shell", ".phase1-shell",
        "body.hide-left", "body.hide-right", "body.focus",
    ]
    # 豁免文件：shell.css（当前 shell 权威）、base.css（基础样式）、legacy-aliases.css（兼容层）、tokens.css（设计令牌）
    exempt = {"shell.css", "base.css", "legacy-aliases.css", "tokens.css"}
    for path in css_files:
        name = path.name
        if name in exempt:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        found = []
        for sel in shell_selectors:
            if sel in text:
                found.append(sel)
        if found:
            warnings.append(
                f"{path}: 包含 shell 级选择器: {', '.join(found)}，应归属 shell.css。"
            )
    return warnings


def check_innerhtml_safety(js_files: list[Path]) -> list[str]:
    """检查 JS 文件中 innerHTML 使用是否配套 sanitize/escape helper。WARN。

    规则：
    - 如果文件中出现 innerHTML，但没有 escapeHtml/sanitize/safeRender 等 helper，WARN。
    - BLOCK 留到后续 Sprint。
    """
    warnings: list[str] = []
    safety_patterns = re.compile(
        r'\bescapeHtml\b|\bsanitize\b|\bsafeRender\b|\bsafeHtml\b'
        r'|\bDOMPurify\b|\bcreateContextualFragment\b',
        re.IGNORECASE,
    )
    for path in js_files:
        text = path.read_text(encoding="utf-8", errors="replace")
        if 'innerHTML' not in text:
            continue
        if safety_patterns.search(text):
            continue  # has safety helper, OK
        # Find lines with innerHTML for detailed warning
        lines_with_inner = []
        for lineno, line in enumerate(text.splitlines(), 1):
            if 'innerHTML' in line:
                stripped = line.strip()
                # skip clearing innerHTML = ''
                if "''" not in stripped and '""' not in stripped:
                    lines_with_inner.append(lineno)
        if lines_with_inner:
            line_info = ', '.join(f'L{n}' for n in lines_with_inner[:5])
            if len(lines_with_inner) > 5:
                line_info += f' +{len(lines_with_inner) - 5} more'
            warnings.append(
                f"{path}: innerHTML 使用未见 sanitize/escape helper（{line_info}），建议后续 Sprint 治理。"
            )
    return warnings


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

    # BLOCK: no-duplicate-base-css
    templates = static.parent / "templates"
    if templates.exists():
        html_files = list(templates.rglob("*.html"))
        errors.extend(check_no_duplicate_base_css(html_files))

    # BLOCK: payload-modal ownership (new violations), WARN: legacy aliases
    pm_errors, pm_warnings = check_payload_modal_ownership(css_files)
    errors.extend(pm_errors)
    warnings.extend(pm_warnings)

    # WARN: shell ownership
    warnings.extend(check_shell_ownership(css_files))

    # WARN: innerHTML safety (replaces old inline JS safety check)
    warnings.extend(check_innerhtml_safety(js_files))
    for path in css_files:
        rel = path.relative_to(repo_root).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        if re.search(r"position\s*:\s*fixed", text):
            if "modal" not in rel.lower() and rel not in (
                "src/session_browser/web/static/css/session-detail.css",
                "src/session_browser/web/static/css/ui-primitives.css",
            ):
                warnings.append(f"{rel}: fixed 布局需确认是否符合桌面端 contract。")

    # BLOCK: eval is forbidden
    for path in js_files:
        rel = path.relative_to(repo_root).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        if "eval(" in text:
            errors.append(f"{rel}: 禁止 eval。")

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
