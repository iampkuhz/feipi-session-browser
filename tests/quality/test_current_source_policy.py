"""测试 scripts/gates/checks/repository/check_current_source_policy.py 的内部规则。"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from scripts.gates.checks._framework import CheckStatus
from scripts.gates.checks.repository.check_current_source_policy import (
    _check_current_source_policy,
    _check_harness_current_state,
    _check_no_historical_version_comments,
    check,
)

if TYPE_CHECKING:
    from pathlib import Path

# -- Rule 1: no-historical-version-comments -------------------------------


class TestNoHistoricalVersionComments:
    @pytest.mark.contract_case('HOOK-HARNESS-011')
    def test_clean_file_passes(self, tmp_path: Path):
        f = tmp_path / 'clean.css'
        f.write_text('.foo { color: red; }')
        errors, warnings = _check_no_historical_version_comments([f])
        assert errors == []
        assert warnings == []

    @pytest.mark.contract_case('HOOK-HARNESS-011')
    def test_hifi_version_blocks(self, tmp_path: Path):
        f = tmp_path / 'shell.css'
        f.write_text('/* HIFI v99: Table header */\n.header { display: flex; }')
        errors, warnings = _check_no_historical_version_comments([f])
        assert len(errors) == 1
        assert warnings == []

    @pytest.mark.contract_case('HOOK-HARNESS-011')
    def test_deprecated_task_blocks(self, tmp_path: Path):
        f = tmp_path / 'code.py'
        f.write_text('# DEPRECATED T001 — migrated to new system\nx = 1')
        errors, warnings = _check_no_historical_version_comments([f])
        assert len(errors) == 1
        assert warnings == []

    @pytest.mark.contract_case('HOOK-HARNESS-011')
    def test_migrated_task_blocks(self, tmp_path: Path):
        f = tmp_path / 'notes.md'
        f.write_text('migrated Task 42 to the new module')
        errors, warnings = _check_no_historical_version_comments([f])
        assert len(errors) == 1
        assert warnings == []

    @pytest.mark.contract_case('HOOK-HARNESS-011')
    def test_session_browser_hifi_v_blocks(self, tmp_path: Path):
        f = tmp_path / 'config.yaml'
        f.write_text('# session_browser_hifi_v99 configuration')
        errors, warnings = _check_no_historical_version_comments([f])
        assert len(errors) == 1
        assert warnings == []

    @pytest.mark.contract_case('HOOK-HARNESS-011')
    def test_session_detail_payload_v_blocks(self, tmp_path: Path):
        f = tmp_path / 'design.md'
        f.write_text('session-detail-payload-v99 design')
        errors, warnings = _check_no_historical_version_comments([f])
        assert len(errors) == 1
        assert warnings == []

    @pytest.mark.contract_case('HOOK-HARNESS-011')
    @pytest.mark.parametrize(
        'marker',
        ['gate-catalog:' + 'v' + '7', 'Catalog ' + 'v' + '7'],
    )
    def test_gate_catalog_version_markers_block(self, tmp_path: Path, marker: str):
        f = tmp_path / 'catalog.md'
        f.write_text(f'{marker} current configuration')
        errors, warnings = _check_no_historical_version_comments([f])
        assert len(errors) == 1
        assert warnings == []

    @pytest.mark.contract_case('HOOK-HARNESS-011')
    def test_multiple_files_reports_per_file(self, tmp_path: Path):
        good = tmp_path / 'good.css'
        bad = tmp_path / 'bad.css'
        good.write_text('.a { margin: 0; }')
        bad.write_text('/* HIFI v99: new */')
        errors, warnings = _check_no_historical_version_comments([good, bad])
        assert len(errors) == 1
        assert 'bad.css' in errors[0]
        assert warnings == []

    @pytest.mark.contract_case('HOOK-HARNESS-011')
    def test_no_false_positive_on_normal_version(self, tmp_path: Path):
        f = tmp_path / 'readme.md'
        f.write_text('## Version 2.0\n\nThis is the changelog.')
        _errors, warnings = _check_no_historical_version_comments([f])
        assert warnings == [], f'Unexpected warning: {warnings}'


# -- Rule 2: harness-current-state-only -----------------------------------


class TestHarnessCurrentStateOnly:
    @pytest.mark.contract_case('HOOK-HARNESS-011')
    def test_clean_harness_passes(self, tmp_path: Path):
        f = tmp_path / 'quality-gate-matrix.md'
        f.write_text('# Quality Gate Matrix\n\nCurrent gates are...')
        errors, warnings = _check_harness_current_state([f])
        assert errors == []
        assert warnings == []

    @pytest.mark.contract_case('HOOK-HARNESS-011')
    def test_deleted_keyword_blocks(self, tmp_path: Path):
        f = tmp_path / 'changelog.md'
        f.write_text('# Changes\n\n- deleted old module X')
        errors, warnings = _check_harness_current_state([f])
        assert len(errors) == 1
        assert warnings == []
        assert 'deleted' in errors[0].lower()

    @pytest.mark.contract_case('HOOK-HARNESS-011')
    def test_changelog_keyword_blocks(self, tmp_path: Path):
        f = tmp_path / 'history.md'
        f.write_text('# changelog for 2024')
        errors, warnings = _check_harness_current_state([f])
        assert len(errors) == 1
        assert warnings == []
        assert 'changelog' in errors[0].lower()

    @pytest.mark.contract_case('HOOK-HARNESS-011')
    def test_agent_quality_blocks(self, tmp_path: Path):
        f = tmp_path / 'config.md'
        f.write_text('Logs stored in .agent/quality/results/')
        errors, warnings = _check_harness_current_state([f])
        assert len(errors) == 1
        assert warnings == []
        assert '.agent/quality' in errors[0]

    @pytest.mark.contract_case('HOOK-HARNESS-011')
    def test_mmdd_log_path_blocks(self, tmp_path: Path):
        f = tmp_path / 'logging.md'
        f.write_text('Logs are at tmp/agent_logs/MMDD_<session-id>/')
        errors, warnings = _check_harness_current_state([f])
        assert len(errors) == 1
        assert warnings == []
        assert 'tmp/agent_logs/MMDD' in errors[0]

    @pytest.mark.contract_case('HOOK-HARNESS-011')
    def test_deleted_chinese_keyword_blocks(self, tmp_path: Path):
        f = tmp_path / 'notes.md'
        f.write_text('已删除的模块需要重新评估')
        errors, warnings = _check_harness_current_state([f])
        assert len(errors) == 1
        assert warnings == []
        assert '已删除' in errors[0]

    @pytest.mark.contract_case('HOOK-HARNESS-011')
    def test_empty_file_passes(self, tmp_path: Path):
        f = tmp_path / 'empty.md'
        f.write_text('')
        errors, warnings = _check_harness_current_state([f])
        assert errors == []
        assert warnings == []


# 客户端私有 worktree 不属于当前 checkout，不能污染当前态检查。
def test_client_private_worktree_is_not_scanned(tmp_path: Path):
    private_copy = tmp_path / '.claude' / 'worktrees' / 'other' / 'legacy.py'
    private_copy.parent.mkdir(parents=True)
    private_copy.write_text('# session_browser_hifi_v99\n', encoding='utf-8')

    errors, _warnings = _check_current_source_policy(tmp_path)

    assert all('.claude/worktrees' not in error for error in errors)


def test_incremental_mode_only_reads_selected_text_files(tmp_path: Path):
    bad = tmp_path / 'docs' / 'bad.md'
    good = tmp_path / 'docs' / 'good.md'
    bad.parent.mkdir(parents=True)
    bad.write_text('session_browser_hifi_v99\n', encoding='utf-8')
    good.write_text('当前说明\n', encoding='utf-8')

    selected_errors, _warnings = _check_current_source_policy(tmp_path, ['docs/good.md'])
    bad_errors, _warnings = _check_current_source_policy(tmp_path, ['docs/bad.md'])

    assert selected_errors == []
    assert len(bad_errors) == 1


def test_invalid_incremental_path_payload_is_execution_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv('QUALITY_EXECUTION_MODE', 'incremental')
    monkeypatch.setenv('QUALITY_CHANGED_FILES', '{}')

    result = check(['--root', str(tmp_path)])

    assert result.status is CheckStatus.FAIL
    assert result.reason == 'input-unavailable'
