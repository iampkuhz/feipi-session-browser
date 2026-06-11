"""Lightweight validation for normalized session JSON.

This module intentionally avoids a JSON Schema dependency. The normalized JSON
contract is still evolving, so first-stage tests use focused semantic checks
that protect the important boundaries.
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
    """Validate the first-stage normalized session contract.

    The checks are intentionally semantic rather than exhaustive. They guard the
    boundaries that matter for importer and snapshot tests:
    one main LLM call per round, direct attribution fields, payload refs, and
    tool-result handoff references.
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

    rounds = data.get("rounds")
    _require(isinstance(rounds, list), "rounds must be an array", errors)

    known_payload_ids: set[str] = set()
    known_tool_ids: set[str] = set()
    known_round_ids: set[int] = set()

    for idx, round_obj in enumerate(_as_list(rounds), 1):
        prefix = f"rounds[{idx - 1}]"
        _require(isinstance(round_obj, dict), f"{prefix} must be an object", errors)
        if not isinstance(round_obj, dict):
            continue

        rid = round_obj.get("round_id")
        known_round_ids.add(rid)
        _require(rid == idx, f"{prefix}.round_id must be sequential starting at 1", errors)
        _require(round_obj.get("round_key") == f"R{idx}", f"{prefix}.round_key mismatch", errors)

        for field in (
            "main_call",
            "request",
            "response",
            "request_attribution",
            "response_attribution",
            "payload_refs",
            "steps",
        ):
            _require(field in round_obj, f"{prefix}.{field} is required", errors)

        payload_refs = round_obj.get("payload_refs") or {}
        for ref_field in (
            "request_payload_id",
            "response_payload_id",
            "request_attribution_id",
            "response_attribution_id",
        ):
            ref = payload_refs.get(ref_field)
            _require(bool(ref), f"{prefix}.payload_refs.{ref_field} is required", errors)
            if ref:
                known_payload_ids.add(ref)

        steps = _as_list(round_obj.get("steps"))
        main_steps = [
            s for s in steps
            if isinstance(s, dict)
            and s.get("type") == "llm_call"
            and s.get("scope") == "main"
        ]
        _require(len(main_steps) == 1, f"{prefix} must contain exactly one main llm_call step", errors)
        if main_steps:
            _require(
                main_steps[0].get("call_id") == (round_obj.get("main_call") or {}).get("call_id"),
                f"{prefix} main llm_call step must reference main_call.call_id",
                errors,
            )

        for step in steps:
            if not isinstance(step, dict):
                continue
            if step.get("type") == "tool_batch":
                for tool in _as_list(step.get("tools")):
                    if isinstance(tool, dict):
                        tid = tool.get("tool_call_id")
                        if tid:
                            known_tool_ids.add(tid)
                        payload_id = tool.get("payload_id")
                        if payload_id:
                            known_payload_ids.add(payload_id)
            if step.get("type") == "subagent_run":
                for sub_round in _as_list(step.get("sub_rounds")):
                    _validate_sub_round(sub_round, f"{prefix}.sub_rounds", errors, known_payload_ids)

        tokens = (round_obj.get("metrics") or {}).get("tokens") or {}
        if tokens:
            expected_total = (
                int(tokens.get("fresh") or 0)
                + int(tokens.get("cache_read") or 0)
                + int(tokens.get("cache_write") or 0)
                + int(tokens.get("output") or 0)
            )
            _require(tokens.get("total") == expected_total, f"{prefix}.metrics.tokens.total mismatch", errors)

    for link in _as_list(data.get("tool_result_links")):
        if not isinstance(link, dict):
            continue
        source = link.get("source_tool_call_id")
        consumed_by = link.get("consumed_by_call_id")
        _require(source in known_tool_ids, f"tool_result_links source {source!r} not found", errors)
        _require(bool(consumed_by), "tool_result_links.consumed_by_call_id is required", errors)

    for payload in _as_list(data.get("payload_index", {}).get("items")):
        if not isinstance(payload, dict):
            continue
        pid = payload.get("payload_id")
        _require(pid in known_payload_ids, f"payload_index item {pid!r} is not referenced", errors)

    for row in _as_list((data.get("diagnostics") or {}).get("token_timeline")):
        if not isinstance(row, dict):
            continue
        _require(row.get("round_id") in known_round_ids, "token_timeline round_id not found", errors)

    if errors:
        raise NormalizedValidationError("; ".join(errors))


def _validate_sub_round(
    sub_round: Any,
    prefix: str,
    errors: list[str],
    known_payload_ids: set[str],
) -> None:
    if not isinstance(sub_round, dict):
        errors.append(f"{prefix} item must be an object")
        return
    for field in (
        "call_id",
        "request",
        "response",
        "request_attribution",
        "response_attribution",
        "payload_refs",
        "steps",
    ):
        _require(field in sub_round, f"{prefix}.{field} is required", errors)
    payload_refs = sub_round.get("payload_refs") or {}
    for ref_field in (
        "request_payload_id",
        "response_payload_id",
        "request_attribution_id",
        "response_attribution_id",
    ):
        ref = payload_refs.get(ref_field)
        _require(bool(ref), f"{prefix}.payload_refs.{ref_field} is required", errors)
        if ref:
            known_payload_ids.add(ref)
    for step in _as_list(sub_round.get("steps")):
        if not isinstance(step, dict) or step.get("type") != "tool_batch":
            continue
        for tool in _as_list(step.get("tools")):
            if not isinstance(tool, dict):
                continue
            payload_id = tool.get("payload_id")
            if payload_id:
                known_payload_ids.add(payload_id)
