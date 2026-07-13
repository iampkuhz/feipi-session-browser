"""新增 quality gate 门禁脚本测试 - bad fixture 测试."""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts.checks.check_css_ownership import (
    check_cross_layer_duplicate,
    check_hardcoded_colors,
    check_layer_purity,
)

# ── check_layout_inline_style ────────────────────────────────────────────
from scripts.checks.check_layout_inline_style import (
    scan_html_inline_styles,
    scan_js_style_assignments,
)

# ── check_raw_innerhtml ──────────────────────────────────────────────────
from scripts.checks.check_raw_innerhtml import (
    scan_innerhtml_assignments,
)

ROOT = Path(__file__).resolve().parents[2]
EXPECTED_TWO_ITEMS = 2

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
