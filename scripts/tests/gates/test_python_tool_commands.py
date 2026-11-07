"""Python 工具链 Gate 的 single-recipe 命令声明契约。"""

from scripts.gates.catalog.registry import gate_by_name


def _step(gate_name: str, step_name: str):
    return next(step for step in gate_by_name(gate_name).recipe.steps if step.name == step_name)


def test_python_tools_explicitly_select_shared_config() -> None:
    for step_name in (
        'pythonFormat',
        'pythonLint',
        'pythonDependencyDeclarations',
        'pythonDeadCode',
    ):
        argv = _step('scriptToolchainQuality', step_name).argv
        assert argv[argv.index('--config') + 1] == '{tool_config}'
    security = _step('scriptToolchainQuality', 'pythonSourceSecurity').argv
    assert security[security.index('-c') + 1] == '{tool_config}'
    pytest = _step('gateFrameworkTests', 'gateFrameworkTests').argv
    assert pytest[pytest.index('-c') + 1] == '{tool_config}'
    assert pytest[pytest.index('--rootdir') + 1] == '{repo_root}'


def test_shell_gate_checks_later_files_and_does_not_execute_scripts(tmp_path):
    import subprocess

    from scripts.gates.execution.command_adapter import adapt_recipe_step

    scripts = tmp_path / 'scripts'
    scripts.mkdir()
    (scripts / 'a.sh').write_text('touch would-execute\n')
    (scripts / 'z.sh').write_text('if true; then\n')
    gate = gate_by_name('bashSyntax')
    (invocation,) = adapt_recipe_step(gate, gate.recipe.steps[0], tmp_path, mode='full')
    result = subprocess.run(invocation.argv, cwd=tmp_path, capture_output=True, check=False)
    assert result.returncode != 0
    assert b'z.sh' in result.stderr
    assert not (tmp_path / 'would-execute').exists()
