"""Shell 契约测试（T054）。

验证 base.html 包含预期的 app-shell 结构，且
CSS 文件包含所需的 shell CSS 规则。

覆盖 ui-shell 规约：
  openspec/changes/contract-driven-ui-redesign/specs/ui-shell.md
"""
import pytest
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_DIR = ROOT / "src" / "session_browser" / "web" / "templates"
STATIC_DIR = ROOT / "src" / "session_browser" / "web" / "static"
BASE_HTML = TEMPLATE_DIR / "base.html"
STYLE_CSS = None  # style.css 已删除 — MHTML 现在打包模块化 CSS
SHELL_CSS = STATIC_DIR / "css" / "shell.css"
UI_PRIMITIVES_CSS = STATIC_DIR / "css" / "ui-primitives.css"
LEGACY_ALIASES_CSS = STATIC_DIR / "css" / "legacy-aliases.css"


def _base_source():
    """返回 base.html 文本，如果文件缺失则跳过测试。"""
    if not BASE_HTML.exists():
        pytest.skip(f"base.html not found at {BASE_HTML}")
    return BASE_HTML.read_text(encoding="utf-8")


def _shell_source():
    """返回 shell.css 文本，如果文件缺失则跳过测试。"""
    if not SHELL_CSS.exists():
        pytest.skip(f"shell.css not found at {SHELL_CSS}")
    return SHELL_CSS.read_text(encoding="utf-8")


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def base_text():
    return _base_source()


@pytest.fixture(scope="module")
def shell_text():
    return _shell_source()


def _ui_primitives_source():
    """返回 ui-primitives.css 文本，如果文件缺失则跳过测试。"""
    if not UI_PRIMITIVES_CSS.exists():
        pytest.skip(f"ui-primitives.css not found at {UI_PRIMITIVES_CSS}")
    return UI_PRIMITIVES_CSS.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def ui_primitives_text():
    return _ui_primitives_source()


# ── base.html shell structure ─────────────────────────────────────────────


class TestBaseHtmlShellStructure:
    """base.html 必须包含预期的 app-shell 容器层级。"""

    @pytest.mark.contract_case("UI-VISUAL-001", "UI-VISUAL-002")
    def test_app_shell_root_exists(self, base_text):
        """Root container must have .app-shell class."""
        assert "app-shell" in base_text, "base.html lacks .app-shell root container"

    @pytest.mark.contract_case("UI-VISUAL-001", "UI-VISUAL-002")
    def test_data_session_detail_shell_marker(self, base_text):
        """Root container must have data-session-detail-shell marker."""
        assert 'data-session-detail-shell' in base_text, \
            "base.html lacks data-session-detail-shell marker"

    @pytest.mark.contract_case("UI-VISUAL-001", "UI-VISUAL-002")
    def test_sidebar_aside_exists(self, base_text):
        """Sidebar must be an <aside class="sidebar"> element."""
        assert '<aside class="sidebar"' in base_text, \
            "base.html lacks <aside class=\"sidebar\">"

    @pytest.mark.contract_case("UI-VISUAL-001", "UI-VISUAL-002")
    def test_main_panel_exists(self, base_text):
        """Main content area must have .main-panel class."""
        assert "main-panel" in base_text, \
            "base.html lacks .main-panel class"

    @pytest.mark.contract_case("UI-VISUAL-001", "UI-VISUAL-002")
    def test_topbar_header_exists(self, base_text):
        """Topbar must be a <header class="topbar"> element."""
        assert 'class="topbar"' in base_text or "class='topbar" in base_text, \
            "base.html lacks .topbar header"

    @pytest.mark.contract_case("UI-VISUAL-001", "UI-VISUAL-002")
    def test_content_section_exists(self, base_text):
        """Content section must exist for page templates."""
        assert 'class="content"' in base_text or "class='content" in base_text, \
            "base.html lacks .content section"

    @pytest.mark.contract_case("UI-VISUAL-001", "UI-VISUAL-002")
    def test_footer_exists(self, base_text):
        """Footer element must exist."""
        assert 'class="footer"' in base_text or "class='footer" in base_text, \
            "base.html lacks .footer element"


# ── base.html navigation items ────────────────────────────────────────────


class TestBaseHtmlNavItems:
    """侧边栏必须包含所有所需的导航项及 data-action="nav-*"。"""

    # ui-shell 规约 1.2 节中定义的导航目标
    NAV_TARGETS = [
        "nav-dashboard",
        "nav-sessions",
        "nav-projects",
        "nav-agents",
        "nav-glossary",
    ]

    @pytest.mark.contract_case("UI-VISUAL-001", "UI-VISUAL-002")
    def test_has_nav_dashboard(self, base_text):
        assert 'data-action="nav-dashboard"' in base_text, \
            "Missing nav-dashboard"

    @pytest.mark.contract_case("UI-VISUAL-001", "UI-VISUAL-002")
    def test_has_nav_sessions(self, base_text):
        assert 'data-action="nav-sessions"' in base_text, \
            "Missing nav-sessions"

    @pytest.mark.contract_case("UI-VISUAL-001", "UI-VISUAL-002")
    def test_has_nav_projects(self, base_text):
        assert 'data-action="nav-projects"' in base_text, \
            "Missing nav-projects"

    @pytest.mark.contract_case("UI-VISUAL-001", "UI-VISUAL-002")
    def test_has_nav_agents(self, base_text):
        assert 'data-action="nav-agents"' in base_text, \
            "Missing nav-agents"

    @pytest.mark.contract_case("UI-VISUAL-001", "UI-VISUAL-002")
    def test_has_nav_glossary(self, base_text):
        assert 'data-action="nav-glossary"' in base_text, \
            "Missing nav-glossary"

    @pytest.mark.contract_case("UI-VISUAL-001", "UI-VISUAL-002")
    def test_nav_item_has_data_target(self, base_text):
        """每个导航项必须包含 data-target 属性。"""
        for target in ["dashboard", "sessions", "projects", "agents", "glossary"]:
            assert f'data-target="{target}"' in base_text, \
                f"Missing data-target=\"{target}\""

    @pytest.mark.contract_case("UI-VISUAL-001", "UI-VISUAL-002")
    def test_nav_list_container(self, base_text):
        """导航必须包裹在 <nav class="nav-list"> 中。"""
        assert 'class="nav-list"' in base_text, \
            "base.html lacks .nav-list container"


# ── base.html sidebar accessibility ───────────────────────────────────────


class TestBaseHtmlSidebarA11y:
    """侧边栏必须具有适当的 aria 属性。"""

    @pytest.mark.contract_case("UI-VISUAL-001", "UI-VISUAL-002")
    def test_sidebar_aria_label(self, base_text):
        """侧边栏 <aside> 必须包含 aria-label。"""
        assert '<aside class="sidebar" aria-label=' in base_text, \
            "Sidebar lacks aria-label"

    @pytest.mark.contract_case("UI-VISUAL-001", "UI-VISUAL-002")
    def test_nav_aria_label(self, base_text):
        """导航容器必须包含 aria-label。"""
        assert 'aria-label="主导航"' in base_text or 'aria-label="Primary navigation"' in base_text, \
            "Nav container lacks aria-label"

    @pytest.mark.contract_case("UI-VISUAL-001", "UI-VISUAL-002")
    def test_icon_aria_hidden(self, base_text):
        """导航图标应设置 aria-hidden 以支持无障碍访问。"""
        assert 'aria-hidden="true"' in base_text, \
            "Nav icons lack aria-hidden"


# ── base.html topbar ──────────────────────────────────────────────────────


class TestBaseHtmlTopbar:
    """顶栏必须包含面包屑导航和操作按钮。"""

    @pytest.mark.contract_case("UI-VISUAL-001", "UI-VISUAL-002")
    def test_breadcrumb_exists(self, base_text):
        """面包屑导航必须存在。"""
        assert 'class="breadcrumb' in base_text, \
            "Topbar lacks .breadcrumb"

    @pytest.mark.contract_case("UI-VISUAL-001", "UI-VISUAL-002")
    def test_breadcrumb_aria_label(self, base_text):
        """面包屑导航必须包含 aria-label。"""
        assert 'aria-label="页面导航"' in base_text or 'aria-label="Page navigation"' in base_text, \
            "Breadcrumb lacks aria-label"

    @pytest.mark.contract_case("UI-VISUAL-001", "UI-VISUAL-002")
    def test_top_actions_container(self, base_text):
        """顶部操作容器必须存在。"""
        assert 'class="top-actions"' in base_text, \
            "Topbar lacks .top-actions container"

    @pytest.mark.contract_case("UI-VISUAL-001", "UI-VISUAL-002")
    def test_topbar_actions_block(self, base_text):
        """顶栏操作块必须存在，供页面模板扩展。"""
        assert "{% block topbar_actions %}" in base_text, \
            "base.html lacks topbar_actions block"


# ── base.html brand card ──────────────────────────────────────────────────


class TestBaseHtmlBrandCard:
    """侧边栏中的品牌卡片结构。"""

    @pytest.mark.contract_case("UI-VISUAL-001", "UI-VISUAL-002")
    def test_brand_card_exists(self, base_text):
        assert 'class="brand-card"' in base_text, \
            "Missing .brand-card"

    @pytest.mark.contract_case("UI-VISUAL-001", "UI-VISUAL-002")
    def test_brand_title_text(self, base_text):
        assert "Agent Run Profiler" in base_text, \
            "Missing brand title text"

    @pytest.mark.contract_case("UI-VISUAL-001", "UI-VISUAL-002")
    def test_brand_mark_exists(self, base_text):
        assert 'class="brand-mark"' in base_text, \
            "Missing .brand-mark"

    @pytest.mark.contract_case("UI-VISUAL-001", "UI-VISUAL-002")
    def test_brand_meta_exists(self, base_text):
        assert 'class="brand-meta"' in base_text, \
            "Missing .brand-meta"


# ── CSS shell rules ───────────────────────────────────────────────────────


class TestCssShellRules:
    """shell.css 和模块化 CSS 文件必须包含所需的 shell CSS 规则。"""

    # 规则已移至 shell.css（任务 05）
    @pytest.mark.contract_case("UI-VISUAL-001", "UI-VISUAL-002")
    def test_app_shell_rule(self, shell_text):
        """.app-shell 规则必须存在于 shell.css 中。"""
        assert re.search(r'\.app-shell\s*\{', shell_text), \
            "shell.css lacks .app-shell rule"

    @pytest.mark.contract_case("UI-VISUAL-001", "UI-VISUAL-002")
    def test_sidebar_rule(self, shell_text):
        """.sidebar 规则必须存在于 shell.css 中。"""
        assert re.search(r'\.sidebar\s*\{', shell_text), \
            "shell.css lacks .sidebar rule"

    @pytest.mark.contract_case("UI-VISUAL-001", "UI-VISUAL-002")
    def test_main_panel_rule(self, shell_text):
        """.main-panel 规则必须存在于 shell.css 中。"""
        assert re.search(r'\.main-panel\s*\{', shell_text), \
            "shell.css lacks .main-panel rule"

    @pytest.mark.contract_case("UI-VISUAL-001", "UI-VISUAL-002")
    def test_topbar_rule(self, shell_text):
        """.topbar 规则必须存在于 shell.css 中。"""
        assert re.search(r'\.topbar\s*\{', shell_text), \
            "shell.css lacks .topbar rule"

    # 规则已迁移到模块化 CSS（原在 style.css 中）
    @pytest.mark.contract_case("UI-VISUAL-001", "UI-VISUAL-002")
    def test_breadcrumb_rule(self, ui_primitives_text):
        """.breadcrumb 规则必须存在于 ui-primitives.css 中（从 style.css 迁移）。"""
        assert re.search(r'\.breadcrumb\s*\{', ui_primitives_text), \
            "ui-primitives.css lacks .breadcrumb rule"

    @pytest.mark.contract_case("UI-VISUAL-001", "UI-VISUAL-002")
    def test_top_actions_rule(self, shell_text):
        """.top-actions 规则必须存在于 shell.css 中。"""
        assert re.search(r'\.top-actions\s*\{', shell_text), \
            "shell.css lacks .top-actions rule"

    @pytest.mark.contract_case("UI-VISUAL-001", "UI-VISUAL-002")
    def test_footer_rule(self, shell_text):
        """.footer 规则必须存在于 shell.css 中。"""
        assert re.search(r'\.footer\s*\{', shell_text), \
            "shell.css lacks .footer rule"

    # 注意：.brand-card、.nav-list、.nav-item 规则位于已删除的 style.css 中。
    # 这些类仍在 base.html 模板中用于结构。
    # 其样式现通过 CSS 变量和继承处理。
    # 上方的模板结构测试已验证这些类存在于 base.html 中。


# ── CSS responsive breakpoints ────────────────────────────────────────────


class TestCssResponsiveBreakpoints:
    """shell.css 必须包含 shell 的响应式断点。

    项目仅支持 MacBook Pro 13/14 英寸内置显示器
    和 2560x1440 外接显示器。不支持移动端/平板断点，
    也不应出现。
    """

    @pytest.mark.contract_case("UI-VISUAL-001", "UI-VISUAL-002")
    def test_no_mobile_breakpoint(self, shell_text):
        """不得包含低于 1024px 的移动端 @media max-width。"""
        assert not re.search(r'@media\s*\(max-width:\s*(480|600|767|768|820|900)\b', shell_text), \
            "shell.css should not have mobile breakpoint"

    @pytest.mark.contract_case("UI-VISUAL-001", "UI-VISUAL-002")
    def test_no_tablet_breakpoint(self, shell_text):
        """不得包含低于 1400px 的平板端 @media max-width。"""
        assert not re.search(r'@media\s*\(max-width:\s*(1023|1024|1180|1260|1320)\b', shell_text), \
            "shell.css should not have tablet breakpoint"

    @pytest.mark.contract_case("UI-VISUAL-001", "UI-VISUAL-002")
    def test_has_desktop_1400_breakpoint(self, shell_text):
        """必须包含 @media (min-width: 1400px) 用于桌面端。"""
        assert re.search(r'@media\s*\([^)]*min-width:\s*1400', shell_text), \
            "shell.css lacks desktop min-width: 1400px breakpoint"

    @pytest.mark.contract_case("UI-VISUAL-001", "UI-VISUAL-002")
    def test_sidebar_collapse_rule(self, shell_text):
        """必须包含 body.hide-left .sidebar 或类似的折叠规则。"""
        assert 'body.hide-left' in shell_text or 'body.sidebar-collapsed' in shell_text, \
            "shell.css lacks sidebar collapse rule"


# ── base.html shell blocks ────────────────────────────────────────────────


class TestBaseHtmlShellBlocks:
    """base.html 必须提供 Jinja 块用于 shell 自定义。"""

    @pytest.mark.contract_case("UI-VISUAL-001", "UI-VISUAL-002")
    def test_shell_class_block(self, base_text):
        """根容器上必须有 shell_class 块。"""
        assert "{% block shell_class %}" in base_text, \
            "base.html lacks shell_class block"

    @pytest.mark.contract_case("UI-VISUAL-001", "UI-VISUAL-002")
    def test_content_block(self, base_text):
        """必须有 content 块。"""
        assert "{% block content %}" in base_text, \
            "base.html lacks content block"

    @pytest.mark.contract_case("UI-VISUAL-001", "UI-VISUAL-002")
    def test_breadcrumb_block(self, base_text):
        """必须有 breadcrumb 块供页面覆写。"""
        assert "{% block breadcrumb %}" in base_text, \
            "base.html lacks breadcrumb block"

    @pytest.mark.contract_case("UI-VISUAL-001", "UI-VISUAL-002")
    def test_sidebar_nav_block(self, base_text):
        """必须有 sidebar_nav 块。"""
        assert "{% block sidebar_nav %}" in base_text, \
            "base.html lacks sidebar_nav block"

    @pytest.mark.contract_case("UI-VISUAL-001", "UI-VISUAL-002")
    def test_head_extra_block(self, base_text):
        """必须有 head_extra 块供页面引入 CSS。"""
        assert "{% block head_extra %}" in base_text, \
            "base.html lacks head_extra block"

    @pytest.mark.contract_case("UI-VISUAL-001", "UI-VISUAL-002")
    def test_shell_has_no_inspector(self, base_text):
        """shell 容器不得在 class 中引用 inspector。"""
        # The root container may have {% block shell_class %}, but
        # should not hardcode inspector-related classes
        assert "data-context-inspector" not in base_text, \
            "base.html must not contain data-context-inspector"
