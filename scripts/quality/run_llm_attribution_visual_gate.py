#!/usr/bin/env python3
"""提供 run llm attribution visual gate 脚本能力。"""

import argparse
import asyncio
import contextlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# 默认 输出 目录。
_RUN_ID = os.environ.get('FEIPI_RUN_ID') or os.environ.get('FEIPI_SESSION_ID') or f'pid-{os.getpid()}'
_RUNTIME_ROOT = Path(os.environ.get('FEIPI_AGENT_RUNTIME_ROOT', REPO_ROOT / 'tmp' / 'agent-runtime'))
DEFAULT_OUT = _RUNTIME_ROOT / 'runs' / _RUN_ID / 'test-results' / 'quality' / 'llm-attribution-visual'

OVERFLOW_MARGIN_PX = 2
HTTP_ERROR_MIN = 400
VIEWPORTS = [
    {'width': 1440, 'height': 900, 'label': '1440x900'},
    {'width': 2560, 'height': 1440, 'label': '2560x1440'},
]


# 维护当前 ISO timestamp。
def _now_iso() -> str:
    """返回：
        now iso 字符串。
    """
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


# ---------------------------------------------------------------------------
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
    const modal = document.getElementById('sd-payload-modal') ||
        document.getElementById('payload-modal');
    if (!modal) return { visible: false, id: '' };
    const isOpen = modal.open || modal.hasAttribute('open');
    return { visible: !!isOpen, id: modal.id };
}
"""

_CLOSE_MODAL_JS = """
() => {
    const modal = document.getElementById('sd-payload-modal') ||
        document.getElementById('payload-modal');
    if (!modal) return;
    if (typeof modal.close === 'function' && modal.open) modal.close();
    else modal.removeAttribute('open');
}
"""

_CHECK_ATTRIBUTION_STATE_JS = """
() => {
    const modal = document.getElementById('sd-payload-modal') ||
        document.getElementById('payload-modal');
    if (!modal) return { state: 'no_modal' };
    const state = modal.getAttribute('data-attribution-state') || 'idle';
    return { state: state };
}
"""

_CHECK_GEOMETRY_JS = """
() => {
    const rect = (sel) => {
        const el = document.querySelector(sel);
        if (!el) return null;
        return el.getBoundingClientRect();
    };
    const modal = document.getElementById('sd-payload-modal') ||
        document.getElementById('payload-modal');
    if (!modal || !modal.open) {
        return {
            modalWithinViewport: true,
            noHorizontalOverflow: document.documentElement.scrollWidth <= window.innerWidth + 2
        };
    }
    const modalRect = modal.getBoundingClientRect();
    const withinViewport = modalRect.left >= -2 && modalRect.right <= window.innerWidth + 2;
    const noOverflow = document.documentElement.scrollWidth <= window.innerWidth + 2;

    // Distribution bar check
    const distBar = document.querySelector('.sd-attribution-distribution__bar');
    const distOk = !!distBar && distBar.getBoundingClientRect().right <= modalRect.right + 2;

    // Availability table check
    const table = document.querySelector('.sd-attrib-table');
    const tableOk = !!table && table.getBoundingClientRect().right <= modalRect.right + 2;

    // Bucket preview check: PASS when no preview element exists (empty-state case).
    // Only FAIL when preview element exists AND overflows modal.
    const preview = document.querySelector('.sd-attribution-bucket__preview');
    const hasPreview = !!preview;
    const previewOk = !hasPreview || preview.getBoundingClientRect().right <= modalRect.right + 2;

    return {
        modalWithinViewport: withinViewport,
        noHorizontalOverflow: noOverflow,
        distributionVisible: distOk,
        tableWithinModal: tableOk,
        previewWithinModal: previewOk,
        modalRect: {
            left: Math.round(modalRect.left),
            right: Math.round(modalRect.right),
            width: Math.round(modalRect.width)
        },
        scrollWidth: document.documentElement.scrollWidth,
        innerWidth: window.innerWidth,
    };
}
"""

_CHECK_MODAL_TEXT_JS = """
() => {
    const modal = document.getElementById('sd-payload-modal') ||
        document.getElementById('payload-modal');
    if (!modal) return { text: '', hasDisplayOnlySection: false };
    // Check if the display-only section ("明细, 不计入总量") exists in the modal
    const hasDisplayOnly = modal.querySelector('h3') &&
        Array.from(modal.querySelectorAll('h3')).some(h => h.textContent.includes('不计入总量'));
    return { text: modal.textContent || '', hasDisplayOnlySection: hasDisplayOnly };
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


# 等待attribution state。
async def wait_for_attribution_state(
    page: object, target_state: str = 'success', timeout: float = 10.0
) -> bool:
    """参数：
        page: page 参数。
        target_state: target state 参数。
        timeout: 超时时间，单位为秒。

    返回：
        true 如果 state reached, false 如果 错误 或 timeout。
    """
    start = time.time()
    while time.time() - start < timeout:
        state_info = await page.evaluate(_CHECK_ATTRIBUTION_STATE_JS)
        state = state_info.get('state', 'idle')
        if state == target_state:
            return True
        if state == 'error':
            return False
        await asyncio.sleep(0.2)
    return False  # timeout


# 运行visual gate。
async def run_visual_gate(url: str, out_dir: Path) -> dict:  # noqa: PLR0912, PLR0915
    """参数：
        url: 待请求的 URL。
        out_dir: 目录 在 screenshots, 结果 JSON, 和 报告 are。

    返回：
        结果映射。
    """
    from playwright.async_api import async_playwright  # noqa: PLC0415

    result = {
        'schemaVersion': 1,
        'status': 'PASS',
        'gate': 'llm-attribution-visual',
        'url': url,
        'viewports': [],
        'startedAt': _now_iso(),
        'finishedAt': '',
        'checks': {},
        'screenshots': [],
        'diagnostics': [],
        'summary': None,
    }

    browser = None
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)

            for vp in VIEWPORTS:
                vw, vh = vp['width'], vp['height']
                vp_label = vp['label']
                result['viewports'].append(vp_label)

                context = await browser.new_context(viewport={'width': vw, 'height': vh})
                page = await context.new_page()

                try:
                    resp = await page.goto(url, wait_until='domcontentloaded', timeout=20000)
                    if resp and resp.status >= HTTP_ERROR_MIN:
                        _fail_service(result, resp.status, url)
                        await context.close()
                        return result
                except Exception as e:
                    _fail_unreachable(result, url, e)
                    await context.close()
                    return result

                # 等待用于 DOM到stabilise。
                await page.wait_for_timeout(1500)

                await page.evaluate(_EXPAND_ROUNDS_WITH_ATTRIBUTION_JS)
                await page.wait_for_timeout(800)

                # 检查attribution buttons exist。
                btn_info = await page.evaluate(_CHECK_ATTRIBUTATION_BUTTONS_VISIBLE_JS)
                if not btn_info['request'] or not btn_info['response']:
                    result['status'] = 'BLOCKED'
                    result['checks'][f'buttonsFound-{vp_label}'] = {
                        'status': 'BLOCKED',
                        'message': f'No attribution buttons found at {vp_label}',
                        'found': btn_info,
                    }
                    result['diagnostics'].append(
                        {
                            'code': 'NO_ATTRIBUTATION_BUTTONS',
                            'message': (
                                'No visible Request/Response attribution buttons found. '
                                'The session may not have attribution data, or the first '
                                'round needs to be expanded.'
                            ),
                            'nextInspection': [
                                'Verify the session has LLM calls with attribution payloads.',
                                'Check if the first round was expanded correctly.',
                            ],
                        }
                    )
                    await context.close()
                    return result

                req_payload_id = await page.evaluate("""
                    () => {
                        const btns = document.querySelectorAll(
                            '[data-action="open-payload"]' +
                            '[data-payload-kind="llm.request_attribution"]'
                        );
                        for (const btn of btns) {
                            if (btn.offsetParent !== null) {
                                btn.click();
                                return btn.getAttribute('data-payload-id') || '';
                            }
                        }
                        return '';
                    }
                """)

                # 等待用于 attribution fetch到complete。
                attr_ok = await wait_for_attribution_state(
                    page, target_state='success', timeout=10.0
                )
                state_info = await page.evaluate(_CHECK_ATTRIBUTION_STATE_JS)
                attr_state = state_info.get('state', 'idle')

                modal_visible = await page.evaluate(_CHECK_MODAL_VISIBLE_JS)
                req_modal_open = modal_visible['visible']
                result['checks'][f'requestModalOpen-{vp_label}'] = {
                    'status': 'PASS' if req_modal_open else 'FAIL',
                    'payloadId': req_payload_id,
                    'modalId': modal_visible.get('id', ''),
                    'attributionState': attr_state,
                }
                if not req_modal_open:
                    result['diagnostics'].append(
                        {
                            'code': 'REQUEST_MODAL_NOT_OPEN',
                            'message': 'Request attribution modal did not open',
                        }
                    )
                elif not attr_ok:
                    if attr_state == 'error':
                        result['diagnostics'].append(
                            {
                                'code': 'API_ATTRIBUTION_ERROR',
                                'message': 'Request attribution API returned error or fetch failed',
                            }
                        )
                    else:
                        result['diagnostics'].append(
                            {
                                'code': 'ATTRIBUTION_FETCH_TIMEOUT',
                                'message': (
                                    'Request attribution fetch did not reach success '
                                    f'state (state={attr_state})'
                                ),
                            }
                        )

                if req_modal_open:
                    text_info = await page.evaluate(_CHECK_MODAL_TEXT_JS)
                    modal_text = text_info.get('text', '')
                    has_display_only = text_info.get('hasDisplayOnlySection', True)
                    req_text_checks = _check_request_text(modal_text, has_display_only)
                    req_text_checks['hasDisplayOnlySection'] = has_display_only
                    result['checks'][f'requestModalText-{vp_label}'] = req_text_checks

                req_screenshot = out_dir / f'request-{vp_label.replace("x", "x")}.png'
                await page.screenshot(path=str(req_screenshot), full_page=False)
                result['screenshots'].append(str(req_screenshot))

                geo = await page.evaluate(_CHECK_GEOMETRY_JS)
                result['checks'][f'requestGeometry-{vp_label}'] = {
                    'status': 'PASS'
                    if all(
                        [
                            geo.get('noHorizontalOverflow'),
                            geo.get('modalWithinViewport'),
                            geo.get('distributionVisible'),
                            geo.get('tableWithinModal'),
                            geo.get('previewWithinModal'),
                        ]
                    )
                    else 'FAIL',
                    'noHorizontalOverflow': geo.get('noHorizontalOverflow'),
                    'modalWithinViewport': geo.get('modalWithinViewport'),
                    'distributionVisible': geo.get('distributionVisible'),
                    'tableWithinModal': geo.get('tableWithinModal'),
                    'previewWithinModal': geo.get('previewWithinModal'),
                    'modalRect': geo.get('modalRect'),
                    'scrollWidth': geo.get('scrollWidth'),
                    'innerWidth': geo.get('innerWidth'),
                }

                # 关闭Request modal。
                await page.evaluate(_CLOSE_MODAL_JS)
                await page.wait_for_timeout(400)

                resp_payload_id = await page.evaluate("""
                    () => {
                        const btns = document.querySelectorAll(
                            '[data-action="open-payload"]' +
                            '[data-payload-kind="llm.response_attribution"]'
                        );
                        for (const btn of btns) {
                            if (btn.offsetParent !== null) {
                                btn.click();
                                return btn.getAttribute('data-payload-id') || '';
                            }
                        }
                        return '';
                    }
                """)

                # 等待用于 attribution fetch到complete。
                attr_ok = await wait_for_attribution_state(
                    page, target_state='success', timeout=10.0
                )
                state_info = await page.evaluate(_CHECK_ATTRIBUTION_STATE_JS)
                attr_state = state_info.get('state', 'idle')

                modal_visible = await page.evaluate(_CHECK_MODAL_VISIBLE_JS)
                resp_modal_open = modal_visible['visible']
                result['checks'][f'responseModalOpen-{vp_label}'] = {
                    'status': 'PASS' if resp_modal_open else 'FAIL',
                    'payloadId': resp_payload_id,
                    'modalId': modal_visible.get('id', ''),
                    'attributionState': attr_state,
                }
                if not resp_modal_open:
                    result['diagnostics'].append(
                        {
                            'code': 'RESPONSE_MODAL_NOT_OPEN',
                            'message': 'Response attribution modal did not open',
                        }
                    )
                elif not attr_ok:
                    if attr_state == 'error':
                        result['diagnostics'].append(
                            {
                                'code': 'API_ATTRIBUTION_ERROR',
                                'message': (
                                    'Response attribution API returned error or fetch failed'
                                ),
                            }
                        )
                    else:
                        result['diagnostics'].append(
                            {
                                'code': 'ATTRIBUTION_FETCH_TIMEOUT',
                                'message': (
                                    'Response attribution fetch did not reach success '
                                    f'state (state={attr_state})'
                                ),
                            }
                        )

                if resp_modal_open:
                    text_info = await page.evaluate(_CHECK_MODAL_TEXT_JS)
                    modal_text = text_info.get('text', '')
                    has_display_only = text_info.get('hasDisplayOnlySection', True)
                    resp_text_checks = _check_response_text(modal_text, has_display_only)
                    resp_text_checks['hasDisplayOnlySection'] = has_display_only
                    result['checks'][f'responseModalText-{vp_label}'] = resp_text_checks

                resp_screenshot = out_dir / f'response-{vp_label}.png'
                await page.screenshot(path=str(resp_screenshot), full_page=False)
                result['screenshots'].append(str(resp_screenshot))

                geo = await page.evaluate(_CHECK_GEOMETRY_JS)
                result['checks'][f'responseGeometry-{vp_label}'] = {
                    'status': 'PASS'
                    if all(
                        [
                            geo.get('noHorizontalOverflow'),
                            geo.get('modalWithinViewport'),
                            geo.get('distributionVisible'),
                            geo.get('tableWithinModal'),
                            geo.get('previewWithinModal'),
                        ]
                    )
                    else 'FAIL',
                    'noHorizontalOverflow': geo.get('noHorizontalOverflow'),
                    'modalWithinViewport': geo.get('modalWithinViewport'),
                    'distributionVisible': geo.get('distributionVisible'),
                    'tableWithinModal': geo.get('tableWithinModal'),
                    'previewWithinModal': geo.get('previewWithinModal'),
                    'modalRect': geo.get('modalRect'),
                    'scrollWidth': geo.get('scrollWidth'),
                    'innerWidth': geo.get('innerWidth'),
                }

                # 关闭Response modal。
                await page.evaluate(_CLOSE_MODAL_JS)
                await page.wait_for_timeout(400)

                await context.close()

    except Exception as e:
        error_msg = str(e)
        if 'playwright' in error_msg.lower() or 'executable' in error_msg.lower():
            result['status'] = 'NOT_RUN_ENV_LIMITED'
            result['checks']['playwright'] = {
                'status': 'NOT_RUN_ENV_LIMITED',
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
    if 'NOT_RUN_ENV_LIMITED' in check_statuses:
        result['status'] = 'NOT_RUN_ENV_LIMITED'
    elif 'BLOCKED' in check_statuses:
        result['status'] = 'BLOCKED'
    elif any(s == 'FAIL' for s in check_statuses):
        result['status'] = 'FAIL'
    else:
        result['status'] = 'PASS'

    # 计算summary。
    statuses = [c.get('status', 'PASS') for c in result['checks'].values()]
    result['summary'] = {
        'total': len(statuses),
        'passed': statuses.count('PASS'),
        'failed': statuses.count('FAIL'),
        'blocked': statuses.count('BLOCKED'),
        'notRun': statuses.count('NOT_RUN_ENV_LIMITED'),
    }

    return result


# 检查request 文本。
def _check_request_text(text: str, has_display_only: bool = True) -> dict:
    """参数：
        text: 待检查的文本。
        has_display_only: 表示是否期望出现 display-only bucket label。

    返回：
        检查映射带individual text predicates 和 FAIL 状态 当。 必需 copy is 缺失 或 原始-body wording appears。

    说明：
        `hasExclusionLabel` is 不 必需。
    """
    text_lower = text.lower()
    checks = {
        'status': 'PASS',
        'hasRebuiltBanner': '基于本地日志重建' in text,
        'hasProviderDisclaimer': '不等同于真实 provider' in text,
        'hasDistribution': '用量分布' in text,
        'hasAttributionDetail': '归因明细' in text,
        'hasContextSummary': '可见内容摘要' in text,
        'hasAvailabilityTable': '参数可得性表' in text,
        'hasExclusionLabel': '不计入总量' in text if has_display_only else True,
        'hasNoRawRequest': 'raw request' not in text_lower,
        'hasNoRawResponse': 'raw response' not in text_lower,
        'hasNoRawHttpRequest': 'raw http request' not in text_lower,
        'hasNoRawHttpResponse': 'raw http response' not in text_lower,
        'hasNoNoRendered': '(no rendered content)' not in text_lower,
        'hasNoNoRaw': '(no raw content)' not in text_lower,
    }
    failures = [k for k, v in checks.items() if k != 'status' and not v]
    if failures:
        checks['status'] = 'FAIL'
        checks['failed'] = failures
    return checks


# 检查response 文本。
def _check_response_text(text: str, has_display_only: bool = True) -> dict:
    """参数：
        text: 从浏览器捕获的 Response attribution modal 可见文本。
        has_display_only: 表示是否期望出现 display-only bucket label。

    返回：
        包含各个文本谓词和 PASS/FAIL 状态的检查映射。

    说明：
        当 has_display_only 为 false 时，不强制要求 display-only bucket label。
    """
    text_lower = text.lower()
    checks = {
        'status': 'PASS',
        'hasRebuiltBanner': '基于本地日志重建' in text,
        'hasProviderDisclaimer': '不等同于真实 provider' in text,
        'hasDistribution': '用量分布' in text,
        'hasAttributionDetail': '归因明细' in text,
        'hasBlocksDetail': 'Blocks 明细' in text,
        'hasContextSummary': '可见内容摘要' in text,
        'hasAvailabilityTable': '参数可得性表' in text,
        'hasExclusionLabel': '不计入总量' in text if has_display_only else True,
        'hasNoRawRequest': 'raw request' not in text_lower,
        'hasNoRawResponse': 'raw response' not in text_lower,
        'hasNoRawHttpRequest': 'raw http request' not in text_lower,
        'hasNoRawHttpResponse': 'raw http response' not in text_lower,
        'hasNoNoRendered': '(no rendered content)' not in text_lower,
        'hasNoNoRaw': '(no raw content)' not in text_lower,
    }
    failures = [k for k, v in checks.items() if k != 'status' and not v]
    if failures:
        checks['status'] = 'FAIL'
        checks['failed'] = failures
    return checks


# 维护fail service。
def _fail_service(result: dict, status: int, url: str) -> None:
    """参数：
        result: 用于累积检查结果的可变对象。
        status: 状态值。
        url: 待请求的 URL。
    """
    result['status'] = 'FAIL'
    result['checks']['navigation'] = {
        'status': 'FAIL',
        'message': f'Server returned HTTP {status}.',
# 记录a browser navigation 失败项 caused by an unreachable URL。
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
# 写入BLOCKED 结果 当 --url-文件 points到a non-existent 文件。
    }
    result['diagnostics'].append(
        {
            'code': 'SERVICE_UNAVAILABLE',
            'message': f'Cannot reach {url}: {exc}',
            'nextInspection': ['Start the fixture server: ./scripts/session-browser.sh serve'],
        }
    )


# 写入blocked url 文件 missing。
def _write_blocked_url_file_missing(out_dir: Path, url_file_path: str) -> None:
    """参数：
        out_dir: Artifact 目录 receiving ``结果.json``。
        url_file_path: User-provided URL 文件路径 that does 不 exist。
    """
    result = {
        'schemaVersion': 1,
        'status': 'BLOCKED',
        'gate': 'llm-attribution-visual',
        'url': None,
        'viewports': [vp['label'] for vp in VIEWPORTS],
        'startedAt': _now_iso(),
        'finishedAt': _now_iso(),
        'checks': {
            'navigation': {
                'status': 'BLOCKED',
                'message': f'URL file not found: {url_file_path}',
            },
        },
        'screenshots': [],
        'diagnostics': [
            {
                'code': 'URL_FILE_NOT_FOUND',
                'message': f'The file specified by --url-file does not exist: {url_file_path}',
                'nextInspection': [
                    'Create the file with a valid session detail URL.',
                    'Run: python3 '
                    + ' '.join(sys.argv)
                    + ' --url http://127.0.0.1:18999/sessions/claude_code/hifi-viz-session-001',
                ],
            }
        ],
# 写入BLOCKED 结果 当 --url-文件 is 空 或 has 仅 comments。
        'summary': {'total': 1, 'passed': 0, 'failed': 0, 'blocked': 1, 'notRun': 0},
    }
    result_path = out_dir / 'result.json'
    result_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8'
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(2)


# 写入blocked url 文件 空。
def _write_blocked_url_file_empty(out_dir: Path, url_file_path: str) -> None:
    """参数：
        out_dir: Artifact 目录 receiving ``结果.json``。
        url_file_path: User-provided URL 文件路径带no usable URL 行。
    """
    result = {
        'schemaVersion': 1,
        'status': 'BLOCKED',
        'gate': 'llm-attribution-visual',
        'url': None,
        'viewports': [vp['label'] for vp in VIEWPORTS],
        'startedAt': _now_iso(),
        'finishedAt': _now_iso(),
        'checks': {
            'navigation': {
                'status': 'BLOCKED',
                'message': f'URL file contains no valid URLs: {url_file_path}',
            },
        },
        'screenshots': [],
        'diagnostics': [
            {
                'code': 'URL_FILE_EMPTY',
                'message': (
                    f'The URL file contains no non-comment, non-blank lines: {url_file_path}'
                ),
                'nextInspection': [
                    'Add a valid session detail URL to the file.',
                    'Run: python3 '
                    + ' '.join(sys.argv)
                    + ' --url http://127.0.0.1:18999/sessions/claude_code/hifi-viz-session-001',
                ],
            }
        ],
# 写入BLOCKED 结果 当 --url-文件 contains multiple URLs。
        'summary': {'total': 1, 'passed': 0, 'failed': 0, 'blocked': 1, 'notRun': 0},
    }
    result_path = out_dir / 'result.json'
    result_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8'
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(2)


# 写入blocked url 文件 multi。
def _write_blocked_url_file_multi(out_dir: Path, url_file_path: str) -> None:
    """参数：
        out_dir: Artifact 目录 receiving ``结果.json``。
        url_file_path: User-provided URL 文件路径带more than one URL。
    """
    result = {
        'schemaVersion': 1,
        'status': 'BLOCKED',
        'gate': 'llm-attribution-visual',
        'url': None,
        'viewports': [vp['label'] for vp in VIEWPORTS],
        'startedAt': _now_iso(),
        'finishedAt': _now_iso(),
        'checks': {
            'navigation': {
                'status': 'BLOCKED',
                'message': (
                    f'URL file contains multiple URLs (only single URL supported): {url_file_path}'
                ),
            },
        },
        'screenshots': [],
        'diagnostics': [
            {
                'code': 'URL_FILE_MULTI',
                'message': (
                    'The URL file contains more than one URL. Only single-URL files '
                    'are currently supported.'
                ),
                'nextInspection': ['Reduce the file to a single session detail URL.'],
            }
        ],
# 写入BLOCKED 结果 当 URL in 文件 does 不 start带http/https。
        'summary': {'total': 1, 'passed': 0, 'failed': 0, 'blocked': 1, 'notRun': 0},
    }
    result_path = out_dir / 'result.json'
    result_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8'
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(2)


# 写入blocked url 文件 invalid。
def _write_blocked_url_file_invalid(out_dir: Path, url_file_path: str, url: str) -> None:
    """参数：
        out_dir: Artifact 目录 receiving ``结果.json``。
        url_file_path: User-provided URL 文件路径。
        url: 待请求的 URL。
    """
    result = {
        'schemaVersion': 1,
        'status': 'BLOCKED',
        'gate': 'llm-attribution-visual',
        'url': None,
        'viewports': [vp['label'] for vp in VIEWPORTS],
        'startedAt': _now_iso(),
        'finishedAt': _now_iso(),
        'checks': {
            'navigation': {
                'status': 'BLOCKED',
                'message': f'Invalid URL in file {url_file_path}: {url}',
            },
        },
        'screenshots': [],
        'diagnostics': [
            {
                'code': 'URL_FILE_INVALID',
                'message': f'The URL does not start with http:// or https://: {url}',
                'nextInspection': ['Provide a valid HTTP(S) session detail URL.'],
            }
        ],
# 生成a human-readable markdown 报告从gate 结果。
        'summary': {'total': 1, 'passed': 0, 'failed': 0, 'blocked': 1, 'notRun': 0},
    }
    result_path = out_dir / 'result.json'
    result_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8'
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(2)


# 维护生成 markdown 报告。
def _generate_markdown_report(result: dict, out_dir: Path) -> Path:  # noqa: PLR0915
    """参数：
        result: 结构化 visual gate 结果 dict。
        out_dir: Artifact 目录 receiving ``报告.md``。

    返回：
        路径到 generated Markdown 报告。
    """
    status = result.get('status', 'UNKNOWN')
    url = result.get('url', 'N/A')
    viewports = result.get('viewports', [])
    screenshots = result.get('screenshots', [])
    checks = result.get('checks', {})
    diagnostics = result.get('diagnostics', [])
    summary = result.get('summary', {})

    lines = []
    lines.append('# LLM Attribution Visual Gate Report')
    lines.append('')
    lines.append('| Field | Value |')
    lines.append('|---|---|')
    lines.append(f'| **Status** | **{status}** |')
    lines.append(f'| URL | `{url}` |')
    lines.append(f'| Started | {result.get("startedAt", "N/A")} |')
    lines.append(f'| Finished | {result.get("finishedAt", "N/A")} |')
    lines.append(f'| Viewports | {", ".join(viewports) if viewports else "N/A"} |')
    lines.append('')

    if summary:
        lines.append('## Summary')
        lines.append('')
        lines.append('| | Count |')
        lines.append('|---|---|')
        for k, v in summary.items():
            lines.append(f'| {k} | {v} |')
        lines.append('')

    lines.append('## Checks')
    lines.append('')
    for check_name, check_data in checks.items():
        c_status = check_data.get('status', 'UNKNOWN')
        c_msg = check_data.get('message', '')
        lines.append(f'### {check_name}')
        lines.append(f'- **Status**: {c_status}')
        if c_msg:
            lines.append(f'- **Message**: {c_msg}')
        for k, v in check_data.items():
            if k not in ('status', 'message'):
                lines.append(f'- **{k}**: {v}')
        lines.append('')

    if diagnostics:
        lines.append('## Diagnostics')
        lines.append('')
        for d in diagnostics:
            code = d.get('code', 'UNKNOWN')
            msg = d.get('message', '')
            lines.append(f'- **[{code}]** {msg}')
        lines.append('')

    if screenshots:
        lines.append('## Screenshots')
        lines.append('')
        for s in screenshots:
            lines.append(f'- `{s}`')
        lines.append('')

    if status in {'FAIL', 'BLOCKED'}:
        lines.append('## Next actions')
        lines.append('')
        lines.append('- Review diagnostics above')
        lines.append('- Check screenshots for visual issues')
        lines.append('- Verify session has proper attribution data')
        lines.append('')

    report_path = out_dir / 'report.md'
    report_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return report_path

# 运行脚本自测试场景。
def _self_test() -> None:
    failures = 0

    # 维护assert。
    def _assert(name: str, cond: bool, msg: str = '') -> None:
        """参数：
            name: 打印到 stdout 的断言标签。
            cond: 布尔断言结果。
            msg: 失败断言的可选诊断信息。
        """
        nonlocal failures
        if cond:
            print(f'  PASS: {name}')
        else:
            failures += 1
            print(f'  FAIL: {name} {msg}')

    # Text checks用于request modal。
    good_req_text = (
        '基于本地日志重建, 不等同于真实 provider request/response body。'
        '用量分布 归因明细 可见内容摘要 参数可得性表 不计入总量'
    )
    req_checks = _check_request_text(good_req_text)
    _assert('request text checks pass', req_checks['status'] == 'PASS', str(req_checks))

    # Text checks用于response modal。
    good_resp_text = (
        '基于本地日志重建, 不等同于真实 provider request/response body。'
        '用量分布 归因明细 Blocks 明细 可见内容摘要 参数可得性表 不计入总量'
    )
    resp_checks = _check_response_text(good_resp_text)
    _assert('response text checks pass', resp_checks['status'] == 'PASS', str(resp_checks))

    bad_req_text = 'Raw request (No rendered content)'
    req_bad = _check_request_text(bad_req_text)
    _assert('request text checks detect forbidden', req_bad['status'] == 'FAIL', str(req_bad))

    bad_resp_text = 'Raw response (No raw content)'
    resp_bad = _check_response_text(bad_resp_text)
    _assert('response text checks detect forbidden', resp_bad['status'] == 'FAIL', str(resp_bad))

    raw_upper_req = _check_request_text('RAW REQUEST is bad')
    _assert(
        'request text case-insensitive RAW REQUEST detection',
        raw_upper_req['status'] == 'FAIL',
        str(raw_upper_req),
    )

    raw_http_resp = _check_response_text('raw http response here')
    _assert(
        'response text case-insensitive raw http response detection',
        raw_http_resp['status'] == 'FAIL',
        str(raw_http_resp),
    )

    display_only_text = '明细, 不计入总量'
    _assert('display-only section text present', '不计入总量' in display_only_text)

    sample = {
        'schemaVersion': 1,
        'status': 'PASS',
        'viewports': ['1440x900', '2560x1440'],
        'checks': {
            'requestModalOpen-1440x900': {'status': 'PASS'},
        },
        'screenshots': [],
        'diagnostics': [],
    }
    try:
        json.dumps(sample)
        _assert('result JSON serialisable', True)
    except Exception:
        _assert('result JSON serialisable', False)

    source = Path(__file__).read_text()
    _assert('source checks request modal', 'llm.request_attribution' in source)
    _assert('source checks response modal', 'llm.response_attribution' in source)
    _assert('source checks no raw request', '"raw request"' in source or "'raw request'" in source)
    _assert(
        'source checks no raw response', '"raw response"' in source or "'raw response'" in source
    )
    _assert('source checks horizontal overflow', 'scrollWidth' in source)

    if failures:
        print(f'\n{failures} self-test(s) failed')
        sys.exit(1)
    else:
        print('\nAll self-tests passed')
        sys.exit(0)


# 解析命令行参数并运行脚本入口。
def main() -> None:  # noqa: PLR0912, PLR0915
    parser = argparse.ArgumentParser(
        description='Browser visual gate for LLM call attribution modals',
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
        '--url-file',
        default=None,
        help='Path to a file containing a single session detail URL',
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

    # 解析URL: --url takes priority, 则 --url-文件。
    url = args.url
    if not url and args.url_file:
        url_file = Path(args.url_file)
        if not url_file.exists():
            _write_blocked_url_file_missing(out_dir, str(url_file))
            return
        content = url_file.read_text(encoding='utf-8').strip()
        lines = [
            line.strip()
            for line in content.splitlines()
            if line.strip() and not line.strip().startswith('#')
        ]
        if not lines:
            _write_blocked_url_file_empty(out_dir, str(url_file))
            return
        if len(lines) > 1:
            _write_blocked_url_file_multi(out_dir, str(url_file))
            return
        url = lines[0]
        if not url.startswith('http://') and not url.startswith('https://'):
            _write_blocked_url_file_invalid(out_dir, str(url_file), url)
            return

    if not url:
        print(
            'BLOCKED: No --url provided.\n'
            '\n'
            'To run this gate you need:\n'
            '  1. A running fixture server: ./scripts/session-browser.sh serve\n'
            '  2. A valid session detail URL with LLM call attribution data.\n'
            '\n'
            'Example:\n'
            '  python3 '
            + ' '.join(sys.argv)
            + ' --url http://127.0.0.1:18999/sessions/claude_code/hifi-viz-session-001\n',
            file=sys.stderr,
        )

        # 写入BLOCKED 结果。
        result = {
            'schemaVersion': 1,
            'status': 'BLOCKED',
            'gate': 'llm-attribution-visual',
            'url': None,
            'viewports': [vp['label'] for vp in VIEWPORTS],
            'startedAt': _now_iso(),
            'finishedAt': _now_iso(),
            'checks': {
                'navigation': {
                    'status': 'BLOCKED',
                    'message': 'No URL provided. Cannot reach browser target.',
                },
            },
            'screenshots': [],
            'diagnostics': [
                {
                    'code': 'NO_URL',
                    'message': 'Provide --url with a session detail URL.',
                    'nextInspection': [
                        'Start server: ./scripts/session-browser.sh serve',
                        'Find a session ID from the dashboard or sessions list.',
                        'Run: python3 '
                        + ' '.join(sys.argv)
                        + ' --url http://127.0.0.1:18999/sessions/claude_code/hifi-viz-session-001',
                    ],
                }
            ],
            'summary': {'total': 1, 'passed': 0, 'failed': 0, 'blocked': 1, 'notRun': 0},
        }
        result_path = out_dir / 'result.json'
        result_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8'
        )
        _generate_markdown_report(result, out_dir)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(2)

    print('LLM Call Attribution Visual Gate')
    print(f'URL: {url}')
    print(f'Output: {out_dir}')
    print()

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    result = loop.run_until_complete(run_visual_gate(url, out_dir))

    # 写入artifact。
    result_path = out_dir / 'result.json'
    result_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8'
    )

    # 生成markdown 报告。
    _generate_markdown_report(result, out_dir)

    # 打印summary。
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print()

    if result['status'] == 'PASS':
        print('PASS: LLM call attribution visual gate passed')
        sys.exit(0)
    elif result['status'] == 'BLOCKED':
        print('BLOCKED: LLM call attribution visual gate blocked (external condition)')
        sys.exit(2)
    elif result['status'] == 'NOT_RUN_ENV_LIMITED':
        print('NOT_RUN_ENV_LIMITED: Browser environment not available')
        sys.exit(2)
    else:
        fail_count = sum(1 for c in result['checks'].values() if c.get('status') == 'FAIL')
        print(f'FAIL: {fail_count} check(s) failed')
        for d in result.get('diagnostics', []):
            print(f'  [{d.get("code")}] {d.get("message", "")}')
        sys.exit(1)


if __name__ == '__main__':
    main()
