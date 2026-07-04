"""提供 result 脚本能力。"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from typing import Any


# 01. Hook 输出模型
@dataclass
class HookResult:
    """汇总 HookResult 的检查结果。

    属性：
        status: 状态值。
        exit_code: exit code 参数。
        message: 用户可读消息。
        warnings: 警告列表。
        details: 附加 JSON metadata。
    """

    status: str = 'PASS'
    exit_code: int = 0
    message: str = ''
    warnings: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)


# 输出 hook 结果。
def emit(result: HookResult) -> int:
    """参数：
        result: hook handler 结果带状态, message, 警告, 和 details。

    返回：
        进程退出码。
    """
    payload = {
        'status': result.status,
        'message': result.message,
        'warnings': result.warnings,
        'details': result.details,
    }
    # Claude hook 输出保持简洁, 避免污染上下文。
    if result.status != 'PASS' or result.message or result.warnings:
        print(
            json.dumps(payload, ensure_ascii=False),
            file=sys.stderr if result.exit_code else sys.stdout,
        )
    return result.exit_code
