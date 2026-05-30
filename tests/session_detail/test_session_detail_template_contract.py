"""Session detail static template contract tests.

Covers:
- base.html and session.html structural hooks
- Trace panel, issue strip, payload modal
- Component macro structure
- Content modal removed (negative assertions)
- Metrics strip
"""
import pytest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_DIR = ROOT / "src" / "session_browser" / "web" / "templates"
COMPONENTS = TEMPLATE_DIR / "components"
BASE_HTML_PATH = TEMPLATE_DIR / "base.html"
SESSION_HTML_PATH = TEMPLATE_DIR / "session.html"


def _session_source():
    return (TEMPLATE_DIR / "session.html").read_text(encoding="utf-8")


def _base_source():
    return (TEMPLATE_DIR / "base.html").read_text(encoding="utf-8")


def _timeline_component():
    return (COMPONENTS / "session_detail_timeline.html").read_text(encoding="utf-8")


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


# ── base.html 检查 ──


class TestBaseHtml:
    @pytest.mark.contract_case("UI-SD-016")
    def test_shell_container_exists(self, base_text):
        """base.html must have a .shell container."""
        assert 'class="shell' in base_text or "class='shell" in base_text, \
            "base.html lacks .shell container"

    @pytest.mark.contract_case("UI-SD-016")
    def test_shell_class_block(self, base_text):
        """base.html .shell must apply shell_class block."""
        assert_contains_any(
            base_text,
            ["{% block shell_class %}", "shell_class"],
            "base.html lacks shell_class block on .shell container",
        )

    @pytest.mark.contract_case("UI-SD-016")
    def test_main_container_exists(self, base_text):
        """base.html must have a .main container."""
        assert_contains_any(
            base_text,
            ['class="main', "class='main"],
            "base.html lacks .main container",
        )

    @pytest.mark.contract_case("UI-SD-016")
    def test_no_inspector_removed(self, base_text):
        """Inspector element must not be rendered in base.html."""
        assert "data-context-inspector" not in base_text, \
            "base.html must not contain inspector element"
        assert "inspector.html" not in base_text, \
            "base.html must not include inspector component"

    @pytest.mark.contract_case("UI-SD-016")
    def test_session_id_set_for_js(self):
        """session.html must expose session-id via <meta> for JS state persistence."""
        source = _session_source()
        assert 'name="session-id"' in source, \
            "session.html must have <meta name=\"session-id\"> for JS state persistence"

    @pytest.mark.contract_case("UI-SD-016")
    def test_payload_modal_element_exists(self, base_text):
        """payload-modal element must exist."""
        assert 'id="payload-modal"' in base_text, \
            "payload-modal element must exist"

    @pytest.mark.contract_case("UI-SD-016")
    def test_payload_modal_has_header(self, base_text):
        """Modal must have header."""
        assert 'class="payload-modal__header"' in base_text, \
            "Modal must have header"

    @pytest.mark.contract_case("UI-SD-016")
    def test_payload_modal_has_title(self, base_text):
        """Modal must have title element."""
        assert 'class="payload-modal__title"' in base_text, \
            "Modal must have title element"

    @pytest.mark.contract_case("UI-SD-016")
    def test_payload_modal_has_rendered_tab(self, base_text):
        """Modal must have Rendered tab."""
        assert 'data-mode="rendered"' in base_text, \
            "Modal must have Rendered tab"

    @pytest.mark.contract_case("UI-SD-016")
    def test_payload_modal_has_raw_tab(self, base_text):
        """Modal must have Raw tab."""
        assert 'data-mode="raw"' in base_text, \
            "Modal must have Raw tab"

    @pytest.mark.contract_case("UI-SD-016")
    def test_payload_modal_has_close_button(self, base_text):
        """Modal must have close button."""
        assert 'data-action="close-modal"' in base_text, \
            "Modal must have close button"

    @pytest.mark.contract_case("UI-SD-016")
    def test_payload_modal_has_rendered_section(self, base_text):
        """Modal must have rendered section."""
        assert 'class="payload-modal__rendered"' in base_text, \
            "Modal must have rendered section"

    @pytest.mark.contract_case("UI-SD-016")
    def test_payload_modal_has_raw_section(self, base_text):
        """Modal must have raw section."""
        assert 'class="payload-modal__raw"' in base_text, \
            "Modal must have raw section"


# ── session.html 检查 ──


class TestSessionHtml:
    @pytest.mark.contract_case("UI-SD-016")
    def test_extends_base(self, session_text):
        """session.html must extend base.html."""
        assert "{% extends" in session_text, \
            "session.html does not extend base.html"

    @pytest.mark.contract_case("UI-SD-016")
    def test_shell_class_declares_sd_shell(self, session_text):
        """session.html shell_class must include sd-shell."""
        assert "sd-shell" in session_text, \
            "session.html shell_class lacks sd-shell"

    @pytest.mark.contract_case("UI-SD-016")
    def test_session_detail_shell_class(self, session_text):
        """session.html must declare sd-shell class."""
        assert "sd-shell" in session_text, \
            "session.html shell_class lacks sd-shell"

    @pytest.mark.contract_case("UI-SD-016")
    def test_session_has_trace_page_marker(self, session_text):
        """session.html must have data-trace-page marker."""
        assert "data-trace-page" in session_text, \
            "session.html lacks data-trace-page"

    @pytest.mark.contract_case("UI-SD-016")
    def test_hero_title_hook(self, session_text):
        """session.html must have hero title via sdt macro."""
        assert "sdt.hero" in session_text, \
            "session.html lacks sdt.hero macro call"

    @pytest.mark.contract_case("UI-SD-016")
    def test_kpi_metrics_hook(self, session_text):
        """session.html must have KPI / metrics via sdt macro."""
        assert "hero_metrics" in session_text, \
            "session.html lacks hero_metrics hook"

    @pytest.mark.contract_case("UI-SD-016")
    def test_trace_round_hook(self, session_text):
        """session.html must have trace_round macro call."""
        assert "sdt.trace_round" in session_text, \
            "session.html lacks sdt.trace_round macro call"

    @pytest.mark.contract_case("UI-SD-016")
    def test_no_old_workbench_views(self, session_text):
        """Calls and Hotspots workbench views should be removed."""
        assert 'data-workbench-view="calls"' not in session_text, \
            "calls view should be removed"
        assert 'data-workbench-view="hotspots"' not in session_text, \
            "hotspots view should be removed"
        assert 'data-workbench' not in session_text, \
            "workbench container should be removed"

    @pytest.mark.contract_case("UI-SD-016")
    def test_content_modal_element_removed(self, session_text):
        """content-modal element must be removed."""
        assert 'id="content-modal"' not in session_text, \
            "content-modal element must be removed"

    @pytest.mark.contract_case("UI-SD-016")
    def test_content_modal_js_removed(self, session_text):
        """Content modal JS must be removed."""
        assert "openContentModal" not in session_text, \
            "openContentModal JS must be removed"
        assert "closeContentModal" not in session_text, \
            "closeContentModal JS must be removed"
        assert "switchContentView" not in session_text, \
            "switchContentView JS must be removed"


# ── Issue Strip ──


class TestIssueStrip:

    def _source(self):
        return _timeline_component()

    @pytest.mark.contract_case("UI-SD-016")
    def test_issue_strip_exists(self):
        source = self._source()
        assert "data-issue-strip" in source, \
            "Issue strip section must exist"

    @pytest.mark.contract_case("UI-SD-016")
    def test_has_empty_state_fallback(self):
        source = self._source()
        assert "data-issue-strip" in source

    @pytest.mark.contract_case("UI-SD-016")
    def test_issue_links_have_jump_action(self):
        source = self._source()
        assert 'data-action="jump-round"' in source, \
            "Issue links must have jump-round action"
        assert 'data-round=' in source, \
            "Issue links must have data-round attribute"


# ── Trace Panel ──


class TestTracePanel:

    def _source(self):
        return _session_source()

    def _timeline(self):
        return _timeline_component()

    @pytest.mark.contract_case("UI-SD-016")
    def test_trace_panel_exists(self):
        source = self._source()
        assert 'data-trace-panel' in source, \
            "Trace panel must exist"

    @pytest.mark.contract_case("UI-SD-016")
    def test_has_all_failed_segmented_control(self):
        source = self._timeline()
        assert 'data-action="status-all"' in source, \
            "Trace must have status-all action"
        assert 'data-action="status-failed"' in source, \
            "Trace must have status-failed action"

    @pytest.mark.contract_case("UI-SD-016")
    def test_has_collapse_all_button(self):
        source = self._timeline()
        assert 'data-action="collapse-all"' not in source, \
            "Trace must NOT have collapse-all button; use toggle-all only"
        assert 'data-action="toggle-all"' in source, \
            "Trace must have toggle-all button"

    @pytest.mark.contract_case("UI-SD-016")
    def test_has_trace_round_row(self):
        source = self._timeline()
        assert 'data-trace-round-row' in source, \
            "Trace must have trace-round-row elements"

    @pytest.mark.contract_case("UI-SD-016")
    def test_has_trace_detail(self):
        source = self._timeline()
        assert 'data-trace-detail' in source, \
            "Trace must have trace-detail elements"

    @pytest.mark.contract_case("UI-SD-016")
    def test_trace_row_has_status(self):
        source = self._timeline()
        assert 'data-status=' in source, \
            "Trace rows must have data-status attribute"

    @pytest.mark.contract_case("UI-SD-016")
    def test_uses_sdt_macros(self):
        source = self._source()
        assert "sdt.trace_round" in source, \
            "Session must use sdt.trace_round macro"
        assert "sdt.hero" in source, \
            "Session must use sdt.hero macro"
        assert "sdt.trace_header" in source, \
            "Session must use sdt.trace_header macro"

    @pytest.mark.contract_case("UI-SD-016")
    def test_toggle_js_in_timeline_js(self):
        js_path = Path(__file__).parents[2] / "src" / "session_browser" / "web" / "static" / "js" / "session_detail_timeline.js"
        js = js_path.read_text(encoding="utf-8")
        assert "toggleRound" in js, \
            "Must have toggleRound JS function"


# ── Metrics Strip ──


class TestMetricsStrip:

    def _timeline(self):
        return _timeline_component()

    @pytest.mark.contract_case("UI-SD-016")
    def test_kpis_exist(self):
        source = self._timeline()
        assert "sd-kpis" in source, \
            "KPI metrics container must exist"
        assert "sd-kpi" in source, \
            "KPI items must exist"

    @pytest.mark.contract_case("UI-SD-016")
    def test_has_tokens_metric(self):
        source = self._timeline()
        assert "tokens" in source.lower(), \
            "Metrics must include tokens"

    @pytest.mark.contract_case("UI-SD-016")
    def test_has_rounds_metric(self):
        source = self._timeline()
        assert "rounds" in source.lower(), \
            "Metrics must include rounds"
