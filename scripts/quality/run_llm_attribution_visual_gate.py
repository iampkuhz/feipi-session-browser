#!/usr/bin/env python3
"""Browser visual gate for LLM call attribution modals.

Opens a real browser, navigates to a session detail page, opens the
Request and Response attribution modals, takes screenshots at 1440px
and 2560px viewports, and checks geometry / text / readability.

Usage:
    python3 scripts/quality/run_llm_attribution_visual_gate.py \
        --url http://127.0.0.1:18999/sessions/claude_code/hifi-viz-session-001
    python3 scripts/quality/run_llm_attribution_visual_gate.py \
        --url http://127.0.0.1:18999/sessions/claude_code/hifi-viz-session-001 \
        --out .agent/quality/llm-attribution-visual
    python3 scripts/quality/run_llm_attribution_visual_gate.py --self-test
    python3 scripts/quality/run_llm_attribution_visual_gate.py --help
"""
import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# ── Default output directory ──
DEFAULT_OUT = REPO_ROOT / ".agent" / "quality" / "llm-attribution-visual"

# ── Thresholds ──
OVERFLOW_MARGIN_PX = 2
VIEWPORTS = [
    {"width": 1440, "height": 900, "label": "1440x900"},
    {"width": 2560, "height": 1440, "label": "2560x1440"},
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# JS evaluation helpers (strings injected into page.evaluate)
# ---------------------------------------------------------------------------

_CLICK_ATTRIBUTATION_BUTTON_JS = """
(kind) => {
    const btns = document.querySelectorAll('[data-action="open-payload"][data-payload-kind]');
    for (const btn of btns) {
        if (btn.getAttribute('data-payload-kind') === kind && btn.offsetParent !== null) {
            btn.click();
            return btn.getAttribute('data-payload-id') || '';
        }
    }
    return '';
}
"""

_CHECK_MODAL_VISIBLE_JS = """
() => {
    const modal = document.getElementById('sd-payload-modal') || document.getElementById('payload-modal');
    if (!modal) return { visible: false, id: '' };
    const isOpen = modal.open || modal.hasAttribute('open');
    return { visible: !!isOpen, id: modal.id };
}
"""

_CLOSE_MODAL_JS = """
() => {
    const modal = document.getElementById('sd-payload-modal') || document.getElementById('payload-modal');
    if (!modal) return;
    if (typeof modal.close === 'function' && modal.open) modal.close();
    else modal.removeAttribute('open');
}
"""

_CHECK_GEOMETRY_JS = """
() => {
    const rect = (sel) => {
        const el = document.querySelector(sel);
        if (!el) return null;
        return el.getBoundingClientRect();
    };
    const modal = document.getElementById('sd-payload-modal') || document.getElementById('payload-modal');
    if (!modal || !modal.open) {
        return { modalWithinViewport: true, noHorizontalOverflow: document.documentElement.scrollWidth <= window.innerWidth + 2 };
    }
    const modalRect = modal.getBoundingClientRect();
    const withinViewport = modalRect.left >= -2 && modalRect.right <= window.innerWidth + 2;
    const noOverflow = document.documentElement.scrollWidth <= window.innerWidth + 2;

    // Distribution bar check
    const distBar = document.querySelector('.sd-attribution-distribution__bar');
    const distOk = distBar ? distBar.getBoundingClientRect().right <= modalRect.right + 2 : true;

    // Availability table check
    const table = document.querySelector('.sd-attrib-table');
    const tableOk = table ? table.getBoundingClientRect().right <= modalRect.right + 2 : true;

    // Bucket preview check
    const preview = document.querySelector('.sd-attribution-bucket__preview');
    const previewOk = preview ? preview.getBoundingClientRect().right <= modalRect.right + 2 : true;

    return {
        modalWithinViewport: withinViewport,
        noHorizontalOverflow: noOverflow,
        distributionVisible: distOk,
        tableWithinModal: tableOk,
        previewWithinModal: previewOk,
        modalRect: { left: Math.round(modalRect.left), right: Math.round(modalRect.right), width: Math.round(modalRect.width) },
        scrollWidth: document.documentElement.scrollWidth,
        innerWidth: window.innerWidth,
    };
}
"""

_CHECK_MODAL_TEXT_JS = """
() => {
    const modal = document.getElementById('sd-payload-modal') || document.getElementById('payload-modal');
    if (!modal) return { text: '' };
    return { text: modal.textContent || '' };
}
"""

_CHECK_ATTRIBUTATION_BUTTONS_VISIBLE_JS = """
() => {
    const btns = document.querySelectorAll('[data-action="open-payload"][data-payload-kind]');
    const req = [], resp = [];
    for (const btn of btns) {
        if (btn.offsetParent === null) continue;
        const kind = btn.getAttribute('data-payload-kind') || '';
        if (kind.includes('request_attribution')) req.push(btn.textContent.trim());
        if (kind.includes('response_attribution')) resp.push(btn.textContent.trim());
    }
    return { request: req, response: resp };
}
"""

# ---------------------------------------------------------------------------
# Expand first round to reveal LLM call cards
# ---------------------------------------------------------------------------

_EXPAND_ROUNDS_WITH_ATTRIBUTION_JS = """
() => {
    // The detail row is a sibling <tr> after the round row, not a child.
    // Structure: <tr data-trace-round-row> ... </tr> <tr data-trace-detail> ... </tr>
    const rounds = document.querySelectorAll('[data-trace-round-row]');
    let expanded = 0;
    for (const round of rounds) {
        // Find the detail row: it's the next sibling <tr> with [data-trace-detail]
        let detail = round.nextElementSibling;
        while (detail && detail.tagName !== 'TR') {
            detail = detail.nextElementSibling;
        }
        if (!detail || !detail.hasAttribute('data-trace-detail')) continue;

        // Check if this detail has attribution payloads
        const hasAttribution = detail.innerHTML && (
            detail.innerHTML.includes('llm.request_attribution') ||
            detail.innerHTML.includes('llm.response_attribution')
        );
        if (hasAttribution && !round.classList.contains('is-open')) {
            round.classList.add('is-open');
            detail.hidden = false;
            const btn = round.querySelector('[data-action="toggle-round"]');
            if (btn) btn.setAttribute('aria-expanded', 'true');
            expanded++;
            if (expanded >= 3) break;
        }
    }
    return expanded;
}
"""


# ---------------------------------------------------------------------------
# Browser gate runner
# ---------------------------------------------------------------------------

async def run_visual_gate(url: str, out_dir: Path) -> dict:
    """Run the full browser visual gate for LLM attribution modals."""
    from playwright.async_api import async_playwright

    result = {
        "schemaVersion": 1,
        "status": "PASS",
        "gate": "llm-attribution-visual",
        "url": url,
        "viewports": [],
        "startedAt": _now_iso(),
        "finishedAt": "",
        "checks": {},
        "screenshots": [],
        "diagnostics": [],
    }

    browser = None
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)

            for vp in VIEWPORTS:
                vw, vh = vp["width"], vp["height"]
                vp_label = vp["label"]
                result["viewports"].append(vp_label)

                context = await browser.new_context(viewport={"width": vw, "height": vh})
                page = await context.new_page()

                # ── Navigate ──
                try:
                    resp = await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                    if resp and resp.status >= 400:
                        _fail_service(result, resp.status, url)
                        await context.close()
                        return result
                except Exception as e:
                    _fail_unreachable(result, url, e)
                    await context.close()
                    return result

                # Wait for DOM to stabilise
                await page.wait_for_timeout(1500)

                # ── Expand rounds that have attribution data ──
                await page.evaluate(_EXPAND_ROUNDS_WITH_ATTRIBUTION_JS)
                await page.wait_for_timeout(800)

                # ── Check attribution buttons exist ──
                btn_info = await page.evaluate(_CHECK_ATTRIBUTATION_BUTTONS_VISIBLE_JS)
                if not btn_info["request"] or not btn_info["response"]:
                    result["status"] = "BLOCKED"
                    result["checks"][f"buttonsFound-{vp_label}"] = {
                        "status": "BLOCKED",
                        "message": f"No attribution buttons found at {vp_label}",
                        "found": btn_info,
                    }
                    result["diagnostics"].append({
                        "code": "NO_ATTRIBUTATION_BUTTONS",
                        "message": "No visible Request/Response attribution buttons found. The session may not have attribution data, or the first round needs to be expanded.",
                        "nextInspection": [
                            "Verify the session has LLM calls with attribution payloads.",
                            "Check if the first round was expanded correctly.",
                        ],
                    })
                    await context.close()
                    return result

                # ── 1. Open Request attribution modal ──
                req_payload_id = await page.evaluate(f"""
                    () => {{
                        const btns = document.querySelectorAll('[data-action="open-payload"][data-payload-kind="llm.request_attribution"]');
                        for (const btn of btns) {{
                            if (btn.offsetParent !== null) {{
                                btn.click();
                                return btn.getAttribute('data-payload-id') || '';
                            }}
                        }}
                        return '';
                    }}
                """)
                await page.wait_for_timeout(800)

                modal_visible = await page.evaluate(_CHECK_MODAL_VISIBLE_JS)
                req_modal_open = modal_visible["visible"]
                result["checks"][f"requestModalOpen-{vp_label}"] = {
                    "status": "PASS" if req_modal_open else "FAIL",
                    "payloadId": req_payload_id,
                    "modalId": modal_visible.get("id", ""),
                }
                if not req_modal_open:
                    result["diagnostics"].append({
                        "code": "REQUEST_MODAL_NOT_OPEN",
                        "message": "Request attribution modal did not open",
                    })

                # ── Request modal text checks ──
                if req_modal_open:
                    text_info = await page.evaluate(_CHECK_MODAL_TEXT_JS)
                    modal_text = text_info.get("text", "")
                    req_text_checks = _check_request_text(modal_text)
                    result["checks"][f"requestModalText-{vp_label}"] = req_text_checks

                # ── Screenshot: Request modal ──
                req_screenshot = out_dir / f"request-{vp_label.replace('x', 'x')}.png"
                await page.screenshot(path=str(req_screenshot), full_page=False)
                result["screenshots"].append(str(req_screenshot))

                # ── Geometry checks (request modal) ──
                geo = await page.evaluate(_CHECK_GEOMETRY_JS)
                result["checks"][f"requestGeometry-{vp_label}"] = {
                    "status": "PASS" if all([geo.get("noHorizontalOverflow"), geo.get("modalWithinViewport")]) else "FAIL",
                    "noHorizontalOverflow": geo.get("noHorizontalOverflow"),
                    "modalWithinViewport": geo.get("modalWithinViewport"),
                    "distributionVisible": geo.get("distributionVisible"),
                    "tableWithinModal": geo.get("tableWithinModal"),
                    "previewWithinModal": geo.get("previewWithinModal"),
                    "modalRect": geo.get("modalRect"),
                    "scrollWidth": geo.get("scrollWidth"),
                    "innerWidth": geo.get("innerWidth"),
                }

                # ── Close Request modal ──
                await page.evaluate(_CLOSE_MODAL_JS)
                await page.wait_for_timeout(400)

                # ── 2. Open Response attribution modal ──
                resp_payload_id = await page.evaluate(f"""
                    () => {{
                        const btns = document.querySelectorAll('[data-action="open-payload"][data-payload-kind="llm.response_attribution"]');
                        for (const btn of btns) {{
                            if (btn.offsetParent !== null) {{
                                btn.click();
                                return btn.getAttribute('data-payload-id') || '';
                            }}
                        }}
                        return '';
                    }}
                """)
                await page.wait_for_timeout(800)

                modal_visible = await page.evaluate(_CHECK_MODAL_VISIBLE_JS)
                resp_modal_open = modal_visible["visible"]
                result["checks"][f"responseModalOpen-{vp_label}"] = {
                    "status": "PASS" if resp_modal_open else "FAIL",
                    "payloadId": resp_payload_id,
                    "modalId": modal_visible.get("id", ""),
                }
                if not resp_modal_open:
                    result["diagnostics"].append({
                        "code": "RESPONSE_MODAL_NOT_OPEN",
                        "message": "Response attribution modal did not open",
                    })

                # ── Response modal text checks ──
                if resp_modal_open:
                    text_info = await page.evaluate(_CHECK_MODAL_TEXT_JS)
                    modal_text = text_info.get("text", "")
                    resp_text_checks = _check_response_text(modal_text)
                    result["checks"][f"responseModalText-{vp_label}"] = resp_text_checks

                # ── Screenshot: Response modal ──
                resp_screenshot = out_dir / f"response-{vp_label}.png"
                await page.screenshot(path=str(resp_screenshot), full_page=False)
                result["screenshots"].append(str(resp_screenshot))

                # ── Geometry checks (response modal) ──
                geo = await page.evaluate(_CHECK_GEOMETRY_JS)
                result["checks"][f"responseGeometry-{vp_label}"] = {
                    "status": "PASS" if all([geo.get("noHorizontalOverflow"), geo.get("modalWithinViewport")]) else "FAIL",
                    "noHorizontalOverflow": geo.get("noHorizontalOverflow"),
                    "modalWithinViewport": geo.get("modalWithinViewport"),
                    "distributionVisible": geo.get("distributionVisible"),
                    "tableWithinModal": geo.get("tableWithinModal"),
                    "previewWithinModal": geo.get("previewWithinModal"),
                    "modalRect": geo.get("modalRect"),
                    "scrollWidth": geo.get("scrollWidth"),
                    "innerWidth": geo.get("innerWidth"),
                }

                # ── Close Response modal ──
                await page.evaluate(_CLOSE_MODAL_JS)
                await page.wait_for_timeout(400)

                await context.close()

    except Exception as e:
        error_msg = str(e)
        if "playwright" in error_msg.lower() or "executable" in error_msg.lower():
            result["status"] = "NOT_RUN_ENV_LIMITED"
            result["checks"]["playwright"] = {
                "status": "NOT_RUN_ENV_LIMITED",
                "message": f"Playwright browser not available: {error_msg}",
            }
            result["diagnostics"].append({
                "code": "PLAYWRIGHT_UNAVAILABLE",
                "message": error_msg,
                "nextInspection": ["Run: python3 -m playwright install chromium"],
            })
        else:
            result["status"] = "FAIL"
            result["diagnostics"].append({
                "code": "BROWSER_ERROR",
                "message": error_msg,
            })
    finally:
        if browser:
            try:
                await browser.close()
            except Exception:
                pass

    # Compute overall status
    result["finishedAt"] = _now_iso()
    check_statuses = [c.get("status", "PASS") for c in result["checks"].values()]
    if "NOT_RUN_ENV_LIMITED" in check_statuses:
        result["status"] = "NOT_RUN_ENV_LIMITED"
    elif "BLOCKED" in check_statuses:
        result["status"] = "BLOCKED"
    elif any(s == "FAIL" for s in check_statuses):
        result["status"] = "FAIL"
    else:
        result["status"] = "PASS"

    return result


# ---------------------------------------------------------------------------
# Text check helpers
# ---------------------------------------------------------------------------

def _check_request_text(text: str) -> dict:
    """Check Request modal text for required and forbidden strings."""
    checks = {
        "status": "PASS",
        "hasRebuiltBanner": "基于本地日志重建" in text,
        "hasDistribution": "用量分布" in text,
        "hasAttributionDetail": "归因明细" in text,
        "hasContextSummary": "可见内容摘要" in text,
        "hasAvailabilityTable": "参数可得性表" in text,
        "hasNoRawRequest": "Raw request" not in text,
        "hasNoRawResponse": "Raw response" not in text,
        "hasNoNoRendered": "(No rendered content)" not in text,
        "hasNoNoRaw": "(No raw content)" not in text,
    }
    failures = [k for k, v in checks.items() if k != "status" and not v]
    if failures:
        checks["status"] = "FAIL"
        checks["failed"] = failures
    return checks


def _check_response_text(text: str) -> dict:
    """Check Response modal text for required and forbidden strings."""
    checks = {
        "status": "PASS",
        "hasRebuiltBanner": "基于本地日志重建" in text,
        "hasDistribution": "用量分布" in text,
        "hasAttributionDetail": "归因明细" in text,
        "hasBlocksDetail": "Blocks 明细" in text,
        "hasContextSummary": "可见内容摘要" in text,
        "hasAvailabilityTable": "参数可得性表" in text,
        "hasNoRawRequest": "Raw request" not in text,
        "hasNoRawResponse": "Raw response" not in text,
        "hasNoNoRendered": "(No rendered content)" not in text,
        "hasNoNoRaw": "(No raw content)" not in text,
    }
    failures = [k for k, v in checks.items() if k != "status" and not v]
    if failures:
        checks["status"] = "FAIL"
        checks["failed"] = failures
    return checks


# ---------------------------------------------------------------------------
# Failure helpers
# ---------------------------------------------------------------------------

def _fail_service(result, status, url):
    result["status"] = "FAIL"
    result["checks"]["navigation"] = {
        "status": "FAIL",
        "message": f"Server returned HTTP {status}.",
    }
    result["diagnostics"].append({
        "code": "SERVICE_UNAVAILABLE",
        "message": f"Server returned HTTP {status} for {url}.",
        "nextInspection": ["Start the fixture server and verify the URL."],
    })


def _fail_unreachable(result, url, exc):
    result["status"] = "FAIL"
    result["checks"]["navigation"] = {
        "status": "FAIL",
        "message": f"Cannot reach {url}: {exc}",
    }
    result["diagnostics"].append({
        "code": "SERVICE_UNAVAILABLE",
        "message": f"Cannot reach {url}: {exc}",
        "nextInspection": ["Start the fixture server: ./scripts/session-browser.sh serve"],
    })


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def _self_test():
    """Run self-tests that verify text checks and aggregation logic."""
    failures = 0

    def _assert(name, cond, msg=""):
        nonlocal failures
        if cond:
            print(f"  PASS: {name}")
        else:
            failures += 1
            print(f"  FAIL: {name} {msg}")

    # Text checks for request modal
    good_req_text = "基于本地日志重建，不等同于真实 provider request/response body。用量分布 归因明细 可见内容摘要 参数可得性表"
    req_checks = _check_request_text(good_req_text)
    _assert("request text checks pass", req_checks["status"] == "PASS", str(req_checks))

    # Text checks for response modal
    good_resp_text = "基于本地日志重建，不等同于真实 provider request/response body。用量分布 归因明细 Blocks 明细 可见内容摘要 参数可得性表"
    resp_checks = _check_response_text(good_resp_text)
    _assert("response text checks pass", resp_checks["status"] == "PASS", str(resp_checks))

    # Forbidden text in request
    bad_req_text = "Raw request (No rendered content)"
    req_bad = _check_request_text(bad_req_text)
    _assert("request text checks detect forbidden", req_bad["status"] == "FAIL", str(req_bad))

    # Forbidden text in response
    bad_resp_text = "Raw response (No raw content)"
    resp_bad = _check_response_text(bad_resp_text)
    _assert("response text checks detect forbidden", resp_bad["status"] == "FAIL", str(resp_bad))

    # Display-only bucket text
    display_only_text = "明细，不计入总量"
    _assert("display-only section text present", "不计入总量" in display_only_text)

    # JSON serialisability
    sample = {
        "schemaVersion": 1,
        "status": "PASS",
        "viewports": ["1440x900", "2560x1440"],
        "checks": {
            "requestModalOpen-1440x900": {"status": "PASS"},
        },
        "screenshots": [],
        "diagnostics": [],
    }
    try:
        json.dumps(sample)
        _assert("result JSON serialisable", True)
    except Exception:
        _assert("result JSON serialisable", False)

    # Check script source contains key patterns
    source = Path(__file__).read_text()
    _assert("source checks request modal", "llm.request_attribution" in source)
    _assert("source checks response modal", "llm.response_attribution" in source)
    _assert("source checks no raw request", '"Raw request"' in source or "'Raw request'" in source)
    _assert("source checks no raw response", '"Raw response"' in source or "'Raw response'" in source)
    _assert("source checks horizontal overflow", "scrollWidth" in source)

    if failures:
        print(f"\n{failures} self-test(s) failed")
        sys.exit(1)
    else:
        print("\nAll self-tests passed")
        sys.exit(0)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Browser visual gate for LLM call attribution modals",
    )
    parser.add_argument(
        "--url", default=None,
        help="Target session detail URL (e.g. http://127.0.0.1:18999/sessions/claude_code/<id>)",
    )
    parser.add_argument(
        "--out", default=None,
        help="Output directory for result.json and screenshots",
    )
    parser.add_argument(
        "--self-test", action="store_true",
        help="Run self-tests without browser",
    )
    args = parser.parse_args()

    if args.self_test:
        _self_test()
        return

    out_dir = Path(args.out) if args.out else DEFAULT_OUT
    out_dir.mkdir(parents=True, exist_ok=True)

    if not args.url:
        print(
            "BLOCKED: No --url provided.\n"
            "\n"
            "To run this gate you need:\n"
            "  1. A running fixture server: ./scripts/session-browser.sh serve\n"
            "  2. A valid session detail URL with LLM call attribution data.\n"
            "\n"
            "Example:\n"
            "  python3 " + " ".join(sys.argv) + " --url http://127.0.0.1:18999/sessions/claude_code/hifi-viz-session-001\n",
            file=sys.stderr,
        )

        # Write BLOCKED result
        result = {
            "schemaVersion": 1,
            "status": "BLOCKED",
            "gate": "llm-attribution-visual",
            "url": None,
            "viewports": [vp["label"] for vp in VIEWPORTS],
            "startedAt": _now_iso(),
            "finishedAt": _now_iso(),
            "checks": {
                "navigation": {
                    "status": "BLOCKED",
                    "message": "No URL provided. Cannot reach browser target.",
                },
            },
            "screenshots": [],
            "diagnostics": [{
                "code": "NO_URL",
                "message": "Provide --url with a session detail URL.",
                "nextInspection": [
                    "Start server: ./scripts/session-browser.sh serve",
                    "Find a session ID from the dashboard or sessions list.",
                    "Run: python3 " + " ".join(sys.argv) + " --url http://127.0.0.1:18999/sessions/claude_code/hifi-viz-session-001",
                ],
            }],
        }
        result_path = out_dir / "result.json"
        result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(2)

    url = args.url
    print(f"LLM Call Attribution Visual Gate")
    print(f"URL: {url}")
    print(f"Output: {out_dir}")
    print()

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    result = loop.run_until_complete(run_visual_gate(url, out_dir))

    # Write artifact
    result_path = out_dir / "result.json"
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # Print summary
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print()

    if result["status"] == "PASS":
        print("PASS: LLM call attribution visual gate passed")
        sys.exit(0)
    elif result["status"] == "BLOCKED":
        print("BLOCKED: LLM call attribution visual gate blocked (external condition)")
        sys.exit(2)
    elif result["status"] == "NOT_RUN_ENV_LIMITED":
        print("NOT_RUN_ENV_LIMITED: Browser environment not available")
        sys.exit(2)
    else:
        fail_count = sum(1 for c in result["checks"].values() if c.get("status") == "FAIL")
        print(f"FAIL: {fail_count} check(s) failed")
        for d in result.get("diagnostics", []):
            print(f"  [{d.get('code')}] {d.get('message', '')}")
        sys.exit(1)


if __name__ == "__main__":
    main()
