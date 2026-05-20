#!/usr/bin/env python3
from __future__ import annotations
import argparse
import re
from pathlib import Path

ROOT = Path(".")

def read(path: str) -> str:
    p = ROOT / path
    return p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--html", default="")
    args = ap.parse_args()

    problems: list[str] = []

    session = read("src/session_browser/web/templates/session.html")
    timeline = read("src/session_browser/web/templates/components/session_detail_timeline.html")
    primitives = read("src/session_browser/web/templates/components/session_detail_primitives.html")
    base = read("src/session_browser/web/templates/base.html")
    js = read("src/session_browser/web/static/js/session_detail_timeline.js")
    css_main = read("src/session_browser/web/static/css/session-detail-timeline.css")
    css_all = css_main
    for path in [
        "src/session_browser/web/static/css/session-detail-timeline-v11.css",
        "src/session_browser/web/static/css/session-detail-response-blocks-v12.css",
        "src/session_browser/web/static/css/session-detail-payload-v16.css",
    ]:
        if Path(path).exists():
            css_all += "\n/* " + path + " */\n" + read(path)

    rendered = read(args.html) if args.html else ""
    all_tpl = session + timeline + primitives + base + rendered

    imports = session + base
    for legacy in ["session-detail-timeline-v11.css", "session-detail-response-blocks-v12.css", "session-detail-payload-v16.css"]:
        if legacy in imports:
            problems.append(f"legacy session detail CSS is still imported: {legacy}")
    if "session-detail-timeline.css" not in imports and "session-detail-timeline.css" not in css_main:
        problems.append("canonical session-detail-timeline.css is not clearly used/imported.")

    compact = css_all.replace(" ", "")
    required_modal_bits = [
        "position:fixed",
        "left:50%",
        "top:50%",
        "translate(-50%,-50%)",
        "70vw",
        "1120px",
        "max-height:82vh",
        "92vw",
    ]
    for bit in required_modal_bits:
        if bit not in compact:
            problems.append(f"modal CSS missing: {bit}")

    if rendered:
        if re.search(r'<body[^>]*>\s*R\d+\s*[·.-]\s*(User request|LLM Call)', rendered, re.I):
            problems.append("rendered modal appears to start as document-flow content before app shell; likely full-page fallback.")
        if "payload-modal__panel" in rendered and "position: fixed" not in css_all and "position:fixed" not in compact:
            problems.append("payload panel rendered but no fixed modal CSS detected.")

    for needle in ["{% if call.context_payload_id %}", "{% if call.response_payload_id %}", "if call.context_payload_id", "if call.response_payload_id"]:
        if needle in timeline:
            problems.append(f"Context/Response button still conditional: {needle}")

    if "body.innerHTML = ''" in js or "innerHTML=''" in js or "document.body.innerHTML" in js:
        problems.append("openPayload may blank or replace document body.")
    if "location.href" in js or "window.location" in js:
        problems.append("openPayload may navigate instead of opening modal.")
    if not any(x in js for x in ["payload-warning", "未找到 payload", "diagnostic"]):
        problems.append("openPayload lacks diagnostic fallback.")

    if not any(x in all_tpl for x in ["context-tool-list", "sd-context-tool-list", "Tool result list before this LLM call"]):
        problems.append("context payload UI does not include previous tool result list.")

    tpl_only = session + timeline + primitives + base
    if "仅捕获渲染上下文；完整 raw HTTP request 未持久化" in tpl_only + css_all:
        problems.append("hardcoded meaningless sd-note remains.")

    if ".sd-tool-result" not in css_all:
        problems.append("sd-tool-result CSS missing.")
    if "sd-tool-row--failed" not in css_all and "sd-tool-row--fail" not in css_all and "data-status=\"failed\"" not in css_all:
        problems.append("failed tool-row styling missing.")
    global_result_rule = re.search(r"\.sd-tool-result\s*\{([^}]*)\}", css_all, re.S)
    if global_result_rule and ("--sd-err" in global_result_rule.group(1) or "red" in global_result_rule.group(1)):
        problems.append("global .sd-tool-result still appears red; only failed rows should be red.")

    if "sd-round-status--failed" not in css_all and "sd-round-status--fail" not in css_all:
        problems.append("FAILED round status class missing.")

    for bit in ["minmax(0,1fr)", "min-width:0", "text-overflow:ellipsis", "white-space:nowrap"]:
        if bit not in compact:
            problems.append(f"narrow truncation CSS missing: {bit}")
    if "column-gap" not in css_all and "gap:" not in css_all:
        problems.append("round grid gap missing.")

    if problems:
        print("FAIL: session detail v17 checks")
        for m in problems:
            print("-", m)
        return 1

    print("PASS: session detail v17 checks")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
