"""Claude Code builtins catalog：默认工具目录。"""

from __future__ import annotations

from session_browser.attribution.agents.claude_code_tool_schemas import (
    ALL_CLAUDE_CODE_TOOLS,
    extract_tool_schemas,
)


def get_builtins_catalog() -> dict[str, dict]:
    """获取 Claude Code 内置工具目录。

    Returns:
        {tool_name: schema_dict} 映射
    """
    try:
        schemas = extract_tool_schemas()
    except Exception:
        schemas = {}

    result = {}
    for tool_name in ALL_CLAUDE_CODE_TOOLS:
        result[tool_name] = schemas.get(tool_name, {'name': tool_name})

    return result
