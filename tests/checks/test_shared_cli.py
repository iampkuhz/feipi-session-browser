"""验证每个领域 Check 都遵守同一套文件、入口和注册约定。"""

from __future__ import annotations

import ast
import stat
import sys
from pathlib import Path
from types import ModuleType

import pytest
import scripts.gates.checks.__main__ as check_cli
import yaml
from scripts.gates.checks._framework import (
    CheckResult,
    CheckSpec,
    CheckStatus,
    argument_parser,
    invoke,
)
from scripts.gates.checks._registry import CHECKS
from scripts.gates.definitions import GATES

ROOT = Path(__file__).resolve().parents[2]
CHECKS_ROOT = ROOT / 'scripts' / 'gates' / 'checks'
DOMAIN_NAMES = {'agent', 'privacy', 'repository', 'source'}


@pytest.fixture
def stub_spec(monkeypatch) -> CheckSpec:
    """注册不读取真实仓库输入的合成 leaf。"""

    module = ModuleType('tests.stub_check_module')
    module.check = lambda _arguments: CheckResult()
    monkeypatch.setitem(sys.modules, module.__name__, module)
    return CheckSpec('stub', module.__name__)


def _leaf_paths() -> list[Path]:
    return sorted(
        path
        for domain in DOMAIN_NAMES
        for path in (CHECKS_ROOT / domain).glob('*.py')
        if path.name != '__init__.py'
    )


def _module_name(path: Path) -> str:
    return '.'.join(path.relative_to(ROOT).with_suffix('').parts)


def test_required_domains_are_registered() -> None:
    assert {
        'agent.runtime-policy',
        'repository.repository-file-policy',
        'security.secret-like-content',
        'repository.acceptance-case-mapping',
    } <= CHECKS.keys()


def test_registry_contains_only_checks_owned_by_a_gate() -> None:
    declared = {
        step.check_id for gate in GATES for step in gate.run.steps if step.check_id is not None
    }
    assert set(CHECKS) == declared


def test_internal_check_cli_is_not_advertised_as_a_public_entry() -> None:
    manifest = yaml.safe_load((ROOT / 'harness' / 'manifest.yaml').read_text(encoding='utf-8'))
    commands = manifest['public_executables'].values()
    assert all('scripts.gates.checks' not in command for command in commands)

    pre_commit = (ROOT / '.pre-commit-config.yaml').read_text(encoding='utf-8')
    assert 'scripts.gates.checks' not in pre_commit
    assert 'scripts/gates/cli.py --mode incremental --gate languagePolicy' in pre_commit


def test_registry_has_one_id_per_leaf_module() -> None:
    modules = [spec.module for spec in CHECKS.values()]
    expected_modules = {_module_name(path) for path in _leaf_paths()}

    assert len(modules) == len(set(modules))
    assert set(modules) == expected_modules
    assert all(not hasattr(spec, 'function') for spec in CHECKS.values())
    assert all(not hasattr(spec, 'load') for spec in CHECKS.values())


def test_leaf_modules_expose_only_the_fixed_check_entry() -> None:
    for path in _leaf_paths():
        assert path.name.startswith('check_'), path
        assert not path.read_text(encoding='utf-8').startswith('#!'), path
        assert path.stat().st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH) == 0, path
        tree = ast.parse(path.read_text(encoding='utf-8'))
        functions = [
            node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        leaf_imports = [
            node.module
            for node in tree.body
            if isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.startswith('scripts.gates.checks.')
            and '.check_' in node.module
        ]
        public_functions = [node for node in functions if not node.name.startswith('_')]

        assert leaf_imports == [], path
        for function in functions:
            function_doc = ast.get_docstring(function) or ''
            assert function_doc, (path, function.name)
            assert any('\u4e00' <= character <= '\u9fff' for character in function_doc), (
                path,
                function.name,
            )
        assert [node.name for node in public_functions] == ['check'], path
        entry = public_functions[0]
        assert [argument.arg for argument in entry.args.args] == ['arguments'], path
        assert not entry.args.posonlyargs
        assert not entry.args.kwonlyargs
        assert entry.args.vararg is None
        assert entry.args.kwarg is None
        assert entry.returns is not None
        assert ast.unparse(entry.returns) == 'CheckResult', path
        assert not any(
            isinstance(node, ast.If) and '__name__' in ast.unparse(node.test) for node in tree.body
        ), path
        assert not any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == 'print'
            for node in ast.walk(tree)
        ), path

        module_doc = ast.get_docstring(tree) or ''
        compact_doc = ''.join(module_doc.split())
        assert '公开入口' in compact_doc or '唯一入口' in compact_doc, path
        assert '诊断' in module_doc or '失败' in module_doc, path


def test_invoke_calls_the_fixed_check_entry(stub_spec: CheckSpec) -> None:
    module = sys.modules[stub_spec.module]
    module.check = lambda _arguments: CheckResult.from_errors(['stub violation'])

    result = invoke(stub_spec, [])

    assert not result.passed
    assert result.diagnostics[0].message == 'stub violation'


def test_shared_cli_emits_single_pass_line(capsys, monkeypatch, stub_spec: CheckSpec) -> None:
    monkeypatch.setattr(check_cli, 'get_check', lambda _check_id: stub_spec)

    assert check_cli.main(['agent.runtime-policy']) == 0
    assert capsys.readouterr().out == 'GATE_RESULT status=PASS check=agent.runtime-policy\n'


def test_leaf_help_keeps_success_exit_code(capsys, monkeypatch, stub_spec: CheckSpec) -> None:
    module = sys.modules[stub_spec.module]

    def check_help(arguments: list[str]) -> CheckResult:
        argument_parser().parse_args(arguments)
        return CheckResult()

    module.check = check_help
    monkeypatch.setattr(check_cli, 'get_check', lambda _check_id: stub_spec)

    assert check_cli.main(['agent.runtime-policy', '--help']) == 0
    assert capsys.readouterr().out == 'GATE_RESULT status=PASS check=agent.runtime-policy\n'


def test_invoke_exception_is_execution_fail(stub_spec: CheckSpec) -> None:
    sys.modules[stub_spec.module].check = lambda _arguments: 1

    result = invoke(stub_spec, [])
    assert result.status is CheckStatus.FAIL
    assert result.reason == 'outcome-unknown'


def test_shared_cli_does_not_add_catalog_listing_mode() -> None:
    with pytest.raises(SystemExit) as failure:
        check_cli.main(['--list'])

    assert failure.value.code == 2


def test_leaf_modules_do_not_reintroduce_bootstrap_or_trigger_logic() -> None:
    for path in _leaf_paths():
        text = path.read_text(encoding='utf-8')
        assert 'TRIGGER_PATTERNS' not in text
        assert 'skip_if_not_triggered' not in text
        assert 'scripts.gates.checks._trigger' not in text
        assert 'import argparse' not in text
        assert 'Path(__file__).resolve().parents' not in text
