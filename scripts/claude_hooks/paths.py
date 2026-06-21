"""Build repository and runtime paths for Claude hook evidence.

Hook handlers use this module to locate the repository root, current agent log files,
and active change metadata. Directory creation is limited to runtime artifact paths under
``tmp`` so hook setup does not modify product sources.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


# 01. 数据结构
@dataclass(frozen=True)
class RepoPaths:
    """Repository root and hook runtime paths used by event handlers.

    Attributes:
        repo_root: Resolved repository root.
        agent_log_dir: Current runtime directory for hook JSONL evidence.
    """

    repo_root: Path
    agent_log_dir: Path

    @property
    def changed_files(self) -> Path:
        """Return the JSONL path that stores post-write file evidence."""
        return self.agent_log_dir / 'changed-files.jsonl'

    @property
    def hook_events(self) -> Path:
        """Return the JSONL path that stores hook lifecycle events."""
        return self.agent_log_dir / 'hook-events.jsonl'

    @property
    def command_events(self) -> Path:
        """Return the JSONL path reserved for command event evidence."""
        return self.agent_log_dir / 'command-events.jsonl'

    @property
    def task_evidence_dir(self) -> Path:
        """Return the directory that stores per-change evidence JSONL files."""
        return self.agent_log_dir / 'task-evidence'

    @property
    def quality_dir(self) -> Path:
        """Return the directory for hook-local quality artifacts."""
        return self.agent_log_dir / 'quality'

    @property
    def stop_summary(self) -> Path:
        """Return the stop-hook summary JSON path."""
        return self.agent_log_dir / 'stop-check-summary.json'

    @property
    def active_change(self) -> Path:
        """Return the active OpenSpec change metadata path."""
        return self.repo_root / 'tmp' / 'active_change.json'


# 02. 仓库根目录定位
def find_repo_root(start: str | Path | None = None) -> Path:
    """Locate the repository root for a hook event.

    Args:
        start: Optional path used as the starting point for git root detection.

    Returns:
        Git repository root when available, otherwise the resolved starting path. The
        fallback keeps hooks usable in tests and partial checkouts.
    """
    start_path = Path.cwd() if start is None else Path(start).resolve()
    try:
        out = subprocess.check_output(
            ['git', '-C', str(start_path), 'rev-parse', '--show-toplevel'],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        if out:
            return Path(out).resolve()
    except Exception:
        pass
    return start_path


# 02. 固定路径常量
AGENT_LOG_DIR_NAME = 'current'
QUALITY_DIR_NAME = 'quality'


def agent_log_dir(repo_root: Path) -> Path:
    """Return the current agent log directory under ``tmp/agent_logs``.

    Args:
        repo_root: Repository root path.

    Returns:
        Runtime log directory for the current hook session.
    """
    return repo_root / 'tmp' / 'agent_logs' / AGENT_LOG_DIR_NAME


def quality_dir(repo_root: Path) -> Path:
    """Return the repository-level quality artifact directory under ``tmp``.

    Args:
        repo_root: Repository root path.

    Returns:
        Path to ``tmp/quality``.
    """
    return repo_root / 'tmp' / QUALITY_DIR_NAME


# 03. 运行态路径构造
def build_paths(repo_root: str | Path | None = None) -> RepoPaths:
    """Build all paths needed by Claude hook handlers.

    Args:
        repo_root: Optional repository root override for tests.

    Returns:
        ``RepoPaths`` containing the repository root and current agent log directory.
    """
    root = find_repo_root(repo_root)
    log_dir = agent_log_dir(root)
    return RepoPaths(repo_root=root, agent_log_dir=log_dir)


# 04. 目录初始化
def ensure_runtime_dirs(paths: RepoPaths) -> None:
    """Create hook runtime directories before writing evidence.

    Args:
        paths: Repository runtime paths whose log directories should exist.
    """
    for path in [
        paths.agent_log_dir,
        paths.task_evidence_dir,
        paths.quality_dir,
        paths.agent_log_dir / 'config',
    ]:
        path.mkdir(parents=True, exist_ok=True)


# 05. 相对路径转换
def rel_to_repo(path: str | Path, repo_root: str | Path) -> str:
    """Convert a tool-supplied path to a repository-relative path when possible.

    Args:
        path: Absolute or relative path from hook input.
        repo_root: Repository root used to relativize absolute paths.

    Returns:
        Repository-relative POSIX path, or the original absolute path string when the
        input is outside the repository.
    """
    p = Path(path)
    root = Path(repo_root).resolve()
    if not p.is_absolute():
        return str(p.as_posix()).lstrip('./')
    try:
        return str(p.resolve().relative_to(root).as_posix())
    except Exception:
        return str(p)
