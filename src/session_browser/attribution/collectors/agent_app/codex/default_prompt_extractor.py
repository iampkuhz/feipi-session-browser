"""Codex default prompt extractor：提取 Codex 默认 system prompt。

支持 raw request 优先；无 raw request 时 best-effort builtins。
"""

from __future__ import annotations

from session_browser.attribution.core.models import ContentRef, Evidence


def extract_default_prompt(
    session_context: dict | None = None,
    raw_request: str | None = None,
    evidence_counter: int = 0,
) -> Evidence | None:
    """提取 Codex 默认 system prompt。

    优先级：
    1. raw request 中的 system prompt
    2. session_context 中的 local_instructions
    3. heuristic placeholder
    """
    # 策略 1：raw request
    if raw_request:
        preview = raw_request[:200]
        return Evidence(
            evidence_id=f"codex_system_prompt_{evidence_counter}",
            scope="provider_usage",
            kind="system_prompt",
            content_ref=ContentRef(
                kind="inline",
                preview=preview,
                can_load_full=True,
                redaction_applied=True,
            ),
            text_preview=preview,
            precision="extracted",
            confidence=0.85,
        )

    # 策略 2：session context
    if session_context:
        local = session_context.get("local_instructions", "")
        if local:
            return Evidence(
                evidence_id=f"codex_system_prompt_{evidence_counter}",
                scope="project_repo",
                kind="system_prompt",
                content_ref=ContentRef(
                    kind="inline",
                    preview=local[:200],
                    can_load_full=True,
                ),
                text_preview=local[:200],
                precision="extracted",
                confidence=0.7,
            )

    # 策略 3：heuristic
    return Evidence(
        evidence_id=f"codex_system_prompt_{evidence_counter}",
        scope="agent_app",
        kind="system_prompt",
        content_ref=ContentRef(
            kind="unavailable",
            preview="Codex system prompt (heuristic)",
        ),
        text_preview="Codex system prompt (heuristic)",
        precision="heuristic",
        confidence=0.3,
    )
