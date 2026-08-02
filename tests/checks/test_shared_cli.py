"""验证每个领域 Check 都遵守同一套文件、入口和注册约定。"""

from __future__ import annotations

import ast
import stat
from pathlib import Path

import pytest
from scripts.checks.__main__ import main
from scripts.checks._framework import CheckSpec, invoke
from scripts.checks._registry import CHECKS

ROOT = Path(__file__).resolve().parents[2]
CHECKS_ROOT = ROOT / 'scripts' / 'checks'
DOMAIN_NAMES = {'agent', 'privacy', 'repository', 'source', 'web'}


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
        'agent.rules-sync',
        'repository.dead-command-reference',
        'security.secret-like-content',
        'repository.acceptance-case-mapping',
    } <= CHECKS.keys()


def test_registry_has_one_id_per_leaf_module() -> None:
    modules = [spec.module for spec in CHECKS.values()]
    expected_modules = {_module_name(path) for path in _leaf_paths()}

    assert len(modules) == len(set(modules))
    assert set(modules) == expected_modules
    assert all(not hasattr(spec, 'function') for spec in CHECKS.values())


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
            and node.module.startswith('scripts.checks.')
            and '.check_' in node.module
        ]
        public_functions = [node for node in functions if not node.name.startswith('_')]

        assert leaf_imports == [], path
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


def test_invoke_calls_the_fixed_check_entry(monkeypatch) -> None:
    import scripts.checks.agent.check_agent_permission_policy as permission

    monkeypatch.setattr(permission, 'SETTINGS_JSON', permission.ROOT / 'missing-permission.json')
    spec = CheckSpec(
        'agent.permission-policy',
        'scripts.checks.agent.check_agent_permission_policy',
    )

    result = invoke(spec, [])

    assert not result.passed
    assert '文件不存在' in result.diagnostics[0].message


def test_shared_cli_emits_single_pass_line(capsys) -> None:
    assert main(['repository.no-product-python']) == 0
    assert capsys.readouterr().out == '[repository.no-product-python] PASS\n'


def test_leaf_help_keeps_success_exit_code(capsys) -> None:
    assert main(['repository.no-product-python', '--help']) == 0
    assert capsys.readouterr().out == '[repository.no-product-python] PASS\n'


def test_shared_cli_does_not_add_catalog_listing_mode() -> None:
    with pytest.raises(SystemExit) as failure:
        main(['--list'])

    assert failure.value.code == 2


def test_leaf_modules_do_not_reintroduce_bootstrap_or_trigger_logic() -> None:
    for path in _leaf_paths():
        text = path.read_text(encoding='utf-8')
        assert 'TRIGGER_PATTERNS' not in text
        assert 'skip_if_not_triggered' not in text
        assert 'scripts.checks._trigger' not in text
        assert 'import argparse' not in text
        assert 'Path(__file__).resolve().parents' not in text
