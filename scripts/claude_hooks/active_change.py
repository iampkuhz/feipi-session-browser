"""提供 active change 脚本能力。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

    from .paths import RepoPaths


# 维护默认 change id。
def default_change_id() -> str:
    """返回：
        default change id 字符串。
    """
    return 'adhoc-' + datetime.now(timezone.utc).strftime('%Y%m%d')


# 读取JSON。
def _read_json(path: Path) -> dict[str, Any]:
    """参数：
        path: JSON 文件到读取。

    返回：
        结果映射。
    """
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding='utf-8'))
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}
    return {}


# 读取active change。
def read_active_change(paths: RepoPaths) -> dict[str, Any]:
    """参数：
        paths: 待检查的路径列表。

    返回：
        结果映射。
    """
    for candidate in paths.active_change_candidates:
        data = _read_json(candidate)
        if data:
            return data
    return {'changeId': default_change_id(), 'source': 'default'}


# 维护当前 change id。
def current_change_id(paths: RepoPaths) -> str:
    """参数：
        paths: 待检查的路径列表。

    返回：
        current change id 字符串。
    """
    data = read_active_change(paths)
    return str(data.get('changeId') or data.get('change_id') or default_change_id())
