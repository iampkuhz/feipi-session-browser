"""Release version contract tests for the session-browser entrypoint."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import yaml

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


def test_windows_runtime_launcher_delegates_classpath_expansion_to_java():
    source = CLI_BUILD.read_text(encoding='utf-8')
    launcher = source.split('val winScript = binDir.resolve("run.bat")', 1)[1]
    launcher = launcher.split('        logger.lifecycle(', 1)[0]

    assert r'set \"CLASSPATH=%APP_HOME%\\lib\\*\"\r\n' in launcher
    assert r'\"%RUNTIME_JAVA%\" %JVM_ARGS% -cp \"%CLASSPATH%\" $mainClassName %*\r\n' in launcher
    assert '*.jar' not in launcher
    assert ':addcp' not in launcher
    assert 'for %%j' not in launcher
    assert r'if not exist \"%RUNTIME_JAVA%\" (' in launcher
    assert r'exit /b 1\r\n' in launcher
    assert 'set JVM_ARGS=$standardJvmArgs' in launcher
    assert (
        r'if \"%~1\"==\"scan\" for %%a in (%*) do if \"%%~a\"==\"--full\" set JVM_ARGS=$fullScanJvmArgs'
        in launcher
    )
    assert r'if \"%~1\"==\"serve\" set JVM_ARGS=$fullScanJvmArgs' in launcher


def test_runtime_launcher_tracks_its_inline_template_for_regeneration():
    source = CLI_BUILD.read_text(encoding='utf-8')
    task = source.split(
        'val generateRuntimeLauncher = tasks.register("generateRuntimeLauncher") {', 1
    )[1]
    inputs = task.split('    doLast {', 1)[0]
    assert 'inputs.file(layout.projectDirectory.file("build.gradle.kts"))' in inputs


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


def test_release_dispatch_requires_explicit_version_and_defaults_to_no_publish():
    workflow = RELEASE_WORKFLOW.read_text(encoding='utf-8')
    dispatch = yaml.safe_load(workflow)[True]['workflow_dispatch']['inputs']

    assert dispatch['version']['required'] is True
    assert 'default' not in dispatch['version']
    assert dispatch['publish']['default'] is False
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


def test_runtime_archives_define_precise_executable_permissions():
    source = CLI_BUILD.read_text(encoding='utf-8')
    archive_config = source.split('fun AbstractArchiveTask.configureRuntimeArchive() {', 1)[1]
    archive_config, archives = archive_config.split('tasks.register<Zip>("runtimeDistZip")', 1)
    assert 'filePermissions { unix("0644") }' in archive_config
    assert 'dirPermissions { unix("0755") }' in archive_config
    assert 'with(runtimeContents)' in archive_config
    assert archives.count('configureRuntimeArchive()') == 2
    assert 'tasks.register<Tar>("runtimeDistTar")' in archives
    contents = source.split('val runtimeContents = copySpec {', 1)[1]
    contents = contents.split('fun AbstractArchiveTask.configureRuntimeArchive()', 1)[0]
    assert 'filesMatching("run") { permissions { unix("0755") } }' in contents
    app = source.split('val runtimeAppContents = copySpec {', 1)[1]
    app = app.split('val prepareRuntimeDist', 1)[0]
    assert 'filesMatching("app-cli") { permissions { unix("0755") } }' in app
    assert 'into("app") { with(runtimeAppContents) }' in contents
    preparation = source.split('val prepareRuntimeDist', 1)[1].split('val runtimeContents', 1)[0]
    assert 'with(runtimeAppContents)' in preparation
    assert 'into(runtimeLayout.map { it.dir("app") })' in preparation
    assert 'from(jlinkImage)' not in preparation
    assert (
        'filesMatching(listOf("bin/*", "lib/jspawnhelper")) { permissions { unix("0755") } }'
        in contents
    )


def test_release_pipeline_is_an_exact_public_executable():
    manifest = yaml.safe_load(HARNESS_MANIFEST.read_text(encoding="utf-8"))
    assert manifest["public_executables"]["release_pipeline"] == (
        "python3 scripts/release/release_pipeline_helpers.py"
    )
