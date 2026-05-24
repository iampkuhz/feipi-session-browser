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

import sqlite3
import sys
from pathlib import Path

# Ensure repo_root is on sys.path so `session_browser.*` imports work.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from session_browser.config import INDEX_PATH, ensure_index_dir

KNOWN_AGENTS = {"claude_code", "codex", "qoder"}

# Required columns that must not be empty for every session row
REQUIRED_NONEMPTY_COLS = [
    "session_key",
    "agent",
    "session_id",
    "project_key",
    "ended_at",
]


class IntegrityResult:
    """Accumulates pass/fail results."""

    def __init__(self) -> None:
        self.checks: list[tuple[str, str]] = []  # (check_name, status)

    def ok(self, name: str) -> None:
        print(f"  [PASS] {name}")
        self.checks.append((name, "PASS"))

    def fail(self, name: str, detail: str = "") -> None:
        msg = f"{name}: {detail}" if detail else name
        print(f"  [FAIL] {msg}")
        self.checks.append((name, "FAIL"))

    @property
    def all_passed(self) -> bool:
        return all(status == "PASS" for _, status in self.checks)


def _get_connection(db_path: Path) -> sqlite3.Connection | None:
    """Try to open the index database. Returns None if it cannot be opened."""
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        return conn
    except Exception:
        return None


def check_index_file_exists(result: IntegrityResult) -> None:
    """Check 1: index file exists."""
    if INDEX_PATH.is_file():
        result.ok("index file exists")
    else:
        result.fail("index file exists", f"not found at {INDEX_PATH}")


def check_session_count(result: IntegrityResult, conn: sqlite3.Connection) -> None:
    """Check 2: sessions table has > 0 rows."""
    try:
        row = conn.execute("SELECT COUNT(*) AS cnt FROM sessions").fetchone()
        cnt = row["cnt"]
        if cnt > 0:
            result.ok(f"session count > 0 (total={cnt})")
        else:
            result.fail("session count > 0", "index is empty")
    except sqlite3.OperationalError as exc:
        result.fail("session count > 0", f"sessions table query failed: {exc}")


def check_required_fields(result: IntegrityResult, conn: sqlite3.Connection) -> None:
    """Check 3: every session row has non-empty required fields."""
    try:
        # Build query to find rows where any required column is empty
        clauses = " OR ".join(f"COALESCE({col}, '') = ''" for col in REQUIRED_NONEMPTY_COLS)
        query = f"SELECT session_key, {', '.join(REQUIRED_NONEMPTY_COLS)} FROM sessions WHERE {clauses}"
        bad_rows = conn.execute(query).fetchall()
        if not bad_rows:
            result.ok("required fields non-empty (all rows)")
        else:
            sample_keys = [r["session_key"] for r in bad_rows[:5]]
            detail = f"{len(bad_rows)} rows have empty required fields; sample: {sample_keys}"
            result.fail("required fields non-empty", detail)
    except sqlite3.OperationalError as exc:
        result.fail("required fields non-empty", f"query failed: {exc}")


def check_no_orphan_agents(result: IntegrityResult, conn: sqlite3.Connection) -> None:
    """Check 4: every agent value is a known agent."""
    try:
        row = conn.execute(
            "SELECT DISTINCT agent FROM sessions WHERE agent NOT IN ({})".format(
                ", ".join("?" for _ in KNOWN_AGENTS)
            ),
            tuple(KNOWN_AGENTS),
        ).fetchall()
        if not row:
            result.ok("no orphan agents")
        else:
            unknown = [r["agent"] for r in row]
            result.fail("no orphan agents", f"unknown agents: {unknown}")
    except sqlite3.OperationalError as exc:
        result.fail("no orphan agents", f"query failed: {exc}")


def check_scan_log_exists(result: IntegrityResult, conn: sqlite3.Connection) -> None:
    """Check 5 (warn-only): scan_log table exists."""
    try:
        conn.execute("SELECT COUNT(*) FROM scan_log").fetchone()
        result.ok("scan_log table exists")
    except sqlite3.OperationalError:
        # Non-blocking — the table may not exist if the schema hasn't been initialized.
        print("  [WARN] scan_log table missing (non-blocking)")
        result.ok("scan_log table exists (warn-only, missing is acceptable)")


def main() -> int:
    print(f"\n{'='*60}")
    print("index integrity gate")
    print(f"index path: {INDEX_PATH}")
    print(f"{'='*60}\n")

    result = IntegrityResult()

    # Check 1: file exists
    check_index_file_exists(result)

    if not INDEX_PATH.is_file():
        print("\nIndex file does not exist — cannot run further checks.\n")
        return 1

    conn = _get_connection(INDEX_PATH)
    if conn is None:
        result.fail("database connection", "cannot open SQLite connection")
        print(f"\nResult: FAIL\n")
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
    passed = sum(1 for _, s in result.checks if s == "PASS")
    failed = sum(1 for _, s in result.checks if s == "FAIL")
    total = passed + failed

    print(f"\n{'='*60}")
    print(f"summary: {passed}/{total} passed, {failed} failures")
    print(f"{'='*60}\n")

    return 0 if result.all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
