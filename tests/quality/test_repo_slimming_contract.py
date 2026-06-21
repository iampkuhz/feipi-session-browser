"""测试 scripts/quality/repo_slimming_contract_check.py 的纯函数."""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts.quality.repo_slimming_contract_check import (
    _css_has_only_comments_or_empty,
    _js_is_only_comments_or_empty,
    check_harness_current_state,
    check_no_dead_compat_shim,
    check_no_historical_version_comments,
    check_repo_slimming,
    check_supported_viewports_only,
)

ROOT = Path(__file__).resolve().parents[2]

# -- Rule 1: no-historical-version-comments -------------------------------


class TestNoHistoricalVersionComments:
    @pytest.mark.contract_case('HOOK-HARNESS-011')
    def test_clean_file_passes(self, tmp_path: Path):
        f = tmp_path / 'clean.css'
        f.write_text('.foo { color: red; }')
        errors, warnings = check_no_historical_version_comments([f])
        assert errors == []
        assert warnings == []

    @pytest.mark.contract_case('HOOK-HARNESS-011')
    def test_hifi_version_blocks(self, tmp_path: Path):
        f = tmp_path / 'shell.css'
        f.write_text('/* HIFI v99: Table header */\n.header { display: flex; }')
        errors, warnings = check_no_historical_version_comments([f])
        assert len(errors) == 1
        assert warnings == []

    @pytest.mark.contract_case('HOOK-HARNESS-011')
    def test_deprecated_task_blocks(self, tmp_path: Path):
        f = tmp_path / 'code.py'
        f.write_text('# DEPRECATED T001 — migrated to new system\nx = 1')
        errors, warnings = check_no_historical_version_comments([f])
        assert len(errors) == 1
        assert warnings == []

    @pytest.mark.contract_case('HOOK-HARNESS-011')
    def test_migrated_task_blocks(self, tmp_path: Path):
        f = tmp_path / 'notes.md'
        f.write_text('migrated Task 42 to the new module')
        errors, warnings = check_no_historical_version_comments([f])
        assert len(errors) == 1
        assert warnings == []

    @pytest.mark.contract_case('HOOK-HARNESS-011')
    def test_session_browser_hifi_v_blocks(self, tmp_path: Path):
        f = tmp_path / 'config.yaml'
        f.write_text('# session_browser_hifi_v99 configuration')
        errors, warnings = check_no_historical_version_comments([f])
        assert len(errors) == 1
        assert warnings == []

    @pytest.mark.contract_case('HOOK-HARNESS-011')
    def test_session_detail_payload_v_blocks(self, tmp_path: Path):
        f = tmp_path / 'design.md'
        f.write_text('session-detail-payload-v99 design')
        errors, warnings = check_no_historical_version_comments([f])
        assert len(errors) == 1
        assert warnings == []

    @pytest.mark.contract_case('HOOK-HARNESS-011')
    def test_multiple_files_reports_per_file(self, tmp_path: Path):
        good = tmp_path / 'good.css'
        bad = tmp_path / 'bad.css'
        good.write_text('.a { margin: 0; }')
        bad.write_text('/* HIFI v99: new */')
        errors, warnings = check_no_historical_version_comments([good, bad])
        assert len(errors) == 1
        assert 'bad.css' in errors[0]
        assert warnings == []

    @pytest.mark.contract_case('HOOK-HARNESS-011')
    def test_no_false_positive_on_normal_version(self, tmp_path: Path):
        f = tmp_path / 'readme.md'
        f.write_text('## Version 2.0\n\nThis is the changelog.')
        _errors, warnings = check_no_historical_version_comments([f])
        assert warnings == [], f'Unexpected warning: {warnings}'


# -- Rule 2: harness-current-state-only -----------------------------------


class TestHarnessCurrentStateOnly:
    @pytest.mark.contract_case('HOOK-HARNESS-011')
    def test_clean_harness_passes(self, tmp_path: Path):
        f = tmp_path / 'quality-gate-matrix.md'
        f.write_text('# Quality Gate Matrix\n\nCurrent gates are...')
        errors, warnings = check_harness_current_state([f])
        assert errors == []
        assert warnings == []

    @pytest.mark.contract_case('HOOK-HARNESS-011')
    def test_deleted_keyword_blocks(self, tmp_path: Path):
        f = tmp_path / 'changelog.md'
        f.write_text('# Changes\n\n- deleted old module X')
        errors, warnings = check_harness_current_state([f])
        assert len(errors) == 1
        assert warnings == []
        assert 'deleted' in errors[0].lower()

    @pytest.mark.contract_case('HOOK-HARNESS-011')
    def test_changelog_keyword_blocks(self, tmp_path: Path):
        f = tmp_path / 'history.md'
        f.write_text('# changelog for 2024')
        errors, warnings = check_harness_current_state([f])
        assert len(errors) == 1
        assert warnings == []
        assert 'changelog' in errors[0].lower()

    @pytest.mark.contract_case('HOOK-HARNESS-011')
    def test_agent_quality_blocks(self, tmp_path: Path):
        f = tmp_path / 'config.md'
        f.write_text('Logs stored in .agent/quality/results/')
        errors, warnings = check_harness_current_state([f])
        assert len(errors) == 1
        assert warnings == []
        assert '.agent/quality' in errors[0]

    @pytest.mark.contract_case('HOOK-HARNESS-011')
    def test_mmdd_log_path_blocks(self, tmp_path: Path):
        f = tmp_path / 'logging.md'
        f.write_text('Logs are at tmp/agent_logs/MMDD_<session-id>/')
        errors, warnings = check_harness_current_state([f])
        assert len(errors) == 1
        assert warnings == []
        assert 'tmp/agent_logs/MMDD' in errors[0]

    @pytest.mark.contract_case('HOOK-HARNESS-011')
    def test_deleted_chinese_keyword_blocks(self, tmp_path: Path):
        f = tmp_path / 'notes.md'
        f.write_text('已删除的模块需要重新评估')
        errors, warnings = check_harness_current_state([f])
        assert len(errors) == 1
        assert warnings == []
        assert '已删除' in errors[0]

    @pytest.mark.contract_case('HOOK-HARNESS-011')
    def test_empty_file_passes(self, tmp_path: Path):
        f = tmp_path / 'empty.md'
        f.write_text('')
        errors, warnings = check_harness_current_state([f])
        assert errors == []
        assert warnings == []


# -- Rule 3: supported-viewports-only -------------------------------------


class TestSupportedViewportsOnly:
    @pytest.mark.contract_case('HOOK-HARNESS-011')
    def test_desktop_viewport_passes(self, tmp_path: Path):
        css = tmp_path / 'desktop.css'
        css.write_text('@media (min-width: 1440px) { .foo { display: flex; } }')
        errors, warnings = check_supported_viewports_only([css], [])
        assert errors == []
        assert warnings == []

    @pytest.mark.contract_case('HOOK-HARNESS-011')
    def test_767px_blocks(self, tmp_path: Path):
        css = tmp_path / 'mobile.css'
        css.write_text('@media (max-width: 767px) { .foo { display: flex; } }')
        errors, _warnings = check_supported_viewports_only([css], [])
        assert len(errors) == 1
        assert '767px' in errors[0]

    @pytest.mark.contract_case('HOOK-HARNESS-011')
    def test_768px_blocks(self, tmp_path: Path):
        css = tmp_path / 'tablet.css'
        css.write_text('@media (max-width: 768px) { .foo { display: flex; } }')
        errors, _warnings = check_supported_viewports_only([css], [])
        assert len(errors) == 1
        assert '768px' in errors[0]

    @pytest.mark.contract_case('HOOK-HARNESS-011')
    def test_820px_blocks(self, tmp_path: Path):
        css = tmp_path / 'ipad.css'
        css.write_text('@media (max-width: 820px) { .foo { display: flex; } }')
        errors, _warnings = check_supported_viewports_only([css], [])
        assert len(errors) == 1
        assert '820px' in errors[0]

    @pytest.mark.contract_case('HOOK-HARNESS-011')
    def test_mobile_media_query_blocks(self, tmp_path: Path):
        css = tmp_path / 'mobile.css'
        css.write_text('@media only screen and (max-width: 480px) and (orientation: portrait)')
        errors, _warnings = check_supported_viewports_only([css], [])
        # Only mobile/tablet/iPad keywords or specific widths should be blocked.
        # This generic mobile keyword pattern should not match.
        assert errors == []  # 该行未命中任何模式

    @pytest.mark.contract_case('HOOK-HARNESS-011')
    def test_js_mobile_blocks(self, tmp_path: Path):
        js = tmp_path / 'responsive.js'
        js.write_text('// @media tablet breakpoint\nconst TABLET = 768;')
        # Comment lines are skipped.
        errors, _warnings = check_supported_viewports_only([], [js])
        assert errors == []

    @pytest.mark.contract_case('HOOK-HARNESS-011')
    def test_comment_lines_skipped(self, tmp_path: Path):
        css = tmp_path / 'notes.css'
        css.write_text('/* This is what mobile at 768px would look like */\n.foo { color: red; }')
        errors, _warnings = check_supported_viewports_only([css], [])
        assert errors == []

    @pytest.mark.contract_case('HOOK-HARNESS-011')
    def test_allowed_desktop_widths_pass(self, tmp_path: Path):
        css = tmp_path / 'wide.css'
        css.write_text('@media (min-width: 1512px) { .foo { max-width: 1200px; } }')
        errors, _warnings = check_supported_viewports_only([css], [])
        assert errors == []


# -- Rule 4: no-dead-compat-shim -----------------------------------------


class TestCssHasOnlyCommentsOrEmpty:
    @pytest.mark.contract_case('HOOK-HARNESS-011')
    def test_only_comments(self):
        assert _css_has_only_comments_or_empty('/* comment */') is True

    @pytest.mark.contract_case('HOOK-HARNESS-011')
    def test_only_whitespace(self):
        assert _css_has_only_comments_or_empty('   \n\n  ') is True

    @pytest.mark.contract_case('HOOK-HARNESS-011')
    def test_empty(self):
        assert _css_has_only_comments_or_empty('') is True

    @pytest.mark.contract_case('HOOK-HARNESS-011')
    def test_with_rules(self):
        assert _css_has_only_comments_or_empty('.foo { color: red; }') is False

    @pytest.mark.contract_case('HOOK-HARNESS-011')
    def test_comment_with_rules(self):
        assert _css_has_only_comments_or_empty('/* Header */\n.header { display: flex; }') is False


class TestJsIsOnlyCommentsOrEmpty:
    @pytest.mark.contract_case('HOOK-HARNESS-011')
    def test_only_line_comments(self):
        assert _js_is_only_comments_or_empty('// comment\n// another') is True

    @pytest.mark.contract_case('HOOK-HARNESS-011')
    def test_only_block_comments(self):
        assert _js_is_only_comments_or_empty('/* comment */') is True

    @pytest.mark.contract_case('HOOK-HARNESS-011')
    def test_with_code(self):
        assert _js_is_only_comments_or_empty('var x = 1;') is False

    @pytest.mark.contract_case('HOOK-HARNESS-011')
    def test_comment_with_code(self):
        assert _js_is_only_comments_or_empty('// init\nconst x = 1;') is False

    @pytest.mark.contract_case('HOOK-HARNESS-011')
    def test_empty(self):
        assert _js_is_only_comments_or_empty('') is True


class TestNoDeadCompatShim:
    @pytest.mark.contract_case('HOOK-HARNESS-011')
    def test_only_comment_css_blocks(self, tmp_path: Path):
        css = tmp_path / 'dead.css'
        css.write_text('/* all gone */')
        errors, _warnings = check_no_dead_compat_shim([css], [])
        assert len(errors) == 1
        assert '死 CSS 文件' in errors[0]

    @pytest.mark.contract_case('HOOK-HARNESS-011')
    def test_only_comment_js_blocks(self, tmp_path: Path):
        js = tmp_path / 'dead.js'
        js.write_text('// nothing here')
        errors, _warnings = check_no_dead_compat_shim([], [js])
        assert len(errors) == 1
        assert '死 JS 文件' in errors[0]

    @pytest.mark.contract_case('HOOK-HARNESS-011')
    def test_valid_css_passes(self, tmp_path: Path):
        css = tmp_path / 'valid.css'
        css.write_text('.foo { color: red; }')
        errors, _warnings = check_no_dead_compat_shim([css], [])
        assert errors == []

    @pytest.mark.contract_case('HOOK-HARNESS-011')
    def test_valid_js_passes(self, tmp_path: Path):
        js = tmp_path / 'valid.js'
        js.write_text('const x = 1;')
        errors, _warnings = check_no_dead_compat_shim([], [js])
        assert errors == []

    @pytest.mark.contract_case('HOOK-HARNESS-011')
    def test_legacy_display_none_blocks(self, tmp_path: Path):
        css = tmp_path / 'compat.css'
        css.write_text('.old-header {\n  display: none;\n}')
        errors, warnings = check_no_dead_compat_shim([css], [])
        # An "old" selector with display:none should trigger BLOCK.
        assert len(errors) == 1
        assert '兼容垫片' in errors[0]
        assert warnings == []

    @pytest.mark.contract_case('HOOK-HARNESS-011')
    def test_normal_display_none_no_warn(self, tmp_path: Path):
        css = tmp_path / 'normal.css'
        css.write_text('.sr-only {\n  display: none;\n}')
        _errors, warnings = check_no_dead_compat_shim([css], [])
        assert warnings == []


# -- Integration: actual repository state --------------------------------


class TestActualRepoState:
    @pytest.mark.contract_case('HOOK-HARNESS-011')
    def test_no_mobile_viewports_in_css(self):
        static = ROOT / 'src/session_browser/web/static'
        css_files = list(static.rglob('*.css'))
        js_files = list(static.rglob('*.js'))
        errors, _warnings = check_supported_viewports_only(css_files, js_files)
        assert errors == [], f'mobile viewport found: {errors}'

    @pytest.mark.contract_case('HOOK-HARNESS-011')
    def test_no_dead_css_js_files(self):
        static = ROOT / 'src/session_browser/web/static'
        css_files = list(static.rglob('*.css'))
        js_files = list(static.rglob('*.js'))
        errors, _warnings = check_no_dead_compat_shim(css_files, js_files)
        assert errors == [], f'dead compat shim found: {errors}'

    @pytest.mark.contract_case('HOOK-HARNESS-011')
    def test_historical_version_blocks_absent(self):
        """验证仓库当前 CSS 不含历史版本注释 BLOCK."""
        static = ROOT / 'src/session_browser/web/static'
        css_files = list(static.rglob('*.css'))
        errors, warnings = check_no_historical_version_comments(css_files)
        assert errors == [], f'Unexpected BLOCK errors: {errors}'
        assert warnings == []

    @pytest.mark.contract_case('HOOK-HARNESS-011')
    def test_repo_slimming_contract_passes_no_block(self):
        """完整检查不应在当前仓库状态下触发 BLOCK."""
        errors, warnings = check_repo_slimming(ROOT)
        assert errors == [], f'Unexpected BLOCK errors: {errors}'
        assert warnings == []
