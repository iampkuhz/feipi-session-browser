#!/usr/bin/env python3
from __future__ import annotations
import argparse
from pathlib import Path

def read(path: str) -> str:
    p = Path(path)
    return p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--html", default="")
    args = ap.parse_args()
    html = read(args.html) if args.html else ""
    css = read("src/session_browser/web/static/css/session-detail-timeline.css")
    timeline = read("src/session_browser/web/templates/components/session_detail_timeline.html")
    session = read("src/session_browser/web/templates/session.html")
    combined = html + timeline + session
    compact = css.replace(" ", "")
    problems = []

    if not any(x in combined + css for x in ["sd-round--has-user", "data-has-user", "sd-user-round"]):
        problems.append("missing stable user-message round marker")
    if not any(x in css for x in ["sd-round--has-user", "data-has-user", "sd-user-round"]):
        problems.append("CSS lacks persistent user-message round highlight selector")
    if not any(x in css for x in ["#14b8a6", "#99f6e4", "teal", "rgba(20, 184, 166"]):
        problems.append("CSS lacks teal/green user-message tone")

    if not any(x in css + combined for x in ["sd-kv", "payload-kv", "sd-payload-meta__row", "payload-meta__row"]):
        problems.append("metadata key/value grid missing")
    if "grid-template-columns:92pxminmax(0,1fr)" not in compact and "grid-template-columns:90pxminmax(0,1fr)" not in compact:
        problems.append("metadata key/value grid width missing")
    if "text-overflow:ellipsis" not in compact:
        problems.append("metadata/value ellipsis missing")

    if not any(x in css + combined for x in ["sd-llm-content-row", "sd-llm-action-group", "sd-llm-call-actions"]):
        problems.append("LLM call action layout selectors missing")
    if "max-width:132px" not in compact and "max-width:128px" not in compact:
        problems.append("LLM action buttons missing max-width; Response may still stretch")
    if "min-width:max-content" not in compact and "width:auto" not in compact:
        problems.append("LLM action buttons do not appear intrinsic-width")

    for legacy in ["session-detail-timeline-v11.css", "session-detail-response-blocks-v12.css", "session-detail-payload-v16.css"]:
        if legacy in session:
            problems.append(f"legacy CSS imported again: {legacy}")

    if problems:
        print("FAIL: session-detail-v18 checks")
        for p in problems:
            print("-", p)
        return 1
    print("PASS: session-detail-v18 checks")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
