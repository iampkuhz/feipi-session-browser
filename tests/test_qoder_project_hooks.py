from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from scripts.harness.sessionctl import activation_config_hash


def _run(cmd: list[str], *, input_text: str = "", env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    merged.update(env or {})
    return subprocess.run(
        cmd,
        cwd=ROOT,
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=merged,
        check=False,
    )


def test_qoder_settings_binds_required_events_to_wrappers():
    settings = json.loads((ROOT / ".qoder/settings.json").read_text(encoding="utf-8"))

    def commands(event: str, matcher: str = "") -> list[str]:
        found: list[str] = []
        for entry in settings["hooks"].get(event, []):
            if matcher and entry.get("matcher") != matcher:
                continue
            if not matcher and entry.get("matcher"):
                continue
            found.extend(hook["command"] for hook in entry.get("hooks", []) if hook.get("type") == "command")
        return found

    expected = {
        ("SessionStart", ""): ".qoder/hooks/session-start.sh",
        ("PreToolUse", "Bash"): ".qoder/hooks/pre_tool_guard.sh",
        ("PreToolUse", "Write|Edit|MultiEdit|NotebookEdit"): ".qoder/hooks/pre_write_guard.sh",
        ("PostToolUse", "Bash"): ".qoder/hooks/post_bash_guard.sh",
        ("PostToolUse", "Write|Edit|MultiEdit|NotebookEdit"): ".qoder/hooks/post_tool_guard.sh",
        ("PostToolUseFailure", ""): ".qoder/hooks/tool_failure.sh",
        ("Stop", ""): ".qoder/hooks/stop_check.sh",
        ("StopFailure", ""): ".qoder/hooks/stop_failure.sh",
        ("SessionEnd", ""): ".qoder/hooks/session_end.sh",
    }
    for key, command in expected.items():
        found = commands(*key)
        assert any(command in item and "git rev-parse --show-toplevel" in item for item in found)


def test_qoder_session_start_without_run_marks_read_only_unbound():
    session_id = "synthetic-qoder-unbound"
    marker = ROOT / "tmp" / "agent_logs" / "qoder" / session_id / "read-only-unbound.json"
    if marker.exists():
        marker.unlink()
    payload = json.dumps({"sessionId": session_id, "cwd": str(ROOT)})
    proc = _run(["bash", ".qoder/hooks/session-start.sh"], input_text=payload, env={"FEIPI_RUN_ID": ""})
    assert proc.returncode == 0, proc.stderr or proc.stdout
    data = json.loads(marker.read_text(encoding="utf-8"))
    assert data["status"] == "read-only-unbound"
    assert data["client"] == "qoder"


def test_qoder_pre_write_payload_blocks_missing_candidate_path():
    proc = _run(
        ["bash", ".qoder/hooks/pre_write_guard.sh"],
        input_text=json.dumps({"client": "qoder", "toolName": "Write", "toolInput": {}}),
    )
    assert proc.returncode != 0
    assert "BLOCK" in (proc.stdout + proc.stderr)


def test_qoder_hook_parity_checker_reads_settings_json():
    proc = _run([sys.executable, "scripts/quality/check_agent_hook_parity.py"])
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "[agentHookParity] PASS" in proc.stdout


def test_qoder_activation_hash_includes_project_settings():
    config_hash = activation_config_hash(ROOT, "qoder")

    assert ".qoder/settings.json" in config_hash
    assert ".qoder/hook-bindings.md" in config_hash
