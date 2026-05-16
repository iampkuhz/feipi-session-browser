"""CLI entry point for session-browser.

Usage:
    python -m session_browser scan        # Full scan
    python -m session_browser scan --incremental   # Incremental scan
    python -m session_browser serve       # Start web server
    python -m session_browser serve --port 18999
    python -m session_browser stop        # Stop web server

Environment variables:
    CLAUDE_DATA_DIR  - Claude Code data directory (default: ~/.claude)
    CODEX_DATA_DIR   - Codex data directory (default: ~/.codex)
    INDEX_DIR        - Index storage directory (default: ~/.local/share/feipi/session-browser/local-test-index)
    SERVER_HOST      - Bind address (default: 127.0.0.1)
    SERVER_PORT      - Server port (default: 18999)
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import subprocess
import sys
import threading
import time

from session_browser.config import (
    CLAUDE_DATA_DIR,
    CODEX_DATA_DIR,
    INDEX_DIR,
    QODER_DATA_DIR,
    SERVER_HOST,
    SERVER_PORT,
    SESSION_BROWSER_LOG_LEVEL,
    SESSION_BROWSER_VERSION,
)


logger = logging.getLogger("session_browser")


def configure_logging(level: str | None = None) -> None:
    """Configure process-wide logging for foreground and container runs."""
    raw_level = (level or SESSION_BROWSER_LOG_LEVEL or "INFO").upper()
    log_level = getattr(logging, raw_level, logging.INFO)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        force=True,
    )
    logging.captureWarnings(True)
    for noisy_logger in ("markdown_it", "PIL"):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)
    logger.debug("Logging configured at %s", logging.getLevelName(log_level))


def _truthy_env(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _run_command(
    cmd: list[str],
    *,
    timeout: float,
) -> subprocess.CompletedProcess[str]:
    """Run a short command and clean up its process group on timeout."""
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
            proc.communicate(timeout=3)
        except ProcessLookupError:
            pass
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.communicate()
        raise subprocess.TimeoutExpired(
            cmd,
            timeout,
            output=exc.output,
            stderr=exc.stderr,
        ) from exc

    return subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)


def _find_running_scan_pid() -> int | None:
    """Find PID of a running 'session_browser scan' process (excluding self)."""
    my_pid = os.getpid()
    try:
        result = subprocess.run(
            ["ps", "aux"],
            capture_output=True, text=True, timeout=5,
        )
        for line in result.stdout.splitlines():
            if "session_browser" in line and " scan" in line and str(my_pid) not in line.split()[1:2]:
                parts = line.split()
                if len(parts) >= 2:
                    try:
                        pid = int(parts[1])
                        if pid != my_pid:
                            return pid
                    except ValueError:
                        pass
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


def _kill_process(pid: int) -> bool:
    """Try to kill a process, return True if successful."""
    try:
        os.kill(pid, signal.SIGTERM)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        try:
            os.kill(pid, signal.SIGKILL)
            return True
        except (ProcessLookupError, PermissionError):
            return False


def cmd_scan(args: argparse.Namespace) -> None:
    """Run a full or incremental scan."""
    from session_browser.index.indexer import full_scan, incremental_scan, init_schema, _get_connection

    # Check if a scan is already running
    force = getattr(args, "force", False)
    scan_pid = _find_running_scan_pid()
    if scan_pid is not None:
        logger.warning("A scan process is already running: pid=%s", scan_pid)
        if force:
            logger.warning("--force: killing existing scan automatically")
        else:
            try:
                answer = input("Kill it and restart? [y/N]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                answer = "n"
        if force or answer in ("y", "yes"):
            if _kill_process(scan_pid):
                logger.warning("Killed scan process pid=%s; waiting for exit", scan_pid)
                time.sleep(1)
            else:
                logger.error("Failed to kill scan process pid=%s; proceeding anyway", scan_pid)
        else:
            print("Aborted.")
            sys.exit(0)

    conn = _get_connection()

    agent = args.agent if hasattr(args, 'agent') else None
    label = f" ({agent})" if agent else ""

    if args.incremental:
        # Only create tables if they don't exist; don't drop existing data
        _ensure_schema_exists(conn)
        print(f"Starting incremental scan{label}...")
        start = time.time()
        result = incremental_scan(conn, verbose=True, agent=agent)
        elapsed = time.time() - start
        print(f"\nIncremental scan complete in {elapsed:.1f}s")
        print(f"  Updated Claude: {result['claude_count']} sessions")
        print(f"  Updated Codex:  {result['codex_count']} sessions")
        if 'qoder_count' in result:
            print(f"  Updated Qoder:  {result['qoder_count']} sessions")
        print(f"  Skipped:        {result['skipped']} sessions")
        print(f"  Total updated:  {result['total']} sessions")
    else:
        init_schema(conn)
        print(f"Starting full scan{label}...")
        start = time.time()
        result = full_scan(conn, verbose=True, agent=agent)
        elapsed = time.time() - start
        print(f"\nScan complete in {elapsed:.1f}s")
        print(f"  Claude Code: {result['claude_count']} sessions")
        print(f"  Codex:       {result['codex_count']} sessions")
        if 'qoder_count' in result:
            print(f"  Qoder:       {result['qoder_count']} sessions")
        print(f"  Total:       {result['total']} sessions")

    conn.close()


def _migrate_model_execution_seconds(conn) -> None:
    """Add model_execution_seconds column if it doesn't exist."""
    try:
        columns = [r[0] for r in conn.execute("PRAGMA table_info(sessions)").fetchall()]
        if "model_execution_seconds" not in columns:
            conn.execute(
                "ALTER TABLE sessions ADD COLUMN model_execution_seconds REAL NOT NULL DEFAULT 0"
            )
            conn.commit()
    except Exception:
        pass


def _migrate_tool_execution_seconds(conn) -> None:
    """Add tool_execution_seconds column if it doesn't exist."""
    try:
        columns = [r[0] for r in conn.execute("PRAGMA table_info(sessions)").fetchall()]
        if "tool_execution_seconds" not in columns:
            conn.execute(
                "ALTER TABLE sessions ADD COLUMN tool_execution_seconds REAL NOT NULL DEFAULT 0"
            )
            conn.commit()
    except Exception:
        pass


def _ensure_schema_exists(conn) -> None:
    """Create tables if they don't exist, without dropping data."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_key TEXT PRIMARY KEY,
            agent TEXT NOT NULL,
            session_id TEXT NOT NULL,
            title TEXT NOT NULL DEFAULT '',
            project_key TEXT NOT NULL,
            project_name TEXT NOT NULL DEFAULT '',
            cwd TEXT NOT NULL DEFAULT '',
            started_at TEXT NOT NULL DEFAULT '',
            ended_at TEXT NOT NULL DEFAULT '',
            duration_seconds REAL NOT NULL DEFAULT 0,
            model_execution_seconds REAL NOT NULL DEFAULT 0,
            tool_execution_seconds REAL NOT NULL DEFAULT 0,
            model TEXT NOT NULL DEFAULT '',
            git_branch TEXT NOT NULL DEFAULT '',
            source TEXT NOT NULL DEFAULT '',
            user_message_count INTEGER NOT NULL DEFAULT 0,
            assistant_message_count INTEGER NOT NULL DEFAULT 0,
            tool_call_count INTEGER NOT NULL DEFAULT 0,
            input_tokens INTEGER NOT NULL DEFAULT 0,
            output_tokens INTEGER NOT NULL DEFAULT 0,
            cached_input_tokens INTEGER NOT NULL DEFAULT 0,
            cached_output_tokens INTEGER NOT NULL DEFAULT 0,
            failed_tool_count INTEGER NOT NULL DEFAULT 0,
            indexed_at REAL NOT NULL DEFAULT 0,
            file_mtime REAL NOT NULL DEFAULT 0,
            file_path TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project_key);
        CREATE INDEX IF NOT EXISTS idx_sessions_agent ON sessions(agent);
        CREATE INDEX IF NOT EXISTS idx_sessions_ended_at ON sessions(ended_at DESC);
        CREATE INDEX IF NOT EXISTS idx_sessions_model ON sessions(model);
        CREATE INDEX IF NOT EXISTS idx_sessions_title ON sessions(title);
        CREATE TABLE IF NOT EXISTS scan_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at REAL NOT NULL,
            finished_at REAL,
            claude_count INTEGER DEFAULT 0,
            codex_count INTEGER DEFAULT 0,
            qoder_count INTEGER DEFAULT 0,
            mode TEXT DEFAULT 'full',
            status TEXT DEFAULT 'running'
        );
    """)
    conn.commit()
    _migrate_model_execution_seconds(conn)
    _migrate_tool_execution_seconds(conn)


def _find_pids_on_port(port: int) -> list[int]:
    """Find PIDs of processes listening on the given port."""
    pids = []
    try:
        result = _run_command(["lsof", "-ti", f":{port}"], timeout=5)
        for line in result.stdout.strip().splitlines():
            line = line.strip()
            if line:
                try:
                    pids.append(int(line))
                except ValueError:
                    pass
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return pids


def cmd_serve(args: argparse.Namespace) -> None:
    """Start the local web server with tiered background incremental scanner."""
    from session_browser.web.routes import create_server
    from session_browser.index.indexer import (
        _get_connection, incremental_scan,
        TIER_HOT_SECONDS, TIER_HOT_INTERVAL,
        TIER_WARM_SECONDS, TIER_WARM_INTERVAL,
    )

    port = args.port or SERVER_PORT
    host = args.host or SERVER_HOST
    force = getattr(args, "force", False)

    # Check if a server is already running on this port
    existing_pids = _find_pids_on_port(port)
    if existing_pids:
        pid_list = ", ".join(str(p) for p in existing_pids)
        logger.warning(
            "A process is already listening: host=%s port=%s pids=%s",
            host,
            port,
            pid_list,
        )
        if force:
            logger.warning("--force: killing existing server automatically")
        else:
            try:
                answer = input("Kill it and restart? [y/N]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                answer = "n"
        if force or answer in ("y", "yes"):
            for pid in existing_pids:
                if _kill_process(pid):
                    logger.warning("Killed server process pid=%s", pid)
                else:
                    logger.error("Failed to kill server process pid=%s", pid)
            time.sleep(1)
        else:
            print("Aborted.")
            sys.exit(0)

    logger.info(
        "Data paths: index=%s claude=%s codex=%s qoder=%s",
        INDEX_DIR,
        CLAUDE_DATA_DIR,
        CODEX_DATA_DIR,
        QODER_DATA_DIR,
    )

    # Ensure index exists (without dropping existing data)
    conn = _get_connection()
    _ensure_schema_exists(conn)
    count = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]

    startup_scan = getattr(args, "startup_scan", False) or _truthy_env("SESSION_BROWSER_STARTUP_SCAN")
    if startup_scan:
        logger.info("Running startup incremental scan before serving")
        start = time.time()
        try:
            result = incremental_scan(conn, verbose=False)
            count = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
            logger.info(
                "Startup scan complete: total_indexed=%s updated=%s new=%s skipped=%s elapsed=%.1fs",
                count,
                result.get("total", 0),
                result.get("new_count", 0),
                result.get("skipped", 0),
                time.time() - start,
            )
        except Exception:
            logger.exception("Startup scan failed")
            if not args.allow_empty:
                conn.close()
                raise
    conn.close()

    if count == 0:
        logger.warning("Index is empty. Run 'scan' first, or server will show empty data.")
        if not args.allow_empty:
            logger.error("Refusing to start with empty index without --allow-empty")
            sys.exit(1)

    # Start tiered background scanner
    if not args.no_scan:
        scanner = _BackgroundScanner(
            hot_seconds=TIER_HOT_SECONDS,
            hot_interval=TIER_HOT_INTERVAL,
            warm_seconds=TIER_WARM_SECONDS,
            warm_interval=TIER_WARM_INTERVAL,
        )
        scanner.start()
        logger.info(
            "Background scanner started: hot_interval=%ss warm_interval=%ss",
            TIER_HOT_INTERVAL,
            TIER_WARM_INTERVAL,
        )

    server = create_server(host=host, port=port)
    logger.info(
        "Starting session-browser: url=http://%s:%s version=%s log_level=%s",
        host,
        port,
        SESSION_BROWSER_VERSION,
        logging.getLevelName(logging.getLogger().getEffectiveLevel()),
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down after KeyboardInterrupt")
        server.shutdown()
    except Exception:
        logger.exception("Fatal server error")
        raise


class _BackgroundScanner:
    """Tiered background scanner for incremental session updates.

    Tiers based on session ended_at:
    - Hot (within TIER_HOT_SECONDS):  scanned every TIER_HOT_INTERVAL seconds
    - Warm (within TIER_WARM_SECONDS): scanned every TIER_WARM_INTERVAL seconds
    - Cold (older than TIER_WARM_SECONDS): skipped, only handled by full_scan

    Only prints output when new sessions are discovered (active sessions
    being re-updated is expected and noisy).
    """

    def __init__(
        self,
        hot_seconds: int,
        hot_interval: int,
        warm_seconds: int,
        warm_interval: int,
    ):
        self.hot_seconds = hot_seconds
        self.hot_interval = hot_interval
        self.warm_seconds = warm_seconds
        self.warm_interval = warm_interval
        self._last_hot_scan = 0.0
        self._last_warm_scan = 0.0
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def _run(self) -> None:
        from session_browser.index.indexer import (
            incremental_scan, _get_connection,
        )

        while True:
            now = time.time()
            needs_hot = (now - self._last_hot_scan) >= self.hot_interval
            needs_warm = (now - self._last_warm_scan) >= self.warm_interval

            if not needs_hot and not needs_warm:
                time.sleep(1)
                continue

            try:
                conn = _get_connection()
                # Ensure tables exist without dropping data
                from session_browser.cli import _ensure_schema_exists
                _ensure_schema_exists(conn)

                if needs_hot:
                    result = incremental_scan(conn, max_age_seconds=self.hot_seconds)
                    if result.get("new_count", 0) > 0:
                        print(f"  [hot scan] {result['new_count']} new session(s), "
                              f"{result['total'] - result['new_count']} updated, "
                              f"{result['skipped']} skipped")
                    self._last_hot_scan = time.time()

                if needs_warm:
                    result = incremental_scan(conn, max_age_seconds=self.warm_seconds)
                    if result.get("new_count", 0) > 0:
                        print(f"  [warm scan] {result['new_count']} new session(s), "
                              f"{result['total'] - result['new_count']} updated, "
                              f"{result['skipped']} skipped")
                    self._last_warm_scan = time.time()

                conn.close()
            except Exception:
                logger.exception("Background incremental scan failed")

            time.sleep(1)


def cmd_stop(args: argparse.Namespace) -> None:
    """Stop the running web server by killing the process on the port."""
    port = args.port or SERVER_PORT

    # Find PID using lsof
    try:
        result = _run_command(
            ["lsof", "-ti", f":{port}"],
            timeout=5,
        )
    except FileNotFoundError:
        print("Error: 'lsof' not found. Stop the server manually.")
        sys.exit(1)
    except subprocess.TimeoutExpired:
        print(f"Error: timed out searching for process on port {port}.")
        sys.exit(1)

    pids = [line.strip() for line in result.stdout.strip().splitlines() if line.strip()]
    if not pids:
        print(f"No process found on port {port}. Server may not be running.")
        return

    for pid in pids:
        try:
            print(f"Stopping process {pid} on port {port}...")
            os.kill(int(pid), signal.SIGTERM)
            print(f"Process {pid} stopped.")
        except ProcessLookupError:
            print(f"Process {pid} already exited.")
        except PermissionError:
            print(f"Permission denied for process {pid}. Try: kill {pid}")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="session-browser",
        description="Local agent session browser and analyzer",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {SESSION_BROWSER_VERSION}")
    sub = parser.add_subparsers(dest="command")

    # scan command
    scan_p = sub.add_parser("scan", help="Scan and index all local sessions")
    scan_p.add_argument("--incremental", action="store_true",
                        help="Only scan sessions whose source files have changed")
    scan_p.add_argument("--agent", choices=["claude_code", "codex", "qoder"],
                        help="Scan only a specific agent (claude_code, codex, or qoder)")
    scan_p.add_argument("--force", "-f", action="store_true",
                        help="Kill existing scan process without prompting")

    # serve command
    serve_p = sub.add_parser("serve", help="Start local web server")
    serve_p.add_argument("--host", default=SERVER_HOST, help=f"Bind address (default: {SERVER_HOST})")
    serve_p.add_argument("--port", type=int, default=SERVER_PORT, help=f"Port (default: {SERVER_PORT})")
    serve_p.add_argument("--allow-empty", action="store_true", help="Allow starting with empty index")
    serve_p.add_argument("--no-scan", action="store_true", help="Disable background incremental scanner")
    serve_p.add_argument("--startup-scan", action="store_true",
                         help="Run one full-window incremental scan before serving")
    serve_p.add_argument("--force", "-f", action="store_true",
                        help="Kill existing server on port without prompting")
    serve_p.add_argument("--log-level", default=SESSION_BROWSER_LOG_LEVEL,
                         help=f"Log level (default: {SESSION_BROWSER_LOG_LEVEL})")

    # stop command
    stop_p = sub.add_parser("stop", help="Stop the running web server")
    stop_p.add_argument("--port", type=int, default=SERVER_PORT, help=f"Port to stop (default: {SERVER_PORT})")

    args = parser.parse_args()
    configure_logging(getattr(args, "log_level", None))

    if args.command == "scan":
        cmd_scan(args)
    elif args.command == "serve":
        cmd_serve(args)
    elif args.command == "stop":
        cmd_stop(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
