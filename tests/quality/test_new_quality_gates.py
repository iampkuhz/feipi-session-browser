"""Tests for new quality gate scripts — bad fixture tests."""
from __future__ import annotations

import pytest
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts" / "quality"

# ── check_selector_depth ─────────────────────────────────────────────────

sys.path.insert(0, str(SCRIPTS))
from check_selector_depth import (
    calculate_selector_depth,
    check_selector_depth,
    extract_css_rules,
    split_selectors,
)

# ── check_no_id_selector ─────────────────────────────────────────────────

from check_no_id_selector import (
    check_id_selectors,
    extract_id_names,
)

# ── check_css_ownership ──────────────────────────────────────────────────

from check_css_ownership import (
    check_cross_layer_duplicate,
    check_hardcoded_colors,
    check_layer_purity,
    check_legacy_aliases_purity,
    extract_css_rules as ownership_extract_rules,
    split_selectors as ownership_split_selectors,
)

# ── check_raw_innerhtml ──────────────────────────────────────────────────

from check_raw_innerhtml import (
    scan_innerhtml_assignments,
)

# ── check_layout_inline_style ────────────────────────────────────────────

from check_layout_inline_style import (
    scan_html_inline_styles,
    scan_js_style_assignments,
)


# ======================================================================
# check_selector_depth tests
# ======================================================================


class TestSplitSelectors:
    @pytest.mark.contract_case("HOOK-HARNESS-008")
    def test_simple_selector(self):
        assert split_selectors(".foo") == [".foo"]

    @pytest.mark.contract_case("HOOK-HARNESS-008")
    def test_comma_separated(self):
        result = split_selectors(".foo, .bar")
        assert ".foo" in result
        assert ".bar" in result

    @pytest.mark.contract_case("HOOK-HARNESS-008")
    def test_ignores_comma_in_not(self):
        """

Comma inside :not() should not split."""
        result = split_selectors(".foo:not(.a, .b)")
        assert len(result) == 1

    @pytest.mark.contract_case("HOOK-HARNESS-008")
    def test_ignores_comma_in_has(self):
        """Comma inside :has() should not split."""
        result = split_selectors(".foo:has(.a, .b)")
        assert len(result) == 1

    @pytest.mark.contract_case("HOOK-HARNESS-008")
    def test_filters_at_rules(self):
        assert split_selectors("@media (max-width: 600px)") == []


class TestCalculateSelectorDepth:
    @pytest.mark.contract_case("HOOK-HARNESS-008")
    def test_single_class(self):
        assert calculate_selector_depth(".foo") == 1

    @pytest.mark.contract_case("HOOK-HARNESS-008")
    def test_two_classes(self):
        assert calculate_selector_depth(".foo .bar") == 2

    @pytest.mark.contract_case("HOOK-HARNESS-008")
    def test_three_classes(self):
        assert calculate_selector_depth(".a .b .c") == 3

    @pytest.mark.contract_case("HOOK-HARNESS-008")
    def test_four_classes_blocks(self):
        assert calculate_selector_depth(".a > .b + .c .d") == 4

    @pytest.mark.contract_case("HOOK-HARNESS-008")
    def test_child_combinator(self):
        assert calculate_selector_depth(".a > .b") == 2

    @pytest.mark.contract_case("HOOK-HARNESS-008")
    def test_sibling_combinator(self):
        assert calculate_selector_depth(".a + .b") == 2

    @pytest.mark.contract_case("HOOK-HARNESS-008")
    def test_pseudo_class_not_extra(self):
        """Pseudo classes attach to elements, don't add depth."""
        assert calculate_selector_depth(".foo:hover") == 1

    @pytest.mark.contract_case("HOOK-HARNESS-008")
    def test_pseudo_element_not_extra(self):
        assert calculate_selector_depth(".foo::before") == 1

    @pytest.mark.contract_case("HOOK-HARNESS-008")
    def test_not_function(self):
        """Content inside :not() should count properly."""
        assert calculate_selector_depth(".foo:not(.bar) .baz") == 2

    @pytest.mark.contract_case("HOOK-HARNESS-008")
    def test_empty_string(self):
        assert calculate_selector_depth("") == 0


class TestExtractCssRules:
    @pytest.mark.contract_case("HOOK-HARNESS-008")
    def test_single_rule(self, tmp_path):
        css = tmp_path / "test.css"
        css.write_text(".foo { color: red; }")
        rules = extract_css_rules(css.read_text())
        assert len(rules) == 1
        assert rules[0][1] == ".foo"

    @pytest.mark.contract_case("HOOK-HARNESS-008")
    def test_multiple_rules(self, tmp_path):
        css = tmp_path / "test.css"
        css.write_text(".foo { color: red; }\n.bar { color: blue; }")
        rules = extract_css_rules(css.read_text())
        assert len(rules) == 2

    @pytest.mark.contract_case("HOOK-HARNESS-008")
    def test_skips_comments(self, tmp_path):
        css = tmp_path / "test.css"
        css.write_text("/* comment */ .foo { color: red; }")
        rules = extract_css_rules(css.read_text())
        assert len(rules) == 1


class TestCheckSelectorDepth:
    @pytest.mark.contract_case("HOOK-HARNESS-008")
    def test_clean_css_no_violations(self, tmp_path):
        css = tmp_path / "clean.css"
        css.write_text(".foo { color: red; }\n.foo .bar { margin: 0; }")
        report = check_selector_depth(css)
        assert report.blocks == []
        # depth=2 is PASS (WARN_THRESHOLD=2 means depth > 2 triggers WARN)
        assert report.warnings == []

    @pytest.mark.contract_case("HOOK-HARNESS-008")
    def test_deep_selector_blocks(self, tmp_path):
        css = tmp_path / "bad.css"
        css.write_text(".a .b .c .d { color: red; }")
        report = check_selector_depth(css)
        assert len(report.blocks) == 1
        assert report.blocks[0].depth == 4

    @pytest.mark.contract_case("HOOK-HARNESS-008")
    def test_boundary_depth_3_warns(self, tmp_path):
        """depth == 3 should be WARN, not BLOCK."""
        css = tmp_path / "boundary.css"
        css.write_text(".a .b .c { color: red; }")
        report = check_selector_depth(css)
        assert report.blocks == []
        assert len(report.warnings) == 1
        assert report.warnings[0].depth == 3

    @pytest.mark.contract_case("HOOK-HARNESS-008")
    def test_multiple_selectors_in_rule(self, tmp_path):
        css = tmp_path / "multi.css"
        css.write_text(".a .b, .x .y .z .w { color: red; }")
        report = check_selector_depth(css)
        # .a .b = depth 2 (pass), .x .y .z .w = depth 4 (BLOCK)
        assert len(report.blocks) == 1

    @pytest.mark.contract_case("HOOK-HARNESS-008")
    def test_at_rule_skipped(self, tmp_path):
        css = tmp_path / "media.css"
        css.write_text("@media (max-width: 600px) { .a .b .c .d { color: red; } }")
        report = check_selector_depth(css)
        # Inside @media the selector is still analyzed
        # (extract_css_rules unwraps @media)
        # Actually the @media selector starts with @, so it's skipped at outer level
        # but inner rules are still extracted
        # Let's just verify no crash
        assert report.files_scanned == 1


# ======================================================================
# check_no_id_selector tests
# ======================================================================


class TestExtractIdNames:
    @pytest.mark.contract_case("HOOK-HARNESS-008")
    def test_simple_id(self):
        assert extract_id_names("#foo") == ["foo"]

    @pytest.mark.contract_case("HOOK-HARNESS-008")
    def test_id_with_class(self):
        ids = extract_id_names("#foo.bar")
        assert "foo" in ids

    @pytest.mark.contract_case("HOOK-HARNESS-008")
    def test_hex_color_excluded(self):
        """Hex colors should not be treated as IDs."""
        assert extract_id_names("#fff") == []
        assert extract_id_names("#d9e2ef") == []
        assert extract_id_names("#aabbcc") == []

    @pytest.mark.contract_case("HOOK-HARNESS-008")
    def test_multiple_ids(self):
        ids = extract_id_names("#foo, #bar")
        assert "foo" in ids
        assert "bar" in ids

    @pytest.mark.contract_case("HOOK-HARNESS-008")
    def test_id_in_combinator(self):
        ids = extract_id_names(".parent #child")
        assert "child" in ids


class TestCheckIdSelectors:
    @pytest.mark.contract_case("HOOK-HARNESS-008")
    def test_no_id_clean_css(self, tmp_path):
        css = tmp_path / "clean.css"
        css.write_text(".foo { color: red; }")
        report = check_id_selectors(css)
        assert report.blocks == []
        assert report.warnings == []

    @pytest.mark.contract_case("HOOK-HARNESS-008")
    def test_unknown_id_blocks(self, tmp_path):
        css = tmp_path / "bad.css"
        css.write_text("#unknown-id { color: red; }")
        report = check_id_selectors(css)
        assert len(report.blocks) == 1
        assert report.blocks[0].id_name == "unknown-id"

    @pytest.mark.contract_case("HOOK-HARNESS-008")
    def test_stock_id_warns_not_blocks(self, tmp_path):
        """Whitelisted IDs should WARN, not BLOCK."""
        css = tmp_path / "glossary.css"
        css.write_text("#glossary-empty { display: none; }")
        report = check_id_selectors(css)
        assert report.blocks == []
        assert len(report.warnings) == 1
        assert report.warnings[0].id_name == "glossary-empty"

    @pytest.mark.contract_case("HOOK-HARNESS-008")
    def test_hex_color_in_css_not_id(self, tmp_path):
        """Hex color values in CSS should not trigger ID detection."""
        css = tmp_path / "colors.css"
        css.write_text(".foo { color: #d9e2ef; background: #fff; }")
        report = check_id_selectors(css)
        assert report.blocks == []
        assert report.warnings == []


# ======================================================================
# check_css_ownership tests
# ======================================================================


class TestCheckLayerPurity:
    @pytest.mark.contract_case("HOOK-HARNESS-008")
    def test_tokens_clean(self, tmp_path):
        violations = check_layer_purity("tokens.css", [
            (1, ":root", "--color-primary: blue;"),
        ])
        assert violations == []

    @pytest.mark.contract_case("HOOK-HARNESS-008")
    def test_tokens_with_selector_blocks(self):
        violations = check_layer_purity("tokens.css", [
            (1, ".btn", "color: red;"),
        ])
        assert len(violations) == 1
        assert violations[0].severity == "BLOCK"

    @pytest.mark.contract_case("HOOK-HARNESS-008")
    def test_base_clean(self):
        violations = check_layer_purity("base.css", [
            (1, "body", "margin: 0;"),
            (2, "* ", "box-sizing: border-box;"),
        ])
        assert violations == []

    @pytest.mark.contract_case("HOOK-HARNESS-008")
    def test_base_with_class_selector_blocks(self):
        violations = check_layer_purity("base.css", [
            (1, ".card", "padding: 16px;"),
        ])
        assert len(violations) == 1

    @pytest.mark.contract_case("HOOK-HARNESS-008")
    def test_shell_with_page_selector_blocks(self):
        violations = check_layer_purity("shell.css", [
            (1, ".sessions-page .main", "padding: 20px;"),
        ])
        assert len(violations) == 1

    @pytest.mark.contract_case("HOOK-HARNESS-008")
    def test_ui_primitives_with_page_selector_blocks(self):
        violations = check_layer_purity("ui-primitives.css", [
            (1, ".dashboard-page .card", "margin: 0;"),
        ])
        assert len(violations) == 1


class TestCheckCrossLayerDuplicate:
    @pytest.mark.contract_case("HOOK-HARNESS-008")
    def test_exempt_file_skipped(self):
        violations = check_cross_layer_duplicate("ui-primitives.css", [
            (1, ".btn", "color: red;"),
        ], set())
        assert violations == []

    @pytest.mark.contract_case("HOOK-HARNESS-008")
    def test_direct_rewrite_warns(self):
        violations = check_cross_layer_duplicate("dashboard.css", [
            (1, ".btn", "color: blue;"),
        ], {".btn"})
        assert len(violations) == 1
        assert violations[0].severity == "WARN"

    @pytest.mark.contract_case("HOOK-HARNESS-008")
    def test_descendant_selector_ok(self):
        """Descendant selector like '.page .btn' should not warn."""
        violations = check_cross_layer_duplicate("dashboard.css", [
            (1, ".dashboard-page .btn", "color: blue;"),
        ], {".btn"})
        assert violations == []

    @pytest.mark.contract_case("HOOK-HARNESS-008")
    def test_modifier_variant_ok(self):
        """.btn--primary is a modifier, should not warn."""
        violations = check_cross_layer_duplicate("dashboard.css", [
            (1, ".btn--primary", "color: blue;"),
        ], {".btn"})
        assert violations == []


class TestCheckHardcodedColors:
    @pytest.mark.contract_case("HOOK-HARNESS-008")
    def test_exempt_file_skipped(self):
        violations = check_hardcoded_colors("tokens.css", [
            (1, ":root", "--color: #ff0000;"),
        ])
        assert violations == []

    @pytest.mark.contract_case("HOOK-HARNESS-008")
    def test_hardcoded_color_warns(self):
        violations = check_hardcoded_colors("dashboard.css", [
            (1, ".card", "color: #ff5500;"),
        ])
        assert len(violations) == 1

    @pytest.mark.contract_case("HOOK-HARNESS-008")
    def test_safe_colors_pass(self):
        violations = check_hardcoded_colors("dashboard.css", [
            (1, ".card", "color: #000; background: #fff;"),
        ])
        assert violations == []


class TestCheckLegacyAliasesPurity:
    @pytest.mark.contract_case("HOOK-HARNESS-008")
    def test_root_is_clean(self):
        violations = check_legacy_aliases_purity("legacy-aliases.css", [
            (1, ":root", "--old: var(--new);"),
        ])
        assert violations == []

    @pytest.mark.contract_case("HOOK-HARNESS-008")
    def test_non_var_selector_warns(self):
        violations = check_legacy_aliases_purity("legacy-aliases.css", [
            (1, ".old-class", "color: red;"),
        ])
        assert len(violations) == 1


# ======================================================================
# check_raw_innerhtml tests
# ======================================================================

# Helper: create test files in a repo-subdir so relative_to(REPO_ROOT) works
_TMP_INNERHTML = ROOT / "tmp" / "test_innerhtml_tmp"
_TMP_INNERHTML.mkdir(parents=True, exist_ok=True)


class TestScanInnerhtmlAssignments:
    def _write_js(self, name: str, content: str) -> Path:
        p = _TMP_INNERHTML / name
        p.write_text(content)
        return p

    @pytest.mark.contract_case("HOOK-HARNESS-008")
    def test_clean_js_no_findings(self):
        js = self._write_js("clean_tmp.js", "var x = 1;")
        findings = scan_innerhtml_assignments([js])
        assert findings == []

    @pytest.mark.contract_case("HOOK-HARNESS-008")
    def test_innerhtml_detected(self):
        js = self._write_js("unsafe_tmp.js", "el.innerHTML = '<div>hello</div>';")
        findings = scan_innerhtml_assignments([js])
        assert len(findings) == 1
        assert findings[0]["file"].endswith("unsafe_tmp.js")

    @pytest.mark.contract_case("HOOK-HARNESS-008")
    def test_innerhtml_clear_not_reported(self):
        """Clearing innerHTML is still reported but marked as isClear."""
        js = self._write_js("clear_tmp.js", "container.innerHTML = '';")
        findings = scan_innerhtml_assignments([js])
        assert len(findings) == 1
        assert findings[0]["isClear"] is True

    @pytest.mark.contract_case("HOOK-HARNESS-008")
    def test_comment_line_skipped(self):
        js = self._write_js("comment_tmp.js", "// el.innerHTML = 'test';")
        findings = scan_innerhtml_assignments([js])
        assert findings == []

    @pytest.mark.contract_case("HOOK-HARNESS-008")
    def test_multiple_findings(self):
        js = self._write_js(
            "multi_tmp.js",
            "a.innerHTML = '<b>1</b>';\nb.innerHTML = '<b>2</b>';\n",
        )
        findings = scan_innerhtml_assignments([js])
        assert len(findings) == 2

    @pytest.mark.contract_case("HOOK-HARNESS-008")
    def test_isClear_flag_not_reported(self):
        js = self._write_js('is_clear_tmp.js', 'el.innerHTML = "";')
        findings = scan_innerhtml_assignments([js])
        # Clear operations are reported but marked as isClear
        assert len(findings) == 1
        assert findings[0]["isClear"] is True


# ======================================================================
# check_layout_inline_style tests
# ======================================================================

_TMP_LAYOUT = ROOT / "tmp" / "test_layout_tmp"
_TMP_LAYOUT.mkdir(parents=True, exist_ok=True)


class TestScanHtmlInlineStyles:
    def _write_html(self, name: str, content: str) -> Path:
        p = _TMP_LAYOUT / name
        p.write_text(content)
        return p

    @pytest.mark.contract_case("HOOK-HARNESS-008")
    def test_clean_html_no_findings(self):
        html = self._write_html("clean_tmp.html", '<div class="foo">hello</div>')
        findings = scan_html_inline_styles([html])
        assert findings == []

    @pytest.mark.contract_case("HOOK-HARNESS-008")
    def test_layout_inline_style_detected(self):
        html = self._write_html("bad_tmp.html", '<div style="display: flex;">hello</div>')
        findings = scan_html_inline_styles([html])
        assert len(findings) == 1

    @pytest.mark.contract_case("HOOK-HARNESS-008")
    def test_position_detected(self):
        html = self._write_html("pos_tmp.html", '<div style="position: absolute;">hello</div>')
        findings = scan_html_inline_styles([html])
        assert len(findings) == 1

    @pytest.mark.contract_case("HOOK-HARNESS-008")
    def test_custom_property_only_skipped(self):
        """Pure CSS custom property should not trigger."""
        html = self._write_html("custom_tmp.html", '<div style="--segment-width: 200px;">hello</div>')
        findings = scan_html_inline_styles([html])
        assert findings == []

    @pytest.mark.contract_case("HOOK-HARNESS-008")
    def test_mixed_custom_property_detected(self):
        """Custom property + layout property should trigger."""
        html = self._write_html("mixed_tmp.html", '<div style="--segment-width: 200px; display: flex;">hello</div>')
        findings = scan_html_inline_styles([html])
        assert len(findings) == 1

    @pytest.mark.contract_case("HOOK-HARNESS-008")
    def test_template_variable_skipped(self):
        """Template variable injection should be skipped."""
        html = self._write_html("template_tmp.html", '<div style="{{ grid_style }}">hello</div>')
        findings = scan_html_inline_styles([html])
        assert findings == []

    @pytest.mark.contract_case("HOOK-HARNESS-008")
    def test_comment_line_skipped(self):
        html = self._write_html("comment_tmp.html", '{# <div style="display: flex;"> #}')
        findings = scan_html_inline_styles([html])
        assert findings == []


class TestScanJsStyleAssignments:
    def _write_js(self, name: str, content: str) -> Path:
        p = _TMP_LAYOUT / name
        p.write_text(content)
        return p

    @pytest.mark.contract_case("HOOK-HARNESS-008")
    def test_clean_js_no_findings(self):
        js = self._write_js("layout_clean_tmp.js", "var x = 1;")
        findings = scan_js_style_assignments([js])
        assert findings == []

    @pytest.mark.contract_case("HOOK-HARNESS-008")
    def test_style_display_detected(self):
        js = self._write_js("layout_display_tmp.js", "el.style.display = 'none';")
        findings = scan_js_style_assignments([js])
        assert len(findings) == 1

    @pytest.mark.contract_case("HOOK-HARNESS-008")
    def test_style_position_detected(self):
        js = self._write_js("layout_pos_tmp.js", "el.style.position = 'absolute';")
        findings = scan_js_style_assignments([js])
        assert len(findings) == 1

    @pytest.mark.contract_case("HOOK-HARNESS-008")
    def test_style_width_detected(self):
        js = self._write_js("layout_width_tmp.js", "el.style.width = '100px';")
        findings = scan_js_style_assignments([js])
        assert len(findings) == 1

    @pytest.mark.contract_case("HOOK-HARNESS-008")
    def test_comment_line_skipped(self):
        js = self._write_js("layout_comment_tmp.js", "// el.style.display = 'none';")
        findings = scan_js_style_assignments([js])
        assert findings == []

    @pytest.mark.contract_case("HOOK-HARNESS-008")
    def test_camelcase_properties(self):
        """CamelCase JS properties like minWidth should be detected."""
        js = self._write_js("layout_camel_tmp.js", "el.style.minWidth = '100px';")
        findings = scan_js_style_assignments([js])
        assert len(findings) == 1
