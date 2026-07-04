#!/usr/bin/env python3
"""提供 检查 sessions list logic contract 脚本能力。"""

from __future__ import annotations

import argparse
import html.parser
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Node:
    """表示 Node。

    属性：
        tag: tag 参数。
        attrs: attrs 参数。
        text: 待检查的文本。
        children: children 参数。
    """

    tag: str
    attrs: dict[str, str]
    text: list[str] = field(default_factory=list)
    children: list[Node] = field(default_factory=list)


class Parser(html.parser.HTMLParser):
    """表示 Parser。
    """

    # 维护init。
    def __init__(self) -> None:
        super().__init__()
        self.root = Node('root', {})
        self.stack = [self.root]
        self.nodes: list[Node] = []

    # 记录 HTML 开始标签。
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """参数：
            tag: tag 参数。
            attrs: attrs 参数。
        """
        node = Node(tag, {k: (v or '') for k, v in attrs})
        self.stack[-1].children.append(node)
        self.stack.append(node)
        self.nodes.append(node)

    # 记录 HTML 结束标签。
    def handle_endtag(self, tag: str) -> None:
        """参数：
            tag: tag 参数。
        """
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break

    # 记录 HTML 文本数据。
    def handle_data(self, data: str) -> None:
        """参数：
            data: 从 HTML 解析出的原始 text chunk，稍后统一规范化空白。
        """
        if self.stack:
            self.stack[-1].text.append(data)


# 维护class。
def cls(node: Node) -> set[str]:
    """参数：
        node: node 参数。

    返回：
        解析后的 HookContext；失败时携带 parse_error。
    """
    return set(node.attrs.get('class', '').split())


# 维护文本。
def text_of(node: Node) -> str:
    """参数：
        node: node 参数。

    返回：
        文本 of 字符串。
    """
    parts = list(node.text)
    for child in node.children:
        parts.append(text_of(child))
    return ' '.join(' '.join(parts).split())


# 维护全部 描述。
def all_desc(node: Node) -> list[Node]:
    """参数：
        node: node 参数。

    返回：
        结果列表。
    """
    out = []
    for child in node.children:
        out.append(child)
        out.extend(all_desc(child))
    return out


# 查找class。
def find_by_class(nodes: list[Node], class_name: str) -> list[Node]:
    """参数：
        nodes: nodes 参数。
        class_name: class name 参数。

    返回：
        结果列表。
    """
    return [n for n in nodes if class_name in cls(n)]


# 维护fail。
def fail(message: str) -> None:
    """参数：
        message: 诊断消息。

    异常：
        SystemExit: 始终 raised带状态 1 之后 printing FAIL 行。
    """
    print(f'FAIL: {message}')
    raise SystemExit(1)


# 维护校验。
def require(condition: bool, message: str) -> None:
    """参数：
        condition: 结果 of 当前 static DOM assertion。
        message: 失败项 detail到print 当 condition 为 false。
    """
    if not condition:
        fail(message)


# 维护查询。
def query(url: str) -> dict[str, list[str]]:
    """参数：
        url: Absolute 或 relative URL从a sessions-列表 control。

    返回：
        映射 of query parameter names到ordered 值, preserving blanks。
    """
    return urllib.parse.parse_qs(urllib.parse.urlparse(url).query, keep_blank_values=True)


# 读取input。
def _read_input(html_path: str | None, url: str | None) -> str:
    """参数：
        html_path: 可选filesystem artifact 路径从a previous browser capture。
        url: 待请求的 URL。

    返回：
        read input 字符串。
    """
    if not html_path and not url:
        fail('provide --html or --url')
    if url:
        return urllib.request.urlopen(url, timeout=10).read().decode('utf-8', errors='replace')
    return Path(str(html_path)).read_text(encoding='utf-8')


# 检查forbidden classes。
def _check_forbidden_classes(nodes: list[Node], all_text: str) -> None:
    """参数：
        nodes: nodes 参数。
        all_text: 规范化 page text used用于copy-level assertions。
    """
    for forbidden_class in [
        'density-toggle',
        'round-map',
        'row--failed',
        'row--anomaly',
        'highlight-warn',
    ]:
        require(
            not find_by_class(nodes, forbidden_class),
            f'forbidden class present: .{forbidden_class}',
        )
    require('sorted by' not in all_text, "footer must not contain 'sorted by'")


# 检查search 契约。
def _check_search_contract(nodes: list[Node], all_text: str) -> None:
    """参数：
        nodes: nodes 参数。
        all_text: 规范化 page text used用于hint assertions。
    """
    search_inputs = [
        n
        for n in nodes
        if n.tag == 'input' and n.attrs.get('name') in {'q', 'session_id', 'session'}
    ]
    require(search_inputs, 'missing session id search input')
    search_input = search_inputs[0]
    hint_ok = ('仅支持 Session ID' in all_text) or (
        'Session ID' in search_input.attrs.get('placeholder', '')
    )
    require(hint_ok, 'search must clearly say it only supports Session ID')


# 检查sort 契约。
def _check_sort_contract(nodes: list[Node]) -> None:
    """参数：
        nodes: nodes 参数。
    """
    sortable_headers = find_by_class(nodes, 'sessions-th--sortable')
    expected_sort = ['Tokens', 'Rounds', 'Tools', 'Duration', 'Updated']
    require(
        len(sortable_headers) == len(expected_sort),
        f'expected {len(expected_sort)} sortable headers, got {len(sortable_headers)}',
    )
    got_sort = []
    for header in sortable_headers:
        label_text = text_of(header).replace('↕', '').replace('↑', '').replace('↓', '').strip()
        got_sort.append(label_text)
        descendants = all_desc(header)
        clickable = [node for node in descendants if node.tag in {'a', 'button'}]
        require(clickable, f'sortable header {label_text!r} has no clickable control')
        control_text = (
            ' '.join(text_of(control) for control in clickable)
            .replace('↕', '')
            .replace('↑', '')
            .replace('↓', '')
            .strip()
        )
        require(
            label_text in control_text or control_text in label_text,
            (
                f'sortable header {label_text!r} clickable text is not the label; '
                'icon-only sort control detected'
            ),
        )
        first_control = clickable[0]
        if first_control.tag == 'a':
            require(
                first_control.attrs.get('href'),
                f'sortable header {label_text!r} anchor has no href',
            )
        if first_control.tag == 'button':
            require(
                first_control.attrs.get('type') in {'submit', 'button'},
                f'sortable header {label_text!r} button type missing',
            )
    require(got_sort == expected_sort, f'sortable headers mismatch: {got_sort!r}')

    aria_sort = [node for node in sortable_headers if 'aria-sort' in node.attrs]
    require(len(aria_sort) == 1, f'expected exactly one aria-sort, got {len(aria_sort)}')


# 检查footer 契约。
def _check_footer_contract(nodes: list[Node], all_text: str) -> None:
    """参数：
        nodes: nodes 参数。
        all_text: 规范化 page text used用于range 和 total assertions。
    """
    footer = find_by_class(nodes, 'sessions-table-footer')
    require(footer, 'missing sessions table footer')
    footer_desc = all_desc(footer[0])
    footer_controls = [node for node in footer_desc if node.tag in {'a', 'button'}]
    labels = [text_of(node).strip() for node in footer_controls]
    require('Previous' in labels, 'footer missing Previous')
    require('Next' in labels, 'footer missing Next')
    require('Rows ' in all_text, 'footer missing Rows range')
    require('matching sessions' in all_text, 'footer missing matching sessions total')

    page_buttons = [
        node for node in nodes if node.tag == 'button' and node.attrs.get('name') == 'page'
    ]
    if not page_buttons:
        return
    hidden_names = {
        node.attrs.get('name')
        for node in nodes
        if node.tag == 'input' and node.attrs.get('type') == 'hidden'
    }
    for required in ['sort', 'dir']:
        require(
            required in hidden_names,
            f'pagination buttons require hidden input preserving {required}',
        )
    require(
        any(name in hidden_names for name in ['q', 'agent', 'model', 'project', 'date']),
        'pagination buttons require hidden inputs preserving filters',
    )


# 检查filter chip removal。
def _check_filter_chip_removal(nodes: list[Node]) -> None:
    """参数：
        nodes: nodes 参数。
    """
    chips = find_by_class(nodes, 'ui-filter-chip')
    for chip in chips:
        desc = all_desc(chip)
        remove_controls = [node for node in desc if node.tag in {'a', 'button'}]
        if remove_controls:
            control = remove_controls[0]
            if control.tag == 'a':
                require(control.attrs.get('href'), 'filter chip remove anchor missing href')
            else:
                require(control.attrs.get('name'), 'filter chip remove button missing name')


# 解析命令行参数并运行脚本入口。
def main() -> int:
    """返回：
        进程退出码。

    说明：
        1 on contract violations, 和 仅 读取 provided page 输入。
    """
    ap = argparse.ArgumentParser()
    ap.add_argument('--html')
    ap.add_argument('--url')
    args = ap.parse_args()

    parser = Parser()
    parser.feed(_read_input(args.html, args.url))
    nodes = parser.nodes
    all_text = ' '.join(text_of(node) for node in nodes)

    _check_forbidden_classes(nodes, all_text)
    _check_search_contract(nodes, all_text)
    _check_sort_contract(nodes)
    _check_footer_contract(nodes, all_text)
    _check_filter_chip_removal(nodes)

    print('PASS: sessions list logic contract')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
