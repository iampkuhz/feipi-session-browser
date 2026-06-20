"""Lightweight validation for normalized session JSON.

This module intentionally avoids a JSON Schema dependency. The normalized JSON
contract is still evolving, so tests use focused semantic checks that protect
the important boundaries.
"""

from __future__ import annotations

from typing import Any


NORMALIZED_SCHEMA_VERSION = "session-detail.normalized.v2"


class NormalizedValidationError(ValueError):
    """Raised when normalized session JSON violates the intermediate contract."""


def _require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def validate_normalized_session(data: dict) -> None:
    """Validate the current normalized session contract.

    The checks are intentionally semantic rather than exhaustive. They guard
    LLM-call boundaries, request/response separation, usage totals, and tool
    result handoff references.
    """
    errors: list[str] = []

    _require(isinstance(data, dict), "normalized payload must be an object", errors)
    if not isinstance(data, dict):
        raise NormalizedValidationError("; ".join(errors))

    _require(
        data.get("schema_version") == NORMALIZED_SCHEMA_VERSION,
        f"schema_version must be {NORMALIZED_SCHEMA_VERSION}",
        errors,
    )
    _require(data.get("agent") in {"codex", "claude_code", "qoder"}, "invalid agent", errors)

    session = data.get("session")
    _require(isinstance(session, dict), "session must be an object", errors)
    if isinstance(session, dict):
        agent = data.get("agent")
        sid = session.get("session_id")
        _require(bool(sid), "session.session_id is required", errors)
        _require(
            session.get("session_key") == f"{agent}:{sid}",
            "session.session_key must be {agent}:{session_id}",
            errors,
        )

    source = data.get("source")
    _require(isinstance(source, dict), "source must be an object", errors)

    calls = data.get("calls")
    _require(isinstance(calls, list), "calls must be an array", errors)

    known_call_ids: set[str] = set()
    declared_tool_ids_by_call: dict[str, set[str]] = {}
    consumed_tool_ids_by_call: dict[str, set[str]] = {}

    for idx, call_obj in enumerate(_as_list(calls), 1):
        prefix = f"calls[{idx - 1}]"
        _require(isinstance(call_obj, dict), f"{prefix} must be an object", errors)
        if not isinstance(call_obj, dict):
            continue

        call_id = str(call_obj.get("call_id") or "")
        _require(bool(call_id), f"{prefix}.call_id is required", errors)
        if call_id:
            _require(call_id not in known_call_ids, f"{prefix}.call_id must be unique", errors)
            known_call_ids.add(call_id)

        _require(call_obj.get("call_index") == idx, f"{prefix}.call_index must be sequential starting at 1", errors)
        _require(call_obj.get("call_key") == f"C{idx}", f"{prefix}.call_key mismatch", errors)

        for field in ("request", "response", "usage"):
            _require(field in call_obj, f"{prefix}.{field} is required", errors)

        request = call_obj.get("request") if isinstance(call_obj.get("request"), dict) else {}
        response = call_obj.get("response") if isinstance(call_obj.get("response"), dict) else {}
        _validate_call_side(prefix, "request", request, ("tool_result_ids",), errors)
        _validate_call_side(prefix, "response", response, ("tool_call_ids",), errors)

        usage = call_obj.get("usage") if isinstance(call_obj.get("usage"), dict) else {}
        expected_total = (
            int(usage.get("fresh") or 0)
            + int(usage.get("cache_read") or 0)
            + int(usage.get("cache_write") or 0)
            + int(usage.get("output") or 0)
        )
        _require(usage.get("total") == expected_total, f"{prefix}.usage.total mismatch", errors)
        usage_source = call_obj.get("usage_source")
        if usage_source is not None:
            _require(isinstance(usage_source, dict), f"{prefix}.usage_source must be an object", errors)
            if isinstance(usage_source, dict):
                _require(usage_source.get("kind") == "estimated", f"{prefix}.usage_source.kind must be estimated", errors)
                _require(bool(usage_source.get("method")), f"{prefix}.usage_source.method is required", errors)
                _require(bool(usage_source.get("reason")), f"{prefix}.usage_source.reason is required", errors)

        for unit_idx, unit in enumerate(_as_list(call_obj.get("source_units"))):
            unit_prefix = f"{prefix}.source_units[{unit_idx}]"
            _require(isinstance(unit, dict), f"{unit_prefix} must be an object", errors)
            if not isinstance(unit, dict):
                continue
            for field in (
                "source_id",
                "dedupe_key",
                "origin_path",
                "canonical_source_locator",
                "unit_type",
                "candidate",
                "direction",
                "event_order",
                "part_index",
                "byte_range",
            ):
                _require(field in unit, f"{unit_prefix}.{field} is required", errors)
            _require(unit.get("direction") in {"request", "response"}, f"{unit_prefix}.direction invalid", errors)
            _require(unit.get("candidate") in {
                "user_input",
                "system_instructions",
                "tool_definitions",
                "skill_definitions",
                "runtime_context",
                "conversation_history",
                "tool_results",
                "reasoning_state",
                "repo_context",
                "assistant_output",
                "reasoning_output",
                "tool_calls",
                "structured_output",
            }, f"{unit_prefix}.candidate invalid", errors)
            byte_range = unit.get("byte_range")
            _require(
                isinstance(byte_range, list)
                and len(byte_range) == 2
                and all(isinstance(v, int) and v >= 0 for v in byte_range),
                f"{unit_prefix}.byte_range must be [start,end]",
                errors,
            )

        declared_tool_ids_by_call[call_id] = set(_as_list(response.get("tool_call_ids")))
        consumed_tool_ids_by_call[call_id] = set(_as_list(request.get("tool_result_ids")))

    known_tool_ids: set[str] = set()
    for idx, tool in enumerate(_as_list(data.get("tool_executions"))):
        prefix = f"tool_executions[{idx}]"
        _require(isinstance(tool, dict), f"{prefix} must be an object", errors)
        if not isinstance(tool, dict):
            continue

        tool_id = str(tool.get("tool_call_id") or "")
        declared_by = str(tool.get("declared_by_call_id") or "")
        consumed_by = str(tool.get("result_consumed_by_call_id") or "")

        _require(bool(tool_id), f"{prefix}.tool_call_id is required", errors)
        _require(tool_id not in known_tool_ids, f"{prefix}.tool_call_id must be unique", errors)
        if tool_id:
            known_tool_ids.add(tool_id)

        _require(declared_by in known_call_ids, f"{prefix}.declared_by_call_id not found", errors)
        if declared_by in declared_tool_ids_by_call:
            _require(
                tool_id in declared_tool_ids_by_call[declared_by],
                f"{prefix}.tool_call_id not referenced by declaring call response",
                errors,
            )
        if consumed_by:
            _require(consumed_by in known_call_ids, f"{prefix}.result_consumed_by_call_id not found", errors)
            if consumed_by in consumed_tool_ids_by_call:
                _require(
                    tool_id in consumed_tool_ids_by_call[consumed_by],
                    f"{prefix}.tool_call_id not referenced by consuming call request",
                    errors,
                )

    diagnostics = data.get("diagnostics", [])
    _require(isinstance(diagnostics, list), "diagnostics must be an array", errors)

    if errors:
        raise NormalizedValidationError("; ".join(errors))


def _validate_call_side(
    prefix: str,
    side_name: str,
    side: dict,
    required_lists: tuple[str, ...],
    errors: list[str],
) -> None:
    side_prefix = f"{prefix}.{side_name}"
    for field in required_lists:
        _require(isinstance(side.get(field), list), f"{side_prefix}.{field} must be an array", errors)
        for idx, item in enumerate(_as_list(side.get(field))):
            _require(isinstance(item, str) and bool(item), f"{side_prefix}.{field}[{idx}] must be a non-empty string", errors)
