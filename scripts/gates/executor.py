#!/usr/bin/env python3
"""执行不可变 GatePlan 中的命令组，不负责规划、fixture 构造或 CLI 编排。"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from functools import lru_cache
from pathlib import Path

from scripts.agent_runtime import locks as resource_lock
from scripts.agent_runtime import paths as runtime_paths
from scripts.agent_runtime.session.contract import resolve_runtime_root
from scripts.gates.catalog import CATALOG_VERSION, gate_by_name
from scripts.gates.model import (
    ChangedFilesInput,
    CommandGroup,
    ExecutionPlan,
    GatePlan,
    GateSpec,
    PlannedGate,
)
from scripts.gates.planner import (
    applicable_gates_for_target,
    required_gates_for_target,
    target_parallel_meta,
)
from scripts.gates.report import (
    BLOCKED,
    FAIL,
    PASS,
    GateDetail,
)
from scripts.harness.python_env import resolve_python

PLAYWRIGHT_COMMAND_MIN_PARTS = 3
PLAYWRIGHT_MIN_WORKERS = 8
PLAYWRIGHT_TIMEOUT_SECONDS = 120
DEFAULT_TIMEOUT_SECONDS = 300
MODULE_CHECK_TIMEOUT_SECONDS = 10
COMMAND_OUTPUT_TAIL_CHARS = 4000
MAX_PARALLEL_GROUPS = 4


# 返回当前运行隔离的临时目录。
def _run_tmp_dir(repo_root: Path, name: str) -> Path:
    """参数：
        repo_root: 仓库根目录。
        name: run tmp 子目录名称。

    返回：
        run-scoped tmp 子目录路径。
    """
    run_id = (
        os.environ.get('FEIPI_RUN_ID') or os.environ.get('FEIPI_SESSION_ID') or f'pid-{os.getpid()}'
    )
    root = (
        Path(os.environ.get('FEIPI_RUN_TMPDIR', '')).expanduser()
        if os.environ.get('FEIPI_RUN_TMPDIR')
        else resolve_runtime_root(repo_root) / 'runs' / run_id / 'tmp'
    )
    path = root / name
    path.mkdir(parents=True, exist_ok=True)
    return path


# 维护relative existing 文件。
def _relative_existing_files(repo_root: Path, patterns: list[str]) -> list[str]:
    """参数：
        repo_root: 仓库根目录。
        patterns: 匹配用的 glob pattern 列表。

    返回：
        稳定排序且去重后的 repository-relative 文件路径列表。
    """
    result: list[str] = []
    seen: set[str] = set()
    for pattern in patterns:
        for path in sorted(repo_root.glob(pattern)):
            if not path.is_file():
                continue
            rel = path.relative_to(repo_root).as_posix()
            if rel not in seen:
                seen.add(rel)
                result.append(rel)
    return result


# 维护Python 候选项。
def _python_candidates(repo_root: Path) -> list[str]:
    """参数：
        repo_root: 仓库根目录。

    返回：
        结果列表。
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


# 记录当前 Python 是否支持模块执行。
def _python_supports_modules(executable: str, repo_root: Path, modules: tuple[str, ...]) -> bool:
    """参数：
        executable: 待探测的 Python executable 名称或路径。
        repo_root: subprocess 工作目录使用的 repo root。
        modules: 需要导入验证的 module 名称。

    返回：
        满足条件时返回 true，否则返回 false。
    """
    if shutil.which(executable) is None:
        return False

    env = os.environ.copy()
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
    # 解析和 cache the project Python用于repeated gate 命令。
    return proc.returncode == 0


# 维护project Python cached。
@lru_cache(maxsize=8)
def _project_python_cached(repo_root: str, modules: tuple[str, ...]) -> str:
    """参数：
        repo_root: 仓库根目录。
        modules: 需要导入验证的 module 名称。

    返回：
        项目 Python executable 路径。
    """
    root = Path(repo_root)
    resolved = resolve_python(root)
    if not modules or _python_supports_modules(resolved, root, modules):
        return resolved
    for candidate in _python_candidates(root):
        if candidate != resolved and _python_supports_modules(candidate, root, modules):
            return candidate
    required = ', '.join(modules)
    raise SystemExit(f'未找到包含开发依赖的 Python 解释器: {required}')


# 维护project Python。
def _project_python(repo_root: Path, *, dev: bool = False) -> str:
    """参数：
        repo_root: 仓库根目录。
        dev: 是否需要 pytest 等开发依赖。

    返回：
        项目环境使用的 executable 路径。
    """
    modules = ('pytest',) if dev else ()
    return _project_python_cached(str(repo_root), modules)


# 维护Playwright workers。
def _playwright_workers() -> int:
    """返回：
    从环境变量读取的 worker 数量，且不低于 gate 最小值。
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


# 维护tail 文件。
def _tail_file(path: Path, max_chars: int = 2000) -> str:
    """参数：
        path: subprocess gate fixture 产生的日志文件路径。
        max_chars: 摘要中包含的最大尾部字符数。

    返回：
        去除首尾空白后的日志尾部；无法读取时返回空字符串。
    """
    try:
        text = path.read_text(encoding='utf-8', errors='replace')
    except OSError:
        return ''
    return text[-max_chars:].strip()


_ANSI_RE = re.compile(r'\x1b\[[0-9;]*m')
_GRADLE_TASK_RE = re.compile(
    r'^> Task (?P<task>:\S+?)(?: (?P<outcome>UP-TO-DATE|FROM-CACHE|NO-SOURCE|SKIPPED|FAILED))?$',
    flags=re.MULTILINE,
)


# 维护去除 ANSI。
def _strip_ansi(text: str) -> str:
    """参数：
        text: 原始 subprocess 输出。

    返回：
        不含 terminal color sequences 的输出文本。
    """
    return _ANSI_RE.sub('', text)


def _gradle_task_outcomes(output: str) -> dict[str, str]:
    """从完整 plain console 输出提取稳定 Gradle task outcome。"""
    return {
        match.group('task'): match.group('outcome') or 'EXECUTED'
        for match in _GRADLE_TASK_RE.finditer(_strip_ansi(output))
    }


# 判断是否Playwright 命令。
def _is_playwright_command(cmd: list[str]) -> bool:
    """参数：
        cmd: gate 命令矩阵中的 subprocess 命令列表。

    返回：
        命令以 ``npx playwright test`` 开头时返回 true。
    """
    return (
        len(cmd) >= PLAYWRIGHT_COMMAND_MIN_PARTS
        and Path(cmd[0]).name == 'npx'
        and cmd[1:3] == ['playwright', 'test']
    )


# 维护Playwright skip count。
def _playwright_skip_count(output: str) -> int:
    """参数：
        output: 原始或 ANSI-colored Playwright 输出。

    返回：
        Playwright 输出中所有 ``N skipped`` 计数的总和。
    """
    clean = _strip_ansi(output)
    matches = re.findall(r'\b(\d+)\s+skipped\b', clean)
    return sum(int(value) for value in matches)


# 判断是否pytest 命令。
def _is_pytest_command(cmd: list[str]) -> bool:
    """参数：
        cmd: 待执行的命令。

    返回：
        满足条件时返回 true，否则返回 false。
    """
    if not cmd:
        return False
    executable = Path(cmd[0]).name
    if executable == 'pytest':
        return True
    return len(cmd) >= 3 and executable.startswith('python') and cmd[1:3] == ['-m', 'pytest']


# 维护pytest skip count。
def _pytest_skip_count(output: str) -> int:
    clean = _strip_ansi(output)
    matches = re.findall(r'\b(\d+)\s+skipped\b', clean)
    return sum(int(value) for value in matches)


# 移除策略明确允许的 warning 噪声。
def _strip_allowed_warning_noise(output: str, *, gate_name: str, cmd: list[str]) -> str:
    """参数：
        output: 选中 gate 的原始 subprocess 输出。
        gate_name: 用于应用 gate 专用 allowlist 噪声的名称。
        cmd: 用于识别 Playwright 输出的命令列表。

    返回：
        已移除 allowlist 警告-like metadata 的输出。
    """
    clean = _strip_ansi(output)

    is_css_ownership = any(Path(part).name == 'check_css_ownership.py' for part in cmd)
    if is_css_ownership:
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
                or re.match(
                    r'^\d+\]\s+DeprecationWarning:\s+'
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

    # 返回一个失败项 reason 当 a selected gate reports warning。
    return clean


# 记录触发后的 warning 原因。
def _warning_after_trigger_reason(
    output: str, *, gate_name: str = '', cmd: list[str] | None = None
) -> str | None:
    """参数：
        output: Subprocess 输出用于a gate that was actually triggered。
        gate_name: gate 名称。
        cmd: 可选命令 列表 used到detect Playwright 输出。

    返回：
        人类可读的 警告 失败项 reason, 或 ``None`` 当 cleaned。 输出 is 警告-free。
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


# 审计network 阻断 reason。
def _audit_network_block_reason(output: str, *, network_failure: str) -> str | None:
    """审计network 阻断 reason。"""
    if network_failure != 'blocked':
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
    # 检查是否the Java HIFI fixture sessions are 可用 on a server。
    return None


# 维护fixture session 可用。
def run_cmd(
    name: str,
    cmd: list[str],
    cwd: Path,
    required: bool = True,
    env_overrides: dict[str, str] | None = None,
    timeout_seconds: int | None = None,
    network_failure: str = 'fail',
) -> GateDetail:
    """参数：
        name: 条目名称。
        cmd: Subprocess 命令到execute。
        cwd: repo root用于命令 execution。
        required: 是否缺失 命令 should be treated as BLOCKED。
        env_overrides: 可选environment 值用于fixture 或 trigger data。
        timeout_seconds: 当前 target 声明的命令超时秒数。

    返回：
        结构化 gate detail containing 状态, 命令, duration, 和。 t运行cated 输出. 命令 is 仅 side effect。
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

    default_timeout = timeout_seconds or DEFAULT_TIMEOUT_SECONDS
    timeout = PLAYWRIGHT_TIMEOUT_SECONDS if cmd[:2] == ['npx', 'playwright'] else default_timeout

    # 构建the subprocess environment带可选 overrides。
    run_env = os.environ.copy()
    if env_overrides:
        run_env.update(env_overrides)
    if _is_playwright_command(cmd) and run_env.get('FORCE_COLOR') and run_env.get('NO_COLOR'):
        run_env.pop('NO_COLOR', None)

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=run_env,
            start_new_session=True,
        )
        try:
            full_output, _ = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                full_output, _ = proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                full_output, _ = proc.communicate()
            return GateDetail(
                name=name,
                status=FAIL,
                command=cmd,
                durationMs=int((time.time() - started) * 1000),
                output=f'超时: command exceeded {timeout}s\n{full_output or ""}',
            )
        duration = int((time.time() - started) * 1000)
        full_output = (full_output or '').strip()
        output = full_output
        if len(output) > COMMAND_OUTPUT_TAIL_CHARS:
            output = output[-COMMAND_OUTPUT_TAIL_CHARS:]
        status = PASS if proc.returncode == 0 else FAIL
        audit_block_reason = (
            _audit_network_block_reason(full_output, network_failure=network_failure)
            if status == FAIL
            else None
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
            skipped = _playwright_skip_count(full_output)
            skipped_kind = 'Playwright'
        elif status == PASS and _is_pytest_command(cmd):
            skipped = _pytest_skip_count(full_output)
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
            _warning_after_trigger_reason(full_output, gate_name=name, cmd=cmd)
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
            taskOutcomes=_gradle_task_outcomes(full_output)
            if Path(cmd[0]).name == 'gradlew'
            else {},
        )
    except OSError as exc:
        return GateDetail(name=name, status=BLOCKED, command=cmd, output=f'命令启动失败: {exc}')


# 展开 catalog argv 中的运行时占位符。
def _expand_argument(argument: str, repo_root: Path) -> str:
    """把 catalog 允许的少量环境占位符解析为稳定 argv。"""
    values = {
        'python': _project_python(repo_root),
        'dev_python': _project_python(repo_root, dev=True),
        'repo_root': str(repo_root),
        'playwright_workers': str(_playwright_workers()),
    }
    return argument.format_map(values)


def _declared_command(spec: GateSpec, repo_root: Path, target: str) -> list[str]:
    """通用渲染 catalog command；不按普通 Gate 名称分派。"""
    declared = spec.command
    if declared is None:
        return []
    argv = next(
        (row.argv for row in declared.target_argv if row.target == target),
        declared.argv,
    )
    if not argv or any(not (repo_root / path).exists() for path in declared.required_paths):
        return []
    command = [_expand_argument(part, repo_root) for part in argv]
    if declared.existing_only:
        command = [
            part for part in command if not part.startswith('tests/') or (repo_root / part).exists()
        ]
    existing = [path for path in declared.existing_args if (repo_root / path).exists()]
    if declared.existing_args and not existing:
        return []
    command.extend(existing)
    globbed = _relative_existing_files(repo_root, list(declared.glob_args))
    if declared.glob_args and not globbed:
        return []
    command.extend(globbed)
    for optional in declared.optional_args:
        if (repo_root / optional.path).exists():
            command.extend(_expand_argument(part, repo_root) for part in optional.argv)
    return command


def _cpd_command(spec: GateSpec, repo_root: Path, target: str) -> list[str]:
    """按 CPD 能力声明补充 full 模式参数。"""
    command = _declared_command(spec, repo_root, target)
    if command and os.environ.get('QUALITY_GATE_TIER') == 'full' and spec.command:
        command.extend(spec.command.full_args)
    return command


def _scan_smoke_command(spec: GateSpec, repo_root: Path, target: str) -> list[str]:
    """兼容独立调用：用 catalog prerequisite 与 pytest 声明构造 smoke 命令。"""
    pytest_command = _declared_command(spec, repo_root, target)
    if not pytest_command or not spec.command:
        return []
    install_log = str(_run_tmp_dir(repo_root, 'logs') / 'scanScriptSmoke-installDist.log')
    install = [str(repo_root / 'gradlew'), *spec.command.prerequisite_tasks]
    script = (
        f'{shlex.join(install)} > {shlex.quote(install_log)} 2>&1; '
        'rc=$?; '
        'if [ $rc -ne 0 ]; then '
        f'echo "FAIL: {shlex.join(spec.command.prerequisite_tasks)} (exit=$rc)"; '
        f'tail -40 {shlex.quote(install_log)}; '
        'exit $rc; '
        'fi; '
        f'{shlex.join(pytest_command)}'
    )
    return ['bash', '-c', script]


_COMMAND_ADAPTERS = {
    'command': _declared_command,
    'playwright': _declared_command,
    'cpd': _cpd_command,
    'scan-smoke': _scan_smoke_command,
}


def _capability(spec: GateSpec) -> str:
    """返回 catalog 声明的执行能力类型。"""
    return spec.command.capability if spec.command else 'gradle'


def command_for_gate(spec: GateSpec, repo_root: Path, target: str) -> list[str]:
    """从 typed declaration 构造单 Gate 命令。"""
    if spec.gradle_tasks:
        gradlew = repo_root / 'gradlew'
        return [str(gradlew), *spec.gradle_tasks, *spec.gradle_args] if gradlew.exists() else []
    if spec.command is None:
        return []
    try:
        adapter = _COMMAND_ADAPTERS[spec.command.capability]
    except KeyError as exc:
        raise ValueError(f'unsupported command capability: {spec.command.capability}') from exc
    return adapter(spec, repo_root, target)


def gate_command(gate: str, repo_root: Path, target: str) -> list[str]:
    """按名称读取 typed catalog，并委托能力 adapter。"""
    return command_for_gate(gate_by_name(gate), repo_root, target)


def changed_files_environment(
    spec: GateSpec,
    changed_files: list[str] | tuple[str, ...] | None,
) -> dict[str, str]:
    """仅为 catalog 明确支持的 Gate 构造 changed-files 环境变量。"""
    if not changed_files or spec.changed_files_input is ChangedFilesInput.NONE:
        return {}
    if spec.changed_files_input is ChangedFilesInput.ENVIRONMENT:
        return {'QUALITY_CHANGED_FILES': json.dumps(changed_files, ensure_ascii=False)}
    raise ValueError(f'unsupported changed-files input: {spec.changed_files_input}')


_VERBOSE_OUTPUT = False


# 维护进度。
def _progress(message: str) -> None:
    """参数：
    message: 不带前缀的进度行。
    """
    if _VERBOSE_OUTPUT:
        print(f'[quality-gate] {message}', file=sys.stderr, flush=True)


# 计算质量门禁环境指纹。
def _environment_fingerprint(repo_root: Path) -> str:
    """参数：
        repo_root: 仓库根目录。

    返回：
        当前执行环境的短哈希。
    """
    raw = json.dumps(
        {
            'python': sys.version.split()[0],
            'platform': sys.platform,
            'javaHome': os.environ.get('JAVA_HOME', ''),
            'gradleUserHomeSet': bool(os.environ.get('GRADLE_USER_HOME')),
            'repo': str(repo_root),
        },
        sort_keys=True,
    )
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]


# 运行目标命令并收集有界输出；失败时保留退出码。
def run_target(
    repo_root: Path,
    target: str,
    changed_files: list[str] | None = None,
    *,
    base_url: str | None = None,
) -> list[GateDetail]:
    """运行目标命令并收集有界输出；失败时保留退出码。"""
    details: list[GateDetail] = []
    gates = (
        required_gates_for_target(target)
        if changed_files is None
        else applicable_gates_for_target(target, changed_files)
    )
    target_timeout = int(target_parallel_meta(target).get('timeout', DEFAULT_TIMEOUT_SECONDS))
    for gate_name in gates:
        spec = gate_by_name(gate_name)
        command = command_for_gate(spec, repo_root, target)
        if not command:
            details.append(
                GateDetail(
                    name=gate_name,
                    status=BLOCKED,
                    output=f'required gate {gate_name} 没有可执行命令或依赖缺失。',
                )
            )
            continue
        env = {'SESSION_BROWSER_PYTHON': _project_python(repo_root)}
        env.update(changed_files_environment(spec, changed_files))
        if _capability(spec) == 'playwright':
            env['FEIPI_AGENT_RUNTIME_ROOT'] = str(resolve_runtime_root(repo_root))
            if base_url:
                env.update(
                    {
                        'BASE_URL': base_url,
                        'PW_SESSION_URL': f'{base_url}/sessions/claude_code/hifi-viz-session-001',
                        'PW_LONG_SESSION_URL': f'{base_url}/sessions/claude_code/long-session-001',
                        'SESSION_BROWSER_REUSE_PLAYWRIGHT_SERVER': '1',
                    }
                )
        details.append(
            run_cmd(
                gate_name,
                command,
                repo_root,
                env_overrides=env,
                timeout_seconds=min(target_timeout, spec.timeout_seconds),
                network_failure=spec.network_failure,
            )
        )
    return details


def _stable_hash(value: object) -> str:
    """计算 JSON 数据的稳定 SHA-256。"""
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def _cpd_gradle_parts(repo_root: Path, changed_files: tuple[str, ...]) -> tuple[list[str], str]:
    """解析 CPD 精确输入并返回可并入 Gradle group 的 task/property。"""
    from scripts.checks import run_reuse_standard_cpd as cpd

    mode = 'full' if os.environ.get('QUALITY_GATE_TIER') == 'full' else 'incremental'
    if mode == 'full':
        return ['reuseStandardCpd', '-PfeipiReuseCpdMode=full'], mode
    if any(cpd.is_reuse_policy_path(path) for path in changed_files):
        return [], 'blocked-policy'
    java_files = cpd.select_incremental_java_files(repo_root, list(changed_files))
    if not java_files:
        return [], 'no-java-input'
    file_list = repo_root / cpd.FILE_LIST_RELATIVE_PATH
    property_arg = f'-PfeipiReuseCpdFileList={file_list.resolve().as_posix()}'
    return ['reuseStandardCpd', property_arg, '-PfeipiReuseCpdMode=incremental'], mode


def _add_dependency_edges(groups: list[CommandGroup]) -> list[CommandGroup]:
    """按稳定顺序为资源冲突和非并发 group 添加无环依赖边。"""
    result: list[CommandGroup] = []
    for index, group in enumerate(groups):
        dependencies = list(group.depends_on)
        resources = set(group.resources)
        for previous in groups[:index]:
            if (
                not group.parallel_safe
                or not previous.parallel_safe
                or resources.intersection(previous.resources)
            ) and previous.group_id not in dependencies:
                dependencies.append(previous.group_id)
        result.append(replace(group, depends_on=tuple(dependencies)))
    return result


def build_execution_plan(
    gate_plan: GatePlan,
    repo_root: Path,
    *,
    base_url: str | None = None,
) -> ExecutionPlan:
    """一次性解析 command/task aggregation 和资源 DAG，executor 不再选择 Gate。"""
    entries: list[tuple[GateSpec, str]] = []
    seen: set[str] = set()
    for target_plan in gate_plan.targets:
        for spec in target_plan.gates:
            if spec.name not in seen:
                seen.add(spec.name)
                entries.append((spec, target_plan.target))

    gradle_entries = [
        (spec, target)
        for spec, target in entries
        if spec.gradle_tasks or _capability(spec) == 'cpd'
    ]
    scan_entries = [entry for entry in entries if _capability(entry[0]) == 'scan-smoke']
    scan_requested = bool(scan_entries)
    gradle_tasks: list[str] = []
    gradle_properties: list[str] = []
    gradle_args: list[str] = []
    gradle_gate_names: list[str] = []
    cpd_mode = ''
    for spec, _target in gradle_entries:
        if _capability(spec) == 'cpd':
            parts, cpd_mode = _cpd_gradle_parts(repo_root, gate_plan.changed_files)
            if parts:
                gradle_tasks.append(parts[0])
                gradle_properties.extend(parts[1:])
                gradle_gate_names.append(spec.name)
            continue
        gradle_tasks.extend(spec.gradle_tasks)
        gradle_args.extend(spec.gradle_args)
        gradle_gate_names.append(spec.name)
    for spec, _target in scan_entries:
        if spec.command:
            gradle_tasks.extend(spec.command.prerequisite_tasks)
    gradle_tasks = list(dict.fromkeys(gradle_tasks))
    gradle_properties = list(dict.fromkeys(gradle_properties))

    groups: list[CommandGroup] = []
    group_by_gate: dict[str, str] = {}
    gradle_group_id = ''
    gradle_group: CommandGroup | None = None
    if gradle_tasks:
        gradle_group_id = 'group-gradle-000'
        resources = tuple(
            dict.fromkeys(
                resource
                for spec, _target in (*gradle_entries, *scan_entries)
                for resource in spec.exclusive_resources
            )
        )
        command = [
            str(repo_root / 'gradlew'),
            *gradle_tasks,
            *gradle_properties,
            '--console=plain',
            *gradle_args,
        ]
        env: dict[str, str] = {'SESSION_BROWSER_PYTHON': _project_python(repo_root)}
        if any(
            spec.changed_files_input is ChangedFilesInput.ENVIRONMENT for spec, _ in gradle_entries
        ):
            env['QUALITY_CHANGED_FILES'] = json.dumps(gate_plan.changed_files, ensure_ascii=False)
        gradle_group = CommandGroup(
            group_id=gradle_group_id,
            kind='gradle',
            command=tuple(command),
            environment=tuple(sorted(env.items())),
            gate_names=tuple(gradle_gate_names),
            resources=resources,
            parallel_safe=False,
            timeout_seconds=max((spec.timeout_seconds for spec, _ in gradle_entries), default=300),
            aggregation_reason=(
                'same checkout/environment Gradle tasks aggregated; '
                'scanScriptSmoke installDist is a prerequisite of its pytest group'
                if scan_requested
                else 'same checkout/environment Gradle tasks aggregated'
            ),
        )
        group_by_gate.update(dict.fromkeys(gradle_gate_names, gradle_group_id))

    command_index = 1
    gradle_added = False
    for spec, target in entries:
        if spec.name in group_by_gate:
            if gradle_group is not None and not gradle_added:
                groups.append(gradle_group)
                gradle_added = True
            continue
        capability = _capability(spec)
        if capability == 'cpd' and cpd_mode in {'no-java-input', 'blocked-policy'}:
            kind = 'cpd-noop' if cpd_mode == 'no-java-input' else 'cpd-blocked'
            command: list[str] = []
        elif capability == 'scan-smoke':
            kind = 'command'
            command = _declared_command(spec, repo_root, target)
        else:
            kind = 'command'
            command = command_for_gate(spec, repo_root, target)
        group_id = f'group-{command_index:03d}-{spec.name}'
        command_index += 1
        env = {'SESSION_BROWSER_PYTHON': _project_python(repo_root)}
        env.update(changed_files_environment(spec, gate_plan.changed_files))
        if capability == 'playwright':
            env['FEIPI_AGENT_RUNTIME_ROOT'] = str(resolve_runtime_root(repo_root))
            if base_url:
                env.update(
                    {
                        'BASE_URL': base_url,
                        'PW_SESSION_URL': f'{base_url}/sessions/claude_code/hifi-viz-session-001',
                        'PW_LONG_SESSION_URL': f'{base_url}/sessions/claude_code/long-session-001',
                        'SESSION_BROWSER_REUSE_PLAYWRIGHT_SERVER': '1',
                    }
                )
        dependencies = (gradle_group_id,) if capability == 'scan-smoke' and gradle_group_id else ()
        groups.append(
            CommandGroup(
                group_id=group_id,
                kind=kind,
                command=tuple(command),
                environment=tuple(sorted(env.items())),
                gate_names=(spec.name,),
                resources=spec.exclusive_resources,
                parallel_safe=spec.parallel_safe,
                timeout_seconds=spec.timeout_seconds,
                depends_on=dependencies,
            )
        )
        group_by_gate[spec.name] = group_id

    if gradle_group is not None and not gradle_added:
        groups.append(gradle_group)

    groups = _add_dependency_edges(groups)
    planned = tuple(
        PlannedGate(
            name=spec.name,
            target=target,
            group_id=group_by_gate[spec.name],
            status_source='gradle-task-outcome'
            if group_by_gate[spec.name] == gradle_group_id
            else 'process-exit',
            resources=spec.exclusive_resources,
            parallel_safe=spec.parallel_safe,
            timeout_seconds=spec.timeout_seconds,
        )
        for spec, target in entries
    )
    payload = {
        'catalog': CATALOG_VERSION,
        'changedFiles': gate_plan.changed_files,
        'targets': gate_plan.effective_targets,
        'gates': [asdict(item) for item in planned],
        'groups': [asdict(item) for item in groups],
    }
    fingerprint = _stable_hash(payload)
    return ExecutionPlan(f'plan-{fingerprint[:16]}', fingerprint, gate_plan, planned, tuple(groups))


def _prepare_cpd(repo_root: Path, execution_plan: ExecutionPlan) -> None:
    """在 Gradle group 启动前写入其 plan 已绑定的精确 CPD file list。"""
    if not any(_capability(gate_by_name(gate.name)) == 'cpd' for gate in execution_plan.gates):
        return
    from scripts.checks import run_reuse_standard_cpd as cpd

    changed = list(execution_plan.gate_plan.changed_files)
    java_files = cpd.select_incremental_java_files(repo_root, changed)
    if java_files:
        cpd.write_cpd_file_list(repo_root, java_files, repo_root / cpd.FILE_LIST_RELATIVE_PATH)


def _execute_group(
    group: CommandGroup,
    repo_root: Path,
    identity: object,
) -> tuple[str, GateDetail, int]:
    """在跨 run ResourceLockSet 内执行一个冻结 group。"""
    started_wait = time.monotonic()
    owner = resource_lock.owner_metadata(
        run_id=getattr(identity, 'raw_run_id', ''),
        client=getattr(identity, 'client', ''),
        session_id=getattr(identity, 'raw_session_id', ''),
        worktree_id=getattr(identity, 'raw_worktree_id', ''),
        target=group.group_id,
    )
    try:
        with resource_lock.ResourceLockSet(
            repo_root,
            group.resources,
            owner,
            timeout_seconds=min(120, group.timeout_seconds),
        ):
            waited_ms = int((time.monotonic() - started_wait) * 1000)
            if group.kind == 'cpd-noop':
                from scripts.checks import run_reuse_standard_cpd as cpd

                changed = json.loads(dict(group.environment).get('QUALITY_CHANGED_FILES', '[]'))
                cpd.write_summary(
                    repo_root,
                    status=PASS,
                    mode='incremental',
                    changed_files=changed,
                    cpd_input_files=[],
                    changed_files_source='Gate execution plan',
                    reason='No changed production Java files; full CPD was not invoked.',
                )
                detail = GateDetail(
                    name=group.group_id,
                    status=PASS,
                    output='No changed production Java files; CPD full scan was not invoked.',
                )
            elif group.kind == 'cpd-blocked':
                from scripts.checks import run_reuse_standard_cpd as cpd

                changed = json.loads(dict(group.environment).get('QUALITY_CHANGED_FILES', '[]'))
                cpd.write_summary(
                    repo_root,
                    status=BLOCKED,
                    mode='incremental',
                    changed_files=changed,
                    cpd_input_files=[],
                    changed_files_source='Gate execution plan',
                    reason='CPD policy changed; explicit full mode is required.',
                )
                detail = GateDetail(
                    name=group.group_id,
                    status=BLOCKED,
                    output='CPD policy changed; explicit full mode is required.',
                )
            elif not group.command:
                detail = GateDetail(
                    name=group.group_id, status=BLOCKED, output='Gate command unavailable.'
                )
            else:
                detail = run_cmd(
                    group.group_id,
                    list(group.command),
                    repo_root,
                    env_overrides=dict(group.environment),
                    timeout_seconds=group.timeout_seconds,
                    network_failure=(
                        'blocked'
                        if any(
                            gate_by_name(name).network_failure == 'blocked'
                            for name in group.gate_names
                        )
                        else 'fail'
                    ),
                )
            return group.group_id, detail, waited_ms
    except resource_lock.ResourceLockTimeoutError as exc:
        waited_ms = int((time.monotonic() - started_wait) * 1000)
        detail = GateDetail(
            name=group.group_id,
            status=BLOCKED,
            command=list(group.command),
            output=f'resource lock timeout: {exc.resource}; owner={json.dumps(exc.owner, ensure_ascii=False, sort_keys=True)}',
        )
        return group.group_id, detail, waited_ms


def _gradle_gate_outcome(task_outcomes: dict[str, str], tasks: tuple[str, ...]) -> str | None:
    """按精确 task 路径优先、唯一短名回退解析逻辑 Gate outcome。"""
    resolved: list[str] = []
    for task in tasks:
        exact = task if task.startswith(':') else f':{task}'
        if exact in task_outcomes:
            resolved.append(task_outcomes[exact])
            continue
        short = task.lstrip(':').split(':')[-1]
        matches = [value for path, value in task_outcomes.items() if path.split(':')[-1] == short]
        if len(matches) != 1:
            return None
        resolved.append(matches[0])
    if any(value == 'FAILED' for value in resolved):
        return 'FAILED'
    if any(value == 'SKIPPED' for value in resolved):
        return 'SKIPPED'
    return 'EXECUTED' if resolved else None


def _selected_task_outcomes(
    task_outcomes: dict[str, str], tasks: tuple[str, ...]
) -> dict[str, str]:
    """只保留当前逻辑 Gate 选中 task 的结构化 outcome。"""
    selected: dict[str, str] = {}
    for task in tasks:
        exact = task if task.startswith(':') else f':{task}'
        if exact in task_outcomes:
            selected[exact] = task_outcomes[exact]
            continue
        short = task.lstrip(':').split(':')[-1]
        matches = [
            (path, value) for path, value in task_outcomes.items() if path.split(':')[-1] == short
        ]
        if len(matches) == 1:
            selected[matches[0][0]] = matches[0][1]
    return selected


def execute_plan(
    execution_plan: ExecutionPlan,
    repo_root: Path,
) -> tuple[GateDetail, ...]:
    """只执行冻结 execution plan；结果始终按 plan 顺序返回。"""
    _prepare_cpd(repo_root, execution_plan)
    identity = runtime_paths.identity_from_values()
    pending = {group.group_id: group for group in execution_plan.groups}
    outcomes: dict[str, tuple[GateDetail, int]] = {}
    while pending:
        ready = [
            group
            for group in execution_plan.groups
            if group.group_id in pending and all(dep in outcomes for dep in group.depends_on)
        ]
        if not ready:
            raise RuntimeError('execution plan resource DAG contains a cycle')
        runnable = [
            group
            for group in ready
            if all(outcomes[dep][0].status == PASS for dep in group.depends_on)
        ]
        blocked = [group for group in ready if group not in runnable]
        for group in blocked:
            outcomes[group.group_id] = (
                GateDetail(
                    name=group.group_id, status=BLOCKED, output='dependency group did not PASS.'
                ),
                0,
            )
            pending.pop(group.group_id)
        with ThreadPoolExecutor(
            max_workers=min(MAX_PARALLEL_GROUPS, max(1, len(runnable)))
        ) as pool:
            futures = [
                pool.submit(_execute_group, group, repo_root, identity) for group in runnable
            ]
            for future in futures:
                group_id, detail, waited_ms = future.result()
                outcomes[group_id] = (detail, waited_ms)
                pending.pop(group_id)

    group_by_id = {group.group_id: group for group in execution_plan.groups}
    details: list[GateDetail] = []
    for gate in execution_plan.gates:
        group = group_by_id[gate.group_id]
        outcome, waited_ms = outcomes[gate.group_id]
        status = outcome.status
        output = outcome.output
        spec = gate_by_name(gate.name)
        selected_outcomes: dict[str, str] = {}
        if group.kind == 'gradle':
            selected_tasks = spec.gradle_tasks or (
                spec.command.gradle_outcome_tasks if spec.command else ()
            )
            task_outcome = _gradle_gate_outcome(outcome.taskOutcomes, selected_tasks)
            selected_outcomes = _selected_task_outcomes(outcome.taskOutcomes, selected_tasks)
            if task_outcome == 'SKIPPED':
                status = FAIL
                output = f'{output}\n[quality-gate] FAIL: selected Gradle task was SKIPPED.'
            elif task_outcome == 'FAILED':
                status = FAIL
            elif task_outcome == 'EXECUTED':
                status = PASS
            else:
                status = BLOCKED
                output = f'{output}\n[quality-gate] BLOCKED: selected Gradle task outcome was not confirmed.'
            if status == PASS:
                output = (
                    f'Gradle task outcome confirmed: '
                    f'{json.dumps(selected_outcomes, ensure_ascii=False, sort_keys=True)}'
                )
        details.append(
            GateDetail(
                name=gate.name,
                status=status,
                command=list(group.command),
                exitCode=outcome.exitCode,
                durationMs=outcome.durationMs,
                output=output,
                executionState='EXECUTED'
                if status == PASS
                else ('BLOCKED' if status == BLOCKED else 'FAILED'),
                groupId=group.group_id,
                queueWaitMs=waited_ms,
                resourceWaitMs=waited_ms,
                rerunCommand=shlex.join(group.command),
                taskOutcomes=selected_outcomes,
            )
        )
    return tuple(details)
