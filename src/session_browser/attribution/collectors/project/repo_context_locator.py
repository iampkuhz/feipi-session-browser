"""仓库上下文定位器：定位项目仓库根目录和相关上下文。"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def locate_project_dir(
    hint_path: str | Path | None = None,
) -> Path | None:
    """尝试定位项目仓库根目录。

    策略：
    1. 使用传入的 hint_path
    2. 从当前工作目录向上查找，直到找到 .git 目录
    3. 返回 None 如果找不到

    Args:
        hint_path: 提示路径（如 session 中记录的 project_path）

    Returns:
        项目根目录 Path，或 None
    """
    if hint_path:
        p = Path(hint_path)
        if p.is_dir():
            return p.resolve()

    # 从当前工作目录向上查找
    current = Path.cwd()
    for _ in range(10):  # 最多向上 10 层
        if (current / ".git").exists():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent

    return None


def has_project_context(project_dir: Path) -> bool:
    """检查目录是否有项目上下文（存在 CLAUDE.md / AGENTS.md / .qoder/rules）。"""
    if not project_dir or not project_dir.is_dir():
        return False

    indicators = [
        project_dir / "CLAUDE.md",
        project_dir / "AGENTS.md",
        project_dir / ".claude" / "CLAUDE.md",
        project_dir / ".qoder" / "rules",
        project_dir / ".codex" / "AGENTS.md",
    ]

    return any(p.exists() for p in indicators)
