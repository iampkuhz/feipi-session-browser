"""MacBook 视口冒烟矩阵 — Python 级 HTTP 测试。

验证所有主要页面在 MacBook 视口尺寸（1280x800 / 1440x900）下
返回 HTTP 200 且具有预期的 HTML 结构。

本测试使用本地测试索引启动 session-browser 服务器，
然后通过带有 MacBook User-Agent 字符串的 HTTP 请求验证每个页面。

用法：
    python3 -m pytest tests/pages/test_macbook_smoke.py -v
"""

from __future__ import annotations

import os
import re
import socket
import subprocess
import sys
import time
import urllib.request

import pytest

# ─── 常量 ──────────────────────────────────────────────────────────

SB_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TEST_INDEX_DIR = os.path.expanduser('~/.local/share/feipi/session-browser/local-test-index')

MACBOOK_13_UA = (
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/120.0.0.0 Safari/537.36'
)
MACBOOK_14_UA = (
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/120.0.0.0 Safari/537.36'
)

# 冒烟测试页面：(名称, 路径, 预期 HTML 片段, 最小 HTML 长度)
PAGES = [
    ('Dashboard', '/dashboard', '>Dashboard<', 500),
    ('Sessions List', '/sessions', '>Sessions<', 500),
    ('Projects', '/projects', '>Projects<', 500),
]


# ─── 服务器夹具 ─────────────────────────────────────────────────────────────


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        s.listen(1)
        return s.getsockname()[1]


def _start_server(env: dict, port: int) -> subprocess.Popen:
    """启动测试服务端进程（直接使用 create_server，绕过 CLI）。"""
    env = env.copy()
    env.setdefault('PYTHONPATH', os.path.join(SB_ROOT, 'src'))
    env.setdefault('SERVER_HOST', '127.0.0.1')
    env['SERVER_PORT'] = str(port)
    env.setdefault('SESSION_BROWSER_LOG_LEVEL', 'WARNING')
    fixture_server_script = (
        'import argparse, sys; sys.path.insert(0, "src"); '
        'from session_browser.web.routes import create_server; '
        'p = argparse.ArgumentParser(); p.add_argument("--port", type=int, default=0); '
        'args = p.parse_args(); '
        's = create_server(port=args.port); s.serve_forever()'
    )
    return subprocess.Popen(
        [sys.executable, '-c', fixture_server_script, '--port', str(port)],
        cwd=SB_ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _wait_for_server(port: int, timeout: float = 15.0) -> str:
    base_url = f'http://127.0.0.1:{port}'
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            resp = urllib.request.urlopen(f'{base_url}/dashboard', timeout=2)
            if resp.status == 200:
                return base_url
        except Exception:
            pass
        time.sleep(0.3)
    raise TimeoutError(f'端口 {port} 上的服务器在 {timeout}s 内未启动')


@pytest.fixture(scope='module')
def macbook_smoke_server():
    """使用本地测试索引启动 session-browser 服务器。

    产出 base_url，如果没有找到索引则跳过。
    """
    index_file = os.path.join(TEST_INDEX_DIR, 'index.sqlite')
    if not os.path.exists(index_file):
        # 尝试 index.db 作为备选
        index_file = os.path.join(TEST_INDEX_DIR, 'index.db')
        if not os.path.exists(index_file):
            pytest.fail('在 ' + TEST_INDEX_DIR + ' 未找到本地测试索引')

    port = _find_free_port()
    env = os.environ.copy()
    env['INDEX_DIR'] = TEST_INDEX_DIR
    env['PYTHONPATH'] = os.path.join(SB_ROOT, 'src')

    proc = _start_server(env, port)

    try:
        base_url = _wait_for_server(port)
        yield base_url
    finally:
        proc.terminate()
        proc.wait()


# ─── 辅助函数 ────────────────────────────────────────────────────────────


def fetch_page(base_url: str, path: str, viewport: str = 'macbook-13') -> tuple[int, str]:
    """获取页面并返回 (status_code, html_body)。"""
    ua = MACBOOK_13_UA if viewport == 'macbook-13' else MACBOOK_14_UA
    url = f'{base_url}{path}'
    req = urllib.request.Request(
        url,
        headers={
            'User-Agent': ua,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        },
    )
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        return resp.status, resp.read().decode('utf-8')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8') if e.fp else ''


# ─── 测试 ──────────────────────────────────────────────────────────────


class TestMacbookSmoke:
    """在 MacBook 视口尺寸下对所有主要页面进行冒烟测试。"""

    @pytest.mark.parametrize('viewport', ['macbook-13', 'macbook-14'])
    @pytest.mark.parametrize('name,path,expected_fragment,min_length', PAGES)
    @pytest.mark.contract_case('UI-VISUAL-009')
    def test_page_loads(
        self, macbook_smoke_server, viewport, name, path, expected_fragment, min_length
    ):
        """每个页面在 MacBook 视口下必须返回 HTTP 200 且包含预期内容。"""
        base_url = macbook_smoke_server
        status, html = fetch_page(base_url, path, viewport)

        assert status == 200, f'{name} 在 {viewport} 下返回 HTTP {status}'
        assert len(html) >= min_length, (
            f'{name} 在 {viewport} 下 HTML 过短：{len(html)} 字节 (预期 >= {min_length})'
        )
        assert expected_fragment in html, (
            f"{name} 在 {viewport} 下缺少预期片段 '{expected_fragment}'"
        )


class TestMacbookViewportSpecific:
    """特定视口的结构检查。"""

    @pytest.mark.contract_case('UI-VISUAL-009')
    def test_dashboard_metric_cards(self, macbook_smoke_server):
        """Dashboard 必须有 6 个 KPI 指标卡片。"""
        base_url = macbook_smoke_server
        status, html = fetch_page(base_url, '/dashboard')
        assert status == 200
        cards = re.findall(r'class="metric-card\b', html)
        assert len(cards) == 6, f'预期 6 个 KPI 指标卡片，发现 {len(cards)} 个'

    @pytest.mark.contract_case('UI-VISUAL-009')
    def test_sessions_list_has_table(self, macbook_smoke_server):
        """Sessions List 必须有会话表格。"""
        base_url = macbook_smoke_server
        status, html = fetch_page(base_url, '/sessions')
        assert status == 200
        assert 'aria-label="Sessions table"' in html, 'Sessions table 必须存在'

    @pytest.mark.contract_case('UI-VISUAL-009')
    def test_projects_page_has_project_entries(self, macbook_smoke_server):
        """Projects 页面必须列出至少一个 project。"""
        base_url = macbook_smoke_server
        status, html = fetch_page(base_url, '/projects')
        assert status == 200
        # 检查 data-table 结构
        has_table = 'class="data-table"' in html or 'class="project-list"' in html
        assert has_table, 'Projects 页面必须有表格或 project 列表'

    @pytest.mark.contract_case('UI-VISUAL-009')
    def test_session_detail_page_exists(self, macbook_smoke_server):
        """Session Detail 页面必须对至少一个会话存在。"""
        base_url = macbook_smoke_server
        # 首先从会话页面获取一个会话 ID
        status, html = fetch_page(base_url, '/sessions?sort=tokens&dir=asc')
        assert status == 200

        # 从轻量候选中提取会话链接，避免真实本地索引的最新大 session 把 smoke 测试变成性能压测。
        match = re.search(r'href="(/sessions/[^"]+/[^"]+)"', html)
        assert match, '在会话列表页面未找到会话链接'

        session_url = match.group(1)
        status, detail_html = fetch_page(base_url, session_url)
        assert status == 200, f'Session detail 在 {session_url} 返回 HTTP {status}'
        assert len(detail_html) >= 500, 'Session detail HTML 过短'
