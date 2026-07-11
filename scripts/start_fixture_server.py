#!/usr/bin/env python3
"""启动供 Playwright e2e 测试使用的 fixture session server。"""

from __future__ import annotations

import atexit
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse

if TYPE_CHECKING:
    from types import FrameType

SB_ROOT = Path(__file__).resolve().parent.parent
if str(SB_ROOT) not in sys.path:
    sys.path.insert(0, str(SB_ROOT))

from scripts.harness.port_allocator import reserve_port  # noqa: E402
from scripts.harness.primary_session import resolve_runtime_root  # noqa: E402
FIXTURE_ROOT = SB_ROOT / 'tests' / 'fixtures' / 'session_hifi_fixture'
LONG_FIXTURE_ROOT = SB_ROOT / 'tests' / 'fixtures' / 'session_hifi_long_fixture'
DEFAULT_PORT = 19099
HTTP_OK = 200


# 维护Java launcher。
def _java_launcher() -> Path | None:
    """返回：
        路径到 app-cli launcher, 或 None 当 installDist has 未运行。
    """
    launcher = SB_ROOT / 'java' / 'app-cli' / 'build' / 'install' / 'app-cli' / 'bin' / 'app-cli'
    return launcher if launcher.exists() else None


# 维护填充 index。
def populate_index(claude_data_dir: Path, index_dir: Path) -> str | None:
    """参数：
        claude_data_dir: claude data dir 参数。
        index_dir: 包含 index.sqlite 的临时 index 目录。

    返回：
        populate index 字符串。
    """
    # 复用 required gates 使用的 deterministic Java fixture index builder，
    # 让本地 Playwright 和 required gates
    # 使用完全相同的 HIFI data。这里刻意避免
    # 避免启动产品包命令或导入产品 Python package。
    from scripts.quality.run_quality_gate import _populate_fixture_index

    error = _populate_fixture_index(claude_data_dir, index_dir)
    if error is None:
        print(f'Indexed sessions to {index_dir / "index.sqlite"}')
    return error


# 解析端口。
def _resolve_port() -> int:
    """返回：
        Port从BASE_URL, SESSION_BROWSER_PLAYWRIGHT_PORT, 或 默认。
    """
    port = int(os.environ.get('SESSION_BROWSER_PLAYWRIGHT_PORT') or DEFAULT_PORT)
    base_url_env = os.environ.get('BASE_URL', '')
    if base_url_env:
        parsed = urlparse(base_url_env)
        if parsed.port:
            port = parsed.port
    return port


# 复制tree contents。
def _copy_tree_contents(source_root: Path, destination_root: Path) -> None:
    """参数：
        source_root: source 根目录 参数。
        destination_root: 临时 目录 receiving fixture 文件。
    """
    for item in source_root.iterdir():
        destination = destination_root / item.name
        if item.is_dir():
            shutil.copytree(item, destination)
        else:
            shutil.copy2(item, destination)


# 合并long fixture。
def _merge_long_fixture(data_dir: Path) -> None:
    """参数：
        data_dir: fixture server 使用的临时数据目录。
    """
    long_projects = LONG_FIXTURE_ROOT / 'projects'
    if long_projects.exists():
        projects_dir = data_dir / 'projects'
        for item in long_projects.iterdir():
            destination = projects_dir / item.name
            if item.is_dir():
                if destination.exists():
                    for subitem in item.iterdir():
                        sub_destination = destination / subitem.name
                        if subitem.is_dir():
                            shutil.copytree(subitem, sub_destination, dirs_exist_ok=True)
                        else:
                            shutil.copy2(subitem, sub_destination)
                else:
                    shutil.copytree(item, destination)
            else:
                shutil.copy2(item, destination)

    long_history = LONG_FIXTURE_ROOT / 'history.jsonl'
    if long_history.exists():
        history_file = data_dir / 'history.jsonl'
        history_file.write_text(
            history_file.read_text() + long_history.read_text(),
            encoding='utf-8',
        )


# 维护prepare fixture 数据。
def _prepare_fixture_data() -> tuple[Path, Path, Path]:
    """返回：
        由temporary root 目录, index 目录, 和 data 目录.组成的 tuple。
    """
    run_id = os.environ.get('FEIPI_RUN_ID') or os.environ.get('FEIPI_SESSION_ID') or f'pid-{os.getpid()}'
    tmp_root = resolve_runtime_root(SB_ROOT) / 'runs' / run_id / 'tmp' / 'playwright-fixture'
    tmp_root.mkdir(parents=True, exist_ok=True)
    tmpdir = Path(tempfile.mkdtemp(prefix='playwright_fixture_', dir=str(tmp_root)))
    index_dir = tmpdir / 'index'
    index_dir.mkdir()
    data_dir = tmpdir / 'claude_data'
    data_dir.mkdir()
    _copy_tree_contents(FIXTURE_ROOT, data_dir)
    _merge_long_fixture(data_dir)
    return tmpdir, index_dir, data_dir


# 构建server 环境。
def _build_server_env(index_dir: Path, data_dir: Path, port: int) -> dict[str, str]:
    """参数：
        index_dir: 包含 index.sqlite 的临时 index 目录。
        data_dir: 临时 Claude data 目录 used as server 输入。
        port: 本地服务端口。

    返回：
        结果映射。
    """
    env = os.environ.copy()
    env['PYTHONPATH'] = str(SB_ROOT / 'src')
    env['INDEX_DIR'] = str(index_dir)
    env['CLAUDE_DATA_DIR'] = str(data_dir)
    env['SERVER_HOST'] = '127.0.0.1'
    env['SERVER_PORT'] = str(port)
    env['SESSION_BROWSER_LOG_LEVEL'] = 'WARN'
    env['PYTHONUNBUFFERED'] = '1'
    return env


# 等待until ready。
def _wait_until_ready(base_url: str, proc: subprocess.Popen[bytes]) -> bool:
    """参数：
        base_url: base url 参数。
        proc: Server subprocess, used 仅到stop polling 如果 it exits early。

    返回：
        当dashboard 和 fixture sessions 返回 HTTP 200 内 timeout.时返回 true。
    """
    for _ in range(30):
        if proc.poll() is not None:
            return False
        try:
            dashboard = urllib.request.urlopen(f'{base_url}/dashboard', timeout=2)
            session = urllib.request.urlopen(
                f'{base_url}/sessions/claude_code/hifi-viz-session-001',
                timeout=2,
            )
            long_session = urllib.request.urlopen(
                f'{base_url}/sessions/claude_code/long-session-001',
                timeout=2,
            )
            if dashboard.status == session.status == long_session.status == HTTP_OK:
                return True
        except (urllib.error.URLError, TimeoutError, OSError):
            time.sleep(0.5)
    return False


# 维护stop process。
def _stop_process(proc: subprocess.Popen[bytes]) -> None:
    """参数：
        proc: proc 参数。
    """
    if proc.poll() is not None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        with suppress(ProcessLookupError):
            proc.kill()
            proc.wait(timeout=3)
    except PermissionError:
        pass


# 解析命令行参数并运行脚本入口。
def main() -> None:
    if 'BASE_URL' in os.environ or 'SESSION_BROWSER_PLAYWRIGHT_PORT' in os.environ:
        port = _resolve_port()
        port_allocation = None
    else:
        port_allocation = reserve_port(SB_ROOT, 'playwright-fixture', hold_socket=True)
        port = port_allocation.port
        os.environ['BASE_URL'] = f'http://127.0.0.1:{port}'
    tmpdir, index_dir, data_dir = _prepare_fixture_data()
    sqlite_path = index_dir / 'index.sqlite'
    populate_error = populate_index(data_dir, index_dir)
    if populate_error:
        if port_allocation is not None:
            port_allocation.close()
        shutil.rmtree(tmpdir, ignore_errors=True)
        print(f'ERROR: {populate_error}')
        sys.exit(1)

    env = _build_server_env(index_dir, data_dir, port)
    launcher = _java_launcher()
    if launcher is None:
        if port_allocation is not None:
            port_allocation.close()
        shutil.rmtree(tmpdir, ignore_errors=True)
        print('ERROR: Java CLI not built; run ./gradlew :java:app-cli:installDist')
        sys.exit(1)

    print(f'Starting fixture server on http://127.0.0.1:{port}')
    print(f'  Data dir: {data_dir}')
    print(f'  Index: {sqlite_path}')
    print('  Session URLs:')
    print(f'    http://127.0.0.1:{port}/sessions/claude_code/hifi-viz-session-001')
    print(f'    http://127.0.0.1:{port}/sessions/claude_code/long-session-001')
    print(f'  TMPDIR: {tmpdir}')

    if port_allocation is not None and port_allocation.socket is not None:
        port_allocation.socket.close()
        port_allocation.socket = None
    proc = subprocess.Popen(
        [
            str(launcher),
            'serve',
            '--allow-empty',
            '--no-scan',
            '--host',
            '127.0.0.1',
            '--port',
            str(port),
        ],
        cwd=SB_ROOT,
        env=env,
    )

    base_url = f'http://127.0.0.1:{port}'
    if not _wait_until_ready(base_url, proc):
        _stop_process(proc)
        if port_allocation is not None:
            port_allocation.close()
        shutil.rmtree(tmpdir, ignore_errors=True)
        print('ERROR: Server did not start within 15 seconds')
        sys.exit(1)

    print(f'Server ready at {base_url}')
    print('Press Ctrl+C to stop and clean up')

    # 维护清理。
    def cleanup(signum: int | None = None, frame: FrameType | None = None) -> None:
        """参数：
            signum: 可选signal 数字 supplied by signal handlers。
            frame: frame 参数。
        """
        del signum, frame
        print(f'\nShutting down server (PID {proc.pid})...')
        _stop_process(proc)
        if port_allocation is not None:
            port_allocation.close()
        shutil.rmtree(tmpdir, ignore_errors=True)
        print('Cleaned up.')
        sys.exit(0)

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    # 维护退出清理 清理。
    def _atexit_cleanup() -> None:
        _stop_process(proc)
        if port_allocation is not None:
            port_allocation.close()
        shutil.rmtree(tmpdir, ignore_errors=True)

    atexit.register(_atexit_cleanup)

    with suppress(ChildProcessError):
        proc.wait()
    cleanup()


if __name__ == '__main__':
    main()
