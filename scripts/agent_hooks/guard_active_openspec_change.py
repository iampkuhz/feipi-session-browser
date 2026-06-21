#!/usr/bin/env python3
"""PreToolUse hook: block protected writes without an active OpenSpec change.

Usage:
    python3 scripts/agent_hooks/guard_active_openspec_change.py <target_file>
    python3 scripts/agent_hooks/guard_active_openspec_change.py --self-test

Exit codes:
    0  ALLOW  - edit is permitted
    1  BLOCK  - edit is blocked (error on stderr)
    2  ERROR  - internal/script error (self-test failure, bad args, etc.)
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Protected root patterns.  A target whose resolved path starts with any of
# these is considered "protected" and requires an active OpenSpec change.
PROTECTED_ROOTS = [
    'CLAUDE.md',
    'AGENTS.md',
    'openspec',
    '.claude',
    '.codex',
    '.qoder',
    'scripts',
    'harness',
    'src',
]

# Paths that are part of *creating* a change - always allowed even if under
# openspec/changes/ or tmp/.
CREATION_EXCEPTIONS = [
    'openspec/changes',
    'tmp/active_change.json',
]

ACTIVE_CHANGE_FILE = 'tmp/active_change.json'
REQUIRED_CHANGE_FILES = ('proposal.md', 'design.md', 'tasks.md')

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def resolve_target(target: str, repo_root: Path) -> Path:
    """Return the absolute path for a hook target.

    Args:
        target: File path received from the hook payload or CLI.
        repo_root: Repository root used to resolve relative targets.

    Returns:
        Absolute resolved target path.
    """
    p = Path(target)
    if not p.is_absolute():
        p = repo_root / p
    return p.resolve()


def is_protected(target_resolved: Path, repo_root: Path) -> bool:
    """Check whether a target is inside a protected root.

    Args:
        target_resolved: Absolute path to evaluate.
        repo_root: Repository root containing the protected roots.

    Returns:
        True when the target requires an active OpenSpec change.
    """
    # Exact match for repo-level files (CLAUDE.md, AGENTS.md)
    for root_name in PROTECTED_ROOTS:
        candidate = repo_root / root_name
        candidate = candidate.resolve()
        if target_resolved == candidate:
            return True
        if candidate.is_dir() and (str(target_resolved) + '/').startswith(str(candidate) + '/'):
            return True
    return False


def is_creation_exception(target_resolved: Path, repo_root: Path) -> bool:
    """Check whether a protected target is allowed during change creation.

    Args:
        target_resolved: Absolute path to evaluate.
        repo_root: Repository root containing the exception paths.

    Returns:
        True when the target is an OpenSpec creation exception.
    """
    for exc_rel in CREATION_EXCEPTIONS:
        candidate = (repo_root / exc_rel).resolve()
        if (str(target_resolved) + '/').startswith(str(candidate) + '/'):
            return True
        if target_resolved == candidate:
            return True
    return False


def check_active_change(repo_root: Path) -> tuple[bool, str]:  # noqa: PLR0911
    """Validate that an active OpenSpec change exists and is complete.

    Args:
        repo_root: Repository root where active change metadata is stored.

    Returns:
        Tuple of success flag and human-readable status or blocking message.
    """
    active_change_path = repo_root / ACTIVE_CHANGE_FILE
    if not active_change_path.exists():
        return False, (
            'BLOCKED: No active OpenSpec change (tmp/active_change.json not found).\n'
            'Create a change with /change before editing protected files.'
        )

    # Validate JSON
    try:
        data = json.loads(active_change_path.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return False, (
            f'BLOCKED: tmp/active_change.json is not valid JSON: {exc}\n'
            'Fix or recreate the active change file.'
        )

    change_id = data.get('change_id', '')
    if not change_id:
        return False, (
            "BLOCKED: tmp/active_change.json is missing 'change_id'.\n"
            'Recreate the active change file with a valid change_id.'
        )

    # Check that a matching non-archive directory exists under openspec/changes/
    changes_dir = repo_root / 'openspec' / 'changes'
    if not changes_dir.is_dir():
        return False, (
            f"BLOCKED: openspec/changes/ directory is missing.\nCannot verify change '{change_id}'."
        )

    matching = [
        d
        for d in changes_dir.iterdir()
        if d.is_dir() and d.name != 'archive' and d.name == change_id
    ]
    if not matching:
        return False, (
            f"BLOCKED: No non-archive directory 'openspec/changes/{change_id}/' found.\n"
            f"active_change.json references '{change_id}', but no matching change "
            "directory exists.\n"
            'Create the change or fix active_change.json.'
        )

    change_dir = matching[0]
    missing = [name for name in REQUIRED_CHANGE_FILES if not (change_dir / name).is_file()]
    if missing:
        return False, (
            f"BLOCKED: Active change '{change_id}' is incomplete; missing "
            f'{", ".join(missing)}.\n'
            f'Before editing protected files, complete openspec/changes/{change_id}/ '
            'or run scripts/openspec/create_active_change.py with the intended change id.'
        )

    return True, f"Active change '{change_id}' verified."


# ---------------------------------------------------------------------------
# Main guard logic
# ---------------------------------------------------------------------------


def guard(target: str, repo_root: Path | None = None) -> int:
    """Run the protected-edit guard for one target path.

    Args:
        target: File path requested by the editing tool.
        repo_root: Optional repository root override for self-tests.

    Returns:
        Process-style exit code where 0 allows and 1 blocks.
    """
    if repo_root is None:
        repo_root = Path.cwd()
    repo_root = repo_root.resolve()

    target_resolved = resolve_target(target, repo_root)

    # Creation exceptions are always allowed.
    if is_creation_exception(target_resolved, repo_root):
        return 0

    # Non-protected files are always allowed.
    if not is_protected(target_resolved, repo_root):
        return 0

    # Protected file - require active change.
    ok, message = check_active_change(repo_root)
    if not ok:
        print(message, file=sys.stderr)
        return 1

    return 0


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------


def run_self_test() -> int:  # noqa: PLR0915
    """Run the guard self-test suite in a temporary repository.

    Returns:
        Process exit code where 0 means all self-tests passed.
    """
    results: list[tuple[str, bool, str]] = []

    with tempfile.TemporaryDirectory(prefix='guard_self_test_') as tmpdir:
        tmp = Path(tmpdir)

        # -- Build a minimal fake repo --
        (tmp / 'openspec' / 'changes' / 'archive').mkdir(parents=True)
        (tmp / 'tmp').mkdir(parents=True)
        for r in ['scripts', 'src']:
            (tmp / r).mkdir(parents=True)
        (tmp / 'CLAUDE.md').touch()
        (tmp / 'AGENTS.md').touch()
        (tmp / 'non-protected.txt').touch()

        # --- Sub-test A: No active_change.json -> protected file should BLOCK ---
        target_a = str(tmp / 'CLAUDE.md')
        ret_a = guard(target_a, repo_root=tmp)
        results.append(
            ('no_active_change -> BLOCK protected file', ret_a == 1, f'exit={ret_a} (expected 1)')
        )

        # --- Sub-test B: Valid active_change.json + matching change dir -> ALLOW ---
        active_change_data = {
            'change_id': 'test-change',
            'change_path': 'openspec/changes/test-change/',
        }
        (tmp / ACTIVE_CHANGE_FILE).write_text(
            json.dumps(active_change_data, indent=2), encoding='utf-8'
        )
        change_b = tmp / 'openspec' / 'changes' / 'test-change'
        change_b.mkdir(parents=True)
        for required in REQUIRED_CHANGE_FILES:
            (change_b / required).write_text(f'# {required}\n', encoding='utf-8')

        target_b = str(tmp / 'src' / 'main.py')
        ret_b = guard(target_b, repo_root=tmp)
        results.append(
            (
                'valid_active_change -> ALLOW protected file',
                ret_b == 0,
                f'exit={ret_b} (expected 0)',
            )
        )

        # --- Sub-test C: Non-protected file is always ALLOW ---
        target_c = str(tmp / 'non-protected.txt')
        ret_c = guard(target_c, repo_root=tmp)
        results.append(('non_protected_file -> ALLOW', ret_c == 0, f'exit={ret_c} (expected 0)'))

        # --- Sub-test D: Non-protected external file (e.g. /tmp/…) -> ALLOW ---
        target_d = '/tmp/guard_test_file.txt'
        ret_d = guard(target_d, repo_root=tmp)
        results.append(('external_file -> ALLOW', ret_d == 0, f'exit={ret_d} (expected 0)'))

        # --- Sub-test E: Active change with non-matching dir -> BLOCK ---
        (tmp / ACTIVE_CHANGE_FILE).write_text(
            json.dumps({'change_id': 'nonexistent-change'}, indent=2), encoding='utf-8'
        )
        target_e = str(tmp / 'CLAUDE.md')
        ret_e = guard(target_e, repo_root=tmp)
        results.append(
            (
                'mismatched_change_id -> BLOCK protected file',
                ret_e == 1,
                f'exit={ret_e} (expected 1)',
            )
        )

        # --- Sub-test F: Invalid JSON in active_change.json -> BLOCK ---
        (tmp / ACTIVE_CHANGE_FILE).write_text('not json {{{', encoding='utf-8')
        target_f = str(tmp / 'scripts' / 'test.py')
        ret_f = guard(target_f, repo_root=tmp)
        results.append(
            ('invalid_json -> BLOCK protected file', ret_f == 1, f'exit={ret_f} (expected 1)')
        )

        # --- Sub-test G: Creation exception (writing to openspec/changes/) -> ALLOW ---
        (tmp / ACTIVE_CHANGE_FILE).write_text(
            json.dumps({'change_id': 'test-change'}, indent=2), encoding='utf-8'
        )
        target_g = str(tmp / 'openspec' / 'changes' / 'test-change' / 'specs' / 'test.md')
        ret_g = guard(target_g, repo_root=tmp)
        results.append(
            (
                'creation_exception -> ALLOW under openspec/changes/',
                ret_g == 0,
                f'exit={ret_g} (expected 0)',
            )
        )

        # --- Sub-test H: Creation exception (tmp/active_change.json) -> ALLOW ---
        target_h = str(tmp / 'tmp' / 'active_change.json')
        ret_h = guard(target_h, repo_root=tmp)
        results.append(
            (
                'creation_exception -> ALLOW tmp/active_change.json',
                ret_h == 0,
                f'exit={ret_h} (expected 0)',
            )
        )

    # Report
    all_pass = True
    print(f'\n{"=" * 60}')
    print('self-test results')
    print(f'{"=" * 60}')
    for name, passed, detail in results:
        status = 'PASS' if passed else 'FAIL'
        if not passed:
            all_pass = False
        print(f'  [{status}] {name} - {detail}')
    print(f'{"=" * 60}')
    print(f'  {sum(1 for _, p, _ in results if p)}/{len(results)} passed')
    print(f'{"=" * 60}')

    return 0 if all_pass else 1


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    """Parse CLI arguments and run the active-change guard.

    Returns:
        Process exit code for the CLI invocation.
    """
    parser = argparse.ArgumentParser(
        description='PreToolUse hook: block protected writes without active OpenSpec change.'
    )
    parser.add_argument(
        'target',
        nargs='?',
        default=None,
        help='Target file path to check.',
    )
    parser.add_argument(
        '--self-test',
        action='store_true',
        help='Run self-tests and exit.',
    )
    args = parser.parse_args()

    if args.self_test:
        return run_self_test()

    if not args.target:
        # No target provided; allow (guard is not applicable without a target).
        return 0

    ret = guard(args.target)
    if ret != 0:
        return ret
    return 0


if __name__ == '__main__':
    sys.exit(main())
