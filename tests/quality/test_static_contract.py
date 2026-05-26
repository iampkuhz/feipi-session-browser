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
    check_innerhtml_safety,
    check_css_ownership_gate,
    check_no_global_component_override,
    check_no_new_legacy_selector,
    check_selector_depth_new_block,
    check_no_raw_innerhtml_new_block,
    check_no_layout_inline_style_new_block,
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
    <link rel="stylesheet" href="/static/css/tokens.css">
    <link rel="stylesheet" href="/static/css/base.css">
    <link rel="stylesheet" href="/static/css/shell.css">
    <link rel="stylesheet" href="/static/css/ui-primitives.css">
    <link rel="stylesheet" href="/static/css/legacy-aliases.css">
    {% block head_extra %}{% endblock %}
    """
        assert check_css_load_order(html) == []

    def test_wrong_order_blocks(self):
        """legacy-aliases before ui-primitives should BLOCK."""
        html = """
    <link rel="stylesheet" href="/static/css/tokens.css">
    <link rel="stylesheet" href="/static/css/base.css">
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
    <link rel="stylesheet" href="/static/css/tokens.css">
    {% block head_extra %}{% endblock %}
    """
        errors = check_css_load_order(html)
        assert len(errors) >= 1
        assert "缺失必需项" in errors[0]

    def test_head_extra_before_legacy_blocks(self):
        """head_extra must come after legacy-aliases."""
        html = """
    <link rel="stylesheet" href="/static/css/tokens.css">
    <link rel="stylesheet" href="/static/css/base.css">
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
        base.write_text('<link rel="stylesheet" href="/static/css/tokens.css">')
        assert check_no_duplicate_base_css([base]) == []

    def test_page_without_base_css_passes(self, tmp_path):
        """Page template with only page-specific CSS should pass."""
        page = tmp_path / "dashboard.html"
        page.write_text('<link rel="stylesheet" href="/static/css/dashboard.css">')
        assert check_no_duplicate_base_css([page]) == []

    def test_page_with_tokens_css_blocks(self, tmp_path):
        """Page loading tokens.css should BLOCK."""
        page = tmp_path / "dashboard.html"
        page.write_text('<link rel="stylesheet" href="/static/css/tokens.css">')
        errors = check_no_duplicate_base_css([page])
        assert len(errors) == 1
        assert "tokens.css" in errors[0]

    def test_page_with_base_css_blocks(self, tmp_path):
        """Page loading base.css should BLOCK."""
        page = tmp_path / "dashboard.html"
        page.write_text('<link rel="stylesheet" href="/static/css/base.css">')
        errors = check_no_duplicate_base_css([page])
        assert len(errors) == 1
        assert "base.css" in errors[0]

    def test_page_with_multiple_base_css_blocks(self, tmp_path):
        """Page loading multiple base CSS should list all."""
        page = tmp_path / "page.html"
        page.write_text(
            '<link rel="stylesheet" href="/static/css/tokens.css">\n'
            '<link rel="stylesheet" href="/static/css/ui-primitives.css">'
        )
        errors = check_no_duplicate_base_css([page])
        assert len(errors) == 1
        assert "tokens.css" in errors[0]
        assert "ui-primitives.css" in errors[0]


# ── check_payload_modal_ownership ─────────────────────────────────────


class TestCheckPayloadModalOwnership:
    def test_ui_primitives_exempt(self, tmp_path):
        """ui-primitives.css is the authority, should not error or warn."""
        css = tmp_path / "ui-primitives.css"
        css.write_text(".payload-modal { display: flex; }")
        errors, warnings = check_payload_modal_ownership([css])
        assert errors == []
        assert warnings == []

    def test_bare_payload_modal_blocks(self, tmp_path):
        """Bare .payload-modal in non-primitive, non-legacy file should BLOCK."""
        css = tmp_path / "session-detail.css"
        css.write_text(".payload-modal { display: flex; }")
        errors, warnings = check_payload_modal_ownership([css])
        assert len(errors) == 1
        assert "payload-modal" in errors[0].lower()
        assert warnings == []

    def test_page_scoped_not_warn(self, tmp_path):
        """Page-scoped .session-detail-page .payload-modal should not BLOCK."""
        css = tmp_path / "session-detail.css"
        css.write_text(".session-detail-page .payload-modal { width: 80vw; }")
        errors, warnings = check_payload_modal_ownership([css])
        assert errors == []
        assert warnings == []

    def test_legacy_aliases_warn_not_block(self, tmp_path):
        """legacy-aliases.css bare #payload-modal should WARN, not BLOCK."""
        css = tmp_path / "legacy-aliases.css"
        css.write_text("#payload-modal { display: flex; }")
        errors, warnings = check_payload_modal_ownership([css])
        assert errors == []
        assert len(warnings) == 1
        assert "payload-modal" in warnings[0].lower()


# ── check_shell_ownership ─────────────────────────────────────────────


class TestCheckShellOwnership:
    def test_legacy_aliases_exempt(self, tmp_path):
        """legacy-aliases.css may contain shell references for backward compat."""
        css = tmp_path / "legacy-aliases.css"
        css.write_text(".shell { display: grid; }")
        warnings = check_shell_ownership([css])
        assert warnings == []

    def test_shell_css_exempt(self, tmp_path):
        """shell.css is the shell authority, should not warn."""
        css = tmp_path / "shell.css"
        css.write_text(".shell { display: grid; }")
        warnings = check_shell_ownership([css])
        assert warnings == []

    def test_base_css_exempt(self, tmp_path):
        """base.css is a base file, should not warn."""
        css = tmp_path / "base.css"
        css.write_text("body { font-family: sans-serif; }")
        warnings = check_shell_ownership([css])
        assert warnings == []

    def test_tokens_css_exempt(self, tmp_path):
        """tokens.css is a tokens file, should not warn."""
        css = tmp_path / "tokens.css"
        css.write_text(":root { --shell-w: 220px; }")
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


# ── check_innerhtml_safety ────────────────────────────────────────────


class TestCheckInnerhtmlSafety:
    def test_no_innerhtml_passes(self, tmp_path):
        """JS without innerHTML should not warn."""
        js = tmp_path / "clean.js"
        js.write_text("var x = 1;")
        warnings = check_innerhtml_safety([js])
        assert warnings == []

    def test_innerhtml_with_escape_passes(self, tmp_path):
        """innerHTML with escapeHtml helper should not warn."""
        js = tmp_path / "safe.js"
        js.write_text(
            "function escapeHtml(s) { return s; }"
            "el.innerHTML = escapeHtml(userInput);"
        )
        warnings = check_innerhtml_safety([js])
        assert warnings == []

    def test_innerhtml_with_sanitize_passes(self, tmp_path):
        """innerHTML with sanitize should not warn."""
        js = tmp_path / "safe.js"
        js.write_text("el.innerHTML = DOMPurify.sanitize(html);")
        warnings = check_innerhtml_safety([js])
        assert warnings == []

    def test_innerhtml_without_safety_warns(self, tmp_path):
        """Raw innerHTML without escape helper should WARN."""
        js = tmp_path / "unsafe.js"
        js.write_text("el.innerHTML = '<div>' + userInput + '</div>';")
        warnings = check_innerhtml_safety([js])
        assert len(warnings) == 1
        assert "innerHTML" in warnings[0]

    def test_innerhtml_clearing_not_warned(self, tmp_path):
        """Clearing innerHTML (el.innerHTML = '') should not warn."""
        js = tmp_path / "clear.js"
        js.write_text("container.innerHTML = '';")
        warnings = check_innerhtml_safety([js])
        assert warnings == []

    def test_multiple_files_reports_per_file(self, tmp_path):
        """Each file with unsafe innerHTML gets its own warning."""
        safe = tmp_path / "safe.js"
        unsafe = tmp_path / "unsafe.js"
        safe.write_text("el.innerHTML = DOMPurify.sanitize(x);")
        unsafe.write_text("el.innerHTML = userInput;")
        warnings = check_innerhtml_safety([safe, unsafe])
        assert len(warnings) == 1
        assert "unsafe.js" in warnings[0]


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


# ── V9 NEW gates: bad-fixture tests ────────────────────────────────────


# ── check_css_ownership_gate ──────────────────────────────────────────


class TestCheckCssOwnershipGate:
    def test_clean_page_css_passes(self, tmp_path):
        css = tmp_path / "dashboard.css"
        css.write_text(".dashboard-page .card { padding: 16px; }")
        assert check_css_ownership_gate([css]) == []

    def test_shell_selector_in_page_blocks(self, tmp_path):
        """Page CSS defining .shell should BLOCK."""
        css = tmp_path / "dashboard.css"
        css.write_text(".shell { grid-template-columns: 200px 1fr; }")
        errors = check_css_ownership_gate([css])
        assert len(errors) == 1
        assert ".shell" in errors[0]

    def test_app_shell_in_page_blocks(self, tmp_path):
        """Page CSS defining .app-shell should BLOCK."""
        css = tmp_path / "sessions.css"
        css.write_text(".app-shell { display: grid; }")
        errors = check_css_ownership_gate([css])
        assert len(errors) == 1
        assert ".app-shell" in errors[0]

    def test_body_state_in_page_blocks(self, tmp_path):
        """Page CSS defining body.hide-left should BLOCK."""
        css = tmp_path / "agents.css"
        css.write_text("body.hide-left .sidebar { display: none; }")
        errors = check_css_ownership_gate([css])
        assert len(errors) == 1
        assert "body" in errors[0]

    def test_shell_css_exempt(self, tmp_path):
        """shell.css defining .shell should not error."""
        css = tmp_path / "shell.css"
        css.write_text(".shell { grid-template-columns: var(--sidebar) 1fr; }")
        assert check_css_ownership_gate([css]) == []

    def test_tokens_with_selector_blocks(self, tmp_path):
        """tokens.css with non-:root selector should BLOCK."""
        css = tmp_path / "tokens.css"
        css.write_text(".btn { color: red; }")
        errors = check_css_ownership_gate([css])
        assert len(errors) == 1

    def test_page_grid_template_allowed(self, tmp_path):
        """Page CSS with grid-template-columns for content grid is allowed."""
        css = tmp_path / "dashboard.css"
        css.write_text(".metric-grid { grid-template-columns: repeat(4, 1fr); }")
        assert check_css_ownership_gate([css]) == []


# ── check_no_global_component_override ────────────────────────────────


class TestCheckNoGlobalComponentOverride:
    def test_clean_page_css_passes(self, tmp_path):
        css = tmp_path / "dashboard.css"
        css.write_text(".dashboard-page .card { padding: 16px; }")
        assert check_no_global_component_override([css]) == []

    def test_bare_payload_modal_blocks(self, tmp_path):
        """Page CSS with bare .payload-modal should BLOCK."""
        css = tmp_path / "session-detail.css"
        css.write_text(".payload-modal { display: flex; }")
        errors = check_no_global_component_override([css])
        assert len(errors) == 1
        assert ".payload-modal" in errors[0]

    def test_bare_data_table_blocks(self, tmp_path):
        """Page CSS with bare .data-table should BLOCK."""
        css = tmp_path / "sessions.css"
        css.write_text(".data-table { width: 100%; }")
        errors = check_no_global_component_override([css])
        assert len(errors) == 1
        assert ".data-table" in errors[0]

    def test_bare_btn_blocks(self, tmp_path):
        """Page CSS with bare .btn should BLOCK."""
        css = tmp_path / "dashboard.css"
        css.write_text(".btn { border-radius: 4px; }")
        errors = check_no_global_component_override([css])
        assert len(errors) == 1
        assert ".btn" in errors[0]

    def test_bare_modal_blocks(self, tmp_path):
        """Page CSS with bare .modal should BLOCK."""
        css = tmp_path / "agents.css"
        css.write_text(".modal { z-index: 1000; }")
        errors = check_no_global_component_override([css])
        assert len(errors) == 1
        assert ".modal" in errors[0]

    def test_ui_primitives_exempt(self, tmp_path):
        """ui-primitives.css defining primitives is allowed."""
        css = tmp_path / "ui-primitives.css"
        css.write_text(".payload-modal { display: flex; }\n.data-table { width: 100%; }")
        assert check_no_global_component_override([css]) == []

    def test_scoped_selector_allowed(self, tmp_path):
        """Page-scoped descendant selector is allowed."""
        css = tmp_path / "dashboard.css"
        css.write_text(".dashboard-page .payload-modal { width: 80vw; }")
        assert check_no_global_component_override([css]) == []


# ── check_no_new_legacy_selector ──────────────────────────────────────


class TestCheckNoNewLegacySelector:
    def test_clean_page_css_passes(self, tmp_path):
        css = tmp_path / "dashboard.css"
        css.write_text(".dashboard-page .card { padding: 16px; }")
        assert check_no_new_legacy_selector([css]) == []

    def test_legacy_app_shell_blocks(self, tmp_path):
        """New .app-shell reference in page CSS should BLOCK."""
        css = tmp_path / "dashboard.css"
        css.write_text(".app-shell { display: grid; }")
        errors = check_no_new_legacy_selector([css])
        assert len(errors) == 1
        assert ".app-shell" in errors[0]

    def test_shell_css_exempt(self, tmp_path):
        """shell.css legacy references are allowed."""
        css = tmp_path / "shell.css"
        css.write_text(".app-shell { display: grid; }")
        assert check_no_new_legacy_selector([css]) == []


# ── check_selector_depth_new_block ────────────────────────────────────


class TestCheckSelectorDepthNewBlock:
    def test_shallow_selectors_pass(self, tmp_path):
        css = tmp_path / "clean.css"
        css.write_text(".foo { color: red; }\n.foo .bar { margin: 0; }")
        assert check_selector_depth_new_block([css]) == []

    def test_depth_3_passes(self, tmp_path):
        """Depth exactly 3 should pass (BLOCK_THRESHOLD > 3)."""
        css = tmp_path / "boundary.css"
        css.write_text(".a .b .c { color: red; }")
        assert check_selector_depth_new_block([css]) == []

    def test_depth_4_blocks(self, tmp_path):
        """Depth > 3 should BLOCK."""
        css = tmp_path / "bad.css"
        css.write_text(".a .b .c .d { color: red; }")
        errors = check_selector_depth_new_block([css])
        assert len(errors) == 1
        assert "depth=4" in errors[0]

    def test_child_combinator_counts(self, tmp_path):
        """Child combinators count towards depth."""
        css = tmp_path / "bad.css"
        css.write_text(".a > .b + .c .d { color: red; }")
        errors = check_selector_depth_new_block([css])
        assert len(errors) == 1

    def test_pseudo_class_not_extra(self, tmp_path):
        """Pseudo classes don't add depth."""
        css = tmp_path / "ok.css"
        css.write_text(".a .b .c:hover { color: red; }")
        assert check_selector_depth_new_block([css]) == []


# ── check_no_raw_innerhtml_new_block ──────────────────────────────────


class TestCheckNoRawInnerhtmlNewBlock:
    def test_clean_js_passes(self, tmp_path):
        js = tmp_path / "clean.js"
        js.write_text("var x = 1;")
        assert check_no_raw_innerhtml_new_block([js]) == []

    def test_raw_innerhtml_blocks(self, tmp_path):
        """Raw innerHTML = should BLOCK."""
        js = tmp_path / "unsafe.js"
        js.write_text("el.innerHTML = '<div>' + userInput + '</div>';")
        errors = check_no_raw_innerhtml_new_block([js])
        assert len(errors) == 1
        assert "innerHTML" in errors[0]

    def test_innerhtml_clear_allowed(self, tmp_path):
        """Clearing innerHTML (innerHTML = '') should not BLOCK."""
        js = tmp_path / "clear.js"
        js.write_text("container.innerHTML = '';")
        assert check_no_raw_innerhtml_new_block([js]) == []

    def test_escapehtml_helper_passes(self, tmp_path):
        """innerHTML with escapeHtml helper should PASS."""
        js = tmp_path / "safe.js"
        js.write_text("function escapeHtml(s) { return s; }\nel.innerHTML = escapeHtml(userInput);")
        assert check_no_raw_innerhtml_new_block([js]) == []

    def test_dompurify_passes(self, tmp_path):
        """innerHTML with DOMPurify should PASS."""
        js = tmp_path / "safe.js"
        js.write_text("el.innerHTML = DOMPurify.sanitize(html);")
        assert check_no_raw_innerhtml_new_block([js]) == []

    def test_comment_line_skipped(self, tmp_path):
        """innerHTML in comments should be skipped."""
        js = tmp_path / "comment.js"
        js.write_text("// el.innerHTML = 'test';")
        assert check_no_raw_innerhtml_new_block([js]) == []


# ── check_no_layout_inline_style_new_block ────────────────────────────


class TestCheckNoLayoutInlineStyleNewBlock:
    def test_clean_html_passes(self, tmp_path):
        html = tmp_path / "clean.html"
        html.write_text('<div class="foo">hello</div>')
        assert check_no_layout_inline_style_new_block([html], []) == []

    def test_layout_inline_style_blocks(self, tmp_path):
        """HTML with layout inline style should BLOCK."""
        html = tmp_path / "bad.html"
        html.write_text('<div style="display: flex;">hello</div>')
        errors = check_no_layout_inline_style_new_block([html], [])
        assert len(errors) == 1
        assert "layout inline style" in errors[0]

    def test_custom_property_only_passes(self, tmp_path):
        """Pure CSS custom property should not BLOCK."""
        html = tmp_path / "custom.html"
        html.write_text('<div style="--segment-width: 200px;">hello</div>')
        assert check_no_layout_inline_style_new_block([html], []) == []

    def test_mixed_custom_property_blocks(self, tmp_path):
        """Custom property + layout property should BLOCK."""
        html = tmp_path / "mixed.html"
        html.write_text('<div style="--segment-width: 200px; display: flex;">hello</div>')
        errors = check_no_layout_inline_style_new_block([html], [])
        assert len(errors) == 1

    def test_template_variable_skipped(self, tmp_path):
        """Template variable injection should be skipped."""
        html = tmp_path / "template.html"
        html.write_text('<div style="{{ grid_style }}">hello</div>')
        assert check_no_layout_inline_style_new_block([html], []) == []

    def test_js_style_display_blocks(self, tmp_path):
        """JS .style.display = should BLOCK."""
        js = tmp_path / "bad.js"
        js.write_text("el.style.display = 'none';")
        errors = check_no_layout_inline_style_new_block([], [js])
        assert len(errors) == 1
        assert ".style" in errors[0]

    def test_js_style_position_blocks(self, tmp_path):
        """JS .style.position = should BLOCK."""
        js = tmp_path / "bad.js"
        js.write_text("el.style.position = 'absolute';")
        errors = check_no_layout_inline_style_new_block([], [js])
        assert len(errors) == 1

    def test_js_style_width_blocks(self, tmp_path):
        """JS .style.width = should BLOCK."""
        js = tmp_path / "bad.js"
        js.write_text("el.style.width = '100px';")
        errors = check_no_layout_inline_style_new_block([], [js])
        assert len(errors) == 1

    def test_js_comment_skipped(self, tmp_path):
        """JS .style in comments should be skipped."""
        js = tmp_path / "comment.js"
        js.write_text("// el.style.display = 'none';")
        assert check_no_layout_inline_style_new_block([], [js]) == []

    def test_new_important_blocks(self, tmp_path):
        """New !important should still be caught by check_no_important."""
        css = tmp_path / "bad.css"
        css.write_text(".foo { color: red !important; }")
        errors = check_no_important([css])
        assert len(errors) == 1
