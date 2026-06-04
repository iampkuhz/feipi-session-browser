"""Agent Runtime 枚举和识别辅助。

Agent Runtime 表示会话浏览器检测到的 agent 运行时：
- claude_code
- codex
- qoder
- unknown
"""

from __future__ import annotations

AGENT_RUNTIME_VALUES = frozenset({"claude_code", "codex", "qoder", "unknown"})


def resolve_agent_runtime(agent_string: str) -> str:
    """从 agent 字符串解析 AgentRuntime。

    如果字符串不能识别，返回 "unknown"。
    """
    normalized = (agent_string or "").strip().lower()
    mapping = {
        "claude_code": "claude_code",
        "claude": "claude_code",
        "codex": "codex",
        "qoder": "qoder",
    }
    return mapping.get(normalized, "unknown")
