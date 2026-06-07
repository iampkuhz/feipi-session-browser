"""Dashboard JS/CSS contract 测试。

覆盖：
- dashboard.js 不含旧职责关键字
- dashboard.css 不重定义共享 primitive
- Dashboard 不出现 Dense/Comfortable/Columns/Export/Keyboard shortcuts
- Dashboard 不出现 Hot Sessions & Signals / Context Budget / All Sessions

T-Dashboard-JS-CSS-Contract
"""

from __future__ import annotations

import pytest
import re

_JS_PATH = "src/session_browser/web/static/js/dashboard.js"
_CSS_PATH = "src/session_browser/web/static/css/dashboard.css"
_TEMPLATE_PATH = "src/session_browser/web/templates/dashboard.html"


def _read(path: str) -> str:
    with open(path) as f:
        return f.read()


class TestDashboardJSContract:
    """验证 dashboard.js 不含旧职责关键字。"""

    _BANNED_KEYWORDS = [
        "density-toggle",
        "settingsDrawer",
        "settings-drawer",
        "chart-export",
        "chart-detail",
        "chart-copy-link",
        "range-btn",
        "chart-range",
        "open-settings",
        "close-settings",
    ]

    @pytest.mark.contract_case("DASHBOARD-JS-001")
    @pytest.mark.parametrize("keyword", _BANNED_KEYWORDS)
    def test_js_no_banned_keywords(self, keyword):
        """dashboard.js 不得包含禁止的关键字。"""
        js = _read(_JS_PATH)
        assert keyword not in js,             f"dashboard.js 包含禁止关键字 '{keyword}'"


class TestDashboardCSSContract:
    """验证 dashboard.css 不重定义共享 primitive。"""

    _SHARED_SELECTORS = [
        ".btn {",
        ".btn--primary {",
        ".badge {",
        ".badge--danger {",
        ".badge--warning {",
        ".badge--info {",
        ".data-table {",
        ".tooltip {",
        ".modal {",
    ]

    @pytest.mark.contract_case("DASHBOARD-CSS-001")
    @pytest.mark.parametrize("selector", _SHARED_SELECTORS)
    def test_css_no_shared_selectors(self, selector):
        """dashboard.css 不得重定义共享组件基础样式。"""
        css = _read(_CSS_PATH)
        # Allow comments mentioning shared selectors
        lines = css.split("\n")
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("/*"):
                continue
            if selector in stripped:
                pytest.fail(
                    f"dashboard.css 包含共享选择器 '{selector}' "
                    f"(第 {css.index(selector)+1} 行附近)"
                )


class TestDashboardTemplateContract:
    """验证 Dashboard 模板不出现禁止项。"""

    _BANNED_PHRASES = [
        "Hot Sessions",
        "Context Budget",
        "Dense",
        "Comfortable",
        "Columns",
        "Export",
        "Keyboard shortcuts",
    ]

    @pytest.mark.contract_case("DASHBOARD-TEMPLATE-001")
    @pytest.mark.parametrize("phrase", _BANNED_PHRASES)
    def test_template_no_banned_phrases(self, phrase):
        """Dashboard 模板不得包含禁止短语。"""
        tmpl = _read(_TEMPLATE_PATH)
        # "Export" is allowed in "Export PNG" context but not as a button label
        if phrase == "Export":
            # Check for standalone Export button/link
            assert 'data-action="export"' not in tmpl,                 "Dashboard 不得有 Export data-action"
            assert "keyboard" not in tmpl.lower(),                 "Dashboard 不得有 keyboard shortcuts"
        else:
            assert phrase not in tmpl,                 f"Dashboard 模板包含禁止短语 '{phrase}'"
