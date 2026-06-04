"""Subagent prompt 读取器：读取 .claude/agents/{subagent_type}.md。"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from session_browser.attribution.core.models import ContentRef, Evidence

logger = logging.getLogger(__name__)

_MAX_PROMPT_SIZE = 4096


def read_subagent_prompt(
    project_dir: str | Path,
    subagent_type: str,
    evidence_counter: int = 0,
) -> Evidence | None:
    """读取 subagent 的 prompt 文件。"""
    path = Path(project_dir)
    candidates = [
        path / ".claude" / "agents" / f"{subagent_type}.md",
        path / ".codex" / "agents" / f"{subagent_type}.md",
    ]

    for candidate in candidates:
        try:
            if candidate.exists() and candidate.is_file():
                text = candidate.read_text(encoding="utf-8", errors="replace")
                text = text[:_MAX_PROMPT_SIZE]
                return Evidence(
                    evidence_id=f"subagent_prompt_{evidence_counter}",
                    scope="project_repo",
                    kind="subagent_prompt",
                    source_path=str(candidate),
                    content_ref=ContentRef(
                        kind="file_slice",
                        pointer=str(candidate),
                        preview=text[:200],
                        can_load_full=True,
                    ),
                    text_preview=text[:200],
                    precision="extracted",
                    confidence=0.9,
                )
        except (OSError, PermissionError) as exc:
            logger.debug("无法读取 subagent prompt %s: %s", candidate, exc)

    return None


def parse_tools_from_frontmatter(text: str) -> list[str] | None:
    """从 YAML frontmatter 中解析 tools: 字段。"""
    m = re.match(r'---\s*\n(.*?)\n---\s*\n', text, re.DOTALL)
    if not m:
        return None

    fm = m.group(1)
    tools_match = re.search(r'^tools:\s*(.+)$', fm, re.MULTILINE)
    if not tools_match:
        return None

    tools_str = tools_match.group(1).strip()
    if not tools_str:
        return None

    tools: list[str] = []
    paren_re = re.compile(r'(\w+)\([^)]*\)')
    for pm in paren_re.finditer(tools_str):
        tools.append(pm.group(1))

    remaining = paren_re.sub('', tools_str)
    for part in remaining.split(','):
        part = part.strip()
        if part:
            tools.append(part)

    return sorted(set(tools)) if tools else None
