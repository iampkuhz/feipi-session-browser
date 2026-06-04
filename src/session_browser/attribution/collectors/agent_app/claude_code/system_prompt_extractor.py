"""Claude Code system prompt extractor：提取 Claude Code 默认 system prompt。"""

from __future__ import annotations

from session_browser.attribution.core.models import ContentRef, Evidence


def extract_system_prompt(
    session_context: dict | None = None,
    evidence_counter: int = 0,
) -> Evidence | None:
    """提取 Claude Code 默认 system prompt。

    策略：
    1. 优先从 session_context 中的 system_reminder_content 提取
    2. 其次从 local_instructions（CLAUDE.md）提取
    3. 最后返回 heuristic placeholder

    注意：不可见的 hidden prompt 不能标 exact。
    """
    if session_context:
        # 策略 1：system-reminder（从 transcript 中提取的内置 prompt）
        reminder = session_context.get("system_reminder_content", "")
        if reminder:
            preview = reminder[:200]
            return Evidence(
                evidence_id=f"cc_system_prompt_{evidence_counter}",
                scope="current_session",
                kind="system_prompt",
                content_ref=ContentRef(
                    kind="inline",
                    preview=preview,
                    can_load_full=True,
                ),
                text_preview=preview,
                precision="extracted",
                confidence=0.9,
            )

        # 策略 2：local_instructions
        local = session_context.get("local_instructions", "")
        if local:
            preview = local[:200]
            return Evidence(
                evidence_id=f"cc_system_prompt_{evidence_counter}",
                scope="project_repo",
                kind="system_prompt",
                content_ref=ContentRef(
                    kind="inline",
                    preview=preview,
                    can_load_full=True,
                ),
                text_preview=preview,
                precision="extracted",
                confidence=0.8,
            )

    # 策略 3：heuristic placeholder
    return Evidence(
        evidence_id=f"cc_system_prompt_{evidence_counter}",
        scope="agent_app",
        kind="system_prompt",
        content_ref=ContentRef(
            kind="unavailable",
            preview="Claude Code system prompt (heuristic)",
        ),
        text_preview="Claude Code system prompt (heuristic)",
        precision="heuristic",
        confidence=0.3,
    )
