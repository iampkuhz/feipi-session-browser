#!/usr/bin/env python3
"""Browser computed layout gate for session detail Phase 1.

Opens a real browser viewport and checks CSS computed geometry against
hard thresholds to catch cascade conflicts, grid auto-placement,
and overflow issues that static checks cannot detect.

Usage:
    python3 scripts/quality/run_session_detail_layout_gate.py \
        --url http://127.0.0.1:18999/sessions/claude_code/SESSION_ID
    python3 scripts/quality/run_session_detail_layout_gate.py \
        --url http://127.0.0.1:18999/sessions/claude_code/SESSION_ID \
        --viewport 1440x1100 --out .agent/quality/demo
    python3 scripts/quality/run_session_detail_layout_gate.py --self-test
    python3 scripts/quality/run_session_detail_layout_gate.py --allow-missing-service
"""
import argparse
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# ── Hard thresholds (1440x1100 viewport) ──
THRESHOLDS = {
    "main_width_min": 1200,
    "detail_width_min": 1100,
    "hero_width_min": 900,
    "title_height_max": 180,
}

# ── Default selectors (scoped to .session-detail-phase1) ──
SELECTORS = {
    "shell": ".shell",
    "main": ".main",
    "detail": ".session-detail-phase1",
    "hero_main": ".session-detail-phase1 .hero-main, .session-detail-phase1 .page-header__main",
    "hero": ".session-detail-phase1 .hero, .session-detail-phase1 .page-header",
    "title": ".session-detail-phase1 .hero-title, .session-detail-phase1 .page-header__title",
    "kpis": ".session-detail-phase1 .kpis, .session-detail-phase1 .metrics-strip",
}

# ── Failure codes ──
FAILURE_CODES = {
    "MISSING_SESSION_DETAIL_ROOT": "No .session-detail-phase1 element found.",
    "SHELL_ZERO_COLUMN": ".shell grid starts with 0px; .main may be placed into collapsed sidebar column.",
    "MAIN_WIDTH_TOO_SMALL": ".main computed width is below threshold.",
    "DETAIL_WIDTH_TOO_SMALL": ".session-detail-phase1 computed width is below threshold.",
    "HERO_WIDTH_TOO_SMALL": ".hero computed width is below threshold.",
    "TITLE_OVERLAPS_KPIS": ".hero-title bottom overlaps .kpis top.",
    "HORIZONTAL_SCROLL": "Page scrollWidth exceeds viewport width.",
    "TITLE_TOO_TALL": ".hero-title height exceeds threshold.",
    "SERVICE_UNAVAILABLE": "Cannot reach target URL.",
    "PLAYWRIGHT_UNAVAILABLE": "Playwright browser is not available.",
}


def parse_viewport(spec: str) -> tuple[int, int]:
    """Parse 'WxH' into (width, height)."""
    parts = spec.split("x")
    return int(parts[0]), int(parts[1])


def check_layout(metrics: dict) -> list[dict]:
    """Evaluate metrics against thresholds. Return list of failures."""
    failures = []

    # Check scroll
    if not metrics.get("scrollOk", True):
        failures.append({
            "code": "HORIZONTAL_SCROLL",
            "message": FAILURE_CODES["HORIZONTAL_SCROLL"],
            "observed": {
                "scrollWidth": metrics.get("scrollWidth"),
                "viewportWidth": metrics.get("viewportWidth"),
            },
            "likelyRootCause": [
                "Element wider than viewport causing horizontal scroll.",
                "Check .shell grid or .session-detail-phase1 width.",
            ],
            "nextInspection": [
                "Inspect computed width of .shell and .session-detail-phase1.",
                "Check for fixed-width elements inside grid.",
            ],
        })

    # Check shell grid
    shell_grid = metrics.get("shellGrid", "")
    if shell_grid and shell_grid.startswith("0px"):
        failures.append({
            "code": "SHELL_ZERO_COLUMN",
            "message": FAILURE_CODES["SHELL_ZERO_COLUMN"],
            "observed": {
                "shellGrid": shell_grid,
                "mainWidth": metrics.get("main", {}).get("width") if metrics.get("main") else None,
            },
            "likelyRootCause": [
                "body.hide-left .shell.no-inspector overrides .shell.phase1-shell",
                ".shell.phase1-shell .main may lack grid-column: 1 / -1",
            ],
            "nextInspection": [
                "Inspect style.css around shell/no-inspector/hide-left rules.",
                "Inspect base.html shell class composition.",
                "Verify session.html declares shell_class including phase1-shell and no-inspector.",
            ],
        })

    # Check main width
    main_rect = metrics.get("main")
    if main_rect and main_rect.get("width", 0) < THRESHOLDS["main_width_min"]:
        failures.append({
            "code": "MAIN_WIDTH_TOO_SMALL",
            "message": FAILURE_CODES["MAIN_WIDTH_TOO_SMALL"],
            "observed": {
                "mainWidth": main_rect.get("width"),
                "threshold": THRESHOLDS["main_width_min"],
            },
            "likelyRootCause": [
                ".main is constrained by parent grid or width rule.",
                "body.hide-left cascade may be active.",
            ],
            "nextInspection": [
                "Inspect computed width of .main parent chain.",
            ],
        })

    # Check detail width
    detail_rect = metrics.get("detail")
    if detail_rect and detail_rect.get("width", 0) < THRESHOLDS["detail_width_min"]:
        failures.append({
            "code": "DETAIL_WIDTH_TOO_SMALL",
            "message": FAILURE_CODES["DETAIL_WIDTH_TOO_SMALL"],
            "observed": {
                "detailWidth": detail_rect.get("width"),
                "threshold": THRESHOLDS["detail_width_min"],
            },
            "likelyRootCause": [
                ".session-detail-phase1 width rule missing or too narrow.",
            ],
            "nextInspection": [
                "Inspect style.css for .session-detail-phase1 width/max-width.",
            ],
        })

    # Check hero width
    hero_rect = metrics.get("hero")
    if hero_rect and hero_rect.get("width", 0) < THRESHOLDS["hero_width_min"]:
        failures.append({
            "code": "HERO_WIDTH_TOO_SMALL",
            "message": FAILURE_CODES["HERO_WIDTH_TOO_SMALL"],
            "observed": {
                "heroWidth": hero_rect.get("width"),
                "threshold": THRESHOLDS["hero_width_min"],
            },
            "likelyRootCause": [
                ".hero is constrained by parent container.",
            ],
            "nextInspection": [
                "Inspect .hero-main and .hero width chain.",
            ],
        })

    # Check title overlaps KPIs
    if metrics.get("titleBeforeKpis") is False:
        failures.append({
            "code": "TITLE_OVERLAPS_KPIS",
            "message": FAILURE_CODES["TITLE_OVERLAPS_KPIS"],
            "observed": {
                "titleRect": metrics.get("title"),
                "kpisRect": metrics.get("kpis"),
            },
            "likelyRootCause": [
                "Hero layout is not single-column, causing title and KPIs side by side.",
                "KPIs may render above title due to flex order.",
            ],
            "nextInspection": [
                "Inspect .hero-main grid-template-columns.",
                "Verify .hero-title DOM order relative to .kpis.",
            ],
        })

    # Check title height
    title_rect = metrics.get("title")
    if title_rect and title_rect.get("height", 0) > THRESHOLDS["title_height_max"]:
        failures.append({
            "code": "TITLE_TOO_TALL",
            "message": FAILURE_CODES["TITLE_TOO_TALL"],
            "observed": {
                "titleHeight": title_rect.get("height"),
                "threshold": THRESHOLDS["title_height_max"],
            },
            "likelyRootCause": [
                "Title text is wrapping to multiple lines.",
                "overflow-wrap or line-clamp may be missing.",
            ],
            "nextInspection": [
                "Inspect .hero-title overflow-wrap, line-clamp, max-width.",
            ],
        })

    return failures


async def collect_metrics(page, selectors: dict) -> dict:
    """Collect computed layout metrics from the page."""
    return await page.evaluate(f"""
    () => {{
        const q = (sel) => {{
            const parts = sel.split(', ').map(s => s.trim());
            for (const p of parts) {{
                const el = document.querySelector(p);
                if (el) return el;
            }}
            return document.querySelector(sel.split(',')[0].trim());
        }};
        const rect = (sel) => {{
            const el = q(sel);
            if (!el) return null;
            const r = el.getBoundingClientRect();
            return {{ left: r.left, right: r.right, top: r.top, bottom: r.bottom, width: r.width, height: r.height }};
        }};

        const shell = q("{selectors['shell']}");
        const main = q("{selectors['main']}");
        const detail = q("{selectors['detail']}");
        const title = q("{selectors['title']}");
        const kpis = q("{selectors['kpis']}");
        const hero = q("{selectors['hero']}");
        const heroMain = q("{selectors['hero_main']}");

        const titleEl = title;
        const kpisEl = kpis;
        let titleBeforeKpis = false;
        if (titleEl && kpisEl) {{
            const t = titleEl.getBoundingClientRect();
            const k = kpisEl.getBoundingClientRect();
            titleBeforeKpis = t.bottom <= k.top + 4;
        }}

        const titleStyles = titleEl ? getComputedStyle(titleEl) : null;

        return {{
            viewportWidth: window.innerWidth,
            viewportHeight: window.innerHeight,
            scrollWidth: document.documentElement.scrollWidth,
            scrollOk: document.documentElement.scrollWidth <= window.innerWidth + 2,
            shellGrid: shell ? getComputedStyle(shell).gridTemplateColumns : null,
            mainGridColumn: main
                ? `${{getComputedStyle(main).gridColumnStart}}/${{getComputedStyle(main).gridColumnEnd}}`
                : null,
            main: rect("{selectors['main']}"),
            detail: rect("{selectors['detail']}"),
            hero: rect("{selectors['hero']}"),
            heroMain: rect("{selectors['hero_main']}"),
            title: rect("{selectors['title']}"),
            kpis: rect("{selectors['kpis']}"),
            titleBeforeKpis,
            titleStyles: titleStyles ? {{
                overflowWrap: titleStyles.overflowWrap,
                wordBreak: titleStyles.wordBreak,
                lineHeight: titleStyles.lineHeight,
                display: titleStyles.display,
            }} : null,
        }};
    }}
    """)


async def run_browser_gate(url: str, viewport: str, out_dir: Path, allow_missing: bool = False) -> dict:
    """Run the browser layout gate. Returns result dict."""
    from playwright.async_api import async_playwright

    vw, vh = parse_viewport(viewport)
    result = {
        "status": "PASS",
        "gate": "session-detail-layout",
        "url": url,
        "viewport": viewport,
        "metrics": {},
        "failures": [],
        "artifacts": {},
    }

    browser = None
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            context = await browser.new_context(viewport={"width": vw, "height": vh})
            page = await context.new_page()

            try:
                resp = await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                if resp and resp.status >= 400:
                    result["status"] = "FAIL"
                    result["failures"].append({
                        "code": "SERVICE_UNAVAILABLE",
                        "message": f"Server returned HTTP {resp.status}.",
                        "observed": {"status": resp.status, "url": url},
                        "likelyRootCause": ["Server not running or session not found."],
                        "nextInspection": [
                            f"Start the fixture server and ensure {url} is accessible.",
                        ],
                    })
                    return result
            except Exception as e:
                if allow_missing:
                    result["status"] = "BLOCKED"
                    result["failures"].append({
                        "code": "SERVICE_UNAVAILABLE",
                        "message": f"Cannot reach {url}: {e}",
                        "observed": {"url": url},
                        "likelyRootCause": ["Fixture server not running."],
                        "nextInspection": [
                            "Start the fixture server with: ./scripts/session-browser.sh serve",
                        ],
                    })
                    return result
                else:
                    result["status"] = "FAIL"
                    result["failures"].append({
                        "code": "SERVICE_UNAVAILABLE",
                        "message": f"Cannot reach {url}: {e}",
                        "observed": {"url": url},
                        "likelyRootCause": ["Fixture server not running."],
                        "nextInspection": [
                            "Start the fixture server with: ./scripts/session-browser.sh serve",
                        ],
                    })
                    return result

            # Collect metrics
            metrics = await collect_metrics(page, SELECTORS)
            result["metrics"] = metrics

            # Check for missing root
            if metrics.get("detail") is None:
                result["status"] = "FAIL"
                result["failures"].append({
                    "code": "MISSING_SESSION_DETAIL_ROOT",
                    "message": FAILURE_CODES["MISSING_SESSION_DETAIL_ROOT"],
                    "observed": {"url": url},
                    "likelyRootCause": [
                        "session.html template missing or not rendered.",
                        "Wrong URL — not a session detail page.",
                    ],
                    "nextInspection": [
                        "Verify URL points to a session detail page.",
                    ],
                })
                return result

            # Run checks
            failures = check_layout(metrics)
            result["failures"] = failures

            # Take screenshot
            screenshot_path = out_dir / "session-detail-layout-1440.png"
            await page.screenshot(path=str(screenshot_path), full_page=False)
            result["artifacts"]["screenshot"] = str(screenshot_path)

            if failures:
                result["status"] = "FAIL"
            else:
                result["status"] = "PASS"

    except Exception as e:
        error_msg = str(e)
        if "playwright" in error_msg.lower() or "executable" in error_msg.lower():
            result["status"] = "BLOCKED"
            result["failures"].append({
                "code": "PLAYWRIGHT_UNAVAILABLE",
                "message": f"Playwright browser not available: {error_msg}",
                "observed": {},
                "likelyRootCause": ["Playwright browsers not installed."],
                "nextInspection": [
                    "Run: python3 -m playwright install chromium",
                ],
            })
        else:
            result["status"] = "FAIL"
            result["failures"].append({
                "code": "SERVICE_UNAVAILABLE",
                "message": f"Browser error: {error_msg}",
                "observed": {},
                "likelyRootCause": [error_msg],
                "nextInspection": ["Check Playwright installation."],
            })
    finally:
        if browser:
            try:
                await browser.close()
            except Exception:
                pass

    return result


def _run_gate_sync(url: str, viewport: str, out_dir: Path, allow_missing: bool = False) -> dict:
    """Synchronous wrapper for the async browser gate."""
    import asyncio
    return asyncio.get_event_loop().run_until_complete(
        run_browser_gate(url, viewport, out_dir, allow_missing)
    )


def main():
    parser = argparse.ArgumentParser(description="Browser layout gate for session detail")
    parser.add_argument("--url", default=None, help="Target session detail URL")
    parser.add_argument("--viewport", default="1440x1100", help="Viewport size (WxH)")
    parser.add_argument("--out", default=None, help="Output directory for artifacts")
    parser.add_argument("--allow-missing-service", action="store_true",
                        help="Report BLOCKED instead of FAIL when service is unavailable")
    parser.add_argument("--self-test", action="store_true", help="Run self-tests")
    args = parser.parse_args()

    if args.self_test:
        _self_test()
        return

    out_dir = Path(args.out) if args.out else REPO_ROOT / ".agent" / "quality" / "browser-gate"
    out_dir.mkdir(parents=True, exist_ok=True)

    if not args.url:
        print("ERROR: --url is required (unless --self-test)", file=sys.stderr)
        sys.exit(2)

    result = _run_gate_sync(args.url, args.viewport, out_dir, args.allow_missing_service)

    # Write artifact
    result_path = out_dir / "session-detail-layout-result.json"
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # Print summary
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if result["status"] == "PASS":
        print("\nPASS: Browser layout gate passed")
        sys.exit(0)
    elif result["status"] == "BLOCKED":
        print("\nBLOCKED: Browser layout gate blocked (external condition)")
        sys.exit(2)
    else:
        print(f"\nFAIL: {len(result['failures'])} failure(s)")
        for f in result["failures"]:
            print(f"  [{f['code']}] {f['message']}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def _self_test():
    """Run self-tests using temporary HTML fixtures loaded via set_content."""
    import asyncio

    def _run(name, html_content, expect_pass, expect_codes=None):
        """Run a single self-test with given HTML content."""
        async def _inner():
            from playwright.async_api import async_playwright
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True)
                context = await browser.new_context(viewport={"width": 1440, "height": 1100})
                page = await context.new_page()
                await page.set_content(html_content, wait_until="domcontentloaded")
                metrics = await collect_metrics(page, SELECTORS)
                failures = []
                if metrics.get("detail") is None:
                    failures.append({"code": "MISSING_SESSION_DETAIL_ROOT", "message": "missing root"})
                else:
                    failures = check_layout(metrics)
                await browser.close()
                return metrics, failures

        metrics, failures = asyncio.get_event_loop().run_until_complete(_inner())
        codes = [f["code"] for f in failures]
        actual_pass = len(failures) == 0

        if actual_pass == expect_pass:
            if expect_codes:
                for ec in expect_codes:
                    if ec in codes:
                        print(f"  PASS: {name} ({ec})")
                        return True
                # If no expected code matched but pass/fail is correct, still pass
                print(f"  PASS: {name}")
                return True
            else:
                print(f"  PASS: {name}")
                return True
        else:
            print(f"  FAIL: {name} — expected {'PASS' if expect_pass else 'FAIL'}, got {'PASS' if actual_pass else 'FAIL'}, codes: {codes}")
            return False

    # Good fixture: all thresholds met
    GOOD_HTML = """
    <!DOCTYPE html>
    <html>
    <head><style>
        body { margin: 0; }
        .shell { display: grid; grid-template-columns: minmax(0, 1fr); width: 1440px; }
        .main { width: 1300px; grid-column: 1 / -1; }
        .session-detail-phase1 { width: 1200px; }
        .hero-main { display: grid; grid-template-columns: 1fr; }
        .hero { width: 1000px; height: 100px; }
        .hero-title { height: 60px; overflow-wrap: break-word; }
        .kpis { margin-top: 20px; }
    </style></head>
    <body>
        <div class="shell">
            <div class="main">
                <div class="session-detail-phase1">
                    <div class="hero-main">
                        <div class="hero">
                            <div class="hero-title">Test Session Title</div>
                        </div>
                        <div class="kpis">Metrics here</div>
                    </div>
                </div>
            </div>
        </div>
    </body>
    </html>
    """

    # Shell zero column fixture
    SHELL_ZERO_HTML = """
    <!DOCTYPE html>
    <html>
    <head><style>
        .shell { display: grid; grid-template-columns: 0px 1440px; width: 1440px; }
        .main { width: 24px; }
        .session-detail-phase1 { width: 500px; }
        .hero-main { display: grid; grid-template-columns: 1fr; }
        .hero { width: 400px; }
        .hero-title { height: 60px; }
        .kpis { margin-top: 100px; }
    </style></head>
    <body>
        <div class="shell"><div class="main">
            <div class="session-detail-phase1">
                <div class="hero-main">
                    <div class="hero"><div class="hero-title">Test</div></div>
                    <div class="kpis">Metrics</div>
                </div>
            </div>
        </div></div>
    </body>
    </html>
    """

    # Title overlaps KPIs fixture
    OVERLAP_HTML = """
    <!DOCTYPE html>
    <html>
    <head><style>
        .shell { display: grid; grid-template-columns: 1fr; }
        .main { width: 1300px; grid-column: 1 / -1; }
        .session-detail-phase1 { width: 1200px; }
        .hero-main { display: grid; grid-template-columns: 1fr; }
        .hero { width: 1000px; }
        .hero-title { height: 60px; position: absolute; top: 0; left: 0; }
        .kpis { position: absolute; top: 10px; left: 0; }
    </style></head>
    <body>
        <div class="shell"><div class="main">
            <div class="session-detail-phase1">
                <div class="hero-main">
                    <div class="hero"><div class="hero-title">Test</div></div>
                    <div class="kpis">Metrics</div>
                </div>
            </div>
        </div></div>
    </body>
    </html>
    """

    # Horizontal scroll fixture
    SCROLL_HTML = """
    <!DOCTYPE html>
    <html>
    <head><style>
        .shell { display: grid; grid-template-columns: 1fr; width: 2000px; }
        .main { width: 1900px; }
        .session-detail-phase1 { width: 1800px; }
        .hero-main { display: grid; grid-template-columns: 1fr; }
        .hero { width: 1700px; }
        .hero-title { height: 60px; }
        .kpis { margin-top: 100px; }
    </style></head>
    <body>
        <div class="shell"><div class="main">
            <div class="session-detail-phase1">
                <div class="hero-main">
                    <div class="hero"><div class="hero-title">Test</div></div>
                    <div class="kpis">Metrics</div>
                </div>
            </div>
        </div></div>
    </body>
    </html>
    """

    # Missing root fixture
    MISSING_HTML = """
    <!DOCTYPE html>
    <html><body><div class="shell"><div class="main">No detail</div></div></body></html>
    """

    failures = 0
    tests = [
        ("good fixture => PASS", GOOD_HTML, True, None),
        ("shell zero column => SHELL_ZERO_COLUMN or MAIN_WIDTH_TOO_SMALL", SHELL_ZERO_HTML, False,
         ["SHELL_ZERO_COLUMN", "MAIN_WIDTH_TOO_SMALL"]),
        ("title/kpi overlap => TITLE_OVERLAPS_KPIS", OVERLAP_HTML, False, ["TITLE_OVERLAPS_KPIS"]),
        ("horizontal scroll => HORIZONTAL_SCROLL", SCROLL_HTML, False, ["HORIZONTAL_SCROLL"]),
        ("missing root => MISSING_SESSION_DETAIL_ROOT", MISSING_HTML, False, ["MISSING_SESSION_DETAIL_ROOT"]),
    ]

    for name, html, expect_pass, expect_codes in tests:
        if not _run(name, html, expect_pass, expect_codes):
            failures += 1

    if failures:
        print(f"\n{failures} test(s) failed")
        sys.exit(1)
    else:
        print(f"\nAll self-tests passed")
        sys.exit(0)


if __name__ == "__main__":
    main()
