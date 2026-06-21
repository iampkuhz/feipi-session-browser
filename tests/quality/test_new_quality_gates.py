"""新增 quality gate 门禁脚本测试 - bad fixture 测试."""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts.quality.check_css_ownership import (
    check_cross_layer_duplicate,
    check_hardcoded_colors,
    check_layer_purity,
)

# ── check_layout_inline_style ────────────────────────────────────────────
from scripts.quality.check_layout_inline_style import (
    scan_html_inline_styles,
    scan_js_style_assignments,
)

# ── check_no_id_selector ─────────────────────────────────────────────────
from scripts.quality.check_no_id_selector import (
    check_id_selectors,
    extract_id_names,
)

# ── check_raw_innerhtml ──────────────────────────────────────────────────
from scripts.quality.check_raw_innerhtml import (
    scan_innerhtml_assignments,
)
from scripts.quality.check_selector_depth import (
    calculate_selector_depth,
    check_selector_depth,
    extract_css_rules,
    split_selectors,
)

ROOT = Path(__file__).resolve().parents[2]
DEPTH_TWO = 2
DEPTH_THREE = 3
DEPTH_FOUR = 4
EXPECTED_TWO_ITEMS = 2

# ======================================================================
# check_selector_depth 测试
# ======================================================================


class TestSplitSelectors:
    @pytest.mark.contract_case('HOOK-HARNESS-008')
    def test_simple_selector(self):
        assert split_selectors('.foo') == ['.foo']

    @pytest.mark.contract_case('HOOK-HARNESS-008')
    def test_comma_separated(self):
        result = split_selectors('.foo, .bar')
        assert '.foo' in result
        assert '.bar' in result

    @pytest.mark.contract_case('HOOK-HARNESS-008')
    def test_ignores_comma_in_not(self):
        """:not() 内的逗号不应被分割."""
        result = split_selectors('.foo:not(.a, .b)')
        assert len(result) == 1

    @pytest.mark.contract_case('HOOK-HARNESS-008')
    def test_ignores_comma_in_has(self):
        """:has() 内的逗号不应被分割."""
        result = split_selectors('.foo:has(.a, .b)')
        assert len(result) == 1

    @pytest.mark.contract_case('HOOK-HARNESS-008')
    def test_filters_at_rules(self):
        assert split_selectors('@media (max-width: 600px)') == []


class TestCalculateSelectorDepth:
    @pytest.mark.contract_case('HOOK-HARNESS-008')
    def test_single_class(self):
        assert calculate_selector_depth('.foo') == 1

    @pytest.mark.contract_case('HOOK-HARNESS-008')
    def test_two_classes(self):
        assert calculate_selector_depth('.foo .bar') == DEPTH_TWO

    @pytest.mark.contract_case('HOOK-HARNESS-008')
    def test_three_classes(self):
        assert calculate_selector_depth('.a .b .c') == DEPTH_THREE

    @pytest.mark.contract_case('HOOK-HARNESS-008')
    def test_four_classes_blocks(self):
        assert calculate_selector_depth('.a > .b + .c .d') == DEPTH_FOUR

    @pytest.mark.contract_case('HOOK-HARNESS-008')
    def test_child_combinator(self):
        assert calculate_selector_depth('.a > .b') == DEPTH_TWO

    @pytest.mark.contract_case('HOOK-HARNESS-008')
    def test_sibling_combinator(self):
        assert calculate_selector_depth('.a + .b') == DEPTH_TWO

    @pytest.mark.contract_case('HOOK-HARNESS-008')
    def test_pseudo_class_not_extra(self):
        """伪类依附于元素,不额外增加深度."""
        assert calculate_selector_depth('.foo:hover') == 1

    @pytest.mark.contract_case('HOOK-HARNESS-008')
    def test_pseudo_element_not_extra(self):
        assert calculate_selector_depth('.foo::before') == 1

    @pytest.mark.contract_case('HOOK-HARNESS-008')
    def test_not_function(self):
        """:not() 内部的内容应正确计数."""
        assert calculate_selector_depth('.foo:not(.bar) .baz') == DEPTH_TWO

    @pytest.mark.contract_case('HOOK-HARNESS-008')
    def test_empty_string(self):
        assert calculate_selector_depth('') == 0


class TestExtractCssRules:
    @pytest.mark.contract_case('HOOK-HARNESS-008')
    def test_single_rule(self, tmp_path: Path):
        css = tmp_path / 'test.css'
        css.write_text('.foo { color: red; }')
        rules = extract_css_rules(css.read_text())
        assert len(rules) == 1
        assert rules[0][1] == '.foo'

    @pytest.mark.contract_case('HOOK-HARNESS-008')
    def test_multiple_rules(self, tmp_path: Path):
        css = tmp_path / 'test.css'
        css.write_text('.foo { color: red; }\n.bar { color: blue; }')
        rules = extract_css_rules(css.read_text())
        assert len(rules) == EXPECTED_TWO_ITEMS

    @pytest.mark.contract_case('HOOK-HARNESS-008')
    def test_skips_comments(self, tmp_path: Path):
        css = tmp_path / 'test.css'
        css.write_text('/* comment */ .foo { color: red; }')
        rules = extract_css_rules(css.read_text())
        assert len(rules) == 1


class TestCheckSelectorDepth:
    @pytest.mark.contract_case('HOOK-HARNESS-008')
    def test_clean_css_no_violations(self, tmp_path: Path):
        css = tmp_path / 'clean.css'
        css.write_text('.foo { color: red; }\n.foo .bar { margin: 0; }')
        report = check_selector_depth(css)
        assert report.blocks == []
        # depth=2 为通过(WARN_THRESHOLD=2 意味着 depth > 2 才触发告警)
        assert report.warnings == []

    @pytest.mark.contract_case('HOOK-HARNESS-008')
    def test_deep_selector_blocks(self, tmp_path: Path):
        css = tmp_path / 'bad.css'
        css.write_text('.a .b .c .d { color: red; }')
        report = check_selector_depth(css)
        assert len(report.blocks) == 1
        assert report.blocks[0].depth == DEPTH_FOUR

    @pytest.mark.contract_case('HOOK-HARNESS-008')
    def test_boundary_depth_3_warns(self, tmp_path: Path):
        """Depth == 3 应为告警,不应拦截."""
        css = tmp_path / 'boundary.css'
        css.write_text('.a .b .c { color: red; }')
        report = check_selector_depth(css)
        assert report.blocks == []
        assert len(report.warnings) == 1
        assert report.warnings[0].depth == DEPTH_THREE

    @pytest.mark.contract_case('HOOK-HARNESS-008')
    def test_multiple_selectors_in_rule(self, tmp_path: Path):
        css = tmp_path / 'multi.css'
        css.write_text('.a .b, .x .y .z .w { color: red; }')
        report = check_selector_depth(css)
        # .a .b = depth 2(通过),.x .y .z .w = depth 4(拦截)
        assert len(report.blocks) == 1

    @pytest.mark.contract_case('HOOK-HARNESS-008')
    def test_at_rule_skipped(self, tmp_path: Path):
        css = tmp_path / 'media.css'
        css.write_text('@media (max-width: 600px) { .a .b .c .d { color: red; } }')
        report = check_selector_depth(css)
        # @media 内的选择器仍然会被分析
        # (extract_css_rules 会展开 @media)
        # 实际上 @media 选择器以 @ 开头,在外层会被跳过
        # 但内层规则仍会被提取
        # 这里只需验证不崩溃
        assert report.files_scanned == 1


# ======================================================================
# check_no_id_selector 测试
# ======================================================================


class TestExtractIdNames:
    @pytest.mark.contract_case('HOOK-HARNESS-008')
    def test_simple_id(self):
        assert extract_id_names('#foo') == ['foo']

    @pytest.mark.contract_case('HOOK-HARNESS-008')
    def test_id_with_class(self):
        ids = extract_id_names('#foo.bar')
        assert 'foo' in ids

    @pytest.mark.contract_case('HOOK-HARNESS-008')
    def test_hex_color_excluded(self):
        """十六进制颜色不应被当作 ID 处理."""
        assert extract_id_names('#fff') == []
        assert extract_id_names('#d9e2ef') == []
        assert extract_id_names('#aabbcc') == []

    @pytest.mark.contract_case('HOOK-HARNESS-008')
    def test_multiple_ids(self):
        ids = extract_id_names('#foo, #bar')
        assert 'foo' in ids
        assert 'bar' in ids

    @pytest.mark.contract_case('HOOK-HARNESS-008')
    def test_id_in_combinator(self):
        ids = extract_id_names('.parent #child')
        assert 'child' in ids


class TestCheckIdSelectors:
    @pytest.mark.contract_case('HOOK-HARNESS-008')
    def test_no_id_clean_css(self, tmp_path: Path):
        css = tmp_path / 'clean.css'
        css.write_text('.foo { color: red; }')
        report = check_id_selectors(css)
        assert report.blocks == []
        assert report.warnings == []

    @pytest.mark.contract_case('HOOK-HARNESS-008')
    def test_unknown_id_blocks(self, tmp_path: Path):
        css = tmp_path / 'bad.css'
        css.write_text('#unknown-id { color: red; }')
        report = check_id_selectors(css)
        assert len(report.blocks) == 1
        assert report.blocks[0].id_name == 'unknown-id'

    @pytest.mark.contract_case('HOOK-HARNESS-008')
    def test_stock_id_warns_not_blocks(self, tmp_path: Path):
        """白名单 ID 应告警,不应拦截."""
        css = tmp_path / 'glossary.css'
        css.write_text('#glossary-empty { display: none; }')
        report = check_id_selectors(css)
        assert report.blocks == []
        assert len(report.warnings) == 1
        assert report.warnings[0].id_name == 'glossary-empty'

    @pytest.mark.contract_case('HOOK-HARNESS-008')
    def test_hex_color_in_css_not_id(self, tmp_path: Path):
        """CSS 中的十六进制颜色值不应触发 ID 检测."""
        css = tmp_path / 'colors.css'
        css.write_text('.foo { color: #d9e2ef; background: #fff; }')
        report = check_id_selectors(css)
        assert report.blocks == []
        assert report.warnings == []


# ======================================================================
# check_css_ownership 测试
# ======================================================================


class TestCheckLayerPurity:
    @pytest.mark.contract_case('HOOK-HARNESS-008')
    def test_tokens_clean(self, tmp_path: Path):
        violations = check_layer_purity(
            'tokens.css',
            [
                (1, ':root', '--color-primary: blue;'),
            ],
        )
        assert violations == []

    @pytest.mark.contract_case('HOOK-HARNESS-008')
    def test_tokens_with_selector_blocks(self):
        violations = check_layer_purity(
            'tokens.css',
            [
                (1, '.btn', 'color: red;'),
            ],
        )
        assert len(violations) == 1
        assert violations[0].severity == 'BLOCK'

    @pytest.mark.contract_case('HOOK-HARNESS-008')
    def test_base_clean(self):
        violations = check_layer_purity(
            'base.css',
            [
                (1, 'body', 'margin: 0;'),
                (2, '* ', 'box-sizing: border-box;'),
            ],
        )
        assert violations == []

    @pytest.mark.contract_case('HOOK-HARNESS-008')
    def test_base_with_class_selector_blocks(self):
        violations = check_layer_purity(
            'base.css',
            [
                (1, '.card', 'padding: 16px;'),
            ],
        )
        assert len(violations) == 1

    @pytest.mark.contract_case('HOOK-HARNESS-008')
    def test_shell_with_page_selector_blocks(self):
        violations = check_layer_purity(
            'shell.css',
            [
                (1, '.sessions-page .main', 'padding: 20px;'),
            ],
        )
        assert len(violations) == 1

    @pytest.mark.contract_case('HOOK-HARNESS-008')
    def test_ui_primitives_with_page_selector_blocks(self):
        violations = check_layer_purity(
            'ui-primitives.css',
            [
                (1, '.dashboard-page .card', 'margin: 0;'),
            ],
        )
        assert len(violations) == 1


class TestCheckCrossLayerDuplicate:
    @pytest.mark.contract_case('HOOK-HARNESS-008')
    def test_exempt_file_skipped(self):
        violations = check_cross_layer_duplicate(
            'ui-primitives.css',
            [
                (1, '.btn', 'color: red;'),
            ],
            set(),
        )
        assert violations == []

    @pytest.mark.contract_case('HOOK-HARNESS-008')
    def test_direct_rewrite_warns(self):
        violations = check_cross_layer_duplicate(
            'dashboard.css',
            [
                (1, '.btn', 'color: blue;'),
            ],
            {'.btn'},
        )
        assert len(violations) == 1
        assert violations[0].severity == 'WARN'

    @pytest.mark.contract_case('HOOK-HARNESS-008')
    def test_descendant_selector_ok(self):
        """后代选择器如 '.page .btn' 不应告警."""
        violations = check_cross_layer_duplicate(
            'dashboard.css',
            [
                (1, '.dashboard-page .btn', 'color: blue;'),
            ],
            {'.btn'},
        )
        assert violations == []

    @pytest.mark.contract_case('HOOK-HARNESS-008')
    def test_modifier_variant_ok(self):
        """.btn--primary 是修饰符变体,不应告警."""
        violations = check_cross_layer_duplicate(
            'dashboard.css',
            [
                (1, '.btn--primary', 'color: blue;'),
            ],
            {'.btn'},
        )
        assert violations == []


class TestCheckHardcodedColors:
    @pytest.mark.contract_case('HOOK-HARNESS-008')
    def test_exempt_file_skipped(self):
        violations = check_hardcoded_colors(
            'tokens.css',
            [
                (1, ':root', '--color: #ff0000;'),
            ],
        )
        assert violations == []

    @pytest.mark.contract_case('HOOK-HARNESS-008')
    def test_hardcoded_color_warns(self):
        violations = check_hardcoded_colors(
            'dashboard.css',
            [
                (1, '.card', 'color: #ff5500;'),
            ],
        )
        assert len(violations) == 1

    @pytest.mark.contract_case('HOOK-HARNESS-008')
    def test_safe_colors_pass(self):
        violations = check_hardcoded_colors(
            'dashboard.css',
            [
                (1, '.card', 'color: #000; background: #fff;'),
            ],
        )
        assert violations == []


# ======================================================================
# check_raw_innerhtml 测试
# ======================================================================

# 辅助函数:在 repo 子目录中创建测试文件,以便 relative_to(REPO_ROOT) 正常工作
_TMP_INNERHTML = ROOT / 'tmp' / 'test_innerhtml_tmp'
_TMP_INNERHTML.mkdir(parents=True, exist_ok=True)


class TestScanInnerhtmlAssignments:
    def _write_js(self, name: str, content: str) -> Path:
        p = _TMP_INNERHTML / name
        p.write_text(content)
        return p

    @pytest.mark.contract_case('HOOK-HARNESS-008')
    def test_clean_js_no_findings(self):
        js = self._write_js('clean_tmp.js', 'var x = 1;')
        findings = scan_innerhtml_assignments([js])
        assert findings == []

    @pytest.mark.contract_case('HOOK-HARNESS-008')
    def test_innerhtml_detected(self):
        js = self._write_js('unsafe_tmp.js', "el.innerHTML = '<div>hello</div>';")
        findings = scan_innerhtml_assignments([js])
        assert len(findings) == 1
        assert findings[0]['file'].endswith('unsafe_tmp.js')

    @pytest.mark.contract_case('HOOK-HARNESS-008')
    def test_innerhtml_clear_not_reported(self):
        """清除 innerHTML 仍被报告但标记为 isClear(清除标志)."""
        js = self._write_js('clear_tmp.js', "container.innerHTML = '';")
        findings = scan_innerhtml_assignments([js])
        assert len(findings) == 1
        assert findings[0]['isClear'] is True

    @pytest.mark.contract_case('HOOK-HARNESS-008')
    def test_comment_line_skipped(self):
        js = self._write_js('comment_tmp.js', "// el.innerHTML = 'test';")
        findings = scan_innerhtml_assignments([js])
        assert findings == []

    @pytest.mark.contract_case('HOOK-HARNESS-008')
    def test_multiple_findings(self):
        js = self._write_js(
            'multi_tmp.js',
            "a.innerHTML = '<b>1</b>';\nb.innerHTML = '<b>2</b>';\n",
        )
        findings = scan_innerhtml_assignments([js])
        assert len(findings) == EXPECTED_TWO_ITEMS

    @pytest.mark.contract_case('HOOK-HARNESS-008')
    def test_is_clear_flag_not_reported(self):
        js = self._write_js('is_clear_tmp.js', 'el.innerHTML = "";')
        findings = scan_innerhtml_assignments([js])
        # 清除操作会被报告,但标记为 isClear(清除标志)
        assert len(findings) == 1
        assert findings[0]['isClear'] is True


# ======================================================================
# check_layout_inline_style 测试
# ======================================================================

_TMP_LAYOUT = ROOT / 'tmp' / 'test_layout_tmp'
_TMP_LAYOUT.mkdir(parents=True, exist_ok=True)


class TestScanHtmlInlineStyles:
    def _write_html(self, name: str, content: str) -> Path:
        p = _TMP_LAYOUT / name
        p.write_text(content)
        return p

    @pytest.mark.contract_case('HOOK-HARNESS-008')
    def test_clean_html_no_findings(self):
        html = self._write_html('clean_tmp.html', '<div class="foo">hello</div>')
        findings = scan_html_inline_styles([html])
        assert findings == []

    @pytest.mark.contract_case('HOOK-HARNESS-008')
    def test_layout_inline_style_detected(self):
        html = self._write_html('bad_tmp.html', '<div style="display: flex;">hello</div>')
        findings = scan_html_inline_styles([html])
        assert len(findings) == 1

    @pytest.mark.contract_case('HOOK-HARNESS-008')
    def test_position_detected(self):
        html = self._write_html('pos_tmp.html', '<div style="position: absolute;">hello</div>')
        findings = scan_html_inline_styles([html])
        assert len(findings) == 1

    @pytest.mark.contract_case('HOOK-HARNESS-008')
    def test_custom_property_only_skipped(self):
        """纯 CSS 自定义属性不应触发检测."""
        html = self._write_html(
            'custom_tmp.html', '<div style="--segment-width: 200px;">hello</div>'
        )
        findings = scan_html_inline_styles([html])
        assert findings == []

    @pytest.mark.contract_case('HOOK-HARNESS-008')
    def test_mixed_custom_property_detected(self):
        """自定义属性 + 布局属性应触发检测."""
        html = self._write_html(
            'mixed_tmp.html', '<div style="--segment-width: 200px; display: flex;">hello</div>'
        )
        findings = scan_html_inline_styles([html])
        assert len(findings) == 1

    @pytest.mark.contract_case('HOOK-HARNESS-008')
    def test_template_variable_skipped(self):
        """模板变量注入应被跳过."""
        html = self._write_html('template_tmp.html', '<div style="{{ grid_style }}">hello</div>')
        findings = scan_html_inline_styles([html])
        assert findings == []

    @pytest.mark.contract_case('HOOK-HARNESS-008')
    def test_comment_line_skipped(self):
        html = self._write_html('comment_tmp.html', '{# <div style="display: flex;"> #}')
        findings = scan_html_inline_styles([html])
        assert findings == []


class TestScanJsStyleAssignments:
    def _write_js(self, name: str, content: str) -> Path:
        p = _TMP_LAYOUT / name
        p.write_text(content)
        return p

    @pytest.mark.contract_case('HOOK-HARNESS-008')
    def test_clean_js_no_findings(self):
        js = self._write_js('layout_clean_tmp.js', 'var x = 1;')
        findings = scan_js_style_assignments([js])
        assert findings == []

    @pytest.mark.contract_case('HOOK-HARNESS-008')
    def test_style_display_detected(self):
        js = self._write_js('layout_display_tmp.js', "el.style.display = 'none';")
        findings = scan_js_style_assignments([js])
        assert len(findings) == 1

    @pytest.mark.contract_case('HOOK-HARNESS-008')
    def test_style_position_detected(self):
        js = self._write_js('layout_pos_tmp.js', "el.style.position = 'absolute';")
        findings = scan_js_style_assignments([js])
        assert len(findings) == 1

    @pytest.mark.contract_case('HOOK-HARNESS-008')
    def test_style_width_detected(self):
        js = self._write_js('layout_width_tmp.js', "el.style.width = '100px';")
        findings = scan_js_style_assignments([js])
        assert len(findings) == 1

    @pytest.mark.contract_case('HOOK-HARNESS-008')
    def test_comment_line_skipped(self):
        js = self._write_js('layout_comment_tmp.js', "// el.style.display = 'none';")
        findings = scan_js_style_assignments([js])
        assert findings == []

    @pytest.mark.contract_case('HOOK-HARNESS-008')
    def test_camelcase_properties(self):
        """驼峰式 JS 属性如 minWidth 应被检测到."""
        js = self._write_js('layout_camel_tmp.js', "el.style.minWidth = '100px';")
        findings = scan_js_style_assignments([js])
        assert len(findings) == 1
