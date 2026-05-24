#!/usr/bin/env python3
"""Stop hook runner for quality targets.

Reads tmp/agent_logs/current/changed-files.jsonl, computes required targets
via classify.required_quality_targets(), and runs run_quality_gate.py for each.

By default excludes session-detail (handled by stop_quality_gate.py).
Pass --include-session-detail to include it in the runner (used by stop.sh).

Usage:
    python3 scripts/quality/run_required_quality_gates.py
    python3 scripts/quality/run_required_quality_gates.py --change-id fix-xyz
    python3 scripts/quality/run_required_quality_gates.py --change-id fix-xyz --dry-run
    python3 scripts/quality/run_required_quality_gates.py --change-id fix-xyz --include-session-detail

Exit codes:
    0 — all targets PASS or no targets to run
    1 — at least one target gate failed
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

AGENT_LOG_DIR = REPO_ROOT / "tmp" / "agent_logs" / "current"
CHANGED_FILES = AGENT_LOG_DIR / "changed-files.jsonl"
SESSION_ID_FILE = AGENT_LOG_DIR / "session-id.txt"
QUALITY_DIR = REPO_ROOT / "tmp" / "quality"

# session-detail 由 stop_quality_gate.py 单独处理，默认排除
EXCLUDED_TARGETS = {"session-detail"}


def resolve_change_id(explicit: str | None) -> str:
    """Resolve change-id from args, env, or active-change file fallback."""
    if explicit:
        return explicit
    env = os.environ.get("ACTIVE_CHANGE_ID", "")
    if env:
        return env
    active_file = REPO_ROOT / "tmp" / "active-change"
    if active_file.exists():
        return active_file.read_text().strip()
    return "unknown"


def get_changed_files() -> list[str]:
    """Read changed files from tmp/agent_logs/current/changed-files.jsonl.

    Filters by session-id if session-id.txt exists.
    """
    session_id = None
    if SESSION_ID_FILE.exists():
        session_id = SESSION_ID_FILE.read_text().strip() or None

    if not CHANGED_FILES.exists():
        return []

    files: list[str] = []
    for line in CHANGED_FILES.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
            if session_id and record.get("sessionId") != session_id:
                continue
            f = record.get("file") or record.get("file_path")
            if f:
                files.append(f)
        except (json.JSONDecodeError, Exception):
            continue
    return files


def compute_required_targets(changed_files: list[str], excluded: set[str]) -> list[str]:
    """Compute required quality targets from changed files, applying exclusions."""
    from scripts.claude_hooks.classify import required_quality_targets

    all_targets = required_quality_targets(changed_files)
    return [t for t in all_targets if t not in excluded]


def run_gate(target: str, change_id: str) -> tuple[bool, str]:
    """Run run_quality_gate.py for a single target. Returns (passed, artifact_path)."""
    cmd = [
        "python3",
        str(REPO_ROOT / "scripts" / "quality" / "run_quality_gate.py"),
        "--target", target,
        "--change-id", change_id,
        "--changed-files", "auto",
    ]
    artifact_path = str(QUALITY_DIR / change_id / f"quality-gate-summary.{target}.json")

    try:
        proc = subprocess.run(
            cmd,
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=300,
        )
        output = (proc.stdout or "").strip()
        if proc.returncode != 0:
            return False, artifact_path
        # Verify artifact exists
        if not Path(artifact_path).exists():
            return False, artifact_path
        return True, artifact_path
    except subprocess.TimeoutExpired:
        return False, artifact_path
    except Exception as e:
        return False, artifact_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run required quality gates (excluding session-detail by default)")
    parser.add_argument("--change-id", default=None, help="Override change-id")
    parser.add_argument("--dry-run", action="store_true", help="Print what would run without executing")
    parser.add_argument("--include-session-detail", action="store_true",
                        help="Include session-detail in runner targets (default: excluded)")
    args = parser.parse_args()

    # Determine effective exclusions
    effective_excluded = set(EXCLUDED_TARGETS)
    if args.include_session_detail:
        effective_excluded.discard("session-detail")
        print("[run_required_quality_gates] --include-session-detail: session-detail will be executed by this runner", file=sys.stderr)
    else:
        print("[run_required_quality_gates] session-detail excluded (handled by stop_quality_gate.py)", file=sys.stderr)

    change_id = resolve_change_id(args.change_id)
    changed_files = get_changed_files()

    print(f"[run_required_quality_gates] change-id={change_id}", file=sys.stderr)
    print(f"[run_required_quality_gates] changed-files={CHANGED_FILES.relative_to(REPO_ROOT)}", file=sys.stderr)

    from scripts.claude_hooks.classify import required_quality_targets
    full_required = required_quality_targets(changed_files)

    # Targets actually executed after exclusions
    all_required = [t for t in full_required if t not in effective_excluded]
    skipped = [t for t in full_required if t in effective_excluded]

    print(f"[run_required_quality_gates] required targets: {', '.join(sorted(full_required)) if full_required else '(none)'}", file=sys.stderr)
    if skipped:
        print(f"[run_required_quality_gates] skipped targets (excluded): {', '.join(sorted(skipped))}", file=sys.stderr)

    if not changed_files:
        print("[run_required_quality_gates] no changed files, exit 0", file=sys.stderr)
        return 0

    if not all_required:
        print("[run_required_quality_gates] no required targets after exclusions, exit 0", file=sys.stderr)
        return 0

    if args.dry_run:
        for t in sorted(all_required):
            print(f"[run_required_quality_gates] would run target: {t}", file=sys.stderr)
        for t in sorted(effective_excluded & set(full_required)):
            print(f"[run_required_quality_gates] skip target handled elsewhere: {t}", file=sys.stderr)
        return 0

    blocked = False
    for target in sorted(all_required):
        print(f"[run_required_quality_gates] running target: {target}", file=sys.stderr)
        passed, artifact_path = run_gate(target, change_id)
        status_str = "PASS" if passed else "FAIL"
        print(
            f"[run_required_quality_gates] {status_str} target={target} artifact={artifact_path}",
            file=sys.stderr,
        )
        if not passed:
            blocked = True

    # Log skipped targets
    for t in sorted(effective_excluded & set(full_required)):
        print(f"[run_required_quality_gates] skip target handled elsewhere: {t}", file=sys.stderr)

    return 1 if blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
