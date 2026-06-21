"""D-03 仪表盘 tooltip 定位静态检查。

契约要求：.dashboard-tooltip 不得使用 position: fixed（必须相对于 bar 定位）。
.bar 必须使用 position: relative 以作为 tooltip 锚点。

T007 — 仪表盘 tooltip 定位静态检查。
"""

from __future__ import annotations

import re

import pytest

_CSS_PATH = 'src/session_browser/web/static/css/dashboard.css'


def _read_css() -> str:
    with open(_CSS_PATH) as f:
        return f.read()


class TestDashboardTooltipContract:
    """静态 CSS 契约：仪表盘趋势 tooltip 不得使用 viewport fixed。"""

    def _get_tooltip_block(self) -> str:
        """从 CSS 中提取 .dashboard-tooltip 规则块。"""
        content = _read_css()
        match = re.search(r'\.dashboard-tooltip\s*\{([^}]+)\}', content)
        assert match, 'CSS 中必须包含 .dashboard-tooltip 规则'
        return match.group(1)

    def _get_bar_block(self) -> str:
        """从 CSS 中提取 .bar 规则块。"""
        content = _read_css()
        match = re.search(r'\.bar\s*\{([^}]+)\}', content)
        assert match, 'CSS 中必须包含 .bar 规则'
        return match.group(1)

    @pytest.mark.contract_case('ROUTE-API-005')
    def test_tooltip_not_fixed(self):
        """.dashboard-tooltip 不得包含 position: fixed。"""
        block = self._get_tooltip_block()
        position_decls = re.findall(r'position\s*:\s*(\S+)\s*;', block, re.IGNORECASE)
        assert 'fixed' not in [p.lower() for p in position_decls], (
            f'.dashboard-tooltip 不得使用 position: fixed；'
            f'当前 position: {position_decls}。'
            f'Tooltip 必须相对于 .bar 定位，而非 viewport。'
        )

    @pytest.mark.contract_case('ROUTE-API-005')
    def test_bar_is_relative(self):
        """.bar 必须包含 position: relative 以锚定 tooltip。"""
        block = self._get_bar_block()
        position_decls = re.findall(r'position\s*:\s*(\S+)\s*;', block, re.IGNORECASE)
        assert 'relative' in [p.lower() for p in position_decls], (
            f'.bar 必须使用 position: relative；'
            f'当前 position: {position_decls}。'
            f'bar 是 tooltip 的定位上下文。'
        )
