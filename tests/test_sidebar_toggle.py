"""Tests for sidebar collapse toggle in base.html.

The sidebar collapse mechanism uses topbar buttons that toggle `hide-left`
on <body>. Old `.sidebar-toggle` / `.sidebar-toggle-expand` buttons are
deprecated and hidden via CSS. State persistence uses arpStorage with
the 'sidebar_collapsed' key (mapped to hide-left at init time).
"""

from __future__ import annotations


class TestSidebarToggleButtons:
    """Verify sidebar toggle buttons exist in topbar."""

    def test_hide_left_button_exists(self):
        """A topbar button for hiding sidebar should be present."""
        with open("src/session_browser/web/templates/base.html") as f:
            content = f.read()
        assert 'title="切换左侧导航"' in content

    def test_toggle_toggles_hide_left(self):
        """Toggle button must toggle the hide-left class."""
        with open("src/session_browser/web/templates/base.html") as f:
            content = f.read()
        assert "classList.toggle('hide-left')" in content

    def test_hide_right_button_exists(self):
        """A topbar button for hiding inspector should be present."""
        with open("src/session_browser/web/templates/base.html") as f:
            content = f.read()
        assert 'title="切换右侧面板"' in content
        assert "classList.toggle('hide-right')" in content

    def test_focus_mode_button_exists(self):
        """A topbar button for focus mode should be present."""
        with open("src/session_browser/web/templates/base.html") as f:
            content = f.read()
        assert 'title="专注模式"' in content


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


class TestSidebarPersistence:
    """Verify sidebar collapse state persistence uses arpStorage."""

    def test_persistence_key(self):
        """Should use 'sidebar_collapsed' as the localStorage key."""
        with open("src/session_browser/web/templates/base.html") as f:
            content = f.read()
        assert "'sidebar_collapsed'" in content

    def test_uses_arpstorage_get(self):
        """Should restore state via arpStorage.get."""
        with open("src/session_browser/web/templates/base.html") as f:
            content = f.read()
        assert "arpStorage.get(" in content

    def test_restores_hide_left_on_load(self):
        """Should add hide-left class when sidebar was previously collapsed."""
        with open("src/session_browser/web/templates/base.html") as f:
            content = f.read()
        assert "classList.add('hide-left')" in content


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
        assert ".sidebar-toggle {" in content
        assert "display: none" in content
