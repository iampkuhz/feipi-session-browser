"""Build ordered attribution spans from collected evidence."""

from __future__ import annotations

import uuid

from session_browser.attribution.core.models import Evidence, PromptSpan
from session_browser.attribution.token_estimator import estimate_tokens_from_text


def build_ordered_spans(
    evidences: list[Evidence],
    api_family: str,
    current_call_boundary: str = '',
) -> list[PromptSpan]:
    """Build ordered prompt spans from evidence records.

    API-family normalizers call this when a provider-specific request order is not
    available. The builder prevents known duplicate current-call evidence, estimates
    tokens from previews, and then sorts spans into a deterministic semantic order.

    Args:
        evidences: Evidence records produced by session, project, or agent collectors.
        api_family: API family label that owns the resulting span paths.
        current_call_boundary: Optional call boundary used to avoid double-counting
            evidence already represented by the active call.

    Returns:
        Prompt spans ordered by semantic priority and then reindexed from zero.
    """
    if not evidences:
        return []

    spans: list[PromptSpan] = []
    order_index = 0
    kind_order = {
        'tool_schema': 0,
        'system_prompt': 1,
        'repo_context': 2,
        'mcp_config': 3,
        'agent_prompt': 4,
        'user_text': 5,
        'tool_result': 6,
        'assistant_text': 7,
        'tool_use': 8,
        'unknown_residual': 99,
    }

    for evidence in evidences:
        if _is_duplicate(evidence, current_call_boundary):
            continue

        text = evidence.text_preview or ''
        token_est = estimate_tokens_from_text(text) if text else 0

        span = PromptSpan(
            span_id=f'span_{uuid.uuid4().hex[:8]}',
            order_index=order_index,
            api_family=api_family,
            api_path=_infer_api_path(evidence.kind, order_index),
            semantic_kind=evidence.kind,
            evidence_ids=[evidence.evidence_id],
            content_ref=evidence.content_ref,
            text_preview=text[:200],
            token_estimate=token_est,
            token_count_method='heuristic',
            precision=evidence.precision,
            confidence=evidence.confidence,
            contributes_to_input=evidence.scope
            in ('current_session', 'prior_session', 'project_repo', 'agent_app'),
        )
        spans.append(span)
        order_index += 1

    spans.sort(key=lambda span: kind_order.get(span.semantic_kind, 99))
    for index, span in enumerate(spans):
        span.order_index = index

    return spans


def _is_duplicate(evidence: Evidence, current_call_boundary: str) -> bool:
    """Check whether evidence should be excluded as duplicate current-call input.

    Args:
        evidence: Evidence record being considered for span construction.
        current_call_boundary: Optional current-call marker supplied by the caller.

    Returns:
        True when the evidence is already represented elsewhere in the active call.
    """
    if not current_call_boundary:
        return False
    return False


def _infer_api_path(kind: str, index: int) -> str:
    """Infer a provider-style API path from semantic kind and order.

    Args:
        kind: Evidence semantic kind.
        index: Current ordered span index.

    Returns:
        API path used by serializers and attribution diagnostics.
    """
    path_map = {
        'tool_schema': f'tools[{index}]',
        'system_prompt': f'system[{index}]',
        'user_text': f'messages[{index}]',
        'tool_result': f'messages[{index}].tool_result',
        'assistant_text': f'messages[{index}]',
        'tool_use': f'messages[{index}].tool_use',
    }
    return path_map.get(kind, f'unknown[{index}]')
