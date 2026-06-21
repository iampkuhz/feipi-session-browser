"""Build the semantic model stored in normalized session artifacts."""

from __future__ import annotations

from typing import Any

from session_browser.normalized.schema import NORMALIZED_SCHEMA_VERSION


def build_normalized_session_model(
    *,
    agent: str,
    session: dict[str, Any],
    source_files: list[dict[str, Any]],
    call_drafts: list[dict[str, Any]],
    parse_warnings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Convert adapter parse output into the current LLM-call semantic model.

    Source adapters call this after reconstructing provider-specific transcript
    details. This layer persists scan-time facts only: LLM calls, usage totals,
    and tool-call edges. Heavier attribution buckets and payload indexes remain
    available for request-time rebuilding from source JSONL.

    Args:
        agent: Source adapter name stored at the artifact root.
        session: Session metadata object already normalized by the adapter.
        source_files: Provenance records for files that contributed to the
            normalized artifact.
        call_drafts: Adapter-produced rounds that contain calls, tool batches,
            and nested subagent runs.
        parse_warnings: Optional non-fatal diagnostics surfaced with the
            artifact.

    Returns:
        Top-level normalized session artifact dictionary ready for validation
        and persistence.
    """
    calls: list[dict[str, Any]] = []
    tool_executions: list[dict[str, Any]] = []

    for round_obj in call_drafts:
        _append_round_as_calls(
            round_obj=round_obj,
            calls=calls,
            tool_executions=tool_executions,
            parent_call_id='',
            parent_tool_call_id='',
        )

    _resolve_tool_consumers(calls, tool_executions)

    return {
        'schema_version': NORMALIZED_SCHEMA_VERSION,
        'agent': agent,
        'source': {
            'files': source_files,
        },
        'session': session,
        'calls': calls,
        'tool_executions': tool_executions,
        'diagnostics': list(parse_warnings or []),
    }


def _append_round_as_calls(
    *,
    round_obj: dict[str, Any],
    calls: list[dict[str, Any]],
    tool_executions: list[dict[str, Any]],
    parent_call_id: str,
    parent_tool_call_id: str,
) -> None:
    """Append one adapter round and nested subagent rounds as normalized calls.

    ``build_normalized_session_model`` calls this while walking the adapter's
    round tree. The helper mutates the shared ``calls`` and ``tool_executions``
    lists in traversal order and links nested subagent calls to the parent call
    and triggering tool-call ID.

    Args:
        round_obj: Adapter round containing a main call and optional steps.
        calls: Shared normalized call list mutated by this helper.
        tool_executions: Shared tool-execution list mutated by this helper.
        parent_call_id: Parent call ID for subagent rounds, otherwise empty.
        parent_tool_call_id: Tool-call ID that triggered a subagent round.
    """
    call = _call_from_round(
        round_obj,
        call_index=len(calls) + 1,
        parent_call_id=parent_call_id,
        parent_tool_call_id=parent_tool_call_id,
    )
    calls.append(call)

    for step in round_obj.get('steps') or []:
        if not isinstance(step, dict):
            continue
        if step.get('type') == 'tool_batch':
            for tool in step.get('tools') or []:
                if isinstance(tool, dict):
                    tool_execution = _tool_execution_from_tool(
                        tool,
                        declared_by_call=call,
                    )
                    tool_executions.append(tool_execution)
        elif step.get('type') == 'subagent_run':
            sub_parent_tool_id = str(step.get('parent_tool_call_id') or '')
            for sub_round in step.get('sub_rounds') or []:
                if isinstance(sub_round, dict):
                    _append_round_as_calls(
                        round_obj=sub_round,
                        calls=calls,
                        tool_executions=tool_executions,
                        parent_call_id=call['call_id'],
                        parent_tool_call_id=sub_parent_tool_id,
                    )


def _call_from_round(
    round_obj: dict[str, Any],
    *,
    call_index: int,
    parent_call_id: str,
    parent_tool_call_id: str,
) -> dict[str, Any]:
    """Build one normalized call dictionary from an adapter round.

    Round traversal calls this before processing tool batches or subagent runs.
    It derives stable call IDs, sequential display keys, usage, edge lists, and
    optional attribution fields without mutating the source round.

    Args:
        round_obj: Adapter round containing main-call, request, response, and
            optional attribution metadata.
        call_index: One-based normalized call index assigned by traversal.
        parent_call_id: Parent call ID for subagent calls, otherwise empty.
        parent_tool_call_id: Parent tool-call ID for subagent calls.

    Returns:
        Normalized call dictionary ready to append to the artifact.
    """
    main_call = round_obj.get('main_call') if isinstance(round_obj.get('main_call'), dict) else {}
    call_id = str(main_call.get('call_id') or round_obj.get('call_id') or f'call-{call_index:04d}')
    metrics = round_obj.get('metrics') if isinstance(round_obj.get('metrics'), dict) else {}
    usage = _usage_from_metrics(metrics)
    usage_source = (
        metrics.get('usage_source') if isinstance(metrics.get('usage_source'), dict) else {}
    )
    request = round_obj.get('request') if isinstance(round_obj.get('request'), dict) else {}
    response = round_obj.get('response') if isinstance(round_obj.get('response'), dict) else {}
    attribution_candidates = (
        round_obj.get('attribution_candidates')
        if isinstance(round_obj.get('attribution_candidates'), dict)
        else {}
    )
    source_units = (
        round_obj.get('source_units') if isinstance(round_obj.get('source_units'), list) else []
    )
    source_unit_ref_ranges = (
        round_obj.get('source_unit_ref_ranges')
        if isinstance(round_obj.get('source_unit_ref_ranges'), list)
        else []
    )
    tool_result_ids = _string_list(request.get('tool_result_ids'))
    tool_call_ids = _string_list(response.get('tool_call_ids'))

    call = {
        'call_id': call_id,
        'call_index': call_index,
        'call_key': f'C{call_index}',
        'scope': str(main_call.get('scope') or 'main'),
        'parent_call_id': parent_call_id,
        'parent_tool_call_id': parent_tool_call_id
        or str(main_call.get('parent_tool_use_id') or ''),
        'turn_id': str(main_call.get('turn_id') or ''),
        'model': str(main_call.get('model') or ''),
        'timestamp': str(main_call.get('timestamp') or ''),
        'usage': usage,
        'request': {
            'tool_result_ids': tool_result_ids,
        },
        'response': {
            'tool_call_ids': tool_call_ids,
        },
    }
    if attribution_candidates:
        call['attribution_candidates'] = attribution_candidates
    if source_units:
        call['source_units'] = source_units
    if source_unit_ref_ranges:
        call['source_unit_ref_ranges'] = source_unit_ref_ranges
    if usage_source:
        call['usage_source'] = {
            'kind': str(usage_source.get('kind') or ''),
            'method': str(usage_source.get('method') or ''),
            'reason': str(usage_source.get('reason') or ''),
        }
    return call


def _usage_from_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    """Convert adapter metrics into normalized token usage fields.

    Call construction invokes this for every round. Missing or malformed token
    values become zero, and absent totals are recomputed from the component
    counts to keep the artifact contract internally consistent.

    Args:
        metrics: Adapter metrics object for the current round.

    Returns:
        Usage dictionary with fresh, cache-read, cache-write, output, and total
        token counts.
    """
    tokens = metrics.get('tokens') if isinstance(metrics.get('tokens'), dict) else {}
    fresh = _int(tokens.get('fresh'))
    cache_read = _int(tokens.get('cache_read'))
    cache_write = _int(tokens.get('cache_write'))
    output = _int(tokens.get('output'))
    total = _int(tokens.get('total')) or fresh + cache_read + cache_write + output
    return {
        'fresh': fresh,
        'cache_read': cache_read,
        'cache_write': cache_write,
        'output': output,
        'total': total,
    }


def _tool_execution_from_tool(
    tool: dict[str, Any],
    *,
    declared_by_call: dict[str, Any],
) -> dict[str, Any]:
    """Convert one adapter tool record into a normalized execution edge.

    Round traversal calls this for every tool in a tool batch. The result keeps
    only durable edge metadata and includes optional status, exit code, duration,
    touched files, and subagent ID when the adapter reported them.

    Args:
        tool: Adapter tool record from a round step.
        declared_by_call: Normalized call dictionary that declared the tool.

    Returns:
        Tool-execution dictionary ready for artifact validation.
    """
    tool_call_id = str(tool.get('tool_call_id') or '')
    result: dict[str, Any] = {
        'tool_call_id': tool_call_id,
        'name': str(tool.get('name') or ''),
        'scope': str(tool.get('scope') or declared_by_call.get('scope') or 'main'),
        'declared_by_call_id': declared_by_call['call_id'],
        'result_consumed_by_call_id': '',
    }
    status = str(tool.get('status') or '')
    if status and status != 'completed':
        result['status'] = status
    exit_code = tool.get('exit_code')
    if exit_code not in (None, 0):
        result['exit_code'] = exit_code
    duration_ms = _int(tool.get('duration_ms'))
    if duration_ms:
        result['duration_ms'] = duration_ms
    files_touched = list(tool.get('files_touched') or [])
    if files_touched:
        result['files_touched'] = files_touched
    subagent_id = str(tool.get('subagent_id') or '')
    if subagent_id:
        result['subagent_id'] = subagent_id
    return result


def _resolve_tool_consumers(
    calls: list[dict[str, Any]],
    tool_executions: list[dict[str, Any]],
) -> None:
    """Resolve tool result consumers after all calls have been collected.

    The semantic builder calls this once traversal is complete because a tool
    result can be consumed by a later call. It mutates matching tool-execution
    dictionaries by setting ``result_consumed_by_call_id``.

    Args:
        calls: Normalized calls containing request-side tool-result IDs.
        tool_executions: Tool-execution edges to update in place.
    """
    by_tool = {tool['tool_call_id']: tool for tool in tool_executions if tool.get('tool_call_id')}
    for call in calls:
        for tool_id in (call.get('request') or {}).get('tool_result_ids') or []:
            tool = by_tool.get(tool_id)
            if not tool:
                continue
            tool['result_consumed_by_call_id'] = call['call_id']


def _string_list(value: object) -> list[str]:
    """Normalize optional adapter arrays into string identifier lists.

    Call and edge builders use this for request and response IDs. Non-list
    values become empty lists, and falsy items are omitted without mutating the
    source adapter payload.

    Args:
        value: Candidate adapter list value.

    Returns:
        Stringified truthy items in source order.
    """
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item]


def _int(value: object) -> int:
    """Coerce optional adapter metric values to non-raising integers.

    Usage and duration normalization call this helper for provider-owned values
    that can be missing or string encoded. Invalid values intentionally collapse
    to zero so validation can continue deterministically.

    Args:
        value: Candidate numeric value from adapter metrics or tool metadata.

    Returns:
        Parsed integer, or ``0`` when the value is missing or invalid.
    """
    try:
        if value is None:
            return 0
        return int(value)
    except (TypeError, ValueError):
        return 0
