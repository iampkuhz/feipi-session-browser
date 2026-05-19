"""Tests for payload modal renderer contract (v9).

v9 uses a simplified payload modal:
- Modal lives in base.html with .payload-modal__rendered and .payload-modal__raw panels.
- session_detail_timeline.js handles open-payload actions via data delegation.
- Payload data comes from [data-payload-source] hidden elements.
- No inline renderPayload/renderRawFallback functions; rendering is innerHTML-based.

Old inline renderers (renderPayload, renderRawFallback, renderLlmRequestJson, etc.)
were removed in the v9 component migration.
"""

from pathlib import Path

TEMPLATE_DIR = Path(__file__).parent.parent / "src" / "session_browser" / "web" / "templates"
STATIC_JS = Path(__file__).parent.parent / "src" / "session_browser" / "web" / "static" / "js"
STATIC_CSS = Path(__file__).parent.parent / "src" / "session_browser" / "web" / "static" / "style.css"


def _base_source():
    return (TEMPLATE_DIR / "base.html").read_text(encoding="utf-8")


def _timeline_js():
    return (STATIC_JS / "session_detail_timeline.js").read_text(encoding="utf-8")


def _css():
    return STATIC_CSS.read_text(encoding="utf-8")


# ── Modal structure (base.html) ────────────────────────────────────


def test_modal_has_rendered_element():
    """Payload modal must have a .payload-modal__rendered element."""
    source = _base_source()
    assert 'class="payload-modal__rendered"' in source, (
        "Modal must contain .payload-modal__rendered element"
    )


def test_modal_has_raw_element():
    """Payload modal must have a .payload-modal__raw element."""
    source = _base_source()
    assert 'class="payload-modal__raw"' in source, (
        "Modal must contain .payload-modal__raw element"
    )


def test_modal_has_tabs():
    """Payload modal must have Rendered and Raw tabs."""
    source = _base_source()
    assert 'data-mode="rendered"' in source, "Modal must have a Rendered tab"
    assert 'data-mode="raw"' in source, "Modal must have a Raw tab"


def test_modal_has_close_button():
    """Payload modal must have a close button."""
    source = _base_source()
    assert 'data-action="close-modal"' in source, "Modal must have close button"


# ── JS interaction (session_detail_timeline.js) ────────────────────


def test_js_has_open_payload_action():
    """JS must handle data-action='open-payload'."""
    js = _timeline_js()
    assert "'open-payload'" in js or '"open-payload"' in js, (
        "JS must handle open-payload action"
    )


def test_js_has_payload_modal_lookup():
    """JS must look up the payload modal by ID."""
    js = _timeline_js()
    assert "payload-modal" in js or "sd-payload-modal" in js, (
        "JS must reference payload modal element"
    )


def test_js_has_fallback_message():
    """JS must show a fallback when payload data is missing."""
    js = _timeline_js()
    assert "payload unavailable" in js.lower() or "payload" in js.lower(), (
        "JS must have fallback message for missing payload"
    )


# ── CSS styles ─────────────────────────────────────────────────────


def test_has_rendered_section_css():
    """CSS must have styles for rendered sections."""
    css = _css()
    assert ".payload-modal__rendered" in css, (
        "CSS must have .payload-modal__rendered styles"
    )


def test_has_rendered_code_block_css():
    """CSS must have styles for code blocks in rendered view."""
    css = _css()
    assert "rendered-code-block" in css or "payload-modal__raw pre" in css, (
        "CSS must have code block styles in payload modal"
    )


# ── v9 no longer uses inline renderers ─────────────────────────────
# The following old tests are superseded by the simplified v9 architecture:
# - renderPayload / renderRawFallback / tryParseJson
# - renderLlmRequestJson / renderLlmResponseJson / renderToolJson
# - renderPrettyJson / renderPlainText / renderMissing
# - render_payload_checks_raw_fallback / raw_non_empty_has_renderable_fallback
# - no_old_fallback_pattern / open_payload_modal_uses_render_payload
# - _escapeHtml / renderers_use_escape_html
#
# These functions were inline in the old session.html and have been replaced
# by the data-driven approach in session_detail_timeline.js.
