"""唯一 Gate executor 的命令、环境、状态与进程终止 contract。"""

import signal
import subprocess
from pathlib import Path

from scripts.gates import executor
from scripts.gates.catalog import gate_by_name
from scripts.gates.model import GatePlan, TargetGatePlan
from scripts.gates.report import FAIL, PASS


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
    monkeypatch.setattr(executor, 'command_for_gate', lambda *_args: ['npx', 'playwright', 'test'])
    execution = executor.build_execution_plan(
        _single_plan('session-detail', 'browserLayout'), Path.cwd()
    )
    group = execution.groups[0]

    assert group.kind == 'command'
    assert group.command == ('npx', 'playwright', 'test')
    assert dict(group.environment).get('FEIPI_AGENT_RUNTIME_ROOT')
    assert 'BASE_URL' not in dict(group.environment)


def test_skip_and_warning_never_pass(monkeypatch, tmp_path: Path) -> None:
    class FakeProc:
        pid = 123
        returncode = 0

        def communicate(self, timeout=None):
            return ('1 skipped\nUserWarning: warning after trigger', None)

    monkeypatch.setattr(executor.shutil, 'which', lambda _name: '/bin/tool')
    monkeypatch.setattr(executor.subprocess, 'Popen', lambda *args, **kwargs: FakeProc())
    assert executor.run_cmd('pytest', ['python3', '-m', 'pytest'], tmp_path).status == FAIL


def test_successful_command_passes(tmp_path: Path) -> None:
    assert executor.run_cmd('echo', ['/bin/echo', 'ok'], tmp_path).status == PASS


def test_java_api_snapshot_uses_declarative_java_rule() -> None:
    command = executor.command_for_gate(
        gate_by_name('javaApiSnapshot'), Path(__file__).resolve().parents[2], 'java-build'
    )

    assert command[-2:] == [
        ':java:tests:quality-gates:runJavaQualityGates',
        '-PfeipiJavaQualityRules=java-api-snapshot',
    ]


def test_timeout_terminates_process_group(monkeypatch, tmp_path: Path) -> None:
    class FakeProc:
        pid = 456
        returncode = -signal.SIGTERM
        calls = 0

        def communicate(self, timeout=None):
            self.calls += 1
            if self.calls == 1:
                raise subprocess.TimeoutExpired(['tool'], timeout)
            return ('terminated', None)

    signals: list[tuple[int, int]] = []
    monkeypatch.setattr(executor.shutil, 'which', lambda _name: '/bin/tool')
    monkeypatch.setattr(executor.subprocess, 'Popen', lambda *args, **kwargs: FakeProc())
    monkeypatch.setattr(executor.os, 'killpg', lambda pid, sig: signals.append((pid, sig)))

    detail = executor.run_cmd('timeout', ['tool'], tmp_path, timeout_seconds=1)

    assert detail.status == FAIL
    assert signals == [(456, signal.SIGTERM)]


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
