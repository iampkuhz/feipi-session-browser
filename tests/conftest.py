"""Session Browser 测试共享 pytest fixtures。"""
import os
import socket
import subprocess
import sys
import time
import shutil
import tempfile
import sqlite3

import pytest

SB_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ─── 共享 HTTP 辅助函数 ─────────────────────────────────────────────

import urllib.request
import urllib.error
import json


def _find_free_port() -> int:
    """在 localhost 上查找一个可用的 TCP 端口。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        return s.getsockname()[1]


def get_html(url: str) -> str:
    """从 url 获取 HTML 并返回解码后的文本。"""
    resp = urllib.request.urlopen(url, timeout=15)
    assert resp.status == 200
    return resp.read().decode("utf-8")


def get_json(url: str) -> dict:
    """从 url 获取 JSON 并返回解析后的字典。"""
    resp = urllib.request.urlopen(url, timeout=10)
    assert resp.status == 200
    content_type = resp.headers.get("Content-Type", "")
    assert "application/json" in content_type, f"Expected JSON, got {content_type}"
    return json.loads(resp.read().decode("utf-8"))


def _start_session_browser_server(env: dict, port: int) -> subprocess.Popen:
    """启动 session-browser 服务端进程。调用方负责清理。"""
    env = env.copy()
    env.setdefault("PYTHONPATH", os.path.join(SB_ROOT, "src"))
    env.setdefault("SERVER_HOST", "127.0.0.1")
    env["SERVER_PORT"] = str(port)
    env.setdefault("SESSION_BROWSER_LOG_LEVEL", "WARNING")
    return subprocess.Popen(
        [sys.executable, "-m", "session_browser", "serve", "--allow-empty", "--no-scan"],
        cwd=SB_ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def wait_for_server(port: int, timeout: float = 15.0) -> str:
    """等待 session-browser 服务端就绪。返回 base_url 或抛出异常。"""
    base_url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            resp = urllib.request.urlopen(f"{base_url}/dashboard", timeout=2)
            if resp.status == 200:
                return base_url
        except Exception:
            pass
        time.sleep(0.3)
    raise TimeoutError(f"Server on port {port} did not start within {timeout}s")


# ─── 本地测试索引服务端 fixture ────────────────────────────────────────────────
# 用于依赖真实 local-test-index 的测试（非合成 fixture）。

DEFAULT_TEST_INDEX = os.path.expanduser(
    "~/.local/share/feipi/session-browser/local-test-index/index.sqlite"
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


@pytest.fixture(scope="session")
def local_test_server():
    """使用本地测试索引启动 session-browser 服务端。

    Yields (base_url, agent, session_id)，如果找不到索引则 skip。
    所有需要真实 session 的测试共享此 fixture（scope=session = 全局单例服务端）。
    """
    index_dir = os.environ.get("SB_TEST_INDEX_DIR", os.path.dirname(DEFAULT_TEST_INDEX))
    index_file = os.path.join(index_dir, "index.sqlite")

    if not os.path.exists(index_file):
        try:
            for f in os.listdir(index_dir):
                if f.endswith(".sqlite"):
                    index_file = os.path.join(index_dir, f)
                    break
            else:
                pytest.skip("No test SQLite index found at " + index_dir)
        except FileNotFoundError:
            pytest.skip("No test SQLite index directory found at " + index_dir)

    test_session = _find_test_session_from_index(index_file)
    if test_session is None:
        pytest.skip("No sessions found in test index")

    agent, session_id = test_session
    port = _find_free_port()

    env = os.environ.copy()
    env["INDEX_DIR"] = index_dir
    env["PYTHONPATH"] = os.path.join(SB_ROOT, "src")

    proc = _start_session_browser_server(env, port)

    try:
        base_url = wait_for_server(port)
        yield base_url, agent, session_id
    finally:
        proc.terminate()
        proc.wait()


@pytest.fixture(scope="module")
def live_server_url():
    """启动 session-browser 服务端并返回其 URL。

    需要 SB_TEST_DB 环境变量指向有效的 index.db。
    未设置 SB_TEST_DB 或文件不存在时 skip。
    """
    db_path = os.environ.get("SB_TEST_DB")
    if not db_path or not os.path.exists(db_path):
        pytest.skip("SB_TEST_DB not set or file not found")

    port = _find_free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "session_browser", "--db", db_path, "--port", str(port)],
        cwd=SB_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # 等待服务端就绪
    for _ in range(20):
        try:
            import urllib.request
            urllib.request.urlopen(f"http://127.0.0.1:{port}/dashboard", timeout=1)
            break
        except Exception:
            time.sleep(0.5)
    else:
        proc.terminate()
        proc.wait()
        pytest.fail("Server did not start within 10 seconds")

    yield f"http://127.0.0.1:{port}"
    proc.terminate()
    proc.wait()


# ─── HIFI 视觉测试 fixture session ───────────────────────────────────────

FIXTURE_ROOT = os.path.join(SB_ROOT, "tests", "fixtures", "session_hifi_fixture")
HIFFI_SESSION_ID = "hifi-viz-session-001"
HIFFI_AGENT = "claude_code"
HIFFI_PROJECT = "test-hifi-project"

# ─── 长 session fixture（100 round，性能测试）────────────────────────

LONG_FIXTURE_ROOT = os.path.join(SB_ROOT, "tests", "fixtures", "session_hifi_long_fixture")
LONG_SESSION_ID = "long-session-001"
LONG_AGENT = "claude_code"
LONG_PROJECT = "test-hifi-project"


def _populate_index_from_fixture(fixture_dir: str, sqlite_path: str) -> str:
    """扫描 fixture CLAUDE_DATA_DIR 并写入 SQLite 索引。

    返回 session key (agent:session_id)。
    """
    sys.path.insert(0, os.path.join(SB_ROOT, "src"))
    import importlib

    # 在任何模块导入之前设置 CLAUDE_DATA_DIR
    old_data_dir = os.environ.get("CLAUDE_DATA_DIR", "")
    os.environ["CLAUDE_DATA_DIR"] = fixture_dir

    # 重新加载 config 及相关模块，使其拾取新的环境变量
    if "session_browser.config" in sys.modules:
        importlib.reload(sys.modules["session_browser.config"])
    for _mod in list(sys.modules):
        if _mod.startswith("session_browser.sources"):
            del sys.modules[_mod]

    try:
        from session_browser.index.indexer import (
            _get_connection, init_schema, upsert_session,
        )
        conn = sqlite3.connect(sqlite_path)
        conn.row_factory = sqlite3.Row
        init_schema(conn)

        from session_browser.sources.claude import scan_all_sessions
        for summary in scan_all_sessions():
            upsert_session(conn, summary)

        conn.commit()
        session_key = f"{HIFFI_AGENT}:{HIFFI_SESSION_ID}"
        row = conn.execute(
            "SELECT agent, session_id FROM sessions WHERE session_key = ?",
            (session_key,),
        ).fetchone()
        conn.close()
        return session_key if row else None
    finally:
        if old_data_dir:
            os.environ["CLAUDE_DATA_DIR"] = old_data_dir
        else:
            os.environ.pop("CLAUDE_DATA_DIR", None)


@pytest.fixture(scope="module")
def hifi_fixture_session():
    """为 HIFI 视觉测试构建确定性 fixture session。

    从 tests/fixtures/session_hifi_fixture/ 创建临时 CLAUDE_DATA_DIR，
    填充 SQLite 索引，启动服务端，Yields (base_url, agent, session_id)。

    退出时清理所有资源。
    """
    import urllib.request

    tmpdir = tempfile.mkdtemp(prefix="hifi_fixture_")
    index_dir = os.path.join(tmpdir, "index")
    os.makedirs(index_dir)
    sqlite_path = os.path.join(index_dir, "index.sqlite")

    # 将 fixture 数据复制到临时目录（CLAUDE_DATA_DIR 布局）
    data_dir = os.path.join(tmpdir, "claude_data")
    shutil.copytree(FIXTURE_ROOT, data_dir)

    try:
        session_key = _populate_index_from_fixture(data_dir, sqlite_path)
        if session_key is None:
            pytest.fail("Fixture session not indexed — check JSONL fixture")

        env = os.environ.copy()
        env["PYTHONPATH"] = os.path.join(SB_ROOT, "src")
        env["INDEX_DIR"] = index_dir
        env["CLAUDE_DATA_DIR"] = data_dir
        env["SERVER_HOST"] = "127.0.0.1"
        port = _find_free_port()
        env["SERVER_PORT"] = str(port)
        env["SESSION_BROWSER_LOG_LEVEL"] = "WARNING"

        proc = subprocess.Popen(
            [sys.executable, "-m", "session_browser", "serve", "--allow-empty", "--no-scan"],
            cwd=SB_ROOT,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        base_url = f"http://127.0.0.1:{port}"
        for _ in range(30):
            try:
                resp = urllib.request.urlopen(f"{base_url}/dashboard", timeout=2)
                if resp.status == 200:
                    break
            except Exception:
                time.sleep(0.5)
        else:
            proc.terminate()
            proc.wait()
            pytest.fail("Server did not start within 15 seconds for fixture session")

        yield base_url, HIFFI_AGENT, HIFFI_SESSION_ID

        proc.terminate()
        proc.wait()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ─── 长 session fixture（100 round，性能测试）────────────────────────

@pytest.fixture(scope="module")
def long_fixture_session():
    """为性能测试构建 100-round 合成 session。

    从 tests/fixtures/session_hifi_long_fixture/ 创建临时 CLAUDE_DATA_DIR，
    填充 SQLite 索引，启动服务端，Yields (base_url, agent, session_id)。

    退出时清理所有资源。
    """
    import urllib.request

    tmpdir = tempfile.mkdtemp(prefix="long_fixture_")
    index_dir = os.path.join(tmpdir, "index")
    os.makedirs(index_dir)
    sqlite_path = os.path.join(index_dir, "index.sqlite")

    # 将 fixture 数据复制到临时目录（CLAUDE_DATA_DIR 布局）
    data_dir = os.path.join(tmpdir, "claude_data")
    shutil.copytree(LONG_FIXTURE_ROOT, data_dir)

    try:
        # 复用相同的索引逻辑，仅常量不同
        sys.path.insert(0, os.path.join(SB_ROOT, "src"))
        import importlib

        old_data_dir = os.environ.get("CLAUDE_DATA_DIR", "")
        os.environ["CLAUDE_DATA_DIR"] = data_dir

        if "session_browser.config" in sys.modules:
            importlib.reload(sys.modules["session_browser.config"])
        for _mod in list(sys.modules):
            if _mod.startswith("session_browser.sources"):
                del sys.modules[_mod]

        try:
            from session_browser.index.indexer import (
                _get_connection, init_schema, upsert_session,
            )
            conn = sqlite3.connect(sqlite_path)
            conn.row_factory = sqlite3.Row
            init_schema(conn)

            from session_browser.sources.claude import scan_all_sessions
            for summary in scan_all_sessions():
                upsert_session(conn, summary)

            conn.commit()
            session_key = f"{LONG_AGENT}:{LONG_SESSION_ID}"
            row = conn.execute(
                "SELECT agent, session_id FROM sessions WHERE session_key = ?",
                (session_key,),
            ).fetchone()
            conn.close()
            if row is None:
                pytest.fail("Long fixture session not indexed — check JSONL fixture")
        finally:
            if old_data_dir:
                os.environ["CLAUDE_DATA_DIR"] = old_data_dir
            else:
                os.environ.pop("CLAUDE_DATA_DIR", None)

        env = os.environ.copy()
        env["PYTHONPATH"] = os.path.join(SB_ROOT, "src")
        env["INDEX_DIR"] = index_dir
        env["CLAUDE_DATA_DIR"] = data_dir
        env["SERVER_HOST"] = "127.0.0.1"
        port = _find_free_port()
        env["SERVER_PORT"] = str(port)
        env["SESSION_BROWSER_LOG_LEVEL"] = "WARNING"

        proc = subprocess.Popen(
            [sys.executable, "-m", "session_browser", "serve", "--allow-empty", "--no-scan"],
            cwd=SB_ROOT,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        base_url = f"http://127.0.0.1:{port}"
        for _ in range(30):
            try:
                resp = urllib.request.urlopen(f"{base_url}/dashboard", timeout=2)
                if resp.status == 200:
                    break
            except Exception:
                time.sleep(0.5)
        else:
            proc.terminate()
            proc.wait()
            pytest.fail("Server did not start within 15 seconds for long fixture session")

        yield base_url, LONG_AGENT, LONG_SESSION_ID

        proc.terminate()
        proc.wait()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
