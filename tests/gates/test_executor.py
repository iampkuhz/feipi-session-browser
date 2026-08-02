"""唯一 Gate executor 的命令、环境、状态与进程终止 contract。"""

import os
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest
from scripts.gates import executor
from scripts.gates.catalog import gate_by_name
from scripts.gates.model import GatePlan, TargetGatePlan
from scripts.gates.report import BLOCKED, FAIL, PASS, GateDetail
from scripts.gates.support import identity_from_values, quality_dir


def _single_plan(target: str, gate: str) -> GatePlan:
    return GatePlan(
        (),
        (),
        (target,),
        (target,),
        (TargetGatePlan(target, (gate_by_name(gate),)),),
    )


def test_command_adapter_reads_typed_declaration(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(executor, '_project_python', lambda _root, dev=False: '/tmp/python')
    assert executor.command_for_gate(
        gate_by_name('noPythonPlaywrightSkips'), tmp_path, 'acceptance-cases'
    ) == [
        '/tmp/python',
        '-m',
        'scripts.checks',
        'repository.no-python-playwright-skips',
    ]


def test_gradle_tasks_come_from_catalog(tmp_path: Path) -> None:
    (tmp_path / 'gradlew').write_text('')
    gate = gate_by_name('javaRecordComponentJavadocs')
    assert executor.command_for_gate(gate, tmp_path, 'java-src')[1] == (
        ':java:tests:quality-gates:runJavaQualityGates'
    )


def test_scan_smoke_command_keeps_the_real_process_suite_and_fails_closed(
    tmp_path: Path,
) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    gate = gate_by_name('scanScriptSmoke')
    command = executor.command_for_gate(gate, repo_root, 'scan-script-smoke')

    assert command[:2] == ['bash', '-c']
    assert ':java:app-cli:installDist' in command[2]
    assert 'tests/script_commands/test_session_browser_scan_smoke.py' in command[2]
    assert executor.command_for_gate(gate, tmp_path, 'scan-script-smoke') == []


def test_reuse_standard_cpd_uses_its_gradle_owner(tmp_path: Path) -> None:
    (tmp_path / 'gradlew').write_text('', encoding='utf-8')
    assert executor.command_for_gate(gate_by_name('reuseStandardCpd'), tmp_path, 'java-src') == [
        str(tmp_path / 'gradlew'),
        'reuseStandardCpd',
    ]


@pytest.mark.contract_case('JR-020-001')
def test_java_comment_rule_uses_registry_and_repository_wide_environment(
    tmp_path: Path,
) -> None:
    (tmp_path / 'gradlew').write_text('', encoding='utf-8')
    gate = gate_by_name('javaChineseComments')
    assert executor.command_for_gate(gate, tmp_path, 'java-src') == [
        str(tmp_path / 'gradlew'),
        ':java:tests:quality-gates:runJavaQualityGates',
        '-PfeipiJavaQualityRules=java-comment-language',
    ]
    assert executor.changed_files_environment(gate, ['java/app/src/main/java/App.java']) == {}


def test_generic_task_marker_overrides_only_its_bound_failed_task() -> None:
    output = '\n'.join(
        [
            '> Task :first FAILED',
            '> Task :second FAILED',
            'GATE_TASK_RESULT task=:first status=BLOCKED reason=input-unavailable',
        ]
    )

    assert executor._gradle_task_outcomes(output) == {  # noqa: SLF001
        ':first': 'BLOCKED',
        ':second': 'FAILED',
    }


def test_malformed_or_unbound_task_marker_does_not_change_failed_outcome() -> None:
    output = '\n'.join(
        [
            '> Task :first FAILED',
            'GATE_TASK_RESULT task=first status=BLOCKED reason=input-unavailable',
            'GATE_TASK_RESULT task=:first status=FAIL reason=input-unavailable',
        ]
    )

    assert executor._gradle_task_outcomes(output) == {':first': 'FAILED'}  # noqa: SLF001


def test_changed_files_only_reach_explicitly_supported_gradle_gate(tmp_path: Path) -> None:
    (tmp_path / 'gradlew').write_text('')
    changed = ['java/app/src/main/java/App.java']
    javadocs = gate_by_name('javaRecordComponentJavadocs')
    reuse = gate_by_name('reuseAnalyzeIncremental')

    assert executor.command_for_gate(javadocs, tmp_path, 'java-src') == [
        str(tmp_path / 'gradlew'),
        ':java:tests:quality-gates:runJavaQualityGates',
        '-PfeipiJavaQualityRules=record-component-javadocs',
    ]
    assert executor.changed_files_environment(javadocs, changed) == {
        'QUALITY_CHANGED_FILES': '["java/app/src/main/java/App.java"]'
    }
    assert executor.command_for_gate(reuse, tmp_path, 'java-src') == [
        str(tmp_path / 'gradlew'),
        'reuseAnalyzeIncremental',
    ]
    assert executor.changed_files_environment(reuse, changed) == {}


def test_generic_gradle_gate_gets_no_unknown_changed_files_input(tmp_path: Path) -> None:
    (tmp_path / 'gradlew').write_text('')
    java_check = gate_by_name('javaCheck')
    command = executor.command_for_gate(java_check, tmp_path, 'java-build')

    assert '--changed-files' not in command
    assert executor.changed_files_environment(java_check, ['build.gradle.kts']) == {}


def test_web_resource_tests_use_java_web_gradle_task(tmp_path: Path) -> None:
    (tmp_path / 'gradlew').write_text('', encoding='utf-8')
    gate = gate_by_name('webResourceTests')
    command = executor.command_for_gate(gate, tmp_path, 'session-detail')
    assert command == [
        str(tmp_path / 'gradlew'),
        ':java:web:test',
    ]


def test_web_resource_tests_missing_gradle_wrapper_is_fail_closed(tmp_path: Path) -> None:
    gate = gate_by_name('webResourceTests')
    assert executor.command_for_gate(gate, tmp_path, 'session-detail') == []


def test_browser_gate_without_base_url_uses_node_managed_fixture(monkeypatch) -> None:
    command = ['npm', '--prefix', 'tests/playwright', 'test', '--']
    monkeypatch.setattr(executor, 'command_for_gate', lambda *_args: command)
    execution = executor.build_execution_plan(
        _single_plan('session-detail', 'browserLayout'), Path.cwd()
    )
    group = execution.groups[0]

    assert group.kind == 'command'
    assert group.command == tuple(command)
    assert dict(group.environment).get('FEIPI_AGENT_RUNTIME_ROOT')
    assert 'BASE_URL' not in dict(group.environment)


def test_playwright_command_recognizes_repository_prefix() -> None:
    command = ['npm', '--prefix', 'tests/playwright', 'test', '--', 'session-detail.spec.js']

    assert executor._is_playwright_command(command)  # noqa: SLF001
    assert not executor._is_playwright_command(['npx', 'playwright', 'test'])  # noqa: SLF001


def test_skip_and_warning_never_pass(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(executor.shutil, 'which', lambda _name: '/bin/tool')
    monkeypatch.setenv('FEIPI_RUN_TMPDIR', str(tmp_path / 'runtime'))

    def bounded(_cmd, **kwargs):
        Path(kwargs['log_path']).parent.mkdir(parents=True, exist_ok=True)
        Path(kwargs['log_path']).write_text('1 skipped\nUserWarning: warning after trigger')
        return SimpleNamespace(
            return_code=0, duration_seconds=0.01, timed_out=False, output_tail=''
        )

    monkeypatch.setattr(executor, 'run_bounded', bounded)
    assert executor.run_cmd('pytest', ['python3', '-m', 'pytest'], tmp_path).status == FAIL


def test_successful_command_passes(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv('FEIPI_RUN_TMPDIR', str(tmp_path / 'runtime'))
    assert executor.run_cmd('echo', ['/bin/echo', 'ok'], tmp_path).status == PASS


def test_execute_plan_injects_run_identity_into_gate_children(tmp_path: Path, monkeypatch) -> None:
    captured = {}
    monkeypatch.setattr(executor, 'command_for_gate', lambda *_args: ['/bin/true'])

    def fake_run(name, cmd, cwd, **kwargs):
        captured.update(kwargs['env_overrides'])
        return GateDetail(name=name, status=PASS)

    monkeypatch.setattr(executor, 'run_cmd', fake_run)
    execution = executor.build_execution_plan(
        _single_plan('python-standard', 'scriptCommentLanguage'),
        tmp_path,
    )

    details = executor.execute_plan(
        execution,
        tmp_path,
        environment_overrides={
            'FEIPI_AGENT_CLIENT': 'codex',
            'FEIPI_SESSION_ID': 'session-a',
            'FEIPI_RUN_ID': 'run-a',
        },
    )

    assert details[0].status == PASS
    assert captured['FEIPI_AGENT_CLIENT'] == 'codex'
    assert captured['FEIPI_SESSION_ID'] == 'session-a'
    assert captured['FEIPI_RUN_ID'] == 'run-a'


def test_gate_child_environment_uses_current_identity_for_private_quality_dir(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv('FEIPI_AGENT_CLIENT', 'codex')
    monkeypatch.setenv('FEIPI_SESSION_ID', 'current-session')
    monkeypatch.setenv('FEIPI_RUN_ID', 'current-run')
    monkeypatch.setenv('FEIPI_AGENT_ID', 'current-agent')
    monkeypatch.setenv('FEIPI_RUN_TMPDIR', str(tmp_path / 'runtime'))

    child = executor.gate_child_environment(tmp_path)
    expected = quality_dir(tmp_path, identity_from_values())

    assert child['FEIPI_QUALITY_ARTIFACT_DIR'] == str(expected)
    assert expected.is_dir()
    assert stat.S_IMODE(expected.stat().st_mode) == 0o700


def test_gate_child_environment_adds_pid_to_each_missing_identity_part(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv('FEIPI_RUN_TMPDIR', str(tmp_path / 'runtime'))
    process_id = f'pid-{os.getpid()}'
    cases = {
        'missing-both': ('', ''),
        'session-only': ('session-only', ''),
        'run-only': ('', 'run-only'),
        'full': ('session-full', 'run-full'),
    }
    observed: set[str] = set()

    for session_id, run_id in cases.values():
        overrides = {
            'FEIPI_AGENT_CLIENT': 'codex',
            'FEIPI_SESSION_ID': session_id,
            'FEIPI_AGENT_ID': 'agent-a',
            'FEIPI_RUN_ID': run_id,
            'FEIPI_WORKTREE_ID': 'worktree-a',
        }
        child = executor.gate_child_environment(tmp_path, overrides)
        expected_identity = identity_from_values(
            agent_client='codex',
            session_id=session_id or process_id,
            agent_id='agent-a',
            run_id=run_id or process_id,
            worktree_id='worktree-a',
        )
        expected = quality_dir(tmp_path, expected_identity)

        assert child['FEIPI_QUALITY_ARTIFACT_DIR'] == str(expected)
        assert expected.is_dir()
        assert stat.S_IMODE(expected.stat().st_mode) == 0o700
        observed.add(str(expected))

    assert len(observed) == len(cases)


def test_gate_child_environment_respects_identity_overrides_and_rejects_path_override(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv('FEIPI_AGENT_CLIENT', 'current-client')
    monkeypatch.setenv('FEIPI_SESSION_ID', 'current-session')
    monkeypatch.setenv('FEIPI_RUN_ID', 'current-run')
    monkeypatch.setenv('FEIPI_AGENT_ID', 'current-agent')
    monkeypatch.setenv('FEIPI_RUN_TMPDIR', str(tmp_path / 'runtime'))
    overrides = {
        'FEIPI_AGENT_CLIENT': 'override-client',
        'FEIPI_SESSION_ID': 'override-session',
        'FEIPI_RUN_ID': 'override-run',
        'FEIPI_AGENT_ID': 'override-agent',
        'FEIPI_QUALITY_ARTIFACT_DIR': str(tmp_path / 'injected'),
    }

    child = executor.gate_child_environment(tmp_path, overrides)
    expected_identity = identity_from_values(
        agent_client='override-client',
        session_id='override-session',
        run_id='override-run',
        agent_id='override-agent',
    )
    expected = quality_dir(tmp_path, expected_identity)

    assert child['FEIPI_QUALITY_ARTIFACT_DIR'] == str(expected)
    assert expected.is_dir()
    assert stat.S_IMODE(expected.stat().st_mode) == 0o700
    assert not (tmp_path / 'injected').exists()


def test_java_api_snapshot_uses_declarative_java_rule() -> None:
    command = executor.command_for_gate(
        gate_by_name('javaApiSnapshot'), Path(__file__).resolve().parents[2], 'java-build'
    )

    assert command[-2:] == [
        ':java:tests:quality-gates:runJavaQualityGates',
        '-PfeipiJavaQualityRules=java-api-snapshot',
    ]


def test_timeout_terminates_process_group(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(executor.shutil, 'which', lambda _name: '/bin/tool')
    monkeypatch.setenv('FEIPI_RUN_TMPDIR', str(tmp_path / 'runtime'))

    def bounded(_cmd, **kwargs):
        Path(kwargs['log_path']).parent.mkdir(parents=True, exist_ok=True)
        Path(kwargs['log_path']).write_text('terminated')
        return SimpleNamespace(
            return_code=-15, duration_seconds=1.0, timed_out=True, output_tail='terminated'
        )

    monkeypatch.setattr(executor, 'run_bounded', bounded)

    detail = executor.run_cmd('timeout', ['tool'], tmp_path, timeout_seconds=1)

    assert detail.status == FAIL
    assert '超时' in detail.output


@pytest.mark.parametrize(
    'output',
    (
        'Warnings: 2',
        '{"warningCount": 1}',
        '[WARN] hardcoded-color',
    ),
)
@pytest.mark.contract_case('HOOK-HARNESS-008')
def test_warning_detector_rejects_ordinary_command_warnings(output: str) -> None:
    command = ['python3', 'scripts/checks/quality_check.py']

    reason = executor._warning_after_trigger_reason(
        output,
        gate_name='group-001-qualityCheck',
        cmd=command,
    )
    status, _ = executor._audit_successful_output('group-001-qualityCheck', command, output, output)

    assert reason is not None
    assert status == FAIL


def test_playwright_allowed_warning_noise_remains_ignored() -> None:
    output = '\n'.join(
        (
            "Warning: The 'NO_COLOR' env is ignored due to the 'FORCE_COLOR' env being set.",
            '[DEP0205] DeprecationWarning: `module.register()` is deprecated.',
            '(Use `node --trace-deprecation ...` to show where the warning was created)',
            '2 passed',
        )
    )

    assert (
        executor._warning_after_trigger_reason(
            output,
            gate_name='group-001-browserLayout',
            cmd=['npm', '--prefix', 'tests/playwright', 'test', '--'],
        )
        is None
    )


def test_dependency_failure_is_one_root_and_downstream_is_dependency_blocked(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / 'gradlew').write_text('#!/bin/sh\n')
    execution = executor.build_execution_plan(
        _single_plan('session-ingestion', 'scanScriptSmoke'), tmp_path
    )
    prerequisite = next(group for group in execution.groups if group.kind == 'gradle')

    def execute(group, _repo):
        assert group.group_id == prerequisite.group_id
        return GateDetail(
            name=group.group_id,
            status=FAIL,
            taskOutcomes={':java:app-cli:installDist': 'FAILED'},
        )

    monkeypatch.setattr(executor, '_execute_group', execute)
    details = executor.execute_plan(execution, tmp_path)

    assert len(details) == 1
    assert details[0].status == BLOCKED
    assert details[0].executionState == 'DEPENDENCY_BLOCKED'
