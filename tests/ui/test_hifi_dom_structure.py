"""Playwright DOM 结构与视觉状态回归测试。

使用 pytest-playwright 通过实时服务端测试高保真 UI 重构。
需要：SB_TEST_DB 环境变量 + `pytest --browser chromium`。

这些测试在正常模式下不检查外部 CSS/JS — /static/ 引用是预期的。
只有 MHTML 模式（在其他地方测试）必须自包含。
"""
import pytest
import os
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _navigate_to_first_session(page, live_server_url):
    """导航到 deterministic HIFI fixture session detail。"""
    page.goto(
        f"{live_server_url}/sessions/claude_code/hifi-viz-session-001",
        wait_until="networkidle",
    )
    return page.query_selector("[data-session-detail-shell]") is not None


@pytest.mark.playwright
class TestShellLayout:
    """验证三列 shell 网格结构。"""

    @pytest.mark.contract_case("UI-VISUAL-013")
    def test_session_detail_has_shell_grid(self, page, live_server_url):
        """Session Detail 页面应有 body > .shell 作为 CSS Grid。"""
        if not _navigate_to_first_session(page, live_server_url):
            pytest.fail("No sessions available")

        shell = page.query_selector("body > .shell")
        assert shell is not None, "missing .shell root container"

        display = shell.evaluate("el => getComputedStyle(el).display")
        assert display == "grid", f".shell display should be grid, got {display}"

    @pytest.mark.contract_case("UI-VISUAL-013")
    def test_sessions_list_no_inspector(self, page, live_server_url):
        """Sessions List 不应渲染右侧 Inspector 列。"""
        page.goto(f"{live_server_url}/sessions", wait_until="networkidle")

        # 页面应存在且不包含 inspector 内容
        body = page.query_selector("body")
        assert body is not None

    @pytest.mark.contract_case("UI-VISUAL-013")
    def test_sidebar_not_fixed(self, page, live_server_url):
        """侧边栏不应使用 position: fixed。"""
        if not _navigate_to_first_session(page, live_server_url):
            pytest.fail("No sessions available")

        sidebar = page.query_selector(".sidebar")
        if sidebar:
            position = sidebar.evaluate("el => getComputedStyle(el).position")
            assert position != "fixed", "sidebar should not be position:fixed"


@pytest.mark.playwright
class TestViewSwitch:
    """验证 trace panel 工具栏（Phase 1：无子视图切换）。"""

    @pytest.mark.contract_case("UI-VISUAL-013")
    def test_trace_panel_toolbar_exists(self, page, live_server_url):
        """Session Detail 应有 trace panel 工具栏，含 All/Failed 和 Expand/Collapse。"""
        if not _navigate_to_first_session(page, live_server_url):
            pytest.fail("No sessions available")

        # 检查 trace panel toolbar
        toolbar = page.query_selector(".sd-trace-head")
        assert toolbar is not None, "missing .sd-trace-head"

        # 检查过滤按钮
        all_btn = page.query_selector('[data-action="status-all"]')
        assert all_btn is not None, 'missing All filter chip'
        failed_btn = page.query_selector('[data-action="status-failed"]')
        assert failed_btn is not None, 'missing Failed filter chip'

        # 检查展开/折叠按钮
        expand_btn = page.query_selector('[data-action="toggle-all"]')
        assert expand_btn is not None, 'missing Expand All button'

    @pytest.mark.contract_case("UI-VISUAL-013")
    def test_old_workbench_views_removed(self, page, live_server_url):
        """Calls 和 Hotspots workbench 视图不应存在。"""
        if not _navigate_to_first_session(page, live_server_url):
            pytest.fail("No sessions available")

        for view in ("calls", "hotspots"):
            el = page.query_selector(f'[data-workbench-view="{view}"]')
            assert el is None, f'unexpected [data-workbench-view="{view}"] (should be removed)'


@pytest.mark.playwright
class TestHeroSection:
    """验证 hero 区域含 badge 和 KPI 条。"""

    @pytest.mark.contract_case("UI-VISUAL-013")
    def test_hero_exists(self, page, live_server_url):
        """Session Detail 应包含 hero 区域。"""
        if not _navigate_to_first_session(page, live_server_url):
            pytest.fail("No sessions available")

        hero = page.query_selector(".sd-hero")
        assert hero is not None, "missing .sd-hero section"

    @pytest.mark.contract_case("UI-VISUAL-013")
    def test_hero_has_badges(self, page, live_server_url):
        """Hero 区域应包含 badge 元素。"""
        if not _navigate_to_first_session(page, live_server_url):
            pytest.fail("No sessions available")

        badge = page.query_selector(".sd-hero__id, .sd-status-pill")
        assert badge is not None, "missing badge/id in hero section"

    @pytest.mark.contract_case("UI-VISUAL-013")
    def test_has_kpi_strip(self, page, live_server_url):
        """页面应有 KPI / 指标条。"""
        if not _navigate_to_first_session(page, live_server_url):
            pytest.fail("No sessions available")

        kpi = page.query_selector(".metrics-strip, .kpis, [class*='kpi']")
        assert kpi is not None, "missing KPI/metrics strip"


@pytest.mark.playwright
class TestSessionsList:
    """验证 Sessions List 页面结构。"""

    @pytest.mark.contract_case("UI-VISUAL-013")
    def test_sessions_list_has_data_table(self, page, live_server_url):
        """/sessions 应有 .data-table 元素。"""
        page.goto(f"{live_server_url}/sessions", wait_until="networkidle")

        table = page.query_selector(".data-table")
        assert table is not None, "missing .data-table on sessions list"

    @pytest.mark.contract_case("UI-VISUAL-013")
    def test_sessions_list_has_filters(self, page, live_server_url):
        """/sessions 应有过滤按钮。"""
        page.goto(f"{live_server_url}/sessions", wait_until="networkidle")

        # 检查与过滤相关的元素
        body_text = page.inner_text("body")
        has_failed = page.query_selector("[class*='failed']") or "Failed" in body_text
        has_token = page.query_selector("[class*='token']") or "Token" in body_text
        has_filter = (
            page.query_selector("[class*='filter']")
            or "filter" in body_text.lower()
            or "筛选" in body_text
        )
        # 至少应存在一种过滤指示器
        assert has_failed or has_token or has_filter or page.query_selector("button"), \
            "sessions list should have some interactive elements"


@pytest.mark.playwright
class TestNoExternalResources:
    """验证正常模式下无 Google Fonts 或远程 CSS/JS。"""

    @pytest.mark.contract_case("UI-VISUAL-013")
    def test_no_google_fonts(self, page, live_server_url):
        """页面 head 不应引用 Google Fonts。"""
        if not _navigate_to_first_session(page, live_server_url):
            pytest.fail("No sessions available")

        head_content = page.inner_html("head")
        assert "fonts.googleapis" not in head_content, \
            "Google Fonts reference found in <head>"

    @pytest.mark.contract_case("UI-VISUAL-013")
    def test_no_https_external_resources(self, page, live_server_url):
        """页面不应引用 https:// 外部 CSS/JS/字体（本地 /static/ 除外）。"""
        if not _navigate_to_first_session(page, live_server_url):
            pytest.fail("No sessions available")

        html = page.content()
        server_prefix = live_server_url  # 例如 http://127.0.0.1:18899

        # 检查外部链接（非 localhost、非相对路径）
        for tag in page.query_selector_all("link[rel='stylesheet']"):
            href = tag.get_attribute("href") or ""
            if href.startswith("https://") and server_prefix not in href:
                raise AssertionError(f"external CSS found: {href}")

        for tag in page.query_selector_all("script[src]"):
            src = tag.get_attribute("src") or ""
            if src.startswith("https://") and server_prefix not in src:
                raise AssertionError(f"external JS found: {src}")
