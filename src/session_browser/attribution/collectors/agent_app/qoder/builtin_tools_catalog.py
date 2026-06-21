"""Qoder builtin tools catalog：Qoder 工具目录。

Qoder 工具 catalog 不一定有完整 schema。
策略：
- exact schema available -> exact/extracted
- known builtin tool catalog -> estimated with catalog source
- only tool count available -> heuristic
- unknown -> residual / unavailable
"""

from __future__ import annotations

from session_browser.attribution.core.models import ContentRef, Evidence

# Qoder 已知工具列表（best-effort）
_QODER_KNOWN_TOOLS = [
    'Read',
    'Write',
    'Edit',
    'Bash',
    'Glob',
    'Grep',
    'WebFetch',
    'WebSearch',
]


def extract_qoder_builtin_tools(
    evidence_counter: int = 0,
) -> list[Evidence]:
    """提取 Qoder 内置工具 catalog。

    Qoder 不提供完整 tool schema，使用 heuristic 精度。
    """
    results = []
    for idx, tool_name in enumerate(_QODER_KNOWN_TOOLS):
        results.append(
            Evidence(
                evidence_id=f'qoder_tool_{evidence_counter + idx}',
                scope='agent_app',
                kind='tool_schema',
                source_path='qoder_builtin_tools',
                content_ref=ContentRef(
                    kind='inline',
                    preview=tool_name,
                    can_load_full=False,
                ),
                text_preview=tool_name,
                precision='heuristic',  # 不标 exact
                confidence=0.4,
            )
        )

    return results
