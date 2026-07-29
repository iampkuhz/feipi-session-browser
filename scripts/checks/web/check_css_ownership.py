#!/usr/bin/env python3
"""检查 CSS 分层所有权、依赖方向与跨层重复定义。

样式层级若相互覆盖会让页面规则来源不可预测，因此阻断越权定义并保留颜色债务警告。唯一公开
入口是 `check(arguments)`；失败表示存在 BLOCK 级所有权违规，完整报告仍写入隔离 artifact。
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from scripts.checks._framework import CheckResult, argument_parser, repository_root
from scripts.gates import support as gate_support

if TYPE_CHECKING:
    from pathlib import Path

REPO_ROOT = repository_root()


@dataclass
class Violation:
    """记录一条带严重级别、规则标识和源码位置的 CSS 违规。"""

    severity: str  # 取值为 BLOCK 或 WARN
    rule: str  # 规则标识
    file: str  # CSS 文件名
    detail: str  # 违规描述
    line: int | None = None


@dataclass
class OwnershipCheck:
    """保存 `OwnershipCheck` 的结构化契约数据；字段由所属运行阶段构造并由后续报告读取。"""

    blocks: list[Violation] = field(default_factory=list)
    warnings: list[Violation] = field(default_factory=list)
    files_scanned: int = 0
    selectors_analyzed: int = 0


# ui-primitives.css 中定义的全局组件(页面 CSS 不得直接重写)
# 这些选择器在 ui-primitives 中有权威定义,页面 CSS 如需定制应使用
# 后代选择器(如 .sessions-page .card)或页面特有前缀(如 .sd-btn--*)
GLOBAL_COMPONENTS = {
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

# 页面 CSS 可以合法使用的共享基础选择器(不属于组件重定义)
SHARED_BASE_SELECTORS = {
    ':root',
}

# 豁免文件:这些文件不受跨层重复检查约束
EXEMPT_FROM_DUPLICATE = {
    'tokens.css',
    'base.css',
    'shell.css',
    'ui-primitives.css',
}


def _extract_css_rules(text: str) -> list[tuple[int, str, str]]:
    """提取 CSS rule 及其源码位置，不修改原始文本。"""
    rules: list[tuple[int, str, str]] = []
    # 去掉注释
    stripped = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
    lines = text.splitlines()

    # 字符 → 行号映射
    char_to_line: dict[int, int] = {}
    pos = 0
    for i, line in enumerate(lines, 1):
        for _ in range(len(line) + 1):
            char_to_line[pos] = i
            pos += 1

    # 用栈保留嵌套块的边界，避免把内层右括号归给外层选择器。
    stack: list[tuple[str, int]] = []
    i = 0
    while i < len(stripped):
        if stripped[i] == '{':
            selector_start = i
            while selector_start > 0 and stripped[selector_start - 1] not in '{};':
                selector_start -= 1
            selector = stripped[selector_start:i].strip()
            stack.append((selector, selector_start))
        elif stripped[i] == '}' and stack:
            selector, start = stack.pop()
            body = stripped[start + 1 : i].strip()
            line_no = char_to_line.get(start, 0)
            if line_no > 0:
                rules.append((line_no, selector, body))
        i += 1

    return rules


def _split_selectors(selector_str: str) -> list[str]:
    """按顶层逗号拆分 selector，不切开括号内的参数。"""
    depth = 0
    parts: list[str] = []
    current: list[str] = []
    for ch in selector_str:
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
        if ch == ',' and depth == 0:
            parts.append(''.join(current).strip())
            current = []
        else:
            current.append(ch)
    if current:
        parts.append(''.join(current).strip())
    return [p for p in parts if p and not p.startswith('@')]


def _is_base_selector(sel: str) -> bool:
    """判断 selector 是否以标准 HTML 元素开头。"""
    base_pattern = re.compile(
        r'^(html|body|div|span|p|a|img|ul|ol|li|table|th|td|thead|tbody|tfoot|'
        r'tr|h[1-6]|pre|code|blockquote|hr|input|button|textarea|select|form|'
        r'label|fieldset|legend|optgroup|option|datalist|output|progress|meter|'
        r'details|summary|dialog|main|header|footer|nav|article|section|aside|'
        r'figure|figcaption|canvas|svg|video|audio|source|track|embed|iframe|'
        r'object|param|map|area|link|meta|style|script|noscript|template|'
        r'slot|br|wbr|del|ins|s|u|b|i|em|strong|small|sub|sup|mark|abbr|'
        r'cite|dfn|data|time|kbd|var|samp|q|bdi|bdo|ruby|rt|rp)\b'
    )
    return bool(base_pattern.match(sel))


def _check_layer_purity(  # noqa: PLR0912 - layer-specific CSS ownership rules stay grouped.
    filename: str,
    rules: list[tuple[int, str, str]],
) -> list[Violation]:
    """检查 CSS layer 纯度，返回跨层声明违规。"""
    violations: list[Violation] = []

    if filename == 'tokens.css':
        # tokens.css 只应有 :root 包裹的自定义属性声明
        for lineno, selector, _body in rules:
            if selector.startswith('@'):
                continue
            # :root 包裹是合法的
            if selector == ':root':
                continue
            violations.append(
                Violation(
                    severity='BLOCK',
                    rule='layer-purity',
                    file=filename,
                    line=lineno,
                    detail=f"tokens.css 不得包含选择器规则:'{selector[:100]}'",
                )
            )

    elif filename == 'base.css':
        # base.css 只允许:通配符,HTML 元素,伪类,:root,@media,@property
        for lineno, selector, _body in rules:
            if selector.startswith('@'):
                continue
            for raw_sel in _split_selectors(selector):
                sel = raw_sel.strip()
                if not sel:
                    continue
                if sel in SHARED_BASE_SELECTORS:
                    continue
                if sel.startswith(':root'):
                    continue
                if _is_base_selector(sel):
                    continue
                # 伪类/伪元素
                if sel.startswith(':') and not any(c in sel for c in '.#'):
                    continue
                # 通配符
                if sel.startswith('*'):
                    continue
                # body/HTML 的复合选择器
                if sel.startswith('body') or sel.startswith('html'):
                    continue
                violations.append(
                    Violation(
                        severity='BLOCK',
                        rule='layer-purity',
                        file=filename,
                        line=lineno,
                        detail=f"base.css 包含非元素选择器:'{sel[:100]}'",
                    )
                )

    elif filename == 'shell.css':
        # shell.css 不应包含页面内组件(按钮,卡片等)
        for lineno, selector, _body in rules:
            if selector.startswith('@'):
                continue
            for raw_sel in _split_selectors(selector):
                sel = raw_sel.strip()
                if not sel:
                    continue
                # 检查是否包含页面级选择器
                page_pats = [
                    r'\.sessions-page\b',
                    r'\.session-detail-page\b',
                    r'\.dashboard-page\b',
                    r'\.projects-page\b',
                    r'\.agents-page\b',
                    r'\.glossary-page\b',
                ]
                if any(re.search(p, sel) for p in page_pats):
                    violations.append(
                        Violation(
                            severity='BLOCK',
                            rule='layer-purity',
                            file=filename,
                            line=lineno,
                            detail=f"shell.css 包含页面级选择器:'{sel[:100]}'",
                        )
                    )

    elif filename == 'ui-primitives.css':
        # ui-primitives 不应包含页面级选择器
        for lineno, selector, _body in rules:
            if selector.startswith('@'):
                continue
            for raw_sel in _split_selectors(selector):
                sel = raw_sel.strip()
                if not sel:
                    continue
                page_pats = [
                    r'\.sessions-page\b',
                    r'\.session-detail-page\b',
                    r'\.sd-shell\b',
                    r'\.sd-page\b',
                    r'\.dashboard-page\b',
                    r'\.projects-page\b',
                    r'\.agents-page\b',
                    r'\.glossary-page\b',
                ]
                if any(re.search(p, sel) for p in page_pats):
                    violations.append(
                        Violation(
                            severity='BLOCK',
                            rule='layer-purity',
                            file=filename,
                            line=lineno,
                            detail=f"ui-primitives.css 包含页面级选择器:'{sel[:100]}'",
                        )
                    )

    return violations


def _check_cross_layer_duplicate(
    filename: str,
    rules: list[tuple[int, str, str]],
    ui_primitives_selectors: set[str],
) -> list[Violation]:
    """返回页面 CSS 直接重写全局组件产生的跨层违规。"""
    violations: list[Violation] = []

    if filename in EXEMPT_FROM_DUPLICATE:
        return violations

    for lineno, selector, _body in rules:
        if selector.startswith('@'):
            continue
        for raw_sel in _split_selectors(selector):
            sel = raw_sel.strip()
            if not sel:
                continue
            # 检查选择器是否为全局组件的直接重写
            for comp in GLOBAL_COMPONENTS:
                # 精确匹配:选择器就是全局组件名
                if sel == comp:
                    violations.append(
                        Violation(
                            severity='WARN',
                            rule='cross-layer-duplicate',
                            file=filename,
                            line=lineno,
                            detail=(
                                f"{filename} 直接重写全局组件 '{comp}'"
                                '(已在 ui-primitives.css 定义),应使用后代选择器或页面特有变体'
                            ),
                        )
                    )
                    break
                # 复合选择器中以全局组件开头且非后代选择器
                # 例如 ".btn.primary" 是修饰符变体(合法),
                # 但 ".btn" 直接重写不是
                if sel.startswith(comp + '.') or sel.startswith(comp + ':'):
                    # 修饰符变体(如 .btn--primary, .btn:hover)是合法的
                    pass
                # 后代选择器:以页面级选择器开头,合法

    return violations


def _check_dependency_direction(
    filename: str,
    rules: list[tuple[int, str, str]],
) -> list[Violation]:
    """检查 CSS layer 依赖方向。"""
    violations: list[Violation] = []

    low_level = {'tokens.css', 'base.css', 'shell.css', 'ui-primitives.css'}
    if filename not in low_level:
        return violations

    # 排除 shell 级选择器(如 .sd-shell 是 session-detail 的外壳包装器)
    shell_wrappers = {
        r'\.sd-shell\b',  # session-detail 外壳
        r'\.sd-page\b',  # session-detail 页面容器
        r'\.sd-content\b',  # session-detail 内容区
    }

    # 真正的页面内容选择器(不应在低层出现)
    page_patterns = [
        r'\.sessions-page\b',
        r'\.session-detail-page\b',
        r'\.dashboard-page\b',
        r'\.projects-page\b',
        r'\.agents-page\b',
        r'\.glossary-page\b',
        r'\.state-panel\b',
    ]

    for lineno, selector, _body in rules:
        if selector.startswith('@'):
            continue
        # 跳过 shell 级包装器选择器
        if filename == 'shell.css' and any(re.search(p, selector) for p in shell_wrappers):
            continue
        for pat in page_patterns:
            if re.search(pat, selector):
                violations.append(
                    Violation(
                        severity='WARN',
                        rule='dependency-direction',
                        file=filename,
                        line=lineno,
                        detail=f"{filename} 反向引用页面级选择器:'{selector[:100]}' "
                        f'(依赖方向应为 page -> ui-primitives -> shell -> base -> tokens)',
                    )
                )
                break

    return violations


def _check_hardcoded_colors(
    filename: str,
    rules: list[tuple[int, str, str]],
) -> list[Violation]:
    """检查不符合 token 约束的硬编码颜色。"""
    violations: list[Violation] = []

    # 豁免:tokens 是颜色定义源,base/shell/ui-primitives 可以有基础色
    if filename in ('tokens.css', 'base.css', 'shell.css', 'ui-primitives.css'):
        return violations

    hex_color = re.compile(r'(?<![a-zA-Z])#[0-9a-fA-F]{3,8}\b')
    safe_colors = {'#000', '#000000', '#fff', '#ffffff'}

    for lineno, selector, body in rules:
        matches = hex_color.findall(body)
        for color in matches:
            if color.lower() not in safe_colors:
                violations.append(
                    Violation(
                        severity='WARN',
                        rule='hardcoded-color',
                        file=filename,
                        line=lineno,
                        detail=f"{filename} 使用硬编码颜色 '{color}'(选择器: '{selector[:60]}...'),"
                        f'建议使用 token 变量',
                    )
                )

    return violations


def _check_css_ownership(repo_root: Path) -> OwnershipCheck:
    """执行 CSS 所有权规则；目录缺失时产生 BLOCK，避免静默放行。"""
    result = OwnershipCheck()
    css_dir = repo_root / 'java/web/src/main/resources/static/css'

    if not css_dir.exists():
        result.blocks.append(
            Violation(
                severity='BLOCK',
                rule='missing-dir',
                file='N/A',
                detail=f'CSS 目录不存在:{css_dir}',
            )
        )
        return result

    css_files = sorted(css_dir.glob('*.css'))
    result.files_scanned = len(css_files)

    # 先建立权威组件层的 selector 集合，再逐文件执行各类所有权规则。
    ui_primitives_selectors: set[str] = set()
    ui_primitives_path = css_dir / 'ui-primitives.css'
    if ui_primitives_path.exists():
        text = ui_primitives_path.read_text(encoding='utf-8')
        for _, selector, _ in _extract_css_rules(text):
            for sel in _split_selectors(selector):
                ui_primitives_selectors.add(sel.strip())

    for css_path in css_files:
        filename = css_path.name
        text = css_path.read_text(encoding='utf-8')
        rules = _extract_css_rules(text)
        result.selectors_analyzed += len(rules)

        # BLOCK 与 WARN 分流必须在汇总阶段完成，避免报告层重新解释规则结果。
        result.blocks.extend(_check_layer_purity(filename, rules))

        for v in _check_cross_layer_duplicate(filename, rules, ui_primitives_selectors):
            (result.blocks if v.severity == 'BLOCK' else result.warnings).append(v)

        for v in _check_dependency_direction(filename, rules):
            (result.blocks if v.severity == 'BLOCK' else result.warnings).append(v)

        result.warnings.extend(_check_hardcoded_colors(filename, rules))

    return result


def _format_report(result: OwnershipCheck) -> str:
    """将结构化所有权结果格式化为稳定的人类可读报告。"""
    lines: list[str] = []
    lines.append('=' * 60)
    lines.append('CSS Ownership Gate Report')
    lines.append('=' * 60)
    lines.append(f'Files scanned:      {result.files_scanned}')
    lines.append(f'Selectors analyzed: {result.selectors_analyzed}')
    lines.append(f'Block violations:   {len(result.blocks)}')
    lines.append(f'Warnings:           {len(result.warnings)}')
    lines.append('')

    if result.blocks:
        lines.append('--- BLOCK violations ---')
        for v in result.blocks:
            line_info = f' (L{v.line})' if v.line else ''
            lines.append(f'  [BLOCK] {v.rule}{line_info}: {v.file} — {v.detail}')
        lines.append('')

    if result.warnings:
        lines.append('--- Warnings ---')
        for v in result.warnings:
            line_info = f' (L{v.line})' if v.line else ''
            lines.append(f'  [WARN]  {v.rule}{line_info}: {v.file} — {v.detail}')
        lines.append('')

    if not result.blocks and not result.warnings:
        lines.append('CSS ownership: PASS (no violations)')
    elif not result.blocks:
        lines.append(f'CSS ownership: PASS ({len(result.warnings)} warnings)')
    else:
        lines.append(
            f'CSS ownership: FAIL ({len(result.blocks)} block, {len(result.warnings)} warn)'
        )

    lines.append('=' * 60)
    return '\n'.join(lines)


def _artifact_dir(
    repo_root: Path,
    identity: gate_support.ExecutionIdentity | None = None,
) -> Path:
    """返回按 client/session/run 隔离的 CSS quality artifact 目录。"""
    resolved = identity or gate_support.identity_from_values()
    if not resolved.has_session or not resolved.has_run:
        process_id = f'pid-{os.getpid()}'
        resolved = gate_support.identity_from_values(
            agent_client=resolved.client,
            session_id=resolved.raw_session_id or process_id,
            agent_id=resolved.raw_agent_id,
            run_id=resolved.raw_run_id or process_id,
        )
    return gate_support.quality_dir(repo_root, resolved) / 'css-ownership'


def check(arguments: list[str]) -> CheckResult:
    """解析统一 CLI 参数，写出结构化报告，并按报告顺序返回 BLOCK 失败。"""
    parser = argument_parser(description='检查 CSS 分层所有权')
    parser.parse_args(arguments)
    repo_root = REPO_ROOT
    result = _check_css_ownership(repo_root)
    report = _format_report(result)

    # 完整报告写入隔离 artifact；失败时同一内容也作为统一 CLI 诊断返回。
    out_dir = _artifact_dir(repo_root)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / 'css-ownership-report.txt'
    out_file.write_text(report + '\n', encoding='utf-8')

    # JSON artifact 只序列化既有结果，不在报告阶段重新判定状态。
    json_report = {
        'schemaVersion': 1,
        'gate': 'css-ownership',
        'status': 'PASS' if not result.blocks else 'FAIL',
        'filesScanned': result.files_scanned,
        'selectorsAnalyzed': result.selectors_analyzed,
        'blockCount': len(result.blocks),
        'warningCount': len(result.warnings),
        'blocks': [
            {'rule': v.rule, 'file': v.file, 'line': v.line, 'detail': v.detail}
            for v in result.blocks
        ],
        'warnings': [
            {'rule': v.rule, 'file': v.file, 'line': v.line, 'detail': v.detail}
            for v in result.warnings
        ],
    }
    json_path = out_dir / 'css-ownership-gate.json'
    json_path.write_text(
        json.dumps(json_report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8'
    )

    if not result.blocks:
        return CheckResult()
    return CheckResult.from_errors(report.splitlines())
