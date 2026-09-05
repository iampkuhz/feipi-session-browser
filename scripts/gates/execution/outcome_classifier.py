"""负责使用 owner 类型化协议把进程事实归类为执行结果；不负责监管进程。

由 Execution 运行编排器在每次进程结束后调用。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scripts.gates.execution.process_supervisor import ProcessObservation
    from scripts.gates.planning.plan_compiler import CommandInvocation

OUTPUT_TAIL_CHARS = 4000


class ExecutionStatus(StrEnum):
    """表示执行事实归类后的三态结果，不包含选择态。"""

    PASS = 'PASS'
    BLOCKED = 'BLOCKED'
    FAIL = 'FAIL'


@dataclass(frozen=True, slots=True)
class InvocationResult:
    """一个 CommandInvocation 的类型化执行证据。"""

    invocation_id: str
    gate_name: str
    recipe_step_name: str
    status: ExecutionStatus
    reason: str
    return_code: int | None
    duration_seconds: float
    log_path: str
    output_tail: str
    task_outcomes: tuple[tuple[str, str], ...] = ()
    task_failure_reasons: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class StepResult:
    """一个 RecipeStep 的全部进程结果。"""

    gate_name: str
    recipe_step_name: str
    status: ExecutionStatus
    reason: str
    duration_seconds: float
    invocation_results: tuple[InvocationResult, ...]
    canonical_rerun: str


@dataclass(frozen=True, slots=True)
class GateResult:
    """一个逻辑 Gate 的全部 RecipeStep 结果。"""

    gate_name: str
    status: ExecutionStatus
    reason: str
    duration_seconds: float
    target_seconds: int
    timing_state: str
    step_results: tuple[StepResult, ...]
    canonical_rerun: str


_ANSI_RE = re.compile(r'\x1b\[[0-9;]*m')
_OWNER_RESULT_RE = re.compile(
    r'^GATE_RESULT status=(?P<status>PASS|BLOCKED|FAIL)'
    r'(?: reason=(?P<reason>[A-Za-z0-9._-]+))?(?: .*)?$',
    flags=re.MULTILINE,
)
_GRADLE_TASK_RE = re.compile(
    r'^> Task (?P<task>:\S+?)(?: (?P<outcome>UP-TO-DATE|FROM-CACHE|NO-SOURCE|SKIPPED|FAILED))?$',
    flags=re.MULTILINE,
)
_GRADLE_OWNER_RE = re.compile(
    r'^GATE_TASK_RESULT task=(?P<task>:\S+) status=(?P<status>BLOCKED|FAIL)'
    r'(?: reason=(?P<reason>[A-Za-z0-9._-]+))?$',
    flags=re.MULTILINE,
)
_GRADLE_VERIFICATION_TASK_RE = re.compile(
    r'^(?:check$|checkstyle(?:Main|Test)$|javadoc(?:Verify)?$|pmd(?:Main|Test)$|'
    r'spotless\w*Check$|test$|[a-z]\w*Test$|verify\w+$|runJavaQualityGates$|reuseStandardCpd$)'
)
_GRADLE_HOUSEKEEPING_TASKS = frozenset({':build-logic:checkKotlinGradlePluginConfigurationErrors'})


def _read_output(observation: ProcessObservation) -> str:
    try:
        return Path(observation.log_path).read_text(encoding='utf-8', errors='replace').strip()
    except OSError:
        return observation.output_tail.strip()


def _owner_marker(output: str) -> tuple[ExecutionStatus, str] | None:
    markers = [
        (ExecutionStatus(match.group('status')), match.group('reason') or '')
        for match in _OWNER_RESULT_RE.finditer(_ANSI_RE.sub('', output))
    ]
    if not markers:
        return None
    if len(set(markers)) != 1:
        return ExecutionStatus.FAIL, 'outcome-unknown'
    status, reason = markers[0]
    if status is ExecutionStatus.FAIL and not reason:
        return ExecutionStatus.FAIL, 'outcome-unknown'
    if status is not ExecutionStatus.FAIL and reason:
        return ExecutionStatus.FAIL, 'outcome-unknown'
    return status, reason


def _pytest_command(argv: tuple[str, ...]) -> bool:
    if not argv:
        return False
    executable = Path(argv[0]).name
    return executable == 'pytest' or (
        len(argv) >= 3 and executable.startswith('python') and argv[1:3] == ('-m', 'pytest')
    )


def _playwright_command(invocation: CommandInvocation) -> bool:
    argv = invocation.argv
    return invocation.kind == 'playwright' or (
        len(argv) >= 5
        and Path(argv[0]).name == 'npm'
        and argv[1:5] == ('--prefix', 'tests/playwright', 'test', '--')
    )


def _skip_count(output: str) -> int:
    return sum(int(value) for value in re.findall(r'\b(\d+)\s+skipped\b', _ANSI_RE.sub('', output)))


def _gradle_evidence(
    invocation: CommandInvocation, output: str
) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    """提取 Gradle task 事实，并筛出真实验证 owner 的公开证据。"""
    clean = _ANSI_RE.sub('', output)
    all_outcomes = {
        match.group('task'): match.group('outcome') or 'EXECUTED'
        for match in _GRADLE_TASK_RE.finditer(clean)
    }
    failures: dict[str, str] = {}
    for match in _GRADLE_OWNER_RE.finditer(clean):
        task = match.group('task')
        status = match.group('status')
        all_outcomes[task] = status
        if status == 'FAIL':
            failures[task] = match.group('reason') or 'outcome-unknown'
    declared_tasks = {
        task if task.startswith(':') else f':{task}'
        for task in invocation.argv[1:]
        if task and not task.startswith('-')
    }
    owner_outcomes = {
        task: outcome
        for task, outcome in all_outcomes.items()
        if task not in _GRADLE_HOUSEKEEPING_TASKS
        and (
            task in declared_tasks
            or outcome in {'FAILED', 'BLOCKED', 'FAIL'}
            or (
                outcome != 'NO-SOURCE'
                and _GRADLE_VERIFICATION_TASK_RE.match(task.rsplit(':', maxsplit=1)[-1])
            )
        )
    }
    return all_outcomes, owner_outcomes, failures


def _base_status(
    invocation: CommandInvocation,
    observation: ProcessObservation,
) -> tuple[ExecutionStatus, str] | None:
    if observation.exit_reason == 'INTERRUPTED':
        return ExecutionStatus.FAIL, 'interrupted'
    if observation.return_code is None:
        return ExecutionStatus.FAIL, 'runtime-missing'
    if observation.return_code < 0:
        return ExecutionStatus.FAIL, 'process-signaled'
    if not invocation.argv:
        return ExecutionStatus.FAIL, 'runtime-missing'
    if observation.stalled:
        return ExecutionStatus.FAIL, 'process-stalled'
    return None


def _classify_python_check(return_code: int, output: str) -> tuple[ExecutionStatus, str]:
    marker = _owner_marker(output)
    if marker is None:
        if return_code == 0:
            return ExecutionStatus.PASS, ''
        if return_code == 1:
            return ExecutionStatus.BLOCKED, 'verification-failed'
        return ExecutionStatus.FAIL, 'outcome-unknown'
    status, reason = marker
    expected = {
        ExecutionStatus.PASS: 0,
        ExecutionStatus.BLOCKED: 1,
        ExecutionStatus.FAIL: 2,
    }[status]
    if return_code != expected:
        return ExecutionStatus.FAIL, 'outcome-unknown'
    if status is ExecutionStatus.BLOCKED:
        return status, 'verification-failed'
    return status, reason


def _classify_pytest(return_code: int, output: str) -> tuple[ExecutionStatus, str]:
    if return_code == 0 and _skip_count(output):
        return ExecutionStatus.FAIL, 'execution-skipped'
    if return_code == 0:
        return ExecutionStatus.PASS, ''
    if return_code == 1:
        return ExecutionStatus.BLOCKED, 'verification-failed'
    reasons = {2: 'invocation-invalid', 3: 'interrupted', 4: 'invocation-invalid', 5: 'input-empty'}
    return ExecutionStatus.FAIL, reasons.get(return_code, 'outcome-unknown')


def _classify_playwright(return_code: int, output: str) -> tuple[ExecutionStatus, str]:
    if return_code == 0 and _skip_count(output):
        return ExecutionStatus.FAIL, 'execution-skipped'
    if return_code == 0:
        return ExecutionStatus.PASS, ''
    if return_code == 1:
        return ExecutionStatus.BLOCKED, 'verification-failed'
    if return_code in {126, 127}:
        return ExecutionStatus.FAIL, 'dependency-unavailable'
    return ExecutionStatus.FAIL, 'outcome-unknown'


def _classify_gradle(
    invocation: CommandInvocation,
    return_code: int,
    all_outcomes: dict[str, str],
    owner_outcomes: dict[str, str],
    failures: dict[str, str],
) -> tuple[ExecutionStatus, str]:
    declared_tasks = {
        task if task.startswith(':') else f':{task}'
        for task in invocation.argv[1:]
        if task and not task.startswith('-')
    }
    declared_outcomes = {
        task: outcome for task, outcome in all_outcomes.items() if task in declared_tasks
    }
    if any(value in {'SKIPPED', 'NO-SOURCE'} for value in declared_outcomes.values()):
        return ExecutionStatus.FAIL, 'execution-skipped'
    if any(value == 'SKIPPED' for value in owner_outcomes.values()):
        return ExecutionStatus.FAIL, 'execution-skipped'
    if any(value == 'FAIL' for value in all_outcomes.values()):
        return ExecutionStatus.FAIL, next(iter(failures.values()), 'outcome-unknown')
    if any(value == 'BLOCKED' for value in all_outcomes.values()):
        return ExecutionStatus.BLOCKED, 'verification-failed'
    if return_code == 0 and not any(value == 'FAILED' for value in all_outcomes.values()):
        return ExecutionStatus.PASS, ''
    if invocation.kind == 'gradle-prerequisite':
        return ExecutionStatus.FAIL, 'dependency-unavailable'
    if return_code == 1 and invocation.kind in {'gradle-task', 'java-rule'}:
        return ExecutionStatus.BLOCKED, 'verification-failed'
    return ExecutionStatus.FAIL, 'outcome-unknown'


def _classify_command(argv: tuple[str, ...], return_code: int) -> tuple[ExecutionStatus, str]:
    if return_code == 0:
        return ExecutionStatus.PASS, ''
    joined = ' '.join(argv)
    known_verifiers = ('ruff ', 'deptry ', 'bandit ', 'vulture', 'bash -n')
    if return_code == 1 or any(marker in joined for marker in known_verifiers):
        return ExecutionStatus.BLOCKED, 'verification-failed'
    return ExecutionStatus.FAIL, 'outcome-unknown'


def classify_owner_outcome(
    invocation: CommandInvocation,
    observation: ProcessObservation,
) -> InvocationResult:
    """按 owner 类型归类；不使用通用 warning 文本猜测。"""

    output = _read_output(observation)
    outcomes: dict[str, str] = {}
    failures: dict[str, str] = {}
    base = _base_status(invocation, observation)
    if base is not None:
        status, reason = base
    else:
        return_code = int(observation.return_code or 0)
        if invocation.kind == 'python-check':
            status, reason = _classify_python_check(return_code, output)
        elif _pytest_command(invocation.argv) or invocation.kind == 'scan-smoke':
            status, reason = _classify_pytest(return_code, output)
        elif _playwright_command(invocation):
            status, reason = _classify_playwright(return_code, output)
        elif invocation.kind in {'gradle-task', 'java-rule', 'gradle-prerequisite'}:
            all_outcomes, outcomes, failures = _gradle_evidence(invocation, output)
            status, reason = _classify_gradle(
                invocation, return_code, all_outcomes, outcomes, failures
            )
        else:
            status, reason = _classify_command(invocation.argv, return_code)
    return InvocationResult(
        invocation.invocation_id,
        invocation.gate_name,
        invocation.recipe_step_name,
        status,
        reason,
        observation.return_code,
        observation.duration_seconds,
        observation.log_path,
        output[-OUTPUT_TAIL_CHARS:],
        tuple(sorted(outcomes.items())),
        tuple(sorted(failures.items())),
    )
