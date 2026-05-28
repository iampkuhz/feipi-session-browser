"""验证 base.html 中侧边栏折叠基础设施的测试。
侧边栏折叠机制使用 body.hide-left 类来切换可见性。
侧边栏切换按钮已从 topbar 移除；仅保留 CSS 基础设施。

注意：Shell 相关的 CSS 规则（.sidebar、body.hide-left、.sidebar-toggle）
自 Task 05 以来位于 css/shell.css 中，而非 style.css 中。
"""


from __future__ import annotations

import pytest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SHELL_CSS = REPO_ROOT / "src" / "session_browser" / "web" / "static" / "css" / "shell.css"


def _shell_css():
    return SHELL_CSS.read_text(encoding="utf-8")


class TestSidebarCollapsedCSS:
    """验证 CSS 支持 hide-left 类用于隐藏侧边栏。"""

    @pytest.mark.contract_case("UI-INTERACTION-001")
    def test_hide_left_selector(self):
        """CSS 应有 body.hide-left .sidebar 规则。"""
        content = _shell_css()
        assert "body.hide-left .sidebar" in content

    @pytest.mark.contract_case("UI-INTERACTION-001")
    def test_hide_left_hides_sidebar(self):
        """CSS 应在 hide-left 激活时隐藏侧边栏。"""
        content = _shell_css()
        assert "display: none" in content

    @pytest.mark.contract_case("UI-INTERACTION-001")
    def test_old_sidebar_toggle_hidden(self):
        """旧的 .sidebar-toggle 按钮应隐藏（已弃用）。"""
        content = _shell_css()
        assert ".sidebar-toggle" in content
        # 该旧按钮已弃用并隐藏
        assert "display: none" in content


class TestOldSidebarToggleDeprecated:
    """验证旧的侧边栏切换按钮未被渲染。"""

    @pytest.mark.contract_case("UI-INTERACTION-001")
    def test_no_sidebar_toggle_button(self):
        """旧的 class='sidebar-toggle' 按钮不应被渲染。"""
        with open("src/session_browser/web/templates/base.html") as f:
            content = f.read()
        # 该旧按钮类不应作为渲染元素出现
        assert 'class="sidebar-toggle"' not in content

    @pytest.mark.contract_case("UI-INTERACTION-001")
    def test_no_sidebar_toggle_expand_button(self):
        """旧的 class='sidebar-toggle-expand' 按钮不应被渲染。"""
        with open("src/session_browser/web/templates/base.html") as f:
            content = f.read()
        assert 'class="sidebar-toggle-expand"' not in content

    @pytest.mark.contract_case("UI-INTERACTION-001")
    def test_old_buttons_hidden_in_css(self):
        """CSS 应显式隐藏旧的切换按钮。"""
        content = _shell_css()
        assert ".sidebar-toggle" in content
        assert "display: none" in content
