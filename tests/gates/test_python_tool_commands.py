"""验证 Python 质量 Gate 直接调用唯一工具 owner，而不回流产品 shell。"""

import tomllib
from pathlib import Path

from scripts.gates.catalog import gate_by_name

ROOT = Path(__file__).resolve().parents[2]
PYTHON_TOOL_GATES = (
    'pythonFormat',
    'pythonLint',
    'pythonCoverage',
    'pythonAudit',
    'pythonComplexity',
    'pythonDeadCode',
    'pythonDeps',
)


def _argv(name: str) -> tuple[str, ...]:
    command = gate_by_name(name).command
    assert command is not None
    return command.argv


def test_python_tool_gates_do_not_call_removed_shell_subcommands() -> None:
    for name in PYTHON_TOOL_GATES:
        argv = _argv(name)
        assert 'scripts/session-browser.sh' not in argv
        assert argv[:2] == ('{dev_python}', '-m')


def test_format_and_lint_cover_format_imports_and_full_lint_once() -> None:
    assert _argv('pythonFormat') == ('{dev_python}', '-m', 'ruff', 'format', '--check', '.')
    assert _argv('pythonLint') == (
        '{dev_python}',
        '-m',
        'ruff',
        'check',
        '--extend-select',
        'I',
        '.',
    )


def test_coverage_keeps_original_suite_and_report_contract() -> None:
    argv = _argv('pythonCoverage')
    assert argv[2:5] == ('pytest', '-W', 'error')
    assert 'tests/harness' in argv
    assert 'tests/checks/test_code_comment_language_gate.py' in argv
    assert 'tests/checks/test_python_security.py' in argv
    assert '--cov=scripts' in argv
    assert '--cov-branch' in argv
    assert '--cov-report=xml:.local/python/coverage/coverage.xml' in argv
    assert '--cov-fail-under=0' in argv


def test_audit_keeps_single_leaf_owner_and_network_blocking_policy() -> None:
    gate = gate_by_name('pythonAudit')
    assert _argv('pythonAudit')[2:4] == ('scripts.checks', 'repository.python-security')
    assert gate.network_failure == 'blocked'


def test_complexity_is_an_explicit_non_blocking_report() -> None:
    gate = gate_by_name('pythonComplexity')
    assert '不阻断' in gate.description
    assert _argv('pythonComplexity')[2:] == (
        'radon',
        'cc',
        '--min',
        'B',
        '--show-complexity',
        '--average',
        'scripts',
    )


def test_complexity_tool_is_a_direct_development_dependency() -> None:
    project = tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))
    dependencies = project['project']['optional-dependencies']['dev']

    assert 'radon' in dependencies
    assert 'xenon' not in dependencies
