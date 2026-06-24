"""说明:Session detail view model builder.

Extracted from routes.py. Contains the large _build_v11_view_model function
and the message content finder helpers used by the bucket-detail API.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from types import SimpleNamespace
from typing import TYPE_CHECKING

from session_browser.attribution.context import (
    build_attribution_session_context,
)
from session_browser.attribution.serializers import (
    request_attribution_to_payload,
    response_attribution_to_payload,
)
from session_browser.attribution.service import (
    build_llm_request_attribution,
    build_llm_response_attribution,
)
from session_browser.domain.models import (
    LLMCall,
    SubagentRun,
    TokenProvider,
)
from session_browser.domain.token_normalizer import normalize_tokens
from session_browser.web.session_detail.payloads import (
    _build_payload_lookup,
    _estimate_payload_tokens,
)
from session_browser.web.session_detail.preview import build_round_preview
from session_browser.web.session_detail.render_helpers import (
    _build_tool_command_summary,
    _build_tool_result_command_fields,
    _render_context_content_blocks,
    _render_response_content_blocks,
    _to_local_time_hms,
)
from session_browser.web.template_env import (
    _display_path,
    _format_bytes,
    _format_compact_token,
    _shorten_path,
    _to_local_time,
    normalize_llm_content,
)

if TYPE_CHECKING:
    from session_browser.web.view_models import SessionDetailViewModel

logger = logging.getLogger('session_browser.web.session_detail')

SECONDS_PER_MINUTE = 60
SECONDS_PER_HOUR = 3600
SHORT_DURATION_DECIMAL_THRESHOLD = 10
BAD_RATIO_THRESHOLD = 10
MAJOR_TOKEN_SHARE_THRESHOLD = 50
MID_TOKEN_SHARE_THRESHOLD = 20
MIN_PATH_PARTS_FOR_PARENT = 2
LOW_CACHE_RATIO_THRESHOLD = 20
LARGE_RESULT_TOKEN_THRESHOLD = 1000
TOKEN_DRIVER_BADGE_LIMIT = 5
ISSUE_LINK_LIMIT = 4
LOW_CACHE_FRACTION_THRESHOLD = 0.2
PAYLOAD_INFO_PREVIEW_CHARS = 200


def _is_main_scope_call(call: object) -> bool:
    """Return whether a normalized call belongs to the main session scope."""
    return getattr(call, 'scope', 'main') != 'subagent'


def _main_scope_llm_call_count(rounds: list, llm_calls: list) -> int:
    """Count main-agent LLM calls without nested subagent call metadata.

    ``ConversationRound.llm_call_count`` may include Agent/spawn tool nested
    calls, so diagnostics that label ``main agent`` must use the flat
    main-scope call list whenever it is available.
    """
    direct_calls = sum(1 for call in llm_calls or [] if _is_main_scope_call(call))
    if direct_calls:
        return direct_calls

    interaction_count = sum(
        1
        for round_obj in rounds or []
        for interaction in getattr(round_obj, 'interactions', []) or []
        if _is_main_scope_call(interaction)
    )
    if interaction_count:
        return interaction_count

    return sum(
        1
        for round_obj in rounds or []
        if getattr(round_obj, 'assistant_msg', None)
        and (
            getattr(round_obj.assistant_msg, 'llm_call_id', '')
            or getattr(round_obj.assistant_msg, 'usage', {})
            or getattr(round_obj.assistant_msg, 'content', '')
            or getattr(round_obj.assistant_msg, 'content_blocks', [])
        )
    )


def _round_main_scope_llm_call_count(round_obj: object | None) -> int:
    """Count main-scope LLM calls rendered for one round."""
    if not round_obj:
        return 0
    interactions = [
        interaction
        for interaction in getattr(round_obj, 'interactions', []) or []
        if _is_main_scope_call(interaction)
    ]
    if interactions:
        return len(interactions)
    assistant_msg = getattr(round_obj, 'assistant_msg', None)
    if assistant_msg and (
        getattr(assistant_msg, 'llm_call_id', '')
        or getattr(assistant_msg, 'usage', {})
        or getattr(assistant_msg, 'content', '')
        or getattr(assistant_msg, 'content_blocks', [])
    ):
        return 1
    return 0


def _format_duration_short(seconds: float) -> str:
    """Format elapsed seconds for compact session detail badges.

    Args:
        seconds: Duration in seconds from model, tool, or session timing fields.

    Returns:
        Human-readable duration using seconds, minutes, or hours.
    """
    seconds = float(seconds or 0)
    if seconds <= 0:
        return '0s'
    if seconds < 1:
        return f'{seconds:.1f}s'
    if seconds < SECONDS_PER_MINUTE:
        return (
            f'{seconds:.1f}s' if seconds < SHORT_DURATION_DECIMAL_THRESHOLD else f'{int(seconds)}s'
        )
    if seconds < SECONDS_PER_HOUR:
        return f'{int(seconds // SECONDS_PER_MINUTE)}m {int(seconds % SECONDS_PER_MINUTE)}s'
    return (
        f'{int(seconds // SECONDS_PER_HOUR)}h '
        f'{int((seconds % SECONDS_PER_HOUR) // SECONDS_PER_MINUTE)}m'
    )


def _format_ratio_pct(numerator: float, denominator: float) -> str:
    """Format a ratio as a percentage label for diagnostics.

    Args:
        numerator: Count or token component used as the ratio numerator.
        denominator: Total count or token value used as the denominator.

    Returns:
        Percentage label with one decimal place, or ``N/A`` for zero totals.
    """
    if not denominator:
        return 'N/A'
    return f'{numerator / denominator * 100:.1f}%'


def _format_percent(value: float) -> str:
    """Format an already-computed percent for chart labels.

    Args:
        value: Percent value in the range expected by the caller.

    Returns:
        Integer percent label when possible, otherwise one decimal place.
    """
    value = float(value or 0)
    if value.is_integer():
        return f'{int(value)}%'
    return f'{value:.1f}%'


def _ratio_value(numerator: float, denominator: float) -> float:
    """Return a clamped percentage value for chart geometry.

    Args:
        numerator: Component value to compare with the denominator.
        denominator: Total value that defines one hundred percent.

    Returns:
        Percentage clamped to the inclusive 0-100 range.
    """
    if not denominator:
        return 0.0
    return max(0.0, min(100.0, numerator / denominator * 100))


def _ratio_tone(value: float) -> str:
    """Classify a percentage into UI tone buckets.

    Args:
        value: Percentage value already normalized by the caller.

    Returns:
        Tone key used by templates for bad, warn, or ok styling.
    """
    if value >= BAD_RATIO_THRESHOLD:
        return 'bad'
    if value > 0:
        return 'warn'
    return 'ok'


def _token_share_tone(value: float) -> str:
    """Classify a token share into coarse contribution buckets.

    Args:
        value: Token share percentage for a session component.

    Returns:
        Tone key describing major, mid, or minor contribution.
    """
    if value >= MAJOR_TOKEN_SHARE_THRESHOLD:
        return 'major'
    if value >= MID_TOKEN_SHARE_THRESHOLD:
        return 'mid'
    return 'minor'


def _session_file_path(session: object) -> str:
    """Resolve the source file path for a session summary.

    Args:
        session: Parsed session object with direct or diagnostic path metadata.

    Returns:
        Session file path string, or an empty string when unavailable.
    """
    file_path = str(getattr(session, 'file_path', '') or '')
    if file_path:
        return file_path

    diagnostics = getattr(session, 'parse_diagnostics', None)
    if isinstance(diagnostics, dict):
        return str(diagnostics.get('file_path') or '')
    return ''


def _middle_truncate(value: str, max_chars: int, head: int, tail: int) -> str:
    """Middle-truncate an identifier while preserving recognizable edges.

    Args:
        value: Source path segment or identifier to shorten.
        max_chars: Maximum displayed character count.
        head: Preferred number of leading characters to keep.
        tail: Preferred number of trailing characters to keep.

    Returns:
        Original value when short enough, otherwise a middle-truncated label.
    """
    value = str(value or '')
    if len(value) <= max_chars:
        return value
    if max_chars <= 1:
        return '…'
    head = max(1, min(head, max_chars - 1))
    tail = max(1, min(tail, max_chars - head - 1))
    return f'{value[:head]}…{value[-tail:]}'


def _agent_session_file_display(path: str) -> str:
    """Format a compact session file path for the agent breakdown table.

    Args:
        path: Raw absolute, home-relative, or project-relative session path.

    Returns:
        Short display path that keeps parent directory and filename context.
    """
    path = str(path or '')
    if not path:
        return '—'
    display_path = _display_path(path).replace('\\', '/')
    parts = [part for part in display_path.split('/') if part]
    filename = _middle_truncate(parts[-1] if parts else display_path, 24, 9, 11)
    if len(parts) < MIN_PATH_PARTS_FOR_PARENT:
        return filename
    parent = _middle_truncate(parts[-2], 14, 6, 6)
    if display_path.startswith('~/'):
        return f'~/…/{parent}/{filename}'
    if display_path.startswith('/'):
        return f'/…/{parent}/{filename}'
    root = parts[0]
    if len(parts) == MIN_PATH_PARTS_FOR_PARENT:
        return f'{root}/{filename}'
    return f'{root}/…/{parent}/{filename}'


def _agent_session_id_display(session_id: str) -> str:
    """Format a compact session identifier for the agent table.

    Args:
        session_id: Raw main-session or subagent session identifier.

    Returns:
        Middle-truncated identifier, or an em dash for missing IDs.
    """
    session_id = str(session_id or '')
    if not session_id:
        return '—'
    return _middle_truncate(session_id, 18, 8, 7)


def _timestamp_sort_key(value: str) -> tuple[int, str]:
    """Build a stable sort key for possibly-invalid timestamps.

    Args:
        value: ISO-like timestamp string from an LLM call or subagent run.

    Returns:
        Tuple that sorts valid timestamps before empty values while preserving
        malformed values as strings.
    """
    if not value:
        return (1, '')
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return (0, parsed.isoformat())
    except (ValueError, TypeError):
        return (0, str(value))


def _call_time_label(value: str) -> str:
    """Format a timestamp for timeline call labels.

    Args:
        value: Raw timestamp string from parsed session events.

    Returns:
        Local ``HH:MM:SS`` label, or an em dash when unavailable.
    """
    return _to_local_time_hms(value or '') or '—'


def _token_provider_for_agent(agent: str) -> str | None:
    """Map a session agent key to the token-normalizer provider.

    Args:
        agent: Session agent label such as codex, qoder, or claude_code.

    Returns:
        Token provider constant for known agents, otherwise ``None``.
    """
    normalized = (agent or '').lower().replace('-', '_')
    if normalized == 'codex':
        return TokenProvider.CODEX
    if normalized == 'qoder':
        return TokenProvider.QODER
    if normalized in ('claude_code', 'claude'):
        return TokenProvider.ANTHROPIC
    return None


def _usage_parts_from_mapping(usage: dict | None, *, agent: str = '', model: str = '') -> dict:
    """Return canonical token parts from a raw provider usage mapping.

    Detail diagnostics call this fallback when a subagent message has usage
    metadata but no normalized ``LLMCall`` object. It keeps display code from
    silently dropping aliases such as cached_input_tokens.

    Args:
        usage: Provider-specific usage mapping from a message or parser.
        agent: Session agent key used to select provider normalization rules.
        model: Optional model name used by provider-specific normalizers.

    Returns:
        Dictionary with fresh, cache read, cache write, output, and total token
        counts normalized to integer values.
    """
    breakdown = normalize_tokens(
        usage or {},
        provider=_token_provider_for_agent(agent),
        model=model or None,
    )
    return {
        'fresh': int(breakdown.fresh_input_tokens or 0),
        'cache_read': int(breakdown.cache_read_tokens or 0),
        'cache_write': int(breakdown.cache_write_tokens or 0),
        'output': int(breakdown.output_tokens or 0),
        'total': int(
            breakdown.total_tokens
            or (
                (breakdown.fresh_input_tokens or 0)
                + (breakdown.cache_read_tokens or 0)
                + (breakdown.cache_write_tokens or 0)
                + (breakdown.output_tokens or 0)
            )
        ),
    }


def _usage_parts_from_call(call: object) -> dict:
    """Return canonical token parts from a parsed LLM call object.

    Args:
        call: Parsed LLM call that may expose a normalized token breakdown or
            legacy token count attributes.

    Returns:
        Dictionary with fresh, cache read, cache write, output, and total token
        counts normalized to integer values.
    """
    breakdown = getattr(call, 'token_breakdown_normalized', None)
    if breakdown is not None:
        fresh = int(getattr(breakdown, 'fresh_input_tokens', 0) or 0)
        cache_read = int(getattr(breakdown, 'cache_read_tokens', 0) or 0)
        cache_write = int(getattr(breakdown, 'cache_write_tokens', 0) or 0)
        output = int(getattr(breakdown, 'output_tokens', 0) or 0)
        total = int(getattr(breakdown, 'total_tokens', 0) or 0) or (
            fresh + cache_read + cache_write + output
        )
        return {
            'fresh': fresh,
            'cache_read': cache_read,
            'cache_write': cache_write,
            'output': output,
            'total': total,
        }
    fresh = int(getattr(call, 'input_tokens', 0) or 0)
    cache_read = int(getattr(call, 'cache_read_tokens', 0) or 0)
    cache_write = int(getattr(call, 'cache_write_tokens', 0) or 0)
    output = int(getattr(call, 'output_tokens', 0) or 0)
    total = int(getattr(call, 'total_tokens', 0) or 0) or (
        fresh + cache_read + cache_write + output
    )
    return {
        'fresh': fresh,
        'cache_read': cache_read,
        'cache_write': cache_write,
        'output': output,
        'total': total,
    }


def _subagent_id_from_tool(tc: object) -> str:
    """Resolve the subagent identifier associated with a tool call.

    Args:
        tc: Parsed tool call with direct or summary-based subagent metadata.

    Returns:
        Subagent identifier string, or an empty string for main-scope tools.
    """
    summary = getattr(tc, 'subagent_summary', {}) or {}
    if isinstance(summary, dict) and summary.get('agent_id'):
        return str(summary.get('agent_id') or '')
    return str(getattr(tc, 'subagent_id', '') or '')


def _is_subagent_parent_tool(tc: object, subagent_id: str = '') -> bool:
    """Detect whether a main-scope tool call spawned a subagent.

    Args:
        tc: Parsed tool call being classified for timeline rendering.
        subagent_id: Optional expected subagent identifier to match.

    Returns:
        ``True`` when the tool belongs to the main scope and references a
        matching subagent.
    """
    if getattr(tc, 'scope', 'main') == 'subagent':
        return False
    candidate = _subagent_id_from_tool(tc)
    return bool(candidate) and (not subagent_id or candidate == subagent_id)


def _median(values: list[int]) -> float:
    """Compute the median token value used by spike diagnostics.

    Args:
        values: Token counts collected from trace rows or subagent rows.

    Returns:
        Median as a float, or ``0.0`` when no values are available.
    """
    clean = sorted(v for v in values if v is not None)
    if not clean:
        return 0.0
    mid = len(clean) // 2
    if len(clean) % 2:
        return float(clean[mid])
    return (clean[mid - 1] + clean[mid]) / 2


def _payload_status(
    request_id: str, response_id: str, result_ids: list[str], payload_map: dict
) -> str:
    """Summarize payload availability for one call row.

    Args:
        request_id: Expected request/context payload ID.
        response_id: Expected response/output payload ID.
        result_ids: Expected tool-result payload IDs.
        payload_map: Lookup returned by ``_build_payload_lookup``.

    Returns:
        Availability status of missing, partial, or available.
    """
    ids = [pid for pid in [request_id, response_id, *result_ids] if pid]
    if not ids:
        return 'missing'
    available = [pid for pid in ids if pid in payload_map]
    if not available:
        return 'missing'
    if len(available) < len(ids):
        return 'partial'
    return 'available'


def _payload_primary_id(
    request_id: str, response_id: str, result_ids: list[str], payload_map: dict
) -> str:
    """Choose the first available payload ID for a selector item.

    Args:
        request_id: Candidate request/context payload ID.
        response_id: Candidate response/output payload ID.
        result_ids: Candidate tool-result payload IDs.
        payload_map: Lookup returned by ``_build_payload_lookup``.

    Returns:
        First candidate present in the lookup, or an empty string.
    """
    for payload_id in (request_id, response_id, *result_ids):
        if payload_id and payload_id in payload_map:
            return payload_id
    return ''


def _append_payload_item(group: dict, item: dict, defaults: dict) -> None:
    """Append a payload selector item and update default selection hints.

    Args:
        group: Round-level payload group receiving the item.
        item: Payload selector row with status and call identifiers.
        defaults: Mutable default-call accumulator shared across groups.

    Returns:
        None. The helper mutates ``group`` and ``defaults`` in place.
    """
    group['items'].append(item)
    if item.get('status') == 'error' and not defaults['failed']:
        defaults['failed'] = item['call_id']
    if item.get('status') in ('missing', 'error') and not defaults.get('problem'):
        defaults['problem'] = item['call_id']
    if item.get('kind') == 'llm' and not defaults['llm']:
        defaults['llm'] = item['call_id']
    if item.get('primary_payload_id') and not defaults['available']:
        defaults['available'] = item['call_id']


def _build_payload_tab_index(  # noqa: PLR0912, PLR0915
    rounds: list,
    tool_calls: list,
    subagent_runs: list[SubagentRun],
    llm_calls: list | None = None,
    *,
    agent: str = '',
) -> dict:
    """Build the persistent Payload tab selector from API-compatible IDs.

    The session detail route calls this after payload lookup construction. It
    groups main LLM calls, tool results, and subagent calls by round while
    preserving stable payload IDs shared with the payload API.

    Args:
        rounds: Parsed main-session rounds used as selector groups.
        tool_calls: Flat parsed tool-call list retained for caller compatibility.
        subagent_runs: Parsed subagent transcripts attached to the session.
        llm_calls: Optional normalized LLM call records used for token labels.
        agent: Session agent key used for fallback token normalization.

    Returns:
        Selector model with groups, default call ID, and payload item count.
    """
    payload_map = _build_payload_lookup(rounds, tool_calls, subagent_runs, truncate=True)
    groups: list[dict] = []
    group_by_round: dict[int, dict] = {}
    defaults = {'failed': '', 'problem': '', 'llm': '', 'available': ''}
    global_call_num = 0
    sub_calls_by_id = {
        getattr(call, 'id', ''): call
        for call in (llm_calls or [])
        if getattr(call, 'scope', '') == 'subagent' and getattr(call, 'id', '')
    }
    sub_calls_by_agent: dict[str, list] = {}
    for call in llm_calls or []:
        if getattr(call, 'scope', '') != 'subagent':
            continue
        sub_calls_by_agent.setdefault(getattr(call, 'subagent_id', '') or '', []).append(call)

    for r_idx, r in enumerate(rounds):
        rid = r_idx + 1
        round_preview = build_round_preview(r)
        round_title = (
            round_preview['preview_text'] or getattr(r.user_msg, 'content', '') or ''
        ).strip()
        if not round_title:
            round_title = 'Untitled round'
        group = {
            'round_id': rid,
            'title': f'R{rid} · {round_title[:96]}',
            'items': [],
        }
        groups.append(group)
        group_by_round[rid] = group

        seen_tool_payloads: set[str] = set()
        for ix_idx, ix in enumerate(r.interactions):
            global_call_num += 1
            call_index = global_call_num
            if getattr(ix, 'scope', 'main') == 'subagent' and getattr(ix, 'subagent_id', ''):
                continue
            request_id = f'llm-R{rid}-IX{call_index}-context'
            response_id = f'llm-R{rid}-IX{call_index}-output'
            parts = _usage_parts_from_call(ix)
            input_side = parts['fresh'] + parts['cache_read'] + parts['cache_write']
            request_attribution_id = f'llm-R{rid}-IX{ix_idx + 1}-request-attribution'
            response_attribution_id = f'llm-R{rid}-IX{ix_idx + 1}-response-attribution'
            token_summary = (
                f'{_format_compact_token(input_side)} in · '
                f'{_format_compact_token(parts["output"])} out'
                if input_side or parts['output']
                else 'tokens unavailable'
            )
            model_label = (getattr(ix, "model", "") or "unknown")[:40]
            ix_tools = [
                tc
                for tc in (getattr(ix, 'tool_calls', []) or [])
                if not getattr(tc, 'subagent_id', '')
            ]
            has_failed_tool = any(getattr(tc, 'is_failed', False) for tc in ix_tools)
            status = _payload_status(request_id, response_id, [], payload_map)
            item_status = 'error' if has_failed_tool else status
            item = {
                'call_id': f'llm-R{rid}-IX{call_index}',
                'kind': 'llm',
                'round_id': rid,
                'title': f'LLM Call #{call_index}',
                'model': (getattr(ix, 'model', '') or 'unknown')[:40],
                'call_status': 'Failed' if has_failed_tool else 'OK',
                'status': item_status,
                'request_payload_id': request_id if request_id in payload_map else '',
                'response_payload_id': response_id if response_id in payload_map else '',
                'request_attribution_id': request_attribution_id,
                'response_attribution_id': response_attribution_id,
                'request_attribution_status': 'partial',
                'response_attribution_status': 'partial',
                'result_payload_ids': [],
                'primary_payload_id': _payload_primary_id(request_id, response_id, [], payload_map),
                'token_summary': token_summary,
                'timestamp': _to_local_time_hms(getattr(ix, 'timestamp', '') or ''),
                'meta': f'{model_label} · {token_summary} · {status}',
            }
            _append_payload_item(group, item, defaults)

            for tc in ix_tools:
                if not getattr(tc, 'result', ''):
                    continue
                tc_global_idx = -1
                for gi, gtc in enumerate(r.tool_calls):
                    if gtc is tc:
                        tc_global_idx = gi + 1
                        break
                if tc_global_idx == -1:
                    tc_global_idx = len(seen_tool_payloads) + 1
                payload_id = f'tool-R{rid}-T{tc_global_idx}'
                if payload_id in seen_tool_payloads:
                    continue
                seen_tool_payloads.add(payload_id)
                availability = 'available' if payload_id in payload_map else 'missing'
                tool_status = 'error' if getattr(tc, 'is_failed', False) else availability
                tool_item = {
                    'call_id': f'tool-R{rid}-T{tc_global_idx}',
                    'kind': 'tool',
                    'round_id': rid,
                    'title': f'Tool Result · {getattr(tc, "name", "tool")}',
                    'model': '',
                    'call_status': 'Failed' if getattr(tc, 'is_failed', False) else 'OK',
                    'status': tool_status,
                    'request_payload_id': '',
                    'response_payload_id': '',
                    'request_attribution_status': '',
                    'response_attribution_status': '',
                    'result_payload_ids': [payload_id] if payload_id in payload_map else [],
                    'primary_payload_id': payload_id if payload_id in payload_map else '',
                    'token_summary': payload_map.get(payload_id, {}).get('size', '—'),
                    'timestamp': '',
                    'meta': f'{getattr(tc, "name", "tool")} · {availability}',
                }
                _append_payload_item(group, tool_item, defaults)

        if not r.interactions and r.tool_calls:
            for tc_idx, tc in enumerate(r.tool_calls, start=1):
                if getattr(tc, 'subagent_id', '') or not getattr(tc, 'result', ''):
                    continue
                payload_id = f'tool-R{rid}-T{tc_idx}'
                availability = 'available' if payload_id in payload_map else 'missing'
                tool_item = {
                    'call_id': f'tool-R{rid}-T{tc_idx}',
                    'kind': 'tool',
                    'round_id': rid,
                    'title': f'Tool Result · {getattr(tc, "name", "tool")}',
                    'model': '',
                    'call_status': 'Failed' if getattr(tc, 'is_failed', False) else 'OK',
                    'status': 'error' if getattr(tc, 'is_failed', False) else availability,
                    'request_payload_id': '',
                    'response_payload_id': '',
                    'request_attribution_status': '',
                    'response_attribution_status': '',
                    'result_payload_ids': [payload_id] if payload_id in payload_map else [],
                    'primary_payload_id': payload_id if payload_id in payload_map else '',
                    'token_summary': payload_map.get(payload_id, {}).get('size', '—'),
                    'timestamp': '',
                    'meta': f'{getattr(tc, "name", "tool")} · {availability}',
                }
                _append_payload_item(group, tool_item, defaults)

    subagent_parent_round: dict[str, int] = {}
    for run in subagent_runs:
        summary = run.get('summary', {})
        sa_id = summary.get('agent_id', '')
        if not sa_id:
            continue
        for r_idx, r in enumerate(rounds):
            for tc in r.tool_calls:
                if _is_subagent_parent_tool(tc, sa_id):
                    subagent_parent_round[sa_id] = r_idx + 1
                    break
            if sa_id in subagent_parent_round:
                break

    for run in subagent_runs:
        summary = run.get('summary', {})
        sa_id = summary.get('agent_id', '')
        if not sa_id:
            continue
        rid = subagent_parent_round.get(sa_id, 0)
        group = group_by_round.get(rid)
        if group is None:
            group = next((g for g in groups if g.get('round_id') == 0), None)
            if group is None:
                group = {'round_id': 0, 'title': 'Subagents', 'items': []}
                groups.append(group)
        agent_type = summary.get('agent_type', '') or 'subagent'
        sub_call_cursor = 0
        agent_calls = sub_calls_by_agent.get(sa_id, [])
        for m_idx, message in enumerate(run.get('messages', []), start=1):
            if getattr(message, 'role', '') != 'assistant':
                continue
            matched_call = sub_calls_by_id.get(getattr(message, 'llm_call_id', '') or '')
            if not matched_call and sub_call_cursor < len(agent_calls):
                matched_call = agent_calls[sub_call_cursor]
            sub_call_cursor += 1
            request_id = f'sub-{sa_id}-{m_idx}-ctx'
            response_id = f'sub-{sa_id}-{m_idx}-rsp'
            parts = (
                _usage_parts_from_call(matched_call)
                if matched_call
                else _usage_parts_from_mapping(
                    getattr(message, 'usage', {}) or {},
                    agent=agent,
                    model=getattr(message, 'model', '') or '',
                )
            )
            input_side = parts['fresh'] + parts['cache_read'] + parts['cache_write']
            output_tokens = parts['output']
            token_summary = (
                f'{_format_compact_token(input_side)} in · '
                f'{_format_compact_token(output_tokens)} out'
                if input_side or output_tokens
                else 'tokens unavailable'
            )
            status = _payload_status(request_id, response_id, [], payload_map)
            request_attribution_id = f'sub-{sa_id}-IX{m_idx}-request-attribution'
            response_attribution_id = f'sub-{sa_id}-IX{m_idx}-response-attribution'
            item = {
                'call_id': f'sub-{sa_id}-IX{m_idx}',
                'kind': 'subagent',
                'round_id': rid,
                'subagent_id': sa_id,
                'subagent_round_id': m_idx,
                'title': f'Subagent · {agent_type}',
                'model': (getattr(message, 'model', '') or 'unknown')[:40],
                'call_status': 'OK',
                'status': status,
                'request_payload_id': request_id if request_id in payload_map else '',
                'response_payload_id': response_id if response_id in payload_map else '',
                'request_attribution_id': request_attribution_id,
                'response_attribution_id': response_attribution_id,
                'request_attribution_status': 'partial',
                'response_attribution_status': 'partial',
                'result_payload_ids': [],
                'primary_payload_id': _payload_primary_id(request_id, response_id, [], payload_map),
                'token_summary': token_summary,
                'timestamp': _to_local_time_hms(getattr(message, 'timestamp', '') or ''),
                'meta': f'{agent_type} · {token_summary} · {status}',
            }
            _append_payload_item(group, item, defaults)

    groups = [group for group in groups if group['items']]
    return {
        'groups': groups,
        'default_call_id': defaults['failed']
        or defaults['problem']
        or defaults['llm']
        or defaults['available'],
        'payload_count': sum(len(group['items']) for group in groups),
    }


def _build_session_diagnostics(  # noqa: PLR0912, PLR0913, PLR0915
    session: object,
    rounds: list,
    llm_calls: list,
    tool_calls: list,
    subagent_runs: list[SubagentRun],
    trace_rows: list,
    session_anomalies: object,
    fresh_tokens: int,
    cache_read_tokens: int,
    cache_write_tokens: int,
    output_tokens: int,
    payload_index: dict,
    payload_sources: list,
) -> dict:
    """Build diagnostics panels for the session detail view model.

    The main view-model builder calls this after trace rows and payload sources
    are available. It derives token charts, issue signals, tool impact, call
    distribution, and agent/subagent cost breakdowns without mutating parsed
    session objects.

    Args:
        session: Parsed session summary object used for IDs, agent, and totals.
        rounds: Parsed main-session rounds displayed in the trace table.
        llm_calls: Flat normalized LLM calls for main and subagent scopes.
        tool_calls: Flat parsed tool-call list used for failure and cost data.
        subagent_runs: Parsed subagent transcripts attached to the session.
        trace_rows: Round rows already built by ``_build_v11_view_model``.
        session_anomalies: Analyzer result containing session-level anomalies.
        fresh_tokens: Provider-reported fresh input token count.
        cache_read_tokens: Provider-reported cache-read token count.
        cache_write_tokens: Provider-reported cache-write token count.
        output_tokens: Provider-reported output token count.
        payload_index: Payload selector model used to detect payload gaps.
        payload_sources: Payload drawer entries used to detect attribution gaps.

    Returns:
        Diagnostics dictionary consumed by templates and hero metrics.
    """
    input_side_tokens = fresh_tokens + cache_read_tokens + cache_write_tokens
    computed_total_tokens = input_side_tokens + output_tokens
    sub_calls_by_agent: dict[str, list] = {}
    sub_calls_by_id = {
        getattr(call, 'id', ''): call
        for call in llm_calls or []
        if getattr(call, 'scope', '') == 'subagent' and getattr(call, 'id', '')
    }
    for call in llm_calls or []:
        if getattr(call, 'scope', '') == 'subagent':
            sub_calls_by_agent.setdefault(getattr(call, 'subagent_id', '') or '', []).append(call)
    sub_round_by_call_id: dict[str, int] = {}
    sub_round_by_agent_sequence: dict[tuple[str, int], int] = {}
    for run in subagent_runs:
        summary = run.get('summary', {})
        sa_id = summary.get('agent_id', '')
        if not sa_id:
            continue
        agent_calls = sub_calls_by_agent.get(sa_id, [])
        sub_call_cursor = 0
        assistant_seq = 0
        for m_idx, message in enumerate(run.get('messages', []), start=1):
            if getattr(message, 'role', '') != 'assistant':
                continue
            assistant_seq += 1
            matched_call = sub_calls_by_id.get(getattr(message, 'llm_call_id', '') or '')
            if not matched_call and sub_call_cursor < len(agent_calls):
                matched_call = agent_calls[sub_call_cursor]
            sub_call_cursor += 1
            sub_round_by_agent_sequence[(sa_id, assistant_seq)] = m_idx
            if matched_call and getattr(matched_call, 'id', ''):
                sub_round_by_call_id[getattr(matched_call, 'id', '')] = m_idx

    round_by_tool_id = {}
    for r_idx, r in enumerate(rounds, start=1):
        for tc in r.tool_calls:
            key = getattr(tc, 'tool_use_id', '') or id(tc)
            round_by_tool_id[key] = r_idx

    subagent_parent_round: dict[str, int] = {}
    for run in subagent_runs:
        summary = run.get('summary', {})
        sa_id = summary.get('agent_id', '')
        if not sa_id:
            continue
        for r_idx, r in enumerate(rounds, start=1):
            for tc in r.tool_calls:
                if _is_subagent_parent_tool(tc, sa_id):
                    subagent_parent_round[sa_id] = r_idx
                    break
            if sa_id in subagent_parent_round:
                break

    round_signals: dict[int, dict] = {
        row.get('round_id', 0): {
            'failed': False,
            'payload_gap': False,
            'attribution_gap': False,
            'subagent': bool(row.get('has_subagent')),
            'issues': [],
        }
        for row in trace_rows
    }
    issue_summary = {
        'tool_failures': 0,
        'llm_errors': 0,
        'payload_gaps': 0,
        'attribution_errors': 0,
    }
    issues: list[dict] = []

    def add_issue(  # noqa: PLR0913
        kind: str,
        label: str,
        evidence: str,
        round_id: int = 0,
        tone: str = 'warning',
        seed: str = '',
        call_id: str = '',
        target_tab: str = 'trace',
    ) -> None:
        """Append a normalized issue signal and update round aggregates.

        Args:
            kind: Stable issue category key.
            label: Human-readable issue label shown in the UI.
            evidence: Short supporting text for the signal.
            round_id: One-based round number associated with the issue.
            tone: Visual severity tone such as warning or critical.
            seed: Optional deterministic seed for issue identity.
            call_id: Optional payload selector call ID for navigation.
            target_tab: Detail tab that should be opened for the issue.

        Returns:
            None. The helper mutates issue lists and round signal maps.
        """
        issue = {
            'kind': kind,
            'label': label,
            'issue': label,
            'evidence': evidence[:160],
            'round_id': round_id,
            'round_label': f'R{round_id}' if round_id else '—',
            'tone': tone,
            'seed': seed or f'{session.session_id} + {kind}',
            'call_id': call_id,
            'target_tab': target_tab,
        }
        issues.append(issue)
        if round_id:
            sig = round_signals.setdefault(
                round_id,
                {
                    'failed': False,
                    'payload_gap': False,
                    'attribution_gap': False,
                    'subagent': False,
                    'issues': [],
                },
            )
            sig['issues'].append(issue)
            if kind in ('tool_failure', 'llm_error'):
                sig['failed'] = True
            if kind == 'payload_gap':
                sig['payload_gap'] = True
            if kind == 'attribution_error':
                sig['attribution_gap'] = True

    token_rounds = []
    round_fresh_values = [row.get('token_input', 0) for row in trace_rows]
    median_fresh = _median(round_fresh_values)
    for row in trace_rows:
        round_id = row.get('round_id', 0)
        round_obj = rounds[round_id - 1] if round_id and round_id <= len(rounds) else None
        fresh_raw = row.get('token_input', 0)
        cache_read_raw = row.get('token_cache_read', 0)
        cache_write_raw = row.get('token_cache_write', 0)
        output_raw = row.get('token_output', 0)
        total_raw = row.get('token_total_raw', 0)
        round_input_side = fresh_raw + cache_read_raw + cache_write_raw
        cache_ratio_value = _ratio_value(cache_read_raw, round_input_side)
        low_cache = bool(round_input_side and cache_ratio_value < LOW_CACHE_RATIO_THRESHOLD)
        fresh_spike = bool(median_fresh > 0 and fresh_raw > median_fresh * 2)
        token_rounds.append(
            {
                'round_id': row.get('round_id', 0),
                'start_time': row.get('start_time', '—'),
                'total': total_raw,
                'total_label': row.get('token_total', '—'),
                'fresh': _format_compact_token(fresh_raw),
                'cache_read': _format_compact_token(cache_read_raw),
                'cache_write': _format_compact_token(cache_write_raw),
                'output': _format_compact_token(output_raw),
                'fresh_share': _format_ratio_pct(fresh_raw, total_raw),
                'cache_read_share': _format_ratio_pct(cache_read_raw, total_raw),
                'cache_write_share': _format_ratio_pct(cache_write_raw, total_raw),
                'output_share': _format_ratio_pct(output_raw, total_raw),
                'cache_read_ratio': _format_ratio_pct(cache_read_raw, round_input_side),
                'cache_read_ratio_value': round(cache_ratio_value, 1),
                'ratio_y': round(100 - cache_ratio_value, 1),
                'mix': row.get('token_mix', {}),
                'llm_calls': _round_main_scope_llm_call_count(round_obj),
                'tool_calls': row.get('tool_count', 0),
                'is_low_cache': low_cache,
                'is_fresh_spike': fresh_spike,
                'has_payload_gap': False,
            }
        )

    failed_tools = [tc for tc in tool_calls if getattr(tc, 'is_failed', False)]
    issue_summary['tool_failures'] = len(failed_tools)
    for tc in failed_tools:
        key = getattr(tc, 'tool_use_id', '') or id(tc)
        rid = round_by_tool_id.get(key, 0)
        if not rid and getattr(tc, 'subagent_id', ''):
            rid = subagent_parent_round.get(getattr(tc, 'subagent_id', ''), 0)
        evidence = f'{getattr(tc, "name", "tool")} · {getattr(tc, "status", "") or "failed"}'
        if getattr(tc, 'exit_code', None) is not None:
            evidence = f'{getattr(tc, "name", "tool")} exit {tc.exit_code}'
        add_issue(
            'tool_failure',
            'Tool failure',
            evidence,
            round_id=rid,
            tone='critical',
            seed=(
                f'{session.session_id} + R{rid or "?"} + {getattr(tc, "tool_use_id", "") or "tool"}'
            ),
        )

    for r_idx, r in enumerate(rounds, start=1):
        llm_errors = getattr(r, 'llm_error_count', 0) or 0
        if not llm_errors:
            continue
        issue_summary['llm_errors'] += llm_errors
        add_issue(
            'llm_error',
            'LLM error',
            f'R{r_idx} · {llm_errors} llm error(s)',
            round_id=r_idx,
            tone='critical',
            seed=f'{session.session_id} + R{r_idx}',
        )

    payload_gap_count = 0
    for group in payload_index.get('groups', []):
        for item in group.get('items', []):
            if item.get('status') not in ('missing', 'error'):
                continue
            payload_gap_count += 1
            rid = int(item.get('round_id') or 0)
            add_issue(
                'payload_gap',
                'Payload gap',
                f'{item.get("title", "Call")} · {item.get("status", "missing")}',
                round_id=rid,
                tone='warning' if item.get('status') == 'missing' else 'critical',
                seed=f'{session.session_id} + {item.get("call_id", "payload")}',
                call_id=item.get('call_id', ''),
                target_tab='payload',
            )
    issue_summary['payload_gaps'] = payload_gap_count

    for payload in payload_sources or []:
        kind = str(payload.get('kind', ''))
        if 'attribution' not in kind:
            continue
        warning = str(payload.get('warning', ''))
        if not warning or 'unavailable' not in warning.lower():
            continue
        issue_summary['attribution_errors'] += 1
        title = payload.get('title', 'Attribution')
        round_id = 0
        if title.startswith('R'):
            try:
                round_id = int(title.split('·', 1)[0].strip()[1:])
            except Exception:
                round_id = 0
        add_issue(
            'attribution_error',
            'Attribution error',
            warning[:120] or 'Attribution unavailable',
            round_id=round_id,
            tone='warning',
            seed=f'{session.session_id} + {payload.get("payload_id", "attribution")}',
            target_tab='payload',
        )

    for anomaly in getattr(session_anomalies, 'anomalies', [])[:5]:
        add_issue(
            'session_anomaly',
            getattr(anomaly, 'label', '') or str(getattr(anomaly, 'type', 'Signal')),
            (getattr(anomaly, 'reason', '') or 'Session anomaly')[:120],
            tone='warning',
            seed=f'{session.session_id}',
        )

    for token_row in token_rounds:
        sig = round_signals.get(token_row.get('round_id', 0), {})
        token_row['has_payload_gap'] = bool(sig.get('payload_gap'))
        badges = []
        if token_row['is_low_cache']:
            badges.append('low cache')
        if token_row['is_fresh_spike']:
            badges.append('fresh spike')
        if token_row['has_payload_gap']:
            badges.append('payload gap')
        token_row['badges'] = badges

    if token_rounds:
        max_round_tokens = max([row.get('total', 0) for row in token_rounds] or [0])
        step = 32
        width = max(1, len(token_rounds) - 1) * step
        plot_width = (len(token_rounds) * 32) + 12
        for idx, token_row in enumerate(token_rounds):
            token_row['line_x'] = idx * step
            token_row['line_y'] = round(100 - (token_row.get('cache_read_ratio_value', 0) or 0), 1)
            token_row['bar_height_pct'] = round(
                _ratio_value(token_row.get('total', 0), max_round_tokens), 1
            )
        line_points = ' '.join(f'{row["line_x"]},{row["line_y"]}' for row in token_rounds)
    else:
        width = 0
        plot_width = 0
        line_points = ''

    tool_stats: dict[str, dict] = {}
    for tc in tool_calls:
        name = getattr(tc, 'name', '') or 'tool'
        stat = tool_stats.setdefault(
            name,
            {
                'tool': name,
                'calls': 0,
                'main_calls': 0,
                'subagent_calls': 0,
                'failed': 0,
                'token_estimate': 0,
                'top_command': '',
            },
        )
        stat['calls'] += 1
        if getattr(tc, 'subagent_id', '') or getattr(tc, 'scope', '') == 'subagent':
            stat['subagent_calls'] += 1
        else:
            stat['main_calls'] += 1
        if getattr(tc, 'is_failed', False):
            stat['failed'] += 1
        result = getattr(tc, 'result', '') or ''
        stat['token_estimate'] += _estimate_payload_tokens(result)
        if not stat['top_command']:
            stat['top_command'] = _build_tool_command_summary(
                name, getattr(tc, 'parameters', {}) or {}
            )[:120]

    tool_summary = []
    for stat in sorted(tool_stats.values(), key=lambda item: (-item['calls'], item['tool']))[:5]:
        failure_rate_value = _ratio_value(stat['failed'], stat['calls'])
        tool_summary.append(
            {
                'tool': stat['tool'],
                'calls': str(stat['calls']),
                'main_calls': stat['main_calls'],
                'subagent_calls': stat['subagent_calls'],
                'tokens': f'~{_format_compact_token(stat["token_estimate"])}'
                if stat['token_estimate']
                else '0',
                'failure': f'{stat["failed"]} · {_format_ratio_pct(stat["failed"], stat["calls"])}',
                'failures': stat['failed'],
                'failure_rate': _format_ratio_pct(stat['failed'], stat['calls']),
                'failure_tone': _ratio_tone(failure_rate_value),
                'note': stat['top_command'],
                'split_note': f'Main {stat["main_calls"]} · Subagent {stat["subagent_calls"]}',
            }
        )

    drivers = []
    for row in trace_rows:
        tokens = int(row.get('token_total_raw', 0) or 0)
        if tokens:
            drivers.append(
                {
                    'type': 'Round',
                    'driver': f'R{row.get("round_id")} · Round total',
                    'tokens': tokens,
                    'target_round': row.get('round_id'),
                    'target_tab': 'trace',
                    'reason': 'Round aggregate',
                }
            )
    subagent_runs_by_time = sorted(
        subagent_runs,
        key=lambda run: _timestamp_sort_key((run.get('summary', {}) or {}).get('started_at', '')),
    )
    subagent_color_map = {
        (run.get('summary', {}) or {}).get('agent_id', ''): idx % 5
        for idx, run in enumerate(subagent_runs_by_time)
        if (run.get('summary', {}) or {}).get('agent_id', '')
    }
    call_legend = [
        {
            'kind': 'main',
            'color': 'main',
            'label': 'Main call',
            'title': 'Main session LLM calls',
        }
    ]
    for run in subagent_runs_by_time:
        summary = run.get('summary', {}) or {}
        sa_id = summary.get('agent_id', '')
        if not sa_id:
            continue
        agent_type = summary.get('agent_type', '') or 'subagent'
        short_id = sa_id[-8:] if sa_id else 'unknown'
        call_legend.append(
            {
                'kind': 'subagent',
                'color': f'subagent-{subagent_color_map.get(sa_id, 0)}',
                'label': f'{agent_type} · {sa_id}',
                'title': f'{agent_type} · {sa_id}',
                'name': agent_type,
                'agent_id': sa_id,
                'short_id': short_id,
            }
        )
    call_legend.append(
        {
            'kind': 'top',
            'color': 'top',
            'label': 'Top 3',
            'title': 'Top 3 token-heavy calls',
        }
    )
    global_call_num = 0
    call_distribution = []
    call_distribution_order = 0
    for r_idx, r in enumerate(rounds, start=1):
        for ix in r.interactions:
            global_call_num += 1
            if getattr(ix, 'scope', 'main') == 'subagent' and getattr(ix, 'subagent_id', ''):
                continue
            call_distribution_order += 1
            parts = _usage_parts_from_call(ix)
            call_tokens = parts['total']
            if call_tokens:
                drivers.append(
                    {
                        'type': 'Main LLM Call',
                        'driver': f'R{r_idx} · LLM #{global_call_num}',
                        'tokens': call_tokens,
                        'target_round': r_idx,
                        'target_tab': 'trace',
                        'reason': (getattr(ix, 'model', '') or 'model')[:40],
                    }
                )
            source_ts = getattr(ix, 'timestamp', '') or ''
            call_distribution.append(
                {
                    'index': len(call_distribution) + 1,
                    'label': f'R{r_idx} #{global_call_num}',
                    'time_label': _call_time_label(source_ts),
                    'tokens': call_tokens,
                    'tokens_label': _format_compact_token(call_tokens),
                    'lane': 'main',
                    'lane_label': 'Main',
                    'subagent_color': '',
                    'sort_key': _timestamp_sort_key(source_ts),
                    '_order': call_distribution_order,
                    'target_round': r_idx,
                    'target_subagent': '',
                    'target_subagent_round': '',
                    'model': (getattr(ix, 'model', '') or 'unknown')[:40],
                    'is_top': False,
                    'height_pct': 0,
                }
            )

    for run in subagent_runs:
        summary = run.get('summary', {})
        sa_id = summary.get('agent_id', '')
        rid = subagent_parent_round.get(sa_id, 0)
        agent_type = summary.get('agent_type', '') or 'subagent'
        call_count = 0
        token_sum = 0
        sub_calls = sub_calls_by_agent.get(sa_id, [])
        if sub_calls:
            source_records = [
                (
                    call,
                    sub_round_by_call_id.get(getattr(call, 'id', ''))
                    or sub_round_by_agent_sequence.get((sa_id, idx))
                    or idx,
                )
                for idx, call in enumerate(sub_calls, start=1)
            ]
        else:
            source_records = [
                (message, m_idx)
                for m_idx, message in enumerate(run.get('messages', []), start=1)
                if getattr(message, 'role', '') == 'assistant'
            ]
        for source, sub_round_id in source_records:
            call_count += 1
            if isinstance(source, LLMCall):
                parts = _usage_parts_from_call(source)
                model = (getattr(source, 'model', '') or 'unknown')[:40]
                source_ts = getattr(source, 'timestamp', '') or summary.get('started_at', '')
            else:
                parts = _usage_parts_from_mapping(
                    getattr(source, 'usage', {}) or {},
                    agent=getattr(session, 'agent', '') or '',
                    model=getattr(source, 'model', '') or '',
                )
                model = (getattr(source, 'model', '') or 'unknown')[:40]
                source_ts = getattr(source, 'timestamp', '') or summary.get('started_at', '')
            call_tokens = parts['total']
            token_sum += call_tokens
            call_distribution_order += 1
            call_distribution.append(
                {
                    'index': len(call_distribution) + 1,
                    'label': f'{agent_type} {sa_id or "unknown"} #{call_count}',
                    'time_label': _call_time_label(source_ts),
                    'tokens': call_tokens,
                    'tokens_label': _format_compact_token(call_tokens),
                    'lane': 'subagent',
                    'lane_label': f'Subagent {agent_type} {sa_id or "unknown"}',
                    'subagent_color': f'subagent-{subagent_color_map.get(sa_id, 0)}',
                    'sort_key': _timestamp_sort_key(source_ts),
                    '_order': call_distribution_order,
                    'target_round': rid,
                    'target_subagent': sa_id,
                    'target_subagent_round': sub_round_id,
                    'model': model,
                    'is_top': False,
                    'height_pct': 0,
                }
            )
        if token_sum:
            drivers.append(
                {
                    'type': 'Subagent',
                    'driver': f'{agent_type} · {sa_id[-8:] if sa_id else "unknown"}',
                    'tokens': token_sum,
                    'target_round': rid,
                    'target_subagent': sa_id,
                    'target_subagent_round': '',
                    'target_tab': 'trace',
                    'reason': f'{call_count} LLM call{"s" if call_count != 1 else ""}',
                }
            )

    for tc in tool_calls:
        result_tokens = max(len(getattr(tc, 'result', '') or '') // 4, 0)
        if not result_tokens:
            continue
        key = getattr(tc, 'tool_use_id', '') or id(tc)
        rid = round_by_tool_id.get(key, 0)
        if not rid and getattr(tc, 'subagent_id', ''):
            rid = subagent_parent_round.get(getattr(tc, 'subagent_id', ''), 0)
        drivers.append(
            {
                'type': 'Tool Result',
                'driver': f'{getattr(tc, "name", "tool")} result',
                'tokens': result_tokens,
                'target_round': rid,
                'target_tab': 'payload',
                'reason': 'large result'
                if result_tokens > LARGE_RESULT_TOKEN_THRESHOLD
                else (getattr(tc, 'status', '') or 'result'),
            }
        )

    driver_total = max(computed_total_tokens, sum(item['tokens'] for item in drivers))
    ranked_drivers = sorted(
        drivers, key=lambda value: (-value['tokens'], value['type'], value['driver'])
    )
    subagent_cost_by_id: dict[str, dict] = {}
    token_round_map = {token_row.get('round_id'): token_row for token_row in token_rounds}
    for rank, item in enumerate(ranked_drivers, start=1):
        row = dict(item)
        row['tokens_label'] = _format_compact_token(row['tokens'])
        row['share'] = _format_ratio_pct(row['tokens'], driver_total)
        row['rank'] = rank
        if row.get('type') == 'Subagent':
            subagent_cost_by_id[str(row.get('target_subagent', ''))] = row
        elif row.get('type') == 'Main LLM Call' and rank <= TOKEN_DRIVER_BADGE_LIMIT:
            target_round = row.get('target_round')
            token_round = token_round_map.get(target_round)
            if not token_round:
                continue
            badge = (
                f'Token Driver {row["driver"]} · '
                f'{row["tokens_label"]} · {row["share"]} · {row["reason"]}'
            )
            token_round.setdefault('badges', []).append(badge)

    max_call_tokens = max([item['tokens'] for item in call_distribution] or [0])
    top_call_indexes = {
        id(item)
        for item in sorted(call_distribution, key=lambda value: value['tokens'], reverse=True)[:3]
        if item['tokens'] > 0
    }
    call_distribution.sort(
        key=lambda value: (value.get('sort_key', (1, '')), value.get('_order', 0))
    )
    for idx, item in enumerate(call_distribution, start=1):
        item['index'] = idx
        item['height_pct'] = (
            round(_ratio_value(item['tokens'], max_call_tokens), 1) if max_call_tokens else 0
        )
        item['is_top'] = id(item) in top_call_indexes
        item.pop('sort_key', None)
        item.pop('_order', None)

    subagent_timeline_map: dict[str, dict] = {}
    subagent_breakdown = []
    for run in subagent_runs:
        summary = run.get('summary', {})
        sa_id = summary.get('agent_id', '')
        agent_type = summary.get('agent_type', '') or 'subagent'
        session_file = str(summary.get('path') or run.get('path') or '')
        sa_tools = [tc for tc in tool_calls if getattr(tc, 'subagent_id', '') == sa_id]
        parent_agent_tools = [tc for tc in tool_calls if _is_subagent_parent_tool(tc, sa_id)]
        related_tool_count = len(sa_tools) + len(parent_agent_tools)
        parent_failed = any(getattr(tc, 'is_failed', False) for tc in parent_agent_tools)
        failures = sum(1 for tc in sa_tools if getattr(tc, 'is_failed', False)) + (
            1 if parent_failed else 0
        )
        failure_rate = _format_ratio_pct(failures, related_tool_count)
        calls = 0
        llm_tokens = 0
        sub_calls = sub_calls_by_agent.get(sa_id, [])
        if sub_calls:
            calls = len(sub_calls)
            llm_tokens = sum(_usage_parts_from_call(call)['total'] for call in sub_calls)
        else:
            for message in run.get('messages', []):
                if getattr(message, 'role', '') != 'assistant':
                    continue
                calls += 1
                parts = _usage_parts_from_mapping(
                    getattr(message, 'usage', {}) or {},
                    agent=getattr(session, 'agent', '') or '',
                    model=getattr(message, 'model', '') or '',
                )
                llm_tokens += parts['total']
        parent_result_tokens = sum(
            max(len(getattr(tc, 'result', '') or '') // 4, 0) for tc in parent_agent_tools
        )
        internal_tool_result_tokens = sum(
            max(len(getattr(tc, 'result', '') or '') // 4, 0) for tc in sa_tools
        )
        footprint_tokens = llm_tokens + parent_result_tokens + internal_tool_result_tokens
        if failures:
            result = 'failed'
        elif calls and llm_tokens:
            result = 'completed'
        elif calls:
            result = 'partial'
        else:
            result = 'unknown'

        timeline_records = []
        if sub_calls:
            for idx, call in enumerate(sub_calls, start=1):
                sub_round_id = (
                    sub_round_by_call_id.get(getattr(call, 'id', ''))
                    or sub_round_by_agent_sequence.get((sa_id, idx))
                    or idx
                )
                timeline_records.append(
                    {
                        'sub_round_id': sub_round_id,
                        'start_time': _call_time_label(
                            getattr(call, 'timestamp', '') or summary.get('started_at', '')
                        ),
                        'parts': _usage_parts_from_call(call),
                        'model': (getattr(call, 'model', '') or 'unknown')[:40],
                    }
                )
        else:
            assistant_idx = 0
            for m_idx, message in enumerate(run.get('messages', []), start=1):
                if getattr(message, 'role', '') != 'assistant':
                    continue
                assistant_idx += 1
                timeline_records.append(
                    {
                        'sub_round_id': m_idx,
                        'start_time': _call_time_label(
                            getattr(message, 'timestamp', '') or summary.get('started_at', '')
                        ),
                        'parts': _usage_parts_from_mapping(
                            getattr(message, 'usage', {}) or {},
                            agent=getattr(session, 'agent', '') or '',
                            model=getattr(message, 'model', '') or '',
                        ),
                        'model': (getattr(message, 'model', '') or 'unknown')[:40],
                    }
                )

        timeline_rows = []
        median_sub_fresh = _median([record['parts'].get('fresh', 0) for record in timeline_records])
        for record in timeline_records:
            parts = record['parts']
            total_raw = int(parts.get('total', 0) or 0)
            input_side = (
                int(parts.get('fresh', 0) or 0)
                + int(parts.get('cache_read', 0) or 0)
                + int(parts.get('cache_write', 0) or 0)
            )
            cache_ratio_value = _ratio_value(parts.get('cache_read', 0), input_side)
            badges = []
            if input_side and cache_ratio_value < LOW_CACHE_RATIO_THRESHOLD:
                badges.append('low cache')
            if median_sub_fresh > 0 and (parts.get('fresh', 0) or 0) > median_sub_fresh * 2:
                badges.append('fresh spike')
            sub_round_id = record['sub_round_id']
            timeline_rows.append(
                {
                    'round_id': sub_round_id,
                    'round_label': f'SR{sub_round_id}',
                    'parent_round': subagent_parent_round.get(sa_id, 0),
                    'subagent_id': sa_id,
                    'subagent_round': sub_round_id,
                    'start_time': record['start_time'],
                    'total': total_raw,
                    'total_label': _format_compact_token(total_raw),
                    'fresh': _format_compact_token(parts.get('fresh', 0)),
                    'cache_read': _format_compact_token(parts.get('cache_read', 0)),
                    'cache_write': _format_compact_token(parts.get('cache_write', 0)),
                    'output': _format_compact_token(parts.get('output', 0)),
                    'fresh_share': _format_ratio_pct(parts.get('fresh', 0), total_raw),
                    'cache_read_share': _format_ratio_pct(parts.get('cache_read', 0), total_raw),
                    'cache_write_share': _format_ratio_pct(parts.get('cache_write', 0), total_raw),
                    'output_share': _format_ratio_pct(parts.get('output', 0), total_raw),
                    'cache_read_ratio': _format_ratio_pct(parts.get('cache_read', 0), input_side),
                    'cache_read_ratio_value': round(cache_ratio_value, 1),
                    'ratio_y': round(100 - cache_ratio_value, 1),
                    'mix': {
                        'fresh': _ratio_value(parts.get('fresh', 0), total_raw),
                        'read': _ratio_value(parts.get('cache_read', 0), total_raw),
                        'write': _ratio_value(parts.get('cache_write', 0), total_raw),
                        'out': _ratio_value(parts.get('output', 0), total_raw),
                    },
                    'llm_calls': 1,
                    'tool_calls': 0,
                    'model': record['model'],
                    'badges': badges,
                }
            )

        if timeline_rows:
            max_sub_tokens = max([row.get('total', 0) for row in timeline_rows] or [0])
            step = 32
            sub_width = max(1, len(timeline_rows) - 1) * step
            sub_plot_width = (len(timeline_rows) * 32) + 12
            for idx, token_row in enumerate(timeline_rows):
                token_row['line_x'] = idx * step
                token_row['line_y'] = round(
                    100 - (token_row.get('cache_read_ratio_value', 0) or 0), 1
                )
                token_row['bar_height_pct'] = round(
                    _ratio_value(token_row.get('total', 0), max_sub_tokens), 1
                )
            sub_line_points = ' '.join(f'{row["line_x"]},{row["line_y"]}' for row in timeline_rows)
        else:
            sub_width = 0
            sub_plot_width = 0
            sub_line_points = ''

        subagent_timeline_map[sa_id] = {
            'subagent': agent_type,
            'subagent_id': sa_id,
            'short_id': sa_id[-8:] if sa_id else 'unknown',
            'color': f'subagent-{subagent_color_map.get(sa_id, 0)}',
            'parent_round': subagent_parent_round.get(sa_id, 0),
            'token_rounds': timeline_rows,
            'cache_line_points': sub_line_points,
            'cache_line_width': sub_width,
            'cache_line_plot_width': sub_plot_width,
            'cache_line_left': 22,
            'summary': (
                f'{calls} LLM · {_format_compact_token(llm_tokens)} LLM tokens · '
                f'{len(sa_tools)} tools · {failures} failures'
            ),
        }
        subagent_cost = subagent_cost_by_id.get(sa_id, {})
        subagent_cost_label = subagent_cost.get('tokens_label') or _format_compact_token(llm_tokens)
        subagent_cost_share = subagent_cost.get('share') or _format_ratio_pct(
            llm_tokens, driver_total
        )
        subagent_cost_reason = (
            subagent_cost.get('reason') or f'{calls} LLM call{"s" if calls != 1 else ""}'
        )
        subagent_cost_note = (
            f'Token Driver = {subagent_cost_label} · {subagent_cost_share} · {subagent_cost_reason}'
        )
        subagent_breakdown.append(
            {
                'subagent': agent_type,
                'agent_id': sa_id,
                'subagent_id': sa_id,
                'short_id': sa_id[-8:] if sa_id else 'unknown',
                'session_file': session_file,
                'session_file_display': _agent_session_file_display(session_file),
                'session_id': sa_id,
                'session_id_display': _agent_session_id_display(sa_id),
                'color': f'subagent-{subagent_color_map.get(sa_id, 0)}',
                'llm_calls': calls,
                'tokens': _format_compact_token(footprint_tokens),
                'tokens_raw': footprint_tokens,
                'token_note': (
                    f'Footprint = LLM {_format_compact_token(llm_tokens)} · '
                    f'Parent result {_format_compact_token(parent_result_tokens)} · '
                    f'Tool results {_format_compact_token(internal_tool_result_tokens)} · '
                    f'{subagent_cost_note}'
                ),
                'cost_tokens': subagent_cost_label,
                'cost_share': subagent_cost_share,
                'cost_reason': subagent_cost_reason,
                'cost_rank': subagent_cost.get('rank', 0),
                'tools': len(sa_tools),
                'failures': failures,
                'failure_rate': failure_rate,
                'failure_label': f'{failures} failed · {failure_rate}',
                'failure_tone': _ratio_tone(_ratio_value(failures, related_tool_count)),
                'failure_note': (
                    'Failures among subagent tool calls and the parent spawn tool'
                    if related_tool_count
                    else 'No related tool calls for failure-rate calculation'
                ),
                'result': result,
                'round_id': subagent_parent_round.get(sa_id, 0),
                'target_subagent_round': '',
            }
        )
    subagent_breakdown.sort(key=lambda row: (-row['tokens_raw'], row['subagent']))
    for idx, row in enumerate(subagent_breakdown):
        row['is_selected'] = idx == 0

    subagent_timelines = [
        subagent_timeline_map[row['subagent_id']]
        for row in subagent_breakdown
        if row.get('subagent_id') in subagent_timeline_map
    ]
    for idx, timeline in enumerate(subagent_timelines):
        timeline['is_selected'] = idx == 0

    main_llm_call_count = _main_scope_llm_call_count(rounds, llm_calls)
    main_tool_calls = [
        tc
        for tc in tool_calls
        if not getattr(tc, 'subagent_id', '') and getattr(tc, 'scope', 'main') != 'subagent'
    ]
    main_failed_tools = [tc for tc in main_tool_calls if getattr(tc, 'is_failed', False)]
    main_failure_rate = _format_ratio_pct(len(main_failed_tools), len(main_tool_calls))
    main_session_file = _session_file_path(session)
    main_session_id = str(getattr(session, 'session_id', '') or '')
    main_tokens = sum(int(row.get('total', 0) or 0) for row in token_rounds)
    main_fresh_tokens = sum(int(row.get('token_input', 0) or 0) for row in trace_rows)
    main_cache_read_tokens = sum(int(row.get('token_cache_read', 0) or 0) for row in trace_rows)
    main_cache_write_tokens = sum(int(row.get('token_cache_write', 0) or 0) for row in trace_rows)
    main_output_tokens = sum(int(row.get('token_output', 0) or 0) for row in trace_rows)
    main_agent_row = {
        'scope': 'main',
        'subagent': 'main agent',
        'agent_id': '',
        'subagent_id': '',
        'short_id': 'main',
        'session_file': main_session_file,
        'session_file_display': _agent_session_file_display(main_session_file),
        'session_id': main_session_id,
        'session_id_display': _agent_session_id_display(main_session_id),
        'color': 'main',
        'llm_calls': main_llm_call_count,
        'tokens': _format_compact_token(main_tokens),
        'tokens_raw': main_tokens,
        'token_note': (
            f'Main round tokens = {_format_compact_token(main_tokens)} · '
            f'Fresh {_format_compact_token(main_fresh_tokens)} · '
            f'Cache Read {_format_compact_token(main_cache_read_tokens)} · '
            f'Cache Write {_format_compact_token(main_cache_write_tokens)} · '
            f'Output {_format_compact_token(main_output_tokens)}'
        ),
        'cost_tokens': _format_compact_token(main_tokens),
        'cost_share': _format_ratio_pct(main_tokens, driver_total),
        'cost_reason': (
            f'{main_llm_call_count} main LLM call{"s" if main_llm_call_count != 1 else ""}'
        ),
        'cost_rank': 0,
        'tools': len(main_tool_calls),
        'failures': len(main_failed_tools),
        'failure_rate': main_failure_rate,
        'failure_label': f'{len(main_failed_tools)} failed · {main_failure_rate}',
        'failure_tone': _ratio_tone(_ratio_value(len(main_failed_tools), len(main_tool_calls))),
        'failure_note': (
            'Failures among main-scope tool calls'
            if main_tool_calls
            else 'No main-scope tool calls for failure-rate calculation'
        ),
        'result': 'completed' if main_llm_call_count else 'unknown',
        'round_id': token_rounds[0].get('round_id', 0) if token_rounds else 0,
        'target_subagent_round': '',
        'is_selected': True,
    }
    main_agent_timeline = {
        'scope': 'main',
        'subagent': 'main agent',
        'subagent_id': '',
        'short_id': 'main',
        'color': 'main',
        'parent_round': '',
        'token_rounds': token_rounds,
        'cache_line_points': line_points,
        'cache_line_width': width,
        'cache_line_plot_width': plot_width,
        'cache_line_left': 22,
        'summary': (
            f'{main_llm_call_count} LLM · {_format_compact_token(main_tokens)} tokens · '
            f'{len(main_tool_calls)} tools · {len(main_failed_tools)} failures'
        ),
        'is_selected': True,
    }
    agent_breakdown = [main_agent_row]
    agent_breakdown.extend(
        [{**row, 'scope': 'subagent', 'is_selected': False} for row in subagent_breakdown]
    )
    agent_timelines = [main_agent_timeline]
    agent_timelines.extend(
        [{**timeline, 'scope': 'subagent', 'is_selected': False} for timeline in subagent_timelines]
    )

    tool_result_tokens = sum(
        _estimate_payload_tokens(getattr(tc, 'result', '') or '') for tc in tool_calls
    )
    subagent_context_tokens = 0
    for run in subagent_runs:
        sa_id = (run.get('summary', {}) or {}).get('agent_id', '')
        sub_calls = sub_calls_by_agent.get(sa_id, [])
        if sub_calls:
            for call in sub_calls:
                parts = _usage_parts_from_call(call)
                subagent_context_tokens += (
                    parts['fresh'] + parts['cache_read'] + parts['cache_write']
                )
        else:
            for message in run.get('messages', []):
                if getattr(message, 'role', '') != 'assistant':
                    continue
                parts = _usage_parts_from_mapping(
                    getattr(message, 'usage', {}) or {},
                    agent=getattr(session, 'agent', '') or '',
                    model=getattr(message, 'model', '') or '',
                )
                subagent_context_tokens += (
                    parts['fresh'] + parts['cache_read'] + parts['cache_write']
                )
    segments = [
        {'label': 'System', 'tokens': None, 'source': 'unavailable', 'precision': 'unavailable'},
        {
            'label': 'Provider Cached Input',
            'tokens': cache_read_tokens,
            'source': 'provider accounting cache read',
            'precision': 'provider_reported',
        },
        {
            'label': 'Current User Input',
            'tokens': fresh_tokens,
            'source': 'provider fresh input component',
            'precision': 'provider_reported',
        },
        {
            'label': 'Tool Results',
            'tokens': tool_result_tokens,
            'source': 'transcript result length',
            'precision': 'estimated',
        },
        {
            'label': 'Subagent Context',
            'tokens': subagent_context_tokens,
            'source': 'subagent usage',
            'precision': 'estimated',
        },
        {
            'label': 'Output',
            'tokens': output_tokens,
            'source': 'provider output',
            'precision': 'exact',
        },
    ]
    segment_total = sum(s['tokens'] or 0 for s in segments)
    for segment in segments:
        if segment['tokens'] is None:
            segment['share'] = 'unavailable'
            segment['share_value'] = 0
            segment['tokens_label'] = 'N/A'
            segment['status'] = 'unavailable'
        else:
            segment['share'] = _format_ratio_pct(segment['tokens'], segment_total)
            segment['share_value'] = round(_ratio_value(segment['tokens'], segment_total), 1)
            label = _format_compact_token(segment['tokens'])
            segment['tokens_label'] = (
                f'~{label}' if segment.get('precision') == 'estimated' and label != '0' else label
            )
            segment['status'] = 'available'

    sorted_issues = sorted(
        issues,
        key=lambda issue: (
            0 if issue['tone'] == 'critical' else 1,
            0 if issue.get('round_id') else 1,
            issue.get('round_id') or 999999,
        ),
    )

    return {
        'token_rounds': token_rounds,
        'cache_line_points': line_points,
        'cache_line_width': width,
        'cache_line_plot_width': plot_width,
        'cache_line_left': 22,
        'token_stats': [],
        'tool_impact': {
            'rows': tool_summary,
            'all_tool_calls': len(tool_calls),
            'failed_tools': len(failed_tools),
            'failed_tools_rate': _format_ratio_pct(len(failed_tools), len(tool_calls)),
            'failed_tools_tone': _ratio_tone(_ratio_value(len(failed_tools), len(tool_calls))),
            'distinct_tools': len(tool_stats),
            'main_tools': sum(1 for tc in tool_calls if not getattr(tc, 'subagent_id', '')),
            'subagent_tools': sum(1 for tc in tool_calls if getattr(tc, 'subagent_id', '')),
        },
        'tool_summary': tool_summary,
        'signals': sorted_issues[:5],
        'issues': sorted_issues,
        'issue_summary': issue_summary,
        'issue_rounds': len([rid for rid, sig in round_signals.items() if sig.get('issues')]),
        'round_signals': round_signals,
        'call_distribution': call_distribution,
        'call_legend': call_legend,
        'agent_breakdown': agent_breakdown,
        'agent_timelines': agent_timelines,
        'subagent_breakdown': subagent_breakdown,
        'subagent_timelines': subagent_timelines,
        'context_segments': segments,
        'context_scope': 'Session-level',
    }


def _find_user_message_content(
    all_messages: list[object], msg_array: list[dict], target_index: int
) -> str:
    """Find full user message text for bucket-detail payload expansion.

    Args:
        all_messages: Raw message records searched for a matching user entry.
        msg_array: Preview message array containing bucket-detail rows.
        target_index: Zero-based user_text preview index to resolve.

    Returns:
        Full matched user text, preview fallback, or an empty string.
    """
    user_text_entries = [m for m in msg_array if m.get('content_type') == 'user_text']
    if target_index >= len(user_text_entries):
        return ''
    target_entry = user_text_entries[target_index]
    target_preview = target_entry.get('content_preview', '')

    for msg in all_messages:
        role = ''
        content = ''
        if isinstance(msg, dict):
            role = msg.get('role', '')
            content = msg.get('content', '')
        elif hasattr(msg, 'role'):
            role = getattr(msg, 'role', '')
            content = getattr(msg, 'content', '') or ''

        if role == 'user' and content:
            content_str = str(content).strip()
            if content_str and content_str[:200] == target_preview:
                return content_str
    return target_preview


def _find_tool_result_content(
    all_messages: list[object], msg_array: list[dict], target_index: int
) -> str:
    """Find full tool result text for bucket-detail payload expansion.

    Args:
        all_messages: Raw message records searched for embedded tool results.
        msg_array: Preview message array containing bucket-detail rows.
        target_index: Zero-based tool_result preview index to resolve.

    Returns:
        Full matched tool result text, preview fallback, or an empty string.
    """
    tr_entries = [m for m in msg_array if m.get('content_type') == 'tool_result']
    if target_index >= len(tr_entries):
        return ''
    target_entry = tr_entries[target_index]
    tuid = target_entry.get('tool_use_id', '')

    for msg in all_messages:
        request_full = ''
        if isinstance(msg, dict):
            request_full = msg.get('request_full', '') or ''
        elif hasattr(msg, 'request_full'):
            request_full = getattr(msg, 'request_full', '') or ''

        if request_full and tuid:
            pattern = f'Tool result for {tuid}:'
            idx = request_full.find(pattern)
            if idx >= 0:
                start = idx + len(pattern)
                end = request_full.find('\n\n', start)
                if end < 0:
                    end = len(request_full)
                return request_full[start:end].strip()
    return target_entry.get('content_preview', '')


def _find_assistant_message_content(
    all_messages: list[object], msg_array: list[dict], target_index: int
) -> str:
    """Find full assistant message text for bucket-detail payload expansion.

    Args:
        all_messages: Raw message records searched for a matching assistant entry.
        msg_array: Preview message array containing bucket-detail rows.
        target_index: Zero-based assistant_text preview index to resolve.

    Returns:
        Full matched assistant text, preview fallback, or an empty string.
    """
    assistant_entries = [m for m in msg_array if m.get('content_type') == 'assistant_text']
    if target_index >= len(assistant_entries):
        return ''
    target_entry = assistant_entries[target_index]
    target_preview = target_entry.get('content_preview', '')

    for msg in all_messages:
        role = ''
        content = ''
        if isinstance(msg, dict):
            role = msg.get('role', '')
            content = msg.get('content', '')
        elif hasattr(msg, 'role'):
            role = getattr(msg, 'role', '')
            content = getattr(msg, 'content', '') or ''

        if role == 'assistant' and content:
            content_str = str(content).strip()
            if content_str and content_str[:200] == target_preview:
                return content_str
    return target_preview


def _build_v11_view_model(  # noqa: PLR0912, PLR0913, PLR0915
    session: object,
    rounds: list,
    llm_calls: list,
    tool_calls: list,
    subagent_runs: list[SubagentRun],
    session_anomalies: object,
    slim: bool = False,
    round_filter: set[int] | None = None,
    skip_attribution: bool = False,
) -> SessionDetailViewModel:
    """Build the session detail timeline view model for the HTML template.

    The session detail route calls this builder after parsing a session and its
    derived attribution/anomaly data. It aggregates trace rows, payload drawer
    sources, hero metrics, diagnostics, and subagent breakdowns while preserving
    the stable payload identifiers used by API endpoints.

    Args:
        session: Parsed session summary object used as the root display model.
        rounds: Parsed main-session rounds to render in order.
        llm_calls: Flat normalized LLM calls for token attribution and labels.
        tool_calls: Flat parsed tool-call list for timeline and diagnostics.
        subagent_runs: Parsed subagent transcripts attached to the session.
        session_anomalies: Analyzer result containing session-level anomalies.
        slim: Whether to skip payload source embedding for fast initial render.
        round_filter: Optional zero-based round indexes to fully materialize.
        skip_attribution: Whether to defer expensive attribution payload building.

    Returns:
        Session detail view model dictionary consumed by ``session.html`` and
        round-detail API responses.
    """
    agent_name = (
        'Claude'
        if session.agent == 'claude_code'
        else 'Qoder'
        if session.agent == 'qoder'
        else 'Codex'
    )
    short_id = session.session_id[-8:] if session.session_id else ''
    started = session.started_at[:10] if session.started_at else '—'

    total_tokens = getattr(session, 'total_tokens', 0) or (
        session.fresh_input_tokens
        + session.output_tokens
        + session.cache_read_tokens
        + session.cache_write_tokens
    )
    total_rounds = len(rounds)
    total_tools = len(tool_calls)
    parsed_failed_tools = sum(1 for tc in tool_calls if getattr(tc, 'is_failed', False))
    total_failed = max(session.failed_tool_count or 0, parsed_failed_tools)

    # 说明:-- Issue links --
    issue_links = []
    for r_idx, r in enumerate(rounds):
        failed = [tc for tc in r.tool_calls if tc.is_failed]
        if failed or r.llm_error_count > 0:
            parts = []
            if failed:
                parts.append(f'{len(failed)} failed')
            if r.llm_error_count > 0:
                parts.append(f'{r.llm_error_count} llm err')
            issue_links.append(
                {
                    'round_id': r_idx + 1,
                    'label': f'R{r_idx + 1} · {", ".join(parts)}',
                    'tone': 'err',
                }
            )
    issue_links = issue_links[:4]

    # 说明:-- Payload sources (LIST, not dict) --
    payload_sources = []

    def add_payload(  # noqa: PLR0912, PLR0913
        payload_id: str,
        kind: str,
        title: str,
        status: str = 'available',
        size: str = '—',
        text: str = '',
        html: str = '',
        warning: str = '',
        context_blocks: list | None = None,
        source_status: str = '',
        response_blocks: list | None = None,
        response_diagnostics: str = '',
        user_input: str = '',
        preceding_tool_results: list | None = None,
        tool_name: str = '',
        tool_command: str = '',
        tool_workdir: str = '',
        tool_parameters: dict | None = None,
        tool_status: str = '',
        data: dict | None = None,
    ) -> None:
        """Append one payload drawer source to the view model.

        Args:
            payload_id: Stable payload ID shared with links and API routes.
            kind: Payload category used by templates and diagnostics.
            title: Human-readable payload drawer title.
            status: Availability status for the payload source.
            size: Display size label when content is summarized.
            text: Plain-text payload body when no HTML rendering is available.
            html: Pre-rendered safe HTML payload body.
            warning: Diagnostic warning shown when source data is unavailable.
            context_blocks: Optional reconstructed context block summaries.
            source_status: Raw, reconstructed, or diagnostic source label.
            response_blocks: Optional response block summaries.
            response_diagnostics: Optional response parsing diagnostic label.
            user_input: Optional user input snippet for reconstructed contexts.
            preceding_tool_results: Optional prior tool summaries.
            tool_name: Optional source tool name for result payloads.
            tool_command: Optional full command or rendered tool command summary.
            tool_workdir: Optional tool working directory for command payloads.
            tool_parameters: Optional raw tool parameters for inspection.
            tool_status: Optional tool exit or status label.
            data: Optional structured attribution payload.

        Returns:
            None. The helper mutates ``payload_sources`` in place.
        """
        entry = {
            'payload_id': payload_id,
            'kind': kind,
            'title': title,
            'status': status,
            'size': size,
        }
        if warning:
            entry['warning'] = warning
        if html:
            entry['html'] = html
        elif text:
            entry['text'] = text
        else:
            entry['text'] = ''
        if context_blocks:
            entry['context_blocks'] = context_blocks
        if source_status:
            entry['source_status'] = source_status
        if response_blocks:
            entry['response_blocks'] = response_blocks
        if response_diagnostics:
            entry['response_diagnostics'] = response_diagnostics
        if user_input:
            entry['user_input'] = user_input
        if preceding_tool_results:
            entry['preceding_tool_results'] = preceding_tool_results
        if tool_name:
            entry['tool_name'] = tool_name
        if tool_command:
            entry['tool_command'] = tool_command
        if tool_workdir:
            entry['tool_workdir'] = tool_workdir
        if tool_parameters:
            entry['tool_parameters'] = tool_parameters
        if tool_status:
            entry['tool_status'] = tool_status
        if kind in {'tool.result', 'subagent.tool.result'} and text:
            entry['token_estimate'] = _estimate_payload_tokens(text)
            entry['token_estimate_precision'] = 'estimated'
            entry['token_estimate_source'] = 'result text'
        if data is not None:
            entry['data'] = data
        payload_sources.append(entry)

    def tool_vm(tc: object, tool_id: str, payload_id: str = '', payload_title: str = '') -> dict:
        """Build a timeline row for one tool call.

        Args:
            tc: Parsed tool call object from the main session or a subagent.
            tool_id: Stable display ID for the timeline row.
            payload_id: Optional result payload ID linked from the row.
            payload_title: Optional payload drawer title for the result.

        Returns:
            Tool-call row dictionary consumed by timeline templates.
        """
        params = getattr(tc, 'parameters', {}) or {}
        raw_command = _build_tool_command_summary(getattr(tc, 'name', 'tool'), params)
        command = _shorten_path(str(raw_command))
        result_text = (getattr(tc, 'result', '') or '').strip()
        result_token_estimate = _estimate_payload_tokens(result_text) if result_text else 0
        if result_text:
            result_summary = result_text[:60]
        elif getattr(tc, 'exit_code', None) is not None:
            result_summary = f'exit {tc.exit_code}'
        else:
            result_summary = getattr(tc, 'status', '') or 'ok'
        return {
            'tool_id': tool_id,
            'type': 'tool_call',
            'tool_name': getattr(tc, 'name', 'tool') or 'tool',
            'kind': (getattr(tc, 'name', 'tool') or 'tool')[:4].upper(),
            'command': str(command)[:180],
            'result_summary': result_summary,
            'exit_label': f'exit {tc.exit_code}'
            if getattr(tc, 'exit_code', None) is not None
            else (getattr(tc, 'status', '') or 'ok'),
            'status_tone': 'fail'
            if getattr(tc, 'is_failed', False)
            else ('warn' if getattr(tc, 'has_nonzero_exit', False) else 'ok'),
            'payload_id': payload_id,
            'payload_title': payload_title or 'Tool Result',
            'timestamp': _call_time_label(getattr(tc, 'timestamp', '') or ''),
            'duration_label': _format_duration_short((getattr(tc, 'duration_ms', 0) or 0) / 1000),
            'result_token_estimate': result_token_estimate,
            'result_token_label': f'~{_format_compact_token(result_token_estimate)}'
            if result_token_estimate
            else '—',
        }

    def payload_action(
        payload_id: str, label: str, kind: str, title: str, status: str = 'partial'
    ) -> dict:
        """Build an attribution or payload action descriptor.

        Args:
            payload_id: Payload ID opened when the action is clicked.
            label: Short button label shown in the timeline row.
            kind: Payload category used for routing and styling.
            title: Full payload drawer title.
            status: Availability status that determines tone and enabled state.

        Returns:
            Action dictionary consumed by trace rows and subagent rows.
        """
        tone = 'ok' if status in ('available', 'ok') else 'warn' if status == 'partial' else 'muted'
        return {
            'payload_id': payload_id,
            'label': label,
            'kind': kind,
            'title': title,
            'status': status,
            'tone': tone,
            'is_available': bool(payload_id),
        }

    def summarize_attribution_actions(actions: list[dict], label: str, kind: str) -> dict:
        """Collapse multiple attribution actions into one round-level action.

        Args:
            actions: Per-call attribution action descriptors for a round.
            label: Short prefix such as Req or Resp.
            kind: Attribution payload category being summarized.

        Returns:
            Representative action with aggregate availability status.
        """
        available = [a for a in actions if a.get('payload_id')]
        total = len(actions)
        if total <= 0:
            return payload_action(
                '', f'{label} —', kind, f'{label} attribution unavailable', 'unavailable'
            )
        first = available[0] if available else actions[0]
        status = (
            'available' if len(available) == total else 'partial' if available else 'unavailable'
        )
        display = f'{label} {len(available)}/{total}' if total > 1 else f'{label} {status}'
        return {
            **first,
            'label': display,
            'status': status,
            'tone': 'ok' if status == 'available' else 'warn' if status == 'partial' else 'muted',
            'is_available': bool(available),
        }

    def assistant_text_blocks(blocks: list[dict]) -> list[dict]:
        """Filter assistant content blocks to visible text-like blocks.

        Args:
            blocks: Raw normalized response content blocks from an LLM call.

        Returns:
            Blocks containing assistant text or thinking content.
        """
        filtered = []
        for block in blocks or []:
            block_type = block.get('type', '')
            if block_type == 'output_text':
                block_type = 'text'
            if block_type not in ('thinking', 'text'):
                continue
            text = block.get('content') or block.get('text') or block.get('thinking') or ''
            if not str(text).strip():
                continue
            normalized = dict(block)
            normalized['type'] = block_type
            normalized['content'] = str(text)
            filtered.append(normalized)
        return filtered

    def assistant_text_from_blocks(blocks: list[dict], fallback_text: str = '') -> str:
        """Extract assistant text from content blocks with a raw fallback.

        Args:
            blocks: Raw normalized response content blocks from an LLM call.
            fallback_text: Raw response text used when blocks are unavailable.

        Returns:
            Joined assistant text suitable for a payload drawer.
        """
        parts = []
        for block in assistant_text_blocks(blocks):
            text = block.get('content') or block.get('text') or block.get('thinking') or ''
            if str(text).strip():
                parts.append(str(text).strip())
        if parts:
            return '\n\n'.join(parts)
        return fallback_text.strip() if fallback_text and fallback_text.strip() else ''

    def content_event_items(
        blocks: list[dict], payload_id: str, payload_title: str, fallback_text: str = ''
    ) -> list[dict]:
        """Build visible assistant content events for a timeline step list.

        Args:
            blocks: Raw normalized response content blocks from an LLM call.
            payload_id: Payload ID that opens the full assistant content.
            payload_title: Payload drawer title for the assistant content.
            fallback_text: Raw response text used when blocks are unavailable.

        Returns:
            Timeline event rows for assistant text or thinking content.
        """
        events = []
        for idx, block in enumerate(blocks or [], start=1):
            block_type = block.get('type', '')
            if block_type == 'output_text':
                block_type = 'text'
            if block_type not in ('thinking', 'text'):
                continue
            text = block.get('content') or block.get('text') or block.get('thinking') or ''
            if not str(text).strip():
                continue
            events.append(
                {
                    'type': 'assistant_thinking' if block_type == 'thinking' else 'assistant_text',
                    'title': 'Assistant Thinking' if block_type == 'thinking' else 'Assistant Text',
                    'text': str(text).strip()[:500],
                    'payload_id': payload_id,
                    'payload_title': payload_title,
                    'timestamp': _call_time_label(block.get('timestamp', '') or ''),
                    'block_index': idx,
                }
            )
        if not events and fallback_text and fallback_text.strip():
            events.append(
                {
                    'type': 'assistant_text',
                    'title': 'Assistant Text',
                    'text': fallback_text.strip()[:500],
                    'payload_id': payload_id,
                    'payload_title': payload_title,
                    'timestamp': '',
                    'block_index': 1,
                }
            )
        return events

    def count_raw_tool_uses(ix: object) -> int:
        """Count raw tool-use blocks embedded in an interaction payload.

        Args:
            ix: Parsed interaction with optional raw tool-call JSON.

        Returns:
            Number of tool_use objects in the raw payload, or zero on parse
            failure.
        """
        raw = getattr(ix, 'tool_calls_raw', '') or ''
        if not raw:
            return 0
        try:
            parsed = json.loads(raw)
        except Exception:
            return 0
        if isinstance(parsed, list):
            return len(
                [
                    p
                    for p in parsed
                    if isinstance(p, dict) and p.get('type', 'tool_use') == 'tool_use'
                ]
            )
        return 0

    sub_llm_calls_by_id = {
        getattr(call, 'id', ''): call
        for call in llm_calls
        if getattr(call, 'scope', '') == 'subagent' and getattr(call, 'id', '')
    }
    sub_llm_calls_by_agent: dict[str, list] = {}
    for call in llm_calls:
        if getattr(call, 'scope', '') != 'subagent':
            continue
        sub_llm_calls_by_agent.setdefault(getattr(call, 'subagent_id', '') or '', []).append(call)

    # 说明:-- Build subagent lookup --
    subagent_lookup = {}
    for run in subagent_runs:
        sa_id = run['summary']['agent_id']
        sa_name = run['summary'].get('agent_type', 'subagent')
        sa_tools = [tc for tc in tool_calls if tc.subagent_id == sa_id]
        parent_tc = next(
            (tc for tc in tool_calls if _is_subagent_parent_tool(tc, sa_id)),
            None,
        )
        display_tools = sa_tools if sa_tools else ([parent_tc] if parent_tc else [])
        sa_messages = run.get('messages', [])
        sa_calls = sub_llm_calls_by_agent.get(sa_id, [])
        if sa_calls:
            sa_input = sum(
                _usage_parts_from_call(call)['fresh']
                + _usage_parts_from_call(call)['cache_read']
                + _usage_parts_from_call(call)['cache_write']
                for call in sa_calls
            )
            sa_output = sum(_usage_parts_from_call(call)['output'] for call in sa_calls)
        else:
            sa_input = 0
            sa_output = 0
            for m in sa_messages:
                if getattr(m, 'role', '') != 'assistant':
                    continue
                parts = _usage_parts_from_mapping(
                    getattr(m, 'usage', {}) or {},
                    agent=session.agent,
                    model=getattr(m, 'model', '') or '',
                )
                sa_input += parts['fresh'] + parts['cache_read'] + parts['cache_write']
                sa_output += parts['output']
        sa_failed = sum(1 for tc in display_tools if tc.is_failed)

        sa_tool_by_id = {tc.tool_use_id: tc for tc in display_tools if tc.tool_use_id}
        matched_tool_ids = set()

        sub_rounds = []
        sub_call_cursor = 0
        for m_idx, m in enumerate(sa_messages):
            if m.role == 'assistant':
                matched_call = sub_llm_calls_by_id.get(getattr(m, 'llm_call_id', '') or '')
                if not matched_call and sub_call_cursor < len(sa_calls):
                    matched_call = sa_calls[sub_call_cursor]
                sub_call_cursor += 1
                parts = (
                    _usage_parts_from_call(matched_call)
                    if matched_call
                    else _usage_parts_from_mapping(
                        getattr(m, 'usage', {}) or {},
                        agent=session.agent,
                        model=getattr(m, 'model', '') or '',
                    )
                )
                call_ref = m.llm_call_id or f'sub-{sa_id}-{m_idx + 1}'
                ctx_payload_id = f'sub-{sa_id}-{m_idx + 1}-ctx'
                rsp_payload_id = f'sub-{sa_id}-{m_idx + 1}-rsp'

                if m.request_full:
                    ctx_norm_blocks = normalize_llm_content(m.request_full)
                    ctx_content_html = (
                        _render_context_content_blocks(ctx_norm_blocks) if ctx_norm_blocks else ''
                    )
                    add_payload(
                        payload_id=ctx_payload_id,
                        kind='subagent.request',
                        title=f'Subagent · Request ({call_ref})',
                        html=ctx_content_html,
                        source_status='raw',
                    )
                else:
                    add_payload(
                        payload_id=ctx_payload_id,
                        kind='subagent.request',
                        title=f'Subagent · Request ({call_ref})',
                        text='',
                        warning='Subagent request context not available',
                        source_status='diagnostic',
                    )

                if m.content or m.content_blocks:
                    sa_tool_calls = []
                    for tc_ref in m.tool_calls or []:
                        sa_tool_calls.append(
                            SimpleNamespace(
                                name=tc_ref.get('name', tc_ref.get('type', 'unknown')),
                                parameters=tc_ref.get('input', {}),
                                tool_use_id=tc_ref.get('id', ''),
                                subagent_id='',
                            )
                        )
                    sa_blocks_html = _render_response_content_blocks(
                        content_blocks=m.content_blocks if m.content_blocks else None,
                        response_text=m.content[:5000] if not m.content_blocks else '',
                        tool_calls=sa_tool_calls if not m.content_blocks else [],
                    )

                    sa_rsp_blocks = []
                    if m.content_blocks:
                        for cb in m.content_blocks:
                            cb_type = cb.get('type', '')
                            if cb_type == 'text':
                                sa_rsp_blocks.append(
                                    {
                                        'type': 'text',
                                        'size_label': _format_bytes(
                                            min(len(cb.get('content', '')), 10000)
                                        ),
                                    }
                                )
                            elif cb_type == 'thinking':
                                sa_rsp_blocks.append(
                                    {
                                        'type': 'thinking',
                                        'size_label': _format_bytes(
                                            min(len(cb.get('content', '')), 10000)
                                        ),
                                    }
                                )
                            elif cb_type == 'tool_use':
                                sa_rsp_blocks.append(
                                    {
                                        'type': 'tool_use',
                                        'name': cb.get('name', 'unknown')[:40],
                                        'tool_id': cb.get('id', '') or '',
                                    }
                                )
                    else:
                        if m.content and m.content.strip():
                            sa_rsp_blocks.append(
                                {
                                    'type': 'text',
                                    'size_label': _format_bytes(min(len(m.content), 10000)),
                                }
                            )
                        for tc in sa_tool_calls:
                            sa_rsp_blocks.append(
                                {
                                    'type': 'tool_use',
                                    'name': getattr(tc, 'name', 'unknown')[:40],
                                    'tool_id': getattr(tc, 'tool_use_id', '') or '',
                                }
                            )

                    block_count = len(sa_rsp_blocks) if sa_rsp_blocks else 1
                    sa_size_label = f'{block_count} content block{"s" if block_count != 1 else ""}'
                    add_payload(
                        payload_id=rsp_payload_id,
                        kind='subagent.response',
                        title=f'Subagent · Response ({call_ref})',
                        html=sa_blocks_html,
                        size=sa_size_label,
                        response_blocks=sa_rsp_blocks,
                        source_status='raw',
                    )
                else:
                    add_payload(
                        payload_id=rsp_payload_id,
                        kind='subagent.response',
                        title=f'Subagent · Response ({call_ref})',
                        text='',
                        warning='Subagent response content not available',
                        source_status='diagnostic',
                    )

                if m.request_full:
                    (m.request_full or '')[:PAYLOAD_INFO_PREVIEW_CHARS]
                    'info' if len(m.request_full) > PAYLOAD_INFO_PREVIEW_CHARS else 'ok'
                else:
                    pass

                m_idx + 1

                sa_req_attr_id = f'sub-{sa_id}-IX{m_idx + 1}-request-attribution'
                sa_rsp_attr_id = f'sub-{sa_id}-IX{m_idx + 1}-response-attribution'
                sa_req_action = payload_action(
                    sa_req_attr_id,
                    'Req partial',
                    'llm.request_attribution',
                    f'Subagent · Request Attribution ({call_ref})',
                    'partial',
                )
                sa_rsp_action = payload_action(
                    sa_rsp_attr_id,
                    'Resp partial',
                    'llm.response_attribution',
                    f'Subagent · Response Attribution ({call_ref})',
                    'partial',
                )

                steps = content_event_items(
                    m.content_blocks if m.content_blocks else [],
                    rsp_payload_id,
                    f'Subagent · Response ({call_ref})',
                    m.content if not m.content_blocks else '',
                )

                add_payload(
                    payload_id=sa_req_attr_id,
                    kind='llm.request_attribution',
                    title=f'Subagent · Request Attribution ({call_ref})',
                    text='',
                    warning='Subagent attribution: use API endpoint for live data.',
                )
                add_payload(
                    payload_id=sa_rsp_attr_id,
                    kind='llm.response_attribution',
                    title=f'Subagent · Response Attribution ({call_ref})',
                    text='',
                    warning='Subagent attribution: use API endpoint for live data.',
                )

                round_tool_tcs = []
                for tc_ref in m.tool_calls or []:
                    tc_id = tc_ref.get('id', '') if isinstance(tc_ref, dict) else ''
                    if tc_id and tc_id in sa_tool_by_id and tc_id not in matched_tool_ids:
                        round_tool_tcs.append(sa_tool_by_id[tc_id])
                        matched_tool_ids.add(tc_id)

                if round_tool_tcs:
                    round_tool_rows = []
                    for t_idx, tc in enumerate(round_tool_tcs, start=1):
                        t_payload_id = (
                            f'sub-{sa_id}-{m_idx + 1}-T{t_idx}-result' if tc.result else ''
                        )
                        t_payload_title = f'Subagent · {tc.name} · Result'
                        if tc.result:
                            command_fields = _build_tool_result_command_fields(
                                tc.name, tc.parameters
                            )
                            add_payload(
                                payload_id=t_payload_id,
                                kind='subagent.tool.result',
                                title=t_payload_title,
                                text=tc.result,
                                tool_name=tc.name,
                                tool_command=command_fields['command'],
                                tool_workdir=command_fields['workdir'],
                                tool_parameters=tc.parameters,
                                tool_status=f'exit {tc.exit_code}'
                                if getattr(tc, 'exit_code', None) is not None
                                else (getattr(tc, 'status', '') or 'ok'),
                            )
                        round_tool_rows.append(
                            tool_vm(tc, f'sub-{sa_id}-T{t_idx}', t_payload_id, t_payload_title)
                        )

                    steps.extend(round_tool_rows)
                else:
                    round_tool_rows = []

                st_input = parts['fresh']
                st_cache_read = parts['cache_read']
                st_cache_write = parts['cache_write']
                st_output = parts['output']
                st_total = st_input + st_cache_read + st_cache_write + st_output
                st_mix = {'fresh': 0, 'read': 0, 'write': 0, 'out': 0}
                if st_total > 0:
                    st_mix['fresh'] = round(st_input / st_total * 100, 1)
                    st_mix['read'] = round(st_cache_read / st_total * 100, 1)
                    st_mix['write'] = round(st_cache_write / st_total * 100, 1)
                    st_mix['out'] = round(st_output / st_total * 100, 1)

                sr_has_fail = any(
                    t['status_tone'] == 'fail' for t in steps if t['type'] == 'tool_call'
                )

                sub_rounds.append(
                    {
                        'sub_round_id': m_idx + 1,
                        'title': (m.content or '')[:80] or 'Assistant response',
                        'start_time': _to_local_time_hms(m.timestamp or ''),
                        'metric': _format_compact_token(st_output),
                        'token_input': st_input,
                        'token_cache_read': st_cache_read,
                        'token_cache_write': st_cache_write,
                        'token_output': st_output,
                        'token_total_raw': st_total,
                        'token_mix': st_mix,
                        'status': 'error' if sr_has_fail else 'ok',
                        'status_label': 'fail tool' if sr_has_fail else 'ok',
                        'status_tone': 'err' if sr_has_fail else 'ok',
                        'has_fail': sr_has_fail,
                        'is_open': sr_has_fail,
                        'request_attribution': sa_req_action,
                        'response_attribution': sa_rsp_action,
                        'request_attribution_id': sa_req_attr_id,
                        'response_attribution_id': sa_rsp_attr_id,
                        'context_payload_id': ctx_payload_id,
                        'response_payload_id': rsp_payload_id,
                        'steps': steps,
                    }
                )

        unmatched_tools = [
            tc
            for tc in display_tools
            if not tc.tool_use_id or tc.tool_use_id not in matched_tool_ids
        ]
        if unmatched_tools:
            unmatched_rows = []
            for u_idx, tc in enumerate(unmatched_tools, start=1):
                u_payload_id = f'sub-{sa_id}-unmatched-T{u_idx}-result' if tc.result else ''
                u_payload_title = f'Subagent · {tc.name} · Result'
                if tc.result:
                    command_fields = _build_tool_result_command_fields(tc.name, tc.parameters)
                    add_payload(
                        payload_id=u_payload_id,
                        kind='subagent.tool.result',
                        title=u_payload_title,
                        text=tc.result,
                        tool_name=tc.name,
                        tool_command=command_fields['command'],
                        tool_workdir=command_fields['workdir'],
                        tool_parameters=tc.parameters,
                        tool_status=f'exit {tc.exit_code}'
                        if getattr(tc, 'exit_code', None) is not None
                        else (getattr(tc, 'status', '') or 'ok'),
                    )
                unmatched_rows.append(
                    tool_vm(tc, f'sub-{sa_id}-UT{u_idx}', u_payload_id, u_payload_title)
                )

            if sub_rounds:
                sub_rounds[-1]['steps'].extend(unmatched_rows)
                if any(t['status_tone'] == 'fail' for t in unmatched_rows):
                    sub_rounds[-1]['is_open'] = True
                    sub_rounds[-1]['has_fail'] = True
                    sub_rounds[-1]['status'] = 'error'
                    sub_rounds[-1]['status_label'] = 'fail tool'
                    sub_rounds[-1]['status_tone'] = 'err'
            else:
                sub_rounds.append(
                    {
                        'sub_round_id': 1,
                        'title': (
                            f'{len(unmatched_tools)} tool '
                            f'call{"s" if len(unmatched_tools) != 1 else ""}'
                        ),
                        'metric': _format_compact_token(sa_output),
                        'token_input': 0,
                        'token_cache_read': 0,
                        'token_cache_write': 0,
                        'token_output': sa_output,
                        'token_total_raw': sa_output,
                        'token_mix': {'fresh': 0, 'read': 0, 'write': 0, 'out': 100}
                        if sa_output > 0
                        else {'fresh': 0, 'read': 0, 'write': 0, 'out': 0},
                        'status': 'failed' if sa_failed > 0 else 'ok',
                        'status_tone': 'err' if sa_failed > 0 else 'ok',
                        'is_open': any(t['status_tone'] == 'fail' for t in unmatched_rows),
                        'request_attribution': payload_action(
                            '',
                            'Req —',
                            'llm.request_attribution',
                            'Subagent request attribution unavailable',
                            'unavailable',
                        ),
                        'response_attribution': payload_action(
                            '',
                            'Resp —',
                            'llm.response_attribution',
                            'Subagent response attribution unavailable',
                            'unavailable',
                        ),
                        'steps': unmatched_rows,
                    }
                )

        if not sub_rounds and display_tools:
            sub_rounds.append(
                {
                    'sub_round_id': 1,
                    'title': (
                        f'{len(display_tools)} tool call{"s" if len(display_tools) > 1 else ""}'
                    ),
                    'metric': _format_compact_token(sa_output),
                    'token_input': 0,
                    'token_cache_read': 0,
                    'token_cache_write': 0,
                    'token_output': sa_output,
                    'token_total_raw': sa_output,
                    'token_mix': {'fresh': 0, 'read': 0, 'write': 0, 'out': 100}
                    if sa_output > 0
                    else {'fresh': 0, 'read': 0, 'write': 0, 'out': 0},
                    'status': 'failed' if sa_failed > 0 else 'ok',
                    'status_tone': 'err' if sa_failed > 0 else 'ok',
                    'is_open': False,
                    'request_attribution': payload_action(
                        '',
                        'Req —',
                        'llm.request_attribution',
                        'Subagent request attribution unavailable',
                        'unavailable',
                    ),
                    'response_attribution': payload_action(
                        '',
                        'Resp —',
                        'llm.response_attribution',
                        'Subagent response attribution unavailable',
                        'unavailable',
                    ),
                    'steps': [
                        {
                            'type': 'tool_step',
                            'kind': tc.name[:4].upper(),
                            'text': _shorten_path(
                                _build_tool_command_summary(tc.name, tc.parameters)
                            )[:80]
                            or tc.name,
                            'result': f'exit {tc.exit_code}' if tc.exit_code is not None else 'ok',
                        }
                        for tc in display_tools[:10]
                    ],
                }
            )

        subagent_lookup[sa_id] = {
            'name': sa_name,
            'agent_id': sa_id,
            'status_label': 'failed' if sa_failed > 0 else 'completed',
            'status_tone': 'err' if sa_failed > 0 else 'ok',
            'meta': (
                f'{len(display_tools)} tools, {_format_compact_token(sa_input + sa_output)} tokens'
            ),
            'has_open_round': any(sr.get('is_open') for sr in sub_rounds),
            'sub_rounds': sub_rounds,
        }

    # 说明:-- Trace rows --
    trace_rows = []
    global_main_call_num = 0
    sa_parent_map: dict[str, dict] = {}
    for run in subagent_runs:
        sa_id = run['summary']['agent_id']
        parent_tc = next(
            (tc for tc in tool_calls if _is_subagent_parent_tool(tc, sa_id)),
            None,
        )
        if parent_tc:
            parent_round_idx = 0
            for ri, rr in enumerate(rounds):
                if any(tc.tool_use_id == parent_tc.tool_use_id for tc in rr.tool_calls):
                    parent_round_idx = ri
                    break
            sa_parent_map[sa_id] = {
                'round_index': parent_round_idx,
                'parent_tool_use_id': parent_tc.tool_use_id,
            }

    for r_idx, r in enumerate(rounds):
        rid = r_idx + 1
        round_preview = build_round_preview(r)
        rb = r.token_breakdown()
        rb['input'] + rb['cache_read'] + rb['cache_write'] + rb['output']
        has_failed = any(tc.is_failed for tc in r.tool_calls)
        has_llm_err = r.llm_error_count > 0
        has_user_input = bool(r.user_msg.content)

        if has_failed or has_llm_err:
            status_key = 'failed'
            status_label = 'Failed'
            status_tone = 'fail'
        elif has_user_input:
            status_key = 'user'
            status_label = 'OK'
            status_tone = 'ok'
        else:
            status_key = 'ok'
            status_label = 'OK'
            status_tone = 'ok'

        start_time = _to_local_time_hms(r.user_msg.timestamp or r.assistant_msg.timestamp or '')
        if r.user_msg.content:
            preview_title = (r.user_msg.content or '')[:300]
        else:
            preview_title = (round_preview['preview_text'] or '')[:300]
        for _fw in [
            'Map',
            'Inspector',
            'Focus',
            'Open selected',
            'Calls',
            'Hotspots',
            'High token',
            'Jump input',
        ]:
            preview_title = preview_title.replace(_fw, '***')
        preview_subtitle = (
            f'{len(r.tool_calls)} tool{"s" if len(r.tool_calls) != 1 else ""}'
            if r.tool_calls
            else 'no tools'
        )

        total_fresh = 0
        total_cache_read = 0
        total_cache_write = 0
        total_output = 0
        for _ix in r.interactions:
            parts = _usage_parts_from_call(_ix)
            total_fresh += parts['fresh']
            total_cache_read += parts['cache_read']
            total_cache_write += parts['cache_write']
            total_output += parts['output']
        if not r.interactions:
            total_fresh = rb['input']
            total_cache_read = rb['cache_read']
            total_cache_write = rb['cache_write']
            total_output = rb['output']
        rt_sum = total_fresh + total_cache_read + total_cache_write + total_output
        token_total = _format_compact_token(rt_sum) if rt_sum > 0 else '—'

        all_tools = set()
        raw_tool_uses = 0
        for _ix in r.interactions:
            raw_tool_uses += count_raw_tool_uses(_ix)
            for _tc in getattr(_ix, 'tool_calls', []) or []:
                key = getattr(_tc, 'tool_use_id', '') or id(_tc)
                all_tools.add(key)
        for tc in r.tool_calls:
            key = getattr(tc, 'tool_use_id', '') or id(tc)
            all_tools.add(key)
        tool_total = max(len(all_tools), raw_tool_uses)
        tool_count_label = f'{tool_total} tools' if tool_total else '0 tools'

        token_mix = {'fresh': 0, 'read': 0, 'write': 0, 'out': 0}
        if rt_sum > 0:
            token_mix['fresh'] = round(total_fresh / rt_sum * 100, 1)
            token_mix['read'] = round(total_cache_read / rt_sum * 100, 1)
            token_mix['write'] = round(total_cache_write / rt_sum * 100, 1)
            token_mix['out'] = round(total_output / rt_sum * 100, 1)

        is_detail_active = not slim and (round_filter is None or r_idx in round_filter)
        if not is_detail_active:
            slim_global_call_start = global_main_call_num
            for _ix_skip in r.interactions:
                global_main_call_num += 1
            slim_has_subagent = any(_is_subagent_parent_tool(tc) for tc in r.tool_calls)
            slim_req_actions = [
                payload_action(
                    f'llm-R{rid}-IX{idx + 1}-request-attribution',
                    'Req partial',
                    'llm.request_attribution',
                    f'R{rid} · LLM Call #{slim_global_call_start + idx + 1} · Request Attribution',
                    'partial',
                )
                for idx, _ix in enumerate(r.interactions)
            ]
            slim_resp_actions = [
                payload_action(
                    f'llm-R{rid}-IX{idx + 1}-response-attribution',
                    'Resp partial',
                    'llm.response_attribution',
                    f'R{rid} · LLM Call #{slim_global_call_start + idx + 1} · Response Attribution',
                    'partial',
                )
                for idx, _ix in enumerate(r.interactions)
            ]
            trace_rows.append(
                {
                    'round_id': rid,
                    'round_label': f'R{rid}',
                    'status_key': status_key,
                    'status_label': status_label,
                    'status_tone': status_tone,
                    'preview_title': preview_title or f'Round {rid}',
                    'preview_subtitle': preview_subtitle,
                    'token_total': token_total,
                    'token_total_raw': rt_sum,
                    'token_mix': token_mix,
                    'token_input': total_fresh,
                    'token_cache_read': total_cache_read,
                    'token_cache_write': total_cache_write,
                    'token_output': total_output,
                    'llm_call_count': getattr(r, 'llm_call_count', 0) or len(r.interactions),
                    'tool_count': tool_total,
                    'tool_count_label': tool_count_label,
                    'has_user_input': bool(r.user_msg.content),
                    'has_subagent': slim_has_subagent,
                    'request_attribution': summarize_attribution_actions(
                        slim_req_actions, 'Req', 'llm.request_attribution'
                    ),
                    'response_attribution': summarize_attribution_actions(
                        slim_resp_actions, 'Resp', 'llm.response_attribution'
                    ),
                    'start_time': start_time,
                    'is_open': False,
                    'timeline_items': [],
                }
            )
            continue

        items = []

        if r.user_msg.content:
            user_payload_id = f'msg-R{rid}-user'
            add_payload(
                payload_id=user_payload_id,
                kind='message.user',
                title=f'R{rid} · User request',
                text=r.user_msg.content,
            )
            lang_label = ''
            first_line = r.user_msg.content.strip().split('\n')[0] if r.user_msg.content else ''
            if first_line.startswith('```'):
                lang_label = first_line.strip('`').strip()
            items.append(
                {
                    'type': 'user_message',
                    'title': 'User Message',
                    'text': (r.user_msg.content or '')[:300],
                    'language_label': lang_label,
                    'payload_id': user_payload_id,
                    'payload_title': f'R{rid} · User request',
                    'timestamp': _call_time_label(getattr(r.user_msg, 'timestamp', '') or ''),
                    'block_index': 1,
                }
            )

        round_has_subagent = False
        round_request_actions = []
        round_response_actions = []

        for ix_idx, ix in enumerate(r.interactions):
            global_main_call_num += 1
            iix = global_main_call_num
            call_ix = ix_idx + 1

            call_id = f'R{rid}-IX{iix}'

            ix_tools = []
            if hasattr(ix, 'tool_calls') and ix.tool_calls:
                for tc in ix.tool_calls:
                    if _is_subagent_parent_tool(tc) or not tc.subagent_id:
                        ix_tools.append(tc)

            tool_rows = []
            if ix_tools:
                for tc in ix_tools:
                    tc_global_idx = -1
                    for gi, gtc in enumerate(r.tool_calls):
                        if gtc is tc:
                            tc_global_idx = gi + 1
                            break
                    if tc_global_idx == -1:
                        tc_global_idx = len(batch_tools) + 1  # noqa: F821

                    tool_payload_id = f'tool-R{rid}-T{tc_global_idx}' if tc.result else ''
                    if tc.result:
                        command_fields = _build_tool_result_command_fields(
                            tc.name, tc.parameters
                        )
                        add_payload(
                            payload_id=tool_payload_id,
                            kind='tool.result',
                            title=f'R{rid} · {tc.name} · Result',
                            text=tc.result,
                            tool_name=tc.name,
                            tool_command=command_fields['command'],
                            tool_workdir=command_fields['workdir'],
                            tool_parameters=tc.parameters,
                            tool_status=f'exit {tc.exit_code}'
                            if getattr(tc, 'exit_code', None) is not None
                            else (getattr(tc, 'status', '') or 'ok'),
                        )

                    tool_rows.append(
                        tool_vm(
                            tc,
                            f'R{rid}-T{tc_global_idx}',
                            tool_payload_id,
                            f'R{rid} · {tc.name} · Result',
                        )
                    )

            context_payload_id = f'llm-R{rid}-IX{iix}-context'
            ix_tool_calls_for_llm = [
                tc
                for tc in (getattr(ix, 'tool_calls', []) or [])
                if _is_subagent_parent_tool(tc) or not getattr(tc, 'subagent_id', '')
            ]

            if ix.request_full:
                source_status = 'raw'
                ctx_norm_blocks = normalize_llm_content(ix.request_full)
                ctx_content_html = (
                    _render_context_content_blocks(ctx_norm_blocks) if ctx_norm_blocks else ''
                )
                add_payload(
                    payload_id=context_payload_id,
                    kind='llm.context',
                    title=f'R{rid} · LLM Call #{iix} · Context',
                    html=ctx_content_html,
                )
            else:
                source_status = 'reconstructed' if r.user_msg.content else 'diagnostic'
                ctx_blocks = []
                if r.user_msg.content:
                    ctx_blocks.append(
                        {
                            'kind': 'user_input',
                            'summary': (r.user_msg.content or '')[:120],
                        }
                    )
                for prev_ix_idx in range(ix_idx):
                    prev_ix = r.interactions[prev_ix_idx]
                    if hasattr(prev_ix, 'tool_calls') and prev_ix.tool_calls:
                        for tc in prev_ix.tool_calls:
                            if _is_subagent_parent_tool(tc) or not getattr(tc, 'subagent_id', ''):
                                tc_result = getattr(tc, 'result', '') or ''
                                ctx_blocks.append(
                                    {
                                        'kind': 'tool_result',
                                        'summary': f'{tc.name}: {(tc_result or "")[:80]}',
                                        'status_tone': 'fail'
                                        if getattr(tc, 'is_failed', False)
                                        else 'ok',
                                    }
                                )

                ctx_warning = ''
                if source_status == 'diagnostic':
                    ctx_warning = '上下文数据缺失;以下为诊断信息.'
                add_payload(
                    payload_id=context_payload_id,
                    kind='llm.context',
                    title=f'R{rid} · LLM Call #{iix} · Context',
                    text='',
                    warning=ctx_warning,
                    context_blocks=ctx_blocks,
                    source_status=source_status,
                    user_input=(r.user_msg.content or '')[:500] if r.user_msg.content else '',
                    preceding_tool_results=ctx_blocks,
                )

            response_payload_id = f'llm-R{rid}-IX{iix}-output'
            assistant_text_payload_id = f'llm-R{rid}-IX{iix}-assistant-text'

            if ix.response_full or ix.content_blocks:
                rsp_source_status = 'raw'
                ix_tool_calls_for_response = ix_tool_calls_for_llm
                content_blocks_html = _render_response_content_blocks(
                    content_blocks=ix.content_blocks,
                    response_text=ix.response_full if not ix.content_blocks else '',
                    tool_calls=ix_tool_calls_for_response if not ix.content_blocks else [],
                )

                rsp_blocks = []
                if ix.content_blocks:
                    for cb in ix.content_blocks:
                        cb_type = cb.get('type', '')
                        if cb_type == 'text':
                            rsp_blocks.append(
                                {
                                    'type': 'text',
                                    'size_label': _format_bytes(
                                        min(len(cb.get('content', '')), 10000)
                                    ),
                                }
                            )
                        elif cb_type == 'thinking':
                            rsp_blocks.append(
                                {
                                    'type': 'thinking',
                                    'size_label': _format_bytes(
                                        min(len(cb.get('content', '')), 10000)
                                    ),
                                }
                            )
                        elif cb_type == 'tool_use':
                            tc_params = cb.get('parameters', {}) or {}
                            tc_command_raw = (
                                tc_params.get('command', '')
                                or tc_params.get('file_path', '')
                                or tc_params.get('path', '')
                                or cb.get('name', 'tool')
                            )
                            tc_command = _shorten_path(str(tc_command_raw))[:100]
                            rsp_blocks.append(
                                {
                                    'type': 'tool_use',
                                    'name': cb.get('name', 'unknown')[:40],
                                    'tool_id': cb.get('id', '') or '',
                                    'command': tc_command,
                                }
                            )
                else:
                    if ix.response_full and ix.response_full.strip():
                        rsp_blocks.append(
                            {
                                'type': 'text',
                                'size_label': _format_bytes(min(len(ix.response_full), 10000)),
                            }
                        )
                    for tc in ix_tool_calls_for_response:
                        tc_params = getattr(tc, 'parameters', {}) or {}
                        tc_command_raw = (
                            tc_params.get('command', '')
                            or tc_params.get('file_path', '')
                            or tc_params.get('path', '')
                            or getattr(tc, 'name', 'tool')
                        )
                        tc_command = _shorten_path(str(tc_command_raw))[:100]
                        rsp_blocks.append(
                            {
                                'type': 'tool_use',
                                'name': getattr(tc, 'name', 'unknown')[:40],
                                'tool_id': getattr(tc, 'tool_use_id', '') or '',
                                'command': tc_command,
                            }
                        )

                block_count = len(rsp_blocks) if rsp_blocks else 1
                size_label = f'{block_count} content block{"s" if block_count != 1 else ""}'

                rsp_diagnostic = ''
                finish_r = getattr(ix, 'finish_reason', '') or getattr(ix, 'status', 'unknown')
                if finish_r and finish_r not in ('end_turn', 'stop', 'ok', 'tool_use', ''):
                    rsp_diagnostic = f'finish_reason: {finish_r}'

                add_payload(
                    payload_id=response_payload_id,
                    kind='llm.output',
                    title=f'R{rid} · LLM Call #{iix} · Response',
                    html=content_blocks_html,
                    size=size_label,
                    response_blocks=rsp_blocks,
                    response_diagnostics=rsp_diagnostic,
                    source_status=rsp_source_status,
                )
            else:
                rsp_source_status = 'diagnostic'
                rsp_blocks = []
                for tc in ix_tool_calls_for_llm:
                    tc_params = getattr(tc, 'parameters', {}) or {}
                    tc_command_raw = (
                        tc_params.get('command', '')
                        or tc_params.get('file_path', '')
                        or tc_params.get('path', '')
                        or getattr(tc, 'name', 'tool')
                    )
                    tc_command = _shorten_path(str(tc_command_raw))[:100]
                    rsp_blocks.append(
                        {
                            'type': 'tool_use',
                            'name': getattr(tc, 'name', 'unknown')[:40],
                            'tool_id': getattr(tc, 'tool_use_id', '') or '',
                            'command': tc_command,
                        }
                    )

                finish_r = getattr(ix, 'finish_reason', '') or getattr(ix, 'status', 'unknown')
                if rsp_blocks:
                    rsp_diagnostic = ''
                elif finish_r and finish_r not in ('tool_use',):
                    rsp_diagnostic = f'响应内容缺失;finish_reason: {finish_r}'
                elif finish_r == 'tool_use':
                    rsp_diagnostic = ''
                else:
                    rsp_diagnostic = '响应内容缺失'

                add_payload(
                    payload_id=response_payload_id,
                    kind='llm.output',
                    title=f'R{rid} · LLM Call #{iix} · Response',
                    text='',
                    warning=rsp_diagnostic,
                    response_blocks=rsp_blocks,
                    source_status=rsp_source_status,
                )

            assistant_blocks = assistant_text_blocks(ix.content_blocks)
            assistant_text_payload = assistant_text_from_blocks(
                ix.content_blocks,
                ix.response_full if not ix.content_blocks else '',
            )
            if assistant_blocks or assistant_text_payload:
                assistant_html = _render_response_content_blocks(
                    content_blocks=assistant_blocks,
                    response_text=assistant_text_payload if not assistant_blocks else '',
                    tool_calls=[],
                )
                assistant_response_blocks = []
                for block in assistant_blocks:
                    block_type = block.get('type', 'text')
                    content = block.get('content') or block.get('text') or ''
                    assistant_response_blocks.append(
                        {
                            'type': block_type,
                            'size_label': _format_bytes(min(len(str(content)), 10000)),
                        }
                    )
                if not assistant_response_blocks and assistant_text_payload:
                    assistant_response_blocks.append(
                        {
                            'type': 'text',
                            'size_label': _format_bytes(min(len(assistant_text_payload), 10000)),
                        }
                    )
                add_payload(
                    payload_id=assistant_text_payload_id,
                    kind='llm.output',
                    title=f'R{rid} · LLM Call #{iix} · Assistant Text',
                    html=assistant_html,
                    size='assistant text',
                    response_blocks=assistant_response_blocks,
                    source_status=rsp_source_status,
                )

            request_attribution_id = f'llm-R{rid}-IX{call_ix}-request-attribution'
            response_attribution_id = f'llm-R{rid}-IX{call_ix}-response-attribution'
            req_action = payload_action(
                request_attribution_id,
                'Req partial',
                'llm.request_attribution',
                f'R{rid} · LLM Call #{iix} · Request Attribution',
                'partial',
            )
            resp_action = payload_action(
                response_attribution_id,
                'Resp partial',
                'llm.response_attribution',
                f'R{rid} · LLM Call #{iix} · Response Attribution',
                'partial',
            )
            round_request_actions.append(req_action)
            round_response_actions.append(resp_action)

            if skip_attribution:
                add_payload(
                    payload_id=request_attribution_id,
                    kind='llm.request_attribution',
                    title=f'R{rid} · LLM Call #{iix} · Request Attribution',
                    text='',
                    warning='Attribution deferred — click button to load on demand.',
                )
                add_payload(
                    payload_id=response_attribution_id,
                    kind='llm.response_attribution',
                    title=f'R{rid} · LLM Call #{iix} · Response Attribution',
                    text='',
                    warning='Attribution deferred — click button to load on demand.',
                )
            else:
                try:
                    attrib_ctx = build_attribution_session_context(
                        session=session,
                        round_obj=r,
                        interaction_index=ix_idx,
                        interactions=r.interactions,
                        round_tool_calls=r.tool_calls,
                        all_messages=None,
                        all_tool_calls=tool_calls,
                        project_dir=session.project_key or None,
                        agent_name=session.agent,
                        all_llm_calls=llm_calls,
                    )
                    req_attr = build_llm_request_attribution(
                        agent=session.agent,
                        llm_call=ix,
                        round_obj=r,
                        session_summary=session,
                        session_context=attrib_ctx,
                    )
                    req_payload = request_attribution_to_payload(req_attr)
                    add_payload(
                        payload_id=request_attribution_id,
                        kind='llm.request_attribution',
                        title=f'R{rid} · LLM Call #{iix} · Request Attribution',
                        text='',
                        warning='Attribution data is embedded; for live data use API endpoint.',
                        **{'data': req_payload},
                    )
                    resp_attr = build_llm_response_attribution(
                        agent=session.agent,
                        llm_call=ix,
                        round_obj=r,
                        session_summary=session,
                        session_context=attrib_ctx,
                    )
                    resp_payload = response_attribution_to_payload(resp_attr)
                    add_payload(
                        payload_id=response_attribution_id,
                        kind='llm.response_attribution',
                        title=f'R{rid} · LLM Call #{iix} · Response Attribution',
                        text='',
                        warning='Attribution data is embedded; for live data use API endpoint.',
                        **{'data': resp_payload},
                    )
                except Exception:
                    logger.debug(
                        'Embedded attribution build failed for R%s-IX%s', rid, iix, exc_info=True
                    )
                    add_payload(
                        payload_id=request_attribution_id,
                        kind='llm.request_attribution',
                        title=f'R{rid} · LLM Call #{iix} · Request Attribution',
                        text='',
                        warning='Attribution data unavailable; use API endpoint.',
                    )
                    add_payload(
                        payload_id=response_attribution_id,
                        kind='llm.response_attribution',
                        title=f'R{rid} · LLM Call #{iix} · Response Attribution',
                        text='',
                        warning='Attribution data unavailable; use API endpoint.',
                    )

            items.extend(
                content_event_items(
                    ix.content_blocks if ix.content_blocks else [],
                    assistant_text_payload_id
                    if (assistant_blocks or assistant_text_payload)
                    else response_payload_id,
                    f'R{rid} · LLM Call #{iix} · Assistant Text',
                    ix.response_full if not ix.content_blocks else '',
                )
            )

            for row in tool_rows:
                items.append(row)

            for tc in ix_tool_calls_for_llm:
                sa_id = _subagent_id_from_tool(tc)
                if _is_subagent_parent_tool(tc, sa_id):
                    sa_info = subagent_lookup.get(sa_id)
                    if sa_info:
                        round_has_subagent = True
                        items.append(
                            {
                                'type': 'subagent',
                                'subagent_id': sa_id,
                                'name': sa_info['name'],
                                'status_label': sa_info['status_label'],
                                'status_tone': sa_info['status_tone'],
                                'meta': sa_info['meta'],
                                'has_open_round': sa_info.get('has_open_round', False),
                                'sub_rounds': sa_info['sub_rounds'],
                                'parent_call_id': call_id,
                                'parent_call_index': iix,
                            }
                        )

        if not items and r.tool_calls:
            for tc_idx, tc in enumerate(r.tool_calls):
                sa_id = _subagent_id_from_tool(tc)
                if _is_subagent_parent_tool(tc, sa_id):
                    sa_info = subagent_lookup.get(sa_id)
                    if sa_info:
                        items.append(
                            {
                                'type': 'subagent',
                                'subagent_id': sa_id,
                                'name': sa_info['name'],
                                'status_label': sa_info['status_label'],
                                'status_tone': sa_info['status_tone'],
                                'meta': sa_info['meta'],
                                'has_open_round': sa_info.get('has_open_round', False),
                                'sub_rounds': sa_info['sub_rounds'],
                            }
                        )
                    continue
                tool_payload_id = f'tool-R{rid}-T{tc_idx + 1}' if tc.result else ''
                if tc.result:
                    command_fields = _build_tool_result_command_fields(tc.name, tc.parameters)
                    add_payload(
                        payload_id=tool_payload_id,
                        kind='tool.result',
                        title=f'R{rid} · {tc.name} · Result',
                        text=tc.result,
                        tool_name=tc.name,
                        tool_command=command_fields['command'],
                        tool_workdir=command_fields['workdir'],
                        tool_parameters=tc.parameters,
                        tool_status=f'exit {tc.exit_code}'
                        if getattr(tc, 'exit_code', None) is not None
                        else (getattr(tc, 'status', '') or 'ok'),
                    )
                items.append(
                    tool_vm(
                        tc,
                        f'R{rid}-T{tc_idx + 1}',
                        tool_payload_id,
                        f'R{rid} · {tc.name} · Result',
                    )
                )

        trace_rows.append(
            {
                'round_id': rid,
                'round_label': f'R{rid}',
                'status_key': status_key,
                'status_label': status_label,
                'status_tone': status_tone,
                'preview_title': preview_title or f'Round {rid}',
                'preview_subtitle': preview_subtitle,
                'token_total': token_total,
                'token_total_raw': rt_sum,
                'token_mix': token_mix,
                'token_input': total_fresh,
                'token_cache_read': total_cache_read,
                'token_cache_write': total_cache_write,
                'token_output': total_output,
                'llm_call_count': getattr(r, 'llm_call_count', 0) or len(r.interactions),
                'tool_count': tool_total,
                'tool_count_label': tool_count_label,
                'has_user_input': bool(r.user_msg.content),
                'has_subagent': round_has_subagent,
                'request_attribution': summarize_attribution_actions(
                    round_request_actions, 'Req', 'llm.request_attribution'
                ),
                'response_attribution': summarize_attribution_actions(
                    round_response_actions, 'Resp', 'llm.response_attribution'
                ),
                'start_time': start_time,
                'is_open': False,
                'timeline_items': items,
            }
        )

    manual_input_count = sum(1 for r in rounds if r.user_msg and r.user_msg.content)
    subagent_count = len(subagent_runs)

    cache_write_pct = ''
    cwt = getattr(session, 'cache_write_tokens', 0) or session.cache_write_tokens
    if total_tokens > 0 and cwt:
        cache_write_pct = f'{cwt / total_tokens * 100:.1f}%'

    status_label = 'Completed'
    if session_anomalies.anomalies:
        status_label = 'Completed with issue signals'
    if total_failed > 0:
        status_label = 'Completed with issue signals'

    fresh_tokens = getattr(session, 'fresh_input_tokens', 0) or session.fresh_input_tokens
    cache_read_tokens = getattr(session, 'cache_read_tokens', 0) or session.cache_read_tokens
    cache_write_tokens = getattr(session, 'cache_write_tokens', 0) or session.cache_write_tokens
    output_tokens = session.output_tokens
    computed_total_tokens = fresh_tokens + cache_read_tokens + cache_write_tokens + output_tokens
    input_side_tokens = fresh_tokens + cache_read_tokens + cache_write_tokens

    round_fresh_values = [row.get('token_input', 0) for row in trace_rows]
    median_fresh = _median(round_fresh_values)
    fresh_spike_rounds = (
        sum(1 for value in round_fresh_values if value > median_fresh * 2)
        if median_fresh > 0
        else 0
    )
    low_cache_rounds = 0
    for row in trace_rows:
        row_input_side = (
            row.get('token_input', 0)
            + row.get('token_cache_read', 0)
            + row.get('token_cache_write', 0)
        )
        if (
            row_input_side
            and (row.get('token_cache_read', 0) / row_input_side) < LOW_CACHE_FRACTION_THRESHOLD
        ):
            low_cache_rounds += 1

    max_round_tokens = max(
        (int(row.get('token_total_raw', 0) or 0) for row in trace_rows),
        default=0,
    )
    for row in trace_rows:
        row_tokens = int(row.get('token_total_raw', 0) or 0)
        token_bar_pct = round(row_tokens / max_round_tokens * 100, 1) if max_round_tokens else 0
        token_gap_pct = round(max(100 - token_bar_pct, 0), 1)
        row['token_bar_pct'] = token_bar_pct
        row['token_gap_pct'] = token_gap_pct
        row['token_bar_label'] = (
            f'{_format_percent(token_bar_pct)} of max round tokens'
            if max_round_tokens
            else 'No round tokens'
        )
        row['token_bar_gap_label'] = (
            f'{_format_percent(token_gap_pct)} below max round tokens'
            if max_round_tokens
            else 'No round token gap'
        )
        row['token_bar_max'] = max_round_tokens

    main_llm_calls = _main_scope_llm_call_count(rounds, llm_calls)
    subagent_llm_calls = sum(1 for call in llm_calls if getattr(call, 'scope', '') == 'subagent')
    if not subagent_llm_calls:
        subagent_llm_calls = sum(
            1
            for run in subagent_runs
            for message in run.get('messages', [])
            if getattr(message, 'role', '') == 'assistant'
        )
    total_llm_calls = main_llm_calls + subagent_llm_calls
    assistant_turns = sum(
        1
        for r in rounds
        if r.assistant_msg and (r.assistant_msg.content or r.assistant_msg.content_blocks)
    )
    distinct_tools = len({getattr(tc, 'name', '') or 'tool' for tc in tool_calls})
    duration_seconds = float(getattr(session, 'duration_seconds', 0) or 0)
    process_seconds = float(getattr(session, 'model_execution_seconds', 0) or 0) + float(
        getattr(session, 'tool_execution_seconds', 0) or 0
    )
    waiting_seconds = max(duration_seconds - process_seconds, 0)
    payload_index = _build_payload_tab_index(
        rounds,
        tool_calls,
        subagent_runs,
        llm_calls,
        agent=session.agent,
    )
    diagnostics = _build_session_diagnostics(
        session,
        rounds,
        llm_calls,
        tool_calls,
        subagent_runs,
        trace_rows,
        session_anomalies,
        fresh_tokens,
        cache_read_tokens,
        cache_write_tokens,
        output_tokens,
        payload_index,
        payload_sources,
    )
    round_signal_map = diagnostics.get('round_signals', {})
    token_round_map = {
        token_row.get('round_id'): token_row for token_row in diagnostics.get('token_rounds', [])
    }
    for row in trace_rows:
        rid = row.get('round_id', 0)
        signal = round_signal_map.get(rid, {})
        token_row = token_round_map.get(rid, {})
        issue_count = len(signal.get('issues', []))
        row['has_failed_signal'] = bool(signal.get('failed')) or row.get('status_key') == 'failed'
        row['has_payload_gap'] = bool(signal.get('payload_gap'))
        row['has_attribution_gap'] = bool(signal.get('attribution_gap'))
        row['is_low_cache'] = bool(token_row.get('is_low_cache'))
        row['is_fresh_spike'] = bool(token_row.get('is_fresh_spike'))
        row['has_issues'] = bool(
            issue_count
            or row['has_failed_signal']
            or row['has_payload_gap']
            or row['has_attribution_gap']
        )
        row['issue_count'] = issue_count
        row['llm_call_count'] = row.get('llm_call_count') or (
            len(rounds[rid - 1].interactions) if rid and rid <= len(rounds) else 0
        )

    issue_summary = diagnostics.get('issue_summary', {})
    issue_links = []
    issue_link_counts: dict[tuple[int, str], int] = {}
    for issue in diagnostics.get('issues', []):
        if not issue.get('round_id'):
            continue
        key = (int(issue['round_id']), str(issue['label']))
        issue_link_counts[key] = issue_link_counts.get(key, 0) + 1
    seen_issue_links: set[tuple[int, str]] = set()
    for issue in diagnostics.get('issues', []):
        if not issue.get('round_id'):
            continue
        key = (int(issue['round_id']), str(issue['label']))
        if key in seen_issue_links:
            continue
        seen_issue_links.add(key)
        issue_links.append(
            {
                'round_id': issue['round_id'],
                'label': f'{issue["round_label"]} · {issue["label"]}',
                'tone': 'err' if issue.get('tone') == 'critical' else 'warn',
            }
        )
        if len(issue_links) >= ISSUE_LINK_LIMIT:
            break
    for link in issue_links:
        key = (int(link['round_id']), link['label'].split(' · ', 1)[-1])
        count = issue_link_counts.get(key, 1)
        if count > 1:
            link['label'] = f'{link["label"]} ×{count}'  # noqa: RUF001

    has_run_issues = bool(
        issue_summary.get('tool_failures')
        or issue_summary.get('llm_errors')
        or issue_summary.get('payload_gaps')
        or issue_summary.get('attribution_errors')
        or getattr(session_anomalies, 'anomalies', [])
    )
    status_label = 'Completed with issue signals' if has_run_issues else 'Completed'

    source_total = getattr(session, 'total_tokens', 0) or total_tokens
    token_total_matches = not source_total or source_total == computed_total_tokens
    token_total_note = ''
    if not token_total_matches:
        token_total_note = (
            f'component sum {_format_compact_token(computed_total_tokens)} '
            f'does not match Provider Raw Total {_format_compact_token(source_total)}'
        )

    model_seconds = float(getattr(session, 'model_execution_seconds', 0) or 0)
    tool_seconds = float(getattr(session, 'tool_execution_seconds', 0) or 0)

    return {
        'session_summary': {
            'agent_label': agent_name,
            'agent_key': session.agent,
            'title': session.title or 'Untitled',
            'model': session.model or 'unknown',
            'branch': session.git_branch or 'branch main',
            'date': started,
            'short_id': short_id,
            'session_id': session.session_id,
            'session_file_path': _session_file_path(session),
            'project_name': session.project_name if hasattr(session, 'project_name') else '',
            'status_label': status_label,
            'manual_input_count': manual_input_count,
            'subagent_count': subagent_count,
            'cache_write_pct': cache_write_pct,
        },
        'hero_metrics': {
            'run_health': status_label,
            'issue_rounds': str(diagnostics.get('issue_rounds', 0) or 0),
            'failed_tools': str(issue_summary.get('tool_failures', 0) or 0),
            'failed_tools_rate': _format_ratio_pct(
                issue_summary.get('tool_failures', 0) or 0, total_tools
            ),
            'failed_tools_tone': _ratio_tone(
                _ratio_value(issue_summary.get('tool_failures', 0) or 0, total_tools)
            ),
            'payload_gaps': str(issue_summary.get('payload_gaps', 0) or 0),
            'attribution_gaps': str(issue_summary.get('attribution_errors', 0) or 0),
            'tokens': _format_compact_token(computed_total_tokens),
            'tokens_note': token_total_note,
            'tokens_component_sum': _format_compact_token(computed_total_tokens),
            'fresh': _format_compact_token(fresh_tokens),
            'fresh_share': _format_ratio_pct(fresh_tokens, computed_total_tokens),
            'fresh_share_tone': _token_share_tone(
                _ratio_value(fresh_tokens, computed_total_tokens)
            ),
            'cache_read': _format_compact_token(cache_read_tokens),
            'cache_read_share': _format_ratio_pct(cache_read_tokens, computed_total_tokens),
            'cache_read_share_tone': _token_share_tone(
                _ratio_value(cache_read_tokens, computed_total_tokens)
            ),
            'cache_write': _format_compact_token(cache_write_tokens),
            'cache_write_share': _format_ratio_pct(cache_write_tokens, computed_total_tokens),
            'cache_write_share_tone': _token_share_tone(
                _ratio_value(cache_write_tokens, computed_total_tokens)
            ),
            'output': _format_compact_token(output_tokens),
            'output_share': _format_ratio_pct(output_tokens, computed_total_tokens),
            'output_share_tone': _token_share_tone(
                _ratio_value(output_tokens, computed_total_tokens)
            ),
            'cache_reuse': _format_ratio_pct(cache_read_tokens, input_side_tokens),
            'input_side_tokens': _format_compact_token(input_side_tokens),
            'fresh_spike_rounds': str(fresh_spike_rounds),
            'low_cache_rounds': str(low_cache_rounds),
            'rounds': str(total_rounds),
            'user_prompts': str(manual_input_count),
            'assistant_turns': str(assistant_turns or total_rounds),
            'subagent_runs': str(subagent_count),
            'tools': str(total_tools),
            'tool_calls': str(total_tools),
            'distinct_tools': str(distinct_tools),
            'failed': str(total_failed) if total_failed > 0 else '0',
            'failure_rate': _format_ratio_pct(total_failed, total_tools),
            'llm_calls': str(total_llm_calls),
            'workload': str(total_llm_calls),
            'main_llm_calls': str(main_llm_calls),
            'subagent_llm_calls': str(subagent_llm_calls),
            'avg_tokens_per_call': (
                _format_compact_token(computed_total_tokens // total_llm_calls)
                if total_llm_calls
                else 'N/A'
            ),
            'process_time': _format_duration_short(process_seconds),
            'active_time': _format_duration_short(process_seconds),
            'duration': _format_duration_short(duration_seconds),
            'waiting_time': _format_duration_short(waiting_seconds),
            'model_time': _format_duration_short(model_seconds) if model_seconds > 0 else 'N/A',
            'tool_time': _format_duration_short(tool_seconds) if tool_seconds > 0 else 'N/A',
            'updated': _to_local_time(getattr(session, 'ended_at', '') or '') or '—',
        },
        'issue_links': issue_links,
        'trace_rows': trace_rows,
        'diagnostics': diagnostics,
        'payload_index': payload_index,
        'payload_sources': payload_sources if not slim else [],
        '_slim': slim,
    }
