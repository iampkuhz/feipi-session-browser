"""Browser suite 使用原生发现，任何变化不得把新测试排除在冻结配方外。"""

from pathlib import Path

import pytest
from scripts.gates.catalog.registry import gate_by_name
from scripts.gates.execution.command_adapter import adapt_recipe_step
from scripts.gates.planning.change_snapshot import ChangeSnapshot
from scripts.gates.planning.plan_compiler import compile_gate_plan


@pytest.mark.parametrize(
    'path',
    (
        'java/tests/playwright/new-critical.spec.js',
        'java/tests/playwright/removed-critical.spec.ts',
        'java/tests/playwright/unclassified-helper.js',
        'java/tests/playwright/playwright.config.js',
        'java/web/src/main/resources/static/js/shared.js',
        'java/web/src/main/resources/templates/unknown-page.html',
        'scripts/session-browser.sh',
        'scripts/harness/java_env.sh',
        'scripts/gates/execution/command_adapter.py',
    ),
)
def test_browser_changed_paths_always_use_complete_native_discovery(
    path: str, tmp_path: Path
) -> None:
    # Neither new nor removed paths need exist: selection cannot depend on a stale suite inventory.
    snapshot = ChangeSnapshot('git-working-tree', 'head', None, (path,), 'fingerprint')
    plan = compile_gate_plan(snapshot)
    gate = gate_by_name('browserTests')
    assert gate in plan.gates
    assert len(gate.recipe.steps) == 1
    step = gate.recipe.steps[0]
    assert step.tests == ()
    (invocation,) = adapt_recipe_step(
        gate, step, tmp_path, mode='incremental', changed_files=(path,)
    )
    assert invocation.argv == ('npm', '--prefix', 'java/tests/playwright', 'test')


@pytest.mark.parametrize(
    'path',
    (
        'java/future/src/main/java/example/Future.java',
        'java/normalization-engine/src/main/java/example/Local.java',
        'scripts/session-browser.sh',
        'scripts/harness/java_env.sh',
        'scripts/gates/catalog/recipe_dsl.py',
    ),
)
def test_unknown_local_java_and_shared_entries_keep_complete_root_check(path: str) -> None:
    snapshot = ChangeSnapshot('git-working-tree', 'head', None, (path,), 'fingerprint')
    plan = compile_gate_plan(snapshot)
    gate = gate_by_name('javaBuildVerification')
    assert gate in plan.gates
    assert gate.recipe.steps[0].tasks == ('check',)
    assert '-x' not in gate.recipe.steps[0].args


def test_unrelated_documentation_does_not_select_product_consumers() -> None:
    snapshot = ChangeSnapshot(
        'git-working-tree', 'head', None, ('docs/unrelated.md',), 'fingerprint'
    )
    names = {gate.name for gate in compile_gate_plan(snapshot).gates}
    assert not names.intersection({'browserTests', 'javaBuildVerification'})


@pytest.mark.parametrize(
    ('path', 'included'),
    (
        ('scripts/harness/doctor.sh', {'bashSyntax', 'agentConfigurationPolicy'}),
        (
            'scripts/gates/checks/agent/new_policy.py',
            {'gateFrameworkTests', 'agentConfigurationPolicy'},
        ),
        ('scripts/gates/presentation/new_report.py', {'gateFrameworkTests'}),
    ),
)
def test_leaf_tools_do_not_select_unrelated_product_checks(path, included) -> None:
    snapshot = ChangeSnapshot('git-working-tree', 'head', None, (path,), 'fingerprint')
    names = {gate.name for gate in compile_gate_plan(snapshot).gates}
    assert included <= names
    assert not names & {'browserTests', 'javaBuildVerification', 'scanCommandSmoke'}
    if path.endswith('.sh'):
        assert 'scriptToolchainQuality' not in names


@pytest.mark.parametrize(
    'path',
    (
        'scripts/gates/execution/new_consumer.py',
        'scripts/gates/config/future_contract.json',
        'scripts/harness/python_env.py',
        'java/gradle/build-logic/src/main/kotlin/new-convention.gradle.kts',
    ),
)
def test_shared_execution_inputs_keep_root_and_browser(path) -> None:
    snapshot = ChangeSnapshot('git-working-tree', 'head', None, (path,), 'fingerprint')
    names = {gate.name for gate in compile_gate_plan(snapshot).gates}
    assert {'browserTests', 'javaBuildVerification'} <= names


def test_python_config_changes_keep_toolchain_framework_and_dependency_audit() -> None:
    snapshot = ChangeSnapshot('git-working-tree', 'head', None, ('scripts/uv.lock',), 'fingerprint')
    names = {gate.name for gate in compile_gate_plan(snapshot).gates}
    assert {'scriptToolchainQuality', 'gateFrameworkTests', 'pythonDependencyAudit'} <= names


@pytest.mark.parametrize(
    ('path', 'browser', 'scan'),
    (
        ('java/web/src/test/java/example/RemovedTest.java', False, False),
        ('java/web/src/test/resources/new-test.json', False, False),
        ('java/web/README.md', False, False),
        ('java/tests/contracts/build.gradle.kts', False, False),
        ('java/tests/quality-gates/src/main/java/example/TestRule.java', False, False),
        ('java/tests/support/src/main/java/example/FixtureHelper.java', False, False),
        ('java/tests/fixtures/new-source.jsonl', True, False),
        ('java/web/src/main/resources/templates/new-page.html', True, True),
        ('java/web/src/main/resources/static/css/shell.css', True, False),
        ('java/sources/src/main/java/example/RemovedReader.java', True, True),
        ('java/future/src/main/resources/defaults.json', True, False),
        ('java/future/build.gradle.kts', True, True),
        ('java/settings.gradle.kts', True, True),
        ('java/gradle/libs.versions.toml', True, True),
        ('scripts/tests/conftest.py', False, True),
    ),
)
def test_runtime_suites_follow_distribution_inputs_not_java_test_modules(path, browser, scan):
    snapshot = ChangeSnapshot('git-working-tree', 'head', None, (path,), 'fingerprint')
    names = {gate.name for gate in compile_gate_plan(snapshot).gates}
    assert ('browserTests' in names, 'scanCommandSmoke' in names) == (browser, scan)
    if '/src/test/' in path or path.endswith(('.java', '/build.gradle.kts')):
        assert 'javaBuildVerification' in names
