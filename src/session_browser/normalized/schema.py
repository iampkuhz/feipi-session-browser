"""Lightweight validation for normalized session JSON.

This module intentionally avoids a JSON Schema dependency. The normalized JSON
contract is still evolving, so tests use focused semantic checks that protect
the important boundaries.
"""

from __future__ import annotations

from typing import Any


NORMALIZED_SCHEMA_VERSION = "session-detail.normalized.v1"


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
    LLM-call boundaries, request/response separation, token source shape,
    payload refs, and tool result handoff references.
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

    context_sources = data.get("context_sources")
    _require(isinstance(context_sources, list), "context_sources must be an array", errors)

    calls = data.get("calls")
    _require(isinstance(calls, list), "calls must be an array", errors)

    known_payload_ids: set[str] = set()
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
        _validate_call_side(prefix, "request", request, known_payload_ids, errors)
        _validate_call_side(prefix, "response", response, known_payload_ids, errors)

        usage = call_obj.get("usage") if isinstance(call_obj.get("usage"), dict) else {}
        expected_total = (
            int(usage.get("fresh") or 0)
            + int(usage.get("cache_read") or 0)
            + int(usage.get("cache_write") or 0)
            + int(usage.get("output") or 0)
        )
        _require(usage.get("total") == expected_total, f"{prefix}.usage.total mismatch", errors)

        declared_tool_ids_by_call[call_id] = set(_as_list(response.get("tool_use_ids")))
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

        result_ref = tool.get("result_ref") if isinstance(tool.get("result_ref"), dict) else {}
        result_payload_id = result_ref.get("payload_id")
        if result_payload_id:
            known_payload_ids.add(result_payload_id)

    for payload in _as_list((data.get("payload_index") or {}).get("items")):
        if not isinstance(payload, dict):
            continue
        pid = payload.get("payload_id")
        _require(pid in known_payload_ids, f"payload_index item {pid!r} is not referenced", errors)

    for row in _as_list((data.get("diagnostics") or {}).get("token_timeline")):
        if not isinstance(row, dict):
            continue
        _require(row.get("call_id") in known_call_ids, "token_timeline call_id not found", errors)

    if errors:
        raise NormalizedValidationError("; ".join(errors))


def _validate_call_side(
    prefix: str,
    side_name: str,
    side: dict,
    known_payload_ids: set[str],
    errors: list[str],
) -> None:
    side_prefix = f"{prefix}.{side_name}"
    _require(isinstance(side.get("content_refs"), list), f"{side_prefix}.content_refs must be an array", errors)
    _require(isinstance(side.get("token_sources"), list), f"{side_prefix}.token_sources must be an array", errors)

    payload_ref = side.get("payload_ref")
    token_source_ref = side.get("token_source_ref")
    _require(bool(payload_ref), f"{side_prefix}.payload_ref is required", errors)
    _require(bool(token_source_ref), f"{side_prefix}.token_source_ref is required", errors)
    if payload_ref:
        known_payload_ids.add(payload_ref)
    if token_source_ref:
        known_payload_ids.add(token_source_ref)

    for idx, source in enumerate(_as_list(side.get("token_sources"))):
        source_prefix = f"{side_prefix}.token_sources[{idx}]"
        _require(isinstance(source, dict), f"{source_prefix} must be an object", errors)
        if not isinstance(source, dict):
            continue
        _require(bool(source.get("canonical_category")), f"{source_prefix}.canonical_category is required", errors)
        _require("agent_bucket" in source, f"{source_prefix}.agent_bucket is required", errors)
        _require("tokens" in source, f"{source_prefix}.tokens is required", errors)
