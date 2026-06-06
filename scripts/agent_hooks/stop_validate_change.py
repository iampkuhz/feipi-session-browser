#!/usr/bin/env python3
"""Stop/SubagentStop hook: validate that protected edits have matching
OpenSpec change and evidence before the agent finishes.

Called by Claude Code as a Stop/SubagentStop hook.  Checks whether
uncommitted changes exist under protected roots, and if so validates
that tmp/active_change.json, the change directory (proposal.md,
design.md, tasks.md), and evidence log are all present and populated.

Usage:
    python3 scripts/agent_hooks/stop_validate_change.py
    python3 scripts/agent_hooks/stop_validate_change.py --self-test

Env vars:
    FEIPI_SKIP_STOP_HOOK=1   Emergency bypass – always exit 0.

Exit codes:
    0  ALLOW  – clean stop or change is complete
    2  BLOCK  – protected changes detected but change/evidence is incomplete
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Roots whose uncommitted edits require an OpenSpec change.
PROTECTED_ROOTS = [
    "CLAUDE.md",
    "AGENTS.md",
    "openspec/",
    ".claude/",
    "scripts/",
    "harness/",
    "src/",
]

ACTIVE_CHANGE_FILE = Path("tmp/active_change.json")
EVIDENCE_DIR = Path("tmp/task-evidence")

# Required files inside openspec/changes/<change-id>/
REQUIRED_CHANGE_FILES = ["proposal.md", "design.md", "tasks.md"]
EXIT_ALLOW = 0
EXIT_BLOCK = 2

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _repo_root() -> Path:
    return Path.cwd().resolve()


def has_uncommitted_changes(roots: list[str] | None = None) -> bool:
    """Return True when any protected root has unstaged or staged changes."""
    if roots is None:
        roots = PROTECTED_ROOTS
    root = _repo_root()
    try:
        result = subprocess.run(
            ["git", "status", "--short"] + roots,
            capture_output=True,
            text=True,
            cwd=root,
            timeout=10,
        )
        return bool(result.stdout.strip())
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        # If git fails, assume there are changes (safer side).
        return True


def load_active_change() -> dict | None:
    """Parse active_change.json from the current OpenSpec location."""
    root = _repo_root()
    p = root / ACTIVE_CHANGE_FILE
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def change_id_from_active(active: dict | None) -> str | None:
    if active:
        return active.get("change_id")
    return None


def change_dir_exists(change_id: str) -> bool:
    return (_repo_root() / "openspec" / "changes" / change_id).is_dir()


def required_files_present(change_id: str) -> list[str]:
    """Return list of missing required files."""
    base = _repo_root() / "openspec" / "changes" / change_id
    missing = []
    for name in REQUIRED_CHANGE_FILES:
        if not (base / name).is_file():
            missing.append(name)
    return missing


def evidence_file(change_id: str) -> Path:
    """Return the current evidence file path."""
    return _repo_root() / EVIDENCE_DIR / f"{change_id}.jsonl"


def has_evidence_entries(change_id: str) -> bool:
    ef = evidence_file(change_id)
    if not ef.is_file():
        return False
    try:
        text = ef.read_text(encoding="utf-8").strip()
        return bool(text)  # non-empty
    except OSError:
        return False


def has_completed_tasks(change_id: str) -> bool:
    """Check tasks.md for at least one task marked complete (- [x] or [x])."""
    tasks = _repo_root() / "openspec" / "changes" / change_id / "tasks.md"
    if not tasks.is_file():
        return False
    content = tasks.read_text(encoding="utf-8")
    # Look for - [x] pattern (common markdown task completion marker)
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("- [x]") or stripped.startswith("* [x]"):
            return True
    return False


def repair_messages(change_id: str | None = None) -> list[str]:
    """Return concise instructions that Claude can turn into next actions."""
    target = f" '{change_id}'" if change_id else ""
    return [
        "Continue instead of stopping: repair the OpenSpec state, then retry stop.",
        f"  1. Ensure active_change.json points to the intended active change{target}.",
        "  2. Ensure proposal.md, design.md, and tasks.md exist under that change.",
        "  3. Record or preserve edit evidence in tmp/agent_logs/current/task-evidence/<change-id>.jsonl.",
        "  4. Mark completed tasks in tasks.md before final stop.",
    ]


# ---------------------------------------------------------------------------
# Core validation
# ---------------------------------------------------------------------------


def validate() -> tuple[int, list[str]]:
    """Run the stop-validation gate.

    Returns (exit_code, messages).
    exit_code 0 = allow, 2 = block.
    """
    messages: list[str] = []

    # Emergency bypass
    if os.environ.get("FEIPI_SKIP_STOP_HOOK", "").strip() == "1":
        messages.append("EMERGENCY BYPASS: FEIPI_SKIP_STOP_HOOK=1 detected, skipping validation.")
        return 0, messages

    # No protected changes -> clean stop
    if not has_uncommitted_changes():
        messages.append("No protected changes detected. Clean stop.")
        return 0, messages

    messages.append("Protected changes detected. Validating OpenSpec change completeness ...")

    # Check active_change.json
    active = load_active_change()
    if active is None:
        messages.append(
            "BLOCK: protected files changed without active change "
            "(active_change.json missing or invalid)."
        )
        messages.extend(repair_messages())
        return EXIT_BLOCK, messages

    cid = change_id_from_active(active)
    if not cid:
        messages.append("BLOCK: active_change.json missing 'change_id'.")
        messages.extend(repair_messages())
        return EXIT_BLOCK, messages

    # Check change directory exists
    if not change_dir_exists(cid):
        messages.append(f"BLOCK: openspec/changes/{cid}/ directory not found.")
        messages.extend(repair_messages(cid))
        return EXIT_BLOCK, messages

    # Check required files
    missing = required_files_present(cid)
    if missing:
        messages.append(
            f"WARN/BLOCK: change '{cid}' is missing required files: {', '.join(missing)}"
        )

    # Check evidence
    ef = evidence_file(cid)
    if not has_evidence_entries(cid):
        messages.append(
            f"WARN/BLOCK: no evidence entries in {ef.relative_to(_repo_root())}"
        )

    # Check completed tasks (informational)
    if has_completed_tasks(cid):
        messages.append(f"  tasks.md: some tasks marked complete (change in progress).")
    else:
        messages.append(f"  tasks.md: no tasks marked complete yet.")

    # Decision: if missing required files or no evidence -> block
    if missing or not has_evidence_entries(cid):
        messages.append(
            "Result: BLOCK – protected changes exist but change/evidence is incomplete."
        )
        messages.extend(repair_messages(cid))
        return EXIT_BLOCK, messages

    messages.append(f"Result: ALLOW – change '{cid}' has required files and evidence.")
    return 0, messages


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------


def _run_self_test() -> int:
    """Run self-test suite in a temporary git repo.

    Sub-tests:
      1. no changes, no active change -> ALLOW
      2. protected changes, no active change -> BLOCK
      3. protected changes, active change, evidence present -> ALLOW
      4. emergency bypass -> ALWAYS ALLOW
    """
    import shutil

    results: list[tuple[str, bool, str]] = []

    def check(name: str, condition: bool, detail: str = "") -> None:
        passed = condition
        status = "PASS" if passed else "FAIL"
        results.append((name, passed, detail))
        print(f"  [{status}] {name}" + (f" -- {detail}" if detail else ""))

    root = _repo_root()

    with tempfile.TemporaryDirectory(prefix="stop_validate_test_") as tmpdir:
        tmp = Path(tmpdir)

        # -- Create a minimal git repo --
        subprocess.run(["git", "init", "-q", str(tmp)], check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp, check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=tmp, check=True, capture_output=True,
        )

        # Create initial files and commit
        for p in [
            tmp / "CLAUDE.md",
            tmp / "AGENTS.md",
            tmp / "README.md",
        ]:
            p.write_text("# test\n", encoding="utf-8")
        (tmp / "openspec" / "changes" / "archive").mkdir(parents=True)
        (tmp / "tmp").mkdir(parents=True)
        (tmp / "src").mkdir(parents=True)
        (tmp / "scripts").mkdir(parents=True)

        subprocess.run(["git", "add", "."], cwd=tmp, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "initial", "-q", "--allow-empty"],
            cwd=tmp, check=True, capture_output=True,
        )

        # --- Sub-test 1: no changes, no active change -> ALLOW ---
        print("Sub-test 1: no protected changes, no active change -> ALLOW")
        saved_cwd = os.getcwd()
        os.chdir(tmp)
        saved_skip = os.environ.pop("FEIPI_SKIP_STOP_HOOK", None)
        exit_code, msgs = validate()
        os.chdir(saved_cwd)
        if saved_skip is not None:
            os.environ["FEIPI_SKIP_STOP_HOOK"] = saved_skip
        check("exit code is 0 (ALLOW)", exit_code == 0, f"exit={exit_code}")

        # --- Sub-test 2: protected changes, no active change -> BLOCK ---
        print("Sub-test 2: protected changes, no active change -> BLOCK")
        os.chdir(tmp)
        saved_skip = os.environ.pop("FEIPI_SKIP_STOP_HOOK", None)
        # Modify a protected file
        (tmp / "CLAUDE.md").write_text("# modified\n", encoding="utf-8")
        exit_code, msgs = validate()
        os.chdir(saved_cwd)
        if saved_skip is not None:
            os.environ["FEIPI_SKIP_STOP_HOOK"] = saved_skip
        check("exit code is 2 (BLOCK)", exit_code == EXIT_BLOCK, f"exit={exit_code}")
        has_block_msg = any("BLOCK" in m or "block" in m.lower() for m in msgs)
        check("message contains BLOCK", has_block_msg,
              "messages: " + "; ".join(msgs[:3]))

        # --- Sub-test 3: protected changes + active change + evidence -> ALLOW ---
        print("Sub-test 3: protected changes + active change + evidence -> ALLOW")
        os.chdir(tmp)
        saved_skip = os.environ.pop("FEIPI_SKIP_STOP_HOOK", None)
        # Set up active change
        (tmp / "tmp" / "active_change.json").write_text(
            json.dumps({
                "change_id": "test-change-003",
                "change_path": "openspec/changes/test-change-003/",
            }, indent=2),
            encoding="utf-8",
        )
        # Set up change directory with required files
        cdir = tmp / "openspec" / "changes" / "test-change-003"
        cdir.mkdir(parents=True)
        (cdir / "proposal.md").write_text("# Proposal\n", encoding="utf-8")
        (cdir / "design.md").write_text("# Design\n", encoding="utf-8")
        (cdir / "tasks.md").write_text("- [x] Task 1\n- [ ] Task 2\n", encoding="utf-8")
        # Set up evidence
        evdir = tmp / "tmp" / "task-evidence"
        evdir.mkdir(parents=True)
        (evdir / "test-change-003.jsonl").write_text(
            '{"ts":"2026-01-01T00:00:00Z","tool":"Edit","file_path":"CLAUDE.md","change_id":"test-change-003"}\n',
            encoding="utf-8",
        )
        exit_code, msgs = validate()
        os.chdir(saved_cwd)
        if saved_skip is not None:
            os.environ["FEIPI_SKIP_STOP_HOOK"] = saved_skip
        check("exit code is 0 (ALLOW)", exit_code == 0, f"exit={exit_code}")

        # --- Sub-test 4: emergency bypass -> ALWAYS ALLOW ---
        print("Sub-test 4: emergency bypass (FEIPI_SKIP_STOP_HOOK=1) -> ALWAYS ALLOW")
        os.chdir(tmp)
        os.environ["FEIPI_SKIP_STOP_HOOK"] = "1"
        # Even with broken state, should still allow
        # Remove active_change to make it the worst case
        (tmp / "tmp" / "active_change.json").unlink()
        exit_code, msgs = validate()
        os.chdir(saved_cwd)
        os.environ.pop("FEIPI_SKIP_STOP_HOOK", None)
        check("exit code is 0 (ALLOW)", exit_code == 0, f"exit={exit_code}")
        has_bypass_msg = any("EMERGENCY BYPASS" in m or "bypass" in m.lower() for m in msgs)
        check("message mentions bypass", has_bypass_msg,
              "messages: " + "; ".join(msgs[:2]))

        # --- Sub-test 5: protected changes + active change but missing files -> BLOCK ---
        print("Sub-test 5: protected changes + active change but missing required files -> BLOCK")
        os.chdir(tmp)
        saved_skip = os.environ.pop("FEIPI_SKIP_STOP_HOOK", None)
        # Re-create active change but with incomplete change dir
        (tmp / "tmp" / "active_change.json").write_text(
            json.dumps({
                "change_id": "test-change-005",
                "change_path": "openspec/changes/test-change-005/",
            }, indent=2),
            encoding="utf-8",
        )
        cdir5 = tmp / "openspec" / "changes" / "test-change-005"
        cdir5.mkdir(parents=True)
        # Only create proposal.md, leave out design.md and tasks.md
        (cdir5 / "proposal.md").write_text("# Proposal\n", encoding="utf-8")
        # No evidence either
        exit_code, msgs = validate()
        os.chdir(saved_cwd)
        if saved_skip is not None:
            os.environ["FEIPI_SKIP_STOP_HOOK"] = saved_skip
        check("exit code is 2 (BLOCK)", exit_code == EXIT_BLOCK, f"exit={exit_code}")
        has_block_msg = any("BLOCK" in m or "block" in m.lower() or "WARN" in m for m in msgs)
        check("message indicates incomplete", has_block_msg,
              "messages: " + "; ".join(msgs[:3]))

    # Summary
    passed_count = sum(1 for _, p, _ in results if p)
    total = len(results)
    all_pass = passed_count == total

    print(f"\n{'='*60}")
    print(f"self-test results: {passed_count}/{total} passed")
    print(f"{'='*60}")
    for name, passed, detail in results:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}" + (f" -- {detail}" if detail else ""))
    print(f"{'='*60}")

    return 0 if all_pass else 1


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Stop/SubagentStop hook: validate OpenSpec change completeness."
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run self-test suite and exit.",
    )
    args = parser.parse_args()

    if args.self_test:
        return _run_self_test()

    exit_code, messages = validate()
    for msg in messages:
        print(msg, file=sys.stderr if exit_code != 0 else sys.stdout)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
