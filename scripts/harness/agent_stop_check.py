#!/usr/bin/env python3
"""Shared stop gate for Claude Code, Codex, and Qoder entrypoints."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

AGENT_LOG_DIR = REPO_ROOT / "tmp" / "agent_logs" / "current"
CHANGED_FILES = AGENT_LOG_DIR / "changed-files.jsonl"
SESSION_ID_FILE = AGENT_LOG_DIR / "session-id.txt"
STOP_SUMMARY = AGENT_LOG_DIR / "stop-check-summary.json"

LOCAL_ONLY_PATHS = [
    ".claude/settings.local.json",
    ".mcp.json",
    ".env",
    "data",
    "output",
    ".venv",
    ".pytest_cache",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json_stdin() -> dict[str, Any]:
    try:
        text = sys.stdin.read()
    except Exception:
        return {}
    if not text.strip():
        return {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _session_id_from_context(ctx: dict[str, Any]) -> str | None:
    sid = ctx.get("session_id") or ctx.get("sessionId")
    if isinstance(sid, str) and sid:
        return sid
    if SESSION_ID_FILE.exists():
        value = SESSION_ID_FILE.read_text(encoding="utf-8").strip()
        return value or None
    return None


def _normalize(path: str) -> str:
    value = path.replace("\\", "/").strip()
    while value.startswith("./"):
        value = value[2:]
    return value.strip("/")


def _dedupe(paths: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for path in paths:
        normalized = _normalize(path)
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def read_recorded_changed_files(session_id: str | None) -> list[str]:
    if not CHANGED_FILES.exists():
        return []

    files: list[str] = []
    for line in CHANGED_FILES.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if session_id and record.get("sessionId") != session_id:
            continue
        file_path = record.get("file") or record.get("file_path")
        if isinstance(file_path, str) and file_path:
            files.append(file_path)
    return _dedupe(files)


def parse_git_status_paths(output: str) -> list[str]:
    files: list[str] = []
    for line in output.splitlines():
        if not line.strip() or len(line) < 4:
            continue
        path_text = line[3:].strip()
        if not path_text:
            continue
        if " -> " in path_text:
            files.extend(part.strip().strip('"') for part in path_text.split(" -> ", 1))
        else:
            files.append(path_text.strip('"'))
    return _dedupe(files)


def read_git_dirty_files() -> list[str]:
    try:
        proc = subprocess.run(
            ["git", "status", "--short", "--untracked-files=all"],
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=30,
        )
    except Exception:
        return []
    if proc.returncode != 0:
        return []
    return parse_git_status_paths(proc.stdout or "")


def collect_changed_files(session_id: str | None) -> list[str]:
    # changed-files.jsonl is precise for Write/Edit hooks; git status catches
    # shell-based deletions and non-Claude agents that do not emit that JSONL.
    return _dedupe(read_recorded_changed_files(session_id) + read_git_dirty_files())


def check_local_only_status() -> list[str]:
    try:
        proc = subprocess.run(
            ["git", "status", "--short", "--", *LOCAL_ONLY_PATHS],
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=30,
        )
    except Exception:
        return []
    lines = [line for line in (proc.stdout or "").splitlines() if line.strip()]
    return lines if proc.returncode == 0 else []


def resolve_change_id() -> str:
    env = os.environ.get("ACTIVE_CHANGE_ID", "")
    if env:
        return env
    active_change = REPO_ROOT / "tmp" / "active_change.json"
    if active_change.exists():
        try:
            data = json.loads(active_change.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return "unknown"
        cid = data.get("change_id", "")
        if isinstance(cid, str) and cid:
            return cid
    return "unknown"


def run_step(name: str, cmd: list[str]) -> bool:
    print(f"[agent_stop_check] running {name}: {' '.join(cmd)}", file=sys.stderr)
    try:
        proc = subprocess.run(cmd, cwd=REPO_ROOT)
    except Exception as exc:
        print(f"[agent_stop_check] {name} failed to start: {exc}", file=sys.stderr)
        return False
    if proc.returncode != 0:
        print(f"[agent_stop_check] {name} failed: exit={proc.returncode}", file=sys.stderr)
        return False
    return True


def task_ledger_warnings() -> list[str]:
    ledger = REPO_ROOT / "tmp" / "task-ledger.md"
    if not ledger.exists():
        return []
    text = ledger.read_text(encoding="utf-8", errors="ignore")
    if "| ID " in text or "|ID" in text:
        return []
    return ["tmp/task-ledger.md 表头格式不正确"]


def required_targets(changed_files: list[str]) -> list[str]:
    from scripts.claude_hooks.classify import required_quality_targets

    return required_quality_targets(changed_files)


def write_summary(
    *,
    agent: str,
    read_only: bool,
    status: str,
    changed_files: list[str],
    targets: list[str],
    failures: list[str],
    warnings: list[str],
) -> None:
    AGENT_LOG_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "schemaVersion": 2,
        "ts": utc_now(),
        "agent": agent,
        "readOnly": read_only,
        "status": status,
        "changeId": resolve_change_id(),
        "changedFiles": changed_files,
        "requiredTargets": targets,
        "blockingFailures": failures,
        "warnings": warnings,
    }
    STOP_SUMMARY.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run shared agent stop checks.")
    parser.add_argument("--agent", default="unknown", help="Agent entrypoint name")
    args = parser.parse_args()

    AGENT_LOG_DIR.mkdir(parents=True, exist_ok=True)
    ctx = _read_json_stdin()
    session_id = _session_id_from_context(ctx)
    changed_files = collect_changed_files(session_id)
    targets = required_targets(changed_files)
    warnings = check_local_only_status() + task_ledger_warnings()
    failures: list[str] = []

    if not changed_files:
        status = "WARN" if warnings else "PASS"
        write_summary(
            agent=args.agent,
            read_only=True,
            status=status,
            changed_files=[],
            targets=[],
            failures=[],
            warnings=warnings,
        )
        if warnings:
            for warning in warnings:
                print(f"[agent_stop_check] WARN {warning}", file=sys.stderr)
            return 1
        print("[agent_stop_check] PASS read-only session", file=sys.stderr)
        return 0

    change_id = resolve_change_id()
    print(f"[agent_stop_check] changed files: {len(changed_files)}", file=sys.stderr)
    print(
        "[agent_stop_check] required targets: "
        + (", ".join(sorted(targets)) if targets else "(none)"),
        file=sys.stderr,
    )

    if not run_step("openspec-stop-validate", [sys.executable, "scripts/agent_hooks/stop_validate_change.py"]):
        failures.append("stop_validate_change.py failed")

    changed_json = json.dumps(changed_files, ensure_ascii=False)
    if not run_step(
        "required-quality-gates",
        [
            sys.executable,
            "scripts/quality/run_required_quality_gates.py",
            "--include-session-detail",
            "--change-id",
            change_id,
            "--changed-files",
            changed_json,
        ],
    ):
        failures.append("run_required_quality_gates.py failed")

    status = "FAIL" if failures else ("WARN" if warnings else "PASS")
    write_summary(
        agent=args.agent,
        read_only=False,
        status=status,
        changed_files=changed_files,
        targets=targets,
        failures=failures,
        warnings=warnings,
    )

    for warning in warnings:
        print(f"[agent_stop_check] WARN {warning}", file=sys.stderr)
    for failure in failures:
        print(f"[agent_stop_check] BLOCK {failure}", file=sys.stderr)

    if failures:
        return 2
    return 1 if warnings else 0


if __name__ == "__main__":
    raise SystemExit(main())
