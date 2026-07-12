from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "checks"))

import check_agent_entry_parity as parity  # noqa: E402


def _read(rel_path: str) -> str:
    return (ROOT / rel_path).read_text(encoding="utf-8", errors="replace")


def test_entry_parity_covers_qoder():
    for entry in parity.REQUIRED_LOGICAL_AGENTS:
        assert entry.qoder_path or entry.qoder_unsupported_reason, entry.name
    assert any(entry.qoder_path for entry in parity.REQUIRED_LOGICAL_AGENTS)


def test_all_required_logical_agents_have_entries_or_unsupported_reason():
    expected = {
        "main-default",
        "java-backend-implementer",
        "session-ingestion-specialist",
        "ui-implementation-specialist",
        "mhtml-export-specialist",
        "quality-gate-diagnoser",
        "privacy-reviewer",
        "runtime-isolation-diagnoser",
        "repo-mapper",
        "openspec-planner",
    }
    assert {entry.name for entry in parity.REQUIRED_LOGICAL_AGENTS} == expected
    for entry in parity.REQUIRED_LOGICAL_AGENTS:
        for platform in ("claude", "codex", "qoder"):
            rel_path, reason = parity._path_or_reason(entry, platform)
            assert bool(rel_path) ^ bool(reason), (entry.name, platform)
            if rel_path:
                assert (ROOT / rel_path).is_file(), (entry.name, platform, rel_path)
            else:
                assert reason and len(reason) >= 20, (entry.name, platform)


def test_claude_main_allowlist_mentions_domain_specialists():
    text = _read(".claude/agents/qwen-main-default.md")
    for specialist in parity.REQUIRED_CLAUDE_MAIN_SPECIALISTS:
        assert specialist in text


def test_agent_entries_reference_required_skills():
    for entry in parity.REQUIRED_LOGICAL_AGENTS:
        if not entry.required_skill:
            continue
        assert (ROOT / entry.required_skill).is_file(), entry.required_skill
        for platform in ("claude", "codex", "qoder"):
            rel_path, _reason = parity._path_or_reason(entry, platform)
            if rel_path:
                assert entry.required_skill in _read(rel_path), (entry.name, platform)


def test_check_agent_entry_parity_script_passes():
    result = subprocess.run(
        [sys.executable, "scripts/checks/check_agent_entry_parity.py"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        env={"ACTIVE_CHANGE_ID": "harden-agent-runtime-full-v3"},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS" in result.stdout
