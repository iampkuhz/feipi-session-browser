#!/usr/bin/env python3
"""Validate the rendered session detail response-blocks v12 DOM contract."""

from __future__ import annotations

import argparse
import html.parser
import pathlib
import sys
import urllib.request


class Parser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.nodes = []
        self.text = []

    def handle_starttag(self, tag, attrs):
        self.nodes.append((tag, dict(attrs)))

    def handle_data(self, data):
        self.text.append(data)


def fail(message: str) -> None:
    sys.exit(f"FAIL {message}")


ap = argparse.ArgumentParser()
ap.add_argument("--html")
ap.add_argument("--url")
args = ap.parse_args()

if not args.html and not args.url:
    fail("provide --html or --url")

html = (
    urllib.request.urlopen(args.url, timeout=15).read().decode("utf-8")
    if args.url
    else pathlib.Path(args.html).read_text(encoding="utf-8")
)

parser = Parser()
parser.feed(html)
attrs = [a for _, a in parser.nodes]
classes = " ".join(a.get("class", "") for a in attrs)

for class_name in [
    "sd-content-block--text",
    "sd-content-block--tool",
    "sd-tool-input-grid",
    "sd-json-inline",
    "sd-user-round",
    "sd-tool-group",
    "sd-sub-tool-group",
    "sd-tool-row",
]:
    if class_name not in classes:
        fail(f"missing .{class_name}")

if "Content</button>" in html or "Metadata</button>" in html or "Debug</button>" in html:
    fail("payload tabs still present")

sources = {a.get("data-payload-source") for a in attrs if a.get("data-payload-source")}
supported_actions = {
    "open-payload",
    "close-payload",
    "toggle-round",
    "toggle-sub-round",
    "toggle-all",
    "filter-status",
    "jump-round",
}

for tag, attr in parser.nodes:
    if tag != "button":
        continue
    action = attr.get("data-action")
    if action not in supported_actions:
        fail(f"unsupported or missing button action: {action or '<missing>'}")
    if action == "open-payload":
        payload_id = attr.get("data-payload-id")
        if not payload_id:
            fail("open-payload missing data-payload-id")
        if payload_id not in sources:
            fail(f"no matching payload source: {payload_id}")

print("PASS response blocks v12 contract")
