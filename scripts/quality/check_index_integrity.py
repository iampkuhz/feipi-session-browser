#!/usr/bin/env python3
"""Index integrity gate — verify the SQLite session index is structurally sound.

Checks performed:
1. Index file exists at the configured INDEX_PATH.
2. The `sessions` table exists and contains > 0 rows.
3. Every row has non-empty required fields (session_key, agent, session_id,
   project_key, ended_at).
4. No orphan entries — every agent value is one of the known agents.
5. The `scan_log` table exists (optional, warn-only if missing).

Usage:
    python3 scripts/quality/check_index_integrity.py

Exit codes:
    0  all checks pass
    1  one or more hard failures
"""

from __future__ import annotations

import os
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# INDEX_PATH 直接定义，不再依赖 session_browser.config
INDEX_DIR = Path(
    os.environ.get(
        'INDEX_DIR',
        str(Path.home() / '.local' / 'share' / 'feipi' / 'session-browser' / 'local-test-index'),
    )
)
INDEX_PATH = INDEX_DIR / 'index.sqlite'

KNOWN_AGENTS = {'claude_code', 'codex', 'qoder'}

# Required columns that must not be empty for every session row
REQUIRED_NONEMPTY_COLS = [
    'session_key',
    'agent',
    'session_id',
    'project_key',
    'ended_at',
]


@dataclass
class IntegrityResult:
    """Accumulate index gate checks for the CLI summary.

    The index integrity quality gate creates one instance per run. It preserves
    check ordering, prints immediate diagnostics, and exposes aggregate pass
    state without mutating the SQLite index.

    Attributes:
        checks: Ordered ``(check_name, status)`` pairs recorded during the gate.
    """

    checks: list[tuple[str, str]] = field(default_factory=list)

    def ok(self, name: str) -> None:
        """Record a passing check and print its CLI evidence.

        Args:
            name: Stable check label shown in gate output.
        """
        print(f'  [PASS] {name}')
        self.checks.append((name, 'PASS'))

    def fail(self, name: str, detail: str = '') -> None:
        """Record a failing check and print the failure reason.

        Args:
            name: Stable check label shown in gate output.
            detail: Optional diagnostic explaining the observed index problem.
        """
        msg = f'{name}: {detail}' if detail else name
        print(f'  [FAIL] {msg}')
        self.checks.append((name, 'FAIL'))

    @property
    def all_passed(self) -> bool:
        """Return whether every recorded hard check passed."""
        return all(status == 'PASS' for _, status in self.checks)


def _get_connection(db_path: Path) -> sqlite3.Connection | None:
    """Open the SQLite index used by the session browser gate.

    Args:
        db_path: Configured index path from ``session_browser.config``.

    Returns:
        SQLite connection with row access enabled, or ``None`` when the file
        cannot be opened. The caller reports that condition as a hard failure.
    """
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        return conn
    except Exception:
        return None


def check_index_file_exists(result: IntegrityResult) -> None:
    """Check that the configured index file exists before SQL checks.

    Args:
        result: Accumulator receiving the pass/fail outcome.
    """
    if INDEX_PATH.is_file():
        result.ok('index file exists')
    else:
        result.fail('index file exists', f'not found at {INDEX_PATH}')


def check_session_count(result: IntegrityResult, conn: sqlite3.Connection) -> None:
    """Check that the sessions table exists and contains indexed rows.

    Args:
        result: Accumulator receiving the pass/fail outcome.
        conn: Open SQLite connection to the session index.
    """
    try:
        row = conn.execute('SELECT COUNT(*) AS cnt FROM sessions').fetchone()
        cnt = row['cnt']
        if cnt > 0:
            result.ok(f'session count > 0 (total={cnt})')
        else:
            result.fail('session count > 0', 'index is empty')
    except sqlite3.OperationalError as exc:
        result.fail('session count > 0', f'sessions table query failed: {exc}')


def check_required_fields(result: IntegrityResult, conn: sqlite3.Connection) -> None:
    """Check required session columns for empty values.

    Args:
        result: Accumulator receiving the pass/fail outcome.
        conn: Open SQLite connection queried by the quality gate.
    """
    try:
        # Build query to find rows where any required column is empty
        clauses = ' OR '.join(f"COALESCE({col}, '') = ''" for col in REQUIRED_NONEMPTY_COLS)
        query = (
            f'SELECT session_key, {", ".join(REQUIRED_NONEMPTY_COLS)} FROM sessions WHERE {clauses}'
        )
        bad_rows = conn.execute(query).fetchall()
        if not bad_rows:
            result.ok('required fields non-empty (all rows)')
        else:
            sample_keys = [r['session_key'] for r in bad_rows[:5]]
            detail = f'{len(bad_rows)} rows have empty required fields; sample: {sample_keys}'
            result.fail('required fields non-empty', detail)
    except sqlite3.OperationalError as exc:
        result.fail('required fields non-empty', f'query failed: {exc}')


def check_no_orphan_agents(result: IntegrityResult, conn: sqlite3.Connection) -> None:
    """Check every indexed session references a known agent adapter.

    Args:
        result: Accumulator receiving the pass/fail outcome.
        conn: Open SQLite connection queried for distinct agent values.
    """
    try:
        row = conn.execute(
            'SELECT DISTINCT agent FROM sessions WHERE agent NOT IN ({})'.format(
                ', '.join('?' for _ in KNOWN_AGENTS)
            ),
            tuple(KNOWN_AGENTS),
        ).fetchall()
        if not row:
            result.ok('no orphan agents')
        else:
            unknown = [r['agent'] for r in row]
            result.fail('no orphan agents', f'unknown agents: {unknown}')
    except sqlite3.OperationalError as exc:
        result.fail('no orphan agents', f'query failed: {exc}')


def check_scan_log_exists(result: IntegrityResult, conn: sqlite3.Connection) -> None:
    """Check whether scan_log exists while keeping missing table warn-only.

    Args:
        result: Accumulator receiving a passing warn-only outcome.
        conn: Open SQLite connection queried by the quality gate.
    """
    try:
        conn.execute('SELECT COUNT(*) FROM scan_log').fetchone()
        result.ok('scan_log table exists')
    except sqlite3.OperationalError:
        # Non-blocking — the table may not exist if the schema hasn't been initialized.
        print('  [WARN] scan_log table missing (non-blocking)')
        result.ok('scan_log table exists (warn-only, missing is acceptable)')


def main() -> int:
    """Run all index integrity checks and return shell-style status.

    Returns:
        ``0`` when all hard index checks pass, otherwise ``1``. The gate only
        reads SQLite metadata and rows; it does not repair or mutate the index.
    """
    print(f'\n{"=" * 60}')
    print('index integrity gate')
    print(f'index path: {INDEX_PATH}')
    print(f'{"=" * 60}\n')

    result = IntegrityResult()

    # Check 1: file exists
    check_index_file_exists(result)

    if not INDEX_PATH.is_file():
        print('\nIndex file does not exist — cannot run further checks.\n')
        return 1

    conn = _get_connection(INDEX_PATH)
    if conn is None:
        result.fail('database connection', 'cannot open SQLite connection')
        print('\nResult: FAIL\n')
        return 1

    try:
        # Check 2: session count
        check_session_count(result, conn)

        # Check 3: required fields
        check_required_fields(result, conn)

        # Check 4: no orphan agents
        check_no_orphan_agents(result, conn)

        # Check 5: scan_log (warn-only)
        check_scan_log_exists(result, conn)
    finally:
        conn.close()

    # Summary
    passed = sum(1 for _, s in result.checks if s == 'PASS')
    failed = sum(1 for _, s in result.checks if s == 'FAIL')
    total = passed + failed

    print(f'\n{"=" * 60}')
    print(f'summary: {passed}/{total} passed, {failed} failures')
    print(f'{"=" * 60}\n')

    return 0 if result.all_passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
