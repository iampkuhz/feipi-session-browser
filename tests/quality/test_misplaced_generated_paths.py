"""Tests for the misplaced generated paths quality gate."""

from __future__ import annotations

from typing import TYPE_CHECKING

import yaml
from scripts.checks import check_misplaced_generated_paths

if TYPE_CHECKING:
    from pathlib import Path


def _write_manifest(root: Path, paths: list[str]) -> Path:
    manifest = root / 'harness' / 'manifest.yaml'
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        yaml.safe_dump({'forbidden_generated_paths': paths}, sort_keys=False),
        encoding='utf-8',
    )
    return manifest


def test_gitignored_directory_is_still_detected(tmp_path: Path):
    root = tmp_path / 'repo'
    root.mkdir()
    _write_manifest(root, ['output/'])
    (root / '.gitignore').write_text('/output/\n', encoding='utf-8')
    (root / 'output').mkdir()
    (root / 'output' / 'ignored.txt').write_text('generated\n', encoding='utf-8')

    assert check_misplaced_generated_paths.main(['--root', str(root)]) == 1


def test_clean_repository_passes(tmp_path: Path):
    root = tmp_path / 'repo'
    root.mkdir()
    _write_manifest(root, ['output/', '.coverage'])

    assert check_misplaced_generated_paths.main(['--root', str(root)]) == 0


def test_manifest_configuration_is_read(tmp_path: Path):
    root = tmp_path / 'repo'
    root.mkdir()
    manifest = _write_manifest(root, ['custom-generated/'])
    (root / 'custom-generated').mkdir()

    assert check_misplaced_generated_paths.load_forbidden_paths(manifest) == ('custom-generated',)
    assert check_misplaced_generated_paths.find_misplaced_paths(
        root,
        check_misplaced_generated_paths.load_forbidden_paths(manifest),
    ) == ('custom-generated',)


def test_repository_manifest_covers_legacy_root_and_misplaced_paths():
    root = check_misplaced_generated_paths.REPO_ROOT
    configured = set(
        check_misplaced_generated_paths.load_forbidden_paths(
            root / check_misplaced_generated_paths.MANIFEST_RELATIVE_PATH
        )
    )

    assert {
        '.gradle',
        '.venv',
        'build',
        'build-logic',
        'lombok.config',
        'package.json',
        'package-lock.json',
        'playwright.config.js',
        'node_modules',
        'reports',
        'harness/reports',
        'tests/test-results',
        'harness/.local',
        'tests/.local',
        '.agent',
        '.traces',
        '.refactor-artifacts',
        'config/reuse-analysis',
        'feipi_jakarta_validation_prompt_tasks',
        'out',
        'data',
        'output',
        '.coverage',
        'coverage.xml',
        '.pytest_cache',
        '.ruff_cache',
    } <= configured
