#!/usr/bin/env python3
"""Static UI contract checks for feipi-session-browser.
Run from repository root.

Checks:
  1. No versioned/patch filenames or inline styles/scripts.
  2. All buttons have data-action or type submit/reset.
  3. Responsive breakpoints exist in canonical CSS files:
     - Desktop  (>=1400px)
     - Tablet   (1024px–1399px or <=1399px range)
     - Mobile   (<768px or <=767px)
     - Sidebar collapse/hide on smaller screens
     - Metric grid reflow rules
     - Table horizontal scroll rules
"""
from __future__ import annotations
import re
import sys
from pathlib import Path

ROOT = Path.cwd()
TEMPLATES = ROOT / "src/session_browser/web/templates"
STATIC = ROOT / "src/session_browser/web/static"
DOCS = ROOT / "docs/ui/contracts"
STYLE_CSS = STATIC / "style.css"
UI_PRIMITIVES = STATIC / "css/ui-primitives.css"
STATES_CSS = STATIC / "css/states.css"

FORBIDDEN_NAME_PATTERNS = [
    re.compile(r"v\d+\.(css|js|html)$"),
    re.compile(r"(patch|fix|overlay)\.(css|js)$"),
]
FORBIDDEN_TEXT_PATTERNS = [
    (re.compile(r"onclick\s*="), "inline onclick"),
    (re.compile(r'(?<=[\s>])style\s*=(?!["\']--)(?![\s]*"\{\{)(?!["\'][^"\']*\{\{)'), "inline style"),
    (re.compile(r'<script(?![^>]*src=)(?![^>]*type=["\']application/json["\'])(?![^>]*>\s*\{\{\s*mhtml_js)(?![^>]*>\s*window\._)'), "inline script"),
    (re.compile(r"session-browser-v\d+\.css"), "versioned global css"),
    (re.compile(r"dashboard-v\d+\.css"), "versioned dashboard css"),
    (re.compile(r"session_browser_ui_v\d+\.js"), "versioned ui js"),
]

errors: list[str] = []
passes: list[str] = []

for base in [TEMPLATES, STATIC / "css", STATIC / "js"]:
    if not base.exists():
        errors.append(f"missing directory: {base}")
        continue
    for path in base.rglob("*"):
        if path.is_file():
            for pat in FORBIDDEN_NAME_PATTERNS:
                if pat.search(path.name):
                    errors.append(f"forbidden version/patch filename: {path}")
            if path.suffix in {".html", ".css", ".js"}:
                text = path.read_text(encoding="utf-8", errors="ignore")
                # Skip .js files from inline style/script checks — they are scripts
                # that legitimately create DOM elements with style attributes at runtime.
                if path.suffix == ".js":
                    continue
                for pat, label in FORBIDDEN_TEXT_PATTERNS:
                    if pat.search(text):
                        errors.append(f"{label}: {path}")

# Button check: every literal button should have data-action or type submit/reset OR be in macro definition.
button_re = re.compile(r"<button\b([^>]*)>", re.I)
for path in TEMPLATES.rglob("*.html"):
    text = path.read_text(encoding="utf-8", errors="ignore")
    for m in button_re.finditer(text):
        attrs = m.group(1)
        if "macro" in text[max(0, m.start()-200):m.start()+200]:
            continue
        if "data-action" not in attrs and "type=\"submit\"" not in attrs and "type='submit'" not in attrs:
            errors.append(f"button missing data-action/type submit: {path}:{text[:m.start()].count(chr(10))+1}")

# ── Responsive breakpoint checks ──────────────────────────────────────
# Combine style.css, ui-primitives.css, and states.css for responsive checks.
css_texts: list[str] = []
for css_path in [STYLE_CSS, UI_PRIMITIVES, STATES_CSS]:
    if css_path.exists():
        css_texts.append(css_path.read_text(encoding="utf-8", errors="ignore"))
    else:
        errors.append(f"missing CSS file: {css_path}")

combined_css = "\n".join(css_texts)

# 1. Desktop breakpoint (>=1400px)
if not re.search(r"@media\s*\([^)]*min-width:\s*1400px", combined_css):
    errors.append("missing responsive breakpoint: desktop (min-width: 1400px)")

# 2. Tablet breakpoint (range 1024px–1399px OR max-width 1399px)
has_tablet = (
    re.search(r"@media\s*\([^)]*max-width:\s*1399px", combined_css) or
    re.search(r"@media\s*\([^)]*min-width:\s*1024px\s*\)\s*and\s*\([^)]*max-width:\s*1399px", combined_css)
)
if not has_tablet:
    errors.append("missing responsive breakpoint: tablet (1024px–1399px)")

# 3. Mobile breakpoint (<768px or <=767px)
if not re.search(r"@media\s*\([^)]*max-width:\s*(767|768)px", combined_css):
    errors.append("missing responsive breakpoint: mobile (max-width: 767px or 768px)")

# 4. Sidebar collapse/hide on smaller screens
if not re.search(r"@media\s*\([^)]*max-width:\s*102[0-9]px\s*\)\s*\{[^}]*\.sidebar", combined_css, re.DOTALL):
    # Also accept sidebar-inner hide
    if not re.search(r"@media\s*\([^)]*max-width:\s*102[0-9]px\s*\)\s*\{[^}]*sidebar", combined_css, re.DOTALL):
        errors.append("missing responsive rule: sidebar collapse/hide on tablet+mobile")

# 5. Metric grid reflow
if not re.search(r"@media\s*\([^)]*max-width:\s*(767|768)px[^)]*\)\s*\{[^}]*\.metric-grid", combined_css, re.DOTALL):
    errors.append("missing responsive rule: metric-grid reflow on mobile")

# 6. Table horizontal scroll
has_table_scroll = (
    re.search(r"@media\s*\([^)]*max-width:\s*(767|768)px[^)]*\)\s*\{[^}]*overflow-x:\s*auto", combined_css, re.DOTALL) or
    re.search(r"\.table-wrap\s*\{[^}]*overflow-x:\s*auto", combined_css)
)
if not has_table_scroll:
    errors.append("missing responsive rule: table horizontal scroll on mobile")


# ── Dashboard-specific static checks ──────────────────────────────────
# T067: Dashboard page contract verification.
# Checks against dashboard.html template, dashboard.css, dashboard.js.

DASHBOARD_HTML = TEMPLATES / "dashboard.html"
DASHBOARD_CSS = STATIC / "css" / "dashboard.css"
DASHBOARD_JS = STATIC / "js" / "dashboard.js"

if DASHBOARD_HTML.exists():
    dash_text = DASHBOARD_HTML.read_text(encoding="utf-8", errors="ignore")

    # 0. Verify CSS imports dashboard.css
    if 'css/dashboard.css' in dash_text or "css/dashboard.css" in dash_text:
        passes.append("dashboard.html: imports dashboard.css")
    else:
        errors.append("dashboard.html: does not import dashboard.css")

    # 0b. Verify JS imports dashboard.js
    if 'js/dashboard.js' in dash_text or "js/dashboard.js" in dash_text:
        passes.append("dashboard.html: imports dashboard.js")
    else:
        errors.append("dashboard.html: does not import dashboard.js")

    # 1. All dashboard.html buttons have data-action
    dash_buttons = list(button_re.finditer(dash_text))
    dash_buttons_without_action = []
    for m in dash_buttons:
        attrs = m.group(1)
        # Skip buttons inside Jinja2 macro calls (rendered server-side)
        # and buttons inside macro definitions in ui_primitives
        if "data-action" not in attrs and "type=\"submit\"" not in attrs and "type='submit'" not in attrs:
            dash_buttons_without_action.append(m.group(0))

    if dash_buttons_without_action:
        errors.append(
            f"dashboard.html: {len(dash_buttons_without_action)} button(s) missing data-action/type submit: "
            + "; ".join(b[:80] for b in dash_buttons_without_action)
        )
    else:
        passes.append(f"dashboard.html: all {len(dash_buttons)} buttons have data-action/type submit")

    # 2. Icons (emoji/unicode used as icon) have aria-hidden or aria-label
    # Check metric-card__icon and legend-dot elements for accessibility attributes
    icon_checks = {
        "metric-card__icon aria-hidden": r"metric-card__icon['\"]?[^>]*aria-hidden=['\"]true['\"]",
        "legend-item aria-hidden (legend dots)": r"legend-item[^>]*aria-hidden=['\"]true['\"]",
    }
    for label, pat in icon_checks.items():
        if not re.search(pat, dash_text):
            errors.append(f"dashboard.html: missing icon accessibility: {label}")
        else:
            passes.append(f"dashboard.html: icon accessibility: {label}")

    # 3. Metric grid has 4 cards
    metric_cards = re.findall(r"class=['\"]metric-card['\"]", dash_text)
    if len(metric_cards) == 4:
        passes.append(f"dashboard.html: metric-grid has 4 cards")
    else:
        errors.append(f"dashboard.html: metric-grid has {len(metric_cards)} cards, expected 4")

    # 4. Chart cards have info and menu buttons
    chart_cards = re.findall(r'data-chart-card=["\'](\w+)["\']', dash_text)
    if len(chart_cards) >= 2:
        passes.append(f"dashboard.html: {len(chart_cards)} chart card(s) found ({', '.join(chart_cards)})")
    else:
        errors.append(f"dashboard.html: expected >=2 chart cards, found {len(chart_cards)}")

    # Info buttons on chart cards
    chart_info_btns = re.findall(r'icon-button--info[^>]*data-info=["\']chart-(\w+)["\']', dash_text)
    if len(chart_info_btns) >= 2:
        passes.append(f"dashboard.html: {len(chart_info_btns)} chart info button(s) found")
    else:
        errors.append(f"dashboard.html: expected >=2 chart info buttons, found {len(chart_info_btns)}")

    # Menu buttons on chart cards (icon-button--ghost)
    chart_menu_btns = re.findall(r'icon-button--ghost[^>]*data-action=["\']chart-menu["\']', dash_text)
    if len(chart_menu_btns) >= 2:
        passes.append(f"dashboard.html: {len(chart_menu_btns)} chart menu button(s) found")
    else:
        errors.append(f"dashboard.html: expected >=2 chart menu buttons, found {len(chart_menu_btns)}")

    # 5. Scope-switch has 3 buttons
    scope_btns = re.findall(r'scope-switch__btn[^>]*data-scope=["\'](\w+)["\']', dash_text)
    if len(scope_btns) == 3:
        passes.append(f"dashboard.html: scope-switch has 3 buttons ({', '.join(scope_btns)})")
    else:
        errors.append(f"dashboard.html: scope-switch has {len(scope_btns)} buttons, expected 3 (day, week, month)")

if DASHBOARD_CSS.exists():
    passes.append("dashboard.css exists on disk")
else:
    errors.append("dashboard.css missing: " + str(DASHBOARD_CSS))

if DASHBOARD_JS.exists():
    passes.append("dashboard.js exists on disk")
else:
    errors.append("dashboard.js missing: " + str(DASHBOARD_JS))


if passes:
    print("UI contract checks:")
    for p in passes:
        print(f"  PASS: {p}")

if errors:
    print("\nUI contract check failed:")
    for e in errors:
        print(f"  FAIL: {e}")
    sys.exit(1)

if passes:
    print(f"\nAll UI contract checks passed ({len(passes)} checks)")
else:
    print("UI contract check passed")
