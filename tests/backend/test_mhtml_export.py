"""MHTML export regression tests."""
import os
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
TEMPLATES = ROOT / "src" / "session_browser" / "web" / "templates"
STATIC_JS = ROOT / "src" / "session_browser" / "web" / "static" / "js"
STATIC_CSS_DIR = ROOT / "src" / "session_browser" / "web" / "static" / "css"

# CSS files bundled by mhtml.py get_css()
MHTML_CSS_FILES = [
    "css/tokens.css",
    "css/base.css",
    "css/shell.css",
    "css/ui-primitives.css",
    "css/legacy-aliases.css",
]


class TestMhtmlTemplateContracts:
    """Static template-level contracts for MHTML readiness."""

    def _read(self, rel_path: str) -> str:
        return (TEMPLATES / rel_path).read_text(encoding="utf-8")

    def _read_js(self, name: str) -> str:
        return (STATIC_JS / name).read_text(encoding="utf-8")

    def _read_css(self) -> str:
        """Read all MHTML-bundled CSS files concatenated."""
        parts = []
        for rel in MHTML_CSS_FILES:
            p = ROOT / "src" / "session_browser" / "web" / "static" / rel
            if p.exists():
                parts.append(p.read_text(encoding="utf-8"))
        return "\n".join(parts)

    # ── Trace panel structure (Phase 1 simplified) ──

    def test_trace_panel_exists(self):
        html = self._read("session.html")
        assert 'data-trace-panel' in html, 'missing trace-panel'

    def test_trace_row_structure(self):
        # v9 uses component macros; trace_round is defined in session_detail_timeline.html
        html = self._read("session.html")
        assert "sdt.trace_round" in html, "missing sdt.trace_round macro call"
        component = self._read("components/session_detail_timeline.html")
        assert 'data-trace-round-row' in component, 'missing trace-round-row'
        assert 'data-trace-detail' in component, 'missing trace-detail'

    def test_toggle_round_detail_function_exists(self):
        # v9 uses toggleRound in session_detail_timeline.js
        js = (STATIC_JS / "session_detail_timeline.js").read_text(encoding="utf-8")
        assert "function toggleRound" in js, "missing toggleRound function"

    # ── Layout modes ──

    def test_layout_mode_classes(self):
        js = self._read_js("view-switching.js")
        # hide-left migration code lives in view-switching.js
        assert "hide-left" in js, 'missing hide-left toggle support'

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
        """Verify key JS functions are referenced for MHTML inclusion."""
        # v9 uses toggleRound in session_detail_timeline.js
        js = self._read_js("session_detail_timeline.js")
        assert "toggleRound" in js, "toggleRound missing from session_detail_timeline.js"

    def test_no_google_fonts_reference(self):
        """No Google Fonts references in either mode."""
        base = self._read("base.html")
        assert "fonts.googleapis.com" not in base, "Google Fonts reference found in base.html"
        for rel in MHTML_CSS_FILES:
            p = ROOT / "src" / "session_browser" / "web" / "static" / rel
            if p.exists():
                css = p.read_text(encoding="utf-8")
                for line in css.split("\n"):
                    if "fonts.googleapis" in line.lower():
                        raise AssertionError(f"Google Fonts URL in CSS ({rel}): {line.strip()}")


class TestPhase1SimplifiedStructure:
    """Verify Phase 1 simplified session detail structure (trace-first)."""

    def _read(self, rel_path: str) -> str:
        return (TEMPLATES / rel_path).read_text(encoding="utf-8")

    def test_has_trace_panel(self):
        html = self._read("session.html")
        assert 'class="trace-panel"' in html or 'data-trace-panel' in html, \
            "missing trace-panel"

    def test_has_issue_summary(self):
        # v9 uses data-issue-strip in the component macro
        component = self._read("components/session_detail_timeline.html")
        assert 'data-issue-strip' in component, "missing issue-strip section"

    def test_has_payload_modal(self):
        html = self._read("base.html")
        assert 'id="payload-modal"' in html, "missing payload-modal in base.html"

    def test_has_expand_collapse_buttons(self):
        # v9 has collapse-all in the component macro
        component = self._read("components/session_detail_timeline.html")
        assert 'data-action="collapse-all"' in component, "missing collapse-all"

    def test_has_all_failed_segmented_control(self):
        # v18: filter controls use status-all/status-failed (HIFI table migration)
        component = self._read("components/session_detail_timeline.html")
        has_new = 'data-action="status-all"' in component and 'data-action="status-failed"' in component
        has_legacy = 'data-action="filter-status"' in component
        assert has_new or has_legacy, "missing filter status buttons (status-all/status-failed or legacy filter-status)"

    def test_no_old_workbench_views(self):
        """Calls and Hotspots workbench views should be removed."""
        html = self._read("session.html")
        assert 'data-workbench-view="calls"' not in html, "calls view should be removed"
        assert 'data-workbench-view="hotspots"' not in html, "hotspots view should be removed"

    def test_no_token_charts_card(self):
        """Token charts card should be removed in Phase 1."""
        html = self._read("session.html")
        assert 'id="tokenChartsCard"' not in html, "token-charts-card should be removed"
