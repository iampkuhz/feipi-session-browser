"""Session context builder for attribution.

Provides ``build_attribution_session_context`` which constructs a call-scoped
context dict that attribution builders use to determine:
- preceding_tool_results: tool results that occur before the current LLM call
- prior_messages: conversation history before this call
- available_tools: request-side tool schemas available to the model
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

from session_browser.attribution.agents.claude_code_parts.claude_code_agent_tools import (
    resolve_claude_code_available_tools,
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
            Used only for agents whose local data does not have a better
            request-side tool list source. Claude Code does not infer request
            tool schemas from observed tool calls.
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
        - available_tools: request-side tool names from the current agent
          definition, or the default Claude Code tool registry as fallback
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

    current_ix = _resolve_current_interaction(round_obj, interactions, interaction_index)

    # -- prior_messages --
    prior_messages = _build_prior_messages(
        all_messages,
        interaction_index,
        round_obj=round_obj,
        current_interaction=current_ix,
    )

    # -- full_messages_array (Anthropic API messages format) --
    full_messages_array = _build_full_messages_array(
        all_messages, interaction_index, round_obj, interactions,
    )

    resolved_project_dir = _resolve_project_dir(session, project_dir)

    # -- available_tools --
    available_tool_context = _build_available_tool_context(
        all_tool_calls=all_tool_calls,
        agent_name=agent_name,
        llm_calls=all_llm_calls,
        project_dir=resolved_project_dir,
        session_file=getattr(session, "file_path", "") if session else "",
        subagent_type=subagent_type,
        call_timestamp=getattr(current_ix, "timestamp", "") if current_ix else "",
    )

    # -- local_instructions, agent_prompt, mcp metadata --
    local_instructions = ""
    agent_prompt_file = ""
    subagent_prompt = ""
    system_reminder_content = ""
    mcp_tools: list[str] = []
    mcp_servers: list[str] = []

    if resolved_project_dir:
        project_path = Path(resolved_project_dir)
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
        "available_tools": available_tool_context["available_tools"],
        "available_tools_source": available_tool_context.get("available_tools_source", ""),
        "available_tools_agent_name": available_tool_context.get("available_tools_agent_name", ""),
        "available_tools_definition_path": available_tool_context.get("available_tools_definition_path", ""),
        "available_tools_reason": available_tool_context.get("available_tools_reason", ""),
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
            if v or k in (
                "prior_messages", "full_messages_array", "available_tools",
                "available_tools_source", "available_tools_agent_name",
                "available_tools_definition_path", "available_tools_reason",
                "mcp_tools", "mcp_servers",
            ):
                existing_context[k] = v
        return existing_context

    return base


# -- Internal helpers --


def _resolve_project_dir(session: SessionSummary | None, project_dir: str | None) -> str:
    """Choose a readable repository path over Claude's encoded project segment."""
    candidates: list[str] = []
    if project_dir:
        candidates.append(str(project_dir))
    if session is not None:
        cwd = getattr(session, "cwd", "") or ""
        project_key = getattr(session, "project_key", "") or ""
        if cwd:
            candidates.append(str(cwd))
        if project_key:
            candidates.append(str(project_key))

    for candidate in candidates:
        try:
            if candidate and Path(candidate).exists():
                return candidate
        except (OSError, ValueError):
            continue

    return candidates[0] if candidates else ""


def _build_prior_messages(
    all_messages: list | None,
    interaction_index: int | None = None,
    *,
    round_obj=None,
    current_interaction=None,
) -> list[dict]:
    """Build prior_messages from all session messages before the current call.

    Each entry has: role, content_preview (truncated to 200 chars),
    content_token_estimate (rough estimate).
    """
    if not all_messages:
        return []

    current_call_id = getattr(current_interaction, "id", "") if current_interaction else ""
    current_ts = getattr(current_interaction, "timestamp", "") if current_interaction else ""
    current_user = getattr(round_obj, "user_msg", None) if round_obj is not None else None
    current_user_content = getattr(current_user, "content", "") if current_user else ""
    current_user_ts = getattr(current_user, "timestamp", "") if current_user else ""

    result = []
    for msg in all_messages:
        role = ""
        content = ""
        msg_ts = ""
        msg_call_id = ""
        if isinstance(msg, dict):
            role = msg.get("role", "")
            content = msg.get("content", "")
            msg_ts = msg.get("timestamp", "")
            msg_call_id = msg.get("llm_call_id", "") or msg.get("id", "")
        elif hasattr(msg, "role"):
            role = getattr(msg, "role", "")
            content = getattr(msg, "content", "") or ""
            msg_ts = getattr(msg, "timestamp", "") or ""
            msg_call_id = getattr(msg, "llm_call_id", "") or ""

        if not role:
            continue
        if current_call_id and role == "assistant" and msg_call_id == current_call_id:
            break
        if current_ts and msg_ts and msg_ts >= current_ts:
            break

        content_str = str(content) if content else ""
        if (
            role == "user"
            and current_user_content
            and content_str == current_user_content
            and (not current_user_ts or msg_ts == current_user_ts)
        ):
            continue
        preview = content_str[:_TRUNCATE_CONTENT_PREVIEW]
        # Rough token estimate: ~4 chars per token for English
        token_estimate = max(1, len(content_str) // 4) if content_str else 0

        result.append({
            "role": role,
            "content": content_str,
            "full_content": content_str,
            "content_preview": preview,
            "content_token_estimate": token_estimate,
            "timestamp": msg_ts,
            "llm_call_id": msg_call_id,
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
    current_ix = _resolve_current_interaction(round_obj, interactions, interaction_index)
    current_call_id = getattr(current_ix, "id", "") if current_ix else ""
    current_request_full = getattr(current_ix, "request_full", "") if current_ix else ""

    if not all_messages:
        return _messages_array_from_request_full(current_request_full)

    candidate: list[dict] = []
    msg_index = 0
    found_current = False
    saw_request_full = False

    for msg in all_messages:
        role = _message_field(msg, "role", "")
        if role != "assistant":
            continue

        msg_call_id = _message_field(msg, "llm_call_id", "") or _message_field(msg, "id", "")
        is_current = bool(current_call_id and msg_call_id == current_call_id)
        request_full = _message_field(msg, "request_full", "")
        if is_current and not request_full:
            request_full = current_request_full

        if request_full:
            msg_index, appended = _append_request_full_entries(candidate, request_full, msg_index)
            saw_request_full = saw_request_full or appended

        if is_current:
            found_current = True
            break

        msg_index = _append_assistant_message_entries(candidate, msg, msg_index)

    if found_current:
        return candidate

    # Subagent attribution currently receives the parent session transcript, so
    # a subagent call id will not be found there.  In that case, use the
    # call-scoped request text instead of attributing the parent transcript.
    if current_call_id and current_request_full:
        return _messages_array_from_request_full(current_request_full)

    # Older unit fixtures and providers may not hydrate request_full.  Keep a
    # transcript fallback, but still stop before the current assistant when an
    # id match is available.
    if not saw_request_full:
        return _build_full_messages_array_legacy(all_messages, current_call_id)

    return candidate


def _resolve_current_interaction(round_obj, interactions: list, interaction_index: int):
    if interactions and 0 <= interaction_index < len(interactions):
        return interactions[interaction_index]
    round_interactions = getattr(round_obj, "interactions", None) or []
    if round_interactions and 0 <= interaction_index < len(round_interactions):
        return round_interactions[interaction_index]
    return None


def _message_field(msg, field_name: str, default=""):
    if isinstance(msg, dict):
        return msg.get(field_name, default)
    return getattr(msg, field_name, default)


def _messages_array_from_request_full(request_full: str) -> list[dict]:
    result: list[dict] = []
    _append_request_full_entries(result, request_full or "", 0)
    return result


def _append_request_full_entries(messages_array: list[dict], request_full: str, msg_index: int) -> tuple[int, bool]:
    from session_browser.attribution.token_estimator import estimate_tokens_from_text

    text = (request_full or "").strip()
    if not text:
        return msg_index, False

    parts = [p.strip() for p in text.split("\n\n") if p.strip()]
    has_tool_result = any(p.startswith("Tool result for ") for p in parts)
    if not has_tool_result:
        parts = [text]

    appended = False
    for part in parts:
        content_type = "user_text"
        tool_use_id = ""
        tool_name = ""
        payload_text = part

        if part.startswith("Tool result for "):
            content_type = "tool_result"
            tr_match = re.match(r"Tool result for (\S+):", part)
            tool_use_id = tr_match.group(1) if tr_match else ""
            lines = part.split("\n", 1)
            payload_text = lines[1] if len(lines) > 1 else part
            tool_name = _extract_tool_name_from_result(payload_text)

        payload_text = payload_text.strip()
        if not payload_text:
            continue

        token_est = estimate_tokens_from_text(payload_text)
        messages_array.append({
            "role": "user",
            "content_type": content_type,
            "content": payload_text,
            "full_content": payload_text,
            "content_preview": payload_text[:_TRUNCATE_CONTENT_PREVIEW],
            "content_token_estimate": token_est,
            "message_index": msg_index,
            "has_full_content": True,
            "tool_name": tool_name,
            "tool_use_id": tool_use_id,
        })
        msg_index += 1
        appended = True

    return msg_index, appended


def _append_assistant_message_entries(messages_array: list[dict], msg, msg_index: int) -> int:
    from session_browser.attribution.token_estimator import estimate_tokens_from_text

    content = _message_field(msg, "content", "") or ""
    content_str = str(content) if content else ""
    if content_str.strip():
        token_est = estimate_tokens_from_text(content_str)
        messages_array.append({
            "role": "assistant",
            "content_type": "assistant_text",
            "content": content_str,
            "full_content": content_str,
            "content_preview": content_str[:_TRUNCATE_CONTENT_PREVIEW],
            "content_token_estimate": token_est,
            "message_index": msg_index,
            "has_full_content": True,
            "tool_name": "",
            "tool_use_id": "",
        })
        msg_index += 1

    seen_tuids_in_msg = set()
    tool_calls = _message_field(msg, "tool_calls", []) or []
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
            params_str = json.dumps(tparams, ensure_ascii=False) if tparams else ""
            tool_use_text = f"{tname}({params_str})" if params_str else tname
            token_est = estimate_tokens_from_text(tool_use_text)
            messages_array.append({
                "role": "assistant",
                "content_type": "tool_use",
                "content": tool_use_text,
                "full_content": tool_use_text,
                "content_preview": tool_use_text[:_TRUNCATE_CONTENT_PREVIEW],
                "content_token_estimate": token_est,
                "message_index": msg_index,
                "has_full_content": True,
                "tool_name": tname,
                "tool_use_id": tuid,
            })
            msg_index += 1

    return msg_index


def _build_full_messages_array_legacy(all_messages: list | None, current_call_id: str = "") -> list[dict]:
    """Fallback for fixtures without request_full hydration."""
    if not all_messages:
        return []

    messages_array: list[dict] = []
    msg_index = 0
    for msg in all_messages:
        role = _message_field(msg, "role", "")
        if not role:
            continue
        if role == "assistant":
            msg_call_id = _message_field(msg, "llm_call_id", "") or _message_field(msg, "id", "")
            if current_call_id and msg_call_id == current_call_id:
                break
            msg_index = _append_assistant_message_entries(messages_array, msg, msg_index)
            continue

        content = _message_field(msg, "content", "") or ""
        content_str = str(content) if content else ""
        if content_str.strip():
            msg_index, _ = _append_request_full_entries(messages_array, content_str, msg_index)

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


def _build_available_tool_context(
    *,
    all_tool_calls: list | None,
    agent_name: str | None = None,
    llm_calls: list | None = None,
    project_dir: str | None = None,
    session_file: str | None = None,
    subagent_type: str | None = None,
    call_timestamp: str | None = None,
) -> dict:
    """Build available-tool context with source metadata."""
    if agent_name == "claude_code":
        resolved = resolve_claude_code_available_tools(
            project_dir=project_dir,
            session_file=session_file,
            subagent_type=subagent_type,
            call_timestamp=call_timestamp,
        )
        return {
            "available_tools": resolved.tools,
            "available_tools_source": resolved.source,
            "available_tools_agent_name": resolved.agent_name,
            "available_tools_definition_path": resolved.definition_path,
            "available_tools_reason": resolved.reason,
        }

    return {
        "available_tools": _build_available_tools(
            all_tool_calls=all_tool_calls,
            agent_name=agent_name,
            llm_calls=llm_calls,
            project_dir=project_dir,
        ),
        "available_tools_source": "",
        "available_tools_agent_name": "",
        "available_tools_definition_path": "",
        "available_tools_reason": "",
    }


def _build_available_tools(
    all_tool_calls: list | None,
    agent_name: str | None = None,
    llm_calls: list | None = None,
    project_dir: str | None = None,
) -> list[str]:
    """Collect request-side available tool names for attribution.

    Claude Code is resolved from the selected main/subagent definition or from
    the default built-in registry.  It never infers request ``tool_schemas``
    from response-side tool calls.
    """
    if agent_name == "claude_code":
        resolved = resolve_claude_code_available_tools(
            project_dir=project_dir,
        )
        return resolved.tools

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
