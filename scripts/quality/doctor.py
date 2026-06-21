#!/usr/bin/env python3
"""Doctor: single-entry health check for spec+harness standard installation.

Runs all validators, hook self-tests, settings verification, and gitignore
checks in one pass. Prints a concise summary table.

Usage:
    python3 scripts/quality/doctor.py

Exit codes:
    0  all hard gates pass
    1  one or more hard failures
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path.cwd().resolve()

# ---------------------------------------------------------------------------
# Check definitions
# ---------------------------------------------------------------------------

CHECKS: list[tuple[str, str, int]] = []  # (name, cmd_or_note, exit_code)


def _run(name: str, cmd: str) -> int:
    """Run a command and record the result.

    Args:
        name: Input value for name.
        cmd: Input value for cmd.

    Returns:
        Computed result.
    """
    print(f'  [{name}] running ...', end=' ')
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            check=False,
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            timeout=30,
        )
        status = 'PASS' if result.returncode == 0 else 'FAIL'
        print(f'{status} (exit={result.returncode})')
        CHECKS.append((name, cmd, result.returncode))
        return result.returncode
    except subprocess.TimeoutExpired:
        print('FAIL (timeout)')
        CHECKS.append((name, cmd, 1))
        return 1
    except Exception as exc:
        print(f'FAIL ({exc})')
        CHECKS.append((name, cmd, 2))
        return 2


def _note(name: str, note: str) -> None:
    """Record a non-blocking doctor observation as a passing check.

    Args:
        name: Input value for name.
        note: Input value for note.
    """
    print(f'  [{name}] {note}')
    CHECKS.append((name, note, 0))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:  # noqa: PLR0915 - doctor keeps ordered diagnostic sections inline.
    """Run repository harness and hook health checks.

    Returns:
        Computed result.
    """
    print(f'\n{"=" * 60}')
    print('doctor: feipi-session-browser harness health check')
    print(f'root: {REPO_ROOT}')
    print(f'{"=" * 60}\n')

    # Section 1: Repo structure
    print('--- repo structure ---')
    _run('repo structure', 'python3 scripts/quality/validate_repo_structure.py')
    print()

    # Section 2: Harness validators
    print('--- harness validators ---')
    _run('harness structure', 'python3 scripts/harness/validate_harness_structure.py')
    _run('openspec layout', 'python3 scripts/harness/validate_openspec_layout.py')
    print()

    # Section 3: Hook self-tests
    print('--- hook self-tests ---')
    _run('guard guard', 'python3 scripts/agent_hooks/guard_active_openspec_change.py --self-test')
    _run('stop validate', 'python3 scripts/agent_hooks/stop_validate_change.py --self-test')
    _run('inject context', 'python3 scripts/agent_hooks/inject_session_context.py --self-test')
    _run('log evidence', 'python3 scripts/agent_hooks/log_change_evidence.py --self-test')
    print()

    # Section 4: Settings JSON
    print('--- settings ---')
    settings_path = REPO_ROOT / '.claude/settings.json'
    if settings_path.is_file():
        try:
            json.loads(settings_path.read_text(encoding='utf-8'))
            _note('settings.json', 'valid JSON')
            content = settings_path.read_text(encoding='utf-8')
            _note('SessionStart hook', 'present' if 'SessionStart' in content else 'MISSING')
            _note('SubagentStart hook', 'present' if 'SubagentStart' in content else 'MISSING')
            _note('PreToolUse hooks', 'present' if 'PreToolUse' in content else 'MISSING')
            _note('PostToolUse hooks', 'present' if 'PostToolUse' in content else 'MISSING')
            _note('Stop hook', 'present' if '"Stop"' in content else 'MISSING')
            _note('SubagentStop hook', 'present' if 'SubagentStop' in content else 'MISSING')
        except Exception as exc:
            _run('settings.json', f'echo FAIL: {exc}')
    else:
        _note('settings.json', 'MISSING')
    print()

    # Section 5: Gitignore
    print('--- gitignore ---')
    gitignore = REPO_ROOT / '.gitignore'
    if gitignore.is_file():
        content = gitignore.read_text(encoding='utf-8')
        _note('tmp/', 'ignored' if 'tmp/' in content else 'NOT ignored')
        _note('openspec/changes/*', 'ignored' if 'openspec/changes/*' in content else 'NOT ignored')
        _note('reports/', 'ignored' if 'reports/' in content else 'NOT ignored')
    else:
        _note('.gitignore', 'MISSING')
    print()

    # Section 6: Default agents
    print('--- default agents ---')
    agents_dir = REPO_ROOT / '.claude/agents'
    for agent in ['openspec-planner.md', 'implementer.md', 'qa-verifier.md']:
        path = agents_dir / agent
        exists = path.is_file()
        _note(agent, 'present' if exists else 'MISSING')
    print()

    # Summary
    hard_failures = sum(1 for _, _, code in CHECKS if code != 0)
    total = len(CHECKS)
    passed = total - hard_failures

    print(f'{"=" * 60}')
    print(f'summary: {passed}/{total} passed, {hard_failures} failures')
    print(f'{"=" * 60}')

    if hard_failures:
        print('\nFailed checks:')
        for name, _cmd, code in CHECKS:
            if code != 0:
                print(f'  - {name} (exit={code})')
        print()

    return 1 if hard_failures > 0 else 0


if __name__ == '__main__':
    sys.exit(main())
