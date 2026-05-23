from __future__ import annotations

from dataclasses import dataclass, field
import json
import sys
from typing import Any


# 01. Hook 输出模型
@dataclass
class HookResult:
    status: str = "PASS"
    exit_code: int = 0
    message: str = ""
    warnings: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)


# 02. 输出函数
def emit(result: HookResult) -> int:
    payload = {
        "status": result.status,
        "message": result.message,
        "warnings": result.warnings,
        "details": result.details,
    }
    # Claude hook 输出保持简洁，避免污染上下文。
    if result.status != "PASS" or result.message or result.warnings:
        print(json.dumps(payload, ensure_ascii=False), file=sys.stderr if result.exit_code else sys.stdout)
    return result.exit_code
