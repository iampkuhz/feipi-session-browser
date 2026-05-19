"""Tests for the payload map contract in session detail (v9).

v9 architecture:
- Payload map built as Python dict in routes.py view model
- Payload buttons use data-payload-id (from sdp.button macro)
- No inline JSON script for payload map in template
- No window.__SESSION_PAYLOADS__ or window.__SESSION_PAYLOAD_MAP__
- Raw JSON in <script type="application/json" id="raw-json"> for copy action
"""

import re
from pathlib import Path

TEMPLATE_DIR = Path(__file__).parent.parent / "src" / "session_browser" / "web" / "templates"
ROUTES = Path(__file__).parent.parent / "src" / "session_browser" / "web" / "routes.py"
COMPONENTS = TEMPLATE_DIR / "components"


def _session_source():
    return (TEMPLATE_DIR / "session.html").read_text(encoding="utf-8")


def _read_routes():
    return ROUTES.read_text(encoding="utf-8")


def _timeline_component():
    return (COMPONENTS / "session_detail_timeline.html").read_text(encoding="utf-8")


# ── Payload map in view model ─────────────────────────────────────────


def test_payload_map_in_routes():
    """View model must build payload index/map."""
    routes = _read_routes()
    assert "payload_index" in routes, (
        "View model must build payload index"
    )


def test_payload_map_script_has_required_fields():
    """Payload entries must contain type, title, rendered, raw, missing_reason."""
    routes = _read_routes()
    for field in ("type", "title", "rendered", "raw", "missing_reason"):
        assert f'"{field}"' in routes or f"'{field}'" in routes, (
            f"Payload entries must have '{field}' field"
        )


def test_payload_map_uses_safe_json():
    """View model must use safe JSON serialization."""
    routes = _read_routes()
    assert "safe_json_display" in routes or "tojson" in routes, (
        "View model must use safe JSON serialization"
    )


# ── Payload buttons in component ─────────────────────────────────────


def test_payload_buttons_in_timeline():
    """Timeline must have open-payload button macro calls."""
    timeline = _timeline_component()
    # Buttons are generated via sdp.button() macro with open-payload action
    assert "open-payload" in timeline, "Timeline must reference open-payload action"


def test_payload_buttons_have_id():
    """Open-payload buttons must have data-payload-id."""
    prim = (COMPONENTS / "session_detail_primitives.html").read_text(encoding="utf-8")
    assert "data-payload-id" in prim, "Button macro must define data-payload-id"


def test_payload_button_titles():
    """Buttons must have descriptive labels: Context, Response, Result."""
    timeline = _timeline_component()
    assert "sdp.button('Context'" in timeline, "Must have Context button"
    assert "sdp.button('Response'" in timeline, "Must have Response button"
    assert "sdp.button('Result'" in timeline, "Must have Result button"


# ── Generic "Payload" button count ──────────────────────────────────


def test_no_massive_payload_buttons():
    """Template must not have 400+ generic 'Payload' buttons."""
    source = _session_source()
    # Template is component-based, no inline button duplication
    payload_buttons = re.findall(
        r'>\s*Payload\s*<',
        source
    )
    assert len(payload_buttons) < 400, (
        f"Must not have 400+ generic 'Payload' buttons"
    )


# ── CSS for payload buttons ─────────────────────────────────────────


def test_css_has_sd_btn_styles():
    """session-detail-timeline.css must define button styles."""
    css_path = Path(__file__).parent.parent / "src" / "session_browser" / "web" / "static" / "css" / "session-detail-timeline.css"
    css = css_path.read_text(encoding="utf-8")
    assert ".sd-btn" in css, "CSS must define .sd-btn styles"
