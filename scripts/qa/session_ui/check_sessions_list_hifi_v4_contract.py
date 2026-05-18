#!/usr/bin/env python3
"""Contract checker for Sessions List HIFI v4. Uses only the Python standard library."""
from __future__ import annotations
import argparse, html.parser, urllib.request
from dataclasses import dataclass, field

@dataclass
class Node:
    tag: str
    attrs: dict[str, str]
    text: list[str] = field(default_factory=list)

class Parser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.nodes = []
        self.stack = []
    def handle_starttag(self, tag, attrs):
        node = Node(tag, {k:(v or "") for k,v in attrs})
        self.nodes.append(node)
        self.stack.append(node)
    def handle_endtag(self, tag):
        for i in range(len(self.stack)-1, -1, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break
    def handle_data(self, data):
        if self.stack:
            self.stack[-1].text.append(data)

def cls(n): return set(n.attrs.get("class","").split())
def text(n): return " ".join(" ".join(n.text).split())
def has(nodes, c): return any(c in cls(n) for n in nodes)
def fail(msg): print("FAIL:", msg); raise SystemExit(1)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--html")
    ap.add_argument("--url")
    args = ap.parse_args()
    if not args.html and not args.url:
        fail("provide --html or --url")
    if args.url:
        html_text = urllib.request.urlopen(args.url, timeout=10).read().decode("utf-8", "replace")
    else:
        html_text = open(args.html, encoding="utf-8").read()
    p = Parser()
    p.feed(html_text)
    nodes = p.nodes
    required = [
        "sessions-page","sessions-page-title","sessions-filter-card","sessions-filter-head",
        "sessions-control-row","sessions-active-filters","sessions-table-card","sessions-table-toolbar",
        "sessions-table-scroll","sessions-grid","sessions-table-footer","sessions-page-range","sessions-footer-total"
    ]
    for c in required:
        if not has(nodes, c): fail(f"missing .{c}")
    forbidden = [
        "density-toggle","round-map","sessions-card","filter-bar","table-wrap","data-table",
        "table-head","row--failed","row--anomaly","highlight-warn","static-mark","legend"
    ]
    for c in forbidden:
        if has(nodes, c): fail(f"forbidden class present: .{c}")
    all_text = " ".join(text(n) for n in nodes)
    for s in ["Msgs","Cache R","Cache W","Output","Failures","Signals","sorted by"]:
        if s in all_text: fail(f"forbidden text present: {s}")
    headers = [n for n in nodes if n.attrs.get("role") == "columnheader"]
    header_texts = [text(n).replace("↕","").replace("↑","").replace("↓","").strip() for n in headers]
    expected = ["Title","Project","Agent","Model","Tokens","Rounds","Tools","Duration","Updated"]
    if header_texts[:9] != expected:
        fail(f"headers mismatch: got {header_texts[:9]!r}, expected {expected!r}")
    sortable = [n for n in nodes if "sessions-th--sortable" in cls(n)]
    if len(sortable) != 5: fail(f"expected 5 sortable headers, got {len(sortable)}")
    aria = [n for n in sortable if "aria-sort" in n.attrs]
    if len(aria) != 1: fail(f"expected exactly one aria-sort header, got {len(aria)}")
    if "仅支持 Session ID" not in all_text: fail("missing search hint")
    if "Rows " not in all_text: fail("missing footer rows range")
    if "matching sessions" not in all_text: fail("missing footer total")
    print("PASS: sessions list HIFI v4 contract")
if __name__ == "__main__":
    main()
