"""本模块负责构造不携带 provider 私有变量的子进程环境。

不负责解释 Gate 状态或业务规则；由 runtime process 和 executor 调用。
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

PROVIDER_ENV_PREFIXES = ('CODEX_', 'QODER_', 'CLAUDE_')


def sanitized_environment(
    overrides: Mapping[str, str | None] | None = None,
    *,
    base: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """合并环境覆盖值，并移除 provider 私有变量。"""
    source = os.environ if base is None else base
    result = {str(key): str(value) for key, value in source.items()}
    for key, value in (overrides or {}).items():
        if value is None:
            result.pop(str(key), None)
        else:
            result[str(key)] = str(value)
    for key in tuple(result):
        if key.startswith(PROVIDER_ENV_PREFIXES):
            result.pop(key, None)
    return result
