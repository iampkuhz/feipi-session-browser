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
import importlib
import json
import os
import re
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
    applicable_gates_for_target,
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
                    r'^\(node:\d+\)\s+\[DEP0205\]\s+DeprecationWarning:\s+'
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
                == '(Use `node --trace-warnings ...` to show where the warning was created)'
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


def _fixture_session_available(base_url: str) -> bool:
    """Check whether the HIFI fixture session is available on a server.

    Args:
        base_url: Candidate session-browser server URL.

    Returns:
        True when the fixture detail route responds with HTTP 200.
    """
    try:
        resp = urllib.request.urlopen(
            f'{base_url}/sessions/claude_code/hifi-viz-session-001', timeout=5
        )
        return resp.status == HTTP_OK
    except Exception:
        return False


def _populate_fixture_index(data_dir: Path, sqlite_path: Path) -> str | None:
    """Populate the temporary SQLite index from the HIFI fixture data.

    Args:
        data_dir: Temporary Claude data directory copied from test fixtures.
        sqlite_path: SQLite database path created for the fixture server.

    Returns:
        ``None`` on success, otherwise a failure reason consumed by the gate
        summary. The function writes only inside the temporary fixture tree.
    """
    try:
        sys.path.insert(0, str(REPO_ROOT / 'src'))
        os.environ['CLAUDE_DATA_DIR'] = str(data_dir)
        if 'session_browser.config' in sys.modules:
            importlib.reload(sys.modules['session_browser.config'])
        for module_name in list(sys.modules):
            if module_name.startswith('session_browser.sources'):
                del sys.modules[module_name]

        indexer = importlib.import_module('session_browser.index.indexer')
        claude_source = importlib.import_module('session_browser.sources.claude')

        conn = sqlite3.connect(sqlite_path)
        conn.row_factory = sqlite3.Row
        indexer.init_schema(conn)
        for summary in claude_source.scan_all_sessions():
            indexer.upsert_session(conn, summary)
        conn.commit()
        conn.close()
    except Exception:
        return 'failed to populate fixture index'
    return None


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
    sqlite_path = index_dir / 'index.sqlite'
    data_dir = tmpdir_path / 'claude_data'
    shutil.copytree(fixture_root, data_dir)

    populate_error = _populate_fixture_index(data_dir, sqlite_path)
    if populate_error:
        shutil.rmtree(tmpdir_path, ignore_errors=True)
        return None, None, None, populate_error

    # Find a free port for the temporary server.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        s.listen(1)
        port = s.getsockname()[1]

    env = os.environ.copy()
    env['PYTHONPATH'] = str(REPO_ROOT / 'src')
    env['INDEX_DIR'] = str(index_dir)
    env['CLAUDE_DATA_DIR'] = str(data_dir)
    env['SERVER_HOST'] = '127.0.0.1'
    env['SERVER_PORT'] = str(port)
    env['SESSION_BROWSER_LOG_LEVEL'] = 'WARNING'
    server_log = Path(tmpdir) / 'fixture-server.log'
    log_handle = server_log.open('w', encoding='utf-8')

    try:
        proc = subprocess.Popen(
            [
                _project_python(REPO_ROOT),
                '-m',
                'session_browser',
                'serve',
                '--allow-empty',
                '--no-scan',
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
        skipped = (
            _playwright_skip_count(output) if status == PASS and _is_playwright_command(cmd) else 0
        )
        if skipped:
            status = FAIL
            output = (
                f'{output}\n\n'
                f'[quality-gate] FAIL: selected Playwright gate reported {skipped} skipped tests. '
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
        return [str(gradlew), 'check']
    if gate == 'javaChineseComments':
        terms_file = repo_root / 'tmp' / 'feipi-java-migration-final' / 'terminology' / 'java-comment-terms.txt'
        checker = repo_root / 'tmp' / 'feipi-java-migration-final' / 'tools' / 'validate_java_chinese_comments.py'
        if not checker.exists() or not terms_file.exists():
            return []
        return [
            python, str(checker),
            '--root', str(repo_root / 'java'),
            '--root', str(repo_root / 'build-logic'),
            '--terms', str(terms_file),
        ]
    if gate == 'noJavaTestSkips':
        gradlew = repo_root / 'gradlew'
        if not gradlew.exists():
            return []
        return [str(gradlew), 'verifyNoSkippedJavaTests']
    return []


# 03. Target execution

# Gates that require the HIFI fixture session (need `hifi-viz-session-001`).
_FIXTURE_GATES = {'browserLayout', 'browserInteraction'}


def run_target(
    repo_root: Path, target: str, changed_files: list[str] | None = None
) -> list[GateDetail]:
    """Run all applicable gates for a target and collect gate details.

    Args:
        repo_root: Repository root where commands are executed.
        target: Validated quality target name.
        changed_files: Optional changed-file list used to narrow triggered
            gates and exported to child gates.

    Returns:
        Gate details in execution order. Fixture server lifecycle is contained
        inside this function and cleaned up before returning.
    """
    details: list[GateDetail] = []

    # Check if any fixture-dependent gate will run.
    needs_fixture = any(
        g in _FIXTURE_GATES for g in applicable_gates_for_target(target, changed_files)
    )

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
        for gate in applicable_gates_for_target(target, changed_files):
            cmd = gate_command(gate, repo_root, target)
            if not cmd:
                details.append(
                    GateDetail(
                        name=gate,
                        status=BLOCKED,
                        command=[],
                        output=f'required gate {gate} 没有可执行命令或依赖缺失。',
                    )
                )
                continue

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
                env_override['SESSION_BROWSER_REUSE_PLAYWRIGHT_SERVER'] = '1'
            elif gate in _FIXTURE_GATES:
                details.append(
                    GateDetail(
                        name=gate,
                        status=BLOCKED,
                        command=cmd,
                        durationMs=0,
                        output=f'fixture server unavailable: {fixture_error or "unknown error"}',
                    )
                )
                continue

            details.append(
                run_cmd(gate, cmd, repo_root, required=True, env_overrides=env_override or None)
            )
    finally:
        if fixture_proc:
            _stop_fixture_server(fixture_proc, fixture_tmpdir)
            print('[fixture-server] stopped')

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

    not_triggered_gates: list[str] = []
    if changed_files is not None:
        selected = set(applicable_gates_for_target(args.target, changed_files))
        not_triggered_gates = [
            gate for gate in required_gates_for_target(args.target) if gate not in selected
        ]
        if not_triggered_gates:
            print(
                '[run_quality_gate] not triggered gates: ' + ', '.join(not_triggered_gates),
                file=sys.stderr,
            )

    details = run_target(repo_root, args.target, changed_files)
    summary = build_summary(args.target, args.change_id, started_at, details, not_triggered_gates, repo_root)
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
