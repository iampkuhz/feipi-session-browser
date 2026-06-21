""".qoder/rules 读取器:从项目目录读取 Qoder 规则文件."""

from __future__ import annotations

import logging
from pathlib import Path

from session_browser.attribution.core.models import ContentRef, Evidence

logger = logging.getLogger(__name__)

_MAX_RULE_SIZE = 4096


def read_qoder_rules(project_dir: str | Path) -> list[Evidence]:
    """读取 `.qoder/rules/` 目录下的规则文件.

    Args:
        project_dir: 项目根目录, 用于定位 Qoder rules 目录.

    Returns:
        每个可读 Markdown 规则文件对应一条 local instructions evidence.
    """
    path = Path(project_dir)
    rules_dir = path / '.qoder' / 'rules'

    if not rules_dir.is_dir():
        return []

    results = []
    for rule_file in sorted(rules_dir.glob('*.md')):
        try:
            text = rule_file.read_text(encoding='utf-8', errors='replace')
            text = text[:_MAX_RULE_SIZE]
            results.append(
                Evidence(
                    evidence_id=f'qoder_rule_{rule_file.name}',
                    scope='project_repo',
                    kind='local_instructions',
                    source_path=str(rule_file),
                    content_ref=ContentRef(
                        kind='file_slice',
                        pointer=str(rule_file),
                        preview=text[:200],
                        can_load_full=True,
                    ),
                    text_preview=text[:200],
                    precision='extracted',
                    confidence=0.9,
                )
            )
        except (OSError, PermissionError) as exc:
            logger.debug('无法读取规则文件 %s: %s', rule_file, exc)

    return results
