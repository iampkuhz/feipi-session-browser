#!/usr/bin/env python3
"""Stop hook runner for quality targets.

Reads tmp/agent_logs/current/changed-files.jsonl, computes required targets
via classify.required_quality_targets(), and runs the full required gate
baseline for each target.

By default excludes session-detail (handled by stop_quality_gate.py).
Pass --include-session-detail to include it in the runner (used by stop.sh).

Usage:
    python3 scripts/quality/run_required_quality_gates.py
    python3 scripts/quality/run_required_quality_gates.py --change-id fix-xyz
    python3 scripts/quality/run_required_quality_gates.py --change-id fix-xyz --dry-run
    python3 scripts/quality/run_required_quality_gates.py --change-id fix-xyz \
--include-session-detail

Exit codes:
    0 — all targets PASS or no targets to run
    1 — at least one target gate failed
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

required_quality_targets = importlib.import_module(
    'scripts.claude_hooks.classify'
).required_quality_targets

AGENT_LOG_DIR = REPO_ROOT / 'tmp' / 'agent_logs' / 'current'
CHANGED_FILES = AGENT_LOG_DIR / 'changed-files.jsonl'
SESSION_ID_FILE = AGENT_LOG_DIR / 'session-id.txt'
QUALITY_DIR = REPO_ROOT / 'tmp' / 'quality'

# session-detail 由 stop_quality_gate.py 单独处理, 默认排除
EXCLUDED_TARGETS = {'session-detail'}


def resolve_change_id(explicit: str | None) -> str:
    """Resolve change-id from args, env, or tmp/active_change.json.

    Args:
        explicit: Input value for explicit.

    Returns:
        Computed result.
    """
    if explicit:
        return explicit
    env = os.environ.get('ACTIVE_CHANGE_ID', '')
    if env:
        return env
    active_change = REPO_ROOT / 'tmp' / 'active_change.json'
    if active_change.exists():
        try:
            data = json.loads(active_change.read_text(encoding='utf-8'))
            cid = data.get('change_id', '')
            if cid:
                return cid
        except (json.JSONDecodeError, OSError):
            pass
    return 'unknown'


def get_changed_files() -> list[str]:
    """Read changed files from tmp/agent_logs/current/changed-files.jsonl.

    Returns:
        Computed result.
    """
    session_id = None
    if SESSION_ID_FILE.exists():
        session_id = SESSION_ID_FILE.read_text().strip() or None

    if not CHANGED_FILES.exists():
        return []

    files: list[str] = []
    for raw_line in CHANGED_FILES.read_text(encoding='utf-8').splitlines():
        stripped_line = raw_line.strip()
        if not stripped_line:
            continue
        try:
            record = json.loads(stripped_line)
            if session_id and record.get('sessionId') != session_id:
                continue
            f = record.get('file') or record.get('file_path')
            if f:
                files.append(f)
        except (json.JSONDecodeError, Exception):
            continue
    return files


def compute_required_targets(changed_files: list[str], excluded: set[str]) -> list[str]:
    """Compute required quality targets from changed files, applying exclusions.

    Args:
        changed_files: Input value for changed_files.
        excluded: Input value for excluded.

    Returns:
        Computed result.
    """
    all_targets = required_quality_targets(changed_files)
    return [t for t in all_targets if t not in excluded]


def run_gate(
    target: str,
    change_id: str,
    changed_files: list[str] | None = None,
) -> tuple[bool, str]:
    """Run run_quality_gate.py for a single target. Returns (passed, artifact_path).

    Args:
        target: Input value for target.
        change_id: Input value for change_id.
        changed_files: Input value for changed_files.

    Returns:
        Computed result.
    """
    cmd = [
        sys.executable,
        str(REPO_ROOT / 'scripts' / 'quality' / 'run_quality_gate.py'),
        '--target',
        target,
        '--change-id',
        change_id,
    ]
    artifact_path = str(QUALITY_DIR / change_id / f'quality-gate-summary.{target}.json')

    try:
        env = os.environ.copy()
        # changed_files selects required targets in this runner. Do not forward
        # it into target execution; each selected target must run its full
        # baseline instead of per-file pruning.
        env.pop('QUALITY_CHANGED_FILES', None)
        proc = subprocess.run(
            cmd,
            cwd=REPO_ROOT,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
            timeout=300,
        )
        if proc.returncode != 0:
            return False, artifact_path
        # Verify artifact exists
        if not Path(artifact_path).exists():
            return False, artifact_path
        return True, artifact_path
    except subprocess.TimeoutExpired:
        return False, artifact_path
    except Exception:
        return False, artifact_path


def main() -> int:
    """Parse CLI options and run required quality targets.

    Returns:
        Computed result.
    """
    parser = argparse.ArgumentParser(
        description='Run required quality gates (excluding session-detail by default)'
    )
    parser.add_argument('--change-id', default=None, help='Override change-id')
    parser.add_argument(
        '--dry-run', action='store_true', help='Print what would run without executing'
    )
    parser.add_argument(
        '--include-session-detail',
        action='store_true',
        help='Include session-detail in runner targets (default: excluded)',
    )
    parser.add_argument(
        '--changed-files',
        default=None,
        help=(
            'JSON array of changed file paths used only to select quality targets. '
            'Target gates always run the full baseline.'
        ),
    )
    args = parser.parse_args()

    # Determine effective exclusions
    effective_excluded = set(EXCLUDED_TARGETS)
    if args.include_session_detail:
        effective_excluded.discard('session-detail')
        print(
            '[run_required_quality_gates] --include-session-detail: '
            'session-detail will be executed by this runner',
            file=sys.stderr,
        )
    else:
        print(
            '[run_required_quality_gates] session-detail excluded '
            '(handled by stop_quality_gate.py)',
            file=sys.stderr,
        )

    change_id = resolve_change_id(args.change_id)
    changed_files = json.loads(args.changed_files) if args.changed_files else get_changed_files()

    print(f'[run_required_quality_gates] change-id={change_id}', file=sys.stderr)
    print(
        f'[run_required_quality_gates] changed-files={CHANGED_FILES.relative_to(REPO_ROOT)}',
        file=sys.stderr,
    )

    full_required = required_quality_targets(changed_files)

    # Targets actually executed after exclusions
    all_required = [t for t in full_required if t not in effective_excluded]
    excluded = [t for t in full_required if t in effective_excluded]

    print(
        '[run_required_quality_gates] required targets: '
        f'{", ".join(sorted(full_required)) if full_required else "(none)"}',
        file=sys.stderr,
    )
    if excluded:
        print(
            '[run_required_quality_gates] excluded targets (handled elsewhere): '
            f'{", ".join(sorted(excluded))}',
            file=sys.stderr,
        )

    if not changed_files:
        print(
            '[run_required_quality_gates] no changed files; quality targets not triggered',
            file=sys.stderr,
        )
        return 0

    if not all_required:
        print(
            '[run_required_quality_gates] no required targets after exclusions; '
            'selected targets not triggered',
            file=sys.stderr,
        )
        return 0

    if args.dry_run:
        for t in sorted(all_required):
            print(f'[run_required_quality_gates] would run target: {t}', file=sys.stderr)
        for t in sorted(effective_excluded & set(full_required)):
            print(
                f'[run_required_quality_gates] excluded target handled elsewhere: {t}',
                file=sys.stderr,
            )
        return 0

    blocked = False
    for target in sorted(all_required):
        print(f'[run_required_quality_gates] running target: {target}', file=sys.stderr)
        passed, artifact_path = run_gate(target, change_id)
        status_str = 'PASS' if passed else 'FAIL/BLOCKED'
        print(
            f'[run_required_quality_gates] {status_str} target={target} artifact={artifact_path}',
            file=sys.stderr,
        )
        if not passed:
            blocked = True

    # Log excluded targets. These were selected by mapping but are handled by a
    # separate runner; they are not test skips.
    for t in sorted(effective_excluded & set(full_required)):
        print(
            f'[run_required_quality_gates] excluded target handled elsewhere: {t}', file=sys.stderr
        )

    return 1 if blocked else 0


if __name__ == '__main__':
    raise SystemExit(main())
