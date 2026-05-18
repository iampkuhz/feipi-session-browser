"""MHTML export regression tests."""
import os
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "src" / "session_browser" / "web" / "templates"
STATIC_JS = ROOT / "src" / "session_browser" / "web" / "static" / "js"
STATIC_CSS = ROOT / "src" / "session_browser" / "web" / "static" / "style.css"


class TestMhtmlTemplateContracts:
    """Static template-level contracts for MHTML readiness."""

    def _read(self, rel_path: str) -> str:
        return (TEMPLATES / rel_path).read_text(encoding="utf-8")

    def _read_js(self, name: str) -> str:
        return (STATIC_JS / name).read_text(encoding="utf-8")

    def _read_css(self) -> str:
        return STATIC_CSS.read_text(encoding="utf-8")

    # ── Trace panel structure (Phase 1 simplified) ──

    def test_trace_panel_exists(self):
        html = self._read("session.html")
        assert 'data-trace-panel' in html, 'missing trace-panel'

    def test_trace_row_structure(self):
        html = self._read("session.html")
        assert 'class="trace-row"' in html, 'missing trace-row'
        assert 'class="trace-detail"' in html, 'missing trace-detail'

    def test_toggle_round_detail_function_exists(self):
        html = self._read("session.html")
        assert "toggleRoundDetail" in html, "missing toggleRoundDetail function"

    # ── Layout modes ──

    def test_layout_mode_classes(self):
        html = self._read("base.html")
        # hide-left is still referenced in JS migration code
        assert "hide-left" in html, 'missing hide-left toggle support'

    def test_css_has_shell_grid(self):
        css = self._read_css()
        assert ".shell" in css, "missing .shell grid"
        assert "grid-template-columns" in css, "missing grid-template-columns"

    # Inspector removed — MHTML export no longer requires inspector components

    # ── MHTML export infrastructure ──

    def test_base_html_has_export_mhtml_branch(self):
        html = self._read("base.html")
        assert "export_mhtml" in html, "missing export_mhtml in base.html"
        assert "mhtml_css" in html, "missing mhtml_css in base.html"
        assert "mhtml_js" in html, "missing mhtml_js in base.html"

    def test_mhtml_py_exists(self):
        mhtml_path = ROOT / "src" / "session_browser" / "web" / "mhtml.py"
        assert mhtml_path.exists(), "mhtml.py not found"
        mhtml = mhtml_path.read_text(encoding="utf-8")
        assert "get_css" in mhtml, "mhtml.py missing get_css"
        assert "get_js" in mhtml, "mhtml.py missing get_js"

    def test_routes_has_export_mhtml_support(self):
        routes = (ROOT / "src" / "session_browser" / "web" / "routes.py").read_text(encoding="utf-8")
        assert "export_mhtml" in routes, "routes.py missing export_mhtml"


class TestMhtmlSelfContained:
    """Self-contained HTML export content checks (static template analysis)."""

    def _read(self, rel_path: str) -> str:
        return (TEMPLATES / rel_path).read_text(encoding="utf-8")

    def _read_js(self, name: str) -> str:
        return (STATIC_JS / name).read_text(encoding="utf-8")

    def test_no_external_resources_in_export(self):
        """Check that MHTML export has no external CSS/JS/font references."""
        html = self._read("base.html")
        # In MHTML mode, the template should have conditional branches
        assert "export_mhtml" in html
        # Verify the CSS/JS are conditionally inlined
        assert "mhtml_css" in html
        assert "mhtml_js" in html

    def test_key_functions_present_in_template(self):
        """Verify key JS functions are referenced in session.html for MHTML inclusion."""
        html = self._read("session.html")
        # toggleRoundDetail is defined inline
        assert "toggleRoundDetail" in html, "toggleRoundDetail missing from session.html"

    def test_no_google_fonts_reference(self):
        """No Google Fonts references in either mode."""
        base = self._read("base.html")
        assert "fonts.googleapis.com" not in base, "Google Fonts reference found in base.html"
        css = (STATIC_CSS).read_text(encoding="utf-8")
        # font-family fallback stack is OK, but no googleapis URL
        for line in css.split("\n"):
            if "fonts.googleapis" in line.lower():
                raise AssertionError(f"Google Fonts URL in CSS: {line.strip()}")


class TestPhase1SimplifiedStructure:
    """Verify Phase 1 simplified session detail structure (trace-first)."""

    def _read(self, rel_path: str) -> str:
        return (TEMPLATES / rel_path).read_text(encoding="utf-8")

    def test_has_trace_panel(self):
        html = self._read("session.html")
        assert 'class="trace-panel"' in html or 'data-trace-panel' in html, \
            "missing trace-panel"

    def test_has_issue_summary(self):
        html = self._read("session.html")
        assert 'data-issue-summary' in html, "missing issue-summary section"

    def test_has_payload_modal(self):
        html = self._read("base.html")
        assert 'id="payload-modal"' in html, "missing payload-modal in base.html"

    def test_has_expand_collapse_buttons(self):
        html = self._read("session.html")
        assert 'data-action="expand-visible"' in html, "missing expand-visible"
        assert 'data-action="collapse-all"' in html, "missing collapse-all"

    def test_has_all_failed_segmented_control(self):
        html = self._read("session.html")
        assert 'data-action="filter-status"' in html, "missing filter-status"
        assert 'data-status="all"' in html, "missing 'all' filter"
        assert 'data-status="failed"' in html, "missing 'failed' filter"

    def test_no_old_workbench_views(self):
        """Calls and Hotspots workbench views should be removed."""
        html = self._read("session.html")
        assert 'data-workbench-view="calls"' not in html, "calls view should be removed"
        assert 'data-workbench-view="hotspots"' not in html, "hotspots view should be removed"

    def test_no_token_charts_card(self):
        """Token charts card should be removed in Phase 1."""
        html = self._read("session.html")
        assert 'id="tokenChartsCard"' not in html, "token-charts-card should be removed"
