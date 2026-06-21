"""Record and validate Claude hook configuration changes.

The config-change hook records lightweight metadata when agent settings change. The JSON
validator is used by diagnostics to report malformed settings without mutating config
files or blocking unrelated hook events.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from ..evidence import append_jsonl, utc_now
from ..paths import ensure_runtime_dirs

if TYPE_CHECKING:
    from pathlib import Path

    from ..hook_io import HookContext
    from ..paths import RepoPaths


# 01. ConfigChange 记录
def record_config_change(paths: RepoPaths, ctx: HookContext) -> None:
    """Record a config-change hook event.

    Args:
        paths: Repository runtime paths for config evidence output.
        ctx: Parsed Claude hook context with session and agent identifiers.
    """
    ensure_runtime_dirs(paths)
    record = {
        'schemaVersion': 1,
        'ts': utc_now(),
        'event': 'config-change',
        'sessionId': ctx.session_id,
        'agentId': ctx.agent_id,
        'agentType': ctx.agent_type,
    }
    append_jsonl(paths.agent_log_dir / 'config-change-log.jsonl', record)


# 02. settings.json 轻量校验
def validate_settings_json(repo_root: Path) -> tuple[bool, str]:
    """Validate Claude settings JSON syntax for diagnostics.

    Args:
        repo_root: Repository root that contains ``.claude/settings.json``.

    Returns:
        Tuple of success flag and user-facing diagnostic message. Invalid JSON returns
        ``False`` instead of raising so callers can report a controlled failure.
    """
    path = repo_root / '.claude/settings.json'
    try:
        json.loads(path.read_text(encoding='utf-8'))
        return True, 'settings.json JSON 格式有效。'
    except Exception as exc:
        return False, f'settings.json JSON 格式错误: {exc}'
