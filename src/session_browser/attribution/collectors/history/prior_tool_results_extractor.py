"""前序工具结果提取器：从 prior messages 中提取已完成的 tool_result。"""

from __future__ import annotations

from session_browser.attribution.core.models import ContentRef, Evidence


def extract_prior_tool_results(
    all_messages: list[dict] | list,
    call_boundary_index: int = 0,
    evidence_counter: int = 0,
) -> list[Evidence]:
    """提取当前 LLM call 之前已完成的工具结果。"""
    results = []
    messages = all_messages[:call_boundary_index] if call_boundary_index > 0 else []
    idx = evidence_counter

    for msg in messages:
        if not isinstance(msg, dict):
            continue

        role = msg.get("role", "")
        content = msg.get("content", "")

        if role == "user" and isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    tr_text = _tool_result_to_text(block)
                    tool_use_id = block.get("tool_use_id", "")
                    results.append(Evidence(
                        evidence_id=f"prior_tool_result_{idx}",
                        scope="prior_session",
                        kind="tool_result",
                        source_event_id=tool_use_id,
                        content_ref=ContentRef(
                            kind="session_event",
                            preview=tr_text[:200],
                            can_load_full=True,
                        ),
                        text_preview=tr_text[:200],
                        precision="extracted",
                        confidence=0.9,
                    ))
                    idx += 1

    return results


def _tool_result_to_text(block: dict) -> str:
    content = block.get("content", "")
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                parts.append(item.get("text", ""))
        return "\n".join(parts)
    return str(content) if content else ""
