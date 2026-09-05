"""测试稳定内部名称 Check 的 full 与 incremental 边界。"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from scripts.gates.checks.check_protocol import CheckStatus
from scripts.gates.checks.repository.check_current_version import (
    _check_current_version,
    _check_stable_internal_names,
    check,
)

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.contract_case('HOOK-HARNESS-011')
def test_stable_name_passes(tmp_path: Path) -> None:
    source = tmp_path / 'clean.css'
    source.write_text('.session-card { color: red; }', encoding='utf-8')

    errors, read_failures = _check_stable_internal_names([source])

    assert errors == []
    assert read_failures == []


@pytest.mark.contract_case('HOOK-HARNESS-011')
@pytest.mark.parametrize(
    'identifier',
    ('component-payload-v9', 'quality-catalog:v3', 'render-schema_v4'),
)
def test_versioned_internal_name_blocks(tmp_path: Path, identifier: str) -> None:
    source = tmp_path / 'source.md'
    source.write_text(identifier, encoding='utf-8')

    errors, read_failures = _check_stable_internal_names([source])

    assert len(errors) == 1
    assert 'stable-internal-name' in errors[0]
    assert read_failures == []


@pytest.mark.contract_case('HOOK-HARNESS-011')
def test_release_version_is_not_an_internal_identifier(tmp_path: Path) -> None:
    source = tmp_path / 'release.md'
    source.write_text('Release v2.0\n', encoding='utf-8')

    errors, read_failures = _check_stable_internal_names([source])

    assert errors == []
    assert read_failures == []


def test_client_private_worktree_is_not_scanned(tmp_path: Path) -> None:
    private_copy = tmp_path / '.claude' / 'worktrees' / 'other' / 'copy.py'
    private_copy.parent.mkdir(parents=True)
    private_copy.write_text('component-payload-v9\n', encoding='utf-8')

    errors, _read_failures = _check_current_version(tmp_path)

    assert all('.claude/worktrees' not in error for error in errors)


def test_incremental_mode_only_reads_selected_text_files(tmp_path: Path) -> None:
    blocked = tmp_path / 'docs' / 'blocked.md'
    selected = tmp_path / 'docs' / 'selected.md'
    blocked.parent.mkdir(parents=True)
    blocked.write_text('component-payload-v9\n', encoding='utf-8')
    selected.write_text('当前说明\n', encoding='utf-8')

    selected_errors, _read_failures = _check_current_version(tmp_path, ['docs/selected.md'])
    blocked_errors, _read_failures = _check_current_version(tmp_path, ['docs/blocked.md'])

    assert selected_errors == []
    assert len(blocked_errors) == 1


def test_invalid_incremental_path_payload_is_execution_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv('QUALITY_EXECUTION_MODE', 'incremental')
    monkeypatch.setenv('QUALITY_CHANGED_FILES', '{}')

    result = check(['--root', str(tmp_path)])

    assert result.status is CheckStatus.FAIL
    assert result.reason == 'input-unavailable'
