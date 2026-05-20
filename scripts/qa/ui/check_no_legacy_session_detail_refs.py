#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path

SEARCH = [
    "src/session_browser/web/templates",
    "src/session_browser/web/static/css",
]
LEGACY = [
    "session-detail-timeline-v11.css",
    "session-detail-response-blocks-v12.css",
    "session-detail-payload-v16.css",
    "session_detail_timeline_v11.html",
    "session_detail_timeline_v12.html",
]

problems = []
for base in SEARCH:
    p = Path(base)
    if not p.exists():
        continue
    for f in p.rglob("*"):
        if f.is_file() and f.suffix in {".html", ".css", ".js"}:
            text = f.read_text(encoding="utf-8", errors="replace")
            for legacy in LEGACY:
                if legacy in text:
                    problems.append(f"{f}: references {legacy}")

if problems:
    print("FAIL: legacy session-detail references")
    for p in problems:
        print("-", p)
    raise SystemExit(1)

print("PASS: no legacy session-detail references")
