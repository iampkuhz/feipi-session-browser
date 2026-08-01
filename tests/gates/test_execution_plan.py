"""Gate serial execution plan、Gradle 聚合与状态 contract。"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import pytest
from scripts.gates import cli, executor
from scripts.gates.planner import plan
from scripts.gates.report import BLOCKED, FAIL, PASS, GateDetail

REPO_ROOT = Path(__file__).resolve().parents[2]
MIXED_FILES = [
    'java/app-cli/src/main/java/com/feipi/session/browser/cli/App.java',
    'build.gradle.kts',
]


def test_execution_plan_is_deterministic_immutable_and_serial() -> None:
    gate_plan = cli._with_preflight(plan(MIXED_FILES))  # noqa: SLF001
    first = executor.build_execution_plan(gate_plan, REPO_ROOT)
    second = executor.build_execution_plan(gate_plan, REPO_ROOT)

    assert first == second
    assert first.plan_id == f'plan-{first.fingerprint[:16]}'
    assert len({gate.name for gate in first.gates}) == len(first.gates)
    assert isinstance(first.groups, tuple)


def test_mixed_required_uses_one_gradle_group_and_changed_files_environment() -> None:
    execution = executor.build_execution_plan(
        cli._with_preflight(plan(MIXED_FILES)),
        REPO_ROOT,  # noqa: SLF001
    )
    gradle_groups = [group for group in execution.groups if group.kind == 'gradle']

    assert len(gradle_groups) == 1
    command = gradle_groups[0].command
    for task in (
        'check',
        ':java:tests:quality-gates:runJavaQualityGates',
        'reuseAnalyzeIncremental',
        'reuseStandardCpd',
        ':java:app-cli:installDist',
    ):
        assert command.count(task) == 1
    assert json.loads(dict(gradle_groups[0].environment)['QUALITY_CHANGED_FILES']) == MIXED_FILES
    java_rule_properties = [part for part in command if part.startswith('-PfeipiJavaQualityRules=')]
    assert java_rule_properties == [
        '-PfeipiJavaQualityRules=java-comment-language,record-component-javadocs,'
        'no-pmd-suppressions'
    ]
    assert '--no-configuration-cache' not in command
    assert 'clean' not in command


@pytest.mark.parametrize(
    ('task_outcome', 'expected_status', 'diagnostic'),
    [
        ('EXECUTED', PASS, 'Gradle task outcome confirmed'),
        ('UP-TO-DATE', PASS, 'Gradle task outcome confirmed'),
        ('FAILED', FAIL, ''),
        ('SKIPPED', FAIL, 'selected Gradle task was SKIPPED'),
        (None, BLOCKED, 'selected Gradle task outcome was not confirmed'),
    ],
)
def test_session_samples_uses_one_gradle_group_and_standard_task_outcome(
    monkeypatch,
    task_outcome: str | None,
    expected_status: str,
    diagnostic: str,
) -> None:
    execution = executor.build_execution_plan(
        cli._with_preflight(plan(['tests/fixtures/session_samples/sample.json'])),
        REPO_ROOT,  # noqa: SLF001
    )
    gradle_groups = [group for group in execution.groups if group.kind == 'gradle']
    outcomes = (
        {':java:tests:contracts:sampleIntegrationTest': task_outcome}
        if task_outcome is not None
        else {}
    )

    assert len(gradle_groups) == 1
    assert gradle_groups[0].command.count(':java:tests:contracts:sampleIntegrationTest') == 1

    def fake_group(group, _repo_root):
        if group.kind != 'gradle':
            return GateDetail(group.group_id, PASS)
        return GateDetail(
            group.group_id,
            PASS,
            taskOutcomes=outcomes,
        )

    monkeypatch.setattr(executor, '_execute_group', fake_group)
    details = {detail.name: detail for detail in executor.execute_plan(execution, REPO_ROOT)}

    assert details['sessionSamples'].status == expected_status
    assert diagnostic in details['sessionSamples'].output
    assert details['sessionSamples'].taskOutcomes == outcomes


def test_scan_dry_run_excludes_pid_scoped_transient_paths() -> None:
    gate_plan = cli.create_plan(
        MIXED_FILES,
        tier='required',
        target=None,
        explicit_changed_files=True,
    )
    first = cli._dry_run_payload(gate_plan, REPO_ROOT)  # noqa: SLF001
    second = cli._dry_run_payload(gate_plan, REPO_ROOT)  # noqa: SLF001

    assert first == second
    encoded = json.dumps(first, sort_keys=True)
    assert 'pid-' not in encoded


def test_template_resource_uses_one_java_quality_group() -> None:
    execution = executor.build_execution_plan(
        cli._with_preflight(  # noqa: SLF001
            plan(['java/web/src/main/resources/templates/session.html'])
        ),
        REPO_ROOT,
    )
    groups = [group for group in execution.groups if 'templateContract' in group.gate_names]

    assert len(groups) == 1
    assert groups[0].kind == 'gradle'
    assert groups[0].command.count(':java:tests:quality-gates:runJavaQualityGates') == 1
    assert '-PfeipiJavaQualityRules=template-contract,static-resource-contract' in groups[0].command


@pytest.mark.parametrize(
    'changed_path',
    [
        'java/web/src/main/resources/static/generated/page.css',
        'java/web/src/main/resources/static/tmp/page.js',
    ],
)
def test_static_resource_in_arbitrary_subdirectory_uses_one_java_quality_group(
    changed_path: str,
) -> None:
    execution = executor.build_execution_plan(
        cli._with_preflight(plan([changed_path])),  # noqa: SLF001
        REPO_ROOT,
    )
    groups = [group for group in execution.groups if 'staticCssContract' in group.gate_names]

    assert len(groups) == 1
    assert groups[0].kind == 'gradle'
    assert groups[0].command.count(':java:tests:quality-gates:runJavaQualityGates') == 1
    assert '-PfeipiJavaQualityRules=static-resource-contract' in groups[0].command


def test_playwright_plan_uses_node_managed_java_fixture_without_base_url() -> None:
    """未提供外部 BASE_URL 时由根 Playwright 配置管理真实 Java fixture。"""
    gate_plan = cli.create_plan(
        ['java/web/src/main/resources/templates/session.html'],
        tier='full',
        target=None,
        explicit_changed_files=True,
    )

    execution = executor.build_execution_plan(gate_plan, REPO_ROOT)
    browser_groups = [
        group
        for group in execution.groups
        if any(name in {'browserLayout', 'browserInteraction'} for name in group.gate_names)
    ]

    assert browser_groups
    assert all(group.kind == 'command' for group in browser_groups)
    assert all(dict(group.environment).get('FEIPI_AGENT_RUNTIME_ROOT') for group in browser_groups)
    assert all('BASE_URL' not in dict(group.environment) for group in browser_groups)


def test_runner_executes_groups_in_tuple_order_after_independent_failure(
    monkeypatch, tmp_path: Path
) -> None:
    groups = (
        executor.CommandGroup('a', 'command', ('echo', 'a'), (), ('noTestSkips',), 10),
        executor.CommandGroup('b', 'command', ('echo', 'b'), (), ('languagePolicy',), 10),
        executor.CommandGroup('c', 'command', ('echo', 'c'), (), ('codexAgentPolicy',), 10),
    )
    calls: list[str] = []

    def execute(group, _repo):
        calls.append(group.group_id)
        return GateDetail(group.group_id, FAIL if group.group_id == 'a' else PASS)

    monkeypatch.setattr(executor, '_execute_group', execute)
    outcomes = executor._run_groups_serially(groups, tmp_path)  # noqa: SLF001

    assert calls == ['a', 'b', 'c']
    assert outcomes['a'].status == FAIL
    assert outcomes['b'].status == PASS
    assert outcomes['c'].status == PASS


def test_scan_smoke_prerequisite_precedes_consumer_in_serial_plan() -> None:
    execution = executor.build_execution_plan(
        cli._with_preflight(plan(['scripts/checks/source/check_code_comment_language.py'])),
        REPO_ROOT,
    )
    positions = {group.group_id: index for index, group in enumerate(execution.groups)}
    scan = next(group for group in execution.groups if 'scanScriptSmoke' in group.gate_names)

    assert positions['group-gradle-000'] < positions[scan.group_id]
    assert scan.kind == 'scan-smoke'


def test_browser_group_reuses_explicit_fixture_server(monkeypatch) -> None:
    monkeypatch.setattr(
        executor,
        'command_for_gate',
        lambda *_args: ['npm', '--prefix', 'tests/playwright', 'test', '--'],
    )
    execution = executor.build_execution_plan(
        cli._with_preflight(  # noqa: SLF001
            plan(['java/web/src/main/resources/templates/session-detail.html'])
        ),
        REPO_ROOT,
        base_url='http://127.0.0.1:61961',
    )
    groups = [group for group in execution.groups if 'browserLayout' in group.gate_names]
    environment = dict(groups[0].environment)

    assert environment['BASE_URL'] == 'http://127.0.0.1:61961'
    assert environment['SESSION_BROWSER_REUSE_PLAYWRIGHT_SERVER'] == '1'
    assert environment['PW_SESSION_URL'].endswith('/sessions/claude_code/hifi-viz-session-001')
    assert environment['FEIPI_AGENT_RUNTIME_ROOT'] == str(executor.resolve_runtime_root(REPO_ROOT))


def test_gradle_group_maps_each_selected_task_outcome(monkeypatch) -> None:
    execution = executor.build_execution_plan(
        cli._with_preflight(plan(MIXED_FILES)),
        REPO_ROOT,  # noqa: SLF001
    )

    def fake_group(group, _repo_root):
        if group.kind != 'gradle':
            return GateDetail(group.group_id, PASS)
        return GateDetail(
            group.group_id,
            FAIL,
            taskOutcomes={
                ':check': 'EXECUTED',
                ':java:tests:quality-gates:runJavaQualityGates': 'FAILED',
                ':reuseStandardCpd': 'FROM-CACHE',
                ':reuseAnalyzeIncremental': 'UP-TO-DATE',
                ':java:app-cli:installDist': 'EXECUTED',
            },
        )

    monkeypatch.setattr(executor, '_execute_group', fake_group)
    details = {detail.name: detail for detail in executor.execute_plan(execution, REPO_ROOT)}

    assert details['javaCheck'].status == PASS
    assert details['javaRecordComponentJavadocs'].status == FAIL
    assert details['noJavaSuppressWarnings'].status == FAIL
    assert details['reuseStandardCpd'].status == PASS
    assert details['reuseAnalyzeIncremental'].status == PASS


@pytest.mark.parametrize(
    ('task_outcomes', 'expected_status'),
    [
        ({':reuseStandardCpd': 'BLOCKED'}, BLOCKED),
        ({':reuseStandardCpd': 'FAILED'}, FAIL),
    ],
)
def test_gradle_task_status_is_generic_and_preserves_blocked_vs_failed(
    monkeypatch, task_outcomes: dict[str, str], expected_status: str
) -> None:
    execution = executor.build_execution_plan(
        cli._with_preflight(plan(['config/reuse-policy/policy.json'])),  # noqa: SLF001
        REPO_ROOT,
    )

    def fake_group(group, _repo_root):
        if group.kind != 'gradle':
            return GateDetail(group.group_id, PASS)
        return GateDetail(group.group_id, FAIL, taskOutcomes=task_outcomes)

    monkeypatch.setattr(executor, '_execute_group', fake_group)
    details = {detail.name: detail for detail in executor.execute_plan(execution, REPO_ROOT)}

    assert details['reuseStandardCpd'].status == expected_status
    if expected_status == BLOCKED:
        assert details['reuseStandardCpd'].executionState == 'BLOCKED'


def test_execution_plan_serialization_is_stable() -> None:
    execution = executor.build_execution_plan(
        cli._with_preflight(plan(MIXED_FILES)),
        REPO_ROOT,  # noqa: SLF001
    )
    first = json.dumps(asdict(execution), ensure_ascii=False, sort_keys=True)
    second = json.dumps(asdict(execution), ensure_ascii=False, sort_keys=True)
    assert first == second
