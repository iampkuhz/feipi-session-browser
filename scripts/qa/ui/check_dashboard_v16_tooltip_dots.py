#!/usr/bin/env python3
"""Static checks for Dashboard v16 tooltip dots.

Run from repo root:
  python scripts/qa/ui/check_dashboard_v16_tooltip_dots.py
"""
from __future__ import annotations
from pathlib import Path

problems = []

def read(path: str) -> str:
    p = Path(path)
    if not p.exists():
        problems.append(f"missing file: {path}")
        return ""
    return p.read_text(encoding="utf-8", errors="replace")

html = read("src/session_browser/web/templates/dashboard.html")
css = read("src/session_browser/web/static/css/dashboard-v16.css") + "\n" + read("src/session_browser/web/static/css/dashboard-v16-tooltip-dots.css")
routes = read("src/session_browser/web/routes.py")

for cls in ["dashboard-tooltip", "tooltip-row", "tooltip-dot--claude", "tooltip-dot--codex", "tooltip-dot--qoder", "tooltip-dot--total"]:
    if cls not in html and cls not in css:
        problems.append(f"missing tooltip class: {cls}")

for label in ["Claude Code", "Codex", "Qoder", "Total"]:
    if label not in html and label not in routes:
        problems.append(f"tooltip label/value source missing: {label}")

if "title=" in html and "dashboard-tooltip" not in html:
    problems.append("tooltip appears to rely on title= instead of structured DOM tooltip")

if "data-tip" in html and "dashboard-tooltip" not in html:
    problems.append("tooltip appears to rely only on data-tip instead of structured DOM tooltip")

if "Token Trend" not in html:
    problems.append("Token Trend chart missing")
if "Session Trend" not in html:
    problems.append("Session Trend chart missing")

if problems:
    print("FAIL: dashboard-v16-tooltip-dots checks")
    for p in problems:
        print("-", p)
    raise SystemExit(1)

print("PASS: dashboard-v16-tooltip-dots checks")
