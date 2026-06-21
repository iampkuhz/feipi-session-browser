"""Validate normalized session JSON without a JSON Schema dependency."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from session_browser.normalized.constants import NORMALIZED_SCHEMA_VERSION
from session_browser.normalized.models import validate_normalized_artifact_model

_BYTE_RANGE_LENGTH = 2


@dataclass(frozen=True)
class _ToolEdgeLookups:
    """Lookup tables used while validating normalized tool execution edges.

    Tool validation creates this short-lived immutable context after call
    validation has collected IDs. It avoids passing several coupled edge maps
    through every helper and keeps validation side effects limited to the shared
    error list.

    Attributes:
        known_call_ids: Call IDs collected from the normalized call list.
        declared_tool_ids_by_call: Response-declared tool IDs keyed by call ID.
        consumed_tool_ids_by_call: Request-consumed tool IDs keyed by call ID.
    """

    known_call_ids: set[str]
    declared_tool_ids_by_call: dict[str, set[str]]
    consumed_tool_ids_by_call: dict[str, set[str]]


class NormalizedValidationError(ValueError):
    """Raised when normalized session JSON violates the intermediate contract."""


def _require(condition: bool, message: str, errors: list[str]) -> None:
    """Append a validation error when a semantic requirement fails.

    All schema helper functions use this tiny collector so validation can report
    every recoverable contract issue in one exception instead of failing fast.

    Args:
        condition: Truth value for the current contract requirement.
        message: Error message to append when the requirement is false.
        errors: Shared validation error list mutated by the current pass.
    """
    if not condition:
        errors.append(message)


def _as_list(value: object) -> list[Any]:
    """Return JSON list values while treating all other inputs as empty.

    Validation helpers call this for optional arrays so malformed containers are
    reported by their owning check without causing iteration errors.

    Args:
        value: Candidate JSON value from the normalized artifact.

    Returns:
        The original list when ``value`` is a list, otherwise an empty list.
    """
    return value if isinstance(value, list) else []


def validate_normalized_session(data: dict[str, Any]) -> None:
    """Validate the current normalized session contract.

    Index scans call this before writing normalized JSON artifacts, and tests use
    it as the semantic gate for fixture payloads. The checks guard LLM-call
    ordering, request/response separation, usage totals, source-unit references,
    and tool-result handoff references; successful validation has no side
    effects.

    Args:
        data: Top-level normalized session artifact object to validate.

    Raises:
        NormalizedValidationError: Raised with all collected contract messages
            when the payload shape or semantic references are invalid.
    """
    errors: list[str] = []

    _require(isinstance(data, dict), 'normalized payload must be an object', errors)
    if not isinstance(data, dict):
        raise NormalizedValidationError('; '.join(errors))

    _validate_top_level(data, errors)
    _validate_session(data, errors)
    _validate_source(data, errors)
    catalog = _validate_source_unit_catalog(data.get('source_unit_catalog'), errors)
    sequences = _validate_source_unit_sequences(data.get('source_unit_sequences'), catalog, errors)
    known_call_ids, declared_tool_ids_by_call, consumed_tool_ids_by_call = _validate_calls(
        data.get('calls'), catalog, sequences, errors
    )
    _validate_tool_executions(
        data.get('tool_executions'),
        _ToolEdgeLookups(
            known_call_ids=known_call_ids,
            declared_tool_ids_by_call=declared_tool_ids_by_call,
            consumed_tool_ids_by_call=consumed_tool_ids_by_call,
        ),
        errors,
    )
    _validate_diagnostics(data.get('diagnostics', []), errors)
    _validate_model_when_semantic_checks_pass(data, errors)

    if errors:
        raise NormalizedValidationError('; '.join(errors))


def _validate_top_level(data: dict[str, Any], errors: list[str]) -> None:
    """Validate schema version, agent name, and call container shape.

    The public validator calls this first because later checks depend on a known
    normalized schema and supported adapter name.

    Args:
        data: Top-level normalized artifact object.
        errors: Shared validation error list mutated by this helper.
    """
    _require(
        data.get('schema_version') == NORMALIZED_SCHEMA_VERSION,
        f'schema_version must be {NORMALIZED_SCHEMA_VERSION}',
        errors,
    )
    _require(data.get('agent') in {'codex', 'claude_code', 'qoder'}, 'invalid agent', errors)
    _require(isinstance(data.get('calls'), list), 'calls must be an array', errors)


def _validate_session(data: dict[str, Any], errors: list[str]) -> None:
    """Validate the normalized session metadata object.

    The public validator calls this before call-edge checks so the canonical
    session key is guaranteed to match the top-level agent when present.

    Args:
        data: Top-level normalized artifact object.
        errors: Shared validation error list mutated by this helper.
    """
    session = data.get('session')
    _require(isinstance(session, dict), 'session must be an object', errors)
    if not isinstance(session, dict):
        return
    agent = data.get('agent')
    sid = session.get('session_id')
    _require(bool(sid), 'session.session_id is required', errors)
    _require(
        session.get('session_key') == f'{agent}:{sid}',
        'session.session_key must be {agent}:{session_id}',
        errors,
    )


def _validate_source(data: dict[str, Any], errors: list[str]) -> None:
    """Validate the presence of the source metadata container.

    The normalized artifact keeps source provenance under ``source``. This check
    only protects the container shape because source-file detail is validated by
    the model layer.

    Args:
        data: Top-level normalized artifact object.
        errors: Shared validation error list mutated by this helper.
    """
    _require(isinstance(data.get('source'), dict), 'source must be an object', errors)


def _validate_source_unit_catalog(value: object, errors: list[str]) -> dict[str, Any] | None:
    """Validate optional source-unit catalog entries.

    Call and sequence validators use the returned catalog to check references.
    The helper accepts an absent catalog, reports malformed entries, and returns
    only dictionary catalogs for downstream lookups.

    Args:
        value: Candidate ``source_unit_catalog`` value from the artifact.
        errors: Shared validation error list mutated by this helper.

    Returns:
        Catalog mapping when present and dictionary-shaped, otherwise ``None``.
    """
    if value is None:
        return None
    _require(isinstance(value, dict), 'source_unit_catalog must be an object', errors)
    if not isinstance(value, dict):
        return None
    for key, unit in value.items():
        _validate_catalog_unit(str(key), unit, errors)
    return value


def _validate_catalog_unit(key: str, unit: object, errors: list[str]) -> None:
    """Validate one source-unit catalog value.

    Catalog validation calls this for each key/value pair. It checks stable key
    identity, required provenance fields, and request/response direction.

    Args:
        key: Catalog key currently being validated.
        unit: Candidate catalog entry value.
        errors: Shared validation error list mutated by this helper.
    """
    prefix = f'source_unit_catalog[{key!r}]'
    _require(isinstance(unit, dict), f'{prefix} must be an object', errors)
    if not isinstance(unit, dict):
        return
    _require(unit.get('unit_key') == key, f'{prefix}.unit_key must match its catalog key', errors)
    for field in (
        'unit_key',
        'origin_path',
        'canonical_source_locator',
        'unit_type',
        'candidate',
        'direction',
        'event_order',
        'part_index',
        'byte_range',
        'content_hash',
    ):
        _require(field in unit, f'{prefix}.{field} is required', errors)
    _require(
        unit.get('direction') in {'request', 'response'}, f'{prefix}.direction invalid', errors
    )


def _validate_source_unit_sequences(
    value: object,
    catalog: dict[str, Any] | None,
    errors: list[str],
) -> dict[str, Any] | None:
    """Validate optional named source-unit sequences.

    Call reference ranges use these sequence names to avoid repeating catalog
    keys. The helper reports missing catalog references when a catalog is
    available and returns a dictionary only when the container shape is valid.

    Args:
        value: Candidate ``source_unit_sequences`` value from the artifact.
        catalog: Validated catalog mapping used for reference checks.
        errors: Shared validation error list mutated by this helper.

    Returns:
        Sequence mapping when present and dictionary-shaped, otherwise ``None``.
    """
    if value is None:
        return None
    _require(isinstance(value, dict), 'source_unit_sequences must be an object', errors)
    if not isinstance(value, dict):
        return None
    for name, refs in value.items():
        _require(isinstance(refs, list), f'source_unit_sequences.{name} must be an array', errors)
        if isinstance(refs, list) and isinstance(catalog, dict):
            for ref in refs:
                _require(
                    str(ref) in catalog,
                    f'source_unit_sequences.{name} references missing catalog unit',
                    errors,
                )
    return value


def _validate_calls(
    calls: object,
    catalog: dict[str, Any] | None,
    sequences: dict[str, Any] | None,
    errors: list[str],
) -> tuple[set[str], dict[str, set[str]], dict[str, set[str]]]:
    """Validate normalized calls and collect edge lookup tables.

    The public validator calls this before tool execution checks. It preserves
    source order, accumulates known call IDs, and records declared/consumed tool
    identifiers by call for later cross-reference validation.

    Args:
        calls: Candidate top-level ``calls`` value.
        catalog: Validated source-unit catalog for reference checks.
        sequences: Validated source-unit sequence mapping for range checks.
        errors: Shared validation error list mutated by this helper.

    Returns:
        Known call IDs, response-declared tool IDs by call, and request-consumed
        tool IDs by call.
    """
    known_call_ids: set[str] = set()
    declared_tool_ids_by_call: dict[str, set[str]] = {}
    consumed_tool_ids_by_call: dict[str, set[str]] = {}

    for idx, call_obj in enumerate(_as_list(calls), 1):
        prefix = f'calls[{idx - 1}]'
        call_id = _validate_call_identity(prefix, idx, call_obj, known_call_ids, errors)
        if not isinstance(call_obj, dict):
            continue
        _validate_call_required_sections(prefix, call_obj, errors)
        _validate_call_source_refs(
            prefix, call_obj.get('source_unit_ref_ranges'), catalog, sequences, errors
        )
        request = call_obj.get('request') if isinstance(call_obj.get('request'), dict) else {}
        response = call_obj.get('response') if isinstance(call_obj.get('response'), dict) else {}
        _validate_call_side(prefix, 'request', request, ('tool_result_ids',), errors)
        _validate_call_side(prefix, 'response', response, ('tool_call_ids',), errors)
        _validate_usage(prefix, call_obj, errors)
        _validate_usage_source(prefix, call_obj.get('usage_source'), errors)
        _validate_inline_source_units(prefix, call_obj.get('source_units'), errors)
        declared_tool_ids_by_call[call_id] = set(_as_list(response.get('tool_call_ids')))
        consumed_tool_ids_by_call[call_id] = set(_as_list(request.get('tool_result_ids')))

    return known_call_ids, declared_tool_ids_by_call, consumed_tool_ids_by_call


def _validate_call_identity(
    prefix: str,
    idx: int,
    call_obj: object,
    known_call_ids: set[str],
    errors: list[str],
) -> str:
    """Validate one call object identity and sequential display key.

    Call validation invokes this first for each list item so later edge maps can
    use the normalized call ID even when additional fields fail validation.

    Args:
        prefix: Error-message prefix for the current call list item.
        idx: One-based call position in normalized traversal order.
        call_obj: Candidate call object from the artifact.
        known_call_ids: Mutable set tracking call ID uniqueness.
        errors: Shared validation error list mutated by this helper.

    Returns:
        String call identifier, or an empty string when absent.
    """
    _require(isinstance(call_obj, dict), f'{prefix} must be an object', errors)
    if not isinstance(call_obj, dict):
        return ''
    call_id = str(call_obj.get('call_id') or '')
    _require(bool(call_id), f'{prefix}.call_id is required', errors)
    if call_id:
        _require(call_id not in known_call_ids, f'{prefix}.call_id must be unique', errors)
        known_call_ids.add(call_id)
    _require(
        call_obj.get('call_index') == idx,
        f'{prefix}.call_index must be sequential starting at 1',
        errors,
    )
    _require(call_obj.get('call_key') == f'C{idx}', f'{prefix}.call_key mismatch', errors)
    return call_id


def _validate_call_required_sections(
    prefix: str, call_obj: dict[str, Any], errors: list[str]
) -> None:
    """Validate that required nested call sections are present.

    Call validation invokes this before section-specific helpers so missing
    request, response, or usage objects are reported explicitly.

    Args:
        prefix: Error-message prefix for the current call.
        call_obj: Current normalized call object.
        errors: Shared validation error list mutated by this helper.
    """
    for field in ('request', 'response', 'usage'):
        _require(field in call_obj, f'{prefix}.{field} is required', errors)


def _validate_call_source_refs(
    prefix: str,
    ref_ranges: object,
    catalog: dict[str, Any] | None,
    sequences: dict[str, Any] | None,
    errors: list[str],
) -> None:
    """Validate source-unit reference ranges attached to one call.

    Call validation invokes this for optional ``source_unit_ref_ranges``. It
    checks container shapes and verifies explicit catalog or sequence references
    when the corresponding lookup tables are available.

    Args:
        prefix: Error-message prefix for the current call.
        ref_ranges: Candidate reference-range list from the call.
        catalog: Validated catalog mapping for explicit reference checks.
        sequences: Validated sequence mapping for named range checks.
        errors: Shared validation error list mutated by this helper.
    """
    if ref_ranges is None:
        return
    _require(
        isinstance(ref_ranges, list), f'{prefix}.source_unit_ref_ranges must be an array', errors
    )
    if not isinstance(ref_ranges, list):
        return
    for range_idx, ref_range in enumerate(ref_ranges):
        range_prefix = f'{prefix}.source_unit_ref_ranges[{range_idx}]'
        _validate_ref_range(range_prefix, ref_range, catalog, sequences, errors)


def _validate_ref_range(
    range_prefix: str,
    ref_range: object,
    catalog: dict[str, Any] | None,
    sequences: dict[str, Any] | None,
    errors: list[str],
) -> None:
    """Validate one source-unit reference range.

    Source-reference validation calls this for each range item. It treats bad
    range containers as local errors and avoids cascading reference lookups.

    Args:
        range_prefix: Error-message prefix for the current range item.
        ref_range: Candidate range object from a normalized call.
        catalog: Validated catalog mapping for explicit reference checks.
        sequences: Validated sequence mapping for named range checks.
        errors: Shared validation error list mutated by this helper.
    """
    _require(isinstance(ref_range, dict), f'{range_prefix} must be an object', errors)
    if not isinstance(ref_range, dict):
        return
    if ref_range.get('sequence'):
        seq_name = str(ref_range.get('sequence'))
        _require(
            isinstance(sequences, dict) and seq_name in sequences,
            f'{range_prefix}.sequence references missing sequence',
            errors,
        )
    refs = ref_range.get('refs')
    if refs is None:
        return
    _require(isinstance(refs, list), f'{range_prefix}.refs must be an array', errors)
    if isinstance(refs, list) and isinstance(catalog, dict):
        for ref in refs:
            _require(
                str(ref) in catalog, f'{range_prefix}.refs references missing catalog unit', errors
            )


def _validate_usage(prefix: str, call_obj: dict[str, Any], errors: list[str]) -> None:
    """Validate token usage totals for one normalized call.

    Call validation invokes this after required section checks. Missing or
    malformed usage containers are treated as empty mappings so the total
    mismatch is still reported deterministically.

    Args:
        prefix: Error-message prefix for the current call.
        call_obj: Current normalized call object.
        errors: Shared validation error list mutated by this helper.
    """
    usage = call_obj.get('usage') if isinstance(call_obj.get('usage'), dict) else {}
    expected_total = (
        int(usage.get('fresh') or 0)
        + int(usage.get('cache_read') or 0)
        + int(usage.get('cache_write') or 0)
        + int(usage.get('output') or 0)
    )
    _require(usage.get('total') == expected_total, f'{prefix}.usage.total mismatch', errors)


def _validate_usage_source(prefix: str, usage_source: object, errors: list[str]) -> None:
    """Validate optional estimated-usage provenance for one call.

    Call validation invokes this when adapters mark token usage as estimated.
    The normalized contract requires a kind, method, and reason so UI consumers
    can explain the estimate.

    Args:
        prefix: Error-message prefix for the current call.
        usage_source: Candidate usage-source object.
        errors: Shared validation error list mutated by this helper.
    """
    if usage_source is None:
        return
    _require(isinstance(usage_source, dict), f'{prefix}.usage_source must be an object', errors)
    if not isinstance(usage_source, dict):
        return
    _require(
        usage_source.get('kind') == 'estimated',
        f'{prefix}.usage_source.kind must be estimated',
        errors,
    )
    _require(bool(usage_source.get('method')), f'{prefix}.usage_source.method is required', errors)
    _require(bool(usage_source.get('reason')), f'{prefix}.usage_source.reason is required', errors)


def _validate_inline_source_units(prefix: str, source_units: object, errors: list[str]) -> None:
    """Validate legacy inline source units attached to one call.

    Call validation keeps this compatibility path while catalog references are
    being adopted. It checks required fields, direction, candidate bucket, and
    byte-range shape for every inline unit.

    Args:
        prefix: Error-message prefix for the current call.
        source_units: Candidate inline source-unit list from the call.
        errors: Shared validation error list mutated by this helper.
    """
    for unit_idx, unit in enumerate(_as_list(source_units)):
        unit_prefix = f'{prefix}.source_units[{unit_idx}]'
        _validate_inline_source_unit(unit_prefix, unit, errors)


def _validate_inline_source_unit(unit_prefix: str, unit: object, errors: list[str]) -> None:
    """Validate one legacy inline source-unit object.

    Inline source-unit validation invokes this for each list item. Bad container
    types are reported locally and skipped to avoid cascading field errors.

    Args:
        unit_prefix: Error-message prefix for the current inline unit.
        unit: Candidate inline source-unit object.
        errors: Shared validation error list mutated by this helper.
    """
    _require(isinstance(unit, dict), f'{unit_prefix} must be an object', errors)
    if not isinstance(unit, dict):
        return
    for field in (
        'source_id',
        'dedupe_key',
        'origin_path',
        'canonical_source_locator',
        'unit_type',
        'candidate',
        'direction',
        'event_order',
        'part_index',
        'byte_range',
    ):
        _require(field in unit, f'{unit_prefix}.{field} is required', errors)
    _require(
        unit.get('direction') in {'request', 'response'}, f'{unit_prefix}.direction invalid', errors
    )
    _require(
        unit.get('candidate') in _INLINE_SOURCE_CANDIDATES,
        f'{unit_prefix}.candidate invalid',
        errors,
    )
    byte_range = unit.get('byte_range')
    _require(
        isinstance(byte_range, list)
        and len(byte_range) == _BYTE_RANGE_LENGTH
        and all(isinstance(v, int) and v >= 0 for v in byte_range),
        f'{unit_prefix}.byte_range must be [start,end]',
        errors,
    )


_INLINE_SOURCE_CANDIDATES = {
    'user_input',
    'system_instructions',
    'tool_definitions',
    'skill_definitions',
    'runtime_context',
    'conversation_history',
    'tool_results',
    'reasoning_state',
    'repo_context',
    'assistant_output',
    'reasoning_output',
    'tool_calls',
    'structured_output',
}


def _validate_tool_executions(
    tools: object,
    lookups: _ToolEdgeLookups,
    errors: list[str],
) -> None:
    """Validate tool execution rows against normalized call edges.

    The public validator calls this after calls have produced lookup tables. It
    enforces unique tool IDs, declaring-call references, and optional consuming
    call references.

    Args:
        tools: Candidate top-level ``tool_executions`` value.
        lookups: Call and tool-edge lookup tables collected from calls.
        errors: Shared validation error list mutated by this helper.
    """
    known_tool_ids: set[str] = set()
    for idx, tool in enumerate(_as_list(tools)):
        prefix = f'tool_executions[{idx}]'
        _validate_tool_execution(prefix, tool, known_tool_ids, lookups, errors)


def _validate_tool_execution(
    prefix: str,
    tool: object,
    known_tool_ids: set[str],
    lookups: _ToolEdgeLookups,
    errors: list[str],
) -> None:
    """Validate one tool execution row and its call references.

    Tool-edge validation invokes this for each row. It records unique tool IDs
    and checks that declared and consumed edges are represented in the owning
    call request or response lists.

    Args:
        prefix: Error-message prefix for the current tool row.
        tool: Candidate tool execution object.
        known_tool_ids: Mutable set tracking tool ID uniqueness.
        lookups: Call and tool-edge lookup tables collected from calls.
        errors: Shared validation error list mutated by this helper.
    """
    _require(isinstance(tool, dict), f'{prefix} must be an object', errors)
    if not isinstance(tool, dict):
        return
    tool_id = str(tool.get('tool_call_id') or '')
    declared_by = str(tool.get('declared_by_call_id') or '')
    consumed_by = str(tool.get('result_consumed_by_call_id') or '')

    _require(bool(tool_id), f'{prefix}.tool_call_id is required', errors)
    _require(tool_id not in known_tool_ids, f'{prefix}.tool_call_id must be unique', errors)
    if tool_id:
        known_tool_ids.add(tool_id)
    _require(
        declared_by in lookups.known_call_ids, f'{prefix}.declared_by_call_id not found', errors
    )
    if declared_by in lookups.declared_tool_ids_by_call:
        _require(
            tool_id in lookups.declared_tool_ids_by_call[declared_by],
            f'{prefix}.tool_call_id not referenced by declaring call response',
            errors,
        )
    _validate_tool_consumer(prefix, tool_id, consumed_by, lookups, errors)


def _validate_tool_consumer(
    prefix: str,
    tool_id: str,
    consumed_by: str,
    lookups: _ToolEdgeLookups,
    errors: list[str],
) -> None:
    """Validate the optional consuming-call side of a tool edge.

    Tool-edge validation calls this only after the declaring side has been
    checked. Empty consumers are allowed because a tool result may not have been
    read by a later LLM call.

    Args:
        prefix: Error-message prefix for the current tool row.
        tool_id: Tool-call identifier being validated.
        consumed_by: Optional consuming call identifier.
        lookups: Call and tool-edge lookup tables collected from calls.
        errors: Shared validation error list mutated by this helper.
    """
    if not consumed_by:
        return
    _require(
        consumed_by in lookups.known_call_ids,
        f'{prefix}.result_consumed_by_call_id not found',
        errors,
    )
    if consumed_by in lookups.consumed_tool_ids_by_call:
        _require(
            tool_id in lookups.consumed_tool_ids_by_call[consumed_by],
            f'{prefix}.tool_call_id not referenced by consuming call request',
            errors,
        )


def _validate_diagnostics(diagnostics: object, errors: list[str]) -> None:
    """Validate the top-level diagnostics container.

    The public validator calls this near the end because diagnostics are
    non-fatal parser metadata and do not affect cross-reference checks.

    Args:
        diagnostics: Candidate diagnostics value from the artifact.
        errors: Shared validation error list mutated by this helper.
    """
    _require(isinstance(diagnostics, list), 'diagnostics must be an array', errors)


def _validate_model_when_semantic_checks_pass(data: dict[str, Any], errors: list[str]) -> None:
    """Run dataclass model validation after semantic checks are clean.

    The public validator invokes this as the final validation layer. It avoids
    cascading model errors when earlier shape checks have already identified
    invalid payloads.

    Args:
        data: Top-level normalized artifact object.
        errors: Shared validation error list mutated by this helper.
    """
    if errors:
        return
    try:
        validate_normalized_artifact_model(data)
    except ValueError as exc:
        errors.append(str(exc))


def _validate_call_side(
    prefix: str,
    side_name: str,
    side: dict[str, Any],
    required_lists: tuple[str, ...],
    errors: list[str],
) -> None:
    """Validate request or response edge-list fields for one call.

    Call validation uses this helper for both request tool-result IDs and
    response tool-call IDs. Each required list must be present, list-shaped, and
    contain non-empty strings.

    Args:
        prefix: Error-message prefix for the current call.
        side_name: Name of the side being checked, either request or response.
        side: Request or response object from the call.
        required_lists: Required list fields for this side.
        errors: Shared validation error list mutated by this helper.
    """
    side_prefix = f'{prefix}.{side_name}'
    for field in required_lists:
        _require(
            isinstance(side.get(field), list), f'{side_prefix}.{field} must be an array', errors
        )
        for idx, item in enumerate(_as_list(side.get(field))):
            _require(
                isinstance(item, str) and bool(item),
                f'{side_prefix}.{field}[{idx}] must be a non-empty string',
                errors,
            )
