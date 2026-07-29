"""共享 check CLI、结果模型与领域调用边界契约。"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.checks.__main__ import main
from scripts.checks._framework import CheckSpec, invoke
from scripts.checks._registry import CHECKS

ROOT = Path(__file__).resolve().parents[2]
RUNNERS = {'validate_repo_structure.py'}


def test_required_domains_are_registered() -> None:
    assert {
        'agent.rules-sync',
        'repository.dead-command-reference',
        'web.css-ownership',
        'security.secret-like-content',
        'openspec.acceptance-contracts',
    } <= CHECKS.keys()


def test_invoke_normalizes_domain_diagnostics(monkeypatch) -> None:
    import scripts.checks.agent.check_agent_permission_policy as permission

    monkeypatch.setattr(permission, 'SETTINGS_JSON', permission.ROOT / 'missing-permission.json')
    spec = CheckSpec(
        'agent.permission-policy',
        'scripts.checks.agent.check_agent_permission_policy',
        'check_permission_policy',
    )

    result = invoke(spec, [])

    assert not result.passed
    assert '文件不存在' in result.diagnostics[0].message


def test_shared_cli_emits_single_pass_line(capsys) -> None:
    assert main(['repository.no-product-python']) == 0
    assert capsys.readouterr().out == '[repository.no-product-python] PASS\n'


def test_shared_cli_does_not_add_catalog_listing_mode() -> None:
    with pytest.raises(SystemExit) as failure:
        main(['--list'])

    assert failure.value.code == 2


def test_leaf_modules_do_not_reintroduce_bootstrap_or_trigger_logic() -> None:
    for path in (ROOT / 'scripts' / 'checks').rglob('*.py'):
        text = path.read_text(encoding='utf-8')
        assert 'TRIGGER_PATTERNS' not in text
        assert 'skip_if_not_triggered' not in text
        assert 'scripts.checks._trigger' not in text
        if path.name not in RUNNERS | {'__init__.py', '__main__.py', '_framework.py'}:
            assert 'import argparse' not in text
        if path.name not in RUNNERS | {'__init__.py', '_framework.py'}:
            assert 'Path(__file__).resolve().parents' not in text
