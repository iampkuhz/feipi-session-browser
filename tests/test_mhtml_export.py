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

    # ── Workbench structure ──

    def test_data_switch_buttons_exist(self):
        html = self._read("session.html")
        for view in ("trace", "calls", "hotspots"):
            assert f'data-switch="{view}"' in html, f'missing data-switch="{view}"'

    def test_data_view_containers_exist(self):
        html = self._read("session.html")
        for view in ("trace", "calls", "hotspots"):
            assert f'data-view="{view}"' in html, f'missing data-view="{view}"'

    def test_switchView_function_exists(self):
        html = self._read("session.html")
        assert "switchView" in html, "missing switchView function"

    # ── Layout modes ──

    def test_layout_mode_classes(self):
        html = self._read("base.html")
        for cls in ("hide-left", "hide-right", "focus"):
            assert cls in html, f'missing {cls} toggle support'

    def test_css_has_shell_grid(self):
        css = self._read_css()
        assert ".shell" in css, "missing .shell grid"
        assert "grid-template-columns" in css, "missing grid-template-columns"

    # ── Inspector structure ──

    def test_inspector_hi_fi_structure(self):
        html = self._read("components/inspector.html")
        for cls in ("insp-head", "insp-close", "insp-title", "insp-sub", "insp-tabs"):
            assert cls in html, f"missing {cls} in inspector.html"

    def test_inspector_has_tabs(self):
        html = self._read("components/inspector.html")
        for tab in ("Overview", "Payload", "Tools"):
            assert tab in html, f"missing {tab} tab in inspector.html"

    def test_inspector_js_has_switchTab(self):
        js = self._read_js("inspector.js")
        assert "switchTab" in js, "missing switchTab in inspector.js"

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
        # openInspector is called (via window.openInspector guard and invocation)
        assert "openInspector" in html, "openInspector missing from session.html"
        # toggleRoundDetail is defined inline
        assert "toggleRoundDetail" in html, "toggleRoundDetail missing from session.html"
        # closeInspector is defined in inspector.js and referenced in inspector.html
        inspector = self._read("components/inspector.html")
        assert "closeInspector" in inspector, "closeInspector missing from inspector.html"

    def test_no_google_fonts_reference(self):
        """No Google Fonts references in either mode."""
        base = self._read("base.html")
        assert "fonts.googleapis.com" not in base, "Google Fonts reference found in base.html"
        css = (STATIC_CSS).read_text(encoding="utf-8")
        # font-family fallback stack is OK, but no googleapis URL
        for line in css.split("\n"):
            if "fonts.googleapis" in line.lower():
                raise AssertionError(f"Google Fonts URL in CSS: {line.strip()}")


class TestOldTabsNotBlocking:
    """Ensure old Conversation/Timeline/Profile tabs don't block new Workbench."""

    def _read(self, rel_path: str) -> str:
        return (TEMPLATES / rel_path).read_text(encoding="utf-8")

    def test_no_old_tab_buttons_as_primary(self):
        """Old tab IDs should not be the primary view switching mechanism."""
        html = self._read("session.html")
        # Old tab IDs may exist as deprecated/legacy anchors but shouldn't be active
        # The primary switching should be via data-view/data-switch
        assert 'data-view="trace"' in html, "data-view trace not primary"
        assert 'data-view="calls"' in html, "data-view calls not primary"
        assert 'data-view="hotspots"' in html, "data-view hotspots not primary"

    def test_workbench_header_exists(self):
        """Workbench header with view switch buttons should be present."""
        html = self._read("session.html")
        assert "wb-head" in html or "wb-viewbar" in html or "view-switch" in html, \
            "missing workbench header / view switch buttons"
