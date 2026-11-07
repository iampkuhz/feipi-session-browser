from __future__ import annotations

from pathlib import Path

import yaml
from scripts.gates.checks.agent import check_documentation as sync_gate
from scripts.gates.checks.check_protocol import CheckStatus

ROOT = Path(__file__).resolve().parents[2]


def test_sync_gate_fails_when_agent_or_skill_root_missing():
    manifest = yaml.safe_load((ROOT / 'harness/agent-policy.manifest.yaml').read_text())
    manifest_roots = sync_gate._manifest_roots(manifest)
    roots = [root for root in manifest_roots if root not in {'.agents/', 'skills/'}]
    errors = sync_gate._check_required_manifest_roots(roots)
    assert any('.agents/' in error for error in errors)
    assert any('skills/' in error for error in errors)


def test_manifest_parser_returns_empty_model_for_invalid_shape():
    assert sync_gate._manifest_roots(None) == []


def test_public_check_reports_missing_required_files_as_fail(tmp_path, monkeypatch):
    monkeypatch.setattr(sync_gate, 'ROOT', tmp_path)

    result = sync_gate.check([])

    assert result.status is CheckStatus.FAIL
    assert result.reason == 'input-unavailable'
