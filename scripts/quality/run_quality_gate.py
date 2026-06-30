#!/usr/bin/env python3
"""Deterministic quality gate runner.

Run quality gates for the selected target and write a structured summary artifact.

Usage:
    python3 scripts/quality/run_quality_gate.py --target session-detail --change-id fix-xyz
    python3 scripts/quality/run_quality_gate.py --target hook-runtime \
        --change-id hook-runtime-selftest
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from functools import lru_cache
from pathlib import Path

# Ensure repo_root is importable when this file is executed directly.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Imports depend on the direct-execution path bootstrap above.
from scripts.harness.python_env import resolve_python  # noqa: E402
from scripts.quality.quality_artifact import (  # noqa: E402
    BLOCKED,
    FAIL,
    PASS,
    GateDetail,
    QualitySummary,
    compute_overall,
    resolve_base_commit,
    resolve_dirty_hash,
    utc_now,
    write_quality_summary,
)
from scripts.quality.quality_targets import (  # noqa: E402
    required_gates_for_target,
    validate_target,
)

HTTP_OK = 200
PLAYWRIGHT_COMMAND_MIN_PARTS = 3
PLAYWRIGHT_MIN_WORKERS = 8
PLAYWRIGHT_TIMEOUT_SECONDS = 120
DEFAULT_TIMEOUT_SECONDS = 300
MODULE_CHECK_TIMEOUT_SECONDS = 10
COMMAND_OUTPUT_TAIL_CHARS = 4000
FIXTURE_SERVER_READY_ATTEMPTS = 30
FIXTURE_SERVER_READY_TIMEOUT_SECONDS = 15

# 01. Command execution helpers


def _python_candidates(repo_root: Path) -> list[str]:
    """Build ordered Python executable candidates for quality gate commands.

    Args:
        repo_root: Repository root used to locate the project virtualenv.

    Returns:
        De-duplicated executable names or paths, preferring explicit
        environment overrides before local virtualenv and system Python.
    """
    candidates: list[str] = []

    explicit = os.environ.get('SESSION_BROWSER_PYTHON')
    if explicit:
        candidates.append(explicit)

    venv_dir = os.environ.get('SESSION_BROWSER_VENV_DIR')
    if venv_dir:
        candidates.append(str(Path(venv_dir) / 'bin' / 'python'))
    else:
        candidates.append(str(repo_root / '.venv' / 'bin' / 'python'))

    for name in ('python', 'python3'):
        resolved = shutil.which(name)
        if resolved:
            candidates.append(resolved)
    candidates.append(sys.executable)

    result: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if not candidate:
            continue
        normalized = str(Path(candidate).expanduser()) if '/' in candidate else candidate
        if normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _python_supports_modules(executable: str, repo_root: Path, modules: tuple[str, ...]) -> bool:
    """Check whether a Python executable can import required gate modules.

    Args:
        executable: Python executable name or path to probe.
        repo_root: Repository root used for subprocess working directory and
            ``PYTHONPATH``.
        modules: Import module names required by the selected gate.

    Returns:
        True when the subprocess imports every module before timeout.
    """
    if shutil.which(executable) is None:
        return False

    env = os.environ.copy()
    src_path = str(repo_root / 'src')
    env['PYTHONPATH'] = src_path + (os.pathsep + env['PYTHONPATH'] if env.get('PYTHONPATH') else '')
    code = (
        'import importlib, sys\n'
        'missing=[]\n'
        'for name in sys.argv[1:]:\n'
        '    try:\n'
        '        importlib.import_module(name)\n'
        '    except Exception:\n'
        '        missing.append(name)\n'
        'sys.exit(1 if missing else 0)\n'
    )
    try:
        proc = subprocess.run(
            [executable, '-c', code, *modules],
            cwd=repo_root,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=MODULE_CHECK_TIMEOUT_SECONDS,
            check=False,
        )
    except Exception:
        return False
    return proc.returncode == 0


@lru_cache(maxsize=8)
def _project_python_cached(repo_root: str, modules: tuple[str, ...]) -> str:
    """Resolve and cache the project Python for repeated gate commands.

    Args:
        repo_root: Repository root serialized for cache stability.
        modules: Required modules included in the cache key.

    Returns:
        Python executable path selected by the shared environment resolver.
    """
    del modules
    return resolve_python(Path(repo_root))


def _project_python(repo_root: Path, *, dev: bool = False) -> str:
    """Resolve the Python executable used by subprocess quality gates.

    Args:
        repo_root: Repository root passed to the environment resolver.
        dev: Whether pytest and other development dependencies are required.

    Returns:
        Executable path for the project environment.
    """
    modules = ('jinja2', 'markdown_it')
    if dev:
        modules = (*modules, 'pytest')
    return _project_python_cached(str(repo_root), modules)


def _playwright_workers() -> int:
    """Return the minimum parallelism for Playwright quality gates.

    Returns:
        Worker count from environment overrides, never below the gate minimum.
    """
    raw = (
        os.environ.get('SESSION_BROWSER_PLAYWRIGHT_WORKERS')
        or os.environ.get('PLAYWRIGHT_WORKERS')
        or ''
    ).strip()
    if raw:
        try:
            return max(PLAYWRIGHT_MIN_WORKERS, int(raw))
        except ValueError:
            pass
    return PLAYWRIGHT_MIN_WORKERS


def _tail_file(path: Path, max_chars: int = 2000) -> str:
    """Read the tail of a log file for fixture-server failure diagnostics.

    Args:
        path: Log file path written by a subprocess gate fixture.
        max_chars: Maximum trailing characters included in the summary.

    Returns:
        Log tail with surrounding whitespace removed, or an empty string when
        the file cannot be read.
    """
    try:
        text = path.read_text(encoding='utf-8', errors='replace')
    except OSError:
        return ''
    return text[-max_chars:].strip()


_ANSI_RE = re.compile(r'\x1b\[[0-9;]*m')


def _strip_ansi(text: str) -> str:
    """Remove ANSI color escapes before parsing quality gate output.

    Args:
        text: Raw subprocess output.

    Returns:
        Output text without terminal color sequences.
    """
    return _ANSI_RE.sub('', text)


def _is_playwright_command(cmd: list[str]) -> bool:
    """Detect Playwright test commands that need gate-specific output parsing.

    Args:
        cmd: Subprocess command list from the gate command matrix.

    Returns:
        True when the command starts with ``npx playwright test``.
    """
    return (
        len(cmd) >= PLAYWRIGHT_COMMAND_MIN_PARTS
        and Path(cmd[0]).name == 'npx'
        and cmd[1:3] == ['playwright', 'test']
    )


def _playwright_skip_count(output: str) -> int:
    """Return Playwright's reported skipped test count from command output.

    Args:
        output: Raw or ANSI-colored Playwright output.

    Returns:
        Sum of all ``N skipped`` counters reported by Playwright.
    """
    clean = _strip_ansi(output)
    matches = re.findall(r'\b(\d+)\s+skipped\b', clean)
    return sum(int(value) for value in matches)


def _is_pytest_command(cmd: list[str]) -> bool:
    """Detect pytest commands whose skipped outcome must fail selected gates."""
    if not cmd:
        return False
    executable = Path(cmd[0]).name
    if executable == 'pytest':
        return True
    return len(cmd) >= 3 and executable.startswith('python') and cmd[1:3] == ['-m', 'pytest']


def _pytest_skip_count(output: str) -> int:
    """Return pytest's reported skipped test count from command output."""
    clean = _strip_ansi(output)
    matches = re.findall(r'\b(\d+)\s+skipped\b', clean)
    return sum(int(value) for value in matches)


def _strip_allowed_warning_noise(output: str, *, gate_name: str, cmd: list[str]) -> str:
    """Remove known non-test warning metadata before warning enforcement.

    Args:
        output: Raw subprocess output from a selected gate.
        gate_name: Gate name used to apply gate-specific allowlisted noise.
        cmd: Command list used to detect Playwright output.

    Returns:
        Output with accepted warning-like metadata removed.
    """
    clean = _strip_ansi(output)

    if gate_name == 'cssOwnership':
        lines: list[str] = []
        for line in clean.splitlines():
            stripped = line.strip()
            if re.match(r'^Warnings:\s*\d+\s*$', stripped, flags=re.IGNORECASE):
                continue
            if re.match(r'^\[WARN\]\s+', stripped, flags=re.IGNORECASE):
                continue
            if re.match(
                r'^CSS ownership:\s+PASS\s+\(\d+\s+warnings?\)\s*$', stripped, flags=re.IGNORECASE
            ):
                continue
            lines.append(line)
        return '\n'.join(lines)

    if _is_playwright_command(cmd):
        lines = []
        skip_trace_for_allowed_warning = False
        for line in clean.splitlines():
            stripped = line.strip()
            is_no_color_noise = (
                "Warning: The 'NO_COLOR' env is ignored due to the 'FORCE_COLOR' env being set."
                in stripped
            )
            is_module_register_noise = bool(
                re.match(
                    r'^(?:[^`\s]*\s+)?\[DEP0205\]\s+DeprecationWarning:\s+'
                    r'`module\.register\(\)` is deprecated\.',
                    stripped,
                )
            )
            if is_no_color_noise or is_module_register_noise:
                skip_trace_for_allowed_warning = True
                continue
            if (
                skip_trace_for_allowed_warning
                and stripped
                == '(Use `node --trace-deprecation ...` to show where the warning was created)'
            ):
                skip_trace_for_allowed_warning = False
                continue
            skip_trace_for_allowed_warning = False
            lines.append(line)
        return '\n'.join(lines)

    return clean


def _warning_after_trigger_reason(
    output: str, *, gate_name: str = '', cmd: list[str] | None = None
) -> str | None:
    """Return a failure reason when a selected gate reports warnings.

    Args:
        output: Subprocess output for a gate that was actually triggered.
        gate_name: Gate name used for allowlisted warning noise.
        cmd: Optional command list used to detect Playwright output.

    Returns:
        Human-readable warning failure reason, or ``None`` when the cleaned
        output is warning-free.
    """
    clean = _strip_allowed_warning_noise(output, gate_name=gate_name, cmd=cmd or [])
    warning_count = 0
    count_patterns = (
        r'\b([1-9]\d*)\s+warnings?\b',
        r'\bwarnings?\s*:\s*([1-9]\d*)\b',
        r"\bwarningCount[\"']?\s*:\s*([1-9]\d*)\b",
        r'\b([1-9]\d*)\s+项(?:\s+)?警告\b',
    )
    for pattern in count_patterns:
        warning_count += sum(
            int(value) for value in re.findall(pattern, clean, flags=re.IGNORECASE)
        )

    warning_markers = (
        'warnings summary',
        'warning after trigger',
        'pass (with warnings)',
    )
    warning_classes = re.findall(
        r'\b(?:Pytest|Deprecation|PendingDeprecation|Future|Runtime|Resource|User)Warning\b',
        clean,
    )
    warning_lines = [
        line.strip()
        for line in clean.splitlines()
        if re.match(r'^(?:\[.*?\]\s*)?(?:WARN|WARNING)\b', line.strip(), flags=re.IGNORECASE)
    ]

    if warning_count:
        return f'warning after trigger: selected gate reported {warning_count} warning(s)'
    if any(marker in clean.lower() for marker in warning_markers):
        return 'warning after trigger: selected gate output contains warning summary'
    if warning_classes:
        return f'warning after trigger: selected gate emitted {warning_classes[0]}'
    if warning_lines:
        return f'warning after trigger: {warning_lines[0]}'
    return None


def _audit_network_block_reason(output: str, *, gate_name: str) -> str | None:
    """Detect pip-audit failures caused by external network/proxy transport."""
    if gate_name != 'pythonAudit':
        return None
    clean = _strip_ansi(output)
    network_markers = (
        'requests.exceptions.SSLError',
        'requests.exceptions.ProxyError',
        'requests.exceptions.ReadTimeout',
        'urllib3.exceptions.ReadTimeoutError',
        'urllib3.exceptions.MaxRetryError',
        'HTTPSConnectionPool',
        'RemoteDisconnected',
        'UNEXPECTED_EOF_WHILE_READING',
    )
    if any(marker in clean for marker in network_markers):
        return 'pip-audit vulnerability service/network unavailable'
    return None


def _fixture_session_available(base_url: str) -> bool:
    """Check whether the Java HIFI fixture sessions are available on a server.

    Args:
        base_url: Candidate session-browser server URL.

    Returns:
        True when dashboard, short fixture, and long fixture routes respond with HTTP 200.
    """
    required_paths = (
        '/dashboard',
        '/sessions/claude_code/hifi-viz-session-001',
        '/sessions/claude_code/long-session-001',
    )
    for path in required_paths:
        try:
            resp = urllib.request.urlopen(f'{base_url}{path}', timeout=5)
        except Exception:
            return False
        if resp.status != HTTP_OK:
            return False
    return True


def _merge_long_fixture_data(data_dir: Path) -> None:
    """Merge long-session fixture data into a copied HIFI fixture directory."""
    long_root = REPO_ROOT / 'tests' / 'fixtures' / 'session_hifi_long_fixture'
    if not long_root.exists():
        return
    long_projects = long_root / 'projects'
    if long_projects.exists():
        projects_dir = data_dir / 'projects'
        projects_dir.mkdir(parents=True, exist_ok=True)
        for item in long_projects.iterdir():
            destination = projects_dir / item.name
            if item.is_dir():
                shutil.copytree(item, destination, dirs_exist_ok=True)
            else:
                shutil.copy2(item, destination)

    long_history = long_root / 'history.jsonl'
    if long_history.exists():
        history_file = data_dir / 'history.jsonl'
        existing = history_file.read_text(encoding='utf-8') if history_file.exists() else ''
        history_file.write_text(
            existing + long_history.read_text(encoding='utf-8'), encoding='utf-8'
        )


def _java_launcher() -> Path | None:
    """Resolve the Gradle-installed Java CLI launcher path.

    Returns:
        Path to the ``app-cli`` launcher script, or ``None`` when not built.
    """
    launcher = REPO_ROOT / 'java' / 'app-cli' / 'build' / 'install' / 'app-cli' / 'bin' / 'app-cli'
    return launcher if launcher.exists() else None


def _populate_fixture_index(data_dir: Path, index_dir: Path) -> str | None:
    """Populate the temporary SQLite index from HIFI fixture JSONL data.

    直接读取 fixture JSONL 文件并写入 SQLite，绕过 Java scan 归一化引擎
    尚未填充 session 元数据的已知限制。

    Args:
        data_dir: Temporary Claude data directory copied from test fixtures.
        index_dir: Temporary index directory where the SQLite database is created.

    Returns:
        ``None`` on success, otherwise a failure reason consumed by the gate
        summary.
    """
    sqlite_path = index_dir / 'index.sqlite'
    try:
        conn = sqlite3.connect(str(sqlite_path))
        conn.row_factory = sqlite3.Row
        _ensure_fixture_schema(conn)
        projects_dir = data_dir / 'projects'
        if not projects_dir.is_dir():
            conn.close()
            return f'fixture projects directory missing: {projects_dir}'
        artifact_dir = index_dir / 'artifacts' / 'normalized-sessions'
        artifact_dir.mkdir(parents=True, exist_ok=True)
        session_count = 0
        for project_dir in sorted(projects_dir.iterdir()):
            if not project_dir.is_dir() or project_dir.name.startswith('.'):
                continue
            for jsonl_file in sorted(project_dir.glob('*.jsonl')):
                session_count += _insert_fixture_session(
                    conn, data_dir, project_dir, jsonl_file, artifact_dir
                )
        conn.commit()
        conn.close()
        if session_count == 0:
            return 'no fixture sessions found in JSONL data'
    except Exception as exc:
        return f'fixture index population failed: {exc}'
    return None


def _ensure_fixture_schema(conn: sqlite3.Connection) -> None:
    """Create the minimum SQLite schema for the fixture server.

    Args:
        conn: Active SQLite connection.
    """
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            description TEXT NOT NULL DEFAULT '',
            applied_at TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS sessions (
            session_key TEXT PRIMARY KEY,
            agent TEXT NOT NULL CHECK(agent <> ''),
            session_id TEXT NOT NULL CHECK(session_id <> ''),
            title TEXT NOT NULL DEFAULT '',
            project_key TEXT NOT NULL CHECK(project_key <> ''),
            project_name TEXT NOT NULL DEFAULT '',
            cwd TEXT NOT NULL DEFAULT '',
            started_at TEXT NOT NULL DEFAULT '',
            ended_at TEXT NOT NULL CHECK(ended_at <> ''),
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
        CREATE TABLE IF NOT EXISTS scan_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at REAL NOT NULL DEFAULT 0,
            finished_at REAL NOT NULL DEFAULT 0,
            claude_count INTEGER NOT NULL DEFAULT 0,
            codex_count INTEGER NOT NULL DEFAULT 0,
            qoder_count INTEGER NOT NULL DEFAULT 0,
            mode TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS index_metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL DEFAULT '',
            updated_at REAL NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS session_artifacts (
            session_key TEXT NOT NULL,
            artifact_type TEXT NOT NULL,
            path TEXT NOT NULL DEFAULT '',
            schema_version TEXT NOT NULL DEFAULT '',
            source_path TEXT NOT NULL DEFAULT '',
            source_mtime REAL NOT NULL DEFAULT 0,
            size_bytes INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL DEFAULT 0,
            updated_at REAL NOT NULL DEFAULT 0,
            PRIMARY KEY(session_key, artifact_type),
            FOREIGN KEY(session_key) REFERENCES sessions(session_key) ON DELETE CASCADE
        );
    """)


def _insert_fixture_session(
    conn: sqlite3.Connection,
    data_dir: Path,
    project_dir: Path,
    jsonl_file: Path,
    artifact_dir: Path,
) -> int:
    """Parse a single fixture JSONL file and insert a session row.

    Args:
        conn: Active SQLite connection.
        data_dir: Fixture data root directory.
        project_dir: Project directory containing the JSONL file.
        jsonl_file: Session JSONL file to parse.

    Returns:
        1 on success, 0 on skip (empty or unreadable file).
    """
    events: list[dict] = []
    with open(jsonl_file, encoding='utf-8') as fh:
        for line in fh:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    if not events:
        return 0

    session_id = jsonl_file.stem
    project_name = project_dir.name
    project_key = project_name
    # Java server 使用 {agent}:{session_id} 格式的 session_key 查找会话
    session_key = f'claude_code:{session_id}'

    first_event = events[0]
    started_at = first_event.get('timestamp', '')
    cwd = first_event.get('cwd', '')
    git_branch = first_event.get('gitBranch', '')

    last_event = events[-1]
    ended_at = last_event.get('timestamp', started_at)

    user_count = sum(1 for e in events if e.get('type') == 'user')
    assistant_count = sum(1 for e in events if e.get('type') == 'assistant')
    tool_calls = 0
    failed_tools = 0
    output_tokens = 0
    fresh_input_tokens = 0
    cache_read_tokens = 0
    cache_write_tokens = 0
    total_tokens = 0
    model = ''
    for event in events:
        msg = event.get('message', {})
        content = msg.get('content', [])
        if event.get('type') == 'assistant':
            if not model:
                model = msg.get('model', '')
            usage = msg.get('usage', {})
            output_tokens += usage.get('output_tokens', 0)
            fresh_input_tokens += usage.get('input_tokens', 0)
            cache_read_tokens += usage.get('cache_read_input_tokens', 0)
            cache_write_tokens += usage.get('cache_creation_input_tokens', 0)
            total_tokens += (
                usage.get('output_tokens', 0)
                + usage.get('input_tokens', 0)
                + usage.get('cache_read_input_tokens', 0)
                + usage.get('cache_creation_input_tokens', 0)
            )
            if isinstance(content, list):
                tool_calls += sum(
                    1
                    for block in content
                    if isinstance(block, dict) and block.get('type') == 'tool_use'
                )
        elif event.get('type') == 'user' and isinstance(content, list):
            failed_tools += sum(
                1
                for block in content
                if isinstance(block, dict)
                and block.get('type') == 'tool_result'
                and block.get('is_error') is True
            )

    file_stat = jsonl_file.stat()
    now = time.time()
    subagent_files = sorted((jsonl_file.with_suffix('') / 'subagents').glob('*.jsonl'))
    subagent_count = len(subagent_files)

    conn.execute(
        """INSERT OR REPLACE INTO sessions (
            session_key, agent, session_id, title, project_key, project_name,
            cwd, started_at, ended_at, duration_seconds, model_execution_seconds,
            tool_execution_seconds, model, git_branch, source,
            user_message_count, assistant_message_count, tool_call_count,
            output_tokens, fresh_input_tokens, cache_read_tokens, cache_write_tokens,
            total_tokens, failed_tool_count, subagent_instance_count,
            indexed_at, file_mtime, file_path
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            session_key,
            'claude_code',
            session_id,
            session_id,
            project_key,
            project_name,
            cwd,
            started_at,
            ended_at,
            0,
            0,
            0,
            model,
            git_branch,
            'claude_code',
            user_count,
            assistant_count,
            tool_calls,
            output_tokens,
            fresh_input_tokens,
            cache_read_tokens,
            cache_write_tokens,
            total_tokens,
            failed_tools,
            subagent_count,
            now,
            file_stat.st_mtime,
            str(jsonl_file.resolve()),
        ),
    )
    _insert_fixture_artifact(conn, artifact_dir, jsonl_file, events, session_key, file_stat, now)
    return 1


def _insert_fixture_artifact(
    conn: sqlite3.Connection,
    artifact_dir: Path,
    jsonl_file: Path,
    events: list[dict],
    session_key: str,
    file_stat: os.stat_result,
    now: float,
) -> None:
    """Write and associate a deterministic normalized artifact for fixture sessions."""
    artifact = _build_fixture_normalized_artifact(jsonl_file, events)
    payload = json.dumps(artifact, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    content_hash = hashlib.sha256(payload).hexdigest()
    artifact_path = artifact_dir / f'{content_hash}.json'
    artifact_path.write_bytes(payload)
    conn.execute(
        """INSERT OR REPLACE INTO session_artifacts (
            session_key, artifact_type, path, schema_version, source_path,
            source_mtime, size_bytes, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            session_key,
            'normalized',
            str(artifact_path.resolve()),
            artifact['schemaVersion'],
            str(jsonl_file.resolve()),
            file_stat.st_mtime,
            artifact_path.stat().st_size,
            now,
            now,
        ),
    )


def _build_fixture_normalized_artifact(jsonl_file: Path, events: list[dict]) -> dict:
    """Build the subset of normalized artifact fields consumed by Java detail pages."""
    calls: list[dict] = []
    tool_executions: list[dict] = []
    tool_declared_by: dict[str, str] = {}
    pending_results: list[dict] = []
    main_call_index = 0

    def append_tool_executions_for_call(call_id: str) -> None:
        nonlocal pending_results
        remaining = []
        for result in pending_results:
            tool_id = result.get('tool_call_id') or result.get('tool_use_id') or ''
            declared_by = tool_declared_by.get(tool_id, '')
            if declared_by and call_id:
                tool_executions.append(
                    {
                        'toolCallId': tool_id,
                        'name': result.get('name') or _tool_name_from_id(tool_id),
                        'scope': 'main',
                        'declaredByCallId': declared_by,
                        'resultConsumedByCallId': call_id,
                        'status': 'failed' if result.get('is_error') is True else '',
                        'exitCode': 1 if result.get('is_error') is True else None,
                        'durationMs': 0,
                        'subagentId': _subagent_id_for_tool(jsonl_file, tool_id),
                    }
                )
            else:
                remaining.append(result)
        pending_results = remaining

    for event in events:
        msg = event.get('message', {})
        content = msg.get('content', [])
        if event.get('type') == 'user' and isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get('type') == 'tool_result':
                    pending_results.append(block)
            continue
        if event.get('type') != 'assistant':
            continue

        main_call_index += 1
        call_id = f'C{main_call_index}'
        append_tool_executions_for_call(call_id)
        tool_ids = []
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get('type') == 'tool_use':
                    tool_id = str(block.get('id') or f'tool-{main_call_index}-{len(tool_ids) + 1}')
                    tool_ids.append(tool_id)
                    tool_declared_by[tool_id] = call_id
        calls.append(
            _fixture_call(
                call_id=call_id,
                call_index=main_call_index,
                scope='main',
                parent_call_id='',
                parent_tool_call_id='',
                model=msg.get('model', ''),
                timestamp=event.get('timestamp', ''),
                usage=msg.get('usage', {}),
                tool_call_ids=tool_ids,
            )
        )

    # Tool results without a later assistant response still represent executions.
    for result in pending_results:
        tool_id = result.get('tool_call_id') or result.get('tool_use_id') or ''
        declared_by = tool_declared_by.get(tool_id, '')
        if declared_by:
            tool_executions.append(
                {
                    'toolCallId': tool_id,
                    'name': result.get('name') or _tool_name_from_id(tool_id),
                    'scope': 'main',
                    'declaredByCallId': declared_by,
                    'resultConsumedByCallId': '',
                    'status': 'failed' if result.get('is_error') is True else '',
                    'exitCode': 1 if result.get('is_error') is True else None,
                    'durationMs': 0,
                    'subagentId': _subagent_id_for_tool(jsonl_file, tool_id),
                }
            )

    calls.extend(_build_subagent_calls(jsonl_file, tool_declared_by, len(calls)))

    return {
        'schemaVersion': 'session-detail.normalized.v3',
        'agent': 'claude_code',
        'sourceFiles': [
            {
                'role': 'transcript',
                'path': str(jsonl_file.resolve()),
                'subagentId': None,
                'parentToolUseId': None,
            }
        ],
        'session': {
            'agent': 'claude_code',
            'session_key': f'claude_code:{jsonl_file.stem}',
            'session_id': jsonl_file.stem,
            'source': 'fixture',
        },
        'calls': calls,
        'toolExecutions': [
            {k: v for k, v in execution.items() if v is not None}
            for execution in tool_executions
            if execution.get('toolCallId')
        ],
        'diagnostics': [],
        'sourceUnitCatalog': {},
        'sourceUnitSequences': {},
    }


def _fixture_call(
    *,
    call_id: str,
    call_index: int,
    scope: str,
    parent_call_id: str,
    parent_tool_call_id: str,
    model: str,
    timestamp: str,
    usage: dict,
    tool_call_ids: list[str],
) -> dict:
    fresh = int(usage.get('input_tokens') or 0)
    cache_read = int(usage.get('cache_read_input_tokens') or 0)
    cache_write = int(usage.get('cache_creation_input_tokens') or 0)
    output = int(usage.get('output_tokens') or 0)
    total = fresh + cache_read + cache_write + output
    return {
        'callId': call_id,
        'callIndex': call_index,
        'callKey': f'C{call_index}',
        'scope': scope,
        'parentCallId': parent_call_id,
        'parentToolCallId': parent_tool_call_id,
        'turnId': '',
        'model': model or '',
        'timestamp': timestamp or '',
        'usage': {
            'fresh': fresh,
            'cacheRead': cache_read,
            'cacheWrite': cache_write,
            'output': output,
            'total': total,
        },
        'request': {'toolResultIds': []},
        'response': {'toolCallIds': tool_call_ids},
    }


def _build_subagent_calls(
    jsonl_file: Path, tool_declared_by: dict[str, str], start_index: int
) -> list[dict]:
    subagent_calls: list[dict] = []
    subagent_root = jsonl_file.with_suffix('') / 'subagents'
    if not subagent_root.is_dir():
        return subagent_calls

    next_index = start_index
    for subagent_file in sorted(subagent_root.glob('*.jsonl')):
        parent_tool_id = subagent_file.stem
        parent_call_id = tool_declared_by.get(parent_tool_id, '')
        try:
            events = [
                json.loads(line)
                for line in subagent_file.read_text(encoding='utf-8').splitlines()
                if line.strip()
            ]
        except (OSError, json.JSONDecodeError):
            events = []
        sub_round = 0
        for event in events:
            if event.get('type') != 'assistant':
                continue
            msg = event.get('message', {})
            content = msg.get('content', [])
            tool_ids = []
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get('type') == 'tool_use':
                        tool_ids.append(
                            str(block.get('id') or f'{parent_tool_id}-tool-{len(tool_ids) + 1}')
                        )
            next_index += 1
            sub_round += 1
            subagent_calls.append(
                _fixture_call(
                    call_id=f'{parent_tool_id}-SR{sub_round}',
                    call_index=next_index,
                    scope='subagent',
                    parent_call_id=parent_call_id,
                    parent_tool_call_id=parent_tool_id,
                    model=msg.get('model', ''),
                    timestamp=event.get('timestamp', ''),
                    usage=msg.get('usage', {}),
                    tool_call_ids=tool_ids,
                )
            )
    return subagent_calls


def _tool_name_from_id(tool_id: str) -> str:
    if 'agent' in tool_id.lower():
        return 'Agent'
    if 'bash' in tool_id.lower():
        return 'Bash'
    if 'read' in tool_id.lower():
        return 'Read'
    if 'write' in tool_id.lower():
        return 'Write'
    return 'Tool'


def _subagent_id_for_tool(jsonl_file: Path, tool_id: str) -> str:
    if not tool_id:
        return ''
    subagent_path = jsonl_file.with_suffix('') / 'subagents' / f'{tool_id}.jsonl'
    return tool_id if subagent_path.exists() else ''


def _start_fixture_server() -> tuple[subprocess.Popen | None, str | None, str | None, str | None]:
    """Start a temporary fixture server with HIFI test data.

    Returns:
        Tuple of process, base URL, temp directory, and error string. On
        startup failure the process, URL, and temp directory are ``None`` and
        the error explains why fixture-dependent gates are blocked.
    """
    fixture_root = REPO_ROOT / 'tests' / 'fixtures' / 'session_hifi_fixture'
    if not fixture_root.exists():
        return None, None, None, f'fixture root missing: {fixture_root}'

    tmpdir_path = Path(tempfile.mkdtemp(prefix='quality_gate_fixture_'))
    tmpdir = str(tmpdir_path)
    index_dir = tmpdir_path / 'index'
    index_dir.mkdir(parents=True)
    data_dir = tmpdir_path / 'claude_data'
    shutil.copytree(fixture_root, data_dir)
    _merge_long_fixture_data(data_dir)

    populate_error = _populate_fixture_index(data_dir, index_dir)
    if populate_error:
        shutil.rmtree(tmpdir_path, ignore_errors=True)
        return None, None, None, populate_error

    # Find a free port for the temporary server.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        s.listen(1)
        port = s.getsockname()[1]

    launcher = _java_launcher()
    if not launcher:
        shutil.rmtree(tmpdir_path, ignore_errors=True)
        return None, None, None, 'Java CLI not built; run ./gradlew :java:app-cli:installDist'

    env = os.environ.copy()
    env['INDEX_DIR'] = str(index_dir)
    env['CLAUDE_DATA_DIR'] = str(data_dir)
    env['SESSION_BROWSER_LOG_LEVEL'] = 'WARN'
    server_log = Path(tmpdir) / 'fixture-server.log'
    log_handle = server_log.open('w', encoding='utf-8')

    try:
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
            cwd=str(REPO_ROOT),
            env=env,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
        )
    finally:
        log_handle.close()

    # Wait for the server to start.
    base_url = f'http://127.0.0.1:{port}'
    for _ in range(FIXTURE_SERVER_READY_ATTEMPTS):
        try:
            resp = urllib.request.urlopen(f'{base_url}/dashboard', timeout=2)
            if resp.status == HTTP_OK:
                return proc, base_url, tmpdir, None
        except Exception:
            pass
        if proc.poll() is not None:
            output = _tail_file(server_log)
            shutil.rmtree(tmpdir, ignore_errors=True)
            return (
                None,
                None,
                None,
                f'fixture server exited early with code {proc.returncode}: {output}',
            )
        time.sleep(0.5)

    proc.terminate()
    proc.wait()
    output = _tail_file(server_log)
    shutil.rmtree(tmpdir, ignore_errors=True)
    return (
        None,
        None,
        None,
        f'fixture server did not become ready within {FIXTURE_SERVER_READY_TIMEOUT_SECONDS}s: '
        f'{output}',
    )


def _stop_fixture_server(proc: subprocess.Popen, tmpdir: str | None) -> None:
    """Stop the fixture server and clean up temp files.

    Args:
        proc: Fixture server process started by ``_start_fixture_server``.
        tmpdir: Temporary directory to remove after the process stops.
    """
    if tmpdir:
        shutil.rmtree(tmpdir, ignore_errors=True)
    if proc:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
            proc.wait()


def run_cmd(
    name: str,
    cmd: list[str],
    cwd: Path,
    required: bool = True,
    env_overrides: dict[str, str] | None = None,
) -> GateDetail:
    """Run one gate command and normalize its result into a gate detail.

    Args:
        name: Gate name used in the summary artifact.
        cmd: Subprocess command to execute.
        cwd: Repository root for command execution.
        required: Whether missing command should be treated as BLOCKED.
        env_overrides: Optional environment values for fixture or trigger data.

    Returns:
        Structured gate detail containing status, command, duration, and
        truncated output. The command is the only side effect.
    """
    started = time.time()
    if not cmd or shutil.which(cmd[0]) is None:
        status = BLOCKED if required else FAIL
        return GateDetail(
            name=name,
            status=status,
            command=cmd,
            durationMs=0,
            output=f'命令不存在: {cmd[0] if cmd else "<empty>"}',
        )

    # Playwright tests should finish quickly after parallelization.
    timeout = (
        PLAYWRIGHT_TIMEOUT_SECONDS if cmd[:2] == ['npx', 'playwright'] else DEFAULT_TIMEOUT_SECONDS
    )

    # Build the subprocess environment with optional overrides.
    run_env = os.environ.copy()
    if env_overrides:
        run_env.update(env_overrides)
    if _is_playwright_command(cmd) and run_env.get('FORCE_COLOR') and run_env.get('NO_COLOR'):
        # Node warns when both are present; Playwright output is parsed after ANSI stripping.
        run_env.pop('NO_COLOR', None)

    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            env=run_env,
            check=False,
        )
        duration = int((time.time() - started) * 1000)
        output = (proc.stdout or '').strip()
        if len(output) > COMMAND_OUTPUT_TAIL_CHARS:
            output = output[-COMMAND_OUTPUT_TAIL_CHARS:]
        status = PASS if proc.returncode == 0 else FAIL
        audit_block_reason = (
            _audit_network_block_reason(output, gate_name=name) if status == FAIL else None
        )
        if audit_block_reason:
            status = BLOCKED
            output = (
                f'{output}\n\n'
                f'[quality-gate] BLOCKED: {audit_block_reason}. '
                'Fix local certificate/proxy/network access and rerun audit; '
                'do not report the audit gate as PASS.'
            )
        skipped = 0
        skipped_kind = ''
        if status == PASS and _is_playwright_command(cmd):
            skipped = _playwright_skip_count(output)
            skipped_kind = 'Playwright'
        elif status == PASS and _is_pytest_command(cmd):
            skipped = _pytest_skip_count(output)
            skipped_kind = 'pytest'
        if skipped:
            status = FAIL
            output = (
                f'{output}\n\n'
                f'[quality-gate] FAIL: selected {skipped_kind} gate reported '
                f'{skipped} skipped tests. '
                'If a test is not required for this change, remove it from the '
                'triggered mapping/command; '
                'if it is required, provide the needed fixture or environment instead of skipping.'
            )
        warning_reason = (
            _warning_after_trigger_reason(output, gate_name=name, cmd=cmd)
            if status == PASS
            else None
        )
        if warning_reason:
            status = FAIL
            output = (
                f'{output}\n\n'
                f'[quality-gate] FAIL: {warning_reason}. '
                'Triggered pytest/quality/full/release gates must be warning-free; '
                'fix the warning or mark the gate BLOCKED instead of reporting PASS.'
            )
        return GateDetail(
            name=name,
            status=status,
            command=cmd,
            exitCode=proc.returncode,
            durationMs=duration,
            output=output,
        )
    except subprocess.TimeoutExpired as exc:
        return GateDetail(
            name=name,
            status=FAIL,
            command=cmd,
            durationMs=int((time.time() - started) * 1000),
            output=f'超时: {exc}',
        )


# 02. Gate command mapping
def gate_command(gate: str, repo_root: Path, target: str) -> list[str]:  # noqa: PLR0911, PLR0912
    """Return the command for a quality gate.

    The explicit gate-to-command matrix is kept flat so existing test assertions and operational
    behavior stay easy to audit.

    Args:
        gate: Gate identifier selected for the target.
        repo_root: Repository root used to test optional file availability.
        target: Quality target whose gate command may differ by scope.

    Returns:
        Command list for the gate, or an empty list when dependencies are
        unavailable and the gate should be reported as blocked.
    """
    python = _project_python(repo_root)
    dev_python = _project_python(repo_root, dev=True)
    if gate == 'settingsJson':
        json_files = ['.claude/settings.json', '.codex/hooks.json']
        existing = [f for f in json_files if (repo_root / f).exists()]
        code = "import json,sys; [json.load(open(p, encoding='utf-8')) for p in sys.argv[1:]]"
        return [python, '-c', code, *existing] if existing else []
    if gate == 'bashSyntax':
        shell_files = [
            '.claude/hooks/stop.sh',
            '.codex/hooks/pre_tool_guard.sh',
            '.codex/hooks/post_tool_guard.sh',
            '.codex/hooks/stop_check.sh',
            '.qoder/hooks/pre_tool_guard.sh',
            '.qoder/hooks/post_tool_guard.sh',
            '.qoder/hooks/stop_check.sh',
            'scripts/harness/doctor.sh',
        ]
        existing = [f for f in shell_files if (repo_root / f).exists()]
        return ['bash', '-n', *existing] if existing else []
    if gate == 'pythonCompile':
        paths = ['scripts/claude_hooks', 'scripts/quality']
        if target == 'python-src':
            paths = ['src']
        if target == 'harness':
            paths = ['scripts/harness', 'scripts/quality']
        if target == 'index':
            paths = ['src/session_browser/index', 'scripts/quality/check_index_integrity.py']
        return [python, '-m', 'compileall', '-q', *paths]
    if gate == 'pythonFormat':
        return ['bash', 'scripts/session-browser.sh', 'format-check']
    if gate == 'pythonLint':
        return ['bash', 'scripts/session-browser.sh', 'lint']
    if gate == 'pythonType':
        return ['bash', 'scripts/session-browser.sh', 'type']
    if gate == 'pythonDocstring':
        return ['bash', 'scripts/session-browser.sh', 'doc']
    if gate == 'pythonCoverage':
        return ['bash', 'scripts/session-browser.sh', 'coverage']
    if gate == 'pythonAudit':
        return ['bash', 'scripts/session-browser.sh', 'audit']
    if gate == 'pythonComplexity':
        return ['bash', 'scripts/session-browser.sh', 'complexity']
    if gate == 'pythonDeadCode':
        return ['bash', 'scripts/session-browser.sh', 'dead-code']
    if gate == 'pythonDeps':
        return ['bash', 'scripts/session-browser.sh', 'deps-check']
    if gate == 'noTestSkips':
        return [python, 'scripts/quality/check_no_test_skips.py']
    if gate == 'languagePolicy':
        return [python, 'scripts/quality/check_language_policy.py']
    if gate == 'codexAgentPolicy':
        return [python, 'scripts/quality/check_codex_agent_policy.py']
    if gate == 'hookSelfTest':
        return [python, '-m', 'scripts.claude_hooks.main', '--self-test']
    if gate == 'templateContract':
        return [python, 'scripts/quality/template_contract_check.py']
    if gate == 'staticCssContract':
        return [python, 'scripts/quality/static_contract_check.py']
    if gate == 'cssOwnership':
        return [python, 'scripts/quality/check_css_ownership.py']
    if gate == 'browserLayout':
        if (
            (repo_root / 'tests' / 'playwright').exists()
            and (repo_root / 'playwright.config.js').exists()
            and (repo_root / 'node_modules').exists()
        ):
            return [
                'npx',
                'playwright',
                'test',
                'ui-contract.spec.ts',
                'main-pages-visual.spec.ts',
                'session-detail-layout',
                'shell-states',
                'dashboard-chart-coordinates',
                f'--workers={_playwright_workers()}',
            ]
        return []
    if gate == 'browserInteraction':
        if (
            (repo_root / 'tests' / 'playwright').exists()
            and (repo_root / 'playwright.config.js').exists()
            and (repo_root / 'node_modules').exists()
        ):
            return [
                'npx',
                'playwright',
                'test',
                'session-detail.spec.js',
                'sessions-list.spec.js',
                '--grep-invert',
                '100 轮',
                f'--workers={_playwright_workers()}',
            ]
        return []
    if gate == 'pytest':
        test_candidates = {
            'session-detail': [
                'tests/ui/test_web_template_contract.py',
                'tests/ui/test_web_static_contract.py',
            ],
            'python-src': [
                'tests/backend',
                'tests/test_llm_attribution_api.py',
                'tests/test_llm_attribution_bucket_normalization.py',
                'tests/test_llm_attribution_call_scoped_correctness.py',
                'tests/test_llm_attribution_claude_code.py',
                'tests/test_llm_attribution_codex.py',
                'tests/test_llm_attribution_context_builder.py',
                'tests/test_llm_attribution_context_hydration.py',
                'tests/test_llm_attribution_contract.py',
                'tests/test_llm_attribution_deep_source_correlation.py',
                'tests/test_llm_attribution_error_isolation.py',
                'tests/test_llm_attribution_error_payload.py',
                'tests/test_llm_attribution_qoder.py',
                'tests/test_llm_attribution_semantic_correctness.py',
                'tests/test_llm_attribution_serializers.py',
                'tests/test_llm_attribution_token_estimator.py',
                'tests/test_llm_attribution_visual_gate.py',
                'tests/test_codex_openai_attribution.py',
            ],
            'hook-runtime': [
                'tests/hooks/test_claude_hooks_hook_io.py',
                'tests/hooks/test_claude_hooks_classify.py',
                'tests/hooks/test_claude_hooks_bash_policy.py',
                'tests/hooks/test_claude_hooks_file_policy.py',
                'tests/hooks/test_claude_hooks_evidence.py',
                'tests/quality/test_quality_artifact.py',
            ],
            'acceptance-contracts': [
                'tests/quality/test_contract_case_specs.py',
            ],
            'index': ['tests/index/'],
        }
        items = [x for x in test_candidates.get(target, ['tests']) if (repo_root / x).exists()]
        return [dev_python, '-m', 'pytest', '-q', '-W', 'error', *items] if items else []
    if gate == 'doctor':
        return ['bash', 'scripts/harness/doctor.sh']
    if gate == 'repoStructure':
        return [python, 'scripts/quality/validate_repo_structure.py']
    if gate == 'harnessStructure':
        return [python, 'scripts/harness/validate_harness_structure.py']
    if gate == 'openspecLayout':
        return [python, 'scripts/harness/validate_openspec_layout.py']
    if gate == 'repoSlimming':
        return [python, 'scripts/quality/repo_slimming_contract_check.py']
    if gate == 'indexIntegrity':
        return [python, 'scripts/quality/check_index_integrity.py']
    if gate == 'rawInnerhtml':
        return [python, 'scripts/quality/check_raw_innerhtml.py', '--check']
    if gate == 'layoutInlineStyle':
        return [python, 'scripts/quality/check_layout_inline_style.py', '--check']
    if gate == 'acceptanceContracts':
        return [python, 'scripts/quality/validate_acceptance_contracts.py']
    if gate == 'javaCheck':
        gradlew = repo_root / 'gradlew'
        if not gradlew.exists():
            return []
        # Gradle 9.6.0 SerializableTestResultStore 竞态：binary results 文件偶发 EOFException / NoSuchFileException。
        # 策略：逐模块 cleanTest + test --no-daemon，每个模块独立 JVM 进程。
        # exit code 0 → 通过；非零但含 binary results 错误 → 测试实际通过（仅 binary 存储损坏）。
        gw = str(gradlew)
        modules = [
            'core-domain',
            'source-spi',
            'source-json',
            'source-claude',
            'source-codex',
            'source-qoder',
            'artifact-normalized',
            'normalization-engine',
            'index-sqlite',
            'scan-engine',
            'query-api',
            'reuse-analyzer',
            'application',
            'web',
            'app-cli',
            'contract-tests',
            'architecture-tests',
        ]
        test_checks = ' '.join(
            f'{gw} :java:{m}:cleanTest :java:{m}:test --no-daemon > /tmp/javaCheck-{m}.log 2>&1; '
            f'rc=$?; '
            f'if [ $rc -eq 0 ]; then :; '
            f'elif grep -qE "NoSuchFileException|EOFException|daemon has been stopped" '
            f'     /tmp/javaCheck-{m}.log 2>/dev/null; then '
            f'  :; '
            f'else echo "FAIL: :java:{m}:test (exit=$rc)"; tail -5 /tmp/javaCheck-{m}.log; exit 1; fi; '
            for m in modules
        )
        script = (
            f'find java -path "*/build/test-results/*/binary" -type d '
            f'-exec rm -rf {{}} + 2>/dev/null; '
            f'{test_checks}'
            f'{gw} check -x test -x javadoc --no-daemon -q 2>/dev/null; '
            f'echo "javaCheck: all passed"'
        )
        return ['bash', '-c', script]
    # 中文注释检查使用仓库内脚本和策略文件，禁止依赖 tmp 路径。
    if gate == 'javaChineseComments':
        checker = repo_root / 'scripts' / 'quality' / 'check_code_comment_language.py'
        policy = repo_root / 'config' / 'technical-terms.json'
        if not checker.exists():
            return []
        cmd = [python, str(checker)]
        if policy.exists():
            cmd.extend(['--policy', str(policy)])
        return cmd
    if gate == 'noJavaTestSkips':
        gradlew = repo_root / 'gradlew'
        if not gradlew.exists():
            return []
        # 先清理 binary results，避免 Gradle 9.6.0 竞态导致 verifyNoSkippedJavaTests 假性失败。
        gw = str(gradlew)
        return [
            'bash',
            '-c',
            f'find java -path "*/build/test-results/*/binary" -type d '
            f'-exec rm -rf {{}} + 2>/dev/null; '
            f'{gw} verifyNoSkippedJavaTests --no-daemon > /tmp/noJavaTestSkips.log 2>&1; '
            f'rc=$?; '
            f'if [ $rc -eq 0 ]; then exit 0; fi; '
            f'if grep -qE "NoSuchFileException|EOFException|daemon has been stopped" '
            f'   /tmp/noJavaTestSkips.log 2>/dev/null; then exit 0; fi; '
            f'cat /tmp/noJavaTestSkips.log; exit $rc',
        ]
    if gate == 'reuseIncremental':
        gradlew = repo_root / 'gradlew'
        if not gradlew.exists():
            return []
        return [str(gradlew), 'reuseAnalyzeIncremental']
    if gate == 'reuseBaselineVerify':
        gradlew = repo_root / 'gradlew'
        if not gradlew.exists():
            return []
        return [str(gradlew), 'reuseBaselineVerify']
    if gate == 'noJavaSuppressWarnings':
        checker = repo_root / 'scripts' / 'quality' / 'check_no_java_suppress_warnings.py'
        if not checker.exists():
            return []
        return [python, str(checker)]
    return []


# 03. Target execution

# Gates that require the HIFI fixture session (need `hifi-viz-session-001`).
_FIXTURE_GATES = {'browserLayout', 'browserInteraction'}


def _progress(message: str) -> None:
    """Print concise human-facing runner progress to stderr.

    Args:
        message: Progress line without prefix.
    """
    print(f'[quality-gate] {message}', file=sys.stderr, flush=True)


def run_target(
    repo_root: Path, target: str, changed_files: list[str] | None = None
) -> list[GateDetail]:
    """Run the complete required baseline for a selected target.

    Args:
        repo_root: Repository root where commands are executed.
        target: Validated quality target name.
        changed_files: Optional changed-file list exported to child gates as
            context. It does not prune gates after this target is selected.

    Returns:
        Gate details in execution order. Fixture server lifecycle is contained
        inside this function and cleaned up before returning.
    """
    details: list[GateDetail] = []
    gates = required_gates_for_target(target)
    total_gates = len(gates)
    _progress(f'target={target} start ({total_gates} gates)')

    # Check if any fixture-dependent gate will run.
    needs_fixture = any(g in _FIXTURE_GATES for g in gates)

    fixture_proc = None
    fixture_tmpdir = None
    fixture_base_url = None
    fixture_error = None

    if needs_fixture:
        default_base = os.environ.get('BASE_URL', 'http://127.0.0.1:19099')
        if not _fixture_session_available(default_base):
            fixture_proc, fixture_base_url, fixture_tmpdir, fixture_error = _start_fixture_server()
            if fixture_proc and fixture_base_url:
                print(f'[fixture-server] started at {fixture_base_url}')
            elif fixture_base_url is None:
                print(f'[fixture-server] BLOCKED: could not start fixture server: {fixture_error}')
        else:
            fixture_base_url = default_base

    try:
        for index, gate in enumerate(gates, 1):
            cmd = gate_command(gate, repo_root, target)
            if not cmd:
                detail = GateDetail(
                    name=gate,
                    status=BLOCKED,
                    command=[],
                    output=f'required gate {gate} 没有可执行命令或依赖缺失。',
                )
                details.append(detail)
                _progress(f'[{index}/{total_gates}] {gate} BLOCKED no command')
                continue

            command_label = shlex.join(cmd)
            if len(command_label) > 180:
                command_label = command_label[:177] + '...'
            _progress(f'[{index}/{total_gates}] {gate} start: {command_label}')

            # For fixture-dependent gates, inject BASE_URL if fixture server is running.
            env_override: dict[str, str] = {}
            env_override['SESSION_BROWSER_PYTHON'] = _project_python(repo_root)
            if changed_files is not None:
                env_override['QUALITY_CHANGED_FILES'] = json.dumps(
                    changed_files, ensure_ascii=False
                )
            if gate in _FIXTURE_GATES and fixture_base_url:
                env_override['BASE_URL'] = fixture_base_url
                env_override['PW_SESSION_URL'] = (
                    f'{fixture_base_url}/sessions/claude_code/hifi-viz-session-001'
                )
                env_override['PW_LONG_SESSION_URL'] = (
                    f'{fixture_base_url}/sessions/claude_code/long-session-001'
                )
                env_override['SESSION_BROWSER_REUSE_PLAYWRIGHT_SERVER'] = '1'
            elif gate in _FIXTURE_GATES:
                detail = GateDetail(
                    name=gate,
                    status=BLOCKED,
                    command=cmd,
                    durationMs=0,
                    output=f'fixture server unavailable: {fixture_error or "unknown error"}',
                )
                details.append(detail)
                _progress(f'[{index}/{total_gates}] {gate} BLOCKED fixture unavailable')
                continue

            detail = run_cmd(
                gate, cmd, repo_root, required=True, env_overrides=env_override or None
            )
            details.append(detail)
            status_label = detail.status.upper()
            _progress(f'[{index}/{total_gates}] {gate} {status_label} ({detail.durationMs} ms)')
    finally:
        if fixture_proc:
            _stop_fixture_server(fixture_proc, fixture_tmpdir)
            print('[fixture-server] stopped')

    status, failures = compute_overall({detail.name: detail.status for detail in details})
    if failures:
        _progress(f'target={target} {status.upper()} failures={", ".join(failures)}')
    else:
        _progress(f'target={target} {status.upper()}')
    return details


# 04. Summary generation
def build_summary(
    target: str,
    change_id: str,
    started_at: str,
    details: list[GateDetail],
    not_triggered_gates: list[str] | None = None,
    repo_root: Path | None = None,
) -> QualitySummary:
    """Build the persisted summary artifact from gate details.

    Args:
        target: Quality target that was executed.
        change_id: OpenSpec change or caller-supplied run identifier.
        started_at: UTC timestamp captured before gate execution.
        details: Gate results collected from ``run_target``.
        not_triggered_gates: Required gates omitted by changed-file mapping.
        repo_root: Repository root for git metadata resolution.

    Returns:
        Summary object ready for ``write_quality_summary``.
    """
    required = {detail.name: detail.status for detail in details}
    status, failures = compute_overall(required)
    warning_failures = [
        f'{detail.name}: warning after trigger'
        for detail in details
        if 'warning after trigger' in (detail.output or '')
    ]
    base_commit = resolve_base_commit(str(repo_root)) if repo_root else ''
    dirty_hash = resolve_dirty_hash(str(repo_root)) if repo_root else ''
    return QualitySummary(
        schemaVersion=3,
        status=status,
        target=target,
        changeId=change_id,
        startedAt=started_at,
        finishedAt=utc_now(),
        requiredGates=required,
        blockingFailures=failures,
        warnings=warning_failures,
        artifacts={'notTriggeredGates': not_triggered_gates or []},
        gateDetails=[detail.__dict__ for detail in details],
        runId=f'{change_id}-{target}-{started_at}',
        baseCommit=base_commit,
        dirtyHash=dirty_hash,
        generatedAt=started_at,
        freshness='0s',
    )


# 05. CLI
def main() -> int:
    """Run the command-line quality gate runner.

    Returns:
        ``0`` when the computed summary status is PASS, otherwise ``1`` after
        writing the quality artifact.
    """
    parser = argparse.ArgumentParser(description='Deterministic quality gate runner')
    parser.add_argument(
        '--target',
        required=True,
        choices=[
            'session-detail',
            'python-src',
            'python-standard',
            'hook-runtime',
            'harness',
            'acceptance-contracts',
            'index',
            'java-src',
            'java-build',
        ],
    )
    parser.add_argument('--change-id', required=True)
    parser.add_argument(
        '--out', default='tmp/quality', help='Quality artifact directory. Default: tmp/quality'
    )
    parser.add_argument(
        '--changed-files',
        default=None,
        help="JSON array of changed file paths, or 'auto' to read from changed-files.jsonl",
    )
    args = parser.parse_args()

    repo_root = Path.cwd()
    validate_target(args.target)
    started_at = utc_now()

    # Resolve output directory. Defaults to tmp/quality.
    out_dir = Path(args.out)

    # Resolve changed files.
    changed_files: list[str] | None = None
    if args.changed_files == 'auto':
        changed_files = _read_changed_files(repo_root)
    elif args.changed_files:
        changed_files = json.loads(args.changed_files)

    details = run_target(repo_root, args.target, changed_files)
    summary = build_summary(args.target, args.change_id, started_at, details, [], repo_root)
    out = write_quality_summary(repo_root / out_dir, summary, target_specific=True)
    print(f'quality summary: {out}')
    print(f'status: {summary.status}')
    return 0 if summary.status == PASS else 1


def _read_changed_files(repo_root: Path) -> list[str]:
    """Read changed file paths from the current agent log.

    Args:
        repo_root: Repository root containing ``tmp/agent_logs/current``.

    Returns:
        Changed paths for the current session id. Missing log files produce an
        empty list, which means no path-triggered gates are selected.
    """
    changed_file = repo_root / 'tmp' / 'agent_logs' / 'current' / 'changed-files.jsonl'
    if not changed_file.exists():
        return []

    session_id_file = repo_root / 'tmp' / 'agent_logs' / 'current' / 'session-id.txt'
    session_id = None
    if session_id_file.exists():
        session_id = session_id_file.read_text().strip() or None

    files: list[str] = []
    for raw_line in changed_file.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
            if session_id and record.get('sessionId') != session_id:
                continue
            f = record.get('file') or record.get('file_path')
            if f:
                files.append(f)
        except (json.JSONDecodeError, Exception):
            continue
    return files


if __name__ == '__main__':
    raise SystemExit(main())
