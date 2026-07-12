"""Git 证据收集与 dirty 文件过滤。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.harness import stop_helpers


def collect_git_evidence(repo_root: Path, record: dict[str, Any]) -> dict[str, Any]:
    """委托 stop_helpers 收集 Git 证据。"""
    return stop_helpers.collect_git_evidence(repo_root, record)


def filter_baseline_dirty(
    changed_files: list[str],
    git_evidence: dict[str, Any],
) -> tuple[list[str], set[str]]:
    """排除 session 启动前已存在的 dirty 文件。

    返回 (过滤后的 changed_files, baseline_dirty_files 集合)。
    """
    baseline_dirty: set[str] = set()
    initial_dirty = git_evidence.get('initialDirtySnapshot')
    if isinstance(initial_dirty, dict):
        for f in initial_dirty.get('tracked') or []:
            baseline_dirty.add(f)
        for f in initial_dirty.get('untracked') or []:
            baseline_dirty.add(f)
        changed_files = [f for f in changed_files if f not in baseline_dirty]
    return changed_files, baseline_dirty
