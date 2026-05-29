"""Session detail presenter.

Extracted view-model construction logic for the session-detail page.
Kept in a separate module so it can be unit-tested in isolation and
does not clutter the HTTP routes handler.
"""
from __future__ import annotations

import json
from typing import Callable

from session_browser.domain.models import (
    ChatMessage,
    ConversationRound,
    LLMCall,
    ToolCall,
)


def _merge_messages(msgs: list[ChatMessage]) -> ChatMessage:
    """Merge a list of same-role messages into one ChatMessage."""
    if len(msgs) == 1:
        return msgs[0]

    content = "\n\n".join(m.content for m in msgs if m.content)
    content_html = "\n\n".join(m.content_html for m in msgs if m.content_html)
    # Use the latest timestamp
    timestamp = msgs[-1].timestamp
    # Merge tool_calls from all messages
    all_tool_calls = []
    for m in msgs:
        all_tool_calls.extend(m.tool_calls)
    # Merge usage (take the last non-None)
    usage = None
    for m in msgs:
        if m.usage:
            usage = m.usage

    return ChatMessage(
        role=msgs[0].role,
        content=content,
        timestamp=timestamp,
        model=msgs[-1].model,
        tool_calls=all_tool_calls,
        usage=usage,
        content_html=content_html,
        llm_call_id=msgs[-1].llm_call_id,
        llm_status=msgs[-1].llm_status,
    )


def _append_tool_calls_to_round(
    round_obj,  # ConversationRound
    assistant_tool_refs: list[dict],
    all_tool_calls: list[ToolCall],
) -> None:
    """Append tool calls from a skipped (no-text) assistant to an existing round."""
    matched_ids = {mt.get("id") for mt in assistant_tool_refs if mt.get("id")}
    for tc in all_tool_calls:
        if tc.tool_use_id and tc.tool_use_id in matched_ids and tc not in round_obj.tool_calls:
            round_obj.tool_calls.append(tc)
            round_obj.llm_call_count += tc.llm_call_count
            round_obj.llm_error_count += tc.llm_error_count


def _make_round(
    user_msg: ChatMessage,
    assistant_msg: ChatMessage,
    all_tool_calls: list[ToolCall],
    total_session_tokens: int,
    agent: str,
    session_cache_write_tokens: int = 0,
) -> ConversationRound:
    """Create a ConversationRound with token calculation and tool call matching."""
    # Match tool calls from assistant message
    round_tool_calls = []
    if assistant_msg.tool_calls:
        matched_ids = {
            mt.get("id")
            for mt in assistant_msg.tool_calls
            if mt.get("id")
        }
        for tc in all_tool_calls:
            if tc.tool_use_id and tc.tool_use_id in matched_ids:
                round_tool_calls.append(tc)

    # Token info (Claude Code, Qoder, and Codex all have per-message usage data)
    round_input = 0
    round_output = 0
    round_cached = 0
    round_cache_write = 0
    if agent in ("claude_code", "qoder", "codex") and assistant_msg.usage:
        round_input = assistant_msg.usage.get("input_tokens", 0)
        round_output = assistant_msg.usage.get("output_tokens", 0)
        # Codex uses cached_input_tokens; Claude/Qoder use cache_read_input_tokens
        round_cached = assistant_msg.usage.get(
            "cache_read_input_tokens",
            assistant_msg.usage.get("cached_input_tokens", 0),
        )
        # Codex has no cache write tokens
        round_cache_write = assistant_msg.usage.get("cache_creation_input_tokens", 0)

    round_total = round_input + round_output + round_cached + round_cache_write
    token_ratio = round_total / total_session_tokens if total_session_tokens > 0 else 0
    direct_llm_calls = 1 if assistant_msg.llm_call_id else 0
    nested_llm_calls = sum(tc.llm_call_count for tc in round_tool_calls)
    nested_llm_errors = sum(tc.llm_error_count for tc in round_tool_calls)

    return ConversationRound(
        user_msg=user_msg,
        assistant_msg=assistant_msg,
        tool_calls=round_tool_calls,
        total_tokens=round_total,
        token_ratio=token_ratio,
        llm_call_count=direct_llm_calls + nested_llm_calls,
        llm_error_count=nested_llm_errors,
    )


def _derive_prompt_preview(
    msg: ChatMessage,
    round_tool_calls: list[ToolCall],
    prev_call_tools: list[ToolCall],
    round: ConversationRound,
    messages: list[ChatMessage],
    call_index_in_round: int,
) -> str:
    """Derive a human-readable hint for what was sent as prompt to this LLM call.

    Returns a short string (<=120 chars) summarising the prompt context.
    """
    # First call in round -> show user message
    if call_index_in_round == 0:
        user_text = round.user_msg.content[:80] if round.user_msg.content else ""
        if user_text:
            return f"User: {user_text}"

    # Subsequent calls -> tool results from prior call(s)
    if prev_call_tools:
        tool_names = ", ".join(tc.name for tc in prev_call_tools[:3])
        suffix = f" +{len(prev_call_tools) - 3}" if len(prev_call_tools) > 3 else ""
        return f"{len(prev_call_tools)} tool results: {tool_names}{suffix}"

    return ""


def build_llm_calls(
    messages: list[ChatMessage],
    tool_calls: list[ToolCall],
    rounds: list[ConversationRound],
    subagent_runs: list[dict],
) -> list[LLMCall]:
    """Extract individual LLMCall objects (one per LLM turn).

    Main agent: one call per assistant message.
    Subagent: one call per internal turn (so the LLM Calls tab shows all).

    For agents without llm_call_id (e.g. Codex), a synthetic ID is generated
    and round assignment is done by sequential matching against rounds.
    """
    llm_calls: list[LLMCall] = []

    # Map assistant llm_call_id -> round_index
    call_id_to_round: dict[str, int] = {}
    for r_idx, r in enumerate(rounds):
        if r.assistant_msg.llm_call_id:
            call_id_to_round[r.assistant_msg.llm_call_id] = r_idx

    # For agents without llm_call_id, build a position-based mapping:
    # assistant message index -> round_index by sequential match.
    assistant_msg_indices: list[int] = [
        i for i, msg in enumerate(messages) if msg.role == "assistant"
    ]
    # Map message_index -> round_index for messages without llm_call_id
    msg_idx_to_round: dict[int, int] = {}
    round_cursor = 0
    for msg_idx in assistant_msg_indices:
        msg = messages[msg_idx]
        if msg.llm_call_id and msg.llm_call_id in call_id_to_round:
            # Already mapped by ID
            msg_idx_to_round[msg_idx] = call_id_to_round[msg.llm_call_id]
        else:
            # Assign to current round cursor, advance when round assistant
            # message timestamp matches (or just assign sequentially).
            if round_cursor < len(rounds):
                msg_idx_to_round[msg_idx] = round_cursor
                round_cursor += 1

    # Main agent calls - track prior call's tools for prompt context
    main_calls_in_round: dict[int, list[LLMCall]] = {}
    for msg_idx, msg in enumerate(messages):
        if msg.role != "assistant":
            continue

        # Determine round index: by llm_call_id or by position mapping
        if msg.llm_call_id and msg.llm_call_id in call_id_to_round:
            r_idx = call_id_to_round[msg.llm_call_id]
        elif msg_idx in msg_idx_to_round:
            r_idx = msg_idx_to_round[msg_idx]
        else:
            continue

        usage = msg.usage or {}
        round_tools = rounds[r_idx].tool_calls if r_idx < len(rounds) else []
        round_obj = rounds[r_idx] if r_idx < len(rounds) else None

        prior_tools: list[ToolCall] = []
        call_index = 0
        if r_idx in main_calls_in_round and main_calls_in_round[r_idx]:
            prior_call = main_calls_in_round[r_idx][-1]
            prior_tools = prior_call.tool_calls
            call_index = len(main_calls_in_round[r_idx])

        prompt_hint = ""
        if round_obj:
            prompt_hint = _derive_prompt_preview(
                msg, round_tools, prior_tools, round_obj, messages, call_index
            )

        request_full = msg.request_full
        request_preview = request_full[:200] if request_full else prompt_hint

        # Generate synthetic ID for agents without llm_call_id
        call_id = msg.llm_call_id or f"synthetic-R{r_idx + 1}-M{call_index + 1}"

        llm_call = LLMCall(
            id=call_id,
            model=msg.model,
            scope="main",
            subagent_id="",
            round_index=r_idx,
            parent_id="",
            parent_tool_name="",
            timestamp=msg.timestamp,
            status=msg.llm_status,
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            cache_read_tokens=usage.get("cache_read_input_tokens", usage.get("cached_input_tokens", 0)),
            cache_write_tokens=usage.get("cache_creation_input_tokens", 0),
            prompt_preview=prompt_hint,
            request_preview=request_preview,
            request_full=request_full,
            response_preview=msg.content[:200],
            response_full=msg.content,
            tool_calls=[tc for tc in round_tools if tc.scope == "main"],
            tool_call_count=len([tc for tc in round_tools if tc.scope == "main"]),
            failed_tool_count=sum(1 for tc in round_tools if tc.scope == "main" and tc.is_failed),
            request_payload_raw="",
            request_payload_missing_reason="current session data source does not persist raw HTTP request payload",
            response_payload_raw="",
            response_payload_missing_reason="current session data source does not persist raw HTTP response",
            finish_reason=msg.stop_reason,
            tool_calls_raw=json.dumps(msg.tool_calls, ensure_ascii=False) if msg.tool_calls else "",
            content_blocks=msg.content_blocks,
        )
        main_calls_in_round.setdefault(r_idx, []).append(llm_call)
        llm_calls.append(llm_call)

    # Subagent individual calls - one per internal LLM turn
    for run in subagent_runs:
        summary = run["summary"]
        agent_id = summary["agent_id"]

        parent_tc = None
        for tc in tool_calls:
            if tc.name == "Agent" and tc.subagent_summary.get("agent_id") == agent_id:
                parent_tc = tc
                break

        parent_round = 0
        if parent_tc:
            for r_idx, r in enumerate(rounds):
                if any(tc.tool_use_id == parent_tc.tool_use_id for tc in r.tool_calls):
                    parent_round = r_idx
                    break

        for msg in run["messages"]:
            if msg.role != "assistant" or not msg.llm_call_id:
                continue
            usage = msg.usage or {}

            request_full = msg.request_full if msg.request_full else ""
            request_preview = request_full[:200] if request_full else ""
            response_preview = msg.content[:200] if msg.content else ""

            llm_calls.append(LLMCall(
                id=msg.llm_call_id,
                model=msg.model,
                scope="subagent",
                subagent_id=agent_id,
                round_index=parent_round,
                parent_id=parent_tc.tool_use_id if parent_tc else "",
                parent_tool_name=parent_tc.name if parent_tc else "Agent",
                timestamp=msg.timestamp,
                status="ok",
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
                cache_read_tokens=usage.get("cache_read_input_tokens", usage.get("cached_input_tokens", 0)),
                cache_write_tokens=usage.get("cache_creation_input_tokens", 0),
                prompt_preview=f"Subagent turn ({msg.content[:80]})" if msg.content else "Subagent turn",
                request_preview=request_preview,
                request_full=request_full,
                response_preview=response_preview,
                response_full=msg.content,
                tool_calls=[],
                tool_call_count=0,
                failed_tool_count=0,
                request_payload_raw="",
                request_payload_missing_reason="current session data source does not persist raw HTTP request payload",
                response_payload_raw="",
                response_payload_missing_reason="current session data source does not persist raw HTTP response",
                finish_reason=msg.stop_reason,
                tool_calls_raw=json.dumps(msg.tool_calls, ensure_ascii=False) if msg.tool_calls else "",
                content_blocks=msg.content_blocks,
            ))

    return llm_calls


def _build_subagent_interactions(
    llm_calls: list[LLMCall],
    subagent_runs: list[dict],
    tool_calls: list[ToolCall],
) -> list[LLMCall]:
    """Build one aggregated interaction per subagent run (for rounds view).

    Each subagent run becomes a single interaction that aggregates all its
    internal LLM calls and tools, so the round expand shows it as one nested
    block instead of repeating 260 times.
    """
    interactions: list[LLMCall] = []
    for run in subagent_runs:
        summary = run["summary"]
        agent_id = summary["agent_id"]

        parent_tc = None
        for tc in tool_calls:
            if tc.name == "Agent" and tc.subagent_summary.get("agent_id") == agent_id:
                parent_tc = tc
                break

        # Find individual subagent calls for this run
        sub_calls = [c for c in llm_calls if c.scope == "subagent" and c.subagent_id == agent_id]
        if not sub_calls:
            continue

        parent_round = sub_calls[0].round_index
        total_input = sum(c.input_tokens for c in sub_calls)
        total_output = sum(c.output_tokens for c in sub_calls)
        total_cr = sum(c.cache_read_tokens for c in sub_calls)
        total_cw = sum(c.cache_write_tokens for c in sub_calls)

        response = ""
        request_full = ""
        for c in reversed(sub_calls):
            if c.response_full:
                response = c.response_full
                break
        for c in sub_calls:
            if c.request_full:
                request_full = c.request_full
                break

        sub_tools = [tc for tc in tool_calls if tc.subagent_id == agent_id]

        interactions.append(LLMCall(
            id=f"subagent-{agent_id}",
            model=sub_calls[0].model if sub_calls else "",
            scope="subagent",
            subagent_id=agent_id,
            round_index=parent_round,
            parent_id=parent_tc.tool_use_id if parent_tc else "",
            parent_tool_name=parent_tc.name if parent_tc else "Agent",
            timestamp=sub_calls[0].timestamp,
            status="ok",
            input_tokens=total_input,
            output_tokens=total_output,
            cache_read_tokens=total_cr,
            cache_write_tokens=total_cw,
            prompt_preview="",
            request_preview=request_full[:200] if request_full else "",
            request_full=request_full,
            response_preview=response[:200],
            response_full=response,
            tool_calls=sub_tools,
            tool_call_count=len(sub_tools),
            failed_tool_count=sum(1 for t in sub_tools if t.is_failed),
            request_payload_raw="",
            request_payload_missing_reason="current session data source does not persist raw HTTP request payload",
            response_payload_raw="",
            response_payload_missing_reason="current session data source does not persist raw HTTP response",
            finish_reason="",
            tool_calls_raw="",
        ))

    return interactions


def assign_interactions_to_rounds(
    rounds: list[ConversationRound],
    llm_calls: list[LLMCall],
    tool_calls: list[ToolCall],
    subagent_runs: list[dict],
) -> None:
    """Populate round.interactions.

    Main agent: individual calls stay as individual interactions.
    Subagent: replaced by one aggregated interaction per run (so round expand
    shows it as a single nested block, not repeated for every internal turn).
    """
    # Group main-agent calls by round
    main_by_round: dict[int, list[LLMCall]] = {}
    for call in llm_calls:
        if call.scope == "main":
            main_by_round.setdefault(call.round_index, []).append(call)

    # Build aggregated subagent interactions
    subagent_interactions = _build_subagent_interactions(llm_calls, subagent_runs, tool_calls)
    sub_by_round: dict[int, list[LLMCall]] = {}
    for ix in subagent_interactions:
        sub_by_round.setdefault(ix.round_index, []).append(ix)

    for r_idx, r in enumerate(rounds):
        main_calls = main_by_round.get(r_idx, [])
        sub_calls = sub_by_round.get(r_idx, [])
        # Main calls first, then subagent interactions
        r.interactions = main_calls + sub_calls


def build_rounds(
    messages: list[ChatMessage],
    tool_calls: list[ToolCall],
    session_input_tokens: int,
    session_output_tokens: int,
    session_cached_tokens: int,
    session_cache_write_tokens: int,
    agent: str,
    md_filter: Callable[[str], str],
) -> list[ConversationRound]:
    """Group messages into conversation rounds and compute token ratios.

    Each assistant LLM response becomes its own round. Consecutive user
    messages before an assistant response are merged; assistant responses that
    happen during tool loops get an empty user_msg so repeated tool iterations
    stay visible instead of collapsing into one giant round.

    Token ratio is derived from the assistant message's usage data (Claude, Qoder)
    or set to zero when usage data is unavailable (Codex).

    ``md_filter`` is injected by the caller (e.g. routes._md_filter) so this
    module stays independent of the HTTP layer.
    """
    if not messages:
        return []

    total_session_tokens = session_input_tokens + session_output_tokens + session_cached_tokens + session_cache_write_tokens

    # Step 1: Render markdown and pair each assistant LLM response into its
    # own round. Tool-result pseudo-user messages are filtered in sources, so
    # consecutive assistant responses are expected during tool loops.
    pending_users: list[ChatMessage] = []
    rounds: list[ConversationRound] = []
    for msg in messages:
        msg.content_html = md_filter(msg.content)

        if msg.role == "user":
            pending_users.append(msg)
            continue

        if msg.role == "assistant":
            # Skip if assistant has no text content - merge tool calls into
            # the previous round and defer user input to the next meaningful
            # round. This handles tool-loop follow-ups where the model only
            # emits tool_use blocks without any visible text.
            has_content = bool(msg.content and msg.content.strip())
            if not has_content and msg.tool_calls:
                # Merge this assistant's tool calls into the last round.
                if rounds:
                    _append_tool_calls_to_round(rounds[-1], msg.tool_calls, tool_calls)
                continue
            if not has_content:
                continue

            if pending_users:
                merged_user = _merge_messages(pending_users)
                pending_users = []
            else:
                merged_user = ChatMessage(role="user", content="", timestamp=msg.timestamp)
            rounds.append(
                _make_round(merged_user, msg, tool_calls,
                            total_session_tokens, agent, session_cache_write_tokens)
            )

    if pending_users:
        rounds.append(
            _make_round(
                _merge_messages(pending_users),
                ChatMessage(role="assistant", content="", timestamp=""),
                tool_calls,
                total_session_tokens,
                agent,
                session_cache_write_tokens,
            )
        )

    return rounds
