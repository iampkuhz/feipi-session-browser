"""Python Gate v6 职责与稳定命令 contract。"""

from pathlib import Path

from scripts.gates.catalog import gate_by_name
from scripts.gates.model import MinimumTier, RunKind

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_format_and_lint_remain_stable_direct_commands() -> None:
    assert gate_by_name('pythonFormat').run.argv == (
        '{dev_python}',
        '-m',
        'ruff',
        'format',
        '--check',
        '.',
    )
    assert gate_by_name('pythonLint').run.argv == (
        '{dev_python}',
        '-m',
        'ruff',
        'check',
        '--extend-select',
        'I',
        '.',
    )


def test_harness_tests_keep_approved_suites_without_coverage_arguments() -> None:
    gate = gate_by_name('pythonHarnessTests')
    argv = gate.run.argv
    assert argv[:5] == ('{dev_python}', '-m', 'pytest', '-W', 'error')
    assert argv[5:] == (
        'tests/harness',
        'tests/gates',
        'tests/checks',
        'tests/quality',
        'tests/misc',
    )
    assert gate.run.glob_args == ('tests/test_*.py',)
    assert all(not value.startswith('--cov') for value in argv)
    assert gate.run.required_paths == argv[5:]


def test_every_python_test_file_has_exactly_one_pytest_gate() -> None:
    """目录归属必须覆盖全部 Python 测试，并禁止两个 Gate 重复执行同一文件。"""
    all_tests = {
        path.relative_to(REPO_ROOT).as_posix() for path in (REPO_ROOT / 'tests').rglob('test_*.py')
    }
    harness = gate_by_name('pythonHarnessTests').run
    harness_roots = tuple(
        path.rstrip('/') + '/' for path in harness.argv if path.startswith('tests/')
    )
    harness_tests = {
        path
        for path in all_tests
        if path.startswith(harness_roots)
        or any(Path(path).match(pattern) for pattern in harness.glob_args)
    }
    web_root = gate_by_name('sessionDetailStaticTests').run.argv[-1].rstrip('/') + '/'
    web_tests = {path for path in all_tests if path.startswith(web_root)}
    smoke = gate_by_name('scanScriptSmoke').run
    smoke_tests = {path for path in smoke.required_paths if path.startswith('tests/')}

    owner_sets = (harness_tests, web_tests, smoke_tests)
    assert set().union(*owner_sets) == all_tests
    assert sum(len(paths) for paths in owner_sets) == len(all_tests)


def test_source_security_is_direct_offline_bandit_with_policy() -> None:
    gate = gate_by_name('pythonSourceSecurity')
    assert gate.run.kind is RunKind.COMMAND
    assert gate.run.argv == (
        '{dev_python}',
        '-m',
        'bandit',
        '-q',
        '-c',
        'pyproject.toml',
        '-r',
        'scripts',
        '--severity-level',
        'high',
    )
    assert gate.minimum_tier is MinimumTier.REQUIRED


def test_dependency_vulnerabilities_is_full_only_typed_dev_python_check() -> None:
    gate = gate_by_name('pythonDependencyVulnerabilities')
    assert gate.run.kind is RunKind.PYTHON_CHECK
    assert gate.run.check == 'repository.python-dependency-vulnerabilities'
    assert gate.run.python == 'dev'
    assert gate.run.required_paths == (
        'scripts/checks/repository/check_python_dependency_vulnerabilities.py',
    )
    assert gate.minimum_tier is MinimumTier.FULL
    assert gate.network_failure == 'blocked'


def test_dependency_declarations_trigger_python_import_changes_but_not_lockfile() -> None:
    rule = gate_by_name('pythonDependencyDeclarations').target_rules[0]
    assert 'scripts/**/*.py' in rule.patterns
    assert 'uv.lock' not in rule.patterns
