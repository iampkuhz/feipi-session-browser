"""Tests for sidebar collapse infrastructure in base.html.

The sidebar collapse mechanism uses body.hide-left class to toggle visibility.
Sidebar toggle buttons have been removed from the topbar; only CSS infrastructure remains.
"""

from __future__ import annotations


class TestSidebarCollapsedCSS:
    """Verify CSS supports hide-left class for sidebar hiding."""

    def test_hide_left_selector(self):
        """CSS should have body.hide-left .sidebar rule."""
        with open("src/session_browser/web/static/style.css") as f:
            content = f.read()
        assert "body.hide-left .sidebar" in content

    def test_hide_left_hides_sidebar(self):
        """CSS should hide sidebar when hide-left is active."""
        with open("src/session_browser/web/static/style.css") as f:
            content = f.read()
        assert "display: none" in content

    def test_old_sidebar_toggle_hidden(self):
        """Old .sidebar-toggle button should be hidden (deprecated)."""
        with open("src/session_browser/web/static/style.css") as f:
            content = f.read()
        assert ".sidebar-toggle" in content
        # The old button is deprecated and hidden
        assert "display: none" in content


class TestOldSidebarToggleDeprecated:
    """Verify old sidebar toggle buttons are deprecated and not rendered."""

    def test_no_sidebar_toggle_button(self):
        """Old class='sidebar-toggle' button should NOT be rendered."""
        with open("src/session_browser/web/templates/base.html") as f:
            content = f.read()
        # The old button class should not appear as a rendered element
        assert 'class="sidebar-toggle"' not in content

    def test_no_sidebar_toggle_expand_button(self):
        """Old class='sidebar-toggle-expand' button should NOT be rendered."""
        with open("src/session_browser/web/templates/base.html") as f:
            content = f.read()
        assert 'class="sidebar-toggle-expand"' not in content

    def test_old_buttons_hidden_in_css(self):
        """CSS should explicitly hide old toggle buttons."""
        with open("src/session_browser/web/static/style.css") as f:
            content = f.read()
        assert ".sidebar-toggle" in content
        assert "display: none" in content
