"""Java 环境发现与验证的进程级测试。

所有测试使用临时 fake HOME、PATH、JDK、Gradle 和 launcher，不依赖本机安装。
固定系统探测路径只在测试副本重定向到临时目录，生产入口没有测试环境变量。
"""

from __future__ import annotations

import shutil
import stat
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SHELL_SCRIPT = REPO_ROOT / 'scripts' / 'session-browser.sh'


def _write_executable(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')
    path.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)


def _create_fake_jdk(
    path: Path,
    *,
    version: int = 25,
    java_home: Path | None = None,
    include_javac: bool = True,
    with_tool_options_banner: bool = False,
) -> None:
    """创建 fake JDK，java 支持 -version 与 -XshowSettings:properties。"""
    home = java_home or path
    banner = ''
    if with_tool_options_banner:
        banner = 'echo "Picked up JAVA_TOOL_OPTIONS: -Dcompat=\\"17\\"" >&2\n'
    java_body = (
        '#!/usr/bin/env bash\n'
        f'{banner}'
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
        f'  printf "os.arch = aarch64\\n"\n'
        'fi\n'
        'if $has_version; then\n'
        f'  echo "java version \\"{version}.0.1\\"" >&2\n'
        '  echo "Java(TM) SE Runtime Environment" >&2\n'
        '  echo "Java HotSpot(TM) 64-Bit Server VM" >&2\n'
        'fi\n'
    )
    _write_executable(path / 'bin' / 'java', java_body)
    if include_javac:
        _write_executable(
            path / 'bin' / 'javac',
            f'#!/usr/bin/env bash\necho "javac {version}.0.1"\n',
        )


def _create_fake_stub_java(path: Path) -> None:
    """创建 macOS 风格的占位 java（执行失败）。"""
    _write_executable(
        path / 'bin' / 'java',
        '#!/usr/bin/env bash\n'
        'if [[ -n "${STUB_PROBE_MARKER:-}" ]]; then printf probed > "$STUB_PROBE_MARKER"; fi\n'
        'echo "No Java runtime present. Please install." >&2\nexit 1\n',
    )


def _create_minimal_project(
    project: Path,
    *,
    include_launcher: bool = True,
    include_gradle: bool = True,
) -> None:
    script = project / 'scripts' / 'session-browser.sh'
    script.parent.mkdir(parents=True)
    script.write_bytes(SHELL_SCRIPT.read_bytes())
    helper = project / 'scripts/harness/java_env.sh'
    helper.parent.mkdir(parents=True, exist_ok=True)
    helper.write_bytes((REPO_ROOT / 'scripts/harness/java_env.sh').read_bytes())
    script.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
    (project / 'scripts' / 'gates').mkdir(parents=True)
    (project / 'scripts' / 'gates' / 'cli.py').write_text('# fake gate\n', encoding='utf-8')
    if include_launcher:
        _write_executable(
            project / 'java/app-cli/build/install/app-cli/bin/app-cli',
            '#!/usr/bin/env bash\n'
            'printf "CWD=<%s>\\n" "$PWD"\n'
            'printf "ARG=<%s>\\n" "$@"\n'
            'printf "JAVA_HOME=<%s>\\n" "${JAVA_HOME:-}"\n',
        )
    if include_gradle:
        _write_executable(
            project / 'java/gradlew',
            '#!/usr/bin/env bash\n'
            'if [[ -n "${FAKE_GRADLE_LOG:-}" ]]; then\n'
            '  printf "GRADLE_ARG=<%s>\\n" "$@" >> "$FAKE_GRADLE_LOG"\n'
            '  printf "\\n" >> "$FAKE_GRADLE_LOG"\n'
            'fi\n'
            'exit "${FAKE_GRADLE_EXIT:-0}"\n',
        )


def _isolate_script(
    project: Path,
    tmp_path: Path,
    *,
    disable_macos_probe: bool = True,
    sdkman_default_root: Path | None = None,
) -> None:
    """仅改测试副本的固定路径，不给生产入口增加环境变量后门。"""
    script = project / 'scripts/harness/java_env.sh'
    content = script.read_text(encoding='utf-8')
    content = content.replace('/opt/homebrew', str(tmp_path / 'system-homebrew'))
    if disable_macos_probe:
        content = content.replace('/usr/libexec/java_home', str(tmp_path / 'absent-java-home'))
    if sdkman_default_root is not None:
        content = content.replace('$HOME/.sdkman', str(sdkman_default_root))
    script.write_text(content, encoding='utf-8')


def _run_script(
    script: Path,
    *args: str,
    env: dict[str, str],
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ['bash', str(script), *args],
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )


def _minimal_env(tmp_path: Path) -> dict[str, str]:
    """只提供指定基础工具，不把宿主 java/shim 带入测试 PATH。"""
    fake_bin = tmp_path / 'fake-bin'
    fake_bin.mkdir(parents=True, exist_ok=True)
    for name in ('bash', 'dirname', 'sed', 'sleep', 'touch', 'uname'):
        tool = shutil.which(name)
        assert tool is not None, f'测试需要基础工具 {name}'
        link = fake_bin / name
        if not link.exists():
            link.symlink_to(tool)
    return {
        'HOME': str(tmp_path / 'fake-home'),
        'PATH': str(fake_bin),
        'TERM': 'dumb',
    }


# === 显式 JAVA_HOME ===


def test_explicit_valid_java_home_is_respected(tmp_path: Path) -> None:
    project = tmp_path / 'project'
    _create_minimal_project(project)
    _isolate_script(project, tmp_path)
    jdk = tmp_path / 'explicit-jdk'
    _create_fake_jdk(jdk)
    env = _minimal_env(tmp_path)
    env['JAVA_HOME'] = str(jdk)

    result = _run_script(
        project / 'scripts' / 'session-browser.sh',
        'serve',
        env=env,
        cwd=project,
    )

    assert result.returncode == 0, result.stderr
    assert f'JAVA_HOME=<{jdk}>' in result.stdout


def test_explicit_invalid_java_home_fails_with_clear_error(tmp_path: Path) -> None:
    project = tmp_path / 'project'
    _create_minimal_project(project)
    _isolate_script(project, tmp_path)
    bad_java_home = tmp_path / 'bad-jdk'
    bad_java_home.mkdir(parents=True)
    env = _minimal_env(tmp_path)
    env['JAVA_HOME'] = str(bad_java_home)

    result = _run_script(
        project / 'scripts' / 'session-browser.sh',
        'serve',
        env=env,
        cwd=project,
    )

    assert result.returncode != 0
    assert 'JAVA_HOME' in result.stderr
    assert '无效' in result.stderr or 'JDK 25' in result.stderr


def test_explicit_old_jdk_version_fails_without_fallback(tmp_path: Path) -> None:
    """显式 JAVA_HOME 指向旧版本时，即使存在其他 JDK 25 也不回退。"""
    project = tmp_path / 'project'
    _create_minimal_project(project)
    _isolate_script(project, tmp_path)
    old_jdk = tmp_path / 'old-jdk'
    _create_fake_jdk(old_jdk, version=17)
    # 同时存在一个有效的 JDK 25
    valid_jdk = tmp_path / 'valid-jdk'
    _create_fake_jdk(valid_jdk, version=25)
    env = _minimal_env(tmp_path)
    env['JAVA_HOME'] = str(old_jdk)
    env['PATH'] = f'{valid_jdk / "bin"}:{env["PATH"]}'

    result = _run_script(
        project / 'scripts' / 'session-browser.sh',
        'serve',
        env=env,
        cwd=project,
    )

    assert result.returncode != 0
    assert 'JAVA_HOME' in result.stderr
    assert 'JDK 25' in result.stderr


def test_explicit_java_home_with_wrong_real_home_fails(tmp_path: Path) -> None:
    """JAVA_HOME 的 java 报告的 java.home 不是有效 JDK 时失败。"""
    project = tmp_path / 'project'
    _create_minimal_project(project)
    _isolate_script(project, tmp_path)
    # 创建一个 java，其报告的 java.home 不存在
    fake_jdk = tmp_path / 'fake-jdk'
    _create_fake_jdk(fake_jdk, java_home=tmp_path / 'nonexistent-home')
    env = _minimal_env(tmp_path)
    env['JAVA_HOME'] = str(fake_jdk)

    result = _run_script(
        project / 'scripts' / 'session-browser.sh',
        'serve',
        env=env,
        cwd=project,
    )

    assert result.returncode != 0
    assert 'JAVA_HOME' in result.stderr


# === PATH 发现 ===


def test_path_discovery_finds_real_java(tmp_path: Path) -> None:
    project = tmp_path / 'project'
    _create_minimal_project(project)
    _isolate_script(project, tmp_path)
    path_jdk = tmp_path / 'path-jdk'
    _create_fake_jdk(path_jdk)
    env = _minimal_env(tmp_path)
    env['PATH'] = f'{path_jdk / "bin"}:{env["PATH"]}'

    result = _run_script(
        project / 'scripts' / 'session-browser.sh',
        'serve',
        env=env,
        cwd=project,
    )

    assert result.returncode == 0, result.stderr
    assert f'JAVA_HOME=<{path_jdk}>' in result.stdout


def test_path_discovery_executes_shim_to_get_real_home(tmp_path: Path) -> None:
    """PATH 中的 java 是 shim，执行后获取真实 java.home 再验证。"""
    project = tmp_path / 'project'
    _create_minimal_project(project)
    _isolate_script(project, tmp_path)
    real_jdk = tmp_path / 'real-jdk'
    _create_fake_jdk(real_jdk)
    # 创建一个 shim，指向真实 java
    shim_dir = tmp_path / 'shim-bin'
    _write_executable(
        shim_dir / 'java',
        f'#!/usr/bin/env bash\nexec "{real_jdk / "bin" / "java"}" "$@"\n',
    )
    env = _minimal_env(tmp_path)
    env['PATH'] = f'{shim_dir}:{env["PATH"]}'

    result = _run_script(
        project / 'scripts' / 'session-browser.sh',
        'serve',
        env=env,
        cwd=project,
    )

    assert result.returncode == 0, result.stderr
    assert f'JAVA_HOME=<{real_jdk}>' in result.stdout


def test_path_with_double_symlink_resolves_to_real_home(tmp_path: Path) -> None:
    """双层软链接最终解析到真实 java.home。"""
    project = tmp_path / 'project'
    _create_minimal_project(project)
    _isolate_script(project, tmp_path)
    real_jdk = tmp_path / 'real-jdk'
    _create_fake_jdk(real_jdk)
    # 创建双层软链接
    link1_dir = tmp_path / 'link1'
    link1_dir.mkdir()
    (link1_dir / 'java').symlink_to(real_jdk / 'bin' / 'java')
    link2_dir = tmp_path / 'link2'
    link2_dir.mkdir()
    (link2_dir / 'java').symlink_to(link1_dir / 'java')
    env = _minimal_env(tmp_path)
    env['PATH'] = f'{link2_dir}:{env["PATH"]}'

    result = _run_script(
        project / 'scripts' / 'session-browser.sh',
        'serve',
        env=env,
        cwd=project,
    )

    assert result.returncode == 0, result.stderr
    assert f'JAVA_HOME=<{real_jdk}>' in result.stdout


def test_path_with_spaces_is_handled(tmp_path: Path) -> None:
    project = tmp_path / 'project'
    _create_minimal_project(project)
    _isolate_script(project, tmp_path)
    spaced_jdk = tmp_path / 'jdk with spaces'
    _create_fake_jdk(spaced_jdk)
    env = _minimal_env(tmp_path)
    env['PATH'] = f'{spaced_jdk / "bin"}:{env["PATH"]}'

    result = _run_script(
        project / 'scripts' / 'session-browser.sh',
        'serve',
        env=env,
        cwd=project,
    )

    assert result.returncode == 0, result.stderr
    assert f'JAVA_HOME=<{spaced_jdk}>' in result.stdout


def test_path_java_with_tool_options_banner(tmp_path: Path) -> None:
    """PATH 中的 java 输出 JAVA_TOOL_OPTIONS banner 时仍能正确解析版本。"""
    project = tmp_path / 'project'
    _create_minimal_project(project)
    _isolate_script(project, tmp_path)
    path_jdk = tmp_path / 'path-jdk'
    _create_fake_jdk(path_jdk, with_tool_options_banner=True)
    env = _minimal_env(tmp_path)
    env['PATH'] = f'{path_jdk / "bin"}:{env["PATH"]}'

    result = _run_script(
        project / 'scripts' / 'session-browser.sh',
        'serve',
        env=env,
        cwd=project,
    )

    assert result.returncode == 0, result.stderr
    assert f'JAVA_HOME=<{path_jdk}>' in result.stdout


# === SDKMAN 发现 ===


def test_sdkman_default_candidates_dir_discovery(tmp_path: Path) -> None:
    """默认 ~/.sdkman/candidates/java/current 发现。"""
    project = tmp_path / 'project'
    _create_minimal_project(project)
    fake_home = tmp_path / 'fake-home'
    sdkman_root = fake_home / '.sdkman'
    _isolate_script(project, tmp_path, sdkman_default_root=sdkman_root)
    sdkman_jdk = sdkman_root / 'candidates' / 'java' / 'current'
    _create_fake_jdk(sdkman_jdk)
    env = _minimal_env(tmp_path)
    env['HOME'] = str(fake_home)

    result = _run_script(
        project / 'scripts' / 'session-browser.sh',
        'serve',
        env=env,
        cwd=project,
    )

    assert result.returncode == 0, result.stderr
    assert f'JAVA_HOME=<{sdkman_jdk}>' in result.stdout


def test_sdkman_custom_candidates_dir_via_env(tmp_path: Path) -> None:
    """SDKMAN_CANDIDATES_DIR 环境变量指定 candidates 目录。"""
    project = tmp_path / 'project'
    _create_minimal_project(project)
    _isolate_script(project, tmp_path)
    custom_root = tmp_path / 'custom-sdkman'
    sdkman_jdk = custom_root / 'java' / 'current'
    _create_fake_jdk(sdkman_jdk)
    env = _minimal_env(tmp_path)
    env['SDKMAN_CANDIDATES_DIR'] = str(custom_root)

    result = _run_script(
        project / 'scripts' / 'session-browser.sh',
        'serve',
        env=env,
        cwd=project,
    )

    assert result.returncode == 0, result.stderr
    assert f'JAVA_HOME=<{sdkman_jdk}>' in result.stdout


def test_sdkman_dir_env_entry(tmp_path: Path) -> None:
    """SDKMAN_DIR 环境变量拼接 candidates/java/current。"""
    project = tmp_path / 'project'
    _create_minimal_project(project)
    _isolate_script(project, tmp_path)
    sdkman_dir = tmp_path / 'sdkman-install'
    sdkman_jdk = sdkman_dir / 'candidates' / 'java' / 'current'
    _create_fake_jdk(sdkman_jdk)
    env = _minimal_env(tmp_path)
    env['SDKMAN_DIR'] = str(sdkman_dir)

    result = _run_script(
        project / 'scripts' / 'session-browser.sh',
        'serve',
        env=env,
        cwd=project,
    )

    assert result.returncode == 0, result.stderr
    assert f'JAVA_HOME=<{sdkman_jdk}>' in result.stdout


def test_sdkman_homebrew_libexec_candidates(tmp_path: Path) -> None:
    """Homebrew sdkman-cli/libexec/candidates/java/current 发现。"""
    project = tmp_path / 'project'
    _create_minimal_project(project)
    _isolate_script(project, tmp_path)
    brew_prefix = tmp_path / 'homebrew'
    sdkman_jdk = brew_prefix / 'opt' / 'sdkman-cli' / 'libexec' / 'candidates' / 'java' / 'current'
    _create_fake_jdk(sdkman_jdk)
    env = _minimal_env(tmp_path)
    env['HOMEBREW_PREFIX'] = str(brew_prefix)

    result = _run_script(
        project / 'scripts' / 'session-browser.sh',
        'serve',
        env=env,
        cwd=project,
    )

    assert result.returncode == 0, result.stderr
    assert f'JAVA_HOME=<{sdkman_jdk}>' in result.stdout


# === macOS java_home 探测 ===


def test_macos_java_home_probe_succeeds(tmp_path: Path) -> None:
    project = tmp_path / 'project'
    _create_minimal_project(project)
    macos_jdk = tmp_path / 'macos-jdk'
    _create_fake_jdk(macos_jdk)
    probe_script = tmp_path / 'fake-java-home-probe'
    _write_executable(probe_script, f'#!/usr/bin/env bash\necho "{macos_jdk}"\n')
    _isolate_script(project, tmp_path, disable_macos_probe=False)
    script = project / 'scripts/harness/java_env.sh'
    script.write_text(
        script.read_text(encoding='utf-8').replace('/usr/libexec/java_home', str(probe_script)),
        encoding='utf-8',
    )
    env = _minimal_env(tmp_path)

    result = _run_script(
        project / 'scripts' / 'session-browser.sh',
        'serve',
        env=env,
        cwd=project,
    )

    assert result.returncode == 0, result.stderr
    assert f'JAVA_HOME=<{macos_jdk}>' in result.stdout


# === Homebrew openjdk ===


@pytest.mark.parametrize('formula', ['openjdk', 'openjdk@25'])
@pytest.mark.parametrize('layout', ['', 'libexec/openjdk.jdk/Contents/Home'])
def test_homebrew_openjdk_paths(tmp_path: Path, formula: str, layout: str) -> None:
    """未注册的 Homebrew 通用/版本化 formula 均支持 opt 与 macOS bundle 布局。"""
    project = tmp_path / 'project'
    _create_minimal_project(project)
    _isolate_script(project, tmp_path)
    brew_prefix = tmp_path / 'homebrew with spaces'
    brew_jdk = brew_prefix / 'opt' / formula / layout
    _create_fake_jdk(brew_jdk)
    env = _minimal_env(tmp_path)
    env['HOMEBREW_PREFIX'] = str(brew_prefix)

    result = _run_script(project / 'scripts/session-browser.sh', 'serve', env=env, cwd=project)

    assert result.returncode == 0, result.stderr
    assert f'JAVA_HOME=<{brew_jdk}>' in result.stdout


# === 失败场景 ===


def test_macos_stub_in_path_is_rejected_and_falls_through(tmp_path: Path) -> None:
    project = tmp_path / 'project'
    _create_minimal_project(project)
    _isolate_script(project, tmp_path)
    stub_bin = tmp_path / 'stub-bin'
    _create_fake_stub_java(Path(stub_bin))
    env = _minimal_env(tmp_path)
    env['PATH'] = f'{stub_bin / "bin"}:{env["PATH"]}'
    marker = tmp_path / 'stub-probed'
    env['STUB_PROBE_MARKER'] = str(marker)
    sdkman_jdk = Path(env['HOME']) / '.sdkman/candidates/java/current'
    _create_fake_jdk(sdkman_jdk)

    result = _run_script(
        project / 'scripts' / 'session-browser.sh',
        'serve',
        env=env,
        cwd=project,
    )

    assert result.returncode == 0, result.stderr
    assert marker.read_text() == 'probed'
    assert f'JAVA_HOME=<{sdkman_jdk}>' in result.stdout


def test_old_jdk_in_path_is_rejected(tmp_path: Path) -> None:
    project = tmp_path / 'project'
    _create_minimal_project(project)
    _isolate_script(project, tmp_path)
    old_jdk = tmp_path / 'old-jdk'
    _create_fake_jdk(old_jdk, version=17)
    env = _minimal_env(tmp_path)
    env['PATH'] = f'{old_jdk / "bin"}:{env["PATH"]}'

    result = _run_script(
        project / 'scripts' / 'session-browser.sh',
        'serve',
        env=env,
        cwd=project,
    )

    assert result.returncode != 0
    assert '未找到' in result.stderr or 'JDK 25' in result.stderr


def test_jre_without_javac_is_rejected(tmp_path: Path) -> None:
    project = tmp_path / 'project'
    _create_minimal_project(project)
    _isolate_script(project, tmp_path)
    jre = tmp_path / 'jre'
    _create_fake_jdk(jre, include_javac=False)
    env = _minimal_env(tmp_path)
    env['PATH'] = f'{jre / "bin"}:{env["PATH"]}'

    result = _run_script(
        project / 'scripts' / 'session-browser.sh',
        'serve',
        env=env,
        cwd=project,
    )

    assert result.returncode != 0
    assert '未找到' in result.stderr or 'JDK 25' in result.stderr


def test_no_jdk_at_all_fails_with_clear_error(tmp_path: Path) -> None:
    project = tmp_path / 'project'
    _create_minimal_project(project)
    _isolate_script(project, tmp_path)
    env = _minimal_env(tmp_path)

    result = _run_script(
        project / 'scripts' / 'session-browser.sh',
        'serve',
        env=env,
        cwd=project,
    )

    assert result.returncode != 0
    assert '未找到' in result.stderr
    assert 'JDK 25' in result.stderr


# === 优先级 ===


def test_path_takes_priority_over_sdkman(tmp_path: Path) -> None:
    """PATH 中的 JDK 优先于 SDKMAN。"""
    project = tmp_path / 'project'
    _create_minimal_project(project)
    fake_home = tmp_path / 'fake-home'
    sdkman_root = fake_home / '.sdkman'
    _isolate_script(project, tmp_path, sdkman_default_root=sdkman_root)
    # SDKMAN 中的 JDK
    sdkman_jdk = sdkman_root / 'candidates' / 'java' / 'current'
    _create_fake_jdk(sdkman_jdk, java_home=sdkman_jdk)
    # PATH 中的 JDK（不同路径）
    path_jdk = tmp_path / 'path-jdk'
    _create_fake_jdk(path_jdk)
    env = _minimal_env(tmp_path)
    env['HOME'] = str(fake_home)
    env['PATH'] = f'{path_jdk / "bin"}:{env["PATH"]}'

    result = _run_script(
        project / 'scripts' / 'session-browser.sh',
        'serve',
        env=env,
        cwd=project,
    )

    assert result.returncode == 0, result.stderr
    # 应该使用 PATH 中的 JDK
    assert f'JAVA_HOME=<{path_jdk}>' in result.stdout


# === 环境传递 ===


def test_gradle_and_launcher_share_discovered_java_home(tmp_path: Path) -> None:
    project = tmp_path / 'project'
    _create_minimal_project(project)
    _isolate_script(project, tmp_path)
    path_jdk = tmp_path / 'path-jdk'
    _create_fake_jdk(path_jdk)
    gradle_log = project / 'gradle.env'
    _write_executable(
        project / 'java/gradlew',
        '#!/usr/bin/env bash\n'
        'printf "GRADLE_JAVA_HOME=<%s>\\n" "${JAVA_HOME:-}" > "$GRADLE_LOG"\n'
        'exit 0\n',
    )
    _write_executable(
        project / 'java/app-cli/build/install/app-cli/bin/app-cli',
        '#!/usr/bin/env bash\nprintf "LAUNCHER_JAVA_HOME=<%s>\\n" "${JAVA_HOME:-}"\n',
    )
    env = _minimal_env(tmp_path)
    env['PATH'] = f'{path_jdk / "bin"}:{env["PATH"]}'
    env['GRADLE_LOG'] = str(gradle_log)

    result = _run_script(
        project / 'scripts' / 'session-browser.sh',
        'serve',
        env=env,
        cwd=project,
    )

    assert result.returncode == 0, result.stderr
    assert f'GRADLE_JAVA_HOME=<{path_jdk}>' in gradle_log.read_text(encoding='utf-8')
    assert f'LAUNCHER_JAVA_HOME=<{path_jdk}>' in result.stdout


# === 参数、退出码与 exec 契约 ===


def test_arguments_are_forwarded_after_discovery(tmp_path: Path) -> None:
    project = tmp_path / 'project'
    _create_minimal_project(project)
    _isolate_script(project, tmp_path)
    path_jdk = tmp_path / 'path-jdk'
    _create_fake_jdk(path_jdk)
    env = _minimal_env(tmp_path)
    env['PATH'] = f'{path_jdk / "bin"}:{env["PATH"]}'

    result = _run_script(
        project / 'scripts' / 'session-browser.sh',
        'scan',
        '--full',
        '--index-dir',
        '/tmp/some dir',
        env=env,
        cwd=project,
    )

    assert result.returncode == 0, result.stderr
    assert 'ARG=<scan>' in result.stdout
    assert 'ARG=<--full>' in result.stdout
    assert 'ARG=<--index-dir>' in result.stdout
    assert 'ARG=</tmp/some dir>' in result.stdout


def test_launcher_exit_code_is_preserved(tmp_path: Path) -> None:
    project = tmp_path / 'project'
    _create_minimal_project(project)
    _isolate_script(project, tmp_path)
    path_jdk = tmp_path / 'path-jdk'
    _create_fake_jdk(path_jdk)
    _write_executable(
        project / 'java/app-cli/build/install/app-cli/bin/app-cli',
        '#!/usr/bin/env bash\nexit 42\n',
    )
    env = _minimal_env(tmp_path)
    env['PATH'] = f'{path_jdk / "bin"}:{env["PATH"]}'

    result = _run_script(
        project / 'scripts' / 'session-browser.sh',
        'scan',
        env=env,
        cwd=project,
    )

    assert result.returncode == 42


def test_discovered_java_home_is_exported_to_path(tmp_path: Path) -> None:
    project = tmp_path / 'project'
    _create_minimal_project(project)
    _isolate_script(project, tmp_path)
    path_jdk = tmp_path / 'path-jdk'
    _create_fake_jdk(path_jdk)
    _write_executable(
        project / 'java/app-cli/build/install/app-cli/bin/app-cli',
        '#!/usr/bin/env bash\nprintf "FIRST_PATH_BIN=<%s>\\n" "$(dirname "$(command -v java)")"\n',
    )
    env = _minimal_env(tmp_path)
    env['PATH'] = f'{path_jdk / "bin"}:{env["PATH"]}'

    result = _run_script(
        project / 'scripts' / 'session-browser.sh',
        'scan',
        env=env,
        cwd=project,
    )

    assert result.returncode == 0, result.stderr
    assert f'FIRST_PATH_BIN=<{path_jdk / "bin"}>' in result.stdout


# === 非 serve 命令 launcher 优先诊断 ===


def test_non_serve_command_reports_missing_launcher_before_jdk(tmp_path: Path) -> None:
    """非 serve 命令缺少 launcher 时，报告 launcher 缺失而非 JDK 缺失。"""
    project = tmp_path / 'project'
    _create_minimal_project(project, include_launcher=False)
    _isolate_script(project, tmp_path)
    # 不设置 JDK，也不在 PATH 中
    env = _minimal_env(tmp_path)

    result = _run_script(
        project / 'scripts' / 'session-browser.sh',
        'scan',
        env=env,
        cwd=project,
    )

    assert result.returncode != 0
    # 应该报告 launcher 缺失，而非 JDK 缺失
    assert 'launcher 未找到' in result.stderr
    assert 'deps' in result.stderr


@pytest.mark.parametrize('failure', ['wrong-java-version', 'wrong-compiler', 'missing-home'])
def test_reported_home_must_itself_be_a_valid_jdk(tmp_path: Path, failure: str) -> None:
    """不能只相信 shim/候选报告的版本或 home。"""
    project = tmp_path / 'project'
    _create_minimal_project(project)
    _isolate_script(project, tmp_path)
    actual = tmp_path / 'actual-jdk'
    _create_fake_jdk(actual, version=17 if failure == 'wrong-java-version' else 25)
    if failure == 'wrong-compiler':
        _write_executable(actual / 'bin/javac', '#!/usr/bin/env bash\necho "javac 17.0.1"\n')
    if failure == 'missing-home':
        actual = tmp_path / 'missing-jdk'
    candidate = tmp_path / 'candidate'
    _create_fake_jdk(candidate, java_home=actual)
    env = _minimal_env(tmp_path)
    env['JAVA_HOME'] = str(candidate)

    result = _run_script(project / 'scripts/session-browser.sh', 'serve', env=env)

    assert result.returncode == 1
    assert 'JAVA_HOME' in result.stderr
    assert 'ARG=<' not in result.stdout


def test_valid_explicit_home_precedes_other_valid_path_jdk(tmp_path: Path) -> None:
    project = tmp_path / 'project'
    _create_minimal_project(project)
    _isolate_script(project, tmp_path)
    explicit, path_jdk = tmp_path / 'explicit', tmp_path / 'path-jdk'
    _create_fake_jdk(explicit)
    _create_fake_jdk(path_jdk)
    env = _minimal_env(tmp_path)
    env['JAVA_HOME'] = str(explicit)
    env['PATH'] = f'{path_jdk / "bin"}:{env["PATH"]}'

    result = _run_script(project / 'scripts/session-browser.sh', 'serve', env=env)

    assert result.returncode == 0, result.stderr
    assert f'JAVA_HOME=<{explicit}>' in result.stdout


def test_homebrew_standard_prefix_is_discovered_without_export(tmp_path: Path) -> None:
    """模拟默认 Homebrew SDKMAN 路径，不依赖 HOMEBREW_PREFIX。"""
    project = tmp_path / 'project'
    _create_minimal_project(project)
    _isolate_script(project, tmp_path)
    jdk = tmp_path / 'system-homebrew/opt/sdkman-cli/libexec/candidates/java/current'
    _create_fake_jdk(jdk)
    env = _minimal_env(tmp_path)
    env.pop('HOME')

    result = _run_script(project / 'scripts/session-browser.sh', 'serve', env=env)

    assert result.returncode == 0, result.stderr
    assert f'JAVA_HOME=<{jdk}>' in result.stdout
    assert 'unbound variable' not in result.stderr


def test_exported_shell_function_does_not_replace_path_executable(tmp_path: Path) -> None:
    project = tmp_path / 'project'
    _create_minimal_project(project)
    _isolate_script(project, tmp_path)
    jdk = tmp_path / 'path-jdk'
    _create_fake_jdk(jdk)
    env = _minimal_env(tmp_path)
    env['PATH'] = f'{jdk / "bin"}:{env["PATH"]}'

    result = subprocess.run(
        [
            'bash',
            '-c',
            'java() { echo shell-function-called >&2; return 1; }; export -f java; '
            'exec bash "$1" serve',
            'test-wrapper',
            str(project / 'scripts/session-browser.sh'),
        ],
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert f'JAVA_HOME=<{jdk}>' in result.stdout
    assert 'shell-function-called' not in result.stderr
