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

from scripts.gates.catalog import gate_by_name
from scripts.gates.model import (
    CommandGroup,
    ExecutionMode,
    ExecutionPlan,
    GatePlan,
    GateSpec,
    PlannedGate,
    RunKind,
    RunProfile,
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
DEFAULT_TIMEOUT_SECONDS = 300
MODULE_CHECK_TIMEOUT_SECONDS = 10
COMMAND_OUTPUT_TAIL_CHARS = 4000
JAVA_QUALITY_RULES_PROPERTY = '-PfeipiJavaQualityRules='
GATE_REQUEST_ENVIRONMENT_KEYS = frozenset({'QUALITY_EXECUTION_MODE', 'QUALITY_CHANGED_FILES'})


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
    r'^GATE_TASK_RESULT task=(?P<task>:\S+) status=(?P<status>BLOCKED|FAIL)'
    r'(?: reason=(?P<reason>[A-Za-z0-9._-]+))?$',
    flags=re.MULTILINE,
)
_GATE_RESULT_RE = re.compile(
    r'^GATE_RESULT status=(?P<status>PASS|BLOCKED|FAIL)'
    r'(?: reason=(?P<reason>[A-Za-z0-9._-]+))?(?: .*)?$',
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
    # task 自己用结构化 marker 区分“已有阻断结论”和“执行失败”。
    outcomes.update(
        {
            match.group('task'): match.group('status')
            for match in _GATE_TASK_RESULT_RE.finditer(clean)
        }
    )
    return outcomes


def _gradle_task_failure_reasons(output: str) -> dict[str, str]:
    """提取 Gradle owner 为 FAIL 提供的稳定原因码。"""

    return {
        match.group('task'): match.group('reason') or 'outcome-unknown'
        for match in _GATE_TASK_RESULT_RE.finditer(_strip_ansi(output))
        if match.group('status') == FAIL
    }


def _owner_result(output: str) -> tuple[str, str] | None:
    """读取 leaf owner marker；冲突或缺失 FAIL reason 时 fail-closed。"""

    markers = [
        (match.group('status'), match.group('reason') or '')
        for match in _GATE_RESULT_RE.finditer(_strip_ansi(output))
    ]
    if not markers:
        return None
    if len(set(markers)) != 1:
        return FAIL, 'outcome-unknown'
    status, reason = markers[0]
    if status == FAIL and not reason:
        return FAIL, 'outcome-unknown'
    if status != FAIL and reason:
        return FAIL, 'outcome-unknown'
    return status, reason


def _command_exit_status(cmd: list[str], return_code: int) -> tuple[str, bool]:
    """把工具自身的退出码翻译为 Gate 状态，并标记该退出码是否已知。"""

    # Vulture 用 3 表示“扫描完成且发现死代码”，它属于仓库问题而不是执行失败。
    if len(cmd) >= 3 and cmd[1:3] == ['-m', 'vulture'] and return_code == 3:
        return BLOCKED, True
    status = {0: PASS, 1: BLOCKED, 2: FAIL}.get(return_code)
    return (status, True) if status is not None else (FAIL, False)


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


def _audit_successful_output(
    name: str,
    cmd: list[str],
    full_output: str,
    output: str,
) -> tuple[str, str, str]:
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
            'execution-skipped',
        )
    warning_reason = _warning_after_trigger_reason(full_output, gate_name=name, cmd=cmd)
    if warning_reason:
        return (
            BLOCKED,
            (
                f'{output}\n\n'
                f'[quality-gate] BLOCKED: {warning_reason}. '
                'Triggered pytest/quality/full/release gates must be warning-free; '
                'fix the warning or mark the gate BLOCKED instead of reporting PASS.'
            ),
            '',
        )
    return PASS, output, ''


def _detail_from_bounded_run(
    name: str,
    cmd: list[str],
    *,
    timeout: int,
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
            reason='timeout',
        )
    output = full_output[-COMMAND_OUTPUT_TAIL_CHARS:]
    if bounded.return_code is None:
        return GateDetail(
            name=name,
            status=FAIL,
            command=cmd,
            durationMs=duration,
            output=f'命令启动失败: {bounded.output_tail or bounded.exit_reason}',
            executionState='CAPABILITY_FAILED',
            reason='runtime-missing',
        )

    owner_result = _owner_result(full_output)
    status, known_exit_code = _command_exit_status(cmd, bounded.return_code)
    reason = 'outcome-unknown' if status == FAIL else ''
    if owner_result is not None:
        marker_status, marker_reason = owner_result
        expected_exit = {PASS: 0, BLOCKED: 1, FAIL: 2}[marker_status]
        if bounded.return_code == expected_exit:
            status, reason = marker_status, marker_reason
        else:
            status, reason = FAIL, 'outcome-unknown'
            output = f'{output}\n\n[quality-gate] FAIL: owner marker conflicts with exit code.'
    if status == PASS:
        status, output, reason = _audit_successful_output(name, cmd, full_output, output)
    elif not known_exit_code:
        output = f'{output}\n\n[quality-gate] FAIL: unrecognized exit code.'
    return GateDetail(
        name=name,
        status=status,
        command=cmd,
        exitCode=bounded.return_code,
        durationMs=duration,
        output=output,
        taskOutcomes=(_gradle_task_outcomes(full_output) if Path(cmd[0]).name == 'gradlew' else {}),
        taskFailureReasons=(
            _gradle_task_failure_reasons(full_output) if Path(cmd[0]).name == 'gradlew' else {}
        ),
        reason=reason,
    )


def run_cmd(
    name: str,
    cmd: list[str],
    cwd: Path,
    env_overrides: dict[str, str] | None = None,
    timeout_seconds: int | None = None,
) -> GateDetail:
    """执行单条受控命令，并严格归约 timeout、skip、warning 与网络阻断状态。"""
    if not cmd or shutil.which(cmd[0]) is None:
        return GateDetail(
            name=name,
            status=FAIL,
            command=cmd,
            durationMs=0,
            output=f'命令不存在: {cmd[0] if cmd else "<empty>"}',
            executionState='CAPABILITY_FAILED',
            reason='runtime-missing',
        )

    timeout = timeout_seconds or DEFAULT_TIMEOUT_SECONDS

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
            timeout=timeout,
            log_path=log_path,
            bounded=bounded,
        )
    except OSError as exc:
        return GateDetail(
            name=name,
            status=FAIL,
            command=cmd,
            output=f'命令启动失败: {exc}',
            executionState='CAPABILITY_FAILED',
            reason='runtime-missing',
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


def _declared_command(profile: RunProfile, repo_root: Path) -> list[str]:
    """通用渲染 catalog command；不按普通 Gate 名称分派。"""
    argv = profile.argv
    if not argv or any(not (repo_root / path).exists() for path in profile.required_paths):
        return []
    command = [_expand_argument(part, repo_root) for part in argv]
    globbed = _relative_existing_files(repo_root, list(profile.append_globs))
    if profile.append_globs and not globbed:
        return []
    command.extend(globbed)
    return command


def _python_check_command(profile: RunProfile, repo_root: Path) -> list[str]:
    """从 typed check id 构造调用；不从 argv 反向猜测 check。"""
    if not profile.check_id:
        return []
    python = _project_python(repo_root, dev=profile.runtime == 'dev')
    command = [python, '-m', 'scripts.checks', profile.check_id]
    command.extend(_expand_argument(part, repo_root) for part in profile.args)
    return command


def _scan_smoke_command(profile: RunProfile, repo_root: Path) -> list[str]:
    """构造 scan smoke 的 pytest 命令；Gradle prerequisite 由 group 负责。"""
    return [_project_python(repo_root, dev=True), '-m', 'pytest', *profile.args, *profile.tests]


def _playwright_command(profile: RunProfile, repo_root: Path) -> list[str]:
    """构造仓库唯一 Playwright runner 命令。"""
    return [
        'npm',
        '--prefix',
        'tests/playwright',
        'test',
        '--',
        *profile.tests,
        *(_expand_argument(part, repo_root) for part in profile.args),
    ]


_COMMAND_ADAPTERS = {
    'command': _declared_command,
    'python-check': _python_check_command,
    'playwright': _playwright_command,
    'scan-smoke': _scan_smoke_command,
}


def _capability(spec: GateSpec) -> str:
    """返回 catalog 声明的执行能力类型。"""
    return spec.run.kind.value


def command_for_gate(
    spec: GateSpec, repo_root: Path, mode: ExecutionMode | str = ExecutionMode.INCREMENTAL
) -> list[str]:
    """从 typed declaration 构造单 Gate 命令。"""
    selected_mode = ExecutionMode(mode)
    profile = spec.run.profile_for(selected_mode)
    if spec.run.kind in {RunKind.GRADLE_TASK, RunKind.JAVA_RULE}:
        gradlew = repo_root / 'gradlew'
        tasks = profile.tasks or (':java:tests:quality-gates:runJavaQualityGates',)
        java_rules = (
            [f'{JAVA_QUALITY_RULES_PROPERTY}{",".join(profile.rules)}'] if profile.rules else []
        )
        return [str(gradlew), *tasks, *java_rules, *profile.args] if gradlew.exists() else []
    try:
        adapter = _COMMAND_ADAPTERS[spec.run.kind.value]
    except KeyError as exc:
        raise ValueError(f'unsupported command capability: {spec.run.kind.value}') from exc
    return adapter(profile, repo_root)


def gate_command(
    gate: str, repo_root: Path, mode: ExecutionMode | str = ExecutionMode.INCREMENTAL
) -> list[str]:
    """按名称读取 typed catalog，并委托能力 adapter。"""
    return command_for_gate(gate_by_name(gate), repo_root, mode)


def gate_request_environment(gate_plan: GatePlan) -> dict[str, str]:
    """把统一 GateRequest 编码为所有 owner 都能读取的受控环境变量。"""
    environment = {'QUALITY_EXECUTION_MODE': gate_plan.mode.value}
    if gate_plan.mode is ExecutionMode.INCREMENTAL:
        environment['QUALITY_CHANGED_FILES'] = json.dumps(
            gate_plan.changed_files, ensure_ascii=False
        )
    return environment


def _stable_hash(value: object) -> str:
    """计算 JSON 数据的稳定 SHA-256。"""
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def _unique_gate_entries(gate_plan: GatePlan) -> list[GateSpec]:
    """Planner 已按 Catalog 顺序去重，Executor 不再重建 Target 归属。"""
    return list(gate_plan.gates)


def _build_command_groups(
    entries: list[GateSpec],
    gate_plan: GatePlan,
    repo_root: Path,
    *,
    base_url: str | None,
) -> tuple[list[CommandGroup], dict[str, str]]:
    """为每个 Gate 构造独立命令；独立边界保证时效证据真正属于该 Gate。"""
    groups: list[CommandGroup] = []
    group_by_gate: dict[str, str] = {}
    command_index = 1
    for spec in entries:
        capability = _capability(spec)
        profile = spec.run.profile_for(gate_plan.mode)
        environment = {
            'SESSION_BROWSER_PYTHON': _project_python(repo_root),
            **gate_request_environment(gate_plan),
        }
        if capability == 'scan-smoke':
            prerequisite_id = f'group-{command_index:03d}-{spec.name}-prerequisite'
            command_index += 1
            groups.append(
                CommandGroup(
                    group_id=prerequisite_id,
                    kind='scan-prerequisite',
                    command=(
                        str(repo_root / 'gradlew'),
                        *profile.prerequisite_tasks,
                        '--console=plain',
                    ),
                    environment=tuple(sorted(environment.items())),
                    gate_names=(spec.name,),
                    timeout_seconds=profile.timeout_seconds,
                )
            )
        command = (
            _scan_smoke_command(profile, repo_root)
            if capability == 'scan-smoke'
            else command_for_gate(spec, repo_root, gate_plan.mode)
        )
        if spec.run.kind in {RunKind.GRADLE_TASK, RunKind.JAVA_RULE}:
            command.append('--console=plain')
        group_id = f'group-{command_index:03d}-{spec.name}'
        command_index += 1
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
                kind=(
                    'gradle'
                    if spec.run.kind in {RunKind.GRADLE_TASK, RunKind.JAVA_RULE}
                    else 'scan-smoke'
                    if capability == 'scan-smoke'
                    else 'command'
                ),
                command=tuple(command),
                environment=tuple(sorted(environment.items())),
                gate_names=(spec.name,),
                timeout_seconds=profile.timeout_seconds,
            )
        )
        group_by_gate[spec.name] = group_id
    return groups, group_by_gate


def _freeze_planned_gates(
    entries: list[GateSpec],
    group_by_gate: dict[str, str],
    group_kind_by_id: dict[str, str],
    mode: ExecutionMode,
) -> tuple[PlannedGate, ...]:
    """冻结逻辑 Gate 到命令 group 与状态来源的映射。"""
    return tuple(
        PlannedGate(
            name=spec.name,
            target='',
            group_id=group_by_gate[spec.name],
            status_source=(
                'gradle-task-outcome'
                if group_kind_by_id[group_by_gate[spec.name]] == 'gradle'
                else 'process-exit'
            ),
            timeout_seconds=spec.run.profile_for(mode).timeout_seconds,
        )
        for spec in entries
    )


def build_execution_plan(
    gate_plan: GatePlan,
    repo_root: Path,
    *,
    base_url: str | None = None,
) -> ExecutionPlan:
    """按“去重 → 稳定分组 → 冻结指纹”生成不可变串行执行计划。"""
    entries = _unique_gate_entries(gate_plan)
    groups, group_by_gate = _build_command_groups(entries, gate_plan, repo_root, base_url=base_url)
    group_kind_by_id = {group.group_id: group.kind for group in groups}
    planned = _freeze_planned_gates(entries, group_by_gate, group_kind_by_id, gate_plan.mode)
    payload = {
        'changedFiles': gate_plan.changed_files,
        'mode': gate_plan.mode.value,
        'selector': gate_plan.selector,
        'selectorValue': gate_plan.selector_value,
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
        return GateDetail(
            name=group.group_id,
            status=FAIL,
            output='Gate command unavailable.',
            executionState='CAPABILITY_FAILED',
            reason='runtime-missing',
        )
    return run_cmd(
        group.group_id,
        list(group.command),
        repo_root,
        env_overrides=dict(group.environment),
        timeout_seconds=group.timeout_seconds,
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
    if any(value == 'FAIL' for value in resolved):
        return 'FAIL'
    if any(value == 'FAILED' for value in resolved):
        return 'FAILED'
    if any(value in {'SKIPPED', 'NO-SOURCE'} for value in resolved):
        return 'NOT_EXECUTED'
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
        for task in gate_by_name(name)
        .run.profile_for(ExecutionMode(dict(group.environment)['QUALITY_EXECUTION_MODE']))
        .prerequisite_tasks
    )
    return bool(
        gradle_outcome
        and gradle_outcome.status == PASS
        and tasks
        and _gradle_gate_outcome(gradle_outcome.taskOutcomes, tasks) == 'EXECUTED'
    )


def _with_total_scan_duration(detail: GateDetail, prerequisite: GateDetail) -> GateDetail:
    """把 prerequisite 与 pytest 的实际耗时合并为 scan Gate 的唯一耗时。"""
    if detail.durationMs is None and prerequisite.durationMs is None:
        return detail
    return replace(
        detail,
        durationMs=(detail.durationMs or 0) + (prerequisite.durationMs or 0),
    )


def _run_groups_serially(
    groups: tuple[CommandGroup, ...],
    repo_root: Path,
    *,
    environment_overrides: dict[str, str] | None = None,
) -> dict[str, GateDetail]:
    """逐项执行独立命令；scan prerequisite 与测试共享同一个 Gate timeout。"""
    overrides = environment_overrides or {}
    reserved = GATE_REQUEST_ENVIRONMENT_KEYS & overrides.keys()
    if reserved:
        names = ', '.join(sorted(reserved))
        raise ValueError(f'GateRequest environment cannot be overridden: {names}')
    execution_groups = tuple(
        replace(
            group,
            environment=tuple(sorted({**dict(group.environment), **overrides}.items())),
        )
        for group in groups
    )
    outcomes: dict[str, GateDetail] = {}
    scan_prerequisites: dict[str, GateDetail] = {}
    for group in execution_groups:
        if group.kind == 'scan-prerequisite':
            detail = _execute_group(group, repo_root)
            for gate_name in group.gate_names:
                scan_prerequisites[gate_name] = detail
        elif group.kind == 'scan-smoke':
            prerequisite = scan_prerequisites.get(group.gate_names[0])
            if not _scan_prerequisite_passed(group, prerequisite):
                detail = GateDetail(
                    name=group.group_id,
                    status=FAIL,
                    durationMs=prerequisite.durationMs if prerequisite else None,
                    output=(
                        'scan-smoke Gradle prerequisite did not complete successfully.\n'
                        + (prerequisite.output if prerequisite else 'prerequisite result missing')
                    ),
                    executionState='DEPENDENCY_FAILED',
                    reason='dependency-unavailable',
                )
            else:
                remaining_ms = group.timeout_seconds * 1000 - (prerequisite.durationMs or 0)
                if remaining_ms <= 0:
                    detail = GateDetail(
                        name=group.group_id,
                        status=FAIL,
                        durationMs=prerequisite.durationMs,
                        output='scan-smoke prerequisite consumed the complete Gate timeout.',
                        reason='timeout',
                    )
                else:
                    remaining_seconds = max(1, (remaining_ms + 999) // 1000)
                    detail = _execute_group(
                        replace(group, timeout_seconds=remaining_seconds), repo_root
                    )
                    detail = _with_total_scan_duration(detail, prerequisite)
        else:
            detail = _execute_group(group, repo_root)
        outcomes[group.group_id] = detail
    return outcomes


def _logical_gate_detail(
    gate: PlannedGate,
    group: CommandGroup,
    outcome: GateDetail,
) -> GateDetail:
    """把 group 技术结果映射为单个逻辑 Gate 明细。"""
    status = outcome.status
    output = outcome.output
    reason = outcome.reason
    spec = gate_by_name(gate.name)
    mode = ExecutionMode(dict(group.environment)['QUALITY_EXECUTION_MODE'])
    profile = spec.run.profile_for(mode)
    selected_outcomes: dict[str, str] = {}
    selected_failure_reasons: dict[str, str] = {}
    task_outcome: str | None = None
    if group.kind == 'gradle':
        selected_run = spec.run
        selected_profile = profile
        selected_tasks = selected_profile.tasks or (
            (':java:tests:quality-gates:runJavaQualityGates',)
            if selected_run.kind is RunKind.JAVA_RULE
            else ()
        )
        task_outcome = _gradle_gate_outcome(outcome.taskOutcomes, selected_tasks)
        selected_outcomes = _selected_task_outcomes(outcome.taskOutcomes, selected_tasks)
        selected_failure_reasons = _selected_task_outcomes(
            outcome.taskFailureReasons, selected_tasks
        )
        if task_outcome == 'BLOCKED':
            status = BLOCKED
            reason = ''
            output = (
                f'{output}\n'
                '[quality-gate] BLOCKED: selected Gradle task reported a blocking result.'
            )
        elif task_outcome == 'FAIL':
            status = FAIL
            reason = next(
                iter(selected_failure_reasons.values()),
                'outcome-unknown',
            )
            output = f'{output}\n[quality-gate] FAIL: selected Gradle task owner failed.'
        elif task_outcome == 'NOT_EXECUTED':
            status = FAIL
            reason = 'execution-skipped'
            output = f'{output}\n[quality-gate] FAIL: selected Gradle task was not executed.'
        elif task_outcome == 'FAILED':
            # Gradle exit 1 表示 owner 完整运行后发现测试或规则问题。
            status = BLOCKED if outcome.status == BLOCKED else FAIL
            reason = '' if status == BLOCKED else (reason or 'outcome-unknown')
        elif task_outcome == 'EXECUTED':
            status = PASS
            reason = ''
        else:
            status = FAIL
            reason = 'outcome-unknown'
            output = (
                f'{output}\n[quality-gate] FAIL: selected Gradle task outcome was not confirmed.'
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
            else 'EXECUTED'
            if status == BLOCKED
            else 'FAILED'
        ),
        groupId=group.group_id,
        rerunCommand=shlex.join(group.command),
        taskOutcomes=selected_outcomes,
        taskFailureReasons=selected_failure_reasons,
        mode=mode.value,
        targetSeconds=profile.target_seconds,
        timingState=(
            'OVER_TARGET'
            if outcome.durationMs is not None and outcome.durationMs > profile.target_seconds * 1000
            else 'WITHIN_TARGET'
        ),
        reason=reason,
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
