#!/usr/bin/env python3
"""提供 run session detail interaction gate 脚本能力。

不负责修复被检查对象；由 Gate executor 或维护者命令行调用。"""

import argparse
import asyncio
import contextlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# 默认 输出 目录。
DEFAULT_OUT = REPO_ROOT / 'tmp' / 'quality' / 'session-detail-interaction-gate'

TOGGLE_SPREGRESSION_PX = 2  # 交互后相对 baseline 允许增加的最大像素
TOGGLE_SPREAD_ABSOLUTE_MAX = 20  # 绝对上限，baseline 也不得超过
OVERFLOW_MARGIN_PX = 2  # 滚动宽度不得超过可视宽度与容差之和
HTTP_ERROR_MIN = 400
SECOND_VISIBLE_ROUND_MIN = 2
EIGHTH_VISIBLE_ROUND_MIN = 8
TWENTY_FOURTH_VISIBLE_ROUND_MIN = 24
EXPECTED_TOGGLE_COUNT = 3


# 维护当前 ISO timestamp。
def _now_iso() -> str:
    """返回：
    ISO-like UTC timestamp带seconds precision用于JSON 结果 fields。
    """
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

_CHECK_TOGGLE_ALIGNMENT_JS = """
() => {
    const els = [...document.querySelectorAll('.trace-round-toggle')];
    const xs = els.slice(0, 50).map(el => Math.round(el.getBoundingClientRect().left));
    if (xs.length === 0) return { count: 0, spread: 0, min: 0, max: 0 };
    return {
        count: xs.length,
        spread: Math.max(...xs) - Math.min(...xs),
        min: Math.min(...xs),
        max: Math.max(...xs),
    };
}
"""

_CHECK_VISIBLE_TOGGLE_ALIGNMENT_JS = """
() => {
    const rows = [...document.querySelectorAll('.trace-row')];
    const visible = rows.filter(r => !r.classList.contains('is-filtered-out'));
    const els = visible.map(r => r.querySelector('.trace-round-toggle')).filter(Boolean);
    const xs = els.slice(0, 50).map(el => Math.round(el.getBoundingClientRect().left));
    if (xs.length === 0) return { count: 0, spread: 0, min: 0, max: 0 };
    return {
        count: xs.length,
        spread: Math.max(...xs) - Math.min(...xs),
        min: Math.min(...xs),
        max: Math.max(...xs),
    };
}
"""

_CHECK_OVERFLOW_JS = """
() => ({
    scrollWidth: document.documentElement.scrollWidth,
    innerWidth: window.innerWidth,
    ok: document.documentElement.scrollWidth <= window.innerWidth + 2,
})
"""

_CHECK_MODAL_RENDERED_JS = """
() => {
    const rendered = document.querySelector('.payload-modal__rendered');
    if (!rendered) return { found: false, text: '', length: 0 };
    const text = rendered.textContent || '';
    const noRendered = text.trim() === '(No rendered content)';
    return {
        found: true,
        text: text.substring(0, 200),
        length: text.trim().length,
        isEmpty: text.trim().length === 0,
        isNoRenderedContent: noRendered,
    };
}
"""


# 运行interaction gate。
async def run_interaction_gate(url: str, out_dir: Path) -> dict:  # noqa: PLR0912, PLR0915
    """参数：
        url: 待请求的 URL。
        out_dir: 目录 在 screenshots 和 结果 artifacts are written。

    返回：
        结构化 结果 dict带PASS, FAIL, 或 BLOCKED 状态 plus 检查,。 诊断信息, 和 artifact 路径。
    """
    from playwright.async_api import async_playwright  # noqa: PLC0415

    result = {
        'schemaVersion': 1,
        'status': 'PASS',
        'gate': 'session-detail-interaction',
        'url': url,
        'startedAt': _now_iso(),
        'finishedAt': '',
        'checks': {},
        'artifacts': {},
        'diagnostics': [],
    }

    browser = None
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            context = await browser.new_context(viewport={'width': 1440, 'height': 1100})
            page = await context.new_page()

            try:
                resp = await page.goto(url, wait_until='domcontentloaded', timeout=20000)
                if resp and resp.status >= HTTP_ERROR_MIN:
                    _fail_service(result, resp.status, url)
                    return result
            except Exception as e:
                _fail_unreachable(result, url, e)
                return result

            # 等待 DOM 稳定，期间允许自动展开完成。
            await page.wait_for_timeout(1000)

            await _reset_filter_to_all(page)
            await page.wait_for_timeout(300)

            toggle_data = await page.evaluate(_CHECK_TOGGLE_ALIGNMENT_JS)
            baseline_spread = toggle_data['spread']
            initial_abs_ok = baseline_spread <= TOGGLE_SPREAD_ABSOLUTE_MAX
            result['checks']['initialToggleAlignment'] = {
                'status': 'PASS' if initial_abs_ok else 'FAIL',
                'spreadPx': toggle_data['spread'],
                'baselinePx': baseline_spread,
                'count': toggle_data['count'],
                'minLeft': toggle_data['min'],
                'maxLeft': toggle_data['max'],
                'note': 'Baseline spread recorded; subsequent checks measure regression.',
            }
            if not initial_abs_ok:
                result['diagnostics'].append(
                    {
                        'code': 'TRACE_TOGGLE_MISALIGN_INITIAL',
                        'observedSpreadPx': toggle_data['spread'],
                        'absoluteMaxPx': TOGGLE_SPREAD_ABSOLUTE_MAX,
                        'likelyRootCause': [
                            'trace-row is not a proper grid/flex row',
                            'toggle cell not fixed width',
                        ],
                    }
                )

            before_path = out_dir / 'before.png'
            await page.screenshot(path=str(before_path), full_page=False)
            result['artifacts']['before'] = str(before_path)

            await _exercise_rounds(page)
            await page.wait_for_timeout(500)

            click_data = await page.evaluate(_CHECK_TOGGLE_ALIGNMENT_JS)
            regression = click_data['spread'] - baseline_spread
            click_ok = regression <= TOGGLE_SPREGRESSION_PX
            result['checks']['afterClicksToggleAlignment'] = {
                'status': 'PASS' if click_ok else 'FAIL',
                'spreadPx': click_data['spread'],
                'baselinePx': baseline_spread,
                'regressionPx': regression,
                'count': click_data['count'],
                'minLeft': click_data['min'],
                'maxLeft': click_data['max'],
            }
            if not click_ok:
                result['diagnostics'].append(
                    {
                        'code': 'TRACE_TOGGLE_MISALIGN_AFTER_CLICK',
                        'observedSpreadPx': click_data['spread'],
                        'regressionPx': regression,
                        'likelyRootCause': [
                            'toggle-round button styling changes on aria-expanded',
                            'trace-detail insert shifts row geometry',
                        ],
                    }
                )

            await _exercise_filters(page)
            await page.wait_for_timeout(500)

            filter_data = await page.evaluate(_CHECK_VISIBLE_TOGGLE_ALIGNMENT_JS)
            filter_regression = filter_data['spread'] - baseline_spread
            filter_ok = filter_regression <= TOGGLE_SPREGRESSION_PX
            result['checks']['afterFiltersToggleAlignment'] = {
                'status': 'PASS' if filter_ok else 'FAIL',
                'spreadPx': filter_data['spread'],
                'baselinePx': baseline_spread,
                'regressionPx': filter_regression,
                'count': filter_data['count'],
                'minLeft': filter_data['min'],
                'maxLeft': filter_data['max'],
            }
            if not filter_ok:
                result['diagnostics'].append(
                    {
                        'code': 'TRACE_TOGGLE_MISALIGN_AFTER_FILTER',
                        'observedSpreadPx': filter_data['spread'],
                        'regressionPx': filter_regression,
                        'likelyRootCause': [
                            'filter changes row visibility but not layout',
                            'CSS cascade conflict on is-filtered-out',
                        ],
                    }
                )

            after_clicks_path = out_dir / 'after-clicks.png'
            await page.screenshot(path=str(after_clicks_path), full_page=False)
            result['artifacts']['afterClicks'] = str(after_clicks_path)

            modal_result = await _exercise_payload_modal(page)
            result['checks']['modalRenderedContent'] = modal_result
            if modal_result['status'] == 'FAIL':
                result['diagnostics'].append(
                    {
                        'code': 'MODAL_RENDER_EMPTY',
                        'observedText': modal_result.get('preview', ''),
                        'likelyRootCause': [
                            'payload key not found in window.__SESSION_PAYLOADS__',
                            'rendered field empty and raw also empty',
                        ],
                    }
                )

            modal_rendered_path = out_dir / 'modal-rendered.png'
            await page.screenshot(path=str(modal_rendered_path), full_page=False)
            result['artifacts']['modalRendered'] = str(modal_rendered_path)

            await page.evaluate('() => { window.closePayloadModal && window.closePayloadModal(); }')
            await page.wait_for_timeout(300)

            overflow = await page.evaluate(_CHECK_OVERFLOW_JS)
            overflow_ok = overflow['ok']
            result['checks']['horizontalOverflow'] = {
                'status': 'PASS' if overflow_ok else 'FAIL',
                'scrollWidth': overflow['scrollWidth'],
                'innerWidth': overflow['innerWidth'],
                'excess': max(0, overflow['scrollWidth'] - overflow['innerWidth']),
            }
            if not overflow_ok:
                result['diagnostics'].append(
                    {
                        'code': 'HORIZONTAL_OVERFLOW',
                        'scrollWidth': overflow['scrollWidth'],
                        'innerWidth': overflow['innerWidth'],
                        'likelyRootCause': [
                            'Element wider than viewport causing horizontal scroll',
                            'Check .shell grid or .session-detail-phase1 width',
                        ],
                    }
                )

            await _exercise_expand_collapse_all(page)
            await page.wait_for_timeout(500)

            final_data = await page.evaluate(_CHECK_TOGGLE_ALIGNMENT_JS)
            final_regression = final_data['spread'] - baseline_spread
            final_ok = final_regression <= TOGGLE_SPREGRESSION_PX
            result['checks']['afterExpandCollapseAll'] = {
                'status': 'PASS' if final_ok else 'FAIL',
                'spreadPx': final_data['spread'],
                'baselinePx': baseline_spread,
                'regressionPx': final_regression,
                'count': final_data['count'],
                'minLeft': final_data['min'],
                'maxLeft': final_data['max'],
            }

            final_path = out_dir / 'final.png'
            await page.screenshot(path=str(final_path), full_page=False)
            result['artifacts']['final'] = str(final_path)

    except Exception as e:
        error_msg = str(e)
        if 'playwright' in error_msg.lower() or 'executable' in error_msg.lower():
            result['status'] = 'BLOCKED'
            result['checks']['playwright'] = {
                'status': 'BLOCKED',
                'message': f'Playwright browser not available: {error_msg}',
            }
            result['diagnostics'].append(
                {
                    'code': 'PLAYWRIGHT_UNAVAILABLE',
                    'message': error_msg,
                    'nextInspection': ['Run: python3 -m playwright install chromium'],
                }
            )
        else:
            result['status'] = 'FAIL'
            result['diagnostics'].append(
                {
                    'code': 'BROWSER_ERROR',
                    'message': error_msg,
                }
            )
    finally:
        if browser:
            with contextlib.suppress(Exception):
                await browser.close()

    # 计算overall 状态。
    result['finishedAt'] = _now_iso()
    check_statuses = [c.get('status', 'PASS') for c in result['checks'].values()]
    if 'BLOCKED' in check_statuses:
        result['status'] = 'BLOCKED'
    elif any(s == 'FAIL' for s in check_statuses):
        result['status'] = 'FAIL'
    else:
        result['status'] = 'PASS'

    return result


# 重置filter 全部。
async def _reset_filter_to_all(page: object) -> None:
    """参数：
    page: page 参数。
    """
    all_chip = await page.query_selector('.trace-panel__chip[data-status="all"]')
    if all_chip:
        is_active = await page.evaluate(
            """
            () => {
                const c = document.querySelector('.trace-panel__chip[data-status="all"]');
                return c && c.classList.contains('active');
            }
            """
        )
        if not is_active:
            await all_chip.click()
            await page.wait_for_timeout(200)


# 演练rounds。
async def _exercise_rounds(page: object) -> None:
    """参数：
    page: page 参数。
    """
    count = await page.evaluate(_COUNT_VISIBLE_ROWS_JS)
    if count == 0:
        return

    indices = [0]
    if count > SECOND_VISIBLE_ROUND_MIN:
        indices.append(1)
    if count > EIGHTH_VISIBLE_ROUND_MIN:
        indices.append(7)
    if count > TWENTY_FOURTH_VISIBLE_ROUND_MIN:
        indices.append(23)

    for idx in indices:
        await page.evaluate(f"""
        () => {{
            const toggles = document.querySelectorAll('.trace-round-toggle');
            if (toggles[{idx}] && window.toggleRoundDetail) {{
                window.toggleRoundDetail(toggles[{idx}], 'expand');
            }}
        }}
        """)
        await page.wait_for_timeout(100)

    for idx in indices:
        await page.evaluate(f"""
        () => {{
            const toggles = document.querySelectorAll('.trace-round-toggle');
            if (toggles[{idx}] && window.toggleRoundDetail) {{
                window.toggleRoundDetail(toggles[{idx}], 'collapse');
            }}
        }}
        """)
        await page.wait_for_timeout(100)


# 演练filters。
async def _exercise_filters(page: object) -> None:
    """参数：
    page: page 参数。
    """
    failed_chip = await page.query_selector('.trace-panel__chip[data-status="failed"]')
    if failed_chip:
        await page.evaluate(
            """
            () => {
                const c = document.querySelector('.trace-panel__chip[data-status="failed"]');
                if (c && !c.classList.contains('active')) c.click();
            }
            """
        )
        await page.wait_for_timeout(300)

    all_chip = await page.query_selector('.trace-panel__chip[data-status="all"]')
    if all_chip:
        await page.evaluate(
            """
            () => {
                const c = document.querySelector('.trace-panel__chip[data-status="all"]');
                if (c && !c.classList.contains('active')) c.click();
            }
            """
        )
        await page.wait_for_timeout(300)


_COUNT_VISIBLE_ROWS_JS = """
() => document.querySelectorAll('.trace-row').length
"""


# 演练payload modal。
async def _exercise_payload_modal(page: object) -> dict:
    """参数：
        page: page 参数。

    返回：
        结果映射。
    """
    check = {
        'status': 'PASS',
        'opened': False,
        'preview': '',
        'renderedLength': 0,
        'isNoRenderedContent': False,
    }

    await page.evaluate("""
    () => {
        const toggles = document.querySelectorAll('.trace-round-toggle');
        if (toggles[0] && window.toggleRoundDetail) {
            window.toggleRoundDetail(toggles[0], 'expand');
        }
    }
    """)
    await page.wait_for_timeout(500)

    btn_found = await page.evaluate("""
    () => {
        // Try LLM call action buttons first (now visible in expanded trace-detail)
        let btn = document.querySelector('.llm-call-card__action-btn[data-action="open-payload"]');
        if (btn && btn.offsetParent !== null) return btn.dataset.payloadKey || '';
        // Fallback: message card buttons
        btn = document.querySelector('.message-card__btn[data-action="open-payload"]');
        if (btn && btn.offsetParent !== null) return btn.dataset.payloadKey || '';
        // Fallback: tool result buttons
        btn = document.querySelector('.payload-btn[data-action="open-payload"]');
        if (btn && btn.offsetParent !== null) return btn.dataset.payloadKey || '';
        return '';
    }
    """)

    if not btn_found:
        check['status'] = 'PASS'
        check['note'] = 'No visible payload buttons found on page'
        return check

    await page.evaluate(f"""
    () => {{
        const btn = document.querySelector('[data-payload-key="{btn_found}"]');
        if (btn) btn.click();
    }}
    """)
    await page.wait_for_timeout(800)

    # 检查如果 modal is open。
    modal_visible = await page.evaluate(
        "() => { const m = document.getElementById('payload-modal'); return m && m.open; }"
    )
    if modal_visible:
        check['opened'] = True

    # 检查页面已渲染内容。
    rendered_info = await page.evaluate(_CHECK_MODAL_RENDERED_JS)
    check['preview'] = rendered_info.get('text', '')
    check['renderedLength'] = rendered_info.get('length', 0)
    check['isNoRenderedContent'] = rendered_info.get('isNoRenderedContent', False)

    if rendered_info.get('isNoRenderedContent') or (
        rendered_info.get('length', 0) == 0 and rendered_info.get('found')
    ):
        check['status'] = 'FAIL'

    # 通过 JavaScript 切换到原始标签再返回。
    await page.evaluate("""
    () => {
        const rawTab = document.querySelector('.payload-modal__tab[data-mode="raw"]');
        if (rawTab) rawTab.click();
    }
    """)
    await page.wait_for_timeout(300)

    await page.evaluate("""
    () => {
        const renderedTab = document.querySelector('.payload-modal__tab[data-mode="rendered"]');
        if (renderedTab) renderedTab.click();
    }
    """)
    await page.wait_for_timeout(300)

    # 关闭modal。
    await page.evaluate('() => { window.closePayloadModal && window.closePayloadModal(); }')
    await page.wait_for_timeout(300)

    return check


# 演练expand collapse 全部。
async def _exercise_expand_collapse_all(page: object) -> None:
    """参数：
    page: page 参数。
    """
    await page.evaluate("""
    () => {
        const expandBtn = document.querySelector('[data-action="expand-all"]');
        if (expandBtn) expandBtn.click();
    }
    """)
    await page.wait_for_timeout(500)

    await page.evaluate("""
    () => {
        const collapseBtn = document.querySelector('[data-action="collapse-all"]');
        if (collapseBtn) collapseBtn.click();
    }
    """)
    await page.wait_for_timeout(500)


# 维护fail service。
def _fail_service(result: dict, status: int, url: str) -> None:
    """参数：
    result: 用于累积检查结果的可变对象。
    status: HTTP 状态 observed从Playwright navigation。
    url: 待请求的 URL。
    """
    result['status'] = 'FAIL'
    result['checks']['navigation'] = {
        'status': 'FAIL',
        'message': f'Server returned HTTP {status}.',
    }
    result['diagnostics'].append(
        {
            'code': 'SERVICE_UNAVAILABLE',
            'message': f'Server returned HTTP {status} for {url}.',
            'nextInspection': ['Start the fixture server and verify the URL.'],
        }
    )


# 维护fail 不可达。
def _fail_unreachable(result: dict, url: str, exc: Exception) -> None:
    """参数：
    result: 用于累积检查结果的可变对象。
    url: 待请求的 URL。
    exc: 捕获的异常对象。
    """
    result['status'] = 'FAIL'
    result['checks']['navigation'] = {
        'status': 'FAIL',
        'message': f'Cannot reach {url}: {exc}',
    }
    result['diagnostics'].append(
        {
            'code': 'SERVICE_UNAVAILABLE',
            'message': f'Cannot reach {url}: {exc}',
            'nextInspection': ['Start the fixture server: ./scripts/session-browser.sh serve'],
        }
    )


# 运行脚本自测试场景。
def _self_test() -> None:  # noqa: PLR0915
    failures = 0

    # 维护assert。
    def _assert(name: str, cond: bool, msg: str = '') -> None:
        """参数：
        name: 条目名称。
        cond: cond 参数。
        msg: 可选失败项 detail。
        """
        nonlocal failures
        if cond:
            print(f'  PASS: {name}')
        else:
            failures += 1
            print(f'  FAIL: {name} {msg}')

    # 维护compute spread。
    def compute_spread(lefts: list[int]) -> int:
        """参数：
            lefts: lefts 参数。

        返回：
            进程退出码。
        """
        if not lefts:
            return 0
        return max(lefts) - min(lefts)

    _assert('spread all same', compute_spread([100, 100, 100]) == 0)
    _assert('spread within threshold', compute_spread([100, 101, 100]) <= TOGGLE_SPREGRESSION_PX)
    _assert('spread too large', compute_spread([100, 128, 100]) > TOGGLE_SPREAD_ABSOLUTE_MAX)
    _assert('spread empty', compute_spread([]) == 0)

    # 检查overflow。
    def check_overflow(scroll_w: int, inner_w: int) -> bool:
        """参数：
            scroll_w: scroll w 参数。
            inner_w: inner w 参数。

        返回：
            当overflow stays 内 configured margin.时返回 true。
        """
        return scroll_w <= inner_w + OVERFLOW_MARGIN_PX

    _assert('overflow ok equal', check_overflow(1440, 1440))
    _assert('overflow ok within margin', check_overflow(1441, 1440))
    _assert('overflow ok at exact margin', check_overflow(1442, 1440))
    _assert('overflow fail excess', not check_overflow(1443, 1440))

    # 检查rendered。
    def check_rendered(text: str) -> bool:
        """参数：
            text: 待检查的文本。

        返回：
            满足条件时返回 true，否则返回 false。
        """
        return text.strip() != '(No rendered content)' and len(text.strip()) > 0

    _assert('rendered content ok', check_rendered('Hello world'))
    _assert('no rendered content fail', not check_rendered('(No rendered content)'))
    _assert('empty fail', not check_rendered('   '))

    sample = {
        'schemaVersion': 1,
        'status': 'PASS',
        'checks': {
            'initialToggleAlignment': {'status': 'PASS', 'spreadPx': 0, 'baselinePx': 0},
        },
        'artifacts': {'before': 'before.png'},
        'diagnostics': [],
    }
    try:
        json.dumps(sample)
        _assert('result JSON serialisable', True)
    except Exception:
        _assert('result JSON serialisable', False)

    # 运行browser test。
    async def _run_browser_test(html: str, js: str) -> dict:
        """参数：
            html: 待检查的 HTML 文本。
            js: 待执行的 JavaScript 表达式。

        返回：
            结果映射。
        """
        from playwright.async_api import async_playwright  # noqa: PLC0415

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            context = await browser.new_context(viewport={'width': 1440, 'height': 1100})
            page = await context.new_page()
            await page.set_content(html, wait_until='domcontentloaded')
            data = await page.evaluate(js)
            await browser.close()
            return data

    # 同步browser test。
    def _sync_browser_test(html: str, js: str) -> dict:
        """参数：
            html: 待检查的 HTML 文本。
            js: 待执行的 JavaScript 表达式。

        返回：
            结果映射。
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop.run_until_complete(_run_browser_test(html, js))

    good_html = """
    <!DOCTYPE html><html><head><style>
    .trace-row { display: flex; }
    .trace-round-toggle { width: 40px; }
    </style></head><body>
    <div class="trace-row"><button class="trace-round-toggle">R1</button></div>
    <div class="trace-row"><button class="trace-round-toggle">R2</button></div>
    <div class="trace-row"><button class="trace-round-toggle">R3</button></div>
    </body></html>
    """

    try:
        align = _sync_browser_test(good_html, _CHECK_TOGGLE_ALIGNMENT_JS)
        _assert(
            'toggle alignment JS works',
            align['count'] == EXPECTED_TOGGLE_COUNT,
            f'count={align.get("count")}',
        )
        _assert('toggle spread is 0', align['spread'] == 0, f'spread={align.get("spread")}')
    except Exception as e:
        _assert('toggle alignment JS works', False, str(e))

    overflow_html = """
    <!DOCTYPE html><html><head><style>
    body { margin: 0; }
    .wide { width: 2000px; height: 100px; }
    </style></head><body><div class="wide">wide</div></body></html>
    """
    try:
        ov = _sync_browser_test(overflow_html, _CHECK_OVERFLOW_JS)
        _assert('overflow JS detects wide', not ov['ok'], f'ok={ov.get("ok")}')
    except Exception as e:
        _assert('overflow JS detects wide', False, str(e))

    modal_html = """
    <!DOCTYPE html><html><body>
    <div class="payload-modal__rendered"><div>Hello world</div></div>
    </body></html>
    """
    try:
        mr = _sync_browser_test(modal_html, _CHECK_MODAL_RENDERED_JS)
        _assert(
            'modal rendered JS works', mr['found'] and mr['length'] > 0, f'text={mr.get("text")}'
        )
    except Exception as e:
        _assert('modal rendered JS works', False, str(e))

    # 页面没有已渲染内容时记录失败。
    no_rendered_html = """
    <!DOCTYPE html><html><body>
    <div class="payload-modal__rendered">(No rendered content)</div>
    </body></html>
    """
    try:
        nr = _sync_browser_test(no_rendered_html, _CHECK_MODAL_RENDERED_JS)
        _assert(
            'modal detects no-rendered',
            nr['isNoRenderedContent'],
            f'isNoRendered={nr.get("isNoRenderedContent")}',
        )
    except Exception as e:
        _assert('modal detects no-rendered', False, str(e))

    if failures:
        print(f'\n{failures} self-test(s) failed')
        sys.exit(1)
    else:
        print('\nAll self-tests passed')
        sys.exit(0)


# 解析命令行参数并运行脚本入口。
def main() -> None:
    """解析命令行参数并运行本文件契约；任一检查失败时返回非零退出码。"""
    parser = argparse.ArgumentParser(
        description='Browser interaction layout gate for session detail',
    )
    parser.add_argument(
        '--url',
        default=None,
        help='Target session detail URL (e.g. http://127.0.0.1:18999/sessions/claude_code/<id>)',
    )
    parser.add_argument(
        '--out',
        default=None,
        help='Output directory for result.json and screenshots',
    )
    parser.add_argument(
        '--self-test',
        action='store_true',
        help='Run self-tests without browser',
    )
    args = parser.parse_args()

    if args.self_test:
        _self_test()
        return

    out_dir = Path(args.out) if args.out else DEFAULT_OUT
    out_dir.mkdir(parents=True, exist_ok=True)

    if not args.url:
        print(
            'BLOCKED: No --url provided.\n'
            '\n'
            'To run this gate you need:\n'
            '  1. A running fixture server: ./scripts/session-browser.sh serve\n'
            '  2. A valid session detail URL.\n'
            '\n'
            'Example:\n'
            '  python3 '
            + ' '.join(sys.argv)
            + ' --url http://127.0.0.1:18999/sessions/claude_code/<session-id>\n',
            file=sys.stderr,
        )

        # 写入BLOCKED 结果。
        result = {
            'schemaVersion': 1,
            'status': 'BLOCKED',
            'gate': 'session-detail-interaction',
            'url': None,
            'startedAt': _now_iso(),
            'finishedAt': _now_iso(),
            'checks': {
                'navigation': {
                    'status': 'BLOCKED',
                    'message': 'No URL provided. Cannot reach browser target.',
                },
            },
            'artifacts': {},
            'diagnostics': [
                {
                    'code': 'NO_URL',
                    'message': 'Provide --url with a session detail URL.',
                    'nextInspection': [
                        'Start server: ./scripts/session-browser.sh serve',
                        'Find a session ID from the dashboard or sessions list.',
                        'Run: python3 '
                        + ' '.join(sys.argv)
                        + ' --url http://127.0.0.1:18999/sessions/claude_code/<id>',
                    ],
                }
            ],
        }
        result_path = out_dir / 'result.json'
        result_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8'
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(2)

    url = args.url
    print('Session detail interaction gate')
    print(f'URL: {url}')
    print(f'Output: {out_dir}')
    print()

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    result = loop.run_until_complete(run_interaction_gate(url, out_dir))

    # 写入artifact。
    result_path = out_dir / 'result.json'
    result_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8'
    )

    # 打印summary。
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print()

    if result['status'] == 'PASS':
        print('PASS: Session detail interaction gate passed')
        sys.exit(0)
    elif result['status'] == 'BLOCKED':
        print('BLOCKED: Session detail interaction gate blocked (external condition)')
        sys.exit(2)
    else:
        fail_count = sum(1 for c in result['checks'].values() if c.get('status') == 'FAIL')
        print(f'FAIL: {fail_count} check(s) failed')
        for d in result.get('diagnostics', []):
            print(f'  [{d.get("code")}] {d.get("message", d.get("observedSpreadPx", ""))}')
        sys.exit(1)


if __name__ == '__main__':
    main()
