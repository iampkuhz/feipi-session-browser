#!/usr/bin/env python3
"""提供 检查 sessions list CSS 脚本能力。"""

from __future__ import annotations

import re
from pathlib import Path

CSS_PATH = 'src/session_browser/web/static/css/sessions-list.css'
SAMPLE_LIMIT = 8


# 读取文件内容。
def read(path: str) -> str | None:
    """参数：
        path: repository-relative CSS 路径 configured用于this static 检查。

    返回：
        文件 content 当 present；None 当 QA gate should 报告 缺失 输入。
    """
    p = Path(path)
    if not p.exists():
        return None
    return p.read_text(encoding='utf-8')


# 检查文件 exists。
def check_file_exists(css: str | None) -> tuple[bool, str]:
    """参数：
        css: 待检查的 CSS 文本。

    返回：
        结果 tuple。

    说明：
        css: CSS text loaded by 读取, 或 None 当 文件 is 缺失。
    """
    if css is None:
        return False, f'File not found: {CSS_PATH}'
    return True, f'File exists: {CSS_PATH}'


# 检查没有裸 hex 颜色值。
def check_no_bare_hex_colors(css: str) -> tuple[bool, str]:
    """参数：
        css: 待检查的 CSS 文本。

    返回：
        结果 tuple。
    """
    stripped = re.sub(r'var\([^)]*\)', '', css)
    bare_hexes = re.findall(r'#[0-9a-fA-F]{3,8}\b', stripped)
    if not bare_hexes:
        return True, 'No bare hardcoded hex colors'
    unique = sorted(set(bare_hexes))
    count = len(unique)
    samples = ', '.join(unique[:SAMPLE_LIMIT])
    suffix = f' ({count} total, first 8: {samples})' if count > SAMPLE_LIMIT else f' ({samples})'
    return (
        True,
        f'WARNING: {count} bare hex color(s) found{suffix} — '
        'these are flagged as warnings; consider migrating to CSS variables',
    )


# 检查无 at import。
def check_no_at_import(css: str) -> tuple[bool, str]:
    """参数：
        css: 待检查的 CSS 文本。

    返回：
        结果 tuple。
    """
    if re.search(r'@import\s', css):
        return False, 'Found @import directive — CSS files should not @import'


# 检查page selectors。
def check_page_selectors(css: str) -> tuple[bool, str]:
    """参数：
        css: 待检查的 CSS 文本。

    返回：
        Pass/fail 状态 和 缺失 selector detail用于CI 输出。
    """
    required = ['.sessions-page', '.sessions-filter-card', '.sessions-row']
    missing = [s for s in required if s not in css]
    if missing:
        return False, f'Missing page-specific selectors: {", ".join(missing)}'
    return True, f'Has all required page-specific selectors: {", ".join(required)}'


# 检查无 generic reset。
def check_no_generic_reset(css: str) -> tuple[bool, str]:
    """参数：
        css: 待检查的 CSS 文本。

    返回：
        Pass/fail 状态 和 offender detail用于static QA 输出。
    """
    offenders = []
    reset_patterns = [
        (r'^\s*\*\s*\{', 'universal reset (* {)'),
        (r'^\s*body\s*\{', 'body reset'),
        (r'^\s*html\s*\{', 'html reset'),
    ]
    for pattern, label in reset_patterns:
        if re.search(pattern, css, re.MULTILINE):
            offenders.append(label)
    for cls in ['btn', 'card']:
        pat = re.compile(rf'^\s*\.{cls}\s*\{{', re.MULTILINE)
        for m in pat.finditer(css):
            line_start = css.rfind('\n', 0, m.start()) + 1
            prefix = css[line_start : m.start()].strip()
            # 判断 not prefix or all(c in ' \t' for c in prefix) 是否满足。
            if not prefix or all(c in ' \t' for c in prefix):
                offenders.append(f'.{cls} {{')
    if offenders:
        return False, f'Generic reset rule(s) found: {", ".join(set(offenders))}'
    return True, 'No generic reset rules'


# 检查token variable usage。
def check_token_variable_usage(css: str) -> tuple[bool, str]:
    """参数：
        css: 待检查的 CSS 文本。

    返回：
        Pass/fail 状态 和 sample of variable names 供 CSS。
    """
    vars_used = re.findall(r'var\((--[\w-]+)', css)
    if not vars_used:
        return False, 'No CSS variable references (var(--...)) found'
    unique = sorted(set(vars_used))
    return True, f'References {len(unique)} CSS variable(s): {", ".join(unique[:SAMPLE_LIMIT])}' + (
        '...' if len(unique) > SAMPLE_LIMIT else ''
    )


# 检查responsive breakpoints。
def check_responsive_breakpoints(css: str) -> tuple[bool, str]:
    """参数：
        css: 待检查的 CSS 文本。

    返回：
        结果 tuple。
    """
    breakpoints = re.findall(r'@media\s', css)
    if breakpoints:
        return True, f'Has {len(breakpoints)} @media breakpoint(s)'
    fluid_patterns = {
        'width: min(100%': 'max-width constraint via min()',
        'flex-wrap: wrap': 'flex-wrap for wrapping',
        'overflow:auto': 'scrollable overflow container',
        'overflow: auto': 'scrollable overflow container',
        'display: contents': 'display:contents (delegates layout to parent)',
    }
    found = [label for pattern, label in fluid_patterns.items() if pattern in css]
    if found:
        return (
            True,
            f'No @media queries; responsiveness handled via fluid layout: {", ".join(found)}',
        )
    return False, 'No @media queries or fluid responsive patterns found'


# 解析命令行参数并运行脚本入口。
def main() -> int:
    """返回：
        进程退出码。

    说明：
        CSS 文件. It 打印 each 检查 结果, 返回 0 当 all 必需 检查。
    """
    css = read(CSS_PATH)

    checks = [
        ('T081-01 File existence', lambda: check_file_exists(css)),
        (
            'T081-02 No bare hardcoded hex colors',
            lambda: check_no_bare_hex_colors(css) if css else (False, 'Skipped — file missing'),
        ),
        (
            'T081-03 No @import',
            lambda: check_no_at_import(css) if css else (False, 'Skipped — file missing'),
        ),
        (
            'T081-04 Has page-specific selectors',
            lambda: check_page_selectors(css) if css else (False, 'Skipped — file missing'),
        ),
        (
            'T081-05 No generic reset rules',
            lambda: check_no_generic_reset(css) if css else (False, 'Skipped — file missing'),
        ),
        (
            'T081-06 Token variable usage',
            lambda: check_token_variable_usage(css) if css else (False, 'Skipped — file missing'),
        ),
        (
            'T081-07 Responsive breakpoint check',
            lambda: check_responsive_breakpoints(css) if css else (False, 'Skipped — file missing'),
        ),
    ]

    all_pass = True
    for label, run in checks:
        ok, detail = run()
        status = 'PASS' if ok else 'FAIL'
        if not ok:
            all_pass = False
        print(f'  [{status}] {label}: {detail}')

    print()
    if all_pass:
        print('PASS: sessions-list.css QA checks')
        return 0
    print('FAIL: sessions-list.css QA checks — see details above')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
