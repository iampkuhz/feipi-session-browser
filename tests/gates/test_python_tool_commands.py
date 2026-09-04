"""Python 工具链 Gate 的 single-recipe 命令声明契约。"""

from scripts.gates.catalog.gate_contracts import RecipeStepKind
from scripts.gates.catalog.registry import gate_by_name


def _step(gate_name: str, step_name: str):
    return next(step for step in gate_by_name(gate_name).recipe.steps if step.name == step_name)


def test_python_tool_step_kinds_are_explicit() -> None:
    assert _step('scriptToolchainQuality', 'pythonLint').kind is RecipeStepKind.COMMAND
    assert (
        _step('scriptToolchainQuality', 'pythonDependencyDeclarations').kind
        is RecipeStepKind.COMMAND
    )
    assert _step('scriptToolchainQuality', 'pythonSourceSecurity').kind is RecipeStepKind.COMMAND
    assert _step('scriptToolchainQuality', 'pythonDeadCode').kind is RecipeStepKind.COMMAND
    assert gate_by_name('pythonDependencyAudit').recipe.steps[0].kind is RecipeStepKind.PYTHON_CHECK


def test_python_command_is_declared_once_without_redundant_ruff_selection() -> None:
    command = _step('scriptToolchainQuality', 'pythonLint').argv
    assert command[:4] == ('{dev_python}', '-m', 'ruff', 'check')
    assert '--extend-select' not in command
    assert command[-1] == '.'


def test_recipe_and_duration_expectations_have_separate_ownership() -> None:
    gate_recipe = gate_by_name('scriptToolchainQuality').recipe
    assert tuple(step.name for step in gate_recipe.steps) == (
        'pythonFormat',
        'pythonLint',
        'bashSyntax',
        'pythonDependencyDeclarations',
        'pythonSourceSecurity',
        'pythonDeadCode',
    )
    assert gate_recipe.duration_expectations.incremental == 80
    assert gate_recipe.duration_expectations.full == 165
