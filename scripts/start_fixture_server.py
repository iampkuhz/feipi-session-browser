#!/usr/bin/env python3
"""Start a fixture session server for Playwright e2e tests.

The Playwright workflow runs this long-lived helper in one terminal before e2e
commands point PW_SESSION_URL or PW_LONG_SESSION_URL at the printed URLs. The
script copies fixture session data into a temporary directory, builds an index,
starts the local server, and cleans all temporary data on signals or exit.
"""

from __future__ import annotations

import atexit
import importlib
import os
import shutil
import signal
import sqlite3
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
FIXTURE_ROOT = SB_ROOT / 'tests' / 'fixtures' / 'session_hifi_fixture'
LONG_FIXTURE_ROOT = SB_ROOT / 'tests' / 'fixtures' / 'session_hifi_long_fixture'
DEFAULT_PORT = 19099
HTTP_OK = 200
VENV_PYTHON = SB_ROOT / '.venv' / 'bin' / 'python'
PYTHON_EXECUTABLE = str(VENV_PYTHON if VENV_PYTHON.exists() else Path(sys.executable))


def populate_index(claude_data_dir: Path, sqlite_path: Path) -> None:
    """Index copied fixture sessions into a temporary SQLite database.

    Args:
        claude_data_dir: Temporary Claude data directory populated from test fixtures.
        sqlite_path: SQLite index file path consumed by the fixture server.
    """
    sys.path.insert(0, str(SB_ROOT / 'src'))

    old_data_dir = os.environ.get('CLAUDE_DATA_DIR', '')
    os.environ['CLAUDE_DATA_DIR'] = str(claude_data_dir)

    if 'session_browser.config' in sys.modules:
        importlib.reload(sys.modules['session_browser.config'])
    for mod in list(sys.modules):
        if mod.startswith('session_browser.sources'):
            del sys.modules[mod]

    try:
        indexer = importlib.import_module('session_browser.index.indexer')
        claude_source = importlib.import_module('session_browser.sources.claude')

        conn = sqlite3.connect(sqlite_path)
        conn.row_factory = sqlite3.Row
        indexer.init_schema(conn)

        for summary in claude_source.scan_all_sessions():
            indexer.upsert_session(conn, summary)

        conn.commit()
        conn.close()
        print(f'Indexed sessions to {sqlite_path}')
    finally:
        if old_data_dir:
            os.environ['CLAUDE_DATA_DIR'] = old_data_dir
        else:
            os.environ.pop('CLAUDE_DATA_DIR', None)


def _resolve_port() -> int:
    """Resolve the fixture server port from Playwright environment variables.

    Returns:
        Port from BASE_URL, SESSION_BROWSER_PLAYWRIGHT_PORT, or the default.
    """
    port = int(os.environ.get('SESSION_BROWSER_PLAYWRIGHT_PORT') or DEFAULT_PORT)
    base_url_env = os.environ.get('BASE_URL', '')
    if base_url_env:
        parsed = urlparse(base_url_env)
        if parsed.port:
            port = parsed.port
    return port


def _copy_tree_contents(source_root: Path, destination_root: Path) -> None:
    """Copy direct children from one fixture directory into a destination.

    Args:
        source_root: Fixture directory whose children should be copied.
        destination_root: Temporary directory receiving fixture files.
    """
    for item in source_root.iterdir():
        destination = destination_root / item.name
        if item.is_dir():
            shutil.copytree(item, destination)
        else:
            shutil.copy2(item, destination)


def _merge_long_fixture(data_dir: Path) -> None:
    """Merge long-session fixture projects and history into the temp data dir.

    Args:
        data_dir: Temporary Claude data directory already populated with hifi fixtures.
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


def _prepare_fixture_data() -> tuple[Path, Path, Path]:
    """Create temporary fixture data and index directories for the server.

    Returns:
        Tuple of temporary root directory, index directory, and data directory.
    """
    tmpdir = Path(tempfile.mkdtemp(prefix='playwright_fixture_'))
    index_dir = tmpdir / 'index'
    index_dir.mkdir()
    data_dir = tmpdir / 'claude_data'
    data_dir.mkdir()
    _copy_tree_contents(FIXTURE_ROOT, data_dir)
    _merge_long_fixture(data_dir)
    return tmpdir, index_dir, data_dir


def _build_server_env(index_dir: Path, data_dir: Path, port: int) -> dict[str, str]:
    """Build the environment used by the fixture server process.

    Args:
        index_dir: Temporary index directory containing index.sqlite.
        data_dir: Temporary Claude data directory used as server input.
        port: Localhost port assigned to the fixture server.

    Returns:
        Environment mapping passed to subprocess.Popen.
    """
    env = os.environ.copy()
    env['PYTHONPATH'] = str(SB_ROOT / 'src')
    env['INDEX_DIR'] = str(index_dir)
    env['CLAUDE_DATA_DIR'] = str(data_dir)
    env['SERVER_HOST'] = '127.0.0.1'
    env['SERVER_PORT'] = str(port)
    env['SESSION_BROWSER_LOG_LEVEL'] = 'WARNING'
    env['PYTHONUNBUFFERED'] = '1'
    return env


def _wait_until_ready(base_url: str, proc: subprocess.Popen[bytes]) -> bool:
    """Poll fixture server endpoints until both session URLs are available.

    Args:
        base_url: Local server base URL including port.
        proc: Server subprocess, used only to stop polling if it exits early.

    Returns:
        True when dashboard and fixture sessions return HTTP 200 within timeout.
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


def _stop_process(proc: subprocess.Popen[bytes]) -> None:
    """Terminate the fixture server process if it is still running.

    Args:
        proc: Server subprocess created by main.
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


def main() -> None:
    """Start the fixture server and block until interrupted.

    The script is triggered by Playwright e2e setup or a developer terminal. It
    prints fixture URLs on success, returns via sys.exit(1) if readiness checks
    fail, and removes temporary data during signal, atexit, or normal cleanup.
    """
    port = _resolve_port()
    tmpdir, index_dir, data_dir = _prepare_fixture_data()
    sqlite_path = index_dir / 'index.sqlite'
    populate_index(data_dir, sqlite_path)

    env = _build_server_env(index_dir, data_dir, port)
    print(f'Starting fixture server on http://127.0.0.1:{port}')
    print(f'  Data dir: {data_dir}')
    print(f'  Index: {sqlite_path}')
    print('  Session URLs:')
    print(f'    http://127.0.0.1:{port}/sessions/claude_code/hifi-viz-session-001')
    print(f'    http://127.0.0.1:{port}/sessions/claude_code/long-session-001')
    print(f'  TMPDIR: {tmpdir}')

    proc = subprocess.Popen(
        [PYTHON_EXECUTABLE, '-m', 'session_browser', 'serve', '--allow-empty', '--no-scan'],
        cwd=SB_ROOT,
        env=env,
    )

    base_url = f'http://127.0.0.1:{port}'
    if not _wait_until_ready(base_url, proc):
        _stop_process(proc)
        shutil.rmtree(tmpdir, ignore_errors=True)
        print('ERROR: Server did not start within 15 seconds')
        sys.exit(1)

    print(f'Server ready at {base_url}')
    print('Press Ctrl+C to stop and clean up')

    def cleanup(signum: int | None = None, frame: FrameType | None = None) -> None:
        """Stop the server and delete temporary fixture data.

        Args:
            signum: Optional signal number supplied by signal handlers.
            frame: Optional interpreter frame supplied by signal handlers.
        """
        del signum, frame
        print(f'\nShutting down server (PID {proc.pid})...')
        _stop_process(proc)
        shutil.rmtree(tmpdir, ignore_errors=True)
        print('Cleaned up.')
        sys.exit(0)

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    def _atexit_cleanup() -> None:
        """Clean temp data when Python exits without receiving a signal."""
        _stop_process(proc)
        shutil.rmtree(tmpdir, ignore_errors=True)

    atexit.register(_atexit_cleanup)

    with suppress(ChildProcessError):
        proc.wait()
    cleanup()


if __name__ == '__main__':
    main()
