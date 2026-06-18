"""Bucket Aggregator：PromptSpan -> semantic bucket 聚合。

将 ordered spans 按语义类别聚合为 buckets。
"""

from __future__ import annotations

from session_browser.attribution.core.models import PromptSpan


# 语义 bucket 定义
SEMANTIC_BUCKET_DEFS: dict[str, dict] = {
    "current_user_prompt": {"label": "当前用户输入", "kinds": {"user_text"}},
    "conversation_history": {"label": "对话历史", "kinds": {"assistant_text", "prior_user_text"}},
    "tool_results": {"label": "工具结果", "kinds": {"tool_result"}},
    "tool_definitions": {"label": "工具定义", "kinds": {"tool_schema"}},
    "local_instructions": {"label": "本地指令", "kinds": {"system_prompt"}},
    "project_rules": {"label": "项目规则", "kinds": {"repo_context", "agent_prompt"}},
    "agent_prompt": {"label": "Agent 内置 prompt", "kinds": {"agent_prompt"}},
    "mcp_tools": {"label": "MCP 工具", "kinds": {"mcp_config"}},
    "provider_wrapper": {"label": "Provider wrapper", "kinds": set()},
    "unknown_residual": {"label": "未定位/残余", "kinds": {"unknown_residual"}},
}


def aggregate_buckets(
    spans: list[PromptSpan],
    total_input: int = 0,
) -> list[dict]:
    """将 spans 聚合为 semantic buckets。

    Returns:
        bucket dict 列表，每个包含 key, label, tokens, percent, precision, source,
        confidence, span_ids, contributes_to_total
    """
    # 按 bucket key 聚合
    bucket_map: dict[str, dict] = {}

    for span in spans:
        bucket_key = _span_to_bucket_key(span.semantic_kind)
        if bucket_key not in bucket_map:
            defn = SEMANTIC_BUCKET_DEFS.get(bucket_key, {})
            bucket_map[bucket_key] = {
                "key": bucket_key,
                "label": defn.get("label", bucket_key),
                "tokens": 0,
                "span_ids": [],
                "precision": span.precision,
                "source": "reconstructed",
                "confidence": span.confidence,
                "contributes_to_total": span.contributes_to_input,
            }

        bucket = bucket_map[bucket_key]
        bucket["tokens"] += span.token_estimate
        bucket["span_ids"].append(span.span_id)
        # 保留最低精度和置信度
        if _precision_weaker(span.precision, bucket["precision"]):
            bucket["precision"] = span.precision
        bucket["confidence"] = min(bucket["confidence"], span.confidence)

    buckets = list(bucket_map.values())

    # 计算百分比
    for b in buckets:
        b["percent"] = round(b["tokens"] / total_input * 100, 1) if total_input > 0 else 0.0

    return buckets


def _span_to_bucket_key(semantic_kind: str) -> str:
    """将 semantic_kind 映射到 bucket key。"""
    for key, defn in SEMANTIC_BUCKET_DEFS.items():
        if semantic_kind in defn.get("kinds", set()):
            return key
    if semantic_kind == "unknown_residual":
        return "unknown_residual"
    return "unknown_residual"


def _precision_weaker(new_prec: str, existing_prec: str) -> bool:
    """判断 new_prec 是否比 existing_prec 更弱。"""
    prec_order = [
        "exact", "provider_reported", "transcript_exact",
        "extracted", "estimated", "heuristic", "residual", "unavailable",
    ]
    new_idx = prec_order.index(new_prec) if new_prec in prec_order else 99
    exist_idx = prec_order.index(existing_prec) if existing_prec in prec_order else 99
    return new_idx > exist_idx
