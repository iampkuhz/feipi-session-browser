"""Tests for the payload map contract in session detail (v9).
v9 architecture:
- Payload map built as Python dict in routes.py view model
- Payload buttons use data-payload-id (from sdp.button macro)
- No inline JSON script for payload map in template
- No window.__SESSION_PAYLOADS__ or window.__SESSION_PAYLOAD_MAP__
- Raw JSON in <script type="application/json" id="raw-json"> for copy action
"""

import pytest

import re
from pathlib import Path

TEMPLATE_DIR = Path(__file__).parents[2] / "src" / "session_browser" / "web" / "templates"
ROUTES = Path(__file__).parents[2] / "src" / "session_browser" / "web" / "routes.py"
TEMPLATE_ENV = Path(__file__).parents[2] / "src" / "session_browser" / "web" / "template_env.py"
COMPONENTS = TEMPLATE_DIR / "components"


def _session_source():
    return (TEMPLATE_DIR / "session.html").read_text(encoding="utf-8")


def _read_routes():
    return ROUTES.read_text(encoding="utf-8")


def _read_template_env():
    return TEMPLATE_ENV.read_text(encoding="utf-8")


def _all_source():
    """Combined routes + template_env source for cross-file checks."""
    return _read_routes() + "\n" + _read_template_env()


def _timeline_component():
    return (COMPONENTS / "session_detail_timeline.html").read_text(encoding="utf-8")


# ── 视图模型中的载荷映射 ─────────────────────────────────────────────


@pytest.mark.contract_case("UI-SD-008")
def test_payload_map_in_routes():
    """View model must build payload index/map."""
    routes = _read_routes()
    assert "payload_index" in routes, (
        "View model must build payload index"
    )


@pytest.mark.contract_case("UI-SD-008")
def test_payload_map_script_has_required_fields():
    """Payload entries must contain type, title, rendered, raw, missing_reason."""
    routes = _read_routes()
    for field in ("type", "title", "rendered", "raw", "missing_reason"):
        assert f'"{field}"' in routes or f"'{field}'" in routes, (
            f"Payload entries must have '{field}' field"
        )


@pytest.mark.contract_case("UI-SD-008")
def test_payload_map_uses_safe_json():
    """View model must use safe JSON serialization."""
    source = _all_source()
    assert "safe_json_display" in source or "tojson" in source, (
        "View model must use safe JSON serialization"
    )


# ── 组件中的载荷按钮 ─────────────────────────────────────────────


@pytest.mark.contract_case("UI-SD-008")
def test_payload_buttons_in_timeline():
    """Timeline must have open-payload button macro calls."""
    timeline = _timeline_component()
    # Buttons are generated via sdp.button() macro with open-payload action
    assert "open-payload" in timeline, "Timeline must reference open-payload action"


@pytest.mark.contract_case("UI-SD-008")
def test_payload_buttons_have_id():
    """Open-payload buttons must have data-payload-id."""
    prim = (COMPONENTS / "session_detail_primitives.html").read_text(encoding="utf-8")
    assert "data-payload-id" in prim, "Button macro must define data-payload-id"


@pytest.mark.contract_case("UI-SD-008")
def test_payload_button_titles():
    """Buttons must have descriptive labels: Request (renamed from Context), Response, Result."""
    timeline = _timeline_component()
    assert "sdp.button('Request'" in timeline, "Must have Request button"
    assert "sdp.button('Response'" in timeline, "Must have Response button"
    assert "sdp.button('Result'" in timeline, "Must have Result button"


# ── Generic "Payload" button count ──────────────────────────────────


@pytest.mark.contract_case("UI-SD-008")
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


@pytest.mark.contract_case("UI-SD-008")
def test_css_has_sd_btn_styles():
    """session-detail.css must define button styles."""
    css_path = Path(__file__).parents[2] / "src" / "session_browser" / "web" / "static" / "css" / "session-detail.css"
    css = css_path.read_text(encoding="utf-8")
    assert ".sd-btn" in css, "CSS must define .sd-btn styles"
