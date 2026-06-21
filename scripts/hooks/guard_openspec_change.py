#!/usr/bin/env python3
"""Guard implementation edits until an active OpenSpec change exists.

Agent hooks call this script before protected implementation work. It checks
openspec/changes for at least one non-archive directory, prints the blocking
reason to stderr, and exits 2 when OpenSpec setup is missing; otherwise it exits
0 without modifying the repository.
"""

import sys
from pathlib import Path

root = Path.cwd()
changes = root / 'openspec' / 'changes'
if not changes.exists():
    print(
        'OpenSpec changes directory is missing. Create openspec/changes/<change-id>/ before editing.',
        file=sys.stderr,
    )
    sys.exit(2)
active = [p for p in changes.iterdir() if p.is_dir() and p.name != 'archive']
if not active:
    print(
        'No active OpenSpec change found. Create a change before implementation edits.',
        file=sys.stderr,
    )
    sys.exit(2)
sys.exit(0)
