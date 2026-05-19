#!/usr/bin/env python3
from __future__ import annotations
import argparse
from pathlib import Path
from html.parser import HTMLParser

class P(HTMLParser):
    def __init__(self):
        super().__init__()
        self.nodes=[]
    def handle_starttag(self, tag, attrs):
        self.nodes.append((tag, dict(attrs)))

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--html", required=True)
    args=ap.parse_args()
    text=Path(args.html).read_text(encoding="utf-8", errors="replace")
    p=P(); p.feed(text)
    nodes=p.nodes
    sources={a.get("data-payload-source"): a for t,a in nodes if t=="template" and a.get("data-payload-source")}
    buttons=[a for t,a in nodes if a.get("data-action")=="open-payload"]
    problems=[]
    if not buttons: problems.append("missing open-payload buttons")
    for b in buttons:
        pid=b.get("data-payload-id")
        if not pid: problems.append("open-payload button missing data-payload-id")
        elif pid not in sources: problems.append(f"button payload missing template source: {pid}")
    kinds={a.get("data-payload-kind") for a in sources.values()}
    for required in ["context","response","tool_result"]:
        if required not in kinds: problems.append(f"missing payload kind: {required}")
    required_classes=["context-tool-list","content-block","tool-input-grid","result-shell"]
    for cls in required_classes:
        if cls not in text: problems.append(f"missing class/content: {cls}")
    if "Payload unavailable" in text and "data-payload-source" not in text:
        problems.append("payload unavailable without source templates")
    if problems:
        print("FAIL: payload v15 contract")
        for x in problems: print("-",x)
        return 1
    print("PASS: payload v15 contract")
    return 0
if __name__=="__main__":
    raise SystemExit(main())
