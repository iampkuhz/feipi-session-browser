#!/usr/bin/env python3
"""提供 检查 inspector viewer 结构 脚本能力。"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# locate 文件。

BASE_DIR = Path(__file__).resolve().parent.parent / 'src' / 'session_browser' / 'web'


# 查找文件。
def find_file(rel: str) -> Path:
    """参数：
        rel: rel 参数。

    返回：
        解析后的 HookContext；失败时携带 parse_error。

    异常：
        FileNotFoundError: Raised 当 QA gate 输入 is 缺失。
    """
    p = BASE_DIR / rel
    if not p.exists():
        raise FileNotFoundError(f'Cannot find {rel} at {p}')
    return p


# 读取文件内容。
def read(rel: str) -> str:
    """参数：
        rel: rel 参数。

    返回：
        read 字符串。
    """
    return find_file(rel).read_text(encoding='utf-8')


_REQUIRED_TABS = [
    'Overview',
    'Rendered Context',
    'Request Payload',
    'Rendered Response',
    'Response Payload',
    'Tools',
    'Raw',
]

_INSPECTOR_FILES = [
    'templates/components/inspector.html',
    'templates/components/viewer.html',
    'templates/session.html',
    'static/js/inspector.js',
]


# 读取全部。
def _read_all() -> dict[str, str]:
    """返回：
        映射 of configured relative 路径到source text 供 检查。
    """
    result = {}
    for rel in _INSPECTOR_FILES:
        try:
            result[rel] = read(rel)
        except FileNotFoundError as exc:
            print(f'[ERROR] {exc}', file=sys.stderr)
            sys.exit(2)
    return result


# 维护合并 源码。
def _combined_source(sources: dict[str, str]) -> str:
    """参数：
        sources: 映射 returned by _读取_all用于当前 QA 运行。

    返回：
        combined source 字符串。
    """
    return '\n'.join(sources.values())


# 检查必需 tabs。
def check_required_tabs(sources: dict[str, str]) -> tuple[bool, str]:
    """参数：
        sources: Template 和 JavaScript source text用于当前 QA 运行。

    返回：
        Pass/fail 状态带缺失 tab labels 或 success detail。
    """
    combined = _combined_source(sources)
    missing = []
    for tab in _REQUIRED_TABS:
        if tab not in combined:
            missing.append(tab)
    if missing:
        return False, f'Missing tab labels: {", ".join(missing)}'
    return True, f'All {_REQUIRED_TABS.__len__()} required tabs found'


# 检查tab aria active。
def check_tab_aria_and_active(sources: dict[str, str]) -> tuple[bool, str]:
    """参数：
        sources: Template 和 JavaScript source text用于当前 QA 运行。

    返回：
        Pass/fail 状态带structural issues 或 success detail。
    """
    combined = _combined_source(sources)

    # 检查用于 tab button pattern: <button ... class="tab ...">带role="tab" 或 data-tab。
    has_tab_buttons = bool(
        re.search(
            r'<button[^>]*class="[^"]*\btab\b[^"]*"[^>]*>',
            combined,
        )
    )
    # 检查用于 ARIA role on buttons。
    has_aria_tab = 'role="tab"' in combined or "role='tab'" in combined
    # 检查用于 tabpanel。
    has_tabpanel = (
        'role="tabpanel"' in combined
        or "role='tabpanel'" in combined
        or 'class="tab-content"' in combined
        or 'class="tabpanel"' in combined
    )
    # 检查用于 active state class。
    has_active = bool(re.search(r'class="[^"]*\bactive\b[^"]*"', combined))

    issues = []
    if not has_tab_buttons:
        issues.append('no tab button elements')
    if not has_aria_tab:
        issues.append("no role='tab' ARIA attribute")
    if not has_tabpanel:
        issues.append("no tabpanel element (role='tabpanel' or class='tab-content')")
    if not has_active:
        issues.append("no 'active' state class")

    if issues:
        return False, f'Tab structure issues: {"; ".join(issues)}'
    return True, 'Tab buttons and tabpanels have active state and ARIA attributes'


# 检查 request payload 的不可用状态。
def check_request_payload_unavailable(sources: dict[str, str]) -> tuple[bool, str]:
    """参数：
        sources: Template 和 JavaScript source text用于当前 QA 运行。

    返回：
        结果 tuple。
    """
    combined = _combined_source(sources)
    # Look用于an explicit "unavailable" 空-state marker用于request payload。
    patterns = [
        r'Request Payload.*unavailable',
        r'unavailable.*Request Payload',
        r'Request Payload.*not available',
        r'No request payload',
        r'request.*payload.*unavailable',
    ]
    for pat in patterns:
        if re.search(pat, combined, re.IGNORECASE):
            return True, "'Request Payload unavailable' empty-state text found"

    if 'unavailable' in combined.lower() and (
        'payload' in combined.lower() or 'request' in combined.lower()
    ):
        return (
            True,
            "Generic unavailable text exists (but not specific 'Request Payload unavailable')",
        )

    return False, "No 'Request Payload unavailable' empty-state text found"


# 检查raw content escaping。
def check_raw_content_escaping(sources: dict[str, str]) -> tuple[bool, str]:
    """参数：
        sources: Template 和 JavaScript source text用于当前 QA 运行。

    返回：
        Pass/fail 状态带缺失 escaping patterns 或 success detail。
    """
    combined = _combined_source(sources)

    # 检查用于 HTML escaping patterns: .replace(/&/g, '&amp;'), .replace(/</g, '&lt;')。
    has_amp_escape = bool(re.search(r"replace\s*\(\s*/&/g\s*,\s*['\"]&amp;['\"]", combined))
    has_lt_escape = bool(re.search(r"replace\s*\(/</g\s*,\s*['\"]&lt;['\"]", combined))
    has_gt_escape = bool(re.search(r"/>/g\s*,\s*['\"]&gt;['\"]", combined))

    issues = []
    if not has_amp_escape:
        issues.append('missing & -> &amp; escaping in JS')
    if not has_lt_escape:
        issues.append('missing < -> &lt; escaping in JS')
    if not has_gt_escape:
        issues.append('missing > -> &gt; escaping in JS')

    if issues:
        return False, f'Raw content escaping issues: {"; ".join(issues)}'
    return True, 'Raw JSON/<pre> content is safely HTML-escaped'


# 检查viewerhtml fallback。
def check_viewerhtml_fallback(sources: dict[str, str]) -> tuple[bool, str]:
    """参数：
        sources: Template 和 JavaScript source text用于当前 QA 运行。

    返回：
        结果 tuple。
    """
    js_source = sources.get('static/js/inspector.js', '')

    has_guarded_viewerhtml = bool(
        re.search(
            r'if\s*\(\s*payload\.viewerHtml\s*\)',
            js_source,
        )
    )

    if not has_guarded_viewerhtml:
        return False, 'viewerHtml injection is not guarded by a conditional check'

    # 检查the inspector has 默认/空 state用于当 viewerHtml is absent。
    inspector_html = sources.get('templates/components/inspector.html', '')
    has_fallback = bool(
        re.search(
            r'(No .*? available|Not available|—|viewer__fallback|inspector-viewer-slot)',
            inspector_html,
        )
    )

    if not has_fallback:
        return False, 'No fallback content for absent viewerHtml in inspector template'

    return True, 'viewerHtml fallback is guarded and has default content'


# 检查inspector tab shell。
def check_inspector_tab_shell(sources: dict[str, str]) -> tuple[bool, str]:
    """参数：
        sources: Template 和 JavaScript source text用于当前 QA 运行。

    返回：
        结果 tuple。
    """
    inspector = sources.get('templates/components/inspector.html', '')

    has_inspector_tabs = bool(
        re.search(
            r'(inspector-tab|data-inspector-tab|class="inspector.*tab)',
            inspector,
            re.IGNORECASE,
        )
    )

    js_source = sources.get('static/js/inspector.js', '')
    has_js_tabs = bool(
        re.search(
            r'(inspector-tab|tab.*panel|tabpanel|role.*tab)',
            js_source,
            re.IGNORECASE,
        )
    )

    if not has_inspector_tabs and not has_js_tabs:
        return (
            False,
            'Inspector lacks a dedicated tab shell (no inspector-level tabs in HTML or JS)',
# 检查rendered 和 原始 Inspector content use separate containers。
        )
    return True, 'Inspector has a dedicated tab shell'


# 检查rendered raw separation。
def check_rendered_raw_separation(sources: dict[str, str]) -> tuple[bool, str]:
    """参数：
        sources: Template 和 JavaScript source text用于当前 QA 运行。

    返回：
        Pass/fail 状态带separation evidence 或 失败项 detail。
    """
    combined = _combined_source(sources)

    # 检查there are distinct classes/containers用于rendered vs 原始。
    has_rendered_container = bool(
        re.search(
            r'(rendered|markdown|viewer__markdown|viewer__part-markdown)',
            combined,
        )
    )
    has_raw_container = bool(
        re.search(
            r'(viewer__raw|raw-pre|raw-json|__raw)',
            combined,
        )
    )

    if not has_rendered_container or not has_raw_container:
        return False, 'Rendered and raw containers are not clearly separated'

    return True, 'Rendered and raw content have separate containers'


CHECKS = [
    ('7 required tabs', check_required_tabs),
    ('Tab ARIA and active state', check_tab_aria_and_active),
    ('Request Payload unavailable', check_request_payload_unavailable),
    ('Raw content escaping', check_raw_content_escaping),
    ('viewerHtml fallback', check_viewerhtml_fallback),
    ('Inspector tab shell', check_inspector_tab_shell),
# 运行all Inspector/Viewer structure checks 和 print their 结果。
    ('Rendered/raw separation', check_rendered_raw_separation),
]


# 运行检查流程。
def run(sources: dict[str, str]) -> int:
    """参数：
        sources: sources 参数。

    返回：
        进程退出码。
    """
    # 打印文件 info。
    for rel, content in sources.items():
        print(f'  {rel}: {len(content)} chars')
    print()

    failures = 0
    passes = 0

    for name, check_fn in CHECKS:
        ok, msg = check_fn(sources)
        if ok:
            print(f'[OK]   {name}: {msg}')
            passes += 1
        else:
            print(f'[FAIL] {name}: {msg}')
            failures += 1

    print()
    print(f'Result: {passes} passed, {failures} failed out of {len(CHECKS)} checks')
# templates 和 JavaScript, prints 缺失-输入 错误 as exit 2, 和 returns。
# 异常 SystemExit：Re-raised 当 _read_all reports 缺失 必需 inputs。

    return 1 if failures > 0 else 0


# 解析命令行参数并运行脚本入口。
def main() -> int:
    """返回：
        进程退出码。

    异常：
        SystemExit: Re-raised 当 _读取_all reports 缺失 必需 inputs。

    说明：
        templates 和 JavaScript, 打印 缺失-输入 错误 as exit 2, 和 返回。
    """
    try:
        sources = _read_all()
    except SystemExit:
        raise
    except Exception as exc:
        print(f'[ERROR] {exc}', file=sys.stderr)
        return 2

    print('Checking Inspector/Viewer structure...')
    print()
    return run(sources)


if __name__ == '__main__':
    sys.exit(main())
