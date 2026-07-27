"""共享 check CLI、结果模型与扫描缓存契约。"""

from __future__ import annotations

from pathlib import Path

from scripts.checks.__main__ import main
from scripts.checks._framework import CheckSpec, ScanContext, invoke
from scripts.checks._registry import CHECKS

ROOT = Path(__file__).resolve().parents[2]
RUNNERS = {
    'run_reuse_standard_cpd.py',
    'run_session_samples_gate.py',
}


def test_required_domains_are_registered() -> None:
    assert {
        'agent.rules-sync',
        'repository.dead-command-reference',
        'web.css-ownership',
        'security.secret-like-content',
        'openspec.acceptance-contracts',
    } <= CHECKS.keys()


def test_scan_context_reuses_file_discovery_and_text(tmp_path: Path) -> None:
    source = tmp_path / 'sample.txt'
    source.write_text('before', encoding='utf-8')
    context = ScanContext(tmp_path)

    assert context.files(('*.txt',)) == (source,)
    assert context.read_text(source) == 'before'
    source.write_text('after', encoding='utf-8')

    assert context.files(('*.txt',)) == (source,)
    assert context.read_text(source) == 'before'


def test_invoke_normalizes_domain_diagnostics(monkeypatch, tmp_path: Path) -> None:
    import scripts.checks.check_agent_permission_policy as permission

    monkeypatch.setattr(permission, 'SETTINGS_JSON', permission.ROOT / 'missing-permission.json')
    spec = CheckSpec(
        'agent.permission-policy',
        'scripts.checks.check_agent_permission_policy',
        'check_permission_policy',
    )

    result = invoke(spec, ScanContext(tmp_path), [])

    assert not result.passed
    assert '文件不存在' in result.diagnostics[0].message


def test_shared_cli_emits_single_pass_line(capsys) -> None:
    assert main(['repository.no-product-python']) == 0
    assert capsys.readouterr().out == '[repository.no-product-python] PASS\n'


def test_leaf_modules_do_not_reintroduce_bootstrap_or_trigger_logic() -> None:
    for path in (ROOT / 'scripts' / 'checks').glob('*.py'):
        text = path.read_text(encoding='utf-8')
        assert 'TRIGGER_PATTERNS' not in text
        assert 'skip_if_not_triggered' not in text
        assert 'scripts.checks._trigger' not in text
        if path.name not in RUNNERS | {'__main__.py', '_framework.py'}:
            assert 'import argparse' not in text
        if path.name not in RUNNERS | {'_framework.py'}:
            assert 'Path(__file__).resolve().parents' not in text
