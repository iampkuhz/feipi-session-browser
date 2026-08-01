"""新增 quality gate 门禁脚本测试 - bad fixture 测试."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from scripts.checks.web.check_css_ownership import (
    _check_cross_layer_duplicate as check_cross_layer_duplicate,
)
from scripts.checks.web.check_css_ownership import (
    _check_hardcoded_colors as check_hardcoded_colors,
)
from scripts.checks.web.check_css_ownership import (
    _check_layer_purity as check_layer_purity,
)

if TYPE_CHECKING:
    from pathlib import Path

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
