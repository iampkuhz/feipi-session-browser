"""T031 · info icon entity/component contract.

Verifies that projects.html and project.html do NOT directly embed the
Unicode info character ⓘ (U+24D8) as raw text. Instead, info icons should
be rendered via a macro or component that uses a semantic/accessible pattern
(e.g., SVG icon, entity reference, or CSS pseudo-element).

Covers P-25: 页面有乱码/特殊字符图标 ⓘ
"""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_DIR = ROOT / "src" / "session_browser" / "web" / "templates"

PROJECTS_HTML = TEMPLATE_DIR / "projects.html"
PROJECT_HTML = TEMPLATE_DIR / "project.html"

# The problematic Unicode character
INFO_CHAR = "ⓘ"  # ⓘ


def _read_template(path: Path) -> str:
    if not path.exists():
        pytest.skip(f"{path.name} not found at {path}")
    return path.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def projects_html():
    return _read_template(PROJECTS_HTML)


@pytest.fixture(scope="module")
def project_html():
    return _read_template(PROJECT_HTML)


class TestInfoIconNotRawEmbedded:
    """Templates must not directly embed ⓘ as raw text.

    The info icon should be produced via a macro/component, not pasted as
    a raw Unicode character into the template source.
    """

    def test_projects_no_raw_info_icon(self, projects_html):
        """projects.html must not contain the raw ⓘ character."""
        assert INFO_CHAR not in projects_html, (
            "projects.html contains raw ⓘ (U+24D8) character. "
            "Use a macro/component or SVG icon instead."
        )

    def test_project_no_raw_info_icon(self, project_html):
        """project.html must not contain the raw ⓘ character."""
        assert INFO_CHAR not in project_html, (
            "project.html contains raw ⓘ (U+24D8) character. "
            "Use a macro/component or SVG icon instead."
        )

    def test_projects_uses_info_button_component(self, projects_html):
        """projects.html should use a semantic info button pattern.

        Acceptable patterns:
        - icon_button macro call
        - icon-button class with info variant
        - data-action="metric-info" or data-action="info"
        """
        has_icon_button = "icon-button--info" in projects_html or "icon_button" in projects_html
        has_data_action = "metric-info" in projects_html or 'data-action="info"' in projects_html
        assert has_icon_button or has_data_action, (
            "projects.html lacks a semantic info button pattern. "
            "Expected icon-button--info class or icon_button macro usage."
        )

    def test_project_uses_info_button_component(self, project_html):
        """project.html should use a semantic info button pattern."""
        has_icon_button = "icon-button--info" in project_html or "icon_button" in project_html
        has_data_action = 'data-action="info"' in project_html
        assert has_icon_button or has_data_action, (
            "project.html lacks a semantic info button pattern. "
            "Expected icon-button--info class or icon_button macro usage."
        )
