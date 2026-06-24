"""Session Browser 测试共享 pytest fixtures。"""

import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time

import pytest

SB_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SKIP_REPORTS_ATTR = '_session_browser_forbidden_skip_reports'
_PYTEST_CONFIG = None


def pytest_configure(config):
    """Track skipped pytest reports so selected/full runs cannot pass with skips."""
    global _PYTEST_CONFIG
    _PYTEST_CONFIG = config
    setattr(config, _SKIP_REPORTS_ATTR, [])


def _record_forbidden_skip(config, report) -> None:
    if not getattr(report, 'skipped', False):
        return
    reports = getattr(config, _SKIP_REPORTS_ATTR, None)
    if reports is None:
        reports = []
        setattr(config, _SKIP_REPORTS_ATTR, reports)
    location = getattr(report, 'location', None)
    if location:
        file_name, line_no, _test_name = location
        loc = f'{file_name}:{line_no + 1}'
    else:
        loc = getattr(report, 'nodeid', '<unknown>')
    reports.append(
        {
            'nodeid': getattr(report, 'nodeid', '<unknown>'),
            'when': getattr(report, 'when', 'collect'),
            'location': loc,
        }
    )


def pytest_runtest_logreport(report):
    config = getattr(report, 'config', None) or _PYTEST_CONFIG
    if config is not None:
        _record_forbidden_skip(config, report)


def pytest_collectreport(report):
    config = getattr(report, 'config', None) or _PYTEST_CONFIG
    if config is not None:
        _record_forbidden_skip(config, report)


def pytest_sessionfinish(session, exitstatus):
    reports = getattr(session.config, _SKIP_REPORTS_ATTR, [])
    if not reports:
        return
    terminal = session.config.pluginmanager.get_plugin('terminalreporter')
    lines = [
        'pytest skipped outcomes are forbidden. Use deterministic fixtures, explicit assertions, or target mapping instead.',
        f'forbidden skipped reports: {len(reports)}',
    ]
    for item in reports[:20]:
        lines.append(f' - {item["nodeid"]} [{item["when"]}] at {item["location"]}')
    if len(reports) > 20:
        lines.append(f' - ... {len(reports) - 20} more')
    if terminal:
        terminal.write_sep('=', 'no test skips enforcement')
        for line in lines:
            terminal.write_line(line)
    else:
        print('\n'.join(lines), file=sys.stderr)
    session.exitstatus = pytest.ExitCode.TESTS_FAILED


# ─── 共享 HTTP 辅助函数 ─────────────────────────────────────────────

import json
import urllib.error
import urllib.request


def _find_free_port() -> int:
    """在 localhost 上查找一个可用的 TCP 端口。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        s.listen(1)
        return s.getsockname()[1]


def get_html(url: str) -> str:
    """从 url 获取 HTML 并返回解码后的文本。"""
    resp = urllib.request.urlopen(url, timeout=15)
    assert resp.status == 200
    return resp.read().decode('utf-8')


def get_json(url: str) -> dict:
    """从 url 获取 JSON 并返回解析后的字典。"""
    resp = urllib.request.urlopen(url, timeout=10)
    assert resp.status == 200
    content_type = resp.headers.get('Content-Type', '')
    assert 'application/json' in content_type, f'Expected JSON, got {content_type}'
    return json.loads(resp.read().decode('utf-8'))


@pytest.fixture
def page():
    """Minimal Playwright page fixture for tests that need browser DOM access."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        try:
            yield page
        finally:
            browser.close()


# 测试 fixture 内联服务脚本：绕过 CLI，直接使用 create_server。
# 生产 serve/stop 已由 Java launcher 接管（WEB-110）。
_FIXTURE_SERVER_SCRIPT = (
    'import argparse, sys; sys.path.insert(0, "src"); '
    'from session_browser.web.routes import create_server; '
    'p = argparse.ArgumentParser(); p.add_argument("--port", type=int, default=0); '
    'args = p.parse_args(); '
    's = create_server(port=args.port); s.serve_forever()'
)


def _start_session_browser_server(env: dict, port: int) -> subprocess.Popen:
    """启动 session-browser 测试服务端进程。调用方负责清理。

    注意：生产 serve/stop 已由 Java launcher 接管（WEB-110）。
    此函数仅用于 Python 侧测试 fixture，直接使用 create_server 绕过 CLI。
    """
    env = env.copy()
    env.setdefault('PYTHONPATH', os.path.join(SB_ROOT, 'src'))
    env.setdefault('SERVER_HOST', '127.0.0.1')
    env['SERVER_PORT'] = str(port)
    env.setdefault('SESSION_BROWSER_LOG_LEVEL', 'WARNING')
    return subprocess.Popen(
        [sys.executable, '-c', _FIXTURE_SERVER_SCRIPT, '--port', str(port)],
        cwd=SB_ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def wait_for_server(port: int, timeout: float = 15.0) -> str:
    """等待 session-browser 服务端就绪。返回 base_url 或抛出异常。"""
    base_url = f'http://127.0.0.1:{port}'
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            resp = urllib.request.urlopen(f'{base_url}/dashboard', timeout=2)
            if resp.status == 200:
                return base_url
        except Exception:
            pass
        time.sleep(0.3)
    raise TimeoutError(f'Server on port {port} did not start within {timeout}s')


# ─── 本地测试索引服务端 fixture ────────────────────────────────────────────────
# 用于依赖真实 local-test-index 的测试（非合成 fixture）。

DEFAULT_TEST_INDEX = os.path.expanduser(
    '~/.local/share/feipi/session-browser/local-test-index/index.sqlite'
)


def _find_test_session_from_index(index_path: str) -> tuple[str, str] | None:
    """从测试索引中返回 (agent, session_id)。"""
    import sqlite3

    if not os.path.exists(index_path):
        return None
    conn = sqlite3.connect(index_path)
    row = conn.execute(
        "SELECT agent, session_id FROM sessions WHERE title != '' LIMIT 1"
    ).fetchone()
    conn.close()
    return row


@pytest.fixture(scope='session')
def local_test_server():
    """使用本地测试索引启动 session-browser 服务端。

    Yields (base_url, agent, session_id)。找不到本地索引时使用仓库内
    deterministic HIFI fixture，避免环境缺失导致测试跳过。
    所有需要真实 session 的测试共享此 fixture（scope=session = 全局单例服务端）。
    """
    explicit_index_dir = os.environ.get('SB_TEST_INDEX_DIR')
    index_dir = explicit_index_dir or os.path.dirname(DEFAULT_TEST_INDEX)
    index_file = os.path.join(index_dir, 'index.sqlite')

    test_session = None
    if explicit_index_dir and not os.path.exists(index_file):
        try:
            for f in os.listdir(index_dir):
                if f.endswith('.sqlite'):
                    index_file = os.path.join(index_dir, f)
                    break
        except FileNotFoundError:
            pass

    if explicit_index_dir and os.path.exists(index_file):
        test_session = _find_test_session_from_index(index_file)

    if test_session is None:
        proc, tmpdir, base_url, agent, session_id = _start_fixture_session_server(
            FIXTURE_ROOT,
            HIFFI_AGENT,
            HIFFI_SESSION_ID,
            'local_test_fixture_',
        )
        try:
            yield base_url, agent, session_id
        finally:
            proc.terminate()
            proc.wait()
            shutil.rmtree(tmpdir, ignore_errors=True)
        return

    agent, session_id = test_session
    port = _find_free_port()

    env = os.environ.copy()
    env['INDEX_DIR'] = index_dir
    env['PYTHONPATH'] = os.path.join(SB_ROOT, 'src')

    proc = _start_session_browser_server(env, port)

    try:
        base_url = wait_for_server(port)
        yield base_url, agent, session_id
    finally:
        proc.terminate()
        proc.wait()


@pytest.fixture(scope='module')
def live_server_url():
    """启动 session-browser 服务端并返回其 URL。

    SB_TEST_DB 指向有效 index.db 时使用该数据库；否则使用仓库内
    deterministic HIFI fixture，避免本地环境缺失导致测试跳过。
    """
    db_path = os.environ.get('SB_TEST_DB')
    if not db_path or not os.path.exists(db_path):
        proc, tmpdir, base_url, _agent, _session_id = _start_fixture_session_server(
            FIXTURE_ROOT,
            HIFFI_AGENT,
            HIFFI_SESSION_ID,
            'live_server_fixture_',
        )
        try:
            yield base_url
        finally:
            proc.terminate()
            proc.wait()
            shutil.rmtree(tmpdir, ignore_errors=True)
        return

    port = _find_free_port()
    proc = subprocess.Popen(
        [sys.executable, '-m', 'session_browser', '--db', db_path, '--port', str(port)],
        cwd=SB_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # 等待服务端就绪
    for _ in range(20):
        try:
            import urllib.request

            urllib.request.urlopen(f'http://127.0.0.1:{port}/dashboard', timeout=1)
            break
        except Exception:
            time.sleep(0.5)
    else:
        proc.terminate()
        proc.wait()
        pytest.fail('Server did not start within 10 seconds')

    yield f'http://127.0.0.1:{port}'
    proc.terminate()
    proc.wait()


# ─── HIFI 视觉测试 fixture session ───────────────────────────────────────

FIXTURE_ROOT = os.path.join(SB_ROOT, 'tests', 'fixtures', 'session_hifi_fixture')
HIFFI_SESSION_ID = 'hifi-viz-session-001'
HIFFI_AGENT = 'claude_code'
HIFFI_PROJECT = 'test-hifi-project'

# ─── 长 session fixture（100 round，性能测试）────────────────────────

LONG_FIXTURE_ROOT = os.path.join(SB_ROOT, 'tests', 'fixtures', 'session_hifi_long_fixture')
LONG_SESSION_ID = 'long-session-001'
LONG_AGENT = 'claude_code'
LONG_PROJECT = 'test-hifi-project'


def _populate_index_from_fixture(
    fixture_dir: str,
    sqlite_path: str,
    expected_agent: str = HIFFI_AGENT,
    expected_session_id: str = HIFFI_SESSION_ID,
) -> str:
    """扫描 fixture CLAUDE_DATA_DIR 并写入 SQLite 索引。

    返回 session key (agent:session_id)。
    """
    sys.path.insert(0, os.path.join(SB_ROOT, 'src'))
    import importlib

    # 在任何模块导入之前设置 CLAUDE_DATA_DIR
    old_data_dir = os.environ.get('CLAUDE_DATA_DIR', '')
    os.environ['CLAUDE_DATA_DIR'] = fixture_dir

    # 重新加载 config 及相关模块，使其拾取新的环境变量
    if 'session_browser.config' in sys.modules:
        importlib.reload(sys.modules['session_browser.config'])
    for _mod in list(sys.modules):
        if _mod.startswith('session_browser.sources'):
            del sys.modules[_mod]

    try:
        from tests.index._test_db_utils import (  # noqa: PLC0415
            init_test_schema,
            insert_test_session,
        )

        conn = sqlite3.connect(sqlite_path)
        conn.row_factory = sqlite3.Row
        init_test_schema(conn)

        from session_browser.sources.claude import scan_all_sessions

        for summary in scan_all_sessions():
            insert_test_session(conn, summary)

        conn.commit()
        session_key = f'{expected_agent}:{expected_session_id}'
        row = conn.execute(
            'SELECT agent, session_id FROM sessions WHERE session_key = ?',
            (session_key,),
        ).fetchone()
        conn.close()
        return session_key if row else None
    finally:
        if old_data_dir:
            os.environ['CLAUDE_DATA_DIR'] = old_data_dir
        else:
            os.environ.pop('CLAUDE_DATA_DIR', None)


def _start_fixture_session_server(
    fixture_root: str,
    agent: str,
    session_id: str,
    tmp_prefix: str,
) -> tuple[subprocess.Popen, str, str, str, str]:
    """Create a deterministic fixture index and start a local web server."""
    tmpdir = tempfile.mkdtemp(prefix=tmp_prefix)
    index_dir = os.path.join(tmpdir, 'index')
    os.makedirs(index_dir)
    sqlite_path = os.path.join(index_dir, 'index.sqlite')
    data_dir = os.path.join(tmpdir, 'claude_data')

    try:
        shutil.copytree(fixture_root, data_dir)
        session_key = _populate_index_from_fixture(
            data_dir,
            sqlite_path,
            expected_agent=agent,
            expected_session_id=session_id,
        )
        if session_key is None:
            pytest.fail(f'Fixture session {agent}:{session_id} not indexed')

        env = os.environ.copy()
        env['PYTHONPATH'] = os.path.join(SB_ROOT, 'src')
        env['INDEX_DIR'] = index_dir
        env['CLAUDE_DATA_DIR'] = data_dir
        env['SERVER_HOST'] = '127.0.0.1'
        port = _find_free_port()
        env['SERVER_PORT'] = str(port)
        env['SESSION_BROWSER_LOG_LEVEL'] = 'WARNING'

        proc = subprocess.Popen(
            [sys.executable, '-c', _FIXTURE_SERVER_SCRIPT, '--port', str(port)],
            cwd=SB_ROOT,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        try:
            base_url = wait_for_server(port)
        except Exception:
            proc.terminate()
            proc.wait()
            raise

        return proc, tmpdir, base_url, agent, session_id
    except Exception:
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise


@pytest.fixture(scope='module')
def hifi_fixture_session():
    """为 HIFI 视觉测试构建确定性 fixture session。

    从 tests/fixtures/session_hifi_fixture/ 创建临时 CLAUDE_DATA_DIR，
    填充 SQLite 索引，启动服务端，Yields (base_url, agent, session_id)。

    退出时清理所有资源。
    """
    import urllib.request

    tmpdir = tempfile.mkdtemp(prefix='hifi_fixture_')
    index_dir = os.path.join(tmpdir, 'index')
    os.makedirs(index_dir)
    sqlite_path = os.path.join(index_dir, 'index.sqlite')

    # 将 fixture 数据复制到临时目录（CLAUDE_DATA_DIR 布局）
    data_dir = os.path.join(tmpdir, 'claude_data')
    shutil.copytree(FIXTURE_ROOT, data_dir)

    try:
        session_key = _populate_index_from_fixture(data_dir, sqlite_path)
        if session_key is None:
            pytest.fail('Fixture session not indexed — check JSONL fixture')

        env = os.environ.copy()
        env['PYTHONPATH'] = os.path.join(SB_ROOT, 'src')
        env['INDEX_DIR'] = index_dir
        env['CLAUDE_DATA_DIR'] = data_dir
        env['SERVER_HOST'] = '127.0.0.1'
        port = _find_free_port()
        env['SERVER_PORT'] = str(port)
        env['SESSION_BROWSER_LOG_LEVEL'] = 'WARNING'

        proc = subprocess.Popen(
            [sys.executable, '-c', _FIXTURE_SERVER_SCRIPT, '--port', str(port)],
            cwd=SB_ROOT,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        base_url = f'http://127.0.0.1:{port}'
        for _ in range(30):
            try:
                resp = urllib.request.urlopen(f'{base_url}/dashboard', timeout=2)
                if resp.status == 200:
                    break
            except Exception:
                time.sleep(0.5)
        else:
            proc.terminate()
            proc.wait()
            pytest.fail('Server did not start within 15 seconds for fixture session')

        yield base_url, HIFFI_AGENT, HIFFI_SESSION_ID

        proc.terminate()
        proc.wait()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ─── 长 session fixture（100 round，性能测试）────────────────────────


@pytest.fixture(scope='module')
def long_fixture_session():
    """为性能测试构建 100-round 合成 session。

    从 tests/fixtures/session_hifi_long_fixture/ 创建临时 CLAUDE_DATA_DIR，
    填充 SQLite 索引，启动服务端，Yields (base_url, agent, session_id)。

    退出时清理所有资源。
    """
    import urllib.request

    tmpdir = tempfile.mkdtemp(prefix='long_fixture_')
    index_dir = os.path.join(tmpdir, 'index')
    os.makedirs(index_dir)
    sqlite_path = os.path.join(index_dir, 'index.sqlite')

    # 将 fixture 数据复制到临时目录（CLAUDE_DATA_DIR 布局）
    data_dir = os.path.join(tmpdir, 'claude_data')
    shutil.copytree(LONG_FIXTURE_ROOT, data_dir)

    try:
        # 复用相同的索引逻辑，仅常量不同
        sys.path.insert(0, os.path.join(SB_ROOT, 'src'))
        import importlib

        old_data_dir = os.environ.get('CLAUDE_DATA_DIR', '')
        os.environ['CLAUDE_DATA_DIR'] = data_dir

        if 'session_browser.config' in sys.modules:
            importlib.reload(sys.modules['session_browser.config'])
        for _mod in list(sys.modules):
            if _mod.startswith('session_browser.sources'):
                del sys.modules[_mod]

        try:
            from tests.index._test_db_utils import (  # noqa: PLC0415
                init_test_schema,
                insert_test_session,
            )

            conn = sqlite3.connect(sqlite_path)
            conn.row_factory = sqlite3.Row
            init_test_schema(conn)

            from session_browser.sources.claude import scan_all_sessions

            for summary in scan_all_sessions():
                insert_test_session(conn, summary)

            conn.commit()
            session_key = f'{LONG_AGENT}:{LONG_SESSION_ID}'
            row = conn.execute(
                'SELECT agent, session_id FROM sessions WHERE session_key = ?',
                (session_key,),
            ).fetchone()
            conn.close()
            if row is None:
                pytest.fail('Long fixture session not indexed — check JSONL fixture')
        finally:
            if old_data_dir:
                os.environ['CLAUDE_DATA_DIR'] = old_data_dir
            else:
                os.environ.pop('CLAUDE_DATA_DIR', None)

        env = os.environ.copy()
        env['PYTHONPATH'] = os.path.join(SB_ROOT, 'src')
        env['INDEX_DIR'] = index_dir
        env['CLAUDE_DATA_DIR'] = data_dir
        env['SERVER_HOST'] = '127.0.0.1'
        port = _find_free_port()
        env['SERVER_PORT'] = str(port)
        env['SESSION_BROWSER_LOG_LEVEL'] = 'WARNING'

        proc = subprocess.Popen(
            [sys.executable, '-c', _FIXTURE_SERVER_SCRIPT, '--port', str(port)],
            cwd=SB_ROOT,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        base_url = f'http://127.0.0.1:{port}'
        for _ in range(30):
            try:
                resp = urllib.request.urlopen(f'{base_url}/dashboard', timeout=2)
                if resp.status == 200:
                    break
            except Exception:
                time.sleep(0.5)
        else:
            proc.terminate()
            proc.wait()
            pytest.fail('Server did not start within 15 seconds for long fixture session')

        yield base_url, LONG_AGENT, LONG_SESSION_ID

        proc.terminate()
        proc.wait()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
