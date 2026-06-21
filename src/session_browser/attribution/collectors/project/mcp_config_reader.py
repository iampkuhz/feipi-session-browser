""".mcp.json 读取器:读取 MCP 配置(脱敏后)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from session_browser.attribution.core.models import ContentRef, Evidence

logger = logging.getLogger(__name__)

_SENSITIVE_FIELDS = frozenset(
    {
        'token',
        'apiKey',
        'api_key',
        'secret',
        'password',
        'authorization',
        'credential',
        'env',
    }
)


def read_mcp_config(project_dir: str | Path) -> Evidence | None:
    """读取项目 MCP 配置并生成脱敏 evidence.

    Args:
        project_dir: 项目根目录, 用于定位 `.mcp.json`.

    Returns:
        找到且可解析配置时返回 MCP config evidence, 否则返回 None.
    """
    path = Path(project_dir)
    mcp_path = path / '.mcp.json'

    if not mcp_path.exists() or not mcp_path.is_file():
        return None

    try:
        text = mcp_path.read_text(encoding='utf-8', errors='replace')
        data = json.loads(text)
        safe_data = _redact_mcp_config(data)
        preview_text = str(safe_data)[:200]

        return Evidence(
            evidence_id='mcp_config',
            scope='project_repo',
            kind='mcp_config',
            source_path=str(mcp_path),
            content_ref=ContentRef(
                kind='file_slice',
                pointer=str(mcp_path),
                preview=preview_text,
                can_load_full=True,
                redaction_applied=True,
            ),
            text_preview=preview_text,
            precision='extracted',
            confidence=0.9,
        )
    except (OSError, PermissionError, json.JSONDecodeError) as exc:
        logger.debug('无法读取 MCP 配置 %s: %s', mcp_path, exc)
        return None


def _redact_mcp_config(data: dict) -> dict:
    """脱敏 MCP 配置中的敏感字段.

    Args:
        data: 已解析的 MCP 配置字典.

    Returns:
        保留原结构但替换敏感字段值的新字典.
    """
    result = {}
    for k, v in data.items():
        if k.lower() in _SENSITIVE_FIELDS:
            result[k] = '***MASKED***'
        elif isinstance(v, dict):
            result[k] = _redact_mcp_config(v)
        elif isinstance(v, list):
            result[k] = [_redact_mcp_config(item) if isinstance(item, dict) else item for item in v]
        else:
            result[k] = v
    return result
