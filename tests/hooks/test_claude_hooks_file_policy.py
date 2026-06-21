import pytest
from scripts.claude_hooks.policy.file_policy import evaluate_write_path


@pytest.mark.contract_case('HOOK-HARNESS-004')
def test_repo_write_allowed(tmp_path):
    d = evaluate_write_path('src/session_browser/a.py', tmp_path)
    assert d.allowed
    assert d.requires_quality_gate


@pytest.mark.contract_case('HOOK-HARNESS-004')
def test_local_generated_warns(tmp_path):
    d = evaluate_write_path('tmp/agent_logs/session1/a.jsonl', tmp_path)
    assert d.allowed
    assert d.warnings
