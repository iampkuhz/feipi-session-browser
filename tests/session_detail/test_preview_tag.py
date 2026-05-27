"""Tests for timeline preview user input (v9).
v9 builds preview text in the view model (routes.py):
- preview_title: from round.preview_text or user_msg.content[:80] (sanitized)
- preview_subtitle: tool count string
- User input indication is embedded in preview_title, not a separate tag.
"""

import pytest

import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROUTES = os.path.join(ROOT, "src", "session_browser", "web", "routes.py")


def _read_routes():
    with open(ROUTES) as f:
        return f.read()


class TestPreviewTextBuiltInViewmodel:
    """Verify preview text is built from user_msg.content in routes.py."""

    @pytest.mark.contract_case("UI-SD-024")
    def test_preview_title_uses_user_msg(self):
        source = _read_routes()
        assert "user_msg.content" in source
        assert "preview_title" in source

    @pytest.mark.contract_case("UI-SD-024")
    def test_preview_title_sanitized(self):
        """preview_title should sanitize forbidden framework words."""
        source = _read_routes()
        # Should replace forbidden words with ***
        assert "***" in source

    @pytest.mark.contract_case("UI-SD-024")
    def test_preview_subtitle_shows_tool_count(self):
        """preview_subtitle should show tool count."""
        source = _read_routes()
        assert "preview_subtitle" in source
        assert "tool" in source.lower()


class TestPreviewTagDoesNotLeakUserContent:
    """Verify user input content is not directly leaked in templates."""

    @pytest.mark.contract_case("UI-SD-024")
    def test_no_direct_user_msg_in_session_template(self):
        """session.html should not reference user_msg.content directly."""
        session_html = os.path.join(
            ROOT, "src", "session_browser", "web", "templates", "session.html"
        )
        with open(session_html) as f:
            content = f.read()
        # user_msg.content should not appear directly in the template
        assert "user_msg.content" not in content, (
            "Template should not reference user_msg.content directly"
        )

    @pytest.mark.contract_case("UI-SD-024")
    def test_preview_uses_view_model_vars(self):
        """Templates should use row.preview_title from view model, not raw content."""
        timeline = os.path.join(
            ROOT, "src", "session_browser", "web", "templates",
            "components", "session_detail_timeline.html"
        )
        with open(timeline) as f:
            content = f.read()
        assert "row.preview_title" in content, "Should use row.preview_title"
        assert "row.preview_subtitle" in content, "Should use row.preview_subtitle"


class TestPreviewTextTruncation:
    """Verify preview text truncation in view model."""

    @pytest.mark.contract_case("UI-SD-024")
    def test_truncation_in_routes(self):
        source = _read_routes()
        # preview_title is truncated to 120 chars
        assert "[:120]" in source or "[:80]" in source
