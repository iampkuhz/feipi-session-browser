"""Tests for scripts/quality/check_session_detail_static.py."""
import importlib.util
import tempfile
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "quality" / "check_session_detail_static.py"
_spec = importlib.util.spec_from_file_location("check_session_detail_static", SCRIPT_PATH)
_csd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_csd)


GOOD_CSS = """
body.hide-left .shell.phase1-shell { grid-template-columns: 0 minmax(0, 1fr); }
.shell.phase1-shell .main { grid-column: 1 / -1; width: 100%; min-width: 0; }
.session-detail-phase1 { width: min(100%, 1360px); margin: 0 auto; }
.hero-main { grid-template-columns: 1fr; }
.hero-title { overflow-wrap: break-word; word-break: normal; }
"""

GOOD_BASE = '<div class="shell{% block shell_class %}{% endblock %}" data-session-detail-shell>'

GOOD_SESSION = """
{% extends "base.html" %}
{% block shell_class %} no-inspector phase1-shell{% endblock %}
"""


def _run_checks(css, base, session):
    with tempfile.TemporaryDirectory() as td:
        p = Path(td)
        return _csd.run_checks(
            p / "style.css",
            p / "base.html",
            p / "session.html",
        )


def _write(p, text):
    p.write_text(text)


def _run_checks_with_files(css, base, session):
    with tempfile.TemporaryDirectory() as td:
        p = Path(td)
        css_p = p / "style.css"
        base_p = p / "base.html"
        session_p = p / "session.html"
        _write(css_p, css)
        _write(base_p, base)
        _write(session_p, session)
        return _csd.run_checks(css_p, base_p, session_p)


class TestPassingContract:
    def test_full_contract_passes(self):
        out = _run_checks_with_files(GOOD_CSS, GOOD_BASE, GOOD_SESSION)
        assert out["status"] == "PASS"
        assert out["failures"] == []


class TestPhase1HideLeftOverride:
    def test_missing_fails(self):
        css = ".shell.phase1-shell .main { grid-column: 1 / -1; }"
        out = _run_checks_with_files(css, GOOD_BASE, GOOD_SESSION)
        assert out["status"] == "FAIL"
        codes = [f["code"] for f in out["failures"]]
        assert "MISSING_PHASE1_HIDE_LEFT_OVERRIDE" in codes


class TestPhase1MainGridColumn:
    def test_missing_grid_column_fails(self):
        css = "body.hide-left .shell.phase1-shell { grid-template-columns: 0 minmax(0, 1fr); }"
        out = _run_checks_with_files(css, GOOD_BASE, GOOD_SESSION)
        assert out["status"] == "FAIL"
        codes = [f["code"] for f in out["failures"]]
        assert "MISSING_PHASE1_MAIN_GRID_COLUMN" in codes


class TestHeroMainSingleColumn:
    def test_two_column_fails(self):
        css = GOOD_CSS.replace(
            ".hero-main { grid-template-columns: 1fr; }",
            ".session-detail-phase1 .hero-main { grid-template-columns: minmax(0, 1fr) minmax(360px, 520px); }",
        )
        out = _run_checks_with_files(css, GOOD_BASE, GOOD_SESSION)
        assert out["status"] == "FAIL"
        codes = [f["code"] for f in out["failures"]]
        assert "HERO_MAIN_STILL_TWO_COLUMN" in codes


class TestHeroTitleWrapping:
    def test_anywhere_wrap_fails(self):
        css = GOOD_CSS.replace(
            ".hero-title { overflow-wrap: break-word; word-break: normal; }",
            ".hero-title { overflow-wrap: anywhere; }",
        )
        out = _run_checks_with_files(css, GOOD_BASE, GOOD_SESSION)
        assert out["status"] == "FAIL"
        codes = [f["code"] for f in out["failures"]]
        assert "HERO_TITLE_UNSAFE_ANYWHERE_WRAP" in codes

    def test_break_all_fails(self):
        css = GOOD_CSS.replace(
            ".hero-title { overflow-wrap: break-word; word-break: normal; }",
            ".hero-title { word-break: break-all; }",
        )
        out = _run_checks_with_files(css, GOOD_BASE, GOOD_SESSION)
        assert out["status"] == "FAIL"
        codes = [f["code"] for f in out["failures"]]
        assert "HERO_TITLE_UNSAFE_ANYWHERE_WRAP" in codes


class TestSessionShellClassHook:
    def test_missing_shell_class_fails(self):
        session = '{% extends "base.html" %}\n'
        out = _run_checks_with_files(GOOD_CSS, GOOD_BASE, session)
        assert out["status"] == "FAIL"
        codes = [f["code"] for f in out["failures"]]
        assert "MISSING_SESSION_SHELL_CLASS_HOOK" in codes


class TestBaseShellClassApplication:
    def test_missing_application_fails(self):
        base = '<div class="shell" data-session-detail-shell>'
        out = _run_checks_with_files(GOOD_CSS, base, GOOD_SESSION)
        assert out["status"] == "FAIL"
        codes = [f["code"] for f in out["failures"]]
        assert "MISSING_BASE_SHELL_CLASS_APPLICATION" in codes


class TestRealFiles:
    def test_real_repo_files(self):
        """Run against actual repo files to ensure they pass."""
        root = SCRIPT_PATH.parent.parent.parent
        css = root / "src" / "session_browser" / "web" / "static" / "style.css"
        base = root / "src" / "session_browser" / "web" / "templates" / "base.html"
        session = root / "src" / "session_browser" / "web" / "templates" / "session.html"
        if css.exists() and base.exists() and session.exists():
            out = _csd.run_checks(css, base, session)
            assert out["status"] == "PASS", f"Real files failed: {out['failures']}"
