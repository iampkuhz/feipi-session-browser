import json
from datetime import datetime, timezone, timedelta
from scripts.claude_hooks.evidence import append_jsonl
from scripts.claude_hooks.paths import RepoPaths
from scripts.claude_hooks.policy.stop_policy import check_stop


def test_stop_blocks_missing_summary(tmp_path):
    paths = RepoPaths(repo_root=tmp_path, agent_log_dir=tmp_path / "tmp/agent_log", legacy_agent_dir=tmp_path / ".agent")
    append_jsonl(paths.changed_files, {
        "ts": datetime.now(timezone.utc).isoformat(),
        "changeId": "c1",
        "file": "src/session_browser/a.py",
        "requiresQualityGate": True,
        "qualityTarget": "python-src",
    })
    result = check_stop(paths)
    assert not result.passed
    assert "python-src" in result.required_targets


def test_stop_passes_valid_summary(tmp_path):
    paths = RepoPaths(repo_root=tmp_path, agent_log_dir=tmp_path / "tmp/agent_log", legacy_agent_dir=tmp_path / ".agent")
    append_jsonl(paths.changed_files, {
        "ts": datetime.now(timezone.utc).isoformat(),
        "changeId": "c1",
        "file": "src/session_browser/a.py",
        "requiresQualityGate": True,
        "qualityTarget": "python-src",
    })
    out = paths.quality_dir / "c1"
    out.mkdir(parents=True)
    (out / "quality-gate-summary.python-src.json").write_text(json.dumps({
        "status": "PASS",
        "finishedAt": (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat(),
        "requiredGates": {"pythonCompile": "PASS", "pytest": "PASS"}
    }))
    result = check_stop(paths)
    assert result.passed
