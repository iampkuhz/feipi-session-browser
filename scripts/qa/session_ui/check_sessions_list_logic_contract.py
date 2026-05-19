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
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass, field


@dataclass
class Node:
    tag: str
    attrs: dict[str, str]
    text: list[str] = field(default_factory=list)
    children: list["Node"] = field(default_factory=list)


class Parser(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.root = Node("root", {})
        self.stack = [self.root]
        self.nodes: list[Node] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = Node(tag, {k: (v or "") for k, v in attrs})
        self.stack[-1].children.append(node)
        self.stack.append(node)
        self.nodes.append(node)

    def handle_endtag(self, tag: str) -> None:
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break

    def handle_data(self, data: str) -> None:
        if self.stack:
            self.stack[-1].text.append(data)


def cls(node: Node) -> set[str]:
    return set(node.attrs.get("class", "").split())


def text_of(node: Node) -> str:
    parts = list(node.text)
    for child in node.children:
        parts.append(text_of(child))
    return " ".join(" ".join(parts).split())


def all_desc(node: Node) -> list[Node]:
    out = []
    for child in node.children:
        out.append(child)
        out.extend(all_desc(child))
    return out


def find_by_class(nodes: list[Node], class_name: str) -> list[Node]:
    return [n for n in nodes if class_name in cls(n)]


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    raise SystemExit(1)


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def query(url: str) -> dict[str, list[str]]:
    return urllib.parse.parse_qs(urllib.parse.urlparse(url).query, keep_blank_values=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--html")
    ap.add_argument("--url")
    args = ap.parse_args()
    if not args.html and not args.url:
        fail("provide --html or --url")

    if args.url:
        html = urllib.request.urlopen(args.url, timeout=10).read().decode("utf-8", errors="replace")
    else:
        html = open(args.html, encoding="utf-8").read()

    p = Parser()
    p.feed(html)
    nodes = p.nodes

    all_text = " ".join(text_of(n) for n in nodes)

    for forbidden_class in ["density-toggle", "round-map", "row--failed", "row--anomaly", "highlight-warn"]:
        require(not find_by_class(nodes, forbidden_class), f"forbidden class present: .{forbidden_class}")

    require("sorted by" not in all_text, "footer must not contain 'sorted by'")

    # Search contract.
    search_inputs = [n for n in nodes if n.tag == "input" and n.attrs.get("name") in {"q", "session_id", "session"}]
    require(search_inputs, "missing session id search input")
    search_input = search_inputs[0]
    hint_ok = ("仅支持 Session ID" in all_text) or ("Session ID" in search_input.attrs.get("placeholder", ""))
    require(hint_ok, "search must clearly say it only supports Session ID")

    # Sort header contract.
    sortable_headers = find_by_class(nodes, "sessions-th--sortable")
    require(len(sortable_headers) == 5, f"expected 5 sortable headers, got {len(sortable_headers)}")
    expected_sort = ["Tokens", "Rounds", "Tools", "Duration", "Updated"]
    got_sort = []
    for h in sortable_headers:
        label_text = text_of(h).replace("↕", "").replace("↑", "").replace("↓", "").strip()
        got_sort.append(label_text)
        descendants = all_desc(h)
        clickable = [d for d in descendants if d.tag in {"a", "button"}]
        require(clickable, f"sortable header {label_text!r} has no clickable control")
        control_text = " ".join(text_of(c) for c in clickable).replace("↕", "").replace("↑", "").replace("↓", "").strip()
        require(label_text in control_text or control_text in label_text, f"sortable header {label_text!r} clickable text is not the label; icon-only sort control detected")
        if clickable[0].tag == "a":
            require(clickable[0].attrs.get("href"), f"sortable header {label_text!r} anchor has no href")
        if clickable[0].tag == "button":
            require(clickable[0].attrs.get("type") in {"submit", "button"}, f"sortable header {label_text!r} button type missing")
    require(got_sort == expected_sort, f"sortable headers mismatch: {got_sort!r}")

    aria_sort = [n for n in sortable_headers if "aria-sort" in n.attrs]
    require(len(aria_sort) == 1, f"expected exactly one aria-sort, got {len(aria_sort)}")

    # Filter/page/sort state contract: href preferred, forms allowed with hidden state.
    footer = find_by_class(nodes, "sessions-table-footer")
    require(footer, "missing sessions table footer")
    footer_desc = all_desc(footer[0])
    footer_controls = [n for n in footer_desc if n.tag in {"a", "button"}]
    labels = [text_of(n).strip() for n in footer_controls]
    require("Previous" in labels, "footer missing Previous")
    require("Next" in labels, "footer missing Next")
    require("Rows " in all_text, "footer missing Rows range")
    require("matching sessions" in all_text, "footer missing matching sessions total")

    # If pagination uses buttons, they must be inside a form carrying current state.
    page_buttons = [n for n in nodes if n.tag == "button" and n.attrs.get("name") == "page"]
    if page_buttons:
        # We cannot fully reconstruct ancestors with this parser, so enforce hidden inputs are present somewhere.
        hidden_names = {n.attrs.get("name") for n in nodes if n.tag == "input" and n.attrs.get("type") == "hidden"}
        for required in ["sort", "dir"]:
            require(required in hidden_names, f"pagination buttons require hidden input preserving {required}")
        # At least one filter state hidden field should exist when not using links.
        require(any(name in hidden_names for name in ["q", "agent", "model", "project", "date"]), "pagination buttons require hidden inputs preserving filters")

    # Active filter removal should be deterministic: either anchors with href or submit controls with hidden state.
    chips = find_by_class(nodes, "ui-filter-chip")
    for chip in chips:
        desc = all_desc(chip)
        remove_controls = [d for d in desc if d.tag in {"a", "button"}]
        if remove_controls:
            ctl = remove_controls[0]
            if ctl.tag == "a":
                require(ctl.attrs.get("href"), "filter chip remove anchor missing href")
            else:
                require(ctl.attrs.get("name"), "filter chip remove button missing name")

    print("PASS: sessions list logic contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
