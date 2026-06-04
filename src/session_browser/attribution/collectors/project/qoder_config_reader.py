"""Qoder 配置读取器：读取 .qoder/config.json 等配置。"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from session_browser.attribution.core.models import ContentRef, Evidence

logger = logging.getLogger(__name__)


def read_qoder_config(project_dir: str | Path) -> Evidence | None:
    """读取 Qoder 配置文件。"""
    path = Path(project_dir)

    candidates = [
        path / ".qoder" / "config.json",
        path / ".qoder" / "settings.json",
    ]

    for candidate in candidates:
        try:
            if candidate.exists() and candidate.is_file():
                text = candidate.read_text(encoding="utf-8", errors="replace")
                data = json.loads(text)
                safe_data = _redact_config(data)
                return Evidence(
                    evidence_id=f"qoder_config_{candidate.name}",
                    scope="project_repo",
                    kind="agent_config",
                    source_path=str(candidate),
                    content_ref=ContentRef(
                        kind="file_slice",
                        pointer=str(candidate),
                        preview=str(safe_data)[:200],
                        can_load_full=True,
                        redaction_applied=True,
                    ),
                    text_preview=str(safe_data)[:200],
                    precision="extracted",
                    confidence=0.8,
                )
        except (OSError, PermissionError, json.JSONDecodeError) as exc:
            logger.debug("无法读取 Qoder 配置 %s: %s", candidate, exc)

    return None


def _redact_config(data: dict) -> dict:
    sensitive_keys = frozenset({
        "api_key", "apikey", "token", "secret", "password",
        "authorization", "credential",
    })
    result = {}
    for k, v in data.items():
        if k.lower() in sensitive_keys:
            result[k] = "***REDACTED***"
        elif isinstance(v, dict):
            result[k] = _redact_config(v)
        else:
            result[k] = v
    return result
