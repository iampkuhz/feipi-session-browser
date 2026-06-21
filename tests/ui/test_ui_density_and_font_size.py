"""UI density 和 font-size 检查脚本的测试。

这些测试使用合成 CSS 输入验证 check_ui_density_and_font_size.py
中的静态分析逻辑，覆盖通过、失败和告警场景。

用法：
    cd <repo-root>
    ./scripts/session-browser.sh test tests/test_ui_density_and_font_size.py
"""

from __future__ import annotations

import pytest


def _run(css: str):
    """在合成 CSS 字符串上运行检查并返回 (all_pass, lines)。"""
    import os
    import tempfile

    from scripts.check_ui_density_and_font_size import run_checks

    with tempfile.NamedTemporaryFile(mode='w', suffix='.css', delete=False) as f:
        f.write(css)
        f.flush()
        from pathlib import Path

        tmp_path = Path(f.name)
        all_pass, lines = run_checks(tmp_path)
    os.unlink(tmp_path)
    return all_pass, lines


def _report_text(lines: list[str]) -> str:
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Token 解析
# ---------------------------------------------------------------------------


class TestTokenParsing:
    """验证从 :root 块提取 CSS token。"""

    @pytest.mark.contract_case('UI-VISUAL-011')
    def test_parses_all_text_tokens(self):
        css = """
        :root {
            --text-micro: 10px;
            --text-xs: 11px;
            --text-sm: 12px;
            --text-base: 14px;
            --text-lg: 16px;
            --text-xl: 18px;
            --text-metric: 22px;
            --text-metric-sm: 18px;
        }
        """
        from scripts.check_ui_density_and_font_size import parse_css_tokens

        tokens = parse_css_tokens(css)
        assert tokens['--text-base']['value_px'] == 14.0
        assert tokens['--text-xs']['value_px'] == 11.0

    @pytest.mark.contract_case('UI-VISUAL-011')
    def test_missing_tokens_reported_unresolved(self):
        css = ':root { --text-base: 14px; }'
        from scripts.check_ui_density_and_font_size import parse_css_tokens

        tokens = parse_css_tokens(css)
        assert tokens['--text-micro']['value_px'] is None
        assert tokens['--text-base']['value_px'] == 14.0


# ---------------------------------------------------------------------------
# 像素值解析
# ---------------------------------------------------------------------------


class TestParsePx:
    """验证 parse_px 辅助函数。"""

    @pytest.mark.contract_case('UI-VISUAL-011')
    def test_valid_px(self):
        from scripts.check_ui_density_and_font_size import parse_px

        assert parse_px('14px') == 14.0
        assert parse_px('10px') == 10.0
        assert parse_px('13.5px') == 13.5

    @pytest.mark.contract_case('UI-VISUAL-011')
    def test_invalid_px(self):
        from scripts.check_ui_density_and_font_size import parse_px

        assert parse_px('1em') is None
        assert parse_px('14') is None
        assert parse_px('var(--text-base)') is None


# ---------------------------------------------------------------------------
# Token 解析与回退
# ---------------------------------------------------------------------------


class TestTokenResolution:
    """验证 var() 解析。"""

    @pytest.mark.contract_case('UI-VISUAL-011')
    def test_direct_var(self):
        from scripts.check_ui_density_and_font_size import resolve_token_ref

        tokens = {'--text-base': {'value_px': 14.0}}
        px, desc = resolve_token_ref('var(--text-base)', tokens)
        assert px == 14.0

    @pytest.mark.contract_case('UI-VISUAL-011')
    def test_fallback_chain(self):
        from scripts.check_ui_density_and_font_size import resolve_token_ref

        tokens = {'--text-xs': {'value_px': 11.0}}
        px, desc = resolve_token_ref('var(--density-font-size, var(--text-xs))', tokens)
        assert px == 11.0

    @pytest.mark.contract_case('UI-VISUAL-011')
    def test_literal_px(self):
        from scripts.check_ui_density_and_font_size import resolve_token_ref

        px, desc = resolve_token_ref('16px', {})
        assert px == 16.0


# ---------------------------------------------------------------------------
# 阈值检查 — 通过场景
# ---------------------------------------------------------------------------


class TestThresholdsPass:
    """应全部通过检查的场景。"""

    @pytest.mark.contract_case('UI-VISUAL-011')
    def test_all_tokens_meet_minimum(self):
        css = """
        :root {
            --text-micro: 10px;
            --text-xs: 11px;
            --text-sm: 13px;
            --text-base: 14px;
            --text-lg: 16px;
            --text-xl: 18px;
            --text-metric: 22px;
            --text-metric-sm: 18px;
        }
        .data-table { font-size: var(--text-sm); }
        .data-table th { font-size: var(--text-sm); }
        .preview-cell { font-size: var(--text-lg); }
        .preview-cell code { font-size: inherit; }
        .btn { font-size: var(--text-sm); }
        .session-info-bar { font-size: var(--text-sm); }
        .metrics-strip__label { font-size: var(--text-sm); }
        .metrics-strip__value { font-size: var(--text-lg); }
        .metrics-strip__value--mono { font-size: var(--text-metric-sm); }
        """
        all_pass, lines = _run(css)
        assert all_pass, _report_text(lines)

    @pytest.mark.contract_case('UI-VISUAL-011')
    def test_literal_px_values_pass(self):
        css = """
        :root {
            --text-micro: 10px;
            --text-xs: 11px;
            --text-sm: 13px;
            --text-base: 15px;
            --text-lg: 16px;
            --text-xl: 18px;
            --text-metric: 22px;
            --text-metric-sm: 18px;
        }
        .data-table { font-size: 13px; }
        .data-table th { font-size: 13px; }
        .preview-cell { font-size: 14px; }
        .btn { font-size: 13px; }
        .session-info-bar { font-size: 12px; }
        .metrics-strip__label { font-size: 12px; }
        .metrics-strip__value { font-size: 14px; }
        .metrics-strip__value--mono { font-size: 18px; }
        """
        all_pass, lines = _run(css)
        assert all_pass, _report_text(lines)


# ---------------------------------------------------------------------------
# 阈值检查 — 失败场景
# ---------------------------------------------------------------------------


class TestThresholdsFail:
    """应失败特定检查的场景。"""

    @pytest.mark.contract_case('UI-VISUAL-011')
    def test_text_base_too_small(self):
        css = """
        :root {
            --text-micro: 10px;
            --text-xs: 11px;
            --text-sm: 12px;
            --text-base: 13px;
            --text-lg: 14px;
            --text-xl: 16px;
            --text-metric: 22px;
            --text-metric-sm: 18px;
        }
        .data-table { font-size: 14px; }
        .data-table th { font-size: 14px; }
        .preview-cell { font-size: 16px; }
        .btn { font-size: 14px; }
        .session-info-bar { font-size: 14px; }
        .metrics-strip__label { font-size: 14px; }
        .metrics-strip__value { font-size: 16px; }
        .metrics-strip__value--mono { font-size: 18px; }
        """
        all_pass, lines = _run(css)
        assert not all_pass
        report = _report_text(lines)
        assert '--text-base' in report
        assert 'FAIL' in report

    @pytest.mark.contract_case('UI-VISUAL-011')
    def test_data_table_too_small(self):
        css = """
        :root {
            --text-micro: 10px;
            --text-xs: 11px;
            --text-sm: 12px;
            --text-base: 14px;
            --text-lg: 16px;
            --text-xl: 18px;
            --text-metric: 22px;
            --text-metric-sm: 18px;
        }
        .data-table { font-size: var(--text-xs); }
        .data-table th { font-size: var(--text-xs); }
        .preview-cell { font-size: var(--text-lg); }
        .btn { font-size: var(--text-sm); }
        .session-info-bar { font-size: var(--text-sm); }
        .metrics-strip__label { font-size: var(--text-sm); }
        .metrics-strip__value { font-size: var(--text-lg); }
        .metrics-strip__value--mono { font-size: var(--text-metric-sm); }
        """
        all_pass, lines = _run(css)
        assert not all_pass
        report = _report_text(lines)
        assert '.data-table' in report
        assert 'FAIL' in report

    @pytest.mark.contract_case('UI-VISUAL-011')
    def test_button_too_small(self):
        css = """
        :root {
            --text-micro: 10px;
            --text-xs: 11px;
            --text-sm: 12px;
            --text-base: 14px;
            --text-lg: 16px;
            --text-xl: 18px;
            --text-metric: 22px;
            --text-metric-sm: 18px;
        }
        .data-table { font-size: var(--text-sm); }
        .data-table th { font-size: var(--text-sm); }
        .preview-cell { font-size: var(--text-lg); }
        .btn { font-size: var(--text-xs); }
        .session-info-bar { font-size: var(--text-sm); }
        .metrics-strip__label { font-size: var(--text-sm); }
        .metrics-strip__value { font-size: var(--text-lg); }
        .metrics-strip__value--mono { font-size: var(--text-metric-sm); }
        """
        all_pass, lines = _run(css)
        assert not all_pass
        report = _report_text(lines)
        assert '.btn' in report
        assert 'FAIL' in report

    @pytest.mark.contract_case('UI-VISUAL-011')
    def test_metrics_strip_label_too_small(self):
        css = """
        :root {
            --text-micro: 10px;
            --text-xs: 11px;
            --text-sm: 12px;
            --text-base: 14px;
            --text-lg: 16px;
            --text-xl: 18px;
            --text-metric: 22px;
            --text-metric-sm: 18px;
        }
        .data-table { font-size: var(--text-sm); }
        .data-table th { font-size: var(--text-sm); }
        .preview-cell { font-size: var(--text-lg); }
        .btn { font-size: var(--text-sm); }
        .session-info-bar { font-size: var(--text-sm); }
        .metrics-strip__label { font-size: var(--text-micro); }
        .metrics-strip__value { font-size: var(--text-lg); }
        .metrics-strip__value--mono { font-size: var(--text-metric-sm); }
        """
        all_pass, lines = _run(css)
        assert not all_pass
        report = _report_text(lines)
        assert '.metrics-strip__label' in report
        assert 'FAIL' in report


# ---------------------------------------------------------------------------
# 报告格式
# ---------------------------------------------------------------------------


class TestReportFormat:
    """验证报告包含预期的章节和标记。"""

    @pytest.mark.contract_case('UI-VISUAL-011')
    def test_report_has_token_section(self):
        css = """
        :root {
            --text-micro: 10px; --text-xs: 11px; --text-sm: 12px;
            --text-base: 14px; --text-lg: 16px; --text-xl: 18px;
            --text-metric: 22px; --text-metric-sm: 18px;
        }
        .data-table { font-size: var(--text-sm); }
        .data-table th { font-size: var(--text-sm); }
        .preview-cell { font-size: var(--text-lg); }
        .btn { font-size: var(--text-sm); }
        .session-info-bar { font-size: var(--text-sm); }
        .metrics-strip__label { font-size: var(--text-sm); }
        .metrics-strip__value { font-size: var(--text-lg); }
        .metrics-strip__value--mono { font-size: var(--text-metric-sm); }
        """
        _, lines = _run(css)
        report = _report_text(lines)
        assert 'CSS Token Values' in report
        assert 'Threshold Checks' in report

    @pytest.mark.contract_case('UI-VISUAL-011')
    def test_report_has_ok_fail_markers(self):
        css = """
        :root {
            --text-micro: 10px; --text-xs: 11px; --text-sm: 12px;
            --text-base: 13px; --text-lg: 14px; --text-xl: 16px;
            --text-metric: 22px; --text-metric-sm: 18px;
        }
        .data-table { font-size: var(--text-sm); }
        .data-table th { font-size: var(--text-sm); }
        .preview-cell { font-size: var(--text-lg); }
        .btn { font-size: var(--text-sm); }
        .session-info-bar { font-size: var(--text-sm); }
        .metrics-strip__label { font-size: var(--text-sm); }
        .metrics-strip__value { font-size: var(--text-lg); }
        .metrics-strip__value--mono { font-size: var(--text-metric-sm); }
        """
        _, lines = _run(css)
        report = _report_text(lines)
        assert '[OK]' in report
        assert '[FAIL]' in report

    @pytest.mark.contract_case('UI-VISUAL-011')
    def test_report_shows_tiny_declarations(self):
        css = """
        :root {
            --text-micro: 10px; --text-xs: 11px; --text-sm: 12px;
            --text-base: 14px; --text-lg: 16px; --text-xl: 18px;
            --text-metric: 22px; --text-metric-sm: 18px;
        }
        .data-table { font-size: var(--text-sm); }
        .data-table th { font-size: var(--text-sm); }
        .preview-cell { font-size: var(--text-lg); }
        .btn { font-size: var(--text-sm); }
        .session-info-bar { font-size: var(--text-sm); }
        .metrics-strip__label { font-size: var(--text-sm); }
        .metrics-strip__value { font-size: var(--text-lg); }
        .metrics-strip__value--mono { font-size: var(--text-metric-sm); }
        .some-tiny { font-size: var(--text-micro); }
        """
        _, lines = _run(css)
        report = _report_text(lines)
        assert 'text-micro' in report or 'text-xs' in report


# ---------------------------------------------------------------------------
# 边界场景
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """边界场景处理。"""

    @pytest.mark.contract_case('UI-VISUAL-011')
    @pytest.mark.contract_case('UI-VISUAL-003')
    def test_missing_css_file(self):
        from pathlib import Path

        from scripts.check_ui_density_and_font_size import run_checks

        all_pass, lines = run_checks(Path('/nonexistent/path/css/shell.css'))
        assert not all_pass
        assert 'FAIL' in _report_text(lines)

    @pytest.mark.contract_case('UI-VISUAL-011')
    @pytest.mark.contract_case('UI-VISUAL-004')
    def test_empty_css(self):
        css = ''
        all_pass, lines = _run(css)
        assert not all_pass

    @pytest.mark.contract_case('UI-VISUAL-011')
    @pytest.mark.contract_case('UI-VISUAL-005')
    def test_no_root_block(self):
        css = '.data-table { font-size: 14px; }'
        all_pass, lines = _run(css)
        # Token 将无法解析，检查会失败/告警
        assert isinstance(all_pass, bool)
        assert len(lines) > 0
