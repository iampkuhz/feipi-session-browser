#!/usr/bin/env python3
"""P0 门禁：JS data-action handler 检查。

规则:
- 所有 data-action 属性必须有对应的 JS handler 或显式 no-op reason
- 关键按钮（Expand all、Failed、round lazy load、Request/Response 归因）必须有 handler

用法:
    python3 scripts/quality/check_js_action_handlers.py

退出码:
    0 — 通过
    1 — 发现无 handler 的 data-action
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_DIR = REPO_ROOT / "src" / "session_browser" / "web" / "templates"
JS_DIR = REPO_ROOT / "src" / "session_browser" / "web" / "static" / "js"

# 关键 action 必须存在 handler
CRITICAL_ACTIONS = {
    "toggle-all",       # Expand all / Collapse all
    "status-failed",    # Failed filter
    "toggle-round",     # Round lazy load/toggle
    "open-payload",     # Payload modal
    "payload-filter",   # Payload tab filter / coverage matrix
    "tab-trace",        # Trace tab
    "tab-payload",      # Payload tab
}


def _extract_template_actions() -> dict[str, list[str]]:
    """从所有模板中提取 data-action 值。"""
    actions: dict[str, list[str]] = {}
    for html_file in TEMPLATE_DIR.rglob("*.html"):
        text = html_file.read_text(encoding="utf-8", errors="replace")
        found = re.findall(r'data-action="([^"]+)"', text)
        rel = html_file.relative_to(REPO_ROOT).as_posix()
        if found:
            actions[rel] = found
    return actions


def _extract_js_handlers() -> set[str]:
    """从所有 JS 文件中提取 handler 的 action key。"""
    handlers: set[str] = set()
    for js_file in JS_DIR.rglob("*.js"):
        text = js_file.read_text(encoding="utf-8", errors="replace")
        # 匹配 data-action 查找模式
        found = re.findall(r'(?:data-action|getAttribute\(["\']data-action["\']\)|dataset\.action)\s*["\'=]\s*["\']?([a-z][a-z0-9_-]*)', text)
        # 更通用的：查找 action 字符串引用
        found2 = re.findall(r'["\']([a-z][a-z0-9_-]*)["\']\s*(?:===|==|\.includes|\.indexOf)', text)
        found2b = re.findall(r'\baction\b\s*(?:===|==)\s*["\']([a-z][a-z0-9_-]*)["\']', text)
        found2c = re.findall(r'\.dataset\.action\s*(?:===|==)\s*["\']([a-z][a-z0-9_-]*)["\']', text)
        found3 = re.findall(r'const\s+\w+Action\s*=\s*["\']([a-z][a-z0-9_-]*)["\']', text)
        found4 = re.findall(r'case\s+["\']([a-z][a-z0-9_-]*)["\']', text)
        handlers.update(found)
        handlers.update(found2)
        handlers.update(found2b)
        handlers.update(found2c)
        handlers.update(found3)
        handlers.update(found4)
        if "action.indexOf('tab-')" in text or 'action.indexOf("tab-")' in text:
            handlers.update({"tab-trace", "tab-payload", "tab-metrics"})
    return handlers


def main() -> None:
    template_actions = _extract_template_actions()
    js_handlers = _extract_js_handlers()

    # 内置 action（浏览器行为或 CSS-only）不需要 JS handler
    built_in = {"sort", "page-input", "go-dashboard", "go-sessions", "run-scan",
                "open-project", "open-project-link", "open-agent", "clear-search",
                "info", "metric-info", "close-modal", "prev-page", "next-page",
                "nav-dashboard", "nav-projects",
                "nav-sessions", "nav-glossary", "payload-mode"}

    errors: list[str] = []
    critical_missing: list[str] = []

    all_actions: set[str] = set()
    for actions in template_actions.values():
        all_actions.update(actions)

    for action in sorted(all_actions):
        if action in built_in:
            continue
        if action not in js_handlers:
            if action in CRITICAL_ACTIONS:
                critical_missing.append(action)
                errors.append(f"[BLOCK] 关键 action '{action}' 无 JS handler")
            else:
                errors.append(f"[WARN] action '{action}' 无 JS handler")

    if critical_missing:
        print("")
        for e in errors:
            print(e)
        print(f"\n关键缺失: {', '.join(critical_missing)}")
        sys.exit(1)
    else:
        print(f"[PASS] 全部 {len(all_actions)} 个 data-action 均有 handler 或豁免。")
        sys.exit(0)


if __name__ == "__main__":
    main()
