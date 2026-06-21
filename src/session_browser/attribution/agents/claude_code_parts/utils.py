"""Claude Code attribution display helpers.

These helpers are used when Claude Code attribution views render tool schema
and tool result evidence. Inputs come from normalized source units or extracted
Claude Code tool schemas; outputs are display-only labels, previews, and masked
text that must not expand the attribution boundary beyond UI diagnostics.
"""

from __future__ import annotations

import re

from session_browser.attribution.agents.claude_code_tool_schemas import (
    _BINARY_TOOL_DESCRIPTIONS,
)

TOOL_DESCRIPTIONS = {
    'Read': '读取文件内容。',
    'Write': '写入文件内容,创建新文件。',
    'Edit': '对文件进行精确的局部修改。',
    'Bash': '执行 shell 命令。',
    'Grep': '在文件中搜索文本。',
    'Glob': '按模式匹配查找文件。',
    'LS': '列出目录内容。',
    'Agent': '启动子 agent 执行任务。',
    'TodoWrite': '创建/更新任务列表。',
    'WebFetch': '获取网页内容。',
}


def _pct(part: int, total: int) -> float:
    """Return a safe percentage for attribution coverage displays.

    Args:
        part: Count attributed to one Claude Code display bucket.
        total: Total count used as the percentage denominator.

    Returns:
        Rounded percentage, or ``0.0`` when the total is not positive.
    """
    if total <= 0:
        return 0.0
    return round(part / total * 100, 1)


def tool_description(name: str) -> str:
    """Return the Claude Code tool description used for schema attribution.

    Args:
        name: Claude Code built-in tool name from a schema or source unit.

    Returns:
        Runtime binary description, fallback display description, or unknown label.
    """
    return _BINARY_TOOL_DESCRIPTIONS.get(name, TOOL_DESCRIPTIONS.get(name, '工具说明未知。'))


def extract_tool_name(result_text: str) -> str:
    """Extract a tool name from normalized Claude Code tool result text.

    Args:
        result_text: Tool result preview captured from normalized source units.

    Returns:
        Best-effort Claude Code tool name bounded to preview text evidence.
    """
    if not result_text:
        return 'unknown'
    m = re.search(r'(?:Tool|tool)[\s_]*(?:Call|Result|Output)?[:\s]+(\w+)', result_text)
    if m:
        return m.group(1)
    m = re.search(r'^###\s+(\w+)', result_text, re.MULTILINE)
    if m:
        return m.group(1)
    first = result_text.split(maxsplit=1)[0] if result_text.split() else 'unknown'
    return first[:30]


def mask_sensitive_keys(text: str) -> str:
    """Mask sensitive key values before showing Claude Code evidence previews.

    Args:
        text: Attribution preview text from tool inputs, outputs, or schemas.

    Returns:
        Preview text with sensitive key values replaced by ``***MASKED***``.
    """
    sensitive_keys = frozenset(
        {
            'api_key',
            'apikey',
            'token',
            'secret',
            'password',
            'authorization',
            'bearer',
            'credential',
            'env',
        }
    )
    if not text:
        return ''
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
    """Truncate a Claude Code attribution preview to the display boundary.

    Args:
        text: Preview text prepared for Claude Code attribution UI.
        max_len: Maximum number of characters allowed in the preview.

    Returns:
        Original text or a shortened preview with an ellipsis suffix.
    """
    if not text:
        return ''
    if len(text) <= max_len:
        return text
    return text[:max_len] + '…'
