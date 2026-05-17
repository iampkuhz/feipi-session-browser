#!/usr/bin/env python3
"""Validate that an active OpenSpec change has all required files.

Usage:
    python scripts/openspec/validate_active_change.py --change-id <id>
    python scripts/openspec/validate_active_change.py --self-test
"""
import argparse
import sys
import tempfile
import shutil
from pathlib import Path


def validate_change(change_id: str) -> list[str]:
    """Return list of error messages (empty = pass)."""
    root = Path.cwd()
    change_dir = root / "openspec" / "changes" / change_id
    errors: list[str] = []

    if not change_dir.is_dir():
        return [f"Change directory not found: openspec/changes/{change_id}"]

    required_files = ["proposal.md", "design.md", "tasks.md"]
    for fname in required_files:
        if not (change_dir / fname).exists():
            errors.append(f"Missing required file: openspec/changes/{change_id}/{fname}")

    specs_dir = change_dir / "specs"
    if not specs_dir.is_dir():
        errors.append(f"Missing directory: openspec/changes/{change_id}/specs/")
    else:
        spec_files = list(specs_dir.rglob("*.md"))
        # Filter out README.md or other non-spec files if needed
        # At least one spec.md should exist (any .md in specs/ counts)
        if not spec_files:
            errors.append(f"No spec.md files found under openspec/changes/{change_id}/specs/")

    return errors


def run_self_test() -> bool:
    """Create a temp change, validate, clean up, report."""
    tmp_root = Path(tempfile.mkdtemp(prefix="openspec_selftest_"))
    change_dir = tmp_root / "openspec" / "changes" / "test-change"
    specs_dir = change_dir / "specs"

    try:
        # Test 1: missing everything
        (change_dir / "specs").mkdir(parents=True)
        errors = validate_change_at_root("test-change", tmp_root)
        if not errors:
            print(f"  FAIL: expected errors for empty change, got none")
            return False
        print(f"  PASS: detected missing files ({len(errors)} errors)")

        # Test 2: all files present
        for fname in ["proposal.md", "design.md", "tasks.md"]:
            (change_dir / fname).write_text(f"# {fname}\n")
        (specs_dir / "spec.md").write_text("# spec\n")

        errors = validate_change_at_root("test-change", tmp_root)
        if errors:
            print(f"  FAIL: expected no errors for complete change, got: {errors}")
            return False
        print(f"  PASS: complete change validates clean")

        # Test 3: non-existent change
        errors = validate_change_at_root("no-such-change", tmp_root)
        if not errors:
            print(f"  FAIL: expected error for non-existent change")
            return False
        print(f"  PASS: detected non-existent change")

        return True
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


def validate_change_at_root(change_id: str, root: Path) -> list[str]:
    """Same as validate_change but with explicit root for self-test."""
    change_dir = root / "openspec" / "changes" / change_id
    errors: list[str] = []

    if not change_dir.is_dir():
        return [f"Change directory not found: openspec/changes/{change_id}"]

    required_files = ["proposal.md", "design.md", "tasks.md"]
    for fname in required_files:
        if not (change_dir / fname).exists():
            errors.append(f"Missing required file: openspec/changes/{change_id}/{fname}")

    specs_dir = change_dir / "specs"
    if not specs_dir.is_dir():
        errors.append(f"Missing directory: openspec/changes/{change_id}/specs/")
    else:
        spec_files = list(specs_dir.rglob("*.md"))
        if not spec_files:
            errors.append(f"No spec.md files found under openspec/changes/{change_id}/specs/")

    return errors


def main():
    parser = argparse.ArgumentParser(description="Validate active OpenSpec change structure")
    parser.add_argument("--change-id", help="Change ID to validate")
    parser.add_argument("--self-test", action="store_true", help="Run self-test and exit")
    args = parser.parse_args()

    if args.self_test:
        print("Running self-test...")
        ok = run_self_test()
        if ok:
            print("self-test: PASS")
            sys.exit(0)
        else:
            print("self-test: FAIL")
            sys.exit(1)

    if not args.change_id:
        parser.error("either --change-id or --self-test is required")

    errors = validate_change(args.change_id)
    if errors:
        print(f"Validation FAILED for change '{args.change_id}':")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    else:
        print(f"Validation PASS for change '{args.change_id}'")
        sys.exit(0)


if __name__ == "__main__":
    main()
