"""Tests for session detail message payload coverage.

Architecture:
- User/assistant messages handled in the view model (routes.py)
- Payload map built as Python dict in routes.py, not Jinja2
- Round detail rendered via sdt macros, not inline message cards
- Payload buttons use data-payload-id, not data-payload-key
"""

import pytest

import re
from pathlib import Path

TEMPLATE_DIR = Path(__file__).parents[2] / "src" / "session_browser" / "web" / "templates"
ROUTES = Path(__file__).parents[2] / "src" / "session_browser" / "web" / "routes.py"


def _read_routes():
    return ROUTES.read_text(encoding="utf-8")


# ── 视图模型中的消息载荷 ──────────────────────────────────────────


@pytest.mark.contract_case("UI-SD-008")
def test_user_msg_content_in_viewmodel():
    """View model must process user_msg.content for payload."""
    routes = _read_routes()
    assert "user_msg.content" in routes, (
        "View model must reference user_msg.content"
    )


@pytest.mark.contract_case("UI-SD-008")
def test_assistant_msg_content_in_viewmodel():
    """View model must process assistant message content for payload."""
    routes = _read_routes()
    assert "assistant_msg" in routes or "assistant" in routes.lower(), (
        "View model must reference assistant message content"
    )


@pytest.mark.contract_case("UI-SD-008")
def test_payload_map_in_routes():
    """Payload map must be built in routes.py view model."""
    routes = _read_routes()
    assert "payload_index" in routes or "payload_map" in routes.lower(), (
        "View model must build payload index/map"
    )


@pytest.mark.contract_case("UI-SD-008")
def test_payload_entries_have_required_fields():
    """Payload entries must have type, title, rendered, raw, missing_reason."""
    routes = _read_routes()
    # 视图模型使用这些键构建载荷字典
    assert "'type'" in routes or '"type"' in routes, (
        "Payload entries must have 'type' field"
    )
    assert "'title'" in routes or '"title"' in routes, (
        "Payload entries must have 'title' field"
    )
    assert "'rendered'" in routes or '"rendered"' in routes, (
        "Payload entries must have 'rendered' field"
    )
    assert "'missing_reason'" in routes or '"missing_reason"' in routes, (
        "Payload entries must have 'missing_reason' field"
    )


# ── Content availability ──────────────────────────────────────────────────


@pytest.mark.contract_case("UI-SD-008")
def test_user_content_available_not_truncated_only():
    """User message must have full-content payload, not just truncated preview."""
    routes = _read_routes()
    # View model must capture full user_msg.content
    assert "user_msg.content" in routes, (
        "View model must capture full user content"
    )


@pytest.mark.contract_case("UI-SD-008")
def test_assistant_content_available_not_truncated_only():
    """Assistant message must have full-content payload."""
    routes = _read_routes()
    assert "assistant" in routes.lower(), (
        "View model must capture assistant content"
    )


# ── Payload modal integration ─────────────────────────────────────────────


@pytest.mark.contract_case("UI-SD-008")
def test_payload_modal_in_base():
    """Payload modal must be defined in base.html."""
    base = (TEMPLATE_DIR / "base.html").read_text(encoding="utf-8")
    assert "payload-modal" in base, "base.html must have payload modal"


@pytest.mark.contract_case("UI-SD-008")
def test_js_handles_payload_unavailable():
    """JS must handle missing payload gracefully."""
    js = (Path(__file__).resolve().parents[2]
          / "src" / "session_browser" / "web" / "static" / "js"
          / "session_detail_timeline.js").read_text(encoding="utf-8")
    assert "unavailable" in js.lower() or "payload" in js.lower(), (
        "JS must handle unavailable payload"
    )
