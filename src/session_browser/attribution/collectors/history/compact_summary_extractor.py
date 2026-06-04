"""Compact summary 提取器：从 session compact/summary 中提取上下文。"""

from __future__ import annotations

from session_browser.attribution.core.models import ContentRef, Evidence


def extract_compact_summary(
    summary_text: str | None = None,
    summary_data: dict | None = None,
    evidence_counter: int = 0,
) -> Evidence | None:
    """从 compact summary 中提取上下文 Evidence。

    某些 agent（如 Claude Code 的 compact 功能）会压缩前序消息为一个 summary。
    这个 summary 本身占用 input tokens，需要作为 Evidence 记录。

    Args:
        summary_text: compact summary 的文本内容
        summary_data: compact summary 的结构化数据
        evidence_counter: evidence ID 起始计数器

    Returns:
        Evidence 对象，scope=prior_session, kind=compact_summary
    """
    if not summary_text and not summary_data:
        return None

    content = summary_text or str(summary_data)
    preview = content[:200]

    return Evidence(
        evidence_id=f"compact_summary_{evidence_counter}",
        scope="prior_session",
        kind="compact_summary",
        content_ref=ContentRef(
            kind="inline",
            preview=preview,
            can_load_full=True,
        ),
        content_preview=preview,
        token_estimate=len(content) // 4 if content else 0,
        precision="extracted",
        confidence=0.7,
    )
