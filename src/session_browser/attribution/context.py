"""Build call-scoped attribution session context.

The attribution builder calls this module before scoring source units for one
LLM call. It collects only payload visible to that call: prior tool results,
transcript messages, available tools, local instructions, prompt files, MCP
metadata, and hydrated normalized artifacts. Returned dictionaries are consumed
by attribution code and may reuse an existing context mapping in place.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING

from session_browser.attribution.agents.claude_code_parts.claude_code_agent_tools import (
    resolve_claude_code_available_tools,
)
from session_browser.attribution.agents.claude_code_tool_schemas import (
    ALL_CLAUDE_CODE_TOOLS,
)
from session_browser.attribution.token_estimator import estimate_tokens_from_text
from session_browser.index.schema import _get_connection, ensure_session_artifacts_schema
from session_browser.normalized.agents.claude_code_parts.source_units import (
    hydrate_source_units as hydrate_claude_code_source_units,
)
from session_browser.normalized.agents.claude_code_parts.source_units import (
    source_units_to_candidates as claude_code_source_units_to_candidates,
)
from session_browser.normalized.agents.codex_parts.source_units import (
    hydrate_source_units as hydrate_codex_source_units,
)
from session_browser.normalized.agents.codex_parts.source_units import (
    source_units_to_candidates as codex_source_units_to_candidates,
)
from session_browser.normalized.artifacts import (
    NORMALIZED_SESSION_ARTIFACT_TYPE,
    read_normalized_session_artifact,
)

if TYPE_CHECKING:
    from session_browser.domain.models import (
        ConversationRound,
        LLMCall,
        SessionSummary,
        ToolCall,
    )

logger = logging.getLogger(__name__)

_TRUNCATE_CONTENT_PREVIEW = 200
_TRUNCATE_LOCAL_INSTRUCTIONS = 2048  # Only keep preview text; source_units are located elsewhere.

# Mask common secret-bearing values before exposing preview context.
_SENSITIVE_KEYS = frozenset(
    {
        'api_key',
        'apikey',
        'api-key',
        'token',
        'auth_token',
        'access_token',
        'refresh_token',
        'secret',
        'secret_key',
        'password',
        'passwd',
        'authorization',
        'bearer',
        'credential',
        'credentials',
        'env',
        'environment',
    }
)
_SENSITIVE_KEY_RE = re.compile(
    r'(?:"|\'|)([A-Za-z0-9_\-]*'
    + r'(?:api_key|apikey|api-key|token|secret|password|passwd|authorization|credential|bearer|env)'
    + r'[A-Za-z0-9_\-]*)\s*(?:"|\'|)?\s*(?::|=)\s*'
    r'("([^"]*)"|\'([^\']*)\'|([^\n,}]+))',
    re.IGNORECASE,
)


def _mask_sensitive_keys(text: str) -> str:
    """Mask secret-looking values before context preview leaves this module.

    Args:
        text: Raw payload text from local instructions, MCP metadata, or tool
            snippets that may include token-like key/value pairs.

    Returns:
        Text with known secret-bearing field values replaced by a mask. Empty
        input returns an empty string and raises no intentional exception.
    """
    if not text:
        return ''

    def _replacer(m: re.Match) -> str:
        """Render one regex match without exposing its captured value.

        Args:
            m: Sensitive key/value match produced by ``_SENSITIVE_KEY_RE``.

        Returns:
            Replacement text preserving the key and quote style while masking
            the value.
        """
        key_part = m.group(1)
        quote_open = m.group(2)[0] if m.group(2) else ''
        if quote_open in ('"', "'"):
            return f'{key_part}: {quote_open}***MASKED***{quote_open}'
        return f'{key_part}: ***MASKED***'

    return _SENSITIVE_KEY_RE.sub(_replacer, text)


def _truncate_preview(text: str, max_len: int = 200) -> str:
    """Trim long attribution payloads to a stable display preview.

    Args:
        text: Full instruction, message, or tool-result text.
        max_len: Maximum number of characters to keep before appending an
            ellipsis marker.

    Returns:
        Empty string for empty input, the original text when already short
        enough, or a truncated preview with a trailing ellipsis.
    """
    if not text:
        return ''
    if len(text) <= max_len:
        return text
    return text[:max_len] + '…'


def build_attribution_session_context(  # noqa: PLR0913 - Public builder receives parser payload pieces separately.
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
    """Build the context dictionary visible to one attribution LLM call.

    Args:
        session: Parsed session summary used for project path and artifact
            lookup; ``None`` disables session-backed hydration.
        round_obj: Conversation round that owns the target interaction and user
            message.
        interaction_index: Index of the current call within ``interactions`` or
            the round fallback list.
        interactions: Round-local LLM calls ordered as the agent emitted them.
        round_tool_calls: Round-local tool calls kept for API compatibility;
            the builder does not mutate or read this payload directly.
        all_messages: Optional transcript payload used to derive prior and full
            request messages.
        all_tool_calls: Optional session-wide tool calls for non-Claude tool
            name discovery.
        project_dir: Optional explicit project directory used for local
            instruction, prompt, and MCP metadata reads.
        agent_name: Agent identifier that selects Codex or Claude-specific
            context behavior.
        existing_context: Optional mapping to hydrate in place for callers that
            already attached partial context.
        all_llm_calls: Optional session-wide calls for tool schema and
            normalized-call ordering.
        subagent_type: Optional subagent identifier used for prompt and tool
            schema resolution.

    Returns:
        A context mapping containing prior messages, request messages,
        available tool metadata, local instruction previews, MCP names, and
        normalized call data when available. It may be ``existing_context`` when
        that mapping is provided.
    """
    preceding_tool_results: list[str] = []

    if interaction_index > 0:
        for ix in interactions[:interaction_index]:
            if hasattr(ix, 'tool_calls') and ix.tool_calls:
                for tc in ix.tool_calls:
                    if tc.result and not getattr(tc, 'subagent_id', ''):
                        preceding_tool_results.append(tc.result)

    current_ix = _resolve_current_interaction(round_obj, interactions, interaction_index)

    prior_messages = _build_prior_messages(
        all_messages,
        interaction_index,
        round_obj=round_obj,
        current_interaction=current_ix,
    )

    full_messages_array = _build_full_messages_array(
        all_messages,
        interaction_index,
        round_obj,
        interactions,
    )

    resolved_project_dir = _resolve_project_dir(session, project_dir)

    available_tool_context = _build_available_tool_context(
        all_tool_calls=all_tool_calls,
        agent_name=agent_name,
        llm_calls=all_llm_calls,
        project_dir=resolved_project_dir,
        session_file=getattr(session, 'file_path', '') if session else '',
        subagent_type=subagent_type,
        call_timestamp=getattr(current_ix, 'timestamp', '') if current_ix else '',
    )

    local_instructions = ''
    agent_prompt_file = ''
    subagent_prompt = ''
    system_reminder_content = ''
    mcp_tools: list[str] = []
    mcp_servers: list[str] = []

    if resolved_project_dir:
        project_path = Path(resolved_project_dir)
        local_instructions = _read_local_instructions(project_path, agent_name)
        agent_prompt_file, subagent_prompt = _read_agent_prompt(
            project_path,
            agent_name,
            subagent_type=subagent_type,
        )
        mcp_tools, mcp_servers = _read_mcp_metadata(project_path)

    if not system_reminder_content and all_messages:
        system_reminder_content = _extract_system_reminder(all_messages)

    base = {
        'interaction_index': interaction_index,
        'preceding_tool_results': preceding_tool_results,
        'prior_messages': prior_messages,
        'full_messages_array': full_messages_array,
        'available_tools': available_tool_context['available_tools'],
        'available_tools_source': available_tool_context.get('available_tools_source', ''),
        'available_tools_agent_name': available_tool_context.get('available_tools_agent_name', ''),
        'available_tools_definition_path': available_tool_context.get(
            'available_tools_definition_path', ''
        ),
        'available_tools_reason': available_tool_context.get('available_tools_reason', ''),
        'local_instructions': local_instructions,
        'system_reminder_content': system_reminder_content,
        'agent_prompt_file': agent_prompt_file,
        'subagent_prompt': subagent_prompt,
        'mcp_tools': mcp_tools,
        'mcp_servers': mcp_servers,
    }
    normalized_call = _load_normalized_call_for_context(
        session=session,
        agent_name=agent_name,
        current_interaction=current_ix,
        interaction_index=interaction_index,
        interactions=interactions,
        all_llm_calls=all_llm_calls,
    )
    if normalized_call:
        base['normalized_call'] = normalized_call

    if existing_context:
        for k, v in base.items():
            if v or k in (
                'prior_messages',
                'full_messages_array',
                'available_tools',
                'available_tools_source',
                'available_tools_agent_name',
                'available_tools_definition_path',
                'available_tools_reason',
                'mcp_tools',
                'mcp_servers',
            ):
                existing_context[k] = v
        return existing_context

    return base


def _load_normalized_call_for_context(  # noqa: PLR0913 - Mirrors caller payload without a new wrapper object.
    *,
    session: SessionSummary | None,
    agent_name: str | None,
    current_interaction: LLMCall | None,
    interaction_index: int,
    interactions: list[LLMCall],
    all_llm_calls: list[LLMCall] | None,
) -> dict:
    """Load and hydrate normalized call data for migrated agents.

    Args:
        session: Session summary used to derive the artifact session key.
        agent_name: Agent override from the parser pipeline.
        current_interaction: Current LLM call selected for attribution.
        interaction_index: Round-local fallback index for calls without stable
            identifiers.
        interactions: Round-local interactions used when a session-wide list is
            unavailable.
        all_llm_calls: Optional session-wide ordering for main and subagent
            scopes.

    Returns:
        Hydrated normalized call dictionary, or an empty dictionary when the
        agent is unsupported, no artifact exists, or lookup fails. Artifact
        read failures are logged at debug level and otherwise swallowed.
    """
    agent = str(agent_name or getattr(session, 'agent', '') or '')
    if agent not in {'codex', 'claude_code', 'qoder'} or current_interaction is None:
        return {}
    session_key = _session_key_for_artifact(session, agent)
    if not session_key:
        return {}
    try:
        normalized = _read_normalized_artifact_for_session_key(session_key)
    except Exception as exc:  # pragma: no cover - 防御性日志
        logger.debug(
            'normalized artifact hydration failed for %s: %s', session_key, exc, exc_info=True
        )
        return {}
    normalized_call = _find_normalized_call_for_interaction(
        normalized,
        current_interaction=current_interaction,
        interaction_index=interaction_index,
        interactions=interactions,
        all_llm_calls=all_llm_calls,
    )
    return _hydrate_normalized_call(normalized, normalized_call)


def _session_key_for_artifact(session: SessionSummary | None, agent: str) -> str:
    """Derive the normalized artifact session key for one session.

    Args:
        session: Session summary that may expose ``session_key`` or
            ``session_id``.
        agent: Agent name used as the prefix when only ``session_id`` exists.

    Returns:
        Existing session key, synthesized ``agent:session_id`` key, or an empty
        string when the artifact cannot be addressed.
    """
    if session is None:
        return ''
    session_key = str(getattr(session, 'session_key', '') or '')
    if session_key:
        return session_key
    session_id = str(getattr(session, 'session_id', '') or '')
    return f'{agent}:{session_id}' if agent and session_id else ''


def _read_normalized_artifact_for_session_key(session_key: str) -> dict:
    """Read the normalized artifact registered for a session key.

    Args:
        session_key: Artifact owner key produced by ``_session_key_for_artifact``.

    Returns:
        Parsed normalized artifact dictionary, or an empty dictionary when no
        artifact row exists. The function opens and closes the index database
        connection as its only side effect.
    """
    conn = _get_connection()
    try:
        ensure_session_artifacts_schema(conn)
        row = conn.execute(
            """
            SELECT path FROM session_artifacts
            WHERE session_key = ? AND artifact_type = ?
            """,
            (session_key, NORMALIZED_SESSION_ARTIFACT_TYPE),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return {}
    path = str(row['path'] if hasattr(row, 'keys') else row[0])
    return read_normalized_session_artifact(path)


def _find_normalized_call_for_interaction(
    normalized: dict,
    *,
    current_interaction: LLMCall,
    interaction_index: int,
    interactions: list[LLMCall],
    all_llm_calls: list[LLMCall] | None,
) -> dict:
    """Find the normalized call matching the current interaction.

    Args:
        normalized: Parsed artifact containing a ``calls`` array.
        current_interaction: LLM call being attributed.
        interaction_index: Round-local fallback index.
        interactions: Round-local calls used when no session-wide ordering is
            available.
        all_llm_calls: Optional full call list used to compute the current
            ordinal within main or subagent scope.

    Returns:
        Matching normalized call dictionary. It first uses stable call IDs,
        then the ordinal within the same scope, then legacy round/index
        fallbacks; an empty dictionary means no match.
    """
    calls = normalized.get('calls') if isinstance(normalized, dict) else []
    if not isinstance(calls, list) or not calls:
        return {}

    call_id = str(getattr(current_interaction, 'id', '') or '')
    if call_id and not call_id.startswith('synthetic-'):
        for call in calls:
            if isinstance(call, dict) and str(call.get('call_id') or '') == call_id:
                return call

    scope = str(getattr(current_interaction, 'scope', '') or 'main')
    subagent_id = str(getattr(current_interaction, 'subagent_id', '') or '')
    candidates = [
        call
        for call in calls
        if isinstance(call, dict)
        and str(call.get('scope') or 'main') == scope
        and (scope != 'subagent' or str(call.get('subagent_id') or '') == subagent_id)
    ]
    if not candidates:
        return {}

    ordinal = _interaction_ordinal_in_scope(
        current_interaction=current_interaction,
        all_llm_calls=all_llm_calls or interactions,
        scope=scope,
        subagent_id=subagent_id,
    )
    if 0 <= ordinal < len(candidates):
        return candidates[ordinal]

    if scope == 'main':
        try:
            round_index = int(getattr(current_interaction, 'round_index', -1))
        except (TypeError, ValueError):
            round_index = -1
        if 0 <= round_index < len(candidates):
            return candidates[round_index]

    return candidates[interaction_index] if 0 <= interaction_index < len(candidates) else {}


def _hydrate_normalized_call(normalized: dict, call: dict) -> dict:
    """Expand compact source-unit references into legacy call payloads.

    Args:
        normalized: Artifact containing the source unit catalog and optional
            reference sequences.
        call: Normalized call dictionary selected for the current interaction.

    Returns:
        The original call when it already carries ``source_units`` or cannot be
        hydrated, otherwise a shallow copy with hydrated ``source_units`` and
        derived ``attribution_candidates``.
    """
    if not isinstance(call, dict) or not call:
        return {}
    if call.get('source_units'):
        return call
    ranges = call.get('source_unit_ref_ranges')
    catalog = normalized.get('source_unit_catalog') if isinstance(normalized, dict) else None
    sequences = normalized.get('source_unit_sequences') if isinstance(normalized, dict) else None
    if not isinstance(ranges, list) or not isinstance(catalog, dict):
        return call

    refs: list[str] = []
    for item in ranges:
        if not isinstance(item, dict):
            continue
        sequence_name = str(item.get('sequence') or '')
        if sequence_name and isinstance(sequences, dict):
            sequence = sequences.get(sequence_name)
            if isinstance(sequence, list):
                start = _int_or_zero(item.get('start'))
                end = _int_or_zero(item.get('end'))
                refs.extend(str(ref) for ref in sequence[start:end])
        item_refs = item.get('refs')
        if isinstance(item_refs, list):
            refs.extend(str(ref) for ref in item_refs)
    catalog_units = [
        catalog[ref] for ref in refs if ref in catalog and isinstance(catalog.get(ref), dict)
    ]
    if not catalog_units:
        return call
    hydrate_source_units, source_units_to_candidates = _source_unit_hydrators(normalized)

    hydrated = dict(call)
    source_units = hydrate_source_units(str(call.get('call_id') or ''), catalog_units)
    hydrated['source_units'] = source_units
    if not isinstance(hydrated.get('attribution_candidates'), dict):
        hydrated['attribution_candidates'] = source_units_to_candidates(source_units)
    return hydrated


SourceUnitHydrator = Callable[[str, list[dict]], list[dict]]
SourceUnitCandidateBuilder = Callable[[list[dict]], dict]


def _source_unit_hydrators(
    normalized: dict,
) -> tuple[SourceUnitHydrator, SourceUnitCandidateBuilder]:
    """Select source-unit hydration helpers for the artifact agent.

    Args:
        normalized: Parsed normalized artifact whose ``agent`` field selects the
            implementation.

    Returns:
        A pair of callables: one hydrates catalog units for a call ID and the
        other converts hydrated units to attribution candidates. The default is
        the Codex implementation for unknown agents.
    """
    agent = str(normalized.get('agent') or '') if isinstance(normalized, dict) else ''
    if agent == 'claude_code':
        return hydrate_claude_code_source_units, claude_code_source_units_to_candidates

    return hydrate_codex_source_units, codex_source_units_to_candidates


def _int_or_zero(value: object) -> int:
    """Convert a range bound to a non-negative integer.

    Args:
        value: Raw ``start`` or ``end`` value from normalized source-unit range
            metadata.

    Returns:
        ``max(0, int(value))`` when conversion succeeds, otherwise ``0``. Invalid
        payloads are treated as empty ranges and do not raise.
    """
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _interaction_ordinal_in_scope(
    *,
    current_interaction: LLMCall,
    all_llm_calls: list[LLMCall] | None,
    scope: str,
    subagent_id: str,
) -> int:
    """Compute a call's ordinal inside one attribution scope.

    Args:
        current_interaction: LLM call being matched to a normalized artifact.
        all_llm_calls: Ordered calls from the whole session, or ``None`` when
            unavailable.
        scope: Scope name such as ``main`` or ``subagent``.
        subagent_id: Subagent identifier required when ``scope`` is
            ``subagent``.

    Returns:
        Zero-based position among calls in the same scope, or ``-1`` when the
        interaction cannot be matched.
    """
    if not all_llm_calls:
        return -1
    scoped: list[LLMCall] = []
    for ix in all_llm_calls:
        if str(getattr(ix, 'scope', '') or 'main') != scope:
            continue
        if scope == 'subagent' and str(getattr(ix, 'subagent_id', '') or '') != subagent_id:
            continue
        scoped.append(ix)
    for idx, ix in enumerate(scoped):
        if ix is current_interaction:
            return idx
        if getattr(ix, 'id', None) and getattr(ix, 'id', None) == getattr(
            current_interaction, 'id', None
        ):
            return idx
    return -1


def _resolve_project_dir(session: SessionSummary | None, project_dir: str | None) -> str:
    """Resolve a readable project directory for context side reads.

    Args:
        session: Session summary that may expose ``cwd`` or ``project_key``.
        project_dir: Explicit path from the caller, preferred when it exists.

    Returns:
        First candidate that exists on disk, falling back to the first provided
        candidate string. Invalid paths are ignored without raising.
    """
    candidates: list[str] = []
    if project_dir:
        candidates.append(str(project_dir))
    if session is not None:
        cwd = getattr(session, 'cwd', '') or ''
        project_key = getattr(session, 'project_key', '') or ''
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

    return candidates[0] if candidates else ''


def _build_prior_messages(
    all_messages: list[object] | None,
    interaction_index: int | None = None,
    *,
    round_obj: ConversationRound | None = None,
    current_interaction: LLMCall | None = None,
) -> list[dict]:
    """Build transcript messages visible before the current LLM call.

    Args:
        all_messages: Session transcript entries as dictionaries or model
            objects.
        interaction_index: Current call index kept for legacy callers; ordering
            is derived from IDs and timestamps.
        round_obj: Round containing the current user message so the active user
            payload can be excluded.
        current_interaction: Current call whose assistant response and later
            messages must not be included.

    Returns:
        List of prior message dictionaries with full content, preview content,
        timestamp, call ID, and token estimate fields. The source transcript is
        not mutated.
    """
    if not all_messages:
        return []

    current_call_id = getattr(current_interaction, 'id', '') if current_interaction else ''
    current_ts = getattr(current_interaction, 'timestamp', '') if current_interaction else ''
    current_user = getattr(round_obj, 'user_msg', None) if round_obj is not None else None
    current_user_content = getattr(current_user, 'content', '') if current_user else ''
    current_user_ts = getattr(current_user, 'timestamp', '') if current_user else ''

    result = []
    for msg in all_messages:
        role = ''
        content = ''
        msg_ts = ''
        msg_call_id = ''
        if isinstance(msg, dict):
            role = msg.get('role', '')
            content = msg.get('content', '')
            msg_ts = msg.get('timestamp', '')
            msg_call_id = msg.get('llm_call_id', '') or msg.get('id', '')
        elif hasattr(msg, 'role'):
            role = getattr(msg, 'role', '')
            content = getattr(msg, 'content', '') or ''
            msg_ts = getattr(msg, 'timestamp', '') or ''
            msg_call_id = getattr(msg, 'llm_call_id', '') or ''

        if not role:
            continue
        if current_call_id and role == 'assistant' and msg_call_id == current_call_id:
            break
        if current_ts and msg_ts and msg_ts >= current_ts:
            break

        content_str = str(content) if content else ''
        if (
            role == 'user'
            and current_user_content
            and content_str == current_user_content
            and (not current_user_ts or msg_ts == current_user_ts)
        ):
            continue
        preview = content_str[:_TRUNCATE_CONTENT_PREVIEW]
        token_estimate = max(1, len(content_str) // 4) if content_str else 0

        result.append(
            {
                'role': role,
                'content': content_str,
                'full_content': content_str,
                'content_preview': preview,
                'content_token_estimate': token_estimate,
                'timestamp': msg_ts,
                'llm_call_id': msg_call_id,
            }
        )

    return result


def _build_full_messages_array(
    all_messages: list[object] | None,
    interaction_index: int,
    round_obj: ConversationRound,
    interactions: list[LLMCall],
) -> list[dict]:
    """Build request-shaped messages for the current attribution call.

    Args:
        all_messages: Transcript entries that may contain ``request_full`` and
            assistant tool-use data.
        interaction_index: Current call index within ``interactions``.
        round_obj: Round fallback used when ``interactions`` is incomplete.
        interactions: Ordered LLM calls from the round.

    Returns:
        Anthropic-style message entries visible to the current request. The
        current assistant output is excluded; subagent calls fall back to their
        call-scoped ``request_full`` when parent transcripts cannot match them.
    """
    current_ix = _resolve_current_interaction(round_obj, interactions, interaction_index)
    current_call_id = getattr(current_ix, 'id', '') if current_ix else ''
    current_request_full = getattr(current_ix, 'request_full', '') if current_ix else ''

    if not all_messages:
        return _messages_array_from_request_full(current_request_full)

    candidate: list[dict] = []
    msg_index = 0
    found_current = False
    saw_request_full = False

    for msg in all_messages:
        role = _message_field(msg, 'role', '')
        if role != 'assistant':
            continue

        msg_call_id = _message_field(msg, 'llm_call_id', '') or _message_field(msg, 'id', '')
        is_current = bool(current_call_id and msg_call_id == current_call_id)
        request_full = _message_field(msg, 'request_full', '')
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

    # Subagent attribution often receives a parent transcript without the subagent call id.
    # Use call-scoped request_full so the parent transcript is not counted for this call.
    if current_call_id and current_request_full:
        return _messages_array_from_request_full(current_request_full)

    # When request_full is missing, build messages from transcript and still stop
    # before the current assistant if the call id can be matched.
    if not saw_request_full:
        return _build_full_messages_array_from_transcript(all_messages, current_call_id)

    return candidate


def _resolve_current_interaction(
    round_obj: ConversationRound, interactions: list[LLMCall], interaction_index: int
) -> LLMCall | None:
    """Resolve the current interaction from explicit or round-local lists.

    Args:
        round_obj: Conversation round that may carry fallback interactions.
        interactions: Preferred list passed by the parser.
        interaction_index: Target position in either list.

    Returns:
        Matching ``LLMCall`` when the index is valid, otherwise ``None``.
    """
    if interactions and 0 <= interaction_index < len(interactions):
        return interactions[interaction_index]
    round_interactions = getattr(round_obj, 'interactions', None) or []
    if round_interactions and 0 <= interaction_index < len(round_interactions):
        return round_interactions[interaction_index]
    return None


def _message_field(
    msg: Mapping[str, object] | object, field_name: str, default: object = ''
) -> object:
    """Read one field from dict-like or attribute-based transcript entries.

    Args:
        msg: Transcript entry represented as a mapping or model object.
        field_name: Field or attribute name to read.
        default: Value returned when the field is absent.

    Returns:
        Field value from the mapping or object, or ``default``.
    """
    if isinstance(msg, dict):
        return msg.get(field_name, default)
    return getattr(msg, field_name, default)


def _messages_array_from_request_full(request_full: str) -> list[dict]:
    """Parse a raw request payload into attribution message entries.

    Args:
        request_full: Raw request text captured on the current LLM call.

    Returns:
        List of user/tool-result entries produced from ``request_full``. Empty
        input returns an empty list.
    """
    result: list[dict] = []
    _append_request_full_entries(result, request_full or '', 0)
    return result


def _append_request_full_entries(
    messages_array: list[dict], request_full: str, msg_index: int
) -> tuple[int, bool]:
    """Append request text or tool-result blocks to a messages array.

    Args:
        messages_array: Mutable output list receiving message dictionaries.
        request_full: Raw request payload, possibly containing tool result
            sections.
        msg_index: Next message index to assign.

    Returns:
        Tuple of the next message index and whether any entry was appended. The
        only side effect is appending to ``messages_array``.
    """
    text = (request_full or '').strip()
    if not text:
        return msg_index, False

    parts = [p.strip() for p in text.split('\n\n') if p.strip()]
    has_tool_result = any(p.startswith('Tool result for ') for p in parts)
    if not has_tool_result:
        parts = [text]

    appended = False
    for part in parts:
        content_type = 'user_text'
        tool_use_id = ''
        tool_name = ''
        payload_text = part

        if part.startswith('Tool result for '):
            content_type = 'tool_result'
            tr_match = re.match(r'Tool result for (\S+):', part)
            tool_use_id = tr_match.group(1) if tr_match else ''
            lines = part.split('\n', 1)
            payload_text = lines[1] if len(lines) > 1 else part
            tool_name = _extract_tool_name_from_result(payload_text)

        payload_text = payload_text.strip()
        if not payload_text:
            continue

        token_est = estimate_tokens_from_text(payload_text)
        messages_array.append(
            {
                'role': 'user',
                'content_type': content_type,
                'content': payload_text,
                'full_content': payload_text,
                'content_preview': payload_text[:_TRUNCATE_CONTENT_PREVIEW],
                'content_token_estimate': token_est,
                'message_index': msg_index,
                'has_full_content': True,
                'tool_name': tool_name,
                'tool_use_id': tool_use_id,
            }
        )
        msg_index += 1
        appended = True

    return msg_index, appended


def _append_assistant_message_entries(
    messages_array: list[dict], msg: Mapping[str, object] | object, msg_index: int
) -> int:
    """Append assistant text and tool-use entries from one transcript message.

    Args:
        messages_array: Mutable output list receiving message dictionaries.
        msg: Assistant transcript entry as a mapping or model object.
        msg_index: Next message index to assign.

    Returns:
        Next message index after appended assistant text and unique tool-use
        entries. The source message is not mutated.
    """
    content = _message_field(msg, 'content', '') or ''
    content_str = str(content) if content else ''
    if content_str.strip():
        token_est = estimate_tokens_from_text(content_str)
        messages_array.append(
            {
                'role': 'assistant',
                'content_type': 'assistant_text',
                'content': content_str,
                'full_content': content_str,
                'content_preview': content_str[:_TRUNCATE_CONTENT_PREVIEW],
                'content_token_estimate': token_est,
                'message_index': msg_index,
                'has_full_content': True,
                'tool_name': '',
                'tool_use_id': '',
            }
        )
        msg_index += 1

    seen_tuids_in_msg = set()
    tool_calls = _message_field(msg, 'tool_calls', []) or []
    for tc in tool_calls:
        if isinstance(tc, dict):
            tuid = tc.get('id', '')
            tname = tc.get('name', 'unknown')
            tparams = tc.get('parameters', {})
        elif hasattr(tc, 'tool_use_id'):
            tuid = getattr(tc, 'tool_use_id', '')
            tname = getattr(tc, 'name', 'unknown')
            tparams = getattr(tc, 'parameters', {})
        else:
            continue

        if tuid and tuid not in seen_tuids_in_msg:
            seen_tuids_in_msg.add(tuid)
            params_str = json.dumps(tparams, ensure_ascii=False) if tparams else ''
            tool_use_text = f'{tname}({params_str})' if params_str else tname
            token_est = estimate_tokens_from_text(tool_use_text)
            messages_array.append(
                {
                    'role': 'assistant',
                    'content_type': 'tool_use',
                    'content': tool_use_text,
                    'full_content': tool_use_text,
                    'content_preview': tool_use_text[:_TRUNCATE_CONTENT_PREVIEW],
                    'content_token_estimate': token_est,
                    'message_index': msg_index,
                    'has_full_content': True,
                    'tool_name': tname,
                    'tool_use_id': tuid,
                }
            )
            msg_index += 1

    return msg_index


def _build_full_messages_array_from_transcript(
    all_messages: list[object] | None, current_call_id: str = ''
) -> list[dict]:
    """Build request messages from transcript when request payloads are absent.

    Args:
        all_messages: Transcript entries from the session.
        current_call_id: Optional current assistant call ID; matching entries
            stop the scan before current output is included.

    Returns:
        Message dictionaries derived from user content plus prior assistant text
        and tool-use entries.
    """
    if not all_messages:
        return []

    messages_array: list[dict] = []
    msg_index = 0
    for msg in all_messages:
        role = _message_field(msg, 'role', '')
        if not role:
            continue
        if role == 'assistant':
            msg_call_id = _message_field(msg, 'llm_call_id', '') or _message_field(msg, 'id', '')
            if current_call_id and msg_call_id == current_call_id:
                break
            msg_index = _append_assistant_message_entries(messages_array, msg, msg_index)
            continue

        content = _message_field(msg, 'content', '') or ''
        content_str = str(content) if content else ''
        if content_str.strip():
            msg_index, _ = _append_request_full_entries(messages_array, content_str, msg_index)

    return messages_array


def _extract_tool_name_from_result(result_text: str) -> str:
    """Infer a tool name from a serialized tool-result payload.

    Args:
        result_text: Tool result text captured in ``request_full``.

    Returns:
        Parsed tool name from common headings or prefixes, ``unknown`` for
        empty input, or the first token truncated to thirty characters.
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


def _build_available_tool_context(  # noqa: PLR0913 - Collects independent tool-resolution hints.
    *,
    all_tool_calls: list | None,
    agent_name: str | None = None,
    llm_calls: list | None = None,
    project_dir: str | None = None,
    session_file: str | None = None,
    subagent_type: str | None = None,
    call_timestamp: str | None = None,
) -> dict:
    """Build available-tool context and provenance metadata.

    Args:
        all_tool_calls: Optional session-wide tool calls used for fallback name
            discovery.
        agent_name: Agent identifier selecting Claude Code or generic behavior.
        llm_calls: Optional LLM calls whose raw request-side tool schema payloads
            can expose available tool names.
        project_dir: Project directory for Claude Code tool definition lookup.
        session_file: Session file path for timestamped Claude Code resolution.
        subagent_type: Optional subagent type for narrowed Claude Code tools.
        call_timestamp: Current call timestamp for time-aware tool lookup.

    Returns:
        Dictionary with ``available_tools`` plus source, agent, definition path,
        and reason fields. It performs read-only filesystem lookup for Claude
        Code metadata when needed.
    """
    if agent_name == 'claude_code':
        resolved = resolve_claude_code_available_tools(
            project_dir=project_dir,
            session_file=session_file,
            subagent_type=subagent_type,
            call_timestamp=call_timestamp,
        )
        return {
            'available_tools': resolved.tools,
            'available_tools_source': resolved.source,
            'available_tools_agent_name': resolved.agent_name,
            'available_tools_definition_path': resolved.definition_path,
            'available_tools_reason': resolved.reason,
        }

    return {
        'available_tools': _build_available_tools(
            all_tool_calls=all_tool_calls,
            agent_name=agent_name,
            llm_calls=llm_calls,
            project_dir=project_dir,
        ),
        'available_tools_source': '',
        'available_tools_agent_name': '',
        'available_tools_definition_path': '',
        'available_tools_reason': '',
    }


def _build_available_tools(  # noqa: PLR0912 - Ordered fallbacks preserve legacy tool discovery.
    all_tool_calls: list | None,
    agent_name: str | None = None,
    llm_calls: list | None = None,
    project_dir: str | None = None,
) -> list[str]:
    """Collect request-side available tool names for attribution context.

    Args:
        all_tool_calls: Parsed tool calls used as a fallback source of names.
        agent_name: Agent identifier; Claude Code uses its definition resolver
            and Codex defaults to no built-in tool list.
        llm_calls: LLM calls whose ``tool_calls_raw`` may contain request-side
            schema names.
        project_dir: Project directory passed to the Claude Code resolver.

    Returns:
        Sorted tool names from request-side schema or parsed tool calls, Claude
        Code resolved tools, an empty Codex list, or the legacy Claude Code
        default schema list.
    """
    if agent_name == 'claude_code':
        resolved = resolve_claude_code_available_tools(
            project_dir=project_dir,
        )
        return resolved.tools

    if llm_calls:
        all_tools_from_llm: set[str] = set()
        for lc in llm_calls:
            raw = getattr(lc, 'tool_calls_raw', '') or ''
            if not raw:
                continue
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    for item in parsed:
                        if isinstance(item, dict):
                            tname = item.get('name', '')
                            if tname:
                                all_tools_from_llm.add(tname)
            except (json.JSONDecodeError, TypeError):
                pass
        if all_tools_from_llm:
            return sorted(all_tools_from_llm)

    if all_tool_calls:
        seen: set[str] = set()
        for tc in all_tool_calls:
            name = ''
            if isinstance(tc, dict):
                name = tc.get('name', tc.get('tool_name', ''))
            elif hasattr(tc, 'name'):
                name = getattr(tc, 'name', '')
            if name:
                seen.add(name)
        if seen:
            return sorted(seen)

    if agent_name == 'codex':
        return []

    return list(ALL_CLAUDE_CODE_TOOLS)


def _read_local_instructions(project_path: Path, agent_name: str | None) -> str:
    """Read the local instruction preview for the active agent.

    Args:
        project_path: Resolved project directory.
        agent_name: Agent identifier that selects Codex or Claude instruction
            file precedence.

    Returns:
        Up to ``_TRUNCATE_LOCAL_INSTRUCTIONS`` characters from the first readable
        instruction file, or an empty string when none can be read. Read errors
        are debug-logged and swallowed.
    """
    if agent_name == 'codex':
        candidates = [
            project_path / 'AGENTS.md',
            project_path / '.codex' / 'AGENTS.md',
            project_path / 'CLAUDE.md',
            project_path / '.claude' / 'CLAUDE.md',
        ]
    else:
        candidates = [
            project_path / 'CLAUDE.md',
            project_path / '.claude' / 'CLAUDE.md',
        ]
    for path in candidates:
        try:
            if path.exists() and path.is_file():
                text = path.read_text(encoding='utf-8', errors='replace')
                return text[:_TRUNCATE_LOCAL_INSTRUCTIONS]
        except (OSError, PermissionError) as exc:
            logger.debug('Cannot read local instructions %s: %s', path, exc)
    return ''


def _read_agent_prompt(
    project_path: Path,
    agent_name: str | None,
    subagent_type: str | None = None,
) -> tuple[str, str]:
    """Read a main-agent or subagent prompt preview from project files.

    Args:
        project_path: Resolved project directory.
        agent_name: Agent identifier that selects agent prompt directories.
        subagent_type: Optional subagent name that takes precedence over the
            main agent name.

    Returns:
        Tuple of prompt file path and truncated prompt content. Both values are
        empty when no target or readable prompt file exists.
    """
    if not agent_name and not subagent_type:
        return '', ''

    if subagent_type:
        target_name = subagent_type
    elif agent_name:
        target_name = agent_name
    else:
        return '', ''

    if agent_name == 'codex':
        agents_dirs = [
            project_path / '.codex' / 'agents',
            project_path / '.claude' / 'agents',
        ]
    else:
        agents_dirs = [project_path / '.claude' / 'agents']

    for agents_dir_path in agents_dirs:
        candidate = agents_dir_path / f'{target_name}.md'
        try:
            if candidate.exists() and candidate.is_file():
                text = candidate.read_text(encoding='utf-8', errors='replace')
                return str(candidate), text[:_TRUNCATE_LOCAL_INSTRUCTIONS]
        except (OSError, PermissionError) as exc:
            logger.debug('Cannot read agent prompt %s: %s', candidate, exc)
    return '', ''


def _read_mcp_metadata(project_path: Path) -> tuple[list[str], list[str]]:
    """Read safe MCP server and tool names from project metadata.

    Args:
        project_path: Resolved project directory containing optional
            ``.mcp.json``.

    Returns:
        Tuple of tool labels and server names. The function intentionally drops
        command, environment, and credential values; parse or read failures
        return empty lists after debug logging.
    """
    mcp_path = project_path / '.mcp.json'
    if not mcp_path.exists() or not mcp_path.is_file():
        return [], []

    try:
        text = mcp_path.read_text(encoding='utf-8', errors='replace')
        data = json.loads(text)
    except (OSError, PermissionError, json.JSONDecodeError) as exc:
        logger.debug('Cannot read MCP metadata %s: %s', mcp_path, exc)
        return [], []

    servers: list[str] = []
    tools: list[str] = []

    mcp_servers_dict = data.get('mcpServers', data.get('mcp_servers', {}))
    if isinstance(mcp_servers_dict, dict):
        for server_name, server_config in mcp_servers_dict.items():
            servers.append(server_name)
            if isinstance(server_config, dict):
                server_tools = server_config.get('tools', server_config.get('allowedTools', []))
                if isinstance(server_tools, list):
                    for t in server_tools:
                        if isinstance(t, str):
                            tools.append(f'{server_name}:{t}')
                if not server_tools:
                    tools.append(f'{server_name}:*')

    return tools, servers


_SYSTEM_REMINDER_PATTERN = re.compile(
    r'<system-reminder>(.*?)</system-reminder>',
    re.DOTALL | re.IGNORECASE,
)


def _extract_system_reminder(messages: list[object]) -> str:
    """Extract the first system-reminder block visible in transcript payloads.

    Args:
        messages: Transcript entries as dictionaries or model objects.

    Returns:
        Inner text from the first ``<system-reminder>`` block found in
        ``request_full`` or ``content``, or an empty string when absent.
    """
    for msg in messages:
        request_full = ''
        if isinstance(msg, dict):
            request_full = msg.get('request_full', '') or msg.get('content', '')
        elif hasattr(msg, 'request_full'):
            request_full = getattr(msg, 'request_full', '') or ''

        if not request_full:
            continue

        m = _SYSTEM_REMINDER_PATTERN.search(request_full)
        if m:
            return m.group(1).strip()

        content = ''
        if isinstance(msg, dict):
            content = msg.get('content', '')
        elif hasattr(msg, 'content'):
            content = getattr(msg, 'content', '') or ''

        if content:
            m2 = _SYSTEM_REMINDER_PATTERN.search(str(content))
            if m2:
                return m2.group(1).strip()

    return ''
