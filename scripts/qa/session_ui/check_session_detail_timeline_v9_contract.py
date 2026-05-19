#!/usr/bin/env python3
"""Session Detail Timeline v9 contract checker.

Usage:
  curl -fsS http://127.0.0.1:18999/sessions/<agent>/<id> > /tmp/session-detail.html
  python scripts/qa/session_ui/check_session_detail_timeline_v9_contract.py --html /tmp/session-detail.html
"""
from __future__ import annotations

import argparse
import html.parser
import re
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Node:
    tag: str
    attrs: dict[str, str]
    text: list[str] = field(default_factory=list)


class Parser(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.nodes: list[Node] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.nodes.append(Node(tag, {k: (v or "") for k, v in attrs}))

    def handle_data(self, data: str) -> None:
        if self.nodes:
            self.nodes[-1].text.append(data)


def cls(node: Node) -> set[str]:
    return set(node.attrs.get("class", "").split())


def text(node: Node) -> str:
    return " ".join(" ".join(node.text).split())


def has_attr(nodes: list[Node], key: str, value: str | None = None) -> bool:
    return any(key in n.attrs and (value is None or n.attrs.get(key) == value) for n in nodes)


def has_class(nodes: list[Node], name: str) -> bool:
    return any(name in cls(n) for n in nodes)


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    raise SystemExit(1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--html")
    ap.add_argument("--url")
    ap.add_argument("--css", default="src/session_browser/web/static/css/session-detail-timeline.css")
    args = ap.parse_args()

    if args.url:
        html = urllib.request.urlopen(args.url, timeout=10).read().decode("utf-8", "replace")
    elif args.html:
        html = Path(args.html).read_text(encoding="utf-8")
    else:
        fail("provide --html or --url")

    parser = Parser()
    parser.feed(html)
    nodes = parser.nodes
    all_text = " ".join(text(n) for n in nodes)

    required_attrs = [
        ("data-session-detail-shell", None),
        ("data-session-overview-hero", None),
        ("data-trace-page", None),
        ("data-trace-panel", None),
        ("data-trace-round-row", None),
        ("data-trace-detail", None),
        ("data-inline-call-card", None),
    ]
    for key, value in required_attrs:
        if not has_attr(nodes, key, value):
            fail(f"missing [{key}{'=' + value if value else ''}]")

    required_classes = [
        "sd-timeline",
        "sd-tool-group",
        "sd-tool-row",
        "sd-subagent",
        "sd-sub-round",
        "sd-mcell",
        "sd-agent-pill",
    ]
    for name in required_classes:
        if not has_class(nodes, name):
            fail(f"missing .{name}")

    forbidden_attrs = [
        ("data-context-inspector", None),
        ("data-workbench-view", "calls"),
        ("data-workbench-view", "hotspots"),
        ("role", "tablist"),
    ]
    for key, value in forbidden_attrs:
        if has_attr(nodes, key, value):
            fail(f"forbidden [{key}{'=' + value if value else ''}]")

    forbidden_classes = ["phase1-shell", "no-inspector", "round-summary-table", "tab-content"]
    for name in forbidden_classes:
        if has_class(nodes, name):
            fail(f"forbidden class present: .{name}")

    for forbidden_text in ["Map", "Inspector", "Focus", "Open selected", "Calls", "Hotspots", "High token", "Go", "Clear"]:
        if forbidden_text in all_text:
            fail(f"forbidden visible text present: {forbidden_text}")

    for button in [n for n in nodes if n.attrs.get("data-action") == "toggle-round"]:
        if "aria-expanded" not in button.attrs or "aria-controls" not in button.attrs:
            fail("toggle-round button missing aria-expanded/aria-controls")

    for button in [n for n in nodes if n.attrs.get("data-action") == "open-payload"]:
        if "data-payload-id" not in button.attrs:
            fail("open-payload button missing data-payload-id")

    css_path = Path(args.css)
    if css_path.exists():
        css = css_path.read_text(encoding="utf-8")
        for pattern in [
            r"\.sd-agent-pill[^{}]*\{[^{}]*justify-content:\s*center",
            r"\.sd-mcell\s+b[^{}]*\{[^{}]*font-size:\s*16px",
            r"\.sd-timeline:before",
            r"\.sd-sub-round",
        ]:
            if not re.search(pattern, css, flags=re.S):
                fail(f"CSS contract missing pattern: {pattern}")

    print("PASS: session detail timeline v9 contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
