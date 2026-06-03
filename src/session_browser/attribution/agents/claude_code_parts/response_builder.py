"""Response attribution builder for Claude Code.

Contains the `build_response` logic extracted as a standalone function
that takes the builder instance as a parameter.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from session_browser.domain.models import LLMCall, ConversationRound, SessionSummary
from session_browser.attribution.contracts import (
    AttributedValue,
    ResponseAttributionBucket,
    LLMResponseAttribution,
    ValuePrecision,
    ValueSource,
)
from session_browser.attribution.token_estimator import estimate_tokens_from_text
from session_browser.attribution.agents.claude_code_tool_schemas import (
    get_cached_schemas,
)
from session_browser.attribution.agents.claude_code_parts.utils import (
    _pct,
    tool_description,
    truncate_preview,
)

if TYPE_CHECKING:
    from session_browser.attribution.agents.base import BaseAttributionBuilder


def build_response(self: "BaseAttributionBuilder") -> LLMResponseAttribution:
    """Build response attribution for a Claude Code LLM call."""
    lc = self.llm_call

    total_output_val = lc.output_tokens or 0

    # ── Step 1: visible content estimation ─────────────────────────
    response_text = lc.response_full or ""
    visible_text_tokens = estimate_tokens_from_text(response_text)

    # Tool use blocks — include both tool definition (description + input_schema)
    # and actual call (tool_use content block) for accurate token accounting.
    schemas = get_cached_schemas()
    tool_use_schema_tokens = 0      # definition (description + input_schema)
    tool_use_call_tokens = 0        # actual tool_use block (name + input)
    tool_use_json_parts = []
    tool_use_detail_items = []

    for cb in (lc.content_blocks or []):
        if cb.get("type") == "tool_use":
            tname = cb.get("name", "unknown")
            # 1. Tool definition tokens (schema: description + input_schema)
            schema_text = json.dumps(schemas.get(tname, {}), ensure_ascii=False) if tname in schemas else ""
            schema_tok = estimate_tokens_from_text(schema_text) if schema_text else 0
            tool_use_schema_tokens += schema_tok

            # 2. Tool call tokens (actual tool_use content block)
            call_text = json.dumps(cb, ensure_ascii=False)
            call_tok = estimate_tokens_from_text(call_text)
            tool_use_call_tokens += call_tok
            tool_use_json_parts.append(call_text)

            # 3. Per-tool detail for bucket display
            tool_def = schemas.get(tname, {})
            desc_preview = tool_def.get("description", tool_description(tname))[:200]
            input_props = tool_def.get("input_schema", {}).get("properties", {})
            input_schema_preview = ""
            if input_props:
                input_schema_preview = ", ".join(list(input_props.keys())[:5])
                if len(input_props) > 5:
                    input_schema_preview += f", ...(+{len(input_props) - 5})"

            tool_use_detail_items.append({
                "name": tname,
                "tool_use_id": cb.get("id", ""),
                "schema_tokens": schema_tok,
                "call_tokens": call_tok,
                "total_tokens": schema_tok + call_tok,
                "description_preview": desc_preview,
                "input_schema_properties": input_schema_preview,
                "call_input_preview": truncate_preview(
                    json.dumps(cb.get("input", {}), ensure_ascii=False)[:200], 120,
                ),
            })

    # Fallback: use tool_calls_raw if content_blocks unavailable
    if not tool_use_json_parts and lc.tool_calls_raw:
        tool_use_call_tokens = estimate_tokens_from_text(lc.tool_calls_raw)

    tool_use_tokens = tool_use_schema_tokens + tool_use_call_tokens

    # Metadata tokens: small heuristic value for non-content fields
    metadata_tokens = 0
    if lc.finish_reason:
        metadata_tokens += 10  # finish_reason
    if lc.tool_calls_raw:
        metadata_tokens += 20  # raw structure overhead

    # ── Step 2: normalize against total ────────────────────────────
    known_sum = visible_text_tokens + tool_use_tokens + metadata_tokens

    if total_output_val > 0:
        if known_sum > total_output_val:
            # Normalize: scale down estimated parts proportionally
            scale = total_output_val / known_sum
            visible_text_tokens = max(0, int(visible_text_tokens * scale))
            tool_use_tokens = max(0, int(tool_use_tokens * scale))
            metadata_tokens = max(0, int(metadata_tokens * scale))
            known_sum = visible_text_tokens + tool_use_tokens + metadata_tokens
        unknown_val = total_output_val - known_sum
    else:
        unknown_val = 0
        total_output_val = known_sum  # fallback: estimated total

    total_output = AttributedValue(
        value=total_output_val,
        unit="tokens",
        precision=ValuePrecision.PROVIDER_REPORTED if lc.output_tokens > 0 else ValuePrecision.ESTIMATED,
        source=ValueSource.PROVIDER_USAGE if lc.output_tokens > 0 else ValueSource.HEURISTIC,
        fill_strategy="provider output_tokens" if lc.output_tokens > 0 else "sum of visible content",
    )

    # ── Step 3: buckets ────────────────────────────────────────────
    buckets = []

    if visible_text_tokens > 0:
        buckets.append(ResponseAttributionBucket(
            key="assistant_text",
            label="Assistant text",
            tokens=visible_text_tokens,
            percent=_pct(visible_text_tokens, total_output_val),
            precision=ValuePrecision.ESTIMATED,
            source=ValueSource.TRANSCRIPT,
            confidence_label="中高",
            summary="助手文本内容可从 transcript 获取，token 通过文本估算。",
        ))

    if tool_use_tokens > 0:
        # Per-tool breakdown (children, contributes_to_total=False)
        block_refs = []
        for item in tool_use_detail_items:
            buckets.append(ResponseAttributionBucket(
                key=f"tool_use:{item['name']}",
                label=f"tool_use: {item['name']}",
                tokens=item['total_tokens'],
                percent=0.0,
                precision=ValuePrecision.ESTIMATED,
                source=ValueSource.TRANSCRIPT,
                confidence_label="中",
                summary=(
                    f"工具定义 {item['schema_tokens']} tokens + "
                    f"调用参数 {item['call_tokens']} tokens"
                ),
                contributes_to_total=False,
                parent_key="tool_use",
                display_group="tool_use",
            ))
            block_refs.append(item['tool_use_id'])

        tool_use_details = {
            "kind": "tool_use",
            "total_schema_tokens": tool_use_schema_tokens,
            "total_call_tokens": tool_use_call_tokens,
            "total_items": len(tool_use_detail_items),
            "items": tool_use_detail_items,
        }
        buckets.append(ResponseAttributionBucket(
            key="tool_use",
            label="Tool use (total)",
            tokens=tool_use_tokens,
            percent=_pct(tool_use_tokens, total_output_val),
            precision=ValuePrecision.ESTIMATED,
            source=ValueSource.TRANSCRIPT,
            confidence_label="中",
            summary=(
                f"工具使用：{tool_use_schema_tokens} tokens 定义 + "
                f"{tool_use_call_tokens} tokens 调用参数，"
                f"共 {len(tool_use_detail_items)} 个工具调用。"
            ),
            block_refs=block_refs,
            contributes_to_total=True,
            details=tool_use_details,
        ))

    if metadata_tokens > 0:
        buckets.append(ResponseAttributionBucket(
            key="metadata",
            label="Metadata",
            tokens=metadata_tokens,
            percent=_pct(metadata_tokens, total_output_val),
            precision=ValuePrecision.HEURISTIC,
            source=ValueSource.SESSION_METADATA,
            confidence_label="低",
            summary="可见字段（如 finish_reason）估算。",
        ))

    buckets.append(ResponseAttributionBucket(
        key="unknown",
        label="Unknown",
        tokens=unknown_val,
        percent=_pct(unknown_val, total_output_val),
        precision=ValuePrecision.RESIDUAL,
        source=ValueSource.RESIDUAL,
        confidence_label="中",
        summary="Total output 减去已知 bucket 后的剩余部分。",
    ))

    # ── Step 4: coverage (only counts contributes_to_total=True) ─────
    known_bucket_sum = sum(
        b.tokens for b in buckets
        if b.key != "unknown" and b.contributes_to_total
    )
    coverage_val = min(known_bucket_sum / total_output_val, 1.0) if total_output_val > 0 else 0.0

    # ── Step 5: availability rows ──────────────────────────────────
    avail_rows = [
        self._avail("total_output", "Total output tokens", True,
                    precision=ValuePrecision.PROVIDER_REPORTED if lc.output_tokens > 0 else ValuePrecision.ESTIMATED,
                    source=ValueSource.PROVIDER_USAGE if lc.output_tokens > 0 else ValueSource.HEURISTIC,
                    fill_strategy="provider output_tokens" if lc.output_tokens > 0 else "sum of visible content"),
        self._avail("assistant_text_content", "Assistant text content", bool(response_text),
                    exact=True,
                    precision=ValuePrecision.TRANSCRIPT_EXACT if response_text else ValuePrecision.UNAVAILABLE,
                    source=ValueSource.TRANSCRIPT,
                    fill_strategy="direct from response_full"),
        self._avail("assistant_text_tokens", "Assistant text tokens", True,
                    exact=False,
                    precision=ValuePrecision.ESTIMATED,
                    source=ValueSource.TRANSCRIPT,
                    fill_strategy="estimated from text"),
        self._avail("tool_use_structure", "Tool use structure",
                    bool(lc.content_blocks or lc.tool_calls_raw), exact=True,
                    precision=ValuePrecision.TRANSCRIPT_EXACT,
                    source=ValueSource.TRANSCRIPT,
                    fill_strategy="from content_blocks or tool_calls_raw"),
        self._avail("tool_use_tokens", "Tool use tokens", True,
                    exact=False,
                    precision=ValuePrecision.ESTIMATED,
                    source=ValueSource.TRANSCRIPT,
                    fill_strategy="estimated from JSON"),
        self._avail("metadata", "Metadata", True,
                    exact=False,
                    precision=ValuePrecision.HEURISTIC,
                    source=ValueSource.SESSION_METADATA,
                    fill_strategy="visible field count heuristic"),
        self._avail("finish_reason", "Finish reason", bool(lc.finish_reason),
                    exact=True,
                    precision=ValuePrecision.EXACT if lc.finish_reason else ValuePrecision.UNAVAILABLE,
                    source=ValueSource.TRANSCRIPT,
                    fill_strategy="from llm_call.finish_reason"),
        self._avail("blocks_count", "Blocks count", True,
                    exact=True,
                    precision=ValuePrecision.EXACT,
                    source=ValueSource.TRANSCRIPT,
                    fill_strategy=f"{len(lc.content_blocks)} blocks" if lc.content_blocks else "0"),
        self._avail("unknown", "Unknown / residual", True, exact=False,
                    precision=ValuePrecision.RESIDUAL,
                    source=ValueSource.RESIDUAL,
                    fill_strategy="residual"),
    ]

    notes = []
    finish_r = lc.finish_reason or ""
    if finish_r and finish_r not in ("end_turn", "tool_use", "stop"):
        notes.append(f"finish_reason: {finish_r} — 可能影响归因完整性。")

    return LLMResponseAttribution(
        agent="claude_code",
        model=lc.model or "unknown",
        request_id=lc.id or "unavailable",
        call_id=lc.id,
        source_label="local logs",
        confidence_label="中高",
        raw_body_available=False,
        total_output=total_output,
        visible_text=AttributedValue(
            value=visible_text_tokens,
            unit="tokens",
            precision=ValuePrecision.ESTIMATED,
            source=ValueSource.TRANSCRIPT,
            fill_strategy="estimate_tokens_from_text(response_full)",
        ),
        tool_use=AttributedValue(
            value=tool_use_tokens,
            unit="tokens",
            precision=ValuePrecision.ESTIMATED,
            source=ValueSource.TRANSCRIPT,
            fill_strategy="estimate_tokens_from_text(serialized tool_use blocks)",
        ),
        metadata=AttributedValue(
            value=metadata_tokens,
            unit="tokens",
            precision=ValuePrecision.HEURISTIC,
            source=ValueSource.SESSION_METADATA,
            fill_strategy="visible field count heuristic",
        ),
        coverage=AttributedValue(
            value=coverage_val,
            unit="ratio",
            precision=ValuePrecision.ESTIMATED,
            source=ValueSource.HEURISTIC,
            fill_strategy="known_buckets / total_output",
        ),
        unknown=AttributedValue(
            value=unknown_val,
            unit="tokens",
            precision=ValuePrecision.RESIDUAL,
            source=ValueSource.RESIDUAL,
            fill_strategy="total - sum(known_buckets)",
        ),
        finish_reason=AttributedValue(
            value=finish_r,
            unit="str",
            precision=ValuePrecision.EXACT if finish_r else ValuePrecision.UNAVAILABLE,
            source=ValueSource.TRANSCRIPT,
            fill_strategy="from llm_call.finish_reason",
        ),
        buckets=buckets,
        blocks=lc.content_blocks or [],
        captured_output_preview=lc.response_preview or "",
        attribution_notes=notes,
        availability_rows=avail_rows,
    )
