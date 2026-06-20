"""Qoder source_units 归因 builder。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from session_browser.attribution.agents.base import BaseAttributionBuilder
from session_browser.attribution.contracts import (
    AttributedValue,
    AvailabilityRow,
    LLMRequestAttribution,
    LLMResponseAttribution,
    RequestAttributionBucket,
    ResponseAttributionBucket,
    ValuePrecision,
    ValueSource,
)
from session_browser.attribution.mapping.agents.qoder_token_accounting_mapping import (
    QoderTokenAccountingMapper,
)
from session_browser.attribution.token_estimator import estimate_tokens_from_text


class QoderAttributionBuilder(BaseAttributionBuilder):
    """只使用 Qoder normalized source_units 的归因实现。"""

    agent_name = "qoder"
    source_label = "normalized artifact source_units"
    mapper_cls = QoderTokenAccountingMapper

    def build_request(self) -> LLMRequestAttribution:
        lc = self.llm_call
        source_units = _load_source_units(self, direction="request")
        fresh_value, cache_read_value, cache_write_value = _request_values_from_call(lc)
        total_value = fresh_value + cache_read_value + cache_write_value
        has_usage = total_value > 0
        precision = ValuePrecision.PROVIDER_REPORTED if has_usage else ValuePrecision.UNAVAILABLE
        source = ValueSource.PROVIDER_USAGE if has_usage else ValueSource.HEURISTIC
        fresh = AttributedValue(
            value=fresh_value if has_usage else None,
            unit="tokens",
            precision=precision,
            source=source,
            fill_strategy="Qoder normalized usage fresh input",
        )
        cache_read = AttributedValue(
            value=cache_read_value if has_usage else None,
            unit="tokens",
            precision=precision,
            source=source,
            fill_strategy="Qoder cache read tokens",
        )
        cache_write = AttributedValue(
            value=cache_write_value if has_usage else None,
            unit="tokens",
            precision=precision,
            source=source,
            fill_strategy="Qoder cache write tokens",
        )
        mapper = self.mapper_cls()
        accounting = mapper.build_request_accounting(
            source_units=source_units,
            fresh_input=fresh,
            cache_read=cache_read,
            cache_write=cache_write,
        )
        fresh_field = accounting["fresh_input_tokens"]
        buckets = _request_buckets_from_candidates(fresh_field.get("candidates") or [], fresh_value)
        residual_tokens = int(fresh_field.get("unattributed_tokens") or 0)
        buckets.append(_request_residual_bucket(residual_tokens, fresh_value))
        known = sum(b.tokens for b in buckets if b.key != "unlocated_residual" and b.contributes_to_total)
        coverage_value = min(known / fresh_value, 1.0) if fresh_value > 0 else 0.0
        return LLMRequestAttribution(
            agent=self.agent_name,
            model=lc.model or "unknown",
            request_id=lc.id or "unavailable",
            call_id=lc.id,
            source_label=self.source_label if source_units else "normalized source_units unavailable",
            confidence_label="高" if source_units else "低",
            raw_body_available=False,
            total_input=AttributedValue(
                value=total_value if has_usage else None,
                unit="tokens",
                precision=precision,
                source=source,
                fill_strategy="fresh + cache_read + cache_write",
            ),
            fresh_input=fresh,
            cache_read=cache_read,
            cache_write=cache_write,
            coverage=AttributedValue(
                value=coverage_value,
                unit="ratio",
                precision=ValuePrecision.ESTIMATED if source_units else ValuePrecision.UNAVAILABLE,
                source=ValueSource.TRANSCRIPT if source_units else ValueSource.HEURISTIC,
                fill_strategy="source_units candidate tokens / fresh_input",
            ),
            unknown=AttributedValue(
                value=residual_tokens,
                unit="tokens",
                precision=ValuePrecision.RESIDUAL,
                source=ValueSource.RESIDUAL,
                fill_strategy="fresh_input - source_units candidate total",
            ),
            buckets=buckets,
            captured_context_preview=_preview_from_units(source_units),
            attribution_notes=_request_notes(source_units),
            availability_rows=_request_availability_rows(has_usage, bool(source_units)),
            timing={"request_at": lc.timestamp or "—", "response_at": "—", "duration": "—"},
            accounting_attribution=accounting,
        )

    def build_response(self) -> LLMResponseAttribution:
        lc = self.llm_call
        source_units = _load_source_units(self, direction="response")
        output_value = int(lc.output_tokens or _estimate_units_tokens(source_units))
        has_provider_output = int(lc.output_tokens or 0) > 0
        total_output = AttributedValue(
            value=output_value,
            unit="tokens",
            precision=ValuePrecision.PROVIDER_REPORTED if has_provider_output else ValuePrecision.ESTIMATED,
            source=ValueSource.PROVIDER_USAGE if has_provider_output else ValueSource.TRANSCRIPT,
            fill_strategy="provider output_tokens" if has_provider_output else "source_units text estimate",
        )
        mapper = self.mapper_cls()
        accounting = mapper.build_response_accounting(source_units=source_units, total_output=total_output)
        output_field = accounting["output_tokens"]
        buckets = _response_buckets_from_candidates(output_field.get("candidates") or [], output_value)
        residual_tokens = int(output_field.get("unattributed_tokens") or 0)
        buckets.append(_response_residual_bucket(residual_tokens, output_value))
        visible_tokens = _candidate_tokens(output_field, "assistant_output")
        tool_tokens = _candidate_tokens(output_field, "tool_calls")
        reasoning_tokens = _candidate_tokens(output_field, "reasoning_output")
        metadata_tokens = _candidate_tokens(output_field, "structured_output")
        known = sum(b.tokens for b in buckets if b.key != "unknown" and b.contributes_to_total)
        coverage_value = min(known / output_value, 1.0) if output_value > 0 else 0.0
        return LLMResponseAttribution(
            agent=self.agent_name,
            model=lc.model or "unknown",
            request_id=lc.id or "unavailable",
            call_id=lc.id,
            source_label=self.source_label if source_units else "normalized source_units unavailable",
            confidence_label="高" if source_units else "低",
            raw_body_available=False,
            total_output=total_output,
            visible_text=AttributedValue(visible_tokens, "tokens", ValuePrecision.ESTIMATED, ValueSource.TRANSCRIPT, "assistant_output source_units"),
            tool_use=AttributedValue(tool_tokens, "tokens", ValuePrecision.ESTIMATED, ValueSource.TRANSCRIPT, "tool_calls source_units"),
            metadata=AttributedValue(metadata_tokens + reasoning_tokens, "tokens", ValuePrecision.ESTIMATED, ValueSource.TRANSCRIPT, "reasoning/structured source_units"),
            coverage=AttributedValue(coverage_value, "ratio", ValuePrecision.ESTIMATED if source_units else ValuePrecision.UNAVAILABLE, ValueSource.HEURISTIC, "known output candidates / output_tokens"),
            unknown=AttributedValue(residual_tokens, "tokens", ValuePrecision.RESIDUAL, ValueSource.RESIDUAL, "output_tokens - source_units candidate total"),
            finish_reason=AttributedValue(lc.finish_reason or "", "str", ValuePrecision.EXACT if lc.finish_reason else ValuePrecision.UNAVAILABLE, ValueSource.TRANSCRIPT, "llm_call.finish_reason"),
            buckets=buckets,
            blocks=lc.content_blocks or [],
            captured_output_preview=_preview_from_units(source_units),
            attribution_notes=_response_notes(source_units),
            availability_rows=_response_availability_rows(output_value > 0, bool(source_units)),
            accounting_attribution=accounting,
        )


def _load_source_units(builder: BaseAttributionBuilder, *, direction: str) -> list[dict]:
    call = _normalized_call(builder)
    units = call.get("source_units") if isinstance(call, dict) else []
    return [u for u in units or [] if isinstance(u, dict) and u.get("direction") == direction]


def _normalized_call(builder: BaseAttributionBuilder) -> dict:
    ctx_call = (builder.session_context or {}).get("normalized_call")
    if isinstance(ctx_call, dict) and ctx_call.get("source_units"):
        return ctx_call
    session_key = _session_key(builder)
    if not session_key:
        return {}
    normalized = _read_normalized_artifact(session_key)
    calls = normalized.get("calls") if isinstance(normalized, dict) else []
    call_id = str(getattr(builder.llm_call, "id", "") or "")
    if isinstance(calls, list):
        for call in calls:
            if isinstance(call, dict) and str(call.get("call_id") or "") == call_id:
                return call
    return {}


def _session_key(builder: BaseAttributionBuilder) -> str:
    session = builder.session_summary
    if session is None:
        return ""
    existing = str(getattr(session, "session_key", "") or "")
    if existing:
        return existing
    sid = str(getattr(session, "session_id", "") or "")
    return f"qoder:{sid}" if sid else ""


def _read_normalized_artifact(session_key: str) -> dict:
    from session_browser.index.schema import _get_connection, ensure_session_artifacts_schema
    from session_browser.normalized.artifacts import NORMALIZED_SESSION_ARTIFACT_TYPE, read_normalized_session_artifact

    conn = _get_connection()
    try:
        ensure_session_artifacts_schema(conn)
        row = conn.execute(
            "SELECT path FROM session_artifacts WHERE session_key = ? AND artifact_type = ?",
            (session_key, NORMALIZED_SESSION_ARTIFACT_TYPE),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return {}
    path = str(row["path"] if hasattr(row, "keys") else row[0])
    if not path or not Path(path).exists():
        return {}
    return read_normalized_session_artifact(path)


def _request_values_from_call(lc) -> tuple[int, int, int]:
    return int(lc.input_tokens or 0), int(lc.cache_read_tokens or 0), int(lc.cache_write_tokens or 0)


def _request_buckets_from_candidates(candidates: list[dict], denominator: int) -> list[RequestAttributionBucket]:
    buckets: list[RequestAttributionBucket] = []
    for candidate in candidates:
        name = str(candidate.get("candidate") or "")
        tokens = int(candidate.get("tokens") or 0)
        buckets.append(RequestAttributionBucket(
            key=_request_bucket_key(name),
            label=_candidate_label(name),
            tokens=tokens,
            percent=_pct(tokens, denominator),
            count_label=f"{len(candidate.get('sources') or [])} sources",
            precision=ValuePrecision.ESTIMATED,
            source=ValueSource.TRANSCRIPT,
            confidence_label="中高",
            summary=f"来自 normalized source_units 的 {name} candidate。",
            details={"kind": "source_units", "candidate": name, "items": candidate.get("sources") or []},
        ))
    return buckets


def _response_buckets_from_candidates(candidates: list[dict], denominator: int) -> list[ResponseAttributionBucket]:
    buckets: list[ResponseAttributionBucket] = []
    for candidate in candidates:
        name = str(candidate.get("candidate") or "")
        tokens = int(candidate.get("tokens") or 0)
        buckets.append(ResponseAttributionBucket(
            key=_response_bucket_key(name),
            label=_candidate_label(name),
            tokens=tokens,
            percent=_pct(tokens, denominator),
            count_label=f"{len(candidate.get('sources') or [])} sources",
            precision=ValuePrecision.ESTIMATED,
            source=ValueSource.TRANSCRIPT,
            confidence_label="中高",
            summary=f"来自 normalized source_units 的 {name} candidate。",
            details={"kind": "source_units", "candidate": name, "items": candidate.get("sources") or []},
        ))
    return buckets


def _request_residual_bucket(tokens: int, denominator: int) -> RequestAttributionBucket:
    return RequestAttributionBucket(
        key="unlocated_residual",
        label="未定位",
        tokens=max(tokens, 0),
        percent=_pct(tokens, denominator),
        precision=ValuePrecision.RESIDUAL,
        source=ValueSource.RESIDUAL,
        confidence_label="中",
        summary="Fresh input 减去 normalized source_units candidate 后的剩余部分。",
    )


def _response_residual_bucket(tokens: int, denominator: int) -> ResponseAttributionBucket:
    return ResponseAttributionBucket(
        key="unknown",
        label="未定位",
        tokens=max(tokens, 0),
        percent=_pct(tokens, denominator),
        precision=ValuePrecision.RESIDUAL,
        source=ValueSource.RESIDUAL,
        confidence_label="中",
        summary="Output tokens 减去 normalized source_units candidate 后的剩余部分。",
    )


def _request_bucket_key(candidate: str) -> str:
    return {
        "user_input": "current_user_input",
        "system_instructions": "instruction_context",
        "tool_definitions": "tool_definitions",
        "skill_definitions": "skill_plugin_catalog",
        "runtime_context": "runtime_environment_context",
        "conversation_history": "conversation_messages",
        "tool_results": "tool_result_context",
        "repo_context": "repository_file_context",
        "reasoning_state": "provider_conversation_state",
    }.get(candidate, "captured_runtime_context")


def _response_bucket_key(candidate: str) -> str:
    return {
        "assistant_output": "assistant_text",
        "reasoning_output": "hidden_reasoning",
        "tool_calls": "tool_call",
        "structured_output": "structured_response_block",
    }.get(candidate, "metadata")


def _candidate_label(candidate: str) -> str:
    return {
        "user_input": "当前用户输入",
        "system_instructions": "系统/项目指令",
        "tool_definitions": "工具定义",
        "skill_definitions": "Skill/Plugin 能力目录",
        "runtime_context": "运行上下文",
        "conversation_history": "对话历史",
        "tool_results": "工具结果",
        "repo_context": "仓库上下文",
        "reasoning_state": "Reasoning state",
        "assistant_output": "助手文本",
        "reasoning_output": "Reasoning 输出",
        "tool_calls": "工具调用",
        "structured_output": "结构化输出",
    }.get(candidate, candidate or "未知")


def _candidate_tokens(field: dict, candidate_name: str) -> int:
    for item in field.get("candidates") or []:
        if item.get("candidate") == candidate_name:
            return int(item.get("tokens") or 0)
    return 0


def _estimate_units_tokens(units: list[dict]) -> int:
    total = 0
    for unit in units:
        total += estimate_tokens_from_text(str(unit.get("text") or unit.get("preview") or unit.get("payload") or ""))
    return total


def _preview_from_units(units: list[dict]) -> str:
    text = "\n\n".join(str(unit.get("preview") or "") for unit in units[:3] if unit.get("preview"))
    return text[:500]


def _request_notes(units: list[dict]) -> list[str]:
    if units:
        return ["已使用 normalized source_units 作为 request 归因来源。"]
    return ["当前 call 没有 normalized source_units；请重新 scan 生成最终版 normalized artifact。"]


def _response_notes(units: list[dict]) -> list[str]:
    if units:
        return ["已使用 normalized source_units 作为 response 归因来源。"]
    return ["当前 call 没有 normalized source_units；请重新 scan 生成最终版 normalized artifact。"]


def _request_availability_rows(has_usage: bool, has_units: bool) -> list[AvailabilityRow]:
    return [
        AvailabilityRow("provider_usage", "Provider usage", True, has_usage, ValuePrecision.PROVIDER_REPORTED if has_usage else ValuePrecision.UNAVAILABLE, ValueSource.PROVIDER_USAGE if has_usage else ValueSource.HEURISTIC, "LLMCall token fields"),
        AvailabilityRow("normalized_source_units", "Normalized source units", True, has_units, ValuePrecision.EXACT if has_units else ValuePrecision.UNAVAILABLE, ValueSource.TRANSCRIPT if has_units else ValueSource.HEURISTIC, "normalized.calls[].source_units"),
    ]


def _response_availability_rows(has_output: bool, has_units: bool) -> list[AvailabilityRow]:
    return [
        AvailabilityRow("output_tokens", "Output tokens", True, has_output, ValuePrecision.PROVIDER_REPORTED if has_output else ValuePrecision.ESTIMATED, ValueSource.PROVIDER_USAGE if has_output else ValueSource.TRANSCRIPT, "LLMCall output_tokens or source_units estimate"),
        AvailabilityRow("normalized_source_units", "Normalized source units", True, has_units, ValuePrecision.EXACT if has_units else ValuePrecision.UNAVAILABLE, ValueSource.TRANSCRIPT if has_units else ValueSource.HEURISTIC, "normalized.calls[].source_units"),
    ]


def _pct(part: int, total: int) -> float:
    return round((max(part, 0) / total) * 100.0, 1) if total > 0 else 0.0
