"""唯一 Gate executor 的命令、环境、状态与进程终止 contract。"""

from pathlib import Path
from types import SimpleNamespace

from scripts.gates import executor
from scripts.gates.catalog import gate_by_name
from scripts.gates.model import GatePlan, TargetGatePlan
from scripts.gates.report import BLOCKED, FAIL, PASS, GateDetail


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
    assert executor.command_for_gate(gate_by_name('noTestSkips'), tmp_path, 'hook-runtime') == [
        '/tmp/python',
        '-m',
        'scripts.checks',
        'repository.no-test-skips',
    ]


def test_gradle_tasks_come_from_catalog(tmp_path: Path) -> None:
    (tmp_path / 'gradlew').write_text('')
    gate = gate_by_name('javaRecordComponentJavadocs')
    assert executor.command_for_gate(gate, tmp_path, 'java-src')[
        1 : 1 + len(gate.gradle_tasks)
    ] == list(gate.gradle_tasks)


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


def test_hook_runtime_pytest_uses_stable_capability_suites(monkeypatch) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    monkeypatch.setattr(executor, '_project_python', lambda _root, dev=False: '/tmp/python')
    command = executor.command_for_gate(gate_by_name('pytest'), repo_root, 'hook-runtime')
    assert command[:6] == ['/tmp/python', '-m', 'pytest', '-q', '-W', 'error']
    assert 'tests/agent_runtime' in command
    assert 'tests/harness' in command
    assert 'tests/gates' in command


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
        _single_plan('session-detail', 'cssOwnership'),
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


def test_css_ownership_advisories_are_allowlisted_for_group_name() -> None:
    output = "Warnings: 2\n  [WARN] hardcoded-color\nCSS ownership: PASS (2 warnings)"

    assert (
        executor._warning_after_trigger_reason(
            output,
            gate_name='group-040-cssOwnership',
            cmd=['python3', 'scripts/checks/check_css_ownership.py'],
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
    prerequisite = next(group for group in execution.groups if not group.depends_on)

    def execute(group, _repo, _identity):
        assert group.group_id == prerequisite.group_id
        return group.group_id, GateDetail(name=group.group_id, status=FAIL), 0

    monkeypatch.setattr(executor, '_execute_group', execute)
    details = executor.execute_plan(execution, tmp_path)

    assert len(details) == 1
    assert details[0].status == BLOCKED
    assert details[0].executionState == 'DEPENDENCY_BLOCKED'
