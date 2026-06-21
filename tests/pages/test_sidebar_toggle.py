"""验证 base.html 中侧边栏折叠基础设施的测试。
侧边栏折叠机制使用 body.hide-left 类来切换可见性。

Shell 相关的 CSS 规则位于 css/shell.css 中。
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SHELL_CSS = REPO_ROOT / 'src' / 'session_browser' / 'web' / 'static' / 'css' / 'shell.css'


def _shell_css():
    return SHELL_CSS.read_text(encoding='utf-8')


class TestSidebarCollapsedCSS:
    """验证 CSS 支持 hide-left 类用于隐藏侧边栏。"""

    @pytest.mark.contract_case('UI-INTERACTION-001')
    def test_hide_left_selector(self):
        """CSS 应有 body.hide-left .sidebar 规则。"""
        content = _shell_css()
        assert 'body.hide-left .sidebar' in content

    @pytest.mark.contract_case('UI-INTERACTION-001')
    def test_hide_left_hides_sidebar(self):
        """CSS 应在 hide-left 激活时隐藏侧边栏。"""
        content = _shell_css()
        assert 'display: none' in content
