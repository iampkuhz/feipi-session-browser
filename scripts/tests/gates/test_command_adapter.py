"""RecipeStep 到 CommandInvocation 的 typed adapter contract。"""

from dataclasses import replace
from pathlib import Path

import pytest
from scripts.gates.catalog.gate_contracts import ExecutionMode
from scripts.gates.catalog.registry import gate_by_name
from scripts.gates.execution import command_adapter


def _write_wrapper(root: Path, platform: str | None = None) -> Path:
    platform = platform or command_adapter.sys.platform
    wrapper = root / 'java' / ('gradlew.bat' if platform == 'win32' else 'gradlew')
    wrapper.parent.mkdir(parents=True, exist_ok=True)
    wrapper.touch()
    return wrapper


def test_non_python_arguments_do_not_probe_python(tmp_path: Path, monkeypatch) -> None:
    def unexpected_python(*args, **kwargs):
        raise AssertionError('Unrelated Python discovery')

    monkeypatch.setattr(command_adapter, '_project_python', unexpected_python)
    assert command_adapter._expand('--parallel', tmp_path) == '--parallel'
    assert command_adapter._expand('--workers={playwright_workers}', tmp_path).startswith(
        '--workers='
    )


def _adapt(gate_name: str, root: Path, monkeypatch):
    monkeypatch.setattr(command_adapter, '_project_python', lambda _root, dev=False: '/tmp/python')
    gate = gate_by_name(gate_name)
    step = gate.recipe.steps[0]
    if gate_name == 'scanCommandSmoke':
        step = replace(step, prerequisite_tasks=(':java:app:installDist',))
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


def test_scan_step_freezes_two_real_processes(tmp_path: Path, monkeypatch) -> None:
    _write_wrapper(tmp_path)
    invocations = _adapt('scanCommandSmoke', tmp_path, monkeypatch)
    assert [invocation.kind for invocation in invocations] == [
        'gradle-prerequisite',
        'scan-smoke',
    ]
    assert len({invocation.invocation_id for invocation in invocations}) == 2
    assert all(invocation.gate_name == 'scanCommandSmoke' for invocation in invocations)


def test_playwright_adapter_freezes_base_url(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(command_adapter, '_project_python', lambda _root, dev=False: '/tmp/python')
    gate = gate_by_name('browserTests')
    (invocation,) = command_adapter.adapt_recipe_step(
        gate,
        gate.recipe.steps[0],
        tmp_path,
        mode='full',
        base_url='http://127.0.0.1:8080',
    )
    assert invocation.argv[:5] == ('npm', '--prefix', 'java/tests/playwright', 'test', '--')
    assert dict(invocation.environment)['BASE_URL'] == 'http://127.0.0.1:8080'
    assert 'QUALITY_CHANGED_FILES' not in dict(invocation.environment)


def test_sanitized_environment_removes_provider_private_values() -> None:
    result = command_adapter.sanitized_environment(
        {'SAFE': 'yes'},
        base={'CODEX_TOKEN': 'secret', 'QODER_MODE': 'private', 'PATH': '/bin'},
    )
    assert result == {'PATH': '/bin', 'SAFE': 'yes'}


def test_missing_required_command_is_not_counted_as_process(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(command_adapter, '_project_python', lambda _root, dev=False: '/tmp/python')
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
    _write_wrapper(tmp_path)
    scan = _adapt('scanCommandSmoke', tmp_path, monkeypatch)[1]
    assert scan.argv[scan.argv.index('-c') + 1] == str(tmp_path / 'scripts/pyproject.toml')
    assert scan.argv[scan.argv.index('--rootdir') + 1] == str(tmp_path)


@pytest.mark.parametrize('platform', ('linux', 'darwin', 'win32'))
@pytest.mark.parametrize(
    'gate_name', ('webResourceContracts', 'webStaticRules', 'scanCommandSmoke')
)
def test_gradle_invocations_use_platform_wrapper_and_explicit_build_root(
    tmp_path: Path, monkeypatch, platform: str, gate_name: str
) -> None:
    wrapper = _write_wrapper(tmp_path, platform)
    monkeypatch.setattr(command_adapter.sys, 'platform', platform)
    invocation = _adapt(gate_name, tmp_path, monkeypatch)[0]
    assert invocation.argv[:3] == (str(wrapper), '-p', str(tmp_path / 'java'))
    assert invocation.argv[-1] == '--console=plain'


@pytest.mark.parametrize(
    'gate_name', ('webResourceContracts', 'webStaticRules', 'scanCommandSmoke')
)
def test_missing_nested_gradle_wrapper_fails_closed(
    tmp_path: Path, monkeypatch, gate_name: str
) -> None:
    (tmp_path / 'gradlew').touch()
    assert _adapt(gate_name, tmp_path, monkeypatch) == ()


@pytest.mark.parametrize('platform', ('linux', 'win32'))
def test_other_platform_wrapper_is_not_a_fallback(
    tmp_path: Path, monkeypatch, platform: str
) -> None:
    _write_wrapper(tmp_path, 'linux' if platform == 'win32' else 'win32')
    monkeypatch.setattr(command_adapter.sys, 'platform', platform)
    assert _adapt('webResourceContracts', tmp_path, monkeypatch) == ()


def test_web_rules_are_one_gradle_invocation_with_all_rules(tmp_path: Path, monkeypatch) -> None:
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


def test_scan_without_prerequisite_is_one_pytest_process(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(command_adapter, '_project_python', lambda _root, dev=False: '/tmp/python')
    gate = gate_by_name('scanCommandSmoke')
    step = replace(gate.recipe.steps[0], prerequisite_tasks=())
    (invocation,) = command_adapter.adapt_recipe_step(gate, step, tmp_path, mode='full')
    assert invocation.kind == 'scan-smoke'
    assert invocation.argv[:3] == ('/tmp/python', '-m', 'pytest')


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
    monkeypatch.setattr(command_adapter, '_project_python', lambda _root, dev=False: '/tmp/python')
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
