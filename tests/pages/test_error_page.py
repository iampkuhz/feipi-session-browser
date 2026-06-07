"""错误页面夹具测试。

验证 404 和 500 错误页面正确渲染，显示错误消息，
并提供返回 Dashboard 的导航链接。

覆盖：
- 404 页面渲染并返回 HTTP 404
- 500 页面模板在有/无错误上下文时均可渲染
- 错误模板中的错误消息显示
- 两个页面都有返回 Dashboard 的链接
- 共享的 state-panel 结构和 CSS 引用

T098 -- Error page 夹具。
"""

from __future__ import annotations

import pytest
import os
import re
import urllib.request
import urllib.error

# ── 路径 ─────────────────────────────────────────────────────────────

SB_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TEMPLATE_DIR = os.path.join(SB_ROOT, "src", "session_browser", "web", "templates")


# ── 404 页面夹具（本地服务器） ────────────────────────────────────────


@pytest.fixture(scope="module")
def error_404_response(hifi_fixture_session):
    """请求一个不存在的路径并捕获 HTTP 响应。"""
    base_url, agent, session_id = hifi_fixture_session
    url = f"{base_url}/__nonexistent_test_path_xyz__"
    try:
        resp = urllib.request.urlopen(url, timeout=10)
        return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")


# ── 错误模板渲染辅助函数 ──────────────────────────────────────────────


def _render_error_template(error: str | None = None) -> str:
    """通过 Jinja2（启用自动转义）渲染 error.html 并返回 HTML 字符串。"""
    from jinja2 import Environment, FileSystemLoader, select_autoescape

    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=True,
    )
    template = env.get_template("error.html")
    error_details = None
    if error is not None:
        error_details = {
            "error_type": "TestError",
            "request_path": "/test-error",
            "request_id": "test-request-id",
            "timestamp": "2026-06-07T00:00:00",
            "message_summary": error,
        }
    return template.render(error_details=error_details, request_path="/test-error")


def _render_404_template() -> str:
    """通过 Jinja2（启用自动转义）渲染 404.html 并返回 HTML 字符串。"""
    from jinja2 import Environment, FileSystemLoader

    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=True,
    )
    template = env.get_template("404.html")
    return template.render()


# ── Test404Page ───────────────────────────────────────────────────────


class Test404Page:
    """验证 404 Not Found 页面渲染及其结构正确。"""

    @pytest.mark.contract_case("UI-VISUAL-007")
    def test_returns_404_status(self, error_404_response):
        """请求未知路径必须返回 HTTP 404。"""
        status, html = error_404_response
        assert status == 404, f"预期 HTTP 404，得到 {status}"

    @pytest.mark.contract_case("UI-VISUAL-007")
    def test_page_renders_substantial_html(self, error_404_response):
        """404 页面必须包含有意义的 HTML 内容。"""
        _, html = error_404_response
        assert len(html) > 200, "404 HTML 必须有足够内容"

    @pytest.mark.contract_case("UI-VISUAL-007")
    def test_has_doctype(self, error_404_response):
        """404 页面必须有正确的 DOCTYPE 声明。"""
        _, html = error_404_response
        assert "<!doctype html" in html.lower(), "404 页面必须有 DOCTYPE"

    @pytest.mark.contract_case("UI-VISUAL-007")
    def test_title_contains_not_found(self, error_404_response):
        """页面标题必须表示 'Not Found'。"""
        _, html = error_404_response
        assert "Not Found" in html, "404 标题必须包含 'Not Found'"

    @pytest.mark.contract_case("UI-VISUAL-007")
    def test_has_404_icon(self, error_404_response):
        """页面必须显示 404 图标。"""
        _, html = error_404_response
        assert ">404<" in html or "404" in html, "404 图标必须可见"

    @pytest.mark.contract_case("UI-VISUAL-007")
    def test_has_page_not_found_text(self, error_404_response):
        """页面必须显示 'Page Not Found' 标题。"""
        _, html = error_404_response
        assert "Page Not Found" in html, "404 页面必须显示 'Page Not Found'"

    @pytest.mark.contract_case("UI-VISUAL-007")
    def test_has_description(self, error_404_response):
        """页面必须显示错误描述。"""
        _, html = error_404_response
        assert "doesn't exist" in html or "has been removed" in html, \
            "404 页面必须描述该错误"

    @pytest.mark.contract_case("UI-VISUAL-007")
    def test_has_state_panel_structure(self, error_404_response):
        """404 页面必须使用共享的 state-panel 组件。"""
        _, html = error_404_response
        assert 'class="state-panel"' in html, "404 页面必须有 state-panel 容器"
        assert 'role="region"' in html, "404 页面必须有 role=region"

    @pytest.mark.contract_case("UI-VISUAL-007")
    def test_has_states_css_reference(self, error_404_response):
        """404 页面必须引用 states.css 样式表。"""
        _, html = error_404_response
        assert "states.css" in html, "404 页面必须引用 states.css"


# ── Test404Template ───────────────────────────────────────────────────


class Test404Template:
    """直接验证 404 模板（无需服务器）。"""

    @pytest.mark.contract_case("UI-VISUAL-007")
    def test_template_renders(self):
        """404.html 必须无错误地渲染。"""
        html = _render_404_template()
        assert len(html) > 100, "404 模板必须产生 HTML"

    @pytest.mark.contract_case("UI-VISUAL-007")
    def test_has_dashboard_link(self):
        """404 页面必须包含返回 Dashboard 的链接。"""
        html = _render_404_template()
        assert '/dashboard' in html, "404 页面必须链接到 /dashboard"
        assert "Dashboard" in html, "404 页面必须显示 'Dashboard' 链接文本"

    @pytest.mark.contract_case("UI-VISUAL-007")
    def test_has_navigation_links(self):
        """404 页面必须提供多个导航选项。"""
        html = _render_404_template()
        nav_links = ["/dashboard", "/projects", "/sessions"]
        for link in nav_links:
            assert link in html, f"404 页面必须链接到 {link}"

    @pytest.mark.contract_case("UI-VISUAL-007")
    def test_has_state_panel_links(self):
        """404 页面的导航链接必须使用 state-panel__link 类。"""
        html = _render_404_template()
        assert 'class="state-panel__link"' in html, \
            "404 页面必须为导航链接使用 state-panel__link"

    @pytest.mark.contract_case("UI-VISUAL-007")
    def test_has_breadcrumb(self):
        """404 页面必须渲染面包屑。"""
        html = _render_404_template()
        assert "sep" in html, "404 页面必须有面包屑分隔符"
        assert "current" in html, "404 页面必须标记当前面包屑项"


# ── Test500ErrorPage ──────────────────────────────────────────────────


class Test500ErrorPage:
    """验证 500 错误页面模板正确渲染。"""

    @pytest.mark.contract_case("UI-VISUAL-007")
    def test_template_renders_without_error(self):
        """即使没有错误消息，错误页面也应能渲染。"""
        html = _render_error_template(error=None)
        assert len(html) > 100, "错误模板必须产生 HTML"

    @pytest.mark.contract_case("UI-VISUAL-007")
    def test_template_renders_with_error(self):
        """错误页面必须在有错误消息时渲染。"""
        html = _render_error_template(error="Test error message")
        assert len(html) > 100, "错误模板必须在有错误时产生 HTML"

    @pytest.mark.contract_case("UI-VISUAL-007")
    def test_title_contains_error(self):
        """页面标题必须表示发生了错误。"""
        html = _render_error_template()
        assert "Error" in html, "错误页面标题必须包含 'Error'"

    @pytest.mark.contract_case("UI-VISUAL-007")
    def test_has_something_went_wrong_text(self):
        """页面必须显示 'Something Went Wrong' 标题。"""
        html = _render_error_template()
        assert "Something Went Wrong" in html, \
            "错误页面必须显示 'Something Went Wrong'"

    @pytest.mark.contract_case("UI-VISUAL-007")
    def test_has_description(self):
        """错误页面必须显示问题描述。"""
        html = _render_error_template()
        assert "unexpected error" in html.lower() or "An unexpected error" in html, \
            "错误页面必须描述问题"

    @pytest.mark.contract_case("UI-VISUAL-007")
    def test_has_state_panel_structure(self):
        """错误页面必须使用共享的 state-panel 组件。"""
        html = _render_error_template()
        assert 'class="state-panel"' in html, "错误页面必须有 state-panel 容器"
        assert 'role="alert"' in html, "错误页面必须有 role=alert"
        assert 'aria-live="assertive"' in html, "错误页面必须有 aria-live=assertive"

    @pytest.mark.contract_case("UI-VISUAL-007")
    def test_has_error_icon(self):
        """错误页面必须显示错误图标。"""
        html = _render_error_template()
        assert 'state-panel__icon--error' in html, \
            "错误页面必须有错误图标修饰类"

    @pytest.mark.contract_case("UI-VISUAL-007")
    def test_has_states_css_reference(self):
        """错误页面必须引用 states.css 样式表。"""
        html = _render_error_template()
        assert "states.css" in html, "错误页面必须引用 states.css"


# ── TestErrorMessageDisplay ──────────────────────────────────────────


class TestErrorMessageDisplay:
    """验证错误消息正确显示。"""

    @pytest.mark.contract_case("UI-VISUAL-007")
    def test_error_message_shown_in_details(self):
        """错误消息必须出现在 details/summary 块中。"""
        html = _render_error_template(error="Database connection failed")
        assert "Database connection failed" in html, \
            "错误消息必须在页面中渲染"
        assert "<details" in html, "错误详情必须在 <details> 元素中"
        assert "<summary>" in html, "错误详情必须有 <summary> 标签"
        assert "Error details" in html, "Summary 必须显示 'Error details'"

    @pytest.mark.contract_case("UI-VISUAL-007")
    def test_error_in_pre_tag(self):
        """错误消息必须包裹在 <pre> 标签中以便阅读。"""
        html = _render_error_template(error="Traceback: line 42")
        assert "<pre" in html, "错误文本必须在 <pre> 块中"
        assert "Traceback: line 42" in html, \
            "错误消息文本必须原样显示"

    @pytest.mark.contract_case("UI-VISUAL-007")
    def test_no_error_details_when_none(self):
        """当没有错误时，错误详情块应隐藏。"""
        html = _render_error_template(error=None)
        # Jinja2 {% if error %} 应完全抑制该块
        assert "<details" not in html, \
            "当 error 为 None 时错误详情块不应渲染"
        # 注意：<pre> 和 <script> 来自基础模板（payload modal、JS），
        # 因此我们只检查错误特定的 <details> 元素。

    @pytest.mark.contract_case("UI-VISUAL-007")
    def test_html_escaped_in_error(self):
        """包含 HTML 的错误消息应在输出中被转义。"""
        html = _render_error_template(error="<script>alert('xss')</script>")
        # Jinja2 自动转义；注入的 <script> 不应作为原始 HTML 出现。
        # 而应作为 &lt;script&gt; 出现在 pre/details 块内。
        # 注意：其他 <script> 标签来自基础模板的 JS 引入，
        # 因此我们检查特定的 XSS 载荷是否被转义。
        assert "&lt;script&gt;" in html, \
            "错误消息必须转义 script 标签"
        # 原始未转义的 <script>alert 不应出现在错误区域
        assert "<script>alert" not in html, \
            "错误消息不得包含未转义的 script 标签"


# ── TestReturnToDashboard ─────────────────────────────────────────────


class TestReturnToDashboard:
    """验证两个错误页面都提供返回 Dashboard 的链接。"""

    @pytest.mark.contract_case("UI-VISUAL-007")
    def test_404_has_dashboard_link(self):
        """404 页面必须有返回 Dashboard 的链接。"""
        html = _render_404_template()
        assert '/dashboard' in html, "404 页面必须链接到 /dashboard"
        # 验证它看起来像一个正常的导航链接
        assert 'state-panel__link' in html, \
            "404 的 Dashboard 链接必须使用 state-panel__link 类"

    @pytest.mark.contract_case("UI-VISUAL-007")
    def test_500_has_dashboard_link(self):
        """500 错误页面必须有返回 Dashboard 的链接。"""
        html = _render_error_template()
        assert '/dashboard' in html, "错误页面必须链接到 /dashboard"
        assert 'state-panel__link' in html, \
            "错误的 Dashboard 链接必须使用 state-panel__link 类"
        assert "Dashboard" in html, "错误页面必须显示 'Dashboard' 链接文本"

    @pytest.mark.contract_case("UI-VISUAL-007")
    def test_404_has_primary_dashboard_label(self):
        """404 页面的主操作应清晰指向 Dashboard。"""
        html = _render_404_template()
        assert "Go to Dashboard" in html, \
            "404 页面必须提供清晰的 Dashboard 主操作"

    @pytest.mark.contract_case("UI-VISUAL-007")
    def test_500_has_primary_dashboard_label(self):
        """500 错误页面的主操作应清晰指向 Dashboard。"""
        html = _render_error_template()
        assert "Go to Dashboard" in html, \
            "错误页面必须提供清晰的 Dashboard 主操作"
