#!/usr/bin/env python3
"""提供 检查 scroll shadow behavior 脚本能力。"""

from __future__ import annotations

import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
SRC = REPO_ROOT / 'src' / 'session_browser' / 'web'

CSS_FILE = SRC / 'static' / 'css' / 'shell.css'
JS_FILES = [
    SRC / 'static' / 'js' / 'app.js',
    SRC / 'static' / 'js' / 'data-table.js',
    SRC / 'static' / 'js' / 'timeline.js',
    SRC / 'static' / 'js' / 'keyboard.js',
]
INLINE_JS_FILES = [
    SRC / 'templates' / 'base.html',
    SRC / 'templates' / 'session.html',
]

_COUNTERS = {'OK': 0, 'FAIL': 0, 'WARN': 0}
_findings: list[tuple[str, str]] = []


# 重置counters。
def _reset_counters() -> None:
    """说明：
        clears 仅 in-memory counters 和 findings；it does 不 读取 文件, 写入。
    """
    _COUNTERS.update({'OK': 0, 'FAIL': 0, 'WARN': 0})
    _findings.clear()


# 维护报告。
def report(level: str, check: str, detail: str = '') -> None:
    """参数：
        level: level 参数。
        check: 检查 参数。
        detail: 可选context explaining matched 或 缺失 static pattern。
    """
    tag = {'OK': 'OK', 'FAIL': 'FAIL', 'WARN': 'WARN'}.get(level, '??')
    line = f'  [{tag}] {check}'
    if detail:
        line += f' — {detail}'
    print(line)
    _findings.append((level, check))
    counter_key = level if level in _COUNTERS else 'WARN'
    _COUNTERS[counter_key] += 1


# 读取文件。
def read_file(p: Path) -> str:
    """参数：
        p: p 参数。

    返回：
        文件 text 当 present；空 字符串 当 可选 assets are absent。
    """
    if not p.exists():
        return ''
    return p.read_text(encoding='utf-8')


# 读取全部 JavaScript。
def read_all_js() -> str:
    """返回：
        Combined JavaScript text in configured 文件 order；缺失 文件 contribute nothing。
    """
    parts: list[str] = []
    for f in JS_FILES:
        content = read_file(f)
        if content:
            parts.append(content)
    return '\n'.join(parts)


# 读取全部 inline JavaScript。
def read_all_inline_js() -> str:
    """返回：
        Combined inline JavaScript bodies, preserving template order用于诊断信息。
    """
    parts: list[str] = []
    for f in INLINE_JS_FILES:
        content = read_file(f)
        if not content:
            continue
        for m in re.finditer(r'<script[^>]*>(.*?)</script>', content, re.DOTALL):
            parts.append(m.group(1))
    return '\n'.join(parts)


# 检查right shadow absent。
def check_right_shadow_absent(css: str) -> None:
    """参数：
        css: 待检查的 CSS 文本。
    """
    has_after = bool(re.search(r'\.table-wrap\s*::after\s*\{', css))
    if not has_after:
        report('OK', 'Right shadow (.table-wrap::after) removed')
    else:
        report('FAIL', 'Right shadow (.table-wrap::after) still present')


# 检查left shadow absent。
def check_left_shadow_absent(css: str) -> None:
    """参数：
        css: 待检查的 CSS 文本。
    """
    has_before = bool(re.search(r'\.table-wrap\s*::before\s*\{', css))
    if not has_before:
        report('OK', 'Left shadow (.table-wrap::before) removed')
    else:
        report('FAIL', 'Left shadow (.table-wrap::before) still present')


# 检查state classes absent。
def check_state_classes_absent(css: str) -> None:
    """参数：
        css: 待检查的 CSS 文本。
    """
    has_left = '.is-scroll-left' in css
    has_right = '.is-scroll-right' in css
    if not has_left:
        report('OK', 'is-scroll-left class rule removed')
    else:
        report('FAIL', 'is-scroll-left class rule still present')
    if not has_right:
        report('OK', 'is-scroll-right class rule removed')
    else:
        report('FAIL', 'is-scroll-right class rule still present')


# 检查JavaScript shadow absent。
def check_js_shadow_absent(js: str, inline_js: str) -> None:
    """参数：
        js: 待执行的 JavaScript 表达式。
        inline_js: 内联 JavaScript 文本。
    """
    all_js = js + '\n' + inline_js

    for name in ['updateScrollShadow', 'initScrollShadows', 'initAllScrollShadows']:
        if name not in all_js:
            report('OK', f'{name} removed from JS')
        else:
            report('FAIL', f'{name} still present in JS')

    # 检查用于 resize listener tied到shadow init。
    has_resize_shadow = bool(
        re.search(r"addEventListener.*['\"]resize['\"].*initAllScrollShadows", all_js)
    )
    if not has_resize_shadow:
        report('OK', 'resize+shadow init listener removed')
    else:
        report('FAIL', 'resize+shadow init listener still present')

    # 检查用于 profile-loaded shadow reinit。
    has_profile_shadow = bool(
        re.search(r"addEventListener.*['\"]profile-loaded['\"].*initAllScrollShadows", all_js)
    )
    if not has_profile_shadow:
        report('OK', 'profile-loaded+shadow reinit listener removed')
    else:
        report('FAIL', 'profile-loaded+shadow reinit listener still present')


# 检查表格 wrap 布局。
def check_table_wrap_layout(css: str) -> None:
    """参数：
        css: 待检查的 CSS 文本。
    """
    has_base = bool(re.search(r'\.table-wrap\s*\{', css))
    has_overflow = 'overflow-x' in css and 'auto' in css
    if has_base:
        report('OK', '.table-wrap base rule preserved')
    else:
        report('FAIL', '.table-wrap base rule missing (layout broken)')
    if has_overflow:
        report('OK', 'overflow-x:auto preserved (scrollable layout)')
    else:
        report('WARN', 'overflow-x:auto not confirmed')


# 解析命令行参数并运行脚本入口。
def main() -> int:
    """返回：
        进程退出码: 0用于pass 或 pass-带-警告, 1用于residual。 behavior, 和 2 当 必需 CSS 输入 is 缺失。
    """
    print('=' * 60)
    print('  Scroll Shadow Removal Verification')
    print('=' * 60)

    css = read_file(CSS_FILE)
    js = read_all_js()
    inline_js = read_all_inline_js()

    if not css:
        print(f'\n  ERROR: CSS file not found: {CSS_FILE}')
        return 2

    print('\n  [1] CSS: .table-wrap::after removed')
    print('  ' + '-' * 40)
    check_right_shadow_absent(css)

    print('\n  [2] CSS: .table-wrap::before removed')
    print('  ' + '-' * 40)
    check_left_shadow_absent(css)

    print('\n  [3] CSS: is-scroll-left/right classes removed')
    print('  ' + '-' * 40)
    check_state_classes_absent(css)

    print('\n  [4] JS: scroll shadow functions removed')
    print('  ' + '-' * 40)
    check_js_shadow_absent(js, inline_js)

    print('\n  [5] CSS: .table-wrap layout preserved')
    print('  ' + '-' * 40)
    check_table_wrap_layout(css)

    # 结果汇总。
    print('\n' + '=' * 60)
    total = sum(_COUNTERS.values())
    ok = _COUNTERS['OK']
    warn = _COUNTERS['WARN']
    fail = _COUNTERS['FAIL']
    print(f'  Results: {ok} OK, {warn} WARN, {fail} FAIL (total: {total})')
    if fail:
        print('  Status: FAIL — scroll shadow residuals found')
    elif warn:
        print('  Status: PASS with warnings')
    else:
        print('  Status: PASS — scroll shadow feature fully removed')
    print('=' * 60)

    return 1 if fail > 0 else 0


if __name__ == '__main__':
    sys.exit(main())
