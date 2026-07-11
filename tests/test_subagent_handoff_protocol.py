from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "scripts" / "quality" / "check_subagent_handoff_protocol.py"


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_subagent_protocol_checker_passes():
    result = subprocess.run(
        [sys.executable, str(CHECKER)],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    assert result.returncode == 0, result.stdout
    assert "[subagentHandoffProtocol] PASS" in result.stdout


def test_required_handoff_fields_are_declared_for_all_platforms():
    required_fields = [
        "Goal",
        "Task id",
        "Task source",
        "Allowed files/directories",
        "Forbidden files/directories",
        "Required context files",
        "Expected output",
        "Validation command",
        "Failure policy",
    ]
    platform_docs = [
        ".claude/agents/qwen-main-default.md",
        ".codex/model-instructions.md",
        ".qoder/agents/qoder-main-default.md",
    ]
    for doc in platform_docs:
        text = _read(doc)
        for field in required_fields:
            assert field in text, f"{doc} missing {field}"
        assert "agent_id" in text or "instance id" in text
        assert "client/session_id" in text


def test_status_values_are_declared():
    docs = [
        "harness/agent-policy.manifest.yaml",
        ".claude/agents/qwen-main-default.md",
        ".codex/model-instructions.md",
        ".qoder/agents/qoder-main-default.md",
    ]
    for doc in docs:
        text = _read(doc)
        for status in ("PASS", "FAIL", "BLOCKED"):
            assert status in text, f"{doc} missing {status}"


def test_agents_md_remains_short_index():
    manifest = _read("harness/agent-policy.manifest.yaml")
    limit_line = next(
        line for line in manifest.splitlines() if line.strip().startswith("AGENTS.md:")
    )
    limit = int(limit_line.split(":", 1)[1].strip())
    agents_path = ROOT / "AGENTS.md"
    assert agents_path.stat().st_size <= limit
    assert "subagent_instance_protocol" not in _read("AGENTS.md")
