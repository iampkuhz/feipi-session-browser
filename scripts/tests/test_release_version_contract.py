"""Release version contract tests for the session-browser entrypoint."""

from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

PROJECT_DIR = Path(__file__).resolve().parents[2]
RELEASE_WORKFLOW = PROJECT_DIR / '.github' / 'workflows' / 'release.yml'
RELEASE_CANDIDATE = PROJECT_DIR / 'scripts' / 'release' / 'create-release-candidate.sh'
HARNESS_MANIFEST = PROJECT_DIR / 'harness' / 'manifest.yaml'
CLI_BUILD = PROJECT_DIR / 'java/app-cli/build.gradle.kts'


def test_distribution_uses_jlink_from_the_actual_gradle_jdk():
    source = CLI_BUILD.read_text(encoding='utf-8')
    assert 'File(System.getProperty("java.home"))' in source
    assert 'distributionJdk.map { it.resolve("bin/jlink") }' in source
    assert 'jlinkExecutable.get().absolutePath,' in source
    assert 'System.getenv("JAVA_HOME")' not in source


def test_jlink_tracks_jdk_identity_and_runtime_modules():
    source = CLI_BUILD.read_text(encoding='utf-8')
    task = source.split('val jlinkImage = tasks.register("jlinkImage") {', 1)[1]
    inputs = task.split('    doLast {', 1)[0]
    assert 'inputs.property("jdkHome", distributionJdk.map { it.absolutePath })' in inputs
    assert 'inputs.file(distributionJdk.map { it.resolve("release") })' in inputs
    assert 'inputs.file(jlinkExecutable)' in inputs
    assert 'inputs.dir(distributionJdk.map { it.resolve("jmods") })' in inputs
    assert 'inputs.property("runtimeModules", modules)' in inputs


def test_runtime_launcher_tracks_its_inline_template_for_regeneration():
    source = CLI_BUILD.read_text(encoding='utf-8')
    task = source.split(
        'val generateRuntimeLauncher = tasks.register("generateRuntimeLauncher") {', 1
    )[1]
    inputs = task.split('    doLast {', 1)[0]
    assert 'inputs.file(layout.projectDirectory.file("build.gradle.kts"))' in inputs


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


def test_release_dispatch_reads_version_from_source_and_defaults_to_no_publish():
    workflow = RELEASE_WORKFLOW.read_text(encoding='utf-8')
    dispatch = yaml.safe_load(workflow)[True]['workflow_dispatch']['inputs']

    assert set(dispatch) == {'publish'}
    assert dispatch['publish']['default'] is False
    assert 'version="$(cat java/gradle/VERSION)"' in workflow
    assert '"$GITHUB_REF_NAME" != "v$version"' in workflow


def test_release_pipeline_is_an_exact_public_executable():
    manifest = yaml.safe_load(HARNESS_MANIFEST.read_text(encoding="utf-8"))
    assert manifest["public_executables"]["release_pipeline"] == (
        "python3 scripts/release/release_pipeline_helpers.py"
    )
