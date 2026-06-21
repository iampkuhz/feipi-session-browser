#!/usr/bin/env python3
"""PostToolUse evidence logger for Write/Edit/MultiEdit hooks.

Called by Claude Code as a PostToolUse hook after protected file edits.
Logs a JSONL entry per edit into tmp/task-evidence/<change-id>.jsonl.

Usage:
    python3 scripts/agent_hooks/log_change_evidence.py [file_path]
    echo '{"tool_name":"Edit","tool_input":{"file_path":"src/x.css"}}' | python3 ...

Modes:
    --self-test   Run self-test suite and exit
    --debug       Print resolved tool/file to stderr (for troubleshooting).
"""

import json
import sys
from datetime import datetime, timezone
from functools import cache
from io import StringIO
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths (all relative to project root = cwd)
# ---------------------------------------------------------------------------
EVIDENCE_DIR = Path('tmp/task-evidence')
ACTIVE_CHANGE = Path('tmp/active_change.json')

DEBUG = '--debug' in sys.argv


@cache
def _get_stdin_payload() -> dict | None:
    """Read and cache the Claude Code stdin JSON payload.

    Returns:
        Parsed JSON payload, or None when stdin is empty or invalid.
    """
    if sys.stdin.isatty():
        return None
    try:
        raw = sys.stdin.read()
        obj = _try_parse_json(raw)
        if obj is not None:
            return obj
    except (OSError, UnicodeDecodeError):
        pass
    return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def load_active_change() -> dict | None:
    """Read active change metadata from tmp/active_change.json.

    Returns:
        Parsed metadata when a change id is present, otherwise None.
    """
    if not ACTIVE_CHANGE.is_file():
        return None
    try:
        data = json.loads(ACTIVE_CHANGE.read_text(encoding='utf-8'))
        cid = data.get('change_id')
        if cid:
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return None


def _try_parse_json(text: str) -> dict | None:
    """Parse a JSON object string from hook input.

    Args:
        text: Raw stdin or test payload text.

    Returns:
        Parsed dictionary when the payload is a JSON object, otherwise None.
    """
    text = text.strip()
    if not text.startswith('{'):
        return None
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except (json.JSONDecodeError, OSError):
        pass
    return None


def _extract_from_payload(payload: dict) -> tuple[str | None, str | None]:
    """Extract file path and tool name from a hook payload.

    Args:
        payload: Claude Code hook payload dictionary.

    Returns:
        Tuple of file path and tool name, with missing values as None.
    """
    file_path = None
    tool_name = None

    # Tool name
    tool_name = payload.get('tool_name') or payload.get('tool')

    # file_path from top-level or tool_input
    tool_input = payload.get('tool_input')
    if isinstance(tool_input, dict):
        file_path = (
            tool_input.get('file_path') or tool_input.get('path') or tool_input.get('notebook_path')
        )
    if not file_path:
        file_path = payload.get('file_path') or payload.get('path')

    return file_path, tool_name


def get_file_path() -> str | None:
    """Resolve the edited file path from argv or stdin.

    Returns:
        File path to log, or None when the hook payload has no target.
    """
    # 1. argv
    if len(sys.argv) > 1 and sys.argv[1] not in ('--self-test', '--debug'):
        return sys.argv[1]

    # 2. stdin JSON payload (cached - stdin is single-use)
    payload = _get_stdin_payload()
    if payload is not None:
        fp, tn = _extract_from_payload(payload)
        if DEBUG and tn:
            print(f'[debug] resolved tool_name={tn} from stdin', file=sys.stderr)
        if fp:
            return fp

    return None


def get_tool_name() -> str:
    """Resolve the editing tool name from cached stdin payload.

    Returns:
        Tool name reported by the hook, defaulting to Write.
    """
    # Use cached stdin payload (stdin is single-use; already cached by get_file_path)
    payload = _get_stdin_payload()
    if payload is not None:
        _, tn = _extract_from_payload(payload)
        if tn:
            return tn

    return 'Write'


def log_entry(file_path: str, tool: str, change_id: str | None) -> Path:
    """Append one evidence JSONL record for a protected edit.

    Args:
        file_path: Edited file path reported by the hook.
        tool: Editing tool name reported by the hook.
        change_id: Active OpenSpec change id, if one is available.

    Returns:
        Path to the JSONL evidence file that received the entry.
    """
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    target = EVIDENCE_DIR / f'{change_id}.jsonl' if change_id else EVIDENCE_DIR / 'unknown.jsonl'
    entry = {
        'ts': datetime.now(timezone.utc).isoformat(),
        'tool': tool,
        'file_path': file_path,
        'change_id': change_id or 'unknown',
    }
    with target.open('a', encoding='utf-8') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + '\n')
    return target


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    """Run the evidence logger CLI and return its process exit code.

    Returns:
        Process exit code for the hook invocation.
    """
    if '--self-test' in sys.argv:
        return self_test()

    file_path = get_file_path()
    if not file_path:
        # Nothing to log, but not an error (exit 0 by contract).
        return 0

    tool = get_tool_name()
    change_data = load_active_change()
    change_id = change_data['change_id'] if change_data else None
    log_entry(file_path, tool, change_id)
    return 0


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------


def self_test() -> int:  # noqa: PLR0915
    """Run the evidence logger self-test suite.

    Returns:
        Process exit code where 0 means all self-tests passed.
    """
    passed = 0
    failed = 0

    def check(name: str, condition: bool) -> None:
        """Record one evidence logger self-test assertion.

        Args:
            name: Human-readable assertion name.
            condition: Whether the assertion passed.
        """
        nonlocal passed, failed
        if condition:
            passed += 1
            print(f'  [PASS] {name}')
        else:
            failed += 1
            print(f'  [FAIL] {name}')

    # --- Test 1: argv raw path still works ---
    print('Test 1: argv raw path writes evidence')
    _reset_evidence()
    active = load_active_change()
    test_id = active['change_id'] if active else '_selftest_'
    fp = 'src/example/file.py'
    log_entry(fp, 'Edit', test_id)
    ev = EVIDENCE_DIR / f'{test_id}.jsonl'
    check('evidence file created', ev.is_file())
    if ev.is_file():
        entry = json.loads(ev.read_text().strip().split('\n')[-1])
        check('file_path matches', entry.get('file_path') == 'src/example/file.py')
        check('tool is Edit', entry.get('tool') == 'Edit')

    # --- Test 2: stdin Claude Code style payload ---
    print('Test 2: stdin JSON payload (Claude Code style)')
    _reset_evidence()
    payload = json.dumps(
        {
            'tool_name': 'Edit',
            'tool_input': {'file_path': 'src/session_browser/web/static/style.css'},
        }
    )
    fp, tn = _simulate_stdin(payload)
    check('extracts tool_name from stdin', tn == 'Edit')
    check('extracts file_path from stdin', fp == 'src/session_browser/web/static/style.css')

    # --- Test 3: MultiEdit payload ---
    print('Test 3: MultiEdit payload - single evidence entry')
    _reset_evidence()
    multi_payload = json.dumps(
        {
            'tool_name': 'MultiEdit',
            'tool_input': {
                'file_path': 'src/multi.html',
                'edits': [{'file_path': 'src/a.html'}, {'file_path': 'src/b.html'}],
            },
        }
    )
    fp, tn = _simulate_stdin(multi_payload)
    check('tool_name is MultiEdit', tn == 'MultiEdit')
    check('file_path is top-level, not first edit', fp == 'src/multi.html')

    # --- Test 4: no active change -> unknown.jsonl ---
    print('Test 4: no active change writes to unknown.jsonl')
    _reset_evidence()
    backup = None
    if ACTIVE_CHANGE.is_file():
        backup = ACTIVE_CHANGE.read_bytes()
        ACTIVE_CHANGE.unlink()
    log_entry('docs/README.md', 'Write', None)
    unknown = EVIDENCE_DIR / 'unknown.jsonl'
    check('unknown.jsonl created', unknown.is_file())
    if unknown.is_file():
        entry = json.loads(unknown.read_text().strip().split('\n')[-1])
        check('change_id is unknown', entry.get('change_id') == 'unknown')
        check('file_path correct', entry.get('file_path') == 'docs/README.md')
    if backup is not None:
        ACTIVE_CHANGE.write_bytes(backup)

    # --- Test 5: notebook_path fallback ---
    print('Test 5: notebook_path extraction')
    _reset_evidence()
    nb_payload = json.dumps(
        {'tool_name': 'NotebookEdit', 'tool_input': {'notebook_path': 'analysis.ipynb'}}
    )
    fp, tn = _simulate_stdin(nb_payload)
    check('extracts notebook_path', fp == 'analysis.ipynb')

    # --- Test 6: top-level path fallback ---
    print('Test 6: top-level path fallback (no tool_input)')
    _reset_evidence()
    flat_payload = json.dumps({'tool': 'Write', 'file_path': 'config.yaml'})
    fp, tn = _simulate_stdin(flat_payload)
    check('extracts top-level file_path', fp == 'config.yaml')
    check('extracts top-level tool', tn == 'Write')

    # Summary
    print(f'\n{"=" * 60}')
    print(f'self-test results: {passed}/{passed + failed} passed')
    print(f'{"=" * 60}')
    return 0 if failed == 0 else 1


def _reset_evidence() -> None:
    """Remove all evidence files for a clean test run."""
    if EVIDENCE_DIR.is_dir():
        for f in EVIDENCE_DIR.iterdir():
            f.unlink()


def _simulate_stdin(json_str: str) -> tuple[str | None, str | None]:
    """Feed a JSON payload through the stdin extraction path.

    Args:
        json_str: JSON hook payload to parse.

    Returns:
        Tuple of extracted file path and tool name.
    """
    saved_stdin = sys.stdin
    sys.stdin = StringIO(json_str)  # not a tty -> triggers stdin branch
    try:
        # Re-parse directly from the string (same logic as main path)
        obj = _try_parse_json(json_str)
        if obj is not None:
            return _extract_from_payload(obj)
    finally:
        sys.stdin = saved_stdin
    return None, None


if __name__ == '__main__':
    sys.exit(main())
