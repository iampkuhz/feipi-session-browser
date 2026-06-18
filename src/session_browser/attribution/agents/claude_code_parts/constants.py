"""Claude Code 归因构建器常量。"""

from __future__ import annotations

# Bucket classification keys for normalization.
MEASURED_BUCKET_KEYS = frozenset({
    "current_user_message",
    "preceding_tool_results",
    "full_messages_array",
})
ESTIMATED_BUCKET_KEYS = frozenset({
    "local_instruction_context",
    "agent_subagent_prompt",
    "mcp_tool_metadata",
})
HEURISTIC_FIXED_KEYS = frozenset({
    "hidden_builtin_system_estimate",
    "tool_definitions",
})
HEURISTIC_SCALED_KEYS = frozenset({
    "top_level_system_estimate",
})
NORMALIZATION_NOTE = (
    "定位率包含推断 bucket；不是 raw request 精确还原。"
)

# Built-in tool descriptions for Claude Code common tools.
TOOL_DESCRIPTIONS = {
    "Read": "读取文件内容。",
    "Write": "写入文件内容，创建新文件。",
    "Edit": "对文件进行精确的局部修改。",
    "Bash": "执行 shell 命令。",
    "Grep": "在文件中搜索文本。",
    "Glob": "按模式匹配查找文件。",
    "LS": "列出目录内容。",
    "Agent": "启动子 agent 执行任务。",
    "TodoWrite": "创建/更新任务列表。",
    "WebFetch": "获取网页内容。",
}
