"""Release version contract tests for the session-browser entrypoint."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_DIR / 'scripts' / 'session-browser.sh'
RELEASE_WORKFLOW = PROJECT_DIR / '.github' / 'workflows' / 'release.yml'
RELEASE_CANDIDATE = PROJECT_DIR / 'scripts' / 'release' / 'create-release-candidate.sh'
HARNESS_MANIFEST = PROJECT_DIR / 'harness' / 'manifest.yaml'
CLI_BUILD = PROJECT_DIR / 'java/app-cli/build.gradle.kts'


def test_distribution_tools_share_the_actual_gradle_jdk():
    source = CLI_BUILD.read_text(encoding='utf-8')
    assert 'val distributionJdk = File(System.getProperty("java.home"))' in source
    assert 'distributionJdk.resolve("bin/jdeps$jdkExecutableSuffix")' in source
    assert 'distributionJdk.resolve("bin/jlink$jdkExecutableSuffix")' in source
    assert 'listOf(jdepsExecutable.absolutePath, "--multi-release"' in source
    assert 'jlinkExecutable.absolutePath,' in source
    assert 'System.getenv("JAVA_HOME")' not in source


def test_distribution_tasks_track_jdk_identity_and_runtime_modules():
    source = CLI_BUILD.read_text(encoding='utf-8')
    for task_name, tool_name in (('jdepsModuleList', 'jdeps'), ('jlinkImage', 'jlink')):
        task = source.split(f'val {task_name} = tasks.register("{task_name}") {{', 1)[1]
        inputs = task.split('    doLast {', 1)[0]
        assert 'inputs.property("jdkHome", distributionJdk.absolutePath)' in inputs
        assert 'inputs.file(distributionJdk.resolve("release"))' in inputs
        assert f'inputs.file({tool_name}Executable)' in inputs
        if task_name == 'jlinkImage':
            assert 'inputs.dir(distributionJdk.resolve("jmods"))' in inputs


def test_help_lists_java_owned_product_commands():
    result = subprocess.run(
        [str(SCRIPT), 'help'],
        cwd=PROJECT_DIR,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert {'scan', 'serve', 'stop', 'status', 'doctor', 'deps', 'version', 'diagnose'} <= set(
        result.stdout.split()
    )


def test_version_command_is_read_only():
    version_file = PROJECT_DIR / 'java/gradle/VERSION'
    before = version_file.read_bytes()

    result = subprocess.run(
        [str(SCRIPT), 'version'],
        cwd=PROJECT_DIR,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == before.decode().strip()
    assert not (PROJECT_DIR / 'VERSION').exists()
    assert version_file.read_bytes() == before


def test_release_candidate_requires_explicit_action():
    result = subprocess.run(
        [str(RELEASE_CANDIDATE)],
        cwd=PROJECT_DIR,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert '<verify|create>' in result.stderr
    manifest = HARNESS_MANIFEST.read_text(encoding='utf-8')
    assert 'create-release-candidate.sh verify' in manifest
    assert 'create-release-candidate.sh create' in manifest


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
