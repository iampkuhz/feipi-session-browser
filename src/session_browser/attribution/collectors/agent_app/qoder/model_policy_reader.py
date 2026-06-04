"""Qoder model policy reader：读取 Qoder model policy 配置。

不默认读真实用户账号 token，只接受测试 fixture 或显式传入。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from session_browser.attribution.core.models import ContentRef, Evidence

logger = logging.getLogger(__name__)


def read_model_policy(
    policy_path: str | Path | None = None,
    evidence_counter: int = 0,
) -> Evidence | None:
    """读取 Qoder model policy 配置。

    Args:
        policy_path: 显式传入的政策文件路径（测试 fixture）

    Returns:
        Evidence 对象或 None
    """
    if not policy_path:
        return None

    path = Path(policy_path)
    try:
        if not path.exists() or not path.is_file():
            return None

        text = path.read_text(encoding="utf-8", errors="replace")
        data = json.loads(text)
        safe_data = _redact_sensitive(data)

        return Evidence(
            evidence_id=f"qoder_model_policy_{evidence_counter}",
            scope="agent_app",
            kind="model_policy",
            source_path=str(path),
            content_ref=ContentRef(
                kind="file_slice",
                pointer=str(path),
                preview=str(safe_data)[:200],
                can_load_full=True,
                redaction_applied=True,
            ),
            text_preview=str(safe_data)[:200],
            precision="extracted",
            confidence=0.7,
        )
    except (OSError, PermissionError, json.JSONDecodeError) as exc:
        logger.debug("无法读取 model policy %s: %s", path, exc)
        return None


def _redact_sensitive(data: dict) -> dict:
    sensitive = frozenset({"token", "api_key", "secret", "password", "credential"})
    result = {}
    for k, v in data.items():
        if k.lower() in sensitive:
            result[k] = "***REDACTED***"
        elif isinstance(v, dict):
            result[k] = _redact_sensitive(v)
        else:
            result[k] = v
    return result
