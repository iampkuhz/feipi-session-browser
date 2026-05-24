"""Tests for scripts/quality/static_contract_check.py pure functions."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "quality"))

from static_contract_check import (
    check_no_important,
    check_css_load_order,
    check_no_dead_css,
    check_no_duplicate_base_css,
    check_payload_modal_ownership,
    check_shell_ownership,
)


# ── check_no_important ────────────────────────────────────────────────


class TestCheckNoImportant:
    def test_clean_css_passes(self, tmp_path):
        css = tmp_path / "clean.css"
        css.write_text(".foo { color: red; }")
        assert check_no_important([css]) == []

    def test_important_blocks(self, tmp_path):
        css = tmp_path / "bad.css"
        css.write_text(".foo { color: red !important; }")
        errors = check_no_important([css])
        assert len(errors) == 1
        assert "!important" in errors[0]

    def test_important_in_comment_still_matches(self, tmp_path):
        """Regex matches !important even in comments — gate is conservative."""
        css = tmp_path / "commented.css"
        css.write_text("/* color: red !important; */")
        errors = check_no_important([css])
        # The regex still matches because we don't strip comments for this check
        # (the actual CSS has no active !important, but the gate is conservative)
        assert len(errors) == 1

    def test_multiple_files(self, tmp_path):
        good = tmp_path / "good.css"
        bad = tmp_path / "bad.css"
        good.write_text(".a { margin: 0; }")
        bad.write_text(".b { margin: 0 !important; }")
        errors = check_no_important([good, bad])
        assert len(errors) == 1
        assert "bad.css" in errors[0]


# ── check_css_load_order ──────────────────────────────────────────────


class TestCheckCssLoadOrder:
    def test_correct_order_passes(self):
        html = """
    <link rel="stylesheet" href="/static/style.css">
    <link rel="stylesheet" href="/static/css/shell.css">
    <link rel="stylesheet" href="/static/css/ui-primitives.css">
    <link rel="stylesheet" href="/static/css/legacy-aliases.css">
    {% block head_extra %}{% endblock %}
    """
        assert check_css_load_order(html) == []

    def test_wrong_order_blocks(self):
        """legacy-aliases before ui-primitives should BLOCK."""
        html = """
    <link rel="stylesheet" href="/static/style.css">
    <link rel="stylesheet" href="/static/css/shell.css">
    <link rel="stylesheet" href="/static/css/legacy-aliases.css">
    <link rel="stylesheet" href="/static/css/ui-primitives.css">
    {% block head_extra %}{% endblock %}
    """
        errors = check_css_load_order(html)
        assert len(errors) >= 1
        assert "ui-primitives.css" in errors[0]

    def test_missing_item_blocks(self):
        html = """
    <link rel="stylesheet" href="/static/style.css">
    {% block head_extra %}{% endblock %}
    """
        errors = check_css_load_order(html)
        assert len(errors) >= 1
        assert "缺失必需项" in errors[0]

    def test_head_extra_before_legacy_blocks(self):
        """head_extra must come after legacy-aliases."""
        html = """
    <link rel="stylesheet" href="/static/style.css">
    <link rel="stylesheet" href="/static/css/shell.css">
    <link rel="stylesheet" href="/static/css/ui-primitives.css">
    {% block head_extra %}{% endblock %}
    <link rel="stylesheet" href="/static/css/legacy-aliases.css">
    """
        errors = check_css_load_order(html)
        assert len(errors) >= 1
        assert "legacy-aliases.css" in errors[0]
        assert "head_extra" in errors[0]


# ── check_no_dead_css ─────────────────────────────────────────────────


class TestCheckNoDeadCss:
    def test_valid_css_passes(self, tmp_path):
        css = tmp_path / "valid.css"
        css.write_text(".foo { color: red; }")
        assert check_no_dead_css([css]) == []

    def test_only_comments_blocks(self, tmp_path):
        css = tmp_path / "dead.css"
        css.write_text("/* This is a comment */\n/* Another comment */\n")
        errors = check_no_dead_css([css])
        assert len(errors) == 1
        assert "死 CSS 文件" in errors[0]

    def test_empty_file_blocks(self, tmp_path):
        css = tmp_path / "empty.css"
        css.write_text("")
        errors = check_no_dead_css([css])
        assert len(errors) == 1

    def test_only_whitespace_blocks(self, tmp_path):
        css = tmp_path / "whitespace.css"
        css.write_text("   \n\n   \t\n")
        errors = check_no_dead_css([css])
        assert len(errors) == 1

    def test_comment_with_rules_passes(self, tmp_path):
        css = tmp_path / "has_rules.css"
        css.write_text("/* Header */\n.header { display: flex; }")
        assert check_no_dead_css([css]) == []


# ── check_no_duplicate_base_css ─────────────────────────────────────


class TestCheckNoDuplicateBaseCss:
    def test_base_html_skipped(self, tmp_path):
        """base.html itself should be skipped."""
        base = tmp_path / "base.html"
        base.write_text('<link rel="stylesheet" href="/static/style.css">')
        assert check_no_duplicate_base_css([base]) == []

    def test_page_without_base_css_passes(self, tmp_path):
        """Page template with only page-specific CSS should pass."""
        page = tmp_path / "dashboard.html"
        page.write_text('<link rel="stylesheet" href="/static/css/dashboard.css">')
        assert check_no_duplicate_base_css([page]) == []

    def test_page_with_style_css_blocks(self, tmp_path):
        """Page loading style.css should BLOCK."""
        page = tmp_path / "dashboard.html"
        page.write_text('<link rel="stylesheet" href="/static/style.css">')
        errors = check_no_duplicate_base_css([page])
        assert len(errors) == 1
        assert "style.css" in errors[0]

    def test_page_with_multiple_base_css_blocks(self, tmp_path):
        """Page loading multiple base CSS should list all."""
        page = tmp_path / "page.html"
        page.write_text(
            '<link rel="stylesheet" href="/static/style.css">\n'
            '<link rel="stylesheet" href="/static/css/ui-primitives.css">'
        )
        errors = check_no_duplicate_base_css([page])
        assert len(errors) == 1
        assert "style.css" in errors[0]
        assert "ui-primitives.css" in errors[0]


# ── check_payload_modal_ownership ─────────────────────────────────────


class TestCheckPayloadModalOwnership:
    def test_ui_primitives_exempt(self, tmp_path):
        """ui-primitives.css is the authority, should not warn."""
        css = tmp_path / "ui-primitives.css"
        css.write_text(".payload-modal { display: flex; }")
        warnings = check_payload_modal_ownership([css])
        assert warnings == []

    def test_bare_payload_modal_warns(self, tmp_path):
        """Bare .payload-modal in non-primitive file should WARN."""
        css = tmp_path / "style.css"
        css.write_text(".payload-modal { display: flex; }")
        warnings = check_payload_modal_ownership([css])
        assert len(warnings) == 1
        assert "payload-modal" in warnings[0].lower()

    def test_page_scoped_not_warn(self, tmp_path):
        """Page-scoped .session-detail-page .payload-modal should not WARN."""
        css = tmp_path / "session-detail.css"
        css.write_text(".session-detail-page .payload-modal { width: 80vw; }")
        warnings = check_payload_modal_ownership([css])
        assert warnings == []

    def test_hash_payload_modal_warns(self, tmp_path):
        """#payload-modal bare definition should WARN."""
        css = tmp_path / "legacy-aliases.css"
        css.write_text("#payload-modal { display: flex; }")
        warnings = check_payload_modal_ownership([css])
        assert len(warnings) == 1


# ── check_shell_ownership ─────────────────────────────────────────────


class TestCheckShellOwnership:
    def test_style_css_exempt(self, tmp_path):
        """style.css may contain residual shell references."""
        css = tmp_path / "style.css"
        css.write_text(".shell { display: grid; }")
        warnings = check_shell_ownership([css])
        assert warnings == []

    def test_shell_css_exempt(self, tmp_path):
        """shell.css is the shell authority, should not warn."""
        css = tmp_path / "shell.css"
        css.write_text(".shell { display: grid; }")
        warnings = check_shell_ownership([css])
        assert warnings == []

    def test_legacy_aliases_exempt(self, tmp_path):
        """legacy-aliases.css is compat layer, should not warn."""
        css = tmp_path / "legacy-aliases.css"
        css.write_text(".app-shell { display: grid; }")
        warnings = check_shell_ownership([css])
        assert warnings == []

    def test_page_css_warns(self, tmp_path):
        """Page CSS with shell selectors should WARN."""
        css = tmp_path / "dashboard.css"
        css.write_text(".app-shell { display: grid; }")
        warnings = check_shell_ownership([css])
        assert len(warnings) == 1
        assert ".app-shell" in warnings[0]

    def test_body_hide_left_warns(self, tmp_path):
        """body.hide-left in page CSS should WARN."""
        css = tmp_path / "agents.css"
        css.write_text("body.hide-left .sidebar { display: none; }")
        warnings = check_shell_ownership([css])
        assert len(warnings) == 1
        assert "body.hide-left" in warnings[0]


# ── Integration: actual repo files ────────────────────────────────────


class TestActualRepoState:
    def test_no_important_in_repo_css(self):
        static = ROOT / "src/session_browser/web/static"
        css_files = list(static.rglob("*.css"))
        errors = check_no_important(css_files)
        assert errors == [], f"!important found: {errors}"

    def test_css_load_order_in_base_html(self):
        base_html = ROOT / "src/session_browser/web/templates/base.html"
        text = base_html.read_text(encoding="utf-8")
        errors = check_css_load_order(text)
        assert errors == [], f"load order violation: {errors}"

    def test_no_dead_css_in_repo(self):
        """After deleting session-detail-timeline.css, no dead CSS should remain."""
        static = ROOT / "src/session_browser/web/static"
        css_files = list(static.rglob("*.css"))
        errors = check_no_dead_css(css_files)
        assert errors == [], f"dead CSS found: {errors}"

    def test_timeline_css_deleted(self):
        """session-detail-timeline.css should be deleted."""
        path = ROOT / "src/session_browser/web/static/css/session-detail-timeline.css"
        assert not path.exists(), "session-detail-timeline.css should be deleted"
