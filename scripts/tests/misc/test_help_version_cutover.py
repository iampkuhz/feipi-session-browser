"""`session-browser.sh` 薄入口进程级契约。

测试只观察公开参数、进程、输出和退出码，不绑定 shell 内部函数。
"""

from __future__ import annotations

import os
import signal
import stat
import subprocess
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SHELL_SCRIPT = REPO_ROOT / 'scripts' / 'session-browser.sh'
LAUNCHER_RELATIVE = Path('java/app-cli/build/install/app-cli/bin/app-cli')
INSTALLED_LAUNCHER = REPO_ROOT / LAUNCHER_RELATIVE


def _write_executable(path: Path, content: str) -> None:
    """写入可执行的测试替身。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')
    path.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)


def _create_fake_jdk(path: Path, *, version: int = 25, java_home: Path | None = None) -> None:
    """创建 fake JDK，java 支持 -version 与 -XshowSettings:properties。"""
    home = java_home or path
    _write_executable(
        path / 'bin' / 'java',
        '#!/usr/bin/env bash\n'
        'has_properties=false\n'
        'has_version=false\n'
        'for arg in "$@"; do\n'
        '  case "$arg" in\n'
        '    -XshowSettings:properties*) has_properties=true ;;\n'
        '    -version) has_version=true ;;\n'
        '  esac\n'
        'done\n'
        'if $has_properties; then\n'
        f'  printf "java.home = %s\\n" "{home}"\n'
        f'  printf "java.specification.version = {version}\\n"\n'
        'fi\n'
        'if $has_version; then\n'
        f'  echo "java version \\"{version}.0.1\\"" >&2\n'
        '  echo "Java(TM) SE Runtime Environment" >&2\n'
        '  echo "Java HotSpot(TM) 64-Bit Server VM" >&2\n'
        'fi\n',
    )
    _write_executable(
        path / 'bin' / 'javac',
        f'#!/usr/bin/env bash\necho "javac {version}.0.1"\n',
    )


def _create_fake_project(
    tmp_path: Path,
    *,
    launcher_body: str | None = None,
    include_launcher: bool = True,
    include_jdk: bool = True,
) -> tuple[Path, Path]:
    """创建路径含空格的最小项目，只保留公开进程边界。"""
    project = tmp_path / 'project with spaces'
    script = project / 'scripts' / 'session-browser.sh'
    script.parent.mkdir(parents=True)
    script.write_bytes(SHELL_SCRIPT.read_bytes())
    helper = project / 'scripts/harness/java_env.sh'
    helper.parent.mkdir(parents=True)
    helper.write_bytes((REPO_ROOT / 'scripts/harness/java_env.sh').read_bytes())
    script.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
    (project / 'scripts' / 'gates').mkdir(parents=True)
    (project / 'scripts' / 'gates' / 'cli.py').write_text('# fake gate entry\n', encoding='utf-8')

    if include_launcher:
        body = launcher_body or (
            '#!/usr/bin/env bash\n'
            'printf "CWD=<%s>\\n" "$PWD"\n'
            'printf "ARG=<%s>\\n" "$@"\n'
            'exit "${FAKE_LAUNCHER_EXIT:-0}"\n'
        )
        _write_executable(project / LAUNCHER_RELATIVE, body)

    _write_executable(
        project / 'java/gradlew',
        '#!/usr/bin/env bash\n'
        'if [[ -n "${FAKE_GRADLE_LOG:-}" ]]; then\n'
        '  printf "GRADLE_ARG=<%s>\\n" "$@" > "$FAKE_GRADLE_LOG"\n'
        'fi\n'
        'exit "${FAKE_GRADLE_EXIT:-0}"\n',
    )

    if include_jdk:
        _create_fake_jdk(project / 'fake-jdk')

    # 隔离系统探测路径
    _isolate_script(project, tmp_path)

    return project, script


def _isolate_script(project: Path, tmp_path: Path) -> None:
    """仅修改测试副本的固定系统路径。"""
    script = project / 'scripts/harness/java_env.sh'
    content = script.read_text(encoding='utf-8')
    content = content.replace('/usr/libexec/java_home', str(tmp_path / 'absent-java-home'))
    content = content.replace('/opt/homebrew', str(tmp_path / 'absent-homebrew'))
    content = content.replace('/usr/local', str(tmp_path / 'absent-localbrew'))
    content = content.replace('$HOME/.sdkman', str(tmp_path / 'absent-sdkman'))
    script.write_text(content, encoding='utf-8')


def _run_shell(
    script: Path,
    *args: str,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """从指定工作目录运行公开 shell 入口。"""
    resolved_env = dict(env) if env is not None else {**os.environ}
    # 根据脚本位置找到 fake JDK（脚本位于 project/scripts/session-browser.sh）
    project_dir = script.parent.parent
    fake_jdk_bin = project_dir / 'fake-jdk' / 'bin'
    if fake_jdk_bin.is_dir():
        resolved_env.pop('JAVA_HOME', None)
        # 清除 SDKMAN 环境变量，避免干扰
        resolved_env.pop('SDKMAN_DIR', None)
        resolved_env.pop('SDKMAN_CANDIDATES_DIR', None)
        resolved_env.pop('HOMEBREW_PREFIX', None)
        # 将 fake JDK 添加到 PATH 首位，保留其他 PATH 内容
        existing_path = resolved_env.get('PATH', '/usr/bin:/bin')
        resolved_env['PATH'] = f'{fake_jdk_bin}:{existing_path}'
    return subprocess.run(
        ['bash', str(script), *args],
        cwd=cwd,
        env=resolved_env,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )


def test_no_args_routes_to_java_help_from_arbitrary_cwd(tmp_path: Path) -> None:
    project, script = _create_fake_project(tmp_path)
    outside = tmp_path / 'outside cwd'
    outside.mkdir()

    result = _run_shell(script, cwd=outside)

    assert result.returncode == 0, result.stderr
    assert 'ARG=<--help>' in result.stdout
    assert f'CWD=<{outside}>' in result.stdout
    assert project != outside


@pytest.mark.parametrize(
    ('arguments', 'expected'),
    [
        (('help',), ('help',)),
        (('--help',), ('--help',)),
        (('-h',), ('-h',)),
        (('version',), ('version',)),
        (('serve', '--port', '19000'), ('serve', '--port', '19000')),
        (('stop', '--force'), ('stop', '--force')),
        (('status',), ('status',)),
        (('scan',), ('scan',)),
        (('doctor',), ('doctor',)),
        (('diagnose', 'session', 'fixture.json'), ('diagnose', 'session', 'fixture.json')),
    ],
)
def test_java_commands_are_forwarded_without_rewriting(
    tmp_path: Path,
    arguments: tuple[str, ...],
    expected: tuple[str, ...],
) -> None:
    _, script = _create_fake_project(tmp_path)

    result = _run_shell(script, *arguments, cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[-len(expected) :] == [f'ARG=<{arg}>' for arg in expected]


def test_java_commands_build_launcher_before_forwarding(tmp_path: Path) -> None:
    project, script = _create_fake_project(tmp_path)
    gradle_log = project / 'gradle.args'
    env = {**os.environ, 'FAKE_GRADLE_LOG': str(gradle_log)}

    result = _run_shell(script, 'serve', '--port', '19000', cwd=tmp_path, env=env)

    assert result.returncode == 0, result.stderr
    assert gradle_log.read_text(encoding='utf-8').splitlines() == [
        'GRADLE_ARG=<-p>',
        'GRADLE_ARG=<java>',
        'GRADLE_ARG=<:java:app-cli:installDist>',
    ]
    assert result.stdout.splitlines()[-3:] == [
        'ARG=<serve>',
        'ARG=<--port>',
        'ARG=<19000>',
    ]


def test_java_command_does_not_start_when_incremental_build_fails(tmp_path: Path) -> None:
    project, script = _create_fake_project(tmp_path)
    marker = project / 'launcher-ran'
    _write_executable(
        project / LAUNCHER_RELATIVE,
        f'#!/usr/bin/env bash\ntouch "{marker}"\n',
    )
    env = {**os.environ, 'FAKE_GRADLE_EXIT': '23'}

    result = _run_shell(script, 'serve', cwd=tmp_path, env=env)

    assert result.returncode == 23
    assert not marker.exists()


def test_argument_boundaries_survive_spaces(tmp_path: Path) -> None:
    _, script = _create_fake_project(tmp_path)
    data_dir = str(tmp_path / 'index path with spaces')

    result = _run_shell(
        script,
        'scan',
        '--full',
        '--index-dir',
        data_dir,
        '--agent',
        'codex',
        cwd=tmp_path,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[1:] == [
        'ARG=<scan>',
        'ARG=<--full>',
        'ARG=<--index-dir>',
        f'ARG=<{data_dir}>',
        'ARG=<--agent>',
        'ARG=<codex>',
    ]


@pytest.mark.parametrize('arguments', [(), ('version',), ('serve',)])
def test_missing_launcher_fails_closed_in_chinese(
    tmp_path: Path, arguments: tuple[str, ...]
) -> None:
    _, script = _create_fake_project(tmp_path, include_launcher=False)

    result = _run_shell(script, *arguments, cwd=tmp_path)

    assert result.returncode != 0
    assert '错误：Java launcher 未找到' in result.stderr
    assert 'session-browser.sh deps' in result.stderr


def test_java_exit_code_is_preserved(tmp_path: Path) -> None:
    _, script = _create_fake_project(tmp_path)
    env = {**os.environ, 'FAKE_LAUNCHER_EXIT': '37'}

    result = _run_shell(script, 'scan', '--full', cwd=tmp_path, env=env)

    assert result.returncode == 37


def test_deps_builds_launcher_then_runs_java_preflight(tmp_path: Path) -> None:
    project, script = _create_fake_project(tmp_path)
    gradle_log = project / 'gradle.args'
    _write_executable(
        project / 'java/gradlew',
        '#!/usr/bin/env bash\nprintf "GRADLE_ARG=<%s>\\n" "$@" > "$GRADLE_LOG"\n',
    )
    env = {**os.environ, 'GRADLE_LOG': str(gradle_log)}

    result = _run_shell(script, 'deps', cwd=tmp_path, env=env)

    assert result.returncode == 0, result.stderr
    assert gradle_log.read_text(encoding='utf-8').splitlines() == [
        'GRADLE_ARG=<-p>',
        'GRADLE_ARG=<java>',
        'GRADLE_ARG=<:java:app-cli:installDist>',
    ]
    assert 'ARG=<deps>' in result.stdout
    assert f'CWD=<{project}>' in result.stdout


def test_deps_plan_has_no_side_effect(tmp_path: Path) -> None:
    project, script = _create_fake_project(tmp_path)
    marker = project / 'unexpected-execution'
    _write_executable(project / 'java/gradlew', f'#!/bin/sh\ntouch "{marker}"\n')

    result = _run_shell(script, 'deps', 'plan', cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[0] == 'PLAN ./java/gradlew -p java :java:app-cli:installDist'
    assert not marker.exists()
    assert 'ARG=<' not in result.stdout


@pytest.mark.parametrize('arguments', [('--dev',), ('unexpected',), ('plan', 'extra')])
def test_deps_rejects_invalid_arguments(tmp_path: Path, arguments: tuple[str, ...]) -> None:
    project, script = _create_fake_project(tmp_path)
    marker = project / 'unexpected-execution'
    _write_executable(project / 'java/gradlew', f'#!/bin/sh\ntouch "{marker}"\n')

    result = _run_shell(script, 'deps', *arguments, cwd=tmp_path)

    assert result.returncode == 2
    assert '错误：deps' in result.stderr
    assert not marker.exists()


def test_test_command_runs_fixed_java_verification(tmp_path: Path) -> None:
    project, script = _create_fake_project(tmp_path)
    _write_executable(
        project / 'java/gradlew',
        '#!/usr/bin/env bash\nprintf "GRADLE_ARG=<%s>\\n" "$@"\n',
    )

    result = _run_shell(script, 'test', cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        'GRADLE_ARG=<-p>',
        'GRADLE_ARG=<java>',
        'GRADLE_ARG=<verifyNoSkippedJavaTests>',
        'GRADLE_ARG=<--no-daemon>',
        'GRADLE_ARG=<--no-build-cache>',
        'GRADLE_ARG=<--no-parallel>',
        'GRADLE_ARG=<--max-workers=1>',
    ]


def test_test_command_rejects_pytest_arguments(tmp_path: Path) -> None:
    project, script = _create_fake_project(tmp_path)
    marker = project / 'unexpected-execution'
    _write_executable(project / 'java/gradlew', f'#!/bin/sh\ntouch "{marker}"\n')

    result = _run_shell(script, 'test', 'tests/example.py', cwd=tmp_path)

    assert result.returncode == 2
    assert 'test 不接受额外参数' in result.stderr
    assert not marker.exists()


def _quality_env(tmp_path: Path) -> dict[str, str]:
    """创建仅记录 Gate CLI 参数的 python3 进程边界。"""
    fake_bin = tmp_path / 'fake-bin'
    _write_executable(
        fake_bin / 'python3',
        '#!/usr/bin/env bash\nprintf "PY_ARG=<%s>\\n" "$@"\n',
    )
    return {**os.environ, 'PATH': f'{fake_bin}{os.pathsep}{os.environ.get("PATH", "")}'}


def test_quality_defaults_to_incremental_gate(tmp_path: Path) -> None:
    _, script = _create_fake_project(tmp_path)

    result = _run_shell(script, 'quality', cwd=tmp_path, env=_quality_env(tmp_path))

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        'PY_ARG=<scripts/gates/cli.py>',
        'PY_ARG=<run>',
        'PY_ARG=<--mode>',
        'PY_ARG=<incremental>',
    ]


def test_quality_forwards_explicit_gate_arguments(tmp_path: Path) -> None:
    _, script = _create_fake_project(tmp_path)

    result = _run_shell(
        script,
        'quality',
        'plan',
        '--mode',
        'full',
        '--format',
        'json',
        cwd=tmp_path,
        env=_quality_env(tmp_path),
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        'PY_ARG=<scripts/gates/cli.py>',
        'PY_ARG=<plan>',
        'PY_ARG=<--mode>',
        'PY_ARG=<full>',
        'PY_ARG=<--format>',
        'PY_ARG=<json>',
    ]


def test_shell_exec_preserves_pid_and_signal(tmp_path: Path) -> None:
    pid_file = tmp_path / 'launcher.pid'
    launcher_body = (
        '#!/usr/bin/env bash\n'
        'printf "%s\\n" "$$" > "$FAKE_PID_FILE"\n'
        "trap 'exit 42' TERM\n"
        'while :; do sleep 0.2; done\n'
    )
    project, script = _create_fake_project(tmp_path, launcher_body=launcher_body)
    fake_jdk_bin = project / 'fake-jdk' / 'bin'
    env = {**os.environ, 'FAKE_PID_FILE': str(pid_file)}
    env.pop('JAVA_HOME', None)
    env.pop('SDKMAN_DIR', None)
    env.pop('SDKMAN_CANDIDATES_DIR', None)
    env.pop('HOMEBREW_PREFIX', None)
    env['PATH'] = f'{fake_jdk_bin}:/usr/bin:/bin'
    process = subprocess.Popen(
        ['bash', str(script), 'scan'],
        cwd=tmp_path,
        env=env,
        text=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 5
        while not pid_file.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert pid_file.exists(), '未观察到 Java launcher 进程'
        assert int(pid_file.read_text(encoding='utf-8')) == process.pid
        process.send_signal(signal.SIGTERM)
        assert process.wait(timeout=5) == 42
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def _run_installed_launcher_with_fake_java(
    tmp_path: Path, *arguments: str, app_cli_opts: str | None = None
) -> subprocess.CompletedProcess[str]:
    """用 fake Java 观测 Gradle 生成 launcher 的最终 JVM 参数。"""
    assert INSTALLED_LAUNCHER.is_file(), '请先运行 :java:app-cli:installDist'
    java_home = tmp_path / 'fake-java-home'
    _write_executable(
        java_home / 'bin' / 'java',
        '#!/usr/bin/env bash\nprintf "JVM_ARG=<%s>\\n" "$@"\n',
    )
    env = {**os.environ, 'JAVA_HOME': str(java_home)}
    if app_cli_opts is None:
        env.pop('APP_CLI_OPTS', None)
    else:
        env['APP_CLI_OPTS'] = app_cli_opts
    return subprocess.run(
        [str(INSTALLED_LAUNCHER), *arguments],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )


def test_generated_launcher_selects_full_scan_heap(tmp_path: Path) -> None:
    normal = _run_installed_launcher_with_fake_java(tmp_path, 'scan')
    full = _run_installed_launcher_with_fake_java(tmp_path, 'scan', '--full')

    assert normal.returncode == 0, normal.stderr
    assert 'JVM_ARG=<-Xmx128m>' in normal.stdout
    assert 'JVM_ARG=<-Xmx512m>' not in normal.stdout
    assert full.returncode == 0, full.stderr
    assert 'JVM_ARG=<-Xmx512m>' in full.stdout
    assert 'JVM_ARG=<-Xmx128m>' not in full.stdout


def test_generated_launcher_keeps_user_heap_override_last(tmp_path: Path) -> None:
    result = _run_installed_launcher_with_fake_java(
        tmp_path,
        'scan',
        '--full',
        app_cli_opts='-Dexample=true -Xmx2g',
    )

    assert result.returncode == 0, result.stderr
    args = result.stdout.splitlines()
    assert args.index('JVM_ARG=<-Xmx512m>') < args.index('JVM_ARG=<-Xmx2g>')
