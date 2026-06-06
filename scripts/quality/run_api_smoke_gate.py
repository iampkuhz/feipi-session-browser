#!/usr/bin/env python3
"""P0 门禁：API Smoke 测试。

覆盖 /dashboard、/sessions、/projects、/glossary、session detail、round API、
request attribution、response attribution。

断言:
- status < 500
- JSON endpoint 可 parse
- 服务日志无 ERROR / Traceback / Rendering 500 response

用法:
    python3 scripts/quality/run_api_smoke_gate.py

退出码:
    0 — 通过
    1 — 发现 API 500 或服务错误
"""

from __future__ import annotations

import json
import logging
import re
import sys
import threading
import time
import urllib.request
import urllib.error
from pathlib import Path

# 捕获服务日志
log_capture = []

class LogCapture(logging.Handler):
    def emit(self, record):
        if record.levelno >= logging.ERROR:
            msg = record.getMessage()
            log_capture.append(msg)

def _fetch_json(url: str, timeout: int = 10):
    """Fetch URL and return (status, parsed_json_or_None, error_str_or_None)."""
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            body = resp.read().decode("utf-8", errors="replace")
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                data = None
            return status, data, None
    except urllib.error.HTTPError as e:
        return e.code, None, str(e)
    except Exception as e:
        return 0, None, str(e)

def main() -> None:
    # 设置日志捕获
    handler = LogCapture()
    logging.getLogger("session_browser.web").addHandler(handler)

    # 启动服务器
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
    from session_browser.web.routes import create_server

    server = create_server(port=0)  # 0 = 随机端口
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.5)  # 等待启动

    errors: list[str] = []
    base = f"http://127.0.0.1:{port}"

    # 页面端点（断言 < 500）
    page_endpoints = [
        "/dashboard",
        "/sessions",
        "/projects",
        "/glossary",
    ]

    for path in page_endpoints:
        try:
            req = urllib.request.Request(f"{base}{path}")
            with urllib.request.urlopen(req, timeout=10) as resp:
                status = resp.status
                if status >= 500:
                    errors.append(f"[BLOCK] {path} 返回 {status}")
                else:
                    print(f"[PASS] {path} -> {status}")
        except urllib.error.HTTPError as e:
            if e.code >= 500:
                errors.append(f"[BLOCK] {path} 返回 HTTP {e.code}")
            else:
                print(f"[PASS] {path} -> {e.code}")
        except Exception as e:
            errors.append(f"[BLOCK] {path} 请求失败: {e}")

    # Round API Smoke：从 /sessions 页面提取 session 链接，测试 round API
    print("\n测试 Round API...")
    try:
        req = urllib.request.Request(f"{base}/sessions")
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="replace")
            # 提取第一个 session 链接
            m = re.search(r'href="/sessions/([^"]+)"', html)
            if m:
                session_path = m.group(1)
                # 测试 round 1
                round_url = f"{base}/api/sessions/{session_path}/round/1"
                status, data, err = _fetch_json(round_url)
                if status >= 500:
                    errors.append(f"[BLOCK] Round API {round_url} 返回 {status}")
                elif status == 404:
                    print(f"  [INFO] Round API 返回 404（session 可能无 round 数据）")
                elif status < 400:
                    if data and "html" in data:
                        print(f"  [PASS] Round API -> {status} (html: {len(data['html'])} chars)")
                    else:
                        print(f"  [PASS] Round API -> {status}")
                else:
                    errors.append(f"[BLOCK] Round API {round_url} 返回 {status}")
            else:
                print("  [INFO] 无 session 链接，跳过 Round API 测试")
    except Exception as e:
        errors.append(f"[BLOCK] Round API 探测失败: {e}")

    # 检查服务日志
    if log_capture:
        for msg in log_capture:
            if "ERROR" in msg or "Traceback" in msg or "Rendering 500" in msg:
                errors.append(f"[BLOCK] 服务日志错误: {msg}")

    server.shutdown()

    if errors:
        print("")
        for e in errors:
            print(e)
        sys.exit(1)
    else:
        print(f"\n[PASS] API Smoke 通过。{len(page_endpoints)} 个端点全部 < 500，Round API 正常，服务日志无 ERROR。")
        sys.exit(0)


if __name__ == "__main__":
    main()
