from scripts.claude_hooks.policy.file_policy import evaluate_write_path


def test_repo_write_allowed(tmp_path):
    d = evaluate_write_path("src/session_browser/a.py", tmp_path)
    assert d.allowed
    assert d.requires_quality_gate


def test_local_generated_warns(tmp_path):
    d = evaluate_write_path("tmp/agent_log/a.jsonl", tmp_path)
    assert d.allowed
    assert d.warnings
