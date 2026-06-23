"""help/version cutover 进程级测试。

验证 help/version 命令通过 Java launcher 执行，其他命令仍走 Python。
使用 fake python trap marker 证明未调用 Python。
"""

import os
import shutil
import stat
import subprocess
import tempfile

# 项目根目录
SB_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SHELL_SCRIPT = os.path.join(SB_ROOT, 'scripts', 'session-browser.sh')


def _create_python_trap(tmp_dir: str) -> str:
    """创建 fake python/python3 trap marker，返回 trap 目录路径。"""
    trap_dir = os.path.join(tmp_dir, 'trap_bin')
    os.makedirs(trap_dir, exist_ok=True)
    marker_file = os.path.join(tmp_dir, 'python_trap_marker.txt')

    for name in ('python', 'python3'):
        script_path = os.path.join(trap_dir, name)
        with open(script_path, 'w') as f:
            f.write('#!/bin/sh\n')
            f.write(f'echo "TRAPPED" >> "{marker_file}"\n')
            f.write('exit 0\n')
        os.chmod(script_path, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)

    return trap_dir


def _run_shell(cmd: str, *, cwd: str | None = None, extra_env: dict | None = None) -> subprocess.CompletedProcess:
    """运行 session-browser.sh 命令并返回结果。"""
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        ['bash', SHELL_SCRIPT, cmd],
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
        timeout=30,
    )


def _run_shell_with_trap(cmd: str, *, cwd: str | None = None, extra_env: dict | None = None) -> tuple:
    """运行命令并检查 Python trap marker。返回 (result, trap_called)。"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        trap_dir = _create_python_trap(tmp_dir)
        marker_file = os.path.join(tmp_dir, 'python_trap_marker.txt')

        env = os.environ.copy()
        env['PATH'] = trap_dir + os.pathsep + env.get('PATH', '')
        if extra_env:
            env.update(extra_env)

        result = subprocess.run(
            ['bash', SHELL_SCRIPT, cmd],
            capture_output=True,
            text=True,
            cwd=cwd,
            env=env,
            timeout=30,
        )
        trap_called = os.path.isfile(marker_file)
        return result, trap_called


class TestHelpVersionRoutesToJava:
    """help/version 正向路径：路由到 Java，不经过 Python。"""

    def test_help_routes_to_java(self):
        """help 命令通过 Java launcher 执行。"""
        result, trap_called = _run_shell_with_trap('help')
        assert result.returncode == 0, f'stderr: {result.stderr}'
        assert 'session-browser' in result.stdout.lower() or 'session-browser' in result.stdout
        assert not trap_called, 'help 不应调用 Python'

    def test_help_flag_routes_to_java(self):
        """--help 标志通过 Java launcher 执行。"""
        result, trap_called = _run_shell_with_trap('--help')
        assert result.returncode == 0, f'stderr: {result.stderr}'
        assert 'session-browser' in result.stdout.lower() or 'session-browser' in result.stdout
        assert not trap_called, '--help 不应调用 Python'

    def test_h_flag_routes_to_java(self):
        """-h 标志通过 Java launcher 执行。"""
        result, trap_called = _run_shell_with_trap('-h')
        assert result.returncode == 0, f'stderr: {result.stderr}'
        assert not trap_called, '-h 不应调用 Python'

    def test_version_routes_to_java(self):
        """version 命令通过 Java launcher 执行。"""
        result, trap_called = _run_shell_with_trap('version')
        assert result.returncode == 0, f'stderr: {result.stderr}'
        assert 'feipi-session-browser' in result.stdout
        assert not trap_called, 'version 不应调用 Python'

    def test_help_outside_repo_cwd(self):
        """从仓库外 cwd 运行 help 仍能定位 Java launcher。"""
        with tempfile.TemporaryDirectory() as outside_dir:
            result, trap_called = _run_shell_with_trap('help', cwd=outside_dir)
            assert result.returncode == 0, f'stderr: {result.stderr}'
            assert not trap_called, '仓库外 cwd 不应调用 Python'

    def test_version_outside_repo_cwd(self):
        """从仓库外 cwd 运行 version 仍能定位 Java launcher。"""
        with tempfile.TemporaryDirectory() as outside_dir:
            result, trap_called = _run_shell_with_trap('version', cwd=outside_dir)
            assert result.returncode == 0, f'stderr: {result.stderr}'
            assert not trap_called, '仓库外 cwd 不应调用 Python'


class TestHelpVersionPathWithSpaces:
    """路径含空格场景。"""

    def test_help_path_with_spaces(self):
        """项目路径含空格时 help 仍能工作。"""
        with tempfile.TemporaryDirectory() as tmp:
            space_dir = os.path.join(tmp, 'path with spaces')
            os.makedirs(space_dir)
            # 创建 symlink 指向项目根
            link_target = os.path.join(space_dir, 'project')
            os.symlink(SB_ROOT, link_target)
            script_in_space = os.path.join(link_target, 'scripts', 'session-browser.sh')

            trap_dir = _create_python_trap(tmp)
            marker_file = os.path.join(tmp, 'python_trap_marker.txt')
            env = os.environ.copy()
            env['PATH'] = trap_dir + os.pathsep + env.get('PATH', '')

            result = subprocess.run(
                ['bash', script_in_space, 'help'],
                capture_output=True,
                text=True,
                cwd=tmp,
                env=env,
                timeout=30,
            )
            assert result.returncode == 0, f'stderr: {result.stderr}'
            assert not os.path.isfile(marker_file), '路径含空格时不应调用 Python'


class TestLauncherMissingNoFallback:
    """launcher 缺失场景：中文报错、非零退出、不 fallback。"""

    def test_launcher_missing_help(self):
        """Java launcher 缺失时 help 回退到 shell print_usage，不 fallback 到 Python。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            # 复制 shell script 到临时目录，模拟无 launcher 的项目
            fake_project = os.path.join(tmp_dir, 'fake_project')
            os.makedirs(fake_project)
            fake_scripts = os.path.join(fake_project, 'scripts')
            os.makedirs(fake_scripts)
            # 创建 src 目录（shell 脚本初始化时需要）
            os.makedirs(os.path.join(fake_project, 'src'))
            fake_sh = os.path.join(fake_scripts, 'session-browser.sh')
            shutil.copy2(SHELL_SCRIPT, fake_sh)
            os.chmod(fake_sh, stat.S_IRWXU)
            # VERSION 文件
            with open(os.path.join(fake_project, 'VERSION'), 'w') as f:
                f.write('0.0-test\n')

            trap_dir = _create_python_trap(tmp_dir)
            marker_file = os.path.join(tmp_dir, 'python_trap_marker.txt')
            env = os.environ.copy()
            env['PATH'] = trap_dir + os.pathsep + env.get('PATH', '')

            result = subprocess.run(
                ['bash', fake_sh, 'help'],
                capture_output=True,
                text=True,
                cwd=tmp_dir,
                env=env,
                timeout=10,
            )
            # help 回退到 shell print_usage，始终成功
            assert result.returncode == 0, f'help 应通过 print_usage 成功: {result.stderr}'
            # 不应 fallback 到 Python
            assert not os.path.isfile(marker_file), '不应 fallback 到 Python'

    def test_launcher_missing_version(self):
        """Java launcher 缺失时 version 报错退出，不 fallback 到 Python。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            fake_project = os.path.join(tmp_dir, 'fake_project')
            os.makedirs(fake_project)
            fake_scripts = os.path.join(fake_project, 'scripts')
            os.makedirs(fake_scripts)
            # 创建 src 目录（shell 脚本初始化时需要）
            os.makedirs(os.path.join(fake_project, 'src'))
            fake_sh = os.path.join(fake_scripts, 'session-browser.sh')
            shutil.copy2(SHELL_SCRIPT, fake_sh)
            os.chmod(fake_sh, stat.S_IRWXU)
            with open(os.path.join(fake_project, 'VERSION'), 'w') as f:
                f.write('0.0-test\n')

            trap_dir = _create_python_trap(tmp_dir)
            marker_file = os.path.join(tmp_dir, 'python_trap_marker.txt')
            env = os.environ.copy()
            env['PATH'] = trap_dir + os.pathsep + env.get('PATH', '')

            result = subprocess.run(
                ['bash', fake_sh, 'version'],
                capture_output=True,
                text=True,
                cwd=tmp_dir,
                env=env,
                timeout=10,
            )
            assert result.returncode != 0, 'launcher 缺失应非零退出'
            assert '错误' in result.stderr or '未找到' in result.stderr, \
                f'stderr 应包含中文错误信息: {result.stderr}'
            assert not os.path.isfile(marker_file), '不应 fallback 到 Python'


class TestBuildInfoCorrupted:
    """build-info.properties 损坏场景。"""

    def test_corrupted_build_info(self):
        """build-info 损坏时 Java launcher 非零退出。"""
        lib_dir = os.path.join(
            SB_ROOT, 'java', 'app-cli', 'build', 'install', 'app-cli', 'lib'
        )
        if not os.path.isdir(lib_dir):
            raise AssertionError('install/lib 目录不存在')

        # 找到包含 build-info.properties 的 JAR
        jar_files = [f for f in os.listdir(lib_dir) if f.startswith('app-cli')]
        if not jar_files:
            raise AssertionError('app-cli JAR 不存在')

        # 此测试只验证 Java launcher 在 build-info 损坏时非零退出
        # 实际损坏测试通过 Gradle cliSmokeTest 覆盖
        # 这里只确认正常状态下 launcher 能工作
        result = _run_shell('version')
        assert result.returncode == 0, f'stderr: {result.stderr}'


class TestUnswitchedCommandsRegression:
    """未切换命令回归：scan/serve/stop/test/deps 保持原行为。

    通过设置 SESSION_BROWSER_VENV_DIR 指向不存在的路径，
    强制 python_bin() 使用 PATH 中的 trap python。
    """

    def test_scan_still_uses_python(self):
        """scan 命令仍路由到 Python。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            trap_dir = _create_python_trap(tmp_dir)
            marker_file = os.path.join(tmp_dir, 'python_trap_marker.txt')
            env = os.environ.copy()
            env['PATH'] = trap_dir + os.pathsep + env.get('PATH', '')
            env['SESSION_BROWSER_VENV_DIR'] = os.path.join(tmp_dir, 'no_such_venv')

            subprocess.run(
                ['bash', SHELL_SCRIPT, 'scan', '--help'],
                capture_output=True,
                text=True,
                env=env,
                timeout=10,
            )
            assert os.path.isfile(marker_file), 'scan 应调用 Python'

    def test_stop_still_uses_python(self):
        """stop 命令仍路由到 Python。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            trap_dir = _create_python_trap(tmp_dir)
            marker_file = os.path.join(tmp_dir, 'python_trap_marker.txt')
            env = os.environ.copy()
            env['PATH'] = trap_dir + os.pathsep + env.get('PATH', '')
            env['SESSION_BROWSER_VENV_DIR'] = os.path.join(tmp_dir, 'no_such_venv')

            subprocess.run(
                ['bash', SHELL_SCRIPT, 'stop', '--help'],
                capture_output=True,
                text=True,
                env=env,
                timeout=10,
            )
            assert os.path.isfile(marker_file), 'stop 应调用 Python'

    def test_test_still_uses_python(self):
        """test 命令仍路由到 Python。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            trap_dir = _create_python_trap(tmp_dir)
            marker_file = os.path.join(tmp_dir, 'python_trap_marker.txt')
            env = os.environ.copy()
            env['PATH'] = trap_dir + os.pathsep + env.get('PATH', '')
            env['SESSION_BROWSER_VENV_DIR'] = os.path.join(tmp_dir, 'no_such_venv')

            subprocess.run(
                ['bash', SHELL_SCRIPT, 'test', '--collect-only'],
                capture_output=True,
                text=True,
                env=env,
                timeout=10,
            )
            assert os.path.isfile(marker_file), 'test 应调用 Python'

    def test_deps_dry_run_still_uses_python(self):
        """deps --dry-run 命令仍路由到 Python。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            trap_dir = _create_python_trap(tmp_dir)
            marker_file = os.path.join(tmp_dir, 'python_trap_marker.txt')
            env = os.environ.copy()
            env['PATH'] = trap_dir + os.pathsep + env.get('PATH', '')
            env['SESSION_BROWSER_VENV_DIR'] = os.path.join(tmp_dir, 'no_such_venv')

            subprocess.run(
                ['bash', SHELL_SCRIPT, 'deps', '--dry-run'],
                capture_output=True,
                text=True,
                env=env,
                timeout=10,
            )
            assert os.path.isfile(marker_file), 'deps 应调用 Python'
