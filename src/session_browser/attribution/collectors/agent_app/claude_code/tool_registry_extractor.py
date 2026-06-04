"""Claude Code tool registry extractor：从已有 schema cache 中提取默认 tools。

输出 Evidence：kind=tool_schema，scope=agent_app。
每个 tool 单独 evidence/span，便于 cache prefix attribution。
"""

from __future__ import annotations

from session_browser.attribution.core.models import ContentRef, Evidence
from session_browser.attribution.agents.claude_code_tool_schemas import (
    ALL_CLAUDE_CODE_TOOLS,
    extract_tool_schemas,
)


def extract_claude_code_tool_registry(
    evidence_counter: int = 0,
) -> list[Evidence]:
    """从 Claude Code tool schema cache 中提取所有默认工具。

    Returns:
        Evidence 列表，每个 tool 一个 Evidence
    """
    # 尝试从 cache 获取 schema
    try:
        schemas = extract_tool_schemas()
    except Exception:
        schemas = {}

    results = []
    for idx, tool_name in enumerate(sorted(ALL_CLAUDE_CODE_TOOLS)):
        schema = schemas.get(tool_name, {})
        schema_str = str(schema)[:300] if schema else ""

        results.append(Evidence(
            evidence_id=f"cc_tool_{evidence_counter + idx}",
            scope="agent_app",
            kind="tool_schema",
            source_path="claude_code_tool_schemas",
            content_ref=ContentRef(
                kind="inline",
                preview=schema_str[:100] if schema_str else tool_name,
                can_load_full=False,
            ),
            text_preview=schema_str[:100] if schema_str else tool_name,
            precision="extracted" if schema else "heuristic",
            confidence=0.85 if schema else 0.5,
            raw_value=schema if schema else None,
        ))

    return results
