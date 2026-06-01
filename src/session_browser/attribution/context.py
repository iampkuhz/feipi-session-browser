"""Session context builder for attribution.

Provides ``build_attribution_session_context`` which constructs a call-scoped
context dict that attribution builders use to determine:
- preceding_tool_results: tool results that occur before the current LLM call
- prior_messages: conversation history before this call
- available_tools: tool schemas available to the model
- local_instructions: CLAUDE.md and agent prompt files
- mcp_tools / mcp_servers: from .mcp.json (no credentials)

This avoids passing session_context=None and enables proper call-scoped
attribution rather than attributing the entire round's tool results to
every LLM call.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from session_browser.domain.models import (
    ConversationRound,
    LLMCall,
    SessionSummary,
    ToolCall,
)

logger = logging.getLogger(__name__)

_DEFAULT_CC_TOOLS = ["Read", "Write", "Edit", "Bash", "Grep", "Glob", "LS", "Agent"]
_TRUNCATE_CONTENT_PREVIEW = 200
_TRUNCATE_LOCAL_INSTRUCTIONS = 2048  # 2KB

# Sensitive key patterns for masking in bucket content extraction.
_SENSITIVE_KEYS = frozenset({
    "api_key", "apikey", "api-key",
    "token", "auth_token", "access_token", "refresh_token",
    "secret", "secret_key",
    "password", "passwd",
    "authorization", "bearer",
    "credential", "credentials",
    "env", "environment",
})
_SENSITIVE_KEY_RE = re.compile(
    r'(?:"|\'|)([A-Za-z0-9_\-]*'
    + r'(?:api_key|apikey|api-key|token|secret|password|passwd|authorization|credential|bearer|env)'
    + r'[A-Za-z0-9_\-]*)\s*(?:"|\'|)?\s*(?::|=)\s*'
    r'("([^"]*)"|\'([^\']*)\'|([^\n,}]+))',
    re.IGNORECASE,
)


def _mask_sensitive_keys(text: str) -> str:
    """Mask values for sensitive keys like api_key, token, secret, password, etc.

    Replaces the value portion with "***MASKED***" while preserving the key name.
    """
    if not text:
        return ""

    def _replacer(m: re.Match) -> str:
        key_part = m.group(1)
        # Reconstruct with masked value
        quote_open = m.group(2)[0] if m.group(2) else ""
        if quote_open in ('"', "'"):
            return f'{key_part}: {quote_open}***MASKED***{quote_open}'
        return f'{key_part}: ***MASKED***'

    return _SENSITIVE_KEY_RE.sub(_replacer, text)


def _truncate_preview(text: str, max_len: int = 200) -> str:
    """Truncate text to max_len characters, appending '…' if truncated."""
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    return text[:max_len] + "…"


def build_attribution_session_context(
    *,
    session: SessionSummary | None,
    round_obj: ConversationRound,
    interaction_index: int,
    interactions: list[LLMCall],
    round_tool_calls: list[ToolCall],
    all_messages: list | None = None,
    all_tool_calls: list | None = None,
    project_dir: str | None = None,
    agent_name: str | None = None,
    existing_context: dict | None = None,
) -> dict:
    """Build a call-scoped session context for attribution builders.

    Args:
        session: The session summary object.
        round_obj: The current conversation round.
        interaction_index: 0-based index of the current LLM interaction within the round.
        interactions: List of LLM interactions in the current round.
        round_tool_calls: All tool calls associated with this round.
        all_messages: All messages from the session transcript (optional).
            Used to build prior_messages.
        all_tool_calls: All tool calls from the entire session (optional).
            Used to build available_tools.
        project_dir: Path to the project root (optional).
            Used to read CLAUDE.md, .mcp.json, etc.
        agent_name: Agent name like "claude_code", "qoder", "codex".
            Used to locate agent-specific prompt files.
        existing_context: Optional pre-existing context to extend.

    Returns:
        A dict with at least:
        - interaction_index: the 0-based index
        - preceding_tool_results: list of tool result texts from interactions
          that occurred BEFORE the current one
        - prior_messages: messages before the current LLM call, each with
          role, content_preview (truncated to 200 chars), content_token_estimate
        - available_tools: unique tool names from observed tool calls, or
          default Claude Code tool list as heuristic fallback
        - local_instructions: CLAUDE.md content (truncated to 2KB)
        - system_reminder_content: from transcript system-reminder (if any)
        - agent_prompt_file / subagent_prompt: from .claude/agents/ if found
        - mcp_tools / mcp_servers: from .mcp.json (names only, no credentials)
    """
    preceding_tool_results: list[str] = []

    if interaction_index > 0:
        # Gather tool results from prior interactions in this round
        for ix in interactions[:interaction_index]:
            if hasattr(ix, "tool_calls") and ix.tool_calls:
                for tc in ix.tool_calls:
                    if tc.result and not getattr(tc, "subagent_id", ""):
                        preceding_tool_results.append(tc.result)
    # else: first LLM call — no preceding tool results

    # -- prior_messages --
    prior_messages = _build_prior_messages(all_messages, interaction_index)

    # -- available_tools --
    available_tools = _build_available_tools(all_tool_calls, agent_name)

    # -- local_instructions, agent_prompt, mcp metadata --
    local_instructions = ""
    agent_prompt_file = ""
    subagent_prompt = ""
    system_reminder_content = ""
    mcp_tools: list[str] = []
    mcp_servers: list[str] = []

    if project_dir:
        project_path = Path(project_dir)
        local_instructions = _read_local_instructions(project_path, agent_name)
        agent_prompt_file, subagent_prompt = _read_agent_prompt(project_path, agent_name)
        mcp_tools, mcp_servers = _read_mcp_metadata(project_path)

    base = {
        "interaction_index": interaction_index,
        "preceding_tool_results": preceding_tool_results,
        "prior_messages": prior_messages,
        "available_tools": available_tools,
        "local_instructions": local_instructions,
        "system_reminder_content": system_reminder_content,
        "agent_prompt_file": agent_prompt_file,
        "subagent_prompt": subagent_prompt,
        "mcp_tools": mcp_tools,
        "mcp_servers": mcp_servers,
    }

    if existing_context:
        # Merge: new keys override existing only if non-empty
        for k, v in base.items():
            if v or k in ("prior_messages", "available_tools", "mcp_tools", "mcp_servers"):
                existing_context[k] = v
        return existing_context

    return base


# -- Internal helpers --


def _build_prior_messages(
    all_messages: list | None,
    interaction_index: int,
) -> list[dict]:
    """Build prior_messages from all session messages before the current call.

    Each entry has: role, content_preview (truncated to 200 chars),
    content_token_estimate (rough estimate).
    """
    if not all_messages:
        return []

    result = []
    for msg in all_messages:
        role = ""
        content = ""
        if isinstance(msg, dict):
            role = msg.get("role", "")
            content = msg.get("content", "")
        elif hasattr(msg, "role"):
            role = getattr(msg, "role", "")
            content = getattr(msg, "content", "") or ""

        if not role:
            continue

        content_str = str(content) if content else ""
        preview = content_str[:_TRUNCATE_CONTENT_PREVIEW]
        # Rough token estimate: ~4 chars per token for English
        token_estimate = max(1, len(content_str) // 4) if content_str else 0

        result.append({
            "role": role,
            "content_preview": preview,
            "content_token_estimate": token_estimate,
        })

    return result


def _build_available_tools(all_tool_calls: list | None, agent_name: str | None = None) -> list[str]:
    """Collect unique tool names from observed tool calls.

    For Codex, returns empty list when no observed tools (do NOT fall back
    to Claude Code default tool list). For other agents, falls back to
    default Claude Code tool list when no observed tools.
    """
    if not all_tool_calls:
        if agent_name == "codex":
            return []
        return list(_DEFAULT_CC_TOOLS)

    seen: set[str] = set()
    for tc in all_tool_calls:
        name = ""
        if isinstance(tc, dict):
            name = tc.get("name", tc.get("tool_name", ""))
        elif hasattr(tc, "name"):
            name = getattr(tc, "name", "")
        if name:
            seen.add(name)

    if not seen:
        if agent_name == "codex":
            return []
        return list(_DEFAULT_CC_TOOLS)

    return sorted(seen)


def _read_local_instructions(project_path: Path, agent_name: str | None) -> str:
    """Read local instructions from project_dir, truncated to 2KB.

    For Codex, prefers AGENTS.md / .codex/AGENTS.md over CLAUDE.md.
    """
    if agent_name == "codex":
        candidates = [
            project_path / "AGENTS.md",
            project_path / ".codex" / "AGENTS.md",
            project_path / "CLAUDE.md",
            project_path / ".claude" / "CLAUDE.md",
        ]
    else:
        candidates = [
            project_path / "CLAUDE.md",
            project_path / ".claude" / "CLAUDE.md",
        ]
    for path in candidates:
        try:
            if path.exists() and path.is_file():
                text = path.read_text(encoding="utf-8", errors="replace")
                return text[:_TRUNCATE_LOCAL_INSTRUCTIONS]
        except (OSError, PermissionError) as exc:
            logger.debug("Cannot read local instructions %s: %s", path, exc)
    return ""


def _read_agent_prompt(
    project_path: Path, agent_name: str | None,
) -> tuple[str, str]:
    """Read agent prompt file if agent_name is known.

    For Codex, checks .codex/agents/ first, then falls back to .claude/agents/.
    """
    if not agent_name:
        return "", ""

    # Try agent-specific directory first
    if agent_name == "codex":
        agents_dirs = [
            project_path / ".codex" / "agents",
            project_path / ".claude" / "agents",
        ]
    else:
        agents_dirs = [project_path / ".claude" / "agents"]

    for agents_dir_path in agents_dirs:
        candidate = agents_dir_path / f"{agent_name}.md"
        try:
            if candidate.exists() and candidate.is_file():
                text = candidate.read_text(encoding="utf-8", errors="replace")
                return str(candidate), text[:_TRUNCATE_LOCAL_INSTRUCTIONS]
        except (OSError, PermissionError) as exc:
            logger.debug("Cannot read agent prompt %s: %s", candidate, exc)
    return "", ""


def _read_mcp_metadata(project_path: Path) -> tuple[list[str], list[str]]:
    """Read .mcp.json from project_dir. Extract server names and tool names only.

    Returns (mcp_tools, mcp_servers). NO credentials/values are returned.
    """
    mcp_path = project_path / ".mcp.json"
    if not mcp_path.exists() or not mcp_path.is_file():
        return [], []

    try:
        text = mcp_path.read_text(encoding="utf-8", errors="replace")
        data = json.loads(text)
    except (OSError, PermissionError, json.JSONDecodeError) as exc:
        logger.debug("Cannot read MCP metadata %s: %s", mcp_path, exc)
        return [], []

    servers: list[str] = []
    tools: list[str] = []

    # .mcp.json typically has "mcpServers" key with server objects
    mcp_servers_dict = data.get("mcpServers", data.get("mcp_servers", {}))
    if isinstance(mcp_servers_dict, dict):
        for server_name, server_config in mcp_servers_dict.items():
            servers.append(server_name)
            if isinstance(server_config, dict):
                # Some configs have explicit tool lists
                server_tools = server_config.get("tools", server_config.get("allowedTools", []))
                if isinstance(server_tools, list):
                    for t in server_tools:
                        if isinstance(t, str):
                            tools.append(f"{server_name}:{t}")
                # If no explicit tool list, the server name itself indicates availability
                if not server_tools:
                    tools.append(f"{server_name}:*")

    return tools, servers
