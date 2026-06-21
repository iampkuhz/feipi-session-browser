"""CLAUDE.md 读取器:从项目目录读取 CLAUDE.md 作为 project context Evidence."""

from __future__ import annotations

import logging
from pathlib import Path

from session_browser.attribution.core.models import ContentRef, Evidence

logger = logging.getLogger(__name__)

_MAX_CLAUDE_MD_SIZE = 4096


def read_claude_md(project_dir: str | Path) -> Evidence | None:
    """读取项目中的 CLAUDE.md 规则文件.

    Args:
        project_dir: 项目根目录, 用于查找仓库级或 `.claude/` 内的
            CLAUDE.md 文件.

    Returns:
        找到规则文件时返回 project context evidence, 否则返回 None.
    """
    path = Path(project_dir)

    candidates = [
        path / 'CLAUDE.md',
        path / '.claude' / 'CLAUDE.md',
    ]

    for candidate in candidates:
        try:
            if candidate.exists() and candidate.is_file():
                text = candidate.read_text(encoding='utf-8', errors='replace')
                text = text[:_MAX_CLAUDE_MD_SIZE]
                return Evidence(
                    evidence_id=f'claude_md_{candidate.name}',
                    scope='project_repo',
                    kind='project_rules',
                    source_path=str(candidate),
                    content_ref=ContentRef(
                        kind='file_slice',
                        pointer=str(candidate),
                        preview=text[:200],
                        can_load_full=True,
                    ),
                    text_preview=text[:200],
                    precision='extracted',
                    confidence=0.95,
                )
        except (OSError, PermissionError) as exc:
            logger.debug('无法读取 %s: %s', candidate, exc)

    return None
