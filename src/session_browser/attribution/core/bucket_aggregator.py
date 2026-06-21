"""Aggregate ordered attribution spans into semantic display buckets."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from session_browser.attribution.core.models import PromptSpan

SEMANTIC_BUCKET_DEFS: dict[str, dict[str, Any]] = {
    'current_user_prompt': {'label': '当前用户输入', 'kinds': {'user_text'}},
    'conversation_history': {'label': '对话历史', 'kinds': {'assistant_text', 'prior_user_text'}},
    'tool_results': {'label': '工具结果', 'kinds': {'tool_result'}},
    'tool_definitions': {'label': '工具定义', 'kinds': {'tool_schema'}},
    'local_instructions': {'label': '本地指令', 'kinds': {'system_prompt'}},
    'project_rules': {'label': '项目规则', 'kinds': {'repo_context', 'agent_prompt'}},
    'agent_prompt': {'label': 'Agent 内置 prompt', 'kinds': {'agent_prompt'}},
    'mcp_tools': {'label': 'MCP 工具', 'kinds': {'mcp_config'}},
    'provider_wrapper': {'label': 'Provider wrapper', 'kinds': set()},
    'unknown_residual': {'label': '未定位/残余', 'kinds': {'unknown_residual'}},
}


def aggregate_buckets(
    spans: list[PromptSpan],
    total_input: int = 0,
) -> list[dict[str, Any]]:
    """Aggregate spans into semantic buckets for attribution UI rendering.

    Attribution normalizers call this after building ordered spans. The function keeps
    the weakest precision and lowest confidence for each bucket so the UI does not
    overstate attribution certainty.

    Args:
        spans: Ordered prompt or response spans to group by semantic kind.
        total_input: Provider or reconstructed total used to calculate percentages.

    Returns:
        Bucket dictionaries containing key, label, tokens, percent, precision, source,
        confidence, span ids, and whether the bucket contributes to totals.
    """
    bucket_map: dict[str, dict[str, Any]] = {}

    for span in spans:
        bucket_key = _span_to_bucket_key(span.semantic_kind)
        if bucket_key not in bucket_map:
            defn = SEMANTIC_BUCKET_DEFS.get(bucket_key, {})
            bucket_map[bucket_key] = {
                'key': bucket_key,
                'label': defn.get('label', bucket_key),
                'tokens': 0,
                'span_ids': [],
                'precision': span.precision,
                'source': 'reconstructed',
                'confidence': span.confidence,
                'contributes_to_total': span.contributes_to_input,
            }

        bucket = bucket_map[bucket_key]
        bucket['tokens'] += span.token_estimate
        bucket['span_ids'].append(span.span_id)
        if _precision_weaker(span.precision, bucket['precision']):
            bucket['precision'] = span.precision
        bucket['confidence'] = min(bucket['confidence'], span.confidence)

    buckets = list(bucket_map.values())
    for bucket in buckets:
        tokens = bucket['tokens']
        bucket['percent'] = round(tokens / total_input * 100, 1) if total_input > 0 else 0.0

    return buckets


def _span_to_bucket_key(semantic_kind: str) -> str:
    """Map one span semantic kind to a stable bucket key.

    Args:
        semantic_kind: Semantic kind emitted by evidence collectors or normalizers.

    Returns:
        Bucket key used by attribution serializers and UI cards.
    """
    for key, defn in SEMANTIC_BUCKET_DEFS.items():
        if semantic_kind in defn.get('kinds', set()):
            return key
    if semantic_kind == 'unknown_residual':
        return 'unknown_residual'
    return 'unknown_residual'


def _precision_weaker(new_prec: str, existing_prec: str) -> bool:
    """Determine whether a new precision label is weaker than the existing label.

    Args:
        new_prec: Precision label carried by the span being merged.
        existing_prec: Precision label already stored on the bucket.

    Returns:
        True when the new precision should replace the existing bucket precision.
    """
    prec_order = [
        'exact',
        'provider_reported',
        'transcript_exact',
        'extracted',
        'estimated',
        'heuristic',
        'residual',
        'unavailable',
    ]
    new_idx = prec_order.index(new_prec) if new_prec in prec_order else 99
    exist_idx = prec_order.index(existing_prec) if existing_prec in prec_order else 99
    return new_idx > exist_idx
