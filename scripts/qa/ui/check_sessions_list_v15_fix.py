#!/usr/bin/env python3
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

routes = read("src/session_browser/web/routes.py")
indexer = read("src/session_browser/index/indexer.py")
sessions_html = read("src/session_browser/web/templates/sessions.html")
grid_html = read("src/session_browser/web/templates/partials/sessions_grid.html")
css = read("src/session_browser/web/static/css/sessions-list.css") + "\n" + read("src/session_browser/web/static/css/session-browser-v15.css")

if "Refresh" in sessions_html or "refresh-link" in sessions_html or "refresh-link" in grid_html:
    problems.append("Refresh button/link still appears in sessions templates.")

if "500" not in routes or "page_size" not in routes:
    problems.append("routes.py does not appear to support page_size=500.")
for value in ["20", "100", "500", "all"]:
    if value not in (sessions_html + grid_html + routes).lower():
        problems.append(f"missing page size option {value}.")

if "order_dir" not in indexer and "sort_dir" not in indexer:
    problems.append("indexer.list_sessions does not appear to apply sort direction.")
if "assistant_message_count" not in routes or "rounds" not in routes:
    problems.append("rounds sort mapping is missing assistant_message_count.")
if "order_dir=raw_dir" not in routes and "sort_dir=raw_dir" not in routes:
    problems.append("routes.py does not appear to pass raw_dir into list_sessions.")

if not re.search(r"SUM\s*\(", routes, re.I) or "cached_input_tokens" not in routes or "cached_output_tokens" not in routes:
    problems.append("routes.py does not appear to compute aggregate token total for filtered sessions.")

for key in ["claude", "codex", "qoder"]:
    if key not in css.lower() or key not in (sessions_html + grid_html).lower():
        problems.append(f"agent tone for {key} is not represented in CSS/templates.")

flat_css = css.replace(" ", "")
if "margin-inline:auto" not in flat_css and "margin:0auto" not in flat_css:
    problems.append("sessions page CSS does not appear to center the page shell.")
if "max-width" not in css:
    problems.append("sessions page CSS lacks max-width for centered page shell.")

if "ROUNDS" not in (sessions_html + grid_html).upper():
    problems.append("ROUNDS header not found in sessions templates.")
if "minmax" not in css or "round" not in css.lower():
    problems.append("CSS does not appear to explicitly size rounds column/header.")

if problems:
    print("FAIL: sessions-list-v15-fix static checks")
    for p in problems:
        print("-", p)
    raise SystemExit(1)

print("PASS: sessions-list-v15-fix static checks")
