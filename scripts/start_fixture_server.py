#!/usr/bin/env python3
"""Start a fixture session server for Playwright e2e tests.

Usage:
    # In terminal 1 (keeps running):
    python scripts/start_fixture_server.py

    # In terminal 2:
    PW_SESSION_URL=http://127.0.0.1:18999/sessions/claude_code/hifi-viz-session-001 npx playwright test

    # For long session tests:
    PW_LONG_SESSION_URL=http://127.0.0.1:18999/sessions/claude_code/long-session-001 npx playwright test --grep "Long Session"
"""
import os
import sys
import shutil
import tempfile
import subprocess
import time
import signal

SB_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE_ROOT = os.path.join(SB_ROOT, "tests", "fixtures", "session_hifi_fixture")
LONG_FIXTURE_ROOT = os.path.join(SB_ROOT, "tests", "fixtures", "session_hifi_long_fixture")
PORT = 18999
VENV_PYTHON = os.path.join(SB_ROOT, ".venv", "bin", "python")


def populate_index(claude_data_dir, sqlite_path):
    """Index fixture sessions into SQLite."""
    sys.path.insert(0, os.path.join(SB_ROOT, "src"))
    import importlib

    old_data_dir = os.environ.get("CLAUDE_DATA_DIR", "")
    os.environ["CLAUDE_DATA_DIR"] = claude_data_dir

    if "session_browser.config" in sys.modules:
        importlib.reload(sys.modules["session_browser.config"])
    for mod in list(sys.modules):
        if mod.startswith("session_browser.sources"):
            del sys.modules[mod]

    try:
        from session_browser.index.indexer import init_schema, upsert_session
        import sqlite3

        conn = sqlite3.connect(sqlite_path)
        conn.row_factory = sqlite3.Row
        init_schema(conn)

        from session_browser.sources.claude import scan_all_sessions
        for summary in scan_all_sessions():
            upsert_session(conn, summary)

        conn.commit()
        conn.close()
        print(f"Indexed sessions to {sqlite_path}")
    finally:
        if old_data_dir:
            os.environ["CLAUDE_DATA_DIR"] = old_data_dir
        else:
            os.environ.pop("CLAUDE_DATA_DIR", None)


def main():
    tmpdir = tempfile.mkdtemp(prefix="playwright_fixture_")
    index_dir = os.path.join(tmpdir, "index")
    os.makedirs(index_dir)

    # Merge both fixtures into one data dir
    data_dir = os.path.join(tmpdir, "claude_data")
    os.makedirs(data_dir)

    # Copy hifi fixture
    for item in os.listdir(FIXTURE_ROOT):
        src = os.path.join(FIXTURE_ROOT, item)
        dst = os.path.join(data_dir, item)
        if os.path.isdir(src):
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)

    # Copy long fixture projects (merge into existing projects dir)
    long_projects = os.path.join(LONG_FIXTURE_ROOT, "projects")
    if os.path.exists(long_projects):
        projects_dir = os.path.join(data_dir, "projects")
        for item in os.listdir(long_projects):
            src = os.path.join(long_projects, item)
            dst = os.path.join(projects_dir, item)
            if os.path.isdir(src):
                if os.path.exists(dst):
                    # Merge: copy files from long fixture into existing project dir
                    for subitem in os.listdir(src):
                        sub_src = os.path.join(src, subitem)
                        sub_dst = os.path.join(dst, subitem)
                        if os.path.isdir(sub_src):
                            shutil.copytree(sub_src, sub_dst, dirs_exist_ok=True)
                        else:
                            shutil.copy2(sub_src, sub_dst)
                else:
                    shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)

    # Copy long fixture history (merge with existing)
    long_history = os.path.join(LONG_FIXTURE_ROOT, "history.jsonl")
    if os.path.exists(long_history):
        history_file = os.path.join(data_dir, "history.jsonl")
        with open(long_history) as f:
            long_entries = f.read()
        with open(history_file, "a") as f:
            f.write(long_entries)

    sqlite_path = os.path.join(index_dir, "index.sqlite")
    populate_index(data_dir, sqlite_path)

    env = os.environ.copy()
    env["PYTHONPATH"] = os.path.join(SB_ROOT, "src")
    env["INDEX_DIR"] = index_dir
    env["CLAUDE_DATA_DIR"] = data_dir
    env["SERVER_HOST"] = "127.0.0.1"
    env["SERVER_PORT"] = str(PORT)
    env["SESSION_BROWSER_LOG_LEVEL"] = "WARNING"
    env["PYTHONUNBUFFERED"] = "1"

    print(f"Starting fixture server on http://127.0.0.1:{PORT}")
    print(f"  Data dir: {data_dir}")
    print(f"  Index: {sqlite_path}")
    print(f"  Session URLs:")
    print(f"    http://127.0.0.1:{PORT}/sessions/claude_code/hifi-viz-session-001")
    print(f"    http://127.0.0.1:{PORT}/sessions/claude_code/long-session-001")
    print(f"  TMPDIR: {tmpdir}")

    proc = subprocess.Popen(
        [VENV_PYTHON, "-m", "session_browser", "serve", "--allow-empty", "--no-scan"],
        cwd=SB_ROOT,
        env=env,
    )

    # Wait for server to start
    import urllib.request
    base_url = f"http://127.0.0.1:{PORT}"
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
        print("ERROR: Server did not start within 15 seconds")
        sys.exit(1)

    print(f"Server ready at {base_url}")
    print(f"Press Ctrl+C to stop and clean up")

    def cleanup(signum=None, frame=None):
        print(f"\nShutting down server (PID {proc.pid})...")
        proc.terminate()
        proc.wait()
        shutil.rmtree(tmpdir, ignore_errors=True)
        print("Cleaned up.")
        sys.exit(0)

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    # Wait for the server process
    proc.wait()
    cleanup()


if __name__ == "__main__":
    main()
