#!/usr/bin/env python3
"""CSS 所有权门禁检查。

基于本脚本内的当前职责边界，检查：

1. 层纯度：tokens/base 层是否包含越权选择器
2. 跨层重复定义：页面 CSS 是否重写 ui-primitives 中的全局组件
3. 依赖方向：低层 CSS 是否反向引用页面级选择器
4. 硬编码颜色：页面 CSS 是否绕过 token 变量

用法:
    python3 scripts/quality/check_css_ownership.py

退出码:
    0 — 无 BLOCK 级违规（可能有 WARN）
    1 — 存在 BLOCK 级违规
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path


# ── 数据结构 ─────────────────────────────────────────────────────────────


@dataclass
class Violation:
    severity: str   # "BLOCK" | "WARN"
    rule: str       # 规则标识
    file: str       # CSS 文件名
    detail: str     # 违规描述
    line: int | None = None


@dataclass
class OwnershipCheck:
    blocks: list[Violation] = field(default_factory=list)
    warnings: list[Violation] = field(default_factory=list)
    files_scanned: int = 0
    selectors_analyzed: int = 0


# ── 所有权配置 ───────────────────────────────────────────────────────


# ui-primitives.css 中定义的全局组件（页面 CSS 不得直接重写）
# 这些选择器在 ui-primitives 中有权威定义，页面 CSS 如需定制应使用
# 后代选择器（如 .sessions-page .card）或页面特有前缀（如 .sd-btn--*）
GLOBAL_COMPONENTS = {
    ".btn", ".ui-btn",
    ".icon-btn", ".icon-button",
    ".badge",
    ".card", ".section", ".section-head",
    ".metric-card", ".metric-grid",
    ".tooltip",
    ".popover", ".menu-popover",
    ".data-table",
    ".filter-card", ".filter-chip",
    ".pagination",
    ".modal", ".payload-modal",
    ".state-strip",
    ".toast",
    ".page-head",
    ".tabs", ".tab-nav", ".tab-btn",
    ".pill",
    ".avatar",
}

# 页面 CSS 可以合法使用的共享基础选择器（不属于组件重定义）
SHARED_BASE_SELECTORS = {
    ":root",
}

# 豁免文件：这些文件不受跨层重复检查约束
EXEMPT_FROM_DUPLICATE = {
    "tokens.css", "base.css", "shell.css", "ui-primitives.css",
}


# ── CSS 解析工具 ─────────────────────────────────────────────────────────


def extract_css_rules(text: str) -> list[tuple[int, str, str]]:
    """提取 CSS 规则，返回 (行号, 选择器, 声明块) 列表。

    处理 @media / @supports 嵌套。
    """
    rules: list[tuple[int, str, str]] = []
    # 去掉注释
    stripped = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    lines = text.splitlines()

    # 字符 → 行号映射
    char_to_line: dict[int, int] = {}
    pos = 0
    for i, line in enumerate(lines, 1):
        for _ in range(len(line) + 1):
            char_to_line[pos] = i
            pos += 1

    # 栈式解析：处理嵌套块
    stack: list[tuple[str, int]] = []
    i = 0
    while i < len(stripped):
        if stripped[i] == "{":
            selector_start = i
            while selector_start > 0 and stripped[selector_start - 1] not in "{};":
                selector_start -= 1
            selector = stripped[selector_start:i].strip()
            stack.append((selector, selector_start))
        elif stripped[i] == "}" and stack:
            selector, start = stack.pop()
            body = stripped[start + 1:i].strip()
            line_no = char_to_line.get(start, 0)
            if line_no > 0:
                rules.append((line_no, selector, body))
        i += 1

    return rules


def split_selectors(selector_str: str) -> list[str]:
    """按逗号拆分选择器，避开 :not() 等函数内的逗号。"""
    depth = 0
    parts: list[str] = []
    current: list[str] = []
    for ch in selector_str:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
    if current:
        parts.append("".join(current).strip())
    return [p for p in parts if p and not p.startswith("@")]


def is_base_selector(sel: str) -> bool:
    """判断是否为 HTML 基础元素选择器。"""
    base_pattern = re.compile(
        r"^(html|body|div|span|p|a|img|ul|ol|li|table|th|td|thead|tbody|tfoot|"
        r"tr|h[1-6]|pre|code|blockquote|hr|input|button|textarea|select|form|"
        r"label|fieldset|legend|optgroup|option|datalist|output|progress|meter|"
        r"details|summary|dialog|main|header|footer|nav|article|section|aside|"
        r"figure|figcaption|canvas|svg|video|audio|source|track|embed|iframe|"
        r"object|param|map|area|link|meta|style|script|noscript|template|"
        r"slot|br|wbr|del|ins|s|u|b|i|em|strong|small|sub|sup|mark|abbr|"
        r"cite|dfn|data|time|kbd|var|samp|q|bdi|bdo|ruby|rt|rp)\b"
    )
    return bool(base_pattern.match(sel))


# ── 检查函数 ─────────────────────────────────────────────────────────────


def check_layer_purity(
    filename: str,
    rules: list[tuple[int, str, str]],
) -> list[Violation]:
    """检查 1: 层纯度 — tokens/base/shell 是否包含越权选择器。"""
    violations: list[Violation] = []

    if filename == "tokens.css":
        # tokens.css 只应有 :root 包裹的自定义属性声明
        for lineno, selector, body in rules:
            if selector.startswith("@"):
                continue
            # :root 包裹是合法的
            if selector == ":root":
                continue
            violations.append(Violation(
                severity="BLOCK",
                rule="layer-purity",
                file=filename,
                line=lineno,
                detail=f"tokens.css 不得包含选择器规则：'{selector[:100]}'",
            ))

    elif filename == "base.css":
        # base.css 只允许：通配符、HTML 元素、伪类、:root、@media、@property
        for lineno, selector, body in rules:
            if selector.startswith("@"):
                continue
            for sel in split_selectors(selector):
                sel = sel.strip()
                if not sel:
                    continue
                if sel in SHARED_BASE_SELECTORS:
                    continue
                if sel.startswith(":root"):
                    continue
                if is_base_selector(sel):
                    continue
                # 伪类/伪元素
                if sel.startswith(":") and not any(c in sel for c in ".#"):
                    continue
                # 通配符
                if sel.startswith("*"):
                    continue
                # body/HTML 的复合选择器
                if sel.startswith("body") or sel.startswith("html"):
                    continue
                violations.append(Violation(
                    severity="BLOCK",
                    rule="layer-purity",
                    file=filename,
                    line=lineno,
                    detail=f"base.css 包含非元素选择器：'{sel[:100]}'",
                ))

    elif filename == "shell.css":
        # shell.css 不应包含页面内组件（按钮、卡片等）
        for lineno, selector, body in rules:
            if selector.startswith("@"):
                continue
            for sel in split_selectors(selector):
                sel = sel.strip()
                if not sel:
                    continue
                # 检查是否包含页面级选择器
                page_pats = [
                    r"\.sessions-page\b", r"\.session-detail-page\b",
                    r"\.dashboard-page\b", r"\.projects-page\b",
                    r"\.agents-page\b", r"\.glossary-page\b",
                ]
                if any(re.search(p, sel) for p in page_pats):
                    violations.append(Violation(
                        severity="BLOCK",
                        rule="layer-purity",
                        file=filename,
                        line=lineno,
                        detail=f"shell.css 包含页面级选择器：'{sel[:100]}'",
                    ))

    elif filename == "ui-primitives.css":
        # ui-primitives 不应包含页面级选择器
        for lineno, selector, body in rules:
            if selector.startswith("@"):
                continue
            for sel in split_selectors(selector):
                sel = sel.strip()
                if not sel:
                    continue
                page_pats = [
                    r"\.sessions-page\b", r"\.session-detail-page\b",
                    r"\.sd-shell\b", r"\.sd-page\b",
                    r"\.dashboard-page\b", r"\.projects-page\b",
                    r"\.agents-page\b", r"\.glossary-page\b",
                ]
                if any(re.search(p, sel) for p in page_pats):
                    violations.append(Violation(
                        severity="BLOCK",
                        rule="layer-purity",
                        file=filename,
                        line=lineno,
                        detail=f"ui-primitives.css 包含页面级选择器：'{sel[:100]}'",
                    ))

    return violations


def check_cross_layer_duplicate(
    filename: str,
    rules: list[tuple[int, str, str]],
    ui_primitives_selectors: set[str],
) -> list[Violation]:
    """检查 2: 跨层重复定义 — 页面 CSS 是否直接重写全局组件。

    核心规则：
    - 如果 ui-primitives.css 已定义了某个全局组件（如 .btn, .card），
      页面 CSS 不得以相同选择器直接重写。
    - 后代选择器（如 .sessions-page .card）是合法的。
    - 页面特有变体（如 .sd-btn--*, .sd-pill--*）是合法的。

    注意：此检查首次引入时设为 WARN 级别，因为现有页面 CSS 中
    存在历史遗留的跨层重复定义。后续迭代治理后应升级为 BLOCK。
    """
    violations: list[Violation] = []

    if filename in EXEMPT_FROM_DUPLICATE:
        return violations

    for lineno, selector, body in rules:
        if selector.startswith("@"):
            continue
        for sel in split_selectors(selector):
            sel = sel.strip()
            if not sel:
                continue
            # 检查选择器是否为全局组件的直接重写
            for comp in GLOBAL_COMPONENTS:
                # 精确匹配：选择器就是全局组件名
                if sel == comp:
                    violations.append(Violation(
                        severity="WARN",
                        rule="cross-layer-duplicate",
                        file=filename,
                        line=lineno,
                        detail=f"{filename} 直接重写全局组件 '{comp}'（已在 ui-primitives.css 定义），"
                               f"应使用后代选择器或页面特有变体",
                    ))
                    break
                # 复合选择器中以全局组件开头且非后代选择器
                # 例如 ".btn.primary" 是修饰符变体（合法），
                # 但 ".btn" 直接重写不是
                if sel.startswith(comp + ".") or sel.startswith(comp + ":"):
                    # 修饰符变体（如 .btn--primary, .btn:hover）是合法的
                    pass
                # 后代选择器：以页面级选择器开头，合法

    return violations


def check_dependency_direction(
    filename: str,
    rules: list[tuple[int, str, str]],
) -> list[Violation]:
    """检查 3: 依赖方向 — 低层不得反向引用页面级选择器。

    注意：`.sd-shell` 等页面外壳选择器是合法的 shell 层规则，
    它们属于页面骨架而非页面内容，不归为页面级选择器。
    """
    violations: list[Violation] = []

    low_level = {"tokens.css", "base.css", "shell.css", "ui-primitives.css"}
    if filename not in low_level:
        return violations

    # 排除 shell 级选择器（如 .sd-shell 是 session-detail 的外壳包装器）
    shell_wrappers = {
        r"\.sd-shell\b",       # session-detail 外壳
        r"\.sd-page\b",        # session-detail 页面容器
        r"\.sd-content\b",     # session-detail 内容区
    }

    # 真正的页面内容选择器（不应在低层出现）
    page_patterns = [
        r"\.sessions-page\b", r"\.session-detail-page\b",
        r"\.dashboard-page\b", r"\.projects-page\b",
        r"\.agents-page\b", r"\.glossary-page\b",
        r"\.state-panel\b",
    ]

    for lineno, selector, body in rules:
        if selector.startswith("@"):
            continue
        # 跳过 shell 级包装器选择器
        if filename == "shell.css" and any(re.search(p, selector) for p in shell_wrappers):
            continue
        for pat in page_patterns:
            if re.search(pat, selector):
                violations.append(Violation(
                    severity="WARN",
                    rule="dependency-direction",
                    file=filename,
                    line=lineno,
                    detail=f"{filename} 反向引用页面级选择器：'{selector[:100]}' "
                           f"（依赖方向应为 page -> ui-primitives -> shell -> base -> tokens）",
                ))
                break

    return violations


def check_hardcoded_colors(
    filename: str,
    rules: list[tuple[int, str, str]],
) -> list[Violation]:
    """检查 4: 硬编码颜色 — 页面 CSS 应优先使用 token 变量。"""
    violations: list[Violation] = []

    # 豁免：tokens 是颜色定义源，base/shell/ui-primitives 可以有基础色
    if filename in ("tokens.css", "base.css", "shell.css", "ui-primitives.css"):
        return violations

    hex_color = re.compile(r"(?<![a-zA-Z])#[0-9a-fA-F]{3,8}\b")
    safe_colors = {"#000", "#000000", "#fff", "#ffffff"}

    for lineno, selector, body in rules:
        matches = hex_color.findall(body)
        for color in matches:
            if color.lower() not in safe_colors:
                violations.append(Violation(
                    severity="WARN",
                    rule="hardcoded-color",
                    file=filename,
                    line=lineno,
                    detail=f"{filename} 使用硬编码颜色 '{color}'（选择器: '{selector[:60]}...'），"
                           f"建议使用 token 变量",
                ))

    return violations


# ── 入口 ─────────────────────────────────────────────────────────────────


def check_css_ownership(repo_root: Path) -> OwnershipCheck:
    """执行 CSS 所有权检查。"""
    result = OwnershipCheck()
    css_dir = repo_root / "src/session_browser/web/static/css"

    if not css_dir.exists():
        result.blocks.append(Violation(
            severity="BLOCK",
            rule="missing-dir",
            file="N/A",
            detail=f"CSS 目录不存在：{css_dir}",
        ))
        return result

    css_files = sorted(css_dir.glob("*.css"))
    result.files_scanned = len(css_files)

    # 预扫描 ui-primitives 中的顶级选择器
    ui_primitives_selectors: set[str] = set()
    ui_primitives_path = css_dir / "ui-primitives.css"
    if ui_primitives_path.exists():
        text = ui_primitives_path.read_text(encoding="utf-8")
        for _, selector, _ in extract_css_rules(text):
            for sel in split_selectors(selector):
                ui_primitives_selectors.add(sel.strip())

    # 逐文件检查
    for css_path in css_files:
        filename = css_path.name
        text = css_path.read_text(encoding="utf-8")
        rules = extract_css_rules(text)
        result.selectors_analyzed += len(rules)

        # 检查 1: 层纯度
        result.blocks.extend(check_layer_purity(filename, rules))

        # 检查 2: 跨层重复定义（按 severity 分流）
        for v in check_cross_layer_duplicate(filename, rules, ui_primitives_selectors):
            (result.blocks if v.severity == "BLOCK" else result.warnings).append(v)

        # 检查 3: 依赖方向（按 severity 分流）
        for v in check_dependency_direction(filename, rules):
            (result.blocks if v.severity == "BLOCK" else result.warnings).append(v)

        # 检查 4: 硬编码颜色
        result.warnings.extend(check_hardcoded_colors(filename, rules))

    return result


def format_report(result: OwnershipCheck) -> str:
    """格式化检查报告。"""
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append("CSS Ownership Gate Report")
    lines.append("=" * 60)
    lines.append(f"Files scanned:      {result.files_scanned}")
    lines.append(f"Selectors analyzed: {result.selectors_analyzed}")
    lines.append(f"Block violations:   {len(result.blocks)}")
    lines.append(f"Warnings:           {len(result.warnings)}")
    lines.append("")

    if result.blocks:
        lines.append("--- BLOCK violations ---")
        for v in result.blocks:
            line_info = f" (L{v.line})" if v.line else ""
            lines.append(f"  [BLOCK] {v.rule}{line_info}: {v.file} — {v.detail}")
        lines.append("")

    if result.warnings:
        lines.append("--- Warnings ---")
        for v in result.warnings:
            line_info = f" (L{v.line})" if v.line else ""
            lines.append(f"  [WARN]  {v.rule}{line_info}: {v.file} — {v.detail}")
        lines.append("")

    if not result.blocks and not result.warnings:
        lines.append("CSS ownership: PASS (no violations)")
    elif not result.blocks:
        lines.append(f"CSS ownership: PASS ({len(result.warnings)} warnings)")
    else:
        lines.append(f"CSS ownership: FAIL ({len(result.blocks)} block, {len(result.warnings)} warn)")

    lines.append("=" * 60)
    return "\n".join(lines)


# ── CLI ──────────────────────────────────────────────────────────────────


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent.parent
    result = check_css_ownership(repo_root)
    report = format_report(result)
    print(report)

    # 写入 artifact
    out_dir = repo_root / "tmp" / "agent_logs" / "current" / "css-ownership"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "css-ownership-report.txt"
    out_file.write_text(report + "\n", encoding="utf-8")

    # JSON artifact 供 quality gate 集成
    json_report = {
        "schemaVersion": 1,
        "gate": "css-ownership",
        "status": "PASS" if not result.blocks else "FAIL",
        "filesScanned": result.files_scanned,
        "selectorsAnalyzed": result.selectors_analyzed,
        "blockCount": len(result.blocks),
        "warningCount": len(result.warnings),
        "blocks": [
            {"rule": v.rule, "file": v.file, "line": v.line, "detail": v.detail}
            for v in result.blocks
        ],
        "warnings": [
            {"rule": v.rule, "file": v.file, "line": v.line, "detail": v.detail}
            for v in result.warnings
        ],
    }
    json_path = out_dir / "css-ownership-gate.json"
    json_path.write_text(json.dumps(json_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return 0 if not result.blocks else 1


if __name__ == "__main__":
    raise SystemExit(main())
