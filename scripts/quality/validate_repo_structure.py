#!/usr/bin/env python3
"""Deterministic repo health gate: validate that command/skill/hook/spec
structure is properly installed.

Usage:
    python3 scripts/quality/validate_repo_structure.py

Exit codes:
    0  all checks pass
    1  one or more hard failures
    2  script error (invalid repo root, etc.)
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path.cwd().resolve()

# ---------------------------------------------------------------------------
# Check definitions
# ---------------------------------------------------------------------------

CHECKS: list[tuple[str, str, bool]] = []  # (name, error, soft=True/False)


def _check(name: str, condition: bool, error: str, hard: bool = True) -> None:
    CHECKS.append((name, condition, error, hard))


def _file_exists(rel: str) -> bool:
    return (REPO_ROOT / rel).is_file()


def _dir_exists(rel: str) -> bool:
    return (REPO_ROOT / rel).is_dir()


def _grep_in_file(rel: str, pattern: str) -> bool:
    p = REPO_ROOT / rel
    if not p.is_file():
        return False
    try:
        return pattern in p.read_text(encoding="utf-8")
    except OSError:
        return False


def _json_valid(rel: str) -> bool:
    p = REPO_ROOT / rel
    if not p.is_file():
        return False
    try:
        json.loads(p.read_text(encoding="utf-8"))
        return True
    except (json.JSONDecodeError, OSError):
        return False


# ---------------------------------------------------------------------------
# Validation logic
# ---------------------------------------------------------------------------


def run_checks() -> None:
    # 1. Change command
    _check(
        "change command exists",
        _file_exists(".claude/commands/change.md"),
        ".claude/commands/change.md is missing",
    )

    # 2. Change skill
    _check(
        "change skill exists",
        _file_exists(".claude/skills/change/SKILL.md"),
        ".claude/skills/change/SKILL.md is missing",
    )

    # 3. Hook scripts
    for hook_file in [
        ".claude/hooks/pre_tool_guard.sh",
        ".claude/hooks/post_tool_guard.sh",
        ".claude/hooks/stop_check.sh",
    ]:
        _check(
            f"hook script: {hook_file}",
            _file_exists(hook_file),
            f"{hook_file} is missing",
        )

    # 4. Agent hooks
    for agent_hook in [
        "scripts/agent_hooks/guard_active_openspec_change.py",
        "scripts/agent_hooks/log_change_evidence.py",
        "scripts/agent_hooks/stop_validate_change.py",
        "scripts/agent_hooks/inject_session_context.py",
    ]:
        _check(
            f"agent hook: {agent_hook}",
            _file_exists(agent_hook),
            f"{agent_hook} is missing",
        )

    # 5. Settings JSON wiring
    settings_ok = _json_valid(".claude/settings.json")
    _check(
        "settings.json is valid JSON",
        settings_ok,
        ".claude/settings.json is missing or invalid JSON",
        hard=True,
    )
    if settings_ok:
        _check(
            "settings has PreToolUse hooks",
            _grep_in_file(".claude/settings.json", "PreToolUse"),
            ".claude/settings.json missing PreToolUse hooks",
        )
        _check(
            "settings has PostToolUse hooks",
            _grep_in_file(".claude/settings.json", "PostToolUse"),
            ".claude/settings.json missing PostToolUse hooks",
        )
        _check(
            "settings has Stop hook",
            _grep_in_file(".claude/settings.json", "Stop"),
            ".claude/settings.json missing Stop hook",
        )
        _check(
            "settings has SessionStart hook",
            _grep_in_file(".claude/settings.json", "SessionStart"),
            ".claude/settings.json missing SessionStart hook",
        )

    # 6. Default agents
    for agent in ["openspec-planner.md", "implementer.md", "qa-verifier.md"]:
        _check(
            f"default agent: {agent}",
            _file_exists(f".claude/agents/{agent}"),
            f".claude/agents/{agent} is missing",
        )

    # 7. Active change references in agents
    for agent in ["openspec-planner.md", "implementer.md", "qa-verifier.md"]:
        path = f".claude/agents/{agent}"
        _check(
            f"{agent} mentions active_change",
            _grep_in_file(path, "active_change"),
            f"{path} does not mention active_change",
            hard=False,
        )

    # 8. OpenSpec config and schema
    _check(
        "openspec config.yaml",
        _file_exists("openspec/config.yaml"),
        "openspec/config.yaml is missing",
    )

    # 9. Harness validation scripts
    for script in [
        "scripts/harness/validate_harness_structure.py",
        "scripts/harness/validate_openspec_layout.py",
        "scripts/harness/check_no_unfinished_markers.py",
        "scripts/harness/validate_task_files.py",
    ]:
        _check(
            f"harness script: {script}",
            _file_exists(script),
            f"{script} is missing",
        )

    # 10. Quality scripts
    _check(
        "quality: validate_repo_structure.py (self)",
        _file_exists("scripts/quality/validate_repo_structure.py"),
        "scripts/quality/validate_repo_structure.py is missing",
    )


def _print_results() -> int:
    hard_fail = 0
    soft_fail = 0
    total = 0

    print(f"\n{'='*60}")
    print(f"repo structure validation -- {REPO_ROOT}")
    print(f"{'='*60}")

    for name, passed, error, hard in CHECKS:
        total += 1
        tag = "PASS" if passed else ("FAIL" if hard else "WARN")
        if not passed:
            if hard:
                hard_fail += 1
            else:
                soft_fail += 1
            print(f"  [{tag}] {name}: {error}")
        else:
            print(f"  [{tag}] {name}")

    print(f"{'='*60}")
    print(f"  {total} checks, {hard_fail} hard failures, {soft_fail} warnings")
    print(f"{'='*60}")

    return 1 if hard_fail > 0 else 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    run_checks()
    return _print_results()


if __name__ == "__main__":
    sys.exit(main())
