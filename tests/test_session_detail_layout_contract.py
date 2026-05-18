"""Session detail template contract tests.

These tests verify that session.html and base.html contain the
structural hooks required by the browser layout gate and static CSS gate.
They do not open a browser or check computed styles.
"""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BASE_HTML_PATH = ROOT / "src" / "session_browser" / "web" / "templates" / "base.html"
SESSION_HTML_PATH = ROOT / "src" / "session_browser" / "web" / "templates" / "session.html"


@pytest.fixture(scope="module")
def base_text():
    if not BASE_HTML_PATH.exists():
        pytest.skip(f"base.html not found at {BASE_HTML_PATH}")
    return BASE_HTML_PATH.read_text()


@pytest.fixture(scope="module")
def session_text():
    if not SESSION_HTML_PATH.exists():
        pytest.skip(f"session.html not found at {SESSION_HTML_PATH}")
    return SESSION_HTML_PATH.read_text()


def assert_contains_any(text, candidates, reason):
    """Assert at least one candidate string appears in text."""
    assert any(c in text for c in candidates), reason


# ── base.html checks ──


class TestBaseHtml:
    def test_shell_container_exists(self, base_text):
        """base.html must have a .shell container."""
        assert 'class="shell' in base_text or "class='shell" in base_text, \
            "base.html lacks .shell container"

    def test_shell_class_block(self, base_text):
        """base.html .shell must apply shell_class block or equivalent."""
        assert_contains_any(
            base_text,
            [
                "{% block shell_class %}",
                "shell_class",
            ],
            "base.html lacks shell_class block on .shell container",
        )

    def test_main_container_exists(self, base_text):
        """base.html must have a .main container."""
        assert_contains_any(
            base_text,
            [
                'class="main',
                "class='main",
            ],
            "base.html lacks .main container",
        )

    def test_no_inspector_logic(self, base_text):
        """no-inspector logic must not block session detail .main rendering."""
        # Check that there's conditional logic around no-inspector
        # (e.g., inspector only renders when no-inspector is not present)
        assert_contains_any(
            base_text,
            [
                "no-inspector",
                "_shell_cls",
            ],
            "base.html lacks no-inspector guard logic",
        )


# ── session.html checks ──


class TestSessionHtml:
    def test_extends_base(self, session_text):
        """session.html must extend base.html."""
        assert "{% extends" in session_text, \
            "session.html does not extend base.html"

    def test_shell_class_declares_phase1(self, session_text):
        """session.html shell_class must include phase1-shell."""
        assert "phase1-shell" in session_text, \
            "session.html shell_class lacks phase1-shell"

    def test_shell_class_declares_no_inspector(self, session_text):
        """session.html shell_class must include no-inspector."""
        assert "no-inspector" in session_text, \
            "session.html shell_class lacks no-inspector"

    def test_session_detail_root_exists(self, session_text):
        """session.html must have .session-detail-phase1 root."""
        assert_contains_any(
            session_text,
            [
                "session-detail-phase1",
                "data-session-detail-shell",
            ],
            "session.html lacks .session-detail-phase1 root element",
        )

    def test_hero_title_hook(self, session_text):
        """session.html must have hero title class hook."""
        assert_contains_any(
            session_text,
            [
                "hero-title",
                "page-header__title",
            ],
            "session.html lacks hero-title class hook",
        )

    def test_kpi_metrics_hook(self, session_text):
        """session.html must have KPI / metrics strip hook."""
        assert_contains_any(
            session_text,
            [
                "kpis",
                "metrics-strip",
            ],
            "session.html lacks KPI/metrics strip hook",
        )

    def test_trace_row_hook(self, session_text):
        """session.html must have trace-row hook."""
        assert_contains_any(
            session_text,
            [
                "trace-row",
            ],
            "session.html lacks trace-row hook",
        )
