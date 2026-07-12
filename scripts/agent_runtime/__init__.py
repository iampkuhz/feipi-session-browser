"""本模块负责三平台共享的 Agent Runtime 身份、路径与 Hook 基础能力。

不负责平台 Hook wrapper 配置；由 Hook 或 Stop runtime 调用。"""

from scripts.agent_runtime.identity import RuntimeIdentity, identity_from_values
from scripts.agent_runtime.paths import (
    agent_log_dir,
    quality_dir,
    session_main_log_dir,
    session_root_dir,
)
from scripts.agent_runtime.policy import (
    is_protected_path,
    load_runtime_manifest,
    normalize_repo_path,
    protected_roots,
    repo_root,
)

__all__ = [
    'RuntimeIdentity',
    'agent_log_dir',
    'identity_from_values',
    'is_protected_path',
    'load_runtime_manifest',
    'normalize_repo_path',
    'protected_roots',
    'quality_dir',
    'repo_root',
    'session_main_log_dir',
    'session_root_dir',
]
