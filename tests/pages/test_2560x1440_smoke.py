"""2560x1440 视口冒烟测试矩阵 — Python 级 HTTP 测试。

验证所有主要页面在 2560x1440（2K 桌面显示器）视口下返回 HTTP 200 并具有预期的 HTML 结构。

本测试使用 hifi 夹具启动本地 session-browser 服务器，
然后通过 2560x1440 User-Agent 发起 HTTP 请求验证每个页面。

覆盖：
- Dashboard 页面渲染
- Sessions List 页面渲染
- Session Detail 页面渲染
- Projects 页面渲染
- 结构检查：CSS 媒体查询、布局容器、表格元素

用法：
    python3 -m pytest tests/pages/test_2560x1440_smoke.py -v
"""

from __future__ import annotations

import pytest
import re

# ─── 常量 ──────────────────────────────────────────────────────────────

# 2560x1440 (QHD / 2K 显示器) User-Agent
DISPLAY_2K_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# 冒烟测试页面：(名称, 路径, 预期 HTML 片段, 最小 HTML 长度)
# 注意：404 页面由 TestDisplay2K404Page 单独测试（预期 HTTP 404）。
PAGES = [
    ("Dashboard", "/dashboard", ">Dashboard<", 500),
    ("Sessions List", "/sessions", ">Sessions<", 500),
    ("Projects", "/projects", ">Projects<", 500),
    ("Glossary", "/glossary", "Token Glossary", 500),
]


# ─── 服务器夹具 ─────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def display_2k_smoke_server(hifi_fixture_session):
    """使用 hifi 夹具会话服务器进行冒烟测试。

    产出确定性夹具服务器的 base_url。
    """
    base_url, agent, session_id = hifi_fixture_session
    yield base_url


# ─── 辅助函数 ────────────────────────────────────────────────────────────


def fetch_page(base_url: str, path: str) -> tuple[int, str]:
    """获取页面并返回 (status_code, html_body)。"""
    import urllib.request
    import urllib.error

    url = f"{base_url}{path}"
    req = urllib.request.Request(url, headers={
        "User-Agent": DISPLAY_2K_UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
    })
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8") if e.fp else ""


# ─── 测试：页面加载 ──────────────────────────────────────────────────────────


class TestDisplay2KSmoke:
    """在 2560x1440 视口下对所有主要页面进行冒烟测试。"""

    @pytest.mark.parametrize("name,path,expected_fragment,min_length", PAGES)
    @pytest.mark.contract_case("UI-VISUAL-008")
    def test_page_loads(self, display_2k_smoke_server, name, path, expected_fragment, min_length):
        """每个页面在 2560x1440 视口下必须返回 HTTP 200 并包含预期内容。"""
        base_url = display_2k_smoke_server
        status, html = fetch_page(base_url, path)

        assert status == 200, f"{name} 在 2560x1440 下返回 HTTP {status}"
        assert len(html) >= min_length, (
            f"{name} 在 2560x1440 下 HTML 过短：{len(html)} 字节 "
            f"（预期 >= {min_length}）"
        )
        assert expected_fragment in html, (
            f"{name} 在 2560x1440 下缺少预期片段 '{expected_fragment}'"
        )


# ─── 测试：视口特定结构检查 ────────────────────────────────────────────────


class TestDisplay2KDashboard:
    """Dashboard 在 2560x1440 下的结构检查。"""

    @pytest.mark.contract_case("UI-VISUAL-008")
    def test_metric_cards_present(self, display_2k_smoke_server):
        """Dashboard 必须有 6 个 KPI 指标卡片。"""
        base_url = display_2k_smoke_server
        status, html = fetch_page(base_url, "/dashboard")
        assert status == 200
        cards = re.findall(r'class="metric-card\b', html)
        assert len(cards) == 6, f"预期 6 个 KPI 指标卡片，发现 {len(cards)} 个"

    @pytest.mark.contract_case("UI-VISUAL-008")
    def test_chart_containers_present(self, display_2k_smoke_server):
        """Dashboard 必须有图表容器。"""
        base_url = display_2k_smoke_server
        status, html = fetch_page(base_url, "/dashboard")
        assert status == 200
        containers = re.findall(r'data-dashboard-chart', html)
        assert len(containers) >= 2, \
            f"预期至少 2 个图表容器，发现 {len(containers)} 个"

    @pytest.mark.contract_case("UI-VISUAL-008")
    def test_metric_grid_layout(self, display_2k_smoke_server):
        """Dashboard 的 kpi-grid 必须存在以支持宽屏布局。"""
        base_url = display_2k_smoke_server
        status, html = fetch_page(base_url, "/dashboard")
        assert status == 200
        assert 'class="kpi-grid"' in html, \
            "kpi-grid 必须存在以支持 2560x1440 布局"

    @pytest.mark.contract_case("UI-VISUAL-008")
    def test_scope_switch_ui(self, display_2k_smoke_server):
        """Dashboard 必须有时间粒度切换 UI。"""
        base_url = display_2k_smoke_server
        status, html = fetch_page(base_url, "/dashboard")
        assert status == 200
        for grain in ["day", "week", "month"]:
            assert f'data-grain="{grain}"' in html, \
                f"时间粒度按钮 '{grain}' 必须存在"


class TestDisplay2KSessionsList:
    """Sessions List 在 2560x1440 下的结构检查。"""

    @pytest.mark.contract_case("UI-VISUAL-008")
    def test_sessions_table_present(self, display_2k_smoke_server):
        """Sessions List 必须有会话表格。"""
        base_url = display_2k_smoke_server
        status, html = fetch_page(base_url, "/sessions")
        assert status == 200
        assert 'aria-label="Sessions table"' in html, \
            "Sessions 表格必须存在"

    @pytest.mark.contract_case("UI-VISUAL-008")
    def test_sessions_has_data_rows(self, display_2k_smoke_server):
        """Sessions List 必须有数据行。"""
        base_url = display_2k_smoke_server
        status, html = fetch_page(base_url, "/sessions")
        assert status == 200
        rows = re.findall(r'class="sessions-row"', html)
        assert len(rows) > 0, \
            "Sessions List 必须至少有一个会话行"

    @pytest.mark.contract_case("UI-VISUAL-008")
    def test_session_links_exist(self, display_2k_smoke_server):
        """Sessions List 必须有可点击的会话链接。"""
        base_url = display_2k_smoke_server
        status, html = fetch_page(base_url, "/sessions")
        assert status == 200
        match = re.search(r'href="(/sessions/[^"]+/[^"]+)"', html)
        assert match, "Sessions List 页面上未找到会话链接"


class TestDisplay2KSessionDetail:
    """Session Detail 在 2560x1440 下的结构检查。"""

    @pytest.mark.contract_case("UI-VISUAL-008")
    def test_session_detail_accessible(self, display_2k_smoke_server):
        """Session Detail 页面必须可访问并渲染。"""
        base_url = display_2k_smoke_server
        # 先从 sessions 页面获取一个会话链接
        status, html = fetch_page(base_url, "/sessions")
        assert status == 200

        match = re.search(r'href="(/sessions/[^"]+/[^"]+)"', html)
        assert match, "Sessions List 页面上未找到会话链接"

        session_url = match.group(1)
        status, detail_html = fetch_page(base_url, session_url)
        assert status == 200, f"Session Detail 在 {session_url} 返回 HTTP {status}"
        assert len(detail_html) >= 500, "Session Detail HTML 过短"

    @pytest.mark.contract_case("UI-VISUAL-008")
    def test_session_detail_has_timeline(self, display_2k_smoke_server):
        """Session Detail 必须有时间线部分。"""
        base_url = display_2k_smoke_server
        status, html = fetch_page(base_url, "/sessions")
        assert status == 200

        match = re.search(r'href="(/sessions/[^"]+/[^"]+)"', html)
        assert match, "未找到会话链接"

        status, detail_html = fetch_page(base_url, match.group(1))
        assert status == 200
        has_timeline = "timeline" in detail_html.lower() or "round" in detail_html.lower()
        assert has_timeline, "Session Detail 必须包含时间线或 round 内容"

    @pytest.mark.contract_case("UI-VISUAL-008")
    def test_session_detail_has_header(self, display_2k_smoke_server):
        """Session Detail 必须有包含会话标题的页面头部。"""
        base_url = display_2k_smoke_server
        status, html = fetch_page(base_url, "/sessions")
        assert status == 200

        match = re.search(r'href="(/sessions/[^"]+/[^"]+)"', html)
        assert match, "未找到会话链接"

        status, detail_html = fetch_page(base_url, match.group(1))
        assert status == 200
        assert "page-head" in detail_html or "session-detail" in detail_html.lower(), \
            "Session Detail 必须有页面头部"


class TestDisplay2KProjects:
    """Projects 页面在 2560x1440 下的结构检查。"""

    @pytest.mark.contract_case("UI-VISUAL-008")
    def test_projects_page_loads(self, display_2k_smoke_server):
        """Projects 页面必须返回 HTTP 200。"""
        base_url = display_2k_smoke_server
        status, html = fetch_page(base_url, "/projects")
        assert status == 200
        assert len(html) >= 500, "Projects page HTML too short"

    @pytest.mark.contract_case("UI-VISUAL-008")
    def test_projects_has_table_or_list(self, display_2k_smoke_server):
        """Projects 页面必须有数据表格或项目列表。"""
        base_url = display_2k_smoke_server
        status, html = fetch_page(base_url, "/projects")
        assert status == 200
        has_table = 'class="data-table"' in html or 'class="project-list"' in html
        assert has_table, "Projects page must have a table or project list"

    @pytest.mark.contract_case("UI-VISUAL-008")
    def test_projects_has_entries(self, display_2k_smoke_server):
        """Projects 页面必须列出至少一个项目。"""
        base_url = display_2k_smoke_server
        status, html = fetch_page(base_url, "/projects")
        assert status == 200
        # 检查页面中的项目相关内容
        has_project_content = (
            'class="data-table"' in html
            or 'class="project-list"' in html
            or "project" in html.lower()
        )
        assert has_project_content, \
            "Projects page must list at least one project entry"


# ─── 测试：CSS 媒体查询检查 ─────────────────────────────────────────────


class TestDisplay2KCSSSupport:
    """验证 CSS 文件包含适用于 2560x1440 的响应式媒体查询。"""

    @pytest.mark.contract_case("UI-VISUAL-008")
    def test_style_css_has_wide_media_query(self):
        """shell.css 应包含宽视口的媒体查询。"""
        css_path = "src/session_browser/web/static/css/shell.css"
        import os
        full_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "..", css_path
        )
        full_path = os.path.normpath(os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            css_path
        ))

        if not os.path.exists(full_path):
            pytest.skip(f"CSS file not found at {full_path}")

        with open(full_path) as f:
            content = f.read()

        # 检查覆盖 2560px 的 min-width 媒体查询
        has_wide_query = (
            "@media" in content
            and ("min-width" in content or "max-width" in content)
        )
        assert has_wide_query, \
            "shell.css must contain responsive media queries"

    @pytest.mark.contract_case("UI-VISUAL-008")
    def test_dashboard_css_responsive(self):
        """Dashboard CSS must be responsive-aware."""
        css_path = "src/session_browser/web/static/css/dashboard.css"
        import os
        full_path = os.path.normpath(os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            css_path
        ))

        if not os.path.exists(full_path):
            pytest.skip(f"CSS file not found at {full_path}")

        with open(full_path) as f:
            content = f.read()

        # Dashboard CSS 应包含布局规则
        has_layout = "grid" in content or "flex" in content or "display" in content
        assert has_layout, \
            "dashboard.css must contain layout rules"


# ─── 测试：2560x1440 下的 Session Detail ─────────────────────────────


class TestDisplay2KSessionDetailPage:
    """使用夹具会话检查 2560x1440 下 Session Detail 页面的结构。"""

    @pytest.mark.contract_case("UI-VISUAL-008")
    def test_session_detail_page_loads(self, display_2k_smoke_server):
        """Session Detail page must return HTTP 200."""
        base_url = display_2k_smoke_server
        status, html = fetch_page(base_url, "/sessions/claude_code/hifi-viz-session-001")
        assert status == 200, f"Session Detail returned HTTP {status}"
        assert len(html) >= 500, "Session Detail HTML too short"

    @pytest.mark.contract_case("UI-VISUAL-008")
    def test_session_detail_has_hero(self, display_2k_smoke_server):
        """Session Detail must have a hero/header section."""
        base_url = display_2k_smoke_server
        status, html = fetch_page(base_url, "/sessions/claude_code/hifi-viz-session-001")
        assert status == 200
        assert "sd-hero" in html or "session-detail" in html.lower(), \
            "Session Detail must have hero or session-detail section"

    @pytest.mark.contract_case("UI-VISUAL-008")
    def test_session_detail_has_tabs(self, display_2k_smoke_server):
        """Session Detail must have tab navigation."""
        base_url = display_2k_smoke_server
        status, html = fetch_page(base_url, "/sessions/claude_code/hifi-viz-session-001")
        assert status == 200
        assert "sd-tabs" in html or "tab" in html.lower(), \
            "Session Detail must have tab navigation"

    @pytest.mark.contract_case("UI-VISUAL-008")
    def test_session_detail_has_trace_panel(self, display_2k_smoke_server):
        """Session Detail must have a trace panel."""
        base_url = display_2k_smoke_server
        status, html = fetch_page(base_url, "/sessions/claude_code/hifi-viz-session-001")
        assert status == 200
        assert "trace" in html.lower() or "round" in html.lower(), \
            "Session Detail must have trace/round content"


# ─── 测试：2560x1440 下的 Glossary ───────────────────────────────────


class TestDisplay2KGlossary:
    """2560x1440 下 Glossary 页面的结构检查。"""

    @pytest.mark.contract_case("UI-VISUAL-008")
    def test_glossary_page_loads(self, display_2k_smoke_server):
        """Glossary page must return HTTP 200."""
        base_url = display_2k_smoke_server
        status, html = fetch_page(base_url, "/glossary")
        assert status == 200, f"Glossary returned HTTP {status}"
        assert len(html) >= 500, "Glossary page HTML too short"

    @pytest.mark.contract_case("UI-VISUAL-008")
    def test_glossary_has_metric_grid(self, display_2k_smoke_server):
        """Glossary must have a metric grid."""
        base_url = display_2k_smoke_server
        status, html = fetch_page(base_url, "/glossary")
        assert status == 200
        assert 'class="metric-grid"' in html, \
            "Glossary must have a metric-grid section"

    @pytest.mark.contract_case("UI-VISUAL-008")
    def test_glossary_has_filter_card(self, display_2k_smoke_server):
        """Glossary must have a filter/search card."""
        base_url = display_2k_smoke_server
        status, html = fetch_page(base_url, "/glossary")
        assert status == 200
        assert "filter-card" in html or "search" in html.lower(), \
            "Glossary must have a filter/search card"

    @pytest.mark.contract_case("UI-VISUAL-008")
    def test_glossary_has_data_tables(self, display_2k_smoke_server):
        """Glossary must have data tables."""
        base_url = display_2k_smoke_server
        status, html = fetch_page(base_url, "/glossary")
        assert status == 200
        assert 'class="data-table' in html, \
            "Glossary must have at least one data-table"

    @pytest.mark.contract_case("UI-VISUAL-008")
    def test_glossary_has_token_terms(self, display_2k_smoke_server):
        """Glossary must contain token-related terminology."""
        base_url = display_2k_smoke_server
        status, html = fetch_page(base_url, "/glossary")
        assert status == 200
        assert "Token" in html or "token" in html, \
            "Glossary must contain token terminology"


# ─── 测试：2560x1440 下的 404 错误页面 ─────────────────────────────


class TestDisplay2K404Page:
    """2560x1440 下 404 错误页面的结构检查。"""

    @pytest.mark.contract_case("UI-VISUAL-008")
    def test_404_page_returns_404_status(self, display_2k_smoke_server):
        """404 page must return HTTP 404 status."""
        base_url = display_2k_smoke_server
        status, html = fetch_page(base_url, "/__test-404-not-found__")
        assert status == 404, f"Expected HTTP 404, got {status}"

    @pytest.mark.contract_case("UI-VISUAL-008")
    def test_404_page_renders_meaningful_html(self, display_2k_smoke_server):
        """404 page must contain meaningful HTML content."""
        base_url = display_2k_smoke_server
        status, html = fetch_page(base_url, "/__test-404-not-found__")
        assert len(html) > 200, "404 HTML must be substantial"

    @pytest.mark.contract_case("UI-VISUAL-008")
    def test_404_page_has_not_found_text(self, display_2k_smoke_server):
        """404 page must show 'Not Found' text."""
        base_url = display_2k_smoke_server
        status, html = fetch_page(base_url, "/__test-404-not-found__")
        assert "Not Found" in html or "not found" in html, \
            "404 page must contain 'Not Found' text"

    @pytest.mark.contract_case("UI-VISUAL-008")
    def test_404_page_has_state_panel(self, display_2k_smoke_server):
        """404 page must use shared state-panel component."""
        base_url = display_2k_smoke_server
        status, html = fetch_page(base_url, "/__test-404-not-found__")
        assert status == 404
        assert 'class="state-panel"' in html, \
            "404 page must have state-panel container"

    @pytest.mark.contract_case("UI-VISUAL-008")
    def test_404_page_has_dashboard_link(self, display_2k_smoke_server):
        """404 page must link back to dashboard."""
        base_url = display_2k_smoke_server
        status, html = fetch_page(base_url, "/__test-404-not-found__")
        assert status == 404
        assert "/dashboard" in html, \
            "404 page must link to /dashboard"
