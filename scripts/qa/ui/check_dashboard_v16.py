#!/usr/bin/env python3
"""Static QA checks for dashboard v16.

Run from repo root:
  python scripts/qa/ui/check_dashboard_v16.py
"""
from __future__ import annotations
from pathlib import Path
import re

problems = []

def read(path: str) -> str:
    p = Path(path)
    if not p.exists():
        problems.append(f"missing file: {path}")
        return ""
    return p.read_text(encoding="utf-8", errors="replace")

html = read("src/session_browser/web/templates/dashboard.html")
css = read("src/session_browser/web/static/css/dashboard-v16.css") + "\n" + read("src/session_browser/web/static/css/session-browser-v15.css")
routes = read("src/session_browser/web/routes.py")

if "Recent activity" in html or "RECENT ACTIVITY" in html.upper():
    problems.append("Recent Activity still appears in dashboard template.")

for word in ["compact", "紧凑"]:
    if word in html.lower():
        problems.append(f"dashboard still appears to include compact/tight toggle text: {word}")

for required in ["Session Trend", "Token Trend"]:
    if required not in html:
        problems.append(f"missing chart title: {required}")

if "data-tip" not in html and "::after" not in css:
    problems.append("bar hover tooltip is not implemented.")

if "margin-top:auto" not in css.replace(" ", "") and "margin-top: auto" not in css:
    problems.append("footer is not pinned with margin-top:auto.")

if "display:flex" not in css.replace(" ", "") or "flex-direction:column" not in css.replace(" ", ""):
    problems.append("main/page shell does not appear to use flex column layout.")

if "token" not in routes.lower() or "trend" not in routes.lower():
    problems.append("routes.py may not provide token trend data.")

if not re.search(r"SUM\s*\(", routes, re.I):
    problems.append("routes.py does not appear to aggregate token trend with SUM().")

if problems:
    print("FAIL: dashboard-v16 static checks")
    for p in problems:
        print("-", p)
    raise SystemExit(1)

print("PASS: dashboard-v16 static checks")
