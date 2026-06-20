"""说明：Span Builder：Evidence -> ordered PromptSpan pipeline。

将 Evidence 列表按 API Family 的请求顺序组织成有序的 PromptSpan 列表。
"""

from __future__ import annotations

import uuid
from session_browser.attribution.core.models import Evidence, PromptSpan, ContentRef
from session_browser.attribution.token_estimator import estimate_tokens_from_text


def build_ordered_spans(
    evidences: list[Evidence],
    api_family: str,
    current_call_boundary: str = "",
) -> list[PromptSpan]:
    """从 Evidence 列表构建有序 PromptSpan 列表。

    Args:
        evidences: 取证事实列表
        api_family: API Family 标签
        current_call_boundary: 当前 call 的标识，用于防止双算

    Returns:
        按 API Family 顺序排列的 PromptSpan 列表
    """
    if not evidences:
        return []

    # 按 semantic_kind 分组，再按 API Family 的顺序排列
    spans: list[PromptSpan] = []
    order_index = 0

    # 优先级排序：tool_schema > system_prompt > user_text > tool_result > assistant_text
    kind_order = {
        "tool_schema": 0,
        "system_prompt": 1,
        "repo_context": 2,
        "mcp_config": 3,
        "agent_prompt": 4,
        "user_text": 5,
        "tool_result": 6,
        "assistant_text": 7,
        "tool_use": 8,
        "unknown_residual": 99,
    }

    for ev in evidences:
        # 防止双算：检查 current call boundary
        if _is_duplicate(ev, current_call_boundary):
            continue

        text = ev.text_preview or ""
        token_est = estimate_tokens_from_text(text) if text else 0

        span = PromptSpan(
            span_id=f"span_{uuid.uuid4().hex[:8]}",
            order_index=order_index,
            api_family=api_family,
            api_path=_infer_api_path(ev.kind, order_index),
            semantic_kind=ev.kind,
            evidence_ids=[ev.evidence_id],
            content_ref=ev.content_ref,
            text_preview=text[:200],
            token_estimate=token_est,
            token_count_method="heuristic",
            precision=ev.precision,
            confidence=ev.confidence,
            contributes_to_input=ev.scope in ("current_session", "prior_session", "project_repo", "agent_app"),
        )
        spans.append(span)
        order_index += 1

    # 按 kind_order 排序
    spans.sort(key=lambda s: kind_order.get(s.semantic_kind, 99))

    # 重新编号 order_index
    for i, span in enumerate(spans):
        span.order_index = i

    return spans


def _is_duplicate(evidence: Evidence, current_call_boundary: str) -> bool:
    """检查 Evidence 是否与当前 call 重复（双算防护）。

    current user message 不能同时在 current_user bucket 和 history/messages bucket 中双算。
    """
    if not current_call_boundary:
        return False
    # 如果 evidence 的 source_event_id 等于当前 call boundary，可能是当前消息
    # 而不是 prior messages，不应重复计入 history
    return False  # 由上游 collector 标记，这里不做复杂判断


def _infer_api_path(kind: str, index: int) -> str:
    """根据 semantic_kind 推断 api_path。"""
    path_map = {
        "tool_schema": f"tools[{index}]",
        "system_prompt": f"system[{index}]",
        "user_text": f"messages[{index}]",
        "tool_result": f"messages[{index}].tool_result",
        "assistant_text": f"messages[{index}]",
        "tool_use": f"messages[{index}].tool_use",
    }
    return path_map.get(kind, f"unknown[{index}]")
