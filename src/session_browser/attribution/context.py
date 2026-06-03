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
    all_llm_calls: list[LLMCall] | None = None,
    subagent_type: str | None = None,
) -> dict:
    """Build a call-scoped session context for attribution builders.

    Args:
        session: The session summary object.
        round_obj: The current conversation round.
        interaction_index: 0-based index of the current LLM interaction within the round.
        interactions: List of LLM interactions in the current round.
        round_tool_calls: All tool calls associated with this round.
        all_messages: All messages from the session transcript (optional).
            Used to build prior_messages and full_messages_array.
        all_tool_calls: All tool calls from the entire session (optional).
            Used to build available_tools.
        project_dir: Path to the project root (optional).
            Used to read CLAUDE.md, .mcp.json, etc.
        agent_name: Agent name like "claude_code", "qoder", "codex".
            Used to locate agent-specific prompt files.
        existing_context: Optional pre-existing context to extend.
        subagent_type: Subagent type name (e.g. "implementer", "qa-verifier").
            Used to read the correct subagent prompt file instead of the main agent prompt.

    Returns:
        A dict with at least:
        - interaction_index: the 0-based index
        - preceding_tool_results: list of tool result texts from interactions
          that occurred BEFORE the current one
        - prior_messages: messages before the current LLM call, each with
          role, content_preview (truncated to 200 chars), content_token_estimate
        - full_messages_array: list of messages in Anthropic API format, each with
          role, content_type (user_text/tool_result/assistant_text/tool_use),
          content_preview, content_token_estimate, and message_index
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

    # -- full_messages_array (Anthropic API messages format) --
    full_messages_array = _build_full_messages_array(
        all_messages, interaction_index, round_obj, interactions,
    )

    # -- available_tools --
    available_tools = _build_available_tools(
        all_tool_calls, agent_name, llm_calls=all_llm_calls,
        project_dir=project_dir,
    )

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
        agent_prompt_file, subagent_prompt = _read_agent_prompt(
            project_path, agent_name, subagent_type=subagent_type,
        )
        mcp_tools, mcp_servers = _read_mcp_metadata(project_path)

    # -- Extract system-reminder from first assistant request_full --
    if not system_reminder_content and all_messages:
        system_reminder_content = _extract_system_reminder(all_messages)

    base = {
        "interaction_index": interaction_index,
        "preceding_tool_results": preceding_tool_results,
        "prior_messages": prior_messages,
        "full_messages_array": full_messages_array,
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
            if v or k in ("prior_messages", "full_messages_array", "available_tools", "mcp_tools", "mcp_servers"):
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


def _build_full_messages_array(
    all_messages: list | None,
    interaction_index: int,
    round_obj,
    interactions: list,
) -> list[dict]:
    """Build full_messages_array: Anthropic API-style messages for attribution.

    Unlike _build_prior_messages (which only stores 200-char previews), this
    builds a structured array that mirrors the real Anthropic API ``messages``
    field sent to the model. Each entry contains:

    - role: "user" or "assistant"
    - content_type: "user_text" | "tool_result" | "assistant_text" | "tool_use"
    - content_preview: truncated to 200 chars for summary display
    - content_token_estimate: rough token count
    - message_index: 0-based index in the messages array
    - has_full_content: whether full text is available for dynamic loading
    - tool_name: tool name for tool_result / tool_use entries
    - tool_use_id: tool_use_id for tool_result entries

    The array includes:
    - All prior user messages (user_text entries)
    - All preceding tool results (tool_result entries, from prior interactions)
    - The current user message (user_text entry)
    - Prior assistant responses (assistant_text + tool_use entries)

    NOTE: The current assistant response is NOT included — it's the OUTPUT,
    not part of the INPUT messages array.
    """
    if not all_messages:
        return []

    from session_browser.attribution.token_estimator import estimate_tokens_from_text

    messages_array = []
    msg_index = 0

    # Gather preceding tool results for this interaction
    preceding_tr_ids: set[str] = set()  # tool_use_ids already attributed
    preceding_tool_texts: dict[str, str] = {}  # tool_use_id -> result_text
    for ix_idx, ix in enumerate(interactions):
        if ix_idx >= interaction_index:
            break
        if hasattr(ix, "tool_calls") and ix.tool_calls:
            for tc in ix.tool_calls:
                if tc.result and tc.tool_use_id and not getattr(tc, "subagent_id", ""):
                    preceding_tool_texts[tc.tool_use_id] = tc.result
                    preceding_tr_ids.add(tc.tool_use_id)

    # Build a lookup: assistant msg's tool_calls -> tool_use_ids for that response
    assistant_tool_use_ids: dict[int, set[str]] = {}  # msg_index -> set of tool_use_ids

    for msg in all_messages:
        role = ""
        content = ""
        tool_calls = []
        request_full = ""

        if isinstance(msg, dict):
            role = msg.get("role", "")
            content = msg.get("content", "")
            tool_calls = msg.get("tool_calls", []) or []
            request_full = msg.get("request_full", "") or ""
        elif hasattr(msg, "role"):
            role = getattr(msg, "role", "")
            content = getattr(msg, "content", "") or ""
            tool_calls = getattr(msg, "tool_calls", []) or []
            request_full = getattr(msg, "request_full", "") or ""

        if not role:
            continue

        content_str = str(content) if content else ""

        if role == "user":
            # Check if this user message contains tool_results
            # Tool results appear as content blocks in the user message
            # We detect them by checking request_full for tool_result patterns
            # or by checking if this message follows assistant tool_calls

            # Add user text as a separate entry
            user_text = content_str.strip()
            if user_text:
                token_est = estimate_tokens_from_text(user_text)
                messages_array.append({
                    "role": "user",
                    "content_type": "user_text",
                    "content_preview": user_text[:_TRUNCATE_CONTENT_PREVIEW],
                    "content_token_estimate": token_est,
                    "message_index": msg_index,
                    "has_full_content": True,
                    "tool_name": "",
                    "tool_use_id": "",
                })
                msg_index += 1

            # Extract tool_result texts from request_full if available
            # request_full contains tool results preceding this LLM call
            if request_full and interaction_index == 0:
                # For the first interaction, tool results are in request_full
                # Split by "\n\n" to find tool result blocks
                parts = [p.strip() for p in request_full.split("\n\n") if p.strip()]
                for part in parts:
                    # Detect tool result blocks (they start with "Tool result for"
                    # or are long text that isn't the user message)
                    if part.startswith("Tool result for "):
                        # Extract tool_use_id from header
                        tr_match = re.match(r"Tool result for (\S+):", part)
                        tuid = tr_match.group(1) if tr_match else ""
                        # Get the actual result text (after the header line)
                        lines = part.split("\n", 1)
                        result_text = lines[1] if len(lines) > 1 else part
                        if tuid and result_text.strip() and tuid not in preceding_tr_ids:
                            token_est = estimate_tokens_from_text(result_text)
                            tool_name = _extract_tool_name_from_result(result_text)
                            messages_array.append({
                                "role": "user",
                                "content_type": "tool_result",
                                "content_preview": result_text.strip()[:_TRUNCATE_CONTENT_PREVIEW],
                                "content_token_estimate": token_est,
                                "message_index": msg_index,
                                "has_full_content": True,
                                "tool_name": tool_name,
                                "tool_use_id": tuid,
                            })
                            msg_index += 1
                            preceding_tr_ids.add(tuid)

            # Also add preceding tool results from interactions
            for tuid, tr_text in preceding_tool_texts.items():
                if tuid not in preceding_tr_ids and tr_text.strip():
                    token_est = estimate_tokens_from_text(tr_text)
                    tool_name = _extract_tool_name_from_result(tr_text)
                    messages_array.append({
                        "role": "user",
                        "content_type": "tool_result",
                        "content_preview": tr_text.strip()[:_TRUNCATE_CONTENT_PREVIEW],
                        "content_token_estimate": token_est,
                        "message_index": msg_index,
                        "has_full_content": True,
                        "tool_name": tool_name,
                        "tool_use_id": tuid,
                    })
                    msg_index += 1
                    preceding_tr_ids.add(tuid)

        elif role == "assistant":
            # Skip the assistant message that corresponds to the current
            # interaction — its response is the OUTPUT, not INPUT
            if hasattr(round_obj, "interactions") and round_obj.interactions:
                current_ix = round_obj.interactions[interaction_index] if interaction_index < len(round_obj.interactions) else None
                if current_ix and getattr(current_ix, "id", "") == getattr(msg, "llm_call_id", ""):
                    # This is the current assistant response — skip
                    continue

            # Add assistant text
            if content_str.strip():
                token_est = estimate_tokens_from_text(content_str)
                messages_array.append({
                    "role": "assistant",
                    "content_type": "assistant_text",
                    "content_preview": content_str[:_TRUNCATE_CONTENT_PREVIEW],
                    "content_token_estimate": token_est,
                    "message_index": msg_index,
                    "has_full_content": True,
                    "tool_name": "",
                    "tool_use_id": "",
                })
                msg_index += 1

            # Add tool_use entries from assistant's tool_calls
            seen_tuids_in_msg = set()
            for tc in tool_calls:
                if isinstance(tc, dict):
                    tuid = tc.get("id", "")
                    tname = tc.get("name", "unknown")
                    tparams = tc.get("parameters", {})
                elif hasattr(tc, "tool_use_id"):
                    tuid = getattr(tc, "tool_use_id", "")
                    tname = getattr(tc, "name", "unknown")
                    tparams = getattr(tc, "parameters", {})
                else:
                    continue

                if tuid and tuid not in seen_tuids_in_msg:
                    seen_tuids_in_msg.add(tuid)
                    params_str = json.dumps(tparams, ensure_ascii=False)[:200] if tparams else ""
                    tool_use_text = f"{tname}({params_str})" if params_str else tname
                    token_est = estimate_tokens_from_text(tool_use_text)
                    messages_array.append({
                        "role": "assistant",
                        "content_type": "tool_use",
                        "content_preview": tool_use_text[:_TRUNCATE_CONTENT_PREVIEW],
                        "content_token_estimate": token_est,
                        "message_index": msg_index,
                        "has_full_content": False,
                        "tool_name": tname,
                        "tool_use_id": tuid,
                    })
                    msg_index += 1

    return messages_array


def _extract_tool_name_from_result(result_text: str) -> str:
    """Extract tool name from a tool result text.

    Looks for patterns like 'Tool result for <tool_use_id>:\\n<tool_name>...'
    or header patterns like 'Tool Call: Name'.
    """
    if not result_text:
        return "unknown"
    m = re.search(r'(?:Tool|tool)[\s_]*(?:Call|Result|Output)?[:\s]+(\w+)', result_text)
    if m:
        return m.group(1)
    m = re.search(r'^###\s+(\w+)', result_text, re.MULTILINE)
    if m:
        return m.group(1)
    # Fallback: first word
    first = result_text.split()[0] if result_text.split() else "unknown"
    return first[:30]


def _parse_agent_tools_from_frontmatter(text: str) -> list[str] | None:
    """Parse YAML frontmatter and extract ``tools:`` field.

    The tools field looks like:
        tools: Agent(implementer, qa-verifier), Read, Glob, Grep, Bash

    Returns a sorted list of tool names, or None if no ``tools:`` found.
    """
    m = re.match(r'---\s*\n(.*?)\n---\s*\n', text, re.DOTALL)
    if not m:
        return None

    fm = m.group(1)
    tools_match = re.search(r'^tools:\s*(.+)$', fm, re.MULTILINE)
    if not tools_match:
        return None

    tools_str = tools_match.group(1).strip()
    if not tools_str:
        return None

    # Extract parenthesized compound tools like "Agent(...)", "Mcp(...)"
    paren_re = re.compile(r'(\w+)\([^)]*\)')
    tools: list[str] = []
    for pm in paren_re.finditer(tools_str):
        tools.append(pm.group(1))

    # Remove parenthesized parts, then split remaining by comma
    remaining = paren_re.sub('', tools_str)
    for part in remaining.split(','):
        part = part.strip()
        if part:
            tools.append(part)

    return sorted(set(tools)) if tools else None


def _read_agent_tool_list(
    project_path: Path,
) -> list[str] | None:
    """Scan .claude/agents/*.md for explicit tool lists in YAML frontmatter.

    Returns the UNION of all found tools lists, or None if no agent files
    have an explicit ``tools:`` field.  Using the union ensures we capture
    all tools available to any agent in the project.
    """
    agents_dir = project_path / ".claude" / "agents"
    if not agents_dir.is_dir():
        return None

    all_tools: set[str] = set()
    found_any = False
    for agent_file in sorted(agents_dir.glob("*.md")):
        try:
            text = agent_file.read_text(encoding="utf-8", errors="replace")
            tools = _parse_agent_tools_from_frontmatter(text)
            if tools:
                found_any = True
                all_tools.update(tools)
        except (OSError, PermissionError):
            continue

    return sorted(all_tools) if found_any else None


def _build_available_tools(
    all_tool_calls: list | None,
    agent_name: str | None = None,
    llm_calls: list | None = None,
    project_dir: str | None = None,
) -> list[str]:
    """Collect unique tool names from observed tool calls AND LLM tool definitions.

    For Claude Code, the JSONL event format does NOT persist the ``tools``
    array (tool definitions sent to the API).  ``tool_calls_raw`` contains
    **invoked** tools (actual calls made by the LLM), not **available**
    tools (all definitions sent to the API).

    Priority:
    1. If the project has .claude/agents/*.md files with explicit ``tools:``
       in their YAML frontmatter, use that list.
    2. Try to extract tools from LLM tool_calls_raw (for agents that persist
       the full tools array).
    3. Fallback to observed tool calls.
    4. Final fallback: full Claude Code tool registry (except codex).
    """
    # Claude Code: try to read explicit tool list from agent definition files.
    if agent_name == "claude_code" and project_dir:
        agent_tools = _read_agent_tool_list(Path(project_dir))
        if agent_tools:
            # Validate: only keep tool names that exist in the SDK registry
            from session_browser.attribution.agents.claude_code_tool_schemas import (
                ALL_CLAUDE_CODE_TOOLS,
            )
            valid_tools = [t for t in agent_tools if t in ALL_CLAUDE_CODE_TOOLS]
            if valid_tools:
                return sorted(valid_tools)

    # First pass: try to extract ALL tools from LLM tool_calls_raw (tool
    # definitions sent to LLM).  This works for agents that persist the
    # full tools array in their session data.
    if llm_calls:
        all_tools_from_llm: set[str] = set()
        for lc in llm_calls:
            raw = getattr(lc, "tool_calls_raw", "") or ""
            if not raw:
                continue
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    for item in parsed:
                        if isinstance(item, dict):
                            tname = item.get("name", "")
                            if tname:
                                all_tools_from_llm.add(tname)
            except (json.JSONDecodeError, TypeError):
                pass
        if all_tools_from_llm:
            return sorted(all_tools_from_llm)

    # Second pass: fallback to observed tool calls
    if all_tool_calls:
        seen: set[str] = set()
        for tc in all_tool_calls:
            name = ""
            if isinstance(tc, dict):
                name = tc.get("name", tc.get("tool_name", ""))
            elif hasattr(tc, "name"):
                name = getattr(tc, "name", "")
            if name:
                seen.add(name)
        if seen:
            return sorted(seen)

    # Final fallback: full Claude Code tool registry (except codex).
    if agent_name == "codex":
        return []
    from session_browser.attribution.agents.claude_code_tool_schemas import (
        ALL_CLAUDE_CODE_TOOLS,
    )
    return list(ALL_CLAUDE_CODE_TOOLS)


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
    subagent_type: str | None = None,
) -> tuple[str, str]:
    """Read agent prompt file if agent_name or subagent_type is known.

    Priority:
    1. If subagent_type is provided (e.g. "implementer", "qa-verifier"),
       read .claude/agents/{subagent_type}.md — this is the subagent's own prompt.
    2. Otherwise read .claude/agents/{agent_name}.md for the main agent prompt.

    For Codex, checks .codex/agents/ first, then falls back to .claude/agents/.
    """
    if not agent_name and not subagent_type:
        return "", ""

    # Determine which agent file to read
    if subagent_type:
        # For subagent calls, read the subagent's own prompt file
        target_name = subagent_type
    elif agent_name:
        # For main agent calls, read the main agent prompt file
        target_name = agent_name
    else:
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
        candidate = agents_dir_path / f"{target_name}.md"
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


_SYSTEM_REMINDER_PATTERN = re.compile(
    r'<system-reminder>(.*?)</system-reminder>',
    re.DOTALL | re.IGNORECASE,
)


def _extract_system_reminder(messages: list) -> str:
    """Extract <system-reminder> content from the first assistant message's request_full.

    Claude Code injects the built-in system prompt (CLAUDE.md + MEMORY.md + config)
    as a <system-reminder> block in the first API request. This function extracts
    that content so attribution builders can use actual token counts instead of
    heuristics.

    Returns the extracted system-reminder text, or empty string if not found.
    """
    for msg in messages:
        # Check assistant message request_full
        request_full = ""
        if isinstance(msg, dict):
            request_full = msg.get("request_full", "") or msg.get("content", "")
        elif hasattr(msg, "request_full"):
            request_full = getattr(msg, "request_full", "") or ""

        if not request_full:
            continue

        m = _SYSTEM_REMINDER_PATTERN.search(request_full)
        if m:
            return m.group(1).strip()

        # Also check if the content itself has system-reminder tags
        content = ""
        if isinstance(msg, dict):
            content = msg.get("content", "")
        elif hasattr(msg, "content"):
            content = getattr(msg, "content", "") or ""

        if content:
            m2 = _SYSTEM_REMINDER_PATTERN.search(str(content))
            if m2:
                return m2.group(1).strip()

    return ""
