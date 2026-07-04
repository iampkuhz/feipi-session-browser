#!/usr/bin/env python3
"""提供 检查 DOM contracts 脚本能力。"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path.cwd()
errors: list[str] = []
passes: list[str] = []

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
primitive_file = ROOT / 'src/session_browser/web/templates/components/ui_primitives.html'
primitive_dir = primitive_file.parent / 'ui_primitives'


# 读取primitive 源码。
def _read_primitive_source() -> str:
    """返回：
        读取到的 primitive source 文本。
    """
    parts: list[str] = []
    if primitive_file.exists():
        parts.append(primitive_file.read_text(encoding='utf-8', errors='ignore'))
    if primitive_dir.is_dir():
        for path in sorted(primitive_dir.glob('*.html')):
            parts.append(path.read_text(encoding='utf-8', errors='ignore'))
    return '\n'.join(parts)


# 维护macro 块。
def _macro_blocks(text: str, name: str) -> str:
    """参数：
        text: 待检查的文本。
        name: 条目名称。

    返回：
        Matching macro body text, 或 空 字符串 当 macro 缺失。
    """
    pattern = re.compile(
        rf'{{% macro {re.escape(name)}\b.*?{{%-?\s*endmacro\s*%}}',
        re.DOTALL,
    )
    return '\n'.join(match.group(0) for match in pattern.finditer(text))


if primitive_file.exists():
    text = _read_primitive_source()

    canonical_macros = [
        'button',
        'icon_button',
        'badge',
        'metric_card',
        'metric_grid',
        'pagination',
        'token_bar',
        'tooltip',
        'popover',
        'section_card',
        'data_table',
        'filter_bar',
        'payload_modal',
        'empty_state',
        'error_state',
    ]
    all_macros = canonical_macros
    found: list[str] = []
    missing: list[str] = []
    for macro in all_macros:
        if re.search(rf'{{% macro {re.escape(macro)}\b', text):
            found.append(macro)
        else:
            missing.append(macro)

    if missing:
        errors.append(f'missing macros in ui_primitives.html: {", ".join(missing)}')
    else:
        passes.append(f'All {len(all_macros)} primitive macros present')
else:
    errors.append(f'ui_primitives.html not found: {primitive_file}')

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
if primitive_file.exists():
    text = _read_primitive_source()
    button_re = re.compile(r'<button\b([^>]*)>', re.I)
    buttons_with_action = 0
    buttons_without_action = 0

    for m in button_re.finditer(text):
        attrs = m.group(1)
        if 'data-action' in attrs or 'type="submit"' in attrs or "type='submit'" in attrs:
            buttons_with_action += 1
        else:
            buttons_without_action += 1

    if buttons_without_action > 0:
        errors.append(
            f'buttons without data-action/submit: {buttons_without_action} '
            f'(with: {buttons_with_action})'
        )
    else:
        passes.append(f'Button data-action coverage: {buttons_with_action} covered, 0 uncovered')

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
if primitive_file.exists():
    text = _read_primitive_source()
    pagination_checks: list[str] = []

    # 检查用于 pagination macro block。
    block = _macro_blocks(text, 'pagination')
    if not block:
        errors.append('pagination macro not found')
    else:
        checks = {
            'prev button': r'data-action=\"prev-page\"',
            'next button': r'data-action=\"next-page\"',
            'page input': r'data-action="page-input"',
            'page-status span': r'class="page-status"',
            'nav role': r'role="navigation"',
        }
        for label, pat in checks.items():
            if re.search(pat, block):
                pagination_checks.append(label)
            else:
                errors.append(f'pagination missing: {label}')

        if len(pagination_checks) == len(checks):
            passes.append(f'Pagination structure complete: {", ".join(pagination_checks)}')

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
if primitive_file.exists():
    text = _read_primitive_source()
    block = _macro_blocks(text, 'token_bar')
    if not block:
        errors.append('token_bar macro not found')
    else:
        segment_kinds = ['fresh', 'read', 'write', 'out']
        found_segments: list[str] = []
        for kind in segment_kinds:
            if re.search(rf"['\"]{re.escape(kind)}['\"]", block):
                found_segments.append(kind)
            else:
                errors.append(f'token_bar missing segment class: {kind}')

        if len(found_segments) == len(segment_kinds):
            passes.append(f'Token bar segment classes: {", ".join(found_segments)}')

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
if primitive_file.exists():
    text = _read_primitive_source()
    block = _macro_blocks(text, 'payload_modal')
    if not block:
        errors.append('payload_modal macro not found')
    else:
        modal_attrs: list[str] = []
        attr_checks = {
            'data-modal': r'data-modal\b',
            'data-modal-kind': r'data-modal-kind',
            'data-modal-title': r'data-modal-title',
            'data-modal-meta': r'data-modal-meta',
            'data-modal-content': r'data-modal-content',
            'role=dialog': r'role="dialog"',
            'aria-modal': r'aria-modal="true"',
            'close-modal action': r'data-action="close-modal"',
        }
        for label, pat in attr_checks.items():
            if re.search(pat, block):
                modal_attrs.append(label)
            else:
                errors.append(f'payload_modal missing: {label}')

        if len(modal_attrs) == len(attr_checks):
            passes.append(f'Payload modal data attributes: {", ".join(modal_attrs)}')

# ---------------------------------------------------------------------------
# 6. 空 state 和 错误 state presence。
# ---------------------------------------------------------------------------
if primitive_file.exists():
    text = _read_primitive_source()
    state_checks_passed: list[str] = []

    block = _macro_blocks(text, 'empty_state')
    if not block:
        errors.append('empty_state macro not found')
    else:
        empty_attrs = {
            'role=status': r'role="status"',
            'aria-live=polite': r'aria-live="polite"',
            'state-strip class': r"['\"]state-strip['\"]",
            'state-title': r'class="state-title"',
            'state-icon': r'class="state-icon"',
        }
        for label, pat in empty_attrs.items():
            if re.search(pat, block):
                state_checks_passed.append(f'empty_state:{label}')
            else:
                errors.append(f'empty_state missing: {label}')

    # 错误 state。
    block = _macro_blocks(text, 'error_state')
    if not block:
        errors.append('error_state macro not found')
    else:
        error_attrs = {
            'role=alert': r'role="alert"',
            'aria-live=assertive': r'aria-live="assertive"',
            'state-strip class': r"['\"]state-strip['\"]",
            'state-title': r'class="state-title"',
            'state-icon': r'class="state-icon"',
        }
        for label, pat in error_attrs.items():
            if re.search(pat, block):
                state_checks_passed.append(f'error_state:{label}')
            else:
                errors.append(f'error_state missing: {label}')

    if not any(e.startswith('empty_state') or e.startswith('error_state') for e in errors):
        passes.append(f'Empty/Error states verified: {", ".join(state_checks_passed)}')

# ---------------------------------------------------------------------------
# 结果汇总。
# ---------------------------------------------------------------------------
if passes:
    print('DOM contract checks:')
    for p in passes:
        print(f'  PASS: {p}')

if errors:
    print('\nDOM contract check failed:')
    for e in errors:
        print(f'  FAIL: {e}')
    sys.exit(1)

print('\nAll DOM contract checks passed')
