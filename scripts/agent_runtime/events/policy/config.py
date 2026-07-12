"""本模块负责记录配置变更证据，并校验仓库内 Claude settings JSON。

不负责平台 Hook wrapper 配置；由 Hook 或 Stop runtime 调用。"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from scripts.agent_runtime.paths import ensure_runtime_dirs

from ..evidence import append_jsonl, utc_now

if TYPE_CHECKING:
    from pathlib import Path

    from scripts.agent_runtime.context import HookContext
    from scripts.agent_runtime.paths import RepoPaths


# 记录配置 change。
def record_config_change(paths: RepoPaths, ctx: HookContext) -> None:
    """参数：
    paths: Repository 运行time 路径用于config evidence 输出。
    ctx: 已解析的Claude hook context带session 和 agent identifiers。
    """
    ensure_runtime_dirs(paths)
    record = {
        'schemaVersion': 1,
        'ts': utc_now(),
        'event': 'config-change',
        'client': paths.identity.client,
        'sessionId': ctx.session_id,
        'agentId': ctx.agent_id,
        'agentType': ctx.agent_type,
    }
    append_jsonl(paths.agent_log_dir / 'config-change-log.jsonl', record)


# 验证settings JSON。
def validate_settings_json(repo_root: Path) -> tuple[bool, str]:
    """参数：
        repo_root: 仓库根目录。

    返回：
        由success flag 和 user-facing diagnostic message. 无效 JSON 返回组成的 tuple。 ``false`` instead of raising so callers can 报告 controlled 失败项。
    """
    path = repo_root / '.claude/settings.json'
    try:
        json.loads(path.read_text(encoding='utf-8'))
        return True, 'settings.json JSON 格式有效。'
    except Exception as exc:
        return False, f'settings.json JSON 格式错误: {exc}'
