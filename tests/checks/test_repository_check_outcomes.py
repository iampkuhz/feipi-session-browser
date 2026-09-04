"""验证仓库类 Check 能区分领域阻断与执行失败。"""

from __future__ import annotations

import pytest
from scripts.gates.checks.check_protocol import CheckStatus
from scripts.gates.checks.privacy import check_credential_leak as secret_policy
from scripts.gates.checks.repository import check_current_source_policy as current_source
from scripts.gates.checks.repository import check_file_boundary as repository_files
from scripts.gates.checks.repository import check_no_python_playwright_skips as no_skips
from scripts.gates.checks.repository import check_test_data_policy as test_data


def _assert_execution_failure(result, reason: str) -> None:
    assert result.status is CheckStatus.FAIL
    assert result.reason == reason
    assert result.diagnostics


def test_test_data_git_unavailable_is_execution_failure(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        test_data,
        '_validate_test_data_policy',
        lambda _root: ['git-tracked-files-unavailable'],
    )

    result = test_data.check(['--repo-root', str(tmp_path)])

    _assert_execution_failure(result, 'dependency-unavailable')


@pytest.mark.contract_case('HOOK-HARNESS-008')
def test_test_data_policy_finding_is_blocked(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        test_data,
        '_validate_test_data_policy',
        lambda _root: ['tests/fixtures/sample.txt: untracked-test-data'],
    )

    result = test_data.check(['--repo-root', str(tmp_path)])

    assert result.status is CheckStatus.BLOCKED


def test_test_data_read_error_is_execution_failure(monkeypatch, tmp_path) -> None:
    def unreadable(_root):
        raise OSError('cannot enumerate test data')

    monkeypatch.setattr(test_data, '_validate_test_data_policy', unreadable)

    result = test_data.check(['--repo-root', str(tmp_path)])

    _assert_execution_failure(result, 'input-unavailable')


def test_repository_git_unavailable_is_execution_failure(monkeypatch, tmp_path) -> None:
    def unavailable(*_args, **_kwargs):
        raise RuntimeError('git unavailable')

    monkeypatch.setattr(repository_files, '_validate', unavailable)

    result = repository_files.check(['--root', str(tmp_path)])

    _assert_execution_failure(result, 'dependency-unavailable')


@pytest.mark.contract_case('HOOK-HARNESS-008')
def test_repository_manifest_violation_is_blocked(monkeypatch, tmp_path) -> None:
    def invalid_manifest(*_args, **_kwargs):
        raise ValueError('forbidden_root_paths must be a list')

    monkeypatch.setattr(repository_files, '_validate', invalid_manifest)

    result = repository_files.check(['--root', str(tmp_path)])

    assert result.status is CheckStatus.BLOCKED


def test_repository_input_read_error_is_execution_failure(monkeypatch, tmp_path) -> None:
    def unreadable(*_args, **_kwargs):
        raise OSError('cannot read commands')

    monkeypatch.setattr(repository_files, '_validate', unreadable)

    result = repository_files.check(['--root', str(tmp_path)])

    _assert_execution_failure(result, 'input-unavailable')


def test_no_skips_scan_error_is_execution_failure(monkeypatch, tmp_path) -> None:
    def unreadable(_root):
        raise OSError('cannot read test source')

    monkeypatch.setattr(no_skips, '_scan_repo', unreadable)

    result = no_skips.check(['--root', str(tmp_path)])

    _assert_execution_failure(result, 'input-unavailable')


def test_current_source_incomplete_scan_is_execution_failure(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        current_source,
        '_check_current_source_policy',
        lambda _root, _changed_files=None: ([], ['source.css: unreadable-source']),
    )

    result = current_source.check(['--root', str(tmp_path)])

    _assert_execution_failure(result, 'input-unavailable')


@pytest.mark.contract_case('HOOK-HARNESS-008')
def test_current_source_policy_finding_is_blocked(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        current_source,
        '_check_current_source_policy',
        lambda _root, _changed_files=None: (['historical version'], []),
    )

    result = current_source.check(['--root', str(tmp_path)])

    assert result.status is CheckStatus.BLOCKED


@pytest.mark.contract_case('HOOK-HARNESS-008')
def test_secret_scan_read_error_is_execution_failure(monkeypatch, tmp_path) -> None:
    source = tmp_path / 'tests' / 'sample.txt'
    source.parent.mkdir(parents=True)
    source.write_text('synthetic\n', encoding='utf-8')
    monkeypatch.setattr(secret_policy, 'ROOT', tmp_path)
    monkeypatch.setattr(secret_policy, 'SCAN_DIRS', ['tests'])

    def unreadable(_path):
        raise OSError('cannot read protected file')

    monkeypatch.setattr(secret_policy, '_scan_file', unreadable)

    result = secret_policy.check([])

    _assert_execution_failure(result, 'input-unavailable')
