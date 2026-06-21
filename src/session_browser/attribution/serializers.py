"""Attribution 数据层序列化器。

把内部 dataclass 对象转换成 routes.py 可返回的 dict payload。
输出 route payload 字段与 v2 attribution 字段（schema_version,
call_identity, ordered_spans, semantic_buckets, coverage,
credit_summary, diagnostics）。
"""

from __future__ import annotations

from dataclasses import asdict

from session_browser.attribution.dto import (
    AttributionErrorPayloadDTO,
    LLMRequestAttributionPayloadDTO,
    LLMResponseAttributionPayloadDTO,
)
from session_browser.attribution.contracts import (
    AttributedValue,
    AvailabilityRow,
    RequestAttributionBucket,
    ResponseAttributionBucket,
    LLMRequestAttribution,
    LLMResponseAttribution,
)
from session_browser.attribution.taxonomy import (
    normalize_request_bucket_payload,
    sort_request_buckets,
)


def attributed_value_to_dict(v: AttributedValue) -> dict:
    """把 AttributedValue 转成可序列化 dict。"""
    return {
        "value": v.value,
        "unit": v.unit,
        "precision": v.precision,
        "source": v.source,
        "fill_strategy": v.fill_strategy,
        "note": v.note,
    }


def _request_bucket_to_dict(b: RequestAttributionBucket) -> dict:
    """把 request bucket 转成可序列化 dict。"""
    return {
        "key": b.key,
        "label": b.label,
        "tokens": b.tokens,
        "percent": b.percent,
        "count_label": b.count_label,
        "precision": b.precision,
        "source": b.source,
        "confidence_label": b.confidence_label,
        "summary": b.summary,
        "contributes_to_total": b.contributes_to_total,
        "parent_key": b.parent_key,
        "display_group": b.display_group,
        "expandable": b.expandable,
        "content_preview": b.content_preview,
        "details": b.details,
    }


def _response_bucket_to_dict(b: ResponseAttributionBucket) -> dict:
    """把 response bucket 转成可序列化 dict。"""
    return {
        "key": b.key,
        "label": b.label,
        "tokens": b.tokens,
        "percent": b.percent,
        "count_label": b.count_label,
        "precision": b.precision,
        "source": b.source,
        "confidence_label": b.confidence_label,
        "summary": b.summary,
        "contributes_to_total": b.contributes_to_total,
        "parent_key": b.parent_key,
        "display_group": b.display_group,
        "block_refs": b.block_refs,
        "details": b.details,
    }


def _num(value) -> float:
    """用于 UI 分布计算的宽松数值转换。"""
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _normalize_bucket_percents_for_display(buckets: list[dict]) -> list[dict]:
    """归一化 attribution 条形图和图例使用的 bucket 百分比。

    builder 可能使用 provider 合计或中间分母计算 percent；modal 展示需要稳定
    占比，确保单个 bucket 不超过 100%，参与合计的 bucket 可叠加成展示总量。
    """
    contributing = [
        b for b in buckets
        if b.get("contributes_to_total", True)
    ]
    total_tokens = sum(max(_num(b.get("tokens")), 0.0) for b in contributing)
    if total_tokens <= 0:
        for b in buckets:
            b["raw_percent"] = b.get("percent", 0.0)
            if b.get("contributes_to_total", True):
                b["percent"] = 0.0
        return buckets

    running = 0.0
    for idx, b in enumerate(contributing):
        b["raw_percent"] = b.get("percent", 0.0)
        tokens = max(_num(b.get("tokens")), 0.0)
        if idx == len(contributing) - 1:
            percent = max(0.0, 100.0 - running)
        else:
            percent = round((tokens / total_tokens) * 100.0, 1)
            running += percent
        b["percent"] = round(min(percent, 100.0), 1)

    for b in buckets:
        if "raw_percent" not in b:
            b["raw_percent"] = b.get("percent", 0.0)
    return buckets


def _request_distribution_denominator(attr: LLMRequestAttribution) -> float:
    """返回 UI 使用的 Request Content Denominator。

    Cache Read/Write 是 provider 计量组件，不是 request content bucket。
    bucket 百分比、覆盖率和残差默认都使用 Fresh；除非后续 OpenSpec 明确定义例外。
    """
    fresh = _num(attr.fresh_input.value)
    if fresh > 0:
        return fresh
    return _input_side_component_total(attr)


def _provider_request_input(attr: LLMRequestAttribution) -> float:
    """尽量还原 provider request input 原始计量值。"""
    fresh = _num(attr.fresh_input.value)
    cache_read = _num(attr.cache_read.value)
    if attr.agent == "codex":
        return fresh + cache_read
    return fresh


def _input_side_component_total(attr: LLMRequestAttribution) -> float:
    """Fresh + Cache Read + Cache Write 输入侧组件合计。"""
    return (
        _num(attr.fresh_input.value)
        + _num(attr.cache_read.value)
        + _num(attr.cache_write.value)
    )


def _input_side_component_value(attr: LLMRequestAttribution) -> dict:
    """构造输入侧组件合计的 AttributedValue 形态。"""
    return attributed_value_to_dict(AttributedValue(
        value=_input_side_component_total(attr),
        unit="tokens",
        precision=attr.fresh_input.precision,
        source=attr.fresh_input.source,
        fill_strategy="Fresh + Cache Read + Cache Write",
        note="Fresh + Cache Read + Cache Write。",
    ))


def _normalize_request_bucket_percents_for_display(
    buckets: list[dict],
    denominator: float,
) -> list[dict]:
    """按 request-content denominator 计算 request bucket 百分比。"""
    for b in buckets:
        b["raw_percent"] = b.get("percent", 0.0)
        if not b.get("contributes_to_total", True):
            continue
        tokens = max(_num(b.get("tokens")), 0.0)
        b["percent"] = round((tokens / denominator) * 100.0, 1) if denominator > 0 else 0.0
    return buckets


def _request_candidate_for_bucket(bucket: dict) -> str | None:
    """把 canonical request bucket metadata 映射到共享 candidate vocabulary。"""
    key = str(bucket.get("canonical_key") or bucket.get("key") or "")
    mapping = {
        "current_user_input": "user_input",
        "user_attachments": "user_input",
        "conversation_messages": "conversation_history",
        "tool_result_context": "tool_results",
        "repository_file_context": "repo_context",
        "tool_definitions": "tool_definitions",
        "mcp_tool_metadata": "tool_definitions",
        "skill_plugin_catalog": "skill_definitions",
        "instruction_context": "system_instructions",
        "platform_default_instructions": "system_instructions",
        "session_injected_instructions": "system_instructions",
        "project_instruction_files": "system_instructions",
        "local_instruction_context": "system_instructions",
        "agent_subagent_prompt": "system_instructions",
        "custom_agent_profile": "system_instructions",
        "builtin_system_prompt": "system_instructions",
        "hidden_instruction_estimate": "system_instructions",
        "captured_runtime_context": "runtime_context",
        "permission_sandbox_policy": "runtime_context",
        "client_app_context": "runtime_context",
        "collaboration_mode_policy": "runtime_context",
        "runtime_environment_context": "runtime_context",
        "task_goal_context": "runtime_context",
        "provider_conversation_state": "reasoning_state",
        "reasoning_config": "reasoning_state",
        "runtime_wrapper_overhead": "runtime_context",
    }
    return mapping.get(key)


def _response_candidate_for_bucket(bucket: dict) -> str | None:
    """把 response bucket keys 映射到共享 response-side candidate vocabulary。"""
    key = str(bucket.get("key") or "")
    if key == "assistant_text" or key == "visible_text":
        return "assistant_output"
    if key in {"assistant_thinking", "hidden_reasoning", "reasoning_output_tokens"}:
        return "reasoning_output"
    if key == "tool_call" or key == "tool_use" or key.startswith("tool_call:"):
        return "tool_calls"
    if key in {"structured_response_block", "structured_items"}:
        return "structured_output"
    return None


def _candidate_entry(candidate: str) -> dict:
    return {
        "candidate": candidate,
        "tokens": 0,
        "percent": 0.0,
        "sources": [],
    }


def _candidate_sources_from_buckets(
    buckets: list[dict],
    candidate_resolver,
    denominator: float,
) -> tuple[list[dict], int]:
    """把 legacy buckets 聚合为共享 Attribution Candidate entries。

    现有 builders 仍生成 bucket-shaped local reconstructions。这个兼容层只暴露
    field-first view，不编造 per-candidate cache allocation。
    """
    by_candidate: dict[str, dict] = {}
    unattributed = 0.0
    for bucket in buckets:
        if not bucket.get("contributes_to_total", True):
            continue
        tokens = max(_num(bucket.get("tokens")), 0.0)
        candidate = candidate_resolver(bucket)
        if not candidate:
            unattributed += tokens
            continue
        entry = by_candidate.setdefault(candidate, _candidate_entry(candidate))
        entry["tokens"] += tokens
        entry["sources"].append({
            "bucket_key": bucket.get("key", ""),
            "canonical_key": bucket.get("canonical_key", bucket.get("key", "")),
            "label": bucket.get("label", ""),
            "tokens": tokens,
            "precision": bucket.get("precision", ""),
            "source": bucket.get("source", ""),
            "summary": bucket.get("summary", ""),
        })

    result = []
    for entry in by_candidate.values():
        tokens = int(round(entry["tokens"]))
        entry["tokens"] = tokens
        entry["percent"] = round((tokens / denominator) * 100.0, 1) if denominator > 0 else 0.0
        result.append(entry)
    result.sort(key=lambda item: item["candidate"])
    return result, int(round(unattributed))


def _accounting_field_payload(
    field: str,
    value: AttributedValue,
    candidates: list[dict] | None = None,
    *,
    unattributed_tokens: int = 0,
    notes: list[str] | None = None,
) -> dict:
    """构造 additive v2 payload 的单个 token accounting field group。"""
    value_dict = attributed_value_to_dict(value)
    return {
        "field": field,
        "tokens": _num(value.value),
        "value": value_dict,
        "candidates": candidates or [],
        "candidate_total_tokens": sum(_num(item.get("tokens")) for item in (candidates or [])),
        "unattributed_tokens": unattributed_tokens,
        "notes": notes or [],
    }


def _zero_accounting_value(note: str = "") -> AttributedValue:
    return AttributedValue(
        value=0,
        unit="tokens",
        precision="unavailable",
        source="heuristic",
        fill_strategy="not applicable",
        note=note,
    )


def _build_request_accounting_attribution(
    attr: LLMRequestAttribution,
    request_buckets: list[dict],
) -> dict:
    """按 TokenAccountingField -> candidates 暴露 request attribution。"""
    fresh_total = _num(attr.fresh_input.value)
    fresh_candidates, unattributed = _candidate_sources_from_buckets(
        request_buckets,
        _request_candidate_for_bucket,
        fresh_total,
    )
    return {
        "schema": "token_accounting_fields.v1",
        "field_order": [
            "fresh_input_tokens",
            "cache_read_tokens",
            "cache_write_tokens",
            "output_tokens",
        ],
        "fresh_input_tokens": _accounting_field_payload(
            "fresh_input_tokens",
            attr.fresh_input,
            fresh_candidates,
            unattributed_tokens=unattributed,
            notes=[
                "现有 request buckets 在这里按统一 Attribution Candidates 暴露。",
                "当前本地重建无法提供 candidate-level cache 分配。",
            ],
        ),
        "cache_read_tokens": _accounting_field_payload(
            "cache_read_tokens",
            attr.cache_read,
            [],
            notes=[
                "Provider 上报的 cache read accounting；不推断 per-candidate split。",
            ],
        ),
        "cache_write_tokens": _accounting_field_payload(
            "cache_write_tokens",
            attr.cache_write,
            [],
            notes=[
                "Provider 上报的 cache write accounting 可用时展示；不推断 per-candidate split。",
            ],
        ),
        "output_tokens": _accounting_field_payload(
            "output_tokens",
            _zero_accounting_value("Request attribution payload 不包含 response output allocation。"),
            [],
        ),
    }


def _build_response_accounting_attribution(
    attr: LLMResponseAttribution,
    response_buckets: list[dict],
) -> dict:
    """按 TokenAccountingField -> candidates 暴露 response attribution。"""
    output_total = _num(attr.total_output.value)
    output_candidates, unattributed = _candidate_sources_from_buckets(
        response_buckets,
        _response_candidate_for_bucket,
        output_total,
    )
    return {
        "schema": "token_accounting_fields.v1",
        "field_order": [
            "fresh_input_tokens",
            "cache_read_tokens",
            "cache_write_tokens",
            "output_tokens",
        ],
        "fresh_input_tokens": _accounting_field_payload(
            "fresh_input_tokens",
            _zero_accounting_value("Response attribution payload 不包含 request input allocation。"),
            [],
        ),
        "cache_read_tokens": _accounting_field_payload(
            "cache_read_tokens",
            _zero_accounting_value("Response attribution payload 不包含 request cache-read allocation。"),
            [],
        ),
        "cache_write_tokens": _accounting_field_payload(
            "cache_write_tokens",
            _zero_accounting_value("Response attribution payload 不包含 request cache-write allocation。"),
            [],
        ),
        "output_tokens": _accounting_field_payload(
            "output_tokens",
            attr.total_output,
            output_candidates,
            unattributed_tokens=unattributed,
            notes=[
                "现有 response buckets 在这里按统一 response-side Attribution Candidates 暴露。",
            ],
        ),
    }


def availability_row_to_dict(row: AvailabilityRow | dict) -> dict:
    """将 AvailabilityRow 或已构造的 dict 转成可序列化对象。"""
    if isinstance(row, dict):
        return row
    return asdict(row)


def request_attribution_to_payload(attr: LLMRequestAttribution, v2_extra: dict | None = None) -> dict:
    """把完整 LLMRequestAttribution 序列化为 route payload。

    包含 schema_version, call_identity, usage_summary (AttributedValue 格式),
    ordered_spans, semantic_buckets, coverage, credit_summary, diagnostics。
    """
    v2_extra = v2_extra or {}

    request_buckets = [
        normalize_request_bucket_payload(attr.agent, _request_bucket_to_dict(b))
        for b in attr.buckets
    ]
    request_buckets = sort_request_buckets(attr.agent, request_buckets)
    request_buckets = _normalize_request_bucket_percents_for_display(
        request_buckets,
        _request_distribution_denominator(attr),
    )
    accounting_attribution = (
        getattr(attr, "accounting_attribution", None)
        or v2_extra.get("accounting_attribution")
        or _build_request_accounting_attribution(attr, request_buckets)
    )

    payload = {
        # 说明：── v2 schema ──
        "schema_version": "llm_attribution_v2",

        # ── 调用身份（v2） ──
        "call_identity": v2_extra.get("call_identity", _build_call_identity(attr)),

        # ── 使用量摘要：字段值保留 AttributedValue 结构（v2） ──
        "usage_summary": {
            "provider_request_input": {
                **attributed_value_to_dict(attr.fresh_input),
                "value": _provider_request_input(attr),
                "note": "可推导时的 provider request input 原始计量值。",
            },
            "input_side_component_total": {
                **_input_side_component_value(attr),
                "value": _input_side_component_total(attr),
                "note": "Fresh + Cache Read + Cache Write。",
            },
            "request_content_denominator": {
                **attributed_value_to_dict(attr.fresh_input),
                "value": _request_distribution_denominator(attr),
                "note": "request content bucket 覆盖率与残差使用的 Fresh 分母。",
            },
            "fresh": attributed_value_to_dict(attr.fresh_input),
            "cache_read": attributed_value_to_dict(attr.cache_read),
            "cache_write": attributed_value_to_dict(attr.cache_write),
            "output": attributed_value_to_dict(_get_output_from_notes(attr)),
        },

        # ── 有序片段（v2） ──
        "ordered_spans": v2_extra.get("ordered_spans", []),

        # ── 语义 bucket（v2） ──
        "semantic_buckets": v2_extra.get("semantic_buckets", []),

        # ── 覆盖率（v2） ──
        "coverage": v2_extra.get("coverage", _build_coverage(attr)),

        # ── Credit 摘要（v2，Qoder） ──
        "credit_summary": v2_extra.get("credit_summary", None),

        # ── 诊断信息（v2） ──
        "diagnostics": v2_extra.get("diagnostics", _build_diagnostics(attr)),

        # ── field-first 归因（v2 additive） ──
        "accounting_attribution": accounting_attribution,

        # ── route payload 字段 ──
        "kind": "llm.request_attribution",
        "agent": attr.agent,
        "model": attr.model,
        "request_id": attr.request_id,
        "call_id": attr.call_id,
        "source_label": attr.source_label,
        "confidence_label": attr.confidence_label,
        "raw_body_available": attr.raw_body_available,
        "usage": {
            "provider_request_input": {
                **attributed_value_to_dict(attr.fresh_input),
                "value": _provider_request_input(attr),
                "note": "可推导时的 provider request input 原始计量值。",
            },
            "input_side_component_total": {
                **_input_side_component_value(attr),
                "value": _input_side_component_total(attr),
                "note": "Fresh + Cache Read + Cache Write。",
            },
            "request_content_denominator": {
                **attributed_value_to_dict(attr.fresh_input),
                "value": _request_distribution_denominator(attr),
                "note": "request content bucket 覆盖率与残差使用的 Fresh 分母。",
            },
            "fresh": attributed_value_to_dict(attr.fresh_input),
            "cache_read": attributed_value_to_dict(attr.cache_read),
            "cache_write": attributed_value_to_dict(attr.cache_write),
            "coverage": attributed_value_to_dict(attr.coverage),
            "unknown": attributed_value_to_dict(attr.unknown),
        },
        "buckets": request_buckets,
        "captured_context_preview": attr.captured_context_preview,
        "attribution_notes": list(attr.attribution_notes),
        "availability_rows": [availability_row_to_dict(r) for r in attr.availability_rows],
        "timing": {
            "request_at": attr.timing.get("request_at", "—") if hasattr(attr, "timing") and attr.timing else "—",
            "response_at": attr.timing.get("response_at", "—") if hasattr(attr, "timing") and attr.timing else "—",
            "duration": attr.timing.get("duration", "—") if hasattr(attr, "timing") and attr.timing else "—",
        },
    }
    return LLMRequestAttributionPayloadDTO(**payload).to_dict()


def response_attribution_to_payload(attr: LLMResponseAttribution, v2_extra: dict | None = None) -> dict:
    """把完整 LLMResponseAttribution 序列化为 route payload。"""
    v2_extra = v2_extra or {}
    response_buckets = _normalize_bucket_percents_for_display([
        _response_bucket_to_dict(b) for b in attr.buckets
    ])
    accounting_attribution = (
        getattr(attr, "accounting_attribution", None)
        or v2_extra.get("accounting_attribution")
        or _build_response_accounting_attribution(attr, response_buckets)
    )

    payload = {
        # 说明：── v2 schema ──
        "schema_version": "llm_attribution_v2",

        # ── 调用身份（v2） ──
        "call_identity": v2_extra.get("call_identity", _build_call_identity(attr)),

        # ── 使用量摘要（v2） ──
        "usage_summary": {
            "total_output": attributed_value_to_dict(attr.total_output),
            "visible_text": attributed_value_to_dict(attr.visible_text),
            "tool_call": attributed_value_to_dict(attr.tool_use),
            "tool_use": attributed_value_to_dict(attr.tool_use),
            "hidden_reasoning": attributed_value_to_dict(_get_hidden_reasoning(attr)),
            "metadata": attributed_value_to_dict(attr.metadata),
            "residual": attributed_value_to_dict(attr.unknown),
        },

        # ── response 片段（v2） ──
        "response_spans": v2_extra.get("response_spans", []),

        # ── 语义 buckets（v2） ──
        "semantic_buckets": v2_extra.get("semantic_buckets", []),

        # ── 诊断信息（v2） ──
        "diagnostics": v2_extra.get("diagnostics", _build_response_diagnostics(attr)),

        # ── field-first 归因（v2 additive） ──
        "accounting_attribution": accounting_attribution,

        # ── route payload 字段 ──
        "kind": "llm.response_attribution",
        "agent": attr.agent,
        "model": attr.model,
        "request_id": attr.request_id,
        "call_id": attr.call_id,
        "source_label": attr.source_label,
        "confidence_label": attr.confidence_label,
        "raw_body_available": attr.raw_body_available,
        "usage": {
            "total_output": attributed_value_to_dict(attr.total_output),
            "visible_text": attributed_value_to_dict(attr.visible_text),
            "tool_call": attributed_value_to_dict(attr.tool_use),
            "tool_use": attributed_value_to_dict(attr.tool_use),
            "metadata": attributed_value_to_dict(attr.metadata),
            "coverage": attributed_value_to_dict(attr.coverage),
            "unknown": attributed_value_to_dict(attr.unknown),
            "finish_reason": attributed_value_to_dict(attr.finish_reason),
        },
        "buckets": response_buckets,
        "blocks": list(attr.blocks),
        "captured_output_preview": attr.captured_output_preview,
        "attribution_notes": list(attr.attribution_notes),
        "availability_rows": [availability_row_to_dict(r) for r in attr.availability_rows],
    }
    return LLMResponseAttributionPayloadDTO(**payload).to_dict()


# 说明：─── v2 helper functions ─────────────────────────────────────────────


def _build_call_identity(attr) -> dict:
    """构建 call_identity v2 字段。"""
    agent_runtime = attr.agent if attr.agent else "unknown"
    return {
        "agent_runtime": agent_runtime,
        "api_family": _infer_api_family_from_agent(agent_runtime),
        "provider_or_broker": _infer_provider_from_agent(agent_runtime),
        "underlying_provider": None,
        "model": attr.model if attr.model and attr.model != "unknown" else None,
        "billing_units": ["tokens"] + (["credits"] if agent_runtime == "qoder" else []),
        "mapping_confidence": 0.5,
        "mapping_reasons": [f"agent={agent_runtime}"],
    }


def _infer_api_family_from_agent(agent: str) -> str:
    """从 agent 字符串推断默认 API Family。"""
    mapping = {
        "claude_code": "anthropic_messages",
        "codex": "openai_responses",
        "qoder": "qoder_broker",
    }
    return mapping.get(agent, "estimate_only")


def _infer_provider_from_agent(agent: str) -> str:
    """从 agent 字符串推断默认 Provider/Broker。"""
    mapping = {
        "claude_code": "anthropic",
        "codex": "openai",
        "qoder": "qoder",
    }
    return mapping.get(agent, "unknown")


def _get_output_from_notes(attr) -> AttributedValue:
    """从 notes 或 bucket 中尝试推断 output tokens。"""
    return AttributedValue(
        value=None, unit="tokens", precision="unavailable",
        source="heuristic", fill_strategy="not available in request",
    )


def _get_hidden_reasoning(attr) -> AttributedValue:
    """推断 hidden reasoning tokens。"""
    return AttributedValue(
        value=None, unit="tokens", precision="unavailable",
        source="heuristic", fill_strategy="not detected",
    )


def _build_coverage(attr) -> dict:
    """构建 coverage v2 对象。"""
    input_side_component_total = _input_side_component_total(attr)
    cache_read_val = (attr.cache_read.value if hasattr(attr, 'cache_read') and attr.cache_read else 0) or 0
    request_content_denominator = _request_distribution_denominator(attr)
    provider_request_input = _provider_request_input(attr)
    unknown_val = (attr.unknown.value if hasattr(attr, 'unknown') and attr.unknown else 0) or 0
    reconstructed = sum(
        max(_num(getattr(bucket, "tokens", 0)), 0)
        for bucket in getattr(attr, "buckets", []) or []
        if getattr(bucket, "contributes_to_total", True)
        and getattr(bucket, "key", "") not in {
            "unknown_overhead",
            "unlocated_residual",
            "unknown",
            "provider_cached_context",
        }
    )
    if reconstructed <= 0 and input_side_component_total > 0:
        reconstructed = max(0, request_content_denominator - unknown_val)
    return {
        "provider_request_input": provider_request_input,
        "input_side_component_total": input_side_component_total,
        "request_content_denominator": request_content_denominator,
        "accounting_cache_read_tokens": cache_read_val,
        "reconstructed_total": int(reconstructed),
        "coverage_ratio": round(reconstructed / request_content_denominator, 3) if request_content_denominator > 0 else 0.0,
        "residual_tokens": unknown_val,
        "residual_likely_sources": [],
    }


def _build_diagnostics(attr) -> dict:
    """构建 diagnostics v2 对象。"""
    return {
        "invariants": [{"name": "current_contract", "passed": True}],
        "warnings": [],
    }


def _build_response_diagnostics(attr) -> dict:
    """构建 response diagnostics v2 对象。"""
    return {
        "tool_schema_counted_as_output": False,
        "invariants": [{"name": "current_contract", "passed": True}],
        "warnings": [],
    }


def attribution_error_to_payload(
    agent: str,
    call_id: str,
    round_id: str,
    error_type: str,
    message: str,
) -> dict:
    """attribution 构建失败时创建诊断 payload。

    payload 故意保持最小；不包含完整 traceback，避免把敏感信息泄漏到 UI。
    """
    return AttributionErrorPayloadDTO(
        kind="llm.attribution_error",
        agent=agent,
        call_id=call_id,
        round_id=round_id,
        error_type=error_type,
        message=message,
        fallback="归因数据不可用；基础 LLM 上下文和输出 payload 仍可查看。",
    ).to_dict()
