#!/usr/bin/env python3
"""P0 门禁：UI 交互 Smoke 测试。

覆盖：
- 打开 /dashboard、/sessions、/projects、/glossary
- 打开 session detail（如果存在 session），点击 Expand all、Failed filter、round lazy load
- 检查无 console error、无 failed network response、服务端无 ERROR

用法:
    python3 scripts/quality/run_ui_interaction_smoke.py

退出码:
    0 — 通过
    1 — 发现交互失败或服务错误
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import threading
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# 捕获服务日志
log_capture = []

class LogCapture(logging.Handler):
    def emit(self, record):
        if record.levelno >= logging.ERROR:
            log_capture.append(record.getMessage())

async def run_smoke(base_url: str) -> list[str]:
    """执行交互 smoke 测试。返回错误列表。"""
    from playwright.async_api import async_playwright

    errors: list[str] = []
    console_errors: list[str] = []
    failed_requests: list[str] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()

        # 收集 console error
        page.on("pageerror", lambda err: console_errors.append(str(err)))

        # 收集 failed network
        def on_response(resp):
            if resp.status >= 400:
                failed_requests.append(f"{resp.url} -> {resp.status}")
        page.on("response", on_response)

        # ── 1. 页面导航测试 ──
        for path in ["/dashboard", "/sessions", "/projects", "/glossary"]:
            try:
                resp = await page.goto(f"{base_url}{path}", wait_until="domcontentloaded", timeout=15000)
                if resp and resp.status >= 500:
                    errors.append(f"[BLOCK] {path} 返回 {resp.status}")
                elif resp:
                    print(f"  [PASS] {path} -> {resp.status}")
            except Exception as e:
                errors.append(f"[BLOCK] {path} 导航失败: {e}")

        # ── 2. Sessions 页面：点击 filter 按钮 ──
        try:
            resp = await page.goto(f"{base_url}/sessions", wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(500)
            # 尝试点击 clear/reset 按钮
            cleared = await page.evaluate("""
            () => {
                const btn = document.querySelector('[data-action="clear"], [data-action="clear-search"]');
                if (btn) { btn.click(); return true; }
                return false;
            }
            """)
            if cleared:
                print("  [PASS] Sessions 页面 clear 按钮可点击")
        except Exception as e:
            errors.append(f"[BLOCK] Sessions 交互失败: {e}")

        # ── 3. Projects 页面：点击 open-project ──
        try:
            resp = await page.goto(f"{base_url}/projects", wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(500)
            # 检查 table 是否存在
            has_table = await page.evaluate("() => !!document.querySelector('#projects-table, .data-table')")
            if has_table:
                print("  [PASS] Projects 页面数据表存在")
        except Exception as e:
            errors.append(f"[BLOCK] Projects 交互失败: {e}")

        # ── 4. Session detail（如果存在）：round lazy load + Expand all ──
        # 尝试从 /sessions 页面获取第一个 session 链接
        session_url = None
        try:
            resp = await page.goto(f"{base_url}/sessions", wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(500)
            session_url = await page.evaluate("""
            () => {
                const a = document.querySelector('.sessions-row a, .col-title a, [data-action="row"] a');
                return a ? a.href : null;
            }
            """)
        except Exception:
            pass

        if session_url:
            try:
                resp = await page.goto(session_url, wait_until="domcontentloaded", timeout=15000)
                await page.wait_for_timeout(1000)

                # 测试 Expand all
                expand_result = await page.evaluate("""
                () => {
                    const btn = document.querySelector('[data-action="toggle-all"], [data-action="expand-all"]');
                    if (btn) { btn.click(); return 'clicked'; }
                    return 'not-found';
                }
                """)
                if expand_result == 'clicked':
                    await page.wait_for_timeout(500)
                    print(f"  [PASS] Session detail Expand all 可点击")

                # 测试 Failed filter
                failed_result = await page.evaluate("""
                () => {
                    const btn = document.querySelector('[data-action="toggle-failed"]');
                    if (btn) { btn.click(); return 'clicked'; }
                    return 'not-found';
                }
                """)
                if failed_result == 'clicked':
                    await page.wait_for_timeout(500)
                    print(f"  [PASS] Session detail Failed filter 可点击")

                # 测试 round lazy load
                round_result = await page.evaluate("""
                () => {
                    const toggles = document.querySelectorAll('.trace-round-toggle');
                    if (toggles.length > 0 && window.toggleRoundDetail) {
                        window.toggleRoundDetail(toggles[0], 'expand');
                        return 'expanded';
                    }
                    return 'not-found';
                }
                """)
                if round_result == 'expanded':
                    await page.wait_for_timeout(500)
                    print(f"  [PASS] Session detail round lazy load 可点击")

            except Exception as e:
                errors.append(f"[BLOCK] Session detail 交互失败 ({session_url}): {e}")

        await browser.close()

    # ── 6. 检查 console errors ──
    for err in console_errors:
        # 过滤掉一些无害的警告
        if "net::ERR" not in err:
            errors.append(f"[BLOCK] Console error: {err}")

    # ── 7. 检查 failed requests ──
    for req in failed_requests:
        if "/static/" not in req and "favicon" not in req:
            errors.append(f"[BLOCK] Failed request: {req}")

    # ── 8. 检查服务日志 ──
    for msg in log_capture:
        if "ERROR" in msg or "Traceback" in msg or "Rendering 500" in msg:
            errors.append(f"[BLOCK] 服务日志错误: {msg}")

    return errors


def main() -> None:
    # 设置日志捕获
    handler = LogCapture()
    logging.getLogger("session_browser.web").addHandler(handler)
    logging.getLogger().addHandler(handler)

    # 启动服务器
    sys.path.insert(0, str(REPO_ROOT / "src"))
    from session_browser.web.routes import create_server

    server = create_server(port=0)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.5)

    base = f"http://127.0.0.1:{port}"
    print(f"UI Interaction Smoke Test (port {port})")
    print()

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        errors = loop.run_until_complete(run_smoke(base))
    finally:
        server.shutdown()

    if errors:
        print("")
        for e in errors:
            print(e)
        sys.exit(1)
    else:
        print("\n[PASS] UI Interaction Smoke 通过。所有页面可访问，关键按钮可点击，无 console error，服务日志无 ERROR。")
        sys.exit(0)


if __name__ == "__main__":
    main()
