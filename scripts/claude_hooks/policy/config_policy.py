from __future__ import annotations

from pathlib import Path
import json
from ..evidence import append_jsonl, utc_now
from ..hook_io import HookContext
from ..paths import RepoPaths, ensure_runtime_dirs


# 01. ConfigChange 记录
def record_config_change(paths: RepoPaths, ctx: HookContext) -> None:
    ensure_runtime_dirs(paths)
    record = {
        "schemaVersion": 1,
        "ts": utc_now(),
        "event": "config-change",
        "sessionId": ctx.session_id,
        "agentId": ctx.agent_id,
        "agentType": ctx.agent_type,
    }
    append_jsonl(paths.agent_log_dir / "config-change-log.jsonl", record)


# 02. settings.json 轻量校验
def validate_settings_json(repo_root: Path) -> tuple[bool, str]:
    path = repo_root / ".claude/settings.json"
    try:
        json.loads(path.read_text(encoding="utf-8"))
        return True, "settings.json JSON 格式有效。"
    except Exception as exc:
        return False, f"settings.json JSON 格式错误：{exc}"
