#!/usr/bin/env python3
"""Shared stop gate for Claude Code, Codex, and Qoder entrypoints."""

from __future__ import annotations

import argparse
import importlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

AGENT_LOG_DIR = REPO_ROOT / 'tmp' / 'agent_logs' / 'current'
CHANGED_FILES = AGENT_LOG_DIR / 'changed-files.jsonl'
SESSION_ID_FILE = AGENT_LOG_DIR / 'session-id.txt'
STOP_SUMMARY = AGENT_LOG_DIR / 'stop-check-summary.json'

GIT_STATUS_PATH_OFFSET = 3
GIT_STATUS_MIN_LINE_LENGTH = GIT_STATUS_PATH_OFFSET + 1

LOCAL_ONLY_PATHS = [
    '.claude/settings.local.json',
    '.mcp.json',
    '.env',
    'data',
    'output',
    '.venv',
    '.pytest_cache',
]


def utc_now() -> str:
    """Return the current UTC timestamp for stop-check summaries.

    Returns:
        ISO-8601 timestamp string in UTC.
    """
    return datetime.now(timezone.utc).isoformat()


def _read_json_stdin() -> dict[str, Any]:
    """Read optional hook context JSON from standard input.

    Returns:
        Parsed JSON object, or an empty mapping when input is absent or invalid.
    """
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
    """Resolve the active agent session id from hook context or log state.

    Args:
        ctx: Hook context parsed from standard input.

    Returns:
        Session id when available; otherwise None.
    """
    sid = ctx.get('session_id') or ctx.get('sessionId')
    if isinstance(sid, str) and sid:
        return sid
    if SESSION_ID_FILE.exists():
        value = SESSION_ID_FILE.read_text(encoding='utf-8').strip()
        return value or None
    return None


def _normalize(path: str) -> str:
    """Normalize repository-relative paths for stable comparisons.

    Args:
        path: Raw path from hook logs or git output.

    Returns:
        Slash-normalized repository-relative path without leading dot segments.
    """
    value = path.replace('\\', '/').strip()
    while value.startswith('./'):
        value = value[2:]
    return value.strip('/')


def _dedupe(paths: list[str]) -> list[str]:
    """Return normalized paths once while preserving first-seen order.

    Args:
        paths: Raw path strings to normalize and deduplicate.

    Returns:
        Ordered unique normalized paths.
    """
    result: list[str] = []
    seen: set[str] = set()
    for path in paths:
        normalized = _normalize(path)
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def read_recorded_changed_files(session_id: str | None) -> list[str]:
    """Read changed files recorded by agent write hooks for the active session.

    Args:
        session_id: Optional session id used to filter hook records.

    Returns:
        Changed paths recorded for the session.
    """
    if not CHANGED_FILES.exists():
        return []

    files: list[str] = []
    for raw_line in CHANGED_FILES.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if session_id and record.get('sessionId') != session_id:
            continue
        file_path = record.get('file') or record.get('file_path')
        if isinstance(file_path, str) and file_path:
            files.append(file_path)
    return _dedupe(files)


def parse_git_status_paths(output: str) -> list[str]:
    """Extract normalized file paths from git short-status output.

    Args:
        output: Raw output from ``git status --short``.

    Returns:
        Normalized changed paths, including both sides of rename records.
    """
    files: list[str] = []
    for line in output.splitlines():
        if not line.strip() or len(line) < GIT_STATUS_MIN_LINE_LENGTH:
            continue
        path_text = line[GIT_STATUS_PATH_OFFSET:].strip()
        if not path_text:
            continue
        if ' -> ' in path_text:
            files.extend(part.strip().strip('"') for part in path_text.split(' -> ', 1))
        else:
            files.append(path_text.strip('"'))
    return _dedupe(files)


def read_git_dirty_files() -> list[str]:
    """Read files currently dirty in git so shell edits are included.

    Returns:
        Normalized dirty paths, or an empty list when git status is unavailable.
    """
    try:
        proc = subprocess.run(
            ['git', 'status', '--short', '--untracked-files=all'],
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=30,
            check=False,
        )
    except Exception:
        return []
    if proc.returncode != 0:
        return []
    return parse_git_status_paths(proc.stdout or '')


def collect_changed_files(session_id: str | None) -> list[str]:
    """Collect changed files from hook logs and git status for gate routing.

    Args:
        session_id: Optional session id used to filter hook records.

    Returns:
        Deduplicated paths from recorded hook writes and current git status.
    """
    # changed-files.jsonl is precise for Write/Edit hooks; git status catches
    # shell-based deletions and non-Claude agents that do not emit that JSONL.
    return _dedupe(read_recorded_changed_files(session_id) + read_git_dirty_files())


def check_local_only_status() -> list[str]:
    """Return dirty local-only paths that should block agent completion.

    Returns:
        Git short-status rows for local-only paths, or an empty list when clean.
    """
    try:
        proc = subprocess.run(
            ['git', 'status', '--short', '--', *LOCAL_ONLY_PATHS],
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=30,
            check=False,
        )
    except Exception:
        return []
    lines = [line for line in (proc.stdout or '').splitlines() if line.strip()]
    return lines if proc.returncode == 0 else []


def resolve_change_id() -> str:
    """Resolve the active OpenSpec change id for stop-check evidence.

    Returns:
        Active change id from the environment or active-change file, else ``unknown``.
    """
    env = os.environ.get('ACTIVE_CHANGE_ID', '')
    if env:
        return env
    active_change = REPO_ROOT / 'tmp' / 'active_change.json'
    if active_change.exists():
        try:
            data = json.loads(active_change.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, OSError):
            return 'unknown'
        cid = data.get('change_id', '')
        if isinstance(cid, str) and cid:
            return cid
    return 'unknown'


def run_step(name: str, cmd: list[str]) -> bool:
    """Run one blocking validation command and report whether it passed.

    Args:
        name: Human-readable step name for stderr diagnostics.
        cmd: Command argv to execute from the repository root.

    Returns:
        True when the command exits with status 0; otherwise False.
    """
    print(f'[agent_stop_check] running {name}: {" ".join(cmd)}', file=sys.stderr)
    try:
        proc = subprocess.run(cmd, cwd=REPO_ROOT, check=False)
    except Exception as exc:
        print(f'[agent_stop_check] {name} failed to start: {exc}', file=sys.stderr)
        return False
    if proc.returncode != 0:
        print(f'[agent_stop_check] {name} failed: exit={proc.returncode}', file=sys.stderr)
        return False
    return True


def task_ledger_warnings() -> list[str]:
    """Return non-blocking task-ledger format warnings for stop summaries.

    Returns:
        Warning messages for malformed task-ledger state.
    """
    ledger = REPO_ROOT / 'tmp' / 'task-ledger.md'
    if not ledger.exists():
        return []
    text = ledger.read_text(encoding='utf-8', errors='ignore')
    if '| ID ' in text or '|ID' in text:
        return []
    return ['tmp/task-ledger.md 表头格式不正确']


def required_targets(changed_files: list[str]) -> list[str]:
    """Map changed files to required quality targets using the hook classifier.

    Args:
        changed_files: Repository-relative paths changed in the session.

    Returns:
        Required quality target identifiers.
    """
    classifier = importlib.import_module('scripts.claude_hooks.classify')
    return classifier.required_quality_targets(changed_files)


@dataclass(frozen=True)
class StopSummary:
    """Structured payload fields written by the shared stop-check gate.

    Attributes:
        agent: Agent entrypoint name producing the summary.
        read_only: Whether the session made no repository changes.
        status: Stop-check status written for downstream adapters.
        changed_files: Changed repository paths considered by the gate.
        targets: Quality targets required for the changed files.
        failures: Blocking validation failures observed during stop checks.
        warnings: Non-blocking warnings captured for operator review.
    """

    agent: str
    read_only: bool
    status: str
    changed_files: list[str]
    targets: list[str]
    failures: list[str]
    warnings: list[str]


def write_summary(summary: StopSummary) -> None:
    """Persist stop-check evidence for agent adapters and later inspection.

    Args:
        summary: Stop-check payload fields to serialize.
    """
    AGENT_LOG_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        'schemaVersion': 2,
        'ts': utc_now(),
        'agent': summary.agent,
        'readOnly': summary.read_only,
        'status': summary.status,
        'changeId': resolve_change_id(),
        'changedFiles': summary.changed_files,
        'requiredTargets': summary.targets,
        'blockingFailures': summary.failures,
        'warnings': summary.warnings,
    }
    STOP_SUMMARY.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8'
    )


def main() -> int:
    """Run stop checks and return the shell exit code for the agent adapter.

    Returns:
        Process exit code for the invoking agent adapter.
    """
    parser = argparse.ArgumentParser(description='Run shared agent stop checks.')
    parser.add_argument('--agent', default='unknown', help='Agent entrypoint name')
    args = parser.parse_args()

    AGENT_LOG_DIR.mkdir(parents=True, exist_ok=True)
    ctx = _read_json_stdin()
    session_id = _session_id_from_context(ctx)
    changed_files = collect_changed_files(session_id)
    targets = required_targets(changed_files)
    warnings = check_local_only_status() + task_ledger_warnings()
    failures: list[str] = []

    if not changed_files:
        status = 'WARN' if warnings else 'PASS'
        write_summary(
            StopSummary(
                agent=args.agent,
                read_only=True,
                status=status,
                changed_files=[],
                targets=[],
                failures=[],
                warnings=warnings,
            )
        )
        if warnings:
            for warning in warnings:
                print(f'[agent_stop_check] WARN {warning}', file=sys.stderr)
            return 1
        print('[agent_stop_check] PASS read-only session', file=sys.stderr)
        return 0

    change_id = resolve_change_id()
    print(f'[agent_stop_check] changed files: {len(changed_files)}', file=sys.stderr)
    print(
        '[agent_stop_check] required targets: '
        + (', '.join(sorted(targets)) if targets else '(none)'),
        file=sys.stderr,
    )

    if not run_step(
        'openspec-stop-validate', [sys.executable, 'scripts/agent_hooks/stop_validate_change.py']
    ):
        failures.append('stop_validate_change.py failed')

    changed_json = json.dumps(changed_files, ensure_ascii=False)
    if not run_step(
        'required-quality-gates',
        [
            sys.executable,
            'scripts/quality/run_required_quality_gates.py',
            '--include-session-detail',
            '--change-id',
            change_id,
            '--changed-files',
            changed_json,
        ],
    ):
        failures.append('run_required_quality_gates.py failed')

    status = 'FAIL' if failures else ('WARN' if warnings else 'PASS')
    write_summary(
        StopSummary(
            agent=args.agent,
            read_only=False,
            status=status,
            changed_files=changed_files,
            targets=targets,
            failures=failures,
            warnings=warnings,
        )
    )

    for warning in warnings:
        print(f'[agent_stop_check] WARN {warning}', file=sys.stderr)
    for failure in failures:
        print(f'[agent_stop_check] BLOCK {failure}', file=sys.stderr)

    if failures:
        return 2
    return 1 if warnings else 0


if __name__ == '__main__':
    raise SystemExit(main())
