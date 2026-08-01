"""Release version contract tests for the session-browser entrypoint."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_DIR / 'scripts' / 'session-browser.sh'
RELEASE_WORKFLOW = PROJECT_DIR / '.github' / 'workflows' / 'release.yml'


def test_help_does_not_advertise_removed_shell_release_commands():
    result = subprocess.run(
        [str(SCRIPT), 'help'],
        cwd=PROJECT_DIR,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert 'set-version' not in result.stdout
    assert 'build-dist' not in result.stdout
    assert 'verify-dist' not in result.stdout
    assert 'release-check' not in result.stdout
    assert 'release' not in result.stdout


def test_set_version_is_not_a_shell_mutation_command():
    version_file = PROJECT_DIR / 'VERSION'
    before = version_file.read_bytes()

    result = subprocess.run(
        [str(SCRIPT), 'set-version', '0.4'],
        cwd=PROJECT_DIR,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 2
    assert 'set-version' in result.stderr
    assert version_file.read_bytes() == before


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
