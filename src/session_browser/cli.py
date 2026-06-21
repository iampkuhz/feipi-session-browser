"""Command-line entry point for scanning and serving local session indexes.

Usage:
    python -m session_browser scan        # Auto scan (incremental when safe)
    python -m session_browser scan --incremental   # Incremental scan
    python -m session_browser scan --full # Full scan
    python -m session_browser serve       # Start web server
    python -m session_browser serve --port 18999
    python -m session_browser stop        # Stop web server

The module is imported by ``python -m session_browser`` and the
``session-browser`` console script. It wires argparse subcommands to index scans,
the local HTTP server, and server shutdown helpers while preserving shell and
container handoff through environment-backed configuration values.
"""

from __future__ import annotations

import argparse
import importlib
import logging
import os
import signal
import sqlite3
import subprocess
import sys
import threading
import time
from contextlib import contextmanager, suppress
from typing import TYPE_CHECKING, TextIO

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path
    from types import ModuleType

try:
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX fallback keeps CLI importable.
    fcntl = None

from session_browser.config import (
    CLAUDE_DATA_DIR,
    CODEX_DATA_DIR,
    INDEX_DIR,
    INDEX_PATH,
    QODER_DATA_DIR,
    SERVER_HOST,
    SERVER_PORT,
    SESSION_BROWSER_LOG_LEVEL,
    SESSION_BROWSER_VERSION,
    ensure_index_dir,
)
from session_browser.index.indexer import (
    TIER_HOT_INTERVAL,
    TIER_HOT_SECONDS,
    TIER_WARM_INTERVAL,
    TIER_WARM_SECONDS,
)
from session_browser.index.schema import (
    SCAN_LOGIC_VERSION,
    ensure_index_metadata_schema,
    ensure_session_artifacts_schema,
    get_stored_scan_logic_version,
    set_stored_scan_logic_version,
)
from session_browser.web.routes import create_server

logger = logging.getLogger('session_browser')


def _indexer_module() -> ModuleType:
    """Return the current indexer module used by scan commands.

    Some index tests reload ``session_browser.index.indexer`` after changing
    environment-backed source paths. CLI scan entry points resolve the module at
    call time so monkeypatches and reloads affect foreground, startup, and
    background scans instead of using a stale module object.

    Returns:
        Currently imported ``session_browser.index.indexer`` module.
    """
    return importlib.import_module('session_browser.index.indexer')


class ScanLockUnavailable(RuntimeError):  # noqa: N818 - preserves existing CLI exception name.
    """Signal that another process already owns the scan lock.

    The scan and serve commands raise this error when a foreground, startup, or
    background scan cannot acquire ``scan.lock`` within the requested wait mode.
    ``lock_path`` identifies the lock file and ``holder`` carries the last owner
    payload written by the active scanner so the caller can print diagnostics.

    Args:
        lock_path: Path to the index lock file that could not be acquired.
        holder: Last owner payload read from the lock file, or an empty string
            when it could not be read.
    """

    def __init__(self, lock_path: Path, holder: str) -> None:
        """Store lock diagnostics without deciding CLI exit status.

        Args:
            lock_path: Path to the index lock file that could not be acquired.
            holder: Last owner payload read from the lock file, or an empty
                string when it could not be read.
        """  # noqa: RUF100  # noqa: DOC301
        super().__init__('session-browser scan lock is unavailable')
        self.lock_path = lock_path
        self.holder = holder


def configure_logging(level: str | None = None) -> None:
    """Configure process-wide logging for CLI commands.

    Args:
        level: Optional log level name from argparse. When omitted, the function
            uses ``SESSION_BROWSER_LOG_LEVEL`` and then ``INFO``.

    Side Effects:
        Reconfigures root logging, captures warnings into logging, and quiets
        noisy third-party loggers used while serving rendered session content.
    """
    raw_level = (level or SESSION_BROWSER_LOG_LEVEL or 'INFO').upper()
    log_level = getattr(logging, raw_level, logging.INFO)
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s %(levelname)s %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        force=True,
    )
    logging.captureWarnings(True)
    for noisy_logger in ('markdown_it', 'PIL'):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)
    logger.debug('Logging configured at %s', logging.getLevelName(log_level))


def _truthy_env(name: str, default: bool = False) -> bool:
    """Interpret opt-in CLI environment switches.

    The scan and serve commands call this helper for feature flags where common
    truthy shell values should enable behavior. ``default`` is returned only
    when ``name`` is absent; malformed non-truthy values intentionally disable
    the flag rather than raising.

    Args:
        name: Environment variable name to read.
        default: Value returned when ``name`` is not set.

    Returns:
        ``True`` for common truthy shell values, ``False`` for all other present
        values, or ``default`` when the variable is absent.
    """
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {'1', 'true', 'yes', 'y', 'on'}


def _run_command(
    cmd: list[str],
    *,
    timeout: float,
) -> subprocess.CompletedProcess[str]:
    """Run a short helper command and clean up its process group on timeout.

    Args:
        cmd: Executable and arguments passed directly to ``subprocess.Popen``.
        timeout: Maximum seconds to wait before terminating the process group.

    Returns:
        Completed process with captured text stdout and stderr.

    Raises:
        subprocess.TimeoutExpired: Raised after SIGTERM/SIGKILL cleanup if the
            helper does not finish within ``timeout``.
    """
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
            with suppress(ProcessLookupError):
                os.killpg(proc.pid, signal.SIGKILL)
            proc.communicate()
        raise subprocess.TimeoutExpired(
            cmd,
            timeout,
            output=exc.output,
            stderr=exc.stderr,
        ) from exc

    return subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)


def _scan_lock_timeout_seconds() -> float:
    """Return the foreground scan-lock wait budget in seconds.

    The scan command reads ``SESSION_BROWSER_SCAN_LOCK_TIMEOUT_SECONDS`` first
    and then the legacy ``SESSION_BROWSER_SCAN_LOCK_TIMEOUT``. Invalid values
    are logged and fall back to the two-minute default; negative values become
    zero for non-blocking behavior.

    Returns:
        Non-negative timeout in seconds used by foreground scans.
    """
    raw = os.environ.get('SESSION_BROWSER_SCAN_LOCK_TIMEOUT_SECONDS')
    if raw is None:
        raw = os.environ.get('SESSION_BROWSER_SCAN_LOCK_TIMEOUT')
    if raw is None:
        return 120.0
    try:
        return max(0.0, float(raw))
    except ValueError:
        logger.warning('Invalid SESSION_BROWSER_SCAN_LOCK_TIMEOUT=%r; using default', raw)
        return 120.0


def _read_scan_lock_holder(lock_file: TextIO) -> str:
    """Read the last owner payload from an opened scan lock file.

    Args:
        lock_file: Open text file positioned arbitrarily by the lock holder.

    Returns:
        Trimmed owner payload, or an empty string when the file cannot be read.
    """
    try:
        lock_file.seek(0)
        return lock_file.read().strip()
    except OSError:
        return ''


def _write_scan_lock_holder(lock_file: TextIO, owner: str) -> None:
    """Persist the current scan owner in the already-locked file.

    Args:
        lock_file: Open text file that already has an exclusive process lock.
        owner: Human-readable label for foreground, startup, or background scan.

    Side Effects:
        Replaces the lock-file contents and fsyncs it so diagnostics survive a
        later blocked scanner in another process.
    """
    started_at = time.strftime('%Y-%m-%dT%H:%M:%S%z')
    payload = f'pid={os.getpid()} owner={owner} started_at={started_at}\n'
    lock_file.seek(0)
    lock_file.truncate()
    lock_file.write(payload)
    lock_file.flush()
    os.fsync(lock_file.fileno())


@contextmanager
def _scan_lock(owner: str, *, blocking: bool, timeout_seconds: float = 0.0) -> Iterator[None]:
    """Coordinate foreground, startup, and background scans across processes.

    Args:
        owner: Label written to ``scan.lock`` after acquiring it.
        blocking: Whether to wait for another scanner until ``timeout_seconds``.
        timeout_seconds: Maximum wait time when ``blocking`` is true.

    Yields:
        ``None`` while the caller owns the lock.

    Raises:
        ScanLockUnavailable: Raised when the lock is held and waiting is disabled
            or the timeout expires.

    Side Effects:
        Creates ``INDEX_DIR`` and ``scan.lock`` when needed, writes owner
        metadata, and releases the OS lock when the context exits.
    """
    if fcntl is None:
        # fcntl is unavailable on some platforms; SQLite busy_timeout still applies.
        yield
        return

    ensure_index_dir()
    lock_path = INDEX_DIR / 'scan.lock'
    lock_path.touch(exist_ok=True)
    lock_file = lock_path.open('r+', encoding='utf-8')
    acquired = False
    deadline = time.monotonic() + max(0.0, timeout_seconds)
    try:
        while True:
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                break
            except BlockingIOError as exc:
                if not blocking or time.monotonic() >= deadline:
                    holder = _read_scan_lock_holder(lock_file)
                    raise ScanLockUnavailable(lock_path, holder) from exc
                time.sleep(0.25)

        _write_scan_lock_holder(lock_file, owner)
        yield
    finally:
        if acquired:
            with suppress(OSError):
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        lock_file.close()


def _find_running_scan_pid() -> int | None:
    """Find another running ``session_browser scan`` process.

    Returns:
        PID of the first matching scan process excluding this process, or
        ``None`` when ``ps`` is unavailable, times out, or no scan is found.
    """
    pid_column_count = 2
    my_pid = os.getpid()
    try:
        result = subprocess.run(
            ['ps', 'aux'],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        for line in result.stdout.splitlines():
            if (
                'session_browser' in line
                and ' scan' in line
                and str(my_pid) not in line.split()[1:2]
            ):
                parts = line.split()
                if len(parts) >= pid_column_count:
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
    """Terminate a process with graceful and forced signals.

    Args:
        pid: Process ID selected by scan or server conflict detection.

    Returns:
        ``True`` when the process is gone by the final check, including the case
        where it already exited; ``False`` when it still appears alive.

    Side Effects:
        Sends SIGTERM, waits up to five seconds, and then attempts SIGKILL.
    """
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return True
    except PermissionError:
        # Fall through to SIGKILL below; the final liveness check reports status.
        pass

    for _ in range(5):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(1)

    try:
        os.kill(pid, signal.SIGKILL)
        time.sleep(1)
    except (ProcessLookupError, PermissionError):
        pass

    try:
        os.kill(pid, 0)
        return False
    except ProcessLookupError:
        return True


def _print_database_locked_help(exc: sqlite3.OperationalError) -> None:
    """Print actionable diagnostics for SQLite lock failures.

    Args:
        exc: OperationalError raised while opening or mutating the index.

    Side Effects:
        Writes remediation steps and, when ``lsof`` is available, current index
        file holders to stderr. The caller remains responsible for process exit.
    """
    print(f'Scan failed: SQLite database is locked ({exc})', file=sys.stderr)
    print(f'Index path: {INDEX_PATH}', file=sys.stderr)
    print('', file=sys.stderr)
    print(
        '通常原因: 另一个 session-browser 服务、后台扫描, '
        '或 IntelliJ/DB Browser 等工具正在打开同一个 SQLite 索引。',
        file=sys.stderr,
    )
    print('处理方式:', file=sys.stderr)
    print(
        f'  1. 停止本地服务: ./scripts/session-browser.sh stop --port {SERVER_PORT}',
        file=sys.stderr,
    )
    print(
        '  2. 断开 IntelliJ Database/SQLite data source, 或关闭占用该 DB 的工具。',
        file=sys.stderr,
    )
    print('  3. 重新执行: ./scripts/session-browser.sh scan', file=sys.stderr)
    print('', file=sys.stderr)

    lsof_targets = [
        str(INDEX_PATH),
        str(INDEX_PATH) + '-wal',
        str(INDEX_PATH) + '-shm',
    ]
    try:
        result = _run_command(['lsof', '-nP', *lsof_targets], timeout=5)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        result = None
    if result and result.stdout.strip():
        print('当前持有索引文件的进程:', file=sys.stderr)
        print(result.stdout.strip(), file=sys.stderr)


def _print_scan_lock_help(exc: ScanLockUnavailable) -> None:
    """Print diagnostics when the scan lock is already held.

    Args:
        exc: Lock acquisition error containing the path and optional holder
            payload.

    Side Effects:
        Writes blocking-scan remediation guidance to stderr. Exit status is
        decided by the caller.
    """
    print('Scan failed: another session-browser scan is already running.', file=sys.stderr)
    print(f'Lock path: {exc.lock_path}', file=sys.stderr)
    if exc.holder:
        print(f'Lock holder: {exc.holder}', file=sys.stderr)
    print('', file=sys.stderr)
    print('处理方式:', file=sys.stderr)
    print('  1. 等待当前前台 scan 或后台 incremental scan 完成。', file=sys.stderr)
    print(
        f'  2. 如由本地服务触发, 可停止服务: '
        f'./scripts/session-browser.sh stop --port {SERVER_PORT}',
        file=sys.stderr,
    )
    print('  3. 如确认没有扫描运行, 可删除同目录 scan.lock 后重试。', file=sys.stderr)


def _scan_logic_version_gate_enabled() -> bool:
    """Return whether automatic scans should rebuild after logic version drift.

    Returns:
        ``True`` when either scan-logic-version gate environment flag is truthy.
    """
    return _truthy_env('SESSION_BROWSER_DEV_SCAN_LOGIC_VERSION_GATE') or _truthy_env(
        'SESSION_BROWSER_ENABLE_SCAN_LOGIC_VERSION_GATE'
    )


def _decide_scan_mode(  # noqa: PLR0911 - ordered CLI decisions are clearer than state flags.
    conn: sqlite3.Connection,
    args: argparse.Namespace,
) -> tuple[str, str]:
    """Choose foreground scan mode from CLI flags and index state.

    Args:
        conn: Open index connection used only for metadata and row-count checks.
        args: Parsed ``scan`` namespace with mutually exclusive mode flags.

    Returns:
        ``("full"|"incremental", reason)`` where reason is printed to explain
        why automatic selection chose that mode.
    """
    if getattr(args, 'full', False):
        return 'full', 'explicit --full'
    if getattr(args, 'incremental', False):
        return 'incremental', 'explicit --incremental'

    if not _table_exists(conn, 'sessions'):
        return 'full', 'index schema missing'
    missing = _missing_current_session_columns(conn)
    if missing:
        return 'full', 'index schema incompatible'
    count = conn.execute('SELECT COUNT(*) FROM sessions').fetchone()[0]
    if count == 0:
        return 'full', 'index empty'

    if _scan_logic_version_gate_enabled():
        stored = get_stored_scan_logic_version(conn)
        current = str(SCAN_LOGIC_VERSION)
        if stored != current:
            before = stored if stored is not None else 'missing'
            return 'full', f'scan logic version changed {before} -> {current}'

    return 'incremental', 'auto'


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    """Return whether ``table_name`` exists in the SQLite index.

    Args:
        conn: Open SQLite connection.
        table_name: Exact table name to look up in ``sqlite_master``.

    Returns:
        ``True`` when SQLite reports a table with that name, otherwise ``False``.
    """
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _missing_current_session_columns(conn: sqlite3.Connection) -> list[str]:
    """List current ``sessions`` columns absent from the opened index.

    Args:
        conn: Open SQLite connection to inspect.

    Returns:
        Sorted missing column names. When the table is absent, every required
        current column is returned so callers can force a full rebuild.
    """
    if not _table_exists(conn, 'sessions'):
        return sorted(_CURRENT_SESSION_COLUMNS)
    columns = {r[1] for r in conn.execute('PRAGMA table_info(sessions)').fetchall()}
    return sorted(_CURRENT_SESSION_COLUMNS - columns)


def cmd_scan(args: argparse.Namespace) -> None:  # noqa: PLR0912, PLR0915 - CLI orchestration.
    """Run an auto, full, or incremental index scan from the CLI.

    Args:
        args: Parsed ``scan`` namespace. ``--full`` forces a rebuild,
            ``--incremental`` only refreshes changed sources, ``--agent`` limits
            the source family, and ``--force`` kills a conflicting scan without
            prompting.

    Raises:
        sqlite3.OperationalError: Re-raised for non-locking SQLite failures.

    Side Effects:
        May prompt on stdin, terminate a conflicting scan process, acquire
        ``scan.lock``, mutate the SQLite index, print scan counts, and exit with
        status ``2`` for lock conflicts.
    """
    force = getattr(args, 'force', False)
    scan_pid = _find_running_scan_pid()
    if scan_pid is not None:
        logger.warning('A scan process is already running: pid=%s', scan_pid)
        if force:
            logger.warning('--force: killing existing scan automatically')
        else:
            try:
                answer = input('Kill it and restart? [y/N]: ').strip().lower()
            except (EOFError, KeyboardInterrupt):
                answer = 'n'
        if force or answer in ('y', 'yes'):
            if _kill_process(scan_pid):
                logger.warning('Killed scan process pid=%s; waiting for exit', scan_pid)
                time.sleep(1)
            else:
                logger.error('Failed to kill scan process pid=%s; proceeding anyway', scan_pid)
        else:
            print('Aborted.')
            sys.exit(0)

    agent = args.agent if hasattr(args, 'agent') else None
    label = f' ({agent})' if agent else ''

    conn = None
    try:
        owner = 'foreground scan'
        with _scan_lock(owner, blocking=True, timeout_seconds=_scan_lock_timeout_seconds()):
            indexer_mod = _indexer_module()
            conn = indexer_mod._get_connection()
            mode, reason = _decide_scan_mode(conn, args)
            label_reason = f': {reason}' if reason else ''

            if mode == 'incremental':
                _ensure_schema_exists(conn)
                print(f'Starting incremental scan{label}{label_reason}...')
                start = time.time()
                result = indexer_mod.incremental_scan(conn, verbose=True, agent=agent)
                elapsed = time.time() - start
                print(f'\nIncremental scan complete in {elapsed:.1f}s')
                print(f'  Updated Claude: {result["claude_count"]} sessions')
                print(f'  Updated Codex:  {result["codex_count"]} sessions')
                if 'qoder_count' in result:
                    print(f'  Updated Qoder:  {result["qoder_count"]} sessions')
                print(f'  Skipped:        {result["skipped"]} sessions')
                print(f'  Total updated:  {result["total"]} sessions')
            else:
                print(f'Starting full scan{label}{label_reason}...')
                start = time.time()
                result = indexer_mod.full_scan(conn, verbose=True, agent=agent)
                if _scan_logic_version_gate_enabled() and agent is None:
                    set_stored_scan_logic_version(conn, SCAN_LOGIC_VERSION)
                    conn.commit()
                elapsed = time.time() - start
                print(f'\nScan complete in {elapsed:.1f}s')
                print(f'  Claude Code: {result["claude_count"]} sessions')
                print(f'  Codex:       {result["codex_count"]} sessions')
                if 'qoder_count' in result:
                    print(f'  Qoder:       {result["qoder_count"]} sessions')
                print(f'  Total:       {result["total"]} sessions')
    except ScanLockUnavailable as exc:
        _print_scan_lock_help(exc)
        sys.exit(2)
    except sqlite3.OperationalError as exc:
        if 'database is locked' in str(exc).lower():
            _print_database_locked_help(exc)
            sys.exit(2)
        raise
    finally:
        if conn is not None:
            conn.close()


_CURRENT_SESSION_COLUMNS = {
    'session_key',
    'agent',
    'session_id',
    'title',
    'project_key',
    'project_name',
    'cwd',
    'started_at',
    'ended_at',
    'duration_seconds',
    'model_execution_seconds',
    'tool_execution_seconds',
    'model',
    'git_branch',
    'source',
    'user_message_count',
    'assistant_message_count',
    'tool_call_count',
    'output_tokens',
    'fresh_input_tokens',
    'cache_read_tokens',
    'cache_write_tokens',
    'total_tokens',
    'failed_tool_count',
    'subagent_instance_count',
    'indexed_at',
    'file_mtime',
    'file_path',
}


def _assert_current_session_schema(conn: sqlite3.Connection) -> None:
    """Ensure the opened index already has the current session schema.

    Args:
        conn: Open SQLite connection after table creation or migration helpers.

    Raises:
        RuntimeError: Raised when required columns are missing; callers should
            rebuild the index with a full scan rather than silently using stale
            data.
    """
    missing = _missing_current_session_columns(conn)
    if missing:
        raise RuntimeError(
            '当前本地索引 schema 缺少列 '
            + ', '.join(missing)
            + '; 请删除旧索引或运行 full scan 重建。'
        )


def _ensure_schema_exists(conn: sqlite3.Connection) -> None:
    """Create required index tables without dropping existing rows.

    Args:
        conn: Open SQLite connection for the index file.

    Side Effects:
        Creates the sessions, scan-log, metadata, and artifact tables and commits
        the connection. Schema validation may raise ``RuntimeError`` when an old
        ``sessions`` table is missing required columns and needs a full rebuild.
    """
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
            output_tokens INTEGER NOT NULL DEFAULT 0,
            fresh_input_tokens INTEGER NOT NULL DEFAULT 0,
            cache_read_tokens INTEGER NOT NULL DEFAULT 0,
            cache_write_tokens INTEGER NOT NULL DEFAULT 0,
            total_tokens INTEGER NOT NULL DEFAULT 0,
            failed_tool_count INTEGER NOT NULL DEFAULT 0,
            subagent_instance_count INTEGER NOT NULL DEFAULT 0,
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
    ensure_index_metadata_schema(conn)
    ensure_session_artifacts_schema(conn)
    _assert_current_session_schema(conn)
    conn.commit()


def _is_orphan(pid: int) -> bool:
    """Return whether a process appears orphaned with parent PID 1.

    Args:
        pid: Process ID discovered on the requested server port.

    Returns:
        ``True`` when ``ps`` reports PPID 1, otherwise ``False`` for active
        parents, unavailable ``ps``, parse failures, or timeout.
    """
    try:
        result = subprocess.run(
            ['ps', '-o', 'ppid=', '-p', str(pid)],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        if result.returncode == 0:
            ppid = int(result.stdout.strip())
            return ppid == 1
    except (ValueError, subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return False


def _find_pids_on_port(port: int) -> list[int]:
    """Find process IDs listening on a TCP port.

    Args:
        port: Local port requested by ``serve`` or ``stop``.

    Returns:
        Integer PIDs reported by ``lsof``. Invalid lines and unavailable ``lsof``
        are ignored so callers can decide whether startup should continue.
    """
    pids = []
    try:
        result = _run_command(['lsof', '-ti', f':{port}'], timeout=5)
        for raw_line in result.stdout.strip().splitlines():
            line = raw_line.strip()
            if line:
                with suppress(ValueError):
                    pids.append(int(line))
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return pids


def cmd_serve(args: argparse.Namespace) -> None:  # noqa: PLR0912, PLR0915 - CLI orchestration.
    """Start the local web server and optional background scanner.

    Args:
        args: Parsed ``serve`` namespace. ``--host`` and ``--port`` choose the
            bind target, ``--allow-empty`` permits an empty index, ``--no-scan``
            disables background refresh, ``--startup-scan`` runs one bounded
            incremental scan before serving, and ``--force`` kills conflicts.

    Raises:
        Exception: Re-raises fatal server and startup-scan failures so the CLI
            exits visibly instead of serving corrupted state.

    Side Effects:
        May kill orphaned or conflicting port owners, creates missing schema,
        starts a daemon scanner thread, logs configured paths, and blocks in the
        HTTP server until interrupted.
    """
    port = args.port or SERVER_PORT
    host = args.host or SERVER_HOST
    force = getattr(args, 'force', False)

    existing_pids = _find_pids_on_port(port)
    if existing_pids:
        pid_list = ', '.join(str(p) for p in existing_pids)
        orphans = [p for p in existing_pids if _is_orphan(p)]
        if orphans:
            orphan_list = ', '.join(str(p) for p in orphans)
            logger.warning(
                'Orphaned process(es) detected on port %s: '
                'pids=%s (PPID=1, likely fixture servers)',
                port,
                orphan_list,
            )
            for pid in orphans:
                if _kill_process(pid):
                    logger.warning('Killed orphaned process pid=%s', pid)
                else:
                    logger.error('Failed to kill orphaned process pid=%s', pid)
            time.sleep(1)
            existing_pids = [p for p in existing_pids if p not in orphans]

        if existing_pids:
            pid_list = ', '.join(str(p) for p in existing_pids)
            logger.warning(
                'A process is already listening: host=%s port=%s pids=%s',
                host,
                port,
                pid_list,
            )
            if force:
                logger.warning('--force: killing existing server automatically')
            else:
                try:
                    answer = input('Kill it and restart? [y/N]: ').strip().lower()
                except (EOFError, KeyboardInterrupt):
                    answer = 'n'
            if force or answer in ('y', 'yes'):
                for pid in existing_pids:
                    if _kill_process(pid):
                        logger.warning('Killed server process pid=%s', pid)
                    else:
                        logger.error('Failed to kill server process pid=%s', pid)
                time.sleep(1)
            else:
                print('Aborted.')
                sys.exit(0)

    logger.info(
        'Data paths: index=%s claude=%s codex=%s qoder=%s',
        INDEX_DIR,
        CLAUDE_DATA_DIR,
        CODEX_DATA_DIR,
        QODER_DATA_DIR,
    )

    indexer_mod = _indexer_module()
    conn = indexer_mod._get_connection()
    _ensure_schema_exists(conn)
    count = conn.execute('SELECT COUNT(*) FROM sessions').fetchone()[0]

    startup_scan = getattr(args, 'startup_scan', False) or _truthy_env(
        'SESSION_BROWSER_STARTUP_SCAN'
    )
    if startup_scan:
        logger.info('Running startup incremental scan before serving')
        start = time.time()
        try:
            with _scan_lock('startup incremental scan', blocking=False):
                result = indexer_mod.incremental_scan(conn, verbose=False, max_age_seconds=2 * 3600)
                count = conn.execute('SELECT COUNT(*) FROM sessions').fetchone()[0]
                logger.info(
                    'Startup scan complete: total_indexed=%s updated=%s '
                    'new=%s skipped=%s elapsed=%.1fs',
                    count,
                    result.get('total', 0),
                    result.get('new_count', 0),
                    result.get('skipped', 0),
                    time.time() - start,
                )
        except ScanLockUnavailable as exc:
            logger.info(
                'Skipping startup scan because another scan is running: lock=%s holder=%s',
                exc.lock_path,
                exc.holder or 'unknown',
            )
        except Exception:
            logger.exception('Startup scan failed')
            if not args.allow_empty:
                conn.close()
                raise
    conn.close()

    if count == 0:
        logger.warning("Index is empty. Run 'scan' first, or server will show empty data.")
        if not args.allow_empty:
            logger.error('Refusing to start with empty index without --allow-empty')
            sys.exit(1)

    if not args.no_scan:
        scanner = _BackgroundScanner(
            hot_seconds=TIER_HOT_SECONDS,
            hot_interval=TIER_HOT_INTERVAL,
            warm_seconds=TIER_WARM_SECONDS,
            warm_interval=TIER_WARM_INTERVAL,
        )
        scanner.start()
        logger.info(
            'Background scanner started: hot_interval=%ss warm_interval=%ss',
            TIER_HOT_INTERVAL,
            TIER_WARM_INTERVAL,
        )

    server = create_server(host=host, port=port)
    logger.info(
        'Starting session-browser: url=http://%s:%s version=%s log_level=%s',
        host,
        port,
        SESSION_BROWSER_VERSION,
        logging.getLevelName(logging.getLogger().getEffectiveLevel()),
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info('Shutting down after KeyboardInterrupt')
        server.shutdown()
    except Exception:
        logger.exception('Fatal server error')
        raise


class _BackgroundScanner:
    """Run tiered incremental refreshes behind the HTTP server.

    ``cmd_serve`` owns this helper for the lifetime of the process. Hot and warm
    windows are scanned at their own intervals, while cold sessions remain the
    responsibility of explicit full scans. The scanner only prints when new
    sessions appear, because repeated active-session updates are expected noise.

    Args:
        hot_seconds: Maximum age in seconds for the hot scan window.
        hot_interval: Minimum seconds between hot scans.
        warm_seconds: Maximum age in seconds for the warm scan window.
        warm_interval: Minimum seconds between warm scans.
    """

    def __init__(
        self,
        hot_seconds: int,
        hot_interval: int,
        warm_seconds: int,
        warm_interval: int,
    ) -> None:
        """Prepare tier windows and the daemon worker thread.

        Args:
            hot_seconds: Maximum age in seconds for the hot scan window.
            hot_interval: Minimum seconds between hot scans.
            warm_seconds: Maximum age in seconds for the warm scan window.
            warm_interval: Minimum seconds between warm scans.
        """  # noqa: RUF100  # noqa: DOC301
        self.hot_seconds = hot_seconds
        self.hot_interval = hot_interval
        self.warm_seconds = warm_seconds
        self.warm_interval = warm_interval
        self._last_hot_scan = 0.0
        self._last_warm_scan = 0.0
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        """Start the daemon scanner thread for a running ``serve`` command."""
        self._thread.start()

    def _run(self) -> None:
        """Loop forever, refreshing hot and warm windows when due.

        Side Effects:
            Opens short-lived SQLite connections, acquires ``scan.lock`` for each
            refresh, updates last-run timestamps, prints new-session summaries,
            and logs exceptions without stopping the server.
        """
        while True:
            now = time.time()
            needs_hot = (now - self._last_hot_scan) >= self.hot_interval
            needs_warm = (now - self._last_warm_scan) >= self.warm_interval

            if not needs_hot and not needs_warm:
                time.sleep(1)
                continue

            try:
                with _scan_lock('background incremental scan', blocking=False):
                    conn = None
                    try:
                        indexer_mod = _indexer_module()
                        conn = indexer_mod._get_connection()
                        _ensure_schema_exists(conn)

                        if needs_hot:
                            result = indexer_mod.incremental_scan(
                                conn, max_age_seconds=self.hot_seconds
                            )
                            if result.get('new_count', 0) > 0:
                                print(
                                    f'  [hot scan] {result["new_count"]} new session(s), '
                                    f'{result["total"] - result["new_count"]} updated, '
                                    f'{result["skipped"]} skipped'
                                )
                            self._last_hot_scan = time.time()

                        if needs_warm:
                            result = indexer_mod.incremental_scan(
                                conn, max_age_seconds=self.warm_seconds
                            )
                            if result.get('new_count', 0) > 0:
                                print(
                                    f'  [warm scan] {result["new_count"]} new session(s), '
                                    f'{result["total"] - result["new_count"]} updated, '
                                    f'{result["skipped"]} skipped'
                                )
                            self._last_warm_scan = time.time()
                    finally:
                        if conn is not None:
                            conn.close()
            except ScanLockUnavailable as exc:
                if needs_hot:
                    self._last_hot_scan = time.time()
                if needs_warm:
                    self._last_warm_scan = time.time()
                logger.debug(
                    'Skipping background scan because another scan is running: lock=%s holder=%s',
                    exc.lock_path,
                    exc.holder or 'unknown',
                )
            except Exception:
                logger.exception('Background incremental scan failed')

            time.sleep(1)


def cmd_stop(args: argparse.Namespace) -> None:
    """Stop running server processes listening on the requested port.

    Args:
        args: Parsed ``stop`` namespace containing the port to inspect.

    Side Effects:
        Calls ``lsof`` to discover listeners, sends SIGTERM to each PID, prints
        status messages, and exits with status ``1`` when ``lsof`` is missing or
        times out.
    """
    port = args.port or SERVER_PORT

    try:
        result = _run_command(
            ['lsof', '-ti', f':{port}'],
            timeout=5,
        )
    except FileNotFoundError:
        print("Error: 'lsof' not found. Stop the server manually.")
        sys.exit(1)
    except subprocess.TimeoutExpired:
        print(f'Error: timed out searching for process on port {port}.')
        sys.exit(1)

    pids = [line.strip() for line in result.stdout.strip().splitlines() if line.strip()]
    if not pids:
        print(f'No process found on port {port}. Server may not be running.')
        return

    for pid in pids:
        try:
            print(f'Stopping process {pid} on port {port}...')
            os.kill(int(pid), signal.SIGTERM)
            print(f'Process {pid} stopped.')
        except ProcessLookupError:
            print(f'Process {pid} already exited.')
        except PermissionError:
            print(f'Permission denied for process {pid}. Try: kill {pid}')


def main() -> None:
    """Parse CLI arguments and dispatch to the selected subcommand.

    The console script and ``python -m session_browser`` call this function. It
    configures logging before dispatch, preserves argparse's version handling,
    and exits with status ``1`` when no subcommand is provided.
    """
    parser = argparse.ArgumentParser(
        prog='session-browser',
        description='Local agent session browser and analyzer',
    )
    parser.add_argument(
        '--version', action='version', version=f'%(prog)s {SESSION_BROWSER_VERSION}'
    )
    sub = parser.add_subparsers(dest='command')

    scan_p = sub.add_parser('scan', help='Scan and index all local sessions')
    scan_mode = scan_p.add_mutually_exclusive_group()
    scan_mode.add_argument(
        '--incremental',
        action='store_true',
        help='Only scan sessions whose source files have changed',
    )
    scan_mode.add_argument('--full', action='store_true', help='Force a full index rebuild')
    scan_p.add_argument(
        '--agent',
        choices=['claude_code', 'codex', 'qoder'],
        help='Scan only a specific agent (claude_code, codex, or qoder)',
    )
    scan_p.add_argument(
        '--force', '-f', action='store_true', help='Kill existing scan process without prompting'
    )

    serve_p = sub.add_parser('serve', help='Start local web server')
    serve_p.add_argument(
        '--host', default=SERVER_HOST, help=f'Bind address (default: {SERVER_HOST})'
    )
    serve_p.add_argument(
        '--port', type=int, default=SERVER_PORT, help=f'Port (default: {SERVER_PORT})'
    )
    serve_p.add_argument(
        '--allow-empty', action='store_true', help='Allow starting with empty index'
    )
    serve_p.add_argument(
        '--no-scan', action='store_true', help='Disable background incremental scanner'
    )
    serve_p.add_argument(
        '--startup-scan',
        action='store_true',
        help='Run one full-window incremental scan before serving',
    )
    serve_p.add_argument(
        '--force', '-f', action='store_true', help='Kill existing server on port without prompting'
    )
    serve_p.add_argument(
        '--log-level',
        default=SESSION_BROWSER_LOG_LEVEL,
        help=f'Log level (default: {SESSION_BROWSER_LOG_LEVEL})',
    )

    stop_p = sub.add_parser('stop', help='Stop the running web server')
    stop_p.add_argument(
        '--port', type=int, default=SERVER_PORT, help=f'Port to stop (default: {SERVER_PORT})'
    )

    args = parser.parse_args()
    configure_logging(getattr(args, 'log_level', None))

    if args.command == 'scan':
        cmd_scan(args)
    elif args.command == 'serve':
        cmd_serve(args)
    elif args.command == 'stop':
        cmd_stop(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    main()
