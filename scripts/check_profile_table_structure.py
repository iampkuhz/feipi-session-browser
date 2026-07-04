#!/usr/bin/env python3
"""提供 检查 profile 表格 结构 脚本能力。"""

from __future__ import annotations

import re
import sys
from pathlib import Path

MAX_INLINE_PRE_CHARS = 200


# 查找session HTML。
def find_session_html() -> Path:
    """返回：
        路径到 first 现有 session.html candidate。
    """
    candidates = [
        Path(__file__).resolve().parent.parent
        / 'src'
        / 'session_browser'
        / 'web'
        / 'templates'
        / 'session.html',
        Path.cwd() / 'src' / 'session_browser' / 'web' / 'templates' / 'session.html',
    ]
    for p in candidates:
        if p.exists():
            return p
    raise FileNotFoundError('Cannot find session.html. Run from repo root or set PYTHONPATH.')


# 提取profile template。
def extract_profile_template(source: str) -> str | None:
    """参数：
        source: 输入来源标识。

    返回：
        提取出的 profile template 文本。
    """
    m = re.search(
        r'<template id="profile-template">(.*?)</template>',
        source,
        re.DOTALL,
    )
    return m.group(1) if m else None


# 提取profile 表格。
def extract_profile_table(template: str) -> str | None:
    """参数：
        template: 待检查的 template HTML。

    返回：
        extract profile 表格 字符串。
    """
    m = re.search(r'(<table.*?</table>)', template, re.DOTALL)
    return m.group(1) if m else None


# 检查没有 inline detail 行。
def check_no_inline_detail_rows(template: str) -> tuple[bool, str]:
    """参数：
        template: 待检查的 template HTML。

    返回：
        由pass 状态 和 diagnostic detail.组成的 tuple。
    """
    if re.search(r'class="[^"]*\bllm-call-detail\b[^"]*"', template):
        return (
            False,
            'Found <tr class="... llm-call-detail ..."> — Profile should not have inline '
            'detail expansion rows',
        )
    return True, 'No inline llm-call-detail expansion rows'


# 检查无 pre 块。
def check_no_pre_blocks(template: str) -> tuple[bool, str]:
    """参数：
        template: 待检查的 template HTML。

    返回：
        由pass 状态 和 diagnostic detail.组成的 tuple。
    """
    if 'llm-call-detail__pre-block' in template:
        return (
            False,
            'Found .llm-call-detail__pre-block — Profile should not contain large inline '
            '<pre> blocks',
        )
    return True, 'No .llm-call-detail__pre-block elements'


# 检查没有 request context 标签。
def check_no_request_context_label(template: str) -> tuple[bool, str]:
    """参数：
        template: 待检查的 template HTML。

    返回：
        由pass 状态 和 diagnostic detail.组成的 tuple。
    """
    if 'Request Context:' in template:
        return (
            False,
# 检查Profile 行 provide Inspect buttons wired到 inspector。
            'Found "Request Context:" label — Profile should not expose inline request '
            'context labels',
        )
    return True, 'No "Request Context:" inline label'


# 检查inspect buttons exist。
def check_inspect_buttons_exist(template: str) -> tuple[bool, str]:
    """参数：
        template: 待检查的 template HTML。

    返回：
        由pass 状态 和 diagnostic detail.组成的 tuple。
    """
    buttons = re.findall(
        r'<button[^>]*class="[^"]*inspect-btn[^"]*"[^>]*>',
        template,
    )
    if not buttons:
        return False, 'No inspect buttons found — each profile row should have an Inspect button'

    has_open = 'openLLMInspector' in template
# 检查Profile markup exposes a marker container用于行 indicators。
    if not has_open:
        return False, 'Inspect buttons exist but openLLMInspector function not found'

    return True, f'{len(buttons)} inspect button(s) found with openLLMInspector handler'


# 检查marker container。
def check_marker_container(template: str) -> tuple[bool, str]:
    """参数：
        template: 待检查的 template HTML。

    返回：
        由pass 状态 和 diagnostic detail.组成的 tuple。
    """
    if 'data-marker' in template or 'marker-container' in template or 'profile-marker' in template:
        return True, 'Marker container found'
    return False, 'No marker container found (data-marker / marker-container / profile-marker)'


# 检查preview truncation。
def check_preview_truncation(template: str) -> tuple[bool, str]:
    """参数：
        template: 待检查的 template HTML。

    返回：
        由pass 状态 和 diagnostic detail.组成的 tuple。
    """
    if (
        'class="text-xs mono truncate"' in template
        or 'class="truncate"' in template
        or 'truncate' in template
    ):
        return True, 'Preview column has truncation class'
    return False, 'Preview column missing truncation class'


# 检查没有大块 inline pre 内容。
def check_no_large_inline_pre(template: str) -> tuple[bool, str]:
    """参数：
        template: 待检查的 template HTML。

    返回：
        由pass 状态 和 diagnostic detail.组成的 tuple。
    """
    detail_section = re.search(
        r'llm-call-detail__grid.*?(?=</template>)',
        template,
        re.DOTALL,
    )
    if not detail_section:
        return True, 'No llm-call-detail__grid section found'

    section = detail_section.group()
    pre_blocks = re.findall(r'<pre[^>]*>(.*?)</pre>', section, re.DOTALL)
    for i, content in enumerate(pre_blocks):
        stripped = re.sub(r'\{\{.*?\}\}', '', content)
        stripped = re.sub(r'\{%.*?%\}', '', stripped)
        stripped_len = len(stripped.strip())
        if stripped_len > MAX_INLINE_PRE_CHARS:
            return (
                False,
                f'Large inline <pre> block #{i + 1} in detail grid '
                f'({stripped_len} chars of static content)',
            )

    return True, 'No large inline <pre> blocks in detail grid'


CHECKS = [
    ('No inline detail rows', check_no_inline_detail_rows),
    ('No pre-blocks', check_no_pre_blocks),
    ('No Request Context label', check_no_request_context_label),
    ('Inspect buttons exist', check_inspect_buttons_exist),
# 运行all Profile table structure checks against a template 路径。
    ('Marker container', check_marker_container),
    ('Preview truncation', check_preview_truncation),
    ('No large inline <pre>', check_no_large_inline_pre),
]


# 运行检查流程。
def run(template_path: Path) -> int:
    """参数：
        template_path: 待检查的路径。

    返回：
        exit code 0 当 all 检查 pass, 1用于contract 失败项, 或 2用于输入 错误。
    """
    source = template_path.read_text(encoding='utf-8')
    template = extract_profile_template(source)

    if template is None:
        print(
            '[ERROR] Cannot find <template id="profile-template"> in session.html', file=sys.stderr
        )
        return 2

    print(f'Checking profile table structure in: {template_path}')
    print(f'Template length: {len(template)} chars')
    print()

    failures = 0
    passes = 0

    for name, check_fn in CHECKS:
        ok, msg = check_fn(template)
        if ok:
            print(f'[OK]   {name}: {msg}')
            passes += 1
        else:
            print(f'[FAIL] {name}: {msg}')
            failures += 1

    print()
    print(f'Result: {passes} passed, {failures} failed out of {len(CHECKS)} checks')

    return 1 if failures > 0 else 0


# 解析命令行参数并运行脚本入口。
def main() -> int:
    """返回：
        进程退出码。
    """
    try:
        path = find_session_html()
    except FileNotFoundError as exc:
        print(f'[ERROR] {exc}', file=sys.stderr)
        return 2

    return run(path)


if __name__ == '__main__':
    sys.exit(main())
