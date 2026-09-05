"""Python Check、pytest、Playwright 与 Gradle 类型化 outcome contract。"""

from pathlib import Path

import pytest
from scripts.gates.execution.outcome_classifier import ExecutionStatus, classify_owner_outcome
from scripts.gates.execution.process_supervisor import ProcessObservation
from scripts.gates.planning.plan_compiler import CommandInvocation


def _classify(
    tmp_path: Path,
    kind: str,
    argv: tuple[str, ...],
    code: int | None,
    output: str,
    *,
    stalled: bool = False,
    exit_reason: str = 'EXITED',
):
    log = tmp_path / f'{kind}.log'
    log.write_text(output, encoding='utf-8')
    invocation = CommandInvocation('i', kind, argv, (), 'gate', 'step')
    observation = ProcessObservation(
        code,
        exit_reason,
        'command',
        'environment',
        'start',
        'finish',
        0.5,
        1,
        str(log),
        output,
        stalled=stalled,
    )
    return classify_owner_outcome(invocation, observation)


@pytest.mark.parametrize(
    ('code', 'marker', 'expected', 'reason'),
    [
        (0, 'GATE_RESULT status=PASS check=owner', ExecutionStatus.PASS, ''),
        (
            1,
            'GATE_RESULT status=BLOCKED check=owner',
            ExecutionStatus.BLOCKED,
            'verification-failed',
        ),
        (
            2,
            'GATE_RESULT status=FAIL reason=input-unavailable check=owner',
            ExecutionStatus.FAIL,
            'input-unavailable',
        ),
    ],
)
def test_python_check_uses_structured_owner_marker(
    tmp_path: Path, code: int, marker: str, expected: ExecutionStatus, reason: str
) -> None:
    result = _classify(tmp_path, 'python-check', ('python', '-m', 'checks'), code, marker)
    assert (result.status, result.reason) == (expected, reason)


def test_pytest_assertion_is_blocked_and_skip_is_fail(tmp_path: Path) -> None:
    blocked = _classify(tmp_path, 'command', ('python', '-m', 'pytest'), 1, '1 failed')
    skipped = _classify(tmp_path, 'command', ('python', '-m', 'pytest'), 0, '1 skipped')
    assert (blocked.status, blocked.reason) == (
        ExecutionStatus.BLOCKED,
        'verification-failed',
    )
    assert (skipped.status, skipped.reason) == (ExecutionStatus.FAIL, 'execution-skipped')


def test_playwright_assertion_is_blocked(tmp_path: Path) -> None:
    result = _classify(
        tmp_path,
        'playwright',
        ('npm', '--prefix', 'tests/playwright', 'test', '--'),
        1,
        '1 failed',
    )
    assert (result.status, result.reason) == (
        ExecutionStatus.BLOCKED,
        'verification-failed',
    )


def test_gradle_spotless_failure_is_verification_blocked(tmp_path: Path) -> None:
    result = _classify(
        tmp_path,
        'gradle-task',
        ('./gradlew', 'check', '--console=plain'),
        1,
        '> Task :java:index-api:spotlessJavaCheck FAILED',
    )
    assert (result.status, result.reason) == (
        ExecutionStatus.BLOCKED,
        'verification-failed',
    )
    assert dict(result.task_outcomes) == {':java:index-api:spotlessJavaCheck': 'FAILED'}


def test_gradle_prerequisite_failure_is_dependency_fail(tmp_path: Path) -> None:
    result = _classify(
        tmp_path,
        'gradle-prerequisite',
        ('./gradlew', ':java:app-cli:installDist'),
        1,
        '> Task :java:app-cli:installDist FAILED',
    )
    assert (result.status, result.reason) == (
        ExecutionStatus.FAIL,
        'dependency-unavailable',
    )


def test_gradle_rejects_skipped_owner_but_ignores_housekeeping(tmp_path: Path) -> None:
    housekeeping = _classify(
        tmp_path,
        'gradle-task',
        ('./gradlew', 'check'),
        0,
        '> Task :build-logic:compileJava NO-SOURCE\n'
        '> Task :build-logic:checkKotlinGradlePluginConfigurationErrors SKIPPED\n'
        '> Task :java:tests:contracts:pmdMain NO-SOURCE\n'
        '> Task :check UP-TO-DATE',
    )
    owner_skipped = _classify(
        tmp_path,
        'gradle-task',
        ('./gradlew', 'check'),
        0,
        '> Task :java:tests:contracts:pmdMain SKIPPED\n> Task :check UP-TO-DATE',
    )
    skipped = _classify(
        tmp_path,
        'gradle-task',
        ('./gradlew', 'check'),
        0,
        '> Task :check SKIPPED',
    )
    no_source = _classify(
        tmp_path,
        'gradle-task',
        ('./gradlew', ':empty:compileJava'),
        0,
        '> Task :empty:compileJava NO-SOURCE',
    )
    assert (housekeeping.status, housekeeping.reason) == (ExecutionStatus.PASS, '')
    assert dict(housekeeping.task_outcomes) == {':check': 'UP-TO-DATE'}
    assert (owner_skipped.status, owner_skipped.reason) == (
        ExecutionStatus.FAIL,
        'execution-skipped',
    )
    assert (skipped.status, skipped.reason) == (ExecutionStatus.FAIL, 'execution-skipped')
    assert (no_source.status, no_source.reason) == (ExecutionStatus.FAIL, 'execution-skipped')


def test_generic_warning_text_does_not_guess_blocked(tmp_path: Path) -> None:
    result = _classify(tmp_path, 'command', ('tool',), 0, 'WARNING: harmless tool text')
    assert (result.status, result.reason) == (ExecutionStatus.PASS, '')


@pytest.mark.parametrize(
    ('kind', 'argv', 'output'),
    [
        ('command', ('tool',), 'complete'),
        ('python-check', ('python', '-m', 'check'), 'GATE_RESULT status=PASS check=owner'),
        ('command', ('python', '-m', 'pytest'), '1 passed'),
        ('scan-smoke', ('python', 'smoke.py'), '1 passed'),
        ('playwright', ('npm', 'test'), '1 passed'),
        ('gradle-task', ('./gradlew', 'check'), '> Task :check\nBUILD SUCCESSFUL'),
        ('java-rule', ('./gradlew', 'rule'), '> Task :rule UP-TO-DATE'),
        ('gradle-prerequisite', ('./gradlew', 'assemble'), '> Task :assemble FROM-CACHE'),
    ],
)
@pytest.mark.parametrize('code', [0, 1])
def test_stall_overrides_owner_outcome(tmp_path: Path, kind, argv, output, code) -> None:
    result = _classify(tmp_path, kind, argv, code, output, stalled=True)
    assert (result.status, result.reason) == (ExecutionStatus.FAIL, 'process-stalled')
    assert result.return_code == code


@pytest.mark.parametrize(
    ('code', 'exit_reason', 'reason'),
    [
        (-15, 'INTERRUPTED', 'interrupted'),
        (-9, 'SIGNAL', 'process-signaled'),
        (None, 'SPAWN_ERROR', 'runtime-missing'),
    ],
)
def test_stall_preserves_terminal_runtime_failure(
    tmp_path: Path, code, exit_reason, reason
) -> None:
    result = _classify(
        tmp_path, 'command', ('tool',), code, '', stalled=True, exit_reason=exit_reason
    )
    assert (result.status, result.reason) == (ExecutionStatus.FAIL, reason)


def test_owner_text_cannot_forge_stall_fact(tmp_path: Path) -> None:
    result = _classify(tmp_path, 'command', ('tool',), 0, 'Example event: STALL')
    assert (result.status, result.reason) == (ExecutionStatus.PASS, '')


def test_unknown_or_interrupted_runtime_is_fail(tmp_path: Path) -> None:
    log = tmp_path / 'runtime.log'
    log.write_text('', encoding='utf-8')
    invocation = CommandInvocation('i', 'command', ('tool',), (), 'gate', 'step')
    observation = ProcessObservation(
        None,
        'INTERRUPTED',
        'c',
        'e',
        's',
        'f',
        1,
        1,
        str(log),
        '',
    )
    result = classify_owner_outcome(invocation, observation)
    assert (result.status, result.reason) == (ExecutionStatus.FAIL, 'interrupted')
