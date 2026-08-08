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
    RunStep,
)
from scripts.gates.report import (
    BLOCKED,
    FAIL,
    PASS,
    GateDetail,
)
from scripts.gates.runtime.environment import sanitized_environment
from scripts.gates.runtime.process import ManagedRunResult, run_managed
from scripts.gates.support import (
    ensure_private_directory,
    identity_from_values,
    quality_dir,
    resolve_runtime_root,
    stable_hash,
)
from scripts.harness.python_env import project_venv_dir, resolve_python

PLAYWRIGHT_COMMAND_MIN_PARTS = 5
PLAYWRIGHT_MIN_WORKERS = 8
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


def _detail_from_managed_run(
    name: str,
    cmd: list[str],
    *,
    log_path: Path,
    managed: ManagedRunResult,
) -> GateDetail:
    """读取无 deadline 的受控进程结果，并归约 Gate 业务状态。"""
    try:
        full_output = log_path.read_text(encoding='utf-8', errors='replace').strip()
    except OSError:
        full_output = managed.output_tail.strip()
    duration = int(managed.duration_seconds * 1000)
    output = full_output[-COMMAND_OUTPUT_TAIL_CHARS:]
    if managed.return_code is None:
        return GateDetail(
            name=name,
            status=FAIL,
            command=cmd,
            durationMs=duration,
            output=f'命令启动失败: {managed.output_tail or managed.exit_reason}',
            executionState='CAPABILITY_FAILED',
            reason='runtime-missing',
        )
    if managed.return_code < 0:
        return GateDetail(
            name=name,
            status=FAIL,
            command=cmd,
            exitCode=managed.return_code,
            durationMs=duration,
            output=output or f'process terminated by signal {-managed.return_code}',
            reason='process-signaled',
        )

    owner_result = _owner_result(full_output)
    status, known_exit_code = _command_exit_status(cmd, managed.return_code)
    reason = 'outcome-unknown' if status == FAIL else ''
    if owner_result is not None:
        marker_status, marker_reason = owner_result
        expected_exit = {PASS: 0, BLOCKED: 1, FAIL: 2}[marker_status]
        if managed.return_code == expected_exit:
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
        exitCode=managed.return_code,
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
) -> GateDetail:
    """执行单条无自动 deadline 的受控命令。"""
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
    run_env = gate_child_environment(cwd, env_overrides)
    if _is_playwright_command(cmd) and run_env.get('FORCE_COLOR') and run_env.get('NO_COLOR'):
        run_env.pop('NO_COLOR', None)
    try:
        log_name = re.sub(r'[^A-Za-z0-9_.-]+', '-', name)[:80] or 'gate'
        command_hash = stable_hash(json.dumps(cmd, ensure_ascii=False, separators=(',', ':')))
        log_path = _run_tmp_dir(cwd, 'logs') / f'{log_name}-{command_hash[:12]}.log'
        managed = run_managed(cmd, cwd=cwd, env=run_env, log_path=log_path)
        return _detail_from_managed_run(name, cmd, log_path=log_path, managed=managed)
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
    values = {
        'python': _project_python(repo_root),
        'dev_python': _project_python(repo_root, dev=True),
        'repo_root': str(repo_root),
        'playwright_workers': str(_playwright_workers()),
    }
    return argument.format_map(values)


def _declared_command(step: RunStep, repo_root: Path) -> list[str]:
    if not step.argv or any(not (repo_root / path).exists() for path in step.required_paths):
        return []
    command = [_expand_argument(part, repo_root) for part in step.argv]
    globbed = _relative_existing_files(repo_root, list(step.append_globs))
    if step.append_globs and not globbed:
        return []
    return [*command, *globbed]


def _python_check_command(step: RunStep, repo_root: Path) -> list[str]:
    if not step.check_id:
        return []
    python = _project_python(repo_root, dev=step.runtime == 'dev')
    return [
        python,
        '-m',
        'scripts.gates.checks',
        step.check_id,
        *(_expand_argument(part, repo_root) for part in step.args),
    ]


def _scan_smoke_command(step: RunStep, repo_root: Path) -> list[str]:
    return [_project_python(repo_root, dev=True), '-m', 'pytest', *step.args, *step.tests]


def _playwright_command(step: RunStep, repo_root: Path) -> list[str]:
    return [
        'npm',
        '--prefix',
        'tests/playwright',
        'test',
        '--',
        *step.tests,
        *(_expand_argument(part, repo_root) for part in step.args),
    ]


_COMMAND_ADAPTERS = {
    RunKind.COMMAND: _declared_command,
    RunKind.PYTHON_CHECK: _python_check_command,
    RunKind.PLAYWRIGHT: _playwright_command,
    RunKind.SCAN_SMOKE: _scan_smoke_command,
}


def command_for_step(step: RunStep, repo_root: Path) -> list[str]:
    """从一个 typed ``RunStep`` 构造唯一真实命令。"""
    if step.kind in {RunKind.GRADLE_TASK, RunKind.JAVA_RULE}:
        gradlew = repo_root / 'gradlew'
        tasks = step.tasks or (':java:tests:quality-gates:runJavaQualityGates',)
        java_rules = [f'{JAVA_QUALITY_RULES_PROPERTY}{",".join(step.rules)}'] if step.rules else []
        return [str(gradlew), *tasks, *java_rules, *step.args] if gradlew.exists() else []
    try:
        return _COMMAND_ADAPTERS[step.kind](step, repo_root)
    except KeyError as exc:
        raise ValueError(f'unsupported command capability: {step.kind.value}') from exc


def gate_request_environment(gate_plan: GatePlan) -> dict[str, str]:
    """把执行范围安全传给 owner，增量模式同时携带已冻结的改动文件。"""

    environment = {'QUALITY_EXECUTION_MODE': gate_plan.mode.value}
    if gate_plan.mode is ExecutionMode.INCREMENTAL:
        environment['QUALITY_CHANGED_FILES'] = json.dumps(
            gate_plan.changed_files, ensure_ascii=False
        )
    return environment


def _build_command_groups(
    entries: list[GateSpec], gate_plan: GatePlan, repo_root: Path, *, base_url: str | None
) -> tuple[list[CommandGroup], dict[str, tuple[str, ...]]]:
    """按 Gate/step 声明顺序构造每组一条真实命令。"""
    groups: list[CommandGroup] = []
    group_ids_by_gate: dict[str, tuple[str, ...]] = {}
    command_index = 1
    for spec in entries:
        gate_group_ids: list[str] = []
        for step in spec.run.steps:
            environment = {
                'SESSION_BROWSER_PYTHON': _project_python(repo_root),
                **gate_request_environment(gate_plan),
            }
            if step.kind is RunKind.PLAYWRIGHT:
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
            if step.kind is RunKind.SCAN_SMOKE:
                prerequisite_id = f'group-{command_index:03d}-{spec.name}-{step.name}-prerequisite'
                command_index += 1
                groups.append(
                    CommandGroup(
                        prerequisite_id,
                        'scan-prerequisite',
                        (str(repo_root / 'gradlew'), *step.prerequisite_tasks, '--console=plain'),
                        tuple(sorted(environment.items())),
                        spec.name,
                        step.name,
                    )
                )
                gate_group_ids.append(prerequisite_id)
            command = command_for_step(step, repo_root)
            if step.kind in {RunKind.GRADLE_TASK, RunKind.JAVA_RULE}:
                command.append('--console=plain')
            group_id = f'group-{command_index:03d}-{spec.name}-{step.name}'
            command_index += 1
            groups.append(
                CommandGroup(
                    group_id,
                    'gradle'
                    if step.kind in {RunKind.GRADLE_TASK, RunKind.JAVA_RULE}
                    else step.kind.value,
                    tuple(command),
                    tuple(sorted(environment.items())),
                    spec.name,
                    step.name,
                )
            )
            gate_group_ids.append(group_id)
        group_ids_by_gate[spec.name] = tuple(gate_group_ids)
    return groups, group_ids_by_gate


def build_execution_plan(
    gate_plan: GatePlan, repo_root: Path, *, base_url: str | None = None
) -> ExecutionPlan:
    """把逻辑选择转换为可复现的命令组计划，不在此阶段启动子进程。"""

    entries = list(gate_plan.gates)
    groups, group_ids_by_gate = _build_command_groups(
        entries, gate_plan, repo_root, base_url=base_url
    )
    planned = tuple(
        PlannedGate(
            name=spec.name,
            group_ids=group_ids_by_gate[spec.name],
            target_seconds=spec.run.target_for(gate_plan.mode),
        )
        for spec in entries
    )
    payload = {
        'changedFiles': gate_plan.changed_files,
        'mode': gate_plan.mode.value,
        'selector': gate_plan.selector,
        'selectorValue': gate_plan.selector_value,
        'gates': [asdict(item) for item in planned],
        'groups': [asdict(item) for item in groups],
    }
    fingerprint = stable_hash(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    )
    return ExecutionPlan(f'plan-{fingerprint[:16]}', fingerprint, gate_plan, planned, tuple(groups))


def _execute_group(group: CommandGroup, repo_root: Path) -> GateDetail:
    if not group.command:
        return GateDetail(
            name=group.step_name,
            status=FAIL,
            output='Gate command unavailable.',
            executionState='CAPABILITY_FAILED',
            reason='runtime-missing',
            groupId=group.group_id,
        )
    return run_cmd(
        group.step_name, list(group.command), repo_root, env_overrides=dict(group.environment)
    )


def _gradle_gate_outcome(task_outcomes: dict[str, str], tasks: tuple[str, ...]) -> str | None:
    """只归约当前 leaf 声明的 Gradle task，避免旁支 task 污染结果。"""

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
    if any(value == 'FAIL' for value in resolved):
        return 'FAIL'
    if any(value in {'SKIPPED', 'NO-SOURCE'} for value in resolved):
        return 'NOT_EXECUTED'
    if any(value == 'BLOCKED' for value in resolved):
        return 'BLOCKED'
    if any(value == 'FAILED' for value in resolved):
        return 'FAILED'
    return 'EXECUTED' if resolved else None


def _selected_task_outcomes(
    task_outcomes: dict[str, str], tasks: tuple[str, ...]
) -> dict[str, str]:
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


def _scan_prerequisite_passed(step: RunStep, outcome: GateDetail | None) -> bool:
    return bool(
        outcome
        and outcome.status == PASS
        and step.prerequisite_tasks
        and _gradle_gate_outcome(outcome.taskOutcomes, step.prerequisite_tasks) == 'EXECUTED'
    )


def _sum_duration(details: list[GateDetail]) -> int | None:
    if any(detail.durationMs is None for detail in details):
        return None
    return sum(detail.durationMs or 0 for detail in details)


def _run_groups_serially(
    groups: tuple[CommandGroup, ...],
    repo_root: Path,
    *,
    environment_overrides: dict[str, str] | None = None,
) -> dict[str, GateDetail]:
    """执行全部 group；业务 FAIL/BLOCKED 不会中止后续 leaf。"""
    overrides = environment_overrides or {}
    reserved = GATE_REQUEST_ENVIRONMENT_KEYS & overrides.keys()
    if reserved:
        raise ValueError(
            f'GateRequest environment cannot be overridden: {", ".join(sorted(reserved))}'
        )
    execution_groups = tuple(
        replace(group, environment=tuple(sorted({**dict(group.environment), **overrides}.items())))
        for group in groups
    )
    outcomes: dict[str, GateDetail] = {}
    prerequisites: dict[tuple[str, str], GateDetail] = {}
    for group in execution_groups:
        key = (group.gate_name, group.step_name)
        if group.kind == 'scan-prerequisite':
            detail = _execute_group(group, repo_root)
            prerequisites[key] = detail
        elif group.kind == RunKind.SCAN_SMOKE.value:
            step = next(
                step
                for step in gate_by_name(group.gate_name).run.steps
                if step.name == group.step_name
            )
            prerequisite = prerequisites.get(key)
            if not _scan_prerequisite_passed(step, prerequisite):
                detail = GateDetail(
                    name=group.step_name,
                    status=FAIL,
                    durationMs=prerequisite.durationMs if prerequisite else None,
                    output='scan-smoke Gradle prerequisite did not complete successfully.\n'
                    + (prerequisite.output if prerequisite else 'prerequisite result missing'),
                    executionState='DEPENDENCY_FAILED',
                    reason='dependency-unavailable',
                    taskOutcomes=prerequisite.taskOutcomes if prerequisite else {},
                )
            else:
                pytest_detail = _execute_group(group, repo_root)
                detail = replace(
                    pytest_detail, durationMs=_sum_duration([prerequisite, pytest_detail])
                )
        else:
            detail = _execute_group(group, repo_root)
        outcomes[group.group_id] = replace(detail, groupId=group.group_id)
    return outcomes


def _leaf_detail(spec: GateSpec, group: CommandGroup, outcome: GateDetail) -> GateDetail:
    """按 leaf typed recipe 校验 task outcome，并保留结构化诊断。"""
    step = next(step for step in spec.run.steps if step.name == group.step_name)
    status, output, reason = outcome.status, outcome.output, outcome.reason
    selected_outcomes = dict(outcome.taskOutcomes)
    selected_failure_reasons = dict(outcome.taskFailureReasons)
    if group.kind == 'gradle':
        tasks = step.tasks or (
            (':java:tests:quality-gates:runJavaQualityGates',)
            if step.kind is RunKind.JAVA_RULE
            else ()
        )
        task_outcome = _gradle_gate_outcome(outcome.taskOutcomes, tasks)
        selected_outcomes = _selected_task_outcomes(outcome.taskOutcomes, tasks)
        selected_failure_reasons = _selected_task_outcomes(outcome.taskFailureReasons, tasks)
        if task_outcome == 'BLOCKED':
            status, reason = BLOCKED, ''
        elif task_outcome == 'FAIL':
            status = FAIL
            reason = next(iter(selected_failure_reasons.values()), 'outcome-unknown')
        elif task_outcome == 'NOT_EXECUTED':
            status, reason = FAIL, 'execution-skipped'
        elif task_outcome == 'FAILED':
            # Java rule owner 会为已完成的规则问题输出 BLOCKED marker。只有裸 Gradle
            # FAILED 时，说明 owner 没能给出业务结论，应按执行未完成归为 FAIL。
            if step.kind is RunKind.JAVA_RULE:
                status = FAIL
            else:
                status = BLOCKED if outcome.status == BLOCKED else FAIL
            reason = '' if status == BLOCKED else (reason or 'outcome-unknown')
        elif task_outcome == 'EXECUTED':
            status, reason = PASS, ''
        else:
            status, reason = FAIL, 'outcome-unknown'
            output = (
                f'{output}\n[quality-gate] FAIL: selected Gradle task outcome was not confirmed.'
            )
    return GateDetail(
        name=step.name,
        status=status,
        command=list(group.command),
        exitCode=outcome.exitCode,
        durationMs=outcome.durationMs,
        output=output,
        executionState='EXECUTED'
        if status == PASS
        else 'BLOCKED'
        if status == BLOCKED
        else 'FAILED',
        groupId=group.group_id,
        rerunCommand=shlex.join(group.command),
        taskOutcomes=selected_outcomes,
        taskFailureReasons=selected_failure_reasons,
        reason=reason,
    )


def _aggregate_status(leaves: list[GateDetail]) -> str:
    """按 FAIL、BLOCKED、PASS 的固定优先级归约全部 leaf。"""

    if not leaves or any(leaf.status == FAIL for leaf in leaves):
        return FAIL
    if any(leaf.status == BLOCKED for leaf in leaves):
        return BLOCKED
    return PASS if all(leaf.status == PASS for leaf in leaves) else FAIL


def _logical_gate_detail(
    gate: PlannedGate,
    groups: list[CommandGroup],
    outcomes: dict[str, GateDetail],
    mode: ExecutionMode,
) -> GateDetail:
    """汇总逻辑 Gate 的全部 leaf 证据，并记录非阻断时效信息。"""

    spec = gate_by_name(gate.name)
    leaves: list[GateDetail] = []
    for group in groups:
        if group.kind == 'scan-prerequisite':
            continue
        leaves.append(_leaf_detail(spec, group, outcomes[group.group_id]))
    status = _aggregate_status(leaves)
    duration = _sum_duration(leaves)
    timing = (
        'UNKNOWN'
        if duration is None
        else ('OVER_TARGET' if duration > gate.target_seconds * 1000 else 'WITHIN_TARGET')
    )
    failed_outputs = [f'{leaf.name}: {leaf.output}' for leaf in leaves if leaf.status != PASS]
    output = (
        '\n'.join(failed_outputs) if failed_outputs else '\n'.join(leaf.output for leaf in leaves)
    )
    task_outcomes = {key: value for leaf in leaves for key, value in leaf.taskOutcomes.items()}
    failure_reasons = {
        key: value for leaf in leaves for key, value in leaf.taskFailureReasons.items()
    }
    reason = next((leaf.reason for leaf in leaves if leaf.status == FAIL and leaf.reason), '')
    return GateDetail(
        name=gate.name,
        status=status,
        command=leaves[0].command if len(leaves) == 1 else [],
        exitCode=leaves[0].exitCode if len(leaves) == 1 else None,
        durationMs=duration,
        output=output,
        executionState='EXECUTED'
        if status == PASS
        else 'BLOCKED'
        if status == BLOCKED
        else 'FAILED',
        groupId=leaves[0].groupId if len(leaves) == 1 else '',
        rerunCommand=leaves[0].rerunCommand if len(leaves) == 1 else '',
        taskOutcomes=task_outcomes,
        taskFailureReasons=failure_reasons,
        mode=mode.value,
        targetSeconds=gate.target_seconds,
        timingState=timing,
        reason=reason,
        leafResults=[
            {
                'name': leaf.name,
                'status': leaf.status,
                'reason': leaf.reason,
                'durationMs': leaf.durationMs,
                'command': leaf.command,
                'exitCode': leaf.exitCode,
                'groupId': leaf.groupId,
                'output': leaf.output,
                'taskOutcomes': leaf.taskOutcomes,
                'taskFailureReasons': leaf.taskFailureReasons,
            }
            for leaf in leaves
        ],
    )


def execute_plan(
    execution_plan: ExecutionPlan,
    repo_root: Path,
    *,
    environment_overrides: dict[str, str] | None = None,
) -> tuple[GateDetail, ...]:
    """完整执行计划中的所有命令组，再按逻辑 Gate 返回有序结果。"""

    outcomes = _run_groups_serially(
        execution_plan.groups, repo_root, environment_overrides=environment_overrides
    )
    group_by_id = {group.group_id: group for group in execution_plan.groups}
    return tuple(
        _logical_gate_detail(
            gate,
            [group_by_id[group_id] for group_id in gate.group_ids],
            outcomes,
            execution_plan.gate_plan.mode,
        )
        for gate in execution_plan.gates
    )
