#!/usr/bin/env python3
"""Session Detail Timeline v11 contract checker.

Usage:
  python scripts/qa/session_ui/check_session_detail_timeline_v11_contract.py --html /tmp/session-detail.html
  python scripts/qa/session_ui/check_session_detail_timeline_v11_contract.py --url http://127.0.0.1:18999/sessions/<agent>/<id>
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


def has_class(nodes: list[Node], class_name: str) -> bool:
    return any(class_name in cls(n) for n in nodes)


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    raise SystemExit(1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--html")
    ap.add_argument("--url")
    ap.add_argument("--css", default="src/session_browser/web/static/css/session-detail-timeline-v11.css")
    ap.add_argument("--js", default="src/session_browser/web/static/js/session_detail_timeline_v11.js")
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
    page_text = " ".join(text(n) for n in nodes)

    required_attrs = [
        ("data-session-detail-shell", None),
        ("data-session-overview-hero", None),
        ("data-trace-page", None),
        ("data-trace-panel", None),
        ("data-trace-round-row", None),
        ("data-trace-detail", None),
        ("data-inline-call-card", None),
        ("data-user-message", None),
        ("data-subagent-block", None),
        ("data-sub-round", None),
        ("data-sub-llm-card", None),
        ("data-payload-body", None),
        ("data-payload-source", None),
    ]
    for key, value in required_attrs:
        if not has_attr(nodes, key, value):
            fail(f"missing [{key}{'=' + value if value else ''}]")

    for class_name in [
        "sd-user-round",
        "sd-payload-modal__panel",
        "sd-sub-llm",
        "sd-sub-mcell",
        "sd-sub-pbtn",
        "sd-note",
    ]:
        if not has_class(nodes, class_name):
            fail(f"missing .{class_name}")

    forbidden_attrs = [
        ("data-context-inspector", None),
        ("data-workbench-view", "calls"),
        ("data-workbench-view", "hotspots"),
        ("role", "tablist"),
    ]
    for key, value in forbidden_attrs:
        if has_attr(nodes, key, value):
            fail(f"forbidden [{key}{'=' + value if value else ''}]")

    for forbidden_class in ["phase1-shell", "no-inspector", "round-summary-table", "tab-content"]:
        if has_class(nodes, forbidden_class):
            fail(f"forbidden class present: .{forbidden_class}")

    for forbidden_text in [
        "Round 内按时间顺序纵向推进",
        "用户输入作为独立高亮 round",
        "payload modal 必须可打开",
        "sd-note 展示规则",
        "Open selected",
        "High token",
    ]:
        if forbidden_text in page_text:
            fail(f"forbidden visible text present: {forbidden_text}")
    # Single words: use word-boundary matching to avoid substring false positives
    # (e.g., "Go" inside "Good")
    for forbidden_word in ["Map", "Inspector", "Focus", "Calls", "Hotspots", "Go", "Clear"]:
        if re.search(r'\b' + re.escape(forbidden_word) + r'\b', page_text):
            fail(f"forbidden word present: {forbidden_word}")

    payload_sources = {n.attrs.get("data-payload-source") for n in nodes if n.tag == "template" and n.attrs.get("data-payload-source")}
    open_payload_buttons = [n for n in nodes if n.attrs.get("data-action") == "open-payload"]
    if not open_payload_buttons:
        fail("no open-payload buttons found")
    for button in open_payload_buttons:
        payload_id = button.attrs.get("data-payload-id")
        if not payload_id:
            fail("open-payload button missing data-payload-id")
        if payload_id not in payload_sources:
            fail(f"open-payload id has no matching template source: {payload_id}")

    toggle_all = [n for n in nodes if n.attrs.get("data-action") == "toggle-all"]
    if len(toggle_all) != 1:
        fail(f"expected exactly one toggle-all button, got {len(toggle_all)}")
    if toggle_all[0].attrs.get("data-state") not in {"collapse", "expand"}:
        fail("toggle-all missing data-state collapse/expand")

    for button in [n for n in nodes if n.attrs.get("data-action") == "toggle-round"]:
        if "aria-expanded" not in button.attrs or "aria-controls" not in button.attrs:
            fail("toggle-round button missing aria-expanded/aria-controls")
    for button in [n for n in nodes if n.attrs.get("data-action") == "toggle-sub-round"]:
        if "aria-expanded" not in button.attrs or "aria-controls" not in button.attrs:
            fail("toggle-sub-round button missing aria-expanded/aria-controls")

    css_path = Path(args.css)
    if css_path.exists():
        css = css_path.read_text(encoding="utf-8")
        for pattern in [
            r"\.sd-user-round",
            r"\.sd-sub-llm",
            r"\.sd-sub-mcell\s+b",
            r"\.sd-payload-modal__panel",
            r"\.sd-note--warn",
        ]:
            if not re.search(pattern, css, flags=re.S):
                fail(f"CSS contract missing pattern: {pattern}")

    js_path = Path(args.js)
    if js_path.exists():
        js = js_path.read_text(encoding="utf-8")
        for required in [
            "function openPayload",
            "function toggleAll",
            "function setSubRoundOpen",
            'data-action="toggle-all"',
            "template[data-payload-source",
        ]:
            if required not in js:
                fail(f"JS contract missing: {required}")
        if "### Payload unavailable" in js:
            fail("JS still contains markdown-string fallback that can break parsing")

    print("PASS: session detail timeline v11 contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
