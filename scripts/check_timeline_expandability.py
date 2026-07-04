#!/usr/bin/env python3
"""提供 检查 timeline expandability 脚本能力。"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# 辅助函数。
# ---------------------------------------------------------------------------

_TOOL_DIR = Path(__file__).resolve().parent.parent
TEMPLATES = _TOOL_DIR / 'src' / 'session_browser' / 'web' / 'templates'
STATIC_JS = _TOOL_DIR / 'src' / 'session_browser' / 'web' / 'static' / 'js'
STATIC_CSS = _TOOL_DIR / 'src' / 'session_browser' / 'web' / 'static' / 'style.css'

_OK = 0
_FAIL_COUNT = 0
_WARN_COUNT = 0


# 维护报告。
def _report(tag: str, msg: str, detail: str = '') -> None:
    """参数：
        tag: tag 参数。
        msg: msg 参数。
        detail: 可选indented detail用于warning 和 失败项。
    """
    global _FAIL_COUNT, _WARN_COUNT  # noqa: PLW0603 - CLI counters aggregate findings.
    prefix = f'[{tag}]'
    if tag == 'OK':
        print(f'  {prefix} {msg}')
    elif tag == 'WARN':
        _WARN_COUNT += 1
        print(f'  {prefix} {msg}')
        if detail:
            print(f'        {detail}')
    elif tag == 'FAIL':
        _FAIL_COUNT += 1
        print(f'  {prefix} {msg}')
        if detail:
            print(f'        {detail}')
    elif tag == 'INFO':
        print(f'  {prefix} {msg}')


# 读取文件内容。
def _read(path: Path) -> str:
    """参数：
        path: Template, JavaScript, 或 CSS 路径到读取。

    返回：
        文件 contents；exits带状态 2 当 必需 输入 is 缺失。
    """
    if not path.exists():
        print(f'[ERROR] File not found: {path}', file=sys.stderr)
        sys.exit(2)
    return path.read_text(encoding='utf-8')


# 检查toggle has children。
def check_toggle_for_has_children(timeline_html: str) -> None:
    """参数：
        timeline_html: timeline.html template 源码。
    """
    # {% 如果 node.children 或 node.expanded is defined %}。

    has_toggle_cond = re.search(
        r'if\s+node\.children\s+and\s+node\.children\s*\|\s*length\s*>\s*0',
        timeline_html,
    )
    if not has_toggle_cond:
        has_toggle_cond = re.search(
            r'if\s+node\.children\s+or\s+node\.expanded\s+is\s+defined',
            timeline_html,
        )
    has_children_cond = re.search(
        r"'has-children'\s+if\s+node\.children",
        timeline_html,
    )

    if has_toggle_cond and has_children_cond:
        _report('OK', 'has-children nodes always render a toggle button')
    else:
        if not has_toggle_cond:
            _report(
                'FAIL',
                'toggle condition not found',
                "Expected: 'if node.children or node.expanded is defined'",
            )
        if not has_children_cond:
            _report(
                'FAIL',
                'has-children class condition not found',
                'Expected: "\'has-children\' if node.children"',
            )

    both_classes = re.search(
        r"\{\{.*'has-children'.*\}\}.*\{\{.*'is-leaf'.*\}\}",
        timeline_html.replace('\n', ' '),
        re.DOTALL,
    )
    if both_classes:
        has_proper_has_children = re.search(
            r"'has-children'\s+if\s+node\.children\s+and",
            timeline_html,
        )
        has_proper_is_leaf = re.search(
            r"'is-leaf'\s+if\s+not\s+node\.children",
            timeline_html,
        )
        if has_proper_has_children and has_proper_is_leaf:
            _report('OK', 'has-children / is-leaf classes are mutually exclusive')
        else:
            _report(
                'WARN',
                'timeline-node always has both has-children and is-leaf',
                'Template renders both classes unconditionally; CSS relies on '
                'is-expanded + children visibility, not on these classes alone. '
                'Not a functional bug, but semantically confusing.',
            )


# 检查timeline id。
def check_timeline_id(timeline_html: str, session_html: str) -> None:
    """参数：
        timeline_html: timeline.html template 源码。
        session_html: session.html template 源码。
    """
    has_timeline_id = 'data-timeline-id' in timeline_html

    if has_timeline_id:
        _report('OK', 'data-timeline-id present in timeline template')
    else:
        _report(
            'FAIL',
            'data-timeline-id missing from timeline-node elements',
            'timeline.html does not render data-timeline-id on nodes. '
            'This means jump-to-node, programmatic expand/collapse, and '
            'accessibility tree cannot reliably identify individual nodes.',
        )

    # 检查是否JS jump function expects data-timeline-id。
    timeline_js_path = STATIC_JS / 'timeline.js'
    if timeline_js_path.exists():
        js_text = _read(timeline_js_path)
        jump_uses_timeline_id = 'data-timeline-id' in js_text
        if jump_uses_timeline_id and not has_timeline_id:
            _report(
                'WARN',
                'jump() queries [data-timeline-id] but template never sets it',
                'selector: [data-timeline-id="..."] in timeline.js jump()',
            )


# 维护analyse expand collapse。
def _analyse_expand_collapse(js_text: str) -> dict[str, Any]:
    """参数：
        js_text: JavaScript 源码文本。

    返回：
        结果映射。
    """
    result: dict[str, Any] = {
        'expandAll_exists': False,
        'expandAll_selectors': [],
        'collapseAll_exists': False,
        'collapseAll_selectors': [],
        'covers_timeline_node': False,
    }

    # 检查expandAll。
    if 'function expandAll' in js_text or 'expandAll:' in js_text:
        result['expandAll_exists'] = True
        expand_fn = re.search(
            r'function expandAll\s*\(\s*\)\s*\{(.*?)}\s*function',
            js_text,
            re.DOTALL,
        )
        if expand_fn:
            result['expandAll_selectors'] = re.findall(
                r"querySelectorAll\s*\(\s*['\"]([^'\"]+)['\"]",
                expand_fn.group(1),
            )

    # 检查collapseAll。
    if 'function collapseAll' in js_text or 'collapseAll:' in js_text:
        result['collapseAll_exists'] = True
        collapse_fn = re.search(
            r'function collapseAll\s*\(\s*\)\s*\{(.*?)}\s*(?:function|window)',
            js_text,
            re.DOTALL,
        )
        if collapse_fn:
            result['collapseAll_selectors'] = re.findall(
                r"querySelectorAll\s*\(\s*['\"]([^'\"]+)['\"]",
                collapse_fn.group(1),
            )

    # 检查如果 either function targets .timeline-node。
    all_sels = result['expandAll_selectors'] + result['collapseAll_selectors']
    for sel in all_sels:
        if '.timeline-node' in sel:
            result['covers_timeline_node'] = True
            break

    return result


# 检查expand collapse coverage。
def check_expand_collapse_coverage(js_text: str) -> None:
    """参数：
        js_text: JavaScript 源码文本。
    """
    info = _analyse_expand_collapse(js_text)

    if not info['expandAll_exists']:
        _report('FAIL', 'expandAll() function not found in timeline.js')
    else:
        _report('OK', 'expandAll() function exists')
        for sel in info['expandAll_selectors']:
            _report('INFO', f'expandAll selector: {sel}')

    if not info['collapseAll_exists']:
        _report('FAIL', 'collapseAll() function not found in timeline.js')
    else:
        _report('OK', 'collapseAll() function exists')
        for sel in info['collapseAll_selectors']:
            _report('INFO', f'collapseAll selector: {sel}')

    if info['covers_timeline_node']:
        _report('OK', 'expandAll/collapseAll cover .timeline-node')
    else:
        _report(
            'FAIL',
            'expandAll/collapseAll do NOT target .timeline-node',
            f'Selectors found: {info["expandAll_selectors"] + info["collapseAll_selectors"]}',
        )

    if "classList.add('is-expanded')" in js_text or 'classList.add("is-expanded")' in js_text:
        _report('OK', 'expandAll adds is-expanded class')
    else:
        _report('WARN', 'expandAll may not add is-expanded class via classList')

    if "classList.remove('is-expanded')" in js_text or 'classList.remove("is-expanded")' in js_text:
        _report('OK', 'collapseAll removes is-expanded class')
    else:
        _report('WARN', 'collapseAll may not remove is-expanded class via classList')


# 检查toggle aria sync。
def check_toggle_aria_sync(timeline_html: str) -> None:
    """参数：
        timeline_html: timeline.html template 源码。
    """
    # 检查用于 inline onclick toggle pattern (legacy)。
    onclick_pattern = re.search(
        r"onclick=\"[^\"]*classList\.toggle\(['\"]is-expanded['\"]\)[^\"]*\"",
        timeline_html,
    )
    aria_pattern = re.search(
        r"onclick=\"[^\"]*setAttribute\(['\"]aria-expanded['\"]\s*,[^\"]*\)[^\"]*\"",
        timeline_html,
    )

    timeline_js_path = STATIC_JS / 'timeline.js'
    has_event_delegation = False
    has_toggle_node_fn = False
    has_aria_sync_in_js = False

    if timeline_js_path.exists():
        js_text = _read(timeline_js_path)
        has_toggle_node_fn = 'function toggleNode' in js_text or 'toggleNode:' in js_text
        has_event_delegation = (
            'data-timeline-toggle' in js_text
            or "closest('.timeline-node__toggle')" in js_text
            or 'closest(".timeline-node__toggle")' in js_text
        )
        has_aria_sync_in_js = (
            "setAttribute('aria-expanded'" in js_text or 'setAttribute("aria-expanded"' in js_text
        )

    if has_event_delegation and has_toggle_node_fn:
        _report(
            'OK',
            'event delegation toggleNode() handles toggle in timeline.js',
            'Inline onclick replaced by event delegation; is-expanded and '
            'aria-expanded are synced in JS toggleNode()',
        )
        if has_aria_sync_in_js:
            _report('OK', 'toggleNode() syncs aria-expanded with is-expanded')
        else:
            _report('WARN', 'toggleNode() may not sync aria-expanded')
    else:
        if onclick_pattern:
            _report('OK', 'toggle onclick toggles is-expanded class')
        else:
            _report(
                'FAIL',
                'toggle onclick does not toggle is-expanded',
                "Expected classList.toggle('is-expanded') in onclick",
            )

        if aria_pattern:
            _report('OK', 'toggle onclick updates aria-expanded attribute')
        else:
            _report(
                'FAIL',
                'toggle onclick does not update aria-expanded',
                "Expected setAttribute('aria-expanded', ...) in onclick",
            )

    aria_initial = re.search(
        r'aria-expanded=\"\{\{.*?if\s+node\.expanded.*?\}\}\"',
        timeline_html,
    )
    if aria_initial:
        _report('OK', 'aria-expanded initial value bound to node.expanded')
    else:
        _report('WARN', 'aria-expanded initial value may not match node.expanded')

    uses_grandparent = 'parentElement.parentElement' in timeline_html
    if uses_grandparent:
        _report(
            'WARN',
            'toggle uses parentElement.parentElement (fragile DOM traversal)',
            'If an intermediate wrapper is added, the toggle will target '
            'the wrong element. Consider using event delegation or '
            "closest('.timeline-node') instead.",
        )


# 检查filter preserves state。
def check_filter_preserves_state(js_text: str) -> None:
    """参数：
        js_text: JavaScript 源码文本。
    """
    has_show_all = '_showAllNodes' in js_text or 'showAllNodes' in js_text

    if has_show_all:
        _report('OK', '_showAllNodes() function exists for filter reset')
    else:
        _report(
            'WARN', 'no _showAllNodes/reset function found', 'Filter may permanently hide nodes'
        )

    show_all_fn = re.search(
        r'function _showAllNodes\s*\(\s*\)\s*\{(.*?)\}',
        js_text,
        re.DOTALL,
    )
    if show_all_fn:
        fn_body = show_all_fn.group(1)
        restores_display = 'style.display' in fn_body
        modifies_expand = 'is-expanded' in fn_body
        if restores_display and not modifies_expand:
            _report(
                'OK',
                "filter('all') restores display without touching is-expanded",
                'Expand state is preserved across filter changes',
            )
        elif modifies_expand:
            _report(
                'WARN',
                '_showAllNodes modifies is-expanded state',
                'This could unexpectedly expand/collapse nodes on filter reset',
            )
    else:
        _report('INFO', 'could not isolate _showAllNodes function body for deep check')

    # 检查non-'all' filters 仅 set display, 不 is-expanded。
    filter_fn = re.search(
        r'function filter\s*\([^)]*\)\s*\{(.*?)}\s*(?:function|window)',
        js_text,
        re.DOTALL,
    )
    if filter_fn:
        fn_body = filter_fn.group(1)
        sets_display_none = '.style.display' in fn_body
        removes_is_expanded = 'remove' in fn_body and 'is-expanded' in fn_body
        if sets_display_none and not removes_is_expanded:
            _report(
                'OK',
                'filter sets display:none without removing is-expanded',
                'Collapsed/expanded state survives filter',
            )
        elif removes_is_expanded:
            _report(
                'FAIL',
                'filter removes is-expanded class',
                'This permanently destroys expand state for filtered nodes',
            )


# 检查tab switch expand。
def check_tab_switch_expand(session_html: str, css_text: str) -> None:
    """参数：
        session_html: session.html template 源码。
        css_text: 待检查的 CSS 文本。
    """
    tab_content_hidden = re.search(
        r'\.tab-content\s*\{[^}]*display\s*:\s*none',
        css_text,
    )
    tab_content_active = re.search(
        r'\.tab-content\.active\s*\{[^}]*display\s*:\s*block',
        css_text,
    )

    if tab_content_hidden and tab_content_active:
        _report(
            'OK',
            'tab switching uses CSS display (DOM preserved)',
            'Timeline nodes remain in DOM when tab is hidden; expand works after switch',
        )
    else:
        _report(
            'WARN',
            'tab display mechanism unclear',
            'If tabs remove content from DOM, expand state is lost on switch',
        )

    timeline_in_tab = re.search(
        r'<div[^>]*id="timeline"[^>]*class="[^"]*tab-content',
        session_html,
    ) or re.search(
        r'<div[^>]*class="[^"]*tab-content[^"]*"[^>]*id="timeline"',
        session_html,
    )
    if timeline_in_tab:
        _report('OK', 'timeline is inside a .tab-content container')
    else:
        _report('WARN', 'timeline may not be inside .tab-content', 'verify session.html structure')

    toolbar_in_timeline = (
        'id="timeline"' in session_html and 'data-action="expand-all"' in session_html
    )
    if toolbar_in_timeline:
        _report('OK', 'expand/collapse toolbar is inside timeline tab')


# 检查round expand 结构。
def check_round_expand_structure(session_html: str, js_text: str) -> None:
    """参数：
        session_html: session.html template 源码。
        js_text: JavaScript 源码文本。
    """
    has_round_header = 'round-header-row' in session_html
    has_round_detail = 'round-detail-row' in session_html
    has_toggle_round = 'toggleRoundDetail' in js_text

    if has_round_header and has_round_detail:
        _report('OK', 'round header + detail row structure present')
    else:
        _report(
            'FAIL',
            'round header/detail structure incomplete',
            f'has_round_header={has_round_header}, has_round_detail={has_round_detail}',
        )

    if has_toggle_round:
        _report('OK', 'toggleRoundDetail() function exists')
    else:
        _report('FAIL', 'toggleRoundDetail() function missing')

    # 检查round onclick binding。
    has_round_onclick = 'onclick="toggleRoundDetail(this)"' in session_html
    if has_round_onclick:
        _report('OK', 'round-header-row has onclick toggle binding')
    else:
        _report('WARN', 'round-header-row onclick binding may differ from expected')


# 检查children visibility CSS。
def check_children_visibility_css(css_text: str) -> None:
    """参数：
        css_text: 待检查的 CSS 文本。
    """
    # Children hidden by 默认。
    children_hidden = re.search(
        r'\.timeline-node__children\s*\{[^}]*display\s*:\s*none',
        css_text,
    )
    children_shown = re.search(
        r'\.timeline-node\.is-expanded[^}]*\.timeline-node__children',
        css_text,
    )

    if children_hidden:
        _report('OK', 'CSS: .timeline-node__children hidden by default (display:none)')
    else:
        _report('FAIL', 'CSS: .timeline-node__children not hidden by default')

    if children_shown:
        _report('OK', 'CSS: .timeline-node.is-expanded shows children')
    else:
        _report(
            'FAIL',
            'CSS: no rule to show children when .is-expanded',
            'Expand will not reveal children visually',
        )


# 检查chevron rotation CSS。
def check_chevron_rotation_css(css_text: str) -> None:
    """参数：
        css_text: 待检查的 CSS 文本。
    """
    chevron_rotate = re.search(
        r'\.timeline-node\.is-expanded\s+\.timeline-node__chevron',
        css_text,
    )
    if chevron_rotate:
        _report('OK', 'CSS: chevron rotates when parent is-expanded')
    else:
        _report('WARN', 'CSS: chevron rotation rule for .is-expanded not found')


# 运行检查流程。
def run() -> int:
    """返回：
        进程退出码。
    """
    print('=' * 60)
    print('Check: Timeline Expandability')
    print('=' * 60)

    # 加载文件。
    timeline_html = _read(TEMPLATES / 'components' / 'timeline.html')
    session_html = _read(TEMPLATES / 'session.html')
    timeline_js = _read(STATIC_JS / 'timeline.js')
    css_text = _read(STATIC_CSS)

    print('\n[1] Round expand structure:')
    check_round_expand_structure(session_html, timeline_js)

    print('\n[2] .timeline-node.has-children toggle:')
    check_toggle_for_has_children(timeline_html)

    # 检查2: data-timeline-id。
    print('\n[3] data-timeline-id on nodes:')
    check_timeline_id(timeline_html, session_html)

    # 检查3: expandAll/collapseAll 覆盖率。
    print('\n[4] expandAll/collapseAll coverage:')
    check_expand_collapse_coverage(timeline_js)

    print('\n[5] Toggle aria-expanded sync:')
    check_toggle_aria_sync(timeline_html)

    print('\n[6] Filter preserve expand state:')
    check_filter_preserves_state(timeline_js)

    # 检查6: tab switching。
    print('\n[7] Tab switching expand:')
    check_tab_switch_expand(session_html, css_text)

    print('\n[8] CSS children visibility:')
    check_children_visibility_css(css_text)

    print('\n[9] CSS chevron rotation:')
    check_chevron_rotation_css(css_text)

    # 结果汇总。
    print('\n' + '=' * 60)
    if _FAIL_COUNT == 0 and _WARN_COUNT == 0:
        print('Result: ALL OK')
    elif _FAIL_COUNT == 0:
        print(f'Result: {_WARN_COUNT} warning(s), 0 failure(s)')
    else:
        print(f'Result: {_FAIL_COUNT} failure(s), {_WARN_COUNT} warning(s)')
    print('=' * 60)

    return 1 if _FAIL_COUNT > 0 else 0


if __name__ == '__main__':
    sys.exit(run())
