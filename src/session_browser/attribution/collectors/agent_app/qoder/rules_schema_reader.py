"""Qoder rules schema reader：读取 Qoder 规则 schema。"""

from __future__ import annotations

import logging
from pathlib import Path

from session_browser.attribution.collectors.project.qoder_rules_reader import read_qoder_rules
from session_browser.attribution.core.models import Evidence

logger = logging.getLogger(__name__)


def read_qoder_rules_schema(
    project_dir: str | Path | None = None,
    evidence_counter: int = 0,
) -> list[Evidence]:
    """读取 Qoder 规则作为 agent_app scope 的 Evidence。

    如果 project_dir 未传入，返回空列表（不读真实用户目录）。
    """
    if not project_dir:
        return []

    return read_qoder_rules(project_dir)
