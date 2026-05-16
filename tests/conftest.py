"""Shared pytest fixtures for session-browser tests."""
import os
import subprocess
import sys
import time

import pytest

SB_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="module")
def live_server_url():
    """Start a session-browser server and return its URL.

    Requires SB_TEST_DB environment variable pointing to a valid index.db.
    Skips if SB_TEST_DB is not set or the file does not exist.
    """
    db_path = os.environ.get("SB_TEST_DB")
    if not db_path or not os.path.exists(db_path):
        pytest.skip("SB_TEST_DB not set or file not found")

    port = 18899
    proc = subprocess.Popen(
        [sys.executable, "-m", "session_browser", "--db", db_path, "--port", str(port)],
        cwd=SB_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # Wait for server to be ready
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
