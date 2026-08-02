from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

from scripts.checks.repository import check_test_data_policy as subject

if TYPE_CHECKING:
    from pathlib import Path


def _write(root: Path, relative: str, text: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    return path


def _init_git(root: Path) -> None:
    subprocess.run(['git', 'init', '-q', str(root)], check=True)


def _track(root: Path, relative: str) -> None:
    subprocess.run(['git', '-C', str(root), 'add', '--', relative], check=True)


def test_rejects_untracked_fixture(tmp_path: Path) -> None:
    _init_git(tmp_path)
    _write(tmp_path, 'tests/unit/fixtures/sample.json', '{"synthetic": true}\n')

    errors = subject._validate_test_data_policy(tmp_path)

    assert errors == ['tests/unit/fixtures/sample.json: untracked-test-data']


def test_accepts_tracked_fixture_and_java_test_resource(tmp_path: Path) -> None:
    _init_git(tmp_path)
    _write(tmp_path, 'tests/unit/fixtures/sample.json', '{"synthetic": true}\n')
    _write(tmp_path, 'java/web/src/test/resources/sample.txt', 'stable test data\n')
    _track(tmp_path, 'tests/unit/fixtures/sample.json')
    _track(tmp_path, 'java/web/src/test/resources/sample.txt')

    assert subject._validate_test_data_policy(tmp_path) == []


def test_rejects_personal_path_and_real_session_without_echoing_content(tmp_path: Path) -> None:
    _init_git(tmp_path)
    private_path = '/Users/' + 'private-owner' + '/.claude/projects/private-session.jsonl'
    _write(tmp_path, 'tests/unit/fixtures/private.txt', private_path + '\n')
    _track(tmp_path, 'tests/unit/fixtures/private.txt')

    errors = subject._validate_test_data_policy(tmp_path)

    assert any('real-session-path' in error for error in errors)
    assert any('personal-device-path' in error for error in errors)
    assert all('private-owner' not in error and 'private-session' not in error for error in errors)


def test_accepts_synthetic_home_path_and_framework_temp_directory(tmp_path: Path) -> None:
    _init_git(tmp_path)
    _write(tmp_path, 'tests/unit/fixtures/sample.txt', '/Users/test/session.jsonl\n')
    _write(
        tmp_path, 'tests/test_temp.py', 'def test_temp(tmp_path):\n    output = tmp_path / "x"\n'
    )
    _track(tmp_path, 'tests/unit/fixtures/sample.txt')
    _track(tmp_path, 'tests/test_temp.py')

    assert subject._validate_test_data_policy(tmp_path) == []


def test_rejects_synthetic_absolute_path_used_as_external_data_source(tmp_path: Path) -> None:
    _init_git(tmp_path)
    synthetic_path = '/Users/' + 'test/external.json'
    source = f'from pathlib import Path\ndata = Path("{synthetic_path}").read_text()\n'
    _write(tmp_path, 'tests/test_external.py', source)
    _track(tmp_path, 'tests/test_external.py')

    errors = subject._validate_test_data_policy(tmp_path)

    assert any('external-test-data-source' in error for error in errors)


def test_rejects_non_home_posix_and_windows_external_data_sources(tmp_path: Path) -> None:
    _init_git(tmp_path)
    posix_path = '/' + 'opt/private-fixtures/input.json'
    windows_path = 'D:' + '\\private-fixtures\\input.json'
    source = (
        f'def load():\n    open("{posix_path}").read()\n    Path(r"{windows_path}").read_text()\n'
    )
    _write(tmp_path, 'tests/test_external_sources.py', source)
    _track(tmp_path, 'tests/test_external_sources.py')

    errors = subject._validate_test_data_policy(tmp_path)

    matching = [error for error in errors if 'external-test-data-source' in error]
    assert len(matching) == 2


def test_rejects_raw_session_but_accepts_explicit_synthetic_record(tmp_path: Path) -> None:
    _init_git(tmp_path)
    parent = 'parent' + 'Uuid'
    prompt = 'prompt' + 'Id'
    message = 'message' + 'Id'
    raw = f'{{"{parent}":null,"{prompt}":"private","{message}":"1"}}\n'
    synthetic = f'{{"synthetic":true,"{parent}":null,"{prompt}":"unit"}}\n'
    _write(tmp_path, 'tests/unit/fixtures/raw.jsonl', raw)
    _write(tmp_path, 'tests/unit/fixtures/synthetic.jsonl', synthetic)
    _track(tmp_path, 'tests/unit/fixtures/raw.jsonl')
    _track(tmp_path, 'tests/unit/fixtures/synthetic.jsonl')

    errors = subject._validate_test_data_policy(tmp_path)

    assert any(error.startswith('tests/unit/fixtures/raw.jsonl:') for error in errors)
    assert not any(error.startswith('tests/unit/fixtures/synthetic.jsonl:') for error in errors)


def test_git_error_fails_closed(tmp_path: Path) -> None:
    _write(tmp_path, 'tests/unit/fixtures/sample.txt', 'data\n')

    assert subject._validate_test_data_policy(tmp_path) == ['git-tracked-files-unavailable']
