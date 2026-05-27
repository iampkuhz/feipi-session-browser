"""Tests for sidebar collapse infrastructure in base.html.
The sidebar collapse mechanism uses body.hide-left class to toggle visibility.
Sidebar toggle buttons have been removed from the topbar; only CSS infrastructure remains.

Note: Shell-related CSS rules (.sidebar, body.hide-left, .sidebar-toggle) are in
css/shell.css since Task 05, not in style.css.
"""


from __future__ import annotations

import pytest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SHELL_CSS = REPO_ROOT / "src" / "session_browser" / "web" / "static" / "css" / "shell.css"


def _shell_css():
    return SHELL_CSS.read_text(encoding="utf-8")


class TestSidebarCollapsedCSS:
    """Verify CSS supports hide-left class for sidebar hiding."""

    @pytest.mark.contract_case("UI-INTERACTION-001")
    def test_hide_left_selector(self):
        """CSS should have body.hide-left .sidebar rule."""
        content = _shell_css()
        assert "body.hide-left .sidebar" in content

    @pytest.mark.contract_case("UI-INTERACTION-001")
    def test_hide_left_hides_sidebar(self):
        """CSS should hide sidebar when hide-left is active."""
        content = _shell_css()
        assert "display: none" in content

    @pytest.mark.contract_case("UI-INTERACTION-001")
    def test_old_sidebar_toggle_hidden(self):
        """Old .sidebar-toggle button should be hidden (deprecated)."""
        content = _shell_css()
        assert ".sidebar-toggle" in content
        # The old button is deprecated and hidden
        assert "display: none" in content


class TestOldSidebarToggleDeprecated:
    """Verify old sidebar toggle buttons are not rendered."""

    @pytest.mark.contract_case("UI-INTERACTION-001")
    def test_no_sidebar_toggle_button(self):
        """Old class='sidebar-toggle' button should NOT be rendered."""
        with open("src/session_browser/web/templates/base.html") as f:
            content = f.read()
        # The old button class should not appear as a rendered element
        assert 'class="sidebar-toggle"' not in content

    @pytest.mark.contract_case("UI-INTERACTION-001")
    def test_no_sidebar_toggle_expand_button(self):
        """Old class='sidebar-toggle-expand' button should NOT be rendered."""
        with open("src/session_browser/web/templates/base.html") as f:
            content = f.read()
        assert 'class="sidebar-toggle-expand"' not in content

    @pytest.mark.contract_case("UI-INTERACTION-001")
    def test_old_buttons_hidden_in_css(self):
        """CSS should explicitly hide old toggle buttons."""
        content = _shell_css()
        assert ".sidebar-toggle" in content
        assert "display: none" in content
