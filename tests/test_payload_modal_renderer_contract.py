"""Tests for payload modal renderer contract.

Verifies that:
- The modal has .payload-modal__rendered and .payload-modal__raw elements.
- JS contains fallback renderers for raw JSON.
- No literal behavior that raw non-empty yields "(No rendered content)".
- The renderPayload/renderRawFallback functions exist in the JS source.
- Payload map entries with raw non-empty must have renderable fallback.
"""

import re
from pathlib import Path

TEMPLATE_DIR = Path(__file__).parent.parent / "src" / "session_browser" / "web" / "templates"


def _session_source():
    return (TEMPLATE_DIR / "session.html").read_text(encoding="utf-8")


def _base_source():
    return (TEMPLATE_DIR / "base.html").read_text(encoding="utf-8")


# ── Modal structure ────────────────────────────────────────────────


def test_modal_has_rendered_element():
    """Payload modal must have a .payload-modal__rendered element."""
    source = _base_source()
    assert 'class="payload-modal__rendered"' in source, (
        "Modal must contain .payload-modal__rendered element (check base.html)"
    )


def test_modal_has_raw_element():
    """Payload modal must have a .payload-modal__raw element."""
    source = _base_source()
    assert 'class="payload-modal__raw"' in source, (
        "Modal must contain .payload-modal__raw element (check base.html)"
    )


def test_modal_has_tabs():
    """Payload modal must have Rendered and Raw tabs."""
    source = _base_source()
    assert 'data-mode="rendered"' in source, (
        "Modal must have a Rendered tab (check base.html)"
    )
    assert 'data-mode="raw"' in source, (
        "Modal must have a Raw tab (check base.html)"
    )


# ── Fallback renderer functions ────────────────────────────────────


def test_has_render_payload_function():
    """JS must define a renderPayload function."""
    source = _session_source()
    assert "function renderPayload(payload)" in source, (
        "JS must define renderPayload(payload) function"
    )


def test_has_render_raw_fallback_function():
    """JS must define a renderRawFallback function."""
    source = _session_source()
    assert "function renderRawFallback(raw, type)" in source, (
        "JS must define renderRawFallback(raw, type) function"
    )


def test_has_try_parse_json_function():
    """JS must define a tryParseJson helper."""
    source = _session_source()
    assert "function tryParseJson(raw)" in source, (
        "JS must define tryParseJson(raw) helper"
    )


def test_has_llm_request_renderer():
    """JS must define an LLM request renderer."""
    source = _session_source()
    assert "function renderLlmRequestJson(obj)" in source, (
        "JS must define renderLlmRequestJson(obj) function"
    )


def test_has_llm_response_renderer():
    """JS must define an LLM response renderer."""
    source = _session_source()
    assert "function renderLlmResponseJson(obj)" in source, (
        "JS must define renderLlmResponseJson(obj) function"
    )


def test_has_tool_renderer():
    """JS must define a tool input/result renderer."""
    source = _session_source()
    assert "function renderToolJson(parsed, type)" in source, (
        "JS must define renderToolJson(parsed, type) function"
    )


def test_has_pretty_json_renderer():
    """JS must define a pretty JSON renderer."""
    source = _session_source()
    assert "function renderPrettyJson(obj)" in source, (
        "JS must define renderPrettyJson(obj) function"
    )


def test_has_plain_text_renderer():
    """JS must define a plain text renderer."""
    source = _session_source()
    assert "function renderPlainText(raw)" in source, (
        "JS must define renderPlainText(raw) function"
    )


def test_has_missing_renderer():
    """JS must define a missing content renderer."""
    source = _session_source()
    assert "function renderMissing(reason)" in source, (
        "JS must define renderMissing(reason) function"
    )


# ── No "(No rendered content)" for raw non-empty ───────────────────


def test_render_payload_checks_raw_fallback():
    """renderPayload must call renderRawFallback when raw is non-empty and rendered is empty."""
    source = _session_source()
    # The function should call renderRawFallback when raw has content
    assert "renderRawFallback" in source, (
        "renderPayload must delegate to renderRawFallback for raw content"
    )


def test_raw_non_empty_has_renderable_fallback():
    """Payload map entries with raw non-empty must have a renderable fallback path."""
    source = _session_source()
    # The renderPayload function should check raw content and call renderRawFallback
    # Find the renderPayload function body
    func_start = source.find("function renderPayload(payload)")
    assert func_start >= 0, "renderPayload function must exist"

    next_func = source.find("\n    function ", func_start + 10)
    if next_func < 0:
        next_func = func_start + 3000

    func_body = source[func_start:next_func]

    # Verify the function checks for raw content and has fallback path
    assert "payload.raw" in func_body, (
        "renderPayload must check payload.raw for fallback content"
    )
    assert "renderRawFallback" in func_body, (
        "renderPayload must call renderRawFallback for raw content fallback"
    )


def test_no_old_fallback_pattern():
    """Old pattern that sets rendered to '(No rendered content)' when raw has content must be removed."""
    source = _session_source()

    # The old code had this pattern:
    # if (!renderedContent && payload.missing_reason) {
    #     renderedContent = '(No rendered content — ' + payload.missing_reason + ')';
    # } else if (!renderedContent) {
    #     renderedContent = '(No rendered content)';
    # }
    # This must no longer exist in the openPayloadModal function.
    # Check that the old literal pattern is not in openPayloadModal.
    # We look for the specific old fallback logic pattern in the openPayloadModal function.

    # Extract the openPayloadModal function body (rough heuristic)
    func_start = source.find("function openPayloadModal(key, button)")
    assert func_start >= 0, "openPayloadModal function must exist"

    # Find the next function definition after openPayloadModal
    next_func = source.find("\n    function ", func_start + 10)
    if next_func < 0:
        next_func = source.find("\n    window.closePayloadModal", func_start)
    if next_func < 0:
        next_func = source.find("\n    /*", func_start + 200)
    if next_func < 0:
        next_func = func_start + 5000  # fallback

    modal_func_body = source[func_start:next_func]

    # The old pattern assigned "(No rendered content)" as a fallback
    # The new version should NOT contain this old logic
    old_pattern = "renderedContent = '(No rendered content)"
    assert old_pattern not in modal_func_body, (
        "openPayloadModal must not contain old '(No rendered content)' fallback logic"
    )


def test_open_payload_modal_uses_render_payload():
    """openPayloadModal must call renderPayload to set rendered content."""
    source = _session_source()
    func_start = source.find("function openPayloadModal(key, button)")
    assert func_start >= 0, "openPayloadModal function must exist"

    next_func = source.find("\n    function ", func_start + 10)
    if next_func < 0:
        next_func = source.find("\n    window.closePayloadModal", func_start)
    if next_func < 0:
        next_func = func_start + 5000

    modal_func_body = source[func_start:next_func]

    assert "renderPayload(payload)" in modal_func_body, (
        "openPayloadModal must call renderPayload(payload) to render content"
    )


# DEDUPLICATED: The following tests are more thoroughly covered in
# test_session_detail_payload_map_contract.py:
# - test_payload_map_script_has_required_fields  (covers type, title, rendered, raw, missing_reason)
# - test_all_payload_buttons_have_type           (covers data-payload-type=)
# - test_all_payload_buttons_have_title          (covers data-payload-title=)
#
# Removed to avoid redundancy:
# - test_payload_map_has_type_field
# - test_payload_map_has_missing_reason_field
# - test_payload_buttons_have_data_type
# - test_payload_buttons_have_data_title


# ── Raw JSON leakage ───────────────────────────────────────────────


def test_no_visible_raw_json_in_page_flow():
    """No visible <pre id="raw-json"> should be in normal page flow.

    If raw JSON exists on the page, it must be hidden (style="display:none")
    or inside a script element, never exposed to the user.
    """
    source = _session_source()
    # Check that #raw-json has display:none
    import re
    match = re.search(
        r'<pre\s+id="raw-json"[^>]*>',
        source
    )
    if match:
        tag = match.group(0)
        assert 'display:none' in tag or "display: none" in tag, (
            "<pre id=\"raw-json\"> must have display:none to prevent raw JSON leakage"
        )


def test_raw_json_is_debug_only():
    """Raw JSON must be debug-only hidden or inside script JSON."""
    source = _session_source()
    import re
    # Find all raw-json occurrences
    raw_json_tags = re.findall(
        r'<(?:pre|script)[^>]*raw-json[^>]*>',
        source
    )
    for tag in raw_json_tags:
        # If it's a pre tag, it must be hidden
        if tag.startswith('<pre'):
            assert 'display:none' in tag or "display: none" in tag, (
                f"Raw JSON pre tag must be hidden: {tag[:100]}"
            )
        # If it's a script tag, it's OK (JSON script data)
        # No assertion needed for script tags


# ── HTML safety ────────────────────────────────────────────────────


def test_escape_html_function_exists():
    """JS must have an _escapeHtml function for safe DOM construction."""
    source = _session_source()
    assert "function _escapeHtml(str)" in source or "function _escapeHtml" in source, (
        "JS must define _escapeHtml function for safe HTML escaping"
    )


def test_renderers_use_escape_html():
    """Fallback renderers must use _escapeHtml to prevent XSS."""
    source = _session_source()
    # Count _escapeHtml usages — should be multiple (in various renderers)
    count = source.count("_escapeHtml(")
    assert count >= 3, (
        f"Expected multiple _escapeHtml() calls, found {count}. "
        "Renderers must escape user-controlled content."
    )


# ── CSS styles ─────────────────────────────────────────────────────


def test_has_rendered_section_css():
    """CSS must have styles for rendered sections."""
    css_path = Path(__file__).parent.parent / "src" / "session_browser" / "web" / "static" / "style.css"
    css = css_path.read_text(encoding="utf-8")
    assert ".payload-modal__rendered" in css, (
        "CSS must have .payload-modal__rendered styles"
    )


def test_has_rendered_code_block_css():
    """CSS must have styles for code blocks in rendered view."""
    css_path = Path(__file__).parent.parent / "src" / "session_browser" / "web" / "static" / "style.css"
    css = css_path.read_text(encoding="utf-8")
    assert "rendered-code-block" in css, (
        "CSS must have .rendered-code-block styles"
    )


def test_has_rendered_missing_css():
    """CSS must have styles for missing content indicator."""
    css_path = Path(__file__).parent.parent / "src" / "session_browser" / "web" / "static" / "style.css"
    css = css_path.read_text(encoding="utf-8")
    assert "rendered-missing" in css, (
        "CSS must have .rendered-missing styles"
    )
