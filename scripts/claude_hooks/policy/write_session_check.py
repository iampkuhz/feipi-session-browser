#!/usr/bin/env python3
"""Report whether the current Claude session wrote files.

The stop hook calls this script with Claude hook JSON on stdin. It reads the session id,
checks ``changed-files.jsonl``, and prints one token: ``no_changes`` for read-only
sessions, ``has_changes`` when matching write evidence exists, or ``unknown`` when input
cannot identify a session. Unknown is conservative and should be treated as changed by
callers.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> None:
    """Print write status for the current hook session.

    The function reads stdin and local JSONL evidence, then writes exactly one status
    token to stdout. JSON parse failures in evidence are ignored so a corrupt line does
    not crash the stop hook.
    """
    repo_root = Path(__file__).resolve().parent.parent.parent.parent
    changed_file = repo_root / 'tmp' / 'agent_logs' / 'current' / 'changed-files.jsonl'

    # 尝试从 stdin 读取 session ID (Claude hook 传入的 JSON)。
    session_id = _read_session_id_from_stdin()

    if not session_id:
        print('unknown')
        return

    if not changed_file.exists() or changed_file.stat().st_size == 0:
        print('no_changes')
        return

    for raw_line in changed_file.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
            if record.get('sessionId') == session_id:
                print('has_changes')
                return
        except json.JSONDecodeError:
            continue

    print('no_changes')


def _read_session_id_from_stdin() -> str | None:
    """Extract the Claude session id from stdin JSON.

    Returns:
        Session id when stdin contains a JSON object with ``session_id`` or
        ``sessionId``; otherwise ``None``.
    """
    try:
        text = sys.stdin.read()
        if not text or not text.strip():
            return None
        data = json.loads(text)
        if not isinstance(data, dict):
            return None
        sid = data.get('session_id') or data.get('sessionId') or ''
        return sid if sid else None
    except Exception:
        return None


if __name__ == '__main__':
    main()
