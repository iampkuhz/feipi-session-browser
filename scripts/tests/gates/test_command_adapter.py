"""RecipeStep 到 CommandInvocation 的 typed adapter contract。"""

from pathlib import Path

import pytest
from scripts.gates.catalog.gate_contracts import ExecutionMode
from scripts.gates.catalog.registry import gate_by_name
from scripts.gates.execution import command_adapter


def _write_wrapper(root: Path) -> Path:
    wrapper = root / 'java' / 'gradlew'
    wrapper.parent.mkdir(parents=True, exist_ok=True)
    wrapper.touch()
    return wrapper


def test_non_python_arguments_do_not_probe_python(tmp_path: Path, monkeypatch) -> None:
    def unexpected_python(*_args, **_kwargs):
        raise AssertionError('Unrelated Python discovery')

    monkeypatch.setattr(command_adapter, '_project_python', unexpected_python)
    assert command_adapter._expand('--parallel', tmp_path) == '--parallel'


def _adapt(gate_name: str, root: Path, monkeypatch):
    monkeypatch.setattr(command_adapter, '_project_python', lambda _root: '/tmp/python')
    gate = gate_by_name(gate_name)
    step = gate.recipe.steps[0]
    return command_adapter.adapt_recipe_step(
        gate,
        step,
        root,
        mode=ExecutionMode.INCREMENTAL,
        changed_files=('scripts/a.py',),
    )


def test_python_check_uses_declared_check_id(tmp_path: Path, monkeypatch) -> None:
    (invocation,) = _adapt('testSkipProhibition', tmp_path, monkeypatch)
    assert invocation.kind == 'python-check'
    assert invocation.argv == (
        '/tmp/python',
        '-m',
        'scripts.gates.checks',
        'repository.test-skip-prohibition',
    )
    assert dict(invocation.environment) == {
        'QUALITY_CHANGED_FILES': '["scripts/a.py"]',
        'QUALITY_EXECUTION_MODE': 'incremental',
    }


def test_gradle_and_java_rule_are_plain_console_invocations(tmp_path: Path, monkeypatch) -> None:
    _write_wrapper(tmp_path)
    gradle = _adapt('webResourceContracts', tmp_path, monkeypatch)[0]
    java_rule = _adapt('webStaticRules', tmp_path, monkeypatch)[0]
    assert gradle.kind == 'gradle-task'
    assert gradle.argv[-2:] == (':java:web:test', '--console=plain')
    assert java_rule.kind == 'java-rule'
    assert any(value.startswith('-PfeipiJavaQualityRules=') for value in java_rule.argv)


def test_sanitized_environment_removes_provider_private_values() -> None:
    result = command_adapter.sanitized_environment(
        {'SAFE': 'yes'},
        base={'CODEX_TOKEN': 'secret', 'QODER_MODE': 'private', 'PATH': '/bin'},
    )
    assert result == {'PATH': '/bin', 'SAFE': 'yes'}


def test_missing_required_command_is_not_counted_as_process(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(command_adapter, '_project_python', lambda _root: '/tmp/python')
    gate = gate_by_name('gateFrameworkTests')
    assert (
        command_adapter.adapt_recipe_step(
            gate,
            gate.recipe.steps[0],
            tmp_path,
            mode='full',
        )
        == ()
    )


def test_python_config_expands_from_repository_root(tmp_path: Path, monkeypatch) -> None:
    invocation = _adapt('scriptToolchainQuality', tmp_path, monkeypatch)[0]
    assert invocation.argv[invocation.argv.index('--config') + 1] == str(
        tmp_path / 'scripts/pyproject.toml'
    )
    (scan,) = _adapt('scanCommandSmoke', tmp_path, monkeypatch)
    assert scan.argv[scan.argv.index('-c') + 1] == str(tmp_path / 'scripts/pyproject.toml')
    assert scan.argv[scan.argv.index('--rootdir') + 1] == str(tmp_path)


@pytest.mark.parametrize('gate_name', ('webResourceContracts', 'webStaticRules'))
def test_gradle_invocations_use_nested_wrapper_and_explicit_build_root(
    tmp_path: Path, monkeypatch, gate_name: str
) -> None:
    wrapper = _write_wrapper(tmp_path)
    invocation = _adapt(gate_name, tmp_path, monkeypatch)[0]
    assert invocation.argv[:3] == (str(wrapper), '-p', str(tmp_path / 'java'))
    assert invocation.argv[-1] == '--console=plain'


@pytest.mark.parametrize('gate_name', ('webResourceContracts', 'webStaticRules'))
def test_missing_nested_gradle_wrapper_fails_closed(
    tmp_path: Path, monkeypatch, gate_name: str
) -> None:
    (tmp_path / 'gradlew').touch()
    assert _adapt(gate_name, tmp_path, monkeypatch) == ()


def test_web_rules_are_one_gradle_invocation_with_all_rules(tmp_path: Path) -> None:
    _write_wrapper(tmp_path)
    gate = gate_by_name('webStaticRules')
    invocations = tuple(
        invocation
        for step in gate.recipe.steps
        for invocation in command_adapter.adapt_recipe_step(gate, step, tmp_path, mode='full')
    )
    assert len(invocations) == 1
    assert (
        '-PfeipiJavaQualityRules=raw-innerhtml,layout-inline-style,template-contract,static-resource-contract,css-ownership'
        in invocations[0].argv
    )


def test_scan_smoke_is_one_pytest_process(tmp_path: Path, monkeypatch) -> None:
    (invocation,) = _adapt('scanCommandSmoke', tmp_path, monkeypatch)
    assert invocation.kind == 'scan-smoke'
    assert invocation.argv[:3] == ('/tmp/python', '-m', 'pytest')
    assert invocation.argv[-2:] == gate_by_name('scanCommandSmoke').recipe.steps[0].tests


def test_playwright_uses_native_full_discovery(tmp_path: Path, monkeypatch) -> None:
    (invocation,) = _adapt('browserTests', tmp_path, monkeypatch)
    assert invocation.kind == 'playwright'
    assert invocation.argv == ('npm', '--prefix', 'java/tests/playwright', 'test')
    assert 'BASE_URL' not in dict(invocation.environment)


@pytest.mark.parametrize(
    ('mode', 'changes', 'expected'),
    (
        ('incremental', ('scripts/tests/checks/test_removed.py',), ('checks',)),
        ('incremental', ('scripts/tests/future/test_new.py',), ('.',)),
        ('incremental', ('scripts/tests/conftest.py',), ('.',)),
        ('incremental', ('scripts/gates/execution/new_consumer.py',), ('.',)),
        ('incremental', ('scripts/uv.lock',), ('.',)),
        (
            'incremental',
            ('scripts/tests/quality/test_added.py', 'scripts/gates/presentation/new_report.py'),
            ('gates', 'quality', 'test_added.py'),
        ),
        (
            'incremental',
            ('scripts/gates/checks/agent/new_check.py',),
            ('checks', 'gates', 'test_added.py'),
        ),
        ('full', (), ('.',)),
    ),
)
def test_framework_uses_native_discovery_for_leaf_and_shared_inputs(
    tmp_path, monkeypatch, mode, changes, expected
):
    monkeypatch.setattr(command_adapter, '_project_python', lambda _root: '/tmp/python')
    tests = tmp_path / 'scripts/tests'
    for name in ('checks', 'gates', 'quality'):
        (tests / name).mkdir(parents=True)
    (tests / 'test_added.py').touch()
    gate = gate_by_name('gateFrameworkTests')
    (invocation,) = command_adapter.adapt_recipe_step(
        gate, gate.recipe.steps[0], tmp_path, mode=mode, changed_files=changes
    )
    args = invocation.argv[invocation.argv.index('error') + 1 :]
    assert (
        tuple(Path(path).relative_to('scripts/tests').as_posix() for path in args[2:]) == expected
    )
    smoke = gate_by_name('scanCommandSmoke').recipe.steps[0].tests
    assert args[:2] == tuple(f'--ignore={path}' for path in smoke)
