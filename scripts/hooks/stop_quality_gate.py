#!/usr/bin/env python3
"""Stop hook quality gate enforcement.

Reads .agent/changed-files.jsonl and .agent/quality/<change-id>/quality-gate-summary.json
to determine if UI changes have passed required quality gates.

This is a DETERMINISTIC check — it does NOT run browsers, LLMs, or subagents.

Usage:
    python3 scripts/hooks/stop_quality_gate.py
    python3 scripts/hooks/stop_quality_gate.py --change-id fix-xyz
    python3 scripts/hooks/stop_quality_gate.py --self-test

Exit codes:
    0  PASS — no UI changes or quality artifact confirms PASS
    1  FAIL — UI changes without PASS artifact, or artifact is FAIL/stale
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CHANGED_FILES = REPO_ROOT / ".agent" / "changed-files.jsonl"
QUALITY_DIR = REPO_ROOT / ".agent" / "quality"

UI_CATEGORIES = {"ui-css", "ui-template", "ui-js"}
HOOK_QUALITY_CATEGORIES = {"hook", "quality-gate"}


def resolve_change_id(explicit: str | None) -> str:
    """Resolve change ID from args, env, or file fallback."""
    if explicit:
        return explicit
    env = os.environ.get("ACTIVE_CHANGE_ID")
    if env:
        return env
    active_file = REPO_ROOT / ".agent" / "active-change"
    if active_file.exists():
        return active_file.read_text().strip()
    return "unknown"


def read_changed_files() -> list[dict]:
    """Read .agent/changed-files.jsonl entries."""
    if not CHANGED_FILES.exists():
        return []
    entries = []
    for line in CHANGED_FILES.read_text(encoding="utf-8").strip().split("\n"):
        line = line.strip()
        if line:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def has_ui_changes(entries: list[dict]) -> tuple[bool, list[str]]:
    """Check if any changed file is UI-related."""
    ui_files = [
        e["file"] for e in entries
        if e.get("category") in UI_CATEGORIES
    ]
    return bool(ui_files), ui_files


def has_hook_quality_changes(entries: list[dict]) -> tuple[bool, list[str]]:
    """Check if any changed file is hook/quality-gate related."""
    files = [
        e["file"] for e in entries
        if e.get("category") in HOOK_QUALITY_CATEGORIES
    ]
    return bool(files), files


def get_latest_ui_edit_time(entries: list[dict]) -> str | None:
    """Get the timestamp of the latest UI file edit."""
    ui_times = [
        e["ts"] for e in entries
        if e.get("category") in UI_CATEGORIES and e.get("ts")
    ]
    return max(ui_times) if ui_times else None


def read_quality_artifact(change_id: str) -> dict | None:
    """Read quality-gate-summary.json for the change."""
    summary_path = QUALITY_DIR / change_id / "quality-gate-summary.json"
    if not summary_path.exists():
        return None
    try:
        return json.loads(summary_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def is_artifact_stale(artifact: dict, latest_ui_edit: str | None) -> bool:
    """Check if quality artifact is older than latest UI edit."""
    if not latest_ui_edit or not artifact:
        return False
    finished_at = artifact.get("finishedAt", "")
    if not finished_at:
        return True
    # Simple string comparison works for ISO 8601 UTC timestamps
    return finished_at < latest_ui_edit


def run_check(change_id: str | None = None) -> tuple[str, list[str]]:
    """Run the stop hook quality check.

    Returns (status, messages) where status is "PASS" or "FAIL".
    """
    cid = resolve_change_id(change_id)
    messages: list[str] = []

    # Read changed files
    entries = read_changed_files()
    if not entries:
        return "PASS", []

    # Check for UI changes
    has_ui, ui_files = has_ui_changes(entries)
    if not has_ui:
        # No UI changes — check if hook/quality files changed
        has_hq, hq_files = has_hook_quality_changes(entries)
        if not has_hq:
            return "PASS", []
        # Hook/quality files changed — require artifact PASS
        artifact = read_quality_artifact(cid)
        if artifact is None:
            return "PASS", []  # No UI changes, hook changes don't require UI gate
        if artifact.get("status") != "PASS":
            return "FAIL", [
                f"Quality gate artifact status is '{artifact.get('status')}' (expected PASS).",
                f"Run: python3 scripts/quality/run_quality_gate.py --target session-detail",
            ]
        return "PASS", []

    # UI changes exist — require quality artifact
    artifact = read_quality_artifact(cid)

    if artifact is None:
        return "FAIL", [
            f"BLOCK: UI files changed but required quality artifact is missing or stale.",
            "",
            f"Changed UI files:",
        ] + [f"  - {f}" for f in ui_files] + [
            "",
            f"Required:",
            f"  python3 scripts/quality/run_quality_gate.py --target session-detail",
            "",
            f"Expected artifact:",
            f"  .agent/quality/{cid}/quality-gate-summary.json",
            "",
            f"Reason:",
            f"  missing artifact",
        ]

    # Artifact exists but is FAIL
    if artifact.get("status") != "PASS":
        blocking = artifact.get("blockingFailures", [])
        summary = f"Artifact status: {artifact.get('status')}"
        if blocking:
            summary += f"\n  Blocking failures:\n" + "\n".join(f"    - {b}" for b in blocking[:5])
        return "FAIL", [
            "BLOCK: UI files changed but quality gate did not PASS.",
            "",
            f"Changed UI files:",
        ] + [f"  - {f}" for f in ui_files] + [
            "",
            f"Artifact summary:",
            f"  {summary}",
        ]

    # Artifact is PASS — check staleness
    latest_ui_edit = get_latest_ui_edit_time(entries)
    if is_artifact_stale(artifact, latest_ui_edit):
        return "FAIL", [
            "BLOCK: Quality artifact is stale (older than latest UI edit).",
            "",
            f"Latest UI edit: {latest_ui_edit}",
            f"Artifact finished: {artifact.get('finishedAt', 'unknown')}",
            "",
            f"Re-run: python3 scripts/quality/run_quality_gate.py --target session-detail",
        ]

    return "PASS", [f"Quality gate PASS (change-id={cid})"]


def _self_test():
    """Run self-tests for the stop hook quality gate."""
    import tempfile
    failures = 0

    def _run(name, func):
        nonlocal failures
        try:
            func()
            print(f"  PASS: {name}")
        except AssertionError as e:
            failures += 1
            print(f"  FAIL: {name} — {e}")
        except Exception as e:
            failures += 1
            print(f"  FAIL: {name} — {type(e).__name__}: {e}")

    def _make_artifact(status: str, finished: str = "2026-05-18T00:01:00Z") -> dict:
        return {
            "schemaVersion": 1,
            "status": status,
            "target": "session-detail",
            "changeId": "test",
            "startedAt": "2026-05-18T00:00:00Z",
            "finishedAt": finished,
            "requiredGates": {},
            "blockingFailures": [],
            "warnings": [],
            "artifacts": {},
        }

    def _t1_no_changed_files():
        """No changed-files => PASS."""
        with tempfile.TemporaryDirectory() as td:
            global CHANGED_FILES, QUALITY_DIR
            old_cf, old_qd = CHANGED_FILES, QUALITY_DIR
            try:
                CHANGED_FILES = Path(td) / "changed-files.jsonl"
                QUALITY_DIR = Path(td) / "quality"
                status, msgs = run_check("test")
                assert status == "PASS", f"Expected PASS, got {status}"
            finally:
                CHANGED_FILES, QUALITY_DIR = old_cf, old_qd

    def _t2_ui_missing_artifact():
        """UI file changed, artifact missing => FAIL."""
        with tempfile.TemporaryDirectory() as td:
            global CHANGED_FILES, QUALITY_DIR
            old_cf, old_qd = CHANGED_FILES, QUALITY_DIR
            try:
                CHANGED_FILES = Path(td) / "changed-files.jsonl"
                QUALITY_DIR = Path(td) / "quality"
                CHANGED_FILES.write_text(
                    json.dumps({"ts": "2026-05-18T00:00:00Z", "tool": "Edit",
                                "file": "src/session_browser/web/static/style.css",
                                "category": "ui-css", "requiresQualityGate": True}) + "\n"
                )
                status, msgs = run_check("test")
                assert status == "FAIL", f"Expected FAIL, got {status}"
                assert "missing" in " ".join(msgs).lower(), f"Expected 'missing' in messages"
            finally:
                CHANGED_FILES, QUALITY_DIR = old_cf, old_qd

    def _t3_ui_artifact_fail():
        """UI file changed, artifact FAIL => FAIL."""
        with tempfile.TemporaryDirectory() as td:
            global CHANGED_FILES, QUALITY_DIR
            old_cf, old_qd = CHANGED_FILES, QUALITY_DIR
            try:
                CHANGED_FILES = Path(td) / "changed-files.jsonl"
                QUALITY_DIR = Path(td) / "quality"
                QUALITY_DIR.mkdir(parents=True)
                CHANGED_FILES.write_text(
                    json.dumps({"ts": "2026-05-18T00:00:00Z", "tool": "Edit",
                                "file": "src/session_browser/web/static/style.css",
                                "category": "ui-css", "requiresQualityGate": True}) + "\n"
                )
                art = _make_artifact("FAIL")
                art["blockingFailures"] = ["css: missing rule"]
                (QUALITY_DIR / "test" / "quality-gate-summary.json").parent.mkdir(parents=True, exist_ok=True)
                (QUALITY_DIR / "test" / "quality-gate-summary.json").write_text(json.dumps(art))
                status, msgs = run_check("test")
                assert status == "FAIL", f"Expected FAIL, got {status}"
            finally:
                CHANGED_FILES, QUALITY_DIR = old_cf, old_qd

    def _t4_ui_artifact_stale():
        """UI file changed, artifact PASS but stale => FAIL."""
        with tempfile.TemporaryDirectory() as td:
            global CHANGED_FILES, QUALITY_DIR
            old_cf, old_qd = CHANGED_FILES, QUALITY_DIR
            try:
                CHANGED_FILES = Path(td) / "changed-files.jsonl"
                QUALITY_DIR = Path(td) / "quality"
                QUALITY_DIR.mkdir(parents=True)
                CHANGED_FILES.write_text(
                    json.dumps({"ts": "2026-05-18T00:02:00Z", "tool": "Edit",
                                "file": "src/session_browser/web/static/style.css",
                                "category": "ui-css", "requiresQualityGate": True}) + "\n"
                )
                art = _make_artifact("PASS", finished="2026-05-18T00:01:00Z")
                (QUALITY_DIR / "test" / "quality-gate-summary.json").parent.mkdir(parents=True, exist_ok=True)
                (QUALITY_DIR / "test" / "quality-gate-summary.json").write_text(json.dumps(art))
                status, msgs = run_check("test")
                assert status == "FAIL", f"Expected FAIL (stale), got {status}"
            finally:
                CHANGED_FILES, QUALITY_DIR = old_cf, old_qd

    def _t5_ui_artifact_pass_fresh():
        """UI file changed, artifact PASS and fresh => PASS."""
        with tempfile.TemporaryDirectory() as td:
            global CHANGED_FILES, QUALITY_DIR
            old_cf, old_qd = CHANGED_FILES, QUALITY_DIR
            try:
                CHANGED_FILES = Path(td) / "changed-files.jsonl"
                QUALITY_DIR = Path(td) / "quality"
                QUALITY_DIR.mkdir(parents=True)
                CHANGED_FILES.write_text(
                    json.dumps({"ts": "2026-05-18T00:00:00Z", "tool": "Edit",
                                "file": "src/session_browser/web/static/style.css",
                                "category": "ui-css", "requiresQualityGate": True}) + "\n"
                )
                art = _make_artifact("PASS", finished="2026-05-18T00:01:00Z")
                (QUALITY_DIR / "test" / "quality-gate-summary.json").parent.mkdir(parents=True, exist_ok=True)
                (QUALITY_DIR / "test" / "quality-gate-summary.json").write_text(json.dumps(art))
                status, msgs = run_check("test")
                assert status == "PASS", f"Expected PASS, got {status}"
            finally:
                CHANGED_FILES, QUALITY_DIR = old_cf, old_qd

    def _t6_docs_only():
        """Only docs changed => PASS."""
        with tempfile.TemporaryDirectory() as td:
            global CHANGED_FILES, QUALITY_DIR
            old_cf, old_qd = CHANGED_FILES, QUALITY_DIR
            try:
                CHANGED_FILES = Path(td) / "changed-files.jsonl"
                QUALITY_DIR = Path(td) / "quality"
                CHANGED_FILES.write_text(
                    json.dumps({"ts": "2026-05-18T00:00:00Z", "tool": "Edit",
                                "file": "README.md",
                                "category": "other", "requiresQualityGate": False}) + "\n"
                )
                status, msgs = run_check("test")
                assert status == "PASS", f"Expected PASS, got {status}"
            finally:
                CHANGED_FILES, QUALITY_DIR = old_cf, old_qd

    def _t7_unknown_change_id():
        """unknown change ID still checks .agent/quality/unknown."""
        with tempfile.TemporaryDirectory() as td:
            global CHANGED_FILES, QUALITY_DIR
            old_cf, old_qd = CHANGED_FILES, QUALITY_DIR
            try:
                CHANGED_FILES = Path(td) / "changed-files.jsonl"
                QUALITY_DIR = Path(td) / "quality"
                CHANGED_FILES.write_text(
                    json.dumps({"ts": "2026-05-18T00:00:00Z", "tool": "Edit",
                                "file": "src/session_browser/web/static/style.css",
                                "category": "ui-css", "requiresQualityGate": True}) + "\n"
                )
                status, msgs = run_check("unknown")
                # No artifact for "unknown" => FAIL
                assert status == "FAIL", f"Expected FAIL, got {status}"
            finally:
                CHANGED_FILES, QUALITY_DIR = old_cf, old_qd

    _run("no changed-files => PASS", _t1_no_changed_files)
    _run("UI changed, artifact missing => FAIL", _t2_ui_missing_artifact)
    _run("UI changed, artifact FAIL => FAIL", _t3_ui_artifact_fail)
    _run("UI changed, artifact stale => FAIL", _t4_ui_artifact_stale)
    _run("UI changed, artifact PASS fresh => PASS", _t5_ui_artifact_pass_fresh)
    _run("docs only changed => PASS", _t6_docs_only)
    _run("unknown change ID checks quality/unknown", _t7_unknown_change_id)

    if failures:
        print(f"\n{failures} test(s) failed")
        sys.exit(1)
    else:
        print(f"\nAll self-tests passed")
        sys.exit(0)


def main():
    parser = argparse.ArgumentParser(description="Stop hook quality gate")
    parser.add_argument("--change-id", default=None, help="Override change ID")
    parser.add_argument("--self-test", action="store_true", help="Run self-tests")
    args = parser.parse_args()

    if args.self_test:
        _self_test()
        return

    status, messages = run_check(args.change_id)

    for msg in messages:
        print(msg, file=sys.stderr if status == "FAIL" else sys.stdout)

    if status == "FAIL":
        sys.exit(1)


if __name__ == "__main__":
    main()
