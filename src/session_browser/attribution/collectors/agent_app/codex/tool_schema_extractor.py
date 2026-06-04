"""Codex tool schema extractor：提取 Codex 工具 schema。"""

from __future__ import annotations

from session_browser.attribution.core.models import ContentRef, Evidence

# Codex 已知工具（best-effort）
_CODEX_KNOWN_TOOLS = [
    "bash", "read_file", "write_file", "find", "grep",
]


def extract_tool_schemas(
    evidence_counter: int = 0,
) -> list[Evidence]:
    """提取 Codex 工具 schema。

    Codex 不提供完整 tool schema，使用 heuristic 精度。
    """
    results = []
    for idx, tool_name in enumerate(_CODEX_KNOWN_TOOLS):
        results.append(Evidence(
            evidence_id=f"codex_tool_{evidence_counter + idx}",
            scope="agent_app",
            kind="tool_schema",
            source_path="codex_builtin_tools",
            content_ref=ContentRef(
                kind="inline",
                preview=tool_name,
                can_load_full=False,
            ),
            text_preview=tool_name,
            precision="heuristic",
            confidence=0.4,
        ))

    return results
