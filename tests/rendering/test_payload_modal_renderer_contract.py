"""Tests for payload modal renderer contract in session_detail_timeline.html.
Verifies that the sd-payload-modal panel includes the canonical `payload-modal__panel`
CSS class and does not use fullscreen inline styles.

Related: SD-17 — sd-payload-modal 宽高变成整个页面
"""

import pytest

from pathlib import Path
import re

TEMPLATE_DIR = Path(__file__).parents[2] / "src" / "session_browser" / "web" / "templates"

TIMELINE_TEMPLATE = TEMPLATE_DIR / "components" / "session_detail_timeline.html"


def _timeline_html():
    return TIMELINE_TEMPLATE.read_text(encoding="utf-8")


def _has_canonical_panel_class(source: str) -> bool:
    """Check whether any class attribute in the payload_modal macro
    contains `payload-modal__panel` as a standalone CSS class token.

    A standalone token means it is separated by whitespace within the
    class attribute value, not merely a substring of a longer identifier
    (e.g. 'sd-payload-modal__panel' does NOT count).
    """
    # Extract the payload_modal macro block
    macro_match = re.search(
        r'\{% macro payload_modal\(\) -%\}(.*?){%- endmacro %}',
        source,
        re.DOTALL,
    )
    if not macro_match:
        return False
    macro_body = macro_match.group(1)

    # Find all class="..." attributes in the macro body
    class_attrs = re.findall(r'class="([^"]*)"', macro_body)
    for attr_value in class_attrs:
        # Split by whitespace and check each token
        tokens = attr_value.split()
        if 'payload-modal__panel' in tokens:
            return True
    return False


def _panel_inline_style(source: str) -> str | None:
    """Return the inline style string of the payload-modal__panel element,
    or None if not found."""
    macro_match = re.search(
        r'\{% macro payload_modal\(\) -%\}(.*?){%- endmacro %}',
        source,
        re.DOTALL,
    )
    if not macro_match:
        return None
    macro_body = macro_match.group(1)

    # Find elements that reference payload-modal__panel (either standalone or namespaced)
    tags = re.findall(r'<[^>]*(?:payload-modal__panel)[^>]*>', macro_body)
    for tag in tags:
        style_match = re.search(r'style="([^"]*)"', tag)
        if style_match:
            return style_match.group(1)
    return None


# ── Panel class contract ──────────────────────────────────────────


@pytest.mark.contract_case("UI-SD-020")
def test_payload_modal_panel_has_canonical_class():
    """sd-payload-modal panel must include canonical `payload-modal__panel` class.

    The panel inside the payload-modal dialog must carry the canonical BEM class
    `payload-modal__panel` as a standalone CSS class token so that selectors in
    ui-primitives.css (e.g. `.payload-modal--sd .payload-modal__panel`) apply.
    A namespaced-only class like `sd-payload-modal__panel` does NOT satisfy this
    contract because the canonical selector would miss it (SD-17).
    """
    source = _timeline_html()
    assert _has_canonical_panel_class(source), (
        "payload_modal panel must include 'payload-modal__panel' as a standalone "
        "CSS class (not just as a substring of a longer name like "
        "'sd-payload-modal__panel')"
    )


@pytest.mark.contract_case("UI-SD-020")
def test_payload_modal_panel_no_fullscreen_inline_style():
    """Panel must not carry fullscreen inline styles like width:100% or height:100vh."""
    source = _timeline_html()
    style = _panel_inline_style(source)
    if style is not None:
        style_lower = style.lower()
        assert '100%' not in style_lower and '100vh' not in style_lower and '100vw' not in style_lower, (
            f"payload-modal__panel must not have fullscreen inline style: {style!r}"
        )


@pytest.mark.contract_case("UI-SD-020")
def test_payload_modal_dialog_has_sd_namespace():
    """The payload modal dialog should carry sd-payload-modal class for scoped targeting."""
    source = _timeline_html()
    assert 'sd-payload-modal' in source, (
        "payload modal dialog should include sd-payload-modal class"
    )
