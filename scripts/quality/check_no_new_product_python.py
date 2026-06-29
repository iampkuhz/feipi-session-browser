#!/usr/bin/env python3
"""Gate: reject new product Python files in src/session_browser/.

This script enforces the Python retirement policy (P40/P43). It scans
src/session_browser/ for .py files and fails if any are found.
Since P43 (2026-06-26), all product Python has been removed and
any new product Python is prohibited.

Harness, quality, test, and dev_tool Python files are NOT restricted
by this gate -- only new product runtime or web Python is blocked.

Exit 0 on pass, exit 1 on fail.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Repository root is two levels up from this script (scripts/quality/ -> repo root).
_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent.parent


def _scan_product_python(repo_root: Path) -> list[str]:
    """Return sorted list of .py file paths under src/session_browser/."""
    src_dir = repo_root / "src" / "session_browser"
    if not src_dir.is_dir():
        return []
    results: list[str] = []
    for py_file in sorted(src_dir.rglob("*.py")):
        # Skip __pycache__
        if "__pycache__" in py_file.parts:
            continue
        rel = py_file.relative_to(repo_root).as_posix()
        results.append(rel)
    return results


def main() -> int:
    """Run the gate check. Returns 0 on pass, 1 on fail."""
    repo_root = _REPO_ROOT
    all_py = _scan_product_python(repo_root)

    if all_py:
        print(
            "FAIL: check_no_new_product_python -- "
            f"found {len(all_py)} product Python file(s) in src/session_browser/:",
            file=sys.stderr,
        )
        for v in all_py:
            print(f"  - {v}", file=sys.stderr)
        print(
            "\nPython retirement policy (P40/P43) prohibits product Python.\n"
            "All product functionality has been migrated to Java.\n"
            "Write new functionality in Java instead.",
            file=sys.stderr,
        )
        return 1

    print(
        "PASS: check_no_new_product_python -- "
        "no product Python files found (src/session_browser/ removed)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
