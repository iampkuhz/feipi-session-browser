#!/usr/bin/env python3
"""PostToolUse evidence logger for Write/Edit/MultiEdit hooks.

Called by Claude Code as a PostToolUse hook after protected file edits.
Logs a JSONL entry per edit into .agent/task-evidence/<change-id>.jsonl.

Usage:
    python3 scripts/agent_hooks/log_change_evidence.py [file_path]

Env vars (checked in order):
    CC_TOOL_INPUT, CLAUDE_TOOL_INPUT, argv[1]

Modes:
    --self-test   Run self-test suite and exit
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths (all relative to project root = cwd)
# ---------------------------------------------------------------------------
EVIDENCE_DIR = Path(".agent/task-evidence")
ACTIVE_CHANGE = Path(".agent/active_change.json")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_active_change() -> dict | None:
    """Read .agent/active_change.json and return change_id or None."""
    if not ACTIVE_CHANGE.is_file():
        return None
    try:
        data = json.loads(ACTIVE_CHANGE.read_text(encoding="utf-8"))
        cid = data.get("change_id")
        if cid:
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return None


def get_file_path() -> str | None:
    """Resolve target file path from env vars or argv."""
    for env in ("CC_TOOL_INPUT", "CLAUDE_TOOL_INPUT"):
        val = os.environ.get(env, "").strip()
        if val:
            return val
    if len(sys.argv) > 1 and sys.argv[1] != "--self-test":
        return sys.argv[1]
    return None


def get_tool_name() -> str:
    """Best-effort tool name from env."""
    return os.environ.get("CC_TOOL_NAME", os.environ.get("CLAUDE_TOOL_NAME", "Write"))


def log_entry(file_path: str, tool: str, change_id: str | None) -> Path:
    """Append one JSONL line and return the evidence file path."""
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    target = EVIDENCE_DIR / f"{change_id}.jsonl" if change_id else EVIDENCE_DIR / "unknown.jsonl"
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "tool": tool,
        "file_path": file_path,
        "change_id": change_id or "unknown",
    }
    with target.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return target


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()

    file_path = get_file_path()
    if not file_path:
        # Nothing to log, but not an error (exit 0 by contract).
        return 0

    tool = get_tool_name()
    change_data = load_active_change()
    change_id = change_data["change_id"] if change_data else None
    log_entry(file_path, tool, change_id)
    return 0


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def self_test() -> int:
    """Run self-test suite. Returns 0 on all-pass, 1 on any failure."""
    passed = 0
    failed = 0

    def check(name: str, condition: bool) -> None:
        nonlocal passed, failed
        if condition:
            passed += 1
            print(f"  PASS: {name}")
        else:
            failed += 1
            print(f"  FAIL: {name}")

    # --- Test 1: with active change ---
    print("Test 1: evidence logged with active change present")
    # Ensure active_change.json exists (it should in real runs)
    change_data = load_active_change()
    if change_data is None:
        # Create a temp one for the test
        ACTIVE_CHANGE.parent.mkdir(parents=True, exist_ok=True)
        ACTIVE_CHANGE.write_text(json.dumps({"change_id": "test-change-001"}), encoding="utf-8")
        change_data = load_active_change()
        _cleanup_temp = True
    else:
        _cleanup_temp = False

    test_id = change_data["change_id"]
    evidence_file = EVIDENCE_DIR / f"{test_id}.jsonl"
    # Remove stale test entries
    if evidence_file.exists():
        evidence_file.unlink()

    os.environ["CC_TOOL_INPUT"] = "src/example/file.py"
    os.environ["CC_TOOL_NAME"] = "Edit"
    log_entry("src/example/file.py", "Edit", test_id)

    check("evidence file created", evidence_file.is_file())

    lines = evidence_file.read_text(encoding="utf-8").strip().split("\n") if evidence_file.is_file() else []
    check("at least one line written", len(lines) >= 1)

    if lines:
        entry = json.loads(lines[-1])
        check("file_path field present", "file_path" in entry and entry["file_path"] == "src/example/file.py")
        check("tool field present", "tool" in entry and entry["tool"] == "Edit")
        check("ts field present (ISO8601)", "ts" in entry and entry["ts"])
        check("change_id field present", "change_id" in entry and entry["change_id"] == test_id)

    # --- Test 2: without active change ---
    print("Test 2: evidence logged to unknown.jsonl when no active change")
    unknown_file = EVIDENCE_DIR / "unknown.jsonl"
    if unknown_file.exists():
        unknown_file.unlink()

    os.environ["CC_TOOL_NAME"] = "Write"
    # Temporarily hide active_change
    backup = None
    if ACTIVE_CHANGE.is_file():
        backup = ACTIVE_CHANGE.read_bytes()
        ACTIVE_CHANGE.unlink()

    log_entry("docs/README.md", "Write", None)

    if backup is not None:
        ACTIVE_CHANGE.write_bytes(backup)

    check("unknown.jsonl created", unknown_file.is_file())

    if unknown_file.is_file():
        lines = unknown_file.read_text(encoding="utf-8").strip().split("\n")
        check("at least one line written", len(lines) >= 1)
        if lines:
            entry = json.loads(lines[-1])
            check("file_path field present", "file_path" in entry and entry["file_path"] == "docs/README.md")
            check("tool field present", "tool" in entry and entry["tool"] == "Write")
            check("ts field present (ISO8601)", "ts" in entry and entry["ts"])
            check("change_id is unknown", "change_id" in entry and entry["change_id"] == "unknown")

    # --- Test 3: --self-test exits 0 ---
    print("Test 3: self-test return code")
    check("overall result", failed == 0)

    # Cleanup temp active_change if we created it
    if _cleanup_temp:
        ACTIVE_CHANGE.unlink(missing_ok=True)

    print(f"\nResults: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
