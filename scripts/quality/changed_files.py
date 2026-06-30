"""Shared changed-file collection for agent and quality-gate entrypoints."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
AGENT_LOG_DIR = REPO_ROOT / 'tmp' / 'agent_logs' / 'current'
DEFAULT_CHANGED_FILES = AGENT_LOG_DIR / 'changed-files.jsonl'
DEFAULT_SESSION_ID_FILE = AGENT_LOG_DIR / 'session-id.txt'
DEFAULT_BASE_COMMIT_FILE = AGENT_LOG_DIR / 'base-commit.txt'

GIT_STATUS_PATH_OFFSET = 3
GIT_STATUS_MIN_LINE_LENGTH = GIT_STATUS_PATH_OFFSET + 1


def normalize_path(path: str) -> str:
    """Normalize a repository-relative path for target matching."""
    value = path.replace('\\', '/').strip()
    while value.startswith('./'):
        value = value[2:]
    return value.strip('/')


def dedupe_paths(paths: list[str]) -> list[str]:
    """Return normalized paths once while preserving first-seen order."""
    result: list[str] = []
    seen: set[str] = set()
    for path in paths:
        normalized = normalize_path(path)
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def read_session_id(session_id_file: Path = DEFAULT_SESSION_ID_FILE) -> str | None:
    """Read an agent session id from disk when present."""
    if not session_id_file.exists():
        return None
    value = session_id_file.read_text(encoding='utf-8').strip()
    return value or None


def read_recorded_changed_files(
    session_id: str | None = None,
    changed_files_path: Path = DEFAULT_CHANGED_FILES,
    agent_id: str | None = None,
) -> list[str]:
    """Read changed-file records written by agent hooks.

    Args:
        session_id: Optional session id used to filter hook records.
        changed_files_path: Path to the changed-files JSONL file.
        agent_id: Optional agent id used to filter records to a specific agent.
    """
    if not changed_files_path.exists():
        return []

    files: list[str] = []
    for raw_line in changed_files_path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            record: Any = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue
        if session_id and record.get('sessionId') != session_id:
            continue
        if agent_id:
            record_agent_id = record.get('agentId') or ''
            if record_agent_id != agent_id:
                continue
        file_path = record.get('file') or record.get('file_path')
        if isinstance(file_path, str) and file_path:
            files.append(file_path)
    return dedupe_paths(files)


def parse_git_status_paths(output: str) -> list[str]:
    """Extract changed paths from ``git status --short`` output."""
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
    return dedupe_paths(files)


def read_git_dirty_files(repo_root: Path = REPO_ROOT) -> list[str]:
    """Read dirty tracked, deleted, renamed, and untracked non-ignored files."""
    try:
        proc = subprocess.run(
            ['git', 'status', '--short', '--untracked-files=all'],
            cwd=repo_root,
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


def read_base_commit(base_commit_file: Path = DEFAULT_BASE_COMMIT_FILE) -> str | None:
    """Read the git commit recorded at agent session start."""
    if not base_commit_file.exists():
        return None
    value = base_commit_file.read_text(encoding='utf-8').strip()
    return value or None


def read_current_head(repo_root: Path = REPO_ROOT) -> str | None:
    """Read the current git HEAD commit hash."""
    try:
        proc = subprocess.run(
            ['git', 'rev-parse', 'HEAD'],
            cwd=repo_root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=30,
            check=False,
        )
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    value = (proc.stdout or '').strip()
    return value or None


def write_base_commit_if_missing(
    repo_root: Path = REPO_ROOT,
    base_commit_file: Path = DEFAULT_BASE_COMMIT_FILE,
    *,
    overwrite: bool = False,
) -> str | None:
    """Persist current HEAD as the session base commit."""
    existing = read_base_commit(base_commit_file)
    if existing and not overwrite:
        return existing

    head = read_current_head(repo_root)
    if not head:
        return None
    try:
        base_commit_file.parent.mkdir(parents=True, exist_ok=True)
        base_commit_file.write_text(head + '\n', encoding='utf-8')
    except OSError:
        return None
    return head


def read_files_since_base_commit(
    repo_root: Path = REPO_ROOT,
    base_commit_file: Path = DEFAULT_BASE_COMMIT_FILE,
) -> list[str]:
    """Read paths changed between the session base commit and current HEAD."""
    base_commit = read_base_commit(base_commit_file)
    if not base_commit:
        return []
    try:
        proc = subprocess.run(
            ['git', 'diff', '--name-only', '--diff-filter=ACMRD', f'{base_commit}..HEAD'],
            cwd=repo_root,
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
    return dedupe_paths([line for line in (proc.stdout or '').splitlines() if line.strip()])


def collect_changed_files(
    session_id: str | None = None,
    *,
    include_git: bool = True,
    repo_root: Path = REPO_ROOT,
    changed_files_path: Path = DEFAULT_CHANGED_FILES,
    base_commit_file: Path | None = None,
    agent_id: str | None = None,
) -> list[str]:
    """Collect hook-recorded and git-dirty files for fail-closed routing.

    Args:
        session_id: Optional session id used to filter hook records.
        include_git: Whether to include current git dirty files.
        repo_root: Repository root for git commands.
        changed_files_path: Path to the changed-files JSONL file.
        base_commit_file: Optional path to the base-commit file.
        agent_id: Optional agent id to filter hook records to a specific agent.
    """
    if base_commit_file is None:
        base_commit_file = changed_files_path.with_name(DEFAULT_BASE_COMMIT_FILE.name)
    paths = read_recorded_changed_files(session_id, changed_files_path, agent_id=agent_id)
    paths.extend(read_files_since_base_commit(repo_root, base_commit_file))
    if include_git:
        paths.extend(read_git_dirty_files(repo_root))
    return dedupe_paths(paths)


def parse_changed_files_json(value: str | None) -> list[str]:
    """Parse an optional JSON list of changed files."""
    if value is None:
        return []
    try:
        parsed: Any = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return dedupe_paths([item for item in parsed if isinstance(item, str)])
