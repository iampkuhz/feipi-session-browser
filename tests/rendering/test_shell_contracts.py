"""Shell contract tests (T054).

Verifies that base.html contains the expected app-shell structure and that
CSS files contain required shell CSS rules.

Covers ui-shell spec at:
  openspec/changes/contract-driven-ui-redesign/specs/ui-shell.md
"""
from pathlib import Path
import re

import pytest

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_DIR = ROOT / "src" / "session_browser" / "web" / "templates"
STATIC_DIR = ROOT / "src" / "session_browser" / "web" / "static"
BASE_HTML = TEMPLATE_DIR / "base.html"
STYLE_CSS = None  # style.css deleted — MHTML now bundles modular CSS
SHELL_CSS = STATIC_DIR / "css" / "shell.css"
UI_PRIMITIVES_CSS = STATIC_DIR / "css" / "ui-primitives.css"
LEGACY_ALIASES_CSS = STATIC_DIR / "css" / "legacy-aliases.css"


def _base_source():
    """Return base.html text, skipping tests if file is missing."""
    if not BASE_HTML.exists():
        pytest.skip(f"base.html not found at {BASE_HTML}")
    return BASE_HTML.read_text(encoding="utf-8")


def _shell_source():
    """Return shell.css text, skipping tests if file is missing."""
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
    """Return ui-primitives.css text, skipping tests if file is missing."""
    if not UI_PRIMITIVES_CSS.exists():
        pytest.skip(f"ui-primitives.css not found at {UI_PRIMITIVES_CSS}")
    return UI_PRIMITIVES_CSS.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def ui_primitives_text():
    return _ui_primitives_source()


# ── base.html shell structure ─────────────────────────────────────────────


class TestBaseHtmlShellStructure:
    """base.html must contain the expected app-shell container hierarchy."""

    def test_app_shell_root_exists(self, base_text):
        """Root container must have .app-shell class."""
        assert "app-shell" in base_text, "base.html lacks .app-shell root container"

    def test_data_session_detail_shell_marker(self, base_text):
        """Root container must have data-session-detail-shell marker."""
        assert 'data-session-detail-shell' in base_text, \
            "base.html lacks data-session-detail-shell marker"

    def test_sidebar_aside_exists(self, base_text):
        """Sidebar must be an <aside class="sidebar"> element."""
        assert '<aside class="sidebar"' in base_text, \
            "base.html lacks <aside class=\"sidebar\">"

    def test_main_panel_exists(self, base_text):
        """Main content area must have .main-panel class."""
        assert "main-panel" in base_text, \
            "base.html lacks .main-panel class"

    def test_topbar_header_exists(self, base_text):
        """Topbar must be a <header class="topbar"> element."""
        assert 'class="topbar"' in base_text or "class='topbar" in base_text, \
            "base.html lacks .topbar header"

    def test_content_section_exists(self, base_text):
        """Content section must exist for page templates."""
        assert 'class="content"' in base_text or "class='content" in base_text, \
            "base.html lacks .content section"

    def test_footer_exists(self, base_text):
        """Footer element must exist."""
        assert 'class="footer"' in base_text or "class='footer" in base_text, \
            "base.html lacks .footer element"


# ── base.html navigation items ────────────────────────────────────────────


class TestBaseHtmlNavItems:
    """Sidebar must contain all required nav items with data-action="nav-*"."""

    # Expected nav targets as defined in ui-shell spec section 1.2
    NAV_TARGETS = [
        "nav-dashboard",
        "nav-sessions",
        "nav-projects",
        "nav-agents",
        "nav-glossary",
    ]

    def test_has_nav_dashboard(self, base_text):
        assert 'data-action="nav-dashboard"' in base_text, \
            "Missing nav-dashboard"

    def test_has_nav_sessions(self, base_text):
        assert 'data-action="nav-sessions"' in base_text, \
            "Missing nav-sessions"

    def test_has_nav_projects(self, base_text):
        assert 'data-action="nav-projects"' in base_text, \
            "Missing nav-projects"

    def test_has_nav_agents(self, base_text):
        assert 'data-action="nav-agents"' in base_text, \
            "Missing nav-agents"

    def test_has_nav_glossary(self, base_text):
        assert 'data-action="nav-glossary"' in base_text, \
            "Missing nav-glossary"

    def test_nav_item_has_data_target(self, base_text):
        """Each nav-item must have a data-target attribute."""
        for target in ["dashboard", "sessions", "projects", "agents", "glossary"]:
            assert f'data-target="{target}"' in base_text, \
                f"Missing data-target=\"{target}\""

    def test_nav_list_container(self, base_text):
        """Navigation must be wrapped in <nav class="nav-list">."""
        assert 'class="nav-list"' in base_text, \
            "base.html lacks .nav-list container"


# ── base.html sidebar accessibility ───────────────────────────────────────


class TestBaseHtmlSidebarA11y:
    """Sidebar must have proper aria attributes."""

    def test_sidebar_aria_label(self, base_text):
        """Sidebar <aside> must have aria-label."""
        assert '<aside class="sidebar" aria-label=' in base_text, \
            "Sidebar lacks aria-label"

    def test_nav_aria_label(self, base_text):
        """Nav container must have aria-label."""
        assert 'aria-label="主导航"' in base_text or 'aria-label="Primary navigation"' in base_text, \
            "Nav container lacks aria-label"

    def test_icon_aria_hidden(self, base_text):
        """Nav icons should have aria-hidden for accessibility."""
        assert 'aria-hidden="true"' in base_text, \
            "Nav icons lack aria-hidden"


# ── base.html topbar ──────────────────────────────────────────────────────


class TestBaseHtmlTopbar:
    """Topbar must contain breadcrumb and actions."""

    def test_breadcrumb_exists(self, base_text):
        """Breadcrumb navigation must exist."""
        assert 'class="breadcrumb' in base_text, \
            "Topbar lacks .breadcrumb"

    def test_breadcrumb_aria_label(self, base_text):
        """Breadcrumb must have aria-label."""
        assert 'aria-label="页面导航"' in base_text or 'aria-label="Page navigation"' in base_text, \
            "Breadcrumb lacks aria-label"

    def test_top_actions_container(self, base_text):
        """Top actions container must exist."""
        assert 'class="top-actions"' in base_text, \
            "Topbar lacks .top-actions container"

    def test_topbar_actions_block(self, base_text):
        """Topbar actions block must exist for page extensions."""
        assert "{% block topbar_actions %}" in base_text, \
            "base.html lacks topbar_actions block"


# ── base.html brand card ──────────────────────────────────────────────────


class TestBaseHtmlBrandCard:
    """Brand card structure in sidebar."""

    def test_brand_card_exists(self, base_text):
        assert 'class="brand-card"' in base_text, \
            "Missing .brand-card"

    def test_brand_title_text(self, base_text):
        assert "Agent Run Profiler" in base_text, \
            "Missing brand title text"

    def test_brand_mark_exists(self, base_text):
        assert 'class="brand-mark"' in base_text, \
            "Missing .brand-mark"

    def test_brand_meta_exists(self, base_text):
        assert 'class="brand-meta"' in base_text, \
            "Missing .brand-meta"


# ── CSS shell rules ───────────────────────────────────────────────────────


class TestCssShellRules:
    """shell.css and modular CSS files must contain required shell CSS rules."""

    # Rules moved to shell.css (Task 05)
    def test_app_shell_rule(self, shell_text):
        """.app-shell rule must exist in shell.css."""
        assert re.search(r'\.app-shell\s*\{', shell_text), \
            "shell.css lacks .app-shell rule"

    def test_sidebar_rule(self, shell_text):
        """.sidebar rule must exist in shell.css."""
        assert re.search(r'\.sidebar\s*\{', shell_text), \
            "shell.css lacks .sidebar rule"

    def test_main_panel_rule(self, shell_text):
        """.main-panel rule must exist in shell.css."""
        assert re.search(r'\.main-panel\s*\{', shell_text), \
            "shell.css lacks .main-panel rule"

    def test_topbar_rule(self, shell_text):
        """.topbar rule must exist in shell.css."""
        assert re.search(r'\.topbar\s*\{', shell_text), \
            "shell.css lacks .topbar rule"

    # Rules remaining in style.css
    def test_breadcrumb_rule(self, ui_primitives_text):
        """.breadcrumb rule must exist in ui-primitives.css (migrated from style.css)."""
        assert re.search(r'\.breadcrumb\s*\{', ui_primitives_text), \
            "ui-primitives.css lacks .breadcrumb rule"

    def test_top_actions_rule(self, shell_text):
        """.top-actions rule must exist in shell.css."""
        assert re.search(r'\.top-actions\s*\{', shell_text), \
            "shell.css lacks .top-actions rule"

    def test_footer_rule(self, shell_text):
        """.footer rule must exist in shell.css."""
        assert re.search(r'\.footer\s*\{', shell_text), \
            "shell.css lacks .footer rule"

    # NOTE: .brand-card, .nav-list, .nav-item rules were in the deleted style.css.
    # These classes are still used in base.html templates for structure.
    # Their styling is now handled through CSS variables and inheritance.
    # The template structure tests above verify the classes exist in base.html.


# ── CSS responsive breakpoints ────────────────────────────────────────────


class TestCssResponsiveBreakpoints:
    """shell.css must contain responsive breakpoints for shell.

    Project only supports MacBook Pro 13/14 inch built-in displays
    and 2560x1440 external monitors. Mobile/tablet breakpoints
    are not supported and should not be present.
    """

    def test_no_mobile_breakpoint(self, shell_text):
        """Must NOT have mobile @media max-width below 1024px."""
        assert not re.search(r'@media\s*\(max-width:\s*(480|600|767|768|820|900)\b', shell_text), \
            "shell.css should not have mobile breakpoint"

    def test_no_tablet_breakpoint(self, shell_text):
        """Must NOT have tablet @media max-width below 1400px."""
        assert not re.search(r'@media\s*\(max-width:\s*(1023|1024|1180|1260|1320)\b', shell_text), \
            "shell.css should not have tablet breakpoint"

    def test_has_desktop_1400_breakpoint(self, shell_text):
        """Must have @media (min-width: 1400px) for desktop."""
        assert re.search(r'@media\s*\([^)]*min-width:\s*1400', shell_text), \
            "shell.css lacks desktop min-width: 1400px breakpoint"

    def test_sidebar_collapse_rule(self, shell_text):
        """Must have body.hide-left .sidebar or similar collapse rule."""
        assert 'body.hide-left' in shell_text or 'body.sidebar-collapsed' in shell_text, \
            "shell.css lacks sidebar collapse rule"


# ── base.html shell blocks ────────────────────────────────────────────────


class TestBaseHtmlShellBlocks:
    """base.html must provide Jinja blocks for shell customization."""

    def test_shell_class_block(self, base_text):
        """Must have shell_class block on root container."""
        assert "{% block shell_class %}" in base_text, \
            "base.html lacks shell_class block"

    def test_content_block(self, base_text):
        """Must have content block."""
        assert "{% block content %}" in base_text, \
            "base.html lacks content block"

    def test_breadcrumb_block(self, base_text):
        """Must have breadcrumb block for page override."""
        assert "{% block breadcrumb %}" in base_text, \
            "base.html lacks breadcrumb block"

    def test_sidebar_nav_block(self, base_text):
        """Must have sidebar_nav block."""
        assert "{% block sidebar_nav %}" in base_text, \
            "base.html lacks sidebar_nav block"

    def test_head_extra_block(self, base_text):
        """Must have head_extra block for page CSS."""
        assert "{% block head_extra %}" in base_text, \
            "base.html lacks head_extra block"

    def test_shell_has_no_inspector(self, base_text):
        """shell container must not reference inspector in class."""
        # The root container may have {% block shell_class %}, but
        # should not hardcode inspector-related classes
        assert "data-context-inspector" not in base_text, \
            "base.html must not contain data-context-inspector"
