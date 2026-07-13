"""定义 Agent Runtime 的仓库根解析与证据目录布局。

本模块是运行时路径的唯一真相源；它不解析 Hook payload、不修改 Registry，
也不执行 Hook 或 Stop。

不负责平台 Hook wrapper 配置；由 Hook 或 Stop runtime 调用。"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from scripts.agent_runtime.identity import RuntimeIdentity, identity_from_values


@dataclass(frozen=True)
class RepoPaths:
    """保存 `RepoPaths` 的结构化契约数据；字段由所属运行阶段构造并由后续报告读取。"""

    repo_root: Path
    agent_log_dir: Path
    identity: RuntimeIdentity = field(
        default_factory=lambda: identity_from_values(
            agent_client='unknown', session_id='', agent_id=''
        )
    )

    # 维护changed-files 文件。
    @property
    def changed_files(self) -> Path:
        """返回：
        解析后的 HookContext；失败时携带 parse_error。
        """
        return self.agent_log_dir / 'changed-files.jsonl'

    # 维护session id 文件。
    @property
    def session_id_file(self) -> Path:
        """返回：
        解析后的 HookContext；失败时携带 parse_error。
        """
        return self.agent_log_dir / 'session-id.txt'

    # 维护base commit。
    @property
    def base_commit(self) -> Path:
        """返回：
        解析后的 HookContext；失败时携带 parse_error。
        """
        return self.agent_log_dir / 'base-commit.txt'

    # 维护hook event。
    @property
    def hook_events(self) -> Path:
        """返回：
        解析后的 HookContext；失败时携带 parse_error。
        """
        return self.agent_log_dir / 'hook-events.jsonl'

    # 维护任务 evidence 目录。
    @property
    def task_evidence_dir(self) -> Path:
        """返回：
        解析后的 HookContext；失败时携带 parse_error。
        """
        return self.agent_log_dir / 'task-evidence'

    # 维护quality 目录。
    @property
    def quality_dir(self) -> Path:
        """返回：
        解析后的 HookContext；失败时携带 parse_error。
        """
        return quality_dir(self.repo_root, self.identity)

    # 维护active change。
    @property
    def active_change(self) -> Path:
        """返回：
        解析后的 HookContext；失败时携带 parse_error。
        """
        return self.active_change_candidates[0]

    # 维护active change 候选项。
    @property
    def active_change_candidates(self) -> list[Path]:
        """返回：
        结果列表。
        """
        repo_openspec = self.repo_root / 'openspec' / 'active_change.json'
        if not self.identity.has_session:
            return [repo_openspec, legacy_active_change_path(self.repo_root)]
        session_main = session_main_log_dir(self.repo_root, self.identity) / 'active_change.json'
        if self.identity.is_agent:
            return [self.agent_log_dir / 'active_change.json', session_main, repo_openspec]
        return [session_main, repo_openspec]


def find_repo_root(start: str | Path | None = None) -> Path:
    """参数：
        start: 可选路径 used as starting point用于git root detection。

    返回：
        解析后的 HookContext；失败时携带 parse_error。
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


QUALITY_DIR_NAME = 'quality'


def legacy_active_change_path(repo_root: Path) -> Path:
    """参数：
        repo_root: 仓库根目录。

    返回：
        解析后的 HookContext；失败时携带 parse_error。
    """
    return repo_root / 'tmp' / 'active_change.json'


# 维护session 根目录 目录。
def session_root_dir(repo_root: Path, identity: RuntimeIdentity) -> Path:
    """参数：
        repo_root: 仓库根目录。
        identity: 当前 hook 运行time identity。

    返回：
        解析后的 HookContext；失败时携带 parse_error。
    """
    return repo_root / 'tmp' / 'agent_logs' / identity.client / identity.session_id


# 返回运行级根目录。
def run_root_dir(repo_root: Path, identity: RuntimeIdentity) -> Path:
    """参数：
        repo_root: 仓库根目录。
        identity: 当前 hook 运行时 identity。

    返回：
        当前运行的根目录。
    """
    base = session_root_dir(repo_root, identity)
    if identity.has_run:
        return base / 'runs' / identity.run_id
    return base


# 返回主 session 日志目录。
def session_main_log_dir(repo_root: Path, identity: RuntimeIdentity) -> Path:
    """参数：
        repo_root: 仓库根目录。
        identity: 当前 hook 运行time identity。

    返回：
        解析后的 HookContext；失败时携带 parse_error。
    """
    return run_root_dir(repo_root, identity) / 'main'


# 维护agent log 目录。
def agent_log_dir(repo_root: Path, identity: RuntimeIdentity | None = None) -> Path:
    """参数：
        repo_root: repo root 路径。
        identity: 当前 hook 运行time identity。

    返回：
        运行time 日志 目录用于当前 hook session。
    """
    identity = identity or identity_from_values()
    if identity.is_agent:
        return run_root_dir(repo_root, identity) / 'agents' / identity.agent_id
    return session_main_log_dir(repo_root, identity)


# 维护session log 目录。
def session_log_dirs(
    repo_root: Path,
    identity: RuntimeIdentity,
    *,
    include_agents: bool = False,
) -> list[Path]:
    """参数：
        repo_root: 仓库根目录。
        identity: 当前 hook 运行time identity。
        include_agents: 是否包含 agent 目录。

    返回：
        结果列表。
    """
    if identity.is_agent:
        return [agent_log_dir(repo_root, identity)]
    dirs = [session_main_log_dir(repo_root, identity)]
    if include_agents:
        agents_root = run_root_dir(repo_root, identity) / 'agents'
        if agents_root.exists():
            dirs.extend(sorted(p for p in agents_root.iterdir() if p.is_dir()))
    return dirs


# 维护quality 目录。
def quality_dir(repo_root: Path, identity: RuntimeIdentity | None = None) -> Path:
    """参数：
        repo_root: repo root 路径。
        identity: 当前 hook 运行time identity。

    返回：
        路径到 ``tmp/quality``。
    """
    identity = identity or identity_from_values()
    base = repo_root / 'tmp' / QUALITY_DIR_NAME / identity.client / identity.session_id
    if identity.has_run:
        base = base / 'runs' / identity.run_id
    if identity.is_agent:
        return base / 'agents' / identity.agent_id
    return base / 'main'


# 构建路径。
def build_paths(
    repo_root: str | Path | None = None,
    identity: RuntimeIdentity | None = None,
) -> RepoPaths:
    """参数：
        repo_root: 可选repo root override用于tests。
        identity: 当前 hook 运行time identity。

    返回：
        ``RepoPaths`` containing repo root 和 当前 agent 日志 目录。
    """
    root = find_repo_root(repo_root)
    resolved_identity = identity or identity_from_values()
    log_dir = agent_log_dir(root, resolved_identity)
    return RepoPaths(repo_root=root, agent_log_dir=log_dir, identity=resolved_identity)


# 确保runtime 目录。
def ensure_runtime_dirs(paths: RepoPaths) -> None:
    """参数：
    paths: Repository 运行time 路径 whose 日志 目录 should exist。
    """
    for path in [
        paths.agent_log_dir,
        paths.task_evidence_dir,
        paths.quality_dir,
        paths.agent_log_dir / 'config',
    ]:
        path.mkdir(parents=True, exist_ok=True)


# 维护相对 repo。
def rel_to_repo(path: str | Path, repo_root: str | Path) -> str:
    """参数：
        path: Absolute 或 relative 路径从hook 输入。
        repo_root: 用于把绝对路径转为相对路径的 repo root。

    返回：
        repository-relative POSIX 路径, 或 original absolute 路径 字符串 当 the。 输入 is outside repository。
    """
    p = Path(path)
    root = Path(repo_root).resolve()
    if not p.is_absolute():
        return str(p.as_posix()).lstrip('./')
    try:
        return str(p.resolve().relative_to(root).as_posix())
    except Exception:
        return str(p)
