"""Python tooling Gate 的 single-recipe 命令声明 contract。"""

from scripts.gates.catalog import gate_by_name
from scripts.gates.model import RunKind


def _step(gate_name: str, step_name: str):
    return next(step for step in gate_by_name(gate_name).run.steps if step.name == step_name)


def test_python_tool_kinds_are_explicit() -> None:
    assert _step('scriptSourceStandard', 'pythonLint').kind is RunKind.COMMAND
    assert _step('scriptSourceStandard', 'pythonDependencyDeclarations').kind is RunKind.COMMAND
    assert _step('scriptSourceStandard', 'pythonSourceSecurity').kind is RunKind.COMMAND
    assert _step('scriptSourceStandard', 'pythonDeadCode').kind is RunKind.COMMAND
    assert gate_by_name('pythonDependencyVulnerabilities').run.steps[0].kind is RunKind.PYTHON_CHECK


def test_python_command_is_declared_once_without_redundant_ruff_selection() -> None:
    command = _step('scriptSourceStandard', 'pythonLint').argv
    assert command[:4] == ('{dev_python}', '-m', 'ruff', 'check')
    assert '--extend-select' not in command
    assert command[-1] == '.'


def test_recipe_and_timing_targets_have_separate_ownership() -> None:
    run = gate_by_name('scriptSourceStandard').run
    assert tuple(step.name for step in run.steps) == (
        'pythonFormat',
        'pythonLint',
        'bashSyntax',
        'pythonDependencyDeclarations',
        'pythonSourceSecurity',
        'pythonDeadCode',
    )
    assert run.target_seconds.incremental == 80
    assert run.target_seconds.full == 165
