"""Shared agent runtime helpers."""


from scripts.agent_runtime.policy import (
    is_protected_path,
    load_runtime_manifest,
    normalize_repo_path,
    protected_roots,
    repo_root,
)

from scripts.agent_runtime.identity import (
    RuntimeIdentity,
    agent_log_dir,
    identity_from_values,
    identity_requires_fail_closed,
    quality_dir,
    session_main_log_dir,
    session_root_dir,
)
__all__ = [
    'RuntimeIdentity',
    'identity_from_values',
    'session_root_dir',
    'session_main_log_dir',
    'agent_log_dir',
    'quality_dir',
    'identity_requires_fail_closed',
    'repo_root',
    'load_runtime_manifest',
    'protected_roots',
    'is_protected_path',
    'normalize_repo_path',
]
