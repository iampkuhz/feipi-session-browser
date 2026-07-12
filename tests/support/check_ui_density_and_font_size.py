#!/usr/bin/env python3
"""提供 检查 UI density and font size 脚本能力。"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# 配置项。
# ---------------------------------------------------------------------------

CSS_FILE = (
    Path(__file__).resolve().parents[2]
    / 'java'
    / 'web'
    / 'src'
    / 'main'
    / 'resources'
    / 'static'
    / 'css'
    / 'tokens.css'
)
MAX_SELECTOR_LENGTH = 200
MAX_TINY_RULES_SHOWN = 50

TEXT_TOKENS = {
    '--text-micro': {'value_px': None},
    '--text-xs': {'value_px': None},
    '--text-sm': {'value_px': None},
    '--text-base': {'value_px': None},
    '--text-lg': {'value_px': None},
    '--text-xl': {'value_px': None},
    '--text-metric': {'value_px': None},
    '--text-metric-sm': {'value_px': None},
}

THRESHOLDS = [
    ('__token__--text-base', 'CSS variable --text-base', 14, '--text-lg'),
    (r'\.data-table\b', 'Table body (.data-table)', 13, '--text-sm'),
    (r'\.preview-cell\b', 'Timeline preview (.preview-cell)', 14, '--text-lg'),
    (r'\.btn\b', 'Button (.btn)', 13, '--text-sm'),
    (r'\.session-info-bar\b', 'Timestamp bar (.session-info-bar)', 12, '--text-sm'),
    (r'\.metrics-strip__label\b', 'Metrics strip label', 12, '--text-sm'),
    (r'\.metrics-strip__value\b', 'Metrics strip value', 12, '--text-sm'),
]


# 解析px。
def parse_px(value: str) -> float | None:
    """参数：
        value: 待解析的值。

    返回：
        解析后的 HookContext；失败时携带 parse_error。
    """
    m = re.match(r'^([0-9.]+)\s*px$', value.strip())
    if m:
        return float(m.group(1))
    return None


# 解析CSS tokens。
def parse_css_tokens(css_text: str) -> dict[str, dict]:
    """参数：
        css_text: 待检查的 CSS 文本。

    返回：
        token name 到原始值和已解析 pixel metadata 的映射。
    """
    tokens: dict[str, dict] = {name: {'value_px': None} for name in TEXT_TOKENS}
    root_m = re.search(r':root\s*\{((?:[^{}]|\{[^{}]*\})*)\}', css_text)
    if not root_m:
        return tokens
    block = root_m.group(1)
    for name, info in tokens.items():
        m = re.search(re.escape(name) + r'\s*:\s*([^;]+);', block)
        if m:
            px = parse_px(m.group(1).strip())
            if px is not None:
                info['value_px'] = px
    return tokens


# 解析token ref。
def resolve_token_ref(value: str, tokens: dict[str, dict]) -> tuple[float | None, str]:
    """参数：
        value: 待解析的值。
        tokens: 已解析的 token metadata。

    返回：
        由resolved pixel 值 和 display label used in 报告.组成的 tuple。
    """
    value = value.strip()

    px = parse_px(value)
    if px is not None:
        return px, f'{px}px (literal)'

    m = re.match(r'^var\(\s*(--[a-zA-Z0-9_-]+)\s*\)$', value)
    if m:
        token_name = m.group(1)
        if token_name in tokens and tokens[token_name]['value_px'] is not None:
            px_val = tokens[token_name]['value_px']
            return px_val, f'{px_val}px (via {token_name})'
        return None, f'unresolved: {value}'

    m = re.match(r'^var\(\s*--[a-zA-Z0-9_-]+\s*,\s*(.+?)\s*\)$', value)
    if m:
        fallback = m.group(1).strip()
        return resolve_token_ref(fallback, tokens)

    return None, f'unresolved: {value}'


# 提取font 大小 rules。
def extract_font_size_rules(css_text: str) -> list[dict]:
    """参数：
        css_text: 待检查的 CSS 文本。

    返回：
        列出of selector, 值, 和 source 行 dictionaries。
    """
    results = []

    css_no_comments = re.sub(r'/\*.*?\*/', '', css_text, flags=re.DOTALL)

    inline_pat = re.compile(r'([^{@][^{]*?)\s*\{\s*font-size\s*:\s*([^;]+)\s*;\s*\}')
    for m in inline_pat.finditer(css_no_comments):
        selector = m.group(1).strip()
        value = m.group(2).strip()
        if selector.startswith('@') or '/' in selector:
            continue
        selector = re.sub(r'\s+', ' ', selector).strip()
        if not selector or len(selector) > MAX_SELECTOR_LENGTH:
            continue
        results.append(
            {'selector': selector, 'value': value, 'line': _line_number(css_text, m.start())}
        )

    block_pat = re.compile(r'([^{@][^{]*?)\s*\{([^}]+)\}', re.MULTILINE)
    for m in block_pat.finditer(css_no_comments):
        selector = m.group(1).strip()
        block = m.group(2)
        fs_m = re.search(r'font-size\s*:\s*([^;]+);', block)
        if fs_m:
            value = fs_m.group(1).strip()
            already = any(r['selector'] == selector and r['value'] == value for r in results)
            if not already:
                selector = re.sub(r'\s+', ' ', selector).strip()
                if not selector or len(selector) > MAX_SELECTOR_LENGTH:
                    continue
                results.append(
                    {
                        'selector': selector,
                        'value': value,
                        'line': _line_number(css_text, m.start()),
                    }
                )

    return results


# 维护行 number。
def _line_number(text: str, pos: int) -> int:
    """参数：
        text: 待检查的文本。
        pos: pos 参数。

    返回：
        进程退出码。
    """
    return text[:pos].count('\n') + 1


# 维护selector 匹配。
def _selector_matches(pattern: str, selector: str) -> bool:
    """参数：
        pattern: 匹配用的 glob pattern。
        selector: 待检查的 CSS selector。

    返回：
        满足条件时返回 true，否则返回 false。
    """
    return bool(re.search(pattern, selector))


# 运行检查。
def run_checks(css_path: Path) -> tuple[bool, list[str]]:  # noqa: PLR0912, PLR0915 - keeps ordered static gate report.
    """参数：
        css_path: CSS 文件路径 selected by CLI 或 默认 gate。

    返回：
        Tuple containing overall pass 状态 和 ordered 报告 行。
    """
    if not css_path.is_file():
        return False, [f'FAIL: CSS file not found: {css_path}']

    css_text = css_path.read_text(encoding='utf-8')
    tokens = parse_css_tokens(css_text)
    rules = extract_font_size_rules(css_text)

    lines: list[str] = []
    lines.append('=' * 72)
    lines.append('UI Density & Font-Size Check (compact mode)')
    lines.append('=' * 72)
    lines.append('')

    lines.append('── CSS Token Values ──')
    for name, info in tokens.items():
        status = 'OK' if info['value_px'] is not None else '??'
        val = f'{info["value_px"]}px' if info['value_px'] is not None else '(unresolved)'
        lines.append(f'  [{status}] {name} = {val}')
    lines.append('')

    lines.append('── Threshold Checks ──')
    all_pass = True

    for pattern, area, min_px, min_token in THRESHOLDS:
        if pattern.startswith('__token__'):
            token_name = pattern.replace('__token__', '')
            actual_px = tokens.get(token_name, {}).get('value_px')
            min_token_px = tokens.get(min_token, {}).get('value_px')
            if actual_px is None:
                lines.append(f'  [FAIL] {area}: {token_name} unresolved')
                all_pass = False
            elif min_token_px is not None and actual_px >= min_token_px:
                lines.append(
                    f'  [OK]   {area}: {token_name} = {actual_px}px >= {min_px}px '
                    f'({min_token}={min_token_px}px)'
                )
            elif actual_px >= min_px:
                lines.append(f'  [OK]   {area}: {token_name} = {actual_px}px >= {min_px}px')
            else:
                lines.append(
                    f'  [FAIL] {area}: {token_name} = {actual_px}px < {min_px}px '
                    f'(need >= {min_token}={min_token_px}px)'
                )
                all_pass = False
            continue

        matching = [r for r in rules if _selector_matches(pattern, r['selector'])]
        if not matching:
            lines.append(f"  [WARN] {area}: no font-size rule matching '{pattern}'")
            continue

        for rule in matching:
            px, desc = resolve_token_ref(rule['value'], tokens)
            if px is None:
                lines.append(
                    f"  [WARN] {area} ({rule['selector']}): unresolved font-size "
                    f"'{rule['value']}' (line {rule['line']})"
                )
                continue

            min_token_px = tokens.get(min_token, {}).get('value_px')
            min_token_label = min_token
            if min_token_px is not None:
                min_token_label = f'{min_token}={min_token_px}px'

            if px >= min_px:
                lines.append(
                    f'  [OK]   {area}: {rule["selector"]} = {desc} >= {min_px}px (threshold)'
                )
            else:
                lines.append(
                    f'  [FAIL] {area}: {rule["selector"]} = {desc} < {min_px}px '
                    f'(need >= {min_token_label})'
                )
                all_pass = False

    lines.append('')

    lines.append('── Potentially Too-Small Declarations (text-micro / text-xs) ──')
    tiny_rules = [r for r in rules if 'text-micro' in r['value'] or 'text-xs' in r['value']]
    tiny_rules.sort(key=lambda r: r['selector'])

    shown = 0
    for shown, rule in enumerate(tiny_rules, start=1):
        _px, desc = resolve_token_ref(rule['value'], tokens)
        lines.append(f'  line {rule["line"]:>4}: {rule["selector"][:60]:<60} -> {desc}')
        if shown >= MAX_TINY_RULES_SHOWN:
            remaining = len(tiny_rules) - shown
            if remaining > 0:
                lines.append(f'  ... and {remaining} more')
            break

    if not tiny_rules:
        lines.append('  (none found)')

    lines.append('')
    lines.append('=' * 72)
    if all_pass:
        lines.append('RESULT: ALL CHECKS PASSED')
    else:
        lines.append('RESULT: SOME CHECKS FAILED — review FAIL items above')
    lines.append('=' * 72)

    return all_pass, lines


# 解析命令行参数并运行脚本入口。
def main() -> None:
    css_path = CSS_FILE
    if len(sys.argv) > 1:
        css_path = Path(sys.argv[1])

    all_pass, report = run_checks(css_path)
    for line in report:
        print(line)

    sys.exit(0 if all_pass else 1)


if __name__ == '__main__':
    main()
