"""Release version contract tests for the session-browser entrypoint."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_DIR / 'scripts' / 'session-browser.sh'
RELEASE_WORKFLOW = PROJECT_DIR / '.github' / 'workflows' / 'release.yml'


def _copy_script_project(tmp_path: Path) -> Path:
    script_dir = tmp_path / 'scripts'
    script_dir.mkdir()
    (tmp_path / 'src').mkdir()
    copied_script = script_dir / 'session-browser.sh'
    shutil.copy2(SCRIPT, copied_script)
    return copied_script


def test_version_help_uses_two_part_release_contract():
    result = subprocess.run(
        [str(SCRIPT), 'help'],
        cwd=PROJECT_DIR,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert 'set-version <x.y>' in result.stdout
    assert 'build-dist [x.y]' in result.stdout
    assert 'verify-dist [x.y]' in result.stdout
    assert 'release-check 0.4' in result.stdout
    assert '<x.y.z>' not in result.stdout


def test_set_version_accepts_canonical_two_part_and_patch_compat(tmp_path):
    copied_script = _copy_script_project(tmp_path)
    version_file = tmp_path / 'VERSION'
    version_file.write_text('0.0-dev\n', encoding='utf-8')

    canonical = subprocess.run(
        [str(copied_script), 'set-version', '0.4'],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )
    assert canonical.returncode == 0, canonical.stderr
    assert version_file.read_text(encoding='utf-8').strip() == '0.4'

    patch = subprocess.run(
        [str(copied_script), 'set-version', '0.4.1-rc.1'],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )
    assert patch.returncode == 0, patch.stderr
    assert version_file.read_text(encoding='utf-8').strip() == '0.4.1-rc.1'


def test_version_validation_rejects_invalid_versions(tmp_path):
    copied_script = _copy_script_project(tmp_path)
    version_file = tmp_path / 'VERSION'
    version_file.write_text('0.4\n', encoding='utf-8')

    result = subprocess.run(
        [str(copied_script), 'set-version', '0.4.beta'],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 1
    assert '版本号不合法：0.4.beta' in result.stderr
    assert '请使用版本号 x.y 或 x.y.z，例如 0.4 或 0.4.1-rc.1' in result.stderr
    assert version_file.read_text(encoding='utf-8').strip() == '0.4'


def _workflow_regex_after(marker: str) -> str:
    workflow = RELEASE_WORKFLOW.read_text(encoding='utf-8')
    pattern = re.compile(rf'{re.escape(marker)}.*=~ (.+?) \]\];')
    match = pattern.search(workflow)
    assert match, f'missing workflow regex after {marker}'
    return match.group(1)


def _bash_regex_matches(pattern: str, value: str) -> bool:
    result = subprocess.run(
        ['bash', '-c', '[[ "$2" =~ $1 ]]', '_', pattern, value],
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def test_release_workflow_defaults_to_two_part_v04():
    workflow = RELEASE_WORKFLOW.read_text(encoding='utf-8')

    assert 'default: "0.4"' in workflow
    assert 'default: "0.3.0"' not in workflow
    assert '请使用发布 tag vX.Y 或 vX.Y.Z，例如 v0.4 或 v0.4.1-rc.1' in workflow
    assert '请使用发布版本 X.Y 或 X.Y.Z，例如 0.4 或 0.4.1-rc.1' in workflow


def test_release_workflow_accepts_two_part_and_patch_versions():
    tag_pattern = _workflow_regex_after('if [[ ! "$tag"')
    input_pattern = _workflow_regex_after('if [[ ! "$version"')

    for value in ('v0.4', 'v0.4-rc.1', 'v0.4.1', 'v0.4.1-rc.1', 'v0.4.1.rc.1'):
        assert _bash_regex_matches(tag_pattern, value), value
    for value in ('0.4', '0.4-rc.1', '0.4.1', '0.4.1-rc.1', '0.4.1.rc.1'):
        assert _bash_regex_matches(input_pattern, value), value

    for value in ('0.4', 'v0.4.beta', 'v0'):
        assert not _bash_regex_matches(tag_pattern, value), value
    for value in ('v0.4', '0.4.beta', '0'):
        assert not _bash_regex_matches(input_pattern, value), value
