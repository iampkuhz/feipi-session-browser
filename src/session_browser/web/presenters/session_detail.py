"""说明:Session detail presenter..

Extracted view-model construction logic for the session-detail page.
Kept in a separate module so it can be unit-tested in isolation and
does not clutter the HTTP routes handler.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from session_browser.domain.models import (
    ChatMessage,
    ConversationRound,
    LLMCall,
    NormalizedTokenBreakdown,
    SubagentRun,
    TokenProvider,
    ToolCall,
)
from session_browser.domain.token_normalizer import normalize_tokens

if TYPE_CHECKING:
    from collections.abc import Callable

_PROMPT_PREVIEW_CHARS = 80
_PAYLOAD_PREVIEW_CHARS = 200
_TOOL_RESULT_PREVIEW_LIMIT = 3
_REQUEST_PAYLOAD_MISSING_REASON = (
    'current session data source does not persist raw HTTP request payload'
)
_RESPONSE_PAYLOAD_MISSING_REASON = 'current session data source does not persist raw HTTP response'


def _merge_messages(msgs: list[ChatMessage]) -> ChatMessage:
    """合并 一个 list of same-role messages,转换为 一个 ChatMessage.

    Args:
        msgs: Consecutive same-role messages collected while building rounds.

    Returns:
        Single message preserving the first role, latest metadata, merged text,
        tool calls, and last available usage payload.
    """
    if len(msgs) == 1:
        return msgs[0]

    content = '\n\n'.join(m.content for m in msgs if m.content)
    # 使用 该 latest timestamp
    timestamp = msgs[-1].timestamp
    # 合并 tool_calls,来源于 所有 messages
    all_tool_calls = []
    for m in msgs:
        all_tool_calls.extend(m.tool_calls)
    # 合并 usage (take 该 last non-None)
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
        llm_call_id=msgs[-1].llm_call_id,
        llm_status=msgs[-1].llm_status,
    )


def _append_tool_calls_to_round(
    round_obj: ConversationRound,
    assistant_tool_refs: list[dict],
    all_tool_calls: list[ToolCall],
) -> None:
    """Append tool calls,来源于 一个 skipped no-text assistant to 一个 existing round.

    Args:
        round_obj: Round receiving tool calls emitted by a hidden assistant turn.
        assistant_tool_refs: Raw assistant tool-use refs used to match tool ids.
        all_tool_calls: Session-level tool calls used as the canonical rows.
    """
    matched_ids = {mt.get('id') for mt in assistant_tool_refs if mt.get('id')}
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
) -> ConversationRound:
    """创建 一个 ConversationRound,使用 token calculation 和 tool call matching.

    Args:
        user_msg: User-side prompt message assigned to the round.
        assistant_msg: Assistant response that defines the round boundary.
        all_tool_calls: Session-level tool calls used to attach matched tools.
        total_session_tokens: Total session tokens used to derive round share.
        agent: Provider key controlling usage normalization semantics.

    Returns:
        Conversation round with matched tool calls, token totals, token share,
        and direct/nested LLM call counts.
    """
    # Match tool calls,来源于 assistant message
    round_tool_calls = []
    if assistant_msg.tool_calls:
        matched_ids = {mt.get('id') for mt in assistant_msg.tool_calls if mt.get('id')}
        for tc in all_tool_calls:
            if tc.tool_use_id and tc.tool_use_id in matched_ids:
                round_tool_calls.append(tc)

    # Token info (Claude Code, Qoder, 和 Codex 所有 have per-message usage data)
    round_input = 0
    round_output = 0
    round_cached = 0
    round_cache_write = 0
    if agent in ('claude_code', 'qoder', 'codex') and assistant_msg.usage:
        if agent == 'codex':
            bd = normalize_tokens(assistant_msg.usage, provider=TokenProvider.CODEX)
            round_input = bd.fresh_input_tokens
            round_output = bd.output_tokens
            round_cached = bd.cache_read_tokens
            round_cache_write = bd.cache_write_tokens
        else:
            round_input = assistant_msg.usage.get('input_tokens', 0)
            round_output = assistant_msg.usage.get('output_tokens', 0)
            round_cached = assistant_msg.usage.get(
                'cache_read_input_tokens',
                assistant_msg.usage.get('cache_read_tokens', 0),
            )
            round_cache_write = assistant_msg.usage.get('cache_creation_input_tokens', 0)

    round_total = round_input + round_output + round_cached + round_cache_write
    token_ratio = round_total / total_session_tokens if total_session_tokens > 0 else 0
    usage_fragment_count = 0
    if assistant_msg.usage:
        usage_fragment_count = int(assistant_msg.usage.get('_usage_fragment_count', 0) or 0)
    direct_llm_calls = usage_fragment_count or (1 if assistant_msg.llm_call_id else 0)
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
    prev_call_tools: list[ToolCall],
    round_obj: ConversationRound,
    call_index_in_round: int,
) -> str:
    """Derive 一个 human-readable hint,用于 what was sent as prompt to this LLM call.

    Args:
        prev_call_tools: Tool calls produced by the previous LLM call in the
            same round.
        round_obj: Conversation round containing the user prompt context.
        call_index_in_round: Zero-based LLM call index inside the round.

    Returns:
        Prompt preview string used by trace rows.
    """
    # 说明:First call in round -> show user message
    if call_index_in_round == 0:
        user_text = (
            round_obj.user_msg.content[:_PROMPT_PREVIEW_CHARS] if round_obj.user_msg.content else ''
        )
        if user_text:
            return f'User: {user_text}'

    # Subsequent calls -> tool results,来源于 prior call(s)
    if prev_call_tools:
        tool_names = ', '.join(tc.name for tc in prev_call_tools[:_TOOL_RESULT_PREVIEW_LIMIT])
        suffix = (
            f' +{len(prev_call_tools) - _TOOL_RESULT_PREVIEW_LIMIT}'
            if len(prev_call_tools) > _TOOL_RESULT_PREVIEW_LIMIT
            else ''
        )
        return f'{len(prev_call_tools)} tool results: {tool_names}{suffix}'

    return ''


def _normalize_codex_usage(
    usage: dict,
    cumulative_state: dict,
) -> dict:
    """将 Codex 累计用量转换为单次调用 delta.

    Args:
        usage: Raw Codex usage payload from an assistant message.
        cumulative_state: Mutable previous cumulative totals for this stream.

    Returns:
        Per-call usage delta with input, cache read, cache write, and output
        fields expected by downstream normalization.
    """
    raw_input = usage.get('input_tokens', 0) or 0
    cached = (
        usage.get('cached_input_tokens')
        or usage.get('cache_read_input_tokens')
        or usage.get('cache_read_tokens')
        or 0
    )
    output = usage.get('output_tokens', 0) or 0
    cache_write = usage.get('cache_creation_input_tokens', usage.get('cache_write_tokens', 0)) or 0

    # 读取上一条累计快照,字段名必须与写入状态保持一致.
    prev_input = cumulative_state.get('input_tokens', 0)
    prev_cached = cumulative_state.get('cached_input_tokens', 0)
    prev_output = cumulative_state.get('output_tokens', 0)
    prev_cache_write = cumulative_state.get('cache_creation_input_tokens', 0)

    # 累计值理论上单调递增;若 provider 重置,按 0 处理本段负 delta.
    delta_input = max(raw_input - prev_input, 0)
    delta_cached = max(cached - prev_cached, 0)
    delta_output = max(output - prev_output, 0)
    delta_cache_write = max(cache_write - prev_cache_write, 0)

    # 这里保留 provider_request_input delta,后续 normalizer 再拆出 Fresh.
    delta_fresh = delta_input

    # 更新状态供下一次累计快照计算 delta.
    cumulative_state['input_tokens'] = raw_input
    cumulative_state['cached_input_tokens'] = cached
    cumulative_state['output_tokens'] = output
    cumulative_state['cache_creation_input_tokens'] = cache_write

    return {
        'input_tokens': delta_fresh,
        'cache_read_input_tokens': delta_cached,
        'cache_creation_input_tokens': delta_cache_write,
        'output_tokens': delta_output,
    }


def _usage_int(usage: dict, *keys: str) -> int:
    """Read the first integer-like usage value from a list of aliases.

    Args:
        usage: Raw usage payload from an assistant message.
        *keys: Field aliases checked in priority order.

    Returns:
        Integer value for the first coercible field, or ``0`` when none exists.
    """
    for key in keys:
        value = usage.get(key)
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return 0


def _codex_usage_is_cumulative(usage: dict) -> bool:
    """Detect whether a Codex usage payload stores cumulative totals.

    Args:
        usage: Raw Codex usage payload with optional source metadata.

    Returns:
        ``True`` when the payload needs delta conversion before rendering.
    """
    if usage.get('_is_cumulative'):
        return True
    source = str(usage.get('_usage_source') or '')
    if source == 'total_token_usage_delta':
        return False
    return 'total_token_usage' in source and 'last_token_usage' not in source


def _codex_usage_for_llm_call(usage: dict, cumulative_state: dict) -> dict:
    """返回 per-call Codex usage,用于 interaction rows.

    ``sources.codex_session_source._extract_messages`` already aggregates
    ``last_token_usage`` into per-assistant-message usage.  Only records that
    explicitly identify ``total_token_usage`` as their source should be
    converted from cumulative totals to deltas here.

    Args:
        usage: Raw Codex usage payload from an assistant message.
        cumulative_state: Mutable previous cumulative totals for this stream.

    Returns:
        Per-call Codex usage payload using the canonical keys expected by
        ``normalize_tokens``.
    """
    if _codex_usage_is_cumulative(usage):
        return _normalize_codex_usage(usage, cumulative_state)
    return {
        'input_tokens': _usage_int(usage, 'input_tokens', 'prompt_tokens', 'input'),
        'cache_read_input_tokens': _usage_int(
            usage,
            'cached_input_tokens',
            'cache_read_input_tokens',
            'cache_read_tokens',
            'cached_tokens',
        ),
        'cache_creation_input_tokens': _usage_int(
            usage, 'cache_creation_input_tokens', 'cache_write_tokens'
        ),
        'output_tokens': _usage_int(usage, 'output_tokens', 'completion_tokens', 'output'),
    }


def _token_breakdown_for_agent(usage: dict, agent: str) -> NormalizedTokenBreakdown:
    """Normalize usage fields according to the session agent.

    Args:
        usage: Per-call usage payload already converted for Codex when needed.
        agent: Session agent key controlling provider-specific normalization.

    Returns:
        Normalized token breakdown used by trace rows and attribution panels.
    """
    if agent == 'codex':
        return normalize_tokens(usage, provider=TokenProvider.CODEX)
    if agent == 'qoder':
        return normalize_tokens(usage, provider=TokenProvider.QODER)
    if agent == 'claude_code':
        return normalize_tokens(usage, provider=TokenProvider.ANTHROPIC)
    return normalize_tokens(usage)


def _find_subagent_parent_tool(tool_calls: list[ToolCall], agent_id: str) -> ToolCall | None:
    """查找 该 main-scope tool call that spawned 一个 subagent run.

    Claude records this as an ``Agent`` tool, while Codex records it as
    ``spawn_agent``.  The stable association is the normalized subagent id, not
    the provider-specific tool name.

    Args:
        tool_calls: Session-level tool calls from main and subagent scopes.
        agent_id: Normalized subagent id from the run summary.

    Returns:
        Main-scope parent tool call that spawned the subagent, if found.
    """
    if not agent_id:
        return None
    for tc in tool_calls:
        if tc.scope != 'main':
            continue
        summary = tc.subagent_summary or {}
        linked_agent_id = tc.subagent_id or summary.get('agent_id', '')
        if linked_agent_id == agent_id:
            return tc
    return None


def build_llm_calls(  # noqa: PLR0912, PLR0915 - preserves trace-row contract
    messages: list[ChatMessage],
    tool_calls: list[ToolCall],
    rounds: list[ConversationRound],
    subagent_runs: list[SubagentRun],
    agent: str = '',
) -> list[LLMCall]:
    """提取 LLMCall objects, 该 token/attribution semantic boundary.

    Main agent: one call per assistant response usage boundary.
    Subagent: one call per sidechain LLM call.

    For agents without llm_call_id (e.g. Codex), a synthetic ID is generated
    and trace-row assignment is done by sequential matching against rounds.

    Args:
        messages: Chronological chat messages for the session.
        tool_calls: Session-level tool calls used for attribution and nesting.
        rounds: Conversation rounds built from the same messages.
        subagent_runs: Parsed subagent sidechain runs with summaries/messages.
        agent: Session agent key controlling Codex usage delta semantics.

    Returns:
        LLM call rows ordered by main-session traversal followed by subagent
        calls. Main calls are assigned to rounds; subagent calls keep parent
        tool metadata when available.
    """
    llm_calls: list[LLMCall] = []

    # 映射 assistant llm_call_id -> round_index
    call_id_to_round: dict[str, int] = {}
    for r_idx, r in enumerate(rounds):
        if r.assistant_msg.llm_call_id:
            call_id_to_round[r.assistant_msg.llm_call_id] = r_idx

    # For agents without llm_call_id, build 一个 position-based mapping:
    # 说明:assistant message index -> round_index by sequential match.
    assistant_msg_indices: list[int] = [
        i for i, msg in enumerate(messages) if msg.role == 'assistant'
    ]
    # 映射 message_index -> round_index,用于 messages without llm_call_id
    msg_idx_to_round: dict[int, int] = {}
    round_cursor = 0
    for msg_idx in assistant_msg_indices:
        msg = messages[msg_idx]
        if msg.llm_call_id and msg.llm_call_id in call_id_to_round:
            # 说明:Already mapped by ID
            msg_idx_to_round[msg_idx] = call_id_to_round[msg.llm_call_id]
        # Assign to current round cursor, advance,当 round assistant
        # 说明:message timestamp matches (or just assign sequentially).
        elif round_cursor < len(rounds):
            msg_idx_to_round[msg_idx] = round_cursor
            round_cursor += 1

    # Shared cumulative state,用于 Codex usage normalization (Issue 2: first call
    # should never show cache reads — deltas are computed,来源于 cumulative totals)
    codex_cumulative: dict = {}

    # Main agent calls - track prior call's tools,用于 prompt context
    main_calls_in_round: dict[int, list[LLMCall]] = {}
    for msg_idx, msg in enumerate(messages):
        if msg.role != 'assistant':
            continue

        # Determine round index: by llm_call_id 或 by position mapping
        if msg.llm_call_id and msg.llm_call_id in call_id_to_round:
            r_idx = call_id_to_round[msg.llm_call_id]
        elif msg_idx in msg_idx_to_round:
            r_idx = msg_idx_to_round[msg_idx]
        else:
            continue

        usage = msg.usage or {}
        if agent == 'codex' and usage:
            usage = _codex_usage_for_llm_call(usage, codex_cumulative)
        token_breakdown = _token_breakdown_for_agent(usage, agent) if usage else None
        round_tools = rounds[r_idx].tool_calls if r_idx < len(rounds) else []
        round_obj = rounds[r_idx] if r_idx < len(rounds) else None

        prior_tools: list[ToolCall] = []
        call_index = 0
        if main_calls_in_round.get(r_idx):
            prior_call = main_calls_in_round[r_idx][-1]
            prior_tools = prior_call.tool_calls
            call_index = len(main_calls_in_round[r_idx])

        prompt_hint = ''
        if round_obj:
            prompt_hint = _derive_prompt_preview(
                prior_tools,
                round_obj,
                call_index,
            )

        request_full = msg.request_full
        request_preview = request_full[:_PAYLOAD_PREVIEW_CHARS] if request_full else prompt_hint

        # Generate synthetic ID,用于 agents without llm_call_id
        call_id = msg.llm_call_id or f'synthetic-R{r_idx + 1}-M{call_index + 1}'

        llm_call = LLMCall(
            id=call_id,
            model=msg.model,
            scope='main',
            subagent_id='',
            round_index=r_idx,
            parent_id='',
            parent_tool_name='',
            timestamp=msg.timestamp,
            status=msg.llm_status,
            input_tokens=usage.get('input_tokens', 0),
            output_tokens=usage.get('output_tokens', 0),
            cache_read_tokens=usage.get(
                'cache_read_input_tokens', usage.get('cache_read_tokens', 0)
            ),
            cache_write_tokens=usage.get('cache_creation_input_tokens', 0),
            prompt_preview=prompt_hint,
            request_preview=request_preview,
            request_full=request_full,
            response_preview=msg.content[:_PAYLOAD_PREVIEW_CHARS],
            response_full=msg.content,
            tool_calls=[tc for tc in round_tools if tc.scope == 'main'],
            tool_call_count=len([tc for tc in round_tools if tc.scope == 'main']),
            failed_tool_count=sum(1 for tc in round_tools if tc.scope == 'main' and tc.is_failed),
            token_breakdown_normalized=token_breakdown,
            request_payload_raw='',
            request_payload_missing_reason=_REQUEST_PAYLOAD_MISSING_REASON,
            response_payload_raw='',
            response_payload_missing_reason=_RESPONSE_PAYLOAD_MISSING_REASON,
            finish_reason=msg.stop_reason,
            tool_calls_raw=json.dumps(msg.tool_calls, ensure_ascii=False) if msg.tool_calls else '',
            content_blocks=msg.content_blocks,
        )
        main_calls_in_round.setdefault(r_idx, []).append(llm_call)
        llm_calls.append(llm_call)

    # Subagent individual calls - 一个 per internal LLM turn
    for run in subagent_runs:
        summary = run['summary']
        agent_id = summary['agent_id']

        parent_tc = _find_subagent_parent_tool(tool_calls, agent_id)

        parent_round = 0
        if parent_tc:
            for r_idx, r in enumerate(rounds):
                if any(tc.tool_use_id == parent_tc.tool_use_id for tc in r.tool_calls):
                    parent_round = r_idx
                    break

        for msg in run['messages']:
            if msg.role != 'assistant' or not msg.llm_call_id:
                continue
            usage = msg.usage or {}
            if agent == 'codex' and usage:
                if 'subagent_cumulative' not in codex_cumulative:
                    codex_cumulative['subagent_cumulative'] = {}
                sub_cum = codex_cumulative['subagent_cumulative']
                if agent_id not in sub_cum:
                    sub_cum[agent_id] = {}
                usage = _codex_usage_for_llm_call(usage, sub_cum[agent_id])
            token_breakdown = _token_breakdown_for_agent(usage, agent) if usage else None

            request_full = msg.request_full if msg.request_full else ''
            request_preview = request_full[:_PAYLOAD_PREVIEW_CHARS] if request_full else ''
            response_preview = msg.content[:_PAYLOAD_PREVIEW_CHARS] if msg.content else ''

            llm_calls.append(
                LLMCall(
                    id=msg.llm_call_id,
                    model=msg.model,
                    scope='subagent',
                    subagent_id=agent_id,
                    round_index=parent_round,
                    parent_id=parent_tc.tool_use_id if parent_tc else '',
                    parent_tool_name=parent_tc.name if parent_tc else 'Agent',
                    timestamp=msg.timestamp,
                    status='ok',
                    input_tokens=usage.get('input_tokens', 0),
                    output_tokens=usage.get('output_tokens', 0),
                    cache_read_tokens=usage.get(
                        'cache_read_input_tokens', usage.get('cache_read_tokens', 0)
                    ),
                    cache_write_tokens=usage.get('cache_creation_input_tokens', 0),
                    prompt_preview=f'Subagent turn ({msg.content[:_PROMPT_PREVIEW_CHARS]})'
                    if msg.content
                    else 'Subagent turn',
                    request_preview=request_preview,
                    request_full=request_full,
                    response_preview=response_preview,
                    response_full=msg.content,
                    tool_calls=[],
                    tool_call_count=0,
                    failed_tool_count=0,
                    token_breakdown_normalized=token_breakdown,
                    request_payload_raw='',
                    request_payload_missing_reason=_REQUEST_PAYLOAD_MISSING_REASON,
                    response_payload_raw='',
                    response_payload_missing_reason=_RESPONSE_PAYLOAD_MISSING_REASON,
                    finish_reason=msg.stop_reason,
                    tool_calls_raw=json.dumps(msg.tool_calls, ensure_ascii=False)
                    if msg.tool_calls
                    else '',
                    content_blocks=msg.content_blocks,
                )
            )

    return llm_calls


def _build_subagent_interactions(
    llm_calls: list[LLMCall],
    subagent_runs: list[SubagentRun],
    tool_calls: list[ToolCall],
) -> list[LLMCall]:
    """构建 一个 aggregated interaction per subagent run (for rounds view).

    Each subagent run becomes a single interaction that aggregates all its
    internal LLM calls and tools, so the round expand shows it as one nested
    block instead of repeating 260 times.

    Args:
        llm_calls: Per-call rows built by ``build_llm_calls``.
        subagent_runs: Parsed subagent sidechain runs with summaries/messages.
        tool_calls: Session-level tool calls used to attach parent and nested
            tool context.

    Returns:
        Aggregated subagent interaction rows keyed by subagent id.
    """
    interactions: list[LLMCall] = []
    for run in subagent_runs:
        summary = run['summary']
        agent_id = summary['agent_id']

        parent_tc = _find_subagent_parent_tool(tool_calls, agent_id)

        # 查找 individual subagent calls,用于 this run
        sub_calls = [c for c in llm_calls if c.scope == 'subagent' and c.subagent_id == agent_id]
        if not sub_calls:
            continue

        parent_round = sub_calls[0].round_index
        total_fresh_input = sum(c.input_tokens for c in sub_calls)
        total_output = sum(c.output_tokens for c in sub_calls)
        total_cr = sum(c.cache_read_tokens for c in sub_calls)
        total_cw = sum(c.cache_write_tokens for c in sub_calls)

        response = ''
        request_full = ''
        for c in reversed(sub_calls):
            if c.response_full:
                response = c.response_full
                break
        for c in sub_calls:
            if c.request_full:
                request_full = c.request_full
                break

        sub_tools = [tc for tc in tool_calls if tc.subagent_id == agent_id]

        interactions.append(
            LLMCall(
                id=f'subagent-{agent_id}',
                model=sub_calls[0].model if sub_calls else '',
                scope='subagent',
                subagent_id=agent_id,
                round_index=parent_round,
                parent_id=parent_tc.tool_use_id if parent_tc else '',
                parent_tool_name=parent_tc.name if parent_tc else 'Agent',
                timestamp=sub_calls[0].timestamp,
                status='ok',
                input_tokens=total_fresh_input,
                output_tokens=total_output,
                cache_read_tokens=total_cr,
                cache_write_tokens=total_cw,
                prompt_preview='',
                request_preview=request_full[:_PAYLOAD_PREVIEW_CHARS] if request_full else '',
                request_full=request_full,
                response_preview=response[:_PAYLOAD_PREVIEW_CHARS],
                response_full=response,
                tool_calls=sub_tools,
                tool_call_count=len(sub_tools),
                failed_tool_count=sum(1 for t in sub_tools if t.is_failed),
                request_payload_raw='',
                request_payload_missing_reason=_REQUEST_PAYLOAD_MISSING_REASON,
                response_payload_raw='',
                response_payload_missing_reason=_RESPONSE_PAYLOAD_MISSING_REASON,
                finish_reason='',
                tool_calls_raw='',
            )
        )

    return interactions


def assign_interactions_to_rounds(
    rounds: list[ConversationRound],
    llm_calls: list[LLMCall],
    tool_calls: list[ToolCall],
    subagent_runs: list[SubagentRun],
) -> None:
    """说明:Populate round.interactions.

    Main agent: individual calls stay as individual interactions.
    Subagent: NOT added to r.interactions directly. Instead, they will be
    attached to their parent LLM call in the view model, so the round expand
    shows them as nested items under the Agent tool call that spawned them.

    Args:
        rounds: Conversation rounds to mutate in place.
        llm_calls: LLM calls already assigned to round indexes.
        tool_calls: Session-level tool calls retained for API compatibility.
        subagent_runs: Subagent runs retained for API compatibility.
    """
    _ = (tool_calls, subagent_runs)
    # 分组 main-agent calls by round
    main_by_round: dict[int, list[LLMCall]] = {}
    for call in llm_calls:
        if call.scope == 'main':
            main_by_round.setdefault(call.round_index, []).append(call)

    for r_idx, r in enumerate(rounds):
        main_calls = main_by_round.get(r_idx, [])
        # 说明:Only main calls in r.interactions; subagents are nested in view model
        r.interactions = main_calls


def build_rounds(  # noqa: PLR0913 - public presenter route contract
    messages: list[ChatMessage],
    tool_calls: list[ToolCall],
    session_input_tokens: int,
    session_output_tokens: int,
    session_cached_tokens: int,
    session_cache_write_tokens: int,
    agent: str,
    md_filter: Callable[[str], str],
) -> list[ConversationRound]:
    """分组 messages,转换为 conversation rounds 和 compute token ratios.

    Each assistant LLM response becomes its own round. Consecutive user
    messages before an assistant response are merged; assistant responses that
    happen during tool loops get an empty user_msg so repeated tool iterations
    stay visible instead of collapsing into one giant round.

    Token ratio is derived from the assistant message's usage data (Claude, Qoder)
    or set to zero when usage data is unavailable (Codex).

    ``md_filter`` is retained as a compatibility parameter; rendering now
    happens in web renderers/view-model code instead of mutating ChatMessage.

    Args:
        messages: Chronological chat messages for the session.
        tool_calls: Session-level tool calls used to match assistant tool refs.
        session_input_tokens: Fresh input token total for the session.
        session_output_tokens: Output token total for the session.
        session_cached_tokens: Cache-read token total for the session.
        session_cache_write_tokens: Cache-write token total for the session.
        agent: Session agent key controlling per-message usage semantics.
        md_filter: Legacy markdown filter retained for route compatibility.

    Returns:
        Ordered conversation rounds. Each visible assistant response becomes a
        round; trailing user-only messages produce an empty assistant round.
    """
    _ = md_filter
    if not messages:
        return []

    total_session_tokens = (
        session_input_tokens
        + session_output_tokens
        + session_cached_tokens
        + session_cache_write_tokens
    )

    # Step 1: Pair each assistant LLM response,转换为 its
    # 说明:own round. Tool-result pseudo-user messages are filtered in sources, so
    # 说明:consecutive assistant responses are expected during tool loops.
    pending_users: list[ChatMessage] = []
    rounds: list[ConversationRound] = []
    for msg in messages:
        if msg.role == 'user':
            pending_users.append(msg)
            continue

        if msg.role == 'assistant':
            # 跳过,如果 assistant has no text content - merge tool calls into
            # the previous round 和 defer user input to 该 next meaningful
            # round. This handles tool-loop follow-ups where 该 model only
            # 说明:emits tool_use blocks without any visible text.
            has_content = bool(msg.content and msg.content.strip())
            has_codex_call_usage = bool(agent == 'codex' and msg.usage)
            if not has_content and msg.tool_calls and not has_codex_call_usage:
                # 合并 this assistant's tool calls,转换为 该 last round.
                if rounds:
                    _append_tool_calls_to_round(rounds[-1], msg.tool_calls, tool_calls)
                continue
            if not has_content and not has_codex_call_usage:
                continue

            if pending_users:
                merged_user = _merge_messages(pending_users)
                pending_users = []
            else:
                merged_user = ChatMessage(role='user', content='', timestamp=msg.timestamp)
            rounds.append(
                _make_round(
                    merged_user,
                    msg,
                    tool_calls,
                    total_session_tokens,
                    agent,
                )
            )

    if pending_users:
        rounds.append(
            _make_round(
                _merge_messages(pending_users),
                ChatMessage(role='assistant', content='', timestamp=''),
                tool_calls,
                total_session_tokens,
                agent,
            )
        )

    return rounds
