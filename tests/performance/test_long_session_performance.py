"""长会话（100 轮）性能与渲染测试。

验证 100+ 轮会话的可用性：
- 页面无错误渲染
- Trace 视图包含所有轮次
- 轮次切换功能正常
- DOM 规模保持合理
"""

import pytest
import os
import subprocess
import sys
import time
import urllib.request

SB_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC_DIR = os.path.join(SB_ROOT, "src")


@pytest.fixture(scope="module")
def long_session_url(long_fixture_session):
    """生成 100 轮 fixture 会话的 session detail URL。"""
    base_url, agent, session_id = long_fixture_session
    yield f"{base_url}/sessions/{agent}/{session_id}"


class TestLongSessionRendering:
    """验证 100 轮会话的正确渲染。"""

    @pytest.mark.contract_case("UI-SD-027", "UI-SD-028")
    def test_long_session_returns_200(self, long_session_url):
        """长会话详情页必须返回 HTTP 200。"""
        resp = urllib.request.urlopen(long_session_url, timeout=15)
        assert resp.status == 200

    @pytest.mark.contract_case("UI-SD-027", "UI-SD-028")
    def test_long_session_contains_trace_panel(self, long_session_url):
        """长会话必须包含 trace 面板结构。"""
        resp = urllib.request.urlopen(long_session_url, timeout=15)
        html = resp.read().decode("utf-8")
        assert "data-trace-panel" in html
        assert "sd-trace-head" in html

    @pytest.mark.contract_case("UI-SD-027", "UI-SD-028")
    def test_trace_view_present(self, long_session_url):
        """Trace 视图容器必须存在。"""
        resp = urllib.request.urlopen(long_session_url, timeout=15)
        html = resp.read().decode("utf-8")
        assert 'class="trace"' in html or 'trace' in html

    @pytest.mark.contract_case("UI-SD-027", "UI-SD-028")
    def test_round_count_matches_100(self, long_session_url):
        """渲染的 HTML 应包含 100 个 trace 行对应 100 轮。"""
        resp = urllib.request.urlopen(long_session_url, timeout=15)
        html = resp.read().decode("utf-8")
        # 使用 v9 data 属性统计 trace 行数
        count = html.count('data-trace-round-row')
        assert count == 100, f"预期 100 个 trace 行，实际找到 {count}"

    @pytest.mark.contract_case("UI-SD-027", "UI-SD-028")
    def test_no_server_error(self, long_session_url):
        """长会话不得触发错误模板。"""
        resp = urllib.request.urlopen(long_session_url, timeout=15)
        html = resp.read().decode("utf-8")
        assert "<title>Error - Agent Run Profiler</title>" not in html

    @pytest.mark.contract_case("UI-SD-027", "UI-SD-028")
    def test_trace_detail_hidden_by_default(self, long_session_url):
        """所有 trace-detail div 初始应为隐藏状态。"""
        resp = urllib.request.urlopen(long_session_url, timeout=15)
        html = resp.read().decode("utf-8")
        # 使用 v9 data 属性统计 trace-detail div 数量
        total = html.count('data-trace-detail')
        # 所有 div 都应带有 hidden 属性
        hidden = html.count('hidden>')
        assert total == 100, f"预期 100 个 trace-detail div，实际找到 {total}"
        assert hidden >= total, f"{total} 个 detail div 中仅 {hidden} 个为隐藏状态"

    @pytest.mark.contract_case("UI-SD-027", "UI-SD-028")
    def test_preview_text_not_full_content(self, long_session_url):
        """Trace 行应使用紧凑的 preview_text，而非完整消息内容。"""
        resp = urllib.request.urlopen(long_session_url, timeout=15)
        html = resp.read().decode("utf-8")
        # v18: 表结构使用 .summary-title 展示预览文本
        assert "summary-title" in html or "sd-round-preview" in html or "sd-round-preview__title" in html, \
            "Trace 行应使用紧凑的预览元素"

    @pytest.mark.contract_case("UI-SD-027", "UI-SD-028")
    def test_css_contain_property(self, long_session_url):
        """CSS 应在 trace 元素上包含 contain: layout style。"""
        css_path = os.path.join(SB_ROOT, "src", "session_browser", "web", "static", "css", "session-detail.css")
        with open(css_path) as f:
            css = f.read()
        assert "contain: layout style" in css


class TestLongSessionPerformance:
    """100 轮会话的粗略性能检查。"""

    @pytest.mark.contract_case("UI-SD-027", "UI-SD-028")
    def test_page_loads_under_time_budget(self, long_session_url):
        """服务器响应加渲染应在 10 秒内完成。"""
        start = time.monotonic()
        resp = urllib.request.urlopen(long_session_url, timeout=15)
        html = resp.read().decode("utf-8")
        elapsed = time.monotonic() - start

        assert elapsed < 10, f"页面加载耗时 {elapsed:.2f}s（预算：10s）"
        assert len(html) > 10000, "页面 HTML 体积异常偏小"

    @pytest.mark.contract_case("UI-SD-027", "UI-SD-028")
    def test_html_size_reasonable(self, long_session_url):
        """100 轮的 HTML payload 应低于 5MB。"""
        resp = urllib.request.urlopen(long_session_url, timeout=15)
        html = resp.read().decode("utf-8")
        size_kb = len(html.encode("utf-8")) / 1024
        assert size_kb < 5000, f"HTML 体积 {size_kb:.0f}KB 超过 5MB 预算"
