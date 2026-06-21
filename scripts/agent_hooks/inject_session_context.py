#!/usr/bin/env python3
"""Inject concise workflow context into each agent session.

SessionStart and SubagentStart hooks call this script so every session knows the
current OpenSpec change status, protected-edit rule, and evidence path.

Usage:
    python3 scripts/agent_hooks/inject_session_context.py
    python3 scripts/agent_hooks/inject_session_context.py --self-test

The script prints context to stdout.  A Stop hook can also call it to
re-verify state before finishing.

Exit codes:
    0  success
    1  self-test failure
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

PROTECTED_ROOTS = [
    'CLAUDE.md',
    'AGENTS.md',
    'openspec/',
    '.claude/',
    '.codex/',
    '.qoder/',
    'scripts/',
    'harness/',
    'src/',
]

ACTIVE_CHANGE_FILE = Path('tmp/active_change.json')
EVIDENCE_DIR = Path('tmp/task-evidence')
MAX_CONTEXT_LINES = 20

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _repo_root() -> Path:
    """Return the repository root assumed by the hook process.

    Returns:
        Absolute path to the current working directory.
    """
    return Path.cwd().resolve()


def load_active_change() -> dict | None:
    """Load the active OpenSpec change metadata for context injection.

    Returns:
        Parsed active change metadata, or None when unavailable.
    """
    p = _repo_root() / ACTIVE_CHANGE_FILE
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, OSError):
        return None


def _change_dir(change_id: str) -> Path:
    """Return the OpenSpec change directory path for a change id.

    Args:
        change_id: Active OpenSpec change identifier.

    Returns:
        Absolute path to the change directory.
    """
    return _repo_root() / 'openspec' / 'changes' / change_id


def _evidence_file(change_id: str) -> Path:
    """Return the evidence JSONL path for a change id.

    Args:
        change_id: Active OpenSpec change identifier.

    Returns:
        Absolute path to the change evidence file.
    """
    return _repo_root() / EVIDENCE_DIR / f'{change_id}.jsonl'


def _count_evidence_entries(change_id: str) -> int:
    """Count non-empty evidence records for the active change summary.

    Args:
        change_id: Active OpenSpec change identifier.

    Returns:
        Number of non-empty evidence lines.
    """
    ef = _evidence_file(change_id)
    if not ef.is_file():
        return 0
    try:
        lines = ef.read_text(encoding='utf-8').strip().splitlines()
        return len([line for line in lines if line.strip()])
    except OSError:
        return 0


def _count_completed_tasks(change_id: str) -> int:
    """Count completed tasks in the active change task list.

    Args:
        change_id: Active OpenSpec change identifier.

    Returns:
        Number of checked markdown task items.
    """
    tasks = _change_dir(change_id) / 'tasks.md'
    if not tasks.is_file():
        return 0
    content = tasks.read_text(encoding='utf-8')
    count = 0
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith('- [x]') or stripped.startswith('* [x]'):
            count += 1
    return count


def _count_total_tasks(change_id: str) -> int:
    """Count all markdown task items in the active change task list.

    Args:
        change_id: Active OpenSpec change identifier.

    Returns:
        Number of checked and unchecked markdown task items.
    """
    tasks = _change_dir(change_id) / 'tasks.md'
    if not tasks.is_file():
        return 0
    content = tasks.read_text(encoding='utf-8')
    count = 0
    for line in content.splitlines():
        stripped = line.strip()
        if (
            stripped.startswith('- [x]')
            or stripped.startswith('- [ ]')
            or stripped.startswith('* [x]')
            or stripped.startswith('* [ ]')
        ):
            count += 1
    return count


def _has_uncommitted_changes() -> bool:
    """Return whether protected roots have staged or unstaged changes.

    Returns:
        True when git reports changes under protected roots.
    """
    root = _repo_root()
    try:
        result = subprocess.run(
            ['git', 'status', '--short', *PROTECTED_ROOTS],
            capture_output=True,
            check=False,
            text=True,
            cwd=root,
            timeout=10,
        )
        return bool(result.stdout.strip())
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return True


# ---------------------------------------------------------------------------
# Context injection
# ---------------------------------------------------------------------------


def inject_context() -> str:
    """Build the session context block consumed by agents.

    Returns:
        Newline-delimited context summary for stdout.
    """
    lines: list[str] = []
    root = _repo_root()
    lines.append(f'[session-context] repo: {root}')

    active = load_active_change()
    if active is None:
        lines.append('[session-context] active change: NONE')
        lines.append(
            '[session-context] NOTE: protected edits are blocked until '
            'you run /change to create an active OpenSpec change.'
        )
        lines.append(f'[session-context] evidence path: {EVIDENCE_DIR}/<change-id>.jsonl')
        lines.append('[session-context] protected roots: ' + ', '.join(PROTECTED_ROOTS))
    else:
        cid = active.get('change_id', 'unknown')
        cpath = active.get('change_path', f'openspec/changes/{cid}/')
        lines.append(f'[session-context] active change: {cid} ({cpath})')

        cd = _change_dir(cid)
        has_dir = cd.is_dir()
        lines.append(f'[session-context] change dir exists: {has_dir}')

        if has_dir:
            proposal = (cd / 'proposal.md').is_file()
            design = (cd / 'design.md').is_file()
            tasks = (cd / 'tasks.md').is_file()
            lines.append(
                f'[session-context] required files: '
                f'proposal.md={proposal}, design.md={design}, tasks.md={tasks}'
            )
            total = _count_total_tasks(cid)
            done = _count_completed_tasks(cid)
            lines.append(f'[session-context] tasks: {done}/{total} completed')

        ev_count = _count_evidence_entries(cid)
        lines.append(f'[session-context] evidence entries: {ev_count}')
        lines.append(f'[session-context] evidence path: {_evidence_file(cid)}')
        lines.append('[session-context] protected roots: ' + ', '.join(PROTECTED_ROOTS))

        dirty = _has_uncommitted_changes()
        lines.append(f'[session-context] uncommitted protected changes: {dirty}')

    lines.append('[session-context] default workflow: use /change for all feature work')
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------


def _run_self_test() -> int:  # noqa: PLR0915
    """Validate the injector in a temporary git repository.

    Sub-tests:
      1. No active change -> output says "NONE" and warns about blocked edits.
      2. Active change present -> output includes change_id, evidence path, etc.
      3. Active change with partial data -> still reports gracefully.
      4. Output format is concise (no huge dumps).

    Returns:
        Process exit code where 0 means all self-tests passed.
    """
    results: list[tuple[str, bool, str]] = []

    def check(name: str, condition: bool, detail: str = '') -> None:
        """Record one self-test assertion and print its short status.

        Args:
            name: Human-readable assertion name.
            condition: Whether the assertion passed.
            detail: Optional diagnostic detail for failures or counters.
        """
        passed = condition
        status = 'PASS' if passed else 'FAIL'
        results.append((name, passed, detail))
        print(f'  [{status}] {name}' + (f' -- {detail}' if detail else ''))

    with tempfile.TemporaryDirectory(prefix='inject_ctx_test_') as tmpdir:
        tmp = Path(tmpdir)

        # -- Minimal git repo --
        subprocess.run(['git', 'init', '-q', str(tmp)], check=True, capture_output=True)
        subprocess.run(
            ['git', 'config', 'user.email', 'test@test.com'],
            cwd=tmp,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ['git', 'config', 'user.name', 'Test'],
            cwd=tmp,
            check=True,
            capture_output=True,
        )
        for p in [tmp / 'CLAUDE.md', tmp / 'README.md']:
            p.write_text('# test\n', encoding='utf-8')
        (tmp / 'openspec' / 'changes' / 'archive').mkdir(parents=True)
        (tmp / 'tmp').mkdir(parents=True)
        (tmp / 'src').mkdir(parents=True)
        subprocess.run(['git', 'add', '.'], cwd=tmp, check=True, capture_output=True)
        subprocess.run(
            ['git', 'commit', '-m', 'initial', '-q'],
            cwd=tmp,
            check=True,
            capture_output=True,
        )

        # --- Sub-test 1: no active change ---
        print('Sub-test 1: no active change -> says NONE + blocked warning')
        saved_cwd = Path.cwd()
        os.chdir(tmp)
        output = inject_context()
        os.chdir(saved_cwd)
        check("contains 'NONE'", 'NONE' in output)
        check('mentions blocked edits', 'blocked' in output.lower() or 'blocked' in output)
        check('mentions /change', '/change' in output)

        # --- Sub-test 2: active change present ---
        print('Sub-test 2: active change present -> reports change_id + evidence path')
        os.chdir(tmp)
        (tmp / 'tmp' / 'active_change.json').write_text(
            json.dumps(
                {
                    'change_id': 'inject-test',
                    'change_path': 'openspec/changes/inject-test/',
                }
            ),
            encoding='utf-8',
        )
        cdir = tmp / 'openspec' / 'changes' / 'inject-test'
        cdir.mkdir()
        (cdir / 'proposal.md').write_text('# Proposal\n', encoding='utf-8')
        (cdir / 'design.md').write_text('# Design\n', encoding='utf-8')
        (cdir / 'tasks.md').write_text(
            '- [x] Setup\n- [ ] Implement\n',
            encoding='utf-8',
        )
        evdir = tmp / 'tmp' / 'task-evidence'
        evdir.mkdir()
        (evdir / 'inject-test.jsonl').write_text(
            '{"ts":"2026-01-01T00:00:00Z","tool":"Edit","file_path":"src/x.py","change_id":"inject-test"}\n',
            encoding='utf-8',
        )
        output = inject_context()
        os.chdir(saved_cwd)
        check('contains change_id', 'inject-test' in output)
        check('mentions evidence path', 'evidence path' in output.lower())
        check('mentions tasks progress', 'tasks:' in output.lower())

        # --- Sub-test 3: active change with partial data (no evidence, no tasks.md) ---
        print('Sub-test 3: partial active change -> reports gracefully')
        os.chdir(tmp)
        (tmp / 'tmp' / 'active_change.json').write_text(
            json.dumps(
                {
                    'change_id': 'partial-test',
                    'change_path': 'openspec/changes/partial-test/',
                }
            ),
            encoding='utf-8',
        )
        cdir3 = tmp / 'openspec' / 'changes' / 'partial-test'
        cdir3.mkdir()
        (cdir3 / 'proposal.md').write_text('# Proposal\n', encoding='utf-8')
        # No design.md, no tasks.md, no evidence
        output = inject_context()
        os.chdir(saved_cwd)
        check('contains change_id', 'partial-test' in output)
        check('reports missing files', 'design.md=False' in output or 'tasks.md=False' in output)
        check('reports zero evidence', 'evidence entries: 0' in output)

        # --- Sub-test 4: output is concise ---
        print('Sub-test 4: output is concise (under 20 lines)')
        os.chdir(tmp)
        output = inject_context()
        os.chdir(saved_cwd)
        line_count = len(output.strip().splitlines())
        check(
            f'line count <= {MAX_CONTEXT_LINES} (got {line_count})',
            line_count <= MAX_CONTEXT_LINES,
            f'lines={line_count}',
        )

    # Summary
    passed_count = sum(1 for _, p, _ in results if p)
    total = len(results)
    all_pass = passed_count == total

    print(f'\n{"=" * 60}')
    print(f'self-test results: {passed_count}/{total} passed')
    print(f'{"=" * 60}')
    for name, passed, detail in results:
        status = 'PASS' if passed else 'FAIL'
        print(f'  [{status}] {name}' + (f' -- {detail}' if detail else ''))
    print(f'{"=" * 60}')

    return 0 if all_pass else 1


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    """Parse CLI arguments and print the current session context.

    Returns:
        Process exit code for the CLI invocation.
    """
    parser = argparse.ArgumentParser(
        description='SessionStart/SubagentStart hook: inject workflow context.'
    )
    parser.add_argument(
        '--self-test',
        action='store_true',
        help='Run self-test suite and exit.',
    )
    args = parser.parse_args()

    if args.self_test:
        return _run_self_test()

    print(inject_context())
    return 0


if __name__ == '__main__':
    sys.exit(main())
