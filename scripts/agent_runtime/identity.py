"""Cross-platform runtime identity helpers for Claude/Codex/Qoder.

This module is the shared contract for deriving runtime evidence paths.  The
implementation intentionally reuses the existing hook path primitives so hook
wrappers can migrate without changing the directory layout.
"""

from __future__ import annotations

from scripts.claude_hooks.paths import (
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
]
