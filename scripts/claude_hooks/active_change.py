from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime, timezone
from .paths import RepoPaths


# 01. 默认 change-id
def default_change_id() -> str:
    """没有 active_change 时使用稳定的日期型 change-id。"""

    return "adhoc-" + datetime.now(timezone.utc).strftime("%Y%m%d")


# 02. JSON 安全读取
def _read_json(path: Path) -> dict:
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}
    return {}


# 03. active_change 读取：新路径优先，legacy 只读兼容。
def read_active_change(paths: RepoPaths) -> dict:
    data = _read_json(paths.active_change)
    if data:
        return data
    legacy = _read_json(paths.legacy_active_change)
    if legacy:
        legacy = dict(legacy)
        legacy["legacySource"] = ".agent/active_change.json"
        return legacy
    return {"changeId": default_change_id(), "source": "default"}


# 04. change-id 提取
def current_change_id(paths: RepoPaths) -> str:
    data = read_active_change(paths)
    return str(data.get("changeId") or data.get("change_id") or default_change_id())
