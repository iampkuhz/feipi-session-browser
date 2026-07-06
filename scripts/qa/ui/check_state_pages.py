#!/usr/bin/env python3
"""API-first state page smoke checks for Java 404/500 templates."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from _api_first_checklib import CSS, JS, TEMPLATES, exists, has_all, has_none, read, run


# 运行页面静态契约检查。
def main() -> int:
    """返回：
        进程退出码。
    """
    not_found = TEMPLATES / '404.html'
    error = TEMPLATES / 'error.html'
    css = CSS / 'states.css'
    js = JS / 'states.js'
    nf_html = read(not_found)
    err_html = read(error)
    combined = nf_html + '\n' + err_html
    web_root = read(Path(__file__).resolve().parents[3] / 'java/web/src/main/java/com/feipi/session/browser/web/WebCompositionRoot.java')
    dto = read(Path(__file__).resolve().parents[3] / 'java/web/src/main/java/com/feipi/session/browser/web/api/PageApiDtos.java')
    checks = [
        ('404.html exists', lambda: exists(not_found)),
        ('error.html exists', lambda: exists(error)),
        ('states.css exists', lambda: exists(css)),
        ('states.js exists', lambda: exists(js)),
        (
            'templates use PageStateModel role/aria/title/message',
            lambda: has_all(combined, ['state.role', 'state.ariaLive', 'state.title', 'state.message', 'state-panel']),
        ),
        (
            '404 actions include dashboard/sessions/projects',
            lambda: has_all(nf_html, ['/dashboard', '/sessions', '/projects', 'state-panel__link']),
        ),
        (
            'error page includes reload and safe details shell',
            lambda: has_all(err_html, ['Something Went Wrong', 'data-action="reload-page"', 'error_details', 'message summary']),
        ),
        (
            'API error boundary is JSON not HTML state',
            lambda: has_all(web_root, ['ctx.path().startsWith("/api/")', 'ctx.json(new ApiErrorResponse', 'isApiPath']),
        ),
        (
            'state DTOs exist',
            lambda: has_all(dto, ['record PageStateModel', 'record SafeErrorDetails', 'record EmptyStateDto']),
        ),
        ('state pages avoid inline style/script/on* handlers', lambda: has_none(combined, ['<style', '<script', 'onclick='])),
    ]
    return run('state pages API-first QA checks', checks)


if __name__ == '__main__':
    raise SystemExit(main())
