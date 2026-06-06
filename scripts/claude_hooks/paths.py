from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import subprocess


# 01. 数据结构
@dataclass(frozen=True)
class RepoPaths:
    """仓库与运行态路径集合。"""

    repo_root: Path
    agent_log_dir: Path

    @property
    def changed_files(self) -> Path:
        return self.agent_log_dir / "changed-files.jsonl"

    @property
    def hook_events(self) -> Path:
        return self.agent_log_dir / "hook-events.jsonl"

    @property
    def command_events(self) -> Path:
        return self.agent_log_dir / "command-events.jsonl"

    @property
    def task_evidence_dir(self) -> Path:
        return self.agent_log_dir / "task-evidence"

    @property
    def quality_dir(self) -> Path:
        return self.agent_log_dir / "quality"

    @property
    def stop_summary(self) -> Path:
        return self.agent_log_dir / "stop-check-summary.json"

    @property
    def active_change(self) -> Path:
        return self.repo_root / "tmp" / "active_change.json"


# 02. 仓库根目录定位
def find_repo_root(start: str | Path | None = None) -> Path:
    """定位仓库根目录；失败时回退到当前目录。"""

    start_path = Path(start or os.getcwd()).resolve()
    try:
        out = subprocess.check_output(
            ["git", "-C", str(start_path), "rev-parse", "--show-toplevel"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        if out:
            return Path(out).resolve()
    except Exception:
        pass
    return start_path


# 02. 固定路径常量
AGENT_LOG_DIR_NAME = "current"
QUALITY_DIR_NAME = "quality"


def agent_log_dir(repo_root: Path) -> Path:
    """固定 agent 日志目录：tmp/agent_logs/current/"""
    return repo_root / "tmp" / "agent_logs" / AGENT_LOG_DIR_NAME


def quality_dir(repo_root: Path) -> Path:
    """固定 quality artifact 目录：tmp/quality/"""
    return repo_root / "tmp" / QUALITY_DIR_NAME


# 03. 运行态路径构造
def build_paths(repo_root: str | Path | None = None) -> RepoPaths:
    root = find_repo_root(repo_root)
    log_dir = agent_log_dir(root)
    return RepoPaths(repo_root=root, agent_log_dir=log_dir)


# 04. 目录初始化
def ensure_runtime_dirs(paths: RepoPaths) -> None:
    """只创建 tmp/agent_log 下的新运行态目录。"""

    for path in [
        paths.agent_log_dir,
        paths.task_evidence_dir,
        paths.quality_dir,
        paths.agent_log_dir / "config",
    ]:
        path.mkdir(parents=True, exist_ok=True)


# 05. 相对路径转换
def rel_to_repo(path: str | Path, repo_root: str | Path) -> str:
    p = Path(path)
    root = Path(repo_root).resolve()
    if not p.is_absolute():
        return str(p.as_posix()).lstrip("./")
    try:
        return str(p.resolve().relative_to(root).as_posix())
    except Exception:
        return str(p)
