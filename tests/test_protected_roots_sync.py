from __future__ import annotations

from pathlib import Path

from scripts.checks._framework import CheckStatus
from scripts.checks.agent import check_protected_roots_sync as sync_gate

ROOT = Path(__file__).resolve().parents[1]


def test_policy_manifest_contains_required_protected_roots():
    roots = sync_gate._manifest_roots(ROOT)
    assert sync_gate._check_required_manifest_roots(roots) == []


def test_agents_document_covers_complete_protected_scope():
    assert sync_gate._check_agents_doc_covers_required_roots(ROOT) == []


def test_sync_gate_fails_when_agent_or_skill_root_missing():
    roots = [
        root for root in sync_gate._manifest_roots(ROOT) if root not in {'.agents/', 'skills/'}
    ]
    errors = sync_gate._check_required_manifest_roots(roots)
    assert any('.agents/' in error for error in errors)
    assert any('skills/' in error for error in errors)


def test_manifest_reader_returns_empty_model_for_missing_required_manifest(tmp_path):
    assert sync_gate._manifest_roots(tmp_path) == []


def test_public_check_reports_missing_required_files_as_blocked(tmp_path, monkeypatch):
    monkeypatch.setattr(sync_gate, 'ROOT', tmp_path)

    result = sync_gate.check([])

    assert result.status is CheckStatus.BLOCKED
    assert not result.reason
