#!/usr/bin/env python3
"""执行不可变 GatePlan 中的命令组，不负责规划、fixture 构造或 CLI 编排。"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import asdict, replace
from functools import lru_cache
from pathlib import Path

from scripts.gates.catalog import CATALOG_VERSION, gate_by_name
from scripts.gates.model import (
    ChangedFilesInput,
    CommandGroup,
    ExecutionPlan,
    GatePlan,
    GateSpec,
    PlannedGate,
)
from scripts.gates.report import (
    BLOCKED,
    FAIL,
    PASS,
    GateDetail,
)
from scripts.gates.runtime.environment import sanitized_environment
from scripts.gates.runtime.process import BoundedRunResult, run_bounded
from scripts.gates.support import (
    ensure_private_directory,
    identity_from_values,
    quality_dir,
    resolve_runtime_root,
)
from scripts.harness.python_env import project_venv_dir, resolve_python

PLAYWRIGHT_COMMAND_MIN_PARTS = 5
PLAYWRIGHT_MIN_WORKERS = 8
PLAYWRIGHT_TIMEOUT_SECONDS = 120
DEFAULT_TIMEOUT_SECONDS = 300
MODULE_CHECK_TIMEOUT_SECONDS = 10
COMMAND_OUTPUT_TAIL_CHARS = 4000
JAVA_QUALITY_RULES_PROPERTY = '-PfeipiJavaQualityRules='


def _run_tmp_dir(repo_root: Path, name: str) -> Path:
    """创建并返回当前 run 隔离的临时子目录。"""
    run_id = (
        os.environ.get('FEIPI_RUN_ID') or os.environ.get('FEIPI_SESSION_ID') or f'pid-{os.getpid()}'
    )
    root = (
        Path(os.environ.get('FEIPI_RUN_TMPDIR', '')).expanduser()
        if os.environ.get('FEIPI_RUN_TMPDIR')
        else (
            resolve_runtime_root(repo_root)
            / 'runs'
            / f'{run_id}-{hashlib.sha256(str(repo_root.resolve()).encode()).hexdigest()[:12]}'
            / 'tmp'
        )
    )
    path = root / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def gate_child_environment(
    repo_root: Path, overrides: dict[str, str] | None = None
) -> dict[str, str]:
    """构造 Gate 净化环境，并按执行身份隔离临时数据和质量产物。"""
    selected_overrides = overrides or {}
    identity = identity_from_values(
        agent_client=selected_overrides.get('FEIPI_AGENT_CLIENT'),
        session_id=selected_overrides.get('FEIPI_SESSION_ID'),
        agent_id=selected_overrides.get('FEIPI_AGENT_ID'),
        run_id=selected_overrides.get('FEIPI_RUN_ID'),
        worktree_id=selected_overrides.get('FEIPI_WORKTREE_ID'),
    )
    if not identity.has_session or not identity.has_run:
        # 缺少 session/run 时沿用旧 owner 的进程级隔离，避免多个无身份执行共享 unknown/main。
        process_id = f'pid-{os.getpid()}'
        identity = identity_from_values(
            agent_client=identity.client,
            session_id=identity.raw_session_id or process_id,
            agent_id=identity.raw_agent_id,
            run_id=identity.raw_run_id or process_id,
            worktree_id=identity.raw_worktree_id,
        )
    quality_root = repo_root / 'tmp' / 'quality'
    artifact_dir = ensure_private_directory(quality_dir(repo_root, identity), root=quality_root)
    child_root = _run_tmp_dir(repo_root, 'child-environment')
    values = {
        'TMPDIR': str(child_root / 'tmp'),
        'XDG_CACHE_HOME': str(child_root / 'cache'),
        'FEIPI_FIXTURE_DATA_DIR': str(child_root / 'fixture-data'),
    }
    for path in values.values():
        Path(path).mkdir(parents=True, exist_ok=True)
    values.update(selected_overrides)
    # 质量产物根目录只能由统一 identity 算法生成，调用方不能注入任意路径。
    values['FEIPI_QUALITY_ARTIFACT_DIR'] = str(artifact_dir)
    return sanitized_environment(values, base=sanitized_environment())


def _relative_existing_files(repo_root: Path, patterns: list[str]) -> list[str]:
    """按 glob 收集稳定排序且去重的 repository-relative 文件。"""
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


def _python_candidates(repo_root: Path) -> list[str]:
    """按显式配置、项目环境和系统环境返回去重的 Python 候选。"""
    candidates: list[str] = []

    explicit = os.environ.get('SESSION_BROWSER_PYTHON')
    if explicit:
        candidates.append(explicit)

    candidates.append(str(project_venv_dir(repo_root) / 'bin' / 'python'))

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
    """探测指定 Python 是否可导入全部必需模块。"""
    if shutil.which(executable) is None:
        return False

    env = sanitized_environment()
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
    # 模块探测结果会被上层缓存，避免每个 Gate 重复启动 Python。
    return proc.returncode == 0


@lru_cache(maxsize=8)
def _project_python_cached(repo_root: str, modules: tuple[str, ...]) -> str:
    """解析并缓存满足模块要求的项目 Python。"""
    root = Path(repo_root)
    resolved = resolve_python(root)
    if not modules or _python_supports_modules(resolved, root, modules):
        return resolved
    for candidate in _python_candidates(root):
        if candidate != resolved and _python_supports_modules(candidate, root, modules):
            return candidate
    required = ', '.join(modules)
    raise SystemExit(f'未找到包含开发依赖的 Python 解释器: {required}')


def _project_python(repo_root: Path, *, dev: bool = False) -> str:
    """返回项目 Python；开发模式额外要求 pytest。"""
    modules = ('pytest',) if dev else ()
    return _project_python_cached(str(repo_root), modules)


def _playwright_workers() -> int:
    """从环境读取 Playwright worker 数量，并应用 Gate 最小值。"""
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


_ANSI_RE = re.compile(r'\x1b\[[0-9;]*m')
_GRADLE_TASK_RE = re.compile(
    r'^> Task (?P<task>:\S+?)(?: (?P<outcome>UP-TO-DATE|FROM-CACHE|NO-SOURCE|SKIPPED|FAILED))?$',
    flags=re.MULTILINE,
)
_GATE_TASK_RESULT_RE = re.compile(
    r'^GATE_TASK_RESULT task=(?P<task>:\S+) status=BLOCKED '
    r'reason=(?P<reason>[A-Za-z0-9._-]+)$',
    flags=re.MULTILINE,
)


def _strip_ansi(text: str) -> str:
    """移除 subprocess 输出中的终端颜色序列。"""
    return _ANSI_RE.sub('', text)


def _gradle_task_outcomes(output: str) -> dict[str, str]:
    """从完整 plain console 输出提取稳定 Gradle task outcome。"""
    clean = _strip_ansi(output)
    outcomes = {
        match.group('task'): match.group('outcome') or 'EXECUTED'
        for match in _GRADLE_TASK_RE.finditer(clean)
    }
    # task 自己可用通用 marker 将执行失败细分为 BLOCKED；marker 必须精确绑定 task。
    outcomes.update(
        {match.group('task'): 'BLOCKED' for match in _GATE_TASK_RESULT_RE.finditer(clean)}
    )
    return outcomes


def _is_playwright_command(cmd: list[str]) -> bool:
    """判断命令是否为仓库声明的 Playwright 调用形式。"""
    return (
        len(cmd) >= PLAYWRIGHT_COMMAND_MIN_PARTS
        and Path(cmd[0]).name == 'npm'
        and cmd[1:5] == ['--prefix', 'tests/playwright', 'test', '--']
    )


def _playwright_skip_count(output: str) -> int:
    """汇总 Playwright 输出中的 skipped 计数。"""
    clean = _strip_ansi(output)
    matches = re.findall(r'\b(\d+)\s+skipped\b', clean)
    return sum(int(value) for value in matches)


def _is_pytest_command(cmd: list[str]) -> bool:
    """判断命令是否直接或通过 Python module 执行 pytest。"""
    if not cmd:
        return False
    executable = Path(cmd[0]).name
    if executable == 'pytest':
        return True
    return len(cmd) >= 3 and executable.startswith('python') and cmd[1:3] == ['-m', 'pytest']


def _pytest_skip_count(output: str) -> int:
    clean = _strip_ansi(output)
    matches = re.findall(r'\b(\d+)\s+skipped\b', clean)
    return sum(int(value) for value in matches)


def _strip_allowed_warning_noise(output: str, *, gate_name: str, cmd: list[str]) -> str:
    """只移除策略明确允许的 Playwright warning 噪声。"""
    clean = _strip_ansi(output)

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

    return clean


def _warning_after_trigger_reason(
    output: str, *, gate_name: str = '', cmd: list[str] | None = None
) -> str | None:
    """检查已触发 Gate 的输出；发现非允许警告时返回稳定原因。"""
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
        if re.match(
            r'^(?:\[(?:WARN|WARNING)\]|(?:\[.*?\]\s*)?(?:WARN|WARNING)\b)',
            line.strip(),
            flags=re.IGNORECASE,
        )
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


def _audit_network_block_reason(output: str, *, network_failure: str) -> str | None:
    """按声明策略识别外部漏洞服务或网络不可用。"""
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
    return None


def _audit_successful_output(
    name: str,
    cmd: list[str],
    full_output: str,
    output: str,
) -> tuple[str, str]:
    """拒绝测试框架 skip 与非允许 warning，避免不完整成功被归约为 PASS。"""
    skipped = 0
    skipped_kind = ''
    if _is_playwright_command(cmd):
        skipped = _playwright_skip_count(full_output)
        skipped_kind = 'Playwright'
    elif _is_pytest_command(cmd):
        skipped = _pytest_skip_count(full_output)
        skipped_kind = 'pytest'
    if skipped:
        return (
            FAIL,
            (
                f'{output}\n\n'
                f'[quality-gate] FAIL: selected {skipped_kind} gate reported '
                f'{skipped} skipped tests. '
                'If a test is not required for this change, remove it from the '
                'triggered mapping/command; '
                'if it is required, provide the needed fixture or environment instead of skipping.'
            ),
        )
    warning_reason = _warning_after_trigger_reason(full_output, gate_name=name, cmd=cmd)
    if warning_reason:
        return (
            FAIL,
            (
                f'{output}\n\n'
                f'[quality-gate] FAIL: {warning_reason}. '
                'Triggered pytest/quality/full/release gates must be warning-free; '
                'fix the warning or mark the gate BLOCKED instead of reporting PASS.'
            ),
        )
    return PASS, output


def _detail_from_bounded_run(
    name: str,
    cmd: list[str],
    *,
    required: bool,
    timeout: int,
    network_failure: str,
    log_path: Path,
    bounded: BoundedRunResult,
) -> GateDetail:
    """读取有界进程结果，并在 executor 内归约 Gate 业务状态。"""
    try:
        full_output = log_path.read_text(encoding='utf-8', errors='replace').strip()
    except OSError:
        full_output = bounded.output_tail.strip()
    duration = int(bounded.duration_seconds * 1000)
    if bounded.timed_out:
        return GateDetail(
            name=name,
            status=FAIL,
            command=cmd,
            durationMs=duration,
            output=f'超时: command exceeded {timeout}s\n{bounded.output_tail}',
        )
    output = full_output[-COMMAND_OUTPUT_TAIL_CHARS:]
    if bounded.return_code is None:
        return GateDetail(
            name=name,
            status=BLOCKED if required else FAIL,
            command=cmd,
            durationMs=duration,
            output=f'命令启动失败: {bounded.output_tail or bounded.exit_reason}',
            executionState='CAPABILITY_BLOCKED',
        )

    status = PASS if bounded.return_code == 0 else FAIL
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
    elif status == PASS:
        status, output = _audit_successful_output(name, cmd, full_output, output)
    return GateDetail(
        name=name,
        status=status,
        command=cmd,
        exitCode=bounded.return_code,
        durationMs=duration,
        output=output,
        taskOutcomes=(_gradle_task_outcomes(full_output) if Path(cmd[0]).name == 'gradlew' else {}),
    )


def run_cmd(
    name: str,
    cmd: list[str],
    cwd: Path,
    required: bool = True,
    env_overrides: dict[str, str] | None = None,
    timeout_seconds: int | None = None,
    network_failure: str = 'fail',
) -> GateDetail:
    """执行单条受控命令，并严格归约 timeout、skip、warning 与网络阻断状态。"""
    if not cmd or shutil.which(cmd[0]) is None:
        status = BLOCKED if required else FAIL
        return GateDetail(
            name=name,
            status=status,
            command=cmd,
            durationMs=0,
            output=f'命令不存在: {cmd[0] if cmd else "<empty>"}',
            executionState='CAPABILITY_BLOCKED',
        )

    default_timeout = timeout_seconds or DEFAULT_TIMEOUT_SECONDS
    timeout = PLAYWRIGHT_TIMEOUT_SECONDS if _is_playwright_command(cmd) else default_timeout

    # Gate、Gradle、fixture 和测试统一使用净化环境，provider 私有目录不得注入应用。
    run_env = gate_child_environment(cwd, env_overrides)
    if _is_playwright_command(cmd) and run_env.get('FORCE_COLOR') and run_env.get('NO_COLOR'):
        run_env.pop('NO_COLOR', None)

    try:
        log_name = re.sub(r'[^A-Za-z0-9_.-]+', '-', name)[:80] or 'gate'
        log_path = _run_tmp_dir(cwd, 'logs') / f'{log_name}-{_stable_hash(cmd)[:12]}.log'
        bounded = run_bounded(
            cmd,
            cwd=cwd,
            timeout=timeout,
            env=run_env,
            log_path=log_path,
        )
        return _detail_from_bounded_run(
            name,
            cmd,
            required=required,
            timeout=timeout,
            network_failure=network_failure,
            log_path=log_path,
            bounded=bounded,
        )
    except OSError as exc:
        return GateDetail(
            name=name,
            status=BLOCKED,
            command=cmd,
            output=f'命令启动失败: {exc}',
            executionState='CAPABILITY_BLOCKED',
        )


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
    'scan-smoke': _scan_smoke_command,
}


def _capability(spec: GateSpec) -> str:
    """返回 catalog 声明的执行能力类型。"""
    return spec.command.capability if spec.command else 'gradle'


def command_for_gate(spec: GateSpec, repo_root: Path, target: str) -> list[str]:
    """从 typed declaration 构造单 Gate 命令。"""
    if spec.gradle_tasks:
        gradlew = repo_root / 'gradlew'
        java_rules = (
            [f'{JAVA_QUALITY_RULES_PROPERTY}{",".join(spec.java_rules)}'] if spec.java_rules else []
        )
        return (
            [str(gradlew), *spec.gradle_tasks, *java_rules, *spec.gradle_args]
            if gradlew.exists()
            else []
        )
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


def _stable_hash(value: object) -> str:
    """计算 JSON 数据的稳定 SHA-256。"""
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def _unique_gate_entries(gate_plan: GatePlan) -> list[tuple[GateSpec, str]]:
    """按 target/注册顺序收集去重后的 Gate 与首次所属 target。"""
    entries: list[tuple[GateSpec, str]] = []
    seen: set[str] = set()
    for target_plan in gate_plan.targets:
        for spec in target_plan.gates:
            if spec.name not in seen:
                seen.add(spec.name)
                entries.append((spec, target_plan.target))
    return entries


def _build_gradle_group(
    entries: list[tuple[GateSpec, str]],
    gate_plan: GatePlan,
    repo_root: Path,
) -> tuple[CommandGroup | None, tuple[str, ...]]:
    """把同一 checkout 的 Gradle Gate 与 scan prerequisite 聚合为一个 group。"""
    gradle_entries = [(spec, target) for spec, target in entries if spec.gradle_tasks]
    scan_entries = [entry for entry in entries if _capability(entry[0]) == 'scan-smoke']
    gradle_tasks = [task for spec, _target in gradle_entries for task in spec.gradle_tasks]
    gradle_args = [argument for spec, _target in gradle_entries for argument in spec.gradle_args]
    java_rules = [rule for spec, _target in gradle_entries for rule in spec.java_rules]
    gate_names = tuple(spec.name for spec, _target in gradle_entries)
    for spec, _target in scan_entries:
        if spec.command:
            gradle_tasks.extend(spec.command.prerequisite_tasks)
    gradle_tasks = list(dict.fromkeys(gradle_tasks))
    java_rules = list(dict.fromkeys(java_rules))
    gradle_properties = (
        [f'{JAVA_QUALITY_RULES_PROPERTY}{",".join(java_rules)}'] if java_rules else []
    )
    if not gradle_tasks:
        return None, gate_names

    environment = {'SESSION_BROWSER_PYTHON': _project_python(repo_root)}
    if any(spec.changed_files_input is ChangedFilesInput.ENVIRONMENT for spec, _ in gradle_entries):
        environment['QUALITY_CHANGED_FILES'] = json.dumps(
            gate_plan.changed_files, ensure_ascii=False
        )
    return (
        CommandGroup(
            group_id='group-gradle-000',
            kind='gradle',
            command=(
                str(repo_root / 'gradlew'),
                *gradle_tasks,
                *gradle_properties,
                '--console=plain',
                *gradle_args,
            ),
            environment=tuple(sorted(environment.items())),
            gate_names=gate_names,
            timeout_seconds=max((spec.timeout_seconds for spec, _ in gradle_entries), default=300),
            aggregation_reason=(
                'same checkout/environment Gradle tasks aggregated; '
                'scanScriptSmoke installDist is a prerequisite of its pytest group'
                if scan_entries
                else 'same checkout/environment Gradle tasks aggregated'
            ),
        ),
        gate_names,
    )


def _build_command_groups(
    entries: list[tuple[GateSpec, str]],
    gate_plan: GatePlan,
    repo_root: Path,
    *,
    base_url: str | None,
) -> tuple[list[CommandGroup], dict[str, str], str]:
    """构造普通命令 group，并在原始稳定位置插入聚合 Gradle group。"""
    gradle_group, gradle_gate_names = _build_gradle_group(entries, gate_plan, repo_root)
    gradle_group_id = gradle_group.group_id if gradle_group else ''
    group_by_gate = dict.fromkeys(gradle_gate_names, gradle_group_id)
    groups: list[CommandGroup] = []
    command_index = 1
    gradle_added = False
    for spec, target in entries:
        if spec.name in group_by_gate:
            if gradle_group is not None and not gradle_added:
                groups.append(gradle_group)
                gradle_added = True
            continue
        capability = _capability(spec)
        if capability == 'scan-smoke' and gradle_group is not None and not gradle_added:
            # prerequisite 必须先出现，否则后续资源串行边可能反向指向并形成环。
            groups.append(gradle_group)
            gradle_added = True
        command = (
            _declared_command(spec, repo_root, target)
            if capability == 'scan-smoke'
            else command_for_gate(spec, repo_root, target)
        )
        group_id = f'group-{command_index:03d}-{spec.name}'
        command_index += 1
        environment = {'SESSION_BROWSER_PYTHON': _project_python(repo_root)}
        environment.update(changed_files_environment(spec, gate_plan.changed_files))
        if capability == 'playwright':
            environment['FEIPI_AGENT_RUNTIME_ROOT'] = str(resolve_runtime_root(repo_root))
            if base_url:
                environment.update(
                    {
                        'BASE_URL': base_url,
                        'PW_SESSION_URL': f'{base_url}/sessions/claude_code/hifi-viz-session-001',
                        'PW_LONG_SESSION_URL': f'{base_url}/sessions/claude_code/long-session-001',
                        'SESSION_BROWSER_REUSE_PLAYWRIGHT_SERVER': '1',
                    }
                )
        groups.append(
            CommandGroup(
                group_id=group_id,
                kind='scan-smoke' if capability == 'scan-smoke' else 'command',
                command=tuple(command),
                environment=tuple(sorted(environment.items())),
                gate_names=(spec.name,),
                timeout_seconds=spec.timeout_seconds,
            )
        )
        group_by_gate[spec.name] = group_id
    if gradle_group is not None and not gradle_added:
        groups.append(gradle_group)
    return groups, group_by_gate, gradle_group_id


def _freeze_planned_gates(
    entries: list[tuple[GateSpec, str]],
    group_by_gate: dict[str, str],
    gradle_group_id: str,
) -> tuple[PlannedGate, ...]:
    """冻结逻辑 Gate 到命令 group 与状态来源的映射。"""
    return tuple(
        PlannedGate(
            name=spec.name,
            target=target,
            group_id=group_by_gate[spec.name],
            status_source=(
                'gradle-task-outcome'
                if group_by_gate[spec.name] == gradle_group_id
                else 'process-exit'
            ),
            timeout_seconds=spec.timeout_seconds,
        )
        for spec, target in entries
    )


def build_execution_plan(
    gate_plan: GatePlan,
    repo_root: Path,
    *,
    base_url: str | None = None,
) -> ExecutionPlan:
    """按“去重 → 稳定分组 → 冻结指纹”生成不可变串行执行计划。"""
    entries = _unique_gate_entries(gate_plan)
    groups, group_by_gate, gradle_group_id = _build_command_groups(
        entries, gate_plan, repo_root, base_url=base_url
    )
    planned = _freeze_planned_gates(entries, group_by_gate, gradle_group_id)
    payload = {
        'catalog': CATALOG_VERSION,
        'changedFiles': gate_plan.changed_files,
        'targets': gate_plan.effective_targets,
        'gates': [asdict(item) for item in planned],
        'groups': [asdict(item) for item in groups],
    }
    fingerprint = _stable_hash(payload)
    return ExecutionPlan(f'plan-{fingerprint[:16]}', fingerprint, gate_plan, planned, tuple(groups))


def _execute_group(
    group: CommandGroup,
    repo_root: Path,
) -> GateDetail:
    """执行一个冻结 group；调用方保证严格按 plan tuple 顺序调用。"""
    if not group.command:
        return GateDetail(name=group.group_id, status=BLOCKED, output='Gate command unavailable.')
    return run_cmd(
        group.group_id,
        list(group.command),
        repo_root,
        env_overrides=dict(group.environment),
        timeout_seconds=group.timeout_seconds,
        network_failure=(
            'blocked'
            if any(gate_by_name(name).network_failure == 'blocked' for name in group.gate_names)
            else 'fail'
        ),
    )


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
    if any(value == 'BLOCKED' for value in resolved):
        return 'BLOCKED'
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


def _scan_prerequisite_passed(group: CommandGroup, gradle_outcome: GateDetail | None) -> bool:
    """只验证 scan-smoke 声明的真实 Gradle prerequisite 已执行成功。"""
    if group.kind != 'scan-smoke':
        return True
    tasks = tuple(
        task
        for name in group.gate_names
        for task in (
            gate_by_name(name).command.prerequisite_tasks if gate_by_name(name).command else ()
        )
    )
    return bool(
        gradle_outcome
        and tasks
        and _gradle_gate_outcome(gradle_outcome.taskOutcomes, tasks) == 'EXECUTED'
    )


def _run_groups_serially(
    groups: tuple[CommandGroup, ...],
    repo_root: Path,
    *,
    environment_overrides: dict[str, str] | None = None,
) -> dict[str, GateDetail]:
    """逐项执行 immutable group tuple；独立失败不阻断后续 group。"""
    overrides = environment_overrides or {}
    execution_groups = tuple(
        replace(
            group,
            environment=tuple(sorted({**dict(group.environment), **overrides}.items())),
        )
        for group in groups
    )
    outcomes: dict[str, GateDetail] = {}
    gradle_outcome: GateDetail | None = None
    for group in execution_groups:
        if not _scan_prerequisite_passed(group, gradle_outcome):
            detail = GateDetail(
                name=group.group_id,
                status=BLOCKED,
                output='scanScriptSmoke Gradle prerequisite did not complete successfully.',
                executionState='DEPENDENCY_BLOCKED',
            )
        else:
            detail = _execute_group(group, repo_root)
        outcomes[group.group_id] = detail
        if group.kind == 'gradle':
            gradle_outcome = detail
    return outcomes


def _logical_gate_detail(
    gate: PlannedGate,
    group: CommandGroup,
    outcome: GateDetail,
) -> GateDetail:
    """把 group 技术结果映射为单个逻辑 Gate 明细。"""
    status = outcome.status
    output = outcome.output
    selected_outcomes: dict[str, str] = {}
    task_outcome: str | None = None
    if group.kind == 'gradle':
        selected_tasks = gate_by_name(gate.name).gradle_tasks
        task_outcome = _gradle_gate_outcome(outcome.taskOutcomes, selected_tasks)
        selected_outcomes = _selected_task_outcomes(outcome.taskOutcomes, selected_tasks)
        if task_outcome == 'BLOCKED':
            status = BLOCKED
            output = (
                f'{output}\n'
                '[quality-gate] BLOCKED: selected Gradle task reported a blocking result.'
            )
        elif task_outcome == 'SKIPPED':
            status = FAIL
            output = f'{output}\n[quality-gate] FAIL: selected Gradle task was SKIPPED.'
        elif task_outcome == 'FAILED':
            status = FAIL
        elif task_outcome == 'EXECUTED':
            status = PASS
        else:
            status = BLOCKED
            output = (
                f'{output}\n[quality-gate] BLOCKED: selected Gradle task outcome was not confirmed.'
            )
        if status == PASS:
            output = (
                'Gradle task outcome confirmed: '
                f'{json.dumps(selected_outcomes, ensure_ascii=False, sort_keys=True)}'
            )
    return GateDetail(
        name=gate.name,
        status=status,
        command=list(group.command),
        exitCode=outcome.exitCode,
        durationMs=outcome.durationMs,
        output=output,
        executionState=(
            'EXECUTED'
            if status == PASS
            else 'BLOCKED'
            if task_outcome == 'BLOCKED'
            else outcome.executionState
            if status == BLOCKED
            else 'FAILED'
        ),
        groupId=group.group_id,
        rerunCommand=shlex.join(group.command),
        taskOutcomes=selected_outcomes,
    )


def execute_plan(
    execution_plan: ExecutionPlan,
    repo_root: Path,
    *,
    environment_overrides: dict[str, str] | None = None,
) -> tuple[GateDetail, ...]:
    """执行冻结 group，再按 plan 顺序归约并返回逻辑 Gate 明细。"""
    outcomes = _run_groups_serially(
        execution_plan.groups,
        repo_root,
        environment_overrides=environment_overrides,
    )
    group_by_id = {group.group_id: group for group in execution_plan.groups}
    return tuple(
        _logical_gate_detail(
            gate,
            group_by_id[gate.group_id],
            outcomes[gate.group_id],
        )
        for gate in execution_plan.gates
    )
