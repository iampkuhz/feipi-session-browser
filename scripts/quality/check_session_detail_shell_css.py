#!/usr/bin/env python3
"""Static CSS firewall check for session detail Phase 1 shell layout.

Verifies that shell.css contains rules sufficient to prevent the
cascade conflict where body.hide-left .shell.no-inspector (specificity 0,3,0)
overrides .shell.phase1-shell (specificity 0,2,0), causing .main to
fall into a 0px grid column.

Usage:
    python3 scripts/quality/check_session_detail_shell_css.py
"""

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SHELL_CSS = REPO_ROOT / 'src' / 'session_browser' / 'web' / 'static' / 'css' / 'shell.css'

FAILURES = []


def fail(msg: str) -> None:
    """Record a blocking shell CSS contract failure.

    Args:
        msg: Input value for msg.
    """
    FAILURES.append(msg)
    print(f'  FAIL: {msg}')


def ok(msg: str) -> None:
    """Print a passing shell CSS assertion for gate evidence.

    Args:
        msg: Input value for msg.
    """
    print(f'  OK:   {msg}')


def check(content: str) -> None:
    """Validate shell.css content against the session detail layout invariant.

    Args:
        content: Input value for content.
    """
    # 1. Must have high-specificity override for body.hide-left
    if (
        'body.hide-left .shell.phase1-shell' in content
        or 'body.hide-left .shell.no-inspector.phase1-shell' in content
    ):
        ok('High-specificity body.hide-left .shell.phase1-shell override exists')
    else:
        fail(
            "Missing 'body.hide-left .shell.phase1-shell' (or .no-inspector.variant) "
            '— cascade conflict will not be resolved when sidebar is collapsed'
        )

    # 2. Must have .shell.phase1-shell .main rule
    if '.shell.phase1-shell .main' in content:
        ok('.shell.phase1-shell .main rule exists')
    else:
        fail("Missing '.shell.phase1-shell .main' rule")

    # 3. Must have grid-column: 1 / -1
    if 'grid-column: 1 / -1' in content or 'grid-column:1/-1' in content:
        ok('grid-column: 1 / -1 found (prevents auto-placement into 0px column)')
    else:
        fail("Missing 'grid-column: 1 / -1' — .main may auto-place into 0px column")

    # 4. Must have width: 100%
    if 'width: 100%' in content or 'width:100%' in content:
        ok('width: 100% found on .main')
    else:
        fail("Missing 'width: 100%' on .main")

    # 5. Must have min-width: 0
    if 'min-width: 0' in content or 'min-width:0' in content:
        ok('min-width: 0 found on .main')
    else:
        fail("Missing 'min-width: 0' on .main")

    # 6. Prevent: only low-specificity rule exists without body.hide-left override
    #    Check if there's a standalone .shell.phase1-shell { grid-template-columns }
    #    that is NOT accompanied by a body.hide-left variant
    standalone_pattern = r'\.shell\.phase1-shell\s*\{[^}]*grid-template-columns'
    has_standalone = bool(re.search(standalone_pattern, content))

    hide_left_pattern = r'body\.hide-left.*\.shell\.phase1-shell'
    has_hide_left_override = bool(re.search(hide_left_pattern, content))

    if has_standalone and not has_hide_left_override:
        fail(
            "Only low-specificity '.shell.phase1-shell' grid rule exists "
            'without body.hide-left override — will be overridden in collapsed sidebar state'
        )
    elif has_hide_left_override:
        ok('High-specificity override prevents cascade conflict in all body states')


def main() -> None:
    """Run the shell CSS firewall quality gate."""
    print('=' * 60)
    print('Session Detail Shell CSS Firewall Check')
    print('=' * 60)

    if not SHELL_CSS.exists():
        print(f'ERROR: shell.css not found at {SHELL_CSS}')
        sys.exit(2)

    content = SHELL_CSS.read_text()
    print(f'\nChecking {SHELL_CSS.relative_to(REPO_ROOT)}\n')

    check(content)

    print()
    if FAILURES:
        print(f'FAILED: {len(FAILURES)} rule(s) missing')
        for f in FAILURES:
            print(f'  - {f}')
        sys.exit(1)
    else:
        print('PASS: All CSS firewall rules present')
        sys.exit(0)


if __name__ == '__main__':
    main()
