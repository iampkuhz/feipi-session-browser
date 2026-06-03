"""Utility functions for Claude Code attribution builder."""

from __future__ import annotations

import re

from session_browser.attribution.agents.claude_code_parts.constants import (
    TOOL_DESCRIPTIONS,
)
from session_browser.attribution.agents.claude_code_tool_schemas import (
    _BINARY_TOOL_DESCRIPTIONS,
)


def _pct(part: int, total: int) -> float:
    """Compute percentage, safe for zero total."""
    if total <= 0:
        return 0.0
    return round(part / total * 100, 1)


def tool_description(name: str) -> str:
    """Return description for a tool.

    Uses _BINARY_TOOL_DESCRIPTIONS (full descriptions from Claude Code binary)
    as primary source, then falls back to TOOL_DESCRIPTIONS (short Chinese),
    then to a generic fallback.
    """
    return _BINARY_TOOL_DESCRIPTIONS.get(
        name, TOOL_DESCRIPTIONS.get(name, "工具说明未知。")
    )


def extract_tool_name(result_text: str) -> str:
    """Attempt to extract tool name from a tool result text.

    Looks for common patterns like 'Tool Call: Name', '### Name', etc.
    Falls back to first word or 'unknown'.
    """
    if not result_text:
        return "unknown"
    # Try common header patterns
    m = re.search(r'(?:Tool|tool)[\s_]*(?:Call|Result|Output)?[:\s]+(\w+)', result_text)
    if m:
        return m.group(1)
    m = re.search(r'^###\s+(\w+)', result_text, re.MULTILINE)
    if m:
        return m.group(1)
    # Fallback: first word
    first = result_text.split()[0] if result_text.split() else "unknown"
    return first[:30]  # cap length


def mask_sensitive_keys(text: str) -> str:
    """Mask sensitive key values in text for safe display."""
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
    """Truncate text to max_len characters with ellipsis."""
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    return text[:max_len] + "…"
