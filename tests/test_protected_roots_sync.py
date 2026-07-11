from __future__ import annotations

from pathlib import Path

from scripts.agent_runtime import policy as runtime_policy
from scripts.quality import check_protected_roots_sync as sync_gate

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_ROOTS = [
    '.claude/',
    '.codex/',
    '.qoder/',
    '.agents/',
    'skills/',
    'harness/',
    'scripts/',
    'openspec/',
    'src/session_browser/',
    'tests/',
    'AGENTS.md',
    'CLAUDE.md',
]


def test_manifest_contains_required_protected_roots():
    roots = runtime_policy.protected_roots(ROOT)
    for required in REQUIRED_ROOTS:
        assert required in roots


def test_is_protected_path_matches_manifest_roots():
    roots = runtime_policy.protected_roots(ROOT)
    for protected in roots:
        sample = protected if not protected.endswith('/') else protected + 'example.txt'
        assert runtime_policy.is_protected_path(sample, ROOT), sample
    assert not runtime_policy.is_protected_path('README-not-protected.tmp', ROOT)


def test_stop_check_uses_manifest_protected_roots():
    text = (ROOT / 'scripts/harness/agent_stop_check.py').read_text(encoding='utf-8')
    assert 'runtime_policy.protected_roots' in text
    assert 'runtime_policy.is_protected_path' in text
    assert sync_gate.check_stop_check_uses_helper(runtime_policy.protected_roots(ROOT)) == []


def test_report_gate_uses_manifest_protected_roots():
    text = (ROOT / 'scripts/quality/check_agent_runtime_report.py').read_text(encoding='utf-8')
    assert 'runtime_policy.protected_roots' in text
    assert 'runtime_policy.is_protected_path' in text
    assert sync_gate.check_report_gate_uses_helper() == []


def test_sync_gate_fails_when_required_root_missing(tmp_path):
    roots = [root for root in runtime_policy.protected_roots(ROOT) if root != '.agents/']
    errors = sync_gate.check_required_manifest_roots(roots)
    assert any('.agents/' in error for error in errors)


def test_sync_gate_fails_when_skills_or_tests_missing(tmp_path):
    roots = [root for root in runtime_policy.protected_roots(ROOT) if root not in {'skills/', 'tests/'}]
    errors = sync_gate.check_required_manifest_roots(roots)
    assert any('skills/' in error for error in errors)
    assert any('tests/' in error for error in errors)
