"""Claude Code attribution 共享展示工具函数。"""

from __future__ import annotations

import re

from session_browser.attribution.agents.claude_code_tool_schemas import (
    _BINARY_TOOL_DESCRIPTIONS,
)


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


def _pct(part: int, total: int) -> float:
    """安全计算百分比。"""
    if total <= 0:
        return 0.0
    return round(part / total * 100, 1)


def tool_description(name: str) -> str:
    """返回工具说明，优先使用 Claude Code binary 中解析出的完整描述。"""
    return _BINARY_TOOL_DESCRIPTIONS.get(
        name, TOOL_DESCRIPTIONS.get(name, "工具说明未知。")
    )


def extract_tool_name(result_text: str) -> str:
    """从工具结果文本中提取工具名。"""
    if not result_text:
        return "unknown"
    m = re.search(r'(?:Tool|tool)[\s_]*(?:Call|Result|Output)?[:\s]+(\w+)', result_text)
    if m:
        return m.group(1)
    m = re.search(r'^###\s+(\w+)', result_text, re.MULTILINE)
    if m:
        return m.group(1)
    first = result_text.split()[0] if result_text.split() else "unknown"
    return first[:30]


def mask_sensitive_keys(text: str) -> str:
    """屏蔽展示文本中的敏感字段值。"""
    sensitive_keys = frozenset({
        "api_key", "apikey", "token", "secret", "password",
        "authorization", "bearer", "credential", "env",
    })
    if not text:
        return ""
    result = text
    for key in sensitive_keys:
        pattern = re.compile(
            r'(["\']?' + re.escape(key) + r'["\']?\s*[:=]\s*)'
            r'(["][^"]*["]|[\'"][^\']*[\'"]|[^\n,}]+)',
            re.IGNORECASE,
        )
        result = pattern.sub(lambda m: m.group(1) + '***MASKED***', result)
    return result


def truncate_preview(text: str, max_len: int = 200) -> str:
    """截断展示预览。"""
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    return text[:max_len] + "…"
