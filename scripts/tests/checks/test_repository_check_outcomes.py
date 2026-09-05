"""验证仓库类 Check 能区分领域阻断与执行失败。"""

from __future__ import annotations

import pytest
from scripts.gates.checks.check_protocol import CheckStatus
from scripts.gates.checks.privacy import check_credential_leak as secret_policy
from scripts.gates.checks.repository import check_current_version as current_version
from scripts.gates.checks.repository import check_file_boundary as repository_files
from scripts.gates.checks.repository import check_test_data_privacy as test_data_privacy
from scripts.gates.checks.repository import check_test_skip_prohibition as skip_prohibition


def _assert_execution_failure(result, reason: str) -> None:
    assert result.status is CheckStatus.FAIL
    assert result.reason == reason
    assert result.diagnostics


def test_test_data_privacy_git_unavailable_is_execution_failure(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        test_data_privacy,
        '_validate_test_data_privacy',
        lambda _root: ['git-tracked-files-unavailable'],
    )

    result = test_data_privacy.check(['--repo-root', str(tmp_path)])

    _assert_execution_failure(result, 'dependency-unavailable')


@pytest.mark.contract_case('HOOK-HARNESS-008')
def test_test_data_privacy_privacy_finding_is_blocked(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        test_data_privacy,
        '_validate_test_data_privacy',
        lambda _root: ['tests/fixtures/sample.txt: untracked-test-data'],
    )

    result = test_data_privacy.check(['--repo-root', str(tmp_path)])

    assert result.status is CheckStatus.BLOCKED


def test_test_data_privacy_read_error_is_execution_failure(monkeypatch, tmp_path) -> None:
    def unreadable(_root):
        raise OSError('cannot enumerate test data')

    monkeypatch.setattr(test_data_privacy, '_validate_test_data_privacy', unreadable)

    result = test_data_privacy.check(['--repo-root', str(tmp_path)])

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


def test_skip_prohibition_scan_error_is_execution_failure(monkeypatch, tmp_path) -> None:
    def unreadable(_root):
        raise OSError('cannot read test source')

    monkeypatch.setattr(skip_prohibition, '_scan_repo', unreadable)

    result = skip_prohibition.check(['--root', str(tmp_path)])

    _assert_execution_failure(result, 'input-unavailable')


def test_current_version_incomplete_scan_is_execution_failure(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        current_version,
        '_check_current_version',
        lambda _root, _changed_files=None: ([], ['source.css: unreadable-source']),
    )

    result = current_version.check(['--root', str(tmp_path)])

    _assert_execution_failure(result, 'input-unavailable')


@pytest.mark.contract_case('HOOK-HARNESS-008')
def test_current_version_finding_is_blocked(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        current_version,
        '_check_current_version',
        lambda _root, _changed_files=None: (['historical version'], []),
    )

    result = current_version.check(['--root', str(tmp_path)])

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


def test_secret_scan_excludes_generated_runtime_but_not_java_source(monkeypatch, tmp_path):
    generated = tmp_path / 'java/app-cli/build/jlink-image/bin/java'
    generated.parent.mkdir(parents=True)
    generated.write_bytes(b'\xcf\xfa\xed\xfe')
    (tmp_path / 'java/app-cli/build.gradle.kts').write_text('', encoding='utf-8')
    source = tmp_path / 'java/app-cli/src/main/resources/example.txt'
    source.parent.mkdir(parents=True)
    source.write_text('gh' + 'p_' + 'A' * 32, encoding='utf-8')
    monkeypatch.setattr(secret_policy, 'ROOT', tmp_path)
    monkeypatch.setattr(secret_policy, 'SCAN_DIRS', ['java'])

    result = secret_policy.check([])

    assert result.status is CheckStatus.BLOCKED
    assert any('example.txt' in item.message for item in result.diagnostics)
    assert not any('bin/java' in item.message for item in result.diagnostics)


def test_secret_scan_unreadable_source_still_fails_closed(monkeypatch, tmp_path):
    source = tmp_path / 'java/app-cli/src/main/resources/entry'
    source.parent.mkdir(parents=True)
    source.write_bytes(b'\xcf\xfa\xed\xfe')
    monkeypatch.setattr(secret_policy, 'ROOT', tmp_path)
    monkeypatch.setattr(secret_policy, 'SCAN_DIRS', ['java'])

    _assert_execution_failure(secret_policy.check([]), 'input-unavailable')


@pytest.mark.parametrize(
    'relative',
    [
        'java/app-cli/src/main/java/com/example/build/BuildCommand.java',
        'java/tests/contracts/src/test/resources/build/fixture.txt',
        'java/tests/contracts/src/test/resources/.gradle/fixture.txt',
    ],
)
def test_secret_scan_preserves_build_named_source_and_fixtures(monkeypatch, tmp_path, relative):
    source = tmp_path / relative
    source.parent.mkdir(parents=True)
    source.write_text('gh' + 'p_' + 'A' * 32, encoding='utf-8')
    # 即使测试样本内模拟 Gradle 工程，也不能排除 src 下的凭据输入。
    (source.parent.parent / 'build.gradle.kts').write_text('', encoding='utf-8')
    monkeypatch.setattr(secret_policy, 'ROOT', tmp_path)
    monkeypatch.setattr(secret_policy, 'SCAN_DIRS', ['java'])

    assert not secret_policy._is_excluded_path(source)
    assert secret_policy.check([]).status is CheckStatus.BLOCKED
