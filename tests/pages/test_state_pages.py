"""Tests for State Pages (404.html, error.html).

Page-level pytest for state pages covering template structure, .state-panel
class, ARIA roles, aria-hidden on icons, navigation links, absence of inline
styles/scripts, and conditional error details rendering.

T178 -- State Pages: Add page-specific pytest.
"""

from __future__ import annotations

import pytest
import os
import re

_404_PATH = "src/session_browser/web/templates/404.html"
_ERROR_PATH = "src/session_browser/web/templates/error.html"


def _read(path: str) -> str:
    with open(path) as f:
        return f.read()


def _read_404() -> str:
    return _read(_404_PATH)


def _read_error() -> str:
    return _read(_ERROR_PATH)


# -- Test404Template --------------------------------------------------------


class Test404Template:
    """Verify the 404.html Jinja2 template structure."""

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_template_file_exists(self):
        """404.html must exist on disk."""
        assert os.path.isfile(_404_PATH), \
            f"{_404_PATH} must exist"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_extends_base(self):
        """404 must extend base.html."""
        content = _read_404()
        assert '{% extends "base.html" %}' in content, \
            "404 must extend base.html"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_title_block(self):
        """404 must set a descriptive page title."""
        content = _read_404()
        assert "Not Found" in content, \
            "404 title must contain 'Not Found'"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_states_css_import(self):
        """404 must import states.css via head_extra block."""
        content = _read_404()
        assert 'href="/static/css/states.css"' in content, \
            "404 must import states.css"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_no_page_specific_js(self):
        """404 must not import page-specific JS (states.js not needed for static page)."""
        content = _read_404()
        assert 'states.js' not in content, \
            "404 must not import states.js (static page, no JS needed)"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_head_extra_block(self):
        """404 must use head_extra block for CSS import."""
        content = _read_404()
        assert '{% block head_extra %}' in content, \
            "404 must use head_extra block"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_topbar_toggles_empty(self):
        """404 must suppress topbar toggles."""
        content = _read_404()
        assert '{% block topbar_toggles %}{% endblock %}' in content, \
            "404 must define empty topbar_toggles block"


# -- Test404Breadcrumb ------------------------------------------------------


class Test404Breadcrumb:
    """Verify 404 breadcrumb structure."""

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_breadcrumb_dashboard_link(self):
        """Breadcrumb must link to /dashboard."""
        content = _read_404()
        assert 'href="/dashboard"' in content, \
            "404 breadcrumb must link to /dashboard"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_breadcrumb_current(self):
        """Breadcrumb must show current page label."""
        content = _read_404()
        assert "Not Found" in content, \
            "404 breadcrumb must show 'Not Found' as current"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_breadcrumb_separator(self):
        """Breadcrumb must use separator span."""
        content = _read_404()
        assert 'class="sep"' in content, \
            "404 breadcrumb must use separator span"


# -- Test404StatePanel ------------------------------------------------------


class Test404StatePanel:
    """Verify .state-panel structure for 404 page."""

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_state_panel_class(self):
        """404 must have a .state-panel container."""
        content = _read_404()
        assert 'class="state-panel"' in content, \
            "404 must have state-panel class"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_state_panel_role_status(self):
        """404 state-panel must have role='status'."""
        content = _read_404()
        assert 'role="status"' in content, \
            "404 state-panel must have role='status'"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_state_panel_aria_live(self):
        """404 state-panel must have aria-live='polite'."""
        content = _read_404()
        assert 'aria-live="polite"' in content, \
            "404 state-panel must have aria-live='polite'"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_state_panel_icon(self):
        """404 must have a .state-panel__icon element."""
        content = _read_404()
        assert 'class="state-panel__icon"' in content, \
            "404 must have state-panel__icon"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_state_panel_icon_aria_hidden(self):
        """404 icon must have aria-hidden='true'."""
        content = _read_404()
        icon_section = content[content.find('state-panel__icon'):]
        icon_section = icon_section[:icon_section.find('</div>') + 6]
        assert 'aria-hidden="true"' in icon_section, \
            "404 state-panel__icon must have aria-hidden='true'"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_state_panel_icon_value(self):
        """404 icon must display '404'."""
        content = _read_404()
        assert '>404<' in content, \
            "404 state-panel__icon must display '404'"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_state_panel_title(self):
        """404 must have a .state-panel__title with 'Page Not Found'."""
        content = _read_404()
        assert 'class="state-panel__title"' in content, \
            "404 must have state-panel__title"
        assert "Page Not Found" in content, \
            "404 title must contain 'Page Not Found'"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_state_panel_desc(self):
        """404 must have a .state-panel__desc element."""
        content = _read_404()
        assert 'class="state-panel__desc"' in content, \
            "404 must have state-panel__desc"


# -- Test404Navigation ------------------------------------------------------


class Test404Navigation:
    """Verify 404 navigation links."""

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_state_panel_links_nav(self):
        """404 must have a nav with .state-panel__links."""
        content = _read_404()
        assert 'class="state-panel__links"' in content, \
            "404 must have state-panel__links"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_nav_aria_label(self):
        """404 nav must have aria-label."""
        content = _read_404()
        assert 'aria-label="Navigation links"' in content, \
            "404 nav must have aria-label='Navigation links'"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_dashboard_link(self):
        """404 must link back to /dashboard."""
        content = _read_404()
        assert 'href="/dashboard"' in content, \
            "404 must have /dashboard link"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_projects_link(self):
        """404 must link to /projects."""
        content = _read_404()
        assert 'href="/projects"' in content, \
            "404 must have /projects link"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_sessions_link(self):
        """404 must link to /sessions."""
        content = _read_404()
        assert 'href="/sessions"' in content, \
            "404 must have /sessions link"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_agents_link(self):
        """404 must link to /agents."""
        content = _read_404()
        assert 'href="/agents"' in content, \
            "404 must have /agents link"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_four_nav_links(self):
        """404 must have exactly 4 navigation links."""
        content = _read_404()
        links = re.findall(r'class="state-panel__link"', content)
        assert len(links) == 4, \
            f"404 must have 4 state-panel__link elements, found {len(links)}"


# -- TestErrorTemplate ------------------------------------------------------


class TestErrorTemplate:
    """Verify the error.html Jinja2 template structure."""

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_template_file_exists(self):
        """error.html must exist on disk."""
        assert os.path.isfile(_ERROR_PATH), \
            f"{_ERROR_PATH} must exist"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_extends_base(self):
        """Error must extend base.html."""
        content = _read_error()
        assert '{% extends "base.html" %}' in content, \
            "Error must extend base.html"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_title_block(self):
        """Error must set a descriptive page title."""
        content = _read_error()
        assert "Error" in content, \
            "Error title must contain 'Error'"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_states_css_import(self):
        """Error must import states.css via head_extra block."""
        content = _read_error()
        assert 'href="/static/css/states.css"' in content, \
            "Error must import states.css"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_no_page_specific_js(self):
        """Error must not import page-specific JS (states.js not needed for static page)."""
        content = _read_error()
        assert 'states.js' not in content, \
            "Error must not import states.js (static page, no JS needed)"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_head_extra_block(self):
        """Error must use head_extra block for CSS import."""
        content = _read_error()
        assert '{% block head_extra %}' in content, \
            "Error must use head_extra block"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_topbar_toggles_empty(self):
        """Error must suppress topbar toggles."""
        content = _read_error()
        assert '{% block topbar_toggles %}{% endblock %}' in content, \
            "Error must define empty topbar_toggles block"


# -- TestErrorBreadcrumb ----------------------------------------------------


class TestErrorBreadcrumb:
    """Verify error breadcrumb structure."""

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_breadcrumb_dashboard_link(self):
        """Breadcrumb must link to /dashboard."""
        content = _read_error()
        assert 'href="/dashboard"' in content, \
            "Error breadcrumb must link to /dashboard"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_breadcrumb_current(self):
        """Breadcrumb must show current page label."""
        content = _read_error()
        # The breadcrumb shows "Error" as current
        assert "Error" in content, \
            "Error breadcrumb must show 'Error' as current"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_breadcrumb_separator(self):
        """Breadcrumb must use separator span."""
        content = _read_error()
        assert 'class="sep"' in content, \
            "Error breadcrumb must use separator span"


# -- TestErrorStatePanel ----------------------------------------------------


class TestErrorStatePanel:
    """Verify .state-panel structure for error page."""

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_state_panel_class(self):
        """Error must have a .state-panel container."""
        content = _read_error()
        assert 'class="state-panel"' in content, \
            "Error must have state-panel class"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_state_panel_role_alert(self):
        """Error state-panel must have role='alert'."""
        content = _read_error()
        assert 'role="alert"' in content, \
            "Error state-panel must have role='alert'"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_state_panel_aria_live_assertive(self):
        """Error state-panel must have aria-live='assertive'."""
        content = _read_error()
        assert 'aria-live="assertive"' in content, \
            "Error state-panel must have aria-live='assertive'"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_state_panel_icon(self):
        """Error must have a .state-panel__icon element."""
        content = _read_error()
        assert 'class="state-panel__icon' in content, \
            "Error must have state-panel__icon"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_state_panel_icon_error_modifier(self):
        """Error icon must have .state-panel__icon--error modifier."""
        content = _read_error()
        assert 'state-panel__icon--error' in content, \
            "Error icon must have state-panel__icon--error modifier"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_state_panel_icon_aria_hidden(self):
        """Error icon must have aria-hidden='true'."""
        content = _read_error()
        icon_section = content[content.find('state-panel__icon'):]
        icon_section = icon_section[:icon_section.find('</div>') + 6]
        assert 'aria-hidden="true"' in icon_section, \
            "Error state-panel__icon must have aria-hidden='true'"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_state_panel_icon_value(self):
        """Error icon must display '!'."""
        content = _read_error()
        # The icon div contains "!" - check within the icon element
        icon_start = content.find('state-panel__icon--error')
        assert icon_start != -1, "Error must have state-panel__icon--error"
        icon_snippet = content[icon_start:icon_start + 100]
        assert '!' in icon_snippet, \
            "Error state-panel__icon must display '!'"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_state_panel_title(self):
        """Error must have a .state-panel__title."""
        content = _read_error()
        assert 'class="state-panel__title"' in content, \
            "Error must have state-panel__title"
        assert "Something Went Wrong" in content, \
            "Error title must contain 'Something Went Wrong'"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_state_panel_desc(self):
        """Error must have a .state-panel__desc element."""
        content = _read_error()
        assert 'class="state-panel__desc"' in content, \
            "Error must have state-panel__desc"


# -- TestErrorNavigation ----------------------------------------------------


class TestErrorNavigation:
    """Verify error navigation links."""

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_state_panel_links_nav(self):
        """Error must have a nav with .state-panel__links."""
        content = _read_error()
        assert 'class="state-panel__links"' in content, \
            "Error must have state-panel__links"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_nav_aria_label(self):
        """Error nav must have aria-label."""
        content = _read_error()
        assert 'aria-label="Navigation links"' in content, \
            "Error nav must have aria-label='Navigation links'"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_dashboard_link(self):
        """Error must link back to /dashboard."""
        content = _read_error()
        assert 'href="/dashboard"' in content, \
            "Error must have /dashboard link"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_single_nav_link(self):
        """Error must have exactly 1 navigation link (Dashboard only)."""
        content = _read_error()
        links = re.findall(r'class="state-panel__link"', content)
        assert len(links) == 1, \
            f"Error must have 1 state-panel__link, found {len(links)}"


# -- TestErrorConditionalDetails --------------------------------------------


class TestErrorConditionalDetails:
    """Verify conditional error details rendering in error.html."""

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_jinja_if_error_block(self):
        """Error template must conditionally render error details."""
        content = _read_error()
        assert '{% if error %}' in content, \
            "Error must have {% if error %} conditional block"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_state_panel_details(self):
        """Error must have .state-panel__details collapsible."""
        content = _read_error()
        assert 'class="state-panel__details"' in content, \
            "Error must have state-panel__details"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_details_summary(self):
        """Error details must have a summary element."""
        content = _read_error()
        assert "<summary>" in content, \
            "Error details must have a summary element"
        assert "Error details" in content, \
            "Error details summary must say 'Error details'"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_raw_error_output(self):
        """Error must have .state-panel__raw for raw error output."""
        content = _read_error()
        assert 'class="state-panel__raw"' in content, \
            "Error must have state-panel__raw"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_jinja_error_variable(self):
        """Error template must render the error variable."""
        content = _read_error()
        assert "{{ error }}" in content, \
            "Error must render {{ error }} variable"


# -- TestNoInlinePatterns (shared) -----------------------------------------


class Test404NoInlinePatterns:
    """Verify 404 has no inline styles or scripts."""

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_no_inline_onclick(self):
        """404 must not use inline onclick handlers."""
        content = _read_404()
        matches = re.findall(r'\bonclick\s*=', content, re.IGNORECASE)
        assert len(matches) == 0, \
            f"404 must not have inline onclick, found {len(matches)}"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_no_inline_script_tags(self):
        """404 must not have inline script blocks."""
        content = _read_404()
        script_tags = re.findall(r'<script(?! src)[^>]*>', content)
        assert len(script_tags) == 0, \
            f"404 must not have inline script tags, found {len(script_tags)}"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_no_inline_style_blocks(self):
        """404 must not have inline style blocks."""
        content = _read_404()
        style_blocks = re.findall(r'<style[^>]*>', content)
        assert len(style_blocks) == 0, \
            f"404 must not have inline style blocks, found {len(style_blocks)}"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_no_inline_style_attribute(self):
        """404 must not have inline style= attributes."""
        content = _read_404()
        inline_styles = re.findall(r'\bstyle\s*="[^"]*"', content, re.IGNORECASE)
        assert len(inline_styles) == 0, \
            f"404 must not have inline style attributes, found {len(inline_styles)}"


class TestErrorNoInlinePatterns:
    """Verify error.html has no inline styles or scripts."""

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_no_inline_onclick(self):
        """Error must not use inline onclick handlers."""
        content = _read_error()
        matches = re.findall(r'\bonclick\s*=', content, re.IGNORECASE)
        assert len(matches) == 0, \
            f"Error must not have inline onclick, found {len(matches)}"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_no_inline_script_tags(self):
        """Error must not have inline script blocks."""
        content = _read_error()
        script_tags = re.findall(r'<script(?! src)[^>]*>', content)
        assert len(script_tags) == 0, \
            f"Error must not have inline script tags, found {len(script_tags)}"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_no_inline_style_blocks(self):
        """Error must not have inline style blocks."""
        content = _read_error()
        style_blocks = re.findall(r'<style[^>]*>', content)
        assert len(style_blocks) == 0, \
            f"Error must not have inline style blocks, found {len(style_blocks)}"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_no_inline_style_attribute(self):
        """Error must not have inline style= attributes."""
        content = _read_error()
        inline_styles = re.findall(r'\bstyle\s*="[^"]*"', content, re.IGNORECASE)
        assert len(inline_styles) == 0, \
            f"Error must not have inline style attributes, found {len(inline_styles)}"
