#!/usr/bin/env python3
"""Guard OpenSpec-protected edits from running without an active change.

Claude Code calls this lightweight hook before implementation edits. It blocks
when the repository has no active OpenSpec change directory, so protected work
keeps proposal, design, and task evidence in sync.
"""

import sys
from pathlib import Path

root = Path.cwd()
changes = root / 'openspec' / 'changes'
if not changes.exists():
    print(
        (
            'OpenSpec changes directory is missing. Create '
            'openspec/changes/<change-id>/ before editing.'
        ),
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
