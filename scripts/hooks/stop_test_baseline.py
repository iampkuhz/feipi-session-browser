#!/usr/bin/env python3
"""Stop hook: block delivery if NEW test failures appear.

Compares pytest results against tests/baseline-failures.txt.
Existing baseline failures are allowed; any new failure BLOCKS.

Usage:
    python3 scripts/hooks/stop_test_baseline.py [--self-test]

Exit codes:
    0  PASS — no tests fail, or only baseline failures
    1  FAIL — new test failure(s) detected (not in baseline)
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BASELINE_PATH = REPO_ROOT / "tests" / "baseline-failures.txt"


def load_baseline() -> set[str]:
    """Load known-failing test identifiers from baseline file."""
    if not BASELINE_PATH.exists():
        return set()
    result = set()
    for line in BASELINE_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            result.add(stripped)
    return result


def run_pytest() -> tuple[list[str], list[str]]:
    """Run pytest and return (failed_test_ids, all_output_lines).

    Each failed_test_id is the full identifier:
        tests/<file>::<Class>::<method>
    """
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--tb=no", "-q",
         "tests/", "--no-header"],
        cwd=str(REPO_ROOT),
        capture_output=True, text=True, timeout=300
    )
    # Parse short summary: "FAILED tests/test_foo.py::TestBar::test_baz"
    # pytest may add " - assertion text..." after the test name,
    # so we only take the first non-space token after FAILED.
    failed = []
    for line in (result.stdout + result.stderr).splitlines():
        m = re.match(r'^FAILED\s+(tests/\S+)', line)
        if m:
            test_id = m.group(1)
            # Ensure it has the full ::Class::method format
            parts = test_id.split("::")
            if len(parts) >= 3:
                failed.append(test_id)
    return failed, (result.stdout + result.stderr).splitlines()


def check_baseline() -> tuple[str, list[str]]:
    """Run the check. Returns (status, messages)."""
    baseline = load_baseline()
    if not baseline:
        return "FAIL", [
            "BLOCK: tests/baseline-failures.txt not found or empty.",
            "Run the full test suite first, then record known failures.",
        ]

    failed, output_lines = run_pytest()

    # Check for new failures not in baseline
    new_failures = [f for f in failed if f not in baseline]

    if not new_failures:
        # Either all pass, or only baseline failures
        baseline_hit = [f for f in failed if f in baseline]
        msgs = []
        if baseline_hit:
            msgs.append(f"PASS ({len(baseline_hit)} baseline failure(s), 0 new)")
        else:
            msgs.append(f"PASS (all {len(failed)} previously failing tests now pass — consider updating baseline)")
        return "PASS", msgs

    # New failures detected — BLOCK
    msgs = [
        f"BLOCK: {len(new_failures)} new test failure(s) detected (not in baseline).",
        "",
        "New failures:",
    ]
    for tf in new_failures:
        msgs.append(f"  - {tf}")

    if baseline_hit := [f for f in failed if f in baseline]:
        msgs.append(f"")
        msgs.append(f"Baseline failures ({len(baseline_hit)} — allowed):")
        for tf in baseline_hit:
            msgs.append(f"  - {tf}")

    msgs.extend([
        "",
        "To fix:",
        "  1. Fix the new test failures above, or",
        "  2. If intentional, add the new test IDs to tests/baseline-failures.txt",
        "     (requires explicit user approval)",
        "",
        "To update baseline after fixing:",
        f"  python3 scripts/hooks/stop_test_baseline.py --update-baseline",
    ])
    return "FAIL", msgs


def update_baseline():
    """Re-run tests and write new baseline file."""
    print("Running full test suite to update baseline...", file=sys.stderr)
    failed, _ = run_pytest()
    failed.sort()

    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Known test failures baseline — auto-generated",
        "# Each line: tests/<file>::<Class>::<method>",
        "# See scripts/hooks/stop_test_baseline.py for usage",
        "",
    ]
    lines.extend(failed)
    BASELINE_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Updated baseline with {len(failed)} known failure(s):", file=sys.stderr)
    for tf in failed:
        print(f"  - {tf}", file=sys.stderr)


def main():
    if "--update-baseline" in sys.argv:
        update_baseline()
        sys.exit(0)

    if "--self-test" in sys.argv:
        _self_test()
        return

    status, messages = check_baseline()
    for msg in messages:
        print(msg, file=sys.stderr if status == "FAIL" else sys.stdout)

    if status == "FAIL":
        sys.exit(1)


def _self_test():
    """Run self-tests."""
    import tempfile

    def _run(name, func):
        try:
            func()
            print(f"  PASS: {name}")
        except AssertionError as e:
            print(f"  FAIL: {name} — {e}")
            sys.exit(1)
        except Exception as e:
            print(f"  FAIL: {name} — {type(e).__name__}: {e}")
            sys.exit(1)

    # Test 1: empty baseline => FAIL
    def _t1():
        with tempfile.TemporaryDirectory() as td:
            global BASELINE_PATH
            old = BASELINE_PATH
            BASELINE_PATH = Path(td) / "baseline-failures.txt"
            try:
                status, msgs = check_baseline()
                assert status == "FAIL", f"Expected FAIL for empty baseline, got {status}"
            finally:
                BASELINE_PATH = old

    # Test 2: baseline with matching failure => PASS
    def _t2():
        global BASELINE_PATH, run_pytest
        old_bp = BASELINE_PATH
        old_rp = run_pytest
        with tempfile.TemporaryDirectory() as td:
            BASELINE_PATH = Path(td) / "baseline.txt"
            BASELINE_PATH.write_text("tests/test_foo.py::TestA::test_b\n")

            def fake_run():
                return ["tests/test_foo.py::TestA::test_b"], []
            run_pytest = fake_run
            try:
                status, msgs = check_baseline()
                assert status == "PASS", f"Expected PASS, got {status}: {msgs}"
            finally:
                BASELINE_PATH = old_bp
                run_pytest = old_rp

    # Test 3: baseline missing a failure => FAIL
    def _t3():
        global BASELINE_PATH, run_pytest
        old_bp = BASELINE_PATH
        old_rp = run_pytest
        with tempfile.TemporaryDirectory() as td:
            BASELINE_PATH = Path(td) / "baseline.txt"
            BASELINE_PATH.write_text("tests/test_foo.py::TestA::test_b\n")

            def fake_run():
                return [
                    "tests/test_foo.py::TestA::test_b",      # baseline
                    "tests/test_bar.py::TestB::test_c",      # NEW
                ], []
            run_pytest = fake_run
            try:
                status, msgs = check_baseline()
                assert status == "FAIL", f"Expected FAIL, got {status}"
                assert any("test_bar" in m for m in msgs), f"Expected new failure in messages: {msgs}"
            finally:
                BASELINE_PATH = old_bp
                run_pytest = old_rp

    _run("empty baseline => FAIL", _t1)
    _run("baseline match => PASS", _t2)
    _run("new failure => FAIL", _t3)
    print("\nAll self-tests passed")


if __name__ == "__main__":
    main()
