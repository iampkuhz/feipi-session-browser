#!/usr/bin/env python3
"""检查 Web 静态资源的加载、安全、所有权与布局契约。

这些契约阻止危险 innerHTML、页面级基础样式重定义和新增 inline 布局等回归越过已审计基线。
唯一公开入口是 `check(arguments)`；失败表示资源目录不可用或存在不在基线内的阻断项。
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from scripts.checks._framework import CheckResult, argument_parser, repository_root

REPO_ROOT = repository_root()


INNERHTML_LINE_PREVIEW_LIMIT = 5
SELECTOR_BLOCK_DEPTH = 3
SELECTOR_COMBINATOR_RE = re.compile(r'\s*(?:>|[+~])\s*|\s+')
INNERHTML_ASSIGN_RE = re.compile(r'\.innerHTML\s*=')
CLEAR_ASSIGN_RE = re.compile(r"\.innerHTML\s*=\s*['\"]\s*['\"]")
COMMENT_LINE_RE = re.compile(r'^\s*(?://|/\*|\*)')
SAFE_HELPER_RE = re.compile(
    r'\bescapeHtml\b|\bsanitize\b|\bsafeRender\b|\bsafeHtml\b'
    r'|\bDOMPurify\b|\bcreateContextualFragment\b',
    re.IGNORECASE,
)
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


def _check_no_important(css_files: list[Path]) -> list[str]:
    """返回包含 !important 的 CSS 文件诊断。"""
    errors: list[str] = []
    for path in css_files:
        text = path.read_text(encoding='utf-8', errors='replace')
        if re.search(r'!important', text):
            errors.append(f'{path}: 禁止 !important(contract: payload-modal-contract).')
    return errors


def _check_no_duplicate_base_css(html_files: list[Path]) -> list[str]:
    """返回页面模板重复加载基础 CSS 的诊断。"""
    errors: list[str] = []
    base_names = {'tokens.css', 'base.css', 'shell.css', 'ui-primitives.css'}
    for path in html_files:
        text = path.read_text(encoding='utf-8', errors='replace')
        # 排除 base.html 自身
        if path.name == 'base.html':
            continue
        # 找出所有 stylesheet link 的 href
        links = re.findall(r'href="([^"]*\.css[^"]*)"', text)
        found_duplicates = []
        for link in links:
            basename = link.split('/')[-1].split('?')[0]
            if basename in base_names:
                found_duplicates.append(basename)
        if found_duplicates:
            errors.append(
                f'{path}: 页面模板重复加载 base 已加载的 CSS: '
                f'{", ".join(sorted(set(found_duplicates)))}.'
            )
    return errors


def _check_css_load_order(base_html_text: str) -> list[str]:
    """校验基础 CSS 与 head_extra 的加载顺序，缺项时立即返回诊断。"""
    errors: list[str] = []
    expected = [
        '/static/css/tokens.css',
        '/static/css/base.css',
        '/static/css/shell.css',
        '/static/css/ui-primitives.css',
        '{% block head_extra %}',
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
                f"'{expected[i + 1]}' 之前加载(位置 {positions[i]} vs {positions[i + 1]})."
            )

    return errors


def _is_import_wrapper(text: str) -> bool:
    stripped = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL).strip()
    if not stripped:
        return False  # 空文件属于无效 CSS，不是 import 包装器
    # 仅包含 import 且没有规则块时视为包装器。
    lines = [css_line.strip() for css_line in stripped.splitlines() if css_line.strip()]
    has_import = any(css_line.startswith('@import') for css_line in lines)
    has_rules = '{' in stripped and '}' in stripped
    return has_import and not has_rules


def _is_in_ui_primitives_subdir(path: Path) -> bool:
    return 'ui-primitives' in path.parent.name or path.parent.name == 'ui-primitives'


def _check_no_dead_css(css_files: list[Path]) -> list[str]:
    """返回仅含注释、空白或没有规则块的无效 CSS 文件。"""
    errors: list[str] = []
    for path in css_files:
        text = path.read_text(encoding='utf-8', errors='replace')
        if _is_import_wrapper(text):
            continue
        # 去掉 CSS 注释
        stripped = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
        # 去掉空白
        stripped = stripped.strip()
        if not stripped:
            errors.append(f'{path}: 死 CSS 文件(只有注释或空白,无有效规则).')
        elif '{' not in stripped and '}' not in stripped:
            errors.append(f'{path}: 死 CSS 文件(无 CSS rule body).')
    return errors


def _check_payload_modal_ownership(css_files: list[Path]) -> tuple[list[str], list[str]]:
    """返回非权威文件裸定义 payload modal 的错误与警告。"""
    errors: list[str] = []
    warnings: list[str] = []
    bare_pattern = re.compile(
        r'^(?!\s*/\*|\s*\*|\s*\.session-detail-page|\s*\.sd-page|\s*\.sd-shell|\s*\.sd-payload-modal)'
        r'\s*(?:\.payload-modal\b(?![-_:\s]*--)|#payload-modal\b)',
        re.MULTILINE,
    )
    for path in css_files:
        name = path.name
        # 权威来源跳过
        if name in ('ui-primitives.css', 'tokens.css', 'base.css') or _is_in_ui_primitives_subdir(
            path
        ):
            continue
        text = path.read_text(encoding='utf-8', errors='replace')
        matches = bare_pattern.findall(text)
        if not matches:
            continue
        errors.append(
            f'{path}: 禁止裸 payload-modal 定义({len(matches)} 处),应收敛至 ui-primitives.css.'
        )
    return errors, warnings


def _check_shell_ownership(css_files: list[Path]) -> list[str]:
    """返回非 shell.css 文件引用 shell 级 selector 的警告。"""
    warnings: list[str] = []
    shell_selectors = [
        '.app-shell',
        '.shell',
        '.phase1-shell',
        'body.hide-left',
        'body.hide-right',
        'body.focus',
    ]
    # 豁免文件:shell.css(当前 shell 权威),base.css(基础样式),tokens.css(设计令牌)
    exempt = {'shell.css', 'base.css', 'tokens.css'}
    for path in css_files:
        name = path.name
        if name in exempt:
            continue
        text = path.read_text(encoding='utf-8', errors='replace')
        found = []
        for sel in shell_selectors:
            if sel in text:
                found.append(sel)
        if found:
            warnings.append(f'{path}: 包含 shell 级选择器: {", ".join(found)},应归属 shell.css.')
    return warnings


def _check_innerhtml_safety(js_files: list[Path]) -> list[str]:
    """返回未发现安全 helper 的 innerHTML 写入警告。"""
    warnings: list[str] = []
    safety_patterns = re.compile(
        r'\bescapeHtml\b|\bsanitize\b|\bsafeRender\b|\bsafeHtml\b'
        r'|\bDOMPurify\b|\bcreateContextualFragment\b',
        re.IGNORECASE,
    )
    for path in js_files:
        text = path.read_text(encoding='utf-8', errors='replace')
        if 'innerHTML' not in text:
            continue
        if safety_patterns.search(text):
            continue  # 已通过安全 helper 处理
        # 只保留少量行号，使诊断可定位且不会输出整段源码。
        lines_with_inner = []
        for lineno, line in enumerate(text.splitlines(), 1):
            if 'innerHTML' in line:
                stripped = line.strip()
                if "''" not in stripped and '""' not in stripped:
                    lines_with_inner.append(lineno)
        if lines_with_inner:
            line_info = ', '.join(f'L{n}' for n in lines_with_inner[:INNERHTML_LINE_PREVIEW_LIMIT])
            if len(lines_with_inner) > INNERHTML_LINE_PREVIEW_LIMIT:
                line_info += f' +{len(lines_with_inner) - INNERHTML_LINE_PREVIEW_LIMIT} more'
            warnings.append(
                f'{path}: innerHTML 使用未见 sanitize/escape helper({line_info}),'
                '建议后续 Sprint 治理.'
            )
    return warnings


# CSS 自定义属性白名单(允许 inline style 中使用)
INLINE_CUSTOM_PROP_WHITELIST = re.compile(
    r'--(bar-height|segment-width|fill-width|sidebar-w|inspector-w|header-h|content-max)'
    r'|--(density-|token-|agent-|status-|badge-|table-row-|card-|tooltip-|shadow|radius|spacing)'
)

# Shell 级选择器(页面 CSS 不得定义这些选择器)
# 这些是 shell 架构选择器,只能由 shell.css 定义
SHELL_SELECTORS_FOR_OWNERSHIP = [
    (r'(?:^|[,\s{;])\s*\.shell\s*[{,\s]', '.shell'),
    (r'(?:^|[,\s{;])\s*\.app-shell\s*[{,\s]', '.app-shell'),
    (r'(?:^|[,\s{;])\s*\.phase1-shell\s*[{,\s]', '.phase1-shell'),
    (r'body\.(hide-left|hide-right|focus|no-inspector)', 'body.* state'),
]

# 原语根组件(页面 CSS 不得裸定义 — 用于坏 fixture 测试)
PRIMITIVE_ROOT_CLASSES = {
    '.btn',
    '.ui-btn',
    '.icon-btn',
    '.icon-button',
    '.badge',
    '.card',
    '.section',
    '.section-head',
    '.metric-card',
    '.metric-grid',
    '.tooltip',
    '.popover',
    '.menu-popover',
    '.data-table',
    '.filter-card',
    '.filter-chip',
    '.pagination',
    '.modal',
    '.payload-modal',
    '.state-strip',
    '.toast',
    '.page-head',
    '.tabs',
    '.tab-nav',
    '.tab-btn',
    '.pill',
    '.avatar',
}


def _check_css_ownership_gate(css_files: list[Path]) -> list[str]:
    """检查 token 与 shell selector 的文件所有权并返回违规。"""
    errors: list[str] = []
    exempt_shell = {'shell.css'}

    for path in css_files:
        name = path.name
        text = path.read_text(encoding='utf-8', errors='replace')
        rel = str(path.relative_to(path.parent.parent.parent.parent))

        # tokens.css 只应有 :root 包裹
        if name == 'tokens.css':
            stripped = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
            # 简化:检查是否有 :root 之外的选择器规则
            # 匹配 "selector { ... }" 模式
            rule_pattern = re.compile(r'([^{;]+?)\s*\{([^}]*)\}', re.DOTALL)
            for match in rule_pattern.finditer(stripped):
                sel_str = match.group(1).strip()
                body = match.group(2).strip()
                # 跳过 @rules 和嵌套规则
                if sel_str.startswith('@') or '{' in body:
                    continue
                if sel_str != ':root':
                    errors.append(f'{rel}: tokens.css 不得包含 :root 外的选择器规则.')
                    break

        # 页面 CSS 不得定义 shell 架构选择器
        # 豁免:shell.css(权威定义)
        if name not in exempt_shell:
            for pattern, label in SHELL_SELECTORS_FOR_OWNERSHIP:
                if re.search(pattern, text):
                    errors.append(
                        f"{rel}: 页面 CSS 不得定义 shell 级选择器 '{label}',应归属 shell.css."
                    )

    return errors


def _check_no_global_component_override(css_files: list[Path]) -> list[str]:
    """返回页面 CSS 裸重写全局原语根组件的违规。"""
    errors: list[str] = []
    exempt = {'ui-primitives.css', 'tokens.css', 'base.css', 'shell.css'}
    for path in css_files:
        if path.name in exempt or _is_in_ui_primitives_subdir(path):
            continue
        text = path.read_text(encoding='utf-8', errors='replace')
        stripped = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
        rel = str(path.relative_to(path.parent.parent.parent.parent))

        # 提取选择器({ 之前的部分)
        found: list[str] = []
        selector_pattern = re.compile(r'([^{;]+?)\s*\{([^}]*)\}', re.DOTALL)
        for match in selector_pattern.finditer(stripped):
            sel_str = match.group(1).strip()
            body = match.group(2).strip()
            if sel_str.startswith('@') or '{' in body:
                continue

            # 按逗号拆分
            for raw_sel in sel_str.split(','):
                sel = raw_sel.strip()
                if not sel:
                    continue
                # 检查每个原始组件选择器
                for comp in sorted(PRIMITIVE_ROOT_CLASSES):
                    comp_escaped = re.escape(comp)
                    # 匹配:选择器以组件名开头(无页面前缀)
                    # .btn, .btn:hover, .btn.primary — 这些是裸定义
                    # .page .btn — 这是后代选择器(合法)
                    # .sd-btn — 这是页面变体(合法)
                    bare_pattern = re.compile(
                        r'^' + comp_escaped + r'(?:$|[:\.\s#\[\]>+~])',
                    )
                    if bare_pattern.match(sel) and comp not in found:
                        found.append(comp)

        if found:
            errors.append(
                f'{rel}: 页面 CSS 裸定义原语根组件: {", ".join(found)},'
                f'应收敛至 ui-primitives.css 或使用后代/页面前缀选择器.'
            )
    return errors


def _check_selector_depth_new_block(css_files: list[Path]) -> list[str]:
    """返回超过最大组合层级的 CSS selector。"""
    errors: list[str] = []
    for path in css_files:
        text = path.read_text(encoding='utf-8', errors='replace')
        # 去掉注释
        stripped = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
        rel = str(path.relative_to(path.parent.parent.parent.parent))

        # 提取真正的选择器({ 之前的部分)
        depth_violations: list[str] = []
        # 用栈式解析提取选择器
        stack: list[str] = []
        i = 0
        while i < len(stripped):
            if stripped[i] == '{':
                # 找到选择器起点
                sel_start = i - 1
                while sel_start >= 0 and stripped[sel_start] not in '{};':
                    sel_start -= 1
                sel_start += 1
                selector_str = stripped[sel_start:i].strip()
                stack.append(selector_str)
            elif stripped[i] == '}' and stack:
                stack.pop()
            i += 1

        # 后续按完整规则块计算 selector 深度，避免嵌套 body 被当作 selector。
        selector_pattern = re.compile(r'([^{;]+?)\s*\{([^}]*)\}', re.DOTALL)
        for match in selector_pattern.finditer(stripped):
            sel_str = match.group(1).strip()
            # body 中可能有嵌套规则(@media 等),跳过
            body = match.group(2).strip()
            if '{' in body:
                continue  # 嵌套规则,跳过
            if sel_str.startswith('@'):
                continue

            # 按逗号拆分
            for raw_sel in sel_str.split(','):
                sel = raw_sel.strip()
                if not sel or sel.startswith('@'):
                    continue

                # 先保护伪类函数参数，避免其中的空格和组合符增加 selector 深度。
                protected = sel
                bracket_contents: list[str] = []

                def protect_brackets(
                    m: re.Match,
                    bracket_values: list[str] = bracket_contents,
                ) -> str:
                    """用占位符保护一段括号内容。"""
                    idx = len(bracket_values)
                    bracket_values.append(m.group(0))
                    return f'__B{idx}__'

                protected = re.sub(r'\([^)]*\)', protect_brackets, protected)

                # 拆分
                segs = [
                    segment.strip()
                    for segment in SELECTOR_COMBINATOR_RE.split(protected)
                    if segment.strip()
                ]
                depth = len(segs)
                if depth > SELECTOR_BLOCK_DEPTH:
                    depth_violations.append(f'{sel} (depth={depth})')

        if depth_violations:
            errors.append(
                f'{rel}: 选择器深度超过 {SELECTOR_BLOCK_DEPTH}: {"; ".join(depth_violations[:5])}'
            )
    return errors


def _check_no_raw_innerhtml_new_block(js_files: list[Path]) -> list[str]:
    """返回没有安全 helper 保护的 raw innerHTML 赋值。"""
    errors: list[str] = []

    for path in js_files:
        text = path.read_text(encoding='utf-8', errors='replace')
        rel = str(path.relative_to(path.parent.parent.parent.parent))

        # 如果文件有安全 helper,跳过
        if SAFE_HELPER_RE.search(text):
            continue

        findings: list[str] = []
        for line_no, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if COMMENT_LINE_RE.match(stripped):
                continue
            if INNERHTML_ASSIGN_RE.search(line) and not CLEAR_ASSIGN_RE.search(line):
                findings.append(f'L{line_no}: {stripped[:100]}')

        if findings:
            errors.append(
                f'{rel}: 新增原始 innerHTML 赋值 ({len(findings)} 处),'
                f'应使用 textContent 或 escapeHtml()/DOMPurify.'
            )
    return errors


def _check_no_layout_inline_style_new_block(  # noqa: PLR0912 - keeps HTML and JS checks together.
    html_files: list[Path],
    js_files: list[Path],
) -> list[str]:
    """返回 HTML 与 JavaScript 中直接写入布局 style 的违规。"""
    errors: list[str] = []

    # 检查 HTML
    for path in html_files:
        text = path.read_text(encoding='utf-8', errors='replace')
        rel = str(path.relative_to(path.parent.parent.parent.parent))
        style_attr_re = re.compile(r'style\s*=\s*["\']([^"\']*)["\']', re.IGNORECASE)

        findings: list[str] = []
        for line_no, line in enumerate(text.splitlines(), 1):
            if line.strip().startswith('{#') or line.strip().startswith('<!--'):
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
                    findings.append(f'L{line_no}')

        if findings:
            errors.append(
                f'{rel}: HTML 新增 layout inline style ({len(findings)} 处),'
                f'应使用 CSS class 或 CSS custom property.'
            )

    # 检查 JS
    for path in js_files:
        text = path.read_text(encoding='utf-8', errors='replace')
        rel = str(path.relative_to(path.parent.parent.parent.parent))

        findings: list[str] = []
        for line_no, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if COMMENT_LINE_RE.match(stripped):
                continue
            if JS_STYLE_ASSIGN_RE.search(line):
                findings.append(f'L{line_no}')

        if findings:
            errors.append(
                f'{rel}: JS 新增 .style.xxx 布局赋值 ({len(findings)} 处),'
                f'应使用 class 切换或 CSS custom property.'
            )

    return errors


def _check_static(repo_root: Path) -> tuple[list[str], list[str]]:
    """汇总静态资源契约；目录或必需模板缺失时 fail-closed 为错误。"""
    errors: list[str] = []
    warnings: list[str] = []
    static = repo_root / 'java/web/src/main/resources/static'
    if not static.exists():
        return [f'静态资源目录不存在:{static}'], []

    css_files = list(static.rglob('*.css'))
    js_files = list(static.rglob('*.js'))

    # 先验证基础文件与加载关系，再执行独立的 CSS、JavaScript 规则。
    errors.extend(_check_no_important(css_files))

    base_html = static.parent / 'templates' / 'base.html'
    if base_html.exists():
        errors.extend(_check_css_load_order(base_html.read_text(encoding='utf-8')))
    else:
        errors.append(f'css-load-order-contract: base.html 不存在:{base_html}')

    errors.extend(_check_no_dead_css(css_files))

    templates = static.parent / 'templates'
    if templates.exists():
        html_files = list(templates.rglob('*.html'))
        errors.extend(_check_no_duplicate_base_css(html_files))

    pm_errors, pm_warnings = _check_payload_modal_ownership(css_files)
    errors.extend(pm_errors)
    warnings.extend(pm_warnings)

    warnings.extend(_check_shell_ownership(css_files))

    warnings.extend(_check_innerhtml_safety(js_files))
    for path in css_files:
        rel = path.relative_to(repo_root).as_posix()
        text = path.read_text(encoding='utf-8', errors='replace')
        if (
            re.search(r'position\s*:\s*fixed', text)
            and 'modal' not in rel.lower()
            and rel
            not in (
                'java/web/src/main/resources/static/css/session-detail.css',
                'java/web/src/main/resources/static/css/ui-primitives.css',
            )
        ):
            warnings.append(f'{rel}: fixed 布局需确认是否符合桌面端 contract.')

    for path in js_files:
        rel = path.relative_to(repo_root).as_posix()
        text = path.read_text(encoding='utf-8', errors='replace')
        if 'eval(' in text:
            errors.append(f'{rel}: 禁止 eval.')

    # 最后用已审计基线区分存量与新增；无效基线按空基线处理，不能掩盖违规。
    baseline = _load_ownership_baseline(repo_root)

    _apply_baseline_gate(
        errors,
        warnings,
        _check_css_ownership_gate(css_files),
        baseline.get('css_ownership_violations', []),
        'css-ownership',
    )

    _apply_baseline_gate(
        errors,
        warnings,
        _check_no_global_component_override(css_files),
        baseline.get('component_override_violations', []),
        'component-override',
    )

    _apply_baseline_gate(
        errors,
        warnings,
        _check_selector_depth_new_block(css_files),
        baseline.get('selector_depth_violations', []),
        'selector-depth',
    )

    _apply_baseline_gate(
        errors,
        warnings,
        _check_no_raw_innerhtml_new_block(js_files),
        baseline.get('raw_innerhtml_violations', []),
        'raw-innerhtml',
    )

    html_files_for_style = list(templates.rglob('*.html')) if templates.exists() else []
    layout_errors = _check_no_layout_inline_style_new_block(html_files_for_style, js_files)
    _apply_baseline_gate_combined(
        errors,
        warnings,
        layout_errors,
        baseline.get('layout_inline_style_html_violations', [])
        + baseline.get('layout_style_js_violations', []),
        'layout-inline-style',
    )
    return errors, warnings


def _load_ownership_baseline(repo_root: Path) -> dict:
    """加载 Web ownership 基线；文件无效时 fail-closed 为无基线。"""
    baseline_path = (
        repository_root() / 'scripts' / 'checks' / 'web' / 'baselines' / 'ownership_baseline.json'
    )
    if baseline_path.exists():
        try:
            return json.loads(baseline_path.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, ValueError):
            # 无效基线不得掩盖任何扫描结果。
            pass
    return {}


def _apply_baseline_gate(
    errors: list[str],
    warnings: list[str],
    gate_results: list[str],
    baseline_items: list[str],
    gate_name: str,
) -> None:
    """将命中 baseline 的违规归为警告，其余违规归为错误。"""
    # 同时接受完整条目、文件和 selector，以兼容现有基线的两种记录格式。
    baseline_set = set()
    for item in baseline_items:
        baseline_set.add(item)
        # 也添加文件名部分用于匹配
        if ':' in item:
            baseline_set.add(item.split(':')[0])
            # 同时加入路径前缀之后的选择器，支持跨路径匹配。
            # Format: "路径/到/文件.css:selector" 或 "路径/文件.css: selector ..."。
            colon_idx = item.index(':')
            selector_part = item[colon_idx + 1 :].strip()
            if selector_part:
                sel = selector_part.split(' (')[0].strip()
                if sel:
                    baseline_set.add(sel)

    for result in gate_results:
        is_known = any(b in result for b in baseline_set)
        if is_known:
            warnings.append(f'[{gate_name}] 存量: {result}')
        else:
            errors.append(f'[{gate_name}] 新增: {result}')


def _apply_baseline_gate_combined(
    errors: list[str],
    warnings: list[str],
    gate_results: list[str],
    baseline_items: list[str],
    gate_name: str,
) -> None:
    """合并多来源 baseline 后，将存量违规归为警告、新增违规归为错误。"""
    baseline_set = set()
    for item in baseline_items:
        baseline_set.add(item)
        # 提取文件名部分
        parts = item.split('/')
        if parts:
            baseline_set.add(parts[-1])
            baseline_set.add(item.split(':')[0] if ':' in item else item)
        # 同时加入选择器部分，支持跨路径匹配。
        if ':' in item:
            colon_idx = item.index(':')
            selector_part = item[colon_idx + 1 :].strip()
            if selector_part:
                sel = selector_part.split(' (')[0].strip()
                if sel:
                    baseline_set.add(sel)

    for result in gate_results:
        is_known = any(b in result for b in baseline_set)
        if is_known:
            warnings.append(f'[{gate_name}] 存量: {result}')
        else:
            errors.append(f'[{gate_name}] 新增: {result}')


def check(arguments: list[str]) -> CheckResult:
    """解析统一 CLI 参数，并保持静态契约原有顺序返回全部阻断诊断。"""
    parser = argument_parser(description='检查 Web 静态资源契约')
    parser.parse_args(arguments)
    errors, warnings = _check_static(Path.cwd())
    if errors and os.environ.get('SESSION_BROWSER_STATIC_CONTRACT_SHOW_WARNINGS') == '1':
        errors = [*(f'[WARN] {item}' for item in warnings), *errors]
    return CheckResult.from_errors(errors)
