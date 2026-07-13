"""Phase 8 execution plan、聚合、资源 DAG 与 receipt 的 contract。"""

from __future__ import annotations

import json
import subprocess
from dataclasses import asdict
from pathlib import Path

from scripts.gates import cli, executor, receipt
from scripts.gates.planner import plan
from scripts.gates.report import FAIL, PASS, GateDetail

REPO_ROOT = Path(__file__).resolve().parents[2]
MIXED_FILES = [
    'java/app-cli/src/main/java/com/feipi/session/browser/cli/App.java',
    'build.gradle.kts',
]


def test_execution_plan_is_deterministic_immutable_and_acyclic() -> None:
    gate_plan = cli._with_preflight(plan(MIXED_FILES))  # noqa: SLF001
    first = executor.build_execution_plan(gate_plan, REPO_ROOT)
    second = executor.build_execution_plan(gate_plan, REPO_ROOT)

    assert first == second
    assert first.plan_id == f'plan-{first.fingerprint[:16]}'
    assert len({gate.name for gate in first.gates}) == len(first.gates)
    completed: set[str] = set()
    for group in first.groups:
        assert set(group.depends_on) <= completed
        completed.add(group.group_id)


def test_mixed_required_uses_one_gradle_group_and_exact_cpd_input() -> None:
    execution = executor.build_execution_plan(
        cli._with_preflight(plan(MIXED_FILES)),
        REPO_ROOT,  # noqa: SLF001
    )
    gradle_groups = [group for group in execution.groups if group.kind == 'gradle']

    assert len(gradle_groups) == 1
    command = gradle_groups[0].command
    for task in (
        'check',
        ':java:tests:quality-gates:verifyJavaRecordComponentJavadocs',
        'reuseAnalyzeIncremental',
        'reuseStandardCpd',
        ':java:app-cli:installDist',
    ):
        assert command.count(task) == 1
    assert sum(part.startswith('-PfeipiReuseCpdFileList=') for part in command) == 1
    assert '--no-configuration-cache' not in command
    assert 'clean' not in command


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


def test_resource_dag_serializes_conflicts_but_allows_disjoint_groups() -> None:
    base = executor.CommandGroup(
        'a', 'command', ('echo', 'a'), (), ('noTestSkips',), ('gradle-daemon',), True, 10
    )
    conflict = executor.CommandGroup(
        'b', 'command', ('echo', 'b'), (), ('languagePolicy',), ('gradle-daemon',), True, 10
    )
    disjoint = executor.CommandGroup(
        'c', 'command', ('echo', 'c'), (), ('codexAgentPolicy',), ('fixture-server',), True, 10
    )

    groups = executor._add_dependency_edges([base, conflict, disjoint])  # noqa: SLF001

    assert groups[1].depends_on == ('a',)
    assert groups[2].depends_on == ()


def test_scan_smoke_prerequisite_precedes_consumer_without_resource_cycle() -> None:
    execution = executor.build_execution_plan(
        cli._with_preflight(plan(['scripts/checks/check_agent_runtime_isolation.py'])),
        REPO_ROOT,
    )
    positions = {group.group_id: index for index, group in enumerate(execution.groups)}
    scan = next(group for group in execution.groups if 'scanScriptSmoke' in group.gate_names)

    assert scan.depends_on == ('group-gradle-000',)
    assert positions['group-gradle-000'] < positions[scan.group_id]
    assert all(
        positions[dependency] < positions[group.group_id]
        for group in execution.groups
        for dependency in group.depends_on
    )


def test_browser_group_reuses_explicit_fixture_server(monkeypatch) -> None:
    monkeypatch.setattr(executor, 'command_for_gate', lambda *_args: ['npx', 'playwright', 'test'])
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

    def fake_group(group, _repo_root, _identity):
        if group.kind != 'gradle':
            return group.group_id, GateDetail(group.group_id, PASS), 0
        return (
            group.group_id,
            GateDetail(
                group.group_id,
                FAIL,
                taskOutcomes={
                    ':check': 'EXECUTED',
                    ':java:tests:quality-gates:verifyJavaRecordComponentJavadocs': 'FAILED',
                    ':reuseStandardCpd': 'FROM-CACHE',
                    ':reuseAnalyzeIncremental': 'UP-TO-DATE',
                    ':java:app-cli:installDist': 'EXECUTED',
                },
            ),
            0,
        )

    monkeypatch.setattr(executor, '_execute_group', fake_group)
    details = {detail.name: detail for detail in executor.execute_plan(execution, REPO_ROOT)}

    assert details['javaCheck'].status == PASS
    assert details['javaRecordComponentJavadocs'].status == FAIL
    assert details['reuseStandardCpd'].status == PASS
    assert details['reuseAnalyzeIncremental'].status == PASS


def test_checkout_fingerprint_covers_commit_index_worktree_and_untracked(tmp_path: Path) -> None:
    subprocess.run(['git', 'init', '-q'], cwd=tmp_path, check=True)
    subprocess.run(
        ['git', 'config', 'user.email', 'gate@example.invalid'], cwd=tmp_path, check=True
    )
    subprocess.run(['git', 'config', 'user.name', 'Gate Test'], cwd=tmp_path, check=True)
    tracked = tmp_path / 'tracked.txt'
    tracked.write_text('one\n')
    subprocess.run(['git', 'add', 'tracked.txt'], cwd=tmp_path, check=True)
    subprocess.run(['git', 'commit', '-qm', 'initial'], cwd=tmp_path, check=True)
    committed = receipt.checkout_content_fingerprint(tmp_path)

    tracked.write_text('two\n')
    working = receipt.checkout_content_fingerprint(tmp_path)
    subprocess.run(['git', 'add', 'tracked.txt'], cwd=tmp_path, check=True)
    staged = receipt.checkout_content_fingerprint(tmp_path)
    (tmp_path / 'untracked.txt').write_text('new\n')
    untracked = receipt.checkout_content_fingerprint(tmp_path)

    assert len({committed, working, staged, untracked}) == 4


def test_receipt_key_invalidates_attribution_plan_command_env_and_gate_input(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(receipt, 'checkout_content_fingerprint', lambda _root: 'checkout')

    def key(**overrides):
        values = {
            'attribution': {'baseline': 'a'},
            'plan_fingerprint': 'plan-a',
            'command_fingerprint': 'command-a',
            'environment': {'BASE_URL': 'http://fixture-a'},
            'gate_inputs': {'files': ['a.py']},
        }
        values.update(overrides)
        return receipt.content_cache_key('harness', ['a.py'], tmp_path, **values)

    baseline = key()
    variants = {
        key(attribution={'baseline': 'b'}),
        key(plan_fingerprint='plan-b'),
        key(command_fingerprint='command-b'),
        key(environment={'BASE_URL': 'http://fixture-b'}),
        key(gate_inputs={'files': ['b.py']}),
    }
    assert baseline not in variants
    assert len(variants) == 5


def test_corrupt_foreign_and_non_pass_receipts_are_never_reused(tmp_path: Path) -> None:
    path = tmp_path / 'receipt.json'
    assert receipt.reuse_decision(path, 'key') == (False, 'missing-or-corrupt-receipt')
    path.write_text('{broken', encoding='utf-8')
    assert receipt.reuse_decision(path, 'key') == (False, 'missing-or-corrupt-receipt')
    path.write_text(json.dumps({'schema_version': 1, 'status': 'PASS'}), encoding='utf-8')
    assert receipt.reuse_decision(path, 'key') == (False, 'foreign-schema')
    path.write_text(json.dumps({'schema_version': 2, 'status': 'FAIL'}), encoding='utf-8')
    assert receipt.reuse_decision(path, 'key') == (False, 'non-pass-receipt')


def test_execution_plan_serialization_is_stable() -> None:
    execution = executor.build_execution_plan(
        cli._with_preflight(plan(MIXED_FILES)),
        REPO_ROOT,  # noqa: SLF001
    )
    first = json.dumps(asdict(execution), ensure_ascii=False, sort_keys=True)
    second = json.dumps(asdict(execution), ensure_ascii=False, sort_keys=True)
    assert first == second
