#!/usr/bin/env python3
"""静态资源契约检查。

Exit 1 仅针对真正阻塞性问题（!important、load order、dead CSS、duplicate base CSS、
css-ownership、global-component-override、new-legacy-selector、selector-depth、
raw-innerHTML、layout-inline-style）。

position: fixed、payload-modal ownership、shell ownership 作为警告输出，不阻塞提交。

纯函数拆出以支持单测：
- check_no_important(css_files)
- check_css_load_order(base_html_text)
- check_no_dead_css(css_files)
- check_no_duplicate_base_css(html_files)
- check_payload_modal_ownership(css_files) -> (errors, warnings)
- check_shell_ownership(css_files)
- check_innerhtml_safety(js_files)
- check_css_ownership_gate(css_files)        [NEW]
- check_no_global_component_override(css_files)  [NEW]
- check_no_new_legacy_selector(css_files)    [NEW]
- check_selector_depth_new_block(css_files)  [NEW]
- check_no_raw_innerhtml_new_block(js_files) [NEW]
- check_no_layout_inline_style_new_block(html_files, js_files) [NEW]
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


def _is_import_wrapper(text: str) -> bool:
    """Check if a CSS file only contains @import statements (no rule bodies)."""
    stripped = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL).strip()
    if not stripped:
        return True
    # If only @import lines and no { }, it's an import wrapper
    lines = [l.strip() for l in stripped.splitlines() if l.strip()]
    has_import = any(l.startswith("@import") for l in lines)
    has_rules = "{" in stripped and "}" in stripped
    return has_import and not has_rules


def _is_in_ui_primitives_subdir(path: Path) -> bool:
    """Check if the file is under a ui-primitives/ subdirectory."""
    return "ui-primitives" in path.parent.name or path.parent.name == "ui-primitives"


def check_no_dead_css(css_files: list[Path]) -> list[str]:
    """检查是否存在 0 有效规则的 CSS 文件。BLOCK。

    去掉注释和空白后，如果没有 '{' 和 '}'，判定为 dead CSS。
    豁免：纯 @import wrapper 文件（如拆分后的 ui-primitives.css）。
    """
    errors: list[str] = []
    for path in css_files:
        text = path.read_text(encoding="utf-8", errors="replace")
        # @import wrapper files are intentional — skip
        if _is_import_wrapper(text):
            continue
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
        # 权威来源跳过（包括 ui-primitives/ 子目录下的拆分文件）
        if name in ("ui-primitives.css", "tokens.css", "base.css") or _is_in_ui_primitives_subdir(path):
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


# ── CSS/JS ownership gates ─────────────────────────────────────────────

# CSS 自定义属性白名单（允许 inline style 中使用）
INLINE_CUSTOM_PROP_WHITELIST = re.compile(
    r'--(bar-height|segment-width|fill-width|sidebar-w|inspector-w|header-h|content-max)'
    r'|--(density-|token-|agent-|status-|badge-|table-row-|card-|tooltip-|shadow|radius|spacing)'
)

# Shell 级选择器（页面 CSS 不得定义这些选择器）
# 这些是 shell 架构选择器，只能由 shell.css 定义
SHELL_SELECTORS_FOR_OWNERSHIP = [
    (r'(?:^|[,\s{;])\s*\.shell\s*[{,\s]', '.shell'),
    (r'(?:^|[,\s{;])\s*\.app-shell\s*[{,\s]', '.app-shell'),
    (r'(?:^|[,\s{;])\s*\.phase1-shell\s*[{,\s]', '.phase1-shell'),
    (r'body\.(hide-left|hide-right|focus|no-inspector)', 'body.* state'),
]

# 原语根组件（页面 CSS 不得裸定义 — 用于坏 fixture 测试）
PRIMITIVE_ROOT_CLASSES = {
    '.btn', '.ui-btn', '.icon-btn', '.icon-button',
    '.badge', '.card', '.section', '.section-head',
    '.metric-card', '.metric-grid', '.tooltip',
    '.popover', '.menu-popover', '.data-table',
    '.filter-card', '.filter-chip', '.pagination',
    '.modal', '.payload-modal', '.state-strip',
    '.toast', '.page-head', '.tabs', '.tab-nav',
    '.tab-btn', '.pill', '.avatar',
}

# 已知遗留类名（用于检测新增引用）
LEGACY_CLASS_NAMES = {
    'app-shell', 'phase1-shell',
}


def check_css_ownership_gate(css_files: list[Path]) -> list[str]:
    """检查：页面 CSS 不得定义 shell 架构选择器。
    tokens.css 不得包含选择器规则。BLOCK。
    注意：此 gate 只检查 shell 级选择器越权，不检查页面内容 grid。
    """
    errors: list[str] = []
    exempt_shell = {"shell.css", "legacy-aliases.css"}

    for path in css_files:
        name = path.name
        text = path.read_text(encoding="utf-8", errors="replace")
        rel = str(path.relative_to(path.parent.parent.parent.parent))

        # tokens.css 只应有 :root 包裹
        if name == "tokens.css":
            stripped = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
            # 简化：检查是否有 :root 之外的选择器规则
            # 匹配 "selector { ... }" 模式
            rule_pattern = re.compile(r'([^{;]+?)\s*\{([^}]*)\}', re.DOTALL)
            for match in rule_pattern.finditer(stripped):
                sel_str = match.group(1).strip()
                body = match.group(2).strip()
                # 跳过 @rules 和嵌套规则
                if sel_str.startswith("@") or "{" in body:
                    continue
                if sel_str != ":root":
                    errors.append(
                        f"{rel}: tokens.css 不得包含 :root 外的选择器规则。"
                    )
                    break

        # 页面 CSS 不得定义 shell 架构选择器
        # 豁免：shell.css（权威定义）、legacy-aliases.css（兼容层）
        if name not in exempt_shell:
            for pattern, label in SHELL_SELECTORS_FOR_OWNERSHIP:
                if re.search(pattern, text):
                    errors.append(
                        f"{rel}: 页面 CSS 不得定义 shell 级选择器 '{label}'，应归属 shell.css。"
                    )

    return errors


def check_no_global_component_override(css_files: list[Path]) -> list[str]:
    """检查：页面 CSS 不得裸定义原语根组件。BLOCK。
    豁免：ui-primitives.css、tokens.css、base.css、shell.css、legacy-aliases.css
    以及 ui-primitives/ 子目录下的所有拆分文件（它们是原语系统的一部分）。

    裸选择器定义：组件选择器在选择器链的开头，没有页面前缀。
    合法：.page .btn（后代）、.sd-btn（变体）
    非法：.btn { ... }（裸定义）
    """
    errors: list[str] = []
    exempt = {"ui-primitives.css", "tokens.css", "base.css", "shell.css", "legacy-aliases.css"}
    for path in css_files:
        # Exempt both the main wrapper and all files in ui-primitives/ subdirectory
        if path.name in exempt or _is_in_ui_primitives_subdir(path):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        stripped = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
        rel = str(path.relative_to(path.parent.parent.parent.parent))

        # 提取选择器（{ 之前的部分）
        found: list[str] = []
        selector_pattern = re.compile(r'([^{;]+?)\s*\{([^}]*)\}', re.DOTALL)
        for match in selector_pattern.finditer(stripped):
            sel_str = match.group(1).strip()
            body = match.group(2).strip()
            if sel_str.startswith("@") or "{" in body:
                continue

            # 按逗号拆分
            for sel in sel_str.split(","):
                sel = sel.strip()
                if not sel:
                    continue
                # 检查每个原始组件选择器
                for comp in sorted(PRIMITIVE_ROOT_CLASSES):
                    comp_escaped = re.escape(comp)
                    # 匹配：选择器以组件名开头（无页面前缀）
                    # .btn, .btn:hover, .btn.primary — 这些是裸定义
                    # .page .btn — 这是后代选择器（合法）
                    # .sd-btn — 这是页面变体（合法）
                    bare_pattern = re.compile(
                        r'^' + comp_escaped + r'(?:\b|$|[:\.\s]|$)',
                    )
                    if bare_pattern.match(sel):
                        if comp not in found:
                            found.append(comp)

        if found:
            errors.append(
                f"{rel}: 页面 CSS 裸定义原语根组件: {', '.join(found)}，"
                f"应收敛至 ui-primitives.css 或使用后代/页面前缀选择器。"
            )
    return errors


def check_no_new_legacy_selector(css_files: list[Path]) -> list[str]:
    """检查：新增遗留选择器引用。BLOCK。
    豁免：shell.css（已知 shell aliases）、legacy-aliases.css（兼容层）
    """
    errors: list[str] = []
    exempt = {"legacy-aliases.css", "shell.css", "tokens.css", "base.css"}
    for path in css_files:
        if path.name in exempt:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        rel = str(path.relative_to(path.parent.parent.parent.parent))

        found: list[str] = []
        for legacy in LEGACY_CLASS_NAMES:
            pattern = re.compile(r'\.' + re.escape(legacy) + r'\b')
            if pattern.search(text):
                found.append('.' + legacy)

        if found:
            errors.append(
                f"{rel}: 新增遗留选择器引用: {', '.join(found)}，"
                f"应迁移到新版 class 名称。"
            )
    return errors


def check_selector_depth_new_block(css_files: list[Path]) -> list[str]:
    """检查：新选择器嵌套深度 > 3。BLOCK。

    深度计算：以 CSS 组合符（空格、>、+、~）拆分，非空部分数量。
    注意：此检查只分析真正的 CSS 选择器，不分析声明块内容。
    """
    errors: list[str] = []
    BLOCK_DEPTH = 3
    COMBINATOR_RE = re.compile(r'\s*(?:>|[+~])\s*|\s+')

    for path in css_files:
        text = path.read_text(encoding="utf-8", errors="replace")
        # 去掉注释
        stripped = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
        rel = str(path.relative_to(path.parent.parent.parent.parent))

        # 提取真正的选择器（{ 之前的部分）
        depth_violations: list[str] = []
        # 用栈式解析提取选择器
        stack: list[str] = []
        i = 0
        while i < len(stripped):
            if stripped[i] == "{":
                # 找到选择器起点
                sel_start = i - 1
                while sel_start >= 0 and stripped[sel_start] not in "{};":
                    sel_start -= 1
                sel_start += 1
                selector_str = stripped[sel_start:i].strip()
                stack.append(selector_str)
            elif stripped[i] == "}" and stack:
                stack.pop()
            i += 1

        # 分析栈中累积的选择器
        # 注意：上面的栈方法不够精确，改用更直接的方法
        # 匹配 "selector { body }" 模式
        selector_pattern = re.compile(r'([^{;]+?)\s*\{([^}]*)\}', re.DOTALL)
        for match in selector_pattern.finditer(stripped):
            sel_str = match.group(1).strip()
            # body 中可能有嵌套规则（@media 等），跳过
            body = match.group(2).strip()
            if "{" in body:
                continue  # 嵌套规则，跳过
            if sel_str.startswith("@"):
                continue

            # 按逗号拆分
            for sel in sel_str.split(","):
                sel = sel.strip()
                if not sel or sel.startswith("@"):
                    continue

                # 保护括号内容
                protected = sel
                bracket_contents: list[str] = []
                def protect_brackets(m: re.Match) -> str:
                    idx = len(bracket_contents)
                    bracket_contents.append(m.group(0))
                    return f"__B{idx}__"
                protected = re.sub(r'\([^)]*\)', protect_brackets, protected)

                # 拆分
                segs = [s.strip() for s in COMBINATOR_RE.split(protected) if s.strip()]
                depth = len(segs)
                if depth > BLOCK_DEPTH:
                    depth_violations.append(f"{sel} (depth={depth})")

        if depth_violations:
            errors.append(
                f"{rel}: 选择器深度超过 {BLOCK_DEPTH}: {'; '.join(depth_violations[:5])}"
            )
    return errors


def check_no_raw_innerhtml_new_block(js_files: list[Path]) -> list[str]:
    """检查：JS 文件中不得有原始 innerHTML 赋值（清空操作除外）。BLOCK。
    安全 helper 调用（escapeHtml/sanitize/DOMPurify）视为 PASS。
    """
    errors: list[str] = []
    INNERHTML_ASSIGN_RE = re.compile(r"\.innerHTML\s*=")
    CLEAR_ASSIGN_RE = re.compile(r"\.innerHTML\s*=\s*['\"]\s*['\"]")
    COMMENT_LINE_RE = re.compile(r"^\s*(?://|/\*|\*)")
    SAFE_HELPER_RE = re.compile(
        r'\bescapeHtml\b|\bsanitize\b|\bsafeRender\b|\bsafeHtml\b'
        r'|\bDOMPurify\b|\bcreateContextualFragment\b',
        re.IGNORECASE,
    )

    for path in js_files:
        text = path.read_text(encoding="utf-8", errors="replace")
        rel = str(path.relative_to(path.parent.parent.parent.parent))

        # 如果文件有安全 helper，跳过
        if SAFE_HELPER_RE.search(text):
            continue

        findings: list[str] = []
        for line_no, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if COMMENT_LINE_RE.match(stripped):
                continue
            if INNERHTML_ASSIGN_RE.search(line) and not CLEAR_ASSIGN_RE.search(line):
                findings.append(f"L{line_no}: {stripped[:100]}")

        if findings:
            errors.append(
                f"{rel}: 新增原始 innerHTML 赋值 ({len(findings)} 处)，"
                f"应使用 textContent 或 escapeHtml()/DOMPurify。"
            )
    return errors


def check_no_layout_inline_style_new_block(
    html_files: list[Path], js_files: list[Path],
) -> list[str]:
    """检查：HTML 模板和 JS 文件中不得有 layout 相关 inline style / .style.xxx 赋值。
    CSS custom property 白名单内的属性允许。BLOCK。
    """
    errors: list[str] = []
    LAYOUT_PROPS_RE = re.compile(
        r'\b(display|position|flex|grid|width|height|min-width|min-height|max-width|max-height'
        r'|top|left|right|bottom'
        r'|padding|padding-top|padding-right|padding-bottom|padding-left'
        r'|margin|margin-top|margin-right|margin-bottom|margin-left'
        r'|overflow|overflow-x|overflow-y'
        r'|z-index'
        r')\s*:',
        re.IGNORECASE,
    )
    CUSTOM_PROP_RE = re.compile(r'\-\-[\w-]+\s*:')
    JS_STYLE_ASSIGN_RE = re.compile(
        r'\.style\.(display|position|flex|grid|width|height|minWidth|minHeight'
        r'|maxWidth|maxHeight|top|left|right|bottom|padding|paddingTop|paddingRight'
        r'|paddingBottom|paddingLeft|margin|marginTop|marginRight|marginBottom|marginLeft'
        r'|overflow|overflowX|overflowY|zIndex)\s*='
    )
    JS_COMMENT_RE = re.compile(r"^\s*(?://|/\*|\*)")

    # 检查 HTML
    for path in html_files:
        text = path.read_text(encoding="utf-8", errors="replace")
        rel = str(path.relative_to(path.parent.parent.parent.parent))
        style_attr_re = re.compile(r'style\s*=\s*["\']([^"\']*)["\']', re.IGNORECASE)

        findings: list[str] = []
        for line_no, line in enumerate(text.splitlines(), 1):
            if line.strip().startswith("{#") or line.strip().startswith("<!--"):
                continue
            for match in style_attr_re.finditer(line):
                style_value = match.group(1)
                # 跳过纯模板变量
                if re.match(r'^\s*\{\{.*\}\}\s*$', style_value):
                    continue
                # 检查是否只有白名单 custom property
                has_custom = bool(CUSTOM_PROP_RE.search(style_value))
                if has_custom:
                    non_custom = CUSTOM_PROP_RE.sub('', style_value).strip()
                    non_custom = re.sub(r'[;\s]+', ' ', non_custom).strip()
                    if not non_custom or not LAYOUT_PROPS_RE.search(non_custom):
                        continue
                if LAYOUT_PROPS_RE.search(style_value):
                    findings.append(f"L{line_no}")

        if findings:
            errors.append(
                f"{rel}: HTML 新增 layout inline style ({len(findings)} 处)，"
                f"应使用 CSS class 或 CSS custom property。"
            )

    # 检查 JS
    for path in js_files:
        text = path.read_text(encoding="utf-8", errors="replace")
        rel = str(path.relative_to(path.parent.parent.parent.parent))

        findings: list[str] = []
        for line_no, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if JS_COMMENT_RE.match(stripped):
                continue
            if JS_STYLE_ASSIGN_RE.search(line):
                findings.append(f"L{line_no}")

        if findings:
            errors.append(
                f"{rel}: JS 新增 .style.xxx 布局赋值 ({len(findings)} 处)，"
                f"应使用 class 切换或 CSS custom property。"
            )

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

    # ── CSS/JS ownership gates ─────────────────────────────────────
    # 加载历史债务 baseline，存量违规 = WARN，新增 = BLOCK
    baseline = _load_ownership_baseline(repo_root)

    # BLOCK: css-ownership-gate (shell selector ownership)
    _apply_baseline_gate(errors, warnings, check_css_ownership_gate(css_files),
                         baseline.get("css_ownership_violations", []), "css-ownership")

    # BLOCK: no-global-component-override
    _apply_baseline_gate(errors, warnings, check_no_global_component_override(css_files),
                         baseline.get("component_override_violations", []), "component-override")

    # BLOCK: no-new-legacy-selector
    _apply_baseline_gate(errors, warnings, check_no_new_legacy_selector(css_files),
                         baseline.get("new_legacy_selector_violations", []), "legacy-selector")

    # BLOCK: selector-depth-new-block
    _apply_baseline_gate(errors, warnings, check_selector_depth_new_block(css_files),
                         baseline.get("selector_depth_violations", []), "selector-depth")

    # BLOCK: no-raw-innerHTML-new-block
    _apply_baseline_gate(errors, warnings, check_no_raw_innerhtml_new_block(js_files),
                         baseline.get("raw_innerhtml_violations", []), "raw-innerhtml")

    # BLOCK: no-layout-inline-style-new-block (HTML + JS)
    html_files_for_style = list(templates.rglob("*.html")) if templates.exists() else []
    layout_errors = check_no_layout_inline_style_new_block(html_files_for_style, js_files)
    _apply_baseline_gate_combined(
        errors, warnings, layout_errors,
        baseline.get("layout_inline_style_html_violations", [])
        + baseline.get("layout_style_js_violations", []),
        "layout-inline-style",
    )

    return errors, warnings


def _load_ownership_baseline(repo_root: Path) -> dict:
    """加载 ownership baseline JSON。"""
    import json
    baseline_path = Path(__file__).parent / "ownership_baseline.json"
    if baseline_path.exists():
        try:
            return json.loads(baseline_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            pass
    return {}


def _apply_baseline_gate(
    errors: list[str], warnings: list[str],
    gate_results: list[str], baseline_items: list[str],
    gate_name: str,
) -> None:
    """将 gate 结果与 baseline 比对：存量 = WARN，新增 = BLOCK。"""
    # 创建 baseline 匹配集合（简化：用子串匹配）
    baseline_set = set()
    for item in baseline_items:
        baseline_set.add(item)
        # 也添加文件名部分用于匹配
        if ":" in item:
            baseline_set.add(item.split(":")[0])
            # Also add the selector part (after path:prefix) for cross-path matching
            # Format: "path/to/file.css:selector" or "path/file.css: selector ..."
            colon_idx = item.index(":")
            selector_part = item[colon_idx + 1:].strip()
            if selector_part:
                # Extract just the selector (before any " (depth=" or other annotations)
                sel = selector_part.split(" (")[0].strip()
                if sel:
                    baseline_set.add(sel)

    for result in gate_results:
        is_known = any(b in result for b in baseline_set)
        if is_known:
            warnings.append(f"[{gate_name}] 存量: {result}")
        else:
            errors.append(f"[{gate_name}] 新增: {result}")


def _apply_baseline_gate_combined(
    errors: list[str], warnings: list[str],
    gate_results: list[str], baseline_items: list[str],
    gate_name: str,
) -> None:
    """同上，但 baseline 中可能包含文件路径前缀。"""
    baseline_set = set()
    for item in baseline_items:
        baseline_set.add(item)
        # 提取文件名部分
        parts = item.split("/")
        if parts:
            baseline_set.add(parts[-1])
            baseline_set.add(item.split(":")[0] if ":" in item else item)
        # Also add selector part for cross-path matching
        if ":" in item:
            colon_idx = item.index(":")
            selector_part = item[colon_idx + 1:].strip()
            if selector_part:
                sel = selector_part.split(" (")[0].strip()
                if sel:
                    baseline_set.add(sel)

    for result in gate_results:
        is_known = any(b in result for b in baseline_set)
        if is_known:
            warnings.append(f"[{gate_name}] 存量: {result}")
        else:
            errors.append(f"[{gate_name}] 新增: {result}")


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
