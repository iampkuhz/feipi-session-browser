"""D-03 Dashboard tooltip positioning static gate.

Contract: .dashboard-tooltip must NOT use position: fixed (must be relative to bar).
.bar must use position: relative to serve as tooltip anchor.

T007 — Dashboard tooltip positioning static gate.
"""

from __future__ import annotations

import pytest
import re

_CSS_PATH = "src/session_browser/web/static/css/dashboard.css"


def _read_css() -> str:
    with open(_CSS_PATH) as f:
        return f.read()


class TestDashboardTooltipContract:
    """Static CSS contract: dashboard trend tooltip must not use viewport fixed."""

    def _get_tooltip_block(self) -> str:
        """Extract the .dashboard-tooltip rule block from CSS."""
        content = _read_css()
        match = re.search(
            r'\.dashboard-tooltip\s*\{([^}]+)\}', content
        )
        assert match, "CSS must contain a .dashboard-tooltip rule"
        return match.group(1)

    def _get_bar_block(self) -> str:
        """Extract the .bar rule block from CSS."""
        content = _read_css()
        match = re.search(
            r'\.bar\s*\{([^}]+)\}', content
        )
        assert match, "CSS must contain a .bar rule"
        return match.group(1)

    @pytest.mark.contract_case("ROUTE-API-005")
    def test_tooltip_not_fixed(self):
        """.dashboard-tooltip must NOT contain position: fixed."""
        block = self._get_tooltip_block()
        position_decls = re.findall(
            r'position\s*:\s*(\S+)\s*;', block, re.IGNORECASE
        )
        assert 'fixed' not in [p.lower() for p in position_decls], (
            f".dashboard-tooltip must not use position: fixed; "
            f"found position: {position_decls}. "
            f"Tooltip must be positioned relative to .bar, not viewport."
        )

    @pytest.mark.contract_case("ROUTE-API-005")
    def test_bar_is_relative(self):
        """.bar must contain position: relative to anchor the tooltip."""
        block = self._get_bar_block()
        position_decls = re.findall(
            r'position\s*:\s*(\S+)\s*;', block, re.IGNORECASE
        )
        assert 'relative' in [p.lower() for p in position_decls], (
            f".bar must use position: relative; "
            f"found position: {position_decls}. "
            f"The bar is the tooltip's positioning context."
        )
