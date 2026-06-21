"""Read redacted Qoder project configuration for attribution evidence.

Project collectors call this module with an explicit repository path. It probes
known Qoder config files, returns at most one redacted Evidence row, and only
performs local file reads plus debug logging on unreadable or malformed files.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from session_browser.attribution.core.models import ContentRef, Evidence

logger = logging.getLogger(__name__)


def read_qoder_config(project_dir: str | Path) -> Evidence | None:
    """Read the first available Qoder project config as redacted Evidence.

    Project evidence collection calls this after repository discovery. Missing,
    unreadable, or invalid JSON files are treated as absent evidence and logged
    at debug level.

    Args:
        project_dir: Repository root that may contain ``.qoder/config.json`` or
            ``.qoder/settings.json``.

    Returns:
        Redacted config Evidence for the first readable candidate, or ``None``
        when no candidate can be used.
    """
    path = Path(project_dir)

    candidates = [
        path / '.qoder' / 'config.json',
        path / '.qoder' / 'settings.json',
    ]

    for candidate in candidates:
        try:
            if candidate.exists() and candidate.is_file():
                text = candidate.read_text(encoding='utf-8', errors='replace')
                data = json.loads(text)
                safe_data = _redact_config(data)
                return Evidence(
                    evidence_id=f'qoder_config_{candidate.name}',
                    scope='project_repo',
                    kind='agent_config',
                    source_path=str(candidate),
                    content_ref=ContentRef(
                        kind='file_slice',
                        pointer=str(candidate),
                        preview=str(safe_data)[:200],
                        can_load_full=True,
                        redaction_applied=True,
                    ),
                    text_preview=str(safe_data)[:200],
                    precision='extracted',
                    confidence=0.8,
                )
        except (OSError, PermissionError, json.JSONDecodeError) as exc:
            logger.debug('无法读取 Qoder 配置 %s: %s', candidate, exc)

    return None


def _redact_config(data: dict) -> dict:
    """Redact sensitive keys from a parsed Qoder config payload.

    The config reader calls this before storing previews in Evidence. Nested
    dictionaries are copied recursively; other values are preserved.

    Args:
        data: Parsed JSON object from a Qoder config file.

    Returns:
        New dictionary with credential-like values replaced by a marker.
    """
    sensitive_keys = frozenset(
        {
            'api_key',
            'apikey',
            'token',
            'secret',
            'password',
            'authorization',
            'credential',
        }
    )
    result = {}
    for k, v in data.items():
        if k.lower() in sensitive_keys:
            result[k] = '***REDACTED***'
        elif isinstance(v, dict):
            result[k] = _redact_config(v)
        else:
            result[k] = v
    return result
