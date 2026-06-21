"""Emit Claude hook results with concise output semantics.

Hook handlers return ``HookResult`` objects. This module serializes non-pass, warning, or
message-bearing results as JSON and returns the requested process exit code. PASS without
messages stays silent to avoid polluting the agent context.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from typing import Any


# 01. Hook 输出模型
@dataclass
class HookResult:
    """Process-facing result produced by a Claude hook handler.

    Attributes:
        status: Hook status such as ``PASS`` or ``BLOCK``.
        exit_code: Process exit code returned to the shell wrapper.
        message: User-facing result message.
        warnings: Advisory messages emitted for allowed operations.
        details: Additional JSON-serializable metadata.
    """

    status: str = 'PASS'
    exit_code: int = 0
    message: str = ''
    warnings: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)


# 02. 输出函数
def emit(result: HookResult) -> int:
    """Serialize a hook result and return its process exit code.

    Args:
        result: Hook handler result with status, message, warnings, and details.

    Returns:
        Exit code consumed by the shell hook wrapper. Blocking policies use non-zero exit
        codes; silent PASS returns ``0``.
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
