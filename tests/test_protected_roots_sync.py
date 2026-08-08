from __future__ import annotations

from pathlib import Path

import yaml
from scripts.gates.checks._framework import CheckStatus
from scripts.gates.checks.agent import check_agent_document_policy as sync_gate

ROOT = Path(__file__).resolve().parents[1]


def test_policy_manifest_contains_required_protected_roots():
    manifest = yaml.safe_load((ROOT / 'harness/agent-policy.manifest.yaml').read_text())
    roots, _phrases = sync_gate._manifest_policy(manifest)
    assert sync_gate._check_required_manifest_roots(roots) == []


def test_agents_document_covers_complete_protected_scope():
    manifest = yaml.safe_load((ROOT / 'harness/agent-policy.manifest.yaml').read_text())
    _roots, phrases = sync_gate._manifest_policy(manifest)
    assert sync_gate._check_agents_doc((ROOT / 'AGENTS.md').read_text(), phrases) == []


def test_sync_gate_fails_when_agent_or_skill_root_missing():
    manifest = yaml.safe_load((ROOT / 'harness/agent-policy.manifest.yaml').read_text())
    manifest_roots, _phrases = sync_gate._manifest_policy(manifest)
    roots = [root for root in manifest_roots if root not in {'.agents/', 'skills/'}]
    errors = sync_gate._check_required_manifest_roots(roots)
    assert any('.agents/' in error for error in errors)
    assert any('skills/' in error for error in errors)


def test_manifest_parser_returns_empty_model_for_invalid_shape():
    assert sync_gate._manifest_policy(None) == ([], [])


def test_public_check_reports_missing_required_files_as_fail(tmp_path, monkeypatch):
    monkeypatch.setattr(sync_gate, 'ROOT', tmp_path)

    result = sync_gate.check([])

    assert result.status is CheckStatus.FAIL
    assert result.reason == 'input-unavailable'
