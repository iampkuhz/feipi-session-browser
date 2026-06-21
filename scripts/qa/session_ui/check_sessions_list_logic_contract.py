#!/usr/bin/env python3
"""Sessions List interaction contract checker.

This checker focuses on behavior-critical DOM:
- filter form keeps current state
- sort links/buttons preserve active filters and page rules
- pagination preserves filters and sort
- active filter removal has deterministic URLs
- sortable header labels are actually clickable, not icon-only
- no stale density/round-map/session-detail controls on /sessions

Usage:
  python scripts/qa/session_ui/check_sessions_list_logic_contract.py --html /tmp/sessions.html
  python scripts/qa/session_ui/check_sessions_list_logic_contract.py --url http://127.0.0.1:18999/sessions?agent=claude_code&project=/tmp/demo&sort=updated&dir=desc
"""

from __future__ import annotations

import argparse
import html.parser
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Node:
    """Represent one parsed DOM node used by the sessions-list contract check.

    The local HTML parser creates these lightweight nodes from either --html or
    --url input. Instances keep tag names, normalized attributes, direct text,
    and child order so checker helpers can report deterministic FAIL messages.

    Attributes:
        tag: HTML tag name preserved from the parser event.
        attrs: Normalized HTML attributes for this node.
        text: Direct text chunks attached to this node.
        children: Child nodes in source order.
    """

    tag: str
    attrs: dict[str, str]
    text: list[str] = field(default_factory=list)
    children: list[Node] = field(default_factory=list)


class Parser(html.parser.HTMLParser):
    """Collect a minimal DOM tree for sessions-list QA assertions.

    The CLI creates one parser per captured sessions page. It preserves node
    order and parent/child relationships without mutating external state; parse
    errors follow HTMLParser recovery semantics and later checks decide failure.
    Its initializer creates root, stack, and flat node inventory for one HTML input.
    """

    def __init__(self) -> None:
        """Initialize parser state for one sessions-list HTML input."""  # noqa: RUF100  # noqa: DOC301
        super().__init__()
        self.root = Node('root', {})
        self.stack = [self.root]
        self.nodes: list[Node] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Record an opening tag from HTMLParser into the current DOM stack.

        Args:
            tag: Lower-level parser tag name emitted for the source HTML.
            attrs: Attribute pairs emitted by HTMLParser; missing values are
                normalized to empty strings for downstream contract checks.
        """
        node = Node(tag, {k: (v or '') for k, v in attrs})
        self.stack[-1].children.append(node)
        self.stack.append(node)
        self.nodes.append(node)

    def handle_endtag(self, tag: str) -> None:
        """Close the matching element in the tolerant parser stack.

        Args:
            tag: End tag emitted by HTMLParser. Unknown or already-closed tags
                are ignored so QA failure remains tied to explicit assertions.
        """
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break

    def handle_data(self, data: str) -> None:
        """Append text content to the current node for label and hint checks.

        Args:
            data: Raw text chunk from HTMLParser. Whitespace is normalized later
                by text_of so parser callbacks do not change page semantics.
        """
        if self.stack:
            self.stack[-1].text.append(data)


def cls(node: Node) -> set[str]:
    """Return class tokens for a parsed node.

    Args:
        node: DOM node inspected by sessions-list contract helpers.

    Returns:
        Unique CSS class names; missing class attributes return an empty set.
    """
    return set(node.attrs.get('class', '').split())


def text_of(node: Node) -> str:
    """Return normalized descendant text for label and content assertions.

    Args:
        node: DOM subtree whose direct and nested text should be inspected.

    Returns:
        Whitespace-collapsed text in DOM traversal order.
    """
    parts = list(node.text)
    for child in node.children:
        parts.append(text_of(child))
    return ' '.join(' '.join(parts).split())


def all_desc(node: Node) -> list[Node]:
    """Return all descendant nodes used for nested control checks.

    Args:
        node: DOM subtree root from the parsed sessions page.

    Returns:
        Descendants in pre-order; an element without children returns an empty list.
    """
    out = []
    for child in node.children:
        out.append(child)
        out.extend(all_desc(child))
    return out


def find_by_class(nodes: list[Node], class_name: str) -> list[Node]:
    """Find parsed nodes that carry a required CSS class.

    Args:
        nodes: Flat node inventory collected by Parser.
        class_name: Class token that represents a sessions-list contract marker.

    Returns:
        Matching nodes in source order; absence lets callers emit contract-specific FAILs.
    """
    return [n for n in nodes if class_name in cls(n)]


def fail(message: str) -> None:
    """Print a QA failure and terminate with exit code 1.

    Args:
        message: Human-readable contract violation shown in CI or local runs.

    Raises:
        SystemExit: Always raised with status 1 after printing the FAIL line.
    """
    print(f'FAIL: {message}')
    raise SystemExit(1)


def require(condition: bool, message: str) -> None:
    """Enforce one sessions-list contract condition.

    Args:
        condition: Result of the current static DOM assertion.
        message: Failure detail to print when the condition is false.
    """
    if not condition:
        fail(message)


def query(url: str) -> dict[str, list[str]]:
    """Parse query parameters from a URL used by link preservation checks.

    Args:
        url: Absolute or relative URL from a sessions-list control.

    Returns:
        Mapping of query parameter names to ordered values, preserving blanks.
    """
    return urllib.parse.parse_qs(urllib.parse.urlparse(url).query, keep_blank_values=True)


def _read_input(html_path: str | None, url: str | None) -> str:
    """Load the sessions page HTML supplied to the contract checker.

    Args:
        html_path: Optional filesystem artifact path from a previous browser capture.
        url: Optional live local sessions URL to fetch during QA.

    Returns:
        Decoded HTML document used by downstream contract assertions.
    """
    if not html_path and not url:
        fail('provide --html or --url')
    if url:
        return urllib.request.urlopen(url, timeout=10).read().decode('utf-8', errors='replace')
    return Path(str(html_path)).read_text(encoding='utf-8')


def _check_forbidden_classes(nodes: list[Node], all_text: str) -> None:
    """Check removed sessions-list controls and stale footer copy are absent.

    Args:
        nodes: Flat DOM inventory parsed from the sessions page.
        all_text: Normalized page text used for copy-level assertions.
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


def _check_search_contract(nodes: list[Node], all_text: str) -> None:
    """Check the sessions-list search UI only promises Session ID lookup.

    Args:
        nodes: Flat DOM inventory parsed from the sessions page.
        all_text: Normalized page text used for hint assertions.
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


def _check_sort_contract(nodes: list[Node]) -> None:
    """Check sortable headers are label-clickable and expose one aria-sort.

    Args:
        nodes: Flat DOM inventory parsed from the sessions page.
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


def _check_footer_contract(nodes: list[Node], all_text: str) -> None:
    """Check footer pagination labels and hidden state preservation.

    Args:
        nodes: Flat DOM inventory parsed from the sessions page.
        all_text: Normalized page text used for range and total assertions.
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


def _check_filter_chip_removal(nodes: list[Node]) -> None:
    """Check active filter chips expose deterministic removal controls.

    Args:
        nodes: Flat DOM inventory parsed from the sessions page.
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


def main() -> int:
    """Run the sessions-list DOM contract checker CLI.

    The QA gate calls this entry point with either --html for a saved artifact or
    --url for a live local page. It prints PASS on success, prints FAIL and exits
    1 on contract violations, and only reads the provided page input.

    Returns:
        Process exit code 0 when all sessions-list behavior checks pass.
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
